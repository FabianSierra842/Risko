"""
Portfolio Position Monitor conectado a Tbl_Posicion.csv.

Como editar este archivo:
1. Cambia rutas, titulos, limites, filtros y columnas en la seccion "EDITA AQUI".
2. La seccion "DATOS Y TABLAS" prepara los DataFrames que usa el dashboard.
3. La seccion "CONSTRUCCION DEL DASHBOARD" arma las secciones, filtros y graficas.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any
import unicodedata

import pandas as pd


# =============================================================================
# 0. BASE DEL PROYECTO
# =============================================================================

RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from compartido.nucleo_risko.rutas import (
    ARCHIVO_PANEL_POSITION_MONITOR,
    ARCHIVO_POSICION_ACTUAL,
    ARCHIVO_POSICION_HISTORICO,
    CARPETA_LOGS_POSITION_MONITOR,
    resolver_ruta_importacion_dashy,
)
from compartido.nucleo_risko.trm import obtener_trm_formada
from proyectos.position_monitor.procesos.consolidacion import (
    TABLA_POSICION_ACTUAL,
    TABLA_POSICION_HISTORICO,
    leer_tabla_position_monitor,
)


# =============================================================================
# 1. EDITA AQUI: RUTAS, TEXTOS, FILTROS Y COLUMNAS
# =============================================================================

# Archivos de entrada y salida.
DATA_PATH = ARCHIVO_POSICION_ACTUAL
HISTORICAL_DATA_PATH = ARCHIVO_POSICION_HISTORICO
OUTPUT_PATH = ARCHIVO_PANEL_POSITION_MONITOR
LOGS_DIR = CARPETA_LOGS_POSITION_MONITOR
PUBLICATION_SCOPE_CONFIG_PATH = (
    PROJECT_DIR.parent / "configuracion" / "dashboard_publicacion.json"
)


# Alcance de productos y books liberados. La misma estructura se puede cambiar
# desde dashboard_publicacion.json sin modificar el codigo del tablero.
DEFAULT_PUBLICATION_SCOPE = {
    "enabled": True,
    "exclude_products": ["Cubrebonos", "NDFTES", "PP"],
    "allowed_books": [
        "Fwd Clientes",
        "Fx Estrat",
        "Futuros Fx",
        "Monedas",
        "Opciones",
        "Renta_Fija_ME",
        "Spot_Cliente",
        "Swaps",
        "AMCOST_NY",
        "Colchon",
        "Cortos",
        "Deuda_Privada",
        "Estructural",
        "FVOCI_PANAMA",
        "FVOCI_SUPAN",
        "FV_OCI_MIAMI",
        "FV_OCI_NY",
        "Obligatorias",
        "RF_ME_FV_OCI",
        "RF_ME_TRADIN",
        "RF_ML_FV_OCI",
        "Trade_Corta",
        "Trading",
    ],
}


# Textos principales del dashboard.
DASHBOARD_TITLE = "Portfolio Position Monitor"
DASHBOARD_SUBTITLE = "Posicion consolidada del portafolio"
DASHBOARD_DESCRIPTION = (
    "Este dashboard presenta la posición consolidada del portafolio del Banco de Bogotá."
    " Permite filtrar y desagregar por: Book, Libro Bancario o Libro Trading,"
    " Producto, Instrumento y Clasificación Contable."
)


# Opciones visuales de la pagina.
PAGE_OPTIONS = {
    "theme_toggle": True,
    "max_width": "1600px",
    "header_height": "72px",
    "page_kicker": "",
    "embedded_branding": True,
    "show_partner_logo": True,
    "brand_title": "Banco de Bogota",
    "brand_labels": [
        "Direccion de Riesgo de Tesoreria y Balance",
        "Jefatura de Riesgo de Mercado",
    ],
    # Cero hace que la barra completa de filtros globales inicie contraida.
    "filters_collapsed_threshold": 0,
    "toolbar_title": "Filtros globales",
    "page_scale": 1,
    "density": "compact",
    "section_details_open": False,
    "show_topbar": True,
    "show_hero_stats": False,
    "show_toolbar_meta": False,
    "show_toolbar_caption": False,
    "show_section_picker": False,
    "show_section_actions": False,
    "show_section_eyebrow": False,
}


# Tarjetas informativas del banner.
HEADER_LIMITS = [
    {"label": "Limite Libro Trading: USD 55 Millones", "tone": "warning"},
]


# Columnas que el dashboard necesita.
POSITION_COLUMN = "POSICION"
DATE_COLUMN = "FECHA"
GLOBAL_FILTER_COLUMNS = (
    "LB_LT",
    "PRODUCTO",
    "BOOK",
    "INSTRUMENTO",
    "BANKING_CVA_DVA",
    "MONEDA_POSICION",
)
CATEGORY_COLUMNS = ("LB_LT", "PRODUCTO", "BOOK", "INSTRUMENTO")
GRAPH_COLUMNS = CATEGORY_COLUMNS

REQUIRED_COLUMNS = [
    "LB_LT",
    "PRODUCTO",
    "BOOK",
    "INSTRUMENTO",
    "BANKING_CVA_DVA",
    POSITION_COLUMN,
    "MONEDA_POSICION",
]
HISTORICAL_REQUIRED_COLUMNS = [*REQUIRED_COLUMNS, DATE_COLUMN]


# Estas columnas se limpian como texto. Si falta alguna, no pasa nada.
TEXT_DIMENSION_COLUMNS = (
    "PRODUCTO",
    "LB_LT",
    "BOOK",
    "MONEDA_POSICION",
    "INSTRUMENTO",
    "COMPANY",
    "CLASIFICACION_CONTABLE",
    "BANKING_CVA_DVA",
)


# Categorias disponibles para graficar en Posicion actual e Historico.
CATEGORY_COLUMN_OPTIONS = [
    {"label": "Libro Bancario / Libro Trading", "value": "LB_LT"},
    {"label": "Producto", "value": "PRODUCTO"},
    {"label": "Book", "value": "BOOK"},
    {"label": "Instrumento", "value": "INSTRUMENTO"},
]


# Filtros globales. Si default esta vacio, el filtro abre como "Todos".
GLOBAL_FILTER_SPECS = [
    {
        "id": "f_global_lb_lt",
        "column": "LB_LT",
        "label": "Libro Bancario / Libro Trading",
        "default": ["Trading", "Bancario", "No definido"],
        "open": False,
    },
    {"id": "f_global_producto", "column": "PRODUCTO", "label": "Producto", "default": [], "open": False},
    {"id": "f_global_book", "column": "BOOK", "label": "Book", "default": [], "open": False},
    {"id": "f_global_instrumento", "column": "INSTRUMENTO", "label": "Instrumento", "default": [], "open": False},
    {
        "id": "f_global_banking_cva_dva",
        "column": "BANKING_CVA_DVA",
        "label": "Banking CVA/DVA",
        "default": [],
        "open": False,
    },
    {
        "id": "f_global_moneda",
        "column": "MONEDA_POSICION",
        "label": "Moneda",
        "default": ["USD"],
        "open": False,
    },
]


# Columnas de la tabla pequena de Posicion actual.
SUMMARY_TABLE_COLUMNS = [
    {"name": "GRUPO_GRAFICA", "label": "Grupo", "format": "text", "highlight": "none"},
    {"name": "MONEDA_POSICION", "label": "Moneda", "format": "text", "align": "center", "highlight": "none"},
    {"name": "POSICION_TOTAL", "label": "Posicion total", "format": "number", "align": "right"},
]


# Columnas de la tabla grande de detalle.
DETAIL_TABLE_COLUMNS = [
    {"name": "FECHA", "label": "Fecha", "format": "date", "align": "center", "highlight": "none"},
    {"name": "PRODUCTO", "label": "Producto", "format": "text", "highlight": "none"},
    {"name": "BOOK", "label": "Book", "format": "text", "highlight": "none"},
    {"name": "MONEDA_POSICION", "label": "Moneda", "format": "text", "align": "center", "highlight": "none"},
    {"name": POSITION_COLUMN, "label": "Posicion", "format": "number", "align": "right"},
    {"name": "LB_LT", "label": "LB / LT", "format": "text", "align": "center", "highlight": "none"},
    {"name": "INSTRUMENTO", "label": "Instrumento", "format": "text", "highlight": "none"},
    {"name": "COMPANY", "label": "Company", "format": "text", "align": "center", "highlight": "none"},
    {"name": "CLASIFICACION_CONTABLE", "label": "Clasificacion contable", "format": "text", "highlight": "none"},
    {"name": "BANKING_CVA_DVA", "label": "Banking CVA/DVA", "format": "text", "highlight": "none"},
]


# Etiqueta de lectura contable para la tabla de detalle. Sin seleccion equivale
# a mostrar Banking + CVA/DVA, que en conjunto conforman la posicion IFRS.
POSITION_ACCOUNTING_CONTEXT = {
    "filter_id": "f_global_banking_cva_dva",
    "prefix": "Posición",
    "empty_label": "IFRS",
    "fallback_label": "IFRS",
    "cases": [
        {"values": ["Banking", "CVA/DVA"], "label": "IFRS"},
        {"values": ["Banking"], "label": "Banking"},
        {"values": ["CVA/DVA"], "label": "CVA/DVA"},
    ],
}

POSITION_ACCOUNTING_CONTEXT_PRELIMINAR = {
    "filter_id": "f_global_banking_cva_dva",
    "prefix": "Posición",
    "empty_label": "Banking preliminar",
    "fallback_label": "Banking preliminar",
    "cases": [
        {"values": ["Banking"], "label": "Banking preliminar"},
    ],
}


# Nombres internos de datasets. Normalmente no necesitas cambiarlos.
DATASET_CURRENT_CHART = "tbl_posicion"
DATASET_CURRENT_DETAIL = "tbl_posicion_detalle"
DATASET_HISTORICAL_CHART = "tbl_posicion_historico"
DATASET_GLOBAL_FILTERS = "tbl_posicion_filtros_globales"
GLOBAL_FILTER_DATASETS = [
    DATASET_CURRENT_CHART,
    DATASET_HISTORICAL_CHART,
    DATASET_CURRENT_DETAIL,
    DATASET_GLOBAL_FILTERS,
]


# =============================================================================
# 2. DATOS Y TABLAS
# =============================================================================

def normalize_column_name(name: str) -> str:
    """Convierte nombres de columnas a MAYUSCULAS_SIN_TILDES."""
    normalized = unicodedata.normalize("NFKD", str(name))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    compact = "".join(char if char.isalnum() else "_" for char in ascii_only)
    while "__" in compact:
        compact = compact.replace("__", "_")
    return compact.strip("_").upper()


def normalize_dimension_key(value: object) -> str:
    """Normaliza dimensiones para comparar sin depender de espacios o guiones."""
    return normalize_column_name(str(value).strip())


def load_publication_scope_config(
    path: str | Path = PUBLICATION_SCOPE_CONFIG_PATH,
) -> dict[str, Any]:
    """Carga y valida el alcance que puede mostrarse en el dashboard publicado."""
    config_path = Path(path)
    scope = dict(DEFAULT_PUBLICATION_SCOPE)
    scope["exclude_products"] = list(DEFAULT_PUBLICATION_SCOPE["exclude_products"])
    scope["allowed_books"] = list(DEFAULT_PUBLICATION_SCOPE["allowed_books"])

    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        configured_scope = payload.get("publication_scope", payload)
        if not isinstance(configured_scope, dict):
            raise ValueError(
                "dashboard_publicacion.json debe contener un objeto publication_scope."
            )
        scope.update(configured_scope)

    if not isinstance(scope.get("enabled"), bool):
        raise ValueError("publication_scope.enabled debe ser true o false.")
    for field in ("exclude_products", "allowed_books"):
        values = scope.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f"publication_scope.{field} debe ser una lista de textos.")

    return scope


def apply_publication_scope(
    df: pd.DataFrame,
    scope: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Limita el universo visible sin alterar la base consolidada."""
    result = df.copy()
    resolved_scope = scope if scope is not None else load_publication_scope_config()
    if not resolved_scope["enabled"]:
        return result.reset_index(drop=True)

    excluded_products = {
        normalize_dimension_key(value)
        for value in resolved_scope["exclude_products"]
        if value.strip()
    }
    if excluded_products and "PRODUCTO" in result.columns:
        product_keys = result["PRODUCTO"].apply(normalize_dimension_key)
        result = result.loc[~product_keys.isin(excluded_products)].copy()

    allowed_books = {
        normalize_dimension_key(value)
        for value in resolved_scope["allowed_books"]
        if value.strip()
    }
    if "BOOK" in result.columns:
        # Con la restriccion habilitada, una lista vacia es un bloqueo total.
        book_keys = result["BOOK"].apply(normalize_dimension_key)
        result = result.loc[book_keys.isin(allowed_books)].copy()

    return result.reset_index(drop=True)


def read_csv_data(path: Path) -> pd.DataFrame:
    """Lee CSV probando codificaciones comunes."""
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el archivo fuente: {path}")

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(path, sep=",", encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    raise RuntimeError(f"No fue posible leer el archivo CSV: {path}") from last_error


def parse_position(series: pd.Series) -> pd.Series:
    """Convierte la columna de posicion a numero."""
    cleaned = series.astype(str).str.strip().str.replace(",", "", regex=False)
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def clean_position_frame(df: pd.DataFrame, required_columns: list[str]) -> pd.DataFrame:
    """Normaliza columnas, valida campos obligatorios y limpia datos basicos."""
    df = df.copy()
    df.columns = [normalize_column_name(column) for column in df.columns]

    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas requeridas en el CSV: {', '.join(missing)}")

    for column in TEXT_DIMENSION_COLUMNS:
        if column not in df.columns:
            continue
        df[column] = df[column].fillna("Sin dato").astype(str).str.strip()
        df.loc[df[column] == "", column] = "Sin dato"

    df[POSITION_COLUMN] = parse_position(df[POSITION_COLUMN])
    if DATE_COLUMN in df.columns:
        df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], dayfirst=True, errors="coerce")

    return df


def build_currency_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """La moneda viene en MONEDA_POSICION y POSICION refleja el valor nativo; no se duplican filas."""
    return df.copy()


def read_position_data(pruebas: bool = False) -> pd.DataFrame:
    """Tabla actual de posiciones."""
    try:
        return clean_position_frame(
            leer_tabla_position_monitor(TABLA_POSICION_ACTUAL, pruebas=pruebas),
            REQUIRED_COLUMNS,
        )
    except ValueError:
        if pruebas:
            raise
        pass

    return clean_position_frame(read_csv_data(DATA_PATH), REQUIRED_COLUMNS)


def read_historical_position_data(pruebas: bool = False) -> pd.DataFrame:
    """Tabla historica de posiciones."""
    try:
        df = clean_position_frame(
            leer_tabla_position_monitor(TABLA_POSICION_HISTORICO, pruebas=pruebas),
            HISTORICAL_REQUIRED_COLUMNS,
        )
    except ValueError:
        if pruebas:
            raise
        df = clean_position_frame(read_csv_data(HISTORICAL_DATA_PATH), HISTORICAL_REQUIRED_COLUMNS)

    df = df[df[DATE_COLUMN].notna()].copy()
    return df


def build_chart_dataset(df: pd.DataFrame, extra_columns: list[str] | None = None) -> pd.DataFrame:
    """
    Convierte una tabla normal en una tabla tipo "tabla dinamica".

    COLUMNA_GRAFICA indica la categoria seleccionada.
    GRUPO_GRAFICA indica el valor que se grafica.
    """
    extra_columns = [column for column in (extra_columns or []) if column in df.columns]
    views: list[pd.DataFrame] = []

    for column in GRAPH_COLUMNS:
        base_columns = [item for item in extra_columns if item != column]
        view = df[[*base_columns, column, POSITION_COLUMN]].copy()
        view = view.rename(columns={column: "GRUPO_GRAFICA"})
        view["COLUMNA_GRAFICA"] = column
        view["GRUPO_GRAFICA"] = view["GRUPO_GRAFICA"].fillna("Sin dato").astype(str).str.strip()
        view.loc[view["GRUPO_GRAFICA"] == "", "GRUPO_GRAFICA"] = "Sin dato"
        view[column] = view["GRUPO_GRAFICA"]
        views.append(view[[*extra_columns, "COLUMNA_GRAFICA", "GRUPO_GRAFICA", POSITION_COLUMN]])

    return pd.concat(views, ignore_index=True)


def build_global_filter_dataset(*frames: pd.DataFrame) -> pd.DataFrame:
    """Crea una tabla pequena solo para alimentar opciones de filtros globales."""
    columns = list(GLOBAL_FILTER_COLUMNS)
    available_frames = [frame[columns] for frame in frames if all(column in frame.columns for column in columns)]
    if not available_frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(available_frames, ignore_index=True).drop_duplicates().reset_index(drop=True)


def load_dashboard_tables(
    pruebas: bool = False,
    current_override: pd.DataFrame | None = None,
    historical_override: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Carga todas las tablas que se entregan al dashboard."""
    publication_scope = load_publication_scope_config()
    current_source = (
        read_position_data(pruebas=pruebas)
        if current_override is None
        else clean_position_frame(current_override, REQUIRED_COLUMNS)
    )
    historical_source = (
        read_historical_position_data(pruebas=pruebas)
        if historical_override is None
        else clean_position_frame(historical_override, HISTORICAL_REQUIRED_COLUMNS)
    )
    current_df = apply_publication_scope(
        current_source,
        publication_scope,
    )
    historical_df = apply_publication_scope(
        historical_source,
        publication_scope,
    )
    current_currency_df = build_currency_dataset(current_df)
    historical_currency_df = build_currency_dataset(historical_df)

    return {
        "current_raw": current_currency_df,
        "historical_raw": historical_currency_df,
        DATASET_CURRENT_CHART: build_chart_dataset(current_currency_df, extra_columns=list(GLOBAL_FILTER_COLUMNS)),
        DATASET_CURRENT_DETAIL: current_currency_df,
        DATASET_HISTORICAL_CHART: build_chart_dataset(
            historical_currency_df,
            extra_columns=[DATE_COLUMN, *GLOBAL_FILTER_COLUMNS],
        ),
        DATASET_GLOBAL_FILTERS: build_global_filter_dataset(current_currency_df, historical_currency_df),
    }


# =============================================================================
# 3. CONSTRUCCION DEL DASHBOARD
# =============================================================================

def _obtener_dashboard_builder(ruta_dashy: str | Path | None = None):
    ruta_importacion = resolver_ruta_importacion_dashy(ruta_dashy)
    if str(ruta_importacion) not in sys.path:
        sys.path.insert(0, str(ruta_importacion))

    from dashy import DashboardBuilder

    return DashboardBuilder


def _fecha_legible(value: str | None) -> str:
    if not value:
        return ""
    texto = str(value).strip()
    fecha = (
        pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
        if len(texto) >= 10 and texto[4:5] == "-" and texto[7:8] == "-"
        else pd.to_datetime(texto, dayfirst=True, errors="coerce")
    )
    if pd.isna(fecha):
        return ""
    return fecha.strftime("%d/%m/%Y %H:%M") if "T" in texto else fecha.strftime("%d/%m/%Y")


def _fechas_de_datos(df: pd.DataFrame) -> list[str]:
    if DATE_COLUMN not in df.columns:
        return []
    fechas = pd.to_datetime(df[DATE_COLUMN], dayfirst=True, errors="coerce").dropna()
    return sorted({fecha.strftime("%d/%m/%Y") for fecha in fechas})


def _resolver_trm_dashboard(
    current_df: pd.DataFrame,
    trm_formada: float | None = None,
) -> float:
    """Usa la TRM FORMADA exacta del corte, igual que el modulo de Opciones."""
    if trm_formada is not None:
        tasa = pd.to_numeric(pd.Series([trm_formada]), errors="coerce").iloc[0]
        if pd.isna(tasa) or float(tasa) <= 0:
            raise ValueError(f"TRM FORMADA invalida para el dashboard: {trm_formada}")
        return float(tasa)

    if DATE_COLUMN not in current_df.columns:
        raise ValueError("No se puede resolver la TRM: la posicion actual no tiene FECHA.")
    fechas = pd.to_datetime(current_df[DATE_COLUMN], dayfirst=True, errors="coerce").dropna()
    fechas_unicas = sorted({fecha.normalize() for fecha in fechas})
    if len(fechas_unicas) != 1:
        raise ValueError(
            "El dashboard requiere una unica fecha de posicion para consultar la TRM "
            f"FORMADA exacta; fechas encontradas: {len(fechas_unicas)}."
        )
    return obtener_trm_formada(fechas_unicas[0])


def _resolver_tasa_escala_dashboard(
    current_df: pd.DataFrame,
    *,
    estado_corte: str | None = None,
    promedio_setfx: float | None = None,
    trm_formada: float | None = None,
) -> tuple[float, str]:
    """Separa la tasa intradía SETFX de la TRM FORMADA usada al cierre."""
    es_preliminar = str(estado_corte or "").upper() in {
        "PRELIMINAR_INTRADIA",
        "INTRADIA",
        "INTRADÍA",
    }
    if es_preliminar:
        tasa = pd.to_numeric(pd.Series([promedio_setfx]), errors="coerce").iloc[0]
        if pd.isna(tasa) or float(tasa) <= 0:
            raise ValueError(
                "El dashboard preliminar requiere un PROMEDIO SETFX valido; "
                f"valor recibido: {promedio_setfx}"
            )
        return float(tasa), "PROMEDIO SETFX"
    return _resolver_trm_dashboard(current_df, trm_formada), "TRM FORMADA"


def create_builder(
    ruta_dashy: str | Path | None = None,
    fecha_publicacion: str | None = None,
    fechas_datos: list[str] | None = None,
    estado_corte: str | None = None,
    productos_pendientes: list[str] | None = None,
    promedio_setfx: float | None = None,
    trm_formada: float | None = None,
    advertencias: list[str] | None = None,
) -> Any:
    """Crea el objeto principal del dashboard y configura su apariencia."""
    DashboardBuilder = _obtener_dashboard_builder(ruta_dashy)
    es_preliminar = str(estado_corte or "").upper() in {
        "PRELIMINAR_INTRADIA",
        "INTRADIA",
        "INTRADÍA",
    }
    etiqueta_corte = "INTRADÍA" if es_preliminar else "CIERRE"
    subtitulo = DASHBOARD_SUBTITLE
    titulo = DASHBOARD_TITLE
    descripcion = DASHBOARD_DESCRIPTION
    if es_preliminar:
        titulo = f"{DASHBOARD_TITLE} · INTRADÍA"
        subtitulo = "Posición INTRADÍA · Vista Banking"
        alcance_pendientes = (
            f" Productos pendientes: {', '.join(productos_pendientes)}."
            if productos_pendientes
            else " Incluye todos los productos intradía configurados."
        )
        descripcion = (
            "Corte INTRADÍA calculado con los últimos reportes de Summit. "
            "No contiene IFRS ni CVA/DVA."
            + alcance_pendientes
        )
    else:
        titulo = f"{DASHBOARD_TITLE} · CIERRE"
        subtitulo = "Posición CIERRE · Vista consolidada"
        descripcion = f"{DASHBOARD_DESCRIPTION} Corte CIERRE oficial."
    if fechas_datos:
        subtitulo = (
            f"{subtitulo} · Fecha de posición: {', '.join(fechas_datos)}"
        )
    builder = DashboardBuilder(
        title=titulo,
        subtitle=subtitulo,
        description=descripcion,
        theme="bdb_light",
        default_layout={"span": "wide", "height": 320, "min_height": 240},
    )
    builder.set_defaults(locale="es-CO", decimals=0, percent_decimals=1)
    builder.set_page_options(**PAGE_OPTIONS)

    for badge in HEADER_LIMITS:
        builder.add_header_badge(badge["label"], tone=badge.get("tone", "subtle"))
    builder.add_header_badge(etiqueta_corte, tone="warning" if es_preliminar else "info")
    if es_preliminar:
        builder.add_header_badge("Solo Banking · Sin IFRS/CVA-DVA", tone="info")
        if productos_pendientes:
            builder.add_header_badge(
                f"Pendiente: {', '.join(productos_pendientes)}",
                tone="warning",
            )
        for advertencia in advertencias or []:
            builder.add_header_badge(advertencia, tone="warning")
    fecha_legible = _fecha_legible(fecha_publicacion)
    if fecha_legible:
        builder.add_header_badge(f"Publicacion: {fecha_legible}", tone="info")
    if fechas_datos:
        builder.add_header_badge(
            f"Fecha de posición: {', '.join(fechas_datos)}",
            tone="subtle",
        )
    if trm_formada is not None:
        tasa_trm = f"{float(trm_formada):,.2f}".translate(str.maketrans(",.", ".,"))
        builder.add_header_badge(f"TRM FORMADA: {tasa_trm}", tone="info")
    if es_preliminar and promedio_setfx is not None:
        valor_setfx = pd.to_numeric(pd.Series([promedio_setfx]), errors="coerce").iloc[0]
        if pd.isna(valor_setfx) or float(valor_setfx) <= 0:
            raise ValueError(
                f"PROMEDIO SETFX invalido para el dashboard preliminar: {promedio_setfx}"
            )
        tasa = f"{float(valor_setfx):,.2f}".translate(str.maketrans(",.", ".,"))
        builder.add_header_badge(f"PROMEDIO SETFX: {tasa}", tone="warning")

    return builder


def add_sections(builder: Any) -> None:
    """Define las tres secciones visibles del dashboard."""
    builder.add_section(
        "posicion_actual",
        "Posicion actual",
        subtitle="Vista resumida del portafolio",
        description="Usa filtros globales para acotar el universo y luego define la categoria de lectura de esta seccion.",
    )
    builder.add_section(
        "historico",
        "Histórico",
        subtitle="Evolucion mensual de la posición",
        description="La serie usa la misma logica de filtros globales, con su propia categoria local y rango de fechas.",
    )
    builder.add_section(
        "posicion_total",
        "Posición total",
        subtitle="Detalle completo de la posición",
        description="Detalle completo del universo visible despues de aplicar los filtros globales.",
    )


def add_datasets(builder: Any, tables: dict[str, pd.DataFrame]) -> None:
    """Registra las tablas que consumen filtros, graficas y tablas."""
    builder.add_dataset(DATASET_CURRENT_CHART, tables[DATASET_CURRENT_CHART])
    builder.add_dataset(DATASET_CURRENT_DETAIL, tables[DATASET_CURRENT_DETAIL])
    builder.add_dataset(DATASET_HISTORICAL_CHART, tables[DATASET_HISTORICAL_CHART])
    builder.add_dataset(DATASET_GLOBAL_FILTERS, tables[DATASET_GLOBAL_FILTERS])


def add_global_filters(builder: Any) -> None:
    """Filtros que afectan todo el dashboard."""
    for filter_spec in GLOBAL_FILTER_SPECS:
        builder.add_filter(
            filter_spec["id"],
            DATASET_GLOBAL_FILTERS,
            filter_spec["column"],
            label=filter_spec["label"],
            kind="multi_select",
            default=filter_spec["default"],
            helper_text="Si no escoges valores, ese filtro no se aplica al resto del dashboard.",
            open=filter_spec["open"],
            datasets=GLOBAL_FILTER_DATASETS,
        )
        builder.filters[-1]["dynamic_options"] = True
        builder.filters[-1]["empty_label"] = "Todos"
        builder.filters[-1]["bulk_actions"] = True


def add_current_position_filters(builder: Any) -> None:
    """Filtros locales de la seccion Posicion actual."""
    builder.add_filter(
        "f_posicion_categoria",
        DATASET_CURRENT_CHART,
        "COLUMNA_GRAFICA",
        label="Categoria",
        kind="select",
        default="LB_LT",
        options=CATEGORY_COLUMN_OPTIONS,
        helper_text="Define la categoria que organiza la grafica y la tabla de esta seccion.",
        section="posicion_actual",
    )
    builder.filters[-1]["allow_empty"] = False

    builder.add_filter(
        "f_posicion_valor_categoria",
        DATASET_CURRENT_CHART,
        "GRUPO_GRAFICA",
        label="Valor categoria",
        kind="multi_select",
        helper_text="Acota los grupos visibles dentro de la categoria elegida.",
        section="posicion_actual",
    )
    builder.filters[-1]["dynamic_options"] = True
    builder.filters[-1]["empty_label"] = "Todos"


def add_historical_filters(builder: Any, historical_df: pd.DataFrame) -> None:
    """Filtros locales de la seccion Historico."""
    builder.add_filter(
        "f_historico_categoria",
        DATASET_HISTORICAL_CHART,
        "COLUMNA_GRAFICA",
        label="Categoria",
        kind="select",
        default="LB_LT",
        options=CATEGORY_COLUMN_OPTIONS,
        helper_text="Define la categoria que controla las lineas visibles en el historico.",
        section="historico",
    )
    builder.filters[-1]["allow_empty"] = False

    builder.add_filter(
        "f_historico_valor_categoria",
        DATASET_HISTORICAL_CHART,
        "GRUPO_GRAFICA",
        label="Valor categoria",
        kind="multi_select",
        helper_text="Permite quedarte con uno o varios grupos de la categoria elegida.",
        section="historico",
    )
    builder.filters[-1]["dynamic_options"] = True
    builder.filters[-1]["empty_label"] = "Todos"

    builder.add_filter(
        "f_historico_fecha",
        DATASET_HISTORICAL_CHART,
        DATE_COLUMN,
        label="Fecha historica",
        kind="date_range",
        default=None,
        helper_text="Sin seleccion muestra todos los cierres; puedes acotar un rango mensual.",
        open=True,
        section="historico",
    )
    builder.filters[-1]["empty_label"] = "Todos los cierres"


def add_filters(builder: Any, tables: dict[str, pd.DataFrame]) -> None:
    """Agrupa todos los filtros en un solo punto."""
    add_global_filters(builder)
    add_current_position_filters(builder)
    add_historical_filters(builder, tables["historical_raw"])


POSITION_ABBREVIATIONS_HELPER = (
    "Abreviaturas: k = miles; MM = millones; Blls = mil millones en USD "
    "y millón de millones en COP."
)


def _position_dual_y_axis(
    tasa_escala: float | None,
    scale_label: str = "TRM FORMADA",
) -> dict[str, Any]:
    """Configuracion compartida por las graficas actual e historica."""
    tasa = pd.to_numeric(pd.Series([tasa_escala]), errors="coerce").iloc[0]
    if pd.isna(tasa) or float(tasa) <= 0:
        raise ValueError(
            f"{scale_label} invalido para escalar la grafica: {tasa_escala}"
        )
    return {
        "primary_value": "COP",
        "primary_title": "Posicion COP",
        "secondary_value": "USD",
        "secondary_title": "Posicion USD",
        "scale_factor": float(tasa),
        "scale_label": scale_label,
        "abbreviations": {
            "thousand_suffix": "k",
            "million_suffix": "MM",
            "billion_suffix": "Blls",
            "billion_divisors": {
                "COP": 1_000_000_000_000,
                "USD": 1_000_000_000,
            },
        },
    }


def add_current_position_cards(
    builder: Any,
    accounting_context: dict[str, Any] = POSITION_ACCOUNTING_CONTEXT,
    trm_formada: float | None = None,
    scale_label: str = "TRM FORMADA",
) -> None:
    """Grafica y tabla de la seccion Posicion actual."""
    builder.bar(
        "posicion_por_grupo",
        DATASET_CURRENT_CHART,
        group="GRUPO_GRAFICA",
        value=POSITION_COLUMN,
        agg="sum",
        color="MONEDA_POSICION",
        palette_by_bar=True,
        dual_y_axis=_position_dual_y_axis(trm_formada, scale_label),
        # Cero desactiva el Top N: se muestran todos los books y nunca se
        # agrega la categoria artificial "Otros". Los valores en cero se
        # conservan como categoria, aunque no tengan una barra visible.
        top_n=0,
        # Las abreviaturas son propias del negocio y cambian el umbral de Blls
        # segun la moneda. El hover conserva siempre el valor completo.
        y_axis_title="Posicion por moneda (k / MM / Blls)",
        section="posicion_actual",
        title="Posicion por categoria",
        subtitle="La categoria y sus valores se controlan desde los filtros locales de esta seccion",
        helper_text=POSITION_ABBREVIATIONS_HELPER,
        layout={"span": "seven", "height": 330},
        icon="DRTB"
        )

    builder.table(
        "tabla_total",
        DATASET_CURRENT_CHART,
        groupby={
            "cols": ["GRUPO_GRAFICA", "MONEDA_POSICION"],
            "aggs": [{"col": POSITION_COLUMN, "op": "sum", "as": "POSICION_TOTAL"}],
        },
        columns=SUMMARY_TABLE_COLUMNS,
        context_label=accounting_context,
        sort={"by": "POSICION_TOTAL", "order": "desc"},
        totals={
            "label": "Total",
            "label_column": "GRUPO_GRAFICA",
            "group_by": "MONEDA_POSICION",
            "columns": {"POSICION_TOTAL": "sum"},
        },
        caption="Resumen por categoria y moneda; los totales no mezclan COP con USD",
        section="posicion_actual",
        title="Total por categoria y moneda",
        subtitle="La tabla y su pie presentan un total independiente por moneda",
        layout={"span": "five", "height": 330},
        icon="DRTB"
    )


def add_historical_cards(
    builder: Any,
    trm_formada: float | None = None,
    scale_label: str = "TRM FORMADA",
) -> None:
    """Grafica de la seccion Historico."""
    builder.line(
        "serie_historica_posicion",
        DATASET_HISTORICAL_CHART,
        x=DATE_COLUMN,
        y=POSITION_COLUMN,
        color="GRUPO_GRAFICA",
        axis_group="MONEDA_POSICION",
        dual_y_axis=_position_dual_y_axis(trm_formada, scale_label),
        y_axis_title="Posicion por moneda (k / MM / Blls)",
        agg="sum",
        markers=True,
        smooth=True,
        range_slider=True,
        x_period_label="month_year",
        section="historico",
        title="Serie historica de la posicion",
        subtitle="Cada punto corresponde al corte mensual de la posicion",
        helper_text=POSITION_ABBREVIATIONS_HELPER,
        layout={"span": "full", "height": 500, "min_height": 380},
        icon="DRTB"
        )


def add_detail_cards(
    builder: Any,
    accounting_context: dict[str, Any] = POSITION_ACCOUNTING_CONTEXT,
) -> None:
    """Tabla grande de detalle."""
    builder.table(
        "tabla_tbl_posicion",
        DATASET_CURRENT_DETAIL,
        columns=DETAIL_TABLE_COLUMNS,
        context_label=accounting_context,
        totals={
            "label": "Total",
            "label_column": "PRODUCTO",
            "group_by": "MONEDA_POSICION",
            "columns": {POSITION_COLUMN: "sum"},
        },
        caption="Detalle completo de la posicion visible tras los filtros globales",
        section="posicion_total",
        title="Detalle completo de la posicion",
        subtitle="Consulta total para revision ejecutiva y operativa",
        layout={"span": "full", "height": 480},
        icon="DRTB"
    )


def add_cards(
    builder: Any,
    accounting_context: dict[str, Any] = POSITION_ACCOUNTING_CONTEXT,
    trm_formada: float | None = None,
    scale_label: str = "TRM FORMADA",
) -> None:
    """Agrupa todas las visualizaciones del dashboard."""
    add_current_position_cards(
        builder,
        accounting_context=accounting_context,
        trm_formada=trm_formada,
        scale_label=scale_label,
    )
    add_historical_cards(
        builder,
        trm_formada=trm_formada,
        scale_label=scale_label,
    )
    add_detail_cards(builder, accounting_context=accounting_context)


def build_dashboard(
    ruta_dashy: str | Path | None = None,
    pruebas: bool = False,
    fecha_publicacion: str | None = None,
    current_df: pd.DataFrame | None = None,
    historical_df: pd.DataFrame | None = None,
    output_path: str | Path | None = None,
    estado_corte: str | None = None,
    productos_pendientes: list[str] | None = None,
    promedio_setfx: float | None = None,
    trm_formada: float | None = None,
    advertencias: list[str] | None = None,
) -> Path:
    """Construye el HTML final."""
    tables = load_dashboard_tables(
        pruebas=pruebas,
        current_override=current_df,
        historical_override=historical_df,
    )
    es_preliminar = str(estado_corte or "").upper() in {
        "PRELIMINAR_INTRADIA",
        "INTRADIA",
        "INTRADÍA",
    }
    tasa_dashboard, etiqueta_tasa = _resolver_tasa_escala_dashboard(
        tables["current_raw"],
        estado_corte=estado_corte,
        promedio_setfx=promedio_setfx,
        trm_formada=trm_formada,
    )
    builder = create_builder(
        ruta_dashy=ruta_dashy,
        fecha_publicacion=fecha_publicacion,
        fechas_datos=_fechas_de_datos(tables["current_raw"]),
        estado_corte=estado_corte,
        productos_pendientes=productos_pendientes,
        promedio_setfx=promedio_setfx,
        trm_formada=None if es_preliminar else tasa_dashboard,
        advertencias=advertencias,
    )
    add_sections(builder)
    add_datasets(builder, tables)
    add_filters(builder, tables)
    contexto = (
        POSITION_ACCOUNTING_CONTEXT_PRELIMINAR
        if es_preliminar
        else POSITION_ACCOUNTING_CONTEXT
    )
    add_cards(
        builder,
        accounting_context=contexto,
        trm_formada=tasa_dashboard,
        scale_label=etiqueta_tasa,
    )
    destino = Path(output_path) if output_path else OUTPUT_PATH
    destino.parent.mkdir(parents=True, exist_ok=True)
    output = builder.export(str(destino), logs_dir=str(LOGS_DIR))
    return Path(output)


if __name__ == "__main__":
    html_path = build_dashboard()
    print(f"HTML generado: {html_path.resolve()}")
