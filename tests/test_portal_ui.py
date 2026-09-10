from __future__ import annotations

import json
import os
from datetime import date, datetime as RealDateTime
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock
from urllib.request import urlopen

from portal import script as portal


class FixedPortalDateTime(RealDateTime):
    current = RealDateTime(2026, 8, 6, 12, 0)

    @classmethod
    def now(cls, tz=None):
        value = cls.current
        return value if tz is None else value.astimezone(tz)


class PortalRiskoUiTests(unittest.TestCase):
    def setUp(self) -> None:
        FixedPortalDateTime.current = RealDateTime(2026, 8, 6, 12, 0)
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        published = root / "publicados"
        applications = root / "aplicaciones"
        configurations = root / "configuraciones"
        legacy_configurations = root / "configuraciones_compartidas"
        comments = root / "comentarios"
        applications.mkdir(parents=True)
        configurations.mkdir(parents=True)
        comment_year = comments / "2026"
        comment_year.mkdir(parents=True)
        (comment_year / "2026-08-05.md").write_text(
            "# Comentario de mercado\n\n"
            "Comentario transversal para la jornada.\n\n"
            "## Indicadores\n\n"
            "- **TRM:** $4.100 COP\n",
            encoding="utf-8",
        )

        self._create_publication(
            published,
            "Portfolio Position Monitor",
            "2026-08-04",
            "Portfolio Position Monitor",
        )
        self._create_publication(
            published,
            "Portfolio Position Monitor",
            "2026-08-05",
            "Portfolio Position Monitor",
        )
        self._create_publication(
            published,
            "Liquidez",
            "2026-08-05",
            "Monitor de Liquidez",
        )
        (published / "Portfolio Position Monitor" / "dashboard.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "portfolio-position-monitor",
                    "nombre": "Portfolio Position Monitor",
                    "descripcion": "Posición consolidada de tesorería.",
                    "archivo": "portfolio_position_monitor.html",
                    "configuracion": {"habilitada": True},
                }
            ),
            encoding="utf-8",
        )

        self.global_patches = (
            mock.patch.object(portal, "PUBLISHED_DIR", published),
            mock.patch.object(portal, "APPLICATIONS_DIR", applications),
            mock.patch.object(portal, "CONFIG_DIR", configurations),
            mock.patch.object(portal, "LEGACY_CONFIG_DIR", legacy_configurations),
            mock.patch.object(portal, "COMMENTS_DIR", comments),
            mock.patch.dict(os.environ, {"PORTAL_RISKO_UI_TEST": "1"}),
        )
        for patcher in self.global_patches:
            patcher.start()

        self.root = tk.Tk()
        self.root.withdraw()
        self.app = portal.PortalRiskoApp(self.root)
        self._wait_until(lambda: self.app.initial_refresh_complete)

    def tearDown(self) -> None:
        if self.root.winfo_exists():
            self.app.close()
        for patcher in reversed(self.global_patches):
            patcher.stop()
        self.temp.cleanup()

    @staticmethod
    def _create_publication(
        published: Path,
        dashboard: str,
        position_date: str,
        title: str,
    ) -> None:
        folder = published / dashboard / position_date
        folder.mkdir(parents=True, exist_ok=True)
        html_path = folder / "portfolio_position_monitor.html"
        html_path.write_text(
            f"<!doctype html><html><head><title>{title}</title></head>"
            "<body>Prueba Portal RISKO</body></html>",
            encoding="utf-8",
        )
        (folder / "publicacion.json").write_text(
            json.dumps(
                {
                    "archivo": html_path.name,
                    "fecha_publicacion": position_date,
                    "fechas_datos": [position_date],
                    "publicado_en": f"{position_date}T16:30:00",
                    "publicado_por": "PRUEBA",
                }
            ),
            encoding="utf-8",
        )

    def _wait_until(self, predicate, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.root.update()
            if predicate():
                return
            time.sleep(0.02)
        self.fail("La interfaz no terminó la operación dentro del tiempo esperado")

    def _select_dashboard_group(self, text: str) -> None:
        label = next(label for label in self.app.combo_map if text in label)
        self.app.dashboard_var.set(label)
        self.app.on_dashboard_combo_changed()

    def _select_position(self, text: str) -> str:
        selected_date = next(
            value
            for value in self.app.version_date_map
            if text in portal._format_calendar_date(value)
        )
        with mock.patch.object(portal, "datetime", FixedPortalDateTime):
            self.app._select_position_date(selected_date)
        return portal._format_calendar_date(selected_date)

    def test_layout_principal_sin_modulos_eliminados_y_responsive(self) -> None:
        self.assertFalse(hasattr(self.app, "sidebar"))
        self.assertIsNone(self.app.tree)
        for removed in (
            "search_entry",
            "quick_filter_combo",
            "versions_card",
            "details_frame",
            "help_page",
            "version_combo",
        ):
            self.assertFalse(hasattr(self.app, removed), removed)
        self.assertEqual(int(self.root.grid_columnconfigure(0)["weight"]), 1)
        self.assertTrue(hasattr(self.app, "preview_card"))
        self.assertTrue(hasattr(self.app, "lower_cards"))
        self.assertTrue(hasattr(self.app, "service_var"))
        self.assertTrue(hasattr(self.app, "calendar_button"))
        self.assertIsNotNone(self.app.logo_image)
        self.assertTrue(hasattr(self.app, "hero_logo_label"))
        self.assertTrue(str(self.app.hero_logo_label.cget("image")))
        self.assertEqual(int(self.app.actions_frame.grid_info()["row"]), 3)
        self.assertEqual(int(self.app.preview_label.grid_info()["row"]), 4)

        self.app._reflow_content(650)
        self.assertEqual(int(self.app.comment_panel.grid_info()["row"]), 5)
        self.assertEqual(int(self.app.comment_panel.grid_info()["column"]), 0)
        action_rows = {
            int(button.grid_info()["row"])
            for button in self.app.action_controls
        }
        self.assertEqual(action_rows, {0, 1})
        self.app._reflow_content(1300)
        self.assertEqual(int(self.app.comment_panel.grid_info()["row"]), 4)
        self.assertEqual(int(self.app.comment_panel.grid_info()["column"]), 1)
        self.assertEqual(
            {int(button.grid_info()["row"]) for button in self.app.action_controls},
            {0},
        )
        self.app._reflow_hero(type("Event", (), {"width": 700})())
        self.assertEqual(self.app.hero_layout, "compact")

        self.root.geometry("1180x760")
        self.root.deiconify()
        self.root.update_idletasks()
        self.root.update()
        self._wait_until(
            lambda: self.app.content_frame.winfo_height()
            >= self.app.content_frame.winfo_reqheight()
        )
        self.assertLessEqual(
            self.app.lower_frame.winfo_rooty() + self.app.lower_frame.winfo_height(),
            self.app.preview_label.winfo_rooty(),
        )

    def test_selectores_fecha_exacta_vista_previa_y_hoy_sin_reemplazo(self) -> None:
        self._select_dashboard_group("Liquidez")
        self.assertEqual(self.app.title_var.get(), "Liquidez")
        liquidez = self.app._dashboard_by_relative(self.app.selected_relative)
        self.assertIsNotNone(liquidez)
        self.assertFalse(liquidez.configurations_enabled)
        self.assertEqual(self.app.lower_config_var.get(), "No parametrizada")

        self._select_dashboard_group("Portfolio Position Monitor")
        FixedPortalDateTime.current = RealDateTime(2026, 8, 6, 12, 0)
        with mock.patch.object(portal, "datetime", FixedPortalDateTime):
            self.app.show_calendar()
        self.assertIsNotNone(self.app.calendar_window)
        self.assertTrue(self.app.calendar_window.winfo_exists())
        self.app._close_calendar()

        self._select_position("04 ago 2026")
        selected = self.app._dashboard_by_relative(self.app.selected_relative)
        self.assertIsNotNone(selected)
        self.assertEqual(portal._position_date(selected).date().isoformat(), "2026-08-04")
        self.assertIn("04 ago 2026", self.app.preview_text_var.get())

        self._select_position("05 ago 2026")
        self.assertIn("05 ago 2026", self.app.preview_text_var.get())

        FixedPortalDateTime.current = RealDateTime(2026, 8, 5, 12, 0)
        with mock.patch.object(portal, "datetime", FixedPortalDateTime):
            self.app.select_today()
        selected = self.app._dashboard_by_relative(self.app.selected_relative)
        self.assertEqual(portal._position_date(selected).date().isoformat(), "2026-08-05")

        FixedPortalDateTime.current = RealDateTime(2026, 8, 6, 12, 0)
        with mock.patch.object(portal, "datetime", FixedPortalDateTime):
            self.app.select_today()
        self.assertIsNone(self.app.selected_relative)
        self.assertEqual(
            self.app.preview_text_var.get(),
            "La posición no se ha procesado para la fecha seleccionada",
        )
        self.assertEqual(str(self.app.open_button.cget("state")), "disabled")

    def test_ultima_publicacion_usa_metadato_y_no_fecha_del_html(self) -> None:
        published = portal.PUBLISHED_DIR
        folder = published / "Portfolio Position Monitor" / "2026-08-31"
        folder.mkdir(parents=True)
        html_path = folder / "portfolio_position_monitor.html"
        html_path.write_text("<html><body>cierre</body></html>", encoding="utf-8")
        (folder / "publicacion.json").write_text(
            json.dumps(
                {
                    "archivo": html_path.name,
                    "fecha_publicacion": "2026-09-01",
                    "fechas_datos": ["2026-08-31"],
                    "publicado_en": "2026-09-01T09:15:00",
                    "estado": "CIERRE_OFICIAL",
                }
            ),
            encoding="utf-8",
        )
        timestamp_html = RealDateTime(2026, 8, 31, 18, 0).timestamp()
        os.utime(html_path, (timestamp_html, timestamp_html))
        older_position = published / "Portfolio Position Monitor" / "2026-08-05"
        (older_position / "publicacion.json").write_text(
            json.dumps(
                {
                    "archivo": "portfolio_position_monitor.html",
                    "fecha_publicacion": "2026-09-01",
                    "fechas_datos": ["2026-08-05"],
                    "publicado_en": "2026-09-01T10:00:00",
                    "estado": "PRELIMINAR_INTRADIA",
                }
            ),
            encoding="utf-8",
        )

        dashboards = portal._scan_dashboards()
        selected = next(
            dashboard
            for dashboard in dashboards
            if dashboard.relative.endswith("2026-08-31/portfolio_position_monitor.html")
        )

        self.assertEqual(
            portal._latest_publication_summary(dashboards, selected),
            "Última publicación: Posición 31 ago 2026 · CIERRE · "
            "Actualizado 01/09/2026 09:15",
        )

    def test_comentario_diario_es_transversal_y_depende_de_la_fecha(self) -> None:
        self._select_dashboard_group("Portfolio Position Monitor")
        self._select_position("05 ago 2026")

        portfolio_comment = self.app.comment_text.get("1.0", "end").strip()
        self.assertIn("Comentario transversal para la jornada.", portfolio_comment)
        self.assertIn("TRM: $4.100 COP", portfolio_comment)
        self.assertNotIn("**", portfolio_comment)
        self.assertEqual(self.app.comment_date_var.get(), "05 ago 2026")
        self.assertIn("2026/2026-08-05.md", self.app.comment_meta_var.get())

        self._select_dashboard_group("Liquidez")
        self.assertEqual(
            self.app.comment_text.get("1.0", "end").strip(),
            portfolio_comment,
        )

        self._select_dashboard_group("Portfolio Position Monitor")
        self._select_position("04 ago 2026")
        self.assertIn(
            "aún no ha publicado un comentario",
            self.app.comment_text.get("1.0", "end"),
        )
        self.assertIn("2026-08-04.md", self.app.comment_meta_var.get())

    def test_lector_de_comentarios_prioriza_markdown_y_formatea_bloques(self) -> None:
        comment = portal._read_daily_comment(date(2026, 8, 5))

        self.assertIsNotNone(comment)
        self.assertEqual(comment.path.name, "2026-08-05.md")
        self.assertEqual(
            portal._markdown_comment_blocks(comment.content),
            [
                ("h1", "Comentario de mercado"),
                ("paragraph", "Comentario transversal para la jornada."),
                ("h2", "Indicadores"),
                ("bullet", "**TRM:** $4.100 COP"),
            ],
        )

    def test_comentario_renderiza_tabla_markdown_en_columnas(self) -> None:
        content = (
            "## Tasas de la jornada\n\n"
            "| Precio máximo | Precio mínimo | Promedio SETFX | TRM del día |\n"
            "|---:|---:|---:|---:|\n"
            "| $3.080,00 | $3.033,33 | $3.062,97 | $3.053,48 |\n"
        )
        blocks = portal._markdown_comment_blocks(content)
        self.assertEqual(blocks[0], ("h2", "Tasas de la jornada"))
        self.assertEqual(blocks[1][0], "table_header")
        self.assertEqual(blocks[2][0], "table_row")
        self.assertEqual(
            [cell.strip() for cell in blocks[1][1].split("│")],
            ["Precio máximo", "Precio mínimo", "Promedio SETFX", "TRM del día"],
        )
        self.assertEqual(
            [cell.strip() for cell in blocks[2][1].split("│")],
            ["$3.080,00", "$3.033,33", "$3.062,97", "$3.053,48"],
        )

        comment = portal.DailyComment(
            date=date(2026, 8, 20),
            path=Path("2026-08-20.md"),
            content=content,
            modified_ts=0,
        )
        self.app._render_daily_comment(comment)
        rendered = self.app.comment_text.get("1.0", "end")

        self.assertEqual(rendered.count("│"), 6)
        self.assertNotIn("\t", rendered)
        self.assertNotIn("|---|", rendered)
        header_index = self.app.comment_text.search("Precio máximo", "1.0")
        row_index = self.app.comment_text.search("$3.080,00", "1.0")
        self.assertIn(
            "comment_table_header",
            self.app.comment_text.tag_names(header_index),
        )
        self.assertIn(
            "comment_table_row",
            self.app.comment_text.tag_names(row_index),
        )
        self.assertEqual(
            self.app.comment_text.tag_cget("comment_table_header", "justify"),
            "center",
        )
        self.assertEqual(
            self.app.comment_text.tag_cget("comment_table_row", "justify"),
            "center",
        )

    def test_calendario_admite_fecha_no_habil_publicada_y_rechaza_futura(self) -> None:
        self._select_dashboard_group("Portfolio Position Monitor")
        FixedPortalDateTime.current = RealDateTime(2026, 8, 10, 12, 0)
        relativo_existente = self.app.version_date_map[date(2026, 8, 5)]
        self.app.version_date_map[date(2026, 8, 8)] = relativo_existente
        with mock.patch.object(portal, "datetime", FixedPortalDateTime):
            self.app._select_position_date(date(2026, 8, 8))
        self.assertEqual(self.app.selected_relative, relativo_existente)

        with mock.patch.object(portal, "datetime", FixedPortalDateTime):
            self.app._select_position_date(date(2026, 8, 11))
        self.assertEqual(
            self.app.preview_text_var.get(),
            "La fecha seleccionada aún no está vigente",
        )

        self.assertTrue(portal._is_colombia_business_day(date(2026, 8, 5)))
        self.assertFalse(portal._is_colombia_business_day(date(2026, 8, 7)))

    def test_modo_de_captura_enfoca_solo_grafica_y_tabla(self) -> None:
        html = (
            "<html><head></head><body><div class='app-shell'>"
            "<header></header><main class='content'>"
            "<section id='posicion_actual' class='section-panel'>"
            "<div class='dashboard-grid'></div></section>"
            "</main></div></body></html>"
        )
        injected = self.app.server._inject_dashboard_tools(html, "dashboard.html")

        self.assertIn("risko-preview-mode", injected)
        self.assertIn('get("risko_preview") === "1"', injected)
        self.assertIn("#posicion_actual > .dashboard-grid", injected)
        self.assertIn(">Actualizar</button>", injected)
        self.assertIn(">Marcar favorita</button>", injected)
        self.assertIn("/api/configurations/favorite", injected)
        self.assertNotIn(">Restaurar</button>", injected)
        self.assertEqual(portal.PREVIEW_RENDER_VERSION, 4)
        self.assertIn("data.favorite_id || data.active_id", injected)
        self.assertIn("restoreConfiguration", injected)

    def test_manifiesto_hace_opcional_el_puente_de_configuraciones(self) -> None:
        self._select_dashboard_group("Liquidez")
        simple = self.app._dashboard_by_relative(self.app.selected_relative)
        self.assertIsNotNone(simple)
        with urlopen(
            self.app.server.dashboard_url(simple.relative), timeout=3
        ) as response:
            simple_html = response.read().decode("utf-8")
        self.assertNotIn("risko-config-shell", simple_html)

        self._select_dashboard_group("Portfolio Position Monitor")
        configurable = self.app._dashboard_by_relative(self.app.selected_relative)
        self.assertIsNotNone(configurable)
        self.assertTrue(configurable.configurations_enabled)
        self.assertEqual(
            configurable.dashboard_id,
            "portfolio-position-monitor",
        )
        with urlopen(
            self.app.server.dashboard_url(configurable.relative), timeout=3
        ) as response:
            configurable_html = response.read().decode("utf-8")
        self.assertIn("risko-config-shell", configurable_html)
        self.assertIn("/api/configurations/save", configurable_html)

    def test_carpeta_sin_manifiesto_se_descubre_por_nombre_y_fecha(self) -> None:
        folder = portal.PUBLISHED_DIR / "Riesgo de Liquidez" / "2026-08-06"
        folder.mkdir(parents=True)
        html_path = folder / "dashboard.html"
        html_path.write_text(
            "<html><head><title>Título interno distinto</title></head><body></body></html>",
            encoding="utf-8",
        )

        dashboard = next(
            item for item in portal._scan_dashboards() if item.path == html_path
        )

        self.assertEqual(dashboard.title, "Riesgo De Liquidez")
        self.assertEqual(portal._position_date(dashboard).date(), date(2026, 8, 6))
        self.assertFalse(dashboard.configurations_enabled)

    def test_vista_previa_usa_solo_la_configuracion_favorita(self) -> None:
        self._select_dashboard_group("Portfolio Position Monitor")
        dashboard = self.app._dashboard_by_relative(self.app.selected_relative)
        self.assertIsNotNone(dashboard)
        portal._write_dashboard_configs(
            self.app.user,
            dashboard.relative,
            {
                "active_id": "activa",
                "favorite_id": "favorita",
                "configurations": [
                    {"id": "activa", "name": "Vista activa", "filters": {"a": ["1"]}},
                    {"id": "favorita", "name": "Vista favorita", "filters": {"a": ["2"]}},
                ],
            },
        )

        firma, nombre = self.app._preview_configuration(dashboard)

        self.assertNotEqual(firma, "default")
        self.assertEqual(nombre, "Vista favorita")

    def test_acciones_abren_el_archivo_correcto_sin_favoritos(self) -> None:
        self._select_dashboard_group("Portfolio Position Monitor")
        self._select_position("05 ago 2026")
        selected_relative = self.app.selected_relative

        with (
            mock.patch.object(
                self.app.server,
                "dashboard_url",
                return_value="http://127.0.0.1/dashboard",
            ) as dashboard_url,
            mock.patch.object(
                portal,
                "_open_dashboard_window",
                return_value=portal.ExternalLaunch(None, False),
            ) as open_window,
            mock.patch.object(portal, "get_current_interface_monitor", return_value=None),
        ):
            self.app.open_button.invoke()

        dashboard_url.assert_called_once_with(selected_relative)
        open_window.assert_called_once()

        self.app.detail_button.invoke()
        self.root.update()
        detail_windows = [
            widget
            for widget in self.root.winfo_children()
            if isinstance(widget, tk.Toplevel)
        ]
        self.assertEqual(len(detail_windows), 1)
        detail_windows[0].destroy()

        self.assertFalse(hasattr(self.app, "favorite_button"))
        self.assertEqual(len(self.app.action_controls), 3)

        self.app.refresh_button.invoke()
        self._wait_until(lambda: not self.app.refreshing)
        self.assertEqual(self.app.selected_relative, selected_relative)

    def test_reproceso_anterior_no_desplaza_la_mayor_fecha_de_posicion(self) -> None:
        self._select_dashboard_group("Portfolio Position Monitor")
        self._select_position("04 ago 2026")
        metadata_path = (
            portal.PUBLISHED_DIR
            / "Portfolio Position Monitor"
            / "2026-08-04"
            / "publicacion.json"
        )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["publicado_en"] = "2026-08-13T18:30:00"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        self.app.refresh_button.invoke()
        self._wait_until(lambda: not self.app.refreshing)

        selected = self.app._dashboard_by_relative(self.app.selected_relative)
        self.assertIsNotNone(selected)
        self.assertEqual(
            portal._position_date(selected).date().isoformat(),
            "2026-08-05",
        )

    def test_dashboard_solicita_ventana_maximizada_aun_sin_monitor(self) -> None:
        browser = Path(self.temp.name) / "browser.exe"
        browser.write_bytes(b"")
        with (
            mock.patch.object(portal, "_browser_candidates", return_value=[browser]),
            mock.patch.object(portal.subprocess, "Popen") as popen,
        ):
            portal._open_dashboard_window("http://127.0.0.1/dashboard", None)

        argumentos = popen.call_args.args[0]
        self.assertIn("--start-maximized", argumentos)

    def test_configuraciones_se_migran_y_guardan_solo_en_local(self) -> None:
        root = Path(self.temp.name)
        local = root / "perfil_local" / "PortalRisko" / "Configuraciones"
        shared = root / "produccion_solo_lectura" / "Configuraciones"
        user = portal.UserIdentity("BANCO", "PRUEBA", "BANCO\\PRUEBA", "BANCO_PRUEBA")
        legacy_user_file = shared / f"{user.safe_key}.json"
        legacy_dashboard_dir = shared / "dashboards" / user.safe_key
        legacy_user_file.parent.mkdir(parents=True)
        legacy_dashboard_dir.mkdir(parents=True)
        legacy_user_file.write_text(
            json.dumps({"favorites": ["dashboard/heredado.html"]}),
            encoding="utf-8",
        )
        legacy_dashboard = legacy_dashboard_dir / "preferencia.json"
        legacy_dashboard.write_text('{"configurations": []}', encoding="utf-8")
        original_user_bytes = legacy_user_file.read_bytes()
        original_dashboard_bytes = legacy_dashboard.read_bytes()

        with (
            mock.patch.object(portal, "CONFIG_DIR", local),
            mock.patch.object(portal, "LEGACY_CONFIG_DIR", shared),
        ):
            loaded = portal._load_config(user)
            self.assertEqual(loaded["favorites"], ["dashboard/heredado.html"])
            destination = portal._config_path(user)
            self.assertTrue(destination.is_file())
            self.assertTrue((portal._dashboard_config_dir(user) / legacy_dashboard.name).is_file())
            loaded["last_selected"] = "dashboard/local.html"
            portal._save_config(destination, loaded)

        self.assertEqual(legacy_user_file.read_bytes(), original_user_bytes)
        self.assertEqual(legacy_dashboard.read_bytes(), original_dashboard_bytes)
        self.assertIn("dashboard/local.html", destination.read_text(encoding="utf-8"))

    def test_launcher_heredado_no_puede_forzar_configuracion_compartida(self) -> None:
        local_app_data = Path(self.temp.name) / "LocalAppData"
        legacy = portal.DEFAULT_PRODUCTION_ROOT / "Configuraciones"
        with mock.patch.dict(
            os.environ,
            {
                "LOCALAPPDATA": str(local_app_data),
                "PORTAL_RISKO_CONFIG_DIR": str(legacy),
            },
            clear=False,
        ):
            resolved = portal._resolved_config_dir()

        self.assertEqual(
            resolved,
            (local_app_data / "PortalRisko" / "Configuraciones").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
