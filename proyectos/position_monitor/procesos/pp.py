from __future__ import annotations

# DESHABILITADO TEMPORALMENTE:
# PP no se expone en la interfaz ni participa en "Ejecutar todo".
# Antes de reactivarlo debe implementarse, validarse y ajustarse al nuevo
# formato definido para Position Monitor y al alcance vigente del portal.

import pandas as pd

from proyectos.position_monitor.procesos.posiciones_pendientes import crear_tabla_pendiente


def ejecutar_pp(fecha_trabajo: str, logger=None) -> pd.DataFrame:
    """Ejecuta el esqueleto de posicion PP."""
    return crear_tabla_pendiente("PP", fecha_trabajo, logger=logger)
