"""Score de lead y calendario de follow-ups.

Todo lo ajustable vive en los diccionarios `PESOS`, `UMBRALES` y `CALENDARIO` de
arriba: se pueden mover sin tocar una linea de logica.

El score no se guarda en la base — se calcula al momento porque depende de cuantos
dias han pasado. Un score almacenado sería mentira al día siguiente.
"""

from __future__ import annotations

from datetime import date

import db

# --------------------------------------------------------------------------- #
# Pesos del score (0-100). Súbele o bájale aquí.
# --------------------------------------------------------------------------- #
PESOS = {
    # Punto de partida según la etapa del embudo.
    "etapa": {
        "Sin contactar": 8,
        "Contactado": 18,
        "Diagnóstico enviado": 30,
        "Diagnóstico visto": 45,
        "Interesado": 52,
        "Propuesta enviada": 60,
        "Negociación": 70,
        "Cerrado - Ganado": 100,
        "Cerrado - Perdido": 0,
    },
    # Abrió el diagnóstico: la señal más fuerte que tenemos sin que hable.
    "primera_apertura": 14,
    "apertura_adicional": 4,
    "aperturas_tope": 26,
    # Contestó alguna vez.
    "respondio": 12,
    # Decaimiento por silencio: los primeros días no penalizan (dar aire es normal),
    # después cada día resta hasta un tope.
    "dias_gracia": 2,
    "castigo_por_dia": 1.6,
    "castigo_tope": 30,
    # Tamaño del trato: un lead de $17,000 merece más atención que uno de $3,500.
    "valor_por_cada_10k": 7,
    "valor_tope": 12,
    # Nunca contactado y ya lleva días en la base sin que nadie lo toque.
    "abandonado_sin_contactar": 6,
}

UMBRALES = {"Caliente": 60, "Tibio": 35}

# Días desde el último contacto en que toca cada follow-up, por etapa.
# Cuanto más avanzado el lead, más corto el ciclo: a quien ya vio la propuesta no
# se le deja una semana de silencio.
CALENDARIO = {
    "Sin contactar": [],
    "Contactado": [3, 7, 14],
    "Diagnóstico enviado": [2, 5, 10],
    "Diagnóstico visto": [1, 3, 7],
    "Interesado": [2, 5, 9],
    "Propuesta enviada": [2, 5, 10],
    "Negociación": [2, 4, 7],
}

# Qué plantilla usar en cada toque (índice = número de seguimiento ya enviado).
ESCALERA_PLANTILLAS = [
    "Recordatorio suave",
    "Con valor / ejemplo",
    "Pregunta directa",
    "Cierre / última llamada",
]

# Días sin tocar un lead caliente antes de que la app te lo reclame.
DIAS_ALERTA_CALIENTE = 5


# --------------------------------------------------------------------------- #
# Score
# --------------------------------------------------------------------------- #

def score_lead(lead: dict, metricas: dict | None = None) -> dict:
    """Devuelve {'score': 0-100, 'temperatura': 'Caliente'|'Tibio'|'Frío', 'factores': [...]}.

    `metricas` es la entrada de `db.metricas_contacto()` para este lead (opcional).

    >>> score_lead({"estatus": "Negociación", "dias_desde_contacto": 1})["temperatura"]
    'Caliente'
    >>> score_lead({"estatus": "Contactado", "dias_desde_contacto": 40})["temperatura"]
    'Frío'
    """
    metricas = metricas or {}
    estatus = lead.get("estatus") or "Sin contactar"
    puntos = float(PESOS["etapa"].get(estatus, 10))
    factores: list[str] = [f"etapa «{estatus}»"]

    # Cerrados: el score ya no significa nada, se devuelve el extremo y se sale.
    if estatus in db.ESTATUS_CERRADOS:
        return {
            "score": int(puntos),
            "temperatura": "Caliente" if estatus == "Cerrado - Ganado" else "Frío",
            "factores": [f"etapa «{estatus}»"],
        }

    aperturas = int(lead.get("aperturas") or 0)
    if aperturas:
        suma = PESOS["primera_apertura"] + (aperturas - 1) * PESOS["apertura_adicional"]
        suma = min(suma, PESOS["aperturas_tope"])
        puntos += suma
        factores.append(f"abrió el diagnóstico {aperturas}×")

    if metricas.get("respuestas", 0) or db.ORDEN_ESTATUS.get(estatus, 0) >= db.ORDEN_ESTATUS["Interesado"]:
        puntos += PESOS["respondio"]
        factores.append("ya contestó")

    dias = lead.get("dias_desde_contacto")
    if dias is None:
        # Nunca contactado: no se castiga por silencio, pero tampoco es urgente.
        if estatus == "Sin contactar":
            puntos += PESOS["abandonado_sin_contactar"]
    elif dias > PESOS["dias_gracia"]:
        castigo = min((dias - PESOS["dias_gracia"]) * PESOS["castigo_por_dia"], PESOS["castigo_tope"])
        puntos -= castigo
        factores.append(f"{dias} días de silencio (−{castigo:.0f})")

    valor = float(lead.get("valor_estimado") or 0)
    if valor > 0:
        extra = min(valor / 10000 * PESOS["valor_por_cada_10k"], PESOS["valor_tope"])
        puntos += extra
        factores.append(f"trato de ${valor:,.0f}")

    score = int(max(0, min(100, round(puntos))))
    if score >= UMBRALES["Caliente"]:
        temperatura = "Caliente"
    elif score >= UMBRALES["Tibio"]:
        temperatura = "Tibio"
    else:
        temperatura = "Frío"
    return {"score": score, "temperatura": temperatura, "factores": factores}


EMOJI_TEMPERATURA = {"Caliente": "🔥", "Tibio": "🌤️", "Frío": "🧊"}


# --------------------------------------------------------------------------- #
# Calendario de follow-ups
# --------------------------------------------------------------------------- #

def plan_seguimiento(lead: dict, metricas: dict | None = None) -> dict:
    """Qué toca hacer con este lead hoy, según su etapa y cuántos toques lleva.

    Devuelve:
      toca        -> bool, si hoy ya toca mandar algo
      numero      -> qué número de seguimiento sería (1, 2, 3…)
      dia_objetivo-> a los cuántos días de silencio tocaba
      dias        -> días de silencio reales
      agotado     -> bool, ya se acabó la secuencia de esta etapa
      plantilla   -> nombre de la plantilla sugerida
      vencido_por -> días de retraso respecto al día objetivo
    """
    metricas = metricas or {}
    estatus = lead.get("estatus") or "Sin contactar"
    dias = lead.get("dias_desde_contacto")
    enviados = int(metricas.get("seguimientos", 0))
    calendario = CALENDARIO.get(estatus, [])

    plan = {
        "toca": False,
        "numero": enviados + 1,
        "dia_objetivo": None,
        "dias": dias,
        "agotado": False,
        "plantilla": ESCALERA_PLANTILLAS[min(enviados, len(ESCALERA_PLANTILLAS) - 1)],
        "vencido_por": 0,
    }

    if estatus in db.ESTATUS_CERRADOS or not calendario or dias is None:
        return plan

    if enviados >= len(calendario):
        # Se acabó la secuencia: ya no se sugiere otro toque, se sugiere decidir.
        plan["agotado"] = True
        return plan

    objetivo = calendario[enviados]
    plan["dia_objetivo"] = objetivo
    if dias >= objetivo:
        plan["toca"] = True
        plan["vencido_por"] = dias - objetivo
    return plan


def _dias(n: int) -> str:
    """'1 día' / '5 días' — la concordancia importa cuando la frase es la interfaz."""
    return "1 día" if n == 1 else f"{n} días"


def razon_urgencia(lead: dict, plan: dict, metricas: dict | None = None) -> str:
    """Frase corta y concreta de por qué este lead necesita algo hoy."""
    metricas = metricas or {}
    estatus = lead.get("estatus") or "Sin contactar"
    dias = lead.get("dias_desde_contacto")
    aperturas = int(lead.get("aperturas") or 0)
    dias_apertura = lead.get("dias_desde_apertura")

    # Lo más elocuente primero: abrió el diagnóstico y no se le ha dado seguimiento.
    if aperturas and dias_apertura is not None:
        cuando = "hoy" if dias_apertura == 0 else "ayer" if dias_apertura == 1 else f"hace {_dias(dias_apertura)}"
        if dias is not None and dias_apertura <= dias:
            return f"abrió el diagnóstico {cuando} y no le has dado seguimiento"
        return f"abrió el diagnóstico {cuando}"

    if estatus == "Sin contactar":
        return "nunca se le ha escrito"

    if plan["agotado"]:
        return f"{_dias(dias)} sin respuesta y ya se acabó la secuencia de seguimiento"

    if plan["toca"]:
        etiqueta = {
            "Propuesta enviada": "propuesta enviada",
            "Diagnóstico enviado": "diagnóstico enviado",
            "Negociación": "en negociación",
            "Interesado": "dijo que le interesa",
        }.get(estatus)
        base = f"seguimiento #{plan['numero']} vencido ({_dias(dias)} de silencio)"
        return f"{etiqueta} hace {_dias(dias)} · {base}" if etiqueta else base

    if dias is not None and plan["dia_objetivo"]:
        faltan = plan["dia_objetivo"] - dias
        return f"{_dias(dias)} de silencio · el siguiente toque es en {_dias(faltan)}"
    return f"{_dias(dias)} desde el último contacto"


def leads_priorizados(df=None) -> list[dict]:
    """Todos los leads abiertos, con score, plan y razón, ordenados por urgencia.

    Urgencia = primero los que ya tocan (o se pasaron), después por score.
    """
    if df is None:
        df = db.listar_leads()
    if df.empty:
        return []

    metricas = db.metricas_contacto()
    filas = []
    for lead in df.to_dict("records"):
        if lead["estatus"] in db.ESTATUS_CERRADOS:
            continue
        m = metricas.get(int(lead["id"]), {})
        s = score_lead(lead, m)
        plan = plan_seguimiento(lead, m)
        filas.append(
            {
                **lead,
                **s,
                "plan": plan,
                "razon": razon_urgencia(lead, plan, m),
                "metricas": m,
            }
        )

    filas.sort(
        key=lambda f: (
            f["plan"]["toca"] or f["plan"]["agotado"],
            f["score"],
            f["plan"]["vencido_por"],
        ),
        reverse=True,
    )
    return filas


def calientes_desatendidos(df=None, dias_umbral: int = DIAS_ALERTA_CALIENTE) -> list[dict]:
    """Leads con interés demostrado que llevan demasiados días sin que los toques.

    Existe por un patrón concreto: seguir buscando prospectos nuevos en vez de
    cerrar a los que ya levantaron la mano.
    """
    if df is None:
        df = db.listar_leads()
    if df.empty:
        return []
    fuera = []
    for lead in df.to_dict("records"):
        if lead["estatus"] not in db.ESTATUS_CALIENTES:
            continue
        dias = lead.get("dias_desde_contacto")
        if dias is not None and dias > dias_umbral:
            fuera.append(lead)
    return sorted(fuera, key=lambda l: l.get("dias_desde_contacto") or 0, reverse=True)


def nombre_para_hablar(lead: dict) -> str:
    """Cómo referirse al lead en la frase de acción: la persona si la conocemos."""
    contacto = (lead.get("contacto") or "").strip()
    if contacto:
        return contacto
    return (lead.get("negocio") or "este lead").strip()


def siguiente_mejor_accion(priorizados: list[dict] | None = None) -> dict | None:
    """El lead que hay que atender ahora, con la frase lista para mostrar."""
    priorizados = priorizados if priorizados is not None else leads_priorizados()
    if not priorizados:
        return None
    lead = priorizados[0]
    verbo = "Escríbele a" if lead["estatus"] == "Sin contactar" else "Habla con"
    return {
        "lead": lead,
        "frase": f"{verbo} {nombre_para_hablar(lead)} — {lead['razon']}.",
    }


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
