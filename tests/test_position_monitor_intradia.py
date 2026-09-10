from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from proyectos.position_monitor.procesos.intradia import (
    _aplicar_nominal_operaciones_dia_novados,
    seleccionar_archivo_intradia,
)
from proyectos.position_monitor.tableros.panel_position_monitor import (
    load_dashboard_tables,
)
from compartido.nucleo_risko.trm import obtener_spot_reproceso


def test_selecciona_sufijo_mayor_aunque_mtime_sea_menor(tmp_path: Path) -> None:
    version_000 = tmp_path / "USR_Posicion_Novado_Intradia_180826_000.xls"
    version_001 = tmp_path / "USR_Posicion_Novado_Intradia_180826_001.xls"
    version_000.write_text("anterior", encoding="utf-8")
    version_001.write_text("reciente", encoding="utf-8")
    os.utime(version_000, (2_000_000_000, 2_000_000_000))
    os.utime(version_001, (1_000_000_000, 1_000_000_000))

    elegido = seleccionar_archivo_intradia(
        tmp_path,
        "USR_Posicion_Novado_Intradia_180826_*.xls",
    )

    assert elegido.name.endswith("_001.xls")


def test_ignora_version_mayor_si_esta_vacia(tmp_path: Path) -> None:
    version_000 = tmp_path / "USR_Caja_Intradia_180826_000.xls"
    version_001 = tmp_path / "USR_Caja_Intradia_180826_001.xls"
    version_000.write_text("contenido", encoding="utf-8")
    version_001.write_bytes(b"")

    elegido = seleccionar_archivo_intradia(
        tmp_path,
        "USR_Caja_Intradia_180826_*.xls",
    )

    assert elegido.name.endswith("_000.xls")


def test_configura_vector_con_criterio_sufijo_numerico() -> None:
    raiz = Path(__file__).resolve().parents[1]
    config = json.loads(
        (raiz / "proyectos/position_monitor/configuracion/risko.json").read_text(
            encoding="utf-8"
        )
    )
    flujo = next(
        item for item in config["flows"]
        if item["name"] == "10_Position_Monitor_Intradia"
    )

    assert len(flujo["steps"]) == 8
    pasos_recientes = [
        paso for paso in flujo["steps"]
        if paso["tipo"] == "copiar_archivo_reciente"
    ]
    assert len(pasos_recientes) == 6
    assert all(
        paso["tipo"] == "copiar_archivo_reciente"
        and paso["criterio_reciente"] == "sufijo_numerico"
        and paso["tamano_minimo_bytes"] >= 1024
        for paso in pasos_recientes
    )
    assert any("USR_OPT_INTRADIA" in paso["patron"] for paso in flujo["steps"])
    assert any(paso["patron"] == "ENTRADA2.xlsb" for paso in flujo["steps"])
    assert any(paso["patron"] == "Insumo tasas.xlsx" for paso in flujo["steps"])


def test_spot_cliente_esta_en_spot_oficial_y_spot_2_sigue_aislado() -> None:
    raiz = Path(__file__).resolve().parents[1]
    config = json.loads(
        (raiz / "proyectos/position_monitor/configuracion/risko.json").read_text(
            encoding="utf-8"
        )
    )
    flujo = next(
        item for item in config["flows"]
        if item["name"] == "11_Spot_2_Cierre_Pruebas"
    )

    assert config["spot_2"]["incluir_en_cierre"] is False
    assert config["spot_2"]["incluir_en_intradia"] is False
    assert config["spot_2"]["posicion_inicial_validada"] is False
    assert len(flujo["steps"]) == 1
    paso = flujo["steps"][0]
    assert paso["patron"] == "Cierre_ReporteCaja_{ddmmyy}_*.xls"
    assert "Intradia" not in paso["patron"]
    assert paso["destino"] == "{Ruta_Risko_Spot_2_Cierre}"
    parametros = (
        raiz / "proyectos/position_monitor/configuracion/param_spot_2.csv"
    ).read_text(encoding="utf-8-sig")
    assert "Spot,SPOT_CLIENTE,Trading,Spot_Cliente,Trading,SPOT,USD,SI" in parametros
    parametros_oficiales = (
        raiz / "proyectos/position_monitor/configuracion/param_libros.csv"
    ).read_text(encoding="utf-8-sig")
    assert "Spot,SPOT_CLIENTE,Trading,Spot_Cliente,Trading,SPOT,USD,SI" in parametros_oficiales


def test_spot_cliente_intradia_supera_el_alcance_del_dashboard() -> None:
    posicion_intradia = pd.DataFrame(
        {
            "FECHA": ["21/08/2026"],
            "PRODUCTO": ["Spot"],
            "BOOK": ["Spot_Cliente"],
            "POSICION": [577_822.59],
            "MONEDA_POSICION": ["USD"],
            "LB_LT": ["Trading"],
            "INSTRUMENTO": ["SPOT"],
            "COMPANY": ["Colombia"],
            "CLASIFICACION_CONTABLE": ["NA"],
            "BANKING_CVA_DVA": ["Banking"],
        }
    )

    tablas = load_dashboard_tables(
        current_override=posicion_intradia,
        historical_override=posicion_intradia,
    )

    assert tablas["current_raw"]["BOOK"].tolist() == ["Spot_Cliente"]
    assert tablas["tbl_posicion_detalle"]["BOOK"].tolist() == ["Spot_Cliente"]


def test_novados_intradia_usa_nominal_firmado_en_operaciones_del_dia() -> None:
    insumo = pd.DataFrame(
        {
            "FECHA NEGOCIACION": ["20/08/26", "20/08/26", "19/08/26"],
            "NOMINAL": ["5,000,000.00", "-1,000,000.00", "9,000,000.00"],
            "VALOR SENSIBLE": ["0.00", "0.00", "8,500,000.00"],
        }
    )

    ajustado, regla = _aplicar_nominal_operaciones_dia_novados(
        insumo,
        pd.Timestamp("2026-08-20"),
    )

    valores_ajustados = pd.to_numeric(
        ajustado["VALOR SENSIBLE"].astype(str).str.replace(",", "", regex=False)
    )
    assert valores_ajustados.tolist() == [
        5_000_000,
        -1_000_000,
        8_500_000,
    ]
    assert regla == {
        "filas_regla": 2,
        "nominal_total": 4_000_000.0,
        "sensible_original_total": 0.0,
        "impacto_usd": 4_000_000.0,
    }



def test_spot_reproceso_se_resuelve_por_encabezado_setfx(tmp_path: Path) -> None:
    import pandas as pd

    ruta = tmp_path / "Insumo tasas.xlsx"
    tabla = pd.DataFrame(
        {
            "Fecha": [pd.Timestamp("2026-08-18")],
            "FORMADA": [None],
            "VIGENTE": [3128.65],
            "DIAS": ["martes"],
            "SETFX": [3094.91],
        }
    )
    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        tabla.to_excel(writer, sheet_name="TRM", index=False)

    spot = obtener_spot_reproceso("18/08/2026", ruta)

    assert spot == 3094.91
