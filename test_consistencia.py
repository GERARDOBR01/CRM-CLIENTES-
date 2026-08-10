"""Pruebas de consistencia entre los catálogos de campos.

Existen por un bug real: se agregó `contacto` a `CAMPOS_IMPORTABLES` pero no a
`ETIQUETAS`, y la vista «Cargar leads» reventó con KeyError hasta que alguien
la abrió. Estas comprobaciones lo cachan antes.

    python test_consistencia.py
"""

from __future__ import annotations

import itertools
import re
import sys

import db
import importador
import mensajes
import plantillas
import plantillas_gancho as pg
import scoring


def _falla(mensaje: str) -> str:
    print(f"  FALLA  {mensaje}")
    return mensaje


def revisar() -> list[str]:
    errores: list[str] = []

    # 1. Todo campo importable necesita etiqueta legible.
    sin_etiqueta = [c for c in db.CAMPOS_IMPORTABLES if c not in importador.ETIQUETAS]
    if sin_etiqueta:
        errores.append(_falla(f"campos importables sin ETIQUETA: {sin_etiqueta}"))

    # 2. Todo campo importable tiene que existir en el modelo.
    fuera_del_modelo = [c for c in db.CAMPOS_IMPORTABLES if c not in db.CAMPOS]
    if fuera_del_modelo:
        errores.append(_falla(f"campos importables que no están en CAMPOS: {fuera_del_modelo}"))

    # 3. Cada estatus del pipeline necesita probabilidad, orden y peso de score.
    for estatus in db.ESTATUS:
        if estatus not in db.PROBABILIDAD_ESTATUS:
            errores.append(_falla(f"«{estatus}» sin PROBABILIDAD_ESTATUS"))
        if estatus not in scoring.PESOS["etapa"]:
            errores.append(_falla(f"«{estatus}» sin peso en scoring.PESOS['etapa']"))
        if estatus not in scoring.CALENDARIO and estatus not in db.ESTATUS_CERRADOS:
            errores.append(_falla(f"«{estatus}» abierto y sin entrada en scoring.CALENDARIO"))

    # 4. Los estatus a los que apunta la migración v1 deben existir hoy.
    for viejo, nuevo in db.MAPEO_ESTATUS_V1.items():
        if nuevo not in db.ESTATUS:
            errores.append(_falla(f"el mapeo «{viejo}» apunta a «{nuevo}», que no existe"))

    # 5. Los estatus calientes y cerrados tienen que ser estatus reales.
    for estatus in [*db.ESTATUS_CALIENTES, *db.ESTATUS_CERRADOS]:
        if estatus not in db.ESTATUS:
            errores.append(_falla(f"«{estatus}» no está en ESTATUS"))

    # 6. La escalera de plantillas tiene que apuntar a plantillas que existan.
    for nombre in scoring.ESCALERA_PLANTILLAS:
        if nombre not in plantillas.SEGUIMIENTOS:
            errores.append(_falla(f"la escalera usa la plantilla «{nombre}», que no existe"))

    # 7. Los sectores prioritarios tienen que ser sectores del catálogo.
    for sector in db.SECTORES_PRIORITARIOS:
        if sector not in db.SECTORES:
            errores.append(_falla(f"sector prioritario «{sector}» no está en SECTORES"))

    # 8. Las variables de plantilla tienen que ser campos reales del lead.
    for variable in plantillas.VARIABLES:
        if variable != "mi_nombre" and variable not in db.CAMPOS:
            errores.append(_falla(f"la variable {{{variable}}} no corresponde a un campo"))

    # 9. Los campos del generador tienen que estar en el modelo y ser importables.
    for campo in db.CAMPOS_MENSAJE:
        if campo not in db.CAMPOS:
            errores.append(_falla(f"el campo del generador «{campo}» no está en CAMPOS"))
        if campo not in db.CAMPOS_IMPORTABLES:
            errores.append(_falla(f"el campo del generador «{campo}» no es importable"))

    # 10. Cada tipo de dolor y de destinatario necesita etiqueta legible.
    for tipo in db.TIPOS_DOLOR:
        if tipo not in db.ETIQUETAS_TIPO_DOLOR:
            errores.append(_falla(f"«{tipo}» sin ETIQUETAS_TIPO_DOLOR"))
    for tipo in db.TIPOS_DESTINATARIO:
        if tipo not in db.ETIQUETAS_TIPO_DESTINATARIO:
            errores.append(_falla(f"«{tipo}» sin ETIQUETAS_TIPO_DESTINATARIO"))

    return errores


# --------------------------------------------------------------------------- #
# Reglas de tono del generador de mensajes
# --------------------------------------------------------------------------- #
# Salieron de iterar mensajes reales con Gerardo y no son negociables. Se prueban
# sobre TODAS las combinaciones de dolor × destinatario × cuántos hechos se saben,
# porque el caso que rompe siempre es el que nadie miró: el lead del que casi no se
# investigó nada.

# Vocabulario que jamás debe salir en un mensaje. Las reseñas negativas suelen ser
# la mejor evidencia y aun así no se mencionan: a alguien que no te conoce lo ofende
# o lo asusta. Se nombra el problema estructural y él conecta.
PROHIBIDO = [
    r"\bingeniero\b",          # es estudiante, no ingeniero
    r"\brese\w*s? negativ",
    r"\bmalas rese\w*s?\b",
    r"\bquejas?\b",
    r"\bcalificaci\w+\b",
    r"\bestrellas?\b",
    r"\bse quejan\b",
]

# Un cierre sin salida explícita convierte el mensaje en presión. Que sea fácil
# decir que no es justo lo que hace que valga la pena contestar.
SALIDAS = ["no hay problema", "ningún problema", "no pasa nada", "aquí lo dejamos",
           "aquí queda", "sin problema", "gracias de todos modos", "gracias por leerlo",
           "gracias."]


def _leads_de_prueba() -> list[dict]:
    """Un lead por cada combinación de dolor × destinatario × nivel de investigación.

    Los niveles van de "no sé nada de este negocio" a "lo investigué completo", que es
    justo el eje donde el generador puede quedarse sin plantilla.
    """
    niveles = [
        {},
        {"num_resenas": 906},
        {"num_sucursales": 3, "num_resenas": 128},
        {"num_profesionales": 4, "horario_extendido": 1, "num_resenas": 356},
        {"sistema_detectado": "LeadConnector", "canales_detectados": "WhatsApp e Instagram",
         "num_sucursales": 2, "num_resenas": 90, "num_profesionales": 3,
         "horario_extendido": 1, "publico_extranjero": 1, "tratamiento": "Dr. Romero"},
    ]
    casos = []
    lead_id = 1
    for dolor, destinatario, hechos in itertools.product(
        [*db.TIPOS_DOLOR, ""], db.TIPOS_DESTINATARIO, niveles
    ):
        casos.append({"id": lead_id, "negocio": f"Negocio {lead_id}", "tipo_dolor": dolor,
                      "tipo_destinatario": destinatario, **hechos})
        lead_id += 1
    return casos


def revisar_mensajes() -> list[str]:
    errores: list[str] = []

    for problema in mensajes.verificar_catalogo():
        errores.append(_falla(f"catálogo de ganchos — {problema}"))

    casos = _leads_de_prueba()

    for lead in casos:
        for canal in ("whatsapp", "dm"):
            m = mensajes.generar(lead, "Gerardo Barrera", canal=canal)
            etiqueta = f"[{lead['tipo_dolor'] or 'sin dolor'}/{lead['tipo_destinatario']}/{canal}]"

            if not m.texto.strip():
                errores.append(_falla(f"{etiqueta} mensaje vacío — ningún lead se queda sin mensaje"))
                continue
            if not m.dentro_del_limite:
                errores.append(_falla(f"{etiqueta} {m.palabras} palabras, máximo {m.limite}"))
            if re.search(r"\{[a-z_]+\}", m.texto):
                errores.append(_falla(f"{etiqueta} quedó un hueco sin rellenar: {m.texto[:70]}"))
            for patron in PROHIBIDO:
                if re.search(patron, m.texto, re.IGNORECASE):
                    errores.append(_falla(f"{etiqueta} dice algo prohibido ({patron}): {m.texto[:70]}"))
            if not any(s.lower() in m.texto.lower() for s in SALIDAS):
                errores.append(_falla(f"{etiqueta} cierra sin salida explícita: …{m.texto[-60:]}"))
            # Saludo antes del gancho: el prospecto no lo conoce de nada, así que
            # el mensaje nunca puede abrir con el "Vi que…".
            apertura = m.texto[:40].lower()
            if not any(s in apertura for s in ("hola", "buen día", "cómo está")):
                errores.append(_falla(f"{etiqueta} no empieza con saludo: {m.texto[:40]}"))
            if m.texto.startswith("Vi que"):
                errores.append(_falla(f"{etiqueta} abre con el gancho, sin saludar antes"))
            # A recepción se le pide que lo pase, no se le vende. Y ese molde no debe
            # salirse a ningún otro destinatario.
            es_recepcion = any(p in m.texto for p in pg.PETICIONES_RECEPCION)
            if es_recepcion != (lead["tipo_destinatario"] == "recepcion"):
                errores.append(_falla(f"{etiqueta} usa el molde de recepción con quien no toca"))
            if lead["tipo_destinatario"] == "recepcion" and not any(
                a in m.texto for a in pg.ACLARACIONES_RECEPCION
            ):
                errores.append(_falla(f"{etiqueta} a recepción sin aclarar que no es venta ni publicidad"))

    # Todo el outreach habla de USTED. Un primer mensaje de usted seguido de un
    # seguimiento que tutea al mismo prospecto se nota, y con un doctor o el dueño de
    # un negocio ese resbalón cuesta credibilidad. (Pasó: el generador nació de usted
    # y las plantillas de seguimiento venían tuteando.)
    tuteo = re.compile(
        r"\b(t[úu]|te|ti|tus|tienes|quieres|puedes|sabes|dime|av[íi]same|"
        r"escr[íi]beme|contigo|tuyo|tuya)\b",
        re.IGNORECASE,
    )
    for nombre, texto in plantillas.SEGUIMIENTOS.items():
        hallado = tuteo.findall(texto)
        if hallado:
            errores.append(_falla(
                f"la plantilla de seguimiento «{nombre}» tutea ({', '.join(sorted(set(hallado)))}); "
                "el generador habla de usted"
            ))
    if tuteo.findall(plantillas.PLANTILLA_NUEVA):
        errores.append(_falla("PLANTILLA_NUEVA tutea; el resto del outreach habla de usted"))
    for lead in casos[:40]:
        texto = mensajes.generar(lead, "Gerardo Barrera").texto
        hallado = tuteo.findall(texto)
        if hallado:
            errores.append(_falla(f"el generador tuteó ({set(hallado)}): {texto[:80]}"))

    # Ninguna transición debe chocar con el verbo del servicio que la sigue. Salió de
    # un ripio real: "Justo eso es lo que armo: armar un tablero simple…". Como las
    # variantes se combinan por `id`, un choque así aparece solo en algunos leads y
    # es fácil que nadie lo vea hasta que ya se mandó.
    # Se comparan los dos verbos que quedan pegados —el que cierra la transición y el
    # que abre el servicio—, no todas las palabras: comparar todo daba falsos
    # positivos ("trabajo" y "trae" comparten letras y no chocan al oído).
    for transicion in pg.TRANSICIONES:
        verbo_t = re.findall(r"[a-záéíóúñ]+", transicion.lower())[-1]
        for tabla in (pg.SERVICIOS, pg.SERVICIOS_MARKETING):
            for tipo, (servicio, _) in tabla.items():
                verbo_s = re.findall(r"[a-záéíóúñ]+", servicio.lower())[0]
                if verbo_t[:3] == verbo_s[:3]:
                    errores.append(_falla(
                        f"«{transicion} {servicio}» — «{verbo_t}» y «{verbo_s}» son el mismo "
                        "verbo pegado; suena a ripio"
                    ))

    # Reproducible: el mismo lead da siempre el mismo mensaje, incluso entre procesos
    # (por eso el generador usa CRC32 y no el hash() de Python, que lleva sal aleatoria).
    muestra = casos[len(casos) // 2]
    if mensajes.generar(muestra).texto != mensajes.generar(muestra).texto:
        errores.append(_falla("el mismo lead produce mensajes distintos — se perdió la reproducibilidad"))

    # …pero dos leads distintos con los MISMOS datos no deben sonar idénticos.
    base = {"tipo_dolor": "seguimiento_manual", "tipo_destinatario": "dueno", "num_resenas": 906}
    textos = {mensajes.generar({"id": i, "negocio": "X", **base}).texto for i in range(1, 21)}
    if len(textos) < 8:
        errores.append(_falla(
            f"20 leads iguales producen solo {len(textos)} mensajes distintos; se va a notar"
        ))

    return errores


if __name__ == "__main__":
    print("Consistencia de catálogos:")
    fallos = revisar()
    print("Reglas de tono del generador:")
    fallos += revisar_mensajes()
    if fallos:
        print(f"\n{len(fallos)} problema(s).")
        sys.exit(1)
    print("  todo consistente.")
