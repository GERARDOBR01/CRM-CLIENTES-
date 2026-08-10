"""Carga de leads desde archivos .xlsx / .csv que Gerardo arme por su cuenta.

Sirve tanto para el seed inicial (`leads_tracker.xlsx`) como para cualquier archivo
nuevo de investigacion. La regla es no bloquear la carga por columnas faltantes: lo que
falte se deja vacio y se marca para completar despues desde la app.
"""

from __future__ import annotations

import io
import unicodedata
from pathlib import Path

import pandas as pd

import db

# Columnas que espera el formato de carga. Solo `negocio` es obligatoria.
COLUMNAS_ESPERADAS = list(db.CAMPOS_IMPORTABLES)
OBLIGATORIAS = ["negocio"]

# Etiquetas legibles para la vista previa.
ETIQUETAS = {
    "negocio": "Negocio",
    "contacto": "Persona de contacto",
    "categoria": "Categoría",
    "sector": "Sector",
    "direccion": "Dirección",
    "telefono": "Teléfono",
    "plataforma": "Plataforma",
    "evidencia_dolor": "Evidencia de dolor",
    "mensaje_plantilla": "Mensaje plantilla",
    "track_recomendado": "Track recomendado",
    "senales_investigacion": "Señales de investigación",
    "valor_estimado": "Valor estimado (MXN)",
    # Generador de mensajes (6.5). Se capturan tecleando números y marcando
    # casillas: nada de aquí se redacta.
    "tipo_dolor": "Tipo de dolor",
    "tipo_destinatario": "A quién se le escribe",
    "tratamiento": "Tratamiento (Dr., Mtra.…)",
    "num_sucursales": "N.º de sucursales",
    "num_resenas": "N.º de reseñas",
    "num_profesionales": "N.º de profesionales",
    "sistema_detectado": "Sistema detectado",
    "canales_detectados": "Canales detectados",
    "horario_extendido": "Horario extendido",
    "publico_extranjero": "Público extranjero",
}

def etiqueta(campo: str) -> str:
    """Nombre legible de un campo. Si alguien agrega un campo importable y olvida
    su etiqueta, devuelve el nombre técnico en vez de tumbar la vista con KeyError."""
    return ETIQUETAS.get(campo, campo.replace("_", " ").capitalize())


ESTADO_NUEVO = "🟢 Nuevo"
ESTADO_SIN_MENSAJE = "🟡 Nuevo · falta mensaje"
ESTADO_DUPLICADO = "⚪ Duplicado (ya existe)"
ESTADO_REPETIDO = "⚪ Repetido dentro del archivo"
ESTADO_SIN_NEGOCIO = "🔴 Sin negocio (se omite)"

ESTADOS_INSERTABLES = {ESTADO_NUEVO, ESTADO_SIN_MENSAJE}


def _norm(texto) -> str:
    """minusculas, sin acentos, sin signos — para comparar encabezados."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in sin_acentos.lower() if c.isalnum())


# Encabezado normalizado (por substring) -> campo del modelo. El orden importa:
# gana la primera regla que coincida.
REGLAS = [
    ("negocio", "negocio"),
    ("nombre", "negocio"),
    ("sector", "sector"),
    ("categoria", "categoria"),
    ("giro", "categoria"),
    ("direccion", "direccion"),
    ("telefono", "telefono"),
    ("whatsapp", "telefono"),
    ("celular", "telefono"),
    # `tipo de dolor` antes que `dolor`: si no, "Tipo de dolor" caería en
    # evidencia_dolor y el generador se quedaría sin clasificación en silencio.
    ("tipodedolor", "tipo_dolor"),
    ("tipodolor", "tipo_dolor"),
    ("evidencia", "evidencia_dolor"),
    ("dolor", "evidencia_dolor"),
    # `canales detectados` antes que `canal`, que mapea a plataforma.
    ("canalesdetectados", "canales_detectados"),
    ("canales", "canales_detectados"),
    ("plataforma", "plataforma"),
    ("canal", "plataforma"),
    ("track", "track_recomendado"),
    ("senales", "senales_investigacion"),
    ("senal", "senales_investigacion"),
    ("investigacion", "senales_investigacion"),
    ("mensaje", "mensaje_plantilla"),
    ("plantilla", "mensaje_plantilla"),
    # Generador de mensajes (6.5).
    ("destinatario", "tipo_destinatario"),
    ("aquien", "tipo_destinatario"),
    ("tratamiento", "tratamiento"),
    ("sucursales", "num_sucursales"),
    ("sucursal", "num_sucursales"),
    ("resenas", "num_resenas"),
    ("profesionales", "num_profesionales"),
    ("sistema", "sistema_detectado"),
    ("horario", "horario_extendido"),
    ("extranjero", "publico_extranjero"),
    ("valor", "valor_estimado"),
]


def mapear_encabezados(columnas) -> dict[str, str]:
    """{columna_original: campo_del_modelo} para las columnas reconocidas."""
    exactas = {_norm(c): c for c in COLUMNAS_ESPERADAS}
    mapa: dict[str, str] = {}
    usados: set[str] = set()
    for col in columnas:
        if col is None:
            continue
        clave = _norm(col)
        if not clave:
            continue
        # Coincidencia exacta primero: un encabezado que ya viene con el nombre del
        # campo ("mensaje_plantilla") no debe caer en una regla por substring.
        if clave in exactas and exactas[clave] not in usados:
            mapa[col] = exactas[clave]
            usados.add(exactas[clave])
            continue
        for patron, campo in REGLAS:
            if patron in clave and campo not in usados:
                mapa[col] = campo
                usados.add(campo)
                break
    return mapa


def leer_archivo(archivo, nombre: str | None = None) -> pd.DataFrame:
    """Lee un .xlsx o .csv (ruta, bytes o UploadedFile de Streamlit) como DataFrame."""
    nombre = nombre or getattr(archivo, "name", str(archivo))
    extension = Path(str(nombre)).suffix.lower()

    if extension in (".xlsx", ".xlsm", ".xls"):
        hojas = pd.read_excel(archivo, sheet_name=None, dtype=str)
        if not hojas:
            raise ValueError("El archivo de Excel no tiene hojas.")
        # Si trae una pestaña llamada "Leads" se usa esa; si no, la primera con datos.
        for titulo, hoja in hojas.items():
            if _norm(titulo) == "leads" and not hoja.dropna(how="all").empty:
                return hoja
        for hoja in hojas.values():
            if not hoja.dropna(how="all").empty:
                return hoja
        return next(iter(hojas.values()))

    if extension == ".csv":
        datos = archivo.read() if hasattr(archivo, "read") else Path(archivo).read_bytes()
        if isinstance(datos, str):
            datos = datos.encode("utf-8")
        for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                # sep=None + engine python => detecta solo si es coma o punto y coma.
                return pd.read_csv(
                    io.BytesIO(datos), dtype=str, sep=None, engine="python", encoding=codificacion
                )
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        raise ValueError("No pude leer el CSV: revisa la codificación o el separador.")

    raise ValueError(f"Formato no soportado: '{extension or nombre}'. Usa .xlsx o .csv.")


def preparar(df_crudo: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Normaliza columnas, rellena las que falten y clasifica cada fila.

    Devuelve (df_preparado, reporte). El df incluye una columna `_estado` con el
    resultado de la deduplicacion.
    """
    mapa = mapear_encabezados(df_crudo.columns)
    reconocidas = set(mapa.values())
    faltantes = [c for c in COLUMNAS_ESPERADAS if c not in reconocidas]
    ignoradas = [str(c) for c in df_crudo.columns if c not in mapa]

    if "negocio" not in reconocidas:
        raise ValueError(
            "El archivo no tiene una columna de negocio reconocible. "
            f"Columnas encontradas: {', '.join(str(c) for c in df_crudo.columns)}"
        )

    df = df_crudo.rename(columns=mapa)
    # Si el archivo repite un encabezado, pandas deja columnas duplicadas: nos
    # quedamos con la primera para que `df[campo]` no devuelva un DataFrame.
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[[c for c in COLUMNAS_ESPERADAS if c in df.columns]].copy()

    for campo in COLUMNAS_ESPERADAS:
        if campo not in df.columns:
            df[campo] = ""
    df = df[COLUMNAS_ESPERADAS]

    # Limpieza de texto: NaN -> "", espacios de sobra fuera.
    for campo in COLUMNAS_ESPERADAS:
        df[campo] = df[campo].fillna("").astype(str).str.strip()
        df.loc[df[campo].str.lower().isin(["nan", "none", "-"]), campo] = ""

    df["plataforma"] = df["plataforma"].map(_plataforma_canonica)
    df["sector"] = df["sector"].map(_sector_canonico)
    df["tipo_dolor"] = df["tipo_dolor"].map(_tipo_dolor_canonico)
    df["tipo_destinatario"] = df["tipo_destinatario"].map(_tipo_destinatario_canonico)

    # Deduplicacion contra la base y dentro del propio archivo.
    existentes = db.claves_existentes()
    vistas: set[tuple[str, str]] = set()
    estados = []
    for _, fila in df.iterrows():
        if not fila["negocio"]:
            estados.append(ESTADO_SIN_NEGOCIO)
            continue
        clave = db.clave_dedup(fila["negocio"], fila["telefono"])
        if clave in existentes:
            estados.append(ESTADO_DUPLICADO)
        elif clave in vistas:
            estados.append(ESTADO_REPETIDO)
        else:
            vistas.add(clave)
            estados.append(ESTADO_NUEVO if fila["mensaje_plantilla"] else ESTADO_SIN_MENSAJE)

    df["_estado"] = estados

    reporte = {
        "filas": len(df),
        "nuevos": int((df["_estado"] == ESTADO_NUEVO).sum()),
        "sin_mensaje": int((df["_estado"] == ESTADO_SIN_MENSAJE).sum()),
        "duplicados": int((df["_estado"] == ESTADO_DUPLICADO).sum()),
        "repetidos": int((df["_estado"] == ESTADO_REPETIDO).sum()),
        "sin_negocio": int((df["_estado"] == ESTADO_SIN_NEGOCIO).sum()),
        "columnas_faltantes": faltantes,
        "columnas_ignoradas": ignoradas,
    }
    reporte["insertables"] = reporte["nuevos"] + reporte["sin_mensaje"]
    return df, reporte


def _sector_canonico(valor: str) -> str:
    """Mapea el sector a uno de los conocidos. Si falta o no se reconoce: 'Otro'.

    Acepta variantes sueltas ("gym", "gimnasio", "fisio", "nutriologa", "resto").
    """
    texto = str(valor or "").strip()
    if not texto:
        return "Otro"
    clave = _norm(texto)
    for sector in db.SECTORES:
        # "Fitness/Gym" -> compara contra "fitness" y "gym" por separado
        for parte in [_norm(p) for p in sector.split("/")]:
            if parte and parte in clave:
                return sector
    alias = {
        "gimnasio": "Fitness/Gym", "gym": "Fitness/Gym", "crossfit": "Fitness/Gym",
        "fisio": "Fisioterapia", "rehabilitacion": "Fisioterapia",
        "nutri": "Nutrición", "nutriologa": "Nutrición", "nutriologo": "Nutrición",
        "resto": "Restaurantes", "restaurant": "Restaurantes", "taqueria": "Restaurantes",
        "cafe": "Restaurantes", "dentista": "Dental", "odonto": "Dental", "clinica": "Dental",
    }
    for patron, sector in alias.items():
        if patron in clave:
            return sector
    return "Otro"


def _tipo_dolor_canonico(valor: str) -> str:
    """Mapea el tipo de dolor al enum. Lo que no se reconozca queda vacío.

    Vacío es correcto aquí: significa "sin clasificar", y el detalle del lead lo
    marca para que Gerardo lo elija. Meterlo a la fuerza en una categoría produciría
    un gancho que no corresponde al negocio.

    >>> _tipo_dolor_canonico("Canales sin unificar")
    'canales_sin_unificar'
    >>> _tipo_dolor_canonico("multisede"), _tipo_dolor_canonico("lo que sea")
    ('multisede_sin_visibilidad', '')
    """
    clave = _norm(valor)
    if not clave:
        return ""
    for tipo in db.TIPOS_DOLOR:
        if _norm(tipo) == clave:
            return tipo
    alias = {
        "canales": "canales_sin_unificar", "unificar": "canales_sin_unificar",
        "seguimiento": "seguimiento_manual", "manual": "seguimiento_manual",
        "datos": "sin_datos", "medir": "sin_datos",
        "repetitivos": "procesos_repetitivos", "automatizar": "procesos_repetitivos",
        "multisede": "multisede_sin_visibilidad", "sucursales": "multisede_sin_visibilidad",
    }
    for patron, tipo in alias.items():
        if patron in clave:
            return tipo
    return ""


def _tipo_destinatario_canonico(valor: str) -> str:
    """Mapea a quién se le escribe. Lo desconocido cae en 'desconocido', que usa la
    versión neutra del mensaje.

    >>> _tipo_destinatario_canonico("Dueño"), _tipo_destinatario_canonico("")
    ('dueno', 'desconocido')
    >>> _tipo_destinatario_canonico("recepción")
    'recepcion'
    """
    clave = _norm(valor)
    if not clave:
        return "desconocido"
    for tipo in db.TIPOS_DESTINATARIO:
        if _norm(tipo) == clave:
            return tipo
    alias = {
        "dueno": "dueno", "socio": "dueno", "propietario": "dueno", "gerente": "dueno",
        "doctor": "doctor", "doctora": "doctor", "dr": "doctor", "medico": "doctor",
        "recepcion": "recepcion", "front": "recepcion", "asistente": "recepcion",
        "marketing": "marketing", "mercadotecnia": "marketing", "publicidad": "marketing",
    }
    for patron, tipo in alias.items():
        if patron in clave:
            return tipo
    return "desconocido"


def _plataforma_canonica(valor: str) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return "WhatsApp"
    clave = _norm(texto)
    for p in db.PLATAFORMAS:
        if _norm(p) in clave:
            return p
    return "Otro"


def insertar(df_preparado: pd.DataFrame) -> dict:
    """Inserta las filas marcadas como nuevas. Devuelve el resumen final."""
    a_insertar = df_preparado[df_preparado["_estado"].isin(ESTADOS_INSERTABLES)]
    registros = a_insertar[COLUMNAS_ESPERADAS].to_dict("records")
    for reg in registros:
        reg["estatus"] = "Sin contactar"

    creados = db.crear_leads_lote(registros)
    return {
        "agregados": creados,
        "duplicados": int((df_preparado["_estado"] == ESTADO_DUPLICADO).sum())
        + int((df_preparado["_estado"] == ESTADO_REPETIDO).sum()),
        "sin_mensaje": int((a_insertar["_estado"] == ESTADO_SIN_MENSAJE).sum()),
        "sin_negocio": int((df_preparado["_estado"] == ESTADO_SIN_NEGOCIO).sum()),
    }


def plantilla_csv() -> bytes:
    """CSV vacio con los encabezados esperados, para armar archivos nuevos."""
    ejemplo = pd.DataFrame(
        [
            {
                "negocio": "Gimnasio Ejemplo",
                "categoria": "Gimnasio de barrio",
                "sector": "Fitness/Gym",
                "direccion": "Av. Siempre Viva 123, Guadalajara",
                "telefono": "+52 33 1234 5678",
                "plataforma": "WhatsApp",
                "evidencia_dolor": "Reseñas mencionan que no contestan los mensajes de Instagram.",
                "mensaje_plantilla": "Hola! Soy {mi_nombre} — ayudo a negocios como {negocio} a…",
                "track_recomendado": "Unificar puertas de entrada",
                "senales_investigacion": "4.2★ · 120 reseñas · 2 sucursales",
                "valor_estimado": 4000,
                # Los campos del generador: números y sí/no, nada que redactar.
                "tipo_dolor": "canales_sin_unificar",
                "tipo_destinatario": "dueno",
                "tratamiento": "",
                "num_sucursales": 2,
                "num_resenas": 120,
                "num_profesionales": "",
                "sistema_detectado": "app de reservas propia",
                "canales_detectados": "WhatsApp e Instagram",
                "horario_extendido": "sí",
                "publico_extranjero": "no",
            }
        ],
        columns=COLUMNAS_ESPERADAS,
    )
    return ejemplo.to_csv(index=False).encode("utf-8-sig")


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
