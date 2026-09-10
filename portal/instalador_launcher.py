# -*- coding: utf-8 -*-
"""
Instalador autocontenido del Launcher local de Portal RISKO.

El ejecutable distribuible contiene un ZIP con el launcher ``onedir``. En la
primera ejecución lo instala bajo ``%LOCALAPPDATA%``, crea accesos directos
locales y abre el Portal. Las aperturas posteriores no cargan Python por SMB.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable
import uuid
import zipfile


APP_NAME = "Portal RISKO"
INSTALL_TITLE = "Instalando Portal RISKO"
PAYLOAD_NAME = "launcher_payload.zip"
PACKAGE_MANIFEST_NAME = "launcher-package.json"
LOCAL_INSTALL_ENV = "PORTAL_RISKO_INSTALL_DIR"
SHORTCUT_DIR_ENV = "PORTAL_RISKO_SHORTCUT_DIR"
CREATE_NO_WINDOW = 0x08000000
StatusCallback = Callable[[str, str], None]

PALETTE = {
    "primary": "#003C86",
    "accent": "#F7BB26",
    "surface": "#FFFFFF",
    "surface_alt": "#F4F7FB",
    "line": "#D5DFEC",
    "text": "#111C2D",
    "muted": "#506078",
}


def _bundle_dir() -> Path:
    folder = getattr(sys, "_MEIPASS", None)
    return Path(folder).resolve() if folder else Path(__file__).resolve().parent


BUNDLE_DIR = _bundle_dir()


def _local_install_dir() -> Path:
    override = os.environ.get(LOCAL_INSTALL_ENV, "").strip()
    if override:
        return Path(override).resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "PortalRisko" / "Launcher"
    return Path.home() / "PortalRisko" / "Launcher"


def _setup_logging() -> Path:
    log_dir = _local_install_dir().parent / "Installer"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "installer.log"
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        encoding="utf-8",
    )
    return path


LOG_PATH = _setup_logging()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_package() -> dict:
    manifest_path = BUNDLE_DIR / PACKAGE_MANIFEST_NAME
    payload_path = BUNDLE_DIR / PAYLOAD_NAME
    if not manifest_path.is_file() or not payload_path.is_file():
        raise FileNotFoundError(
            "El instalador no contiene todos los componentes del Launcher."
        )

    try:
        package = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer el paquete del Launcher: {exc}") from exc

    if not isinstance(package, dict) or package.get("schema_version") != 1:
        raise RuntimeError("El paquete del Launcher no es compatible.")

    expected_payload_hash = str(package.get("payload_sha256") or "").lower()
    if _sha256(payload_path).lower() != expected_payload_hash:
        raise RuntimeError("El paquete del Launcher no superó la validación SHA-256.")
    return package


def _extract_payload(payload_path: Path, destination: Path) -> None:
    """Extrae únicamente rutas contenidas dentro de la carpeta temporal."""
    destination = destination.resolve()
    with zipfile.ZipFile(payload_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(destination)
            except ValueError as exc:
                raise RuntimeError(
                    "El paquete contiene una ruta de extracción no permitida."
                ) from exc
        archive.extractall(destination)


def _create_shortcuts(target: Path) -> list[Path]:
    """
    Crea accesos directos mediante WScript.Shell.

    PowerShell solo se usa en la instalación inicial. El launcher diario no lo
    necesita. La ruta alternativa permite validar el instalador sin tocar el
    escritorio real.
    """
    override = os.environ.get(SHORTCUT_DIR_ENV, "").strip()
    script = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$target = $env:PORTAL_RISKO_SHORTCUT_TARGET
$override = $env:PORTAL_RISKO_SHORTCUT_DIR
$destinations = @()
if ($override) {
    [IO.Directory]::CreateDirectory($override) | Out-Null
    $destinations += (Join-Path $override 'Portal RISKO.lnk')
}
else {
    $destinations += (Join-Path $shell.SpecialFolders.Item('Desktop') 'Portal RISKO.lnk')
    $destinations += (Join-Path $shell.SpecialFolders.Item('Programs') 'Portal RISKO.lnk')
}
foreach ($shortcutPath in $destinations) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = Split-Path -Parent $target
    $shortcut.IconLocation = "$target,0"
    $shortcut.Description = 'Portal RISKO - Riesgo de Mercado'
    $shortcut.Save()
}
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    environment = os.environ.copy()
    environment["PORTAL_RISKO_SHORTCUT_TARGET"] = str(target)
    if override:
        environment[SHORTCUT_DIR_ENV] = override
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-EncodedCommand",
            encoded,
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
        timeout=45,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"No se pudo crear el acceso directo local. {detail}")

    if override:
        return [Path(override) / "Portal RISKO.lnk"]
    return []


def install_launcher(
    status_callback: StatusCallback | None = None,
    *,
    create_shortcuts: bool = True,
) -> Path:
    def report(status: str, detail: str) -> None:
        if status_callback is not None:
            status_callback(status, detail)

    report("Validando instalador", "Comprobando la integridad del paquete.")
    package = _read_package()
    payload_path = BUNDLE_DIR / PAYLOAD_NAME
    version = str(package.get("launcher_version") or "").strip()
    executable_name = str(package.get("launcher_executable") or "").strip()
    expected_launcher_hash = str(package.get("launcher_sha256") or "").lower()
    if not version or not executable_name or len(expected_launcher_hash) != 64:
        raise RuntimeError("La información del Launcher está incompleta.")

    install_dir = _local_install_dir()
    target_exe = install_dir / executable_name
    marker = install_dir / "install.json"

    if target_exe.is_file() and marker.is_file():
        try:
            installed = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            installed = {}
        if (
            installed.get("launcher_version") == version
            and installed.get("launcher_sha256") == expected_launcher_hash
            and _sha256(target_exe).lower() == expected_launcher_hash
        ):
            report(
                f"Launcher {version} ya instalado",
                "Reparando accesos directos y abriendo Portal RISKO.",
            )
            if create_shortcuts:
                _create_shortcuts(target_exe)
            return target_exe

    report(
        f"Instalando Launcher {version}",
        "Preparando el acceso rápido en este equipo.",
    )
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = install_dir.parent / f".Launcher.{uuid.uuid4().hex}.tmp"
    backup = install_dir.parent / f".Launcher.{uuid.uuid4().hex}.bak"

    try:
        staging.mkdir()
        _extract_payload(payload_path, staging)

        staged_exe = staging / executable_name
        if (
            not staged_exe.is_file()
            or _sha256(staged_exe).lower() != expected_launcher_hash
        ):
            raise RuntimeError("El Launcher extraído no superó la validación SHA-256.")

        if install_dir.exists():
            install_dir.replace(backup)
        staging.replace(install_dir)
        marker.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "launcher_version": version,
                    "launcher_sha256": expected_launcher_hash,
                    "installed_from": str(Path(sys.executable).resolve()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if backup.exists():
            if install_dir.exists():
                shutil.rmtree(install_dir, ignore_errors=True)
            if not install_dir.exists():
                backup.replace(install_dir)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    if create_shortcuts:
        report("Creando acceso local", "Configurando el escritorio del usuario.")
        _create_shortcuts(target_exe)
    logging.info("Launcher %s instalado en %s", version, install_dir)
    return target_exe


class InstallerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.status_var = tk.StringVar(value="Preparando Portal RISKO...")
        self.detail_var = tk.StringVar(value="Esta operación solo toma unos segundos.")
        self._configure()
        self._build()
        self.root.after(80, self._start)
        self.root.after(100, self._process_events)

    def _configure(self) -> None:
        self.root.title(INSTALL_TITLE)
        self.root.geometry("560x245")
        self.root.resizable(False, False)
        self.root.configure(bg=PALETTE["surface"])
        self.root.attributes("-topmost", True)
        icon = BUNDLE_DIR / "portal-risko.ico"
        if icon.is_file():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - 560) // 2)
        y = max(0, (self.root.winfo_screenheight() - 245) // 2 - 25)
        self.root.geometry(f"560x245+{x}+{y}")

    def _build(self) -> None:
        header = tk.Frame(self.root, bg=PALETTE["primary"], height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="RISKO",
            bg=PALETTE["primary"],
            fg=PALETTE["surface"],
            font=("Segoe UI Semibold", 22),
        ).pack(side="left", padx=26)
        tk.Label(
            header,
            text="Instalación local",
            bg=PALETTE["primary"],
            fg="#DCE9F8",
            font=("Segoe UI", 10),
        ).pack(side="right", padx=26)

        body = tk.Frame(self.root, bg=PALETTE["surface"])
        body.pack(fill="both", expand=True, padx=30, pady=24)
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
        ).pack(fill="x", pady=(5, 17))
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "RISKO.Horizontal.TProgressbar",
            troughcolor=PALETTE["surface_alt"],
            background=PALETTE["accent"],
            bordercolor=PALETTE["line"],
            lightcolor=PALETTE["accent"],
            darkcolor=PALETTE["accent"],
        )
        self.progress = ttk.Progressbar(
            body, mode="indeterminate", style="RISKO.Horizontal.TProgressbar"
        )
        self.progress.pack(fill="x")
        self.progress.start(12)

    def _start(self) -> None:
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self) -> None:
        try:
            target = install_launcher(
                lambda status, detail: self.events.put(("status", (status, detail)))
            )
            self.events.put(("ready", target))
        except Exception as exc:
            logging.exception("No fue posible instalar el Launcher.")
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
                    target = Path(str(payload))
                    self.status_var.set("Portal RISKO instalado")
                    self.detail_var.set("Abriendo el acceso local.")
                    self.progress.stop()
                    subprocess.Popen(
                        [str(target)],
                        cwd=str(target.parent),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                    )
                    self.root.after(500, self.root.destroy)
                    return
                elif event == "error":
                    self.progress.stop()
                    self.root.attributes("-topmost", False)
                    messagebox.showerror(
                        APP_NAME,
                        f"{payload}\n\nRegistro técnico:\n{LOG_PATH}",
                        parent=self.root,
                    )
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._process_events)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Este instalador está diseñado para Windows.")

    if "--self-test" in sys.argv:
        package = _read_package()
        lines = [
            f"Launcher: {package.get('launcher_version', '')}",
            f"Payload: {BUNDLE_DIR / PAYLOAD_NAME}",
            "Integridad: OK",
        ]
        if sys.stdout is not None:
            print("\n".join(lines))
        else:
            for line in lines:
                logging.info("SELF-TEST | %s", line)
        return

    if "--install-test" in sys.argv:
        install_launcher(create_shortcuts=True)
        return

    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
