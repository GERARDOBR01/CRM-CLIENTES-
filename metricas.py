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


def por_sector(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Una fila por sector con leads en la base."""
    if df is None:
        df = db.listar_leads()
    if df.empty:
        return pd.DataFrame()

    primeros = _primeros_contactos()
    orden_interesado = db.ORDEN_ESTATUS["Interesado"]
    filas = []

    for sector, grupo in df.groupby("sector", dropna=False):
        sector = sector or "Otro"
        total = len(grupo)
        orden = grupo["estatus"].map(db.ORDEN_ESTATUS).fillna(0)

        contactados = int((orden >= db.ORDEN_ESTATUS["Contactado"]).sum())
        respondieron = int((orden >= orden_interesado).sum())
        con_dx = int((orden >= db.ORDEN_ESTATUS["Diagnóstico enviado"]).sum())
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
