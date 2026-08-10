"""PWA y adaptación a pantalla de celular.

El requisito real no es "que se vea en el teléfono": es que Gerardo, en horas
laborales y a veces con mala señal, abra el CRM, vea a quién seguir, genere el
mensaje y lo mande por WhatsApp **en menos de cuatro toques**. Streamlit no es
mobile-first, así que eso hay que trabajarlo explícitamente o el resultado es una
app accesible y miserable.

Tres piezas:

1. `montar_pwa()` — el manifest y los iconos, para "Agregar a pantalla de inicio".
   Se abre como app, sin barra de navegador, en un toque.
2. `estilos()` — objetivos táctiles de 44 px, una sola columna en pantalla angosta,
   y el botón de WhatsApp destacado en cada tarjeta.
3. `SOLO_ESCRITORIO` / `SOLO_MOVIL` — llaves de contenedor para mostrar la tabla en
   escritorio y tarjetas en el celular. Una tabla de 17 columnas es inservible con
   el pulgar.

**Limitación conocida y aceptada:** sin señal no funciona nada. No hay modo offline
y no vale la pena construirlo en esta etapa.
"""

from __future__ import annotations

import streamlit as st

# Llaves de `st.container(key=...)`. Streamlit las publica como clase CSS
# `.st-key-<llave>`, que es lo que permite mostrar u ocultar por ancho de pantalla.
SOLO_ESCRITORIO = "solo_escritorio"
SOLO_MOVIL = "solo_movil"

# Debajo de esto se considera pantalla de pulgar.
CORTE_MOVIL = 820

RUTA_ESTATICA = "app/static"


def montar_pwa() -> None:
    """Inyecta el manifest y los meta de PWA en el `<head>` de la página.

    El manifest tiene que quedar en el documento principal: dentro de un iframe el
    navegador no lo ve y no ofrece instalar la app. `st.html` inyecta en el
    documento real, así que basta con `document`; el `window.parent` de respaldo
    está por si algún día vuelve a renderizarse dentro de un iframe.

    Requiere `enableStaticServing = true` en `.streamlit/config.toml`, que es lo que
    publica la carpeta `static/`.
    """
    st.html(
        f"""
        <script>
        (function () {{
          var doc = (window.parent && window.parent.document) || document;
          if (!doc || doc.getElementById("crm-pwa")) return;

          function etiqueta(tag, attrs) {{
            var el = doc.createElement(tag);
            for (var k in attrs) el.setAttribute(k, attrs[k]);
            doc.head.appendChild(el);
            return el;
          }}

          var marca = doc.createElement("meta");
          marca.id = "crm-pwa";
          doc.head.appendChild(marca);

          etiqueta("link", {{rel: "manifest", href: "{RUTA_ESTATICA}/manifest.json"}});
          etiqueta("link", {{rel: "apple-touch-icon", href: "{RUTA_ESTATICA}/apple-touch-icon.png"}});
          etiqueta("link", {{rel: "icon", type: "image/png", href: "{RUTA_ESTATICA}/favicon-32.png"}});
          etiqueta("meta", {{name: "theme-color", content: "#0C1E2A"}});
          etiqueta("meta", {{name: "mobile-web-app-capable", content: "yes"}});
          etiqueta("meta", {{name: "apple-mobile-web-app-capable", content: "yes"}});
          etiqueta("meta", {{name: "apple-mobile-web-app-status-bar-style", content: "black-translucent"}});
          etiqueta("meta", {{name: "apple-mobile-web-app-title", content: "Certeza"}});
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def estilos() -> None:
    """CSS de pantalla angosta. Todo lo de aquí solo aplica en el celular."""
    st.markdown(
        f"""
        <style>
        /* El botón de WhatsApp es la acción más frecuente del día: se ve primero. */
        .stButton button[kind="primary"] {{ font-weight: 600; }}

        /* Escritorio: las tarjetas de la lista larga no estorban. */
        @media (min-width: {CORTE_MOVIL + 1}px) {{
            .st-key-{SOLO_MOVIL} {{ display: none !important; }}
        }}

        @media (max-width: {CORTE_MOVIL}px) {{
            /* Una tabla de 17 columnas no se usa con el pulgar. */
            .st-key-{SOLO_ESCRITORIO} {{ display: none !important; }}

            /* Se recupera el ancho que Streamlit reserva para escritorio. */
            .block-container {{
                padding: 0.75rem 0.7rem 4.5rem !important;
                max-width: 100% !important;
            }}

            /* Las columnas se acomodan de dos en dos en vez de encogerse a nada. */
            [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; gap: 0.4rem; }}
            [data-testid="stColumn"] {{ min-width: 46% !important; flex: 1 1 46% !important; }}

            /* 44 px es el mínimo para acertarle con el pulgar sin pelear. */
            .stButton button, .stFormSubmitButton button, .stLinkButton a,
            .stDownloadButton button {{
                min-height: 46px !important;
                font-size: 0.95rem !important;
            }}
            [data-baseweb="select"] > div, .stTextInput input, .stNumberInput input,
            .stDateInput input {{ min-height: 44px !important; }}

            /* Títulos más compactos: en 6 pulgadas, un h1 se come la pantalla. */
            h1 {{ font-size: 1.5rem !important; }}
            h2 {{ font-size: 1.25rem !important; }}
            h3 {{ font-size: 1.05rem !important; }}

            /* La frase de "siguiente mejor acción" tiene que caber sin scroll. */
            .st-key-accion_hoy h2 {{ font-size: 1.15rem !important; line-height: 1.35; }}

            /* Las métricas de la ficha, de dos en dos y sin desbordar. */
            [data-testid="stMetricValue"] {{ font-size: 1.05rem !important; }}
            [data-testid="stMetricLabel"] {{ font-size: 0.72rem !important; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
