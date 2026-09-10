from __future__ import annotations

from datetime import date
from pathlib import Path

import tempfile
import unittest

from proyectos.position_monitor.procesos.spot_2 import (
    VERSION_CONTRATO_CALCULO,
    COLUMNAS_REQUERIDAS,
    _detectar_encabezado,
    _leer_movimientos,
)


HEADER = [
    "GeneratedPK",
    "DmOwnerTable",
    "TradeId",
    "Book",
    "Desk",
    "EvType",
    "SettleCcy",
    "Amount",
    "TRADE DATE",
]


def _fila(pk: str, amount: str, fecha: str) -> list[str]:
    return [
        pk,
        "FXSPOT",
        f"T-{pk}",
        "SPOT_CLIENTE",
        "MERCADO",
        "CASH",
        "USD",
        amount,
        fecha,
    ]


def _escribir_reporte(
    ruta: Path,
    filas: list[list[str]],
    header: list[str] | None = None,
) -> None:
    lineas = ["Linea preliminar", ";".join(header or HEADER)]
    lineas.extend(";".join(fila) for fila in filas)
    ruta.write_text("\n".join(lineas), encoding="cp1252")


def test_trade_date_filtra_por_fecha_de_corte(tmp_path: Path) -> None:
    reporte = tmp_path / "caja.xls"
    _escribir_reporte(
        reporte,
        [
            _fila("1", "10.50", "20/08/2026"),
            _fila("2", "99", "19/08/2026"),
        ],
    )
    por_book = {
        "SPOT_CLIENTE": {
            "POSICION_ID": "SPOT_CLIENTE",
            "POSICION_NOMBRE": "Spot Cliente",
            "ACTIVO": True,
        }
    }

    movimientos, alertas = _leer_movimientos(
        reporte,
        date(2026, 8, 20),
        por_book,
        {"FXSPOT"},
    )

    assert COLUMNAS_REQUERIDAS[-1] == "TRADE DATE"
    assert VERSION_CONTRATO_CALCULO == "SPOT_2_TRADE_DATE_V1"
    assert len(movimientos) == 1
    assert movimientos[0]["SOURCE_ROW_ID"] == "1"
    assert movimientos[0]["MONTO_USD"] == "10.50"
    assert alertas == []

    reporte_anterior = tmp_path / "caja_valuedate.xls"
    header_anterior = [*HEADER[:-1], "ValueDate"]
    _escribir_reporte(reporte_anterior, [_fila("3", "10", "20/08/2026")], header_anterior)

    try:
        _detectar_encabezado(reporte_anterior)
    except ValueError as exc:
        assert "TRADE DATE" in str(exc)
    else:
        raise AssertionError("ValueDate no debe sustituir a TRADE DATE")


def _ejecutar_con_temporal(prueba) -> None:
    with tempfile.TemporaryDirectory() as carpeta:
        prueba(Path(carpeta))


def load_tests(loader, tests, pattern):
    del loader, tests, pattern
    return unittest.TestSuite(
        [
            unittest.FunctionTestCase(
                lambda: _ejecutar_con_temporal(test_trade_date_filtra_por_fecha_de_corte)
            )
        ]
    )


