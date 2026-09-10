from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from proyectos.position_monitor.procesos.consolidacion import (
    COLUMNAS_POSICION,
    _es_fin_mes_operativo,
    _filtrar_fin_mes_historico,
    _fusionar_historico,
    _preparar_historico_desde_excel,
)


def posicion(fecha: str, producto: str = "Spot", valor: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "FECHA": fecha,
                "PRODUCTO": producto,
                "BOOK": producto,
                "POSICION": valor,
                "MONEDA_POSICION": "USD",
                "LB_LT": "Tesoreria",
                "INSTRUMENTO": "Derivados",
                "COMPANY": "Colombia",
                "CLASIFICACION_CONTABLE": "NA",
                "BANKING_CVA_DVA": "Banking",
            }
        ],
        columns=COLUMNAS_POSICION,
    )


class HistoricoCierreMensualTests(unittest.TestCase):
    def test_mes_que_termina_en_fin_de_semana_usa_solo_ultimo_dia_calendario(self):
        self.assertFalse(_es_fin_mes_operativo(pd.Timestamp("2026-05-29")))
        self.assertFalse(_es_fin_mes_operativo(pd.Timestamp("2026-05-30")))
        self.assertTrue(_es_fin_mes_operativo(pd.Timestamp("2026-05-31")))

    def test_mes_que_termina_en_dia_habil_conserva_el_mismo_cierre(self):
        self.assertFalse(_es_fin_mes_operativo(pd.Timestamp("2026-07-30")))
        self.assertTrue(_es_fin_mes_operativo(pd.Timestamp("2026-07-31")))

    def test_filtro_historico_descarta_el_ultimo_habil_si_no_es_fin_calendario(self):
        tabla = pd.concat(
            [
                posicion("29/05/2026", valor=10.0),
                posicion("31/05/2026", valor=20.0),
                posicion("30/06/2026", valor=30.0),
            ],
            ignore_index=True,
        )

        resultado = _filtrar_fin_mes_historico(tabla)

        self.assertEqual(
            resultado["FECHA"].tolist(),
            ["31/05/2026", "30/06/2026"],
        )

    def test_reproceso_reemplaza_producto_y_fecha_sin_duplicar(self):
        existente = pd.concat(
            [
                posicion("31/05/2026", "Spot", 10.0),
                posicion("31/05/2026", "Forward", 20.0),
            ],
            ignore_index=True,
        )
        corregido = posicion("31/05/2026", "Spot", 99.0)

        resultado = _fusionar_historico(existente, corregido)

        spot = resultado.loc[resultado["PRODUCTO"].eq("Spot")]
        forward = resultado.loc[resultado["PRODUCTO"].eq("Forward")]
        self.assertEqual(len(spot), 1)
        self.assertEqual(spot.iloc[0]["POSICION"], 99.0)
        self.assertEqual(len(forward), 1)
        self.assertEqual(forward.iloc[0]["POSICION"], 20.0)

    def test_preparacion_acepta_unicamente_el_historico_real_2026(self):
        tabla = pd.concat(
            [
                posicion("31/01/2026", "Spot", 10.0),
                posicion("28/02/2026", "Forward", 20.0),
            ],
            ignore_index=True,
        )
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "historico.xlsx"
            tabla.to_excel(ruta, sheet_name="Hoja1", index=False)

            resultado = _preparar_historico_desde_excel(ruta)

        self.assertEqual(len(resultado), 2)
        self.assertEqual(set(resultado["FECHA"]), {"31/01/2026", "28/02/2026"})

    def test_preparacion_rechaza_filas_de_2025(self):
        tabla = posicion("31/12/2025", "Spot", 10.0)
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "historico.xlsx"
            tabla.to_excel(ruta, sheet_name="Hoja1", index=False)

            with self.assertRaisesRegex(ValueError, "unicamente 2026"):
                _preparar_historico_desde_excel(ruta)


if __name__ == "__main__":
    unittest.main()
