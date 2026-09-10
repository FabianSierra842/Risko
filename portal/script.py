# -*- coding: utf-8 -*-
from __future__ import annotations

import getpass
import hashlib
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import calendar as calendar_module
import ctypes
from ctypes import wintypes
from fnmatch import fnmatch
import json
import mimetypes
import os
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from urllib.parse import parse_qs, quote, unquote, urlparse
import uuid
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageChops, ImageTk
except ImportError:
    Image = None
    ImageChops = None
    ImageTk = None

try:
    import holidays as country_holidays
except ImportError:
    country_holidays = None


APP_NAME = "Portal Risko"
APP_VERSION = "2.1.15"
PREVIEW_RENDER_VERSION = 4
DASHBOARD_MANIFEST_NAME = "dashboard.json"
DAILY_COMMENTS_FOLDER_NAME = "Comentarios diarios"
NEWS_FOLDER_NAME = "Novedades"
MAX_DAILY_COMMENT_BYTES = 256 * 1024
DEFAULT_SHARED_ROOT = Path(
    r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\Proyecto Risko"
)
DEFAULT_PRODUCTION_ROOT = Path(
    r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado"
)


def _portal_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "_internal").exists() and exe_dir.parent.name.lower() == "portal":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path | None:
    folder = getattr(sys, "_MEIPASS", None)
    return Path(folder).resolve() if folder else None


def _risk_root(portal_dir: Path) -> Path:
    configured = os.environ.get("PORTAL_RISKO_ROOT")
    if configured:
        return Path(configured).resolve()

    candidate = portal_dir.parent
    if (candidate / "datos").exists() and (candidate / "portal").exists():
        return candidate.resolve()

    return DEFAULT_SHARED_ROOT.resolve()


PORTAL_DIR = _portal_dir()
RISK_ROOT = _risk_root(PORTAL_DIR)
BUNDLE_DIR = _bundle_dir()

# Notas para mover el portal a otra carpeta compartida:
# - PORTAL_DIR queda apuntando a la carpeta donde viva script.py o el .exe.
#   En build tipo carpeta, si el .exe esta en portal/PortalRisko, se usa portal
#   como raiz operativa para conservar las configuraciones en el mismo lugar.
# - RISK_ROOT apunta al proyecto compartido. Primero respeta PORTAL_RISKO_ROOT,
#   luego detecta la estructura local y, si el .exe fue movido a cualquier otra
#   carpeta, usa DEFAULT_SHARED_ROOT. Ese valor es la ruta que se debe cambiar si
#   el proyecto se publica en otra carpeta compartida del banco.
# - El portal NO necesita ejecutar Dashy ni el demo web. De Dashy solo usa el logo
#   de RISKO para la cabecera. En el .exe ese logo queda embebido; en modo script,
#   si no se mueve la carpeta Herramientas/dashy, copiar al menos logo-risko-56.png
#   o logo-risko.png y cambiar LOGO_RISKO_PNG abajo.
# - PUBLISHED_DIR es la biblioteca de produccion donde estan los HTML finales.
#   Se puede cambiar editando el valor por defecto o definiendo la variable de
#   entorno PORTAL_RISKO_PUBLICADOS antes de iniciar el portal.
# - CONFIG_DIR es donde se guardan favoritos y configuraciones por usuario.
#   Por defecto usa %LOCALAPPDATA%\PortalRisko\Configuraciones, junto a la
#   instalacion local. La biblioteca productiva se consume solo con lectura.
#   PORTAL_RISKO_CONFIG_DIR admite una ruta local alternativa para pruebas o
#   contingencias; la antigua ruta compartida se reconoce y migra en lectura.
DASHY_DIR = RISK_ROOT / "Herramientas" / "dashy"
# DEMO_DIR queda como referencia visual/historica. No es requerido para operar.
DEMO_DIR = RISK_ROOT / "Herramientas" / "DEMO" / "risko-demo"
LOGO_DIR = BUNDLE_DIR if BUNDLE_DIR is not None else DASHY_DIR
INTERFACE_ASSETS_DIR = RISK_ROOT / "aplicaciones" / "interfaz_risko" / "assets"
BRAND_ASSETS_DIR = BUNDLE_DIR if BUNDLE_DIR is not None else INTERFACE_ASSETS_DIR
LOGO_RISKO_PNG = BRAND_ASSETS_DIR / "logo-risko-alta-resolucion.png"
LOGO_RISKO_PNG_FALLBACK = LOGO_DIR / "logo-risko-56.png"
LOGO_RISKO_SVG = LOGO_DIR / "LOGO RISKO.svg"
LOGO_BANCO_PNG = BRAND_ASSETS_DIR / "escudo-banco-bogota-sin-fondo.png"
ICON_PORTAL = (
    (BUNDLE_DIR if BUNDLE_DIR is not None else PORTAL_DIR / "assets")
    / "portal-risko.ico"
)

PUBLISHED_DIR = Path(
    os.environ.get(
        "PORTAL_RISKO_PUBLICADOS",
        DEFAULT_PRODUCTION_ROOT / "Dashboards",
    )
).resolve()
APPLICATIONS_DIR = Path(
    os.environ.get(
        "PORTAL_RISKO_APLICACIONES",
        DEFAULT_PRODUCTION_ROOT / "Aplicaciones",
    )
).resolve()
COMMENTS_DIR = Path(
    os.environ.get(
        "PORTAL_RISKO_COMENTARIOS",
        DEFAULT_PRODUCTION_ROOT / DAILY_COMMENTS_FOLDER_NAME,
    )
).resolve()
NEWS_DIR = (COMMENTS_DIR / NEWS_FOLDER_NAME).resolve()
NEWS_FILE = NEWS_DIR / "novedad.md"


def _local_portal_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home()
    return (base / "PortalRisko").resolve()


def _legacy_production_config_dir() -> Path:
    production_root = os.environ.get(
        "PORTAL_RISKO_PRODUCCION",
        str(DEFAULT_PRODUCTION_ROOT),
    ).strip()
    return (Path(production_root) / "Configuraciones").resolve()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _resolved_config_dir() -> Path:
    """Elige almacenamiento local e ignora el override compartido heredado."""
    requested = os.environ.get("PORTAL_RISKO_CONFIG_DIR", "").strip()
    legacy = _legacy_production_config_dir()
    if requested:
        candidate = Path(requested).resolve()
        if not _same_path(candidate, legacy):
            return candidate
    return _local_portal_data_root() / "Configuraciones"


LEGACY_CONFIG_DIR = _legacy_production_config_dir()
CONFIG_DIR = _resolved_config_dir()


PALETTE = {
    "primary": "#003c86",
    "secondary": "#214a8b",
    "deep": "#081f3d",
    "accent": "#f7bb26",
    "accent_dark": "#d99a11",
    "bg": "#edf2f8",
    "surface": "#ffffff",
    "surface_alt": "#f7f9fc",
    "line": "#d5dfec",
    "text": "#111c2d",
    "muted": "#506078",
    "soft_blue": "#eaf2fb",
    "soft_gold": "#fff5d8",
    "success": "#0f8a7a",
    "danger": "#b42318",
    "disabled": "#9aacbf",
}

DATE_FILTERS = (
    "Todos",
    "Hoy",
    "Ultimas 24 horas",
    "Ultimos 7 dias",
    "Ultimos 30 dias",
)
SECTIONS = ("Todos", "Favoritos", "Recientes")
SPANISH_MONTHS = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)
SPANISH_MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
VERSION_DATE_PATTERNS = (
    re.compile(r"(?<!\d)(20\d{2})[-_./](\d{1,2})[-_./](\d{1,2})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,2})[-_./](\d{1,2})[-_./](20\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)"),
)
PREVIEW_BROWSER_LOCK = threading.Lock()


class RoundedCard(tk.Canvas):
    """Contenedor con fondo y borde redondeados que admite grid/pack internos."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        radius: int = 16,
        fill: str = PALETTE["surface"],
        outline: str = PALETTE["line"],
    ) -> None:
        try:
            parent_bg = str(parent.cget("bg"))
        except tk.TclError:
            parent_bg = PALETTE["bg"]
        super().__init__(
            parent,
            bg=parent_bg,
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
        )
        self._card_radius = radius
        self._card_fill = fill
        self._card_outline = outline
        self.bind("<Configure>", self._draw_rounded_background, add="+")

    def _draw_rounded_background(self, event: tk.Event | None = None) -> None:
        width = max(2, int(event.width if event is not None else self.winfo_width()))
        height = max(2, int(event.height if event is not None else self.winfo_height()))
        radius = max(4, min(self._card_radius, width // 2, height // 2))
        self.delete("_rounded_card")
        points = (
            radius,
            1,
            width - radius,
            1,
            width - 1,
            1,
            width - 1,
            radius,
            width - 1,
            height - radius,
            width - 1,
            height - 1,
            width - radius,
            height - 1,
            radius,
            height - 1,
            1,
            height - 1,
            1,
            height - radius,
            1,
            radius,
            1,
            1,
        )
        self.create_polygon(
            points,
            smooth=True,
            splinesteps=24,
            fill=self._card_fill,
            outline=self._card_outline,
            width=1,
            tags=("_rounded_card",),
        )
        self.tag_lower("_rounded_card")


@dataclass(frozen=True)
class UserIdentity:
    domain: str
    username: str
    display: str
    safe_key: str


@dataclass(frozen=True)
class DashboardFile:
    path: Path
    relative: str
    title: str
    file_name: str
    folder: str
    modified_ts: float
    size_bytes: int
    kind: str = "dashboard"
    version_date: str = ""
    published_ts: float = 0.0
    publisher: str = ""
    cut_type: str = ""
    data_dates: tuple[str, ...] = ()
    dashboard_id: str = ""
    description: str = ""
    coverage: str = ""
    audience: str = ""
    configurations_enabled: bool = False


@dataclass(frozen=True)
class DashboardDefinition:
    root: Path
    relative_root: str
    dashboard_id: str
    name: str
    description: str = ""
    coverage: str = ""
    audience: str = ""
    entrypoint: str = ""
    configurations_enabled: bool = False
    has_manifest: bool = False


@dataclass(frozen=True)
class DailyComment:
    date: date
    path: Path
    content: str
    modified_ts: float


def _current_user() -> UserIdentity:
    username = os.environ.get("USERNAME") or getpass.getuser() or "usuario"
    domain = os.environ.get("USERDOMAIN") or socket.gethostname() or "LOCAL"
    display = f"{domain}\\{username}"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{domain}_{username}").strip("._")
    return UserIdentity(domain=domain, username=username, display=display, safe_key=safe or "usuario")


def _config_path(user: UserIdentity) -> Path:
    return CONFIG_DIR / f"{user.safe_key}.json"


def _dashboard_config_dir(user: UserIdentity) -> Path:
    return CONFIG_DIR / "dashboards" / user.safe_key


def _safe_dashboard_key(relative: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", relative).strip("._")[:90] or "dashboard"
    digest = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:10]
    return f"{slug}_{digest}"


def _dashboard_configuration_scope(relative: str) -> str:
    """Comparte configuraciones entre fechas del mismo dashboard lógico."""
    parts = relative.replace("\\", "/").split("/")
    for index, part in enumerate(parts[:-1]):
        if index > 0 and _parse_version_date(part) is not None:
            return "/".join([*parts[:index], parts[-1]])
    return relative


def _dashboard_config_path(user: UserIdentity, relative: str) -> Path:
    scope = _dashboard_configuration_scope(relative)
    return _dashboard_config_dir(user) / f"{_safe_dashboard_key(scope)}.json"


def _default_config(user: UserIdentity) -> dict:
    return {
        "version": 1,
        "app": APP_NAME,
        "user": {"domain": user.domain, "username": user.username, "display": user.display},
        "filters": {"section": "Todos", "search": "", "date_range": "Todos"},
        "favorites": [],
        "recents": [],
        "last_selected": "",
        "last_opened": "",
        "sort": {"column": "modified", "descending": True},
        "window": {"geometry": "1360x820"},
    }


def _deep_merge(base: dict, incoming: dict) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _copy_legacy_config_file(source: Path, target: Path) -> None:
    """Copia una preferencia heredada sin escribir ni modificar su origen."""
    if target.exists() or not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.migrating")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _migrate_legacy_user_config(user: UserIdentity) -> None:
    """Migra una sola vez preferencias compartidas al perfil local del usuario."""
    if _same_path(CONFIG_DIR, LEGACY_CONFIG_DIR):
        return
    try:
        _copy_legacy_config_file(
            LEGACY_CONFIG_DIR / f"{user.safe_key}.json",
            _config_path(user),
        )
        legacy_dashboard_dir = LEGACY_CONFIG_DIR / "dashboards" / user.safe_key
        if legacy_dashboard_dir.is_dir():
            for source in legacy_dashboard_dir.glob("*.json"):
                _copy_legacy_config_file(
                    source,
                    _dashboard_config_dir(user) / source.name,
                )
    except OSError:
        # La carpeta compartida puede no existir o no estar visible. El Portal
        # conserva su operacion normal con una configuracion local nueva.
        return


def _load_config(user: UserIdentity) -> dict:
    config = _default_config(user)
    _migrate_legacy_user_config(user)
    path = _config_path(user)
    if not path.exists():
        return config
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return config
    if isinstance(loaded, dict):
        _deep_merge(config, loaded)
    return config


def _save_config(path: Path, config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config["saved_at"] = datetime.now().isoformat(timespec="seconds")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _read_dashboard_configs(user: UserIdentity, relative: str) -> dict:
    path = _dashboard_config_path(user, relative)
    legacy_path = _dashboard_config_dir(user) / f"{_safe_dashboard_key(relative)}.json"
    if not path.exists() and legacy_path != path and legacy_path.exists():
        path = legacy_path
    if not path.exists():
        return {
            "version": 1,
            "dashboard": relative,
            "user": user.display,
            "active_id": "",
            "favorite_id": "",
            "configurations": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "version": 1,
            "dashboard": relative,
            "user": user.display,
            "active_id": "",
            "favorite_id": "",
            "configurations": [],
        }
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", 1)
    data["dashboard"] = relative
    data["user"] = user.display
    data.setdefault("active_id", "")
    data.setdefault("favorite_id", "")
    data.setdefault("configurations", [])
    if not isinstance(data["configurations"], list):
        data["configurations"] = []
    return data


def _write_dashboard_configs(user: UserIdentity, relative: str, data: dict) -> None:
    folder = _dashboard_config_dir(user)
    folder.mkdir(parents=True, exist_ok=True)
    path = _dashboard_config_path(user, relative)
    data["version"] = 1
    data["dashboard"] = relative
    data["user"] = user.display
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _read_html_title(path: Path) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:80_000]
    except OSError:
        return ""
    match = re.search(r"<title[^>]*>(.*?)</title>", head, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return html.unescape(title)


def _friendly_name(stem: str) -> str:
    text = re.sub(r"[_-]+", " ", stem).strip()
    return text.title() if text else stem


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _dashboard_manifest_root(path: Path) -> tuple[Path, dict[str, object]] | None:
    """Busca el manifiesto más cercano sin salir de la biblioteca publicada."""
    current = path.parent
    while _inside(current, PUBLISHED_DIR):
        manifest_path = current / DASHBOARD_MANIFEST_NAME
        if manifest_path.is_file():
            manifest = _read_json_object(manifest_path)
            if manifest:
                return current, manifest
        if _same_path(current, PUBLISHED_DIR):
            break
        current = current.parent
    return None


def _configuration_is_enabled(manifest: dict[str, object]) -> bool:
    value = manifest.get("configuracion", manifest.get("configurations", False))
    if isinstance(value, bool):
        return value
    if not isinstance(value, dict):
        return False
    enabled = value.get("habilitada", value.get("enabled", False))
    return enabled is True


def _dashboard_definition(path: Path) -> DashboardDefinition:
    manifest_match = _dashboard_manifest_root(path)
    manifest: dict[str, object] = {}
    if manifest_match is not None:
        root, manifest = manifest_match
        has_manifest = True
    else:
        try:
            relative = path.relative_to(PUBLISHED_DIR)
        except ValueError:
            relative = Path(path.name)
        root = PUBLISHED_DIR / relative.parts[0] if len(relative.parts) > 1 else PUBLISHED_DIR
        has_manifest = False

    try:
        relative_root = root.relative_to(PUBLISHED_DIR).as_posix()
    except ValueError:
        relative_root = root.name
    if relative_root == ".":
        relative_root = ""

    default_name = (
        _friendly_name(root.name)
        if relative_root
        else (_read_html_title(path) or _friendly_name(path.stem))
    )

    def text_value(*keys: str) -> str:
        for key in keys:
            value = manifest.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    dashboard_id = text_value("id") or relative_root or path.stem
    return DashboardDefinition(
        root=root,
        relative_root=relative_root,
        dashboard_id=dashboard_id,
        name=text_value("nombre", "name", "titulo", "title") or default_name,
        description=text_value("descripcion", "description"),
        coverage=text_value("cobertura", "coverage"),
        audience=text_value("audiencia", "audience"),
        entrypoint=text_value("archivo", "entrypoint").replace("\\", "/"),
        configurations_enabled=_configuration_is_enabled(manifest),
        has_manifest=has_manifest,
    )


def _matches_manifest_entrypoint(path: Path, definition: DashboardDefinition) -> bool:
    pattern = definition.entrypoint.strip().lstrip("./")
    if not pattern:
        return True
    if "/" not in pattern:
        return fnmatch(path.name.casefold(), pattern.casefold())
    try:
        relative = path.relative_to(definition.root).as_posix()
    except ValueError:
        return False
    return fnmatch(relative.casefold(), pattern.casefold())


def _declared_publication_entrypoint(folder: Path) -> str:
    metadata = _read_json_object(folder / "publicacion.json")
    value = metadata.get("archivo")
    return value.strip() if isinstance(value, str) else ""


def _dashboard_configurations_enabled(relative: str) -> bool:
    path = (PUBLISHED_DIR / relative).resolve()
    if not _inside(path, PUBLISHED_DIR) or not path.is_file():
        return False
    return _dashboard_definition(path).configurations_enabled


def _parse_version_date(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for index, pattern in enumerate(VERSION_DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        try:
            if index == 1:
                day, month, year = (int(part) for part in match.groups())
            else:
                year, month, day = (int(part) for part in match.groups())
            return datetime(year, month, day)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_publication_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _parse_version_date(text)


def _publication_metadata(path: Path, modified_ts: float) -> dict[str, object]:
    metadata_path = path.parent / "publicacion.json"
    metadata: dict[str, object] = {}
    if metadata_path.is_file():
        try:
            loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                configured_file = str(loaded.get("archivo") or "").strip()
                if not configured_file or configured_file.casefold() == path.name.casefold():
                    metadata = loaded
        except (OSError, json.JSONDecodeError):
            metadata = {}

    version = _parse_version_date(metadata.get("fecha_publicacion"))
    if version is None:
        for part in reversed(path.parts):
            version = _parse_version_date(part)
            if version is not None:
                break
    if version is None:
        version = datetime.fromtimestamp(modified_ts)

    published = _parse_publication_datetime(metadata.get("publicado_en"))
    published_ts = published.timestamp() if published is not None else modified_ts
    data_dates = metadata.get("fechas_datos")
    raw_cut_type = str(metadata.get("tipo_corte") or metadata.get("estado") or "").strip().upper()
    cut_type = "INTRADÍA" if raw_cut_type in {"INTRADIA", "INTRADÍA", "PRELIMINAR_INTRADIA"} else "CIERRE"
    return {
        "version_date": version.strftime("%Y-%m-%d"),
        "published_ts": published_ts,
        "publisher": str(metadata.get("publicado_por") or ""),
        "cut_type": cut_type,
        "data_dates": tuple(
            str(item) for item in data_dates if str(item).strip()
        )
        if isinstance(data_dates, list)
        else (),
    }


def _version_datetime(dashboard: DashboardFile) -> datetime:
    timestamp = dashboard.published_ts or dashboard.modified_ts
    return datetime.fromtimestamp(timestamp)


def _position_dates(dashboard: DashboardFile) -> tuple[datetime, ...]:
    parsed = tuple(
        value
        for value in (
            _parse_version_date(item)
            for item in dashboard.data_dates
        )
        if value is not None
    )
    if parsed:
        return tuple(sorted(parsed))
    reference = _parse_version_date(dashboard.version_date)
    if reference is not None:
        return (reference,)
    return (datetime.fromtimestamp(dashboard.modified_ts),)


def _position_date(dashboard: DashboardFile) -> datetime:
    """Fecha efectiva de la posición; usa la referencia legada solo como respaldo."""
    return _position_dates(dashboard)[-1]


def _version_date(dashboard: DashboardFile) -> datetime:
    """Alias compatible: en la interfaz una versión representa una posición."""
    return _position_date(dashboard)


def _format_version_date(dashboard: DashboardFile) -> str:
    value = _version_date(dashboard)
    return _format_calendar_date(value.date())


def _format_calendar_date(value: date) -> str:
    return f"{value.day:02d} {SPANISH_MONTHS[value.month - 1]} {value.year}"


def _daily_comment_candidates(value: date) -> tuple[Path, ...]:
    """Rutas admitidas, priorizando la estructura anual y Markdown."""
    iso_date = value.isoformat()
    year_dir = COMMENTS_DIR / str(value.year)
    return (
        year_dir / f"{iso_date}.md",
        year_dir / f"{iso_date}.txt",
        COMMENTS_DIR / f"{iso_date}.md",
        COMMENTS_DIR / f"{iso_date}.txt",
    )


def _read_daily_comment(value: date) -> DailyComment | None:
    """Lee un comentario diario UTF-8 sin permitir archivos excesivos."""
    for candidate in _daily_comment_candidates(value):
        try:
            if not candidate.is_file():
                continue
            stat = candidate.stat()
            if stat.st_size > MAX_DAILY_COMMENT_BYTES:
                raise RuntimeError(
                    f"El comentario {candidate.name} supera "
                    f"{MAX_DAILY_COMMENT_BYTES // 1024} KB."
                )
            content = candidate.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"El comentario {candidate.name} debe guardarse en UTF-8."
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"No se pudo leer el comentario {candidate.name}: {exc}"
            ) from exc

        content = (
            content.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\u00a0", " ")
            .strip()
        )
        if not content:
            return None
        return DailyComment(
            date=value,
            path=candidate,
            content=content,
            modified_ts=stat.st_mtime,
        )
    return None


def _novedades_summary() -> str:
    """Lee la unica notificacion global del portal."""
    if not NEWS_FILE.is_file():
        return "Sin novedades publicadas"
    try:
        content = NEWS_FILE.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeDecodeError):
        return "Sin novedades publicadas"
    return content or "Sin novedades publicadas"


def _latest_publication_summary(
    dashboards: list[DashboardFile],
    selected: DashboardFile | None = None,
) -> str:
    """Resume el HTML mas reciente del dashboard seleccionado."""
    if selected is not None:
        group_key = _resource_group_key(selected)
        dashboards = [
            dashboard
            for dashboard in dashboards
            if _resource_group_key(dashboard) == group_key
        ]
    if not dashboards:
        return "Última publicación: sin publicaciones"
    latest_position = max(_position_date(dashboard) for dashboard in dashboards)
    latest = max(
        (
            dashboard
            for dashboard in dashboards
            if _position_date(dashboard) == latest_position
        ),
        key=lambda dashboard: dashboard.published_ts,
    )
    published = datetime.fromtimestamp(latest.published_ts)
    position = _format_calendar_date(_position_date(latest).date())
    return (
        f"Última publicación: Posición {position} · "
        f"{latest.cut_type or 'CIERRE'} · "
        f"Actualizado {published:%d/%m/%Y %H:%M}"
    )


def _markdown_table_cells(line: str) -> list[str] | None:
    """Separa una fila de tabla Markdown simple; exige al menos dos columnas."""
    stripped = line.strip()
    if "|" not in stripped:
        return None
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells = [cell.strip() for cell in stripped.split("|")]
    return cells if len(cells) >= 2 else None


def _is_markdown_table_separator(line: str) -> bool:
    cells = _markdown_table_cells(line)
    return bool(
        cells
        and all(re.fullmatch(r":?-{3,}:?", cell) is not None for cell in cells)
    )


def _markdown_comment_blocks(content: str) -> list[tuple[str, str]]:
    """Convierte el subconjunto editorial de Markdown en bloques seguros."""
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_lines:
            text = " ".join(line.strip() for line in paragraph_lines if line.strip())
            if text:
                blocks.append(("paragraph", text))
            paragraph_lines.clear()

    lines = content.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            index += 1
            continue
        table_header = _markdown_table_cells(line)
        if (
            table_header is not None
            and index + 1 < len(lines)
            and _is_markdown_table_separator(lines[index + 1])
        ):
            flush_paragraph()
            separator_cells = _markdown_table_cells(lines[index + 1]) or []
            index += 2
            table_rows: list[list[str]] = []
            while index < len(lines):
                table_row = _markdown_table_cells(lines[index])
                if table_row is None:
                    break
                if len(table_row) < len(table_header):
                    table_row.extend([""] * (len(table_header) - len(table_row)))
                table_rows.append(table_row[: len(table_header)])
                index += 1

            column_widths = [
                max(
                    len(row[column])
                    for row in [table_header, *table_rows]
                )
                for column in range(len(table_header))
            ]

            def format_table_row(cells: list[str], *, header: bool = False) -> str:
                formatted: list[str] = []
                for column, width in enumerate(column_widths):
                    cell = cells[column]
                    separator = (
                        separator_cells[column]
                        if column < len(separator_cells)
                        else "---"
                    )
                    if header or not separator.endswith(":"):
                        formatted.append(cell.ljust(width))
                    elif separator.startswith(":"):
                        formatted.append(cell.center(width))
                    else:
                        formatted.append(cell.rjust(width))
                return " │ ".join(formatted).rstrip()

            blocks.append(
                ("table_header", format_table_row(table_header, header=True))
            )
            blocks.extend(
                ("table_row", format_table_row(table_row))
                for table_row in table_rows
            )
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            blocks.append((f"h{len(heading.group(1))}", heading.group(2).strip()))
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet:
            flush_paragraph()
            blocks.append(("bullet", bullet.group(1).strip()))
            index += 1
            continue
        numbered = re.match(r"^(\d+)[.)]\s+(.+)$", line)
        if numbered:
            flush_paragraph()
            blocks.append(
                ("numbered", f"{numbered.group(1)}. {numbered.group(2).strip()}")
            )
            index += 1
            continue
        paragraph_lines.append(line)
        index += 1
    flush_paragraph()
    return blocks


_COLOMBIA_HOLIDAYS: dict[int, object] = {}


def _is_colombia_business_day(value: date) -> bool:
    if value.weekday() >= 5:
        return False
    if country_holidays is None:
        return True
    holiday_calendar = _COLOMBIA_HOLIDAYS.get(value.year)
    if holiday_calendar is None:
        holiday_calendar = country_holidays.Colombia(years=value.year)
        _COLOMBIA_HOLIDAYS[value.year] = holiday_calendar
    return value not in holiday_calendar


def _format_position_dates(dashboard: DashboardFile) -> str:
    return ", ".join(
        f"{value.day:02d} {SPANISH_MONTHS[value.month - 1]} {value.year}"
        for value in _position_dates(dashboard)
    )


def _format_publication_datetime(dashboard: DashboardFile) -> str:
    value = _version_datetime(dashboard)
    return (
        f"{value.day:02d} {SPANISH_MONTHS[value.month - 1]} "
        f"{value.year} · {value:%H:%M}"
    )


def _resource_group_key(dashboard: DashboardFile) -> str:
    if dashboard.kind == "application":
        return f"application:{dashboard.relative.casefold()}"
    if dashboard.dashboard_id:
        return f"dashboard:{dashboard.dashboard_id.casefold()}"
    parts = dashboard.relative.split("/")
    for index, part in enumerate(parts[:-1]):
        if _parse_version_date(part) is not None and index > 0:
            return "dashboard:" + "/".join(parts[:index]).casefold()
    stem = Path(parts[-1]).stem
    for pattern in VERSION_DATE_PATTERNS:
        stem = pattern.sub("", stem)
    stable = re.sub(r"[_\-. ]+", " ", stem).strip().casefold()
    folder = "/".join(parts[:-1]).casefold()
    return f"dashboard:{folder}/{stable}"


def _resource_group_title(dashboard: DashboardFile) -> str:
    if dashboard.kind == "application":
        return dashboard.title
    if dashboard.dashboard_id:
        return dashboard.title
    parts = dashboard.relative.split("/")
    for index, part in enumerate(parts[:-1]):
        if _parse_version_date(part) is not None and index > 0:
            return _friendly_name(parts[index - 1])
    return dashboard.title


def _latest_position_relative(
    dashboards: list[DashboardFile],
    preferred_relative: str | None,
) -> str | None:
    """Conserva el recurso elegido, pero apunta a su mayor fecha de posicion."""
    if not preferred_relative:
        return None
    preferred = next(
        (item for item in dashboards if item.relative == preferred_relative),
        None,
    )
    if preferred is None:
        return None
    group_key = _resource_group_key(preferred)
    versions = [
        item for item in dashboards if _resource_group_key(item) == group_key
    ]
    if not versions:
        return preferred.relative
    return max(
        versions,
        key=lambda item: (
            _position_date(item),
            _version_datetime(item),
            item.modified_ts,
            item.relative,
        ),
    ).relative


def _scan_dashboards() -> list[DashboardFile]:
    if not PUBLISHED_DIR.exists():
        return []
    dashboards: list[DashboardFile] = []
    html_paths = sorted(
        {
            *PUBLISHED_DIR.rglob("*.html"),
            *PUBLISHED_DIR.rglob("*.htm"),
        },
        key=lambda item: str(item).casefold(),
    )
    for path in html_paths:
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            relative = path.relative_to(PUBLISHED_DIR).as_posix()
            folder = path.parent.relative_to(PUBLISHED_DIR).as_posix()
        except OSError:
            continue
        definition = _dashboard_definition(path)
        if not _matches_manifest_entrypoint(path, definition):
            continue
        declared_entrypoint = _declared_publication_entrypoint(path.parent)
        if declared_entrypoint and declared_entrypoint.casefold() != path.name.casefold():
            continue
        publication = _publication_metadata(path, stat.st_mtime)
        dashboards.append(
            DashboardFile(
                path=path,
                relative=relative,
                title=definition.name,
                file_name=path.name,
                folder="" if folder == "." else folder,
                modified_ts=stat.st_mtime,
                size_bytes=stat.st_size,
                kind="dashboard",
                version_date=str(publication["version_date"]),
                published_ts=float(publication["published_ts"]),
                publisher=str(publication["publisher"]),
                cut_type=str(publication["cut_type"]),
                data_dates=tuple(publication["data_dates"]),
                dashboard_id=definition.dashboard_id,
                description=definition.description,
                coverage=definition.coverage,
                audience=definition.audience,
                configurations_enabled=definition.configurations_enabled,
            )
        )
    return dashboards


def _scan_applications() -> list[DashboardFile]:
    if not APPLICATIONS_DIR.exists():
        return []
    applications: list[DashboardFile] = []
    for path in sorted(APPLICATIONS_DIR.rglob("*.exe")):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            app_relative = path.relative_to(APPLICATIONS_DIR).as_posix()
            folder = path.parent.relative_to(APPLICATIONS_DIR).as_posix()
        except OSError:
            continue
        applications.append(
            DashboardFile(
                path=path,
                relative=f"Aplicaciones/{app_relative}",
                title=_friendly_name(path.stem),
                file_name=path.name,
                folder="Aplicaciones" if folder == "." else f"Aplicaciones/{folder}",
                modified_ts=stat.st_mtime,
                size_bytes=stat.st_size,
                kind="application",
                version_date=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                published_ts=stat.st_mtime,
            )
        )
    return applications


def _scan_resources() -> list[DashboardFile]:
    return [*_scan_dashboards(), *_scan_applications()]


def _format_datetime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _format_size(num_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def _dashboard_label(dashboard: DashboardFile) -> str:
    if dashboard.kind == "application":
        title = dashboard.title
        if title.casefold() in {"aplicaciones mercado", "dash aplicaciones mercado"}:
            title = "Centro de Información Riesgos de Mercado"
        return f"{title} · Aplicacion"
    if dashboard.folder:
        return f"{dashboard.title} · {dashboard.folder.replace('/', ' / ')}"
    return dashboard.title


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _dashboard_profile(dashboard: DashboardFile | None) -> dict[str, str]:
    if dashboard is None:
        return {
            "title": "Seleccione un recurso",
            "description": "Seleccione un dashboard para consultar sus versiones disponibles.",
            "coverage": "No disponible",
            "audience": "No disponible",
            "status": "Pendiente de selección",
        }
    available = dashboard.path.is_file()
    if dashboard.kind == "application":
        title = dashboard.title
        if title.casefold() in {"aplicaciones mercado", "dash aplicaciones mercado"}:
            title = "Centro de Información Riesgos de Mercado"
        return {
            "title": title,
            "description": f"Aplicación Windows publicada en {dashboard.folder}.",
            "coverage": dashboard.folder or "Aplicaciones",
            "audience": "No disponible",
            "status": "Disponible" if available else "Archivo no disponible",
        }
    return {
        "title": _resource_group_title(dashboard),
        "description": dashboard.description
        or f"Dashboard HTML publicado en {dashboard.folder or 'Dashboards'}.",
        "coverage": dashboard.coverage or dashboard.folder or "Dashboards",
        "audience": dashboard.audience or "No disponible",
        "status": (
            f"{dashboard.cut_type} · Disponible"
            if available and dashboard.cut_type
            else "Disponible" if available else "Archivo no disponible"
        ),
    }


@dataclass(frozen=True)
class MonitorWorkArea:
    handle: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(1, self.right - self.left)

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)


@dataclass(frozen=True)
class ExternalLaunch:
    process: subprocess.Popen | None
    positioning_requested: bool


class _WinPoint(ctypes.Structure):
    _fields_ = (("x", wintypes.LONG), ("y", wintypes.LONG))


class _WinRect(ctypes.Structure):
    _fields_ = (
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    )


class _MonitorInfo(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _WinRect),
        ("rcWork", _WinRect),
        ("dwFlags", wintypes.DWORD),
    )


MONITOR_DEFAULTTONEAREST = 2
SW_RESTORE = 9
SW_MAXIMIZE = 3


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def get_monitor_from_point(x: int, y: int) -> int | None:
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.argtypes = (_WinPoint, wintypes.DWORD)
    user32.MonitorFromPoint.restype = wintypes.HANDLE
    handle = user32.MonitorFromPoint(
        _WinPoint(int(x), int(y)),
        MONITOR_DEFAULTTONEAREST,
    )
    return int(handle) if handle else None


def get_monitor_work_area(monitor: int | None) -> MonitorWorkArea | None:
    if os.name != "nt" or not monitor:
        return None
    user32 = ctypes.windll.user32
    user32.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MonitorInfo))
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not user32.GetMonitorInfoW(wintypes.HANDLE(monitor), ctypes.byref(info)):
        return None
    work = info.rcWork
    return MonitorWorkArea(
        handle=monitor,
        left=int(work.left),
        top=int(work.top),
        right=int(work.right),
        bottom=int(work.bottom),
    )


def _cursor_monitor_work_area() -> MonitorWorkArea | None:
    if os.name != "nt":
        return None
    point = _WinPoint()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        return None
    return get_monitor_work_area(get_monitor_from_point(point.x, point.y))


def get_current_interface_monitor(root: tk.Tk) -> MonitorWorkArea | None:
    root.update_idletasks()
    center_x = root.winfo_rootx() + max(1, root.winfo_width()) // 2
    center_y = root.winfo_rooty() + max(1, root.winfo_height()) // 2
    return get_monitor_work_area(get_monitor_from_point(center_x, center_y))


def _tk_top_level_hwnd(root: tk.Tk) -> int:
    hwnd = int(root.winfo_id())
    if os.name != "nt":
        return hwnd
    user32 = ctypes.windll.user32
    while True:
        parent = int(user32.GetParent(hwnd) or 0)
        if not parent:
            return hwnd
        hwnd = parent


def get_window_dpi(root: tk.Tk) -> int:
    if os.name != "nt":
        return 96
    try:
        user32 = ctypes.windll.user32
        get_dpi = user32.GetDpiForWindow
        get_dpi.argtypes = (wintypes.HWND,)
        get_dpi.restype = wintypes.UINT
        dpi = int(get_dpi(wintypes.HWND(_tk_top_level_hwnd(root))) or 0)
        return dpi if dpi > 0 else 96
    except Exception:
        return 96


def maximize_on_monitor(root: tk.Tk) -> None:
    work = _cursor_monitor_work_area()
    if work is None:
        try:
            root.state("zoomed")
        except tk.TclError:
            pass
        return

    root.state("normal")
    initial_width = max(
        320,
        min(work.width - 40, max(720, int(work.width * 0.78))),
    )
    initial_height = max(
        280,
        min(work.height - 40, max(520, int(work.height * 0.78))),
    )
    initial_x = work.left + (work.width - initial_width) // 2
    initial_y = work.top + (work.height - initial_height) // 2
    root.geometry(
        f"{initial_width}x{initial_height}{initial_x:+d}{initial_y:+d}"
    )
    root.update_idletasks()
    try:
        root.state("zoomed")
        root.update_idletasks()
        if root.state() == "zoomed":
            return
    except tk.TclError:
        pass

    if os.name == "nt":
        try:
            hwnd = _tk_top_level_hwnd(root)
            ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
            root.update_idletasks()
            if ctypes.windll.user32.IsZoomed(hwnd):
                return
            ctypes.windll.user32.MoveWindow(
                hwnd,
                work.left,
                work.top,
                work.width,
                work.height,
                True,
            )
            return
        except Exception:
            pass
    root.geometry(
        f"{work.width}x{work.height}{work.left:+d}{work.top:+d}"
    )


def _visible_windows_for_pid(process_id: int) -> list[int]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HWND,
        wintypes.LPARAM,
    )

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) == process_id and user32.IsWindowVisible(hwnd):
            if user32.GetWindowTextLengthW(hwnd) > 0:
                handles.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return handles


def _move_window_to_monitor(hwnd: int, work: MonitorWorkArea) -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        moved = user32.MoveWindow(
            hwnd,
            work.left,
            work.top,
            work.width,
            work.height,
            True,
        )
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return bool(moved)
    except Exception:
        return False


def _browser_candidates() -> list[Path]:
    candidates: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", "")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
    for base in (local_app_data, program_files, program_files_x86):
        if not base:
            continue
        candidates.extend(
            [
                Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
        )
    unique: list[Path] = []
    known: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in known:
            unique.append(candidate)
            known.add(key)
    return unique


def _local_preview_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home()
    return base / "PortalRisko" / "Preview"


def _capture_dashboard_preview(
    url: str,
    target: Path,
    *,
    focus_position_chart: bool = False,
) -> Path:
    """Renderiza el dashboard real y guarda una vista previa local en PNG."""
    browser = next(
        (candidate for candidate in _browser_candidates() if candidate.is_file()),
        None,
    )
    if browser is None:
        raise FileNotFoundError("No se encontró Microsoft Edge o Google Chrome.")

    target.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    raw = target.parent / f".{target.stem}.{token}.raw.png"
    processed = target.parent / f".{target.stem}.{token}.tmp.png"
    profile = target.parent / "browser-profile"
    capture_url = url
    window_height = 1800
    if focus_position_chart:
        separator = "&" if "?" in url else "?"
        capture_url = f"{url}{separator}risko_preview=1"
        window_height = 760
    arguments = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=7000",
        f"--user-data-dir={profile}",
        f"--window-size=1280,{window_height}",
        f"--screenshot={raw}",
        capture_url,
    ]
    if focus_position_chart:
        arguments.insert(-2, "--force-device-scale-factor=1.25")
    try:
        with PREVIEW_BROWSER_LOCK:
            result = subprocess.run(
                arguments,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=35,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        if result.returncode != 0 or not raw.is_file() or raw.stat().st_size == 0:
            raise RuntimeError("El navegador no pudo renderizar la vista previa.")

        if Image is None:
            os.replace(raw, target)
            return target

        with Image.open(raw) as screenshot:
            image = screenshot.convert("RGB")
            if focus_position_chart:
                if ImageChops is not None:
                    background = Image.new("RGB", image.size, "#edf2f8")
                    bounds = ImageChops.difference(image, background).getbbox()
                else:
                    bounds = None
                if bounds is not None:
                    padding = 14
                    left = max(0, bounds[0] - padding)
                    top = max(0, bounds[1] - padding)
                    right = min(image.width, bounds[2] + padding)
                    bottom = min(image.height, bounds[3] + padding)
                    image = image.crop((left, top, right, bottom))
            image.save(processed, format="PNG", optimize=True)
        os.replace(processed, target)
        return target
    finally:
        for temporary in (raw, processed):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _open_dashboard_window(
    url: str,
    work_area: MonitorWorkArea | None = None,
) -> ExternalLaunch:
    for browser in _browser_candidates():
        if browser.exists():
            arguments = [
                str(browser),
                f"--app={url}",
                "--new-window",
                "--start-maximized",
            ]
            positioning_requested = work_area is not None
            if work_area is not None:
                arguments.extend(
                    [
                        f"--window-position={work_area.left},{work_area.top}",
                        f"--window-size={work_area.width},{work_area.height}",
                    ]
                )
            process = subprocess.Popen(
                arguments,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ExternalLaunch(process, positioning_requested)

    webbrowser.open(url)
    return ExternalLaunch(None, False)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


class PortalDashboardServer:
    def __init__(self, user: UserIdentity) -> None:
        self.user = user
        self.lock = threading.Lock()
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> None:
        if self.httpd is not None:
            return
        state = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PortalRiskoBridge/1.3"

            def log_message(self, _format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                state.handle_get(self)

            def do_POST(self) -> None:
                state.handle_post(self)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = int(self.httpd.server_address[1])
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        self.thread = None

    def dashboard_url(self, relative: str) -> str:
        self.start()
        return f"http://127.0.0.1:{self.port}/dashboard/{quote(relative, safe='/')}"

    def handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        if parsed.path.startswith("/dashboard/"):
            relative = unquote(parsed.path.removeprefix("/dashboard/"))
            self._serve_dashboard_file(handler, relative)
            return
        if parsed.path == "/api/configurations":
            query = parse_qs(parsed.query)
            dashboard = query.get("dashboard", [""])[0]
            if not dashboard:
                _json_response(handler, 400, {"ok": False, "error": "dashboard requerido"})
                return
            if not _dashboard_configurations_enabled(dashboard):
                _json_response(
                    handler,
                    403,
                    {
                        "ok": False,
                        "error": "configuraciones no parametrizadas para este dashboard",
                    },
                )
                return
            with self.lock:
                data = _read_dashboard_configs(self.user, dashboard)
            _json_response(handler, 200, {"ok": True, **data})
            return
        _json_response(handler, 404, {"ok": False, "error": "recurso no encontrado"})

    def handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        length = int(handler.headers.get("Content-Length", "0") or "0")
        try:
            body = json.loads(handler.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            _json_response(handler, 400, {"ok": False, "error": "JSON invalido"})
            return
        if not isinstance(body, dict):
            _json_response(handler, 400, {"ok": False, "error": "JSON invalido"})
            return

        parsed = urlparse(handler.path)
        dashboard = str(body.get("dashboard") or "")
        if not dashboard:
            _json_response(handler, 400, {"ok": False, "error": "dashboard requerido"})
            return
        if not _dashboard_configurations_enabled(dashboard):
            _json_response(
                handler,
                403,
                {
                    "ok": False,
                    "error": "configuraciones no parametrizadas para este dashboard",
                },
            )
            return

        if parsed.path == "/api/configurations/save":
            self._save_dashboard_configuration(handler, dashboard, body)
            return
        if parsed.path == "/api/configurations/delete":
            self._delete_dashboard_configuration(handler, dashboard, body)
            return
        if parsed.path == "/api/configurations/active":
            self._set_active_dashboard_configuration(handler, dashboard, body)
            return
        if parsed.path == "/api/configurations/favorite":
            self._set_favorite_dashboard_configuration(handler, dashboard, body)
            return
        _json_response(handler, 404, {"ok": False, "error": "recurso no encontrado"})

    def _serve_dashboard_file(self, handler: BaseHTTPRequestHandler, relative: str) -> None:
        path = (PUBLISHED_DIR / relative).resolve()
        if not _inside(path, PUBLISHED_DIR) or not path.is_file():
            handler.send_error(404, "Archivo no encontrado")
            return
        tipo, _ = mimetypes.guess_type(str(path))
        try:
            data = path.read_bytes()
        except OSError:
            handler.send_error(500, "No se pudo leer el archivo")
            return

        if path.suffix.lower() in {".html", ".htm"}:
            if _dashboard_configurations_enabled(relative):
                text = data.decode("utf-8", errors="ignore")
                text = self._inject_dashboard_tools(text, relative)
                data = text.encode("utf-8")
            tipo = "text/html; charset=utf-8"

        handler.send_response(200)
        handler.send_header("Content-Type", tipo or "application/octet-stream")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(data)

    def _save_dashboard_configuration(self, handler: BaseHTTPRequestHandler, dashboard: str, body: dict) -> None:
        name = str(body.get("name") or "").strip() or "Mi configuracion"
        filters = body.get("filters") if isinstance(body.get("filters"), dict) else {}
        theme_name = str(body.get("themeName") or "")
        config_id = str(body.get("id") or "").strip()
        now = datetime.now().isoformat(timespec="seconds")

        with self.lock:
            data = _read_dashboard_configs(self.user, dashboard)
            items = [item for item in data.get("configurations", []) if isinstance(item, dict)]
            existing = None
            for item in items:
                same_id = config_id and item.get("id") == config_id
                same_name = not config_id and str(item.get("name", "")).strip().lower() == name.lower()
                if same_id or same_name:
                    existing = item
                    break
            if existing is None:
                existing = {"id": config_id or uuid.uuid4().hex[:12], "created_at": now}
                items.append(existing)
            existing.update(
                {
                    "name": name,
                    "filters": filters,
                    "themeName": theme_name,
                    "updated_at": now,
                }
            )
            data["configurations"] = items
            data["active_id"] = existing["id"]
            _write_dashboard_configs(self.user, dashboard, data)
        _json_response(handler, 200, {"ok": True, **data})

    def _delete_dashboard_configuration(self, handler: BaseHTTPRequestHandler, dashboard: str, body: dict) -> None:
        config_id = str(body.get("id") or "")
        with self.lock:
            data = _read_dashboard_configs(self.user, dashboard)
            items = [item for item in data.get("configurations", []) if item.get("id") != config_id]
            data["configurations"] = items
            if data.get("active_id") == config_id:
                data["active_id"] = items[0]["id"] if items else ""
            if data.get("favorite_id") == config_id:
                data["favorite_id"] = ""
            _write_dashboard_configs(self.user, dashboard, data)
        _json_response(handler, 200, {"ok": True, **data})

    def _set_active_dashboard_configuration(self, handler: BaseHTTPRequestHandler, dashboard: str, body: dict) -> None:
        config_id = str(body.get("id") or "")
        with self.lock:
            data = _read_dashboard_configs(self.user, dashboard)
            valid = any(item.get("id") == config_id for item in data.get("configurations", []))
            data["active_id"] = config_id if valid else ""
            _write_dashboard_configs(self.user, dashboard, data)
        _json_response(handler, 200, {"ok": True, **data})

    def _set_favorite_dashboard_configuration(self, handler: BaseHTTPRequestHandler, dashboard: str, body: dict) -> None:
        config_id = str(body.get("id") or "")
        with self.lock:
            data = _read_dashboard_configs(self.user, dashboard)
            valid = any(item.get("id") == config_id for item in data.get("configurations", []))
            data["favorite_id"] = config_id if valid else ""
            _write_dashboard_configs(self.user, dashboard, data)
        _json_response(handler, 200, {"ok": True, **data})

    def _inject_dashboard_tools(self, html_text: str, relative: str) -> str:
        settings = {
            "dashboard": relative,
            "user": self.user.display,
            "username": self.user.username,
            "apiBase": "",
        }
        injection = f"""
<style>
  #risko-config-shell {{
    margin: 8px auto 10px;
    width: min(1500px, calc(100% - 32px));
    font-family: "Segoe UI", Arial, sans-serif;
    color: #111c2d;
    background: rgba(255,255,255,.98);
    border: 1px solid rgba(17, 28, 45, .10);
    box-shadow: 0 10px 28px rgba(17, 28, 45, .10);
    position: relative;
    z-index: 10;
  }}
  #risko-config-shell * {{ box-sizing: border-box; }}
  .risko-config-top {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-left: 5px solid #f7bb26;
  }}
  .risko-config-brand {{
    min-width: 118px;
    padding: 8px 12px;
    color: #fff;
    background: linear-gradient(135deg, #003c86, #214a8b);
    font-weight: 800;
    letter-spacing: .04em;
  }}
  .risko-config-main {{ flex: 1 1 auto; min-width: 320px; }}
  .risko-config-kicker {{
    color: #003c86;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: .08em;
  }}
  .risko-config-title {{
    margin-top: 2px;
    font-size: 13px;
    font-weight: 750;
  }}
  .risko-config-controls {{
    display: flex;
    align-items: end;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .risko-config-field {{ display: grid; gap: 4px; }}
  .risko-config-field span {{
    color: #506078;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
  }}
  .risko-config-field input,
  .risko-config-field select {{
    min-height: 34px;
    min-width: 170px;
    border: 1px solid #d4deec;
    background: #fff;
    color: #111c2d;
    padding: 0 10px;
    font: inherit;
  }}
  .risko-config-button {{
    min-height: 34px;
    border: 0;
    padding: 0 13px;
    font-weight: 800;
    cursor: pointer;
    color: #003c86;
    background: #eaf2fb;
  }}
  .risko-config-button:hover {{ background: #dce9f7; }}
  .risko-config-button--primary {{
    color: #fff;
    background: linear-gradient(135deg, #003c86, #0d5bc2);
  }}
  .risko-config-button--primary:hover {{ background: #214a8b; }}
  .risko-config-button--danger {{
    color: #b42318;
    background: #fff0ef;
  }}
  .risko-config-status {{
    padding: 0 12px 10px 135px;
    color: #506078;
    font-size: 11px;
  }}
  html.risko-preview-mode,
  html.risko-preview-mode body {{
    margin: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
    background: #edf2f8 !important;
  }}
  html.risko-preview-mode body > * {{ display: none !important; }}
  html.risko-preview-mode body > .app-shell {{ display: block !important; }}
  html.risko-preview-mode body > .app-shell > * {{ display: none !important; }}
  html.risko-preview-mode body main.content {{
    display: block !important;
    width: 100% !important;
    max-width: none !important;
    margin: 0 !important;
    padding: 12px !important;
  }}
  html.risko-preview-mode main.content > .section-panel {{
    display: none !important;
  }}
  html.risko-preview-mode main.content > #posicion_actual {{
    display: block !important;
    margin: 0 !important;
    padding: 0 !important;
  }}
  html.risko-preview-mode #posicion_actual > .section-panel__head,
  html.risko-preview-mode #posicion_actual > .section-panel__guide,
  html.risko-preview-mode #posicion_actual > .section-filters {{
    display: none !important;
  }}
  html.risko-preview-mode #posicion_actual > .dashboard-grid {{
    margin: 0 !important;
    gap: 12px !important;
  }}
  html.risko-preview-mode #posicion_actual .card {{
    box-shadow: none !important;
  }}
  @media (max-width: 900px) {{
    .risko-config-top {{ align-items: stretch; flex-direction: column; }}
    .risko-config-brand {{ min-width: 0; }}
    .risko-config-status {{ padding-left: 16px; }}
  }}
</style>
<script>
window.__RISKO_PORTAL__ = {json.dumps(settings, ensure_ascii=False)};
(function () {{
  "use strict";
  var previewMode = new URLSearchParams(window.location.search).get("risko_preview") === "1";
  if (previewMode) document.documentElement.classList.add("risko-preview-mode");
  var settings = window.__RISKO_PORTAL__;
  var apiBase = settings.apiBase || "";
  var activeData = null;

  function qs(selector, root) {{ return (root || document).querySelector(selector); }}
  function qsa(selector, root) {{ return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }}
  function normalize(value) {{ return value === null || value === undefined ? "" : String(value); }}
  function canonicalFilterValue(filterId, value) {{
    var text = normalize(value);
    if (filterId === "f_global_lb_lt" && text.toUpperCase() === "TESORERIA") return "Trading";
    return value;
  }}
  function toArray(value) {{
    if (Array.isArray(value)) return value.slice();
    if (value === null || value === undefined || value === "") return [];
    return [value];
  }}
  function cssEscape(value) {{
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value));
    return String(value).replace(/["\\\\]/g, "\\\\$&");
  }}
  function payload() {{ return window.__DASHY_PAYLOAD__ || null; }}
  function dashyFilters() {{ return payload() && Array.isArray(payload().filters) ? payload().filters : []; }}
  function hasDashyFilters() {{ return dashyFilters().length > 0 && !!qs(".filter-control"); }}
  function isPortalOwned(element) {{ return !!(element && element.closest && element.closest("#risko-config-shell")); }}
  function dispatchChange(control) {{
    if (!control) return;
    control.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}
  function controlKey(element) {{
    return (element.getAttribute("data-filter") || element.name || element.id || element.getAttribute("aria-label") || "").trim();
  }}
  function genericControls() {{
    var selector = [
      "select",
      "textarea",
      "input[type='checkbox']",
      "input[type='radio']",
      "input[type='date']",
      "input[type='text']",
      "input[type='search']",
      "input[type='number']",
      ".filter-control input",
      ".filter-control select",
      "[data-filter]"
    ].join(",");
    return qsa(selector).filter(function (element) {{
      return !isPortalOwned(element) && !!controlKey(element);
    }});
  }}
  function groupControls(controls) {{
    return controls.reduce(function (groups, control) {{
      var key = controlKey(control);
      groups[key] = groups[key] || [];
      groups[key].push(control);
      return groups;
    }}, {{}});
  }}
  function readGenericFilters() {{
    var grouped = groupControls(genericControls());
    var filters = {{}};
    Object.keys(grouped).forEach(function (key) {{
      var controls = grouped[key];
      var first = controls[0];
      var tag = first.tagName.toLowerCase();
      if (tag === "select") {{
        filters[key] = first.multiple ? qsa("option", first).filter(function (option) {{ return option.selected; }}).map(function (option) {{ return option.value; }}) : first.value;
      }} else if (first.type === "radio") {{
        var checkedRadio = controls.find(function (control) {{ return control.checked; }});
        filters[key] = checkedRadio ? checkedRadio.value : "";
      }} else if (first.type === "checkbox") {{
        filters[key] = controls.length === 1 ? !!first.checked : controls.filter(function (control) {{ return control.checked; }}).map(function (control) {{ return control.value; }});
      }} else {{
        filters[key] = first.value || "";
      }}
    }});
    return filters;
  }}
  function readDashyFilters() {{
    var filters = {{}};
    dashyFilters().forEach(function (filterDef) {{
      if (filterDef.kind === "date_range" || filterDef.kind === "number_range") {{
        var fromInput = qs("[data-filter-id='" + cssEscape(filterDef.id) + "'][data-filter-bound='from']");
        var toInput = qs("[data-filter-id='" + cssEscape(filterDef.id) + "'][data-filter-bound='to']");
        filters[filterDef.id] = {{ from: fromInput ? fromInput.value || "" : "", to: toInput ? toInput.value || "" : "" }};
        return;
      }}
      var choices = qsa("[data-filter-choice='" + cssEscape(filterDef.id) + "']");
      if (filterDef.kind === "select") {{
        var checked = choices.find(function (choice) {{ return choice.checked; }});
        filters[filterDef.id] = checked ? checked.value : "";
        return;
      }}
      filters[filterDef.id] = choices.filter(function (choice) {{
        return choice.checked && choice.value !== "";
      }}).map(function (choice) {{ return choice.value; }});
    }});
    return filters;
  }}
  function getCurrentFilters() {{ return hasDashyFilters() ? readDashyFilters() : readGenericFilters(); }}
  function applyGenericFilters(filters) {{
    var grouped = groupControls(genericControls());
    Object.keys(filters || {{}}).forEach(function (key) {{
      var controls = grouped[key];
      if (!controls || !controls.length) return;
      var first = controls[0];
      var nextValue = filters[key];
      var tag = first.tagName.toLowerCase();
      if (tag === "select") {{
        if (first.multiple && Array.isArray(nextValue)) {{
          qsa("option", first).forEach(function (option) {{ option.selected = nextValue.indexOf(option.value) !== -1; }});
        }} else {{
          first.value = nextValue || "";
        }}
        dispatchChange(first);
        return;
      }}
      if (first.type === "radio") {{
        controls.forEach(function (control) {{ control.checked = normalize(control.value) === normalize(nextValue); }});
        dispatchChange(controls[0]);
        return;
      }}
      if (first.type === "checkbox") {{
        if (controls.length === 1 && typeof nextValue === "boolean") {{
          first.checked = nextValue;
        }} else {{
          var desired = new Set(toArray(nextValue).map(normalize));
          controls.forEach(function (control) {{ control.checked = desired.has(normalize(control.value)); }});
        }}
        dispatchChange(controls[0]);
        return;
      }}
      first.value = nextValue || "";
      dispatchChange(first);
    }});
  }}
  function applyDashyFilters(filters) {{
    dashyFilters().forEach(function (filterDef) {{
      if (!Object.prototype.hasOwnProperty.call(filters || {{}}, filterDef.id)) return;
      var rawValue = filters[filterDef.id];
      if (Array.isArray(rawValue)) rawValue = rawValue.map(function (value) {{ return canonicalFilterValue(filterDef.id, value); }});
      else rawValue = canonicalFilterValue(filterDef.id, rawValue);
      if (filterDef.kind === "date_range" || filterDef.kind === "number_range") {{
        ["from", "to"].forEach(function (bound) {{
          var input = qs("[data-filter-id='" + cssEscape(filterDef.id) + "'][data-filter-bound='" + bound + "']");
          if (!input) return;
          input.value = rawValue && rawValue[bound] ? rawValue[bound] : "";
          dispatchChange(input);
        }});
        return;
      }}
      var choices = qsa("[data-filter-choice='" + cssEscape(filterDef.id) + "']");
      if (filterDef.kind === "select") {{
        choices.forEach(function (choice) {{ choice.checked = normalize(choice.value) === normalize(rawValue); }});
        dispatchChange(choices.find(function (choice) {{ return choice.checked; }}) || choices[0]);
        return;
      }}
      var selected = new Set(toArray(rawValue).map(normalize));
      choices.forEach(function (choice) {{ choice.checked = selected.has(normalize(choice.value)); }});
      dispatchChange(choices[0]);
    }});
  }}
  function applyFilters(filters) {{ hasDashyFilters() ? applyDashyFilters(filters) : applyGenericFilters(filters); }}
  function themeName() {{
    try {{ return window.localStorage.getItem("dashy.theme") || window.localStorage.getItem("dashlite.theme") || ""; }}
    catch (error) {{ return ""; }}
  }}
  function setStatus(message) {{
    var status = qs("#risko-config-status");
    if (status) status.textContent = message;
  }}
  function requestJson(path, options) {{
    var settingsRequest = options || {{}};
    settingsRequest.headers = Object.assign({{ "Content-Type": "application/json" }}, settingsRequest.headers || {{}});
    return fetch(apiBase + path, settingsRequest).then(function (response) {{
      return response.json().then(function (data) {{
        if (!response.ok || data.ok === false) throw new Error(data.error || "Solicitud no exitosa");
        return data;
      }});
    }});
  }}
  function renderConfigurations(data) {{
    activeData = data;
    var select = qs("#risko-config-select");
    if (!select) return;
    var previousId = select.value;
    select.innerHTML = "";
    var items = data.configurations || [];
    if (!items.length) {{
      var empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "Sin configuraciones guardadas";
      select.appendChild(empty);
      setStatus("No hay configuraciones guardadas para este dashboard y usuario.");
      return;
    }}
    items.slice().sort(function (a, b) {{ return String(b.updated_at || "").localeCompare(String(a.updated_at || "")); }}).forEach(function (item) {{
      var option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.name + (item.updated_at ? " - " + item.updated_at : "");
      select.appendChild(option);
    }});
    select.value = items.some(function (item) {{ return item.id === previousId; }}) ? previousId : (data.favorite_id || data.active_id || items[0].id);
    var active = items.find(function (item) {{ return item.id === select.value; }});
    var favoriteButton = qs("#risko-config-favorite");
    if (favoriteButton) favoriteButton.textContent = active && active.id === data.favorite_id ? "Quitar favorita" : "Marcar favorita";
    setStatus(active ? "Configuracion seleccionada: " + active.name + "." : "Seleccione una configuracion para actualizar la vista.");
  }}
  function restoreConfiguration(item, message, attempt) {{
    if (!item || !item.filters) return;
    var retries = attempt || 0;
    if (dashyFilters().length && !hasDashyFilters()) {{
      if (retries < 50) {{
        window.setTimeout(function () {{ restoreConfiguration(item, message, retries + 1); }}, 100);
      }} else {{
        setStatus("La configuracion se encontro, pero los filtros del dashboard no estuvieron listos para aplicarla.");
      }}
      return;
    }}
    applyFilters(item.filters);
    setStatus(message);
  }}
  function loadConfigurations(options) {{
    return requestJson("/api/configurations?dashboard=" + encodeURIComponent(settings.dashboard))
      .then(function (data) {{
        renderConfigurations(data);
        var shouldRestore = !options || options.restore !== false;
        var items = data.configurations || [];
        var targetId = previewMode ? data.favorite_id : (data.favorite_id || data.active_id);
        var active = items.find(function (item) {{ return item.id === targetId; }}) || (previewMode ? null : items[0]);
        if (shouldRestore && active && active.filters) {{
          restoreConfiguration(
            active,
            previewMode ? "Vista previa favorita: " + active.name + "." : "Configuracion aplicada automaticamente: " + active.name + ".",
            0
          );
        }}
        return data;
      }})
      .catch(function (error) {{ setStatus("No se pudieron leer configuraciones: " + error.message); }});
  }}
  function selectedConfiguration() {{
    if (!activeData) return null;
    var id = qs("#risko-config-select").value;
    return (activeData.configurations || []).find(function (item) {{ return item.id === id; }}) || null;
  }}
  function saveConfiguration() {{
    var nameInput = qs("#risko-config-name");
    var selected = selectedConfiguration();
    var body = {{
      dashboard: settings.dashboard,
      id: selected && nameInput && nameInput.value.trim() === selected.name ? selected.id : "",
      name: nameInput && nameInput.value.trim() ? nameInput.value.trim() : "Mi configuracion",
      filters: getCurrentFilters(),
      themeName: themeName()
    }};
    requestJson("/api/configurations/save", {{ method: "POST", body: JSON.stringify(body) }})
      .then(function (data) {{ renderConfigurations(data); setStatus("Configuracion guardada: " + body.name + "."); }})
      .catch(function (error) {{ setStatus("No se pudo guardar: " + error.message); }});
  }}
  function updateConfiguration() {{
    var item = selectedConfiguration();
    if (!item || !item.filters) {{ setStatus("No hay una configuracion guardada para actualizar la vista."); return; }}
    applyFilters(item.filters);
    requestJson("/api/configurations/active", {{ method: "POST", body: JSON.stringify({{ dashboard: settings.dashboard, id: item.id }}) }})
      .then(function (data) {{ renderConfigurations(data); setStatus("Vista actualizada con la configuracion: " + item.name + "."); }})
      .catch(function () {{ setStatus("La vista se actualizo localmente, pero no se pudo marcar la configuracion como activa."); }});
  }}
  function toggleFavoriteConfiguration() {{
    var item = selectedConfiguration();
    if (!item) {{ setStatus("No hay una configuracion seleccionada para marcar como favorita."); return; }}
    var nextId = activeData && activeData.favorite_id === item.id ? "" : item.id;
    requestJson("/api/configurations/favorite", {{ method: "POST", body: JSON.stringify({{ dashboard: settings.dashboard, id: nextId }}) }})
      .then(function (data) {{
        renderConfigurations(data);
        setStatus(nextId ? "Configuracion favorita para la vista previa: " + item.name + "." : "Se retiro la configuracion favorita; la vista previa usara la vista predeterminada.");
      }})
      .catch(function (error) {{ setStatus("No se pudo actualizar la configuracion favorita: " + error.message); }});
  }}
  function deleteConfiguration() {{
    var item = selectedConfiguration();
    if (!item) {{ setStatus("No hay una configuracion seleccionada para eliminar."); return; }}
    if (!window.confirm("Eliminar la configuracion '" + item.name + "'?")) return;
    requestJson("/api/configurations/delete", {{ method: "POST", body: JSON.stringify({{ dashboard: settings.dashboard, id: item.id }}) }})
      .then(function (data) {{ renderConfigurations(data); setStatus("Configuracion eliminada."); }})
      .catch(function (error) {{ setStatus("No se pudo eliminar: " + error.message); }});
  }}
  function buildShell() {{
    if (qs("#risko-config-shell")) return;
    var shell = document.createElement("section");
    shell.id = "risko-config-shell";
    shell.innerHTML = [
      "<div class='risko-config-top'>",
      "  <div class='risko-config-brand'>RISKO</div>",
      "  <div class='risko-config-main'>",
      "    <div class='risko-config-kicker'>Configuraciones por usuario Windows</div>",
      "    <div class='risko-config-title'>", settings.user.replace(/&/g, "&amp;").replace(/</g, "&lt;"), "</div>",
      "  </div>",
      "  <div class='risko-config-controls'>",
      "    <label class='risko-config-field'><span>Nombre</span><input id='risko-config-name' value='Mi configuracion'></label>",
      "    <label class='risko-config-field'><span>Guardadas</span><select id='risko-config-select'></select></label>",
      "    <button class='risko-config-button risko-config-button--primary' id='risko-config-save' type='button'>Guardar</button>",
      "    <button class='risko-config-button' id='risko-config-update' type='button'>Actualizar</button>",
      "    <button class='risko-config-button' id='risko-config-favorite' type='button'>Marcar favorita</button>",
      "    <button class='risko-config-button risko-config-button--danger' id='risko-config-delete' type='button'>Eliminar</button>",
      "  </div>",
      "</div>",
      "<div class='risko-config-status' id='risko-config-status'>Leyendo configuraciones...</div>"
    ].join("");
    var toolbar = qs(".toolbar") || qs("#filter-toolbar");
    if (toolbar && toolbar.parentNode) {{
      toolbar.parentNode.insertBefore(shell, toolbar);
    }} else {{
      document.body.insertBefore(shell, document.body.firstChild);
    }}
    qs("#risko-config-save").addEventListener("click", saveConfiguration);
    qs("#risko-config-update").addEventListener("click", updateConfiguration);
    qs("#risko-config-favorite").addEventListener("click", toggleFavoriteConfiguration);
    qs("#risko-config-delete").addEventListener("click", deleteConfiguration);
    qs("#risko-config-select").addEventListener("change", function () {{
      var item = selectedConfiguration();
      if (item) {{
        qs("#risko-config-name").value = item.name;
        qs("#risko-config-favorite").textContent = activeData && activeData.favorite_id === item.id ? "Quitar favorita" : "Marcar favorita";
        setStatus("Seleccionada: " + item.name + ".");
      }}
    }});
  }}
  function init() {{
    buildShell();
    loadConfigurations({{ restore: true }});
  }}
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {{ once: true }});
  else init();
}})();
</script>
"""
        if "</head>" in html_text.lower():
            index = html_text.lower().rfind("</head>")
            return html_text[:index] + injection + html_text[index:]
        if "</body>" in html_text.lower():
            index = html_text.lower().find("<body")
            body_end = html_text.find(">", index)
            if index >= 0 and body_end >= 0:
                return html_text[: body_end + 1] + injection + html_text[body_end + 1 :]
        return injection + html_text


class _LegacyPortalRiskoApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.user = _current_user()
        self.server = PortalDashboardServer(self.user)
        self.config_path = _config_path(self.user)
        self.config = _load_config(self.user)
        self.favorites: set[str] = set(self.config.get("favorites", []))
        self.recents: list[str] = list(self.config.get("recents", []))
        self.dashboards: list[DashboardFile] = []
        self.filtered: list[DashboardFile] = []
        self.combo_map: dict[str, str] = {}
        self.selected_relative: str | None = self.config.get("last_selected") or None
        self.save_after_id: str | None = None
        self.updating_combo = False
        self.logo_image: tk.PhotoImage | None = None
        self.bank_logo_image: tk.PhotoImage | None = None

        filters = self.config.get("filters", {})
        self.section_var = tk.StringVar(value=self._valid_option(filters.get("section"), SECTIONS, "Todos"))
        self.search_var = tk.StringVar(value=str(filters.get("search", "")))
        self.date_var = tk.StringVar(value=self._valid_option(filters.get("date_range"), DATE_FILTERS, "Todos"))
        self.dashboard_var = tk.StringVar(value="")
        self.sort_column = str(self.config.get("sort", {}).get("column", "modified"))
        self.sort_descending = bool(self.config.get("sort", {}).get("descending", True))

        self.title_var = tk.StringVar(value="Seleccione un recurso")
        self.description_var = tk.StringVar(value="")
        self.coverage_var = tk.StringVar(value="-")
        self.audience_var = tk.StringVar(value="-")
        self.status_dashboard_var = tk.StringVar(value="-")
        self.preference_var = tk.StringVar(value="Sin configuraciones guardadas para este usuario")
        self.user_pill_var = tk.StringVar(value=f"Usuario activo: {self.user.display}")
        self.runtime_var = tk.StringVar(value="Configuraciones: listas")
        self.count_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        self.section_buttons: dict[str, tk.Button] = {}
        self.action_buttons: list[tk.Button] = []
        self.tree: ttk.Treeview | None = None

        self._configure_root()
        self._configure_styles()
        self._load_logo()
        self._build_layout()
        self._bind_events()
        self.refresh_dashboards(keep_selection=True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    @staticmethod
    def _valid_option(value: object, options: tuple[str, ...], fallback: str) -> str:
        text = str(value or "")
        return text if text in options else fallback

    def _configure_root(self) -> None:
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        if ICON_PORTAL.is_file():
            try:
                self.root.iconbitmap(str(ICON_PORTAL))
            except tk.TclError:
                pass
        self.root.geometry(str(self.config.get("window", {}).get("geometry", "1360x820")))
        self.root.minsize(1120, 720)
        self.root.configure(bg=PALETTE["bg"])
        self.root.option_add("*Font", "{Segoe UI} 10")
        self.root.after(50, self._maximize_root)

    def _maximize_root(self) -> None:
        maximize_on_monitor(self.root)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Portal.Treeview",
            background=PALETTE["surface"],
            fieldbackground=PALETTE["surface"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["line"],
            rowheight=32,
            font=("Segoe UI", 9),
        )
        style.map("Portal.Treeview", background=[("selected", PALETTE["primary"])], foreground=[("selected", "#ffffff")])
        style.configure(
            "Portal.Treeview.Heading",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["text"],
            relief="flat",
            font=("Segoe UI Semibold", 8),
            padding=(8, 7),
        )
        style.configure("Portal.TCombobox", fieldbackground=PALETTE["surface"], background=PALETTE["surface"], padding=7)
        style.configure("Portal.Vertical.TScrollbar", troughcolor=PALETTE["surface_alt"], background="#b9c7d7")

    def _load_logo(self) -> None:
        for path in (LOGO_RISKO_PNG, LOGO_RISKO_PNG_FALLBACK):
            if path.exists():
                try:
                    self.logo_image = tk.PhotoImage(master=self.root, file=str(path))
                    break
                except tk.TclError:
                    continue
        if LOGO_BANCO_PNG.exists():
            try:
                self.bank_logo_image = tk.PhotoImage(master=self.root, file=str(LOGO_BANCO_PNG))
            except tk.TclError:
                self.bank_logo_image = None

    def _build_layout(self) -> None:
        outer = tk.Frame(self.root, bg=PALETTE["bg"])
        outer.pack(fill="both", expand=True, padx=22, pady=18)
        self._build_hero(outer)

        grid = tk.Frame(outer, bg=PALETTE["bg"])
        grid.pack(fill="both", expand=True, pady=(14, 0))

        left = self._card_frame(grid)
        left.pack(side="left", fill="both", expand=True)

        self._build_selection_card(left)
        self._build_status_bar(outer)

    def _build_hero(self, parent: tk.Widget) -> None:
        hero = tk.Frame(parent, bg=PALETTE["primary"], highlightthickness=0)
        hero.pack(fill="x")
        tk.Frame(hero, bg=PALETTE["accent"], height=5).pack(fill="x", side="top")

        content = tk.Frame(hero, bg=PALETTE["primary"])
        content.pack(fill="x", padx=26, pady=18)

        logo_box = tk.Frame(content, bg="#ffffff", highlightthickness=0)
        logo_box.pack(side="left", padx=(0, 22), pady=2)
        if self.bank_logo_image:
            tk.Label(logo_box, image=self.bank_logo_image, bg="#ffffff").pack(padx=18, pady=10)
        else:
            tk.Label(logo_box, text="BANCO DE BOGOTÁ", bg="#ffffff", fg=PALETTE["primary"], font=("Segoe UI Semibold", 14)).pack(
                padx=24, pady=12
            )

        title_box = tk.Frame(content, bg=PALETTE["primary"])
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text="PORTAL EJECUTIVO RISKO",
            bg=PALETTE["primary"],
            fg=PALETTE["accent"],
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Centro de Información Riesgos de Mercado",
            bg=PALETTE["primary"],
            fg="#ffffff",
            font=("Segoe UI Semibold", 23),
        ).pack(anchor="w", pady=(2, 4))
        tk.Label(
            title_box,
            text=(
                "Acceso centralizado a dashboards y aplicaciones publicados, "
                "con preferencias guardadas por usuario de Windows."
            ),
            bg=PALETTE["primary"],
            fg="#dce8f7",
            font=("Segoe UI", 10),
            wraplength=900,
            justify="left",
        ).pack(anchor="w")
        risko_box = tk.Frame(content, bg="#ffffff", highlightthickness=0)
        risko_box.pack(side="right", padx=(18, 0), pady=2)
        if self.logo_image:
            tk.Label(risko_box, image=self.logo_image, bg="#ffffff").pack(padx=18, pady=10)
        else:
            tk.Label(risko_box, text="RISKO", bg="#ffffff", fg=PALETTE["primary"], font=("Segoe UI Semibold", 20)).pack(
                padx=24, pady=12
            )

    def _card_frame(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=PALETTE["surface"], highlightthickness=1, highlightbackground="#dbe4ef")

    def _session_panel(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, bg=PALETTE["deep"], width=0, highlightthickness=0)
        panel.pack_propagate(False)
        return panel

    def _panel_fact(self, parent: tk.Widget, label: str, value: str) -> None:
        tk.Label(parent, text=label.upper(), bg=PALETTE["deep"], fg="#b9cbe1", font=("Segoe UI Semibold", 7)).pack(
            anchor="w", pady=(0, 3)
        )
        tk.Label(
            parent,
            text=value,
            bg=PALETTE["deep"],
            fg="#ffffff",
            font=("Segoe UI", 8),
            wraplength=285,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

    def _build_selection_card(self, parent: tk.Widget) -> None:
        section = tk.Frame(parent, bg=PALETTE["surface"])
        section.pack(fill="both", expand=True, padx=28, pady=(26, 24))
        tk.Label(section, text="SELECCION DE RECURSO", bg=PALETTE["surface"], fg=PALETTE["primary"], font=("Segoe UI Semibold", 8)).pack(
            anchor="w"
        )
        tk.Label(
            section,
            textvariable=self.title_var,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 20),
            wraplength=760,
            justify="left",
        ).pack(anchor="w", pady=(5, 5))
        tk.Label(
            section,
            textvariable=self.description_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 10),
            wraplength=880,
            justify="left",
        ).pack(anchor="w")

        details = tk.Frame(section, bg=PALETTE["surface"])
        details.pack(fill="x", pady=(16, 12))
        self._detail_card(details, "Alcance", self.coverage_var).grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._detail_card(details, "Audiencia", self.audience_var).grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self._detail_card(details, "Estado", self.status_dashboard_var).grid(row=0, column=2, sticky="ew")
        self._detail_card(details, "Configuraciones guardadas", self.preference_var).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        for column in range(3):
            details.columnconfigure(column, weight=1)

        controls = tk.Frame(section, bg=PALETTE["surface"])
        controls.pack(fill="x")
        picker = tk.Frame(controls, bg=PALETTE["surface"])
        picker.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._field_label(picker, "Dashboard o aplicacion").pack(anchor="w")
        self.dashboard_combo = ttk.Combobox(
            picker,
            textvariable=self.dashboard_var,
            values=(),
            state="readonly",
            style="Portal.TCombobox",
            font=("Segoe UI", 10),
        )
        self.dashboard_combo.pack(fill="x", ipady=6, pady=(4, 0))

        self.open_button = self._button(controls, "Abrir recurso", self.open_selected, "primary")
        self.open_button.pack(side="left", padx=(0, 8), pady=(18, 0))
        self.favorite_button = self._button(controls, "Marcar favorito", self.toggle_favorite, "secondary")
        self.favorite_button.pack(side="left", padx=(0, 8), pady=(18, 0))
        self.refresh_button = self._button(controls, "Actualizar", self.refresh_dashboards, "secondary")
        self.refresh_button.pack(side="left", pady=(18, 0))
        self.action_buttons = [self.open_button, self.favorite_button]

        pills = tk.Frame(section, bg=PALETTE["surface"])
        pills.pack(fill="x", pady=(14, 0))
        self._pill(pills, self.runtime_var, "#f1f3f6", PALETTE["muted"]).pack(side="left", padx=(0, 8))

    def _detail_card(self, parent: tk.Widget, label: str, variable: tk.StringVar) -> tk.Frame:
        frame = tk.Frame(parent, bg=PALETTE["surface_alt"], highlightthickness=1, highlightbackground="#e2e9f2")
        tk.Label(frame, text=label.upper(), bg=PALETTE["surface_alt"], fg=PALETTE["muted"], font=("Segoe UI Semibold", 7)).pack(
            anchor="w", padx=12, pady=(9, 0)
        )
        tk.Label(
            frame,
            textvariable=variable,
            bg=PALETTE["surface_alt"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 9),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(4, 10))
        return frame

    def _build_status_bar(self, parent: tk.Widget) -> None:
        bar = tk.Frame(parent, bg=PALETTE["surface"], highlightthickness=1, highlightbackground=PALETTE["line"])
        bar.pack(fill="x", pady=(10, 0))
        tk.Label(bar, textvariable=self.status_var, bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI", 8), anchor="w").pack(
            fill="x", padx=12, pady=7
        )

    def _field_label(self, parent: tk.Widget, text: str) -> tk.Label:
        return tk.Label(parent, text=text.upper(), bg=PALETTE["surface"], fg=PALETTE["muted"], font=("Segoe UI Semibold", 7))

    def _pill(self, parent: tk.Widget, variable: tk.StringVar, bg: str, fg: str) -> tk.Label:
        return tk.Label(parent, textvariable=variable, bg=bg, fg=fg, font=("Segoe UI Semibold", 8), padx=12, pady=8)

    def _button(self, parent: tk.Widget, text: str, command, variant: str) -> tk.Button:
        styles = {
            "primary": (PALETTE["primary"], "#ffffff", PALETTE["secondary"]),
            "secondary": (PALETTE["soft_blue"], PALETTE["primary"], "#dce9f7"),
            "accent": (PALETTE["accent"], "#1f2430", PALETTE["accent_dark"]),
            "panel": ("#ffffff", PALETTE["primary"], "#e7eef8"),
        }
        bg, fg, active_bg = styles.get(variant, styles["secondary"])
        return tk.Button(
            parent,
            text=text,
            command=command,
            relief="flat",
            borderwidth=0,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            disabledforeground=PALETTE["disabled"],
            padx=15,
            pady=9,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
        )

    def _bind_events(self) -> None:
        self.dashboard_combo.bind("<<ComboboxSelected>>", self.on_dashboard_combo_changed)
        if self.tree is not None:
            self.tree.bind("<<TreeviewSelect>>", self.on_tree_selection_changed)
            self.tree.bind("<Double-1>", lambda _event: self.open_selected())

    def refresh_dashboards(self, keep_selection: bool = True) -> None:
        selected = self.selected_relative if keep_selection else None
        self.dashboards = _scan_resources()
        known = {dashboard.relative for dashboard in self.dashboards}
        self.favorites = {item for item in self.favorites if item in known}
        self.recents = [item for item in self.recents if item in known][:20]
        if selected not in known:
            selected = self.config.get("last_opened") if self.config.get("last_opened") in known else None
        selected = _latest_position_relative(self.dashboards, selected)
        if selected is None and self.dashboards:
            selected = max(
                self.dashboards,
                key=lambda item: (
                    _position_date(item),
                    _version_datetime(item),
                    item.modified_ts,
                ),
            ).relative
        self._refresh_dashboard_selector(selected)
        self.filtered = sorted(self.dashboards, key=self._sort_key, reverse=self.sort_descending)
        self._update_counts()
        self.select_dashboard(selected)
        self._sync_config()
        self._schedule_save()
        if self.dashboards:
            newest = max(self.dashboards, key=lambda item: item.modified_ts)
            self.status(f"{len(self.dashboards)} recurso(s) disponibles. Ultima publicacion: {_format_datetime(newest.modified_ts)}.")
        else:
            self.status("No se encontraron dashboards ni aplicaciones publicados.")

    def _refresh_dashboard_selector(self, selected: str | None) -> None:
        self.combo_map.clear()
        values = []
        for dashboard in sorted(self.dashboards, key=lambda item: item.title.lower()):
            label = _dashboard_label(dashboard)
            self.combo_map[label] = dashboard.relative
            values.append(label)
        self.dashboard_combo.configure(values=values)
        self.updating_combo = True
        if selected:
            dashboard = self._dashboard_by_relative(selected)
            self.dashboard_var.set(_dashboard_label(dashboard) if dashboard else "")
        elif values:
            self.dashboard_var.set(values[0])
        else:
            self.dashboard_var.set("")
        self.updating_combo = False

    def apply_filters(self, selected: str | None = None) -> None:
        section = self.section_var.get()
        terms = [term for term in re.split(r"\s+", self.search_var.get().strip().lower()) if term]
        recents = set(self.recents)
        filtered: list[DashboardFile] = []
        for dashboard in self.dashboards:
            if section == "Favoritos" and dashboard.relative not in self.favorites:
                continue
            if section == "Recientes" and dashboard.relative not in recents:
                continue
            if not self._matches_date_filter(dashboard):
                continue
            if terms:
                haystack = " ".join((dashboard.title, dashboard.file_name, dashboard.folder, dashboard.relative)).lower()
                if not all(term in haystack for term in terms):
                    continue
            filtered.append(dashboard)
        self.filtered = sorted(filtered, key=self._sort_key, reverse=self.sort_descending)
        self._render_table(selected)
        self._refresh_section_buttons()
        self._update_counts()

    def _matches_date_filter(self, dashboard: DashboardFile) -> bool:
        selected = self.date_var.get()
        modified = datetime.fromtimestamp(dashboard.modified_ts)
        now = datetime.now()
        if selected == "Hoy":
            return modified.date() == now.date()
        if selected == "Ultimas 24 horas":
            return modified >= now - timedelta(hours=24)
        if selected == "Ultimos 7 dias":
            return modified >= now - timedelta(days=7)
        if selected == "Ultimos 30 dias":
            return modified >= now - timedelta(days=30)
        return True

    def _sort_key(self, dashboard: DashboardFile):
        if self.sort_column == "fav":
            return dashboard.relative in self.favorites
        if self.sort_column == "name":
            return dashboard.title.lower()
        if self.sort_column == "size":
            return dashboard.size_bytes
        return dashboard.modified_ts

    def _render_table(self, selected: str | None = None) -> None:
        if self.tree is None:
            return
        rows = self.tree.get_children()
        if rows:
            self.tree.delete(*rows)
        for dashboard in self.filtered:
            is_favorite = dashboard.relative in self.favorites
            self.tree.insert(
                "",
                "end",
                iid=dashboard.relative,
                values=(
                    "Si" if is_favorite else "No",
                    dashboard.title,
                    _format_datetime(dashboard.modified_ts),
                    _format_size(dashboard.size_bytes),
                    self._configuration_count_text(dashboard.relative),
                ),
                tags=("favorite",) if is_favorite else (),
            )
        valid = {dashboard.relative for dashboard in self.filtered}
        if selected and selected in valid:
            self.tree.selection_set(selected)
            self.tree.focus(selected)
            self.tree.see(selected)
        elif self.filtered and self.selected_relative in valid:
            self.tree.selection_set(self.selected_relative)
            self.tree.focus(self.selected_relative)
            self.tree.see(self.selected_relative)
        else:
            self.tree.selection_remove(self.tree.selection())

    def _configuration_count_text(self, relative: str) -> str:
        dashboard = self._dashboard_by_relative(relative)
        if dashboard is not None and (
            dashboard.kind == "application" or not dashboard.configurations_enabled
        ):
            return "-"
        data = _read_dashboard_configs(self.user, relative)
        count = len(data.get("configurations", []))
        return str(count)

    def _refresh_section_buttons(self) -> None:
        active = self.section_var.get()
        for name, button in self.section_buttons.items():
            if name == active:
                button.configure(bg=PALETTE["primary"], fg="#ffffff", activebackground=PALETTE["secondary"])
            else:
                button.configure(bg=PALETTE["soft_blue"], fg=PALETTE["primary"], activebackground="#dce9f7")

    def _update_counts(self) -> None:
        total = len(self.dashboards)
        shown = len(self.filtered)
        favs = len(self.favorites)
        configs = sum(
            len(_read_dashboard_configs(self.user, dashboard.relative).get("configurations", []))
            for dashboard in self.dashboards
            if dashboard.kind == "dashboard" and dashboard.configurations_enabled
        )
        self.count_var.set(f"{shown} visibles | {total} publicados | {favs} favoritos | {configs} configuraciones")

    def set_section(self, section: str) -> None:
        if section in SECTIONS:
            self.section_var.set(section)

    def set_sort(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = column in {"modified", "size", "fav"}
        self.apply_filters(selected=self.selected_relative)
        self._sync_config()
        self._schedule_save()

    def on_filter_changed(self) -> None:
        self.apply_filters(selected=self.selected_relative)
        self._sync_config()
        self._schedule_save()

    def clear_filters(self) -> None:
        self.search_var.set("")
        self.date_var.set("Todos")
        self.section_var.set("Todos")
        self.status("Filtros restablecidos para este usuario.")

    def on_dashboard_combo_changed(self, _event=None) -> None:
        if self.updating_combo:
            return
        self.select_dashboard(self.combo_map.get(self.dashboard_var.get()))

    def on_tree_selection_changed(self, _event=None) -> None:
        if self.tree is None:
            return
        selected = self.tree.selection()
        if selected:
            self.select_dashboard(selected[0], sync_combo=True)

    def _dashboard_by_relative(self, relative: str | None) -> DashboardFile | None:
        if not relative:
            return None
        for dashboard in self.dashboards:
            if dashboard.relative == relative:
                return dashboard
        return None

    def select_dashboard(self, relative: str | None, sync_combo: bool = False, sync_table: bool = False) -> None:
        dashboard = self._dashboard_by_relative(relative)
        self.selected_relative = dashboard.relative if dashboard else None
        profile = _dashboard_profile(dashboard)
        self.title_var.set(profile["title"])
        self.description_var.set(profile["description"])
        self.coverage_var.set(profile["coverage"])
        self.audience_var.set(profile["audience"])
        self.status_dashboard_var.set(profile["status"])
        if dashboard:
            if dashboard.kind == "dashboard" and dashboard.configurations_enabled:
                count = len(_read_dashboard_configs(self.user, dashboard.relative).get("configurations", []))
                self.preference_var.set(f"{count} configuracion(es) guardada(s) para {self.user.username}")
                self.open_button.configure(text="Abrir dashboard")
            elif dashboard.kind == "dashboard":
                self.preference_var.set("Configuraciones no parametrizadas")
                self.open_button.configure(text="Abrir dashboard")
            else:
                self.preference_var.set("Las configuraciones guardadas no aplican a ejecutables")
                self.open_button.configure(text="Abrir aplicacion")
            is_favorite = dashboard.relative in self.favorites
            self.favorite_button.configure(text="Quitar favorito" if is_favorite else "Marcar favorito")
            self._set_action_state(True)
        else:
            self.preference_var.set("Sin configuraciones guardadas para este usuario")
            self.open_button.configure(text="Abrir recurso")
            self.favorite_button.configure(text="Marcar favorito")
            self._set_action_state(False)
        if sync_combo and dashboard:
            self.updating_combo = True
            self.dashboard_var.set(_dashboard_label(dashboard))
            self.updating_combo = False
        if sync_table and self.tree is not None and dashboard and dashboard.relative in {item.relative for item in self.filtered}:
            self.tree.selection_set(dashboard.relative)
            self.tree.focus(dashboard.relative)
            self.tree.see(dashboard.relative)
        self._sync_config()
        self._schedule_save()

    def _set_action_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        cursor = "hand2" if enabled else "arrow"
        for button in self.action_buttons:
            button.configure(state=state, cursor=cursor)

    def open_selected(self) -> None:
        dashboard = self._dashboard_by_relative(self.selected_relative)
        if dashboard is None:
            return
        if dashboard.kind == "application":
            try:
                subprocess.Popen(
                    [str(dashboard.path)],
                    cwd=str(dashboard.path.parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            except OSError as exc:
                messagebox.showerror(
                    APP_NAME,
                    f"No se pudo iniciar la aplicacion.\n\n{exc}",
                )
                return
            self.runtime_var.set("Aplicacion: iniciada")
            self.recents = [dashboard.relative] + [
                item for item in self.recents if item != dashboard.relative
            ]
            self.recents = self.recents[:20]
            self.config["last_opened"] = dashboard.relative
            self.select_dashboard(dashboard.relative, sync_combo=True)
            self.status(f"Aplicacion iniciada: {dashboard.title}")
            return
        try:
            url = self.server.dashboard_url(dashboard.relative)
        except OSError:
            messagebox.showerror(APP_NAME, "No se pudo preparar el dashboard.")
            return
        _open_dashboard_window(url)
        self.runtime_var.set(
            "Configuraciones: activas"
            if dashboard.configurations_enabled
            else "Dashboard: modo estándar"
        )
        self.recents = [dashboard.relative] + [item for item in self.recents if item != dashboard.relative]
        self.recents = self.recents[:20]
        self.config["last_opened"] = dashboard.relative
        self.select_dashboard(dashboard.relative, sync_combo=True)
        self.status(
            (
                "Abierto con configuraciones por usuario: "
                if dashboard.configurations_enabled
                else "Dashboard abierto: "
            )
            + dashboard.title
        )

    def toggle_favorite(self) -> None:
        dashboard = self._dashboard_by_relative(self.selected_relative)
        if dashboard is None:
            return
        if dashboard.relative in self.favorites:
            self.favorites.remove(dashboard.relative)
            self.status(f"Favorito retirado: {dashboard.title}")
        else:
            self.favorites.add(dashboard.relative)
            self.status(f"Favorito guardado: {dashboard.title}")
        self.select_dashboard(dashboard.relative, sync_combo=True)
        self.filtered = sorted(self.dashboards, key=self._sort_key, reverse=self.sort_descending)
        self._update_counts()
        self._sync_config()
        self._schedule_save()

    def status(self, text: str) -> None:
        self.status_var.set(text)

    def _sync_config(self) -> None:
        self.config["user"] = {"domain": self.user.domain, "username": self.user.username, "display": self.user.display}
        self.config["filters"] = {"section": self.section_var.get(), "search": self.search_var.get(), "date_range": self.date_var.get()}
        self.config["favorites"] = sorted(self.favorites)
        self.config["recents"] = self.recents[:20]
        self.config["last_selected"] = self.selected_relative or ""
        self.config["sort"] = {"column": self.sort_column, "descending": self.sort_descending}
        self.config["window"] = {"geometry": self.root.geometry()}

    def _schedule_save(self) -> None:
        if self.save_after_id is not None:
            self.root.after_cancel(self.save_after_id)
        self.save_after_id = self.root.after(350, self._flush_save)

    def _flush_save(self) -> None:
        self.save_after_id = None
        try:
            self._sync_config()
            _save_config(self.config_path, self.config)
        except OSError:
            self.status("No se pudo guardar la configuracion del usuario.")

    def close(self) -> None:
        if self.save_after_id is not None:
            self.root.after_cancel(self.save_after_id)
            self.save_after_id = None
        try:
            self._sync_config()
            _save_config(self.config_path, self.config)
        except OSError:
            messagebox.showwarning(APP_NAME, "No se pudo guardar la configuracion.")
        self.server.stop()
        self.root.destroy()


class PortalRiskoApp(_LegacyPortalRiskoApp):
    """Interfaz ejecutiva que reutiliza la lógica funcional del portal."""

    def __init__(self, root: tk.Tk) -> None:
        self.initial_refresh_complete = False
        self.defer_initial_window = os.environ.get("PORTAL_RISKO_UI_TEST") != "1"
        if self.defer_initial_window:
            root.withdraw()
        self.groups: dict[str, list[DashboardFile]] = {}
        self.group_titles: dict[str, str] = {}
        self.selected_group_key: str | None = None
        self.visible_group_keys: list[str] = []
        self.version_date_map: dict[date, str] = {}
        self.calendar_window: tk.Toplevel | None = None
        self.calendar_body: tk.Frame | None = None
        self.calendar_display_month: date | None = None
        self.calendar_selected_date: date | None = None
        self.refresh_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.refreshing = False
        self.preview_source: Path | None = None
        self.preview_original = None
        self.preview_photo = None
        self.preview_cache: dict[tuple[str, int, int, int], object] = {}
        self.preview_resize_after: str | None = None
        self.preview_queue: queue.Queue[tuple[int, str, object]] = queue.Queue()
        self.preview_request_id = 0
        self.preview_identity = ""
        self.preview_poll_after: str | None = None
        self.preview_pending_requests: set[int] = set()
        self.current_layout = ""
        self.current_dpi = 0
        self.monitor_sync_after: str | None = None
        self.scroll_region_after: str | None = None
        self.root_layout = ""

        self.version_var = tk.StringVar(value="")
        self.preview_text_var = tk.StringVar(value="Seleccione un dashboard.")
        self.comment_date_var = tk.StringVar(value="Sin fecha seleccionada")
        self.comment_meta_var = tk.StringVar(value="Pendiente de selección")
        self.daily_comment: DailyComment | None = None
        self.last_refresh_var = tk.StringVar(value="Última actualización: pendiente")
        self.service_var = tk.StringVar(value="Estado del servicio: verificando")
        self.lower_config_var = tk.StringVar(value="No disponible")
        self.lower_history_var = tk.StringVar(value="Sin publicaciones")
        self.lower_preferences_var = tk.StringVar(value="Sin preferencias")
        self.lower_latest_var = tk.StringVar(value="Última publicación: pendiente")
        self.lower_news_var = tk.StringVar(value="Sin novedades publicadas")

        super().__init__(root)
        # Los filtros históricos siguen existiendo en la configuración para
        # conservar compatibilidad, pero ya no condicionan la interfaz principal.
        self.section_var.set("Todos")
        self.search_var.set("")
        self.date_var.set("Todos")

    def _configure_root(self) -> None:
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        if ICON_PORTAL.is_file():
            try:
                self.root.iconbitmap(str(ICON_PORTAL))
            except tk.TclError:
                pass
        self.root.geometry("1180x760")
        self.root.minsize(820, 600)
        self.root.configure(bg=PALETTE["bg"])
        self.root.option_add("*Font", "{Segoe UI} 10")
        if os.environ.get("PORTAL_RISKO_UI_TEST") != "1":
            self.root.after(70, self._maximize_root)

    def _maximize_root(self) -> None:
        if self.defer_initial_window:
            return
        maximize_on_monitor(self.root)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Portal.Treeview",
            background=PALETTE["surface"],
            fieldbackground=PALETTE["surface"],
            foreground=PALETTE["text"],
            bordercolor=PALETTE["line"],
            rowheight=34,
            font=("Segoe UI", 9),
        )
        style.map(
            "Portal.Treeview",
            background=[("selected", "#0b63ce")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Portal.Treeview.Heading",
            background=PALETTE["surface_alt"],
            foreground=PALETTE["text"],
            relief="flat",
            font=("Segoe UI Semibold", 8),
            padding=(8, 8),
        )
        style.map(
            "Portal.Treeview.Heading",
            background=[("active", PALETTE["soft_blue"])],
        )
        style.configure(
            "Portal.TCombobox",
            fieldbackground=PALETTE["surface"],
            background=PALETTE["surface"],
            foreground=PALETTE["text"],
            arrowcolor=PALETTE["primary"],
            bordercolor=PALETTE["line"],
            padding=7,
        )
        style.map(
            "Portal.TCombobox",
            fieldbackground=[("readonly", PALETTE["surface"])],
            foreground=[("readonly", PALETTE["text"])],
        )
        style.configure(
            "Portal.Vertical.TScrollbar",
            troughcolor=PALETTE["surface_alt"],
            background="#b9c7d7",
            arrowcolor=PALETTE["primary"],
        )

    def _card_frame(self, parent: tk.Widget) -> RoundedCard:
        return RoundedCard(parent, radius=17)

    def _build_layout(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        main = tk.Frame(self.root, bg=PALETTE["bg"])
        main.grid(row=0, column=0, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self._build_hero(main)

        content_shell = tk.Frame(main, bg=PALETTE["bg"])
        content_shell.grid(row=1, column=0, sticky="nsew")
        content_shell.grid_rowconfigure(0, weight=1)
        content_shell.grid_columnconfigure(0, weight=1)

        self.main_canvas = tk.Canvas(
            content_shell,
            bg=PALETTE["bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.main_canvas.grid(row=0, column=0, sticky="nsew")
        self.main_scrollbar = ttk.Scrollbar(
            content_shell,
            orient="vertical",
            command=self.main_canvas.yview,
            style="Portal.Vertical.TScrollbar",
        )
        self.main_scrollbar.grid(row=0, column=1, sticky="ns")
        self.main_canvas.configure(yscrollcommand=self.main_scrollbar.set)

        self.content_frame = tk.Frame(self.main_canvas, bg=PALETTE["bg"])
        self.content_window = self.main_canvas.create_window(
            (0, 0),
            window=self.content_frame,
            anchor="nw",
        )
        self.content_frame.bind("<Configure>", self._schedule_scroll_region_update)
        self.main_canvas.bind("<Configure>", self._on_canvas_configure)
        self.main_canvas.bind(
            "<Enter>",
            lambda _event: self.main_canvas.bind_all(
                "<MouseWheel>",
                self._on_mousewheel,
            ),
        )
        self.main_canvas.bind(
            "<Leave>",
            lambda _event: self.main_canvas.unbind_all("<MouseWheel>"),
        )

        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.dashboard_page = tk.Frame(self.content_frame, bg=PALETTE["bg"])
        self.dashboard_page.grid(row=0, column=0, sticky="nsew")
        self._build_selection_card(self.dashboard_page)
        self._build_status_bar(main)

    def _build_hero(self, parent: tk.Widget) -> None:
        hero = tk.Frame(parent, bg=PALETTE["primary"])
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_columnconfigure(0, weight=1)
        tk.Frame(hero, bg=PALETTE["accent"], height=3).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
        )

        brand = tk.Frame(hero, bg=PALETTE["primary"])
        brand.grid(row=1, column=0, sticky="ew", padx=(24, 14), pady=9)
        self.hero_brand = brand

        logo_box = tk.Frame(brand, bg=PALETTE["primary"], highlightthickness=0)
        logo_box.pack(side="left", padx=(0, 16), pady=1)
        self.hero_logo_box = logo_box
        if self.bank_logo_image or self.logo_image:
            self.hero_logo_label = tk.Label(
                logo_box,
                image=self.bank_logo_image or self.logo_image,
                bg=PALETTE["primary"],
            )
            self.hero_logo_label.pack(padx=10, pady=6)
        else:
            self.hero_logo_label = tk.Label(
                logo_box,
                text="BANCO DE BOGOTÁ",
                bg=PALETTE["primary"],
                fg="#ffffff",
                font=("Segoe UI Semibold", 20),
            )
            self.hero_logo_label.pack(padx=14, pady=8)

        titles = tk.Frame(brand, bg=PALETTE["primary"])
        titles.pack(side="left", fill="x", expand=True)
        self.hero_titles = titles
        tk.Label(
            titles,
            text="PORTAL EJECUTIVO RISKO",
            bg=PALETTE["primary"],
            fg=PALETTE["accent"],
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w")
        self.hero_title_label = tk.Label(
            titles,
            text="Centro de Información Riesgos de Mercado",
            bg=PALETTE["primary"],
            fg="#ffffff",
            font=("Segoe UI Semibold", 19),
            justify="left",
            anchor="w",
            wraplength=780,
        )
        self.hero_title_label.pack(anchor="w", fill="x")
        self.hero_description_label = tk.Label(
            titles,
            text=(
                "Acceso centralizado a dashboards y aplicaciones publicados, "
                "con preferencias guardadas por usuario de Windows."
            ),
            bg=PALETTE["primary"],
            fg="#dce8f7",
            justify="left",
            anchor="w",
            wraplength=820,
            font=("Segoe UI", 9),
        )
        self.hero_description_label.pack(anchor="w", fill="x", pady=(0, 0))

        risko_box = tk.Frame(hero, bg=PALETTE["primary"], highlightthickness=0)
        risko_box.grid(row=1, column=1, sticky="e", padx=(0, 24), pady=9)
        self.hero_session = risko_box
        self.hero_layout = "wide"
        if self.logo_image:
            tk.Label(risko_box, image=self.logo_image, bg=PALETTE["primary"]).pack(padx=12, pady=6)
        else:
            tk.Label(risko_box, text="RISKO", bg=PALETTE["primary"], fg="#ffffff", font=("Segoe UI Semibold", 20)).pack(
                padx=16, pady=8
            )
        hero.bind("<Configure>", self._reflow_hero)

    def _build_selection_card(self, parent: tk.Widget) -> None:
        parent.grid_columnconfigure(0, weight=1)

        filters = self._card_frame(parent)
        self.filters_card = filters
        filters.grid(row=0, column=0, sticky="ew", padx=18, pady=(10, 6))
        filters.grid_columnconfigure(0, weight=3)
        filters.grid_columnconfigure(1, weight=2)
        tk.Label(
            filters,
            text="SELECCIÓN",
            bg=PALETTE["surface"],
            fg=PALETTE["primary"],
            font=("Segoe UI Semibold", 8),
        ).grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="w",
            padx=20,
            pady=(10, 6),
        )

        dashboard_field = tk.Frame(filters, bg=PALETTE["surface"])
        self.dashboard_field = dashboard_field
        dashboard_field.grid(row=1, column=0, sticky="ew", padx=(16, 10), pady=(0, 12))
        self._field_label(dashboard_field, "Dashboard o aplicación").pack(anchor="w")
        self.dashboard_combo = ttk.Combobox(
            dashboard_field,
            textvariable=self.dashboard_var,
            state="readonly",
            style="Portal.TCombobox",
        )
        self.dashboard_combo.pack(fill="x", pady=(4, 0))

        version_field = tk.Frame(filters, bg=PALETTE["surface"])
        self.version_field = version_field
        version_field.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 12))
        self._field_label(version_field, "Posición por fecha").pack(anchor="w")
        date_picker = tk.Frame(version_field, bg=PALETTE["surface"])
        date_picker.pack(fill="x", pady=(4, 0))
        self.version_entry = tk.Entry(
            date_picker,
            textvariable=self.version_var,
            state="readonly",
            readonlybackground=PALETTE["surface"],
            fg=PALETTE["text"],
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        self.version_entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.calendar_button = self._button(
            date_picker,
            "Calendario",
            self.show_calendar,
            "secondary",
        )
        self.calendar_button.pack(side="left", padx=(8, 0))

        self.today_button = self._button(filters, "Hoy", self.select_today, "secondary")
        self.today_button.grid(row=1, column=2, sticky="s", padx=(0, 10), pady=(0, 12))

        self.lower_frame = tk.Frame(parent, bg=PALETTE["bg"])
        self.lower_frame.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))

        self.workspace = tk.Frame(parent, bg=PALETTE["bg"])
        self.workspace.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 10))
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        self.preview_card = self._card_frame(self.workspace)
        self.preview_card.grid(row=0, column=0, sticky="nsew")
        self.preview_card.grid_rowconfigure(4, weight=1, minsize=260)
        self.preview_card.grid_columnconfigure(0, weight=3)
        self.preview_card.grid_columnconfigure(1, weight=2)
        tk.Label(
            self.preview_card,
            text="VISTA PREVIA Y ACCIONES",
            bg=PALETTE["surface"],
            fg=PALETTE["primary"],
            font=("Segoe UI Semibold", 8),
        ).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            padx=18,
            pady=(15, 9),
        )
        self.preview_title_label = tk.Label(
            self.preview_card,
            textvariable=self.title_var,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 14),
            justify="left",
            anchor="w",
        )
        self.preview_title_label.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
        )
        self.preview_description_label = tk.Label(
            self.preview_card,
            textvariable=self.description_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
        )
        self.preview_description_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(3, 10),
        )
        self.preview_label = tk.Label(
            self.preview_card,
            textvariable=self.preview_text_var,
            bg=PALETTE["surface_alt"],
            fg=PALETTE["muted"],
            justify="center",
            anchor="center",
            wraplength=500,
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )
        self.preview_label.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=(16, 8),
            pady=(0, 16),
            ipady=48,
        )
        self.preview_label.bind("<Configure>", self._schedule_preview_resize)

        self.comment_panel = tk.Frame(
            self.preview_card,
            bg=PALETTE["surface_alt"],
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )
        self.comment_panel.grid(
            row=4,
            column=1,
            sticky="nsew",
            padx=(8, 16),
            pady=(0, 16),
        )
        self.comment_panel.grid_rowconfigure(3, weight=1)
        self.comment_panel.grid_columnconfigure(0, weight=1)
        tk.Frame(self.comment_panel, bg=PALETTE["accent"], height=4).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        comment_header = tk.Frame(self.comment_panel, bg=PALETTE["surface_alt"])
        comment_header.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(12, 2),
        )
        comment_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            comment_header,
            text="COMENTARIO DEL DÍA",
            bg=PALETTE["surface_alt"],
            fg=PALETTE["primary"],
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            comment_header,
            textvariable=self.comment_date_var,
            bg=PALETTE["soft_gold"],
            fg=PALETTE["accent_dark"],
            font=("Segoe UI Semibold", 8),
            padx=8,
            pady=4,
        ).grid(row=0, column=1, sticky="e")
        tk.Label(
            self.comment_panel,
            textvariable=self.comment_meta_var,
            bg=PALETTE["surface_alt"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 7),
            anchor="w",
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 8),
        )
        comment_body = tk.Frame(self.comment_panel, bg=PALETTE["surface_alt"])
        comment_body.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=(14, 8),
            pady=(0, 12),
        )
        comment_body.grid_rowconfigure(0, weight=1)
        comment_body.grid_columnconfigure(0, weight=1)
        self.comment_text = tk.Text(
            comment_body,
            wrap="word",
            height=12,
            state="disabled",
            bg=PALETTE["surface_alt"],
            fg=PALETTE["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=2,
            pady=2,
            cursor="arrow",
            font=("Segoe UI", 9),
            spacing1=1,
            spacing3=5,
        )
        self.comment_text.grid(row=0, column=0, sticky="nsew")
        self.comment_scrollbar = ttk.Scrollbar(
            comment_body,
            orient="vertical",
            command=self.comment_text.yview,
            style="Portal.Vertical.TScrollbar",
        )
        self.comment_scrollbar.grid(row=0, column=1, sticky="ns")
        self.comment_text.configure(yscrollcommand=self.comment_scrollbar.set)
        self.comment_text.tag_configure(
            "comment_h1",
            font=("Segoe UI Semibold", 11),
            foreground=PALETTE["primary"],
            spacing1=2,
            spacing3=7,
        )
        self.comment_text.tag_configure(
            "comment_h2",
            font=("Segoe UI Semibold", 9),
            foreground=PALETTE["deep"],
            spacing1=4,
            spacing3=5,
        )
        self.comment_text.tag_configure(
            "comment_h3",
            font=("Segoe UI Semibold", 9),
            foreground=PALETTE["muted"],
            spacing1=3,
            spacing3=4,
        )
        self.comment_text.tag_configure(
            "comment_paragraph",
            font=("Segoe UI", 9),
            foreground=PALETTE["text"],
            spacing3=7,
        )
        self.comment_text.tag_configure(
            "comment_bullet",
            font=("Segoe UI", 9),
            foreground=PALETTE["text"],
            lmargin1=10,
            lmargin2=24,
            spacing3=4,
        )
        self.comment_text.tag_configure(
            "comment_table_header",
            font=("Consolas", 9, "bold"),
            foreground=PALETTE["surface"],
            background=PALETTE["primary"],
            lmargin1=12,
            lmargin2=12,
            rmargin=12,
            justify="center",
            spacing1=5,
            spacing3=1,
        )
        self.comment_text.tag_configure(
            "comment_table_row",
            font=("Consolas", 9),
            foreground=PALETTE["text"],
            background=PALETTE["soft_blue"],
            lmargin1=12,
            lmargin2=12,
            rmargin=12,
            justify="center",
            spacing1=1,
            spacing3=1,
        )
        self.comment_text.tag_configure(
            "comment_bold",
            font=("Segoe UI Semibold", 9),
        )
        self.comment_text.tag_configure(
            "comment_empty",
            font=("Segoe UI", 9, "italic"),
            foreground=PALETTE["muted"],
            justify="center",
            spacing1=24,
        )

        actions = tk.Frame(self.preview_card, bg=PALETTE["surface"])
        self.actions_frame = actions
        actions.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 12),
        )
        self.open_button = self._button(
            actions,
            "Abrir dashboard",
            self.open_selected,
            "primary",
        )
        self.refresh_button = self._button(
            actions,
            "Actualizar",
            self.refresh_dashboards,
            "secondary",
        )
        self.detail_button = self._button(
            actions,
            "Ver detalle",
            self.show_selected_detail,
            "secondary",
        )
        self.action_buttons = [
            self.open_button,
            self.detail_button,
        ]
        self.action_controls = [
            self.open_button,
            self.refresh_button,
            self.detail_button,
        ]
        for column, button in enumerate(self.action_controls):
            actions.grid_columnconfigure(column, weight=1)
            button.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 8) if column < len(self.action_controls) - 1 else 0,
            )

        lower_specs = (
            ("Configuración de vista", self.lower_config_var),
            ("Última publicación", self.lower_latest_var),
            ("Novedades", self.lower_news_var),
        )
        self.lower_cards: list[tk.Frame] = []
        for label, variable in lower_specs:
            card = self._detail_card(self.lower_frame, label, variable, compact=True)
            self.lower_cards.append(card)

    def _build_status_bar(self, parent: tk.Widget) -> None:
        bar = tk.Frame(
            parent,
            bg=PALETTE["surface"],
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=3)
        bar.grid_columnconfigure(1, weight=1)
        tk.Label(
            bar,
            textvariable=self.status_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            anchor="w",
            font=("Segoe UI", 8),
        ).grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=7)
        tk.Label(
            bar,
            textvariable=self.count_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 8),
        ).grid(row=0, column=1, sticky="e", padx=8)
        tk.Label(
            bar,
            textvariable=self.service_var,
            bg=PALETTE["surface"],
            fg=PALETTE["success"],
            font=("Segoe UI Semibold", 8),
        ).grid(row=0, column=2, sticky="e", padx=8)
        tk.Label(
            bar,
            text=f"v{APP_VERSION}",
            bg=PALETTE["surface"],
            fg=PALETTE["primary"],
            font=("Segoe UI Semibold", 8),
        ).grid(row=0, column=3, sticky="e", padx=(8, 14))

    def _detail_card(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        *,
        compact: bool = False,
    ) -> RoundedCard:
        frame = RoundedCard(parent, radius=8 if compact else 14)
        horizontal_padding = 8 if compact else 12
        tk.Frame(
            frame,
            bg=PALETTE["accent"],
            height=2 if compact else 3,
        ).pack(
            fill="x",
            padx=horizontal_padding,
            pady=((5 if compact else 10), 0),
        )
        tk.Label(
            frame,
            text=label.upper(),
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=("Segoe UI Semibold", 7),
            justify="left",
            anchor="w",
        ).pack(
            fill="x",
            padx=horizontal_padding,
            pady=((3 if compact else 7), 0),
        )
        value_label = tk.Label(
            frame,
            textvariable=variable,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 8 if compact else 9),
            justify="left",
            anchor="w",
            wraplength=190 if compact else 260,
        )
        value_label.pack(
            fill="x",
            padx=horizontal_padding,
            pady=((1 if compact else 4), (5 if compact else 11)),
        )
        frame.value_label = value_label
        return frame

    def _button(self, parent: tk.Widget, text: str, command, variant: str) -> tk.Button:
        styles = {
            "primary": ("#0057b8", "#ffffff", "#0b63ce"),
            "secondary": (PALETTE["soft_blue"], PALETTE["primary"], "#dce9f7"),
            "accent": (PALETTE["accent"], PALETTE["text"], PALETTE["accent_dark"]),
        }
        bg, fg, active_bg = styles.get(variant, styles["secondary"])
        return tk.Button(
            parent,
            text=text,
            command=command,
            relief="flat",
            borderwidth=0,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            disabledforeground=PALETTE["disabled"],
            padx=14,
            pady=8,
            cursor="hand2",
            font=("Segoe UI Semibold", 9),
        )

    def _schedule_scroll_region_update(self, _event=None) -> None:
        if self.scroll_region_after is not None:
            self.root.after_cancel(self.scroll_region_after)
        self.scroll_region_after = self.root.after(50, self._update_scroll_region)

    def _update_scroll_region(self) -> None:
        self.scroll_region_after = None
        requested_height = max(
            self.main_canvas.winfo_height(),
            self.content_frame.winfo_reqheight(),
        )
        self.main_canvas.itemconfigure(
            self.content_window,
            height=requested_height,
        )
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        width = max(1, int(event.width))
        height = max(int(event.height), self.content_frame.winfo_reqheight())
        self.main_canvas.itemconfigure(
            self.content_window,
            width=width,
            height=height,
        )
        self._reflow_content(self._logical_width(width))
        self._schedule_scroll_region_update()

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _reflow_hero(self, event: tk.Event) -> None:
        width = max(1, int(event.width))
        logical_width = self._logical_width(width)
        layout = "compact" if logical_width < 900 else "wide"
        text_width = max(260, width - (500 if layout == "wide" else 190))
        self.hero_title_label.configure(wraplength=text_width)
        self.hero_description_label.configure(wraplength=text_width)
        if layout == self.hero_layout:
            return
        self.hero_layout = layout
        self.hero_session.grid_forget()
        if layout == "wide":
            self.hero_session.grid(
                row=1,
                column=1,
                sticky="e",
                padx=(0, 24),
                pady=9,
            )
        else:
            self.hero_session.grid(
                row=2,
                column=0,
                sticky="w",
                padx=24,
                pady=(0, 8),
            )

    def _logical_width(self, physical_width: int) -> int:
        dpi = self.current_dpi or get_window_dpi(self.root)
        return max(1, round(physical_width * 96 / max(72, dpi)))

    def _on_root_configure(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        if self.monitor_sync_after is not None:
            self.root.after_cancel(self.monitor_sync_after)
        self.monitor_sync_after = self.root.after(90, self._sync_monitor_layout)

    def _sync_monitor_layout(self) -> None:
        self.monitor_sync_after = None
        if not self.root.winfo_exists() or self.root.state() == "iconic":
            return
        dpi = get_window_dpi(self.root)
        dpi_changed = dpi != self.current_dpi
        if dpi_changed:
            self.current_dpi = dpi
            try:
                self.root.tk.call("tk", "scaling", dpi / 72.0)
            except tk.TclError:
                pass
            self._configure_styles()

        root_width = max(1, self.root.winfo_width())
        logical_root = self._logical_width(root_width)
        layout = (
            "wide"
            if logical_root >= 1280
            else "compact"
            if logical_root >= 920
            else "narrow"
        )
        self.root.minsize(
            round(820 * dpi / 96),
            round(600 * dpi / 96),
        )
        if layout != self.root_layout or dpi_changed:
            self.root_layout = layout
            self.current_layout = ""
        canvas_width = max(1, self.main_canvas.winfo_width())
        self._reflow_content(self._logical_width(canvas_width))
        self._schedule_preview_resize()

    def _reflow_content(self, width: int) -> None:
        layout = "wide" if width >= 1180 else "medium" if width >= 760 else "narrow"
        if layout == self.current_layout:
            physical_width = max(1, self.main_canvas.winfo_width())
            self._update_content_wraplengths(physical_width, layout)
            return
        self.current_layout = layout

        for widget in (
            self.dashboard_field,
            self.version_field,
            self.today_button,
        ):
            widget.grid_forget()
        if layout == "wide":
            column_weights = (3, 2, 0)
            placements = (
                (self.dashboard_field, 1, 0, 1, (16, 10)),
                (self.version_field, 1, 1, 1, (0, 8)),
                (self.today_button, 1, 2, 1, (0, 20)),
            )
        elif layout == "medium":
            column_weights = (3, 2, 0)
            placements = (
                (self.dashboard_field, 1, 0, 1, (16, 10)),
                (self.version_field, 1, 1, 1, (0, 8)),
                (self.today_button, 1, 2, 1, (0, 20)),
            )
        else:
            column_weights = (1, 1, 0)
            placements = (
                (self.dashboard_field, 1, 0, 3, (16, 16)),
                (self.version_field, 2, 0, 2, (16, 10)),
                (self.today_button, 2, 2, 1, (0, 20)),
            )
        for column, weight in enumerate(column_weights):
            self.filters_card.grid_columnconfigure(column, weight=weight)
        for widget, row, column, columnspan, padx in placements:
            widget.grid(
                row=row,
                column=column,
                columnspan=columnspan,
                sticky="ew" if widget is not self.today_button else "s",
                padx=padx,
                pady=(0, 12),
            )

        self.preview_label.grid_forget()
        self.comment_panel.grid_forget()
        if layout == "narrow":
            self.preview_card.grid_columnconfigure(0, weight=1)
            self.preview_card.grid_columnconfigure(1, weight=0)
            self.preview_card.grid_rowconfigure(4, weight=1, minsize=240)
            self.preview_card.grid_rowconfigure(5, weight=1, minsize=220)
            self.preview_label.grid(
                row=4,
                column=0,
                sticky="nsew",
                padx=16,
                pady=(0, 12),
                ipady=36,
            )
            self.comment_panel.grid(
                row=5,
                column=0,
                sticky="nsew",
                padx=16,
                pady=(0, 16),
            )
        else:
            self.preview_card.grid_columnconfigure(0, weight=3)
            self.preview_card.grid_columnconfigure(1, weight=2)
            self.preview_card.grid_rowconfigure(4, weight=1, minsize=260)
            self.preview_card.grid_rowconfigure(5, weight=0, minsize=0)
            self.preview_label.grid(
                row=4,
                column=0,
                sticky="nsew",
                padx=(16, 8),
                pady=(0, 16),
                ipady=48,
            )
            self.comment_panel.grid(
                row=4,
                column=1,
                sticky="nsew",
                padx=(8, 16),
                pady=(0, 16),
            )

        action_columns = 3 if layout != "narrow" else 2
        for button in self.action_controls:
            button.grid_forget()
        for column in range(4):
            self.actions_frame.grid_columnconfigure(
                column,
                weight=1 if column < action_columns else 0,
            )
        for index, button in enumerate(self.action_controls):
            row = index // action_columns
            column = index % action_columns
            button.grid(
                row=row,
                column=column,
                sticky="ew",
                padx=(0, 8) if column < action_columns - 1 else 0,
                pady=(0, 8) if row == 0 and action_columns == 2 else 0,
            )

        for card in self.lower_cards:
            card.grid_forget()
        lower_columns = 3 if layout != "narrow" else 1
        for column in range(4):
            if layout != "narrow" and column < 3:
                self.lower_frame.grid_columnconfigure(column, weight=(1, 1, 3)[column])
            else:
                self.lower_frame.grid_columnconfigure(column, weight=0 if column else 1)
        for index, card in enumerate(self.lower_cards):
            card.grid(
                row=index // lower_columns,
                column=index % lower_columns,
                sticky="nsew",
                padx=(0, 8) if index % lower_columns < lower_columns - 1 else 0,
                pady=(0, 8),
            )
        self._update_content_wraplengths(
            max(1, self.main_canvas.winfo_width()),
            layout,
        )

    def _update_content_wraplengths(self, physical_width: int, layout: str) -> None:
        content_wrap = max(240, physical_width - 90)
        self.preview_title_label.configure(wraplength=content_wrap)
        self.preview_description_label.configure(wraplength=content_wrap)
        preview_wrap = (
            content_wrap
            if layout == "narrow"
            else max(240, round(physical_width * 0.58) - 70)
        )
        self.preview_label.configure(wraplength=preview_wrap)
        for index, card in enumerate(self.lower_cards):
            if layout == "narrow":
                wraplength = max(220, physical_width - 68)
            elif index == 2:
                wraplength = max(320, round(physical_width * 0.60) - 56)
            else:
                wraplength = max(150, round(physical_width * 0.20) - 40)
            card.value_label.configure(wraplength=wraplength)

    def _bind_events(self) -> None:
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self.dashboard_combo.bind(
            "<<ComboboxSelected>>",
            self.on_dashboard_combo_changed,
        )
        self.version_entry.bind("<Button-1>", lambda _event: self.show_calendar())

    def refresh_dashboards(self, keep_selection: bool = True) -> None:
        if self.refreshing:
            self.status("La actualización ya está en curso.")
            return
        self.refreshing = True
        selected = self.selected_relative if keep_selection else None
        self.status("Actualizando la biblioteca de dashboards...")
        self.service_var.set("Estado del servicio: sincronizando")
        if hasattr(self, "refresh_button"):
            self.refresh_button.configure(state="disabled", cursor="arrow")
        if hasattr(self, "dashboard_combo"):
            self.dashboard_combo.configure(state="disabled")

        def worker() -> None:
            try:
                resources = _scan_resources()
                availability = {
                    "dashboards": PUBLISHED_DIR.exists(),
                    "applications": APPLICATIONS_DIR.exists(),
                }
                self.refresh_queue.put(
                    ("success", (resources, availability, selected))
                )
            except Exception as exc:
                self.refresh_queue.put(("error", exc))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(80, self._poll_refresh_queue)

    def _poll_refresh_queue(self) -> None:
        try:
            event, payload = self.refresh_queue.get_nowait()
        except queue.Empty:
            if self.refreshing and self.root.winfo_exists():
                self.root.after(80, self._poll_refresh_queue)
            return

        self.refreshing = False
        if hasattr(self, "refresh_button"):
            self.refresh_button.configure(state="normal", cursor="hand2")
        if hasattr(self, "dashboard_combo"):
            self.dashboard_combo.configure(state="readonly")

        if event == "error":
            self.service_var.set("Estado del servicio: con error")
            self.status("No fue posible actualizar la biblioteca.")
            self.initial_refresh_complete = True
            self._reveal_after_initial_refresh()
            messagebox.showerror(
                APP_NAME,
                f"No fue posible consultar los recursos publicados.\n\n{payload}",
                parent=self.root,
            )
            return

        resources, availability, selected = payload  # type: ignore[misc]
        self.dashboards = list(resources)
        known = {dashboard.relative for dashboard in self.dashboards}
        self.favorites = {item for item in self.favorites if item in known}
        self.recents = [item for item in self.recents if item in known][:20]
        self._build_groups()

        if selected not in known:
            last_opened = str(self.config.get("last_opened") or "")
            selected = last_opened if last_opened in known else None
        selected = _latest_position_relative(self.dashboards, selected)
        self.apply_filters(selected=selected)

        now = datetime.now()
        sync_text = (
            f"Última actualización: {now.day:02d} "
            f"{SPANISH_MONTHS[now.month - 1]} {now.year}, {now:%H:%M}"
        )
        self.last_refresh_var.set(sync_text)
        self.lower_news_var.set(_novedades_summary())
        if availability.get("dashboards") or availability.get("applications"):
            self.service_var.set("Estado del servicio: operativo")
        else:
            self.service_var.set("Estado del servicio: no disponible")
            messagebox.showwarning(
                APP_NAME,
                "Las carpetas de dashboards y aplicaciones no están disponibles.",
                parent=self.root,
            )
        self._sync_config()
        self._schedule_save()
        if self.dashboards:
            self.status(
                f"{len(self.groups)} recurso(s) y {len(self.dashboards)} "
                "posición(es) disponibles."
            )
        else:
            self.status("No se encontraron dashboards ni aplicaciones publicados.")
        self.initial_refresh_complete = True
        self._reveal_after_initial_refresh()

    def _reveal_after_initial_refresh(self) -> None:
        if (
            not self.defer_initial_window
            or not self.initial_refresh_complete
            or self.preview_pending_requests
            or not self.root.winfo_exists()
        ):
            return
        self.defer_initial_window = False
        self.root.update_idletasks()
        self.root.deiconify()
        maximize_on_monitor(self.root)
        self.root.lift()
        self.root.focus_force()

    def _build_groups(self) -> None:
        self.groups.clear()
        self.group_titles.clear()
        for dashboard in self.dashboards:
            key = _resource_group_key(dashboard)
            self.groups.setdefault(key, []).append(dashboard)
        for key, versions in self.groups.items():
            versions.sort(
                key=lambda item: (
                    _version_date(item),
                    _version_datetime(item),
                    item.modified_ts,
                ),
                reverse=True,
            )
            self.group_titles[key] = _resource_group_title(versions[0])

    def _filtered_group_keys(self) -> list[str]:
        return sorted(
            self.groups,
            key=lambda item: self.group_titles.get(item, "").casefold(),
        )

    def _refresh_dashboard_selector(
        self,
        selected: str | None,
        keys: list[str] | None = None,
    ) -> None:
        self.combo_map.clear()
        self.visible_group_keys = keys if keys is not None else self._filtered_group_keys()
        values: list[str] = []
        for key in self.visible_group_keys:
            base = self.group_titles.get(key, "Recurso")
            label = base
            suffix = 2
            while label in self.combo_map:
                label = f"{base} ({suffix})"
                suffix += 1
            self.combo_map[label] = key
            values.append(label)
        self.dashboard_combo.configure(values=values)

        selected_key = (
            _resource_group_key(self._dashboard_by_relative(selected))
            if self._dashboard_by_relative(selected) is not None
            else self.selected_group_key
        )
        if selected_key not in self.visible_group_keys:
            selected_key = (
                max(
                    self.visible_group_keys,
                    key=lambda key: (
                        _version_date(self.groups[key][0]),
                        _version_datetime(self.groups[key][0]),
                    ),
                )
                if self.visible_group_keys
                else None
            )
        self.selected_group_key = selected_key
        self.updating_combo = True
        if selected_key is not None:
            label = next(
                (
                    display
                    for display, key in self.combo_map.items()
                    if key == selected_key
                ),
                "",
            )
            self.dashboard_var.set(label)
        else:
            self.dashboard_var.set("")
        self.updating_combo = False

    def apply_filters(self, selected: str | None = None) -> None:
        keys = self._filtered_group_keys()
        self._refresh_dashboard_selector(selected, keys)
        if self.selected_group_key is None:
            self.filtered = []
            self.select_dashboard(None)
        else:
            preferred = selected
            if (
                preferred is None
                or self._dashboard_by_relative(preferred) not in self.groups.get(
                    self.selected_group_key,
                    [],
                )
            ):
                preferred = self.groups[self.selected_group_key][0].relative
            self._select_group(self.selected_group_key, preferred)
        self._update_counts()

    def _select_group(
        self,
        group_key: str,
        preferred_relative: str | None = None,
    ) -> None:
        versions = self.groups.get(group_key, [])
        self.selected_group_key = group_key
        self.filtered = list(versions)
        selected = next(
            (
                item
                for item in versions
                if item.relative == preferred_relative
            ),
            versions[0] if versions else None,
        )
        self._refresh_version_selector(versions, selected)
        self.select_dashboard(
            selected.relative if selected else None,
            sync_combo=True,
        )

    def _refresh_version_selector(
        self,
        versions: list[DashboardFile],
        selected: DashboardFile | None,
    ) -> None:
        self.version_date_map.clear()
        for dashboard in versions:
            position_date = _version_date(dashboard).date()
            self.version_date_map.setdefault(position_date, dashboard.relative)
        self.calendar_selected_date = (
            _version_date(selected).date() if selected is not None else None
        )
        self.version_var.set(
            _format_calendar_date(self.calendar_selected_date)
            if self.calendar_selected_date is not None
            else ""
        )
        enabled = bool(versions)
        state = "normal" if enabled else "disabled"
        cursor = "hand2" if enabled else "arrow"
        self.calendar_button.configure(state=state, cursor=cursor)
        self.today_button.configure(state=state, cursor=cursor)
        if self.calendar_window is not None and self.calendar_window.winfo_exists():
            self._render_calendar()

    def on_dashboard_combo_changed(self, _event=None) -> None:
        if self.updating_combo:
            return
        key = self.combo_map.get(self.dashboard_var.get())
        if key is not None:
            self._select_group(key)

    def show_calendar(self) -> None:
        versions = self.groups.get(self.selected_group_key or "", [])
        if not versions:
            self.status("El recurso seleccionado no tiene posiciones disponibles.")
            return
        if self.calendar_window is not None and self.calendar_window.winfo_exists():
            self.calendar_window.lift()
            self.calendar_window.focus_force()
            return

        anchor = self.calendar_selected_date or datetime.now().date()
        self.calendar_display_month = date(anchor.year, anchor.month, 1)
        popup = tk.Toplevel(self.root)
        self.calendar_window = popup
        popup.title("Seleccionar fecha de posición")
        popup.configure(bg=PALETTE["surface"])
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", self._close_calendar)
        popup.bind("<Escape>", lambda _event: self._close_calendar())
        self.calendar_body = tk.Frame(popup, bg=PALETTE["surface"])
        self.calendar_body.pack(fill="both", expand=True, padx=14, pady=14)
        self._render_calendar()
        popup.update_idletasks()
        x = self.version_field.winfo_rootx()
        y = self.version_field.winfo_rooty() + self.version_field.winfo_height() + 4
        popup.geometry(f"{popup.winfo_reqwidth()}x{popup.winfo_reqheight()}{x:+d}{y:+d}")
        popup.grab_set()
        popup.focus_force()

    def _close_calendar(self) -> None:
        popup = self.calendar_window
        self.calendar_window = None
        self.calendar_body = None
        if popup is not None and popup.winfo_exists():
            try:
                popup.grab_release()
            except tk.TclError:
                pass
            popup.destroy()

    def _shift_calendar_month(self, months: int) -> None:
        current = self.calendar_display_month or date.today().replace(day=1)
        offset = current.year * 12 + current.month - 1 + months
        candidate = date(offset // 12, offset % 12 + 1, 1)
        current_month = datetime.now().date().replace(day=1)
        if candidate <= current_month:
            self.calendar_display_month = candidate
            self._render_calendar()

    def _render_calendar(self) -> None:
        body = self.calendar_body
        month = self.calendar_display_month
        if body is None or month is None or not body.winfo_exists():
            return
        for widget in body.winfo_children():
            widget.destroy()

        header = tk.Frame(body, bg=PALETTE["surface"])
        header.grid(row=0, column=0, columnspan=7, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(1, weight=1)
        tk.Button(
            header,
            text="‹",
            command=lambda: self._shift_calendar_month(-1),
            relief="flat",
            bg=PALETTE["soft_blue"],
            fg=PALETTE["primary"],
            cursor="hand2",
            font=("Segoe UI Semibold", 13),
            width=3,
        ).grid(row=0, column=0)
        tk.Label(
            header,
            text=f"{SPANISH_MONTH_NAMES[month.month - 1].capitalize()} {month.year}",
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=1, padx=12)
        next_month = self._month_after(month)
        next_enabled = next_month <= datetime.now().date().replace(day=1)
        tk.Button(
            header,
            text="›",
            command=lambda: self._shift_calendar_month(1),
            state="normal" if next_enabled else "disabled",
            relief="flat",
            bg=PALETTE["soft_blue"],
            fg=PALETTE["primary"],
            disabledforeground=PALETTE["disabled"],
            cursor="hand2" if next_enabled else "arrow",
            font=("Segoe UI Semibold", 13),
            width=3,
        ).grid(row=0, column=2)

        for column, label in enumerate(("LU", "MA", "MI", "JU", "VI", "SÁ", "DO")):
            tk.Label(
                body,
                text=label,
                bg=PALETTE["surface"],
                fg=PALETTE["muted"],
                font=("Segoe UI Semibold", 7),
                width=4,
            ).grid(row=1, column=column, padx=2, pady=(0, 4))

        today = datetime.now().date()
        weeks = calendar_module.Calendar(firstweekday=0).monthdayscalendar(
            month.year,
            month.month,
        )
        for row, week in enumerate(weeks, start=2):
            for column, day_number in enumerate(week):
                if not day_number:
                    tk.Label(body, text="", bg=PALETTE["surface"], width=4).grid(
                        row=row,
                        column=column,
                        padx=2,
                        pady=2,
                    )
                    continue
                value = date(month.year, month.month, day_number)
                available = value in self.version_date_map
                valid = value <= today and (
                    available or _is_colombia_business_day(value)
                )
                selected = value == self.calendar_selected_date
                bg = (
                    PALETTE["accent"]
                    if selected
                    else PALETTE["soft_blue"]
                    if available
                    else PALETTE["surface_alt"]
                )
                fg = PALETTE["primary"] if available or selected else (
                    PALETTE["text"] if valid else PALETTE["disabled"]
                )
                tk.Button(
                    body,
                    text=str(day_number),
                    command=lambda chosen=value: self._select_calendar_date(chosen),
                    relief="solid" if value == today else "flat",
                    borderwidth=1 if value == today else 0,
                    bg=bg,
                    fg=fg,
                    activebackground=PALETTE["soft_gold"],
                    activeforeground=PALETTE["text"],
                    cursor="hand2",
                    font=("Segoe UI Semibold" if available else "Segoe UI", 8),
                    width=4,
                    height=2,
                ).grid(row=row, column=column, padx=2, pady=2)

        legend_row = len(weeks) + 2
        tk.Label(
            body,
            text="Azul: procesada  ·  Amarillo: seleccionada",
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 7),
        ).grid(row=legend_row, column=0, columnspan=7, pady=(9, 0))

    @staticmethod
    def _month_after(value: date) -> date:
        return date(value.year + (1 if value.month == 12 else 0), value.month % 12 + 1, 1)

    def _select_calendar_date(self, selected_date: date) -> None:
        self._close_calendar()
        self._select_position_date(selected_date)

    def _select_position_date(self, selected_date: date) -> None:
        self.calendar_selected_date = selected_date
        date_label = _format_calendar_date(selected_date)
        self.version_var.set(date_label)
        today = datetime.now().date()
        if selected_date > today:
            self._show_unavailable_position(
                date_label,
                "La fecha seleccionada aún no está vigente",
            )
            return
        relative = self.version_date_map.get(selected_date)
        if relative is None:
            self._show_missing_position(date_label)
            return
        self.select_dashboard(relative)
        self.status(f"Posición seleccionada: {date_label}.")

    def select_today(self) -> None:
        versions = self.groups.get(self.selected_group_key or "", [])
        if not versions:
            self.status("El recurso seleccionado no tiene versiones disponibles.")
            return
        self._select_position_date(datetime.now().date())

    def _show_missing_position(self, date_label: str) -> None:
        self._show_unavailable_position(
            date_label,
            "La posición no se ha procesado para la fecha seleccionada",
        )

    def _show_unavailable_position(self, date_label: str, message: str) -> None:
        self.selected_relative = None
        versions = self.groups.get(self.selected_group_key or "", [])
        reference = versions[0] if versions else None
        profile = _dashboard_profile(reference)
        self.title_var.set(profile["title"])
        self.description_var.set(
            f"{message}: {date_label}." if date_label else f"{message}."
        )
        self.coverage_var.set(profile["coverage"])
        self.audience_var.set(profile["audience"])
        self.status_dashboard_var.set("No disponible")
        self.preference_var.set("Sin configuraciones para la fecha seleccionada")
        self.lower_config_var.set("No disponible")
        self.lower_history_var.set(
            f"{len(versions)} posición(es) publicada(s)"
            if versions
            else "Sin publicaciones"
        )
        self.lower_preferences_var.set(
            f"Sin posición seleccionada · {self.user.username}"
        )
        self._set_action_state(False)
        self._update_preview(None, message)
        self._update_daily_comment(self.calendar_selected_date)
        self.status(
            f"{message}: {date_label}." if date_label else f"{message}."
        )
        self._sync_config()
        self._schedule_save()

    def select_dashboard(
        self,
        relative: str | None,
        sync_combo: bool = False,
    ) -> None:
        dashboard = self._dashboard_by_relative(relative)
        self.selected_relative = dashboard.relative if dashboard else None
        profile = _dashboard_profile(dashboard)
        self.title_var.set(profile["title"])
        self.description_var.set(profile["description"])
        self.coverage_var.set(profile["coverage"])
        self.audience_var.set(profile["audience"])
        self.status_dashboard_var.set(profile["status"])

        if dashboard is None:
            self.preference_var.set("Sin configuraciones guardadas")
            self.lower_config_var.set("No disponible")
            self.lower_history_var.set("Sin publicaciones")
            self.lower_preferences_var.set("Sin preferencias")
            self._set_action_state(False)
            self._update_preview(None)
            self._update_daily_comment(None)
            self._sync_config()
            self._schedule_save()
            return

        group_key = _resource_group_key(dashboard)
        self.selected_group_key = group_key
        group_title = self.group_titles.get(
            group_key,
            _resource_group_title(dashboard),
        )
        self.title_var.set(group_title)

        configs = (
            _read_dashboard_configs(self.user, dashboard.relative)
            if dashboard.kind == "dashboard" and dashboard.configurations_enabled
            else {"configurations": []}
        )
        items = [
            item
            for item in configs.get("configurations", [])
            if isinstance(item, dict)
        ]
        count = len(items)
        if dashboard.kind == "dashboard":
            publication_summary = (
                f"Posición efectiva: {_format_position_dates(dashboard)} · "
                f"Publicada: {_format_publication_datetime(dashboard)}."
            )
            self.description_var.set(
                f"{dashboard.description} · {publication_summary}"
                if dashboard.description
                else publication_summary
            )
            self.preference_var.set(
                f"{count} configuración(es) guardada(s)"
                if dashboard.configurations_enabled
                else "Configuraciones no parametrizadas"
            )
            self.open_button.configure(text="Abrir dashboard")
        else:
            self.preference_var.set("No aplica a ejecutables")
            self.open_button.configure(text="Abrir aplicación")

        self._set_action_state(True)

        versions = self.groups.get(group_key, [dashboard])
        self.lower_config_var.set(
            f"{count} guardada(s)"
            if dashboard.kind == "dashboard" and dashboard.configurations_enabled
            else "No parametrizada"
            if dashboard.kind == "dashboard"
            else "No aplica"
        )
        self.lower_history_var.set(
            f"{len(versions)} posición(es) publicada(s)"
        )
        self.lower_latest_var.set(
            _latest_publication_summary(self.dashboards, dashboard)
        )
        self.calendar_selected_date = _version_date(dashboard).date()
        self.version_var.set(_format_calendar_date(self.calendar_selected_date))
        if sync_combo or self.dashboard_var.get() not in self.combo_map:
            self.updating_combo = True
            label = next(
                (
                    display
                    for display, key in self.combo_map.items()
                    if key == group_key
                ),
                "",
            )
            if label:
                self.dashboard_var.set(label)
            self.updating_combo = False

        self._update_preview(dashboard)
        self._update_daily_comment(self.calendar_selected_date)
        self._sync_config()
        self._schedule_save()

    def _set_action_state(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        cursor = "hand2" if enabled else "arrow"
        for button in self.action_buttons:
            button.configure(state=state, cursor=cursor)

    def _insert_comment_inline(
        self,
        text: str,
        base_tag: str,
        *,
        prefix: str = "",
    ) -> None:
        if prefix:
            self.comment_text.insert("end", prefix, (base_tag,))
        position = 0
        for match in re.finditer(r"\*\*(.+?)\*\*", text):
            if match.start() > position:
                self.comment_text.insert(
                    "end",
                    text[position : match.start()],
                    (base_tag,),
                )
            self.comment_text.insert(
                "end",
                match.group(1),
                (base_tag, "comment_bold"),
            )
            position = match.end()
        if position < len(text):
            self.comment_text.insert("end", text[position:], (base_tag,))
        self.comment_text.insert("end", "\n", (base_tag,))

    def _render_daily_comment(self, comment: DailyComment | None) -> None:
        self.comment_text.configure(state="normal")
        self.comment_text.delete("1.0", "end")
        if comment is None:
            self.comment_text.insert(
                "end",
                "El analista aún no ha publicado un comentario para esta fecha.",
                ("comment_empty",),
            )
            self.comment_text.configure(state="disabled")
            return

        tag_map = {
            "h1": "comment_h1",
            "h2": "comment_h2",
            "h3": "comment_h3",
            "paragraph": "comment_paragraph",
            "bullet": "comment_bullet",
            "numbered": "comment_bullet",
            "table_header": "comment_table_header",
            "table_row": "comment_table_row",
        }
        for block_type, text in _markdown_comment_blocks(comment.content):
            tag = tag_map.get(block_type, "comment_paragraph")
            prefix = "• " if block_type == "bullet" else ""
            self._insert_comment_inline(text, tag, prefix=prefix)
        self.comment_text.configure(state="disabled")
        self.comment_text.yview_moveto(0.0)

    def _update_daily_comment(self, selected_date: date | None) -> None:
        self.daily_comment = None
        if selected_date is None:
            self.comment_date_var.set("Sin fecha seleccionada")
            self.comment_meta_var.set("Seleccione una fecha para consultar el comentario")
            self._render_daily_comment(None)
            return

        self.comment_date_var.set(_format_calendar_date(selected_date))
        try:
            comment = _read_daily_comment(selected_date)
        except RuntimeError as exc:
            self.comment_meta_var.set("El archivo del comentario presenta un error")
            self.comment_text.configure(state="normal")
            self.comment_text.delete("1.0", "end")
            self.comment_text.insert("end", str(exc), ("comment_empty",))
            self.comment_text.configure(state="disabled")
            return

        self.daily_comment = comment
        if comment is None:
            self.comment_meta_var.set(
                f"Esperado: {selected_date.isoformat()}.md"
            )
        else:
            try:
                source = comment.path.relative_to(COMMENTS_DIR).as_posix()
            except ValueError:
                source = comment.path.name
            modified = datetime.fromtimestamp(comment.modified_ts)
            self.comment_meta_var.set(
                f"{source} · actualizado {modified.day:02d} "
                f"{SPANISH_MONTHS[modified.month - 1]} {modified:%H:%M}"
            )
        self._render_daily_comment(comment)

    def _find_preview_path(self, dashboard: DashboardFile) -> Path | None:
        image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        if dashboard.path.suffix.casefold() in image_extensions:
            return dashboard.path
        stem = dashboard.path.stem
        names = (
            f"{stem}_preview",
            f"{stem}_thumbnail",
            "preview",
            "thumbnail",
        )
        for folder in (
            dashboard.path.parent,
            dashboard.path.parent / "assets",
            dashboard.path.parent / "images",
            dashboard.path.parent / "img",
        ):
            try:
                if not folder.is_dir():
                    continue
                for name in names:
                    for extension in image_extensions:
                        candidate = folder / f"{name}{extension}"
                        if candidate.is_file():
                            return candidate
            except OSError:
                continue
        return None

    def _update_preview(
        self,
        dashboard: DashboardFile | None,
        empty_message: str = "Seleccione un dashboard.",
    ) -> None:
        if dashboard is None:
            identity = f"empty:{empty_message}"
        elif dashboard.kind == "dashboard":
            signature, _name = self._preview_configuration(dashboard)
            identity = f"{dashboard.relative}|{dashboard.modified_ts}|{signature}"
        else:
            identity = f"{dashboard.relative}|{dashboard.modified_ts}"
        if (
            identity == self.preview_identity
            and (
                self.preview_source is not None
                or self.preview_pending_requests
            )
        ):
            return
        self.preview_identity = identity
        self.preview_request_id += 1
        self.preview_source = None
        self.preview_original = None
        self.preview_photo = None
        self.preview_label.configure(image="")
        if dashboard is None:
            self.preview_text_var.set(empty_message)
            return

        preview = self._find_preview_path(dashboard)
        if preview is not None and Image is not None and ImageTk is not None:
            if self._load_preview_image(preview, preview.name):
                return

        if (
            dashboard.kind == "dashboard"
            and dashboard.path.suffix.casefold() == ".html"
            and Image is not None
            and ImageTk is not None
            and os.environ.get("PORTAL_RISKO_UI_TEST") != "1"
        ):
            if self._start_dashboard_preview(dashboard):
                return

        self._set_preview_fallback(dashboard)

    def _set_preview_fallback(self, dashboard: DashboardFile) -> None:
        self.preview_source = None
        self.preview_original = None
        self.preview_photo = None
        self.preview_label.configure(image="")

        file_type = (
            "Aplicación Windows"
            if dashboard.kind == "application"
            else dashboard.path.suffix.upper().lstrip(".") or "Archivo"
        )
        self.preview_text_var.set(
            f"{_resource_group_title(dashboard)}\n\n"
            f"Posición: {_format_position_dates(dashboard)}\n"
            f"Publicada: {_format_publication_datetime(dashboard)} · {file_type}"
            "\n\nVista previa gráfica no disponible"
        )

    def _preview_configuration(self, dashboard: DashboardFile) -> tuple[str, str]:
        if not dashboard.configurations_enabled:
            return "default", "Vista predeterminada"
        data = _read_dashboard_configs(self.user, dashboard.relative)
        items = [
            item
            for item in data.get("configurations", [])
            if isinstance(item, dict)
        ]
        favorite_id = str(data.get("favorite_id") or "")
        favorite = next(
            (item for item in items if str(item.get("id") or "") == favorite_id),
            None,
        )
        if favorite is None:
            return "default", "Vista predeterminada"
        payload = {
            "id": favorite.get("id"),
            "filters": favorite.get("filters"),
            "themeName": favorite.get("themeName"),
            "updated_at": favorite.get("updated_at"),
        }
        signature = hashlib.sha1(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:14]
        name = str(favorite.get("name") or "Configuración favorita")
        return signature, name

    def _preview_cache_path(
        self,
        dashboard: DashboardFile,
        configuration_signature: str,
    ) -> Path:
        fingerprint = hashlib.sha1(
            (
                f"preview-{PREVIEW_RENDER_VERSION}|"
                f"{dashboard.relative}|{dashboard.modified_ts}|"
                f"{configuration_signature}"
            ).encode("utf-8")
        ).hexdigest()
        return _local_preview_directory() / f"{fingerprint}.png"

    def _load_preview_image(self, path: Path, label: str) -> bool:
        if Image is None or ImageTk is None:
            return False
        try:
            with Image.open(path) as source:
                self.preview_original = source.convert("RGBA").copy()
            self.preview_source = path
            self.preview_text_var.set(label)
            self._render_preview_image()
            return True
        except Exception as exc:
            self.status(f"No fue posible cargar la vista previa: {exc}")
            return False

    def _start_dashboard_preview(self, dashboard: DashboardFile) -> bool:
        if not any(candidate.is_file() for candidate in _browser_candidates()):
            return False
        signature, configuration_name = self._preview_configuration(dashboard)
        target = self._preview_cache_path(dashboard, signature)
        if target.is_file() and self._load_preview_image(
            target,
            f"Vista gráfica · {configuration_name}",
        ):
            return True

        request_id = self.preview_request_id
        self.preview_text_var.set(
            f"Generando vista gráfica de la posición...\n{configuration_name}"
        )
        try:
            url = self.server.dashboard_url(dashboard.relative)
        except OSError as exc:
            self.status(f"No fue posible preparar la vista previa: {exc}")
            return False

        def worker() -> None:
            try:
                generated = _capture_dashboard_preview(
                    url,
                    target,
                    focus_position_chart=(
                        "portfolio_position_monitor"
                        in dashboard.file_name.casefold()
                    ),
                )
                self.preview_queue.put(
                    (
                        request_id,
                        "success",
                        (dashboard.relative, generated, configuration_name),
                    )
                )
            except Exception as exc:
                self.preview_queue.put(
                    (request_id, "error", (dashboard.relative, exc))
                )

        self.preview_pending_requests.add(request_id)
        threading.Thread(target=worker, daemon=True).start()
        if self.preview_poll_after is None:
            self.preview_poll_after = self.root.after(
                120,
                self._poll_preview_queue,
            )
        return True

    def _poll_preview_queue(self) -> None:
        self.preview_poll_after = None
        while True:
            try:
                request_id, event, payload = self.preview_queue.get_nowait()
            except queue.Empty:
                break
            self.preview_pending_requests.discard(request_id)
            if request_id != self.preview_request_id:
                continue
            if event == "success":
                relative, path, configuration_name = payload  # type: ignore[misc]
                if relative == self.selected_relative:
                    self._load_preview_image(
                        Path(path),
                        f"Vista gráfica · {configuration_name}",
                    )
                    self.status("Vista previa gráfica actualizada.")
            else:
                relative, error = payload  # type: ignore[misc]
                dashboard = self._dashboard_by_relative(relative)
                if dashboard is not None and relative == self.selected_relative:
                    self._set_preview_fallback(dashboard)
                    self.status(
                        f"No fue posible generar la vista previa gráfica: {error}"
                    )
        if (
            self.preview_pending_requests
            and self.root.winfo_exists()
        ):
            self.preview_poll_after = self.root.after(
                160,
                self._poll_preview_queue,
            )
        else:
            self._reveal_after_initial_refresh()

    def _schedule_preview_resize(self, _event=None) -> None:
        if self.preview_resize_after is not None:
            self.root.after_cancel(self.preview_resize_after)
        self.preview_resize_after = self.root.after(
            100,
            self._render_preview_image,
        )

    def _render_preview_image(self) -> None:
        self.preview_resize_after = None
        if (
            self.preview_source is None
            or self.preview_original is None
            or Image is None
            or ImageTk is None
        ):
            return
        width = max(
            240,
            min(880, self.preview_label.winfo_width() - 96),
        )
        height = max(
            120,
            min(340, self.preview_label.winfo_height() - 32),
        )
        try:
            modified = int(self.preview_source.stat().st_mtime)
        except OSError:
            modified = 0
        cache_key = (
            str(self.preview_source),
            width // 40,
            height // 40,
            modified,
        )
        photo = self.preview_cache.get(cache_key)
        if photo is None:
            resized = self.preview_original.copy()
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            resized.thumbnail((width, height), resampling)
            photo = ImageTk.PhotoImage(resized)
            if len(self.preview_cache) >= 12:
                self.preview_cache.pop(next(iter(self.preview_cache)))
            self.preview_cache[cache_key] = photo
        self.preview_photo = photo
        self.preview_label.configure(
            image=self.preview_photo,
            compound="top",
            textvariable=self.preview_text_var,
        )

    def _modal(self, title: str, width: int, height: int) -> tk.Toplevel:
        modal = tk.Toplevel(self.root)
        modal.title(title)
        modal.configure(bg=PALETTE["surface"])
        modal.resizable(False, False)
        modal.transient(self.root)
        if ICON_PORTAL.is_file():
            try:
                modal.iconbitmap(str(ICON_PORTAL))
            except tk.TclError:
                pass
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        modal.geometry(f"{width}x{height}{x:+d}{y:+d}")
        modal.grab_set()
        return modal

    def show_selected_detail(self) -> None:
        dashboard = self._dashboard_by_relative(self.selected_relative)
        if dashboard is None:
            return
        modal = self._modal("Detalle del recurso", 620, 390)
        tk.Frame(modal, bg=PALETTE["accent"], height=4).pack(fill="x")
        body = tk.Frame(modal, bg=PALETTE["surface"])
        body.pack(fill="both", expand=True, padx=28, pady=22)
        tk.Label(
            body,
            text=_resource_group_title(dashboard),
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 16),
            wraplength=550,
            justify="left",
        ).pack(anchor="w")
        details = (
            ("Fecha de posición", _format_position_dates(dashboard)),
            ("Publicado", _format_publication_datetime(dashboard)),
            ("Archivo", dashboard.file_name),
            ("Tamaño", _format_size(dashboard.size_bytes)),
            ("Publicado por", dashboard.publisher or "No disponible"),
            ("Ruta", str(dashboard.path)),
        )
        for label, value in details:
            row = tk.Frame(body, bg=PALETTE["surface"])
            row.pack(fill="x", pady=3)
            tk.Label(
                row,
                text=f"{label}:",
                width=18,
                anchor="w",
                bg=PALETTE["surface"],
                fg=PALETTE["muted"],
                font=("Segoe UI Semibold", 8),
            ).pack(side="left")
            tk.Label(
                row,
                text=value,
                anchor="w",
                justify="left",
                wraplength=430,
                bg=PALETTE["surface"],
                fg=PALETTE["text"],
                font=("Segoe UI", 8),
            ).pack(side="left", fill="x", expand=True)
        self._button(
            body,
            "Cerrar",
            modal.destroy,
            "secondary",
        ).pack(anchor="e", side="bottom")

    def _update_counts(self) -> None:
        favorite_groups = sum(
            any(item.relative in self.favorites for item in versions)
            for versions in self.groups.values()
        )
        self.count_var.set(
            f"{len(self.visible_group_keys)} visibles · "
            f"{len(self.groups)} recursos · "
            f"{favorite_groups} favoritos"
        )

    def toggle_favorite(self) -> None:
        dashboard = self._dashboard_by_relative(self.selected_relative)
        if dashboard is None:
            return
        if dashboard.relative in self.favorites:
            self.favorites.remove(dashboard.relative)
            self.status(f"Favorito retirado: {_resource_group_title(dashboard)}")
        else:
            self.favorites.add(dashboard.relative)
            self.status(f"Favorito guardado: {_resource_group_title(dashboard)}")
        self.select_dashboard(dashboard.relative, sync_combo=True)
        self._update_counts()
        self._sync_config()
        self._schedule_save()

    def _track_external_window(
        self,
        process: subprocess.Popen | None,
        work: MonitorWorkArea | None,
        *,
        positioning_requested: bool,
        resource_name: str,
    ) -> None:
        if process is None or work is None or os.name != "nt":
            self.status(
                "El dashboard fue abierto, pero no fue posible ubicar "
                "automáticamente su ventana."
            )
            return
        deadline = time.monotonic() + 10.0

        def poll() -> None:
            if not self.root.winfo_exists():
                return
            handles = _visible_windows_for_pid(process.pid)
            if handles:
                if _move_window_to_monitor(handles[0], work):
                    self.status(
                        f"{resource_name} abierto en el mismo monitor de Portal Risko."
                    )
                else:
                    self.status(
                        f"{resource_name} fue abierto, pero Windows no permitió "
                        "mover su ventana."
                    )
                return
            if time.monotonic() < deadline:
                self.root.after(250, poll)
                return
            if positioning_requested:
                self.status(
                    f"{resource_name} abierto solicitando el mismo monitor; "
                    "Windows no expuso una ventana verificable."
                )
            else:
                self.status(
                    "El dashboard fue abierto, pero no fue posible ubicar "
                    "automáticamente su ventana."
                )

        self.root.after(180, poll)

    def _record_open(self, dashboard: DashboardFile) -> None:
        self.recents = [dashboard.relative] + [
            item for item in self.recents if item != dashboard.relative
        ]
        self.recents = self.recents[:20]
        self.config["last_opened"] = dashboard.relative
        self._sync_config()
        self._schedule_save()

    def open_selected(self) -> None:
        dashboard = self._dashboard_by_relative(self.selected_relative)
        if dashboard is None:
            self.status("Seleccione un recurso antes de abrirlo.")
            return
        if not dashboard.path.is_file():
            messagebox.showerror(
                APP_NAME,
                "El archivo seleccionado ya no está disponible. Actualice la biblioteca.",
                parent=self.root,
            )
            return

        try:
            work = get_current_interface_monitor(self.root)
        except Exception:
            work = None
            self.status("No fue posible consultar el monitor actual; se abrirá normalmente.")

        if dashboard.kind == "application":
            try:
                process = subprocess.Popen(
                    [str(dashboard.path)],
                    cwd=str(dashboard.path.parent),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                )
            except OSError as exc:
                messagebox.showerror(
                    APP_NAME,
                    f"No se pudo iniciar la aplicación.\n\n{exc}",
                    parent=self.root,
                )
                return
            self.runtime_var.set("Aplicación: iniciada")
            self._record_open(dashboard)
            self._track_external_window(
                process,
                work,
                positioning_requested=False,
                resource_name="Aplicación",
            )
            return

        try:
            url = self.server.dashboard_url(dashboard.relative)
            launch = _open_dashboard_window(url, work)
        except OSError as exc:
            messagebox.showerror(
                APP_NAME,
                f"No se pudo abrir el dashboard.\n\n{exc}",
                parent=self.root,
            )
            return
        self.runtime_var.set(
            "Configuraciones: activas"
            if dashboard.configurations_enabled
            else "Dashboard: modo estándar"
        )
        self._record_open(dashboard)
        self._track_external_window(
            launch.process,
            work,
            positioning_requested=launch.positioning_requested,
            resource_name="Dashboard",
        )


def run_self_test() -> int:
    user = _current_user()
    dashboards = _scan_resources()
    config = _load_config(user)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _dashboard_config_dir(user).mkdir(parents=True, exist_ok=True)
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"Logo Risko disponible: {LOGO_RISKO_PNG.exists() or LOGO_RISKO_PNG_FALLBACK.exists() or LOGO_RISKO_SVG.exists()}")
    print(f"Icono Windows disponible: {ICON_PORTAL.exists()}")
    print(f"Usuario: {user.display}")
    dashboard_count = sum(item.kind == "dashboard" for item in dashboards)
    application_count = sum(item.kind == "application" for item in dashboards)
    print(f"Dashboards HTML encontrados: {dashboard_count}")
    print(f"Aplicaciones EXE encontradas: {application_count}")
    print(f"Favoritos guardados: {len(config.get('favorites', []))}")
    if dashboards:
        newest = max(
            dashboards,
            key=lambda item: (
                _position_date(item),
                _version_datetime(item),
                item.modified_ts,
            ),
        )
        total_configs = sum(
            len(_read_dashboard_configs(user, item.relative).get("configurations", []))
            for item in dashboards
            if item.kind == "dashboard" and item.configurations_enabled
        )
        print(
            f"Ultima posicion: {newest.relative} "
            f"({_format_calendar_date(_position_date(newest).date())})"
        )
        print(f"Configuraciones de dashboards guardadas: {total_configs}")
    server = PortalDashboardServer(user)
    server.start()
    print("Puente interno de configuraciones: OK")
    server.stop()
    return 0


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(run_self_test())
    _enable_dpi_awareness()
    root = tk.Tk()
    PortalRiskoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
