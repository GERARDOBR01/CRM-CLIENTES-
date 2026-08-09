"""Pruebas de consistencia entre los catálogos de campos.

Existen por un bug real: se agregó `contacto` a `CAMPOS_IMPORTABLES` pero no a
`ETIQUETAS`, y la vista «Cargar leads» reventó con KeyError hasta que alguien
la abrió. Estas comprobaciones lo cachan antes.

    python test_consistencia.py
"""

from __future__ import annotations

import sys

import db
import importador
import plantillas
import scoring


def _falla(mensaje: str) -> str:
    print(f"  FALLA  {mensaje}")
    return mensaje


def revisar() -> list[str]:
    errores: list[str] = []

    # 1. Todo campo importable necesita etiqueta legible.
    sin_etiqueta = [c for c in db.CAMPOS_IMPORTABLES if c not in importador.ETIQUETAS]
    if sin_etiqueta:
        errores.append(_falla(f"campos importables sin ETIQUETA: {sin_etiqueta}"))

    # 2. Todo campo importable tiene que existir en el modelo.
    fuera_del_modelo = [c for c in db.CAMPOS_IMPORTABLES if c not in db.CAMPOS]
    if fuera_del_modelo:
        errores.append(_falla(f"campos importables que no están en CAMPOS: {fuera_del_modelo}"))

    # 3. Cada estatus del pipeline necesita probabilidad, orden y peso de score.
    for estatus in db.ESTATUS:
        if estatus not in db.PROBABILIDAD_ESTATUS:
            errores.append(_falla(f"«{estatus}» sin PROBABILIDAD_ESTATUS"))
        if estatus not in scoring.PESOS["etapa"]:
            errores.append(_falla(f"«{estatus}» sin peso en scoring.PESOS['etapa']"))
        if estatus not in scoring.CALENDARIO and estatus not in db.ESTATUS_CERRADOS:
            errores.append(_falla(f"«{estatus}» abierto y sin entrada en scoring.CALENDARIO"))

    # 4. Los estatus a los que apunta la migración v1 deben existir hoy.
    for viejo, nuevo in db.MAPEO_ESTATUS_V1.items():
        if nuevo not in db.ESTATUS:
            errores.append(_falla(f"el mapeo «{viejo}» apunta a «{nuevo}», que no existe"))

    # 5. Los estatus calientes y cerrados tienen que ser estatus reales.
    for estatus in [*db.ESTATUS_CALIENTES, *db.ESTATUS_CERRADOS]:
        if estatus not in db.ESTATUS:
            errores.append(_falla(f"«{estatus}» no está en ESTATUS"))

    # 6. La escalera de plantillas tiene que apuntar a plantillas que existan.
    for nombre in scoring.ESCALERA_PLANTILLAS:
        if nombre not in plantillas.SEGUIMIENTOS:
            errores.append(_falla(f"la escalera usa la plantilla «{nombre}», que no existe"))

    # 7. Los sectores prioritarios tienen que ser sectores del catálogo.
    for sector in db.SECTORES_PRIORITARIOS:
        if sector not in db.SECTORES:
            errores.append(_falla(f"sector prioritario «{sector}» no está en SECTORES"))

    # 8. Las variables de plantilla tienen que ser campos reales del lead.
    for variable in plantillas.VARIABLES:
        if variable != "mi_nombre" and variable not in db.CAMPOS:
            errores.append(_falla(f"la variable {{{variable}}} no corresponde a un campo"))

    return errores


if __name__ == "__main__":
    print("Consistencia de catálogos:")
    fallos = revisar()
    if fallos:
        print(f"\n{len(fallos)} problema(s).")
        sys.exit(1)
    print("  todo consistente.")
