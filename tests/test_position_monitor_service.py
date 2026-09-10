from __future__ import annotations

from types import SimpleNamespace
from unittest import mock
import unittest

import pandas as pd

from aplicaciones.interfaz_risko.servicios import position_monitor as servicio
from proyectos.position_monitor.procesos.consolidacion import (
    COLUMNAS_POSICION,
    _excluir_productos_no_liberados,
    _normalizar_tabla_posicion,
)
from proyectos.position_monitor.procesos.parametros_libros import (
    cargar_parametros_libros,
    enriquecer_con_parametros_libros,
)
from proyectos.position_monitor.tableros.panel_position_monitor import (
    apply_publication_scope,
    load_publication_scope_config,
)


def tabla_canonica(producto: str, fecha: str = "06/08/2026") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "FECHA": fecha,
                "PRODUCTO": producto,
                "BOOK": producto,
                "POSICION": 1.0,
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


class EjecucionTotalPositionMonitorTests(unittest.TestCase):
    def test_preliminar_entrega_al_dashboard_el_setfx_usado_por_opciones(self):
        resultado_intradia = SimpleNamespace(
            posicion=tabla_canonica("Opciones", "18/08/2026"),
            estado="PRELIMINAR_INTRADIA",
            productos_pendientes=[],
            promedio_setfx=3094.91,
            calidad=[],
            vista_contable="Banking",
            fecha="2026-08-18",
            fuentes={},
        )

        with (
            mock.patch(
                "proyectos.position_monitor.procesos.intradia.calcular_position_monitor_intradia",
                return_value=resultado_intradia,
            ),
            mock.patch(
                "proyectos.position_monitor.tableros.panel_position_monitor.read_historical_position_data",
                return_value=tabla_canonica("Opciones", "31/07/2026"),
            ),
            mock.patch(
                "proyectos.position_monitor.tableros.panel_position_monitor.build_dashboard",
                return_value="preliminar.html",
            ) as dashboard,
        ):
            servicio.ejecutar_intradia_position_monitor(
                "18/08/2026",
                cargar_insumos=False,
                publicar=False,
            )

        self.assertEqual(dashboard.call_args.kwargs["promedio_setfx"], 3094.91)

    def test_ejecutar_todo_invoca_solo_productos_liberados(self):
        invocados: list[str] = []

        def ejecutar(producto, *_args, **kwargs):
            invocados.append(producto)
            self.assertTrue(kwargs["retornar_canonica"])
            return tabla_canonica(producto)

        with (
            mock.patch.object(servicio, "limpiar_insumos_risko") as limpiar,
            mock.patch.object(servicio, "ejecutar_producto", side_effect=ejecutar),
            mock.patch.object(
                servicio,
                "consolidar_position_monitor",
                return_value={"actual": "actual.csv"},
            ) as consolidar,
            mock.patch.object(
                servicio,
                "generar_tablero",
                return_value="panel.html",
            ) as tablero,
        ):
            resultado = servicio.ejecutar_todo_position_monitor("06-08-2026")

        self.assertEqual(invocados, list(servicio.PRODUCTOS_EJECUCION_TOTAL))
        self.assertEqual(
            servicio.PRODUCTOS_EJECUCION_TOTAL,
            ("SPOT", "NOVADOS", "FORWARD", "RENTA_FIJA", "OPCIONES", "SWAPS"),
        )
        self.assertEqual(len(resultado["tablas"]), 6)
        limpiar.assert_called_once()
        tablas_consolidadas = consolidar.call_args.kwargs["tablas"]
        self.assertEqual(len(tablas_consolidadas), 6)
        self.assertIn("SPOT", {tabla.iloc[0]["PRODUCTO"] for tabla in tablas_consolidadas})
        self.assertTrue(
            set(servicio.PRODUCTOS_FUERA_EJECUCION_TOTAL).isdisjoint(invocados)
        )
        tablero.assert_called_once()

    def test_ejecutar_todo_fin_de_semana_incluye_spot_acumulado(self):
        invocados: list[str] = []

        def ejecutar(producto, *_args, **_kwargs):
            invocados.append(producto)
            return tabla_canonica(producto, "08/08/2026")

        with (
            mock.patch.object(servicio, "limpiar_insumos_risko"),
            mock.patch.object(servicio, "ejecutar_producto", side_effect=ejecutar),
            mock.patch.object(
                servicio,
                "consolidar_position_monitor",
                return_value={"actual": "actual.csv"},
            ),
            mock.patch.object(servicio, "generar_tablero", return_value="panel.html"),
        ):
            resultado = servicio.ejecutar_todo_position_monitor("08-08-2026")

        self.assertEqual(
            invocados,
            ["SPOT", "NOVADOS", "FORWARD", "RENTA_FIJA", "OPCIONES", "SWAPS"],
        )
        self.assertEqual(len(resultado["tablas"]), 6)

    def test_festivo_aplica_la_misma_regla_de_fecha_no_habil(self):
        self.assertTrue(servicio._es_fecha_no_habil("07-08-2026"))
        self.assertEqual(
            servicio._productos_ejecucion_total("07-08-2026"),
            servicio.PRODUCTOS_EJECUCION_TOTAL,
        )

    def test_novados_fin_de_semana_arrastra_ultima_posicion(self):
        historico = pd.concat(
            [
                tabla_canonica("Novados", "06/08/2026"),
                tabla_canonica("Novados", "05/08/2026"),
            ],
            ignore_index=True,
        )
        historico.loc[historico["FECHA"] == "06/08/2026", "POSICION"] = 25.0

        with mock.patch.object(
            servicio,
            "leer_tabla_position_monitor",
            return_value=historico,
        ):
            resultado = servicio._arrastrar_ultima_posicion_novados("08-08-2026")

        self.assertEqual(resultado["FECHA"].unique().tolist(), ["08/08/2026"])
        self.assertEqual(resultado["POSICION"].tolist(), [25.0])

    def test_spot_fin_de_semana_usa_carry_forward_sin_vector(self):
        canonica = tabla_canonica("Spot", "08/08/2026")
        resumen = pd.DataFrame({"POSICION_ID": ["OPCIONES"], "POSICION_FINAL_USD": [10]})
        canonica.attrs["resumen_spot"] = resumen

        with (
            mock.patch(
                "proyectos.position_monitor.procesos.spot.arrastrar_spot_acumulado",
                return_value=canonica,
            ) as arrastrar,
            mock.patch.object(servicio, "ejecutar_flujo_vector") as vector,
            mock.patch.object(servicio, "guardar_tabla_producto_position_monitor"),
        ):
            resultado = servicio.ejecutar_producto(
                "SPOT",
                "08-08-2026",
                cargar_insumos=True,
                consolidar=False,
                retornar_canonica=True,
            )

        self.assertIs(resultado, canonica)
        arrastrar.assert_called_once()
        vector.assert_not_called()

    def test_spot_entrega_canonica_al_pipeline_y_resumen_a_interfaz(self):
        canonica = tabla_canonica("Spot")
        resumen = pd.DataFrame({"POSICION_ID": ["OPCIONES"], "POSICION_FINAL_USD": [10]})
        canonica.attrs["resumen_spot"] = resumen

        with (
            mock.patch(
                "proyectos.position_monitor.procesos.spot.ejecutar_spot",
                return_value=canonica,
            ),
            mock.patch.object(servicio, "guardar_tabla_producto_position_monitor"),
        ):
            para_interfaz = servicio.ejecutar_producto(
                "SPOT",
                "06-08-2026",
                cargar_insumos=False,
                consolidar=False,
            )
            para_pipeline = servicio.ejecutar_producto(
                "SPOT",
                "06-08-2026",
                cargar_insumos=False,
                consolidar=False,
                retornar_canonica=True,
            )

        self.assertIs(para_interfaz, resumen)
        self.assertIs(para_pipeline, canonica)

    def test_renta_fija_individual_consolida_cuando_se_solicita(self):
        canonica = tabla_canonica("Titulos")

        with (
            mock.patch(
                "proyectos.position_monitor.procesos.renta_fija.ejecutar_renta_fija",
                return_value=canonica,
            ),
            mock.patch.object(servicio, "guardar_tabla_producto_position_monitor") as guardar,
            mock.patch.object(servicio, "consolidar_position_monitor") as consolidar,
        ):
            resultado = servicio.ejecutar_producto(
                "RENTA_FIJA",
                "06-08-2026",
                cargar_insumos=False,
                consolidar=True,
                retornar_canonica=True,
            )

        self.assertIs(resultado, canonica)
        guardar.assert_called_once()
        consolidar.assert_called_once()

    def test_renta_fija_se_incluye_en_la_entrada_al_consolidado(self):
        entrada = pd.concat(
            [tabla_canonica("Spot"), tabla_canonica("Titulos")],
            ignore_index=True,
        )

        resultado = _excluir_productos_no_liberados(entrada)

        self.assertEqual(resultado["PRODUCTO"].tolist(), ["Spot", "Titulos"])

    def test_modulos_no_liberados_se_excluyen_de_la_entrada_al_consolidado(self):
        entrada = pd.concat(
            [tabla_canonica("Titulos"), tabla_canonica("Cubrebonos")],
            ignore_index=True,
        )

        resultado = _excluir_productos_no_liberados(entrada)

        self.assertEqual(resultado["PRODUCTO"].tolist(), ["Titulos"])

    def test_caja_se_homologa_como_spot(self):
        tabla = tabla_canonica("Caja")

        resultado = _normalizar_tabla_posicion(tabla)

        self.assertEqual(resultado["PRODUCTO"].tolist(), ["Spot"])
        self.assertEqual(resultado["LB_LT"].tolist(), ["Trading"])

    def test_novados_fwd_clientes_tiene_clasificacion_trading(self):
        tabla = pd.DataFrame({"BOOK": ["FWD_CLIENTES"], "POSICION": [0.0]})

        resultado = enriquecer_con_parametros_libros(tabla, producto="Novados")

        self.assertEqual(resultado["BOOK"].tolist(), ["FWD_Clientes"])
        self.assertEqual(resultado["LB_LT"].tolist(), ["Trading"])

    def test_productos_con_books_rf_conservan_el_nombre_original(self):
        tabla = pd.DataFrame(
            {
                "BOOK": ["RF_ME_FV_OCI", "RF_ME_TRADIN"],
                "POSICION": [1.0, 2.0],
            }
        )

        for producto in ("Forward", "Novados", "Opciones", "Spot"):
            with self.subTest(producto=producto):
                resultado = enriquecer_con_parametros_libros(
                    tabla,
                    producto=producto,
                    default_instrumento="Derivados",
                    default_moneda_posicion="USD",
                )

                self.assertEqual(
                    resultado["BOOK"].tolist(),
                    ["RF_ME_FV_OCI", "RF_ME_TRADIN"],
                )
                self.assertEqual(resultado["LB_LT"].tolist(), ["Trading", "Trading"])
                instrumento = "Renta_fija" if producto == "Spot" else "Derivados"
                self.assertEqual(
                    resultado["INSTRUMENTO"].tolist(),
                    [instrumento, instrumento],
                )

    def test_novados_cubre_todos_los_books_actuales_como_trading(self):
        parametros = cargar_parametros_libros()
        books_actuales = set(parametros["BOOK"])
        novados = parametros.loc[parametros["PRODUCTO"] == "Novados"]

        self.assertSetEqual(set(novados["BOOK"]), books_actuales)
        self.assertSetEqual(set(novados["LB_BT"]), {"Trading"})
        self.assertSetEqual(set(novados["LB_LT"]), {"Trading"})

    def test_productos_fuera_del_alcance_no_se_publican(self):
        scope = load_publication_scope_config()
        tabla = pd.DataFrame(
            {
                "PRODUCTO": ["Spot", "Cubrebonos", "NDFTES", "PP"],
                "BOOK": ["Opciones", "Opciones", "Opciones", "Opciones"],
                "POSICION": [1, 2, 3, 4],
            }
        )

        resultado = apply_publication_scope(tabla, scope)

        self.assertEqual(resultado["PRODUCTO"].tolist(), ["Spot"])

    def test_books_rf_de_todos_los_productos_estan_en_el_alcance_publicable(self):
        scope = load_publication_scope_config()
        tabla = pd.DataFrame(
            {
                "PRODUCTO": [
                    "Titulos",
                    "Forward",
                    "Forward",
                    "Novados",
                    "Novados",
                    "Opciones",
                    "Opciones",
                    "Spot",
                    "Spot",
                ],
                "BOOK": [
                    "RF_ME_TRADIN",
                    "RF_ME_FV_OCI",
                    "RF_ME_TRADIN",
                    "RF_ME_FV_OCI",
                    "RF_ME_TRADIN",
                    "RF_ME_FV_OCI",
                    "RF_ME_TRADIN",
                    "RF_ME_FV_OCI",
                    "RF_ME_TRADIN",
                ],
                "POSICION": [1, 2, 3, 4, 5, 6, 7, 8, 9],
            }
        )

        resultado = apply_publication_scope(tabla, scope)

        self.assertEqual(resultado["PRODUCTO"].tolist(), tabla["PRODUCTO"].tolist())

    def test_spot_cliente_esta_en_el_alcance_publicable(self):
        scope = load_publication_scope_config()
        tabla = pd.DataFrame(
            {
                "PRODUCTO": ["Spot", "Spot"],
                "BOOK": ["Spot_Cliente", "No permitido"],
                "POSICION": [577822.59, 1.0],
            }
        )

        resultado = apply_publication_scope(tabla, scope)

        self.assertEqual(resultado["BOOK"].tolist(), ["Spot_Cliente"])


if __name__ == "__main__":
    unittest.main()
