from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


MODULE_PATH = Path(__file__).resolve().parents[1] / "portal" / "macos" / "launcher_macos.py"
TEST_IMPORT_ROOT = Path(tempfile.gettempdir()) / "risko-macos-launcher-tests"
os.environ.setdefault("PORTAL_RISKO_MAC_LOCAL_ROOT", str(TEST_IMPORT_ROOT))
SPEC = importlib.util.spec_from_file_location("risko_launcher_macos", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
mac = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mac)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(version: str = "2.1.8") -> dict:
    return {
        "schema_version": 1,
        "app": "Portal RISKO",
        "platform": "macos",
        "architecture": "arm64",
        "version": version,
        "package": f"Versiones Mac/{version}/Portal-RISKO-macOS-arm64.zip",
        "package_sha256": "0" * 64,
        "bundle": "Portal RISKO.app",
        "executable": "Contents/MacOS/Portal RISKO",
        "executable_sha256": "0" * 64,
        "require_code_signature": False,
        "dashboards_dir": "Dashboards",
        "comments_dir": "Comentarios diarios",
    }


class PortalMacOSLauncherTests(unittest.TestCase):
    def test_discovers_office_smb_layout(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            production = (
                root
                / "Gerencia_Riesgo_De_Tesoreria"
                / "Portal Riesgos de Mercado"
            )
            system_root = production / "Sistema Portal"
            system_root.mkdir(parents=True)
            (system_root / "portal-macos.json").write_text(
                json.dumps(_manifest()), encoding="utf-8"
            )
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PORTAL_RISKO_PRODUCCION", None)
                discovered = mac._discover_production_root(root)

            self.assertEqual(discovered, production.resolve())

    def test_manifest_is_exclusive_to_macos_arm64(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "portal-macos.json"
            intel_manifest = _manifest()
            intel_manifest["architecture"] = "x86_64"
            path.write_text(json.dumps(intel_manifest), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "macOS ARM64"):
                mac._read_manifest(path)

    def test_manifest_paths_cannot_escape_system_portal(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manifest = _manifest()
            manifest["package"] = "../portal.json"
            manifest["__manifest_root"] = str(Path(folder) / "Sistema Portal")

            with self.assertRaisesRegex(RuntimeError, "no es valida"):
                mac._manifest_path(manifest, "package")

    def test_release_is_cached_validated_and_available_offline(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local_root = root / "local"
            production = root / "production"
            system_root = production / "Sistema Portal"
            package_dir = system_root / "Versiones Mac" / "2.1.8"
            source_bundle = root / "source" / "Portal RISKO.app"
            executable = source_bundle / "Contents" / "MacOS" / "Portal RISKO"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"portal-risko-macos-arm64")

            package_dir.mkdir(parents=True)
            package = package_dir / "Portal-RISKO-macOS-arm64.zip"
            with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in source_bundle.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(source_bundle.parent))

            manifest = _manifest()
            manifest.update(
                {
                    "package_sha256": _sha256(package),
                    "executable_sha256": _sha256(executable),
                    "__manifest_root": str(system_root),
                    "__production_root": str(production),
                }
            )
            with mock.patch.dict(
                os.environ,
                {"PORTAL_RISKO_MAC_LOCAL_ROOT": str(local_root)},
            ):
                cached = mac._cache_release(manifest)
                self.assertTrue(cached.is_file())
                self.assertEqual(cached.read_bytes(), executable.read_bytes())
                self.assertIn(local_root, cached.parents)

                package.unlink()
                self.assertEqual(mac._cache_release(manifest), cached)

    def test_application_environment_uses_macos_local_storage(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            local_root = root / "local"
            production = root / "production"
            (production / "Dashboards").mkdir(parents=True)
            manifest = _manifest()
            manifest["__production_root"] = str(production)
            with mock.patch.dict(
                os.environ,
                {"PORTAL_RISKO_MAC_LOCAL_ROOT": str(local_root)},
            ):
                environment = mac._application_environment(manifest)

            self.assertEqual(environment["PORTAL_RISKO_PLATFORM"], "macos-arm64")
            self.assertEqual(
                Path(environment["PORTAL_RISKO_PUBLICADOS"]),
                production / "Dashboards",
            )
            self.assertEqual(
                Path(environment["PORTAL_RISKO_COMENTARIOS"]),
                production / "Comentarios diarios",
            )
            self.assertEqual(
                Path(environment["PORTAL_RISKO_APLICACIONES"]),
                local_root / "Aplicaciones",
            )
            self.assertEqual(
                Path(environment["PORTAL_RISKO_CONFIG_DIR"]),
                local_root / "Configuraciones",
            )

    def test_build_script_uses_separate_mac_artifacts(self) -> None:
        script = (
            MODULE_PATH.parent / "construir_instalador_risko_mac.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('INSTALLER_NAME="Instalador RISKO Mac.pkg"', script)
        self.assertIn("portal-macos.json", script)
        self.assertNotIn("publicar_portal.ps1", script)
        self.assertNotIn("Instalar Portal RISKO.exe", script)


if __name__ == "__main__":
    unittest.main()
