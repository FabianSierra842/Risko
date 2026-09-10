# -*- coding: utf-8 -*-
"""Adaptador de Portal RISKO para macOS.

La aplicacion funcional sigue siendo ``portal/script.py``. Este punto de entrada
solo aporta ubicaciones nativas de Chrome/Edge para abrir dashboards y generar
vistas previas; no cambia el comportamiento de Windows.
"""

from __future__ import annotations

from pathlib import Path
import sys


PORTAL_DIR = Path(__file__).resolve().parent.parent
if str(PORTAL_DIR) not in sys.path:
    sys.path.insert(0, str(PORTAL_DIR))

import script as portal  # noqa: E402


def _macos_browser_candidates() -> list[Path]:
    relative_locations = (
        Path("Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        Path("Chromium.app/Contents/MacOS/Chromium"),
    )
    roots = (Path("/Applications"), Path.home() / "Applications")
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(root / relative for relative in relative_locations)
    return candidates


portal._browser_candidates = _macos_browser_candidates


if __name__ == "__main__":
    portal.main()
