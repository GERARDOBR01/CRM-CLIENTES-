"""Capa de datos del CRM de leads: SQLite local, sin servicios externos.

Todo vive en un solo archivo `leads.db` junto a este modulo (se puede mover con
la variable de entorno LEADS_DB).
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import config

DB_PATH = config.ruta_db()

# --------------------------------------------------------------------------- #
# Pipeline de ventas
# --------------------------------------------------------------------------- #
# El orden de la lista ES el orden del embudo: un lead solo avanza, nunca retrocede
# por mandar un seguimiento (ver `avanzar_estatus`).
ESTATUS = [
    "Sin contactar",
    "Contactado",
    "Diagnóstico enviado",
    "Diagnóstico visto",
    "Interesado",
    "Propuesta enviada",
    "Negociación",
    "Cerrado - Ganado",
    "Cerrado - Perdido",
]

ORDEN_ESTATUS = {e: i for i, e in enumerate(ESTATUS)}

# Estatus que ya no requieren seguimiento automatico.
ESTATUS_CERRADOS = {"Cerrado - Ganado", "Cerrado - Perdido"}

# Estatus "calientes": hay interes demostrado y dejarlos enfriar es el error caro.
ESTATUS_CALIENTES = ["Diagnóstico visto", "Interesado", "Propuesta enviada", "Negociación"]

# Probabilidad de cierre por etapa, para el pipeline ponderado.
PROBABILIDAD_ESTATUS = {
    "Sin contactar": 0.02,
    "Contactado": 0.05,
    "Diagnóstico enviado": 0.15,
    "Diagnóstico visto": 0.30,
    "Interesado": 0.45,
    "Propuesta enviada": 0.60,
    "Negociación": 0.80,
    "Cerrado - Ganado": 1.0,
    "Cerrado - Perdido": 0.0,
}

# Estatus viejos (v1) -> nuevos (v2). Se aplica una sola vez en la migracion.
MAPEO_ESTATUS_V1 = {
    "Respondió": "Interesado",
    "Reunión agendada": "Negociación",
    "Cerrado - Sí": "Cerrado - Ganado",
    "Cerrado - No": "Cerrado - Perdido",
}

SECTORES = ["Fitness/Gym", "Fisioterapia", "Nutrición", "Restaurantes", "Dental", "Otro"]

# Sectores prioritarios hoy (se marcan en la vista de metricas).
SECTORES_PRIORITARIOS = ["Fitness/Gym", "Fisioterapia", "Nutrición"]

PLATAFORMAS = ["WhatsApp", "Instagram", "Facebook", "LinkedIn", "Email", "Otro"]

TIPOS_CONTACTO = ["Mensaje inicial", "Seguimiento", "Respuesta recibida", "Nota", "Cambio de estatus"]

SEVERIDADES = ["GRAVE", "OBSERVACIÓN"]

# --------------------------------------------------------------------------- #
# Precios de Certeza (MXN). El default se sugiere, siempre es editable a mano.
# --------------------------------------------------------------------------- #
PRECIOS = {
    "diagnostico": {"min": 3500, "max": 5000, "default": 4000},
    "sistema_verificacion": {"min": 12000, "max": 18000, "default": 15000},
    "mensualidad": {"min": 1500, "max": 2500, "default": 2000},
}

# Campos editables del lead (el orden se usa en la tabla principal).
CAMPOS = [
    "negocio",
    "contacto",
    "categoria",
    "sector",
    "direccion",
    "telefono",
    "plataforma",
    "evidencia_dolor",
    "track_recomendado",
    "senales_investigacion",
    "mensaje_plantilla",
    "estatus",
    "valor_estimado",
    "fecha_contacto",
    "proxima_accion",
    "notas",
]

# Campos que maneja la app sola (tracking del diagnostico). No se editan a mano
# en la tabla, pero si viven en la misma fila.
CAMPOS_SISTEMA = [
    "token_diagnostico",
    "diagnostico_url",
    "diagnostico_enviado_en",
    "aperturas",
    "ultima_apertura",
]

# Tipo SQL de las columnas que no son TEXT.
TIPOS_COLUMNA = {"valor_estimado": "REAL DEFAULT 0", "aperturas": "INTEGER DEFAULT 0"}

# Campos que llena la investigacion previa (los que trae un archivo de carga).
CAMPOS_IMPORTABLES = [
    "negocio",
    "contacto",
    "categoria",
    "sector",
    "direccion",
    "telefono",
    "plataforma",
    "evidencia_dolor",
    "mensaje_plantilla",
    "track_recomendado",
    "senales_investigacion",
]

AJUSTES_DEFAULT = {
    "nombre_remitente": "Gerardo",
    "dias_seguimiento": "4",
    "lada_default": "52",
    "base_url_diagnosticos": "",
    "goatcounter_sitio": "",
}

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    negocio           TEXT NOT NULL,
    contacto          TEXT DEFAULT '',
    categoria         TEXT DEFAULT '',
    direccion         TEXT DEFAULT '',
    telefono          TEXT DEFAULT '',
    plataforma        TEXT DEFAULT 'WhatsApp',
    evidencia_dolor   TEXT DEFAULT '',
    track_recomendado TEXT DEFAULT '',
    senales_investigacion TEXT DEFAULT '',
    mensaje_plantilla TEXT DEFAULT '',
    estatus           TEXT NOT NULL DEFAULT 'Sin contactar',
    sector            TEXT DEFAULT 'Otro',
    valor_estimado    REAL DEFAULT 0,
    fecha_contacto    TEXT,
    proxima_accion    TEXT DEFAULT '',
    notas             TEXT DEFAULT '',
    token_diagnostico TEXT DEFAULT '',
    diagnostico_url   TEXT DEFAULT '',
    diagnostico_enviado_en TEXT,
    aperturas         INTEGER DEFAULT 0,
    ultima_apertura   TEXT,
    creado_en         TEXT NOT NULL,
    actualizado_en    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contactos (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id  INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    fecha    TEXT NOT NULL,
    tipo     TEXT NOT NULL,
    canal    TEXT DEFAULT '',
    mensaje  TEXT DEFAULT '',
    detalle  TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_contactos_lead ON contactos(lead_id);

CREATE TABLE IF NOT EXISTS ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

-- Banco de dolores por sector: lo que la investigacion ya enseñó que duele.
CREATE TABLE IF NOT EXISTS dolores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sector          TEXT NOT NULL,
    titulo          TEXT NOT NULL,
    descripcion     TEXT DEFAULT '',
    severidad       TEXT NOT NULL DEFAULT 'GRAVE',
    efecto          TEXT DEFAULT '',
    etapa           TEXT DEFAULT '',
    contexto        TEXT DEFAULT '',
    veces_usado     INTEGER DEFAULT 0,
    veces_convirtio INTEGER DEFAULT 0,
    creado_en       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dolores_sector ON dolores(sector);

-- Qué dolores se usaron en el diagnóstico de cada lead.
CREATE TABLE IF NOT EXISTS lead_dolores (
    lead_id  INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    dolor_id INTEGER NOT NULL REFERENCES dolores(id) ON DELETE CASCADE,
    PRIMARY KEY (lead_id, dolor_id)
);
"""


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    """Conexion de un solo uso: commitea al salir y SIEMPRE cierra.

    (`with sqlite3.connect(...)` por si solo commitea pero no cierra, y en una app
    de Streamlit que re-ejecuta el script en cada interaccion eso va acumulando
    conexiones abiertas.)
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys = ON")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> dict:
    """Crea o actualiza el esquema. Nunca borra datos: las versiones nuevas se
    aplican con ALTER TABLE y con mapeos de valores idempotentes."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with conectar() as con:
        con.executescript(_ESQUEMA)
        agregadas = _migrar_columnas(con)
        estatus_migrados = _migrar_estatus_v1(con)
        for clave, valor in AJUSTES_DEFAULT.items():
            con.execute("INSERT OR IGNORE INTO ajustes (clave, valor) VALUES (?, ?)", (clave, valor))
    sembrados = sembrar_dolores()
    return {
        "columnas_agregadas": agregadas,
        "estatus_migrados": estatus_migrados,
        "dolores_sembrados": sembrados,
    }


def _agregar_columnas(con: sqlite3.Connection, tabla: str, columnas: dict[str, str]) -> list[str]:
    """ALTER TABLE ADD COLUMN para las que falten. Nunca toca datos existentes."""
    existentes = {f["name"] for f in con.execute(f"PRAGMA table_info({tabla})").fetchall()}
    agregadas = []
    for campo, tipo in columnas.items():
        if campo not in existentes:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {campo} {tipo}")
            agregadas.append(f"{tabla}.{campo}")
    return agregadas


def _migrar_columnas(con: sqlite3.Connection) -> list[str]:
    """Agrega columnas nuevas a una base que ya existia (sin perder datos)."""
    agregadas = _agregar_columnas(
        con,
        "leads",
        {c: TIPOS_COLUMNA.get(c, "TEXT DEFAULT ''") for c in [*CAMPOS, *CAMPOS_SISTEMA]},
    )
    agregadas += _agregar_columnas(
        con, "dolores", {"etapa": "TEXT DEFAULT ''", "contexto": "TEXT DEFAULT ''"}
    )
    _rellenar_dolores_semilla(con)
    # `sector` nace vacío en las filas viejas; el default solo aplica a inserts nuevos.
    con.execute("UPDATE leads SET sector = 'Otro' WHERE sector IS NULL OR sector = ''")
    con.execute("UPDATE leads SET valor_estimado = 0 WHERE valor_estimado IS NULL")
    con.execute("UPDATE leads SET aperturas = 0 WHERE aperturas IS NULL")
    return agregadas


def _rellenar_dolores_semilla(con: sqlite3.Connection) -> int:
    """Completa `etapa` y `contexto` en los dolores semilla que se hayan sembrado
    antes de que existieran esas columnas. Solo toca filas con el campo vacío, así
    que nunca pisa una edición manual."""
    rellenados = 0
    for d in DOLORES_SEMILLA:
        cur = con.execute(
            "UPDATE dolores SET etapa = ?, contexto = ? "
            "WHERE titulo = ? AND (etapa IS NULL OR etapa = '')",
            (d.get("etapa", ""), d.get("contexto", ""), d["titulo"]),
        )
        rellenados += cur.rowcount
    return rellenados


def _migrar_estatus_v1(con: sqlite3.Connection) -> dict[str, int]:
    """Traduce los estatus del pipeline v1 al v2. Idempotente: si ya no queda
    ninguno viejo, no hace nada."""
    migrados: dict[str, int] = {}
    for viejo, nuevo in MAPEO_ESTATUS_V1.items():
        cur = con.execute("UPDATE leads SET estatus = ? WHERE estatus = ?", (nuevo, viejo))
        if cur.rowcount:
            migrados[f"{viejo} → {nuevo}"] = cur.rowcount
    # Cualquier valor que no exista en el pipeline nuevo se estaciona en Contactado
    # antes que dejar un estatus fantasma que rompa los selectbox.
    marcas = ", ".join("?" * len(ESTATUS))
    cur = con.execute(
        f"UPDATE leads SET estatus = 'Contactado' WHERE estatus NOT IN ({marcas})", ESTATUS
    )
    if cur.rowcount:
        migrados["desconocido → Contactado"] = cur.rowcount
    return migrados


def avanzar_estatus(actual: str, propuesto: str) -> str:
    """El pipeline solo avanza: devuelve el más adelantado de los dos.

    Mandar un seguimiento a alguien que ya está en Negociación no lo regresa a
    Contactado — eso borraría información que ya se ganó.

    >>> avanzar_estatus("Negociación", "Contactado")
    'Negociación'
    >>> avanzar_estatus("Sin contactar", "Contactado")
    'Contactado'
    """
    if actual not in ORDEN_ESTATUS:
        return propuesto
    if propuesto not in ORDEN_ESTATUS:
        return actual
    return actual if ORDEN_ESTATUS[actual] >= ORDEN_ESTATUS[propuesto] else propuesto


def valor_sugerido(sector: str = "", estatus: str = "Sin contactar") -> float:
    """Valor por default del lead según en qué punto del embudo está.

    Antes de que haya propuesta lo que está en juego es el diagnóstico; ya en
    propuesta o negociación, el sistema completo más el primer mes.
    """
    if estatus in ("Propuesta enviada", "Negociación", "Cerrado - Ganado"):
        base = PRECIOS["sistema_verificacion"]["default"] + PRECIOS["mensualidad"]["default"]
    else:
        base = PRECIOS["diagnostico"]["default"]

    # Los sectores prioritarios se trabajan con el ticket medio del rango;
    # el resto arranca en el piso hasta que haya datos propios que digan otra cosa.
    if sector and sector not in SECTORES_PRIORITARIOS and sector != "Dental":
        if estatus in ("Propuesta enviada", "Negociación", "Cerrado - Ganado"):
            base = PRECIOS["sistema_verificacion"]["min"] + PRECIOS["mensualidad"]["min"]
        else:
            base = PRECIOS["diagnostico"]["min"]
    return float(base)


# --------------------------------------------------------------------------- #
# Ajustes
# --------------------------------------------------------------------------- #

def get_ajuste(clave: str, default: str | None = None) -> str:
    with conectar() as con:
        fila = con.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
    if fila is None:
        return default if default is not None else AJUSTES_DEFAULT.get(clave, "")
    return fila["valor"]


def set_ajuste(clave: str, valor: str) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO ajustes (clave, valor) VALUES (?, ?) "
            "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
            (clave, str(valor)),
        )


# --------------------------------------------------------------------------- #
# Leads
# --------------------------------------------------------------------------- #

def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dias_desde(fecha_iso: str | None) -> int | None:
    """Dias transcurridos desde una fecha ISO (YYYY-MM-DD). None si no hay fecha."""
    if not fecha_iso:
        return None
    try:
        return (date.today() - date.fromisoformat(str(fecha_iso)[:10])).days
    except ValueError:
        return None


def listar_leads(
    estatus: list[str] | None = None,
    plataformas: list[str] | None = None,
    busqueda: str = "",
    sectores: list[str] | None = None,
) -> pd.DataFrame:
    """Devuelve los leads como DataFrame, con `dias_desde_contacto` calculado y
    ordenados por urgencia (mas dias sin seguimiento primero)."""
    with conectar() as con:
        df = pd.read_sql_query("SELECT * FROM leads", con)

    if df.empty:
        return pd.DataFrame(columns=["id", *CAMPOS, "dias_desde_contacto", "creado_en", "actualizado_en"])

    df["dias_desde_contacto"] = df["fecha_contacto"].map(_dias_desde).astype("Int64")
    df["dias_desde_apertura"] = df["ultima_apertura"].map(_dias_desde).astype("Int64")

    if estatus:
        df = df[df["estatus"].isin(estatus)]
    if plataformas:
        df = df[df["plataforma"].isin(plataformas)]
    if sectores:
        df = df[df["sector"].isin(sectores)]
    if busqueda:
        aguja = busqueda.strip().lower()
        cols = ["negocio", "categoria", "direccion", "evidencia_dolor", "notas", "proxima_accion"]
        mascara = df[cols].fillna("").apply(lambda s: s.str.lower().str.contains(aguja, regex=False))
        df = df[mascara.any(axis=1)]

    # Los mas urgentes arriba; los que nunca se han contactado van al final del
    # bloque (no tienen "dias sin seguimiento" todavia, pero si prioridad propia).
    df = df.sort_values(
        by=["dias_desde_contacto", "negocio"],
        ascending=[False, True],
        na_position="last",
    ).reset_index(drop=True)
    return df


def obtener_lead(lead_id: int) -> dict | None:
    with conectar() as con:
        fila = con.execute("SELECT * FROM leads WHERE id = ?", (int(lead_id),)).fetchone()
    if fila is None:
        return None
    lead = dict(fila)
    lead["dias_desde_contacto"] = _dias_desde(lead.get("fecha_contacto"))
    return lead


def crear_lead(**campos) -> int:
    datos = {c: "" for c in CAMPOS}
    datos["estatus"] = "Sin contactar"
    datos["plataforma"] = "WhatsApp"
    datos["fecha_contacto"] = None
    datos.update({k: v for k, v in campos.items() if k in CAMPOS})

    if not str(datos["negocio"] or "").strip():
        raise ValueError("El lead necesita al menos un nombre de negocio.")

    ahora = _ahora()
    cols = [*CAMPOS, "creado_en", "actualizado_en"]
    valores = [datos[c] for c in CAMPOS] + [ahora, ahora]
    marcas = ", ".join("?" * len(cols))
    with conectar() as con:
        cur = con.execute(f"INSERT INTO leads ({', '.join(cols)}) VALUES ({marcas})", valores)
        return int(cur.lastrowid)


def actualizar_lead(lead_id: int, **campos) -> None:
    # Incluye los campos de sistema (token, aperturas…): si solo se aceptaran los
    # editables, el tracking del diagnóstico se perdería en silencio.
    permitidos = {*CAMPOS, *CAMPOS_SISTEMA}
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return
    # Normaliza fechas (acepta date/datetime/str/None).
    if "fecha_contacto" in cambios:
        cambios["fecha_contacto"] = normalizar_fecha(cambios["fecha_contacto"])

    sets = ", ".join(f"{k} = ?" for k in cambios)
    with conectar() as con:
        con.execute(
            f"UPDATE leads SET {sets}, actualizado_en = ? WHERE id = ?",
            [*cambios.values(), _ahora(), int(lead_id)],
        )


def clave_dedup(negocio, telefono) -> tuple[str, str]:
    """Clave de duplicado: negocio + telefono, ambos normalizados.

    El telefono se reduce a puros digitos (sin espacios, guiones, parentesis ni +)
    para que "+52 33 1593 4381" y "3315934381" cuenten como el mismo numero.

    >>> clave_dedup("Boutique Ejemplo ", "+52 33-1578-0598")
    ('boutique ejemplo', '523315780598')
    >>> clave_dedup("TotalMarket", None)
    ('totalmarket', '')
    """
    import whatsapp  # import local: whatsapp no importa db, no hay ciclo

    nombre = " ".join(str(negocio or "").split()).strip().lower()
    normalizado = whatsapp.limpiar_telefono(telefono, get_ajuste("lada_default", "52"))
    if normalizado is None:
        # Si no es un telefono usable, igual conservamos los digitos que traiga
        # para no fusionar dos negocios distintos con telefonos raros diferentes.
        normalizado = "".join(c for c in str(telefono or "") if c.isdigit())
    return nombre, normalizado


def claves_existentes() -> set[tuple[str, str]]:
    """Todas las claves de dedup que ya estan en la base."""
    with conectar() as con:
        filas = con.execute("SELECT negocio, telefono FROM leads").fetchall()
    return {clave_dedup(f["negocio"], f["telefono"]) for f in filas}


def crear_leads_lote(registros: list[dict]) -> int:
    """Inserta varios leads en una sola transaccion. Devuelve cuantos se crearon."""
    if not registros:
        return 0
    ahora = _ahora()
    cols = [*CAMPOS, "creado_en", "actualizado_en"]
    marcas = ", ".join("?" * len(cols))
    filas = []
    for reg in registros:
        datos = {c: "" for c in CAMPOS}
        datos["estatus"] = "Sin contactar"
        datos["plataforma"] = "WhatsApp"
        datos["fecha_contacto"] = None
        datos.update({k: v for k, v in reg.items() if k in CAMPOS})
        if not str(datos["negocio"] or "").strip():
            continue
        filas.append([datos[c] for c in CAMPOS] + [ahora, ahora])

    with conectar() as con:
        con.executemany(f"INSERT INTO leads ({', '.join(cols)}) VALUES ({marcas})", filas)
    return len(filas)


def eliminar_lead(lead_id: int) -> None:
    with conectar() as con:
        con.execute("DELETE FROM leads WHERE id = ?", (int(lead_id),))


def normalizar_fecha(valor) -> str | None:
    """Convierte date/datetime/str/NaT a 'YYYY-MM-DD' o None."""
    if valor is None or valor == "" or pd.isna(valor):
        return None
    if isinstance(valor, (datetime, pd.Timestamp)):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    try:
        return date.fromisoformat(texto[:10]).isoformat()
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Historial de contacto
# --------------------------------------------------------------------------- #

def registrar_contacto(
    lead_id: int,
    tipo: str,
    canal: str = "",
    mensaje: str = "",
    detalle: str = "",
    fecha: str | None = None,
) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO contactos (lead_id, fecha, tipo, canal, mensaje, detalle) VALUES (?, ?, ?, ?, ?, ?)",
            (int(lead_id), fecha or _ahora(), tipo, canal, mensaje, detalle),
        )


def historial(lead_id: int) -> pd.DataFrame:
    with conectar() as con:
        return pd.read_sql_query(
            "SELECT fecha, tipo, canal, mensaje, detalle FROM contactos "
            "WHERE lead_id = ? ORDER BY fecha DESC, id DESC",
            con,
            params=(int(lead_id),),
        )


def metricas_contacto() -> dict[int, dict[str, int]]:
    """Por lead: cuántos seguimientos se le han mandado y cuántas respuestas hubo.

    Una sola consulta agregada — el score se calcula para todos los leads a la vez
    y no queremos una query por fila.
    """
    with conectar() as con:
        filas = con.execute(
            "SELECT lead_id, tipo, COUNT(*) AS n FROM contactos GROUP BY lead_id, tipo"
        ).fetchall()

    metricas: dict[int, dict[str, int]] = {}
    for f in filas:
        entrada = metricas.setdefault(int(f["lead_id"]), {"seguimientos": 0, "respuestas": 0, "total": 0})
        if f["tipo"] == "Seguimiento":
            entrada["seguimientos"] += f["n"]
        if f["tipo"] == "Respuesta recibida":
            entrada["respuestas"] += f["n"]
        if f["tipo"] in ("Mensaje inicial", "Seguimiento"):
            entrada["total"] += f["n"]
    return metricas


def registrar_respuesta(lead_id: int, detalle: str = "", nuevo_estatus: str = "Interesado") -> None:
    """El prospecto contestó: se registra en el historial y avanza el pipeline."""
    lead = obtener_lead(lead_id)
    if lead is None:
        return
    registrar_contacto(lead_id, tipo="Respuesta recibida", canal=lead.get("plataforma", ""),
                       detalle=detalle)
    destino = avanzar_estatus(lead["estatus"], nuevo_estatus)
    if destino != lead["estatus"]:
        cambiar_estatus(lead_id, destino, nota="respondió")


def marcar_contactado(
    lead_id: int,
    mensaje: str = "",
    canal: str = "WhatsApp",
    tipo: str = "Mensaje inicial",
    proxima_accion: str | None = None,
) -> dict:
    """Registra un contacto: avanza el estatus a 'Contactado', pone la fecha de hoy
    y guarda el mensaje en el historial.

    Si el lead ya avanzo en el embudo (diagnostico visto, interesado, negociacion…)
    NO se regresa a 'Contactado' — solo se actualiza la fecha. Ver `avanzar_estatus`.
    """
    lead = obtener_lead(lead_id)
    if lead is None:
        raise ValueError(f"No existe el lead {lead_id}")

    campos: dict = {"fecha_contacto": date.today().isoformat()}
    campos["estatus"] = avanzar_estatus(lead["estatus"], "Contactado")
    if proxima_accion is not None:
        campos["proxima_accion"] = proxima_accion

    actualizar_lead(lead_id, **campos)
    registrar_contacto(lead_id, tipo=tipo, canal=canal, mensaje=mensaje)
    return obtener_lead(lead_id)


def cambiar_estatus(lead_id: int, nuevo: str, nota: str = "") -> None:
    lead = obtener_lead(lead_id)
    if lead is None or lead["estatus"] == nuevo:
        return
    actualizar_lead(lead_id, estatus=nuevo)
    registrar_contacto(
        lead_id,
        tipo="Cambio de estatus",
        detalle=f"{lead['estatus']} → {nuevo}" + (f" · {nota}" if nota else ""),
    )


# --------------------------------------------------------------------------- #
# Seguimientos
# --------------------------------------------------------------------------- #

def leads_para_seguimiento(dias_umbral: int = 4) -> pd.DataFrame:
    """Leads contactados que llevan >= `dias_umbral` dias sin respuesta."""
    df = listar_leads()
    if df.empty:
        return df
    pendientes = df[
        (df["estatus"] == "Contactado")
        & (df["dias_desde_contacto"].notna())
        & (df["dias_desde_contacto"] >= int(dias_umbral))
    ]
    return pendientes.sort_values("dias_desde_contacto", ascending=False).reset_index(drop=True)


def resumen() -> dict:
    df = listar_leads()
    total = len(df)
    conteo = df["estatus"].value_counts().to_dict() if total else {}
    return {
        "total": total,
        "por_estatus": {e: int(conteo.get(e, 0)) for e in ESTATUS},
        "pendientes_seguimiento": len(leads_para_seguimiento(int(get_ajuste("dias_seguimiento", "4")))),
        **pipeline_valor(df),
    }


def pipeline_valor(df: pd.DataFrame | None = None) -> dict:
    """Pipeline en dinero: bruto (suma de valores) y ponderado (× probabilidad).

    El ponderado es el número honesto: 10 leads recién contactados de $4,000 no son
    $40,000, son $2,000 de expectativa.
    """
    if df is None:
        df = listar_leads()
    if df.empty:
        return {"pipeline_bruto": 0.0, "pipeline_ponderado": 0.0, "ganado": 0.0}

    valores = pd.to_numeric(df["valor_estimado"], errors="coerce").fillna(0.0)
    probabilidad = df["estatus"].map(PROBABILIDAD_ESTATUS).fillna(0.0)
    abiertos = ~df["estatus"].isin(ESTATUS_CERRADOS)
    return {
        "pipeline_bruto": float(valores[abiertos].sum()),
        "pipeline_ponderado": float((valores * probabilidad)[abiertos].sum()),
        "ganado": float(valores[df["estatus"] == "Cerrado - Ganado"].sum()),
    }


# --------------------------------------------------------------------------- #
# Banco de dolores por sector
# --------------------------------------------------------------------------- #

# Semilla: los dolores que la primera investigacion de campo dejo documentados en
# una clinica dental. Nacen en sector Dental porque ahi se detectaron, pero varios
# son transversales: aplican a cualquier negocio con varias puertas de entrada.
DOLORES_SEMILLA = [
    {
        "sector": "Dental",
        "severidad": "GRAVE",
        "titulo": "El CRM/agenda no ve toda la demanda",
        "etapa": "Llega el interés",
        "contexto": (
            "Varias puertas de entrada, un solo equipo. Cada puerta con su propia "
            "bandeja, su propio tono y su propia hora de revisión."
        ),
        "descripcion": (
            "La agenda vive en una herramienta, pero los mensajes directos de Instagram "
            "y WhatsApp no entran ahí. El sistema por el que ya se paga solo ve una "
            "fracción de la demanda real; el resto depende de que alguien se acuerde de revisar."
        ),
        "efecto": "El CRM reporta menos clientes de los que realmente tocaron la puerta.",
    },
    {
        "sector": "Dental",
        "severidad": "GRAVE",
        "titulo": "El prospecto decide antes de la primera cita",
        "etapa": "Alguien contesta",
        "contexto": (
            "Llega alguien que escribe fuera de horario, y que está escribiéndole "
            "a otros tres al mismo tiempo."
        ),
        "descripcion": (
            "Quien compara varios proveedores escribe a tres o cuatro a la vez. El criterio "
            "de decisión inicial no es técnico: es quién respondió primero, en su idioma y "
            "con una respuesta completa. Ese filtro se resuelve antes de que el dueño "
            "tenga oportunidad de intervenir."
        ),
        "efecto": "Se pierde el ticket alto sin haber competido por él.",
    },
    {
        "sector": "Dental",
        "severidad": "GRAVE",
        "titulo": "El presupuesto alto se enfría en silencio",
        "etapa": "Valoración y presupuesto",
        "contexto": "Se entrega el presupuesto. El cliente responde que lo va a pensar.",
        "descripcion": (
            "Una compra grande no se decide el mismo día: se decide en semanas. Si el "
            "seguimiento depende de que alguien lo recuerde entre clientes, el presupuesto "
            "más caro es también el que más fácil se enfría. No se pierde por precio; se "
            "pierde por silencio."
        ),
        "efecto": "Se pierde sin dejar rastro: no hay cancelación que registrar.",
    },
    {
        "sector": "Dental",
        "severidad": "OBSERVACIÓN",
        "titulo": "Coordinación manual del cliente foráneo",
        "etapa": "Coordinación del cliente foráneo",
        "contexto": "Traslado, hospedaje y varias citas encadenadas en pocos días.",
        "descripcion": (
            "Traslado, hospedaje y varias citas encadenadas en pocos días, coordinado a "
            "mano por el equipo. Funciona bien y por eso mismo es el cuello de botella: "
            "no puede duplicarse sin duplicar personal."
        ),
        "efecto": "Techo de crecimiento, no fuga de ingreso.",
    },
    {
        "sector": "Dental",
        "severidad": "OBSERVACIÓN",
        "titulo": "Alta o fin de servicio sin sistema de referidos y reseñas",
        "etapa": "Alta y seguimiento",
        "contexto": "Termina el servicio. El cliente queda satisfecho y se va.",
        "descripcion": (
            "El momento de máxima disposición a recomendar dura pocos días después del "
            "cierre del servicio. Sin un recordatorio sistemático de reseña, referido y "
            "mantenimiento, ese pico se desperdicia."
        ),
        "efecto": "Cada cierre es una recompra y una referencia que no se piden.",
    },
]


def sembrar_dolores() -> int:
    """Carga los dolores semilla si la tabla está vacía. No duplica."""
    with conectar() as con:
        ya_hay = con.execute("SELECT COUNT(*) AS n FROM dolores").fetchone()["n"]
        if ya_hay:
            return 0
        ahora = _ahora()
        con.executemany(
            "INSERT INTO dolores (sector, titulo, descripcion, severidad, efecto, etapa, "
            "contexto, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (d["sector"], d["titulo"], d["descripcion"], d["severidad"], d["efecto"],
                 d.get("etapa", ""), d.get("contexto", ""), ahora)
                for d in DOLORES_SEMILLA
            ],
        )
    return len(DOLORES_SEMILLA)


def listar_dolores(sector: str | None = None) -> pd.DataFrame:
    """Dolores del banco, ordenados por tasa de conversión (los que más venden arriba)."""
    consulta = "SELECT * FROM dolores"
    params: tuple = ()
    if sector:
        consulta += " WHERE sector = ?"
        params = (sector,)
    with conectar() as con:
        df = pd.read_sql_query(consulta, con, params=params)

    if df.empty:
        return df
    # Sin usos la tasa es NaN (no 0): "todavía no se sabe" no es lo mismo que "no vende".
    usado = df["veces_usado"].astype(float).replace(0.0, float("nan"))
    df["tasa_conversion"] = df["veces_convirtio"].astype(float) / usado
    # Sin usos todavía no hay tasa: van después de los que ya probaron algo,
    # pero los GRAVE antes que las OBSERVACIÓN.
    df["_sev"] = (df["severidad"] == "GRAVE").astype(int)
    df = df.sort_values(
        by=["tasa_conversion", "veces_usado", "_sev", "id"],
        ascending=[False, False, False, True],
        na_position="last",
    ).drop(columns="_sev")
    return df.reset_index(drop=True)


def crear_dolor(sector: str, titulo: str, descripcion: str = "", severidad: str = "GRAVE",
                efecto: str = "", etapa: str = "", contexto: str = "") -> int:
    if not titulo.strip():
        raise ValueError("El dolor necesita un título.")
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO dolores (sector, titulo, descripcion, severidad, efecto, etapa, "
            "contexto, creado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sector, titulo.strip(), descripcion.strip(), severidad, efecto.strip(),
             etapa.strip(), contexto.strip(), _ahora()),
        )
        return int(cur.lastrowid)


def actualizar_dolor(dolor_id: int, **campos) -> None:
    permitidos = {"sector", "titulo", "descripcion", "severidad", "efecto", "etapa",
                  "contexto", "veces_usado", "veces_convirtio"}
    cambios = {k: v for k, v in campos.items() if k in permitidos}
    if not cambios:
        return
    sets = ", ".join(f"{k} = ?" for k in cambios)
    with conectar() as con:
        con.execute(f"UPDATE dolores SET {sets} WHERE id = ?", [*cambios.values(), int(dolor_id)])


def eliminar_dolor(dolor_id: int) -> None:
    with conectar() as con:
        con.execute("DELETE FROM dolores WHERE id = ?", (int(dolor_id),))


def dolores_del_lead(lead_id: int) -> list[int]:
    with conectar() as con:
        return [
            f["dolor_id"]
            for f in con.execute("SELECT dolor_id FROM lead_dolores WHERE lead_id = ?", (int(lead_id),))
        ]


def asignar_dolores(lead_id: int, dolor_ids: list[int]) -> None:
    """Deja exactamente estos dolores asociados al lead y actualiza `veces_usado`.

    `veces_usado` cuenta en cuántos diagnósticos se usó el dolor, así que se
    incrementa solo la primera vez que se asocia a este lead (y se descuenta si
    se quita), no cada vez que se guarda.
    """
    nuevos = {int(d) for d in dolor_ids}
    previos = set(dolores_del_lead(lead_id))
    with conectar() as con:
        for dolor_id in nuevos - previos:
            con.execute(
                "INSERT OR IGNORE INTO lead_dolores (lead_id, dolor_id) VALUES (?, ?)",
                (int(lead_id), dolor_id),
            )
            con.execute("UPDATE dolores SET veces_usado = veces_usado + 1 WHERE id = ?", (dolor_id,))
        for dolor_id in previos - nuevos:
            con.execute(
                "DELETE FROM lead_dolores WHERE lead_id = ? AND dolor_id = ?",
                (int(lead_id), dolor_id),
            )
            con.execute(
                "UPDATE dolores SET veces_usado = MAX(veces_usado - 1, 0) WHERE id = ?", (dolor_id,)
            )


def registrar_conversion_dolores(lead_id: int) -> int:
    """Al cerrar un lead como ganado, sube `veces_convirtio` de los dolores que se
    usaron en su diagnóstico. Devuelve cuántos dolores se acreditaron."""
    ids = dolores_del_lead(lead_id)
    if not ids:
        return 0
    with conectar() as con:
        con.executemany(
            "UPDATE dolores SET veces_convirtio = veces_convirtio + 1 WHERE id = ?",
            [(i,) for i in ids],
        )
    return len(ids)


def exportar_todo() -> bytes:
    """Respaldo completo (todas las tablas) en un ZIP de CSVs.

    Sirve para dos cosas: no perder nada si se corrompe `leads.db`, y poder mover
    los datos a otro motor (Postgres) el día que la app se despliegue en la nube.
    """
    import io
    import zipfile

    buffer = io.BytesIO()
    with conectar() as con:
        tablas = [
            f["name"]
            for f in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for tabla in tablas:
                datos = pd.read_sql_query(f"SELECT * FROM {tabla}", con)
                z.writestr(f"{tabla}.csv", datos.to_csv(index=False, encoding="utf-8"))
    return buffer.getvalue()


if __name__ == "__main__":  # pequeño smoke test manual
    print(f"DB en {DB_PATH}")
    print("migración:", init_db())
    print("resumen:", resumen())
