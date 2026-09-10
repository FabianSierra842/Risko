"""Contrato y validaciones de los insumos nativos del PyG FX_ESTRAT."""

from __future__ import annotations

from pathlib import Path


ARCHIVOS_REQUERIDOS_FX_ESTRAT = (
    "INFORME FWD CONSOLIDADO {fecha_dd-mm-yy}.xlsb",
    "REPORTE_CAJA_LIVIANO_{fecha_yyyymmdd}.xls",
    "FTP COP.xlsx",
    "FTP USD.xlsx",
    "Informe Libro FX_ESTRAT {fecha_yyyymmdd}.xlsb",
    "Curva Forward V2.xlsm",
    "MASCARA FX TOTAL REPORT (5.5-3-8).xls",
    "Cierre_SwapTotalReport_{fecha_ddmmyy}_000.xls",
    "Cierre_SwapTotalReport_IFRS_{fecha_ddmmyy}_000.xls",
)


def nombres_insumos_fx_strat(fecha) -> tuple[str, ...]:
    """Resuelve los nombres de archivo del corte para FX_ESTRAT."""
    fecha_valor = fecha.to_pydatetime() if hasattr(fecha, "to_pydatetime") else fecha
    valores = {
        "fecha_dd-mm-yy": fecha_valor.strftime("%d-%m-%y"),
        "fecha_yyyymmdd": fecha_valor.strftime("%Y%m%d"),
        "fecha_ddmmyy": fecha_valor.strftime("%d%m%y"),
    }
    return tuple(nombre.format(**valores) for nombre in ARCHIVOS_REQUERIDOS_FX_ESTRAT)


def validar_insumos_fx_strat(carpeta: str | Path, fecha) -> dict[str, list[str]]:
    """Exige los insumos de DORA antes de ejecutar el motor PyG nativo."""
    carpeta_insumos = Path(carpeta)
    esperados = nombres_insumos_fx_strat(fecha)
    faltantes = [nombre for nombre in esperados if not (carpeta_insumos / nombre).is_file()]
    return {
        "esperados": list(esperados),
        "faltantes": faltantes,
        "disponibles": [nombre for nombre in esperados if nombre not in faltantes],
    }


__all__ = [
    "ARCHIVOS_REQUERIDOS_FX_ESTRAT",
    "nombres_insumos_fx_strat",
    "validar_insumos_fx_strat",
]
