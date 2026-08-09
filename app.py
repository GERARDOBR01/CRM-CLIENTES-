"""CRM local de leads + preparacion de outreach por WhatsApp.

    streamlit run app.py

La app PREPARA y ORGANIZA mensajes; nunca los envia sola. El boton de WhatsApp
abre wa.me con el texto ya escrito y el envio final lo das tu con un clic.
"""

from __future__ import annotations

import html as html_mod
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import config
import db
import diagnostico
import importador
import metricas
import migrate_excel
import plantillas
import scoring
import tracking
import whatsapp

st.set_page_config(page_title="CRM Leads · Outreach", page_icon="📇", layout="wide")

# Muro de contraseña: solo estorba si CRM_PASSWORD está configurada (es decir, en la
# nube). En localhost no aparece.
config.exigir_password()

db.init_db()

VISTAS = [
    "🎯 HOY",
    "📋 Leads",
    "💬 Preparar mensaje",
    "🩺 Dolores y diagnósticos",
    "📥 Cargar leads",
    "📊 Métricas",
    "⚙️ Datos y ajustes",
]

COLOR_ESTATUS = {
    "Sin contactar": "⚪",
    "Contactado": "🔵",
    "Diagnóstico enviado": "📄",
    "Diagnóstico visto": "👀",
    "Interesado": "🟢",
    "Propuesta enviada": "📝",
    "Negociación": "🟣",
    "Cerrado - Ganado": "✅",
    "Cerrado - Perdido": "⛔",
}


# --------------------------------------------------------------------------- #
# Helpers de UI
# --------------------------------------------------------------------------- #

def ir_a(vista: str, lead_id: int | None = None) -> None:
    """Callback para navegar entre vistas conservando el lead seleccionado."""
    st.session_state["vista"] = vista
    if lead_id is not None:
        st.session_state["lead_sel"] = int(lead_id)


def boton_copiar(texto: str, etiqueta: str = "📋 Copiar mensaje", key: str = "copy") -> None:
    """Boton de copiado al portapapeles (con fallback para navegadores viejos)."""
    payload = json.dumps(texto)
    components.html(
        f"""
        <button id="btn-{key}" style="
            width:100%; padding:.55rem 1rem; cursor:pointer; font-size:.9rem;
            border-radius:.5rem; border:1px solid rgba(128,128,128,.4);
            background:transparent; color:inherit; font-family:inherit;">
            {html_mod.escape(etiqueta)}
        </button>
        <script>
        const btn = document.getElementById("btn-{key}");
        const txt = {payload};
        btn.addEventListener("click", async () => {{
            try {{
                await navigator.clipboard.writeText(txt);
            }} catch (e) {{
                const ta = document.createElement("textarea");
                ta.value = txt; document.body.appendChild(ta); ta.select();
                document.execCommand("copy"); document.body.removeChild(ta);
            }}
            const original = btn.innerHTML;
            btn.innerHTML = "✅ Copiado";
            setTimeout(() => btn.innerHTML = original, 1500);
        }});
        </script>
        """,
        height=48,
    )


def abrir_whatsapp(url: str, key: str) -> None:
    """Intenta abrir wa.me en una pestaña nueva y deja un link de respaldo.

    El auto-open puede ser bloqueado por el navegador (es una pestaña abierta sin
    gesto directo del usuario), por eso siempre se muestra el link manual.
    """
    seguro = html_mod.escape(url, quote=True)
    components.html(
        f"""
        <script>
          try {{ window.open({json.dumps(url)}, "_blank", "noopener"); }} catch (e) {{}}
        </script>
        <a href="{seguro}" target="_blank" rel="noopener" style="
            display:block; text-align:center; padding:.6rem 1rem; text-decoration:none;
            border-radius:.5rem; background:#25D366; color:#0b2e1a; font-weight:600;
            font-family:inherit; font-size:.9rem;">
            ↗ Abrir WhatsApp (si no se abrió solo)
        </a>
        """,
        height=56,
    )


def opciones_columna(df: pd.DataFrame, columna: str, base: list[str]) -> list[str]:
    """Opciones del selectbox de la tabla: las canónicas más cualquier valor raro
    que ya exista en la base (si no, st.data_editor truena al pintar la fila)."""
    extras = [v for v in df[columna].dropna().unique().tolist() if v and v not in base]
    return [*base, *extras]


def ficha_lead(lead: dict) -> None:
    dias = lead.get("dias_desde_contacto")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Estatus", f"{COLOR_ESTATUS.get(lead['estatus'], '')} {lead['estatus']}")
    c2.metric("Sector", lead.get("sector") or "—")
    c3.metric("Valor est.", f"${float(lead.get('valor_estimado') or 0):,.0f}")
    c4.metric("Último contacto", lead.get("fecha_contacto") or "Nunca")
    c5.metric("Días sin seguimiento", dias if dias is not None else "—")


@st.cache_resource
def seed_inicial() -> str | None:
    """Con la base vacía, carga datos iniciales una sola vez.

    Primero busca el `leads_tracker.xlsx` (el arranque real, en la PC de Gerardo).
    Si no está — que es el caso en un despliegue en la nube — cae al
    `leads_ejemplo.csv` de datos ficticios, para que la app se vea funcionando en
    vez de aparecer vacía.
    """
    if db.get_ajuste("seed_hecho", "0") == "1" or db.resumen()["total"] > 0:
        db.set_ajuste("seed_hecho", "1")
        return None

    for ruta in migrate_excel.RUTAS_CANDIDATAS:
        if ruta.exists():
            try:
                res = migrate_excel.importar(ruta)
            except Exception:
                break
            db.set_ajuste("seed_hecho", "1")
            return f"Se cargaron {res['creados']} leads iniciales desde {ruta.name}"

    ejemplo = config.RAIZ / "leads_ejemplo.csv"
    if ejemplo.exists():
        try:
            preparado, _ = importador.preparar(importador.leer_archivo(ejemplo))
            resultado = importador.insertar(preparado)
        except Exception:
            return None
        db.set_ajuste("seed_hecho", "1")
        return f"Demo: se cargaron {resultado['agregados']} leads de ejemplo"
    return None


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

mensaje_seed = seed_inicial()
if mensaje_seed:
    st.toast(mensaje_seed, icon="📥")

if config.es_demo():
    st.info(
        "**Demostración.** Los leads que ves son negocios inventados, no clientes "
        "reales. Puedes tocar todo: los cambios son temporales y se borran solos "
        "cuando el servidor se reinicia.",
        icon="👋",
    )

res = db.resumen()
umbral_guardado = int(db.get_ajuste("dias_seguimiento", "4"))

with st.sidebar:
    st.title("📇 CRM de Leads")
    st.caption("Herramienta local · SQLite · un solo usuario")

    st.radio("Vista", VISTAS, key="vista", label_visibility="collapsed")

    st.divider()
    a, b = st.columns(2)
    a.metric("Leads", res["total"])
    b.metric("Pipeline", f"${res['pipeline_ponderado']:,.0f}",
             help="Ponderado por probabilidad de cierre de cada etapa.")

    calientes = sum(res["por_estatus"][e] for e in db.ESTATUS_CALIENTES)
    a.metric("Sin contactar", res["por_estatus"]["Sin contactar"])
    b.metric("Calientes", calientes,
             help="Diagnóstico visto, Interesado, Propuesta enviada o Negociación.")

    if res["pendientes_seguimiento"]:
        st.warning(f"🔔 {res['pendientes_seguimiento']} lead(s) esperan seguimiento hoy")

    st.divider()
    st.caption(
        "Esta app **prepara** mensajes, no los envía. El envío final siempre lo das tú "
        "con un clic en WhatsApp."
    )

vista = st.session_state.get("vista", VISTAS[0])


# --------------------------------------------------------------------------- #
# Vista 1 · Tabla de leads
# --------------------------------------------------------------------------- #

def vista_leads() -> None:
    st.header("📋 Leads")
    st.caption("Ordenados por días sin seguimiento (los más urgentes arriba).")

    f1, f2, f3, f4 = st.columns([2, 2, 2, 3])
    filtro_estatus = f1.multiselect("Estatus", db.ESTATUS, default=[])
    filtro_sector = f2.multiselect("Sector", db.SECTORES, default=[])
    filtro_plataforma = f3.multiselect("Plataforma", db.PLATAFORMAS, default=[])
    busqueda = f4.text_input("Buscar", placeholder="negocio, categoría, dirección, notas…")

    df = db.listar_leads(filtro_estatus, filtro_plataforma, busqueda, filtro_sector)

    if df.empty:
        st.info(
            "No hay leads que coincidan. Si es la primera vez, importa el Excel desde "
            "**⚙️ Datos y ajustes**."
        )
        return

    vista_df = df[["id", *db.CAMPOS, "dias_desde_contacto"]].copy()
    vista_df["fecha_contacto"] = pd.to_datetime(vista_df["fecha_contacto"], errors="coerce")
    vista_df["dias_desde_contacto"] = vista_df["dias_desde_contacto"].astype("float")

    # La clave del editor incluye los filtros: si cambian, las posiciones de fila
    # dejan de coincidir con lo editado, así que el editor se reinicia limpio.
    version = st.session_state.setdefault("editor_ver", 0)
    firma = abs(hash(f"{filtro_estatus}|{filtro_sector}|{filtro_plataforma}|{busqueda}"))
    editor_key = f"editor_leads_{version}_{firma}"

    # Pipeline en dinero de lo que está viendo el filtro actual.
    plata = db.pipeline_valor(df)
    p1, p2, p3 = st.columns(3)
    p1.metric("Pipeline bruto", f"${plata['pipeline_bruto']:,.0f}")
    p2.metric("Pipeline ponderado", f"${plata['pipeline_ponderado']:,.0f}",
              help="Suma de valor_estimado × probabilidad de cierre de cada etapa. "
                   "Es el número honesto para planear.")
    p3.metric("Ganado", f"${plata['ganado']:,.0f}")

    st.data_editor(
        vista_df,
        key=editor_key,
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "negocio": st.column_config.TextColumn("Negocio", width="medium", required=True),
            "sector": st.column_config.SelectboxColumn(
                "Sector", options=opciones_columna(df, "sector", db.SECTORES)
            ),
            "valor_estimado": st.column_config.NumberColumn(
                "Valor est.", format="$%.0f", min_value=0, step=500
            ),
            "categoria": st.column_config.TextColumn("Categoría"),
            "direccion": st.column_config.TextColumn("Dirección", width="medium"),
            "telefono": st.column_config.TextColumn("Teléfono", help="Formato E.164: +52..."),
            "plataforma": st.column_config.SelectboxColumn(
                "Plataforma", options=opciones_columna(df, "plataforma", db.PLATAFORMAS)
            ),
            "evidencia_dolor": st.column_config.TextColumn("Evidencia de dolor", width="large"),
            "track_recomendado": st.column_config.TextColumn("Track recomendado"),
            "senales_investigacion": st.column_config.TextColumn(
                "Señales de investigación", width="medium"
            ),
            "mensaje_plantilla": st.column_config.TextColumn("Mensaje plantilla", width="large"),
            "estatus": st.column_config.SelectboxColumn(
                "Estatus", options=opciones_columna(df, "estatus", db.ESTATUS), required=True
            ),
            "fecha_contacto": st.column_config.DateColumn("Fecha contacto", format="YYYY-MM-DD"),
            "proxima_accion": st.column_config.TextColumn("Próxima acción"),
            "notas": st.column_config.TextColumn("Notas", width="medium"),
            "dias_desde_contacto": st.column_config.NumberColumn(
                "Días sin seguim.", disabled=True, width="small"
            ),
        },
        column_order=[
            "dias_desde_contacto", "negocio", "estatus", "sector", "valor_estimado", "plataforma",
            "telefono", "categoria", "proxima_accion", "fecha_contacto", "track_recomendado",
            "evidencia_dolor", "senales_investigacion", "mensaje_plantilla", "direccion",
            "notas", "id",
        ],
    )

    cambios = st.session_state.get(editor_key, {})
    pendientes = (
        len(cambios.get("edited_rows", {}))
        + len(cambios.get("added_rows", []))
        + len(cambios.get("deleted_rows", []))
    )

    c1, c2 = st.columns([1, 4])
    if c1.button(
        f"💾 Guardar cambios ({pendientes})" if pendientes else "💾 Guardar cambios",
        type="primary",
        disabled=not pendientes,
        width="stretch",
    ):
        guardar_edicion_tabla(vista_df, cambios)
        st.session_state["editor_ver"] = version + 1
        st.rerun()

    if pendientes:
        c2.warning("Tienes cambios sin guardar en la tabla.")

    st.divider()
    st.subheader("Ir al detalle")
    opciones = df["id"].tolist()
    sel = st.selectbox(
        "Lead",
        opciones,
        format_func=lambda i: f"{COLOR_ESTATUS.get(df.loc[df['id'] == i, 'estatus'].iloc[0], '')} "
                              f"{df.loc[df['id'] == i, 'negocio'].iloc[0]}",
        label_visibility="collapsed",
    )
    st.button(
        "💬 Preparar mensaje para este lead",
        type="primary",
        on_click=ir_a,
        args=(VISTAS[2], sel),
    )


def guardar_edicion_tabla(vista_df: pd.DataFrame, cambios: dict) -> None:
    """Aplica a SQLite lo editado/agregado/borrado en el st.data_editor."""
    editadas = cambios.get("edited_rows", {})
    for pos, campos in editadas.items():
        lead_id = int(vista_df.iloc[int(pos)]["id"])
        limpios = {k: v for k, v in campos.items() if k in db.CAMPOS}
        if limpios:
            db.actualizar_lead(lead_id, **limpios)

    for nueva in cambios.get("added_rows", []):
        limpios = {k: v for k, v in nueva.items() if k in db.CAMPOS}
        if str(limpios.get("negocio", "")).strip():
            db.crear_lead(**limpios)

    borradas = cambios.get("deleted_rows", [])
    for pos in borradas:
        db.eliminar_lead(int(vista_df.iloc[int(pos)]["id"]))

    st.toast(
        f"Guardado: {len(editadas)} editado(s), {len(cambios.get('added_rows', []))} nuevo(s), "
        f"{len(borradas)} borrado(s)",
        icon="💾",
    )


# --------------------------------------------------------------------------- #
# Vista 2 · Detalle y preparacion del mensaje
# --------------------------------------------------------------------------- #

def vista_detalle() -> None:
    st.header("💬 Preparar mensaje")

    df = db.listar_leads()
    if df.empty:
        st.info("Todavía no hay leads. Importa el Excel desde **⚙️ Datos y ajustes**.")
        return

    ids = df["id"].tolist()
    actual = st.session_state.get("lead_sel")
    indice = ids.index(actual) if actual in ids else 0

    lead_id = st.selectbox(
        "Lead",
        ids,
        index=indice,
        format_func=lambda i: f"{COLOR_ESTATUS.get(df.loc[df['id'] == i, 'estatus'].iloc[0], '')} "
                              f"{df.loc[df['id'] == i, 'negocio'].iloc[0]}",
    )
    st.session_state["lead_sel"] = int(lead_id)

    lead = db.obtener_lead(lead_id)
    if lead is None:
        st.error("Ese lead ya no existe.")
        return

    st.subheader(lead["negocio"])
    ficha_lead(lead)

    with st.expander("📌 Contexto del lead", expanded=True):
        st.markdown(f"**Categoría:** {lead['categoria'] or '—'}")
        st.markdown(f"**Dirección:** {lead['direccion'] or '—'}")
        st.markdown(f"**Teléfono:** {lead['telefono'] or '—'}")
        st.markdown(f"**Evidencia de dolor:** {lead['evidencia_dolor'] or '—'}")
        if lead.get("track_recomendado"):
            st.markdown(f"**Track recomendado:** {lead['track_recomendado']}")
        if lead.get("senales_investigacion"):
            st.markdown(f"**Señales de investigación:** {lead['senales_investigacion']}")
        if lead.get("diagnostico_url"):
            aperturas = int(lead.get("aperturas") or 0)
            estado_dx = (
                f"abierto {aperturas} vez/veces · última {lead.get('ultima_apertura') or '—'}"
                if aperturas else "todavía sin abrir"
            )
            st.markdown(f"**Diagnóstico:** {estado_dx}  \n`{lead['diagnostico_url']}`")
        if lead["notas"]:
            st.markdown(f"**Notas:** {lead['notas']}")

    mi_nombre = db.get_ajuste("nombre_remitente", "Gerardo")
    lada = db.get_ajuste("lada_default", "52")

    st.markdown("### Mensaje")
    faltantes = plantillas.variables_faltantes(lead["mensaje_plantilla"])
    if faltantes:
        st.warning(f"La plantilla usa variables que no existen: {', '.join('{'+f+'}' for f in faltantes)}")

    if not (lead["mensaje_plantilla"] or "").strip():
        st.info(
            "Este lead no trae mensaje propio (viene de una carga sin esa columna). "
            "Abajo está la plantilla genérica: personalízala antes de mandarla, y guárdala "
            "en *Actualizar estatus…* si quieres reutilizarla."
        )

    base = plantillas.render(lead["mensaje_plantilla"], lead, mi_nombre) or plantillas.render(
        plantillas.PLANTILLA_NUEVA, lead, mi_nombre
    )

    # El texto editado vive por lead, para que cambiar de lead no arrastre el anterior.
    key_msg = f"msg_{lead_id}"
    if key_msg not in st.session_state:
        st.session_state[key_msg] = base

    mensaje = st.text_area("Mensaje final (editable antes de enviar)", key=key_msg, height=170)

    m1, m2 = st.columns([3, 1])
    m1.caption(f"{len(mensaje)} caracteres · variables: "
               + ", ".join("{" + v + "}" for v in plantillas.VARIABLES))
    if m2.button("↻ Restaurar plantilla", width="stretch",
                 help="Vuelve a generar el mensaje desde la plantilla guardada."):
        del st.session_state[key_msg]
        st.rerun()

    url = whatsapp.link_whatsapp(lead["telefono"], mensaje, lada)

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if url:
            if st.button(
                "📲 Abrir en WhatsApp y marcar como Contactado",
                type="primary",
                width="stretch",
            ):
                db.marcar_contactado(
                    lead_id,
                    mensaje=mensaje,
                    canal="WhatsApp",
                    tipo="Seguimiento" if lead["estatus"] == "Contactado" else "Mensaje inicial",
                )
                st.session_state["wa_abrir"] = {"url": url, "lead": lead["negocio"]}
                st.rerun()
        else:
            st.button(
                "📲 Abrir en WhatsApp (sin teléfono)",
                disabled=True,
                width="stretch",
                help="Este lead no tiene un teléfono válido.",
            )

    with col2:
        boton_copiar(mensaje, key=f"c{lead_id}")

    with col3:
        if st.button("✍️ Marcar contactado a mano", width="stretch",
                     help="Úsalo si contactaste por Instagram, Facebook o llamada."):
            db.marcar_contactado(lead_id, mensaje=mensaje, canal=lead["plataforma"], tipo="Mensaje inicial")
            st.rerun()

    if whatsapp.url_demasiado_larga(url):
        st.warning(
            "El mensaje es muy largo para un link de WhatsApp; algunos clientes lo cortan. "
            "Recórtalo o cópialo y pégalo a mano."
        )

    # Si acabamos de marcar contacto, abrimos wa.me en pestaña nueva.
    pendiente = st.session_state.pop("wa_abrir", None)
    if pendiente:
        st.success(f"Estatus actualizado a **Contactado** · fecha {date.today().isoformat()}")
        abrir_whatsapp(pendiente["url"], key=f"wa{lead_id}")

    if not url:
        st.info(
            f"**{lead['negocio']} no tiene teléfono.** Búscalo manualmente en Instagram o "
            "Facebook, manda el mensaje por DM y luego usa *Marcar contactado a mano*."
        )
        enlaces = whatsapp.links_busqueda_manual(lead["negocio"], lead["direccion"])
        cols = st.columns(len(enlaces))
        for col, (etiqueta, enlace) in zip(cols, enlaces.items()):
            col.link_button(etiqueta, enlace, width="stretch")

    st.divider()

    # ---- Edicion rapida de seguimiento ----
    with st.expander("✏️ Actualizar estatus, próxima acción y notas"):
        with st.form(f"form_lead_{lead_id}"):
            e1, e2 = st.columns(2)
            nuevo_estatus = e1.selectbox(
                "Estatus", db.ESTATUS, index=db.ESTATUS.index(lead["estatus"])
            )
            fecha_val = db.normalizar_fecha(lead["fecha_contacto"])
            nueva_fecha = e2.date_input(
                "Fecha de contacto",
                value=date.fromisoformat(fecha_val) if fecha_val else None,
                format="YYYY-MM-DD",
            )
            e3, e4 = st.columns(2)
            sector_actual = lead.get("sector") or "Otro"
            nuevo_sector = e3.selectbox(
                "Sector",
                db.SECTORES,
                index=db.SECTORES.index(sector_actual) if sector_actual in db.SECTORES else len(db.SECTORES) - 1,
            )
            valor_actual = float(lead.get("valor_estimado") or 0)
            nuevo_valor = e4.number_input(
                "Valor estimado (MXN)",
                min_value=0.0,
                step=500.0,
                value=valor_actual or db.valor_sugerido(sector_actual, lead["estatus"]),
                help=f"Sugerido para {sector_actual} en «{lead['estatus']}»: "
                     f"${db.valor_sugerido(sector_actual, lead['estatus']):,.0f}. "
                     "Diagnóstico $3,500-5,000 · Sistema $12,000-18,000 · Mensualidad $1,500-2,500.",
            )
            proxima = st.text_input("Próxima acción", value=lead["proxima_accion"] or "")
            notas = st.text_area("Notas", value=lead["notas"] or "", height=100)
            nueva_plantilla = st.text_area(
                "Plantilla guardada de este lead",
                value=lead["mensaje_plantilla"] or "",
                height=120,
                help="Se guarda con las {variables} sin rellenar.",
            )
            if st.form_submit_button("💾 Guardar", type="primary"):
                if nuevo_estatus != lead["estatus"]:
                    db.cambiar_estatus(lead_id, nuevo_estatus)
                    if nuevo_estatus == "Cerrado - Ganado":
                        acreditados = db.registrar_conversion_dolores(lead_id)
                        if acreditados:
                            st.toast(f"{acreditados} dolor(es) acreditados como convertidos", icon="🎯")
                db.actualizar_lead(
                    lead_id,
                    sector=nuevo_sector,
                    valor_estimado=nuevo_valor,
                    fecha_contacto=nueva_fecha,
                    proxima_accion=proxima,
                    notas=notas,
                    mensaje_plantilla=nueva_plantilla,
                )
                st.toast("Lead actualizado", icon="✅")
                st.rerun()

    # ---- Historial ----
    st.markdown("### 🕘 Historial de contacto")
    hist = db.historial(lead_id)
    if hist.empty:
        st.caption("Sin registros todavía.")
    else:
        for _, fila in hist.iterrows():
            with st.expander(f"{fila['fecha'][:16].replace('T', ' ')} · {fila['tipo']}"
                             + (f" · {fila['canal']}" if fila["canal"] else "")):
                if fila["mensaje"]:
                    st.text(fila["mensaje"])
                if fila["detalle"]:
                    st.caption(fila["detalle"])

    with st.form(f"nota_{lead_id}", clear_on_submit=True):
        nota = st.text_input("Agregar nota al historial", placeholder="Contestó que lo ve el lunes…")
        if st.form_submit_button("➕ Agregar nota") and nota.strip():
            db.registrar_contacto(lead_id, tipo="Nota", detalle=nota.strip())
            st.rerun()


# --------------------------------------------------------------------------- #
# Vista 1 · HOY — pantalla de entrada
# --------------------------------------------------------------------------- #

MAX_EN_HOY = 7


def vista_hoy() -> None:
    st.header("🎯 Hoy")

    df = db.listar_leads()
    if df.empty:
        st.info("Todavía no hay leads. Empieza en **📥 Cargar leads** o en ⚙️ Datos y ajustes.")
        return

    priorizados = scoring.leads_priorizados(df)

    # ---- Alerta de patrón: calientes abandonados ----
    calientes = scoring.calientes_desatendidos(df)
    if calientes:
        nombres = ", ".join(l["negocio"] for l in calientes[:3])
        resto = f" y {len(calientes) - 3} más" if len(calientes) > 3 else ""
        st.error(
            f"**Tienes {len(calientes)} lead(s) calientes sin seguimiento** ({nombres}{resto}). "
            "Antes de buscar prospectos nuevos, cierra estos.",
            icon="🚨",
        )

    # ---- Siguiente mejor acción ----
    accion = scoring.siguiente_mejor_accion(priorizados)
    if accion is None:
        st.success("No hay leads abiertos. Todo está cerrado — toca prospectar. 🎉")
        return

    lead_top = accion["lead"]
    with st.container(border=True):
        st.caption("SIGUIENTE MEJOR ACCIÓN")
        st.markdown(f"## {accion['frase']}")
        detalle = [
            f"{scoring.EMOJI_TEMPERATURA[lead_top['temperatura']]} {lead_top['temperatura']} · score {lead_top['score']}",
            f"{COLOR_ESTATUS.get(lead_top['estatus'], '')} {lead_top['estatus']}",
            lead_top.get("sector") or "—",
            f"${float(lead_top.get('valor_estimado') or 0):,.0f}",
        ]
        st.caption(" · ".join(detalle))

        c1, c2 = st.columns(2)
        c1.button(
            f"💬 Abrir a {lead_top['negocio']}",
            type="primary", width="stretch",
            on_click=ir_a, args=(VISTAS[2], int(lead_top["id"])), key="hoy_ir_top",
        )
        url_top = whatsapp.link_whatsapp(
            lead_top["telefono"],
            plantillas.render(lead_top["mensaje_plantilla"], lead_top,
                              db.get_ajuste("nombre_remitente", "Gerardo")),
            db.get_ajuste("lada_default", "52"),
        )
        if url_top:
            c2.link_button("📲 WhatsApp directo", url_top, width="stretch")
        else:
            c2.button("📲 Sin teléfono", disabled=True, width="stretch", key="hoy_sin_tel")

    # ---- Lista corta de pendientes ----
    pendientes = [l for l in priorizados if l["plan"]["toca"] or l["plan"]["agotado"]]
    if not pendientes:
        st.success("Nada vencido hoy. Los siguientes toques todavía no tocan. 🎉")
        pendientes = priorizados[:3]
        st.caption("Aun así, estos son los que más pesan ahora mismo:")
    else:
        st.subheader(f"Necesitan algo hoy ({len(pendientes)})")
        if len(pendientes) > MAX_EN_HOY:
            st.caption(f"Se muestran los {MAX_EN_HOY} más urgentes de {len(pendientes)}. "
                       "El resto está en 📋 Leads.")

    mi_nombre = db.get_ajuste("nombre_remitente", "Gerardo")
    lada = db.get_ajuste("lada_default", "52")

    for lead in pendientes[:MAX_EN_HOY]:
        _tarjeta_seguimiento(lead, mi_nombre, lada)


def _tarjeta_seguimiento(lead: dict, mi_nombre: str, lada: str) -> None:
    """Tarjeta de un lead en la vista HOY: razón, mensaje sugerido y acciones."""
    lead_id = int(lead["id"])
    plan = lead["plan"]
    dias = lead.get("dias_desde_contacto")

    with st.container(border=True):
        enc1, enc2 = st.columns([4, 1])
        enc1.markdown(f"**{lead['negocio']}** · {lead.get('sector') or '—'}")
        enc1.caption(f"{lead['razon']}")
        enc2.markdown(
            f"### {scoring.EMOJI_TEMPERATURA[lead['temperatura']]} {lead['score']}"
        )

        if plan["agotado"]:
            st.warning(
                f"Ya se mandaron los {len(scoring.CALENDARIO.get(lead['estatus'], []))} "
                "seguimientos de esta etapa sin respuesta. Toca decidir: insistir con otro "
                "ángulo o cerrarlo como perdido para dejar de cargarlo.",
                icon="🤔",
            )

        variante = st.selectbox(
            "Mensaje",
            list(plantillas.SEGUIMIENTOS),
            index=list(plantillas.SEGUIMIENTOS).index(plan["plantilla"])
            if plan["plantilla"] in plantillas.SEGUIMIENTOS else 0,
            key=f"var_{lead_id}",
            help=f"Sugerido por el calendario: toque #{plan['numero']} de la etapa "
                 f"«{lead['estatus']}».",
        )
        key_seg = f"seg_{lead_id}_{variante}"
        if key_seg not in st.session_state:
            st.session_state[key_seg] = plantillas.render(
                plantillas.SEGUIMIENTOS[variante], lead, mi_nombre
            )
        texto = st.text_area("Texto", key=key_seg, height=104, label_visibility="collapsed")

        url = whatsapp.link_whatsapp(lead["telefono"], texto, lada)
        b1, b2, b3 = st.columns([2, 1, 1])

        if url:
            if b1.button("📲 Abrir WhatsApp y registrar", key=f"wa_{lead_id}",
                         type="primary", width="stretch"):
                db.marcar_contactado(lead_id, mensaje=texto, canal="WhatsApp", tipo="Seguimiento")
                st.session_state[f"abrir_{lead_id}"] = url
                st.rerun()
        else:
            b1.info("Sin teléfono — mándalo por DM y usa *Marcar enviado*.")

        with b2:
            boton_copiar(texto, "📋 Copiar", key=f"cs{lead_id}")

        if b3.button("✍️ Marcar enviado", key=f"me_{lead_id}", width="stretch"):
            db.marcar_contactado(lead_id, mensaje=texto, canal=lead["plataforma"], tipo="Seguimiento")
            st.rerun()

        d1, d2, d3 = st.columns(3)
        if d1.button("🟢 Ya respondió", key=f"resp_{lead_id}", width="stretch"):
            db.registrar_respuesta(lead_id)
            st.rerun()
        d2.button("👁️ Ver detalle", key=f"det_{lead_id}", width="stretch",
                  on_click=ir_a, args=(VISTAS[2], lead_id))
        if d3.button("⛔ Cerrar perdido", key=f"no_{lead_id}", width="stretch"):
            db.cambiar_estatus(lead_id, "Cerrado - Perdido",
                               nota=f"Sin respuesta tras {dias} días")
            st.rerun()

        pendiente_url = st.session_state.pop(f"abrir_{lead_id}", None)
        if pendiente_url:
            st.success("Seguimiento registrado en el historial.")
            abrir_whatsapp(pendiente_url, key=f"was{lead_id}")


# --------------------------------------------------------------------------- #
# Vista 4 · Banco de dolores y generador de diagnósticos
# --------------------------------------------------------------------------- #

def vista_dolores() -> None:
    st.header("🩺 Dolores y diagnósticos")

    tab_banco, tab_generar = st.tabs(["Banco de dolores", "Generar diagnóstico"])

    with tab_banco:
        _tab_banco_dolores()
    with tab_generar:
        _tab_generar_diagnostico()


def _tab_banco_dolores() -> None:
    st.caption(
        "Lo que la investigación ya enseñó que duele, por sector. Ordenados por tasa de "
        "conversión: los que más venden aparecen primero."
    )

    sector = st.selectbox("Sector", ["(todos)", *db.SECTORES], key="banco_sector")
    dolores = db.listar_dolores(None if sector == "(todos)" else sector)

    if dolores.empty:
        st.info(f"No hay dolores registrados para {sector}. Agrégalos abajo.")
    else:
        tabla = dolores[
            ["sector", "severidad", "etapa", "titulo", "veces_usado", "veces_convirtio",
             "tasa_conversion"]
        ].copy()
        st.dataframe(
            tabla,
            width="stretch",
            hide_index=True,
            column_config={
                "sector": st.column_config.TextColumn("Sector", width="small"),
                "severidad": st.column_config.TextColumn("Sev.", width="small"),
                "etapa": st.column_config.TextColumn("Etapa del recorrido"),
                "titulo": st.column_config.TextColumn("Dolor", width="large"),
                "veces_usado": st.column_config.NumberColumn("Usado", width="small"),
                "veces_convirtio": st.column_config.NumberColumn("Cerró", width="small"),
                "tasa_conversion": st.column_config.ProgressColumn(
                    "Conversión", min_value=0.0, max_value=1.0, format="%.0f%%"
                ),
            },
        )
        st.caption("«Conversión» vacía = todavía no se ha usado en ningún diagnóstico cerrado.")

        with st.expander("Ver el detalle de cada dolor"):
            for d in dolores.to_dict("records"):
                marca = "🔴" if d["severidad"] == "GRAVE" else "🟡"
                st.markdown(f"**{marca} {d['titulo']}** · _{d['sector']}_")
                if d.get("etapa"):
                    st.caption(f"Etapa: {d['etapa']} — {d.get('contexto') or ''}")
                st.write(d["descripcion"])
                if d.get("efecto"):
                    st.caption(f"Efecto: {d['efecto']}")
                st.divider()

    st.subheader("Agregar un dolor")
    with st.form("nuevo_dolor", clear_on_submit=True):
        d1, d2, d3 = st.columns([2, 1, 2])
        nuevo_sector = d1.selectbox("Sector", db.SECTORES)
        severidad = d2.selectbox("Severidad", db.SEVERIDADES)
        etapa = d3.text_input("Etapa del recorrido", placeholder="Llega el interés")
        titulo = st.text_input("Título del dolor *", placeholder="El CRM no ve toda la demanda")
        contexto = st.text_input("Línea de contexto", placeholder="Varias puertas, un solo equipo.")
        descripcion = st.text_area("Descripción (es lo que se lee en el diagnóstico)", height=110)
        efecto = st.text_input("Efecto", placeholder="El CRM reporta menos clientes de los que tocaron la puerta.")
        if st.form_submit_button("➕ Agregar al banco", type="primary"):
            if not titulo.strip():
                st.error("El título es obligatorio.")
            else:
                db.crear_dolor(nuevo_sector, titulo, descripcion, severidad, efecto, etapa, contexto)
                st.success(f"«{titulo.strip()}» agregado al banco de {nuevo_sector}.")
                st.rerun()


def _tab_generar_diagnostico() -> None:
    df = db.listar_leads()
    if df.empty:
        st.info("Primero necesitas leads.")
        return

    ids = df["id"].tolist()
    actual = st.session_state.get("lead_sel")
    lead_id = st.selectbox(
        "Lead",
        ids,
        index=ids.index(actual) if actual in ids else 0,
        format_func=lambda i: f"{df.loc[df['id'] == i, 'negocio'].iloc[0]}",
        key="dx_lead",
    )
    lead = db.obtener_lead(int(lead_id))
    if lead is None:
        return

    sector = lead.get("sector") or "Otro"
    st.caption(f"Sector del lead: **{sector}** · estatus **{lead['estatus']}**")

    # ---- Checklist de dolores del sector ----
    banco = db.listar_dolores(sector)
    if banco.empty:
        st.warning(
            f"No hay dolores registrados para el sector **{sector}**. "
            "Agrégalos en la pestaña *Banco de dolores* o cambia el sector del lead."
        )
        banco = db.listar_dolores()
        if banco.empty:
            return
        st.caption("Mientras tanto, se muestran todos los sectores:")

    st.markdown("**Hallazgos a incluir** — busca si el negocio tiene esto:")
    ya_asignados = set(db.dolores_del_lead(int(lead_id)))
    seleccionados = []
    for d in banco.to_dict("records"):
        marca = "🔴" if d["severidad"] == "GRAVE" else "🟡"
        etiqueta = f"{marca} {d['titulo']}"
        if d["veces_usado"]:
            tasa = d["tasa_conversion"]
            etiqueta += f"  ·  usado {int(d['veces_usado'])}×"
            if tasa == tasa:  # no es NaN
                etiqueta += f", cierra {tasa:.0%}"
        if st.checkbox(etiqueta, value=d["id"] in ya_asignados, key=f"dol_{lead_id}_{d['id']}"):
            seleccionados.append(d)

    st.divider()
    c1, c2 = st.columns(2)
    titular_1 = c1.text_input("Titular (línea 1)", value="Dónde sangra", key=f"t1_{lead_id}")
    titular_2 = c2.text_input("Titular (línea 2, en cursiva)", value="el embudo.", key=f"t2_{lead_id}")

    puertas = st.text_area(
        "Puertas de entrada detectadas",
        value=st.session_state.get(f"puertas_{lead_id}", _puertas_sugeridas(lead)),
        key=f"puertas_{lead_id}",
        height=140,
        help="Una por línea, en formato «Canal: detalle». Ej: Instagram: @cuenta · 5,361 seg.",
    )
    premisa = st.text_area(
        "Premisa de apertura", value=diagnostico.PREMISA_DEFAULT, height=120, key=f"prem_{lead_id}"
    )

    st.info(
        "La nota de honestidad del pie y la firma no son editables: se omiten cifras de "
        "pérdida estimadas porque inventar un número sin datos no es diagnóstico, es "
        "publicidad. Es la parte que más credibilidad da.",
        icon="🔒",
    )

    if st.button("🩺 Generar diagnóstico", type="primary", disabled=not seleccionados):
        resultado = diagnostico.generar_para_lead(
            lead, seleccionados, puertas, (titular_1, titular_2), premisa
        )
        db.asignar_dolores(int(lead_id), [d["id"] for d in seleccionados])
        db.actualizar_lead(
            int(lead_id),
            token_diagnostico=resultado["token"],
            diagnostico_url=resultado["url"],
        )
        db.registrar_contacto(
            int(lead_id), tipo="Nota",
            detalle=f"Diagnóstico generado con {len(seleccionados)} hallazgo(s).",
        )
        st.session_state["dx_resultado"] = {
            **resultado,
            "archivo": str(resultado["archivo"]),
            "carpeta": str(resultado["carpeta"]),
        }
        st.rerun()

    if not seleccionados:
        st.caption("Selecciona al menos un hallazgo para poder generar.")

    resultado = st.session_state.pop("dx_resultado", None)
    if resultado:
        st.success(f"Diagnóstico generado en `{resultado['archivo']}`")
        st.code(resultado["url"], language=None)
        st.caption(
            "La carpeta lleva un token impredecible y la página va con `noindex`: "
            "no sale en Google y el link no se puede adivinar. Quien lo tenga, lo ve — "
            "mándalo solo al prospecto."
        )
        if not db.get_ajuste("base_url_diagnosticos", ""):
            st.warning(
                "Configura la **URL base de diagnósticos** en ⚙️ Datos y ajustes para que "
                "el link salga completo."
            )

        g1, g2 = st.columns(2)
        with open(resultado["archivo"], "rb") as f:
            g1.download_button("⬇️ Descargar el HTML", f.read(),
                               file_name=f"diagnostico-{resultado['slug']}.html",
                               mime="text/html", width="stretch")
        if g2.button("📤 Publicar en el portafolio", width="stretch"):
            try:
                destino = diagnostico.publicar(Path(resultado["carpeta"]))
                st.success(f"Copiado a `{destino}`")
                st.caption("Falta el paso que decides tú: revisa, y luego en esa carpeta")
                st.code(f'git add . && git commit -m "diagnóstico nuevo" && git push',
                        language="bash")
            except Exception as exc:
                st.error(str(exc))

    # ---- Estado del envío y de la apertura ----
    st.divider()
    st.subheader("Envío y apertura")
    e1, e2, e3 = st.columns(3)
    e1.metric("Aperturas", int(lead.get("aperturas") or 0))
    e2.metric("Última apertura", lead.get("ultima_apertura") or "—")
    e3.metric("Enviado", lead.get("diagnostico_enviado_en") or "—")

    if lead.get("diagnostico_url"):
        st.caption(f"Link del lead: `{lead['diagnostico_url']}`")
        b1, b2 = st.columns(2)
        if b1.button("📤 Marcar diagnóstico como enviado", width="stretch"):
            db.actualizar_lead(
                int(lead_id),
                diagnostico_enviado_en=date.today().isoformat(),
                estatus=db.avanzar_estatus(lead["estatus"], "Diagnóstico enviado"),
            )
            db.registrar_contacto(int(lead_id), tipo="Nota", detalle="Diagnóstico enviado al prospecto.")
            st.rerun()
        if b2.button("👀 Marcar que lo abrió (manual)", width="stretch",
                     help="Úsalo si no tienes Goatcounter configurado o si te consta que lo vio."):
            tracking.marcar_apertura_manual(int(lead_id))
            st.rerun()


def _puertas_sugeridas(lead: dict) -> str:
    """Arranque para el campo de puertas, con lo que ya sabemos del lead."""
    lineas = []
    if lead.get("telefono"):
        lineas.append(f"WhatsApp: {lead['telefono']}")
    if lead.get("plataforma") and lead["plataforma"] != "WhatsApp":
        lineas.append(f"{lead['plataforma']}: ")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- #
# Vista 6 · Métricas por sector
# --------------------------------------------------------------------------- #

def vista_metricas() -> None:
    st.header("📊 Métricas por sector")
    st.caption(
        "Para decidir dónde enfocar con datos propios en vez de proyecciones. "
        "Con pocos leads los porcentajes son ruidosos — el conteo manda."
    )

    tabla = metricas.por_sector()
    if tabla.empty:
        st.info("Todavía no hay leads que medir.")
        return

    st.dataframe(
        tabla,
        width="stretch",
        hide_index=True,
        column_config={
            "sector": st.column_config.TextColumn("Sector"),
            "leads": st.column_config.NumberColumn("Leads", width="small"),
            "contactados": st.column_config.NumberColumn("Contactados", width="small"),
            "tasa_respuesta": st.column_config.ProgressColumn(
                "Tasa de respuesta", min_value=0.0, max_value=1.0, format="%.0f%%"
            ),
            "tasa_apertura": st.column_config.ProgressColumn(
                "Apertura del dx", min_value=0.0, max_value=1.0, format="%.0f%%"
            ),
            "tasa_cierre": st.column_config.ProgressColumn(
                "Tasa de cierre", min_value=0.0, max_value=1.0, format="%.0f%%"
            ),
            "ticket_promedio": st.column_config.NumberColumn("Ticket promedio", format="$%.0f"),
            "dias_ciclo": st.column_config.NumberColumn("Días de ciclo", format="%.0f"),
            "pipeline_ponderado": st.column_config.NumberColumn("Pipeline pond.", format="$%.0f"),
        },
    )

    st.caption(
        "**Tasa de respuesta** = leads que llegaron al menos a «Interesado» ÷ contactados. "
        "**Apertura del dx** = leads con al menos una apertura ÷ leads con diagnóstico enviado. "
        "**Cierre** = ganados ÷ (ganados + perdidos). **Días de ciclo** = del primer contacto al cierre ganado."
    )

    prioritarios = ", ".join(db.SECTORES_PRIORITARIOS)
    st.info(
        f"Sectores prioritarios hoy: **{prioritarios}** (fitness/salud), con Restaurantes y "
        "Dental corriendo en paralelo. Cuando estas métricas tengan volumen suficiente, "
        "que decidan ellas y no la corazonada.",
        icon="🎯",
    )

    faltantes = metricas.sectores_sin_datos(tabla)
    if faltantes:
        st.warning(
            "Sin datos todavía en: " + ", ".join(faltantes)
            + ". No hay nada que concluir de esos sectores.",
        )


# --------------------------------------------------------------------------- #
# Vista 5 · Cargar leads desde archivo
# --------------------------------------------------------------------------- #

def vista_cargar() -> None:
    st.header("📥 Cargar leads")
    st.caption(
        "Sube un Excel o CSV con leads nuevos. Se muestra una vista previa antes de "
        "insertar nada, y los que ya existen se omiten solos."
    )

    # El resumen se pinta arriba porque tras insertar, el mismo archivo ya cargado
    # pasa a contarse como duplicado y la vista previa de abajo sale vacía.
    hecho = st.session_state.pop("resumen_carga", None)
    if hecho:
        st.success(
            f"**{hecho['agregados']} leads agregados**, {hecho['duplicados']} duplicados omitidos, "
            f"{hecho['sin_mensaje']} con mensaje pendiente de completar."
        )
        if hecho["sin_mensaje"]:
            st.info(
                "Los que quedaron sin mensaje aparecen en 📋 Leads con la columna *Mensaje "
                "plantilla* vacía — puedes escribirlo ahí mismo o en la vista de detalle."
            )

    with st.expander("¿Qué columnas debe traer el archivo?"):
        st.markdown(
            "Solo **negocio** es obligatoria. El resto es opcional y lo que falte se "
            "deja vacío para completarlo después desde la app:\n\n"
            + "\n".join(
                f"- `{c}` — {importador.etiqueta(c)}" + ("  ← obligatoria" if c == "negocio" else "")
                for c in importador.COLUMNAS_ESPERADAS
            )
            + "\n\nLos encabezados se reconocen sin importar acentos, mayúsculas ni "
            "variantes comunes (*Teléfono*, *Plataforma recomendada*, *Evidencia de dolor…*). "
            "`estatus`, `fecha_contacto`, `proxima_accion` y `notas` no se importan: "
            "los llenas tú desde la app."
        )
        st.download_button(
            "⬇️ Descargar plantilla CSV de ejemplo",
            importador.plantilla_csv(),
            file_name="plantilla_leads.csv",
            mime="text/csv",
        )

    archivo = st.file_uploader("Archivo de leads", type=["xlsx", "xlsm", "csv"])
    if archivo is None:
        st.info("Arrastra aquí un `.xlsx` o `.csv` para empezar.")
        return

    try:
        crudo = importador.leer_archivo(archivo, archivo.name)
        preparado, reporte = importador.preparar(crudo)
    except Exception as exc:
        st.error(f"No pude leer el archivo: {exc}")
        return

    if reporte["filas"] == 0:
        st.warning("El archivo no tiene filas con datos.")
        return

    st.markdown("### Vista previa")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Filas leídas", reporte["filas"])
    m2.metric("Nuevos a insertar", reporte["insertables"])
    m3.metric("Duplicados", reporte["duplicados"] + reporte["repetidos"])
    m4.metric("Sin mensaje", reporte["sin_mensaje"])

    if reporte["columnas_faltantes"]:
        st.warning(
            "Columnas que no venían en el archivo (se quedan vacías): "
            + ", ".join(f"`{c}`" for c in reporte["columnas_faltantes"])
        )
    if reporte["columnas_ignoradas"]:
        st.caption("Columnas ignoradas del archivo: " + ", ".join(reporte["columnas_ignoradas"]))
    if reporte["sin_negocio"]:
        st.warning(f"{reporte['sin_negocio']} fila(s) sin nombre de negocio: se van a omitir.")

    solo_nuevos = st.checkbox("Ver solo los que se van a insertar", value=False)
    tabla = preparado[preparado["_estado"].isin(importador.ESTADOS_INSERTABLES)] if solo_nuevos else preparado

    st.dataframe(
        tabla.rename(columns={
            **{c: importador.etiqueta(c) for c in importador.COLUMNAS_ESPERADAS},
            "_estado": "Estado",
        }),
        width="stretch",
        hide_index=True,
        column_order=["Estado", *[importador.etiqueta(c) for c in importador.COLUMNAS_ESPERADAS]],
    )
    st.caption(
        f"{importador.ESTADO_SIN_MENSAJE} = se inserta igual, pero hay que escribirle el "
        "mensaje antes de contactarlo. · Duplicado = mismo negocio y mismo teléfono que "
        "un lead que ya tienes."
    )

    if reporte["insertables"] == 0:
        st.info("No hay nada nuevo que insertar: todos los leads del archivo ya están en tu base.")
        return

    if st.button(f"✅ Confirmar carga de {reporte['insertables']} lead(s)", type="primary"):
        st.session_state["resumen_carga"] = importador.insertar(preparado)
        st.rerun()


# --------------------------------------------------------------------------- #
# Vista 5 · Datos y ajustes
# --------------------------------------------------------------------------- #

def vista_datos() -> None:
    st.header("⚙️ Datos y ajustes")

    st.subheader("Ajustes")
    with st.form("ajustes"):
        nombre = st.text_input("Tu nombre (variable {mi_nombre})", value=db.get_ajuste("nombre_remitente"))
        lada = st.text_input("Lada de país por defecto", value=db.get_ajuste("lada_default"),
                             help="Se antepone a teléfonos de 10 dígitos. México = 52.")
        base_url = st.text_input(
            "URL base de los diagnósticos",
            value=db.get_ajuste("base_url_diagnosticos"),
            placeholder="https://gerardobr01.github.io/portafolio",
            help="Dónde quedan publicados los diagnósticos (GitHub Pages del repo de "
                 "portafolio). Se usa para armar el link que le mandas al prospecto.",
        )
        ruta_portafolio = st.text_input(
            "Carpeta local del repo de portafolio",
            value=db.get_ajuste("ruta_repo_portafolio"),
            placeholder=r"C:\Users\jesus\portafolio",
            help="Dónde tienes clonado el repo de portafolio. El botón «Publicar» copia "
                 "ahí el diagnóstico; el commit y el push los das tú.",
        )
        gc_sitio = st.text_input(
            "Sitio de Goatcounter",
            value=db.get_ajuste("goatcounter_sitio"),
            placeholder="https://tucuenta.goatcounter.com",
            help="Para saber si abrieron el diagnóstico. Sin cookies y sin datos personales.",
        )
        if st.form_submit_button("💾 Guardar ajustes", type="primary"):
            db.set_ajuste("nombre_remitente", nombre.strip() or "Gerardo")
            db.set_ajuste("lada_default", "".join(c for c in lada if c.isdigit()) or "52")
            db.set_ajuste("base_url_diagnosticos", base_url.strip())
            db.set_ajuste("ruta_repo_portafolio", ruta_portafolio.strip())
            db.set_ajuste("goatcounter_sitio", gc_sitio.strip())
            st.toast("Ajustes guardados", icon="✅")
            st.rerun()

    st.subheader("Aperturas del diagnóstico")
    if tracking.configurado():
        st.caption("Goatcounter configurado. Sincroniza para traer las visitas recientes.")
        if st.button("🔄 Sincronizar aperturas"):
            try:
                res = tracking.sincronizar()
                st.success(
                    f"{res['leads_actualizados']} lead(s) actualizados de "
                    f"{res['rutas_con_visitas']} ruta(s) con visitas."
                )
                if res["nuevos_vistos"]:
                    st.info("Abrieron el diagnóstico por primera vez: "
                            + ", ".join(res["nuevos_vistos"]))
            except tracking.TrackingNoConfigurado as exc:
                st.warning(str(exc))
            except Exception as exc:
                st.error(f"No se pudo consultar Goatcounter: {exc}")
    else:
        st.info(
            "**Tracking desactivado.** Para activarlo: crea una cuenta gratis en "
            "goatcounter.com, pon la URL de tu sitio aquí arriba, y guarda el token de "
            "la API como `GOATCOUNTER_TOKEN` en `.streamlit/secrets.toml` o como variable "
            "de entorno. Mientras tanto puedes marcar las aperturas a mano desde "
            "🩺 Dolores y diagnósticos.",
            icon="ℹ️",
        )
    st.caption(
        "Privacidad: esto solo mide si se abrió una página propia que tú enviaste. "
        "Sin cookies, sin datos personales, sin perfilar y sin terceros publicitarios."
    )

    st.divider()
    st.subheader("Importar desde Excel")
    st.caption("Lee la pestaña **Leads** de `leads_tracker.xlsx`. No duplica: identifica por nombre de negocio.")

    import migrate_excel

    ruta_default = ""
    for p in migrate_excel.RUTAS_CANDIDATAS:
        if p.exists():
            ruta_default = str(p)
            break

    ruta = st.text_input("Ruta del archivo .xlsx", value=ruta_default,
                         placeholder=r"C:\Users\...\leads_tracker.xlsx")
    i1, i2 = st.columns(2)
    actualizar = i1.checkbox("Sobrescribir leads que ya existen")
    reset = i2.checkbox("⚠️ Vaciar la base antes de importar (borra historial)")

    if st.button("📥 Importar", type="primary", disabled=not ruta):
        try:
            r = migrate_excel.importar(Path(ruta), reset=reset, actualizar=actualizar)
            st.success(
                f"Leídos {r['leidos']} · nuevos {r['creados']} · actualizados {r['actualizados']} "
                f"· ya existían {r['omitidos']}"
            )
        except Exception as exc:  # ruta mala, pestaña inexistente, archivo abierto en Excel…
            st.error(f"No se pudo importar: {exc}")

    st.divider()
    st.subheader("Exportar y respaldar")
    df = db.listar_leads()
    x1, x2 = st.columns(2)
    if not df.empty:
        x1.download_button(
            "⬇️ Leads en CSV",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"leads_{date.today().isoformat()}.csv",
            mime="text/csv",
            width="stretch",
        )
    x2.download_button(
        "🗄️ Respaldo completo (ZIP)",
        db.exportar_todo(),
        file_name=f"crm_respaldo_{date.today().isoformat()}.zip",
        mime="application/zip",
        width="stretch",
        help="Todas las tablas (leads, contactos, dolores, ajustes) en CSVs. "
             "Hazlo antes de tocar el código o de migrar a la nube.",
    )

    st.divider()
    st.subheader("Agregar lead a mano")
    with st.form("nuevo_lead", clear_on_submit=True):
        n1, n2, n3 = st.columns(3)
        negocio = n1.text_input("Negocio *")
        sector = n2.selectbox("Sector", db.SECTORES)
        categoria = n3.text_input("Categoría")
        direccion = st.text_input("Dirección")
        n4, n5, n6 = st.columns(3)
        telefono = n4.text_input("Teléfono", placeholder="+52 33 1234 5678")
        plataforma = n5.selectbox("Plataforma", db.PLATAFORMAS)
        estatus_nuevo = n6.selectbox("Estatus", db.ESTATUS)
        valor = st.number_input(
            "Valor estimado (MXN)", min_value=0.0, step=500.0,
            value=db.valor_sugerido(sector, estatus_nuevo),
            help="Se sugiere según sector y etapa; ajústalo a mano si el caso lo amerita.",
        )
        evidencia = st.text_area("Evidencia de dolor", height=80)
        notas_nuevas = st.text_area("Notas", height=70)
        mensaje = st.text_area("Mensaje plantilla", value=plantillas.PLANTILLA_NUEVA, height=110)
        if st.form_submit_button("➕ Crear lead", type="primary"):
            if not negocio.strip():
                st.error("El negocio es obligatorio.")
            else:
                db.crear_lead(
                    negocio=negocio.strip(), sector=sector, categoria=categoria.strip(),
                    direccion=direccion.strip(), telefono=telefono.strip(), plataforma=plataforma,
                    estatus=estatus_nuevo, valor_estimado=valor,
                    evidencia_dolor=evidencia.strip(), notas=notas_nuevas.strip(),
                    mensaje_plantilla=mensaje.strip(),
                )
                st.success(f"Lead «{negocio.strip()}» creado.")

    st.divider()
    st.caption(f"Base de datos: `{db.DB_PATH}`")
    with st.expander("¿Por qué la app no envía los mensajes sola?"):
        st.markdown(
            "Automatizar envíos a contactos fríos con librerías no oficiales "
            "(whatsapp-web.js, Baileys, Selenium sobre WhatsApp Web) **viola los Términos "
            "de Servicio de WhatsApp/Meta** y en la práctica termina en baneo permanente "
            "del número. No es un tecnicismo: le pasa seguido a cuentas que hacen outreach "
            "frío automatizado.\n\n"
            "Por eso esta app prepara y organiza, y tú das el clic final. La única vía "
            "automatizada legítima es la **WhatsApp Business API oficial** (Meta o Twilio), "
            "que requiere verificación de negocio y plantillas pre-aprobadas — vale la pena "
            "evaluarla como fase 2 si el volumen de leads crece bastante."
        )


# --------------------------------------------------------------------------- #

if vista == VISTAS[0]:
    vista_hoy()
elif vista == VISTAS[1]:
    vista_leads()
elif vista == VISTAS[2]:
    vista_detalle()
elif vista == VISTAS[3]:
    vista_dolores()
elif vista == VISTAS[4]:
    vista_cargar()
elif vista == VISTAS[5]:
    vista_metricas()
else:
    vista_datos()
