# -*- coding: utf-8 -*-
"""Launcher local y autoactualizable de Portal RISKO para macOS ARM64.

Este modulo es independiente del launcher de Windows. Consulta exclusivamente
``Sistema Portal/portal-macos.json``, copia la aplicacion publicada al disco
local y la abre desde ``~/Library/Application Support/PortalRisko``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import BinaryIO, Callable
import uuid
import zipfile


APP_NAME = "Portal RISKO"
LAUNCHER_TITLE = "Inicializando Portal RISKO"
MANIFEST_NAME = "portal-macos.json"
SYSTEM_FOLDER_NAME = "Sistema Portal"
PRODUCTION_ROOT_ENV = "PORTAL_RISKO_PRODUCCION"
LOCAL_ROOT_ENV = "PORTAL_RISKO_MAC_LOCAL_ROOT"
VOLUMES_ROOT_ENV = "PORTAL_RISKO_MAC_VOLUMES_ROOT"
DEFAULT_SMB_URL = "smb://ISILONSMBPROD/Gerencia_Riesgo_De_Tesoreria"
DEFAULT_SHARE_NAME = "Gerencia_Riesgo_De_Tesoreria"
PRODUCTION_FOLDER_NAME = "Portal Riesgos de Mercado"
POLL_INTERVAL_MS = 120
READY_GRACE_SECONDS = 2.0
MOUNT_WAIT_SECONDS = 45.0
StatusCallback = Callable[[str, str], None]

PALETTE = {
    "primary": "#003C86",
    "deep": "#081F3D",
    "accent": "#F7BB26",
    "surface": "#FFFFFF",
    "line": "#D5DFEC",
    "text": "#111C2D",
    "muted": "#506078",
}


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path | None:
    folder = getattr(sys, "_MEIPASS", None)
    return Path(folder).resolve() if folder else None


BASE_DIR = _base_dir()
BUNDLE_DIR = _bundle_dir()


def _local_portal_root() -> Path:
    override = os.environ.get(LOCAL_ROOT_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Library" / "Application Support" / "PortalRisko").resolve()


def _setup_logging() -> Path:
    log_dir = _local_portal_root() / "Launcher"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher-macos.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
    )
    return log_path


LOG_PATH = _setup_logging()
MANIFEST_CACHE_PATH = LOG_PATH.parent / "portal-macos-cache.json"


def _find_logo() -> Path | None:
    candidates: list[Path] = []
    if BUNDLE_DIR is not None:
        candidates.extend(
            [
                BUNDLE_DIR / "logo-risko-56.png",
                BUNDLE_DIR / "logo-risko.png",
                BUNDLE_DIR / "portal-risko-256.png",
            ]
        )
    candidates.extend(
        [
            BASE_DIR / "logo-risko-56.png",
            BASE_DIR / "logo-risko.png",
            BASE_DIR / "portal-risko-256.png",
            BASE_DIR.parent / "assets" / "portal-risko-256.png",
        ]
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _volumes_root() -> Path:
    configured = os.environ.get(VOLUMES_ROOT_ENV, "").strip()
    return Path(configured).expanduser() if configured else Path("/Volumes")


def _production_candidates(volumes_root: Path | None = None) -> list[Path]:
    """Genera candidatos sin recorrer recursivamente la carpeta compartida."""
    configured = os.environ.get(PRODUCTION_ROOT_ENV, "").strip()
    if configured:
        return [Path(configured).expanduser()]

    volumes = volumes_root or _volumes_root()
    candidates = [
        volumes / DEFAULT_SHARE_NAME / PRODUCTION_FOLDER_NAME,
        volumes / PRODUCTION_FOLDER_NAME,
    ]
    try:
        mounted = sorted(volumes.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        mounted = []
    for volume in mounted:
        candidates.extend(
            [
                volume / PRODUCTION_FOLDER_NAME,
                volume / DEFAULT_SHARE_NAME / PRODUCTION_FOLDER_NAME,
            ]
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def _discover_production_root(volumes_root: Path | None = None) -> Path | None:
    for candidate in _production_candidates(volumes_root):
        manifest = candidate / SYSTEM_FOLDER_NAME / MANIFEST_NAME
        try:
            if candidate.is_dir() and manifest.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _report(callback: StatusCallback | None, status: str, detail: str) -> None:
    if callback is not None:
        callback(status, detail)


def _ensure_production_root(
    status_callback: StatusCallback | None = None,
    *,
    wait_seconds: float = MOUNT_WAIT_SECONDS,
) -> Path | None:
    root = _discover_production_root()
    if root is not None:
        return root

    if sys.platform != "darwin" or os.environ.get(PRODUCTION_ROOT_ENV):
        return None

    _report(
        status_callback,
        "Conectando con la red corporativa",
        "Abriendo la carpeta compartida de Portal RISKO.",
    )
    try:
        subprocess.Popen(
            ["/usr/bin/open", DEFAULT_SMB_URL],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        logging.warning("No se pudo solicitar el montaje SMB: %s", exc)
        return None

    deadline = time.monotonic() + max(0.0, wait_seconds)
    while time.monotonic() < deadline:
        root = _discover_production_root()
        if root is not None:
            return root
        time.sleep(0.5)
    return None


def _read_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise RuntimeError(f"El manifiesto {path} no tiene un formato compatible.")
    platform_name = str(manifest.get("platform") or "")
    architecture = str(manifest.get("architecture") or "")
    if platform_name != "macos" or architecture != "arm64":
        raise RuntimeError("El manifiesto no corresponde a macOS ARM64.")
    return manifest


def _manifest_with_context(manifest: dict, production_root: Path) -> dict:
    contextual = dict(manifest)
    contextual["__production_root"] = str(production_root)
    contextual["__manifest_root"] = str(production_root / SYSTEM_FOLDER_NAME)
    return contextual


def _write_manifest_cache(manifest: dict) -> None:
    temporary = MANIFEST_CACHE_PATH.with_name(
        f".{MANIFEST_CACHE_PATH.name}.{uuid.uuid4().hex}.tmp"
    )
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, MANIFEST_CACHE_PATH)


def _load_manifest(status_callback: StatusCallback | None = None) -> dict:
    local_manifest = BASE_DIR / MANIFEST_NAME
    if not getattr(sys, "frozen", False) and local_manifest.is_file():
        return _manifest_with_context(_read_manifest(local_manifest), BASE_DIR)

    last_error: Exception | None = None
    production_root = _ensure_production_root(status_callback)
    if production_root is not None:
        manifest_path = production_root / SYSTEM_FOLDER_NAME / MANIFEST_NAME
        try:
            manifest = _manifest_with_context(
                _read_manifest(manifest_path), production_root
            )
            _write_manifest_cache(manifest)
            logging.info("Manifiesto macOS leido desde %s", manifest_path)
            return manifest
        except (OSError, RuntimeError) as exc:
            last_error = exc
            logging.warning("No se pudo consultar %s: %s", manifest_path, exc)

    if MANIFEST_CACHE_PATH.is_file():
        try:
            cached = _read_manifest(MANIFEST_CACHE_PATH)
            logging.warning("Se usara el ultimo manifiesto macOS local valido.")
            return cached
        except RuntimeError as exc:
            last_error = exc

    message = (
        "No fue posible encontrar Portal RISKO en la carpeta compartida. "
        "Conecte la VPN, abra la unidad de red e intente nuevamente."
    )
    raise RuntimeError(message) from last_error


def _safe_relative_path(raw: object, field: str) -> Path:
    value = str(raw or "").strip()
    posix = PurePosixPath(value)
    if not value or posix.is_absolute() or ".." in posix.parts:
        raise RuntimeError(f"La ruta '{field}' del manifiesto no es valida.")
    return Path(*posix.parts)


def _manifest_path(manifest: dict, field: str) -> Path:
    manifest_root = Path(str(manifest.get("__manifest_root") or ""))
    relative = _safe_relative_path(manifest.get(field), field)
    candidate = (manifest_root / relative).resolve()
    if not _inside(candidate, manifest_root):
        raise RuntimeError(f"La ruta '{field}' sale de Sistema Portal.")
    return candidate


def _production_path(manifest: dict, field: str, default: str) -> Path:
    production_root = Path(str(manifest.get("__production_root") or ""))
    relative = _safe_relative_path(manifest.get(field) or default, field)
    candidate = (production_root / relative).resolve()
    if not _inside(candidate, production_root):
        raise RuntimeError(f"La ruta '{field}' sale de la carpeta de produccion.")
    return candidate


def _bundle_paths(manifest: dict, cache_dir: Path) -> tuple[Path, Path]:
    bundle_name = str(manifest.get("bundle") or "").strip()
    if (
        not bundle_name.endswith(".app")
        or Path(bundle_name).name != bundle_name
        or bundle_name in {".app", "..app"}
    ):
        raise RuntimeError("El nombre del bundle macOS no es valido.")
    executable_relative = _safe_relative_path(
        manifest.get("executable"), "executable"
    )
    bundle = cache_dir / bundle_name
    executable = bundle / executable_relative
    if not _inside(executable, bundle):
        raise RuntimeError("El ejecutable sale del bundle macOS.")
    return bundle, executable


def _verify_code_signature(bundle: Path) -> None:
    if sys.platform != "darwin":
        raise RuntimeError("La firma del bundle solo puede validarse en macOS.")
    completed = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=45,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "firma no valida"
        raise RuntimeError(f"La firma de Portal RISKO no es valida: {detail}")


def _validate_cached_release(manifest: dict, cache_dir: Path) -> Path | None:
    expected_hash = str(manifest.get("executable_sha256") or "").strip().lower()
    marker_path = cache_dir / ".release.json"
    bundle, executable = _bundle_paths(manifest, cache_dir)
    if not executable.is_file() or not marker_path.is_file():
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        marker.get("version") != str(manifest.get("version") or "")
        or marker.get("executable_sha256") != expected_hash
        or _sha256(executable).lower() != expected_hash
    ):
        return None
    if bool(manifest.get("require_code_signature", True)):
        _verify_code_signature(bundle)
    return executable


def _extract_package(package: Path, destination: Path) -> None:
    """Extrae el ZIP conservando permisos y enlaces de un bundle en macOS."""
    if sys.platform == "darwin" and Path("/usr/bin/ditto").is_file():
        completed = subprocess.run(
            ["/usr/bin/ditto", "-x", "-k", str(package), str(destination)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "No se pudo extraer la aplicacion: "
                + (completed.stderr.strip() or "error de ditto")
            )
        return

    destination = destination.resolve()
    with zipfile.ZipFile(package) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not _inside(target, destination):
                raise RuntimeError("El paquete contiene una ruta no permitida.")
        archive.extractall(destination)


def _cache_release(
    manifest: dict,
    status_callback: StatusCallback | None = None,
) -> Path:
    version = str(manifest.get("version") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", version):
        raise RuntimeError("La version del manifiesto no es valida.")

    package_hash = str(manifest.get("package_sha256") or "").strip().lower()
    executable_hash = str(manifest.get("executable_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", package_hash):
        raise RuntimeError("El manifiesto no contiene el SHA-256 del paquete.")
    if not re.fullmatch(r"[0-9a-f]{64}", executable_hash):
        raise RuntimeError("El manifiesto no contiene el SHA-256 del ejecutable.")

    local_root = _local_portal_root() / "App"
    cache_dir = local_root / f"{version}-{package_hash[:12]}"
    _report(
        status_callback,
        f"Validando Portal RISKO {version}",
        "Comprobando la version disponible en este Mac.",
    )
    cached = _validate_cached_release(manifest, cache_dir)
    if cached is not None:
        return cached

    if cache_dir.exists():
        if not _inside(cache_dir, local_root) or not cache_dir.name.startswith(
            f"{version}-"
        ):
            raise RuntimeError("Se rechazo limpiar una ruta de cache inesperada.")
        shutil.rmtree(cache_dir)

    source_package = _manifest_path(manifest, "package")
    if not source_package.is_file():
        raise FileNotFoundError(
            "La version publicada no esta disponible y no existe una copia local valida."
        )
    if _sha256(source_package).lower() != package_hash:
        raise RuntimeError("El paquete publicado no supero la validacion SHA-256.")

    _report(
        status_callback,
        f"Actualizando Portal RISKO a {version}",
        "Copiando la aplicacion desde el servidor. Esto ocurre una sola vez.",
    )
    local_root.mkdir(parents=True, exist_ok=True)
    staging = local_root / f".{cache_dir.name}.{uuid.uuid4().hex}.tmp"
    staging.mkdir(parents=True)
    local_package = staging / "Portal-RISKO-macOS-arm64.zip"
    try:
        shutil.copy2(source_package, local_package)
        if _sha256(local_package).lower() != package_hash:
            raise RuntimeError("La copia local del paquete no supero la validacion.")
        _extract_package(local_package, staging)
        local_package.unlink(missing_ok=True)
        bundle, executable = _bundle_paths(manifest, staging)
        if not executable.is_file() or _sha256(executable).lower() != executable_hash:
            raise RuntimeError("El ejecutable extraido no supero la validacion SHA-256.")
        if bool(manifest.get("require_code_signature", True)):
            _verify_code_signature(bundle)
        (staging / ".release.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "platform": "macos",
                    "architecture": "arm64",
                    "package_sha256": package_hash,
                    "executable_sha256": executable_hash,
                    "source": str(source_package),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            staging.replace(cache_dir)
        except FileExistsError:
            pass
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    cached = _validate_cached_release(manifest, cache_dir)
    if cached is None:
        raise RuntimeError("No fue posible preparar la version local de Portal RISKO.")
    return cached


def _application_environment(manifest: dict) -> dict[str, str]:
    environment = os.environ.copy()
    local_root = _local_portal_root()
    applications_dir = local_root / "Aplicaciones"
    applications_dir.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "PORTAL_RISKO_PUBLICADOS": str(
                _production_path(manifest, "dashboards_dir", "Dashboards")
            ),
            "PORTAL_RISKO_COMENTARIOS": str(
                _production_path(
                    manifest,
                    "comments_dir",
                    "Comentarios diarios",
                )
            ),
            "PORTAL_RISKO_APLICACIONES": str(applications_dir),
            "PORTAL_RISKO_CONFIG_DIR": str(local_root / "Configuraciones"),
            "PORTAL_RISKO_PRODUCCION": str(
                Path(str(manifest.get("__production_root") or ""))
            ),
            "PORTAL_RISKO_PLATFORM": "macos-arm64",
            # script.py conserva su comportamiento Windows; este valor hace que
            # sus caches vivan en Application Support dentro del proceso Mac.
            "LOCALAPPDATA": str(Path.home() / "Library" / "Application Support"),
        }
    )
    return environment


def _resolve_portal_command(
    status_callback: StatusCallback | None = None,
) -> tuple[list[str], Path, dict[str, str], str]:
    _report(
        status_callback,
        "Buscando actualizaciones",
        "Consultando la version ARM64 publicada en el servidor.",
    )
    manifest = _load_manifest(status_callback)
    executable = _cache_release(manifest, status_callback)
    environment = _application_environment(manifest)
    return [str(executable)], executable.parent, environment, str(manifest["version"])


def _acquire_single_instance_lock() -> tuple[BinaryIO | None, bool]:
    if sys.platform != "darwin":
        return None, False
    import fcntl

    lock_path = _local_portal_root() / "Launcher" / "launcher.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None, True
    return handle, False


class LauncherApp:
    def __init__(self, root: tk.Tk, lock_handle: BinaryIO | None) -> None:
        self.root = root
        self.lock_handle = lock_handle
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[bytes] | None = None
        self.logo_image: tk.PhotoImage | None = None
        self.failed = False
        self.status_var = tk.StringVar(value="Inicializando Portal RISKO...")
        self.detail_var = tk.StringVar(value="Preparando el entorno de trabajo.")

        self._configure_root()
        self._build_ui()
        self._center_window()
        self.root.update_idletasks()
        self.root.after(POLL_INTERVAL_MS, self._process_events)
        self.root.after(220, self._begin)

    def _configure_root(self) -> None:
        self.root.title(LAUNCHER_TITLE)
        self.root.geometry("560x320")
        self.root.resizable(False, False)
        self.root.configure(bg=PALETTE["line"])
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.bind("<Escape>", self._on_escape)

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
                if self.logo_image.width() > 130:
                    factor = max(1, round(self.logo_image.width() / 130))
                    self.logo_image = self.logo_image.subsample(factor, factor)
                tk.Label(
                    logo_box,
                    image=self.logo_image,
                    bg=PALETTE["surface"],
                    borderwidth=0,
                ).pack(padx=14, pady=10)
            except tk.TclError:
                self._text_logo(logo_box)
        else:
            self._text_logo(logo_box)

        title_box = tk.Frame(header, bg=PALETTE["primary"])
        title_box.pack(side="left", fill="both", expand=True, pady=22)
        tk.Label(
            title_box,
            text="PORTAL CORPORATIVO",
            bg=PALETTE["primary"],
            fg=PALETTE["accent"],
            font=("Helvetica Neue", 9, "bold"),
        ).pack(anchor="w", pady=(7, 2))
        tk.Label(
            title_box,
            text="Portal RISKO",
            bg=PALETTE["primary"],
            fg="#FFFFFF",
            font=("Helvetica Neue", 23, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Riesgo de Mercado · macOS ARM64",
            bg=PALETTE["primary"],
            fg="#DCE8F7",
            font=("Helvetica Neue", 10),
        ).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(shell, bg=PALETTE["surface"])
        body.pack(fill="both", expand=True, padx=34, pady=(25, 18))
        tk.Label(
            body,
            textvariable=self.status_var,
            bg=PALETTE["surface"],
            fg=PALETTE["text"],
            font=("Helvetica Neue", 13, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            textvariable=self.detail_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=("Helvetica Neue", 10),
            anchor="w",
        ).pack(fill="x", pady=(5, 16))
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "RISKO.Horizontal.TProgressbar",
            troughcolor="#E4EAF2",
            background=PALETTE["accent"],
            thickness=8,
        )
        self.progress = ttk.Progressbar(
            body,
            mode="indeterminate",
            style="RISKO.Horizontal.TProgressbar",
        )
        self.progress.pack(fill="x")
        self.progress.start(10)

    @staticmethod
    def _text_logo(parent: tk.Widget) -> None:
        tk.Label(
            parent,
            text="RISKO",
            bg=PALETTE["surface"],
            fg=PALETTE["primary"],
            font=("Helvetica Neue", 19, "bold"),
        ).pack(padx=20, pady=16)

    def _center_window(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _begin(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()

    def _status(self, status: str, detail: str) -> None:
        self.events.put(("status", (status, detail)))

    def _worker(self) -> None:
        try:
            command, working_dir, environment, version = _resolve_portal_command(
                self._status
            )
            self._status(
                f"Abriendo Portal RISKO {version}",
                "Iniciando la aplicacion desde este Mac.",
            )
            self.process = subprocess.Popen(
                command,
                cwd=str(working_dir),
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + READY_GRACE_SECONDS
            while time.monotonic() < deadline:
                exit_code = self.process.poll()
                if exit_code is not None:
                    raise RuntimeError(
                        f"Portal RISKO termino durante el inicio (codigo {exit_code})."
                    )
                time.sleep(0.2)
            self.events.put(("ready", None))
        except Exception as exc:
            logging.exception("No fue posible iniciar Portal RISKO para macOS.")
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
                    self.status_var.set("Portal RISKO listo")
                    self.detail_var.set("Abriendo el entorno de trabajo.")
                    self.root.attributes("-topmost", False)
                    self.root.after(180, self._close)
                elif event == "error":
                    self._show_error(str(payload))
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(POLL_INTERVAL_MS, self._process_events)

    def _show_error(self, detail: str) -> None:
        self.failed = True
        self.progress.stop()
        self.status_var.set("No fue posible iniciar Portal RISKO")
        self.detail_var.set("Revise el detalle del error.")
        self.root.attributes("-topmost", False)
        messagebox.showerror(
            APP_NAME,
            f"{detail}\n\nRegistro tecnico:\n{LOG_PATH}",
            parent=self.root,
        )
        self._close()

    def _on_escape(self, _event=None) -> None:
        if self.failed:
            self._close()

    def _close(self) -> None:
        try:
            self.root.destroy()
        finally:
            if self.lock_handle is not None:
                self.lock_handle.close()
                self.lock_handle = None


def _self_test() -> int:
    print(f"Launcher: {APP_NAME} macOS")
    print("Plataforma objetivo: macOS ARM64")
    print(f"Arquitectura detectada: {platform.machine()}")
    print(f"Manifiesto: {MANIFEST_NAME}")
    print(f"Cache local: {_local_portal_root()}")
    root = _discover_production_root()
    print(f"Produccion detectada: {root or 'no disponible'}")
    if root is not None:
        manifest = _read_manifest(root / SYSTEM_FOLDER_NAME / MANIFEST_NAME)
        print(f"Version publicada: {manifest.get('version', '')}")
    return 0


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    if sys.platform != "darwin":
        raise SystemExit("Este launcher esta disenado exclusivamente para macOS.")
    if platform.machine().lower() != "arm64":
        raise SystemExit("Instalador RISKO Mac requiere un equipo Apple Silicon ARM64.")

    logging.info("========== Inicio Launcher macOS ARM64 ==========")
    lock_handle, already_running = _acquire_single_instance_lock()
    if already_running:
        hidden = tk.Tk()
        hidden.withdraw()
        messagebox.showinfo(
            APP_NAME,
            "Portal RISKO ya se esta iniciando. Espere a que finalice la carga.",
            parent=hidden,
        )
        hidden.destroy()
        return

    root = tk.Tk()
    LauncherApp(root, lock_handle)
    root.mainloop()


if __name__ == "__main__":
    main()
