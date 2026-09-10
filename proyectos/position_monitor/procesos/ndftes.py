from __future__ import annotations

# DESHABILITADO TEMPORALMENTE:
# NDFTES no se expone en la interfaz ni participa en "Ejecutar todo".
# Antes de reactivarlo debe implementarse, validarse y ajustarse al nuevo
# formato definido para Position Monitor y al alcance vigente del portal.

import pandas as pd

from proyectos.position_monitor.procesos.posiciones_pendientes import crear_tabla_pendiente


def ejecutar_ndftes(fecha_trabajo: str, logger=None) -> pd.DataFrame:
    """Ejecuta el esqueleto de posicion NDFTES."""
    return crear_tabla_pendiente("NDFTES", fecha_trabajo, logger=logger)
