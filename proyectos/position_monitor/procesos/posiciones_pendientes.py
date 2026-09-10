from __future__ import annotations

import pandas as pd

from compartido.nucleo_risko.archivos import registrar_log
from compartido.nucleo_risko.tablas_auxiliares import guardar_tablas_auxiliares_modulo


COLUMNAS_POSICION = [
    "FECHA",
    "PRODUCTO",
    "BOOK",
    "POSICION",
    "MONEDA_POSICION",
    "LB_LT",
    "INSTRUMENTO",
    "COMPANY",
    "CLASIFICACION_CONTABLE",
    "BANKING_CVA_DVA",
]


def crear_tabla_pendiente(producto: str, fecha_trabajo: str, logger=None) -> pd.DataFrame:
    """Esqueleto ejecutable para posiciones pendientes de regla de negocio."""
    fecha = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha no valida para {producto}: {fecha_trabajo}")

    # TODO: Reemplazar este esqueleto cuando se confirme fuente, Vector flow,
    # regla de calculo de POSICION, moneda y mapeo de BOOK para el producto.
    registrar_log(
        logger,
        f"{producto}: esqueleto ejecutado para {fecha.strftime('%d/%m/%Y')}. "
        "Pendiente implementar insumos y regla de posicion.",
    )
    tabla = pd.DataFrame(columns=COLUMNAS_POSICION)

    # ADICION AUXILIAR: deja creada la tabla del módulo aun mientras su cálculo esté pendiente.
    guardar_tablas_auxiliares_modulo(
        producto,
        fecha,
        {"posicion_pendiente": tabla},
        logger=logger,
    )
    return tabla
