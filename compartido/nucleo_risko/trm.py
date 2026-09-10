"""Lectura centralizada de la TRM FORMADA usada por los procesos de Risko."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re
import unicodedata

import pandas as pd

from compartido.nucleo_risko.archivos import registrar_log
from compartido.nucleo_risko.rutas import ARCHIVO_LOCAL_INSUMO_TASAS


HOJA_TRM = "TRM"
COLUMNA_FECHA_TRM = "FECHA"
COLUMNA_VALOR_TRM = "FORMADA"
COLUMNA_SPOT_REPROCESO = "SETFX"


def _normalizar_encabezado(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.upper()


def _normalizar_fecha(valor: object) -> pd.Timestamp:
    if isinstance(valor, (date, datetime, pd.Timestamp)):
        return pd.Timestamp(valor).normalize()

    texto = str(valor).strip()
    if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", texto):
        fecha = pd.to_datetime(texto, yearfirst=True, errors="coerce")
    else:
        fecha = pd.to_datetime(texto, dayfirst=True, errors="coerce")
    return fecha.normalize() if not pd.isna(fecha) else pd.NaT


def cargar_historico_trm(
    ruta_archivo: str | Path = ARCHIVO_LOCAL_INSUMO_TASAS,
    logger=None,
) -> pd.DataFrame:
    """Carga las columnas A (Fecha) y B (FORMADA) del historico oficial de TRM."""
    ruta = Path(ruta_archivo)
    registrar_log(logger, f"Historico TRM esperado: {ruta}")
    if not ruta.exists():
        raise FileNotFoundError(
            "Vector no dejo el historico de TRM requerido en: "
            f"{ruta}"
        )

    try:
        historico = pd.read_excel(
            ruta,
            sheet_name=HOJA_TRM,
            usecols="A:B",
            engine="openpyxl",
        )
    except ValueError as error:
        raise ValueError(
            f"No fue posible leer la hoja {HOJA_TRM!r} o las columnas A:B de {ruta}."
        ) from error

    historico.columns = [_normalizar_encabezado(columna) for columna in historico.columns]
    faltantes = [
        columna
        for columna in (COLUMNA_FECHA_TRM, COLUMNA_VALOR_TRM)
        if columna not in historico.columns
    ]
    if faltantes:
        raise ValueError(
            "El historico de TRM no cumple el contrato esperado: columna A = Fecha "
            f"y columna B = FORMADA. Faltan: {', '.join(faltantes)}. Archivo: {ruta}"
        )

    historico = historico[[COLUMNA_FECHA_TRM, COLUMNA_VALOR_TRM]].copy()
    historico[COLUMNA_FECHA_TRM] = historico[COLUMNA_FECHA_TRM].apply(
        _normalizar_fecha
    )
    historico[COLUMNA_VALOR_TRM] = pd.to_numeric(
        historico[COLUMNA_VALOR_TRM],
        errors="coerce",
    )
    return historico.loc[historico[COLUMNA_FECHA_TRM].notna()].reset_index(drop=True)


def obtener_trm_formada(
    fecha_trabajo: str | pd.Timestamp,
    ruta_archivo: str | Path = ARCHIVO_LOCAL_INSUMO_TASAS,
    logger=None,
) -> float:
    """Obtiene la TRM FORMADA de la fecha exacta, sin usar tasas sustitutas."""
    fecha = _normalizar_fecha(fecha_trabajo)
    if pd.isna(fecha):
        raise ValueError(f"Fecha no valida para consultar TRM: {fecha_trabajo}")
    fecha = fecha.normalize()

    historico = cargar_historico_trm(ruta_archivo, logger=logger)
    filas_fecha = historico.loc[
        historico[COLUMNA_FECHA_TRM].eq(fecha),
        COLUMNA_VALOR_TRM,
    ]
    if filas_fecha.empty:
        raise ValueError(
            "El historico de TRM no contiene la fecha exacta "
            f"{fecha.strftime('%d/%m/%Y')}."
        )

    valores = filas_fecha.dropna()
    if valores.empty:
        raise ValueError(
            "La TRM FORMADA esta vacia para la fecha "
            f"{fecha.strftime('%d/%m/%Y')}."
        )

    valores_unicos = valores.drop_duplicates()
    if len(valores_unicos) > 1:
        raise ValueError(
            "El historico contiene mas de una TRM FORMADA diferente para "
            f"{fecha.strftime('%d/%m/%Y')}: {valores_unicos.tolist()}"
        )

    trm = float(valores_unicos.iloc[0])
    registrar_log(
        logger,
        f"TRM FORMADA para {fecha.strftime('%d/%m/%Y')}: {trm:,.6f}",
    )
    return trm


def obtener_spot_reproceso(
    fecha_trabajo: str | pd.Timestamp,
    ruta_archivo: str | Path = ARCHIVO_LOCAL_INSUMO_TASAS,
    logger=None,
    *,
    columna_valor: str = COLUMNA_SPOT_REPROCESO,
) -> float:
    """Obtiene el spot de reproceso intradia para la fecha exacta.

    La columna se resuelve por encabezado y no por posicion fisica. En el
    insumo vigente, ``SETFX`` es el cuarto campo de datos despues de Fecha
    (columna E de Excel); esto evita confundirla con ``DIAS`` si el archivo
    vuelve a insertar o desplazar columnas.
    """
    fecha = _normalizar_fecha(fecha_trabajo)
    if pd.isna(fecha):
        raise ValueError(f"Fecha no valida para consultar spot de reproceso: {fecha_trabajo}")
    fecha = fecha.normalize()

    ruta = Path(ruta_archivo)
    registrar_log(logger, f"Insumo de spot de reproceso esperado: {ruta}")
    if not ruta.exists():
        raise FileNotFoundError(
            "Vector no dejo el insumo de tasas requerido para el spot de reproceso: "
            f"{ruta}"
        )

    try:
        historico = pd.read_excel(
            ruta,
            sheet_name=HOJA_TRM,
            engine="openpyxl",
        )
    except ValueError as error:
        raise ValueError(
            f"No fue posible leer la hoja {HOJA_TRM!r} de {ruta}."
        ) from error

    historico.columns = [_normalizar_encabezado(columna) for columna in historico.columns]
    columna = _normalizar_encabezado(columna_valor)
    faltantes = [
        nombre
        for nombre in (COLUMNA_FECHA_TRM, columna)
        if nombre not in historico.columns
    ]
    if faltantes:
        raise ValueError(
            "El insumo no cumple el contrato de spot de reproceso. "
            f"Faltan: {', '.join(faltantes)}. Archivo: {ruta}"
        )

    fechas = historico[COLUMNA_FECHA_TRM].apply(_normalizar_fecha)
    valores = pd.to_numeric(
        historico.loc[fechas.eq(fecha), columna],
        errors="coerce",
    ).dropna()
    if valores.empty:
        raise ValueError(
            f"La columna {columna} no contiene un spot numerico para "
            f"{fecha.strftime('%d/%m/%Y')}. Archivo: {ruta}"
        )

    valores_unicos = valores.drop_duplicates()
    if len(valores_unicos) > 1:
        raise ValueError(
            f"El insumo contiene mas de un valor {columna} para "
            f"{fecha.strftime('%d/%m/%Y')}: {valores_unicos.tolist()}"
        )

    spot = float(valores_unicos.iloc[0])
    if spot <= 0:
        raise ValueError(
            f"El spot {columna} debe ser positivo para {fecha.strftime('%d/%m/%Y')}: {spot}"
        )
    registrar_log(
        logger,
        f"Spot de reproceso {columna} para {fecha.strftime('%d/%m/%Y')}: {spot:,.6f}",
    )
    return spot
