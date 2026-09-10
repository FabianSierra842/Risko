"""Compatibilidad del antiguo tablero FX_ESTRAT con el tablero PyG único."""

from __future__ import annotations

from pathlib import Path

from proyectos.pyg.tableros.panel_pyg import build_dashboard


def build_dashboard_fx_strat(datos: dict, ruta_salida: str | Path | None = None) -> Path:
    """Usa el contrato consolidado; las plantillas con importes fijos no son insumos."""
    if "detalle" not in datos:
        raise ValueError("Genere el PyG consolidado con detalle diario antes de construir el tablero.")
    return build_dashboard(datos, ruta_salida)


__all__ = ["build_dashboard_fx_strat"]
