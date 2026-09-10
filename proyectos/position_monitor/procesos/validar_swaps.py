from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from compartido.nucleo_risko.fechas import Calcula_Fecha
from compartido.nucleo_risko.rutas import (
    ARCHIVO_POSICION_ACTUAL,
    ARCHIVO_POSICION_CONSOLIDADA,
    ARCHIVO_POSICION_HISTORICO,
    ARCHIVO_SALIDA_SWAPS_TABLA,
    ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE,
)
from proyectos.position_monitor.procesos.consolidacion import consolidar_position_monitor
from proyectos.position_monitor.procesos.swaps import COLUMNAS_POSICION, ejecutar_swaps


def _leer_csv(ruta: Path) -> pd.DataFrame:
    return pd.read_csv(ruta, encoding="utf-8-sig")


def validar_swaps(fecha_trabajo: str, logger=print) -> None:
    """Ejecuta Swaps y verifica salidas, columnas y consolidacion final."""
    logger(f"Validando Swaps para la fecha: {fecha_trabajo}")

    tabla = ejecutar_swaps(
        fecha_trabajo=fecha_trabajo,
        logger=logger,
        confirmar_reemplazo=False,
    )
    if tabla is None:
        raise RuntimeError("La ejecucion de Swaps retorno None.")

    if not callable(ejecutar_swaps):
        raise RuntimeError("No se pudo importar ejecutar_swaps correctamente.")

    fecha_objetivo = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_objetivo):
        raise ValueError(f"Fecha no valida para validar Swaps: {fecha_trabajo}")

    tabla_fecha = tabla.loc[
        pd.to_datetime(tabla["FECHA"], dayfirst=True, errors="coerce") == fecha_objetivo
    ].copy()
    if tabla_fecha.empty:
        raise AssertionError("La salida oficial de Swaps no devolvio datos para la fecha validada.")

    if list(tabla_fecha.columns) != COLUMNAS_POSICION:
        raise AssertionError(
            "La tabla de Swaps no tiene las 10 columnas canonicas esperadas. "
            f"Actual: {list(tabla_fecha.columns)}"
        )

    if pd.to_numeric(tabla_fecha["POSICION"], errors="coerce").isna().any():
        raise AssertionError("La columna POSICION contiene valores no numericos.")

    if tabla_fecha["FECHA"].astype(str).str.strip().eq("").any():
        raise AssertionError("La columna FECHA contiene valores vacios.")

    if not tabla_fecha["PRODUCTO"].eq("Swap").all():
        raise AssertionError("La columna PRODUCTO no quedo homologada como 'Swap'.")

    etiquetas = set(tabla_fecha["BANKING_CVA_DVA"].astype(str).str.strip())
    etiquetas_esperadas = {"Banking", "IFRS", "CVA/DVA"}
    if etiquetas != etiquetas_esperadas:
        raise AssertionError(
            "La salida oficial de Swaps debe contener exactamente Banking, IFRS y CVA/DVA. "
            f"Actual: {sorted(etiquetas)}"
        )

    lb_lt = set(tabla_fecha["LB_LT"].astype(str).str.strip())
    lb_lt_validos = {"Bancario", "Trading", "No definido"}
    if not lb_lt.issubset(lb_lt_validos):
        raise AssertionError(
            "La salida oficial de Swaps solo debe publicar LB_LT parametrico valido. "
            f"Actual: {sorted(lb_lt)}"
        )

    books = set(tabla_fecha["BOOK"].astype(str).str.strip())
    if not books:
        raise AssertionError(
            "La salida oficial de Swaps debe publicar al menos un BOOK."
        )
    if "SWAP" in books:
        raise AssertionError(
            "La salida oficial de Swaps ya no debe publicar el total agregado BOOK = 'SWAP'. "
            f"Actual: {sorted(books)}"
        )

    conteos = tabla_fecha.groupby("BOOK")["BANKING_CVA_DVA"].nunique()
    if not (conteos == 3).all():
        raise AssertionError(
            "Cada BOOK de Swaps debe traer exactamente Banking, IFRS y CVA/DVA. "
            f"Actual: {conteos.to_dict()}"
        )

    if not ARCHIVO_SALIDA_SWAPS_TABLA.exists():
        raise FileNotFoundError(f"No se genero el archivo esperado: {ARCHIVO_SALIDA_SWAPS_TABLA}")
    if not ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE.exists():
        raise FileNotFoundError(f"No se genero el detalle esperado: {ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE}")

    logger("Tabla de Swaps generada. Iniciando consolidacion desde archivos procesados...")
    consolidar_position_monitor(fecha_corte=fecha_trabajo, logger=logger)

    for ruta in (
        ARCHIVO_POSICION_CONSOLIDADA,
        ARCHIVO_POSICION_ACTUAL,
        ARCHIVO_POSICION_HISTORICO,
    ):
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontro el archivo consolidado: {ruta}")

    consolidada = _leer_csv(ARCHIVO_POSICION_CONSOLIDADA)
    actual = _leer_csv(ARCHIVO_POSICION_ACTUAL)
    historico = _leer_csv(ARCHIVO_POSICION_HISTORICO)

    fecha_publicada = fecha_objetivo.strftime("%d/%m/%Y")
    consolidada_swap = consolidada.loc[
        (consolidada["PRODUCTO"].astype(str).str.strip() == "Swap")
        & (consolidada["FECHA"].astype(str).str.strip() == fecha_publicada)
    ].copy()
    actual_swap = actual.loc[
        (actual["PRODUCTO"].astype(str).str.strip() == "Swap")
        & (actual["FECHA"].astype(str).str.strip() == fecha_publicada)
    ].copy()
    historico_swap = historico.loc[
        (historico["PRODUCTO"].astype(str).str.strip() == "Swap")
        & (historico["FECHA"].astype(str).str.strip() == fecha_publicada)
    ].copy()

    if consolidada_swap.empty:
        raise AssertionError("Swaps no entro en tbl_posicion_consolidada.csv.")
    if actual_swap.empty:
        raise AssertionError("Swaps no entro en tbl_posicion_actual.csv.")
    if historico_swap.empty:
        raise AssertionError("Swaps no entro en tbl_posicion_historico.csv.")

    for nombre, df_publicado in (
        ("tbl_posicion_consolidada.csv", consolidada_swap),
        ("tbl_posicion_actual.csv", actual_swap),
        ("tbl_posicion_historico.csv", historico_swap),
    ):
        etiquetas_publicadas = set(df_publicado["BANKING_CVA_DVA"].astype(str).str.strip())
        if etiquetas_publicadas != {"Banking", "CVA/DVA"}:
            raise AssertionError(
                f"{nombre} debe publicar solo Banking y CVA/DVA para Swaps. "
                f"Actual: {sorted(etiquetas_publicadas)}"
            )

    logger("Validacion de Swaps finalizada correctamente.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida la integracion de Swaps en Position Monitor.")
    parser.add_argument(
        "--fecha",
        default=Calcula_Fecha(),
        help="Fecha de corte en formato dd-mm-YYYY o equivalente entendible por pandas.",
    )
    args = parser.parse_args()
    validar_swaps(args.fecha)


if __name__ == "__main__":
    main()
