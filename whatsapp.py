"""Generacion de links "click-to-chat" de WhatsApp.

IMPORTANTE — limite de diseño deliberado:
Este modulo NO envia mensajes. Solo construye la URL oficial https://wa.me/... que
abre WhatsApp Web / la app con el texto ya escrito. El envio final siempre lo hace
una persona con un clic.

No se usa whatsapp-web.js, Baileys, Selenium sobre WhatsApp Web ni ninguna libreria
no oficial: automatizar envios a contactos frios viola los Terminos de Servicio de
WhatsApp/Meta y en la practica termina en baneo permanente del numero. La unica via
automatizada legitima es la WhatsApp Business API oficial (Meta/Twilio), que exige
verificacion de negocio y plantillas pre-aprobadas — fuera del alcance de este MVP.
"""

from __future__ import annotations

import re
from urllib.parse import quote

BASE = "https://wa.me/"

# Los navegadores manejan URLs largas sin problema, pero arriba de ~2000 caracteres
# algunos clientes de WhatsApp truncan el texto. Avisamos antes de llegar ahi.
LARGO_SEGURO_URL = 1800

# Texto que en el Excel original ocupaba el lugar del telefono cuando no habia uno.
_NO_ES_TELEFONO = re.compile(r"[a-zA-Z]{4,}")


def limpiar_telefono(raw: str | None, lada_default: str = "52") -> str | None:
    """Normaliza un telefono a solo digitos en formato internacional.

    Devuelve None si el valor no parece un telefono usable.

    >>> limpiar_telefono("+52 33 1593 4381")
    '523315934381'
    >>> limpiar_telefono("33 1593 4381")
    '523315934381'
    >>> limpiar_telefono("Sin teléfono público — buscar en Instagram")
    """
    if raw is None:
        return None
    texto = str(raw).strip()
    if not texto:
        return None

    tiene_mas = texto.startswith("+")
    # Si el campo trae una frase ("sin telefono publico...") y no un numero, se descarta.
    if _NO_ES_TELEFONO.search(texto) and not tiene_mas:
        digitos_sueltos = re.sub(r"\D", "", texto)
        if len(digitos_sueltos) < 10:
            return None

    digitos = re.sub(r"\D", "", texto)
    if not digitos:
        return None

    if not tiene_mas:
        # Numero nacional de 10 digitos (MX) -> se le antepone la lada de pais.
        if len(digitos) == 10:
            digitos = f"{lada_default}{digitos}"
        # Formato viejo de MX movil con 1 intermedio: 521XXXXXXXXXX -> se deja igual,
        # WhatsApp lo acepta; 11 digitos que empiezan con 1 se asumen nacionales +1.
    if len(digitos) < 10 or len(digitos) > 15:
        return None
    return digitos


def es_telefono_valido(raw: str | None, lada_default: str = "52") -> bool:
    return limpiar_telefono(raw, lada_default) is not None


def link_whatsapp(telefono: str | None, mensaje: str = "", lada_default: str = "52") -> str | None:
    """URL click-to-chat con el mensaje pre-escrito. None si el telefono no sirve."""
    numero = limpiar_telefono(telefono, lada_default)
    if numero is None:
        return None
    if not mensaje:
        return f"{BASE}{numero}"
    return f"{BASE}{numero}?text={quote(mensaje)}"


def url_demasiado_larga(url: str | None) -> bool:
    return bool(url) and len(url) > LARGO_SEGURO_URL


def links_busqueda_manual(negocio: str, direccion: str = "") -> dict[str, str]:
    """Para leads sin telefono: busquedas listas para abrir y encontrar el perfil
    de Instagram/Facebook a mano. Sigue siendo un proceso manual a proposito."""
    consulta = " ".join(x for x in [negocio, direccion] if x).strip()
    return {
        "Instagram (Google)": "https://www.google.com/search?q=" + quote(f'site:instagram.com "{negocio}"'),
        "Facebook (Google)": "https://www.google.com/search?q=" + quote(f'site:facebook.com "{negocio}"'),
        "Buscar el negocio": "https://www.google.com/search?q=" + quote(consulta),
        "Buscar en Instagram": "https://www.instagram.com/explore/search/keyword/?q=" + quote(negocio),
    }


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
