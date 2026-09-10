from __future__ import annotations

import errno
from pathlib import Path
import sys
import unicodedata

import pandas as pd


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from compartido.nucleo_risko.archivos import (
    leer_csv_con_codificaciones,
    leer_excel,
    registrar_log,
)
from compartido.nucleo_risko.base_datos import (
    actualizar_dataframe_por_fecha_sqlite,
    columnas_tabla_sqlite,
    conectar_sqlite,
    crear_tabla_sqlite,
    crear_indice_sqlite,
    guardar_dataframe_sqlite,
    leer_dataframe_sqlite,
    listar_tablas_sqlite,
)
from compartido.nucleo_risko.rutas import (
    ARCHIVO_BASE_DATOS_POSITION_MONITOR,
    ARCHIVO_BASE_DATOS_RISKO_PRUEBAS,
    ARCHIVO_POSICION_ACTUAL,
    ARCHIVO_POSICION_CONSOLIDADA,
    ARCHIVO_POSICION_HISTORICO,
    ARCHIVO_SALIDA_FORWARD,
    ARCHIVO_SALIDA_FORWARD_TABLA,
    ARCHIVO_SALIDA_NOVADOS,
    ARCHIVO_SALIDA_NOVADOS_LEGACY,
    ARCHIVO_SALIDA_OPCIONES_TABLA,
    ARCHIVO_SALIDA_RENTA_FIJA,
    ARCHIVO_SALIDA_RENTA_FIJA_TABLA,
    ARCHIVO_SALIDA_SWAPS_TABLA,
)


TABLA_POSICION_CONSOLIDADA = "tbl_posicion_consolidada"
TABLA_POSICION_ACTUAL = "tbl_posicion_actual"
TABLA_POSICION_HISTORICO = "tbl_posicion_historico"
TABLA_POSICION_FORWARD = "tbl_posicion_forward"
TABLA_POSICION_NOVADOS = "tbl_posicion_novados"
TABLA_POSICION_OPCIONES = "tbl_posicion_opciones"
TABLA_POSICION_RENTA_FIJA = "tbl_posicion_renta_fija"
TABLA_POSICION_SWAPS = "tbl_posicion_swaps"
TABLA_POSICION_SPOT = "tbl_posicion_spot"
TABLA_POSICION_CUBREBONOS = "tbl_posicion_cubrebonos"
TABLA_POSICION_NDFTES = "tbl_posicion_ndftes"
TABLA_POSICION_PP = "tbl_posicion_pp"
PRODUCTOS_EN_PRUEBAS: set[str] = set()

# Modulos que conservan codigo de apoyo, pero aun no estan liberados.
PRODUCTOS_EXCLUIDOS_CONSOLIDACION = {"CUBREBONOS", "NDFTES", "PP"}

TABLAS_PRODUCTO = {
    "FORWARD": TABLA_POSICION_FORWARD,
    "NOVADOS": TABLA_POSICION_NOVADOS,
    "OPCIONES": TABLA_POSICION_OPCIONES,
    "RENTA_FIJA": TABLA_POSICION_RENTA_FIJA,
    "RENTA FIJA": TABLA_POSICION_RENTA_FIJA,
    "TITULOS": TABLA_POSICION_RENTA_FIJA,
    "SWAPS": TABLA_POSICION_SWAPS,
    "SWAP": TABLA_POSICION_SWAPS,
    "SPOT": TABLA_POSICION_SPOT,
    "CUBREBONOS": TABLA_POSICION_CUBREBONOS,
    "CUBRE_BONOS": TABLA_POSICION_CUBREBONOS,
    "NDFTES": TABLA_POSICION_NDFTES,
    "NDF_TES": TABLA_POSICION_NDFTES,
    "PP": TABLA_POSICION_PP,
}

COLUMNAS_POSICION = [
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
]

MAPA_COLUMNAS = {
    "FECHA": "FECHA",
    "PRODUCTO": "PRODUCTO",
    "BOOK": "BOOK",
    "POSICION": "POSICION",
    "MONEDA_POSICION": "MONEDA_POSICION",
    "MONEDA_POSICION_": "MONEDA_POSICION",
    "MONEDA_POSICIONN": "MONEDA_POSICION",
    "MONEDA": "MONEDA_POSICION",
    "LB_LT": "LB_LT",
    "LB_L_T": "LB_LT",
    "LB_BT": "LB_LT",
    "AGENCIA": "COMPANY",
    "COMPANY": "COMPANY",
    "INSTRUMENTO": "INSTRUMENTO",
    "DER_TF": "INSTRUMENTO",
    "CLASIFICACION_CONTABLE": "CLASIFICACION_CONTABLE",
    "BANKING_CVA_DVA": "BANKING_CVA_DVA",
}

MAPA_PRODUCTOS = {
    "NOVADO": "Novados",
    "NOVADOS": "Novados",
    "FORWARD": "Forward",
    "OPCION": "Opciones",
    "OPCIONES": "Opciones",
    "SWAP": "Swap",
    "SWAPS": "Swap",
    "TITULOS": "Titulos",
    "TITULO": "Titulos",
    "RENTA_FIJA": "Titulos",
    "SPOT": "Spot",
    "CAJA": "Spot",
    "CUBREBONOS": "Cubrebonos",
    "CUBRE_BONOS": "Cubrebonos",
    "NDFTES": "NDFTES",
    "NDF_TES": "NDFTES",
    "PP": "PP",
}

MAPA_BANKING = {
    "BANKING": "Banking",
    "IFRS": "IFRS",
    "CVA_DVA": "CVA/DVA",
    "CVA/DVA": "CVA/DVA",
    "CVA DVA": "CVA/DVA",
}
VISTAS_PUBLICABLES = {"BANKING", "CVA_DVA", "CVA/DVA", "CVA DVA"}


def _resolver_ruta_db(ruta_db: str | Path | None = None, pruebas: bool = False) -> Path:
    if ruta_db is not None:
        return Path(ruta_db)
    if pruebas:
        return ARCHIVO_BASE_DATOS_RISKO_PRUEBAS
    return ARCHIVO_BASE_DATOS_POSITION_MONITOR


def conectar_base_position_monitor(ruta_db: str | Path | None = None, pruebas: bool = False):
    """Abre la base SQLite usada por Position Monitor."""
    return conectar_sqlite(_resolver_ruta_db(ruta_db, pruebas=pruebas))


def listar_tablas_position_monitor(
    ruta_db: str | Path | None = None,
    pruebas: bool = False,
) -> list[str]:
    """Lista las tablas disponibles en la base SQLite de Position Monitor."""
    return listar_tablas_sqlite(_resolver_ruta_db(ruta_db, pruebas=pruebas))


def columnas_tabla_position_monitor(
    nombre_tabla: str,
    ruta_db: str | Path | None = None,
    pruebas: bool = False,
) -> list[str]:
    return columnas_tabla_sqlite(_resolver_ruta_db(ruta_db, pruebas=pruebas), nombre_tabla)


def nombre_tabla_producto(producto: str) -> str:
    clave = _normalizar_nombre_columna(producto)
    return TABLAS_PRODUCTO.get(clave, f"tbl_posicion_{clave.lower()}")


def crear_tabla_auxiliar(
    nombre_tabla: str,
    columnas: dict[str, str],
    ruta_db: str | Path | None = None,
    reemplazar: bool = False,
    logger=None,
) -> str:
    """
    Crea una tabla auxiliar vacia en SQLite.

    Ejemplo de columnas: {"fecha": "TEXT", "trm": "REAL"}.
    Por defecto usa risko_pruebas.db para no mezclar pruebas con la base oficial.
    """
    nombre = crear_tabla_sqlite(
        _resolver_ruta_db(ruta_db, pruebas=True),
        nombre_tabla,
        columnas,
        reemplazar=reemplazar,
    )
    registrar_log(logger, f"Tabla auxiliar disponible en SQLite: {nombre}")
    return nombre


def guardar_tabla_position_monitor(
    nombre_tabla: str,
    datos,
    ruta_db: str | Path | None = None,
    if_exists: str = "replace",
    pruebas: bool = False,
    logger=None,
) -> str:
    """Guarda un DataFrame o estructura tabular en SQLite."""
    df = datos.copy() if isinstance(datos, pd.DataFrame) else pd.DataFrame(datos)
    nombre = guardar_dataframe_sqlite(
        df,
        _resolver_ruta_db(ruta_db, pruebas=pruebas),
        nombre_tabla,
        if_exists=if_exists,
        index=False,
    )
    _crear_indice_fecha_si_existe(nombre, df, ruta_db=ruta_db, pruebas=pruebas)
    registrar_log(logger, f"Tabla SQLite actualizada: {nombre} ({len(df)} filas).")
    return nombre


def leer_tabla_position_monitor(
    nombre_tabla: str,
    ruta_db: str | Path | None = None,
    columnas: list[str] | None = None,
    where: str | None = None,
    params=None,
    pruebas: bool = False,
    limite: int | None = None,
) -> pd.DataFrame:
    """Lee una tabla desde SQLite."""
    return leer_dataframe_sqlite(
        _resolver_ruta_db(ruta_db, pruebas=pruebas),
        nombre_tabla,
        columnas=columnas,
        where=where,
        params=params,
        limite=limite,
    )


def _crear_indice_fecha_si_existe(
    nombre_tabla: str,
    df: pd.DataFrame,
    ruta_db: str | Path | None = None,
    pruebas: bool = False,
) -> None:
    for columna in ("FECHA", "CORTE"):
        if columna in df.columns:
            crear_indice_sqlite(
                _resolver_ruta_db(ruta_db, pruebas=pruebas),
                nombre_tabla,
                [columna],
            )
            return


def actualizar_tabla_por_fecha_position_monitor(
    nombre_tabla: str,
    datos,
    fecha_corte,
    ruta_db: str | Path | None = None,
    columna_fecha: str = "FECHA",
    pruebas: bool = False,
    logger=None,
) -> str:
    """Reemplaza una fecha dentro de una tabla SQLite y conserva las demas."""
    df = datos.copy() if isinstance(datos, pd.DataFrame) else pd.DataFrame(datos)
    nombre = actualizar_dataframe_por_fecha_sqlite(
        df,
        _resolver_ruta_db(ruta_db, pruebas=pruebas),
        nombre_tabla,
        fecha_corte,
        columna_fecha=columna_fecha,
    )
    _crear_indice_fecha_si_existe(nombre, df, ruta_db=ruta_db, pruebas=pruebas)
    registrar_log(logger, f"Tabla SQLite actualizada por fecha: {nombre} ({fecha_corte}).")
    return nombre


def guardar_tabla_producto_position_monitor(
    producto: str,
    datos,
    fecha_corte,
    ruta_db: str | Path | None = None,
    pruebas: bool = False,
    logger=None,
) -> str:
    """Guarda la tabla de un producto en risko.db reemplazando la fecha procesada."""
    clave_producto = _normalizar_nombre_columna(producto)
    if clave_producto in PRODUCTOS_EN_PRUEBAS and not pruebas:
        raise ValueError(
            f"{producto} esta marcado como producto en pruebas. "
            "Guardelo en risko_pruebas.db usando pruebas=True."
        )

    nombre_tabla = nombre_tabla_producto(producto)
    df = datos.copy() if isinstance(datos, pd.DataFrame) else pd.DataFrame(datos)
    df = _normalizar_tabla_posicion(df)
    return actualizar_tabla_por_fecha_position_monitor(
        nombre_tabla,
        df,
        fecha_corte,
        ruta_db=ruta_db,
        columna_fecha="FECHA",
        pruebas=pruebas,
        logger=logger,
    )


def guardar_tabla_auxiliar(
    nombre_tabla: str,
    datos,
    ruta_db: str | Path | None = None,
    if_exists: str = "replace",
    logger=None,
) -> str:
    """Alias explicito para cargar tablas auxiliares en SQLite."""
    return guardar_tabla_position_monitor(
        nombre_tabla,
        datos,
        ruta_db=ruta_db,
        if_exists=if_exists,
        pruebas=True,
        logger=logger,
    )


def leer_tabla_auxiliar(
    nombre_tabla: str,
    ruta_db: str | Path | None = None,
    columnas: list[str] | None = None,
    where: str | None = None,
    params=None,
) -> pd.DataFrame:
    """Alias explicito para consultar tablas auxiliares en SQLite."""
    return leer_tabla_position_monitor(
        nombre_tabla,
        ruta_db=ruta_db,
        columnas=columnas,
        where=where,
        params=params,
        pruebas=True,
    )


def _normalizar_texto(valor) -> str:
    texto = str(valor).strip()
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto


def _normalizar_nombre_columna(nombre: str) -> str:
    texto = _normalizar_texto(nombre).upper()
    texto = "".join(caracter if caracter.isalnum() else "_" for caracter in texto)
    while "__" in texto:
        texto = texto.replace("__", "_")
    return texto.strip("_")


def _normalizar_producto(valor) -> str:
    clave = _normalizar_nombre_columna(valor)
    return MAPA_PRODUCTOS.get(clave, str(valor).strip())


def _normalizar_banking(valor) -> str:
    clave = _normalizar_nombre_columna(valor)
    return MAPA_BANKING.get(clave, str(valor).strip() or "Banking")


def _normalizar_lb_lt(valor) -> str:
    """Homologa el nombre legado Tesoreria a la clasificacion Trading."""
    clave = _normalizar_nombre_columna(valor)
    if clave in {"TESORERIA", "TRADING"}:
        return "Trading"
    if clave == "BANCARIO":
        return "Bancario"
    return str(valor).strip() or "No definido"


def _normalizar_fecha_serie(serie: pd.Series) -> pd.Series:
    fechas = pd.to_datetime(serie, dayfirst=True, errors="coerce")
    return fechas.dt.strftime("%d/%m/%Y")


def _normalizar_posicion_serie(serie: pd.Series) -> pd.Series:
    texto = serie.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(texto, errors="coerce").fillna(0.0)


def _normalizar_numero_serie(serie: pd.Series) -> pd.Series:
    texto = serie.astype(str).str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(texto, errors="coerce")


def _ordenar_tabla(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_FECHA_ORDEN"] = pd.to_datetime(df["FECHA"], dayfirst=True, errors="coerce")
    df = df.sort_values(
        by=["_FECHA_ORDEN", "PRODUCTO", "BOOK", "BANKING_CVA_DVA"],
        kind="stable",
    )
    return df.drop(columns="_FECHA_ORDEN").reset_index(drop=True)


def _normalizar_tabla_posicion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_normalizar_nombre_columna(columna) for columna in df.columns]
    df = df.rename(columns={columna: MAPA_COLUMNAS.get(columna, columna) for columna in df.columns})
    df = df.loc[:, ~df.columns.duplicated(keep="last")]

    for columna in COLUMNAS_POSICION:
        if columna not in df.columns:
            df[columna] = ""

    df["FECHA"] = _normalizar_fecha_serie(df["FECHA"])
    df["PRODUCTO"] = df["PRODUCTO"].apply(_normalizar_producto)
    df["BOOK"] = df["BOOK"].astype(str).str.strip()
    df["POSICION"] = _normalizar_posicion_serie(df["POSICION"])
    df["MONEDA_POSICION"] = df["MONEDA_POSICION"].astype(str).str.strip().replace({"": "USD", "nan": "USD", "None": "USD"})
    df["LB_LT"] = df["LB_LT"].apply(_normalizar_lb_lt)
    df["INSTRUMENTO"] = df["INSTRUMENTO"].astype(str).str.strip().replace({"": "Derivados", "nan": "Derivados", "None": "Derivados"})
    df["COMPANY"] = df["COMPANY"].astype(str).str.strip().replace({"": "Colombia", "nan": "Colombia", "None": "Colombia"})
    df["CLASIFICACION_CONTABLE"] = df["CLASIFICACION_CONTABLE"].astype(str).str.strip().replace({"": "NA", "nan": "NA", "None": "NA"})
    df["BANKING_CVA_DVA"] = df["BANKING_CVA_DVA"].apply(_normalizar_banking)

    df = df[df["FECHA"].notna() & (df["FECHA"] != "NaT")].copy()
    return df[COLUMNAS_POSICION]


def _clave_producto(serie: pd.Series) -> pd.Series:
    return serie.apply(lambda valor: _normalizar_nombre_columna(valor))


def _cargar_tabla_novados() -> pd.DataFrame | None:
    if ARCHIVO_SALIDA_NOVADOS.exists():
        return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ARCHIVO_SALIDA_NOVADOS))
    if ARCHIVO_SALIDA_NOVADOS_LEGACY.exists():
        return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ARCHIVO_SALIDA_NOVADOS_LEGACY))
    return None


def _cargar_tabla_forward() -> pd.DataFrame | None:
    if ARCHIVO_SALIDA_FORWARD_TABLA.exists():
        return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ARCHIVO_SALIDA_FORWARD_TABLA))

    if ARCHIVO_SALIDA_FORWARD.exists():
        return _normalizar_tabla_posicion(leer_excel(ARCHIVO_SALIDA_FORWARD))

    return None


def _cargar_tabla_opciones() -> pd.DataFrame | None:
    if not ARCHIVO_SALIDA_OPCIONES_TABLA.exists():
        return None
    return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ARCHIVO_SALIDA_OPCIONES_TABLA))


def _cargar_tabla_renta_fija() -> pd.DataFrame | None:
    if ARCHIVO_SALIDA_RENTA_FIJA_TABLA.exists():
        return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ARCHIVO_SALIDA_RENTA_FIJA_TABLA))

    if not ARCHIVO_SALIDA_RENTA_FIJA.exists():
        return None

    detalle = leer_excel(ARCHIVO_SALIDA_RENTA_FIJA, sheet_name="Detalle")
    detalle = detalle.rename(columns={"Fecha": "FECHA", "Book": "BOOK", "Posición": "POSICION", "LB/LT": "LB_LT", "Moneda": "MONEDA"})
    detalle["PRODUCTO"] = "Titulos"
    detalle["INSTRUMENTO"] = "Renta_fija"
    detalle["COMPANY"] = detalle.get("Agencia", "Colombia")
    detalle["CLASIFICACION_CONTABLE"] = "NA"
    detalle["BANKING_CVA_DVA"] = "Banking"
    return _normalizar_tabla_posicion(detalle)


def _cargar_tabla_swaps() -> pd.DataFrame | None:
    if not ARCHIVO_SALIDA_SWAPS_TABLA.exists():
        return None
    return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ARCHIVO_SALIDA_SWAPS_TABLA))


def _cargar_tabla_producto_sqlite(nombre_tabla: str, pruebas: bool = False) -> pd.DataFrame | None:
    try:
        tabla = leer_tabla_position_monitor(nombre_tabla, pruebas=pruebas)
    except ValueError:
        return None
    if tabla.empty:
        return None
    return _normalizar_tabla_posicion(tabla)


def cargar_tablas_desde_procesados(
    fecha_corte: str | None = None,
    logger=None,
    pruebas: bool = False,
) -> pd.DataFrame:
    tablas = []

    for nombre, nombre_tabla, cargador in (
        ("Novados", TABLA_POSICION_NOVADOS, _cargar_tabla_novados),
        ("Forward", TABLA_POSICION_FORWARD, _cargar_tabla_forward),
        ("Opciones", TABLA_POSICION_OPCIONES, _cargar_tabla_opciones),
        ("Titulos", TABLA_POSICION_RENTA_FIJA, _cargar_tabla_renta_fija),
        ("Swap", TABLA_POSICION_SWAPS, _cargar_tabla_swaps),
        ("Spot", TABLA_POSICION_SPOT, lambda: None),
        ("Cubrebonos", TABLA_POSICION_CUBREBONOS, lambda: None),
        ("NDFTES", TABLA_POSICION_NDFTES, lambda: None),
        ("PP", TABLA_POSICION_PP, lambda: None),
    ):
        if _normalizar_nombre_columna(nombre) in PRODUCTOS_EXCLUIDOS_CONSOLIDACION:
            registrar_log(
                logger,
                f"{nombre} no esta liberado para produccion; se excluye de la consolidacion.",
            )
            continue
        tabla = _cargar_tabla_producto_sqlite(nombre_tabla, pruebas=pruebas)
        origen = "SQLite"
        if (tabla is None or tabla.empty) and not pruebas:
            tabla = cargador()
            origen = "archivo procesado"
            if tabla is not None and not tabla.empty:
                guardar_tabla_position_monitor(nombre_tabla, tabla, if_exists="replace", logger=logger)

        if tabla is None or tabla.empty:
            registrar_log(logger, f"No se encontro una tabla vigente para {nombre}.")
            continue
        tablas.append(tabla)
        registrar_log(logger, f"Tabla de {nombre} cargada desde {origen}: {len(tabla)} filas.")

    if not tablas:
        raise FileNotFoundError("No se encontraron salidas procesadas para consolidar Position Monitor.")

    tabla_consolidada = pd.concat(tablas, ignore_index=True)
    if fecha_corte:
        fecha_objetivo = pd.to_datetime(fecha_corte, dayfirst=True, errors="coerce")
        if pd.isna(fecha_objetivo):
            raise ValueError(f"Fecha no valida para consolidacion: {fecha_corte}")
        tabla_consolidada = tabla_consolidada.loc[
            tabla_consolidada["FECHA"] == fecha_objetivo.strftime("%d/%m/%Y")
        ].copy()

    if tabla_consolidada.empty:
        raise ValueError("No hubo filas para consolidar con la fecha seleccionada.")

    return _ordenar_tabla(tabla_consolidada)


def _dataframe_posicion_vacio() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNAS_POSICION)


def _leer_tabla_posicion_sqlite_si_existe(nombre_tabla: str, pruebas: bool = False) -> pd.DataFrame:
    try:
        tabla = leer_tabla_position_monitor(nombre_tabla, pruebas=pruebas)
    except ValueError:
        return _dataframe_posicion_vacio()

    if tabla.empty:
        return _dataframe_posicion_vacio()
    return _normalizar_tabla_posicion(tabla)


def _leer_tabla_posicion(
    nombre_tabla: str,
    ruta_csv_legacy: Path | None = None,
    pruebas: bool = False,
) -> pd.DataFrame:
    tabla_sqlite = _leer_tabla_posicion_sqlite_si_existe(nombre_tabla, pruebas=pruebas)
    if not tabla_sqlite.empty:
        return tabla_sqlite

    if not pruebas and ruta_csv_legacy is not None and ruta_csv_legacy.exists():
        return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ruta_csv_legacy))

    return _dataframe_posicion_vacio()


def _leer_publicado_si_existe(ruta: Path) -> pd.DataFrame:
    tablas_por_ruta = {
        ARCHIVO_POSICION_CONSOLIDADA: TABLA_POSICION_CONSOLIDADA,
        ARCHIVO_POSICION_ACTUAL: TABLA_POSICION_ACTUAL,
        ARCHIVO_POSICION_HISTORICO: TABLA_POSICION_HISTORICO,
    }
    nombre_tabla = tablas_por_ruta.get(ruta)
    if nombre_tabla is not None:
        return _leer_tabla_posicion(nombre_tabla, ruta)

    if not ruta.exists():
        return _dataframe_posicion_vacio()
    return _normalizar_tabla_posicion(leer_csv_con_codificaciones(ruta))


def _exportar_csv_si_posible(df: pd.DataFrame, ruta: Path, logger=None) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
    except OSError as exc:
        if isinstance(exc, PermissionError) or getattr(exc, "errno", None) in {
            errno.EACCES,
            errno.EPERM,
        }:
            registrar_log(
                logger,
                "No se pudo actualizar el CSV porque parece estar abierto o bloqueado. "
                f"La base SQLite si quedo actualizada: {ruta}",
            )
            return
        raise


def _guardar_tabla_posicion(
    nombre_tabla: str,
    df: pd.DataFrame,
    ruta_csv: Path,
    logger=None,
    pruebas: bool = False,
    exportar_csv: bool = True,
) -> None:
    tabla = df[COLUMNAS_POSICION].copy() if not df.empty else _dataframe_posicion_vacio()
    guardar_tabla_position_monitor(nombre_tabla, tabla, if_exists="replace", pruebas=pruebas, logger=logger)
    if exportar_csv:
        _exportar_csv_si_posible(tabla, ruta_csv, logger=logger)


def _preparar_historico_desde_excel(
    ruta_excel: str | Path,
    hoja: str = "Hoja1",
    anio_real: int = 2026,
) -> pd.DataFrame:
    """Lee y valida una base real antes de reemplazar el historico oficial."""
    fuente = leer_excel(ruta_excel, sheet_name=hoja, keep_default_na=False)
    columnas_fuente = {
        _normalizar_nombre_columna(columna) for columna in fuente.columns
    }
    faltantes = [
        columna for columna in COLUMNAS_POSICION if columna not in columnas_fuente
    ]
    if faltantes:
        raise ValueError(
            "El historico no contiene todas las columnas requeridas: "
            + ", ".join(faltantes)
        )
    if fuente.empty:
        raise ValueError("El historico de origen esta vacio.")

    tabla = _normalizar_tabla_posicion(fuente)
    if len(tabla) != len(fuente):
        raise ValueError("El historico contiene fechas vacias o no validas.")

    fechas = pd.to_datetime(tabla["FECHA"], dayfirst=True, errors="coerce")
    anios = sorted(set(fechas.dt.year.dropna().astype(int)))
    if anios != [anio_real]:
        raise ValueError(
            f"El historico real debe contener unicamente {anio_real}; "
            f"se encontraron los anos: {anios}."
        )

    fechas_no_cierre = sorted(
        set(tabla.loc[~fechas.apply(_es_fin_mes_operativo), "FECHA"])
    )
    if fechas_no_cierre:
        raise ValueError(
            "El historico contiene fechas que no son ultimo dia calendario del mes: "
            + ", ".join(fechas_no_cierre)
        )

    vistas = tabla["BANKING_CVA_DVA"].apply(_normalizar_nombre_columna)
    vistas_no_publicables = sorted(
        set(tabla.loc[~vistas.isin(VISTAS_PUBLICABLES), "BANKING_CVA_DVA"])
    )
    if vistas_no_publicables:
        raise ValueError(
            "El historico contiene vistas no publicables: "
            + ", ".join(vistas_no_publicables)
        )

    columnas_clave = [columna for columna in COLUMNAS_POSICION if columna != "POSICION"]
    duplicados = tabla.duplicated(subset=columnas_clave, keep=False)
    if duplicados.any():
        muestra = tabla.loc[duplicados, columnas_clave].head(5).to_dict("records")
        raise ValueError(
            "El historico contiene posiciones duplicadas para una misma fecha: "
            f"{muestra}"
        )

    return _ordenar_tabla(tabla)


def reemplazar_historico_desde_excel(
    ruta_excel: str | Path,
    hoja: str = "Hoja1",
    anio_real: int = 2026,
    logger=None,
    pruebas: bool = False,
) -> pd.DataFrame:
    """Reemplaza el historico completo con una base mensual previamente validada.

    Esta operacion es intencionalmente explicita: depura todos los anos que
    existan en la tabla anterior. El flujo diario posterior vuelve a sumar cada
    corte ejecutado en el ultimo dia calendario del mes.
    """
    historico = _preparar_historico_desde_excel(
        ruta_excel,
        hoja=hoja,
        anio_real=anio_real,
    )
    _guardar_tabla_posicion(
        TABLA_POSICION_HISTORICO,
        historico,
        ARCHIVO_POSICION_HISTORICO,
        logger=logger,
        pruebas=pruebas,
        exportar_csv=not pruebas,
    )
    registrar_log(
        logger,
        f"Historico real {anio_real} publicado desde {ruta_excel}: "
        f"{len(historico)} filas.",
    )
    return historico


def _fusionar_historico(df_existente: pd.DataFrame, df_nuevo: pd.DataFrame) -> pd.DataFrame:
    df_existente = df_existente.copy()
    df_existente["_PRODUCTO_CLAVE"] = _clave_producto(df_existente["PRODUCTO"])
    df_nuevo = df_nuevo.copy()
    df_nuevo["_PRODUCTO_CLAVE"] = _clave_producto(df_nuevo["PRODUCTO"])

    productos_objetivo = set(df_nuevo["_PRODUCTO_CLAVE"].unique())
    fechas_objetivo = set(df_nuevo["FECHA"].unique())

    mascara = (
        df_existente["_PRODUCTO_CLAVE"].isin(productos_objetivo)
        & df_existente["FECHA"].isin(fechas_objetivo)
    )
    base = df_existente.loc[~mascara, COLUMNAS_POSICION]
    nuevo = df_nuevo[COLUMNAS_POSICION]
    if base.empty:
        combinado = nuevo.copy()
    elif nuevo.empty:
        combinado = base.copy()
    else:
        combinado = pd.concat([base, nuevo], ignore_index=True)
    return _ordenar_tabla(combinado)


def _es_fin_mes_operativo(fecha: pd.Timestamp) -> bool:
    """Indica si la fecha es el ultimo dia calendario de su mes.

    El nombre se conserva por compatibilidad interna. El cierre historico no
    usa el ultimo dia habil: cuando el mes termina en sabado, domingo o festivo,
    se guarda el corte construido para esa fecha no habil.
    """
    if pd.isna(fecha):
        return False
    fecha = fecha.normalize()
    return (fecha + pd.Timedelta(days=1)).month != fecha.month


def _filtrar_fin_mes_historico(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df[COLUMNAS_POSICION].copy()
    tabla = df.copy()
    fechas = pd.to_datetime(tabla["FECHA"], dayfirst=True, errors="coerce")
    mascara = fechas.apply(_es_fin_mes_operativo)
    return _ordenar_tabla(tabla.loc[mascara, COLUMNAS_POSICION].copy())


def _seleccionar_actual_desde_tabla(df_nuevo: pd.DataFrame, fecha_actual: str | None = None) -> pd.DataFrame:
    df_nuevo = df_nuevo.copy()
    if fecha_actual is not None:
        return df_nuevo.loc[df_nuevo["FECHA"] == fecha_actual, COLUMNAS_POSICION].copy()

    df_nuevo["_PRODUCTO_CLAVE"] = _clave_producto(df_nuevo["PRODUCTO"])
    df_nuevo["_FECHA_ORDEN"] = pd.to_datetime(df_nuevo["FECHA"], dayfirst=True, errors="coerce")
    fechas_maximas = df_nuevo.groupby("_PRODUCTO_CLAVE")["_FECHA_ORDEN"].transform("max")
    actual_nuevo = df_nuevo.loc[df_nuevo["_FECHA_ORDEN"] == fechas_maximas, COLUMNAS_POSICION].copy()
    return _ordenar_tabla(actual_nuevo)


def _filtrar_vistas_actual(df_actual: pd.DataFrame) -> pd.DataFrame:
    mascara = df_actual["BANKING_CVA_DVA"].apply(_normalizar_nombre_columna).isin(VISTAS_PUBLICABLES)
    return _ordenar_tabla(df_actual.loc[mascara, COLUMNAS_POSICION].copy())


def _filtrar_vistas_consolidadas(df: pd.DataFrame) -> pd.DataFrame:
    """Mantiene solo las vistas que se presentan en tablas consolidadas."""
    if df.empty:
        return df[COLUMNAS_POSICION].copy()
    return _filtrar_vistas_actual(df)


def _excluir_productos_no_liberados(
    df: pd.DataFrame,
    logger=None,
) -> pd.DataFrame:
    """Retira solo de la entrada nueva los modulos aun no liberados."""
    if df.empty:
        return df[COLUMNAS_POSICION].copy()
    claves = _clave_producto(df["PRODUCTO"])
    mascara = claves.isin(PRODUCTOS_EXCLUIDOS_CONSOLIDACION)
    if mascara.any():
        productos = sorted(set(df.loc[mascara, "PRODUCTO"].astype(str)))
        registrar_log(
            logger,
            "Se excluyen de la consolidacion los modulos en pruebas: "
            + ", ".join(productos),
        )
    return _ordenar_tabla(df.loc[~mascara, COLUMNAS_POSICION].copy())


def consolidar_position_monitor(
    fecha_corte: str | None = None,
    tablas: list[pd.DataFrame] | None = None,
    logger=None,
    pruebas: bool = False,
) -> dict[str, Path]:
    if tablas is None:
        tabla_nueva = cargar_tablas_desde_procesados(
            fecha_corte=fecha_corte,
            logger=logger,
            pruebas=pruebas,
        )
    else:
        tabla_nueva = pd.concat([_normalizar_tabla_posicion(tabla) for tabla in tablas], ignore_index=True)
        if fecha_corte:
            fecha_objetivo = pd.to_datetime(fecha_corte, dayfirst=True, errors="coerce")
            if pd.isna(fecha_objetivo):
                raise ValueError(f"Fecha no valida para consolidacion: {fecha_corte}")
            tabla_nueva = tabla_nueva.loc[
                tabla_nueva["FECHA"] == fecha_objetivo.strftime("%d/%m/%Y")
            ].copy()
        tabla_nueva = _ordenar_tabla(tabla_nueva)

    tabla_nueva = _excluir_productos_no_liberados(tabla_nueva, logger=logger)
    if tabla_nueva.empty:
        raise ValueError("No hay informacion para consolidar Position Monitor.")

    tabla_nueva_publicable = _filtrar_vistas_consolidadas(tabla_nueva)
    if tabla_nueva_publicable.empty:
        raise ValueError("No hay informacion publicable para consolidar Position Monitor.")

    consolidada_existente = _leer_tabla_posicion(
        TABLA_POSICION_CONSOLIDADA,
        ARCHIVO_POSICION_CONSOLIDADA,
        pruebas=pruebas,
    )
    consolidada_existente = _filtrar_vistas_consolidadas(consolidada_existente)
    consolidada = _fusionar_historico(consolidada_existente, tabla_nueva_publicable)
    _guardar_tabla_posicion(
        TABLA_POSICION_CONSOLIDADA,
        consolidada,
        ARCHIVO_POSICION_CONSOLIDADA,
        logger=logger,
        pruebas=pruebas,
        exportar_csv=not pruebas,
    )

    historico_existente = _leer_tabla_posicion(
        TABLA_POSICION_HISTORICO,
        ARCHIVO_POSICION_HISTORICO,
        pruebas=pruebas,
    )
    historico_existente = _filtrar_vistas_consolidadas(historico_existente)
    historico = _fusionar_historico(historico_existente, tabla_nueva_publicable)
    historico = _filtrar_fin_mes_historico(historico)
    _guardar_tabla_posicion(
        TABLA_POSICION_HISTORICO,
        historico,
        ARCHIVO_POSICION_HISTORICO,
        logger=logger,
        pruebas=pruebas,
        exportar_csv=not pruebas,
    )

    fecha_actual = None
    if fecha_corte:
        fecha_actual = pd.to_datetime(fecha_corte, dayfirst=True, errors="coerce").strftime("%d/%m/%Y")
    actual = _seleccionar_actual_desde_tabla(consolidada, fecha_actual=fecha_actual)
    actual = _filtrar_vistas_actual(actual)
    _guardar_tabla_posicion(
        TABLA_POSICION_ACTUAL,
        actual,
        ARCHIVO_POSICION_ACTUAL,
        logger=logger,
        pruebas=pruebas,
        exportar_csv=not pruebas,
    )

    ruta_db = _resolver_ruta_db(pruebas=pruebas)
    registrar_log(logger, f"Base SQLite actualizada en: {ruta_db}")
    if pruebas:
        registrar_log(logger, "Modo pruebas activo: no se exportaron CSV oficiales.")
    else:
        registrar_log(logger, f"Consolidado interno exportado en: {ARCHIVO_POSICION_CONSOLIDADA}")
        registrar_log(logger, f"Posicion actual publicada en: {ARCHIVO_POSICION_ACTUAL}")
        registrar_log(logger, f"Historico publicado en: {ARCHIVO_POSICION_HISTORICO}")

    return {
        "base_datos": ruta_db,
        "consolidado": ARCHIVO_POSICION_CONSOLIDADA,
        "actual": ARCHIVO_POSICION_ACTUAL,
        "historico": ARCHIVO_POSICION_HISTORICO,
    }


def reiniciar_tablas_consolidadas(logger=None, pruebas: bool = False) -> dict[str, Path]:
    """Reinicia las salidas consolidadas; las tablas por producto no se tocan."""
    vacia = _dataframe_posicion_vacio()
    for nombre_tabla, ruta in (
        (TABLA_POSICION_CONSOLIDADA, ARCHIVO_POSICION_CONSOLIDADA),
        (TABLA_POSICION_ACTUAL, ARCHIVO_POSICION_ACTUAL),
        (TABLA_POSICION_HISTORICO, ARCHIVO_POSICION_HISTORICO),
    ):
        _guardar_tabla_posicion(
            nombre_tabla,
            vacia,
            ruta,
            logger=logger,
            pruebas=pruebas,
            exportar_csv=not pruebas,
        )
        registrar_log(logger, f"Tabla reiniciada: {nombre_tabla}")
    return {
        "base_datos": ARCHIVO_BASE_DATOS_POSITION_MONITOR,
        "consolidado": ARCHIVO_POSICION_CONSOLIDADA,
        "actual": ARCHIVO_POSICION_ACTUAL,
        "historico": ARCHIVO_POSICION_HISTORICO,
    }
