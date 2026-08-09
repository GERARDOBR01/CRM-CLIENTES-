"""Configuración por entorno y puerta de acceso.

Nada de rutas absolutas de Windows en el código: todo sale de variables de entorno
o de `st.secrets`, para que el mismo repo corra en local y en la nube.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def secreto(clave: str, default: str = "") -> str:
    """Lee de variables de entorno primero, luego de `st.secrets`.

    El entorno gana para que en local baste un `set VAR=...` sin crear secrets.toml.
    """
    valor = os.environ.get(clave, "").strip()
    if valor:
        return valor
    try:
        import streamlit as st

        return str(st.secrets.get(clave, default)).strip()
    except Exception:
        return default


def ruta_db() -> Path:
    """Ubicación de la base. `LEADS_DB` la mueve (útil para pruebas y para la nube)."""
    return Path(os.environ.get("LEADS_DB", RAIZ / "leads.db"))


def ruta_diagnosticos() -> Path:
    return Path(os.environ.get("DIAGNOSTICOS_DIR", RAIZ / "diagnosticos"))


def es_demo() -> bool:
    """Modo demostración: datos ficticios y efímeros.

    Se enciende con `DEMO=1` (o en secrets). Sirve para el despliegue público:
    quien abra el link tiene que saber que lo que ve es de muestra, y que lo que
    escriba ahí se borra cuando el contenedor se reinicia.
    """
    return secreto("DEMO", "").lower() in ("1", "true", "si", "sí", "yes")


# --------------------------------------------------------------------------- #
# Puerta de acceso
# --------------------------------------------------------------------------- #

def hay_password() -> bool:
    return bool(secreto("CRM_PASSWORD"))


def password_correcto(intento: str) -> bool:
    """Comparación en tiempo constante — no filtra la contraseña por timing."""
    esperado = secreto("CRM_PASSWORD")
    if not esperado:
        return True
    return hmac.compare_digest(
        hashlib.sha256(intento.encode()).hexdigest(),
        hashlib.sha256(esperado.encode()).hexdigest(),
    )


def exigir_password() -> bool:
    """Muro de contraseña. Devuelve True si se puede seguir.

    Si no hay `CRM_PASSWORD` configurada, no estorba: es el caso de correr en
    localhost. En cuanto la app se publica hay datos de prospectos de por medio,
    así que ahí sí conviene ponerla.
    """
    import streamlit as st

    if not hay_password():
        return True
    if st.session_state.get("_autenticado"):
        return True

    st.title("📇 CRM de Leads")
    st.caption("Esta instancia está protegida con contraseña.")
    with st.form("acceso"):
        intento = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if password_correcto(intento):
                st.session_state["_autenticado"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    st.stop()
    return False
