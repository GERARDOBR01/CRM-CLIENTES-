"""¿Abrieron el diagnóstico? Consulta de visitas contra Goatcounter.

POR QUÉ GOATCOUNTER (y no otra cosa)
------------------------------------
Los diagnósticos se publican en GitHub Pages, que es hosting estático: no hay
backend propio donde registrar la visita. Las opciones eran tres:

1. **Goatcounter** — plan gratuito real para uso personal, sin cookies, sin recolectar
   datos personales, con API pública para consultar los hits. Es open source y se
   puede auto-hospedar después si hiciera falta. → **elegida**.
2. **Plausible** — muy buena herramienta, pero hoy es de paga (solo prueba de 30 días).
   Para un CRM personal que arranca, un costo fijo mensual no se justifica.
3. **Endpoint propio** — control total, pero exige un servidor encendido 24/7, que es
   justo el problema que este proyecto está tratando de evitar.

PRIVACIDAD
----------
Esto mide **si se abrió una página propia que se le envió al prospecto**, nada más.
No hay cookies, no se recolectan datos personales, no se perfila a nadie y no se
comparte nada con terceros publicitarios. Cada diagnóstico tiene su ruta única
(`/dx/{token}`) y lo único que se sabe es cuántas veces se abrió y cuándo.

Si no hay Goatcounter configurado, la app sigue funcionando: el estado se marca a
mano desde el detalle del lead.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

import db
import diagnostico

TIMEOUT = 12
DIAS_CONSULTA = 120


class TrackingNoConfigurado(RuntimeError):
    """Falta el sitio o el token de la API de Goatcounter."""


def configurado() -> bool:
    return bool(db.get_ajuste("goatcounter_sitio", "").strip() and _token_api())


def _token_api() -> str:
    """El token de la API vive en secrets/entorno, nunca en la base ni en el repo."""
    import config

    return config.secreto("GOATCOUNTER_TOKEN")


def _url_api(sitio: str) -> str:
    dominio = sitio.strip().rstrip("/")
    if not dominio.startswith("http"):
        dominio = f"https://{dominio}"
    return f"{dominio}/api/v0/stats/hits"


def consultar_hits(dias: int = DIAS_CONSULTA) -> list[dict]:
    """Trae las rutas con visitas de los últimos `dias`.

    Devuelve [{'path': '/dx/token', 'count': 3, 'ultima': '2026-08-08'}, ...].

    El parseo es defensivo a propósito: si Goatcounter cambia la forma exacta de la
    respuesta, se intenta extraer path/count de lo que venga en vez de reventar.
    """
    sitio = db.get_ajuste("goatcounter_sitio", "").strip()
    token = _token_api()
    if not sitio or not token:
        raise TrackingNoConfigurado(
            "Falta el sitio de Goatcounter (⚙️ Datos y ajustes) o el GOATCOUNTER_TOKEN "
            "en secrets/variables de entorno."
        )

    inicio = (date.today() - timedelta(days=dias)).isoformat()
    url = f"{_url_api(sitio)}?start={inicio}&end={date.today().isoformat()}&limit=200"
    peticion = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion, timeout=TIMEOUT) as respuesta:
        datos = json.loads(respuesta.read().decode("utf-8"))

    crudos = datos.get("hits") or datos.get("paths") or datos.get("stats") or []
    salida = []
    for h in crudos:
        if not isinstance(h, dict):
            continue
        ruta = h.get("path") or h.get("name") or ""
        if not ruta:
            continue
        salida.append(
            {
                "path": str(ruta),
                "count": int(h.get("count") or h.get("total") or 0),
                "ultima": _ultimo_dia(h),
            }
        )
    return salida


def _ultimo_dia(hit: dict) -> str | None:
    """Último día con visitas dentro del desglose diario que manda Goatcounter."""
    series = hit.get("stats") or hit.get("days") or []
    ultimo = None
    for punto in series:
        if not isinstance(punto, dict):
            continue
        dia = punto.get("day") or punto.get("date")
        total = punto.get("daily")
        if total is None:
            horas = punto.get("hourly") or []
            total = sum(horas) if isinstance(horas, list) else 0
        if dia and total:
            ultimo = max(ultimo, str(dia)[:10]) if ultimo else str(dia)[:10]
    return ultimo


def sincronizar() -> dict:
    """Cruza las visitas con los leads que tienen token y actualiza la base.

    La primera apertura mueve el lead de «Diagnóstico enviado» a «Diagnóstico visto»
    y lo deja anotado en el historial.
    """
    hits = consultar_hits()
    por_ruta = {h["path"].rstrip("/"): h for h in hits}

    df = db.listar_leads()
    actualizados, nuevos_vistos = 0, []
    for lead in df.to_dict("records"):
        token = (lead.get("token_diagnostico") or "").strip()
        if not token:
            continue
        ruta = diagnostico.ruta_tracking(token).rstrip("/")
        hit = por_ruta.get(ruta) or por_ruta.get(ruta.lstrip("/"))
        if not hit or not hit["count"]:
            continue

        previas = int(lead.get("aperturas") or 0)
        if hit["count"] == previas:
            continue

        db.actualizar_lead(
            int(lead["id"]),
            aperturas=hit["count"],
            ultima_apertura=hit["ultima"] or date.today().isoformat(),
        )
        actualizados += 1

        if previas == 0:
            nuevos_vistos.append(lead["negocio"])
            db.registrar_contacto(
                int(lead["id"]),
                tipo="Nota",
                detalle=f"Abrió el diagnóstico ({hit['count']} vez/veces).",
            )
            destino = db.avanzar_estatus(lead["estatus"], "Diagnóstico visto")
            if destino != lead["estatus"]:
                db.cambiar_estatus(int(lead["id"]), destino, nota="abrió el diagnóstico")

    return {
        "rutas_con_visitas": len(hits),
        "leads_actualizados": actualizados,
        "nuevos_vistos": nuevos_vistos,
        "revisado_en": datetime.now().isoformat(timespec="seconds"),
    }


def marcar_apertura_manual(lead_id: int, cuando: str | None = None) -> None:
    """Fallback sin Goatcounter: registrar a mano que el prospecto lo abrió
    (porque lo dijo, o porque se ve en el 'visto' del chat)."""
    lead = db.obtener_lead(lead_id)
    if lead is None:
        return
    previas = int(lead.get("aperturas") or 0)
    db.actualizar_lead(
        lead_id,
        aperturas=previas + 1,
        ultima_apertura=cuando or date.today().isoformat(),
    )
    db.registrar_contacto(lead_id, tipo="Nota", detalle="Apertura del diagnóstico registrada a mano.")
    destino = db.avanzar_estatus(lead["estatus"], "Diagnóstico visto")
    if destino != lead["estatus"]:
        db.cambiar_estatus(lead_id, destino, nota="abrió el diagnóstico (manual)")
