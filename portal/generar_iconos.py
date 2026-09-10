"""Genera los iconos Windows de Portal RISKO desde el logo oficial."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg


PORTAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PORTAL_DIR.parent
SOURCE_LOGO = PROJECT_ROOT / "Herramientas" / "dashy" / "LOGO RISKO.svg"
ASSETS_DIR = PORTAL_DIR / "assets"
PREVIEW_PATH = ASSETS_DIR / "portal-risko-256.png"
ICON_PATH = ASSETS_DIR / "portal-risko.ico"

CANVAS_SIZE = 256
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def _risko_symbol() -> Image.Image:
    drawing = svg2rlg(str(SOURCE_LOGO))
    if drawing is None:
        raise RuntimeError(f"No se pudo interpretar el SVG: {SOURCE_LOGO}")
    logo_rgb = renderPM.drawToPIL(drawing, dpi=96).convert("RGB")

    white = Image.new("RGB", logo_rgb.size, "white")
    difference = ImageChops.difference(logo_rgb, white)
    content_bbox = difference.getbbox()
    if not content_bbox:
        raise RuntimeError("El SVG RISKO no contiene pixeles visibles.")

    # El isotipo ocupa el primer 35 % del contenido horizontal del logo; el
    # resto corresponde al texto RISKO, que no es legible como icono pequeño.
    left, top, right, bottom = content_bbox
    symbol_right = left + round((right - left) * 0.35)
    symbol_rgb = logo_rgb.crop((left, top, symbol_right, bottom))

    red, green, blue = symbol_rgb.split()
    alpha = ImageChops.lighter(
        ImageChops.invert(red),
        ImageChops.lighter(ImageChops.invert(green), ImageChops.invert(blue)),
    )
    symbol = symbol_rgb.convert("RGBA")
    symbol.putalpha(alpha)
    bbox = symbol.getbbox()
    return symbol.crop(bbox) if bbox else symbol


def build_icon() -> Image.Image:
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (8, 8, 248, 248),
        radius=52,
        fill=(255, 255, 255, 255),
        outline=(0, 60, 134, 255),
        width=12,
    )

    symbol = _risko_symbol()
    max_side = 172
    scale = min(max_side / symbol.width, max_side / symbol.height)
    size = (
        max(1, round(symbol.width * scale)),
        max(1, round(symbol.height * scale)),
    )
    symbol = symbol.resize(size, Image.Resampling.LANCZOS)
    position = (
        (CANVAS_SIZE - symbol.width) // 2,
        (CANVAS_SIZE - symbol.height) // 2,
    )
    canvas.alpha_composite(symbol, position)
    return canvas


def main() -> None:
    if not SOURCE_LOGO.is_file():
        raise FileNotFoundError(f"No se encontro el logo RISKO: {SOURCE_LOGO}")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    icon = build_icon()
    icon.save(PREVIEW_PATH, format="PNG", optimize=True)
    icon.save(ICON_PATH, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    print(f"Vista previa: {PREVIEW_PATH}")
    print(f"Icono Windows: {ICON_PATH}")


if __name__ == "__main__":
    main()
