"""Plantillas de mensajes y relleno de variables por lead."""

from __future__ import annotations

import re

# Variables que se pueden usar dentro de una plantilla, con {llaves}.
VARIABLES = {
    "negocio": "Nombre del negocio",
    "categoria": "Giro / categoría",
    "direccion": "Dirección",
    "telefono": "Teléfono",
    "plataforma": "Plataforma de contacto",
    "evidencia_dolor": "Evidencia de dolor",
    "track_recomendado": "Track recomendado",
    "senales_investigacion": "Señales de investigación",
    "proxima_accion": "Próxima acción",
    "mi_nombre": "Tu nombre (ajustes)",
}

_PATRON = re.compile(r"\{([a-z_]+)\}")


def render(plantilla: str | None, lead: dict, mi_nombre: str = "Gerardo") -> str:
    """Rellena {variables} con los datos del lead.

    Las variables desconocidas se dejan tal cual para que se vean y se puedan
    corregir, en vez de romper con KeyError.

    >>> render("Hola {negocio}, soy {mi_nombre}", {"negocio": "Boutique Ejemplo"})
    'Hola Boutique Ejemplo, soy Gerardo'
    >>> render("Hola {no_existe}", {})
    'Hola {no_existe}'
    """
    if not plantilla:
        return ""
    datos = {k: ("" if lead.get(k) is None else str(lead.get(k))) for k in VARIABLES if k != "mi_nombre"}
    datos["mi_nombre"] = mi_nombre

    def _sub(m: re.Match) -> str:
        clave = m.group(1)
        return datos.get(clave, m.group(0))

    return _PATRON.sub(_sub, plantilla).strip()


def variables_faltantes(plantilla: str | None) -> list[str]:
    """Variables usadas en la plantilla que no existen en el modelo de datos."""
    if not plantilla:
        return []
    return sorted({v for v in _PATRON.findall(plantilla) if v not in VARIABLES})


# --------------------------------------------------------------------------- #
# Plantilla base para leads nuevos
# --------------------------------------------------------------------------- #

PLANTILLA_NUEVA = (
    "Hola! Soy {mi_nombre} — ayudo a negocios como {negocio} a automatizar procesos "
    "operativos (checklists, reportes, inventario) con IA. ¿Tienen 10 min esta semana "
    "para un diagnóstico rápido? Sin costo."
)

# --------------------------------------------------------------------------- #
# Segundo contacto: corto, sin repetir el pitch inicial, con salida fácil.
# --------------------------------------------------------------------------- #

SEGUIMIENTOS: dict[str, str] = {
    "Recordatorio suave": (
        "Hola! Te escribí hace unos días sobre automatizar parte de la operación de "
        "{negocio}. ¿Te late que te mande un ejemplo concreto de lo que haría en un "
        "negocio como el suyo?"
    ),
    "Con valor / ejemplo": (
        "Hola! Retomo mi mensaje anterior. Armé un ejemplo de cómo se vería un reporte "
        "automático para {negocio} — te lo puedo pasar en 2 min por aquí, sin compromiso. "
        "¿Te sirve?"
    ),
    "Cierre / última llamada": (
        "Hola! No quiero ser insistente — si no es el momento, sin problema y te dejo "
        "tranquilo. Si más adelante quieren revisar lo de automatizar reportes en "
        "{negocio}, aquí ando. Saludos, {mi_nombre}."
    ),
    "Pregunta directa": (
        "Hola! Una pregunta rápida sobre {negocio}: hoy, ¿quién se encarga de revisar "
        "que la operación diaria salga completa? Es justo la parte que automatizo."
    ),
}

SEGUIMIENTO_DEFAULT = "Recordatorio suave"


def sugerir_seguimiento(lead: dict, dias: int | None) -> str:
    """Elige la variante de seguimiento segun cuanto lleva sin respuesta."""
    if dias is None:
        return SEGUIMIENTO_DEFAULT
    if dias >= 12:
        return "Cierre / última llamada"
    if dias >= 8:
        return "Pregunta directa"
    if dias >= 6:
        return "Con valor / ejemplo"
    return SEGUIMIENTO_DEFAULT


if __name__ == "__main__":
    import doctest

    doctest.testmod(verbose=True)
