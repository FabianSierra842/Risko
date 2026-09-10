"""Lectura y conciliación del PyG mensual oficial del Book Opciones.

El libro mensual es el control de cierre. Las griegas se vuelven a sumar desde
las columnas diarias de ``GRIEGAS OPC`` y se contrastan con
``RESUMEN FINAL!C1:H22``. Las posiciones de las filas 19 y 22 son controles;
no se convierten en contribuciones de PyG.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import sqlite3

import pandas as pd


PRODUCTOS = ("FORWARD", "OPCIONES", "CAJA")
COMPONENTES = (
    "THETA",
    "DELTA_PYG",
    "RHO",
    "VEGA",
    "TRADING",
    "AJUSTES",
    "COSTO_FONDOS",
    "EPSILON",
)

_COLUMNAS_PRODUCTO = {"FORWARD": 3, "OPCIONES": 4, "CAJA": 5}
_FILAS_RESUMEN = {
    "THETA": 6,
    "DELTA_PYG": 7,
    "RHO": 8,
    "VEGA": 9,
    "TRADING": 10,
    "AJUSTES": 11,
    "COSTO_FONDOS": 12,
    "EPSILON": 13,
    "PYG_BANKING": 14,
    "CVA": 15,
    "PYG_IFRS": 16,
}
_FILAS_DIARIAS = {
    "FORWARD": {"THETA": 15, "DELTA_PYG": 16, "RHO": 17, "VEGA": 18, "TRADING": 19},
    "OPCIONES": {"THETA": 21, "DELTA_PYG": 22, "RHO": 23, "VEGA": 24, "TRADING": 25},
    "CAJA": {"THETA": 9, "DELTA_PYG": 10, "RHO": 11, "VEGA": 12, "TRADING": 13},
}


@dataclass(frozen=True)
class ReferenciaMensual:
    fecha: date
    fecha_inicio: date
    trm_inicio: float
    trm_corte: float
    componentes: dict[str, dict[str, float]]
    totales_producto: dict[str, dict[str, float]]
    totales_book: dict[str, float]
    calculo_diario: dict[str, dict[str, float]]
    diferencias_diarias: dict[str, dict[str, float]]
    posiciones_referencia: dict[str, dict[str, float]]
    conciliacion: dict[str, float | str]
    ruta: Path


def _numero(valor: object) -> float:
    numero = pd.to_numeric(valor, errors="coerce")
    return 0.0 if pd.isna(numero) else float(numero)


def _fecha_excel(valor: object) -> date:
    if isinstance(valor, (datetime, pd.Timestamp)):
        return pd.Timestamp(valor).date()
    numero = pd.to_numeric(valor, errors="coerce")
    if pd.isna(numero):
        marca = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    else:
        marca = pd.Timestamp("1899-12-30") + pd.to_timedelta(float(numero), unit="D")
    if pd.isna(marca):
        raise ValueError(f"Fecha inválida en referencia mensual: {valor!r}")
    return pd.Timestamp(marca).date()


def _fecha_parametro(valor: str | date) -> pd.Timestamp:
    """Interpreta ISO sin ambigüedad y conserva soporte para DD/MM/AAAA."""
    if isinstance(valor, (date, datetime, pd.Timestamp)):
        return pd.Timestamp(valor)
    texto = str(valor).strip()
    if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
        return pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
    return pd.to_datetime(texto, dayfirst=True, errors="coerce")


def _columnas_periodo(tabla: pd.DataFrame, fecha_corte: date) -> list[int]:
    columnas: list[int] = []
    for columna in range(1, min(32, tabla.shape[1])):
        valor = tabla.iloc[2, columna]
        try:
            fecha = _fecha_excel(valor)
        except ValueError:
            continue
        if fecha.year == fecha_corte.year and fecha.month == fecha_corte.month and fecha <= fecha_corte:
            columnas.append(columna)
    if not columnas:
        raise ValueError(f"GRIEGAS OPC no contiene fechas del periodo hasta {fecha_corte:%d/%m/%Y}")
    return columnas


def cargar_referencia_mensual(
    ruta: str | Path,
    fecha_corte: str | date,
    *,
    tolerancia_cop: float = 2.0,
) -> ReferenciaMensual:
    archivo = Path(ruta)
    if not archivo.is_file():
        raise FileNotFoundError(f"No existe la referencia mensual de PyG: {archivo}")
    fecha_solicitada = _fecha_parametro(fecha_corte)
    if pd.isna(fecha_solicitada):
        raise ValueError(f"Fecha de corte inválida: {fecha_corte}")
    fecha_solicitada = fecha_solicitada.date()
    resumen = pd.read_excel(archivo, sheet_name="RESUMEN FINAL", header=None, engine="pyxlsb")
    griegas = pd.read_excel(archivo, sheet_name="GRIEGAS OPC", header=None, engine="pyxlsb")
    fecha_libro = _fecha_excel(resumen.iloc[2, 3])
    if fecha_libro != fecha_solicitada:
        raise ValueError(
            f"La referencia {archivo.name} tiene corte {fecha_libro:%d/%m/%Y}, "
            f"no {fecha_solicitada:%d/%m/%Y}"
        )
    componentes: dict[str, dict[str, float]] = {}
    totales_producto: dict[str, dict[str, float]] = {}
    for producto, columna in _COLUMNAS_PRODUCTO.items():
        componentes[producto] = {
            componente: _numero(resumen.iloc[fila, columna])
            for componente, fila in _FILAS_RESUMEN.items()
            if componente in COMPONENTES
        }
        totales_producto[producto] = {
            **componentes[producto],
            "PYG_BANKING": _numero(resumen.iloc[_FILAS_RESUMEN["PYG_BANKING"], columna]),
            "CVA": _numero(resumen.iloc[_FILAS_RESUMEN["CVA"], columna]),
            "PYG_IFRS": _numero(resumen.iloc[_FILAS_RESUMEN["PYG_IFRS"], columna]),
        }
        # Alias de compatibilidad con consumidores de la primera versión.
        totales_producto[producto]["PYG_TOTAL"] = totales_producto[producto]["PYG_BANKING"]
        totales_producto[producto]["PYG_CVA"] = totales_producto[producto]["CVA"]

    totales_book = {
        componente: _numero(resumen.iloc[fila, 7])
        for componente, fila in _FILAS_RESUMEN.items()
    }
    columnas_periodo = _columnas_periodo(griegas, fecha_libro)
    calculo_diario: dict[str, dict[str, float]] = {}
    diferencias_diarias: dict[str, dict[str, float]] = {}
    for producto, filas in _FILAS_DIARIAS.items():
        calculo_diario[producto] = {
            componente: sum(_numero(griegas.iloc[fila, columna]) for columna in columnas_periodo)
            for componente, fila in filas.items()
        }
        diferencias_diarias[producto] = {
            componente: calculo_diario[producto][componente] - componentes[producto][componente]
            for componente in filas
        }

    posiciones_referencia = {
        producto: {
            "BANKING_USD": _numero(resumen.iloc[18, columna]),
            "IFRS_USD": _numero(resumen.iloc[21, columna]),
        }
        for producto, columna in _COLUMNAS_PRODUCTO.items()
    }
    diferencias: list[float] = []
    for producto in PRODUCTOS:
        diferencias.append(
            sum(componentes[producto].values()) - totales_producto[producto]["PYG_BANKING"]
        )
        diferencias.append(
            totales_producto[producto]["PYG_BANKING"]
            + totales_producto[producto]["CVA"]
            - totales_producto[producto]["PYG_IFRS"]
        )
        diferencias.extend(diferencias_diarias[producto].values())
    diferencias.append(sum(totales_book[c] for c in COMPONENTES) - totales_book["PYG_BANKING"])
    diferencias.append(totales_book["PYG_BANKING"] + totales_book["CVA"] - totales_book["PYG_IFRS"])
    max_diferencia = max(map(abs, diferencias), default=0.0)
    return ReferenciaMensual(
        fecha=fecha_libro,
        fecha_inicio=_fecha_excel(resumen.iloc[1, 3]),
        trm_inicio=_numero(resumen.iloc[1, 4]),
        trm_corte=_numero(resumen.iloc[2, 4]),
        componentes=componentes,
        totales_producto=totales_producto,
        totales_book=totales_book,
        calculo_diario=calculo_diario,
        diferencias_diarias=diferencias_diarias,
        posiciones_referencia=posiciones_referencia,
        conciliacion={
            "estado": "OK" if max_diferencia <= tolerancia_cop else "DIFERENCIA",
            "max_diferencia_cop": float(max_diferencia),
            "tolerancia_cop": float(tolerancia_cop),
            "dias_acumulados": float(len(columnas_periodo)),
        },
        ruta=archivo,
    )


def cargar_posiciones_publicadas(ruta_db: str | Path, fecha_corte: str | date) -> dict[str, dict[str, float]]:
    """Lee el contrato de Position Monitor sin ejecutar ni modificar sus módulos."""
    archivo = Path(ruta_db)
    if not archivo.is_file():
        raise FileNotFoundError(f"No existe el snapshot de posiciones: {archivo}")
    fecha = _fecha_parametro(fecha_corte)
    if pd.isna(fecha):
        raise ValueError(f"Fecha de posición inválida: {fecha_corte}")
    fecha_texto = fecha.strftime("%d/%m/%Y")

    def sumar(conexion: sqlite3.Connection, tabla: str, producto: str, clasificacion: str) -> float:
        consulta = f"""
            SELECT COALESCE(SUM(POSICION), 0)
            FROM {tabla}
            WHERE FECHA = ? AND UPPER(TRIM(BOOK)) = 'OPCIONES'
              AND UPPER(TRIM(PRODUCTO)) = ? AND UPPER(TRIM(BANKING_CVA_DVA)) = ?
        """
        return float(conexion.execute(consulta, (fecha_texto, producto, clasificacion)).fetchone()[0])

    # SQLite/Python no admite ``file://servidor`` como URI en todos los
    # entornos Windows. El archivo ya fue validado y se fuerza query_only.
    with sqlite3.connect(str(archivo)) as conexion:
        conexion.execute("PRAGMA query_only = ON")
        forward_banking = sumar(conexion, "tbl_posicion_forward", "FORWARD", "BANKING")
        forward_ifrs = sumar(conexion, "tbl_posicion_forward", "FORWARD", "IFRS")
        opciones = sumar(conexion, "tbl_posicion_opciones", "OPCIONES", "BANKING")
        caja = sumar(conexion, "tbl_posicion_spot", "SPOT", "BANKING")
    return {
        "FORWARD": {"BANKING_USD": forward_banking, "IFRS_USD": forward_ifrs},
        "OPCIONES": {"BANKING_USD": opciones, "IFRS_USD": opciones},
        "CAJA": {"BANKING_USD": caja, "IFRS_USD": caja},
    }


__all__ = [
    "COMPONENTES",
    "PRODUCTOS",
    "ReferenciaMensual",
    "cargar_posiciones_publicadas",
    "cargar_referencia_mensual",
]
