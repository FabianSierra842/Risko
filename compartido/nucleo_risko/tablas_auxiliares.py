"""Persistencia transversal de tablas de soporte en una base SQLite separada.

Esta capa es deliberadamente aditiva: no reemplaza los Excel, CSV ni escrituras
oficiales de los modulos. Un fallo aqui se registra y no interrumpe el calculo
que origino los DataFrames.
"""

from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from compartido.nucleo_risko.archivos import registrar_log
from compartido.nucleo_risko.base_datos import (
    actualizar_dataframe_por_fecha_sqlite,
    conectar_sqlite,
    crear_indice_sqlite,
    normalizar_identificador_sql,
)
from compartido.nucleo_risko.rutas import ARCHIVO_BASE_DATOS_RISKO_AUXILIAR


TABLA_CATALOGO_AUXILIAR = "tbl_catalogo_auxiliar"
COLUMNA_CORTE_AUXILIAR = "AUX_FECHA_CORTE"
COLUMNA_MODULO_AUXILIAR = "AUX_MODULO"
COLUMNA_CARGA_AUXILIAR = "AUX_CARGADO_EN"

# Inventario único de las copias agregadas en los procesos. El catálogo permite
# ver desde el primer día qué tablas aún están pendientes de una ejecución real.
INVENTARIO_TABLAS_AUXILIARES = {
    "Forward": (
        "insumo_banking_depurado",
        "insumo_ifrs_depurado",
        "posicion_banking",
        "posicion_ifrs",
        "posicion_cva_dva",
        "posicion_consolidada",
    ),
    "Novados": ("insumo_depurado", "posicion"),
    "Opciones": (
        "detalle_calculado",
        "posicion_por_book",
        "control",
        "curva_usd",
        "curva_cop",
        "superficie_volatilidad",
        "posicion",
    ),
    "Renta_Fija": (
        "reporte_enriquecido",
        "posicion_operativa",
        "posicion_por_libro",
        "posicion_por_agencia",
        "posicion_por_estructura",
        "posicion_por_moneda",
        "posicion_canonica",
    ),
    "Swaps": (
        "banking_depurado",
        "ifrs_depurado",
        "posicion_banking",
        "posicion_ifrs",
        "posicion_cva_dva",
        "posicion_detalle",
        "posicion_publicada",
    ),
    "Spot": (
        "posicion_canonica",
        "posicion_acumulada",
        "parametros_book",
        "compras_ventas_por_book",
        "movimientos",
        "alertas",
        "ejecuciones",
        "auditoria",
    ),
    "Cubrebonos": ("posicion_pendiente",),
    "NDFTES": ("posicion_pendiente",),
    "PP": ("posicion_pendiente",),
}


def _fecha_texto(fecha_corte) -> str:
    fecha = pd.to_datetime(fecha_corte, dayfirst=True, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha no valida para base auxiliar: {fecha_corte}")
    return fecha.strftime("%d/%m/%Y")


def _nombre_tabla(modulo: str, nombre_logico: str) -> str:
    modulo_sql = normalizar_identificador_sql(modulo).lower()
    nombre_sql = normalizar_identificador_sql(nombre_logico).lower()
    return normalizar_identificador_sql(f"aux_{modulo_sql}_{nombre_sql}")


def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Prepara una copia compatible con SQLite sin tocar el DataFrame fuente."""
    resultado = df.copy()
    columnas: list[str] = []
    usados: set[str] = set()
    for posicion, columna in enumerate(resultado.columns, start=1):
        try:
            base = normalizar_identificador_sql(str(columna))
        except ValueError:
            base = f"COLUMNA_{posicion}"
        candidato = base
        sufijo = 2
        while candidato.upper() in usados:
            candidato = f"{base}_{sufijo}"
            sufijo += 1
        usados.add(candidato.upper())
        columnas.append(candidato)
    resultado.columns = columnas

    def normalizar_valor(valor):
        if valor is None:
            return None
        if isinstance(valor, pd.Timestamp):
            return None if pd.isna(valor) else valor.isoformat()
        if isinstance(valor, (datetime, date)):
            return valor.isoformat()
        if isinstance(valor, Decimal):
            return format(valor, "f")
        if isinstance(valor, (dict, list, tuple, set)):
            return json.dumps(valor, ensure_ascii=False, default=str, sort_keys=True)
        try:
            if pd.isna(valor):
                return None
        except (TypeError, ValueError):
            pass
        return valor

    for columna in resultado.columns:
        if pd.api.types.is_datetime64_any_dtype(resultado[columna]):
            resultado[columna] = resultado[columna].map(normalizar_valor)
        elif pd.api.types.is_timedelta64_dtype(resultado[columna]):
            resultado[columna] = resultado[columna].astype(str)
        elif resultado[columna].dtype == "object":
            resultado[columna] = resultado[columna].map(normalizar_valor)
    return resultado


def _asegurar_catalogo(ruta_db: Path) -> None:
    with closing(conectar_sqlite(ruta_db)) as conexion:
        conexion.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLA_CATALOGO_AUXILIAR} (
                MODULO TEXT NOT NULL,
                NOMBRE_LOGICO TEXT NOT NULL,
                TABLA_FISICA TEXT NOT NULL,
                FECHA_ULTIMA_CARGA TEXT,
                FILAS_ULTIMA_CARGA INTEGER NOT NULL DEFAULT 0,
                COLUMNAS TEXT NOT NULL DEFAULT '',
                ESTADO TEXT NOT NULL,
                MENSAJE TEXT NOT NULL DEFAULT '',
                ACTUALIZADO_EN TEXT NOT NULL,
                PRIMARY KEY (MODULO, NOMBRE_LOGICO)
            )
            """
        )
        conexion.commit()


def _actualizar_catalogo(
    ruta_db: Path,
    *,
    modulo: str,
    nombre_logico: str,
    tabla_fisica: str,
    fecha_corte: str,
    filas: int,
    columnas: list[str],
    estado: str,
    mensaje: str = "",
) -> None:
    _asegurar_catalogo(ruta_db)
    actualizado = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(conectar_sqlite(ruta_db)) as conexion:
        conexion.execute(
            f"""
            INSERT INTO {TABLA_CATALOGO_AUXILIAR} (
                MODULO, NOMBRE_LOGICO, TABLA_FISICA, FECHA_ULTIMA_CARGA,
                FILAS_ULTIMA_CARGA, COLUMNAS, ESTADO, MENSAJE, ACTUALIZADO_EN
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(MODULO, NOMBRE_LOGICO) DO UPDATE SET
                TABLA_FISICA = excluded.TABLA_FISICA,
                FECHA_ULTIMA_CARGA = excluded.FECHA_ULTIMA_CARGA,
                FILAS_ULTIMA_CARGA = excluded.FILAS_ULTIMA_CARGA,
                COLUMNAS = excluded.COLUMNAS,
                ESTADO = excluded.ESTADO,
                MENSAJE = excluded.MENSAJE,
                ACTUALIZADO_EN = excluded.ACTUALIZADO_EN
            """,
            (
                modulo,
                nombre_logico,
                tabla_fisica,
                fecha_corte,
                filas,
                json.dumps(columnas, ensure_ascii=False),
                estado,
                mensaje,
                actualizado,
            ),
        )
        conexion.commit()


def _registrar_inventario(ruta_db: Path) -> None:
    actualizado = datetime.now().astimezone().isoformat(timespec="seconds")
    filas = [
        (
            modulo,
            nombre_logico,
            _nombre_tabla(modulo, nombre_logico),
            None,
            0,
            "[]",
            "PENDIENTE_EJECUCION",
            "La tabla física se creará en la próxima ejecución exitosa del módulo.",
            actualizado,
        )
        for modulo, nombres in INVENTARIO_TABLAS_AUXILIARES.items()
        for nombre_logico in nombres
    ]
    with closing(conectar_sqlite(ruta_db)) as conexion:
        conexion.executemany(
            f"""
            INSERT OR IGNORE INTO {TABLA_CATALOGO_AUXILIAR} (
                MODULO, NOMBRE_LOGICO, TABLA_FISICA, FECHA_ULTIMA_CARGA,
                FILAS_ULTIMA_CARGA, COLUMNAS, ESTADO, MENSAJE, ACTUALIZADO_EN
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            filas,
        )
        conexion.commit()


def inicializar_base_auxiliar(ruta_db: str | Path | None = None) -> Path:
    """Crea la base auxiliar y su catálogo sin modificar las bases oficiales."""
    ruta = Path(ruta_db) if ruta_db is not None else ARCHIVO_BASE_DATOS_RISKO_AUXILIAR
    _asegurar_catalogo(ruta)
    _registrar_inventario(ruta)
    return ruta


def guardar_tablas_auxiliares_modulo(
    modulo: str,
    fecha_corte,
    tablas: Mapping[str, object],
    *,
    ruta_db: str | Path | None = None,
    logger=None,
) -> dict[str, str]:
    """Copia varios DataFrames de un módulo a ``risko_auxiliar.db``.

    Cada tabla es una foto por corte. Reprocesar una fecha reemplaza solamente
    esa foto y conserva los demás cortes. Las excepciones quedan aisladas para
    que esta copia de soporte nunca cambie el resultado del proceso principal.
    """
    ruta = Path(ruta_db) if ruta_db is not None else ARCHIVO_BASE_DATOS_RISKO_AUXILIAR
    guardadas: dict[str, str] = {}

    try:
        fecha_texto = _fecha_texto(fecha_corte)
        inicializar_base_auxiliar(ruta)
    except Exception as exc:
        registrar_log(
            logger,
            f"ADVERTENCIA base auxiliar [{modulo}]: no se pudo inicializar {ruta}: {exc}",
        )
        return guardadas

    for nombre_logico, datos in tablas.items():
        tabla_fisica = _nombre_tabla(modulo, nombre_logico)
        try:
            df = datos.copy() if isinstance(datos, pd.DataFrame) else pd.DataFrame(datos)
            df = _normalizar_columnas(df)
            instante = datetime.now().astimezone().isoformat(timespec="seconds")
            df.insert(0, COLUMNA_CARGA_AUXILIAR, instante)
            df.insert(0, COLUMNA_MODULO_AUXILIAR, str(modulo).strip())
            df.insert(0, COLUMNA_CORTE_AUXILIAR, fecha_texto)

            actualizar_dataframe_por_fecha_sqlite(
                df,
                ruta,
                tabla_fisica,
                fecha_texto,
                columna_fecha=COLUMNA_CORTE_AUXILIAR,
            )
            crear_indice_sqlite(
                ruta,
                tabla_fisica,
                [COLUMNA_CORTE_AUXILIAR],
                nombre_indice=f"idx_{tabla_fisica}_corte",
            )
            _actualizar_catalogo(
                ruta,
                modulo=str(modulo).strip(),
                nombre_logico=str(nombre_logico).strip(),
                tabla_fisica=tabla_fisica,
                fecha_corte=fecha_texto,
                filas=len(df),
                columnas=list(df.columns),
                estado="OK",
            )
            guardadas[str(nombre_logico)] = tabla_fisica
            registrar_log(
                logger,
                f"Tabla auxiliar actualizada: {tabla_fisica} ({len(df):,} filas) en {ruta}.",
            )
        except Exception as exc:
            try:
                _actualizar_catalogo(
                    ruta,
                    modulo=str(modulo).strip(),
                    nombre_logico=str(nombre_logico).strip(),
                    tabla_fisica=tabla_fisica,
                    fecha_corte=fecha_texto,
                    filas=0,
                    columnas=[],
                    estado="ERROR",
                    mensaje=str(exc),
                )
            except Exception:
                pass
            registrar_log(
                logger,
                f"ADVERTENCIA tabla auxiliar [{modulo}/{nombre_logico}]: {exc}. "
                "El proceso principal conserva sus salidas actuales.",
            )
    return guardadas
