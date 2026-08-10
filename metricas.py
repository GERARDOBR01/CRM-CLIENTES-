"""Métricas por sector: dónde enfocar según datos propios, no según proyecciones.

Las definiciones importan más que los números, así que están escritas explícitas:

- tasa_respuesta = leads que llegaron al menos a «Interesado» ÷ leads contactados
- tasa_apertura  = leads con >=1 apertura ÷ leads con diagnóstico enviado
- tasa_cierre    = ganados ÷ (ganados + perdidos)   ← solo sobre decisiones tomadas
- ticket_promedio= promedio de valor_estimado de los ganados; si no hay ganados
                   todavía, el promedio de los abiertos con valor (y se nota)
- dias_ciclo     = días entre el primer contacto registrado y el cierre ganado
"""

from __future__ import annotations

from datetime import date

import pandas as pd

import db


def _dias_entre(inicio: str | None, fin: str | None) -> float | None:
    try:
        a = date.fromisoformat(str(inicio)[:10])
        b = date.fromisoformat(str(fin)[:10])
    except (ValueError, TypeError):
        return None
    return max((b - a).days, 0)


def _primeros_contactos() -> dict[int, str]:
    """Fecha del primer contacto registrado por lead (para el ciclo de venta)."""
    with db.conectar() as con:
        filas = con.execute(
            "SELECT lead_id, MIN(fecha) AS primero FROM contactos "
            "WHERE tipo IN ('Mensaje inicial', 'Seguimiento') GROUP BY lead_id"
        ).fetchall()
    return {int(f["lead_id"]): f["primero"] for f in filas}


def _contactado(lead: dict, m: dict) -> bool:
    """¿Se le escribió alguna vez? Manda el historial, que es el registro de lo que
    de verdad pasó; el estatus es una etiqueta que se puede mover a mano."""
    return bool(m.get("total", 0)) or bool(lead.get("fecha_contacto")) or \
        (lead.get("estatus") or "Sin contactar") != "Sin contactar"


def _respondio(lead: dict, m: dict) -> bool:
    """¿Contestó alguna vez?

    Una respuesta registrada en el historial, o una etapa a la que solo se llega
    contestando. `Cerrado - Perdido` NO cuenta: se cierra como perdido justamente
    a los que nunca contestaron.
    """
    return bool(m.get("respuestas", 0)) or (lead.get("estatus") or "") in db.ESTATUS_CON_RESPUESTA


def _recibio_diagnostico(lead: dict) -> bool:
    if lead.get("diagnostico_enviado_en"):
        return True
    if int(pd.to_numeric(lead.get("aperturas"), errors="coerce") or 0) > 0:
        return True
    return (lead.get("estatus") or "") in db.ESTATUS_CON_DIAGNOSTICO


def por_sector(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Una fila por sector con leads en la base."""
    if df is None:
        df = db.listar_leads()
    if df.empty:
        return pd.DataFrame()

    primeros = _primeros_contactos()
    conteos = db.metricas_contacto()
    filas = []

    for sector, grupo in df.groupby("sector", dropna=False):
        sector = sector or "Otro"
        total = len(grupo)
        registros = grupo.to_dict("records")

        contactados = sum(1 for l in registros if _contactado(l, conteos.get(int(l["id"]), {})))
        respondieron = sum(1 for l in registros if _respondio(l, conteos.get(int(l["id"]), {})))
        con_dx = sum(1 for l in registros if _recibio_diagnostico(l))
        abrieron = int((pd.to_numeric(grupo["aperturas"], errors="coerce").fillna(0) > 0).sum())
        ganados = grupo[grupo["estatus"] == "Cerrado - Ganado"]
        perdidos = grupo[grupo["estatus"] == "Cerrado - Perdido"]
        decididos = len(ganados) + len(perdidos)

        valores = pd.to_numeric(grupo["valor_estimado"], errors="coerce").fillna(0)
        if len(ganados):
            ticket = float(pd.to_numeric(ganados["valor_estimado"], errors="coerce").fillna(0).mean())
        else:
            con_valor = valores[valores > 0]
            ticket = float(con_valor.mean()) if len(con_valor) else 0.0

        ciclos = [
            d for d in (
                _dias_entre(primeros.get(int(l["id"])), l["fecha_contacto"])
                for l in ganados.to_dict("records")
            ) if d is not None
        ]

        probabilidad = grupo["estatus"].map(db.PROBABILIDAD_ESTATUS).fillna(0.0)
        abiertos = ~grupo["estatus"].isin(db.ESTATUS_CERRADOS)

        filas.append(
            {
                "sector": sector,
                "leads": total,
                "contactados": contactados,
                "tasa_respuesta": respondieron / contactados if contactados else float("nan"),
                "tasa_apertura": abrieron / con_dx if con_dx else float("nan"),
                "tasa_cierre": len(ganados) / decididos if decididos else float("nan"),
                "ticket_promedio": ticket,
                "dias_ciclo": sum(ciclos) / len(ciclos) if ciclos else float("nan"),
                "pipeline_ponderado": float((valores * probabilidad)[abiertos].sum()),
            }
        )

    tabla = pd.DataFrame(filas)
    return tabla.sort_values(["pipeline_ponderado", "leads"], ascending=False).reset_index(drop=True)


def dolor_usado_por_lead() -> dict[int, str]:
    """Qué `tipo_dolor` se usó en el PRIMER mensaje generado de cada lead.

    Se lee de la firma que `mensajes.Mensaje.firma()` deja en el historial
    (`[gen] whatsapp · sin_datos · g2 · v1-3`). Importa que sea el primero: es el
    mensaje que abrió la conversación, y por lo tanto el que se está midiendo.

    Se guarda al enviar y no se deduce del lead porque `tipo_dolor` se puede
    reclasificar después; si se leyera el valor actual, la métrica cambiaría
    retroactivamente y dejaría de medir lo que de verdad se mandó.
    """
    with db.conectar() as con:
        filas = con.execute(
            "SELECT lead_id, detalle FROM contactos c "
            "WHERE detalle LIKE '[gen]%' "
            "  AND fecha = (SELECT MIN(fecha) FROM contactos d "
            "               WHERE d.lead_id = c.lead_id AND d.detalle LIKE '[gen]%')"
        ).fetchall()

    usados: dict[int, str] = {}
    for f in filas:
        partes = [p.strip() for p in str(f["detalle"]).split("·")]
        if len(partes) >= 2 and partes[1] in db.TIPOS_DOLOR:
            usados.setdefault(int(f["lead_id"]), partes[1])
    return usados


def por_tipo_dolor(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Tasa de respuesta por tipo de dolor: qué argumento hace que contesten.

    Sin este dato no hay forma de saber qué mensajes funcionan, y vale más que
    cualquier suposición sobre el tono correcto.

    Cuenta solo leads ya contactados. Para los que se mandaron con el generador usa
    el dolor registrado en el envío; para los contactados antes de que el generador
    existiera, cae a su clasificación actual. La columna `con_traza` dice cuántos son
    de los primeros — mientras sea baja, la tabla es indicativa y no medición.
    """
    if df is None:
        df = db.listar_leads()
    if df.empty:
        return pd.DataFrame()

    usados = dolor_usado_por_lead()
    conteos = db.metricas_contacto()
    contactados = df[
        [_contactado(l, conteos.get(int(l["id"]), {})) for l in df.to_dict("records")]
    ].copy()
    if contactados.empty:
        return pd.DataFrame()

    contactados["_dolor"] = [
        usados.get(int(r["id"])) or (r["tipo_dolor"] or "")
        for _, r in contactados.iterrows()
    ]
    contactados["_traza"] = [int(int(r["id"]) in usados) for _, r in contactados.iterrows()]

    filas = []
    for dolor, grupo in contactados.groupby("_dolor", dropna=False):
        registros = grupo.to_dict("records")
        enviados = len(grupo)
        respondieron = sum(1 for l in registros if _respondio(l, conteos.get(int(l["id"]), {})))
        ganados = int((grupo["estatus"] == "Cerrado - Ganado").sum())
        perdidos = int((grupo["estatus"] == "Cerrado - Perdido").sum())
        decididos = ganados + perdidos
        filas.append(
            {
                "tipo_dolor": dolor or "(sin clasificar)",
                "contactados": enviados,
                "respondieron": respondieron,
                "tasa_respuesta": respondieron / enviados if enviados else float("nan"),
                "ganados": ganados,
                "tasa_cierre": ganados / decididos if decididos else float("nan"),
                "con_traza": int(grupo["_traza"].sum()),
            }
        )

    tabla = pd.DataFrame(filas)
    return tabla.sort_values(
        ["tasa_respuesta", "contactados"], ascending=False, na_position="last"
    ).reset_index(drop=True)


def sectores_sin_datos(tabla: pd.DataFrame | None = None) -> list[str]:
    """Sectores del catálogo que todavía no tienen ni un lead."""
    tabla = por_sector() if tabla is None else tabla
    presentes = set(tabla["sector"]) if not tabla.empty else set()
    return [s for s in db.SECTORES if s not in presentes]


def embudo_global(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Cuántos leads hay en cada etapa, en orden de embudo."""
    if df is None:
        df = db.listar_leads()
    conteo = df["estatus"].value_counts().to_dict() if not df.empty else {}
    return pd.DataFrame(
        [{"etapa": e, "leads": int(conteo.get(e, 0))} for e in db.ESTATUS]
    )
