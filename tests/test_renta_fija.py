from __future__ import annotations

import unittest

import pandas as pd

from proyectos.position_monitor.procesos.renta_fija import (
    _construir_posicion_operativa,
    _construir_tabla_canonica,
    _nombre_archivo_fuente_titulos,
)


class RentaFijaTests(unittest.TestCase):
    @staticmethod
    def _reporte() -> pd.DataFrame:
        monedas = ["USD", "COP", "EUR", "UVR"]
        return pd.DataFrame(
            {
                "FECHA INFORME": pd.to_datetime(["2026-08-19"] * 4),
                "BOOK": ["RF_ME_TRADIN", "Trading", "FVOCI_PANAMA", "Colchon"],
                "COMPANY": ["Colombia"] * 4,
                "TITULOS": ["BONOS"] * 4,
                "VP MDO Y CCY": [10.0, 20.0, 30.0, 40.0],
                "LB_LT": ["Trading", "Trading", "Bancario", "Bancario"],
                "INSTRUMENTO": ["Renta_fija"] * 4,
                "MONEDA DEL TITULO": monedas,
            }
        )

    def test_tabla_canonica_y_exportacion_conservan_monedas_habilitadas(self):
        reporte = self._reporte()

        canonica = _construir_tabla_canonica(reporte)
        operativa = _construir_posicion_operativa(reporte)

        self.assertSetEqual(set(canonica["MONEDA_POSICION"]), {"USD", "COP", "EUR", "UVR"})
        self.assertSetEqual(set(operativa["Moneda"]), {"USD", "COP", "EUR", "UVR"})
        self.assertEqual(canonica["POSICION"].sum(), 100.0)

    def test_fuente_no_habil_usa_fecha_base_y_secuencia(self):
        self.assertEqual(
            _nombre_archivo_fuente_titulos(
                pd.Timestamp("2026-08-07"),
                "ReporteTitulos_",
            ),
            "ReporteTitulos_06082026_1.csv",
        )
        self.assertEqual(
            _nombre_archivo_fuente_titulos(
                pd.Timestamp("2026-08-09"),
                "ReporteTitulos_",
            ),
            "ReporteTitulos_06082026_3.csv",
        )


if __name__ == "__main__":
    unittest.main()
