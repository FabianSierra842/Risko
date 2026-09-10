from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from proyectos.pyg.procesos.referencia_mensual import cargar_referencia_mensual


def test_referencia_exige_mismo_corte(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    resumen = pd.DataFrame([[None] * 8 for _ in range(22)])
    resumen.iloc[1, 3] = 46234
    resumen.iloc[2, 3] = 46247
    griegas = pd.DataFrame([[None] * 33 for _ in range(41)])

    def leer(_ruta, *, sheet_name, **_kwargs):
        return resumen if sheet_name == "RESUMEN FINAL" else griegas

    archivo = tmp_path / "referencia.xlsb"
    archivo.touch()
    monkeypatch.setattr(pd, "read_excel", leer)
    with pytest.raises(ValueError, match="tiene corte 13/08/2026"):
        cargar_referencia_mensual(archivo, "12/08/2026")


@pytest.mark.skipif(
    not Path("datos/pyg/insumos/PYG_OPCIONES_MES_REFERENCIA.xlsb").is_file(),
    reason="requiere referencia mensual copiada por Vector",
)
def test_referencia_productiva_13_agosto_concilia() -> None:
    resultado = cargar_referencia_mensual(
        "datos/pyg/insumos/PYG_OPCIONES_MES_REFERENCIA.xlsb", "13/08/2026"
    )
    assert resultado.totales_book["PYG_BANKING"] == pytest.approx(155_797_860.85967374, abs=1.0)
    assert resultado.totales_book["DELTA_PYG"] == pytest.approx(-201_018_073.2645793, abs=1.0)
    assert resultado.conciliacion["estado"] == "OK"
