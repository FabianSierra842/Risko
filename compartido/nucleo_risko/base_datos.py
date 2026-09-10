from __future__ import annotations

from contextlib import closing
from pathlib import Path
import re
import sqlite3
from typing import Iterable

import pandas as pd


_PATRON_IDENTIFICADOR = re.compile(r"[^0-9A-Za-z_]+")
_TIPOS_SQLITE_VALIDOS = {"TEXT", "INTEGER", "REAL", "NUMERIC", "BLOB"}


def normalizar_identificador_sql(nombre: str) -> str:
    """Convierte un nombre libre en un identificador simple para SQLite."""
    identificador = _PATRON_IDENTIFICADOR.sub("_", str(nombre).strip())
    identificador = re.sub(r"_+", "_", identificador).strip("_")
    if not identificador:
        raise ValueError("El nombre de tabla o columna no puede quedar vacio.")
    if identificador[0].isdigit():
        identificador = f"t_{identificador}"
    return identificador


def citar_identificador(nombre: str) -> str:
    identificador = normalizar_identificador_sql(nombre)
    return f'"{identificador}"'


def conectar_sqlite(ruta_db: str | Path, timeout: int = 30) -> sqlite3.Connection:
    """Abre la base SQLite y aplica parametros conservadores para red compartida."""
    ruta_db = Path(ruta_db)
    ruta_db.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta_db, timeout=timeout)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute(f"PRAGMA busy_timeout = {int(timeout) * 1000}")
    return conexion


def listar_tablas_sqlite(ruta_db: str | Path) -> list[str]:
    if not Path(ruta_db).exists():
        return []

    with closing(conectar_sqlite(ruta_db)) as conexion:
        filas = conexion.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [fila[0] for fila in filas]


def existe_tabla_sqlite(ruta_db: str | Path, nombre_tabla: str) -> bool:
    nombre_tabla = normalizar_identificador_sql(nombre_tabla)
    if not Path(ruta_db).exists():
        return False

    with closing(conectar_sqlite(ruta_db)) as conexion:
        fila = conexion.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (nombre_tabla,),
        ).fetchone()
    return fila is not None


def columnas_tabla_sqlite(ruta_db: str | Path, nombre_tabla: str) -> list[str]:
    nombre_tabla = normalizar_identificador_sql(nombre_tabla)
    if not existe_tabla_sqlite(ruta_db, nombre_tabla):
        return []

    with closing(conectar_sqlite(ruta_db)) as conexion:
        filas = conexion.execute(f"PRAGMA table_info({citar_identificador(nombre_tabla)})").fetchall()
    return [fila[1] for fila in filas]


def crear_indice_sqlite(
    ruta_db: str | Path,
    nombre_tabla: str,
    columnas: Iterable[str],
    nombre_indice: str | None = None,
) -> str:
    nombre_tabla = normalizar_identificador_sql(nombre_tabla)
    columnas = [normalizar_identificador_sql(columna) for columna in columnas]
    if not columnas:
        raise ValueError("Se requiere al menos una columna para crear el indice.")

    if nombre_indice is None:
        nombre_indice = f"idx_{nombre_tabla}_{'_'.join(columnas)}"
    nombre_indice = normalizar_identificador_sql(nombre_indice)

    columnas_sql = ", ".join(citar_identificador(columna) for columna in columnas)
    with closing(conectar_sqlite(ruta_db)) as conexion:
        conexion.execute(
            f"CREATE INDEX IF NOT EXISTS {citar_identificador(nombre_indice)} "
            f"ON {citar_identificador(nombre_tabla)} ({columnas_sql})"
        )
        conexion.commit()
    return nombre_indice


def guardar_dataframe_sqlite(
    df: pd.DataFrame,
    ruta_db: str | Path,
    nombre_tabla: str,
    if_exists: str = "replace",
    index: bool = False,
) -> str:
    """Crea o actualiza una tabla SQLite desde un DataFrame."""
    if if_exists not in {"fail", "replace", "append"}:
        raise ValueError("if_exists debe ser 'fail', 'replace' o 'append'.")

    nombre_tabla = normalizar_identificador_sql(nombre_tabla)
    with closing(conectar_sqlite(ruta_db)) as conexion:
        df.to_sql(nombre_tabla, conexion, if_exists=if_exists, index=index)
        conexion.commit()
    return nombre_tabla


def _normalizar_fecha_sqlite(serie: pd.Series) -> pd.Series:
    fechas = pd.to_datetime(serie, dayfirst=True, errors="coerce")
    normalizadas = fechas.dt.strftime("%d/%m/%Y")
    return normalizadas.fillna(serie.astype(str).str.strip())


def actualizar_dataframe_por_fecha_sqlite(
    df_nuevo: pd.DataFrame,
    ruta_db: str | Path,
    nombre_tabla: str,
    fecha_corte,
    columna_fecha: str = "FECHA",
) -> str:
    """Reemplaza en SQLite las filas de una fecha y conserva el resto."""
    nombre_tabla = normalizar_identificador_sql(nombre_tabla)
    df_nuevo = df_nuevo.copy()

    fecha_objetivo = pd.to_datetime(fecha_corte, dayfirst=True, errors="coerce")
    if pd.isna(fecha_objetivo):
        raise ValueError(f"Fecha no valida para actualizar SQLite: {fecha_corte}")
    fecha_texto = fecha_objetivo.strftime("%d/%m/%Y")

    if columna_fecha not in df_nuevo.columns:
        df_nuevo[columna_fecha] = fecha_texto
    else:
        df_nuevo[columna_fecha] = _normalizar_fecha_sqlite(df_nuevo[columna_fecha])
        df_nuevo = df_nuevo.loc[df_nuevo[columna_fecha] == fecha_texto].copy()

    if existe_tabla_sqlite(ruta_db, nombre_tabla):
        df_existente = leer_dataframe_sqlite(ruta_db, nombre_tabla)
    else:
        df_existente = pd.DataFrame(columns=df_nuevo.columns)

    if not df_existente.empty and columna_fecha in df_existente.columns:
        df_existente = df_existente.copy()
        df_existente[columna_fecha] = _normalizar_fecha_sqlite(df_existente[columna_fecha])
        df_existente = df_existente.loc[df_existente[columna_fecha] != fecha_texto]

    columnas = list(dict.fromkeys([*df_existente.columns, *df_nuevo.columns]))
    combinado = pd.concat(
        [
            df_existente.reindex(columns=columnas),
            df_nuevo.reindex(columns=columnas),
        ],
        ignore_index=True,
    )
    return guardar_dataframe_sqlite(combinado, ruta_db, nombre_tabla, if_exists="replace", index=False)


def leer_dataframe_sqlite(
    ruta_db: str | Path,
    nombre_tabla: str,
    columnas: Iterable[str] | None = None,
    where: str | None = None,
    params: Iterable | dict | None = None,
    limite: int | None = None,
) -> pd.DataFrame:
    """Lee una tabla SQLite completa o filtrada."""
    nombre_tabla = normalizar_identificador_sql(nombre_tabla)
    if not existe_tabla_sqlite(ruta_db, nombre_tabla):
        raise ValueError(f"No existe la tabla SQLite: {nombre_tabla}")

    if columnas:
        columnas_sql = ", ".join(citar_identificador(columna) for columna in columnas)
    else:
        columnas_sql = "*"

    sql = f"SELECT {columnas_sql} FROM {citar_identificador(nombre_tabla)}"
    if where:
        sql = f"{sql} WHERE {where}"
    if limite is not None:
        sql = f"{sql} LIMIT {int(limite)}"

    with closing(conectar_sqlite(ruta_db)) as conexion:
        return pd.read_sql_query(sql, conexion, params=params)


def crear_tabla_sqlite(
    ruta_db: str | Path,
    nombre_tabla: str,
    columnas: dict[str, str],
    reemplazar: bool = False,
) -> str:
    """Crea una tabla vacia con tipos SQLite basicos."""
    if not columnas:
        raise ValueError("Se requiere al menos una columna para crear la tabla.")

    nombre_tabla = normalizar_identificador_sql(nombre_tabla)
    definiciones: list[str] = []
    for nombre_columna, tipo_sql in columnas.items():
        tipo = str(tipo_sql).strip().upper()
        if tipo not in _TIPOS_SQLITE_VALIDOS:
            raise ValueError(f"Tipo SQLite no soportado para {nombre_columna}: {tipo_sql}")
        definiciones.append(f"{citar_identificador(nombre_columna)} {tipo}")

    with closing(conectar_sqlite(ruta_db)) as conexion:
        if reemplazar:
            conexion.execute(f"DROP TABLE IF EXISTS {citar_identificador(nombre_tabla)}")
        conexion.execute(
            f"CREATE TABLE IF NOT EXISTS {citar_identificador(nombre_tabla)} "
            f"({', '.join(definiciones)})"
        )
        conexion.commit()
    return nombre_tabla
