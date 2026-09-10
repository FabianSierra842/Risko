from __future__ import annotations

from pathlib import Path

from proyectos.pyg.procesos.consolidacion import ResultadoPygConsolidado
from proyectos.pyg.tableros.panel_pyg import build_dashboard


def _resultado() -> ResultadoPygConsolidado:
    componentes = {"THETA": -10.0, "DELTA_PYG": 2.0, "RHO": -1.0, "VEGA": 0.5, "TRADING": -0.5, "AJUSTES": 0.0, "COSTO_FONDOS": 0.0, "EPSILON": 0.0, "PYG_BANKING": -9.0, "CVA": -8.0, "PYG_IFRS": -17.0}
    detalle = [
        {"FECHA": "2026-08-13", "BOOK": "OPCIONES", "PRODUCTO": "OPCIONES", "COMPONENTE": k, "VALOR_COP": v, "TIPO": "GRIEGA", "ESTADO": "PRELIMINAR"}
        for k, v in componentes.items() if k in {"THETA", "DELTA_PYG", "RHO", "VEGA", "TRADING", "AJUSTES", "COSTO_FONDOS", "EPSILON"}
    ]
    return ResultadoPygConsolidado(
        fecha="2026-08-13", fecha_anterior="2026-08-12", estado="PRELIMINAR",
        detalle=detalle,
        totales={"THETA": -10.0, "DELTA_PYG": 2.0, "RHO": -1.0, "VEGA": 0.5, "TRADING": -0.5, "AJUSTES": 0.0, "COSTO_FONDOS": 0.0, "EPSILON": 0.0, "PYG_BANKING": -9.0, "CVA": -8.0, "PYG_IFRS": -17.0},
        totales_producto={"OPCIONES": componentes},
        mercado={"TRM_ANTERIOR": 3100.0, "TRM_ACTUAL": 3110.0, "VARIACION_TRM": 10.0},
        conciliacion={"estado": "OK", "productos_ok": 1.0, "productos_total": 1.0},
        fuentes={"anterior": "anterior.xlsx", "actual": "actual.xlsx"},
        posiciones_control={"OPCIONES": {"BANKING_USD": -1.0, "IFRS_USD": -1.0}},
        calidad=[{"control": "Opciones", "estado": "OK", "detalle": "Completo"}],
    )


def test_dashboard_es_consolidado_autocontenido_y_parametrizable(tmp_path: Path) -> None:
    salida = build_dashboard(_resultado(), tmp_path / "pyg.html")
    contenido = salida.read_text(encoding="utf-8")
    assert 'data-filter="PERIODO"' in contenido
    assert 'data-filter="FECHA"' in contenido
    assert 'data-filter="BOOK"' in contenido
    assert 'data-filter="PRODUCTO"' in contenido
    assert 'data-filter="COMPONENTE"' in contenido
    assert "https://" not in contenido
    assert "PRELIMINAR" in contenido
