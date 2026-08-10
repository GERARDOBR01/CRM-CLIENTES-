"""Generador algorítmico de mensajes de primer contacto.

Gerardo no tiene tiempo de redactar un mensaje por lead: el CRM lo arma, él lo revisa
y lo manda. **Nunca se envía solo** — igual que todo lo demás en esta app, el último
clic es suyo.

## Cómo se arma

    1. Saludo        — usa `tratamiento` si existe; si no, "Hola, buen día."
    2. Identidad     — "Soy Gerardo Barrera, estudio Ingeniería en Software…"
    3. Gancho        — la primera plantilla de `plantillas_gancho.GANCHOS[tipo_dolor]`
                       cuyos campos requeridos estén llenos.
    4. Servicio      — 1-2 fragmentos según `tipo_dolor`.
    5. Cierre        — ofrece el diagnóstico y deja una salida explícita.

El fraseo de cada bloque fijo tiene varias variantes y se elige de forma
**determinística según el `id` del lead**: el mismo lead produce siempre el mismo
mensaje (regenerarlo no sorprende a nadie), pero dos leads con el mismo `tipo_dolor`
no suenan idénticos.

## Reglas de tono que el código hace cumplir

- Saludo antes del gancho — el prospecto no lo conoce de nada.
- Sin misterio: se dice directo qué es.
- Nunca se mencionan reseñas negativas ni calificaciones (ver `plantillas_gancho`).
- Nunca se inventan cifras: solo se usan hechos capturados, y los aproximados se
  redondean **hacia abajo** para que "más de N" sea literalmente cierto.
- Nunca el título "Ingeniero" — es estudiante.
- Máximo 90 palabras (50 en DM). El generador recorta solo si se pasa.
- Salida explícita en el cierre.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

import db
import plantillas_gancho as pg

# Huecos de plantilla que no son un campo tal cual, sino una versión derivada de uno.
FUENTE_DEL_HUECO = {"num_resenas_aprox": "num_resenas"}


# --------------------------------------------------------------------------- #
# Elección determinística de variantes
# --------------------------------------------------------------------------- #

def _indice(lead_id: int, sal: str, total: int) -> int:
    """Índice estable para un lead y un bloque dado.

    No usa el `hash()` de Python **a propósito**: el hash de una cadena lleva sal
    aleatoria por proceso, así que el mismo lead daría un mensaje distinto en cada
    arranque de la app. Aquí hace falta lo contrario — regenerar el mensaje de un
    lead tiene que dar exactamente lo mismo.

    Y usa SHA-256 en vez de CRC32 porque CRC32 sobre cadenas casi iguales
    ("saludo:21", "saludo:23") reparte mal los bits bajos: con 25 leads salían
    varios pares con las cuatro variantes idénticas, que es justo lo que se quiere
    evitar.

    >>> _indice(7, "saludo", 4) == _indice(7, "saludo", 4)
    True
    >>> 0 <= _indice(31, "cierre", 4) < 4
    True
    """
    if total <= 1:
        return 0
    digest = hashlib.sha256(f"{sal}:{int(lead_id)}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % total


def _elegir(opciones, lead_id: int, sal: str) -> tuple[str, int]:
    """Devuelve (variante elegida, su índice) para poder registrarla después."""
    i = _indice(lead_id, sal, len(opciones))
    return opciones[i], i


# --------------------------------------------------------------------------- #
# Hechos del lead
# --------------------------------------------------------------------------- #

def _lleno(lead: dict, campo: str) -> bool:
    """¿El lead tiene ese hecho capturado?

    Un entero en `None` es "no lo investigué"; un 0 es "no aplica". Ninguno de los
    dos sirve para armar una frase, así que los dos cuentan como vacío.
    """
    valor = lead.get(campo)
    if valor is None:
        return False
    if campo in db.CAMPOS_ENTEROS:
        return db.entero_o_none(valor) not in (None, 0)
    if campo in db.CAMPOS_BOOLEANOS:
        return db.booleano(valor) == 1
    return bool(str(valor).strip())


def _aprox(n: int) -> int:
    """Redondea hacia abajo a una cifra redonda **estrictamente menor** que `n`.

    Para que "más de 900 reseñas" sea verdad cuando son 906. Dos detalles que
    importan más de lo que parecen:

    - Se redondea hacia abajo, nunca hacia arriba: hacia arriba la frase se vuelve
      una cifra inventada, y eso no se hace.
    - Si el redondeo cae justo en `n`, baja un escalón más — con 90 reseñas, "más de
      90" sería falso por un pelo, y un prospecto que lo note deja de creer el resto.

    >>> [_aprox(n) for n in (906, 356, 224, 118, 100, 90, 61, 43)]
    [900, 350, 200, 100, 90, 80, 60, 40]
    >>> all(_aprox(n) < n for n in range(20, 2000))
    True
    """
    if n < 20:
        return n
    paso = 500 if n >= 1000 else 50 if n >= 100 else 10
    valor = n // paso * paso
    if valor >= n:
        valor -= 10 if paso > 10 else paso
    return valor


def _valores(lead: dict) -> dict:
    """Los hechos del lead listos para meter en una plantilla."""
    datos = {c: str(lead.get(c) or "").strip() for c in db.CAMPOS_MENSAJE}
    for campo in db.CAMPOS_ENTEROS:
        n = db.entero_o_none(lead.get(campo))
        datos[campo] = str(n) if n else ""
    resenas = db.entero_o_none(lead.get("num_resenas"))
    datos["num_resenas_aprox"] = str(_aprox(resenas)) if resenas else ""
    return datos


def elegir_gancho(lead: dict) -> tuple[str, int]:
    """La primera plantilla de su `tipo_dolor` que se pueda llenar.

    Devuelve (texto ya rellenado, índice de la plantilla). Como la última plantilla de
    cada dolor no requiere nada, **siempre** hay gancho. Si el lead ni siquiera tiene
    `tipo_dolor`, devuelve ("", -1) y el que llama decide qué hacer.
    """
    plantillas = pg.GANCHOS.get(str(lead.get("tipo_dolor") or ""))
    if not plantillas:
        return "", -1

    valores = _valores(lead)
    for i, plantilla in enumerate(plantillas):
        requeridos = plantilla.get("requiere", ())
        if not all(_lleno(lead, campo) for campo in requeridos):
            continue
        minimos = plantilla.get("min", {})
        if any(
            (db.entero_o_none(lead.get(campo)) or 0) < tope for campo, tope in minimos.items()
        ):
            continue
        return plantilla["texto"].format(**valores), i
    return "", -1


# --------------------------------------------------------------------------- #
# El mensaje
# --------------------------------------------------------------------------- #

def contar_palabras(texto: str) -> int:
    """>>> contar_palabras("Hola, buen día.  Soy Gerardo.")
    5
    """
    return len(texto.split())


@dataclass
class Mensaje:
    """Un mensaje generado, con la traza de cómo se armó.

    La traza no es adorno: es lo que después permite saber **qué tipo de mensaje
    funciona**. Se guarda en el historial al enviarlo y alimenta la tasa de respuesta
    por `tipo_dolor` en 📊 Métricas.
    """

    texto: str
    canal: str                       # "whatsapp" | "dm"
    tipo_dolor: str = ""
    tipo_destinatario: str = "desconocido"
    gancho_idx: int = -1
    variantes: dict[str, int] = field(default_factory=dict)
    recortes: list[str] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)

    @property
    def palabras(self) -> int:
        return contar_palabras(self.texto)

    @property
    def limite(self) -> int:
        return pg.MAX_PALABRAS_DM if self.canal == "dm" else pg.MAX_PALABRAS

    @property
    def dentro_del_limite(self) -> bool:
        return self.palabras <= self.limite

    def firma(self) -> str:
        """Marca compacta para el historial: qué dolor y qué combinación de variantes.

        Formato: `[gen] canal · tipo_dolor · g<N> · v<a-b-c>`. El prefijo `[gen]` es
        lo que `metricas.py` busca para separar los envíos generados de los escritos
        a mano.

        >>> Mensaje("x", "whatsapp", "sin_datos", gancho_idx=2,
        ...         variantes={"saludo": 1, "cierre": 3}).firma()
        '[gen] whatsapp · sin_datos · g2 · v1-3'
        """
        combo = "-".join(str(v) for v in self.variantes.values())
        dolor = self.tipo_dolor or "sin_clasificar"
        return f"[gen] {self.canal} · {dolor} · g{self.gancho_idx} · v{combo}"


def _saludo(lead: dict, lead_id: int) -> tuple[str, int]:
    tratamiento = str(lead.get("tratamiento") or "").strip().rstrip(",.")
    if tratamiento:
        plantilla, i = _elegir(pg.SALUDOS_CON_TRATAMIENTO, lead_id, "saludo")
        return plantilla.format(tratamiento=tratamiento), i
    return _elegir(pg.SALUDOS_SIN_TRATAMIENTO, lead_id, "saludo")


def _unir(partes) -> str:
    """Pega los bloques en un párrafo, sin espacios dobles ni bloques vacíos."""
    return " ".join(p.strip() for p in partes if p and p.strip())


def generar(lead: dict, mi_nombre: str = "Gerardo Barrera", canal: str = "whatsapp") -> Mensaje:
    """Arma el mensaje de primer contacto de un lead.

    `canal="dm"` produce la versión de 50 palabras para Instagram y similares: sin
    detallar servicios, porque eso va en la respuesta si contesta.
    """
    lead_id = int(lead.get("id") or 0)
    tipo_dolor = str(lead.get("tipo_dolor") or "")
    destinatario = str(lead.get("tipo_destinatario") or "desconocido")
    if destinatario not in db.TIPOS_DESTINATARIO:
        destinatario = "desconocido"

    faltantes = []
    if not tipo_dolor:
        faltantes.append("tipo_dolor")

    gancho, gancho_idx = elegir_gancho(lead)
    variantes: dict[str, int] = {}

    saludo, i_saludo = _saludo(lead, lead_id)
    variantes["saludo"] = i_saludo
    identidad, i_identidad = _elegir(pg.IDENTIDADES, lead_id, "identidad")
    identidad = identidad.format(mi_nombre=mi_nombre)
    variantes["identidad"] = i_identidad

    if destinatario == "recepcion":
        return _armar_recepcion(lead_id, saludo, identidad, tipo_dolor, variantes, faltantes)

    if canal == "dm":
        return _armar_dm(lead_id, saludo, gancho, tipo_dolor, destinatario,
                         gancho_idx, variantes, faltantes)

    # `marketing` habla de captación; el resto usa la versión de negocio, que es la
    # neutra y la que aplica también cuando no se sabe quién contesta.
    tabla = pg.SERVICIOS_MARKETING if destinatario == "marketing" else pg.SERVICIOS
    servicios = tabla.get(tipo_dolor)

    transicion, i_transicion = _elegir(pg.TRANSICIONES, lead_id, "transicion")
    variantes["transicion"] = i_transicion
    cierre, i_cierre = _elegir(pg.CIERRES, lead_id, "cierre")
    variantes["cierre"] = i_cierre

    recortes: list[str] = []

    def _cuerpo(con_segundo_servicio: bool, cierre_texto: str) -> str:
        if not servicios:
            return _unir([saludo, identidad, gancho, cierre_texto])
        bloque = f"{transicion} {servicios[0]}"
        if con_segundo_servicio:
            bloque += f", y {servicios[1]}"
        return _unir([saludo, identidad, gancho, bloque + ".", cierre_texto])

    texto = _cuerpo(True, cierre)

    # Degradación por longitud: primero se suelta el segundo servicio (es el bloque
    # menos esencial), después se acorta el cierre. La salida explícita del cierre
    # nunca se toca: es regla de tono, no relleno.
    if contar_palabras(texto) > pg.MAX_PALABRAS:
        texto = _cuerpo(False, cierre)
        recortes.append("segundo servicio")
    if contar_palabras(texto) > pg.MAX_PALABRAS:
        cierre_corto = pg.CIERRES_CORTOS[i_cierre]
        texto = _cuerpo(False, cierre_corto)
        recortes.append("cierre corto")

    return Mensaje(
        texto=texto, canal="whatsapp", tipo_dolor=tipo_dolor,
        tipo_destinatario=destinatario, gancho_idx=gancho_idx,
        variantes=variantes, recortes=recortes, faltantes=faltantes,
    )


def _armar_dm(lead_id, saludo, gancho, tipo_dolor, destinatario, gancho_idx,
              variantes, faltantes) -> Mensaje:
    """Versión de 50 palabras: saludo + gancho + una línea de oferta + cierre.

    Sin identidad larga ni detalle de servicios — en un DM eso no se lee, y además no
    cabe. Lo que importa es que se entienda qué es y que sea fácil contestar.
    """
    oferta, i_oferta = _elegir(pg.OFERTAS_DM, lead_id, "oferta_dm")
    variantes["oferta_dm"] = i_oferta
    cierre, i_cierre = _elegir(pg.CIERRES_DM, lead_id, "cierre_dm")
    variantes["cierre_dm"] = i_cierre

    texto = _unir([saludo, gancho, oferta, cierre])
    recortes = []
    if contar_palabras(texto) > pg.MAX_PALABRAS_DM:
        texto = _unir([saludo, gancho, cierre])
        recortes.append("línea de oferta")

    return Mensaje(
        texto=texto, canal="dm", tipo_dolor=tipo_dolor,
        tipo_destinatario=destinatario, gancho_idx=gancho_idx,
        variantes=variantes, recortes=recortes, faltantes=faltantes,
    )


def _armar_recepcion(lead_id, saludo, identidad, tipo_dolor, variantes, faltantes) -> Mensaje:
    """Mensaje para quien contesta pero no decide.

    **No se le vende a recepción.** El único objetivo es que el mensaje llegue a quien
    sí decide, así que se pide explícito y se aclara qué NO es — que es exactamente lo
    que recepción filtra todo el día. Sin gancho del dolor operativo: ese argumento es
    para el dueño, y aquí solo estorba y alarga.
    """
    peticion, i_peticion = _elegir(pg.PETICIONES_RECEPCION, lead_id, "peticion")
    variantes["peticion"] = i_peticion
    aclaracion, i_aclaracion = _elegir(pg.ACLARACIONES_RECEPCION, lead_id, "aclaracion")
    variantes["aclaracion"] = i_aclaracion
    cierre, i_cierre = _elegir(pg.CIERRES_RECEPCION, lead_id, "cierre_recepcion")
    variantes["cierre_recepcion"] = i_cierre

    servicios = pg.SERVICIOS.get(tipo_dolor)
    que_hago = f"{aclaracion} Ayudo a {servicios[0]}." if servicios else \
        f"{aclaracion} Ayudo a ordenar la parte operativa de negocios como el suyo."

    texto = _unir([saludo, identidad, que_hago, peticion, cierre])
    return Mensaje(
        texto=texto, canal="whatsapp", tipo_dolor=tipo_dolor,
        tipo_destinatario="recepcion", gancho_idx=-1,
        variantes=variantes, faltantes=faltantes,
    )


# --------------------------------------------------------------------------- #
# Integridad del catálogo
# --------------------------------------------------------------------------- #

def verificar_catalogo() -> list[str]:
    """Revisa las invariantes del catálogo. Lista vacía = todo bien.

    La que más importa: cada `tipo_dolor` tiene que terminar en una plantilla sin
    campos requeridos, o habrá leads sin mensaje y nadie se va a enterar hasta que
    Gerardo abra el detalle y encuentre el hueco.
    """
    problemas = []
    for tipo in db.TIPOS_DOLOR:
        plantillas = pg.GANCHOS.get(tipo)
        if not plantillas:
            problemas.append(f"{tipo}: no tiene ganchos en plantillas_gancho.GANCHOS")
            continue
        if plantillas[-1].get("requiere"):
            problemas.append(
                f"{tipo}: la última plantilla exige {plantillas[-1]['requiere']}; "
                "tiene que haber una sin requisitos o algunos leads se quedan sin mensaje"
            )
        campos_conocidos = set(db.CAMPOS_MENSAJE)
        for i, p in enumerate(plantillas):
            exigidos = set(p.get("requiere", ()))
            for etiqueta, conjunto in (("requiere", exigidos), ("min", set(p.get("min", {})))):
                desconocidos = conjunto - campos_conocidos
                if desconocidos:
                    problemas.append(
                        f"{tipo}[{i}]: '{etiqueta}' menciona campos inexistentes {sorted(desconocidos)}"
                    )
            # Cada {hueco} tiene que existir y estar exigido. Si no existe, revienta
            # con KeyError justo al generar el mensaje; si existe pero no se exige,
            # tarde o temprano algún lead lo recibe vacío y la frase queda coja.
            for hueco in sorted(set(re.findall(r"\{([a-z_]+)\}", p["texto"]))):
                campo = FUENTE_DEL_HUECO.get(hueco, hueco)
                if campo not in campos_conocidos:
                    problemas.append(f"{tipo}[{i}]: el hueco {{{hueco}}} no corresponde a un campo")
                elif campo not in exigidos:
                    problemas.append(
                        f"{tipo}[{i}]: usa {{{hueco}}} sin exigir '{campo}' en 'requiere'"
                    )
        if tipo not in pg.SERVICIOS:
            problemas.append(f"{tipo}: no tiene servicio en plantillas_gancho.SERVICIOS")
        if tipo not in pg.SERVICIOS_MARKETING:
            problemas.append(f"{tipo}: no tiene servicio en SERVICIOS_MARKETING")

    bloques = {
        "SALUDOS_SIN_TRATAMIENTO": pg.SALUDOS_SIN_TRATAMIENTO,
        "SALUDOS_CON_TRATAMIENTO": pg.SALUDOS_CON_TRATAMIENTO,
        "IDENTIDADES": pg.IDENTIDADES,
        "TRANSICIONES": pg.TRANSICIONES,
        "CIERRES": pg.CIERRES,
        "CIERRES_CORTOS": pg.CIERRES_CORTOS,
        "OFERTAS_DM": pg.OFERTAS_DM,
        "CIERRES_DM": pg.CIERRES_DM,
        "PETICIONES_RECEPCION": pg.PETICIONES_RECEPCION,
        "ACLARACIONES_RECEPCION": pg.ACLARACIONES_RECEPCION,
        "CIERRES_RECEPCION": pg.CIERRES_RECEPCION,
    }
    for nombre, variantes in bloques.items():
        if len(variantes) < 3:
            problemas.append(f"{nombre}: solo {len(variantes)} variantes; se notan los repetidos")

    # `CIERRES_CORTOS` se indexa con el mismo índice que `CIERRES` al degradar.
    if len(pg.CIERRES) != len(pg.CIERRES_CORTOS):
        problemas.append("CIERRES y CIERRES_CORTOS deben tener el mismo número de variantes")

    return problemas


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
    print("catálogo:", verificar_catalogo() or "OK")
