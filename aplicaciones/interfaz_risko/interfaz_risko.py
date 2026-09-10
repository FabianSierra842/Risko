"""Interfaz gráfica profesional para ejecutar y consultar Position Monitor.

Arquitectura (clase ``AppRisko``) organizada en bloques:
    · Construcción visual  -> métodos ``_construir_*``
    · Estilos              -> ``_aplicar_estilos`` + constantes de color
    · Eventos / handlers   -> métodos ``run_*`` (idénticos a la lógica previa)
    · Actualización datos  -> ``_cargar_datos`` / ``_render_tabla`` / ``_actualizar_kpis``

NOTA: La lógica de negocio (servicios, rutas, cálculos) NO se modifica.
Solo cambia la capa de presentación y experiencia de usuario.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import pandas as pd

RAIZ_RISKO = Path(__file__).resolve().parents[2]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from aplicaciones.interfaz_risko.servicios.position_monitor import (
    cargar_posicion_actual,
    cargar_posicion_historica,
    cargar_tabla_db,
    consolidar_posicion,
    ejecutar_intradia_position_monitor,
    ejecutar_producto,
    ejecutar_spot_2_cierre_pruebas,
    ejecutar_todo_position_monitor,
    generar_tablero,
    importar_iniciales_spot_desde_excel,
    listar_tablas_db,
    limpiar_insumos_risko,
    publicar_tablero,
)
from compartido.nucleo_risko import fechas
from compartido.nucleo_risko.archivos import configurar_confirmador_reemplazo
from compartido.nucleo_risko.rutas import (
    CARPETA_DASHY_POR_DEFECTO,
    CARPETA_HERRAMIENTAS,
)

MAX_FILAS_TABLA = 1000

# Ruta de Dashy fija: nunca cambia, se especifica aquí en lugar de pedirla en la UI.
RUTA_DASHY = str(CARPETA_DASHY_POR_DEFECTO)

MESES = (
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)

# ──────────────────────────────────────────────
# PALETA CORPORATIVA
# ──────────────────────────────────────────────
_C_BG = "#EEF2F9"
_C_PANEL = "#FFFFFF"
_C_SIDEBAR = "#0A2040"
_C_SIDEBAR_SECTION = "#152E56"
_C_BTN_PRIMARY = "#1A56B8"
_C_BTN_HOVER = "#2970D9"
_C_BTN_SECONDARY = "#243A60"
_C_BTN_SECONDARY_HOVER = "#2F4E7E"
_C_BTN_SUCCESS = "#0A6B38"
_C_BTN_SUCCESS_HOVER = "#0E8F4C"
_C_BTN_DANGER = "#8C1515"
_C_BTN_DANGER_HOVER = "#B01C1C"
_C_TEXT_SIDEBAR = "#E8EEFA"
_C_TEXT_LABEL = "#9AAAC8"
_C_TEXT_VALUE = "#FFFFFF"
_C_BORDER = "#D2DCF0"
_C_SCROLL = "#2A4570"
_C_INK = "#1A2E50"
_C_MUTED = "#8090B0"
_C_ERROR = "#D9534F"
_C_SUCCESS = "#2E9E5B"
_C_WARNING = "#D4860A"

# Tabla
_C_FILA_PAR = "#F6F9FF"
_C_FILA_IMPAR = "#FFFFFF"
_C_FILA_CVA = "#FFF8EE"
_C_FILA_IFRS = "#F0F8FF"
_C_VAL_POS = "#1E7A46"
_C_VAL_NEG = "#C0392B"
_C_VAL_NEU = _C_INK

# Log estilo consola
_C_LOG_BG = "#0C1A30"
_C_LOG_TS = "#6A82AA"
_C_LOG_MSG = "#C8D6F0"

COLS_NUMERICAS = ("POSICION", "POSICION_COP", "POSICION_USD", "TRM")


# ══════════════════════════════════════════════════════════════════════
# CARGA DE LOGOS
# ══════════════════════════════════════════════════════════════════════
def _cargar_png(ruta: Path, alto: int) -> ctk.CTkImage | None:
    """Carga un PNG existente y lo escala a la altura indicada."""
    try:
        from PIL import Image
        img = Image.open(ruta).convert("RGBA")
        if img.height <= 0:
            return None
        ancho = max(1, round(alto * img.width / img.height))
        img = img.resize((ancho, alto), Image.LANCZOS)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(ancho, alto))
    except Exception:
        return None


def _intentar_cargar_escudo(alto: int = 22) -> ctk.CTkImage | None:
    """Carga el escudo/logo del banco para el pie del sidebar."""
    for nombre in ("escudo.png", "logo-banco.png"):
        ruta = CARPETA_HERRAMIENTAS / "dashy" / nombre
        if ruta.exists():
            img = _cargar_png(ruta, alto)
            if img is not None:
                return img
    return None


def _intentar_cargar_logo_risko(alto: int = 46) -> ctk.CTkImage | None:
    """Carga el logo de Risko (SVG) escalado, con caché PNG por altura."""
    ruta_svg = CARPETA_HERRAMIENTAS / "dashy" / "LOGO RISKO.svg"
    ruta_png_cache = CARPETA_HERRAMIENTAS / "dashy" / f"logo-risko-{alto}.png"

    if not ruta_svg.exists():
        return None

    if ruta_png_cache.exists():
        img = _cargar_png(ruta_png_cache, alto)
        if img is not None:
            return img

    def _guardar_cache(img_pil):
        try:
            img_pil.save(str(ruta_png_cache))
        except Exception:
            pass

    # Conversión vía svglib (Python puro, sin Cairo)
    try:
        import io
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        from PIL import Image

        drawing = svg2rlg(str(ruta_svg))
        if drawing and drawing.width > 0 and drawing.height > 0:
            png_buf = io.BytesIO()
            renderPM.drawToFile(drawing, png_buf, fmt="PNG")
            png_buf.seek(0)
            img = Image.open(png_buf).convert("RGBA")
            target_w = max(alto, round(alto * drawing.width / drawing.height))
            img = img.resize((target_w, alto), Image.LANCZOS)
            # Fondo blanco -> transparente (luce limpio sobre la cápsula blanca)
            img.putdata([
                (r, g, b, 0) if r > 245 and g > 245 and b > 245 else (r, g, b, a)
                for r, g, b, a in img.getdata()
            ])
            _guardar_cache(img)
            return ctk.CTkImage(light_image=img, dark_image=img, size=(target_w, alto))
    except Exception:
        pass

    # Fallback: cairosvg
    try:
        import io
        import cairosvg
        from PIL import Image
        png_bytes = cairosvg.svg2png(url=str(ruta_svg), output_height=alto)
        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        w, h = img.size
        _guardar_cache(img)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
    except Exception:
        pass

    return None


def _fmt_miles(num: float) -> str:
    """Formato con separador de miles estilo es-CO (1.234.567)."""
    return f"{num:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_compacto(num: float) -> str:
    """Abrevia magnitudes grandes: 1.234.567 -> 1.2 M."""
    signo = "-" if num < 0 else ""
    n = abs(num)
    if n >= 1e9:
        return f"{signo}{n / 1e9:.1f} B"
    if n >= 1e6:
        return f"{signo}{n / 1e6:.1f} M"
    if n >= 1e3:
        return f"{signo}{n / 1e3:.1f} K"
    return f"{signo}{n:.0f}"


# ══════════════════════════════════════════════════════════════════════
# APLICACIÓN
# ══════════════════════════════════════════════════════════════════════
class AppRisko:
    def __init__(self) -> None:
        # --- Estado de datos (presentación) ---
        self.df_completo: pd.DataFrame | None = None   # datos cargados (ya filtrados por fecha)
        self.columnas: list[str] = []
        self.col_visibles: dict[str, bool] = {}
        self.botones_proceso: list[ctk.CTkButton] = []
        # Filtros avanzados (presentación; no alteran los datos originales)
        self.filtros: dict[str, set[str]] = {}          # columna -> valores permitidos
        self.filtro_pos_min: float | None = None
        self.filtro_pos_max: float | None = None
        # Ejecución en segundo plano (la interfaz no se congela)
        self._ejecutando = False
        self._cola_log: "queue.Queue[tuple[str, str, str]]" = queue.Queue()
        self._cola_resultados: "queue.Queue" = queue.Queue()

        ctk.set_appearance_mode("light")
        self.root = ctk.CTk()
        self.root.title("RISKO — Position Monitor")
        self._configurar_geometria()
        self.root.configure(fg_color=_C_BG)
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.var_tabla_db = ctk.StringVar(value="")
        self.usar_db_pruebas = tk.BooleanVar(value=False)

        self.fecha_inicial = fechas.Calcula_Fecha()

        # --- Construcción de la interfaz ---
        self._aplicar_estilos()
        self._construir_sidebar()
        self._construir_contenido()

        # La capa de datos no debe abrir diálogos modales propios: cuando una fecha
        # ya existe, registramos en el log y reemplazamos (re-ejecutar lo pretende).
        configurar_confirmador_reemplazo(self._confirmar_reemplazo_datos)

        # Sondeos en el hilo principal: log y resultados de los hilos de trabajo
        self.root.after(150, self._drenar_log)
        self.root.after(120, self._drenar_resultados)

        # --- Mensajes iniciales ---
        self._escribir_log("Sistema RISKO iniciado. Seleccione una fecha y ejecute los módulos.")
        self._escribir_log(f"Fecha por defecto: {self.fecha_inicial}")
        self._actualizar_kpis(None)
        self._set_chip("Sin datos", "idle")

        if fechas.Es_Primer_Dia_Habil_Mes(date.today()):
            self.root.after(400, lambda: messagebox.showwarning(
                "RISKO — Históricos",
                "Hoy es el primer día hábil del mes.\n"
                "Recuerde verificar que el cierre del mes anterior se haya consolidado en el histórico.",
            ))

    def run(self) -> None:
        self.root.mainloop()

    # ──────────────────────────────────────────────
    # GEOMETRÍA RESPONSIVA (se ajusta a la pantalla, incl. portátiles)
    # ──────────────────────────────────────────────
    def _configurar_geometria(self) -> None:
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        ancho = min(1360, sw - 80)
        alto = min(820, sh - 120)
        x = max(0, (sw - ancho) // 2)
        y = max(0, (sh - alto) // 3)
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")
        self.root.minsize(900, 560)

    # ──────────────────────────────────────────────
    # ESTILOS DE LA TABLA (ttk)
    # ──────────────────────────────────────────────
    def _aplicar_estilos(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Risko.Treeview",
            background=_C_PANEL, foreground=_C_INK,
            fieldbackground=_C_PANEL, rowheight=25,
            font=("Consolas", 10), borderwidth=0,
        )
        style.configure(
            "Risko.Treeview.Heading",
            background="#E7EDF8", foreground=_C_INK,
            font=("Segoe UI Semibold", 9), relief="flat", padding=(6, 5),
        )
        style.map(
            "Risko.Treeview.Heading",
            background=[("active", "#D8E2F5")],
        )
        # Selección: fondo suave; NO mapeamos foreground para conservar verde/rojo por signo.
        style.map(
            "Risko.Treeview",
            background=[("selected", "#CBDBF8")],
        )

    # ══════════════════════════════════════════════
    # 1. SIDEBAR
    # ══════════════════════════════════════════════
    def _construir_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self.root, width=276, fg_color=_C_SIDEBAR, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(1, weight=1)  # el cuerpo con scroll absorbe el espacio

        # --- Cabecera: logo RISKO sobre cápsula blanca ---
        cabecera = ctk.CTkFrame(sidebar, fg_color=_C_SIDEBAR_SECTION, corner_radius=0, height=116)
        cabecera.grid(row=0, column=0, sticky="ew")
        cabecera.grid_propagate(False)
        cabecera.grid_columnconfigure(0, weight=1)

        capsula = ctk.CTkFrame(cabecera, fg_color="#FFFFFF", corner_radius=12)
        capsula.grid(row=0, column=0, pady=(18, 4))
        logo = _intentar_cargar_logo_risko(44)
        if logo:
            ctk.CTkLabel(capsula, image=logo, text="", fg_color="transparent").grid(
                row=0, column=0, padx=18, pady=8)
        else:
            ctk.CTkLabel(
                capsula, text="RISKO", text_color=_C_SIDEBAR,
                font=ctk.CTkFont(size=26, weight="bold"),
            ).grid(row=0, column=0, padx=22, pady=8)
        ctk.CTkLabel(
            cabecera, text="POSITION MONITOR",
            text_color=_C_TEXT_LABEL, font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=1, column=0, pady=(0, 12))

        # --- Cuerpo con scroll (fecha + botones; nunca se ocultan en portátiles) ---
        panel = ctk.CTkScrollableFrame(
            sidebar, fg_color=_C_SIDEBAR, corner_radius=0,
            scrollbar_button_color=_C_SCROLL, scrollbar_button_hover_color=_C_BTN_SECONDARY_HOVER,
        )
        panel.grid(row=1, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        self._panel = panel
        self._fila_panel = 0

        # Fecha de corte
        self._label_section("FECHA DE CORTE")
        marco_fecha = ctk.CTkFrame(panel, fg_color="transparent")
        marco_fecha.grid(row=self._sig(), column=0, sticky="ew", padx=14, pady=(0, 4))
        marco_fecha.grid_columnconfigure(0, weight=1)
        self.entrada_fecha = ctk.CTkEntry(
            marco_fecha, height=34, fg_color="#152E56", text_color=_C_TEXT_VALUE,
            border_color="#2A4570", border_width=1, font=ctk.CTkFont(size=13),
        )
        self.entrada_fecha.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.entrada_fecha.insert(0, self.fecha_inicial)
        ctk.CTkButton(
            marco_fecha, text="📅", width=38, height=34,
            fg_color=_C_BTN_SECONDARY, hover_color=_C_BTN_SECONDARY_HOVER,
            font=ctk.CTkFont(size=14), command=self.abrir_calendario,
        ).grid(row=0, column=1, sticky="e")

        # Acciones principales
        self._separador()
        self._label_section("ACCIONES PRINCIPALES")
        self._crear_boton("▶   Ejecutar cierre", self.run_todo, _C_BTN_SUCCESS, _C_BTN_SUCCESS_HOVER)
        self._crear_boton(
            "⚠   Ejecutar intradía",
            self.run_intradia,
            _C_WARNING,
            "#D97706",
        )
        self._crear_boton("🗑   Limpiar insumos", self.run_limpiar, _C_BTN_DANGER, _C_BTN_DANGER_HOVER)

        # Módulos individuales
        self._separador()
        self._label_section("MÓDULOS INDIVIDUALES")
        for prod in (
            "Spot",
            "Novados",
            "Forward",
            "Opciones",
            "Swaps",
            "Renta Fija",
            # Deshabilitados temporalmente en la interfaz y en Ejecutar todo.
            # Antes de reactivarlos deben validarse y ajustarse al nuevo formato
            # definido para Position Monitor y al alcance vigente del portal:
            # "Cubrebonos",
            # "NDFTES",
            # "PP",
        ):
            clave = prod.upper().replace(" ", "_")
            self._crear_boton_producto(
                prod,
                lambda p=clave: self.run_producto(p),
                lambda p=clave: self._abrir_configuracion_producto(p),
            )

        # Consolidación y tablero (después de las posiciones individuales)
        self._separador()
        self._label_section("CONSOLIDACIÓN Y TABLERO")
        self._crear_boton("⚡   Consolidar posición", self.run_consolidar)
        self._crear_boton("📊   Generar tablero", self.run_tablero,
                          _C_BTN_SECONDARY, _C_BTN_SECONDARY_HOVER)
        self._crear_boton("☁   Publicar en portal", self.run_publicar_tablero,
                          _C_BTN_SUCCESS, _C_BTN_SUCCESS_HOVER)

        # Proyecto independiente: abre su propia interfaz y no altera ningun
        # proceso, tabla ni publicacion de Position Monitor.
        self._separador()
        self._label_section("PYG")
        self._crear_boton("◈   Abrir PyG", self.run_abrir_pyg,
                          _C_BTN_PRIMARY, _C_BTN_HOVER)

        # Gestión
        self._separador()
        self._label_section("GESTIÓN")
        self._crear_boton("📋   Ver históricos", self.run_historicos,
                          _C_BTN_SECONDARY, _C_BTN_SECONDARY_HOVER)
        self._crear_boton("🧹   Limpiar tabla", self._limpiar_vista,
                          _C_BTN_SECONDARY, _C_BTN_SECONDARY_HOVER)

        # --- Pie: estado + escudo/versión ---
        pie = ctk.CTkFrame(sidebar, fg_color=_C_SIDEBAR_SECTION, corner_radius=0)
        pie.grid(row=2, column=0, sticky="ew")
        pie.grid_columnconfigure(0, weight=1)
        pie.grid_columnconfigure(1, weight=0)
        self.lbl_estado = ctk.CTkLabel(
            pie, text="● Listo para ejecutar", text_color=_C_SUCCESS,
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
            wraplength=244, justify="left",
        )
        self.lbl_estado.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(10, 4))
        escudo = _intentar_cargar_escudo(22)
        if escudo:
            ctk.CTkLabel(pie, image=escudo, text="", fg_color="transparent").grid(
                row=1, column=0, sticky="w", padx=(16, 0), pady=(0, 12))
        ctk.CTkLabel(
            pie, text="v1.2  ·  Riesgo de Mercado", text_color="#6A82AA",
            font=ctk.CTkFont(size=9), anchor="e",
        ).grid(row=1, column=1, sticky="e", padx=16, pady=(0, 12))

    # Helpers de layout del sidebar -----------------------------------
    def _sig(self) -> int:
        f = self._fila_panel
        self._fila_panel += 1
        return f

    def _label_section(self, texto: str) -> None:
        ctk.CTkLabel(
            self._panel, text=texto, text_color=_C_TEXT_LABEL,
            font=ctk.CTkFont(size=10, weight="bold"), anchor="w",
        ).grid(row=self._sig(), column=0, sticky="ew", padx=18, pady=(16, 3))

    def _separador(self) -> None:
        ctk.CTkFrame(self._panel, height=1, fg_color=_C_BTN_SECONDARY, corner_radius=0).grid(
            row=self._sig(), column=0, sticky="ew", padx=16, pady=(6, 0))

    def _crear_boton(self, texto, comando, color=_C_BTN_PRIMARY, hover=_C_BTN_HOVER) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            self._panel, text=texto, fg_color=color, hover_color=hover,
            text_color="white", height=34, anchor="w",
            font=ctk.CTkFont(size=12), corner_radius=6, command=comando,
        )
        btn.grid(row=self._sig(), column=0, sticky="ew", padx=14, pady=(0, 5))
        self.botones_proceso.append(btn)
        return btn

    def _crear_boton_producto(self, texto, comando, configurar) -> None:
        """Crea una acción de posición con acceso lateral a procesos adicionales."""
        fila = ctk.CTkFrame(self._panel, fg_color="transparent")
        fila.grid(row=self._sig(), column=0, sticky="ew", padx=14, pady=(0, 5))
        fila.grid_columnconfigure(0, weight=1)

        btn_posicion = ctk.CTkButton(
            fila,
            text=texto,
            fg_color=_C_BTN_SECONDARY,
            hover_color=_C_BTN_SECONDARY_HOVER,
            text_color="white",
            height=34,
            anchor="w",
            font=ctk.CTkFont(size=12),
            corner_radius=6,
            command=comando,
        )
        btn_posicion.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        btn_config = ctk.CTkButton(
            fila,
            text="⚙",
            width=36,
            height=34,
            fg_color="#344E75",
            hover_color=_C_BTN_HOVER,
            text_color="white",
            font=ctk.CTkFont(size=16),
            corner_radius=6,
            command=configurar,
        )
        btn_config.grid(row=0, column=1, sticky="e")
        self.botones_proceso.extend((btn_posicion, btn_config))

    def _acciones_configuracion_producto(self, producto: str):
        """Punto extensible para registrar procesos adicionales por posición."""
        if producto == "SPOT":
            return [
                (
                    "Cargar / recalcular Spot acumulado",
                    "Importa las posiciones iniciales parametrizadas y recalcula "
                    "el histórico acumulado posterior.",
                    self.run_importar_iniciales_spot,
                ),
                (
                    "Probar Spot 2 · cierre",
                    "Procesa SPOT_CLIENTE con el reporte de Caja de cierre en "
                    "una base dedicada. No usa insumos intradía.",
                    self.run_spot_2_cierre_pruebas,
                ),
            ]
        return []

    def _abrir_configuracion_producto(self, producto: str) -> None:
        acciones = self._acciones_configuracion_producto(producto)
        nombre = producto.replace("_", " ").title()
        if not acciones:
            messagebox.showinfo(
                f"RISKO — Configuración de {nombre}",
                "No hay procesos adicionales configurados para esta posición.",
            )
            return

        vent = ctk.CTkToplevel(self.root)
        vent.title(f"RISKO — Configuración de {nombre}")
        alto = 130 + (82 * len(acciones))
        vent.geometry(f"440x{alto}")
        vent.resizable(False, False)
        vent.transient(self.root)
        vent.configure(fg_color=_C_PANEL)
        vent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            vent,
            text=f"Procesos adicionales · {nombre}",
            text_color=_C_INK,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=22, pady=(20, 8))

        for fila, (etiqueta, descripcion, accion) in enumerate(acciones, start=1):
            tarjeta = ctk.CTkFrame(
                vent,
                fg_color="#F4F7FC",
                border_width=1,
                border_color=_C_BORDER,
                corner_radius=8,
            )
            tarjeta.grid(row=fila, column=0, sticky="ew", padx=22, pady=6)
            tarjeta.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                tarjeta,
                text=descripcion,
                text_color=_C_MUTED,
                font=ctk.CTkFont(size=10),
                justify="left",
                wraplength=260,
                anchor="w",
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=10)

            def ejecutar_y_cerrar(comando=accion):
                vent.destroy()
                comando()

            ctk.CTkButton(
                tarjeta,
                text=etiqueta,
                width=150,
                height=34,
                fg_color=_C_BTN_PRIMARY,
                hover_color=_C_BTN_HOVER,
                command=ejecutar_y_cerrar,
            ).grid(row=0, column=1, padx=12, pady=10)

        vent.after(50, vent.focus_force)

    # ══════════════════════════════════════════════
    # PANEL DERECHO: header + KPIs + tabla + log
    # ══════════════════════════════════════════════
    def _construir_contenido(self) -> None:
        cont = ctk.CTkFrame(self.root, fg_color=_C_BG, corner_radius=0)
        cont.grid(row=0, column=1, sticky="nsew")
        cont.grid_columnconfigure(0, weight=1)
        cont.grid_rowconfigure(2, weight=4)  # tabla (prioriza el resultado del procesamiento)
        cont.grid_rowconfigure(3, weight=2)  # log

        self._construir_header(cont)
        self._construir_kpis(cont)
        self._construir_tabla(cont)
        self._construir_log(cont)

    # --- 2. Header --------------------------------------------------
    def _construir_header(self, parent) -> None:
        barra = ctk.CTkFrame(parent, fg_color=_C_PANEL, corner_radius=0, height=66)
        barra.grid(row=0, column=0, sticky="ew")
        barra.grid_propagate(False)
        barra.grid_columnconfigure(0, weight=1)
        izq = ctk.CTkFrame(barra, fg_color="transparent")
        izq.grid(row=0, column=0, sticky="w", padx=20, pady=8)
        ctk.CTkLabel(
            izq, text="Position Monitor  /  Consolidación",
            text_color=_C_MUTED, font=ctk.CTkFont(size=10), anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            izq, text="Posición Consolidada de Portafolio",
            text_color=_C_INK, font=ctk.CTkFont(size=17, weight="bold"), anchor="w",
        ).grid(row=1, column=0, sticky="w")
        ctk.CTkLabel(
            barra, text="Jefatura de Riesgo de Mercado — Banco de Bogotá",
            text_color=_C_MUTED, font=ctk.CTkFont(size=11), anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=20)

    # --- 3. Tarjetas KPI -------------------------------------------
    def _construir_kpis(self, parent) -> None:
        fila = ctk.CTkFrame(parent, fg_color="transparent")
        fila.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 2))
        for i in range(4):
            fila.grid_columnconfigure(i, weight=1, uniform="kpi")

        self.kpi_registros, _ = self._tarjeta_kpi(fila, 0, "REGISTROS CARGADOS", _C_BTN_PRIMARY)
        self.kpi_exposicion, self.kpi_exposicion_sub = self._tarjeta_kpi(fila, 1, "EXPOSICIÓN NETA", _C_VAL_NEG)
        self.kpi_moneda, _ = self._tarjeta_kpi(fila, 2, "MONEDA PRINCIPAL", _C_SUCCESS)
        self.kpi_ejecucion, self.kpi_ejecucion_sub = self._tarjeta_kpi(fila, 3, "ÚLTIMA EJECUCIÓN", _C_WARNING)

    def _tarjeta_kpi(self, parent, col, titulo, color_acento):
        # La tarjeta se ajusta a su contenido (sin altura fija que recorte el valor),
        # con fuentes/paddings compactos para que quede baja pero totalmente legible.
        card = ctk.CTkFrame(parent, fg_color=_C_PANEL, corner_radius=10)
        card.grid(row=0, column=col, sticky="ew", padx=5)
        card.grid_columnconfigure(1, weight=1)
        # Acento de color a la izquierda (height=1 para no imponer el alto por
        # defecto de CTkFrame, 200px; se estira al alto real con sticky="ns")
        ctk.CTkFrame(card, fg_color=color_acento, corner_radius=10, width=4, height=1).grid(
            row=0, column=0, rowspan=2, sticky="ns", padx=(6, 0), pady=8)
        ctk.CTkLabel(
            card, text=titulo, text_color=_C_MUTED,
            font=ctk.CTkFont(size=9, weight="bold"), anchor="w",
        ).grid(row=0, column=1, columnspan=2, sticky="w", padx=10, pady=(8, 0))
        val = ctk.CTkLabel(
            card, text="--", text_color=_C_INK,
            font=ctk.CTkFont(size=18, weight="bold"), anchor="w",
        )
        val.grid(row=1, column=1, sticky="w", padx=10, pady=(0, 8))
        sub = ctk.CTkLabel(
            card, text="", text_color=_C_MUTED,
            font=ctk.CTkFont(size=9), anchor="e",
        )
        sub.grid(row=1, column=2, sticky="e", padx=(0, 10), pady=(0, 9))
        return val, sub

    # --- 4 y 5. Toolbar + Tabla ------------------------------------
    def _construir_tabla(self, parent) -> None:
        marco = ctk.CTkFrame(parent, fg_color=_C_PANEL, corner_radius=10)
        marco.grid(row=2, column=0, sticky="nsew", padx=14, pady=(6, 6))
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(3, weight=1)

        # --- Barra de herramientas ---
        tb = ctk.CTkFrame(marco, fg_color="transparent")
        tb.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        tb.grid_columnconfigure(0, weight=1)

        self.var_busqueda = ctk.StringVar()
        self.var_busqueda.trace_add("write", lambda *_: self._filtrar_y_render())
        ctk.CTkEntry(
            tb, textvariable=self.var_busqueda, height=32,
            placeholder_text="Buscar en resultados…",
            fg_color="#F4F7FC", border_color=_C_BORDER, border_width=1,
            text_color=_C_INK, font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        def _tb_btn(col, texto, cmd, ancho=96, destacado=False):
            b = ctk.CTkButton(
                tb, text=texto, width=ancho, height=32, command=cmd,
                fg_color=_C_BTN_PRIMARY if destacado else "#E7EDF8",
                hover_color=_C_BTN_HOVER if destacado else "#D8E2F5",
                text_color="white" if destacado else _C_INK,
                font=ctk.CTkFont(size=12), corner_radius=6,
            )
            b.grid(row=0, column=col, padx=3)
            return b

        self.btn_filtros = _tb_btn(1, "Filtros", self._abrir_filtros, 88)
        _tb_btn(2, "Columnas", self._abrir_columnas, 92)
        _tb_btn(3, "Exportar", self._exportar, 92)
        _tb_btn(4, "↻ Actualizar", self.run_actualizar, 110, destacado=True)

        # Chip de estado — ancho fijo para que NO reacomode los botones al actualizarse
        self.chip = ctk.CTkLabel(
            tb, text="●  Sin datos", width=150, height=30, corner_radius=15,
            fg_color="#E7EDF8", text_color=_C_MUTED, anchor="center",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.chip.grid(row=0, column=5, padx=(8, 0))
        self.chip.grid_propagate(False)

        fila_db = ctk.CTkFrame(marco, fg_color="transparent")
        fila_db.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        fila_db.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            fila_db, text="Tabla DB", text_color=_C_MUTED,
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(2, 8))
        self.selector_tabla_db = ctk.CTkOptionMenu(
            fila_db,
            variable=self.var_tabla_db,
            values=["Sin tablas"],
            height=30,
            fg_color="#F4F7FC",
            button_color=_C_BTN_SECONDARY,
            button_hover_color=_C_BTN_SECONDARY_HOVER,
            text_color=_C_INK,
            dropdown_fg_color="#FFFFFF",
            dropdown_text_color=_C_INK,
        )
        self.selector_tabla_db.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            fila_db, text="Cargar", width=78, height=30,
            fg_color=_C_BTN_PRIMARY, hover_color=_C_BTN_HOVER,
            command=self.run_cargar_tabla_db,
        ).grid(row=0, column=2, padx=3)
        ctk.CTkButton(
            fila_db, text="Listar", width=70, height=30,
            fg_color="#E7EDF8", hover_color="#D8E2F5", text_color=_C_INK,
            command=self._actualizar_lista_tablas_db,
        ).grid(row=0, column=3, padx=3)
        ctk.CTkSwitch(
            fila_db, text="Pruebas", variable=self.usar_db_pruebas,
            command=self._actualizar_lista_tablas_db, text_color=_C_MUTED,
            font=ctk.CTkFont(size=11), progress_color=_C_BTN_PRIMARY,
        ).grid(row=0, column=4, padx=(8, 2))
        self.root.after(300, self._actualizar_lista_tablas_db)

        ctk.CTkLabel(
            marco, text="Resultado del procesamiento", text_color=_C_INK,
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=14, pady=(2, 4))

        # --- Treeview ---
        cont_tree = tk.Frame(marco, bg=_C_BORDER)
        cont_tree.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 4))
        cont_tree.grid_columnconfigure(0, weight=1)
        cont_tree.grid_rowconfigure(0, weight=1)

        self.tabla = ttk.Treeview(cont_tree, show="headings", style="Risko.Treeview")
        sb_y = ttk.Scrollbar(cont_tree, orient="vertical", command=self.tabla.yview)
        sb_x = ttk.Scrollbar(cont_tree, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")
        sb_x.grid(row=1, column=0, sticky="ew")

        # Tags de FONDO (zebra + clasificación) -- solo configuran 'background'
        self.tabla.tag_configure("fila_par", background=_C_FILA_PAR)
        self.tabla.tag_configure("fila_impar", background=_C_FILA_IMPAR)
        self.tabla.tag_configure("fila_cva", background=_C_FILA_CVA)
        self.tabla.tag_configure("fila_ifrs", background=_C_FILA_IFRS)
        # Tags de TEXTO por signo de POSICION -- solo configuran 'foreground'.
        # ttk.Treeview no permite color por celda; se colorea la fila según el signo.
        self.tabla.tag_configure("val_pos", foreground=_C_VAL_POS)
        self.tabla.tag_configure("val_neg", foreground=_C_VAL_NEG)
        self.tabla.tag_configure("val_neu", foreground=_C_VAL_NEU)

        self.lbl_conteo = ctk.CTkLabel(
            marco, text="", text_color=_C_MUTED, font=ctk.CTkFont(size=10), anchor="e",
        )
        self.lbl_conteo.grid(row=4, column=0, sticky="e", padx=14, pady=(0, 8))

    # --- 6. Log estilo consola -------------------------------------
    def _construir_log(self, parent) -> None:
        marco = ctk.CTkFrame(parent, fg_color=_C_PANEL, corner_radius=10)
        marco.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 10))
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(1, weight=1)

        cab = ctk.CTkFrame(marco, fg_color="transparent")
        cab.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        cab.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            cab, text="Log de ejecución", text_color=_C_INK,
            font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")

        def _log_btn(col, texto, cmd):
            ctk.CTkButton(
                cab, text=texto, width=80, height=26, command=cmd,
                fg_color="#E7EDF8", hover_color="#D8E2F5", text_color=_C_INK,
                font=ctk.CTkFont(size=11), corner_radius=6,
            ).grid(row=0, column=col, padx=3)

        _log_btn(1, "Limpiar", self._limpiar_log)
        _log_btn(2, "Exportar", self._exportar_log)
        _log_btn(3, "Expandir", self._expandir_log)

        self.log = ctk.CTkTextbox(
            marco, wrap="word", font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=_C_LOG_BG, text_color=_C_LOG_MSG, border_width=0,
        )
        self.log.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.log.tag_config("ts", foreground=_C_LOG_TS)
        self.log.tag_config("info", foreground=_C_SUCCESS)
        self.log.tag_config("warn", foreground=_C_WARNING)
        self.log.tag_config("error", foreground="#FF6B6B")
        self.log.tag_config("msg", foreground=_C_LOG_MSG)
        self.log.configure(state="disabled")

    def _actualizar_lista_tablas_db(self) -> None:
        try:
            tablas = listar_tablas_db(pruebas=self.usar_db_pruebas.get())
        except Exception as exc:
            self._escribir_log(f"No se pudo listar la base de datos: {exc}", "ERROR")
            tablas = []

        valores = tablas or ["Sin tablas"]
        self.selector_tabla_db.configure(values=valores)
        seleccion = self.var_tabla_db.get()
        if seleccion not in valores:
            preferida = "tbl_posicion_actual" if "tbl_posicion_actual" in valores else valores[0]
            self.var_tabla_db.set(preferida)

        nombre_db = "risko_pruebas.db" if self.usar_db_pruebas.get() else "risko.db"
        self._escribir_log(f"Tablas disponibles en {nombre_db}: {len(tablas)}.")

    def run_cargar_tabla_db(self) -> None:
        nombre_tabla = self.var_tabla_db.get().strip()
        if not nombre_tabla or nombre_tabla == "Sin tablas":
            messagebox.showinfo("RISKO", "No hay tablas disponibles en la base seleccionada.")
            return

        usar_pruebas = self.usar_db_pruebas.get()
        fecha = self.entrada_fecha.get()

        def trabajo():
            return cargar_tabla_db(nombre_tabla, pruebas=usar_pruebas, fecha_trabajo=fecha)

        def al_terminar(df):
            self._cargar_datos(self._filtrar_por_fecha(df))
            self._set_estado(f"● Tabla cargada desde DB: {nombre_tabla}.", _C_SUCCESS)
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")
            self._escribir_log(f"Tabla DB cargada: {nombre_tabla} ({len(df)} registros).")

        self._ejecutar_en_hilo(f"Cargar {nombre_tabla}", trabajo, al_terminar)

    # ══════════════════════════════════════════════
    # LOG
    # ══════════════════════════════════════════════
    def _nivel_de(self, mensaje: str, nivel: str) -> str:
        """Detecta el nivel a partir del texto cuando el servicio no lo indica."""
        if nivel != "INFO":
            return nivel
        m = mensaje.upper()
        if m.startswith("ERROR") or "ERROR:" in m:
            return "ERROR"
        if "ADVERT" in m or "WARN" in m or "NO SE" in m:
            return "WARN"
        return "INFO"

    def _escribir_log(self, mensaje: str, nivel: str = "INFO") -> None:
        """Thread-safe: encola el mensaje; el volcado al widget lo hace _drenar_log
        en el hilo principal. Así puede llamarse desde los hilos de trabajo."""
        nivel = self._nivel_de(mensaje, nivel)
        hora = datetime.now().strftime("%H:%M:%S")
        self._cola_log.put((hora, nivel, mensaje))

    def _drenar_log(self) -> None:
        """Vuelca al textbox los mensajes encolados (corre en el hilo principal)."""
        pendientes = []
        try:
            while True:
                pendientes.append(self._cola_log.get_nowait())
        except queue.Empty:
            pass
        if pendientes:
            tags = {"INFO": "info", "WARN": "warn", "ERROR": "error"}
            self.log.configure(state="normal")
            for hora, nivel, mensaje in pendientes:
                self.log.insert("end", f"[{hora}] ", "ts")
                self.log.insert("end", f"{nivel:<5} ", tags[nivel])
                self.log.insert("end", f"{mensaje}\n", "msg")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(150, self._drenar_log)

    def _confirmar_reemplazo_datos(self, titulo: str, mensaje: str) -> bool:
        """Confirmador sin GUI para la capa de datos: registra y reemplaza.

        Evita que se abran diálogos modales de tkinter desde el procesamiento
        (que congelaban/cerraban la app al re-ejecutar una fecha ya existente).
        """
        self._escribir_log(
            "La fecha de corte ya existía en el archivo de salida: se reemplazan los datos.",
            "WARN",
        )
        return True

    def _limpiar_log(self) -> None:
        # Vacía también la cola para que no reaparezcan líneas de una ejecución previa
        try:
            while True:
                self._cola_log.get_nowait()
        except queue.Empty:
            pass
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _exportar_log(self) -> None:
        contenido = self.log.get("1.0", "end").strip()
        if not contenido:
            messagebox.showinfo("RISKO", "El log está vacío.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Exportar log", defaultextension=".log",
            filetypes=[("Log", "*.log"), ("Texto", "*.txt")],
            initialfile=f"risko_log_{datetime.now():%Y%m%d_%H%M%S}.log",
        )
        if ruta:
            Path(ruta).write_text(contenido, encoding="utf-8")
            self._escribir_log(f"Log exportado: {ruta}")

    def _expandir_log(self) -> None:
        vent = ctk.CTkToplevel(self.root)
        vent.title("RISKO — Log de ejecución")
        vent.geometry("900x600")
        vent.transient(self.root)
        vent.configure(fg_color=_C_LOG_BG)
        caja = ctk.CTkTextbox(
            vent, wrap="word", font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=_C_LOG_BG, text_color=_C_LOG_MSG, border_width=0,
        )
        caja.pack(fill="both", expand=True, padx=10, pady=10)
        caja.insert("1.0", self.log.get("1.0", "end"))
        caja.configure(state="disabled")

    # ══════════════════════════════════════════════
    # FECHA / ESTADO / CHIP
    # ══════════════════════════════════════════════
    def _obtener_fecha(self) -> date:
        f = pd.to_datetime(self.entrada_fecha.get(), dayfirst=True, errors="coerce")
        if pd.isna(f):
            f = pd.to_datetime(self.fecha_inicial, dayfirst=True, errors="coerce")
        return f.date() if not pd.isna(f) else date.today()

    def _set_fecha(self, f: date) -> None:
        self.entrada_fecha.delete(0, "end")
        self.entrada_fecha.insert(0, f.strftime("%d-%m-%Y"))

    def _set_estado(self, texto: str, color: str = _C_TEXT_LABEL) -> None:
        self.lbl_estado.configure(text=texto, text_color=color)
        self.root.update_idletasks()

    def _set_chip(self, texto: str, estado: str = "ok") -> None:
        colores = {
            "ok": ("#DCF3E6", _C_VAL_POS),
            "warn": ("#FCEFD4", _C_WARNING),
            "error": ("#FBE0E0", _C_VAL_NEG),
            "idle": ("#E7EDF8", _C_MUTED),
        }
        bg, fg = colores.get(estado, colores["idle"])
        self.chip.configure(text=f"●  {texto}", fg_color=bg, text_color=fg)

    def _bloquear(self, activar: bool) -> None:
        estado = "disabled" if activar else "normal"
        cursor = "watch" if activar else ""
        for btn in self.botones_proceso:
            btn.configure(state=estado)
        self.root.configure(cursor=cursor)
        self.root.update_idletasks()

    def _filtrar_por_fecha(self, df: pd.DataFrame | None) -> pd.DataFrame | None:
        if df is None or df.empty:
            return df
        fc = self._obtener_fecha()
        for col in ("FECHA", "CORTE"):
            if col in df.columns:
                fechas_df = pd.to_datetime(df[col], dayfirst=True, errors="coerce").dt.date
                filtrado = df.loc[fechas_df == fc]
                if filtrado.empty:
                    self._escribir_log(
                        f"La tabla no tiene registros para la fecha {fc:%d-%m-%Y}.",
                        "WARN",
                    )
                return filtrado.copy()
        return df

    # ══════════════════════════════════════════════
    # DATOS: carga, KPIs, render, búsqueda
    # ══════════════════════════════════════════════
    def _cargar_datos(self, df: pd.DataFrame | None) -> None:
        """Punto único de entrada: fija el dataset, resetea filtros/columnas y pinta."""
        self.df_completo = df if (df is not None and not df.empty) else None
        self.columnas = [str(c) for c in df.columns] if self.df_completo is not None else []
        self.col_visibles = {c: True for c in self.columnas}
        # Reinicia los filtros avanzados al cargar un dataset nuevo
        self.filtros = {}
        self.filtro_pos_min = self.filtro_pos_max = None
        self._refrescar_btn_filtros()
        if hasattr(self, "var_busqueda"):
            self.var_busqueda.set("")  # dispara _filtrar_y_render
        else:
            self._render_tabla(self.df_completo)
        self._actualizar_kpis(self.df_completo)

    def _filtrar_y_render(self) -> None:
        """Aplica filtros avanzados + búsqueda y pinta, sin tocar los datos originales."""
        self._render_tabla(self._df_filtrado())

    def _df_filtrado(self) -> pd.DataFrame | None:
        """Devuelve df_completo tras aplicar filtros avanzados y el texto de búsqueda."""
        df = self.df_completo
        if df is None:
            return None
        # 1) Filtros avanzados por columna (valores permitidos)
        for col, permitidos in self.filtros.items():
            if permitidos and col in df.columns:
                df = df[df[col].astype(str).isin(permitidos)]
        # 2) Rango de POSICION
        if "POSICION" in df.columns and (self.filtro_pos_min is not None or self.filtro_pos_max is not None):
            serie = pd.to_numeric(df["POSICION"], errors="coerce")
            if self.filtro_pos_min is not None:
                df = df[serie >= self.filtro_pos_min]
                serie = serie.loc[df.index]
            if self.filtro_pos_max is not None:
                df = df[serie <= self.filtro_pos_max]
        # 3) Búsqueda de texto sobre el resultado
        txt = self.var_busqueda.get().strip().lower()
        if txt:
            mask = df.apply(
                lambda r: r.astype(str).str.lower().str.contains(txt, regex=False, na=False).any(),
                axis=1,
            )
            df = df.loc[mask]
        return df

    def _filtros_activos(self) -> int:
        """Cuenta cuántos filtros avanzados están aplicados (para el botón)."""
        n = sum(1 for v in self.filtros.values() if v)
        n += 1 if (self.filtro_pos_min is not None or self.filtro_pos_max is not None) else 0
        return n

    def _refrescar_btn_filtros(self) -> None:
        if not hasattr(self, "btn_filtros"):
            return
        n = self._filtros_activos()
        self.btn_filtros.configure(
            text=f"Filtros ({n})" if n else "Filtros",
            fg_color=_C_BTN_PRIMARY if n else "#E7EDF8",
            text_color="white" if n else _C_INK,
        )

    def _render_tabla(self, df: pd.DataFrame | None) -> None:
        # IMPORTANTE: resetear displaycolumns a "#all" ANTES de cambiar 'columns'.
        # Si displaycolumns aún apunta a columnas previas (p. ej. FECHA), asignar
        # 'columns' nuevas o () lanza TclError "Invalid column index" y cerraba la app.
        self.tabla["displaycolumns"] = "#all"
        self.tabla.delete(*self.tabla.get_children())
        if df is None or df.empty:
            self.tabla["columns"] = ()
            self.lbl_conteo.configure(text="" if df is None else "0 registros")
            return

        df_vista = df.head(MAX_FILAS_TABLA).copy()
        cols = [str(c) for c in df_vista.columns]
        self.tabla["columns"] = cols
        for col in cols:
            es_num = col.upper() in COLS_NUMERICAS
            self.tabla.heading(col, text=col)
            self.tabla.column(
                col,
                width=130 if es_num else max(90, min(220, len(col) * 11)),
                minwidth=70, stretch=False,
                anchor="e" if es_num else "w",
            )
        # Respeta columnas ocultas
        visibles = [c for c in cols if self.col_visibles.get(c, True)]
        self.tabla["displaycolumns"] = visibles if visibles else cols

        for i, (_, fila) in enumerate(df_vista.iterrows()):
            banking = str(fila.get("BANKING_CVA_DVA", "")).upper()
            if "CVA" in banking:
                tag_bg = "fila_cva"
            elif "IFRS" in banking:
                tag_bg = "fila_ifrs"
            else:
                tag_bg = "fila_par" if i % 2 == 0 else "fila_impar"

            pos = pd.to_numeric(fila.get("POSICION"), errors="coerce")
            if pd.isna(pos) or pos == 0:
                tag_fg = "val_neu"
            elif pos < 0:
                tag_fg = "val_neg"
            else:
                tag_fg = "val_pos"

            valores = []
            for col, val in zip(cols, fila.tolist()):
                num = pd.to_numeric(val, errors="coerce")
                if pd.isna(val):
                    valores.append("")
                elif col.upper() in ("POSICION", "POSICION_COP", "POSICION_USD") and pd.notna(num):
                    valores.append(_fmt_miles(num))
                elif col.upper() == "TRM" and pd.notna(num):
                    valores.append(f"{num:,.2f}")
                else:
                    valores.append(str(val))
            self.tabla.insert("", "end", values=valores, tags=(tag_bg, tag_fg))

        total = len(df)
        mostradas = len(df_vista)
        self.lbl_conteo.configure(
            text=f"Mostrando 1 a {mostradas} de {total} registros"
            + ("  (límite de vista alcanzado)" if total > MAX_FILAS_TABLA else "")
        )

    def _actualizar_kpis(self, df: pd.DataFrame | None) -> None:
        if df is None or df.empty:
            self.kpi_registros.configure(text="--")
            self.kpi_exposicion.configure(text="--", text_color=_C_INK)
            self.kpi_exposicion_sub.configure(text="")
            self.kpi_moneda.configure(text="--")
            return

        self.kpi_registros.configure(text=_fmt_miles(len(df)))

        # Moneda principal (más frecuente)
        moneda = "--"
        for col in ("MONEDA_POSICION", "MONEDA"):
            if col in df.columns and not df[col].dropna().empty:
                moneda = str(df[col].mode(dropna=True).iloc[0])
                break
        self.kpi_moneda.configure(text=moneda)

        # Exposición neta = suma de POSICION de la moneda principal (display)
        if "POSICION" in df.columns:
            serie = pd.to_numeric(df["POSICION"], errors="coerce")
            if moneda != "--" and "MONEDA_POSICION" in df.columns:
                serie = serie[df["MONEDA_POSICION"] == moneda]
            total = float(serie.sum(skipna=True))
            color = _C_VAL_NEG if total < 0 else _C_VAL_POS
            sufijo = "" if moneda == "--" else f" {moneda}"
            self.kpi_exposicion.configure(text=_fmt_compacto(total), text_color=color)
            self.kpi_exposicion_sub.configure(text=f"Suma de POSICION{sufijo}")
        else:
            self.kpi_exposicion.configure(text="--", text_color=_C_INK)
            self.kpi_exposicion_sub.configure(text="")

    def _marcar_ejecucion(self, estado: str) -> None:
        """Actualiza la tarjeta 'Última ejecución' con hora y resultado."""
        ahora = datetime.now()
        textos = {"ok": "Éxito", "warn": "Advertencia", "error": "Error"}
        colores = {"ok": _C_VAL_POS, "warn": _C_WARNING, "error": _C_VAL_NEG}
        self.kpi_ejecucion.configure(text=ahora.strftime("%H:%M:%S"))
        self.kpi_ejecucion_sub.configure(
            text=f"{ahora:%d-%m-%Y} · {textos.get(estado, '')}",
            text_color=colores.get(estado, _C_MUTED),
        )

    # ══════════════════════════════════════════════
    # TOOLBAR: filtros / columnas / exportar
    # ══════════════════════════════════════════════
    # Columnas categóricas candidatas a filtro (se usan las presentes con pocos valores únicos)
    COLS_FILTRO = ("PRODUCTO", "BOOK", "MONEDA_POSICION", "CLASIFICACION_CONTABLE",
                   "LB_LT", "BANKING_CVA_DVA", "COMPANY", "INSTRUMENTO")
    MAX_VALORES_FILTRO = 60

    def _abrir_filtros(self) -> None:
        if self.df_completo is None:
            messagebox.showinfo("RISKO", "No hay datos cargados para filtrar.")
            return
        df = self.df_completo

        vent = ctk.CTkToplevel(self.root)
        vent.title("Filtros avanzados")
        vent.geometry("420x560")
        vent.transient(self.root)
        vent.configure(fg_color=_C_PANEL)
        vent.grid_columnconfigure(0, weight=1)
        vent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            vent, text="Filtros avanzados", text_color=_C_INK,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))

        cuerpo = ctk.CTkScrollableFrame(vent, fg_color="#F4F7FC")
        cuerpo.grid(row=1, column=0, sticky="nsew", padx=16)
        cuerpo.grid_columnconfigure(0, weight=1)

        # --- Filtros categóricos (multi-selección por columna) ---
        vars_por_col: dict[str, dict[str, tk.BooleanVar]] = {}
        for col in self.COLS_FILTRO:
            if col not in df.columns:
                continue
            valores = sorted(df[col].dropna().astype(str).unique().tolist())
            if not valores or len(valores) > self.MAX_VALORES_FILTRO:
                continue  # demasiados valores: no es práctico como checklist
            ctk.CTkLabel(
                cuerpo, text=col, text_color=_C_INK,
                font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
            ).grid(sticky="ew", padx=4, pady=(10, 2))
            sel_previa = self.filtros.get(col)
            vars_col: dict[str, tk.BooleanVar] = {}
            for v in valores:
                # Marcado si no hay filtro previo (todo visible) o si estaba seleccionado
                marcado = (sel_previa is None) or (v in sel_previa)
                bvar = tk.BooleanVar(value=marcado)
                vars_col[v] = bvar
                ctk.CTkCheckBox(
                    cuerpo, text=v, variable=bvar, text_color=_C_INK,
                    font=ctk.CTkFont(size=11), checkbox_width=18, checkbox_height=18,
                ).grid(sticky="w", padx=12, pady=2)
            vars_por_col[col] = vars_col

        # --- Rango de POSICION ---
        ent_min = ent_max = None
        if "POSICION" in df.columns:
            ctk.CTkLabel(
                cuerpo, text="POSICIÓN (rango)", text_color=_C_INK,
                font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
            ).grid(sticky="ew", padx=4, pady=(12, 2))
            marco_rango = ctk.CTkFrame(cuerpo, fg_color="transparent")
            marco_rango.grid(sticky="ew", padx=8)
            marco_rango.grid_columnconfigure((0, 1), weight=1)
            ent_min = ctk.CTkEntry(marco_rango, placeholder_text="Mín.", height=30,
                                   fg_color="#FFFFFF", border_color=_C_BORDER, text_color=_C_INK)
            ent_max = ctk.CTkEntry(marco_rango, placeholder_text="Máx.", height=30,
                                   fg_color="#FFFFFF", border_color=_C_BORDER, text_color=_C_INK)
            ent_min.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            ent_max.grid(row=0, column=1, sticky="ew", padx=(4, 0))
            if self.filtro_pos_min is not None:
                ent_min.insert(0, str(self.filtro_pos_min))
            if self.filtro_pos_max is not None:
                ent_max.insert(0, str(self.filtro_pos_max))

        # --- Botonera ---
        barra = ctk.CTkFrame(vent, fg_color="transparent")
        barra.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        barra.grid_columnconfigure((0, 1), weight=1)

        def _to_float(entry):
            if entry is None or not entry.get().strip():
                return None
            try:
                return float(entry.get().strip())
            except ValueError:
                return None  # entrada no numérica => se ignora el límite

        def aplicar():
            nuevos: dict[str, set[str]] = {}
            for col, vars_col in vars_por_col.items():
                marcados = {v for v, bv in vars_col.items() if bv.get()}
                # Solo se considera filtro si NO están todos marcados
                if marcados and len(marcados) < len(vars_col):
                    nuevos[col] = marcados
                elif not marcados:
                    # nada marcado => no mostrará filas de esa columna; lo respetamos
                    nuevos[col] = set()
            self.filtros = nuevos
            self.filtro_pos_min = _to_float(ent_min)
            self.filtro_pos_max = _to_float(ent_max)
            self._refrescar_btn_filtros()
            self._filtrar_y_render()
            n = self._filtros_activos()
            self._set_chip("Datos actualizados" if self.df_completo is not None else "Sin datos",
                           "ok" if self.df_completo is not None else "idle")
            self._escribir_log(f"Filtros aplicados ({n} activo(s)).")
            vent.destroy()

        def limpiar():
            self.filtros = {}
            self.filtro_pos_min = self.filtro_pos_max = None
            self._refrescar_btn_filtros()
            self._filtrar_y_render()
            self._escribir_log("Filtros avanzados eliminados.")
            vent.destroy()

        ctk.CTkButton(barra, text="Limpiar filtros", command=limpiar,
                      fg_color="#E7EDF8", hover_color="#D8E2F5", text_color=_C_INK).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(barra, text="Aplicar", command=aplicar,
                      fg_color=_C_BTN_PRIMARY, hover_color=_C_BTN_HOVER).grid(
            row=0, column=1, sticky="ew", padx=(4, 0))
        vent.focus()

    def _abrir_columnas(self) -> None:
        if not self.columnas:
            messagebox.showinfo("RISKO", "No hay datos cargados.")
            return
        vent = ctk.CTkToplevel(self.root)
        vent.title("Columnas visibles")
        vent.resizable(False, False)
        vent.transient(self.root)
        vent.configure(fg_color=_C_PANEL)
        ctk.CTkLabel(
            vent, text="Mostrar / ocultar columnas", text_color=_C_INK,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        variables: dict[str, tk.BooleanVar] = {}
        cont = ctk.CTkScrollableFrame(vent, fg_color="#F4F7FC", width=240, height=300)
        cont.grid(row=1, column=0, padx=16, sticky="nsew")
        for c in self.columnas:
            var = tk.BooleanVar(value=self.col_visibles.get(c, True))
            variables[c] = var
            ctk.CTkCheckBox(
                cont, text=c, variable=var, text_color=_C_INK,
                font=ctk.CTkFont(size=12),
            ).grid(sticky="w", padx=8, pady=4)

        def aplicar():
            for c, var in variables.items():
                self.col_visibles[c] = bool(var.get())
            if not any(self.col_visibles.values()):  # evita ocultar todo
                self.col_visibles = {c: True for c in self.columnas}
            self._filtrar_y_render()
            vent.destroy()

        ctk.CTkButton(
            vent, text="Aplicar", command=aplicar,
            fg_color=_C_BTN_PRIMARY, hover_color=_C_BTN_HOVER,
        ).grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        vent.focus()

    def _exportar(self) -> None:
        df_exportar = self._df_filtrado()
        if df_exportar is None or df_exportar.empty:
            messagebox.showinfo("RISKO", "No hay datos para exportar.")
            return
        nombre_tabla = self.var_tabla_db.get().strip() or "tabla_risko"
        nombre_tabla = "".join(car if car.isalnum() or car in ("_", "-") else "_" for car in nombre_tabla)
        ruta = filedialog.asksaveasfilename(
            title="Exportar resultados", defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            initialfile=f"{nombre_tabla}_{self._obtener_fecha():%Y%m%d}.xlsx",
        )
        if not ruta:
            return
        try:
            if ruta.lower().endswith(".csv"):
                df_exportar.to_csv(ruta, index=False, encoding="utf-8-sig")
            else:
                df_exportar.to_excel(ruta, index=False)
            self._escribir_log(f"Datos exportados: {ruta}")
            messagebox.showinfo("RISKO", f"Exportado correctamente en:\n{ruta}")
        except Exception as exc:
            self._escribir_log(f"ERROR al exportar: {exc}", "ERROR")
            messagebox.showerror("RISKO", f"No se pudo exportar:\n{exc}")

    # ══════════════════════════════════════════════
    # CALENDARIO EMERGENTE
    # ══════════════════════════════════════════════
    def abrir_calendario(self) -> None:
        vent_abierta = getattr(self.root, "_ventana_cal", None)
        if vent_abierta and vent_abierta.winfo_exists():
            vent_abierta.focus()
            return

        fa = self._obtener_fecha()
        mes_var = tk.IntVar(value=fa.month)
        anio_var = tk.IntVar(value=fa.year)
        cal_obj = calendar.Calendar(firstweekday=calendar.MONDAY)

        vent = ctk.CTkToplevel(self.root)
        self.root._ventana_cal = vent
        vent.title("Seleccionar fecha")
        vent.resizable(False, False)
        vent.transient(self.root)
        vent.configure(fg_color=_C_PANEL)

        cont = ctk.CTkFrame(vent, fg_color=_C_PANEL, corner_radius=8)
        cont.grid(row=0, column=0, padx=12, pady=12)
        cont.grid_columnconfigure(1, weight=1)
        marco_dias = ctk.CTkFrame(cont, fg_color="transparent")

        def cerrar():
            self.root._ventana_cal = None
            vent.destroy()

        def elegir(f: date):
            self._set_fecha(f)
            cerrar()

        def cambiar_mes(delta: int):
            m, a = mes_var.get() + delta, anio_var.get()
            if m == 0:
                m, a = 12, a - 1
            elif m == 13:
                m, a = 1, a + 1
            mes_var.set(m)
            anio_var.set(a)
            pintar()

        ctk.CTkButton(cont, text="◀", width=30, height=28,
                      fg_color=_C_BTN_PRIMARY, hover_color=_C_BTN_HOVER,
                      command=lambda: cambiar_mes(-1)).grid(row=0, column=0, padx=(0, 6), pady=(0, 8))
        titulo_mes = ctk.CTkLabel(cont, text="", text_color=_C_INK,
                                  font=ctk.CTkFont(size=13, weight="bold"))
        titulo_mes.grid(row=0, column=1, columnspan=5, sticky="ew", pady=(0, 8))
        ctk.CTkButton(cont, text="▶", width=30, height=28,
                      fg_color=_C_BTN_PRIMARY, hover_color=_C_BTN_HOVER,
                      command=lambda: cambiar_mes(1)).grid(row=0, column=6, padx=(6, 0), pady=(0, 8))

        for idx, dia in enumerate(("L", "Ma", "Mi", "J", "V", "S", "D")):
            ctk.CTkLabel(cont, text=dia, width=34, text_color="#6080A0",
                         font=ctk.CTkFont(size=11, weight="bold")).grid(
                row=1, column=idx, padx=2, pady=(0, 4))
        marco_dias.grid(row=2, column=0, columnspan=7)

        def pintar():
            for w in marco_dias.winfo_children():
                w.destroy()
            m, a = mes_var.get(), anio_var.get()
            titulo_mes.configure(text=f"{MESES[m]} {a}")
            hoy = self._obtener_fecha()
            for fila, semana in enumerate(cal_obj.monthdayscalendar(a, m)):
                for col, d in enumerate(semana):
                    if not d:
                        ctk.CTkLabel(marco_dias, text="", width=30, height=28).grid(
                            row=fila, column=col, padx=2, pady=2)
                        continue
                    fb = date(a, m, d)
                    sel = fb == hoy
                    ctk.CTkButton(
                        marco_dias, text=str(d), width=30, height=28,
                        fg_color=_C_BTN_PRIMARY if sel else "#EEF2FA",
                        hover_color=_C_BTN_HOVER,
                        text_color="white" if sel else _C_INK,
                        font=ctk.CTkFont(size=11, weight="bold" if sel else "normal"),
                        command=lambda f=fb: elegir(f),
                    ).grid(row=fila, column=col, padx=2, pady=2)

        ctk.CTkButton(cont, text="Hoy", height=28,
                      fg_color=_C_BTN_SECONDARY, hover_color=_C_BTN_SECONDARY_HOVER,
                      command=lambda: elegir(date.today())).grid(
            row=3, column=0, columnspan=7, sticky="ew", pady=(10, 0))
        vent.protocol("WM_DELETE_WINDOW", cerrar)
        pintar()
        vent.focus()

    # ══════════════════════════════════════════════
    # HANDLERS DE EJECUCIÓN  (lógica de negocio intacta)
    # ══════════════════════════════════════════════
    def _ejecutar_en_hilo(self, nombre, trabajo, al_terminar, limpiar_tabla=True) -> None:
        """Ejecuta 'trabajo' (bloqueante) en segundo plano para no congelar la UI.

        - trabajo(): corre en un hilo; devuelve un resultado. Puede llamar a
          self._escribir_log (thread-safe).
        - al_terminar(resultado): corre en el hilo principal si no hubo error;
          actualiza tabla/KPIs/estado según el caso.
        Los errores se reportan en el hilo principal.
        """
        if self._ejecutando:
            self._escribir_log("Ya hay un proceso en ejecución; espere a que termine.", "WARN")
            return
        self._ejecutando = True
        if limpiar_tabla:
            self._cargar_datos(None)
        self._limpiar_log()
        self._set_estado(f"● Ejecutando {nombre}…", _C_WARNING)
        self._set_chip("Procesando…", "warn")
        self._bloquear(True)

        def hilo():
            resultado, error = None, None
            try:
                resultado = trabajo()
            except Exception as exc:  # se reporta en la UI desde el hilo principal
                error = exc
            # NO tocar tkinter desde el hilo: se encola y lo procesa el hilo principal
            self._cola_resultados.put((nombre, resultado, error, al_terminar))

        threading.Thread(target=hilo, daemon=True).start()

    def _drenar_resultados(self) -> None:
        """Procesa en el hilo principal los resultados que dejan los hilos de trabajo."""
        try:
            while True:
                nombre, resultado, error, al_terminar = self._cola_resultados.get_nowait()
                self._completar(nombre, resultado, error, al_terminar)
        except queue.Empty:
            pass
        self.root.after(120, self._drenar_resultados)

    def _completar(self, nombre, resultado, error, al_terminar) -> None:
        """Cierre de una ejecución en el hilo principal: errores o callback de éxito."""
        try:
            if error is not None:
                self._set_estado(f"● Error en {nombre}.", _C_ERROR)
                self._set_chip("Error", "error")
                self._marcar_ejecucion("error")
                self._escribir_log(f"ERROR: {error}", "ERROR")
                messagebox.showerror("RISKO", f"Error inesperado:\n{error}")
            else:
                al_terminar(resultado)
        finally:
            self._bloquear(False)
            self._ejecutando = False

    def run_abrir_pyg(self) -> None:
        """Abre el proyecto PyG en un proceso independiente."""
        interfaz = Path(__file__).with_name("interfaz_pyg.py")
        try:
            subprocess.Popen(
                [sys.executable, str(interfaz)],
                cwd=str(RAIZ_RISKO),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self._escribir_log("Interfaz PyG abierta en un proceso independiente.")
        except Exception as exc:
            self._escribir_log(f"ERROR al abrir PyG: {exc}", "ERROR")
            messagebox.showerror("RISKO", f"No se pudo abrir PyG:\n{exc}")

    def run_limpiar(self) -> None:
        fecha = self.entrada_fecha.get()

        def trabajo():
            limpiar_insumos_risko(fecha, logger=self._escribir_log)

        def al_terminar(_):
            self._set_estado("● Insumos limpiados.", _C_SUCCESS)
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")

        self._ejecutar_en_hilo("Limpiar insumos", trabajo, al_terminar)

    def run_todo(self) -> None:
        fecha = self.entrada_fecha.get()
        usar_pruebas = self.usar_db_pruebas.get()

        def trabajo():
            resultado = ejecutar_todo_position_monitor(
                fecha,
                ruta_dashy=RUTA_DASHY,
                logger=self._escribir_log,
                limpiar_insumos=True,
                pruebas=usar_pruebas,
            )
            df = cargar_posicion_actual(fecha, pruebas=usar_pruebas)
            return df, resultado.get("dashboard")

        def al_terminar(res):
            df, dashboard = res
            self._cargar_datos(self._filtrar_por_fecha(df))
            self._actualizar_lista_tablas_db()
            self.var_tabla_db.set("tbl_posicion_actual")
            self._set_estado("● Cierre completo finalizado.", _C_SUCCESS)
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")
            self._escribir_log(f"Dashboard: {dashboard}")

        self._ejecutar_en_hilo("Cierre completo", trabajo, al_terminar)

    def run_intradia(self) -> None:
        fecha = self.entrada_fecha.get()
        if self.usar_db_pruebas.get():
            messagebox.showwarning(
                "RISKO — Preliminar intradía",
                "Desactive 'Usar base de pruebas' para publicar el preliminar en el portal.",
            )
            return
        continuar = messagebox.askyesno(
            "RISKO — Ejecutar intradía",
            "Se publicará una posición PRELIMINAR solo Banking, sin IFRS/CVA-DVA "
            "e incluyendo Opciones revaloradas con el promedio SETFX del corte. "
            "El intradía no consulta TRM FORMADA.\n\n"
            "¿Desea ejecutar y publicar el preliminar?",
        )
        if not continuar:
            return

        def trabajo():
            return ejecutar_intradia_position_monitor(
                fecha,
                ruta_dashy=RUTA_DASHY,
                logger=self._escribir_log,
                cargar_insumos=True,
                publicar=True,
            )

        def al_terminar(resultado):
            tabla = resultado["tabla"]
            publicacion = resultado["publicacion"]
            self._cargar_datos(self._filtrar_por_fecha(tabla))
            self._set_estado("● Preliminar intradía publicado.", _C_WARNING)
            self._set_chip("Preliminar", "warn")
            self._marcar_ejecucion("ok")
            self._escribir_log(f"Publicación preliminar: {publicacion['html']}")
            messagebox.showwarning(
                "RISKO — Preliminar intradía publicado",
                f"Dashboard publicado en:\n{publicacion['html']}\n\n"
                "Vista Banking. Sin IFRS/CVA-DVA. Opciones y escala COP/USD "
                "calculadas únicamente con el promedio SETFX.",
            )

        self._ejecutar_en_hilo(
            "Preliminar intradía",
            trabajo,
            al_terminar,
        )

    def run_consolidar(self) -> None:
        fecha = self.entrada_fecha.get()
        usar_pruebas = self.usar_db_pruebas.get()
        nombre_db = "risko_pruebas.db" if usar_pruebas else "risko.db"

        def trabajo():
            consolidar_posicion(fecha, logger=self._escribir_log, pruebas=usar_pruebas)
            self._escribir_log(f"Cargando tbl_posicion_actual desde {nombre_db} para visualización.")
            return cargar_posicion_actual(fecha, pruebas=usar_pruebas)

        def al_terminar(df):
            self._set_estado("● Consolidación exitosa.", _C_SUCCESS)
            if df is not None:
                self._cargar_datos(self._filtrar_por_fecha(df))
            self._actualizar_lista_tablas_db()
            self.var_tabla_db.set("tbl_posicion_actual")
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")

        self._ejecutar_en_hilo("Consolidar posición", trabajo, al_terminar)

    def run_tablero(self) -> None:
        fecha = self.entrada_fecha.get()
        usar_pruebas = self.usar_db_pruebas.get()

        def trabajo():
            return generar_tablero(
                fecha,
                RUTA_DASHY,
                logger=self._escribir_log,
                consolidar=False,
                pruebas=usar_pruebas,
            )

        def al_terminar(html):
            self._set_estado("● Tablero generado.", _C_SUCCESS)
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")
            self._escribir_log(f"Archivo: {html}")
            messagebox.showinfo("RISKO", f"Tablero generado en:\n{html}")

        # No limpia la tabla: generar el tablero no cambia los datos mostrados
        self._ejecutar_en_hilo("Generar tablero", trabajo, al_terminar, limpiar_tabla=False)

    def run_publicar_tablero(self) -> None:
        fecha = self.entrada_fecha.get()
        usar_pruebas = self.usar_db_pruebas.get()

        def trabajo():
            if usar_pruebas:
                raise ValueError(
                    "Desactive 'Usar base de pruebas' antes de publicar en produccion."
                )
            html = generar_tablero(
                fecha,
                RUTA_DASHY,
                logger=self._escribir_log,
                consolidar=False,
                pruebas=False,
            )
            return publicar_tablero(
                fecha,
                RUTA_DASHY,
                logger=self._escribir_log,
                html_origen=html,
                pruebas=False,
            )

        def al_terminar(resultado):
            destino = resultado["html"]
            fecha_posicion = resultado["fecha_posicion"]
            fecha_publicacion = resultado["fecha_publicacion"]
            fechas_datos = resultado["fechas_datos"]
            self._set_estado("● Tablero publicado en el portal.", _C_SUCCESS)
            self._set_chip("Publicado", "ok")
            self._marcar_ejecucion("ok")
            self._escribir_log(f"Publicacion: {destino}")

            detalle_fechas = ""
            if fechas_datos and fecha_posicion not in fechas_datos:
                detalle_fechas = (
                    "\n\nAviso de trazabilidad: la posicion solicitada fue "
                    f"{fecha_posicion}, pero los datos efectivos corresponden a "
                    f"{', '.join(fechas_datos)}."
                )
            messagebox.showinfo(
                "RISKO — Publicacion completada",
                f"Tablero disponible para el portal en:\n{destino}\n\n"
                f"Fecha de publicacion: {fecha_publicacion}{detalle_fechas}",
            )

        self._ejecutar_en_hilo(
            "Publicar tablero",
            trabajo,
            al_terminar,
            limpiar_tabla=False,
        )

    def run_historicos(self) -> None:
        usar_pruebas = self.usar_db_pruebas.get()

        def trabajo():
            try:
                df = cargar_posicion_historica(self.entrada_fecha.get(), pruebas=usar_pruebas)
            except ValueError:
                return "no_existe", None
            if df.empty:
                return "vacio", None
            return "ok", df

        def al_terminar(res):
            estado, df = res
            if estado == "no_existe":
                self._escribir_log("Archivo tbl_posicion_historico.csv no encontrado.", "WARN")
                messagebox.showwarning(
                    "RISKO — Históricos",
                    "No existe historial. El archivo se genera automáticamente\n"
                    "al ejecutar la consolidación en el último día hábil de cada mes.",
                )
                self._set_estado("● Histórico no disponible.", _C_WARNING)
                self._set_chip("Pendiente", "warn")
                return
            if estado == "vacio":
                self._escribir_log("Histórico vacío — se poblará al cierre de cada mes.", "WARN")
                messagebox.showinfo("RISKO", "El histórico estará disponible al cierre de mes.")
                self._set_estado("● Histórico vacío.", _C_WARNING)
                self._set_chip("Pendiente", "warn")
                return
            self._cargar_datos(self._filtrar_por_fecha(df))
            self._set_estado(f"● Histórico cargado ({len(df)} registros).", _C_SUCCESS)
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")
            self._escribir_log(f"Histórico cargado: {len(df)} registros de cierre de mes.")

        self._ejecutar_en_hilo("Cargar históricos", trabajo, al_terminar)

    def run_producto(self, producto: str) -> None:
        fecha = self.entrada_fecha.get()
        usar_pruebas = self.usar_db_pruebas.get()

        def trabajo():
            self._escribir_log(f"Módulo: {producto}.")
            return ejecutar_producto(
                producto,
                fecha,
                logger=self._escribir_log,
                pruebas=usar_pruebas,
            )

        def al_terminar(tabla):
            self._cargar_datos(self._filtrar_por_fecha(tabla))
            self._actualizar_lista_tablas_db()
            self._set_estado(f"● {producto} completado.", _C_SUCCESS)
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")

        self._ejecutar_en_hilo(producto, trabajo, al_terminar)

    def run_importar_iniciales_spot(self) -> None:
        usar_pruebas = self.usar_db_pruebas.get()

        def trabajo():
            return importar_iniciales_spot_desde_excel(
                logger=self._escribir_log,
                pruebas=usar_pruebas,
            )

        def al_terminar(tabla):
            self._cargar_datos(tabla)
            self._actualizar_lista_tablas_db()
            self.var_tabla_db.set("tbl_posicion_spot_acumulada")
            self._set_estado("● Posiciones iniciales Spot importadas.", _C_SUCCESS)
            self._set_chip("Datos actualizados", "ok")
            self._marcar_ejecucion("ok")

        self._ejecutar_en_hilo("Cargar parámetros Spot", trabajo, al_terminar)

    def run_spot_2_cierre_pruebas(self) -> None:
        fecha = self.entrada_fecha.get()
        continuar = messagebox.askyesno(
            "RISKO — Spot 2 de cierre",
            "Se ejecutará SPOT_CLIENTE con el reporte de Caja de CIERRE en una "
            "base dedicada de pruebas. No se usarán insumos intradía ni se "
            "modificará, consolidará o publicará la posición oficial.\n\n"
            "¿Desea continuar?",
        )
        if not continuar:
            return

        def trabajo():
            return ejecutar_spot_2_cierre_pruebas(
                fecha,
                logger=self._escribir_log,
                cargar_insumo=True,
            )

        def al_terminar(resultado):
            tabla = resultado["tabla"]
            self._cargar_datos(self._filtrar_por_fecha(tabla))
            self._set_estado("● Spot 2 de cierre completado en pruebas.", _C_WARNING)
            self._set_chip("Prueba aislada", "warn")
            self._marcar_ejecucion("ok")
            self._escribir_log(f"Spot 2 de cierre no publicado. Base aislada: {resultado['ruta_db']}")
            fuente = resultado["ruta_insumo"] or "Carry-forward de cierre"
            messagebox.showinfo(
                "RISKO — Spot 2 de cierre completado",
                f"Resultado calculado sin consolidar ni publicar.\n\n"
                f"Fuente: {fuente}\n"
                f"Base aislada: {resultado['ruta_db']}",
            )

        self._ejecutar_en_hilo("Spot 2 de cierre aislado", trabajo, al_terminar)

    def _limpiar_vista(self) -> None:
        """Depura la tabla y los KPIs mostrados (no toca archivos ni insumos)."""
        self._cargar_datos(None)
        self._set_chip("Sin datos", "idle")
        self._escribir_log("Tabla depurada.")

    def run_actualizar(self) -> None:
        """Refresca la vista leyendo de nuevo la tabla seleccionada en SQLite."""
        nombre_tabla = self.var_tabla_db.get().strip()
        if nombre_tabla and nombre_tabla != "Sin tablas":
            self.run_cargar_tabla_db()
            return

        if self.df_completo is None:
            self._set_chip("Sin datos", "idle")
            self._escribir_log("No hay datos cargados para actualizar.", "WARN")
            return
        self._filtrar_y_render()
        self._actualizar_kpis(self.df_completo)
        self._set_chip("Datos actualizados", "ok")
        self._escribir_log("Vista actualizada.")


def main() -> None:
    """Construye y ejecuta la ventana principal de Risko."""
    AppRisko().run()


if __name__ == "__main__":
    main()
