from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from compartido.nucleo_risko.trm import obtener_trm_formada


class ObtenerTrmFormadaTests(unittest.TestCase):
    def _crear_archivo(self, filas: list[dict]) -> Path:
        temporal = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        temporal.close()
        ruta = Path(temporal.name)
        pd.DataFrame(filas).to_excel(ruta, sheet_name="TRM", index=False)
        self.addCleanup(ruta.unlink, missing_ok=True)
        return ruta

    def test_obtiene_formada_de_la_fecha_exacta(self) -> None:
        ruta = self._crear_archivo(
            [
                {"Fecha": "2026-08-02", "FORMADA": 3144.14},
                {"Fecha": "2026-08-03", "FORMADA": 3230.44},
            ]
        )

        self.assertEqual(obtener_trm_formada("03/08/2026", ruta), 3230.44)

    def test_no_retrocede_si_falta_la_fecha(self) -> None:
        ruta = self._crear_archivo(
            [{"Fecha": "2026-08-02", "FORMADA": 3144.14}]
        )

        with self.assertRaisesRegex(ValueError, "no contiene la fecha exacta"):
            obtener_trm_formada("03/08/2026", ruta)

    def test_rechaza_formada_vacia(self) -> None:
        ruta = self._crear_archivo(
            [{"Fecha": "2026-08-04", "FORMADA": None}]
        )

        with self.assertRaisesRegex(ValueError, "FORMADA esta vacia"):
            obtener_trm_formada("04/08/2026", ruta)

    def test_rechaza_valores_duplicados_diferentes(self) -> None:
        ruta = self._crear_archivo(
            [
                {"Fecha": "2026-08-03", "FORMADA": 3230.44},
                {"Fecha": "2026-08-03", "FORMADA": 3231.00},
            ]
        )

        with self.assertRaisesRegex(ValueError, "mas de una TRM FORMADA"):
            obtener_trm_formada("03/08/2026", ruta)


if __name__ == "__main__":
    unittest.main()
