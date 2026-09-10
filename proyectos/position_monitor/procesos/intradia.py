"""Posición preliminar intradía sin alterar el cierre oficial.

El flujo consume únicamente vistas Banking. Forward, Novados, Swaps y Spot
se calculan con los mismos transformadores del cierre; Opciones queda marcada
como pendiente hasta disponer de su reporte intradía compatible.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

import pandas as pd

from compartido.nucleo_risko.rutas import (
    ARCHIVO_BASE_DATOS_POSITION_MONITOR,
    ARCHIVO_BASE_DATOS_RISKO_INTRADIA,
    CARPETA_INSUMOS_INTRADIA_POSITION_MONITOR,
    CARPETA_PROCESADOS_INTRADIA_POSITION_MONITOR,
)
from compartido.nucleo_risko.trm import (
    COLUMNA_SPOT_REPROCESO,
    obtener_spot_reproceso,
)
from proyectos.position_monitor.procesos.forward import (
    _depurar_forward_posicion,
    _leer_insumo_forward,
)
from proyectos.position_monitor.procesos.novados import _depurar_novados
from proyectos.position_monitor.procesos.opciones import (
    MercadoOpciones,
    _calcular_detalle_opciones,
    _construir_curva_desde_xlsb,
    _construir_superficie_volatilidad,
    _construir_tabla_posicion,
    _leer_reporte_opciones,
)
from proyectos.position_monitor.procesos.spot import ejecutar_spot
from proyectos.position_monitor.procesos.swaps import (
    _agrupar_posicion_por_book,
    _calcular_posicion_usd,
    _construir_tabla_canonica,
    _depurar_insumo_swaps,
    _leer_banking_swaps,
    _validar_fecha_valoracion_archivo,
)


PRODUCTOS_INTRADIA = ("Forward", "Novados", "Opciones", "Swap", "Spot")
PRODUCTOS_PENDIENTES: tuple[str, ...] = ()
_COLUMNAS_CANONICAS = (
    "FECHA",
    "PRODUCTO",
    "BOOK",
    "POSICION",
    "MONEDA_POSICION",
    "LB_LT",
    "INSTRUMENTO",
    "COMPANY",
    "CLASIFICACION_CONTABLE",
    "BANKING_CVA_DVA",
)
_PATRON_SUFIJO = re.compile(r"_(\d+)(?=\.[^.]+$)")


@dataclass(frozen=True)
class ResultadoPosicionIntradia:
    fecha: str
    estado: str
    vista_contable: str
    posicion: pd.DataFrame
    totales_producto: dict[str, float]
    total_usd: float
    promedio_setfx: float
    fuentes: dict[str, dict[str, str | int | None]]
    calidad: list[dict[str, str]]
    productos_pendientes: list[str]
    rutas: dict[str, str]

    def metadata(self) -> dict:
        datos = asdict(self)
        datos.pop("posicion", None)
        return datos


def _fecha(valor: str | date | datetime | pd.Timestamp) -> pd.Timestamp:
    if isinstance(valor, (date, datetime, pd.Timestamp)):
        marca = pd.Timestamp(valor)
    else:
        texto = str(valor).strip()
        marca = (
            pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
            if len(texto) == 10 and texto[4:5] == "-" and texto[7:8] == "-"
            else pd.to_datetime(texto, dayfirst=True, errors="coerce")
        )
    if pd.isna(marca):
        raise ValueError(f"Fecha intradía inválida: {valor}")
    return marca.normalize()


def _sufijo_numerico(ruta: Path) -> int:
    coincidencia = _PATRON_SUFIJO.search(ruta.name)
    return int(coincidencia.group(1)) if coincidencia else -1


def seleccionar_archivo_intradia(
    carpeta: str | Path,
    patron: str,
    *,
    tamano_minimo_bytes: int = 1,
) -> Path:
    """Escoge el sufijo mayor entre archivos completos; mtime desempata."""
    raiz = Path(carpeta)
    coincidencias = [ruta for ruta in raiz.glob(patron) if ruta.is_file()]
    candidatos = [
        ruta
        for ruta in coincidencias
        if ruta.stat().st_size >= tamano_minimo_bytes
    ]
    if not candidatos:
        detalle = (
            f"; {len(coincidencias)} coincidencia(s) incompleta(s)"
            if coincidencias
            else ""
        )
        raise FileNotFoundError(
            f"No hay insumo intradia util para el patron {raiz / patron}{detalle}"
        )
    return max(
        candidatos,
        key=lambda ruta: (_sufijo_numerico(ruta), ruta.stat().st_mtime, ruta.name.lower()),
    )


def resolver_insumos_intradia(
    fecha_corte: str | date,
    carpeta: str | Path = CARPETA_INSUMOS_INTRADIA_POSITION_MONITOR,
) -> dict[str, Path]:
    fecha = _fecha(fecha_corte)
    patrones = {
        "forward": f"USR_Posicion_Fwd_Intradia_{fecha:%d%m%Y}_*.xls",
        "novados": f"USR_Posicion_Novado_Intradia_{fecha:%d%m%y}_*.xls",
        "swaps_operaciones": f"USR_Posicion_Swaps_Intraday_{fecha:%d%m%y}_*.xls",
        "swaps_flujos": f"USR_Posicion_Swaps_Intraday_Flujos_{fecha:%d%m%y}_*.xls",
        "spot": f"USR_Caja_Intradia_{fecha:%d%m%y}_*.xls",
        "opciones": f"USR_OPT_INTRADIA_{fecha:%d%m%y}_*.xls",
        "entrada2": "ENTRADA2.xlsb",
        "insumo_tasas": "Insumo tasas.xlsx",
    }
    return {
        nombre: seleccionar_archivo_intradia(carpeta, patron)
        for nombre, patron in patrones.items()
    }


def _sha256(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _normalizar_canonica(tabla: pd.DataFrame, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    faltantes = [columna for columna in _COLUMNAS_CANONICAS if columna not in tabla.columns]
    if faltantes:
        raise ValueError(f"Salida intradía sin columnas canónicas: {', '.join(faltantes)}")
    salida = tabla.loc[:, _COLUMNAS_CANONICAS].copy()
    salida["POSICION"] = pd.to_numeric(
        salida["POSICION"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0.0)
    salida["FECHA"] = fecha_corte.strftime("%d/%m/%Y")
    salida["BANKING_CVA_DVA"] = "Banking"
    return salida.reset_index(drop=True)


def _calcular_forward(ruta: Path, fecha_corte: pd.Timestamp) -> pd.DataFrame:
    insumo = _leer_insumo_forward(ruta)
    _, tabla = _depurar_forward_posicion(
        insumo,
        fecha_corte.strftime("%d-%m-%Y"),
        "Banking",
    )
    return _normalizar_canonica(tabla, fecha_corte)


def _aplicar_nominal_operaciones_dia_novados(
    insumo: pd.DataFrame,
    fecha_corte: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Usa el nominal firmado en operaciones negociadas el dia del intradia."""
    ajustado = insumo.copy()
    ajustado.columns = ajustado.columns.str.strip()
    requeridas = {"FECHA NEGOCIACION", "NOMINAL", "VALOR SENSIBLE"}
    faltantes = sorted(requeridas.difference(ajustado.columns))
    if faltantes:
        raise ValueError(
            "Novados intradia no contiene las columnas requeridas para la regla "
            f"de operaciones del dia: {', '.join(faltantes)}"
        )

    fecha_texto = ajustado["FECHA NEGOCIACION"].astype(str).str.strip()
    fechas_negociacion = pd.to_datetime(
        fecha_texto,
        format="%d/%m/%y",
        errors="coerce",
    )
    formato_largo = fechas_negociacion.isna()
    fechas_negociacion.loc[formato_largo] = pd.to_datetime(
        fecha_texto.loc[formato_largo],
        format="%d/%m/%Y",
        errors="coerce",
    )
    operaciones_dia = fechas_negociacion.dt.normalize().eq(fecha_corte.normalize())

    nominal = pd.to_numeric(
        ajustado["NOMINAL"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    nominal_invalido = operaciones_dia & nominal.isna()
    if nominal_invalido.any():
        raise ValueError(
            "Novados intradia tiene "
            f"{int(nominal_invalido.sum())} operacion(es) del dia sin NOMINAL valido."
        )

    sensible_original = pd.to_numeric(
        ajustado["VALOR SENSIBLE"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0.0)
    ajustado["VALOR SENSIBLE"] = ajustado["VALOR SENSIBLE"].astype(object)
    ajustado.loc[operaciones_dia, "VALOR SENSIBLE"] = nominal.loc[operaciones_dia]

    return ajustado, {
        "filas_regla": int(operaciones_dia.sum()),
        "nominal_total": float(nominal.loc[operaciones_dia].sum()),
        "sensible_original_total": float(sensible_original.loc[operaciones_dia].sum()),
        "impacto_usd": float(
            (nominal.loc[operaciones_dia] - sensible_original.loc[operaciones_dia]).sum()
        ),
    }


def _calcular_novados(
    ruta: Path,
    fecha_corte: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, str]]:
    insumo = pd.read_csv(ruta, sep=";", skiprows=2, encoding="latin1", engine="python")
    insumo.columns = insumo.columns.str.strip()
    sensible = pd.to_numeric(
        insumo.get("VALOR SENSIBLE", pd.Series(dtype=float))
        .astype(str)
        .str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0.0)
    if sensible.empty:
        raise ValueError(f"Novados no contiene la columna VALOR SENSIBLE: {ruta}")
    no_cero = int(sensible.ne(0.0).sum())
    insumo, regla = _aplicar_nominal_operaciones_dia_novados(insumo, fecha_corte)
    calidad = {
        "producto": "Novados",
        "estado": "OK",
        "detalle": (
            f"VALOR SENSIBLE informado por Summit: {len(sensible)} filas, "
            f"{no_cero} no cero. Regla intradia: {regla['filas_regla']} operacion(es) "
            "con FECHA NEGOCIACION igual al corte usan NOMINAL firmado; impacto "
            f"USD {regla['impacto_usd']:,.2f}."
        ),
    }
    _, tabla = _depurar_novados(insumo, fecha_corte.strftime("%d-%m-%Y"))
    return _normalizar_canonica(tabla, fecha_corte), calidad


def _validar_fecha_reporte_opciones(ruta: Path, fecha_corte: pd.Timestamp) -> None:
    with ruta.open("r", encoding="latin1", errors="replace") as archivo:
        lineas = [archivo.readline().strip() for _ in range(4)]
    linea_fecha = next(
        (linea for linea in lineas if linea.upper().startswith("FECHA DEL REPORTE;")),
        "",
    )
    if not linea_fecha:
        raise ValueError(f"Opciones intradia no informa FECHA DEL REPORTE: {ruta}")
    valor = linea_fecha.split(";", 1)[1].strip()
    fecha_reporte = pd.to_datetime(valor, format="%d%m%Y", errors="coerce")
    if pd.isna(fecha_reporte) or fecha_reporte.normalize() != fecha_corte:
        raise ValueError(
            "La fecha del reporte de Opciones intradia no coincide con el corte: "
            f"{valor} != {fecha_corte.strftime('%d%m%Y')}. Archivo: {ruta}"
        )


def _calcular_opciones(
    ruta_opciones: Path,
    ruta_entrada2: Path,
    ruta_insumo_tasas: Path,
    fecha_corte: pd.Timestamp,
    logger=None,
) -> tuple[pd.DataFrame, dict[str, str], float]:
    _validar_fecha_reporte_opciones(ruta_opciones, fecha_corte)
    detalle = _leer_reporte_opciones(ruta_opciones)
    spot = obtener_spot_reproceso(
        fecha_corte,
        ruta_insumo_tasas,
        logger=logger,
        columna_valor=COLUMNA_SPOT_REPROCESO,
    )
    mercado = MercadoOpciones(
        trm=spot,
        curva_usd=_construir_curva_desde_xlsb(ruta_entrada2, "A:C", 18, "TASA_USD"),
        curva_cop=_construir_curva_desde_xlsb(ruta_entrada2, "E:G", 13, "TASA_COP"),
        superficie_vol=_construir_superficie_volatilidad(ruta_entrada2),
    )
    detalle_calculado = _calcular_detalle_opciones(detalle, fecha_corte, mercado)
    tabla = _construir_tabla_posicion(detalle_calculado, fecha_corte, logger=logger)
    calidad = {
        "producto": "Opciones",
        "estado": "OK",
        "detalle": (
            f"{len(detalle_calculado)} operaciones revaloradas con "
            f"{COLUMNA_SPOT_REPROCESO}={spot:,.6f}; sin IFRS/CVA-DVA."
        ),
    }
    return _normalizar_canonica(tabla, fecha_corte), calidad, spot


def _validar_operaciones_swaps(ruta: Path) -> None:
    with ruta.open("r", encoding="latin1", errors="replace") as archivo:
        cabecera = next((linea for linea in archivo if linea.startswith("FILA;")), "")
    requeridas = ("BOOK", "SALDO_PAY_NTL", "SALDO_REC_NTL")
    if not cabecera or any(columna not in cabecera for columna in requeridas):
        raise ValueError(f"El reporte de operaciones Swaps no tiene la estructura esperada: {ruta}")


def _calcular_swaps(
    ruta_flujos: Path,
    ruta_operaciones: Path,
    fecha_corte: pd.Timestamp,
) -> pd.DataFrame:
    _validar_operaciones_swaps(ruta_operaciones)
    insumo, fecha_archivo = _leer_banking_swaps(ruta_flujos)
    _validar_fecha_valoracion_archivo(
        fecha_archivo,
        fecha_corte,
        "Banking intradía",
    )
    depurado = _depurar_insumo_swaps(insumo, fecha_archivo)
    depurado = _calcular_posicion_usd(depurado, fecha_corte)
    posicion = _agrupar_posicion_por_book(depurado)
    tabla = _construir_tabla_canonica(posicion, fecha_corte, "Banking")
    return _normalizar_canonica(tabla, fecha_corte)


def _clonar_base_spot(ruta_origen: Path, ruta_destino: Path) -> Path:
    if not ruta_origen.is_file():
        raise FileNotFoundError(f"No existe la base oficial para anclar Spot: {ruta_origen}")
    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta_destino.with_name(f".{ruta_destino.name}.{uuid.uuid4().hex}.tmp")
    try:
        with closing(sqlite3.connect(str(ruta_origen))) as origen, closing(
            sqlite3.connect(str(temporal))
        ) as destino:
            origen.backup(destino)
        os.replace(temporal, ruta_destino)
    finally:
        if temporal.exists():
            temporal.unlink()
    return ruta_destino


def _calcular_spot(
    ruta: Path,
    fecha_corte: pd.Timestamp,
    ruta_db_base: Path,
    ruta_db_intradia: Path,
) -> pd.DataFrame:
    _clonar_base_spot(ruta_db_base, ruta_db_intradia)
    tabla = ejecutar_spot(
        fecha_corte.strftime("%d-%m-%Y"),
        ruta_db=ruta_db_intradia,
        ruta_insumo=ruta,
    )
    return _normalizar_canonica(tabla, fecha_corte)


def _manifestar_fuentes(insumos: dict[str, Path]) -> dict[str, dict[str, str | int | None]]:
    return {
        nombre: {
            "archivo": ruta.name,
            "ruta": str(ruta),
            "sufijo": (_sufijo_numerico(ruta) if _sufijo_numerico(ruta) >= 0 else None),
            "tamano_bytes": ruta.stat().st_size,
            "sha256": _sha256(ruta),
        }
        for nombre, ruta in insumos.items()
    }


def calcular_position_monitor_intradia(
    fecha_corte: str | date,
    *,
    carpeta_insumos: str | Path = CARPETA_INSUMOS_INTRADIA_POSITION_MONITOR,
    ruta_db_base: str | Path = ARCHIVO_BASE_DATOS_POSITION_MONITOR,
    ruta_db_intradia: str | Path = ARCHIVO_BASE_DATOS_RISKO_INTRADIA,
    carpeta_salida: str | Path = CARPETA_PROCESADOS_INTRADIA_POSITION_MONITOR,
    logger=None,
) -> ResultadoPosicionIntradia:
    fecha = _fecha(fecha_corte)
    insumos = resolver_insumos_intradia(fecha, carpeta=carpeta_insumos)
    if logger:
        for nombre, ruta in insumos.items():
            sufijo = _sufijo_numerico(ruta)
            version = f"version {sufijo:03d}" if sufijo >= 0 else "archivo fijo"
            logger(f"Intradia {nombre}: {ruta.name} ({version}).")

    forward = _calcular_forward(insumos["forward"], fecha)
    novados, calidad_novados = _calcular_novados(insumos["novados"], fecha)
    opciones, calidad_opciones, promedio_setfx = _calcular_opciones(
        insumos["opciones"],
        insumos["entrada2"],
        insumos["insumo_tasas"],
        fecha,
        logger=logger,
    )
    swaps = _calcular_swaps(
        insumos["swaps_flujos"],
        insumos["swaps_operaciones"],
        fecha,
    )
    spot = _calcular_spot(
        insumos["spot"],
        fecha,
        Path(ruta_db_base),
        Path(ruta_db_intradia),
    )
    posicion = pd.concat([forward, novados, opciones, swaps, spot], ignore_index=True)
    posicion = _normalizar_canonica(posicion, fecha)
    vistas = set(posicion["BANKING_CVA_DVA"].astype(str).str.upper())
    if vistas != {"BANKING"}:
        raise ValueError(f"El preliminar intradía contiene vistas no permitidas: {sorted(vistas)}")

    totales = {
        str(producto): float(valor)
        for producto, valor in posicion.groupby("PRODUCTO")["POSICION"].sum().items()
    }
    salida = Path(carpeta_salida)
    salida.mkdir(parents=True, exist_ok=True)
    csv = salida / f"posicion_intradia_{fecha:%Y%m%d}.csv"
    metadata = salida / f"posicion_intradia_{fecha:%Y%m%d}.json"
    posicion.to_csv(csv, index=False, encoding="utf-8-sig")

    resultado = ResultadoPosicionIntradia(
        fecha=fecha.date().isoformat(),
        estado="PRELIMINAR_INTRADIA",
        vista_contable="Banking",
        posicion=posicion,
        totales_producto=totales,
        total_usd=float(posicion["POSICION"].sum()),
        promedio_setfx=promedio_setfx,
        fuentes=_manifestar_fuentes(insumos),
        calidad=[
            {"producto": "Forward", "estado": "OK", "detalle": "Estructura 107 columnas compatible."},
            calidad_novados,
            calidad_opciones,
            {"producto": "Swap", "estado": "OK", "detalle": "Cálculo realizado con el reporte intradía de flujos."},
            {"producto": "Spot", "estado": "OK", "detalle": "Caja acumulada sobre un clon del cierre oficial anterior."},
        ],
        productos_pendientes=list(PRODUCTOS_PENDIENTES),
        rutas={"csv": str(csv), "metadata": str(metadata), "db_spot": str(ruta_db_intradia)},
    )
    metadata.write_text(
        json.dumps(resultado.metadata(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if logger:
        logger(
            f"Posición preliminar intradía calculada: {len(posicion)} filas, "
            f"USD {resultado.total_usd:,.2f}."
        )
    return resultado


__all__ = [
    "PRODUCTOS_INTRADIA",
    "PRODUCTOS_PENDIENTES",
    "ResultadoPosicionIntradia",
    "calcular_position_monitor_intradia",
    "resolver_insumos_intradia",
    "seleccionar_archivo_intradia",
]
