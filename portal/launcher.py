# -*- coding: utf-8 -*-
r"""
Launcher independiente para Portal RISKO.

Ubicación recomendada:
    Proyecto Risko\portal\launcher.py

Durante desarrollo busca, en este orden:
    1. script.py
    2. PortalRisko\PortalRisko.exe
    3. PortalRisko.exe

El Launcher:
    - muestra un splash inmediatamente;
    - lee portal.json y detecta la versión vigente;
    - copia esa versión una sola vez al caché local y valida su SHA-256;
    - inicia el Portal en segundo plano;
    - espera a que la ventana del Portal esté visible y respondiendo;
    - se cierra automáticamente;
    - no modifica la lógica interna de script.py.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable
import uuid


APP_NAME = "Portal RISKO"
LAUNCHER_TITLE = "Inicializando Portal RISKO"
PORTAL_WINDOW_PREFIX = "portal risko"

PALETTE = {
    "primary": "#003C86",
    "secondary": "#214A8B",
    "deep": "#081F3D",
    "accent": "#F7BB26",
    "surface": "#FFFFFF",
    "surface_alt": "#F4F7FB",
    "line": "#D5DFEC",
    "text": "#111C2D",
    "muted": "#506078",
    "danger": "#B42318",
}

POLL_INTERVAL_MS = 120
READY_CHECK_INTERVAL_SECONDS = 0.35
LONG_WAIT_SECONDS = 90
PROCESS_EXIT_GRACE_SECONDS = 2.5
MANIFEST_NAME = "portal.json"
SYSTEM_FOLDER_NAME = "Sistema Portal"
PRODUCTION_ROOT_ENV = "PORTAL_RISKO_PRODUCCION"
DEFAULT_PRODUCTION_ROOT = (
    r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado"
)
StatusCallback = Callable[[str, str], None]

# API de Windows.
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

WM_NULL = 0x0000
SMTO_BLOCK = 0x0001
SMTO_ABORTIFHUNG = 0x0002
SW_RESTORE = 9
ERROR_ALREADY_EXISTS = 183
CREATE_NO_WINDOW = 0x08000000


def _enable_dpi_awareness() -> None:
    """Mejora la nitidez del splash en escalas de Windows superiores al 100 %."""
    try:
        # Windows 10/11: Per Monitor DPI Aware V2.
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def _base_dir() -> Path:
    """Carpeta real donde está launcher.py o Launcher.exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path | None:
    """Carpeta temporal de recursos cuando el Launcher se empaqueta."""
    folder = getattr(sys, "_MEIPASS", None)
    return Path(folder).resolve() if folder else None


BASE_DIR = _base_dir()
BUNDLE_DIR = _bundle_dir()


def _production_root() -> Path:
    """
    Retorna la biblioteca productiva sin acceder a la red durante la importación.

    El acceso SMB ocurre dentro del hilo de trabajo, después de mostrar el splash.
    La variable de entorno permite pruebas controladas y contingencias.
    """
    configured = os.environ.get(PRODUCTION_ROOT_ENV, DEFAULT_PRODUCTION_ROOT).strip()
    return Path(configured)


PRODUCTION_ROOT = _production_root()
SYSTEM_ROOT = PRODUCTION_ROOT / SYSTEM_FOLDER_NAME


def _local_portal_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home()
    return base / "PortalRisko"


def _local_config_dir() -> Path:
    """Mantiene las preferencias junto a la instalacion local del Portal."""
    requested = os.environ.get("PORTAL_RISKO_CONFIG_DIR", "").strip()
    legacy = PRODUCTION_ROOT / "Configuraciones"
    if requested:
        candidate = Path(requested).resolve()
        if os.path.normcase(str(candidate)) != os.path.normcase(str(legacy.resolve())):
            return candidate
    return _local_portal_root() / "Configuraciones"


def _setup_logging() -> Path:
    log_dir = _local_portal_root() / "Launcher"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher.log"

    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
    )
    return log_path


LOG_PATH = _setup_logging()
MANIFEST_CACHE_PATH = LOG_PATH.parent / "portal-cache.json"


def _create_single_instance_mutex() -> tuple[int | None, bool]:
    """
    Evita iniciar dos Launchers simultáneamente en la misma sesión de Windows.

    Retorna:
        (handle, already_exists)
    """
    mutex_name = "Local\\PortalRiskoLauncher"
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    if not handle:
        return None, False
    return int(handle), kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def _window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _is_portal_window(hwnd: int) -> bool:
    if not user32.IsWindowVisible(hwnd):
        return False

    # Evita confundir el splash con el Portal.
    if _window_pid(hwnd) == os.getpid():
        return False

    title = _window_title(hwnd).casefold()
    return title.startswith(PORTAL_WINDOW_PREFIX)


def _find_portal_window() -> int | None:
    found: list[int] = []

    @EnumWindowsProc
    def callback(hwnd: int, _lparam: int) -> bool:
        if _is_portal_window(hwnd):
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def _is_window_responding(hwnd: int, timeout_ms: int = 900) -> bool:
    """
    Envía un mensaje vacío y verifica que la interfaz procese mensajes de Windows.

    Es más confiable que comprobar solamente que la ventana existe.
    """
    result = ctypes.c_size_t()
    response = user32.SendMessageTimeoutW(
        hwnd,
        WM_NULL,
        0,
        0,
        SMTO_BLOCK | SMTO_ABORTIFHUNG,
        timeout_ms,
        ctypes.byref(result),
    )
    return bool(response)


def _activate_window(hwnd: int) -> None:
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        logging.exception("No fue posible activar la ventana existente del Portal.")


def _find_logo() -> Path | None:
    candidates: list[Path] = []

    if BUNDLE_DIR is not None:
        candidates.extend(
            [
                BUNDLE_DIR / "logo-risko-56.png",
                BUNDLE_DIR / "logo-risko.png",
                BUNDLE_DIR / "assets" / "logo-risko-56.png",
                BUNDLE_DIR / "assets" / "logo-risko.png",
            ]
        )

    candidates.extend(
        [
            BASE_DIR / "logo-risko-56.png",
            BASE_DIR / "logo-risko.png",
            BASE_DIR / "assets" / "logo-risko-56.png",
            BASE_DIR / "assets" / "logo-risko.png",
            BASE_DIR.parent / "Herramientas" / "dashy" / "logo-risko-56.png",
            BASE_DIR.parent / "Herramientas" / "dashy" / "logo-risko.png",
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _find_icon() -> Path | None:
    candidates: list[Path] = []

    if BUNDLE_DIR is not None:
        candidates.extend(
            [
                BUNDLE_DIR / "portal-risko.ico",
                BUNDLE_DIR / "assets" / "portal-risko.ico",
            ]
        )

    candidates.extend(
        [
            BASE_DIR / "portal-risko.ico",
            BASE_DIR / "assets" / "portal-risko.ico",
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _read_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise RuntimeError(f"El manifiesto {path} no tiene un formato compatible.")
    return manifest


def _manifest_with_context(
    manifest: dict,
    manifest_root: Path,
    production_root: Path,
) -> dict:
    contextual = dict(manifest)
    contextual["__manifest_root"] = str(manifest_root)
    contextual["__production_root"] = str(production_root)
    return contextual


def _load_manifest() -> dict | None:
    """
    Lee el manifiesto productivo y conserva una copia local de contingencia.

    En desarrollo no consulta SMB salvo que se defina PORTAL_RISKO_PRODUCCION.
    En el ejecutable instalado siempre consulta primero ``Sistema Portal`` y
    admite temporalmente el manifiesto antiguo de la raíz durante la migración.
    """
    if not getattr(sys, "frozen", False) and not os.environ.get(PRODUCTION_ROOT_ENV):
        local_path = BASE_DIR / MANIFEST_NAME
        if not local_path.is_file():
            return None
        return _manifest_with_context(_read_manifest(local_path), BASE_DIR, BASE_DIR)

    candidates = (
        (SYSTEM_ROOT / MANIFEST_NAME, SYSTEM_ROOT),
        (PRODUCTION_ROOT / MANIFEST_NAME, PRODUCTION_ROOT),
    )
    last_error: Exception | None = None
    for path, manifest_root in candidates:
        try:
            if not path.is_file():
                continue
            manifest = _manifest_with_context(
                _read_manifest(path),
                manifest_root,
                PRODUCTION_ROOT,
            )
            MANIFEST_CACHE_PATH.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logging.info("Manifiesto productivo leído desde %s", path)
            return manifest
        except (OSError, RuntimeError) as exc:
            last_error = exc
            logging.warning("No se pudo consultar %s: %s", path, exc)

    if MANIFEST_CACHE_PATH.is_file():
        try:
            cached = _read_manifest(MANIFEST_CACHE_PATH)
            logging.warning(
                "Se usará el último manifiesto local porque producción no respondió."
            )
            return cached
        except RuntimeError as exc:
            last_error = exc

    if last_error is not None:
        raise RuntimeError(
            "No fue posible consultar la versión publicada ni la copia local."
        ) from last_error
    return None


def _manifest_path(manifest: dict, key: str, default: str | None = None) -> Path:
    manifest_root = Path(str(manifest.get("__manifest_root") or SYSTEM_ROOT))
    raw = str(manifest.get(key) or default or "").strip()
    if not raw:
        raise RuntimeError(f"Falta '{key}' en {manifest_root / MANIFEST_NAME}.")
    candidate = (manifest_root / Path(raw.replace("/", os.sep))).resolve()
    if not _inside(candidate, manifest_root):
        raise RuntimeError(f"La ruta '{key}' sale de Sistema Portal.")
    return candidate


def _production_path(manifest: dict, key: str, default: str) -> Path:
    production_root = Path(
        str(manifest.get("__production_root") or PRODUCTION_ROOT)
    )
    raw = str(manifest.get(key) or default).strip()
    candidate = (production_root / Path(raw.replace("/", os.sep))).resolve()
    if not _inside(candidate, production_root):
        raise RuntimeError(f"La ruta '{key}' sale de la carpeta de producción.")
    return candidate


def _report_status(
    callback: StatusCallback | None,
    status: str,
    detail: str,
) -> None:
    if callback is not None:
        callback(status, detail)


def _cache_release(
    manifest: dict,
    status_callback: StatusCallback | None = None,
) -> Path:
    version = str(manifest.get("version") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", version):
        raise RuntimeError("La version del manifiesto es invalida.")

    expected_hash = str(manifest.get("entrypoint_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise RuntimeError("El manifiesto no contiene un SHA-256 valido.")

    source_exe = _manifest_path(manifest, "entrypoint")
    local_root = _local_portal_root() / "App"
    cache_dir = local_root / f"{version}-{expected_hash[:12]}"
    cached_exe = cache_dir / source_exe.name
    marker = cache_dir / ".release.json"

    if cached_exe.is_file() and marker.is_file():
        _report_status(
            status_callback,
            f"Validando Portal RISKO {version}",
            "Comprobando la integridad de la version local.",
        )
        try:
            cached_marker = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached_marker = {}
        if (
            cached_marker.get("version") == version
            and cached_marker.get("entrypoint_sha256") == expected_hash
            and _sha256(cached_exe).lower() == expected_hash
        ):
            logging.info("Version %s disponible en cache local.", version)
            _report_status(
                status_callback,
                f"Portal RISKO {version} listo",
                "La version local esta actualizada y validada.",
            )
            return cached_exe

    if not source_exe.is_file():
        raise FileNotFoundError(
            "No se encontró la versión publicada y tampoco hay una copia local "
            f"válida: {source_exe}"
        )

    _report_status(
        status_callback,
        f"Actualizando Portal RISKO a {version}",
        "Copiando la nueva version desde el servidor. Esto ocurre una sola vez.",
    )
    local_root.mkdir(parents=True, exist_ok=True)
    staging = local_root / f".{cache_dir.name}.{uuid.uuid4().hex}.tmp"
    try:
        shutil.copytree(source_exe.parent, staging)
        staged_exe = staging / source_exe.name
        if not staged_exe.is_file() or _sha256(staged_exe).lower() != expected_hash:
            raise RuntimeError("La copia local del Portal no supero la validacion SHA-256.")
        (staging / ".release.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "entrypoint_sha256": expected_hash,
                    "source": str(source_exe),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            staging.replace(cache_dir)
        except FileExistsError:
            # Otra sesion termino de copiar la misma version primero.
            pass
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    if not cached_exe.is_file() or _sha256(cached_exe).lower() != expected_hash:
        raise RuntimeError("No fue posible preparar la version local del Portal.")
    logging.info("Version %s copiada y validada en cache local.", version)
    _report_status(
        status_callback,
        f"Portal RISKO {version} actualizado",
        "La nueva version fue copiada y validada correctamente.",
    )
    return cached_exe


def _resolve_portal_command(
    status_callback: StatusCallback | None = None,
) -> tuple[list[str], Path, str, dict[str, str]]:
    """
    Localiza automáticamente la forma disponible de iniciar el Portal.

    Retorna:
        command, working_directory, mode, environment
    """
    if getattr(sys, "frozen", False) or os.environ.get(PRODUCTION_ROOT_ENV):
        _report_status(
            status_callback,
            "Buscando actualizaciones",
            "Consultando la versión publicada en el servidor.",
        )
    manifest = _load_manifest()
    if manifest is not None:
        version = str(manifest.get("version") or "").strip()
        _report_status(
            status_callback,
            f"Versión publicada: {version}",
            "Validando la copia disponible en este equipo.",
        )
        cached_exe = _cache_release(manifest, status_callback=status_callback)
        environment = os.environ.copy()
        environment["PORTAL_RISKO_PUBLICADOS"] = str(
            _production_path(manifest, "dashboards_dir", "Dashboards")
        )
        environment["PORTAL_RISKO_COMENTARIOS"] = str(
            _production_path(
                manifest,
                "comments_dir",
                "Comentarios diarios",
            )
        )
        environment["PORTAL_RISKO_CONFIG_DIR"] = str(_local_config_dir())
        environment["PORTAL_RISKO_APLICACIONES"] = str(
            _production_path(manifest, "applications_dir", "Aplicaciones")
        )
        project_root = str(manifest.get("project_root") or "").strip()
        if project_root:
            environment["PORTAL_RISKO_ROOT"] = project_root
        return [str(cached_exe)], cached_exe.parent, "release-cache", environment

    portal_in_folder = BASE_DIR / "PortalRisko" / "PortalRisko.exe"
    portal_direct = BASE_DIR / "PortalRisko.exe"
    portal_script = BASE_DIR / "script.py"
    environment = os.environ.copy()

    if portal_script.is_file() and not getattr(sys, "frozen", False):
        python_executable = Path(sys.executable)
        pythonw = python_executable.with_name("pythonw.exe")
        runtime = pythonw if pythonw.is_file() else python_executable
        return [str(runtime), str(portal_script)], BASE_DIR, "script", environment

    if portal_in_folder.is_file():
        return [str(portal_in_folder)], portal_in_folder.parent, "exe-folder", environment

    current_executable = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None
    if portal_direct.is_file() and (
        current_executable is None or portal_direct.resolve() != current_executable
    ):
        return [str(portal_direct)], BASE_DIR, "exe-direct", environment

    if portal_script.is_file():
        python_executable = Path(sys.executable)

        # Evita mostrar una consola negra cuando el Launcher se ejecuta con python.exe.
        pythonw = python_executable.with_name("pythonw.exe")
        runtime = pythonw if pythonw.is_file() else python_executable

        return [str(runtime), str(portal_script)], BASE_DIR, "script", environment

    expected = (
        f"No se encontró el Portal.\n\n"
        f"El Launcher buscó:\n"
        f"• {portal_in_folder}\n"
        f"• {portal_direct}\n"
        f"• {portal_script}"
    )
    raise FileNotFoundError(expected)


class LauncherApp:
    def __init__(self, root: tk.Tk, mutex_handle: int | None) -> None:
        self.root = root
        self.mutex_handle = mutex_handle
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[bytes] | None = None
        self.logo_image: tk.PhotoImage | None = None
        self.started_at = time.monotonic()
        self.long_wait_message_shown = False
        self.failed = False

        self.status_var = tk.StringVar(value="Inicializando Portal RISKO...")
        self.detail_var = tk.StringVar(value="Preparando el entorno de trabajo.")
        self.footer_var = tk.StringVar(value="RISKO · Riesgo de Mercado")

        self._configure_root()
        self._configure_styles()
        self._build_ui()
        self._center_window()

        # Garantiza que el splash se pinte antes de tocar el Portal o la red.
        self.root.update_idletasks()
        self.root.update()

        self.root.after(POLL_INTERVAL_MS, self._process_events)
        self.root.after(220, self._begin)

    def _configure_root(self) -> None:
        self.root.title(LAUNCHER_TITLE)
        self.root.geometry("560x320")
        self.root.resizable(False, False)
        self.root.configure(bg=PALETTE["line"])
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        icon = _find_icon()
        if icon is not None:
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError:
                logging.exception("No se pudo cargar el icono del Launcher.")

        self.root.bind("<Escape>", self._on_escape)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "RISKO.Horizontal.TProgressbar",
            troughcolor="#E4EAF2",
            background=PALETTE["accent"],
            bordercolor="#E4EAF2",
            lightcolor=PALETTE["accent"],
            darkcolor=PALETTE["accent"],
            thickness=8,
        )

    def _build_ui(self) -> None:
        shell = tk.Frame(
            self.root,
            bg=PALETTE["surface"],
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )
        shell.pack(fill="both", expand=True, padx=1, pady=1)

        tk.Frame(shell, bg=PALETTE["accent"], height=6).pack(fill="x")

        header = tk.Frame(shell, bg=PALETTE["primary"], height=116)
        header.pack(fill="x")
        header.pack_propagate(False)

        logo_box = tk.Frame(header, bg=PALETTE["surface"])
        logo_box.pack(side="left", padx=(28, 20), pady=22)

        logo = _find_logo()
        if logo is not None:
            try:
                self.logo_image = tk.PhotoImage(file=str(logo))

                # Reduce imágenes demasiado grandes sin depender de Pillow.
                max_width = 130
                if self.logo_image.width() > max_width:
                    factor = max(1, round(self.logo_image.width() / max_width))
                    self.logo_image = self.logo_image.subsample(factor, factor)

                tk.Label(
                    logo_box,
                    image=self.logo_image,
                    bg=PALETTE["surface"],
                    borderwidth=0,
                ).pack(padx=14, pady=10)
            except tk.TclError:
                logging.exception("No se pudo cargar el logo RISKO.")
                self._build_text_logo(logo_box)
        else:
            self._build_text_logo(logo_box)

        title_box = tk.Frame(header, bg=PALETTE["primary"])
        title_box.pack(side="left", fill="both", expand=True, pady=22)

        tk.Label(
            title_box,
            text="PORTAL CORPORATIVO",
            bg=PALETTE["primary"],
            fg=PALETTE["accent"],
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w", pady=(7, 2))

        tk.Label(
            title_box,
            text="Portal RISKO",
            bg=PALETTE["primary"],
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 23),
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Acceso ejecutivo a tableros de Riesgo de Mercado",
            bg=PALETTE["primary"],
            fg="#DCE8F7",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(shell, bg=PALETTE["surface"])
        body.pack(fill="both", expand=True, padx=34, pady=(25, 18))

        tk.Label(
            body,
            textvariable=self.status_var,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            body,
            textvariable=self.detail_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(5, 18))

        self.progress = ttk.Progressbar(
            body,
            mode="indeterminate",
            style="RISKO.Horizontal.TProgressbar",
            length=492,
        )
        self.progress.pack(fill="x")
        self.progress.start(12)

        footer = tk.Frame(shell, bg=PALETTE["surface_alt"], height=39)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        tk.Label(
            footer,
            textvariable=self.footer_var,
            bg=PALETTE["surface_alt"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 8),
        ).pack(side="left", padx=18)

        tk.Label(
            footer,
            text="Conexión segura a recursos corporativos",
            bg=PALETTE["surface_alt"],
            fg=PALETTE["muted"],
            font=("Segoe UI", 8),
        ).pack(side="right", padx=18)

    def _build_text_logo(self, parent: tk.Widget) -> None:
        tk.Label(
            parent,
            text="RISKO",
            bg=PALETTE["surface"],
            fg=PALETTE["primary"],
            font=("Segoe UI Semibold", 21),
        ).pack(padx=18, pady=11)

    def _center_window(self) -> None:
        self.root.update_idletasks()

        width = self.root.winfo_width()
        height = self.root.winfo_height()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2 - 25)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _begin(self) -> None:
        existing = _find_portal_window()
        if existing is not None and _is_window_responding(existing):
            logging.info("Se detectó una instancia existente del Portal.")
            _activate_window(existing)
            self._finish_success()
            return

        worker = threading.Thread(target=self._launch_and_monitor, daemon=True)
        worker.start()

    def _launch_and_monitor(self) -> None:
        try:
            def report_status(status: str, detail: str) -> None:
                self.events.put(("status", (status, detail)))

            command, working_dir, mode, environment = _resolve_portal_command(
                status_callback=report_status
            )
            logging.info(
                "Iniciando Portal. Modo=%s | Directorio=%s | Comando=%s",
                mode,
                working_dir,
                command,
            )

            self.events.put(
                (
                    "status",
                    (
                        "Cargando dashboards y configuraciones...",
                        "El Portal aparecerá cuando termine la actualización inicial.",
                    ),
                )
            )

            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            creationflags = CREATE_NO_WINDOW if mode == "script" else 0

            self.process = subprocess.Popen(
                command,
                cwd=str(working_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags,
                env=environment,
            )

            logging.info("Proceso iniciado. PID=%s", self.process.pid)

            exit_detected_at: float | None = None

            while True:
                hwnd = _find_portal_window()

                if hwnd is not None and _is_window_responding(hwnd):
                    logging.info(
                        "Portal listo. HWND=%s | PID ventana=%s",
                        hwnd,
                        _window_pid(hwnd),
                    )
                    self.events.put(("ready", hwnd))
                    return

                exit_code = self.process.poll()
                if exit_code is not None:
                    if exit_detected_at is None:
                        exit_detected_at = time.monotonic()
                        logging.warning(
                            "El proceso inicial terminó antes de detectar la ventana. Código=%s",
                            exit_code,
                        )

                    # Da margen para builds onefile que lancen un proceso hijo.
                    if time.monotonic() - exit_detected_at >= PROCESS_EXIT_GRACE_SECONDS:
                        hwnd = _find_portal_window()
                        if hwnd is not None and _is_window_responding(hwnd):
                            self.events.put(("ready", hwnd))
                            return

                        raise RuntimeError(
                            "Portal RISKO terminó antes de mostrar su ventana "
                            f"(código de salida: {exit_code})."
                        )

                elapsed = time.monotonic() - self.started_at
                if elapsed >= LONG_WAIT_SECONDS and not self.long_wait_message_shown:
                    self.long_wait_message_shown = True
                    self.events.put(
                        (
                            "status",
                            (
                                "El Portal continúa iniciando...",
                                "La conexión de red puede tardar más de lo habitual.",
                            ),
                        )
                    )

                time.sleep(READY_CHECK_INTERVAL_SECONDS)

        except Exception as exc:
            logging.exception("Fallo durante el inicio del Portal.")
            self.events.put(("error", str(exc)))

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()

                if event == "status":
                    status, detail = payload  # type: ignore[misc]
                    self.status_var.set(str(status))
                    self.detail_var.set(str(detail))

                elif event == "ready":
                    hwnd = int(payload)
                    _activate_window(hwnd)
                    self._finish_success()
                    return

                elif event == "error":
                    self._show_error(str(payload))
                    return

        except queue.Empty:
            pass

        if self.root.winfo_exists():
            self.root.after(POLL_INTERVAL_MS, self._process_events)

    def _finish_success(self) -> None:
        self.progress.stop()
        self.status_var.set("Portal RISKO listo")
        self.detail_var.set("Abriendo el entorno de trabajo.")
        self.root.attributes("-topmost", False)
        self.root.after(180, self._close)

    def _show_error(self, detail: str) -> None:
        self.failed = True
        self.progress.stop()
        self.status_var.set("No fue posible iniciar Portal RISKO")
        self.detail_var.set("Revise el detalle del error.")
        self.root.attributes("-topmost", False)

        messagebox.showerror(
            APP_NAME,
            f"{detail}\n\n"
            f"Registro técnico:\n{LOG_PATH}",
            parent=self.root,
        )
        self._close()

    def _on_escape(self, _event=None) -> None:
        # Escape solo cierra el Launcher cuando ocurrió un error.
        if self.failed:
            self._close()

    def _close(self) -> None:
        try:
            self.root.destroy()
        finally:
            if self.mutex_handle:
                kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Este Launcher está diseñado exclusivamente para Windows.")

    if "--self-test" in sys.argv:
        command, working_dir, mode, environment = _resolve_portal_command()
        lines = [
            f"Modo: {mode}",
            f"Comando: {command[0]}",
            f"Directorio: {working_dir}",
            f"Dashboards: {environment.get('PORTAL_RISKO_PUBLICADOS', '')}",
            f"Comentarios: {environment.get('PORTAL_RISKO_COMENTARIOS', '')}",
            f"Aplicaciones: {environment.get('PORTAL_RISKO_APLICACIONES', '')}",
            f"Configuraciones: {environment.get('PORTAL_RISKO_CONFIG_DIR', '')}",
        ]
        if sys.stdout is not None:
            print("\n".join(lines))
        else:
            # Los ejecutables --windowed no tienen consola. Registrar el
            # resultado evita un dialogo de error durante la autoprueba.
            for line in lines:
                logging.info("SELF-TEST | %s", line)
        return

    _enable_dpi_awareness()
    logging.info("========== Inicio Launcher ==========")
    logging.info("BASE_DIR=%s", BASE_DIR)

    mutex_handle, already_exists = _create_single_instance_mutex()

    if already_exists:
        existing = _find_portal_window()
        if existing is not None:
            _activate_window(existing)
            logging.info("Se activó una instancia existente del Portal.")
        else:
            # Otro Launcher ya está esperando a que el Portal termine de iniciar.
            hidden = tk.Tk()
            hidden.withdraw()
            messagebox.showinfo(
                APP_NAME,
                "Portal RISKO ya se está iniciando.\n"
                "Espere a que finalice la carga.",
                parent=hidden,
            )
            hidden.destroy()

        if mutex_handle:
            kernel32.CloseHandle(mutex_handle)
        return

    root = tk.Tk()
    LauncherApp(root, mutex_handle)
    root.mainloop()


if __name__ == "__main__":
    main()
