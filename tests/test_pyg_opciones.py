from __future__ import annotations

import os
from pathlib import Path

import pytest

from proyectos.pyg.procesos.opciones import (
    calcular_pyg_opciones,
    cargar_configuracion,
    resolver_ruta_dataset,
)
from proyectos.pyg.procesos.consolidacion import calcular_pyg_consolidado


def test_configuracion_declara_modulo_y_fuentes() -> None:
    config = cargar_configuracion()
    assert config["modulos"]["book_opciones"]["habilitado"] is True
    assert config["modulos"]["book_opciones"]["productos"] == ["FORWARD", "OPCIONES", "CAJA"]
    assert config["calculo"]["estado"].startswith("PRELIMINAR")
    assert config["calculo"]["periodicidad"] == "MTD"
    assert "DELTA_PYG" in config["modulos"]["book_opciones"]["componentes"]
    assert "{fecha:%Y%m%d}" in config["fuentes"]["opciones"]["patron"]


def test_ruta_dataset_se_parametriza_sin_position_monitor(tmp_path: Path) -> None:
    config = cargar_configuracion()
    config["fuentes"]["opciones"]["carpeta_datasets"] = str(tmp_path)
    ruta = resolver_ruta_dataset("13/08/2026", config)
    assert ruta == tmp_path / "Dataset Libro de Opciones 20260813.xlsx"


@pytest.mark.skipif(
    os.environ.get("RISKO_PRUEBA_INTEGRACION_PYG") != "1",
    reason="requiere los datasets productivos de Opciones",
)
def test_integracion_13_agosto_concilia_book_y_productos() -> None:
    resultado = calcular_pyg_consolidado("13/08/2026")
    assert resultado.totales_producto["OPCIONES"]["PYG_BANKING"] == pytest.approx(832_702_473.5999825, abs=1.0)
    assert resultado.totales_producto["FORWARD"]["PYG_BANKING"] == pytest.approx(-1_171_063_298.4922979, abs=1.0)
    assert resultado.totales_producto["CAJA"]["PYG_BANKING"] == pytest.approx(494_158_685.81927347, abs=1.0)
    assert resultado.totales["PYG_BANKING"] == pytest.approx(155_797_860.85967374, abs=1.0)
    assert resultado.totales["DELTA_PYG"] == pytest.approx(-201_018_073.2645793, abs=1.0)
    assert resultado.posiciones_control["OPCIONES"]["BANKING_USD"] == pytest.approx(-29_366_297.9597445, abs=1.0)
    assert resultado.conciliacion["estado"] == "OK"
