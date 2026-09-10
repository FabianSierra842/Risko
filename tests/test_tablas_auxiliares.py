from __future__ import annotations

from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd

from compartido.nucleo_risko.tablas_auxiliares import (
    guardar_tablas_auxiliares_modulo,
    inicializar_base_auxiliar,
)


class TablasAuxiliaresTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.ruta_db = Path(self.temporal.name) / "risko_auxiliar.db"

    def tearDown(self):
        self.temporal.cleanup()

    def test_crea_catalogo_y_tablas_por_modulo(self):
        inicializar_base_auxiliar(self.ruta_db)
        resultado = guardar_tablas_auxiliares_modulo(
            "Forward",
            "03/08/2026",
            {
                "Detalle Banking": pd.DataFrame(
                    {"BOOK": ["FWD_CLIENTES"], "VALOR": [Decimal("10.25")]}
                ),
                "Posicion": pd.DataFrame({"BOOK": ["FWD_CLIENTES"], "POSICION": [10.25]}),
            },
            ruta_db=self.ruta_db,
        )

        self.assertEqual(resultado["Detalle Banking"], "aux_forward_detalle_banking")
        with closing(sqlite3.connect(self.ruta_db)) as conexion:
            tablas = {
                fila[0]
                for fila in conexion.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            detalle = pd.read_sql_query("SELECT * FROM aux_forward_detalle_banking", conexion)
            catalogo = pd.read_sql_query(
                "SELECT * FROM tbl_catalogo_auxiliar WHERE MODULO = 'Forward' "
                "AND NOMBRE_LOGICO IN ('Detalle Banking', 'Posicion')",
                conexion,
            )

        self.assertIn("aux_forward_posicion", tablas)
        self.assertEqual(detalle.loc[0, "AUX_FECHA_CORTE"], "03/08/2026")
        self.assertEqual(detalle.loc[0, "VALOR"], "10.25")
        self.assertEqual(set(catalogo["ESTADO"]), {"OK"})

    def test_reproceso_reemplaza_solo_el_corte(self):
        guardar_tablas_auxiliares_modulo(
            "Novados",
            "03/08/2026",
            {"Posicion": pd.DataFrame({"BOOK": ["A"], "POSICION": [1]})},
            ruta_db=self.ruta_db,
        )
        guardar_tablas_auxiliares_modulo(
            "Novados",
            "04/08/2026",
            {"Posicion": pd.DataFrame({"BOOK": ["B"], "POSICION": [2]})},
            ruta_db=self.ruta_db,
        )
        guardar_tablas_auxiliares_modulo(
            "Novados",
            "03/08/2026",
            {"Posicion": pd.DataFrame({"BOOK": ["C"], "POSICION": [3]})},
            ruta_db=self.ruta_db,
        )

        with closing(sqlite3.connect(self.ruta_db)) as conexion:
            tabla = pd.read_sql_query(
                "SELECT AUX_FECHA_CORTE, BOOK, POSICION FROM aux_novados_posicion",
                conexion,
            )

        self.assertEqual(len(tabla), 2)
        self.assertEqual(
            dict(zip(tabla["AUX_FECHA_CORTE"], tabla["BOOK"])),
            {"03/08/2026": "C", "04/08/2026": "B"},
        )


if __name__ == "__main__":
    unittest.main()
