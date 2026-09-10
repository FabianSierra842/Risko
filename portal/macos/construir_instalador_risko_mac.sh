#!/bin/bash
# Construye y, opcionalmente, publica Portal RISKO para macOS ARM64.
# Este script no modifica portal.json, releases o instaladores Windows.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORTAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(cd "$PORTAL_DIR/.." && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/dist-macos"
PUBLISH_ROOT=""
VERSION=""
APPLICATION_IDENTITY="${RISKO_APPLE_APPLICATION_IDENTITY:-}"
INSTALLER_IDENTITY="${RISKO_APPLE_INSTALLER_IDENTITY:-}"
NOTARY_PROFILE="${RISKO_APPLE_NOTARY_PROFILE:-}"
INSTALLER_NAME="Instalador RISKO Mac.pkg"
PUBLISH_STAGE=""

usage() {
    echo "Uso: $0 [opciones]"
    echo ""
    echo "  --version VERSION          Version a publicar; por defecto usa APP_VERSION."
    echo "  --output DIR               Carpeta local de salida."
    echo "  --publish-root DIR         Raiz macOS de Portal Riesgos de Mercado."
    echo "  --application-identity ID  Developer ID Application para firmar los .app."
    echo "  --installer-identity ID    Developer ID Installer para firmar el .pkg."
    echo "  --notary-profile PERFIL    Perfil de xcrun notarytool y notarizacion."
    echo "  --help                     Muestra esta ayuda."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="${2:?Falta el valor de --version}"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="${2:?Falta el valor de --output}"
            shift 2
            ;;
        --publish-root)
            PUBLISH_ROOT="${2:?Falta el valor de --publish-root}"
            shift 2
            ;;
        --application-identity)
            APPLICATION_IDENTITY="${2:?Falta el valor de --application-identity}"
            shift 2
            ;;
        --installer-identity)
            INSTALLER_IDENTITY="${2:?Falta el valor de --installer-identity}"
            shift 2
            ;;
        --notary-profile)
            NOTARY_PROFILE="${2:?Falta el valor de --notary-profile}"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Opcion no reconocida: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Este proceso debe ejecutarse en macOS; PyInstaller no compila macOS desde Windows." >&2
    exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
    echo "Instalador RISKO Mac se construye unicamente en Apple Silicon ARM64." >&2
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "Se requiere Python 3.11 o posterior con tkinter." >&2
    exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "Se requiere Python 3.11 o posterior." >&2
    exit 1
fi
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo "El Python disponible no incluye tkinter." >&2
    exit 1
fi
for command_name in ditto codesign productbuild shasum xcrun; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "No se encontro la herramienta macOS requerida: $command_name" >&2
        exit 1
    fi
done
if [[ -n "$NOTARY_PROFILE" && ( -z "$APPLICATION_IDENTITY" || -z "$INSTALLER_IDENTITY" ) ]]; then
    echo "La notarizacion requiere identidades Developer ID Application e Installer." >&2
    exit 1
fi

SOURCE_VERSION="$(python3 - "$PORTAL_DIR/script.py" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r'^APP_VERSION\s*=\s*["\x27]([^"\x27]+)["\x27]', text, re.MULTILINE)
if not match:
    raise SystemExit("No se encontro APP_VERSION en portal/script.py")
print(match.group(1))
PY
)"
if [[ -z "$VERSION" ]]; then
    VERSION="$SOURCE_VERSION"
fi
if [[ ! "$VERSION" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Version no valida: $VERSION" >&2
    exit 1
fi
if [[ "$VERSION" != "$SOURCE_VERSION" ]]; then
    echo "La version solicitada ($VERSION) no coincide con APP_VERSION ($SOURCE_VERSION)." >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/risko_macos_build.XXXXXXXX")"
cleanup() {
    if [[ -n "$PUBLISH_STAGE" && -e "$PUBLISH_STAGE" ]]; then
        case "$PUBLISH_STAGE" in
            */Sistema\ Portal/.macos-*.tmp)
                rm -rf -- "$PUBLISH_STAGE"
                ;;
            *)
                echo "Se omitio limpiar una ruta productiva inesperada: $PUBLISH_STAGE" >&2
                ;;
        esac
    fi
    case "$BUILD_ROOT" in
        "${TMPDIR:-/tmp}"/risko_macos_build.*)
            rm -rf -- "$BUILD_ROOT"
            ;;
        *)
            echo "Se omitio la limpieza de una ruta temporal inesperada: $BUILD_ROOT" >&2
            ;;
    esac
}
trap cleanup EXIT

VENV="$BUILD_ROOT/venv"
python3 -m venv "$VENV"
PYTHON="$VENV/bin/python"
"$PYTHON" -m pip install --disable-pip-version-check --upgrade pip
"$PYTHON" -m pip install --disable-pip-version-check -r "$SCRIPT_DIR/requirements-macos.txt"

LOGO_SMALL="$PROJECT_DIR/Herramientas/dashy/logo-risko-56.png"
LOGO_LARGE="$PROJECT_DIR/Herramientas/dashy/logo-risko.png"
ICON_PNG="$PORTAL_DIR/assets/portal-risko-256.png"
ICON_ICO="$PORTAL_DIR/assets/portal-risko.ico"
ENTITLEMENTS="$SCRIPT_DIR/entitlements.plist"

for required_path in \
    "$PORTAL_DIR/script.py" \
    "$SCRIPT_DIR/app_macos.py" \
    "$SCRIPT_DIR/launcher_macos.py" \
    "$ICON_PNG" \
    "$ENTITLEMENTS"; do
    if [[ ! -f "$required_path" ]]; then
        echo "No se encontro el archivo requerido: $required_path" >&2
        exit 1
    fi
done

common_data=()
for asset in "$LOGO_SMALL" "$LOGO_LARGE" "$ICON_PNG" "$ICON_ICO"; do
    if [[ -f "$asset" ]]; then
        common_data+=(--add-data "$asset:.")
    fi
done

codesign_args=()
if [[ -n "$APPLICATION_IDENTITY" ]]; then
    codesign_args+=(--codesign-identity "$APPLICATION_IDENTITY")
fi

APP_DIST="$BUILD_ROOT/dist-app"
APP_WORK="$BUILD_ROOT/work-app"
APP_SPEC="$BUILD_ROOT/spec-app"
mkdir -p "$APP_DIST" "$APP_WORK" "$APP_SPEC"

"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name "Portal RISKO" \
    --osx-bundle-identifier "co.com.bancodebogota.risko.portal.app" \
    --target-arch arm64 \
    --osx-entitlements-file "$ENTITLEMENTS" \
    --icon "$ICON_PNG" \
    --collect-all holidays \
    --paths "$PORTAL_DIR" \
    --distpath "$APP_DIST" \
    --workpath "$APP_WORK" \
    --specpath "$APP_SPEC" \
    "${common_data[@]}" \
    "${codesign_args[@]}" \
    "$SCRIPT_DIR/app_macos.py"

APPLICATION_APP="$APP_DIST/Portal RISKO.app"
APPLICATION_EXECUTABLE="$APPLICATION_APP/Contents/MacOS/Portal RISKO"
if [[ ! -x "$APPLICATION_EXECUTABLE" ]]; then
    echo "PyInstaller no genero el ejecutable esperado: $APPLICATION_EXECUTABLE" >&2
    exit 1
fi
codesign --verify --deep --strict "$APPLICATION_APP"

if [[ -n "$NOTARY_PROFILE" ]]; then
    APP_NOTARY_ZIP="$BUILD_ROOT/Portal-RISKO-app-notary.zip"
    ditto -c -k --sequesterRsrc --keepParent "$APPLICATION_APP" "$APP_NOTARY_ZIP"
    xcrun notarytool submit "$APP_NOTARY_ZIP" \
        --keychain-profile "$NOTARY_PROFILE" \
        --wait
    xcrun stapler staple "$APPLICATION_APP"
    xcrun stapler validate "$APPLICATION_APP"
fi

RELEASE_OUT="$OUTPUT_DIR/release"
MAC_VERSION_DIR="$RELEASE_OUT/Versiones Mac/$VERSION"
mkdir -p "$MAC_VERSION_DIR"
PACKAGE_NAME="Portal-RISKO-macOS-arm64.zip"
PACKAGE_PATH="$MAC_VERSION_DIR/$PACKAGE_NAME"
ditto -c -k --sequesterRsrc --keepParent "$APPLICATION_APP" "$PACKAGE_PATH"
PACKAGE_SHA256="$(shasum -a 256 "$PACKAGE_PATH" | awk '{print $1}')"
EXECUTABLE_SHA256="$(shasum -a 256 "$APPLICATION_EXECUTABLE" | awk '{print $1}')"

MANIFEST_PATH="$RELEASE_OUT/portal-macos.json"
PUBLISHED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
PUBLISHED_BY="$(id -un)@$(scutil --get ComputerName 2>/dev/null || hostname)"
"$PYTHON" - \
    "$MANIFEST_PATH" \
    "$VERSION" \
    "$PACKAGE_NAME" \
    "$PACKAGE_SHA256" \
    "$EXECUTABLE_SHA256" \
    "$PUBLISHED_AT" \
    "$PUBLISHED_BY" <<'PY'
import json
import sys
from pathlib import Path

(
    target,
    version,
    package_name,
    package_sha256,
    executable_sha256,
    published_at,
    published_by,
) = sys.argv[1:]
payload = {
    "schema_version": 1,
    "app": "Portal RISKO",
    "platform": "macos",
    "architecture": "arm64",
    "version": version,
    "package": f"Versiones Mac/{version}/{package_name}",
    "package_sha256": package_sha256,
    "bundle": "Portal RISKO.app",
    "executable": "Contents/MacOS/Portal RISKO",
    "executable_sha256": executable_sha256,
    "require_code_signature": True,
    "dashboards_dir": "Dashboards",
    "comments_dir": "Comentarios diarios",
    "applications_enabled": False,
    "published_at": published_at,
    "published_by": published_by,
}
Path(target).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

LAUNCHER_DIST="$BUILD_ROOT/dist-launcher"
LAUNCHER_WORK="$BUILD_ROOT/work-launcher"
LAUNCHER_SPEC="$BUILD_ROOT/spec-launcher"
mkdir -p "$LAUNCHER_DIST" "$LAUNCHER_WORK" "$LAUNCHER_SPEC"

"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --name "Portal RISKO" \
    --osx-bundle-identifier "co.com.bancodebogota.risko.portal.launcher" \
    --target-arch arm64 \
    --osx-entitlements-file "$ENTITLEMENTS" \
    --icon "$ICON_PNG" \
    --distpath "$LAUNCHER_DIST" \
    --workpath "$LAUNCHER_WORK" \
    --specpath "$LAUNCHER_SPEC" \
    "${common_data[@]}" \
    "${codesign_args[@]}" \
    "$SCRIPT_DIR/launcher_macos.py"

LAUNCHER_APP="$LAUNCHER_DIST/Portal RISKO.app"
if [[ ! -x "$LAUNCHER_APP/Contents/MacOS/Portal RISKO" ]]; then
    echo "PyInstaller no genero el launcher esperado." >&2
    exit 1
fi
codesign --verify --deep --strict "$LAUNCHER_APP"

INSTALLER_PATH="$OUTPUT_DIR/$INSTALLER_NAME"
UNSIGNED_INSTALLER="$BUILD_ROOT/$INSTALLER_NAME"
if [[ -n "$INSTALLER_IDENTITY" ]]; then
    productbuild \
        --component "$LAUNCHER_APP" /Applications \
        --sign "$INSTALLER_IDENTITY" \
        "$UNSIGNED_INSTALLER"
else
    productbuild \
        --component "$LAUNCHER_APP" /Applications \
        "$UNSIGNED_INSTALLER"
fi
cp -f "$UNSIGNED_INSTALLER" "$INSTALLER_PATH"

if [[ -n "$NOTARY_PROFILE" ]]; then
    xcrun notarytool submit "$INSTALLER_PATH" \
        --keychain-profile "$NOTARY_PROFILE" \
        --wait
    xcrun stapler staple "$INSTALLER_PATH"
    xcrun stapler validate "$INSTALLER_PATH"
fi

INSTALLER_SHA256="$(shasum -a 256 "$INSTALLER_PATH" | awk '{print $1}')"
echo ""
echo "Instalador creado: $INSTALLER_PATH"
echo "SHA-256 instalador: $INSTALLER_SHA256"
echo "Manifiesto Mac: $MANIFEST_PATH"
echo "Release Mac: $PACKAGE_PATH"

if [[ -n "$PUBLISH_ROOT" ]]; then
    PUBLISH_ROOT="$(cd "$PUBLISH_ROOT" && pwd)"
    SYSTEM_ROOT="$PUBLISH_ROOT/Sistema Portal"
    if [[ ! -d "$SYSTEM_ROOT" || ! -f "$SYSTEM_ROOT/portal.json" ]]; then
        echo "La raiz indicada no contiene Sistema Portal/portal.json: $PUBLISH_ROOT" >&2
        exit 1
    fi

    PUBLISHED_VERSION_DIR="$SYSTEM_ROOT/Versiones Mac/$VERSION"
    if [[ -e "$PUBLISHED_VERSION_DIR" ]]; then
        echo "La version Mac $VERSION ya existe y es inmutable: $PUBLISHED_VERSION_DIR" >&2
        exit 1
    fi

    mkdir -p "$SYSTEM_ROOT/Versiones Mac" "$SYSTEM_ROOT/Instalador"
    PUBLISH_STAGE="$SYSTEM_ROOT/.macos-$VERSION-$$.tmp"
    mkdir "$PUBLISH_STAGE"
    cp "$PACKAGE_PATH" "$PUBLISH_STAGE/$PACKAGE_NAME"
    if [[ "$(shasum -a 256 "$PUBLISH_STAGE/$PACKAGE_NAME" | awk '{print $1}')" != "$PACKAGE_SHA256" ]]; then
        echo "El release copiado a produccion no supero SHA-256." >&2
        exit 1
    fi
    mv "$PUBLISH_STAGE" "$PUBLISHED_VERSION_DIR"

    cp -f "$INSTALLER_PATH" "$SYSTEM_ROOT/Instalador/$INSTALLER_NAME"
    MANIFEST_TEMP="$SYSTEM_ROOT/.portal-macos.$$.tmp"
    cp "$MANIFEST_PATH" "$MANIFEST_TEMP"
    mv -f "$MANIFEST_TEMP" "$SYSTEM_ROOT/portal-macos.json"

    echo "Publicado sin modificar Windows:"
    echo "  $SYSTEM_ROOT/Instalador/$INSTALLER_NAME"
    echo "  $SYSTEM_ROOT/portal-macos.json"
    echo "  $PUBLISHED_VERSION_DIR/$PACKAGE_NAME"
fi
