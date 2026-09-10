from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import pandas as pd

from proyectos.position_monitor.procesos.forward import (
    _cargar_insumos_forward,
    _leer_fecha_objetivo_forward,
    _resolver_fuente_forward_por_fecha,
)
from proyectos.position_monitor.procesos.swaps import (
    _consolidar_tabla_swaps_publicacion,
    _resolver_fecha_fuente,
)
from proyectos.position_monitor.tableros.panel_position_monitor import (
    POSITION_ABBREVIATIONS_HELPER,
    _resolver_tasa_escala_dashboard,
    apply_publication_scope,
    create_builder,
    load_publication_scope_config,
    add_current_position_cards,
    add_detail_cards,
    add_global_filters,
    add_historical_cards,
    add_historical_filters,
)


class DashboardPositionMonitorTests(unittest.TestCase):
    def test_swaps_corrige_el_nombre_en_el_modulo_que_lo_origina(self):
        detalle = pd.DataFrame(
            {
                "FECHA": ["05/08/2026"],
                "PRODUCTO": ["Swap"],
                "BOOK": ["FX_ESTRAT"],
                "POSICION": [10.0],
                "MONEDA_POSICION": ["USD"],
                "LB_LT": ["Tesoreria"],
                "INSTRUMENTO": ["Derivados"],
                "COMPANY": ["Colombia"],
                "CLASIFICACION_CONTABLE": ["NA"],
                "BANKING_CVA_DVA": ["Banking"],
            }
        )

        resultado = _consolidar_tabla_swaps_publicacion(detalle)

        self.assertEqual(resultado["BOOK"].tolist(), ["Swaps"])
        self.assertEqual(resultado["LB_LT"].tolist(), ["Trading"])

    def test_forward_acepta_fecha_con_barras_hasta_validar_el_archivo(self):
        with self.assertRaises(FileNotFoundError) as error:
            _cargar_insumos_forward("05/08/2099")

        self.assertIn("05082099_000.xls", str(error.exception))

    def test_forward_lee_fecha_real_desde_parametro_fecha_y(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "Cierre_Valoracion_FxFwd_06082026_002.xls"
            ruta.write_text(
                "BANCO DE BOGOTA\nREPORTE\nFECHA GENERACION: ;06082026\n"
                "PARAMETRO FECHA X: ;07082026;PARAMETRO FECHA Y: ;08082026\n",
                encoding="latin1",
            )
            fecha = _leer_fecha_objetivo_forward(ruta)

        self.assertEqual(fecha, pd.Timestamp("2026-08-08"))

    def test_forward_resuelve_festivo_desde_archivo_001(self):
        with tempfile.TemporaryDirectory() as temporal:
            carpeta = Path(temporal)
            ruta = carpeta / "Cierre_Valoracion_FxFwd_06082026_001.xls"
            ruta.write_text(
                "BANCO DE BOGOTA\nREPORTE\nFECHA GENERACION: ;06082026\n"
                "PARAMETRO FECHA X: ;06082026;PARAMETRO FECHA Y: ;07082026\n",
                encoding="latin1",
            )
            fila = pd.Series(
                {
                    "Ruta": str(carpeta),
                    "Nombre_Archivo": "Cierre_Valoracion_FxFwd_",
                }
            )

            resultado = _resolver_fuente_forward_por_fecha(
                pd.Timestamp("2026-08-07"),
                fila,
            )

        self.assertEqual(resultado.name, "Cierre_Valoracion_FxFwd_06082026_001.xls")

    def test_swaps_usa_fecha_exacta_en_fin_de_semana(self):
        fecha = pd.Timestamp("2026-08-08")
        self.assertEqual(_resolver_fecha_fuente(fecha), fecha)

    def test_alcance_primera_entrega(self):
        tabla = pd.DataFrame(
            {
                "PRODUCTO": ["Forward", "Forward", "Swap", "Titulos"],
                "BOOK": ["FWD_CLIENTES", "No permitido", "Swaps", "Swaps"],
                "POSICION": [1, 2, 0, 4],
            }
        )
        scope = {
            "enabled": True,
            "exclude_products": ["Titulos"],
            "allowed_books": ["Fwd Clientes", "Swaps"],
        }

        resultado = apply_publication_scope(tabla, scope)

        self.assertEqual(resultado["BOOK"].tolist(), ["FWD_CLIENTES", "Swaps"])
        self.assertEqual(resultado["POSICION"].tolist(), [1, 0])
        self.assertNotIn("Titulos", set(resultado["PRODUCTO"]))

    def test_restriccion_se_puede_desactivar_desde_configuracion(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "dashboard_publicacion.json"
            ruta.write_text(
                json.dumps(
                    {
                        "publication_scope": {
                            "enabled": False,
                            "exclude_products": ["Titulos"],
                            "allowed_books": [],
                        }
                    }
                ),
                encoding="utf-8",
            )
            scope = load_publication_scope_config(ruta)
            tabla = pd.DataFrame(
                {"PRODUCTO": ["Titulos"], "BOOK": ["SWAPS"], "POSICION": [5]}
            )

            resultado = apply_publication_scope(tabla, scope)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado.iloc[0]["BOOK"], "SWAPS")

    def test_dashboard_sin_decimales_y_sin_categoria_otros(self):
        builder = create_builder()
        add_current_position_cards(builder, trm_formada=3053.48)

        self.assertEqual(builder.defaults["decimals"], 0)
        grafica = next(chart for chart in builder.charts if chart["id"] == "posicion_por_grupo")
        self.assertEqual(grafica["top_n"], 0)
        self.assertNotIn("y_tickformat", grafica)
        self.assertEqual(grafica["y_axis_title"], "Posicion por moneda (k / MM / Blls)")
        self.assertEqual(grafica["color"], "MONEDA_POSICION")
        self.assertTrue(grafica["palette_by_bar"])
        self.assertEqual(grafica["dual_y_axis"]["primary_value"], "COP")
        self.assertEqual(grafica["dual_y_axis"]["secondary_value"], "USD")
        self.assertEqual(grafica["dual_y_axis"]["primary_title"], "Posicion COP")
        self.assertEqual(grafica["dual_y_axis"]["secondary_title"], "Posicion USD")
        self.assertEqual(grafica["dual_y_axis"]["scale_factor"], 3053.48)
        self.assertEqual(grafica["dual_y_axis"]["scale_label"], "TRM FORMADA")
        self.assertEqual(
            grafica["dual_y_axis"]["abbreviations"]["billion_divisors"],
            {"COP": 1_000_000_000_000, "USD": 1_000_000_000},
        )
        self.assertEqual(
            grafica["helper_text"],
            "Abreviaturas: k = miles; MM = millones; Blls = mil millones en USD "
            "y millón de millones en COP.",
        )

        tabla = next(chart for chart in builder.charts if chart["id"] == "tabla_total")
        self.assertEqual(
            tabla["groupby"]["cols"],
            ["GRUPO_GRAFICA", "MONEDA_POSICION"],
        )
        self.assertIn("MONEDA_POSICION", [columna["name"] for columna in tabla["columns"]])
        self.assertEqual(tabla["totals"]["group_by"], "MONEDA_POSICION")

    def test_historico_presenta_la_fecha_como_corte_mensual(self):
        builder = create_builder()
        add_historical_cards(builder, trm_formada=3053.48)

        grafica = next(
            chart for chart in builder.charts if chart["id"] == "serie_historica_posicion"
        )
        self.assertEqual(grafica["x"], "FECHA")
        self.assertEqual(grafica["x_period_label"], "month_year")
        self.assertEqual(grafica["axis_group"], "MONEDA_POSICION")
        self.assertEqual(grafica["dual_y_axis"]["scale_factor"], 3053.48)
        self.assertEqual(
            grafica["dual_y_axis"]["abbreviations"]["billion_divisors"],
            {"COP": 1_000_000_000_000, "USD": 1_000_000_000},
        )
        self.assertEqual(grafica["y_axis_title"], "Posicion por moneda (k / MM / Blls)")
        self.assertEqual(grafica["helper_text"], POSITION_ABBREVIATIONS_HELPER)
        self.assertIn("corte mensual", grafica["subtitle"])

    def test_filtro_historico_inicia_sin_restriccion_de_fecha(self):
        builder = create_builder()
        historico = pd.DataFrame({"FECHA": pd.to_datetime(["2026-01-31", "2026-07-31"])})

        add_historical_filters(builder, historico)

        filtro = next(item for item in builder.filters if item["id"] == "f_historico_fecha")
        self.assertIsNone(filtro["default"])
        self.assertEqual(filtro["empty_label"], "Todos los cierres")

    def test_preliminar_agrega_promedio_setfx_al_banner_despues_de_la_fecha(self):
        builder = create_builder(
            estado_corte="PRELIMINAR_INTRADIA",
            fechas_datos=["18/08/2026"],
            promedio_setfx=3094.91,
        )

        etiquetas = [item["label"] for item in builder.header_badges]
        self.assertEqual(etiquetas[-2], "Fecha de posición: 18/08/2026")
        self.assertEqual(etiquetas[-1], "PROMEDIO SETFX: 3.094,91")
        self.assertFalse(builder.charts)

    def test_preliminar_rechaza_promedio_setfx_invalido(self):
        with self.assertRaisesRegex(ValueError, "PROMEDIO SETFX invalido"):
            create_builder(
                estado_corte="PRELIMINAR_INTRADIA",
                promedio_setfx=0,
            )

    def test_preliminar_usa_solo_promedio_setfx_para_la_escala(self):
        posicion = pd.DataFrame({"FECHA": ["18/08/2026"]})
        with mock.patch(
            "proyectos.position_monitor.tableros.panel_position_monitor."
            "obtener_trm_formada",
            side_effect=AssertionError("No debe consultar TRM FORMADA"),
        ) as obtener_formada:
            tasa, etiqueta = _resolver_tasa_escala_dashboard(
                posicion,
                estado_corte="PRELIMINAR_INTRADIA",
                promedio_setfx=3094.91,
            )

        obtener_formada.assert_not_called()
        self.assertEqual(tasa, 3094.91)
        self.assertEqual(etiqueta, "PROMEDIO SETFX")

        builder = create_builder(
            estado_corte="PRELIMINAR_INTRADIA",
            promedio_setfx=tasa,
        )
        add_current_position_cards(
            builder,
            trm_formada=tasa,
            scale_label=etiqueta,
        )
        grafica = next(
            chart for chart in builder.charts if chart["id"] == "posicion_por_grupo"
        )
        etiquetas = [item["label"] for item in builder.header_badges]
        self.assertEqual(grafica["dual_y_axis"]["scale_factor"], 3094.91)
        self.assertEqual(grafica["dual_y_axis"]["scale_label"], "PROMEDIO SETFX")
        self.assertFalse(any(item.startswith("TRM FORMADA:") for item in etiquetas))

    def test_filtros_globales_inician_cerrados_y_tienen_todos_ninguno(self):
        builder = create_builder()
        add_global_filters(builder)

        self.assertEqual(builder.page_options["filters_collapsed_threshold"], 0)
        self.assertTrue(builder.filters)
        self.assertTrue(all(not filtro["open"] for filtro in builder.filters))
        self.assertTrue(all(filtro["bulk_actions"] for filtro in builder.filters))

    def test_tabla_muestra_la_posicion_contable_segun_el_filtro(self):
        builder = create_builder()
        add_current_position_cards(builder, trm_formada=3053.48)
        add_detail_cards(builder)

        tablas = [
            chart
            for chart in builder.charts
            if chart["id"] in {"tabla_total", "tabla_tbl_posicion"}
        ]
        self.assertEqual(len(tablas), 2)
        contexto = tablas[0]["context_label"]
        casos = {tuple(caso["values"]): caso["label"] for caso in contexto["cases"]}

        self.assertTrue(all(tabla["context_label"] == contexto for tabla in tablas))
        self.assertEqual(contexto["filter_id"], "f_global_banking_cva_dva")
        self.assertEqual(contexto["empty_label"], "IFRS")
        self.assertEqual(casos[("Banking", "CVA/DVA")], "IFRS")
        self.assertEqual(casos[("Banking",)], "Banking")
        self.assertEqual(casos[("CVA/DVA",)], "CVA/DVA")
        self.assertTrue(
            all(tabla["totals"]["group_by"] == "MONEDA_POSICION" for tabla in tablas)
        )


if __name__ == "__main__":
    unittest.main()
