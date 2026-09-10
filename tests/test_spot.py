from __future__ import annotations

from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest

from proyectos.position_monitor.procesos.spot import (
    _leer_movimientos,
    arrastrar_spot_acumulado,
    ejecutar_spot,
    importar_posiciones_iniciales_excel,
    registrar_posiciones_iniciales,
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
    "ValueDate",
    "TRADE DATE",
    "VALUE DATE",
]


def fila(
    pk: str,
    amount: str,
    *,
    book: str = "FWD_CLIENTES",
    fecha: str = "03/08/26",
    owner: str = "FXFWD",
    moneda: str = "USD",
    evtype: str = "CASH",
    trade_date: str = "31/12/99",
) -> list[str]:
    return [pk, owner, f"T-{pk}", book, "MERCADO", evtype, moneda, amount, fecha, trade_date, "31/12/99"]


def escribir_reporte(ruta: Path, filas: list[list[str]], preambulo: int = 3) -> None:
    lineas = [f"Linea preliminar {numero}" for numero in range(preambulo)]
    lineas.append(";".join(HEADER))
    lineas.extend(";".join(valores) for valores in filas)
    ruta.write_text("\n".join(lineas), encoding="cp1252")


def leer_uno(db: Path, sql: str, params=()):
    with closing(sqlite3.connect(db)) as conexion:
        return conexion.execute(sql, params).fetchone()


class SpotTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.carpeta = Path(self.temporal.name)
        self.db = self.carpeta / "risko_spot.db"

    def tearDown(self):
        self.temporal.cleanup()

    def _ejecutar(self, fecha: str, ruta: Path):
        return ejecutar_spot(
            fecha,
            ruta_insumo=ruta,
            ruta_db=self.db,
            pruebas=True,
        )

    def test_decimal_signo_multiples_aliases_y_book_desconocido(self):
        reporte = self.carpeta / "caja.xls"
        escribir_reporte(
            reporte,
            [
                fila("1", "10.10000"),
                fila("2", "-2.00100"),
                fila("3", "0"),
                fila("4", "3", book="FWD_POSICION"),
                fila("5", "-1", book="POSI_PROPIA"),
                fila("6", "100", book="SPOT_CLIENTE", trade_date="03/08/26"),
                fila("7", "999", owner="DPMT_TR"),
                fila("8", "500", moneda="EUR"),
                fila("9", "700", fecha="04/08/26"),
            ],
            preambulo=11,
        )

        resultado = self._ejecutar("03/08/2026", reporte)
        resumen = resultado.attrs["resumen_spot"].set_index("POSICION_ID")

        self.assertEqual(resumen.at["FWD_CLIENTES", "COMPRAS_USD"], "10.10000")
        self.assertEqual(resumen.at["FWD_CLIENTES", "VENTAS_USD"], "2.00100")
        self.assertEqual(resumen.at["FWD_CLIENTES", "MOVIMIENTO_NETO_USD"], "8.09900")
        self.assertEqual(resumen.at["FWD_CLIENTES", "POSICION_FINAL_USD"], "8.09900")
        self.assertEqual(resumen.at["POS_PROPIA", "POSICION_FINAL_USD"], "2")
        self.assertEqual(resumen.at["SPOT_CLIENTE", "POSICION_FINAL_USD"], "100")
        self.assertEqual(len(resultado), 15)
        self.assertEqual(
            set(resumen.index),
            {
                "CFH",
                "CUBRE_BAC",
                "FACTURASUSD",
                "FILIALES",
                "FUTUROS_FX",
                "FVH",
                "FWD_CLIENTES",
                "FX_ESTRAT",
                "OPCIONES",
                "POS_PROPIA",
                "SPOT_CLIENTE",
                "RF_ME_FV_OCI",
                "RF_ME_TRADIN",
                "SWAPS",
                "TRADING",
            },
        )
        self.assertEqual(
            int((resumen["POSICION_FINAL_USD"] == "0").sum()),
            12,
        )
        self.assertEqual(resumen.at["CFH", "TIPO_ORIGEN"], "INICIAL_CERO")
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_alertas_spot "
                "WHERE CODIGO='UNKNOWN_BOOK' AND VIGENTE=1",
            )[0],
            0,
        )
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COMPRAS_USD,VENTAS_USD,MOVIMIENTO_NETO_USD,"
                "NUMERO_MOVIMIENTOS FROM tbl_compras_ventas_spot_book "
                "WHERE FECHA='03/08/2026' AND BOOK_CLAVE='FWD_CLIENTES'",
            ),
            ("10.10000", "2.00100", "8.09900", 3),
        )
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COMPRAS_USD,VENTAS_USD,ESTADO_MAPEO,PUBLICABLE "
                "FROM tbl_compras_ventas_spot_book "
                "WHERE FECHA='03/08/2026' AND BOOK_CLAVE='SPOT_CLIENTE'",
            ),
            ("100", "0", "ACTIVO", 1),
        )
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_compras_ventas_spot_book "
                "WHERE FECHA='03/08/2026'",
            )[0],
            16,
        )


    def test_spot_cliente_usa_trade_date_y_otros_books_valuedate(self):
        reporte = self.carpeta / "caja_fechas_por_book.xls"
        escribir_reporte(
            reporte,
            [
                fila("1", "10", book="SPOT_CLIENTE", fecha="31/12/99", trade_date="03/08/26"),
                fila("2", "99", book="SPOT_CLIENTE", fecha="03/08/26", trade_date="04/08/26"),
                fila("3", "5", fecha="03/08/26", trade_date="31/12/99"),
            ],
        )

        resultado = self._ejecutar("03/08/2026", reporte)
        resumen = resultado.attrs["resumen_spot"].set_index("POSICION_ID")

        self.assertEqual(resumen.at["FWD_CLIENTES", "POSICION_FINAL_USD"], "5")
        self.assertEqual(resumen.at["SPOT_CLIENTE", "POSICION_FINAL_USD"], "10")
        canonica = resultado.set_index("BOOK")
        self.assertEqual(canonica.at["Spot_Cliente", "INSTRUMENTO"], "SPOT")

    def test_colaterales_dp_de_fwd_clientes_replican_filtro_excel(self):
        reporte = self.carpeta / "caja_colaterales.xls"
        escribir_reporte(
            reporte,
            [
                fila("1", "10"),
                fila("2", "4", owner="DPMT_TR", evtype="FEE"),
                fila("3", "-1", owner="DPMT_TR", evtype="INT"),
                fila("4", "100", owner="DPMT_TR", evtype="CASH"),
                fila("5", "200", owner="DPMT_TR", book="FX_ESTRAT", evtype="FEE"),
                fila("6", "300", owner="DPMT_TR", evtype="FEE", moneda="EUR"),
            ],
        )

        resultado = self._ejecutar("03/08/2026", reporte)
        resumen = resultado.attrs["resumen_spot"].set_index("POSICION_ID")

        self.assertEqual(resumen.at["FWD_CLIENTES", "COMPRAS_USD"], "14")
        self.assertEqual(resumen.at["FWD_CLIENTES", "VENTAS_USD"], "1")
        self.assertEqual(resumen.at["FWD_CLIENTES", "MOVIMIENTO_NETO_USD"], "13")
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_movimientos_spot "
                "WHERE PRODUCTO_ORIGEN='DPMT_TR' AND VIGENTE=1",
            )[0],
            2,
        )

    def test_posicion_inicial_fin_de_semana_y_carry_forward(self):
        registrar_posiciones_iniciales(
            "01/08/2026",
            {"FWD_Clientes": Decimal("100")},
            ruta_db=self.db,
            pruebas=True,
        )
        reporte = self.carpeta / "caja_0308.xls"
        escribir_reporte(reporte, [fila("1", "10")])
        self._ejecutar("03/08/2026", reporte)

        with closing(sqlite3.connect(self.db)) as conexion:
            datos = conexion.execute(
                "SELECT FECHA, POSICION_ANTERIOR, POSICION_FINAL_USD, TIPO_ORIGEN "
                "FROM tbl_posicion_spot_acumulada WHERE POSICION_ID='FWD_CLIENTES' "
                "ORDER BY substr(FECHA,7,4), substr(FECHA,4,2), substr(FECHA,1,2)"
            ).fetchall()
        self.assertEqual(
            datos,
            [
                ("01/08/2026", "0", "100", "EXCEL_INICIAL"),
                ("02/08/2026", "100", "100", "CARRY_FORWARD"),
                ("03/08/2026", "100", "110", "MOVIMIENTOS"),
            ],
        )

    def test_arrastrar_spot_acumulado_publica_fecha_sin_reporte_caja(self):
        posiciones = {
            posicion: Decimal("0")
            for posicion in (
                "CFH",
                "CUBRE_BAC",
                "FACTURASUSD",
                "FILIALES",
                "FUTUROS_FX",
                "FVH",
                "FWD_CLIENTES",
                "FX_ESTRAT",
                "OPCIONES",
                "POS_PROPIA",
                "SPOT_CLIENTE",
                "RF_ME_FV_OCI",
                "RF_ME_TRADIN",
                "SWAPS",
                "TRADING",
            )
        }
        posiciones["FWD_CLIENTES"] = Decimal("100")
        registrar_posiciones_iniciales(
            "06/08/2026",
            posiciones,
            ruta_db=self.db,
            pruebas=True,
        )

        resultado = arrastrar_spot_acumulado(
            "08/08/2026",
            ruta_db=self.db,
            pruebas=True,
        )
        resumen = resultado.attrs["resumen_spot"].set_index("POSICION_ID")

        self.assertEqual(len(resultado), 15)
        self.assertEqual(resultado["FECHA"].unique().tolist(), ["08/08/2026"])
        self.assertEqual(resumen.at["FWD_CLIENTES", "POSICION_FINAL_USD"], "100")
        self.assertEqual(resumen.at["FWD_CLIENTES", "TIPO_ORIGEN"], "CARRY_FORWARD")
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_movimientos_spot WHERE FECHA='08/08/2026'",
            )[0],
            0,
        )

    def test_archivo_repetido_es_idempotente(self):
        reporte = self.carpeta / "caja.xls"
        escribir_reporte(reporte, [fila("1", "10")])
        self._ejecutar("03/08/2026", reporte)
        movimientos_antes = leer_uno(
            self.db, "SELECT COUNT(*) FROM tbl_movimientos_spot"
        )[0]
        self._ejecutar("03/08/2026", reporte)

        self.assertEqual(
            leer_uno(self.db, "SELECT COUNT(*) FROM tbl_movimientos_spot")[0],
            movimientos_antes,
        )
        self.assertEqual(
            leer_uno(self.db, "SELECT COUNT(*) FROM tbl_ejecuciones_spot")[0],
            2,
        )
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_ejecuciones_spot WHERE ESTADO='OMITIDA'",
            )[0],
            1,
        )
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_alertas_spot "
                "WHERE CODIGO='DUPLICATE_SOURCE_FILE' AND VIGENTE=1",
            )[0],
            1,
        )

    def test_reproceso_historico_recalcula_fechas_posteriores(self):
        registrar_posiciones_iniciales(
            "01/08/2026", {"FWD_CLIENTES": "100"}, ruta_db=self.db, pruebas=True
        )
        reporte_3a = self.carpeta / "caja_3a.xls"
        reporte_4 = self.carpeta / "caja_4.xls"
        reporte_3b = self.carpeta / "caja_3b.xls"
        escribir_reporte(reporte_3a, [fila("1", "10")])
        escribir_reporte(reporte_4, [fila("2", "5", fecha="04/08/26")])
        escribir_reporte(reporte_3b, [fila("1", "20")])

        self._ejecutar("03/08/2026", reporte_3a)
        self._ejecutar("04/08/2026", reporte_4)
        self._ejecutar("03/08/2026", reporte_3b)

        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT POSICION_FINAL_USD FROM tbl_posicion_spot_acumulada "
                "WHERE FECHA='03/08/2026' AND POSICION_ID='FWD_CLIENTES'",
            )[0],
            "120",
        )
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT POSICION_FINAL_USD FROM tbl_posicion_spot_acumulada "
                "WHERE FECHA='04/08/2026' AND POSICION_ID='FWD_CLIENTES'",
            )[0],
            "125",
        )
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_movimientos_spot "
                "WHERE FECHA='03/08/2026' AND VIGENTE=0",
            )[0],
            1,
        )

    def test_cambio_de_posicion_inicial_recalcula_acumulado(self):
        registrar_posiciones_iniciales(
            "01/08/2026", {"FWD_CLIENTES": "100"}, ruta_db=self.db, pruebas=True
        )
        reporte = self.carpeta / "caja.xls"
        escribir_reporte(reporte, [fila("1", "10")])
        self._ejecutar("03/08/2026", reporte)
        registrar_posiciones_iniciales(
            "01/08/2026", {"FWD_CLIENTES": "200"}, ruta_db=self.db, pruebas=True
        )

        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT POSICION_FINAL_USD FROM tbl_posicion_spot_acumulada "
                "WHERE FECHA='03/08/2026' AND POSICION_ID='FWD_CLIENTES'",
            )[0],
            "210",
        )
        self.assertGreaterEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_auditoria_spot "
                "WHERE MOTIVO='INITIAL_POSITION_CHANGE'",
            )[0],
            1,
        )

    def test_encabezado_invalido_no_crea_base(self):
        reporte = self.carpeta / "invalido.xls"
        reporte.write_text("A;B;C\n1;2;3", encoding="cp1252")
        with self.assertRaisesRegex(ValueError, "encabezado requerido"):
            self._ejecutar("03/08/2026", reporte)
        self.assertFalse(self.db.exists())

    def test_fecha_y_amount_invalidos_quedan_en_alertas(self):
        reporte = self.carpeta / "valores_invalidos.xls"
        escribir_reporte(
            reporte,
            [
                fila("1", "NO_ES_NUMERO"),
                fila("2", "10", fecha="FECHA_MALA"),
                fila("3", "5"),
            ],
        )
        resultado = self._ejecutar("03/08/2026", reporte)
        resumen = resultado.attrs["resumen_spot"].set_index("POSICION_ID")
        self.assertEqual(resumen.at["FWD_CLIENTES", "POSICION_FINAL_USD"], "5")
        with closing(sqlite3.connect(self.db)) as conexion:
            codigos = {
                fila_db[0]
                for fila_db in conexion.execute(
                    "SELECT CODIGO FROM tbl_alertas_spot WHERE VIGENTE=1"
                ).fetchall()
            }
        self.assertIn("INVALID_AMOUNT", codigos)
        self.assertIn("INVALID_DATE", codigos)

    def test_book_inactivo_se_traza_y_no_se_publica(self):
        reporte = self.carpeta / "inactivo.xls"
        escribir_reporte(reporte, [fila("1", "10", book="LIBRO_INACTIVO")])
        definicion = {
            "BOOK": "LIBRO_INACTIVO",
            "BOOK_CLAVE": "LIBRO_INACTIVO",
            "POSICION_ID": "POS_INACTIVA",
            "POSICION_NOMBRE": "Pos inactiva",
            "ACTIVO": False,
            "LB_LT": "Tesoreria",
            "INSTRUMENTO": "Derivados",
            "MONEDA_POSICION": "USD",
        }
        movimientos, alertas = _leer_movimientos(
            reporte,
            __import__("datetime").date(2026, 8, 3),
            {"LIBRO_INACTIVO": definicion},
            {"FXFWD"},
        )
        self.assertEqual(movimientos[0]["PUBLICABLE"], 0)
        self.assertEqual([alerta["CODIGO"] for alerta in alertas], ["INACTIVE_BOOK"])

    def test_importa_excel_parametrico_propio_con_las_15_posiciones(self):
        from datetime import datetime
        from openpyxl import Workbook

        posiciones = [
            "CFH",
            "Cubre_Bac",
            "FVH",
            "FWD_Clientes",
            "FX_Estrat",
            "FacturasUSD",
            "Filiales",
            "Futuros_FX",
            "Opciones",
            "Pos_propia",
            "Spot_Cliente",
            "RF_ME_FV_OCI",
            "RF_ME_TRADIN",
            "Swaps",
            "Trading",
        ]
        ruta = self.carpeta / "param_posiciones_iniciales_spot.xlsx"
        libro = Workbook()
        hoja = libro.active
        hoja.title = "Posiciones_Iniciales"
        hoja.append(
            [
                "FECHA",
                "POSICION",
                "POSICION_FINAL_USD",
                "ESTADO_PARAMETRO",
            ]
        )
        for numero, posicion in enumerate(posiciones, start=1):
            hoja.append([datetime(2026, 8, 1), posicion, str(numero), "VALIDADO"])
        libro.save(ruta)
        libro.close()

        resultado = importar_posiciones_iniciales_excel(
            ruta_excel=ruta,
            ruta_db=self.db,
            pruebas=True,
        )

        self.assertEqual(len(resultado), 15)
        self.assertEqual(set(resultado["TIPO_ORIGEN"]), {"EXCEL_INICIAL"})
        self.assertEqual(
            leer_uno(
                self.db,
                "SELECT COUNT(*) FROM tbl_posicion_spot_acumulada "
                "WHERE FECHA='01/08/2026'",
            )[0],
            15,
        )


if __name__ == "__main__":
    unittest.main()
