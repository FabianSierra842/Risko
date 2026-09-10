"""Configuración y calendario del flujo PyG, independientes de las posiciones."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
import os
from pathlib import Path

RAIZ_RISKO = Path(__file__).resolve().parents[3]
ARCHIVO_CONFIG = Path(__file__).resolve().parents[1] / "configuracion" / "pyg.json"


def cargar_configuracion(ruta: str | Path | None = None) -> dict:
    archivo = Path(ruta or os.environ.get("RISKO_PYG_CONFIG", "") or ARCHIVO_CONFIG)
    with archivo.open(encoding="utf-8") as stream:
        return normalizar_configuracion(json.load(stream))


def normalizar_configuracion(config: dict) -> dict:
    cfg = deepcopy(config)
    raiz = Path(cfg.get("raiz", RAIZ_RISKO)).resolve()
    for nombre, valor in cfg.setdefault("rutas", {}).items():
        ruta = Path(valor)
        cfg["rutas"][nombre] = str(ruta if ruta.is_absolute() else raiz / ruta)
    for fuente in cfg.get("fuentes", {}).values():
        for clave in ("carpeta_datasets", "archivo"):
            if clave in fuente:
                ruta = Path(fuente[clave])
                fuente[clave] = str(ruta if ruta.is_absolute() else raiz / ruta)
    return cfg


def configuracion(config: dict | None = None) -> dict:
    return normalizar_configuracion(config) if config is not None else cargar_configuracion()


def fecha(valor) -> date:
    import pandas as pd
    if isinstance(valor, date):
        return pd.Timestamp(valor).date()
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return pd.to_datetime(texto, format=formato, errors="raise").date()
        except (ValueError, TypeError):
            pass
    raise ValueError(f"Fecha PyG inválida: {valor}")


def habil(corte: date, config: dict) -> bool:
    calendario = config.get("calculo", {}).get("calendario", "CALENDARIO")
    if calendario == "CALENDARIO":
        return True
    if calendario != "HABIL_CO":
        raise ValueError(f"Calendario PyG no soportado: {calendario}")
    import holidays
    return corte.weekday() < 5 and corte not in holidays.Colombia(years=corte.year)


def fecha_previa(corte: date, config: dict) -> date:
    candidato = corte - timedelta(days=1)
    while not habil(candidato, config):
        candidato -= timedelta(days=1)
    return candidato


def intervalos(corte, periodo: str, config: dict) -> list[tuple[date, date]]:
    corte = fecha(corte)
    periodo = periodo.upper()
    if periodo not in {"DIARIO", "MTD"}:
        raise ValueError("El período PyG debe ser DIARIO o MTD.")
    if not habil(corte, config):
        raise ValueError(f"El corte {corte} no pertenece al calendario configurado.")
    if periodo == "DIARIO":
        return [(fecha_previa(corte, config), corte)]
    inicio = corte.replace(day=1)
    anterior = fecha_previa(inicio, config)
    salida = []
    cursor = inicio
    while cursor <= corte:
        if habil(cursor, config):
            salida.append((anterior, cursor))
            anterior = cursor
        cursor += timedelta(days=1)
    return salida


def libros_configurados(config: dict | None = None) -> list[str]:
    cfg = configuracion(config)
    return [nombre for nombre, item in cfg["libros"].items() if item.get("habilitado")]


def seleccionar_libros(libro: str, config: dict) -> list[str]:
    disponibles = libros_configurados(config)
    nombre = libro.upper().strip()
    if nombre == "TODOS":
        if not disponibles:
            raise ValueError("No hay libros PyG habilitados.")
        return disponibles
    if nombre not in disponibles:
        estado = config.get("libros", {}).get(nombre, {}).get("estado", "NO_CONFIGURADO")
        raise ValueError(f"Book {nombre} no habilitado para cálculo: {estado}.")
    return [nombre]
