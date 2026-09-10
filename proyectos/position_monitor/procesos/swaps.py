from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from compartido.nucleo_risko.archivos import (
    actualizar_datos_por_fecha,
    leer_csv,
    registrar_log,
)
from compartido.nucleo_risko.tablas_auxiliares import guardar_tablas_auxiliares_modulo
from compartido.nucleo_risko.rutas import (
    ARCHIVO_PARAM_RUTAS,
    ARCHIVO_SALIDA_SWAPS_DETALLE,
    ARCHIVO_SALIDA_SWAPS_TABLA,
    ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE,
)
from proyectos.position_monitor.procesos.parametros_libros import (
    VALOR_LB_LT_NO_DEFINIDO,
    enriquecer_con_parametros_libros,
)


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

COLUMNAS_SWAP_REQUERIDAS = [
    "TRADE ID",
    "PAY/REC",
    "FREQ",
    "FREQ_RESET",
    "MODALIDAD",
    "START",
    "END",
    "FIXING",
    "FECHA FX FIXING",
    "NOTIONAL",
    "NOTIONAL CCY",
    "DATE",
    "FLOWS",
    "TYPE",
    "FLOWS_SETT_CCY",
    "CLIENTE",
    "ID_TYPE",
    "ID_CONTRAPARTE",
    "CCS/IRS",
    "BOOK",
    "DESK",
    "COMPANY",
    "MONEDA EN RIESGO",
    "Flujo en Moneda en Riesgo",
    "VP MONEDA EN RIESGO",
]

COLUMNAS_NUMERICAS_SWAP = [
    "NOTIONAL",
    "FLOWS",
    "Flujo en Moneda en Riesgo",
    "VP MONEDA EN RIESGO",
]

COLUMNAS_FECHA_SWAP = [
    "START",
    "END",
    "FIXING",
    "FECHA FX FIXING",
    "DATE",
]

MAPA_COMPANY = {
    "BDB_COLOMBIA": "Colombia",
    "COLOMBIA": "Colombia",
}

ETIQUETAS_SWAPS = ("Banking", "IFRS", "CVA/DVA")
ORDEN_ETIQUETAS_SWAPS = {etiqueta: indice for indice, etiqueta in enumerate(ETIQUETAS_SWAPS)}
ORDEN_LB_LT_SWAPS = {
    "Bancario": 0,
    "Trading": 1,
    VALOR_LB_LT_NO_DEFINIDO: 2,
}
BOOK_TOTAL_SWAPS = "SWAP"
BOOK_TRADING_PUBLICADO = "Swaps"
MAPA_ETIQUETAS_POSICION = {
    "BANKING": "Banking",
    "IFRS": "IFRS",
    "CVA DVA": "CVA/DVA",
    "CVA_DVA": "CVA/DVA",
    "CVA/DVA": "CVA/DVA",
}
MAPA_LB_LT_PUBLICACION = {
    "BANCARIO": "Bancario",
    "TRADING": "Trading",
    # Compatibilidad al leer salidas historicas anteriores al cambio de nombre.
    "TESORERIA": "Trading",
}


def _normalizar_fecha_trabajo(fecha_trabajo: str) -> pd.Timestamp:
    """Convierte la fecha de corte diligenciada a Timestamp y valida el formato."""
    fecha_valor = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_valor):
        raise ValueError(f"Fecha no valida para Swaps: {fecha_trabajo}")
    return fecha_valor.normalize()


def _resolver_fecha_fuente(fecha_corte: pd.Timestamp) -> pd.Timestamp:
    """Usa siempre el reporte exacto del corte, incluidos fines de semana."""
    return fecha_corte.normalize()


def _cargar_parametros_rutas() -> pd.DataFrame:
    """Lee el archivo maestro de rutas parametrizadas del Position Monitor."""
    return leer_csv(ARCHIVO_PARAM_RUTAS, sep=",", encoding="latin-1")


def _fila_parametro(df_parametros: pd.DataFrame, detalle: str) -> pd.Series:
    fila = df_parametros.loc[df_parametros["Detalle"].astype(str).str.strip() == detalle]
    if fila.empty:
        raise ValueError(f"No se encontro la configuracion {detalle} en param_rutas.csv")
    return fila.iloc[0]


def _ruta_desde_parametro(fila: pd.Series, sufijo: str) -> Path:
    """Construye la ruta final a partir de Ruta + Nombre_Archivo + sufijo."""
    ruta_base = str(fila["Ruta"]).strip()
    nombre_archivo = str(fila["Nombre_Archivo"]).strip()
    return Path(f"{ruta_base}{nombre_archivo}{sufijo}")


def _construir_rutas_swaps(fecha_fuente: pd.Timestamp, logger=None) -> dict[str, Path]:
    """Construye las rutas locales que Vector debe poblar para Banking e IFRS."""
    df_parametros = _cargar_parametros_rutas()
    sufijo = f"{fecha_fuente.strftime('%d%m%y')}_000.xls"

    configuraciones = {
        "banking": "Swaps_Banking_Local",
        "ifrs": "Swaps_IFRS_Local",
    }

    rutas: dict[str, Path] = {}
    for llave, detalle_local in configuraciones.items():
        fila_local = _fila_parametro(df_parametros, detalle_local)

        rutas[f"{llave}_local"] = _ruta_desde_parametro(fila_local, sufijo)

        registrar_log(logger, f"Ruta Swaps {llave} local esperada: {rutas[f'{llave}_local']}")

    return rutas


def _validar_insumo_vector(ruta_local: Path, etiqueta: str, logger=None) -> Path:
    """Valida que Vector haya dejado el insumo local de Swaps."""
    registrar_log(logger, f"Insumo Swaps {etiqueta} esperado por Vector: {ruta_local}")
    if not ruta_local.exists():
        raise FileNotFoundError(
            f"Vector no dejo el insumo de Swaps {etiqueta} para la fecha seleccionada: {ruta_local}"
        )

    return ruta_local


def _leer_fecha_valoracion_archivo(ruta_archivo: Path) -> pd.Timestamp | None:
    """Extrae la fecha interna informada en el encabezado del archivo fuente."""
    with ruta_archivo.open("r", encoding="latin1", newline="") as archivo:
        next(archivo, "")
        segunda_linea = next(archivo, "")

    coincidencia = re.search(r"(\d{2}/\d{2}/\d{4})", segunda_linea)
    if coincidencia is None:
        return None

    fecha_archivo = pd.to_datetime(coincidencia.group(1), dayfirst=True, errors="coerce")
    if pd.isna(fecha_archivo):
        return None

    return fecha_archivo.normalize()


def _leer_insumo_swap(ruta_archivo: Path) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Lee un reporte SwapTotalReport y retorna el DataFrame crudo y su fecha interna."""
    fecha_archivo = _leer_fecha_valoracion_archivo(ruta_archivo)
    df_swap = pd.read_csv(
        ruta_archivo,
        sep=";",
        skiprows=3,
        encoding="latin1",
        engine="python",
        index_col=False,
        on_bad_lines="skip",
    )
    df_swap.columns = df_swap.columns.astype(str).str.strip()
    df_swap = df_swap.loc[:, ~df_swap.columns.str.startswith("Unnamed")]

    if "FILA" in df_swap.columns:
        df_swap = df_swap.drop(columns=["FILA"])

    return df_swap, fecha_archivo


def _leer_banking_swaps(ruta_archivo: Path) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Lee el insumo Banking de Swaps."""
    return _leer_insumo_swap(ruta_archivo)


def _leer_ifrs_swaps(ruta_archivo: Path) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Lee el insumo IFRS de Swaps."""
    return _leer_insumo_swap(ruta_archivo)


def _validar_fecha_valoracion_archivo(
    fecha_archivo: pd.Timestamp | None,
    fecha_fuente: pd.Timestamp,
    etiqueta: str,
    logger=None,
) -> None:
    """Valida que la fecha interna del archivo corresponda al archivo fuente esperado."""
    if fecha_archivo is None:
        registrar_log(
            logger,
            f"No se pudo leer la fecha interna del archivo {etiqueta}; se continua con la fecha fuente parametrizada.",
        )
        return

    registrar_log(logger, f"Fecha interna de valoracion {etiqueta}: {fecha_archivo.strftime('%d/%m/%Y')}")
    if fecha_archivo.date() != fecha_fuente.date():
        raise ValueError(
            f"La fecha interna del archivo {etiqueta} ({fecha_archivo.strftime('%d/%m/%Y')}) "
            f"no coincide con la fecha fuente esperada ({fecha_fuente.strftime('%d/%m/%Y')})."
        )


def _depurar_insumo_swaps(
    df_insumo: pd.DataFrame,
    fecha_archivo: pd.Timestamp | None,
) -> pd.DataFrame:
    """
    Conserva solo las columnas necesarias para posicion y normaliza tipos basicos.

    Recibe el archivo crudo ya leido y devuelve un DataFrame listo para el calculo de
    posicion USD, con fechas y numericos estandarizados.
    """
    df_swap = df_insumo.copy()
    df_swap.columns = df_swap.columns.astype(str).str.strip()

    faltantes = [columna for columna in COLUMNAS_SWAP_REQUERIDAS if columna not in df_swap.columns]
    if faltantes:
        raise ValueError(
            "El insumo de Swaps no contiene todas las columnas requeridas. "
            f"Faltan: {', '.join(faltantes)}"
        )

    df_swap = df_swap[COLUMNAS_SWAP_REQUERIDAS].copy()

    for columna in df_swap.columns:
        if columna in COLUMNAS_NUMERICAS_SWAP or columna in COLUMNAS_FECHA_SWAP:
            continue
        df_swap[columna] = df_swap[columna].fillna("").astype(str).str.strip()

    for columna in COLUMNAS_FECHA_SWAP:
        df_swap[columna] = pd.to_datetime(
            df_swap[columna].astype(str).str.strip(),
            dayfirst=True,
            errors="coerce",
        )

    for columna in COLUMNAS_NUMERICAS_SWAP:
        df_swap[columna] = pd.to_numeric(
            df_swap[columna].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        ).fillna(0.0)

    df_swap["BOOK"] = (
        df_swap["BOOK"]
        .replace({"": "Sin_Book", "nan": "Sin_Book", "None": "Sin_Book"})
        .astype(str)
        .str.strip()
    )
    df_swap["MONEDA EN RIESGO"] = df_swap["MONEDA EN RIESGO"].astype(str).str.strip().str.upper()
    df_swap["FECHA_VALORACION_ARCHIVO"] = (
        fecha_archivo.strftime("%d/%m/%Y") if fecha_archivo is not None else ""
    )

    return df_swap


def _calcular_posicion_usd(df_swap: pd.DataFrame, fecha_valoracion: pd.Timestamp) -> pd.DataFrame:
    """
    Calcula POSICION_USD aplicando la regla funcional definida para Swaps.

    Reglas:
    - si DATE < fecha_valoracion -> 0
    - si MONEDA EN RIESGO == COP -> 0
    - en otro caso -> VP MONEDA EN RIESGO
    """
    df_swap = df_swap.copy()
    fechas_flujo = pd.to_datetime(df_swap["DATE"], errors="coerce")

    df_swap["POSICION_USD"] = np.where(
        fechas_flujo < fecha_valoracion,
        0.0,
        np.where(
            df_swap["MONEDA EN RIESGO"].eq("COP"),
            0.0,
            df_swap["VP MONEDA EN RIESGO"],
        ),
    )
    return df_swap


def _normalizar_company(valor: str) -> str:
    texto = str(valor).strip()
    if texto in ("", "nan", "None"):
        return "Colombia"
    return MAPA_COMPANY.get(texto.upper(), texto)


def _company_por_book(serie: pd.Series) -> str:
    for valor in serie:
        texto = str(valor).strip()
        if texto not in ("", "nan", "None"):
            return _normalizar_company(texto)
    return "Colombia"


def _agrupar_posicion_por_book(df_swap: pd.DataFrame) -> pd.DataFrame:
    """Agrupa la posicion USD por BOOK y conserva la compania asociada."""
    posicion = df_swap.groupby("BOOK", as_index=False)["POSICION_USD"].sum()
    company = df_swap.groupby("BOOK")["COMPANY"].agg(_company_por_book).reset_index()
    posicion = posicion.merge(company, on="BOOK", how="left")
    return posicion


def _calcular_cva_dva(
    posicion_ifrs: pd.DataFrame,
    posicion_banking: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula CVA/DVA como IFRS menos Banking por BOOK."""
    cva_dva = posicion_ifrs.merge(
        posicion_banking,
        on="BOOK",
        how="outer",
        suffixes=("_IFRS", "_BANKING"),
    )
    cva_dva["POSICION_USD_IFRS"] = cva_dva["POSICION_USD_IFRS"].fillna(0.0)
    cva_dva["POSICION_USD_BANKING"] = cva_dva["POSICION_USD_BANKING"].fillna(0.0)
    cva_dva["POSICION_USD"] = cva_dva["POSICION_USD_IFRS"] - cva_dva["POSICION_USD_BANKING"]
    cva_dva["COMPANY"] = cva_dva["COMPANY_IFRS"].combine_first(cva_dva["COMPANY_BANKING"]).fillna("Colombia")
    return cva_dva[["BOOK", "POSICION_USD", "COMPANY"]]


def _normalizar_etiqueta_posicion(valor: str) -> str:
    """Homologa etiquetas contables para construir las vistas finales de Swaps."""
    texto = str(valor).strip().upper().replace("-", " ").replace("/", " ").replace("__", "_")
    texto = " ".join(texto.split())
    return MAPA_ETIQUETAS_POSICION.get(texto, str(valor).strip() or "Banking")


def _normalizar_lb_lt_publicacion(valor: str) -> str:
    """Normaliza la agrupacion final a los dos flujos: Bancario y Trading."""
    texto = (
        str(valor)
        .strip()
        .upper()
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
    )
    return MAPA_LB_LT_PUBLICACION.get(texto, "Trading")


def _resumir_posicion_total(posicion_por_book: pd.DataFrame) -> pd.DataFrame:
    """Resume una vista de Swaps a una sola fila total para publicacion final."""
    company = "Colombia"
    if "COMPANY" in posicion_por_book.columns and not posicion_por_book.empty:
        company = _company_por_book(posicion_por_book["COMPANY"])

    return pd.DataFrame(
        {
            "BOOK": [BOOK_TOTAL_SWAPS],
            "POSICION_USD": [
                pd.to_numeric(posicion_por_book.get("POSICION_USD", pd.Series(dtype=float)), errors="coerce")
                .fillna(0.0)
                .sum()
            ],
            "COMPANY": [company],
        }
    )


def _construir_tabla_canonica(
    posicion_por_book: pd.DataFrame,
    fecha_corte: pd.Timestamp,
    etiqueta_banking_cva_dva: str,
    logger=None,
) -> pd.DataFrame:
    """Construye la tabla canonica de Position Monitor para Swaps por BOOK."""
    tabla_base = enriquecer_con_parametros_libros(
        posicion_por_book,
        producto="Swap",
        logger=logger,
        default_lb_lt=VALOR_LB_LT_NO_DEFINIDO,
        default_instrumento="Derivados",
        default_moneda_posicion="USD",
    )

    tabla = pd.DataFrame(
        {
            "FECHA": fecha_corte.strftime("%d/%m/%Y"),
            "PRODUCTO": "Swap",
            "BOOK": tabla_base["BOOK"].astype(str).str.strip(),
            "POSICION": pd.to_numeric(tabla_base["POSICION_USD"], errors="coerce").fillna(0.0),
            "MONEDA_POSICION": tabla_base["MONEDA_POSICION"].astype(str).str.strip(),
            "LB_LT": tabla_base["LB_LT"].astype(str).str.strip(),
            "INSTRUMENTO": tabla_base["INSTRUMENTO"].astype(str).str.strip(),
            "COMPANY": tabla_base["COMPANY"].apply(_normalizar_company),
            "CLASIFICACION_CONTABLE": "NA",
            "BANKING_CVA_DVA": etiqueta_banking_cva_dva,
        }
    )
    return tabla[COLUMNAS_POSICION]


def _resolver_fuente_detalle_swaps() -> Path:
    """Usa primero el historico detallado y, si no existe, recicla la tabla oficial actual."""
    if ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE.exists():
        return ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE
    if ARCHIVO_SALIDA_SWAPS_TABLA.exists():
        return ARCHIVO_SALIDA_SWAPS_TABLA
    return ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE


def _ordenar_tabla_swaps(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica un orden estable por fecha, vista contable y book."""
    if df.empty:
        return df.copy()

    tabla = df.copy()
    tabla["_FECHA_ORDEN"] = pd.to_datetime(tabla["FECHA"], dayfirst=True, errors="coerce")
    tabla["_VISTA_ORDEN"] = tabla["BANKING_CVA_DVA"].map(ORDEN_ETIQUETAS_SWAPS).fillna(len(ETIQUETAS_SWAPS))
    tabla["_LB_LT_ORDEN"] = tabla["LB_LT"].map(ORDEN_LB_LT_SWAPS).fillna(len(ORDEN_LB_LT_SWAPS))
    tabla = tabla.sort_values(
        by=["_FECHA_ORDEN", "_VISTA_ORDEN", "_LB_LT_ORDEN", "BOOK"],
        kind="stable",
    )
    return tabla.drop(columns=["_FECHA_ORDEN", "_VISTA_ORDEN", "_LB_LT_ORDEN"]).reset_index(drop=True)


def _consolidar_tabla_swaps_publicacion(tabla_detalle: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Normaliza el detalle historico y lo publica con tres books: CFH, FVH y Swaps."""
    if tabla_detalle.empty:
        return pd.DataFrame(columns=COLUMNAS_POSICION)

    tabla = tabla_detalle.copy()
    tabla.columns = [str(columna).strip() for columna in tabla.columns]
    tabla["FECHA"] = pd.to_datetime(tabla["FECHA"], dayfirst=True, errors="coerce").dt.strftime("%d/%m/%Y")
    tabla["BANKING_CVA_DVA"] = tabla["BANKING_CVA_DVA"].apply(_normalizar_etiqueta_posicion)
    tabla["POSICION"] = pd.to_numeric(tabla["POSICION"], errors="coerce").fillna(0.0)
    tabla["PRODUCTO"] = "Swap"
    tabla = enriquecer_con_parametros_libros(
        tabla,
        producto="Swap",
        logger=logger,
        default_lb_lt=VALOR_LB_LT_NO_DEFINIDO,
        default_instrumento="Derivados",
        default_moneda_posicion="USD",
    )
    tabla["COMPANY"] = (
        tabla.get("COMPANY", pd.Series(index=tabla.index, dtype=object))
        .fillna("Colombia")
        .apply(_normalizar_company)
    )
    tabla["CLASIFICACION_CONTABLE"] = (
        tabla.get("CLASIFICACION_CONTABLE", pd.Series(index=tabla.index, dtype=object))
        .fillna("NA")
        .astype(str)
        .str.strip()
        .replace({"": "NA", "nan": "NA", "None": "NA"})
    )
    tabla = tabla.loc[tabla["FECHA"].notna() & (tabla["FECHA"] != "NaT")].copy()

    # Todos los libros de Trading se agregan al book homologado "Swaps".
    # CFH y FVH (Bancario) se conservan con su nombre original.
    trading = tabla["LB_LT"].astype(str).str.strip().str.upper().isin(
        {"TRADING", "TESORERIA"}
    )
    tabla.loc[trading, "BOOK"] = BOOK_TRADING_PUBLICADO

    groupby_cols = [col for col in COLUMNAS_POSICION if col != "POSICION"]
    tabla = (
        tabla.groupby(groupby_cols, as_index=False, dropna=False)["POSICION"]
        .sum()
    )

    registrar_log(
        logger,
        f"Swaps publicacion: {tabla['BOOK'].nunique()} books tras colapso Trading -> Swaps "
        f"({sorted(tabla['BOOK'].unique().tolist())}).",
    )
    return _ordenar_tabla_swaps(tabla[COLUMNAS_POSICION])


def _guardar_detalle_swaps(
    df_banking: pd.DataFrame,
    df_ifrs: pd.DataFrame,
    posicion_banking: pd.DataFrame,
    posicion_ifrs: pd.DataFrame,
    posicion_cva_dva: pd.DataFrame,
    tabla_swaps_detalle: pd.DataFrame,
    tabla_swaps_publicada: pd.DataFrame,
) -> None:
    """Guarda un workbook de soporte con detalle depurado y agregados intermedios."""
    ARCHIVO_SALIDA_SWAPS_DETALLE.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(ARCHIVO_SALIDA_SWAPS_DETALLE, engine="openpyxl", mode="w") as writer:
        df_banking.to_excel(writer, sheet_name="Banking_Depurado", index=False)
        df_ifrs.to_excel(writer, sheet_name="IFRS_Depurado", index=False)
        posicion_banking.to_excel(writer, sheet_name="Posicion_Banking", index=False)
        posicion_ifrs.to_excel(writer, sheet_name="Posicion_IFRS", index=False)
        posicion_cva_dva.to_excel(writer, sheet_name="Posicion_CVA_DVA", index=False)
        tabla_swaps_detalle.to_excel(writer, sheet_name="Tabla_Canonica_Detalle", index=False)
        tabla_swaps_publicada.to_excel(writer, sheet_name="Tabla_Canonica_Total", index=False)


def _guardar_detalle_swaps_si_posible(
    df_banking: pd.DataFrame,
    df_ifrs: pd.DataFrame,
    posicion_banking: pd.DataFrame,
    posicion_ifrs: pd.DataFrame,
    posicion_cva_dva: pd.DataFrame,
    tabla_swaps_detalle: pd.DataFrame,
    tabla_swaps_publicada: pd.DataFrame,
    logger=None,
) -> None:
    """Guarda el workbook de soporte sin afectar la salida oficial si esta bloqueado."""
    try:
        _guardar_detalle_swaps(
            df_banking,
            df_ifrs,
            posicion_banking,
            posicion_ifrs,
            posicion_cva_dva,
            tabla_swaps_detalle,
            tabla_swaps_publicada,
        )
    except OSError as exc:
        registrar_log(
            logger,
            "No se pudo actualizar el workbook de soporte de Swaps. "
            f"La tabla oficial continua en memoria para consolidacion. Detalle: {exc}",
        )


def _guardar_csv_con_reintentos(
    df: pd.DataFrame,
    ruta: Path,
    logger=None,
    descripcion: str = "archivo CSV",
    reintentos: int = 5,
    espera_segundos: float = 1.0,
) -> None:
    """Guarda un CSV tolerando locks transitorios del recurso compartido."""
    ultimo_error: Exception | None = None

    for intento in range(1, reintentos + 1):
        try:
            df.to_csv(ruta, index=False, encoding="utf-8-sig")
            return
        except PermissionError as exc:
            ultimo_error = exc
            if intento == reintentos:
                break
            registrar_log(
                logger,
                f"No se pudo guardar {descripcion} en intento {intento}/{reintentos} por bloqueo temporal. "
                f"Se reintentara en {espera_segundos:.0f} segundo(s).",
            )
            time.sleep(espera_segundos)

    registrar_log(
        logger,
        f"No se pudo actualizar {descripcion} porque el CSV esta abierto o bloqueado. "
        "La ejecucion continuara; si aplica, la tabla oficial se actualizara en SQLite.",
    )
    return


def ejecutar_swaps(
    fecha_trabajo: str,
    logger=None,
    confirmar_reemplazo: bool = True,
) -> pd.DataFrame | None:
    """
    Ejecuta la posicion de Swaps para la fecha de corte seleccionada.

    Recibe:
    - fecha_trabajo: fecha seleccionada en interfaz
    - logger: callback opcional para registrar mensajes
    - confirmar_reemplazo: controla si se pregunta al usuario al reemplazar una fecha ya publicada

    Devuelve:
    - DataFrame con la salida oficial historica de Swaps por BOOK para Banking, IFRS y CVA/DVA
    - None si el usuario cancela el reemplazo de la fecha existente

    Reglas:
    - usa la fecha seleccionada como FECHA de salida
    - usa el reporte exacto del corte, incluso cuando la fecha es no habil
    - valida que la fecha interna del archivo coincida con la fuente usada
    """
    registrar_log(logger, "Inicia proceso Swaps.")
    registrar_log(logger, f"Fecha de trabajo Swaps: {fecha_trabajo}.")

    fecha_corte = _normalizar_fecha_trabajo(fecha_trabajo)
    fecha_fuente = _resolver_fecha_fuente(fecha_corte)

    rutas = _construir_rutas_swaps(fecha_fuente, logger=logger)
    ruta_banking = _validar_insumo_vector(rutas["banking_local"], "Banking", logger=logger)
    ruta_ifrs = _validar_insumo_vector(rutas["ifrs_local"], "IFRS", logger=logger)

    df_banking_crudo, fecha_archivo_banking = _leer_banking_swaps(ruta_banking)
    df_ifrs_crudo, fecha_archivo_ifrs = _leer_ifrs_swaps(ruta_ifrs)
    registrar_log(logger, f"Insumo Swaps Banking cargado: {df_banking_crudo.shape[0]} filas, {df_banking_crudo.shape[1]} columnas.")
    registrar_log(logger, f"Insumo Swaps IFRS cargado: {df_ifrs_crudo.shape[0]} filas, {df_ifrs_crudo.shape[1]} columnas.")

    _validar_fecha_valoracion_archivo(fecha_archivo_banking, fecha_fuente, "Banking", logger=logger)
    _validar_fecha_valoracion_archivo(fecha_archivo_ifrs, fecha_fuente, "IFRS", logger=logger)

    # Se conservan solo las columnas necesarias para la posicion y se limpian tipos.
    df_banking = _depurar_insumo_swaps(df_banking_crudo, fecha_archivo_banking)
    df_ifrs = _depurar_insumo_swaps(df_ifrs_crudo, fecha_archivo_ifrs)
    registrar_log(logger, "Depuracion de insumos Swaps completada.")

    # La fecha de valoracion para POSICION_USD siempre es la fecha de corte elegida en la interfaz.
    df_banking = _calcular_posicion_usd(df_banking, fecha_corte)
    df_ifrs = _calcular_posicion_usd(df_ifrs, fecha_corte)
    registrar_log(logger, "Calculo de POSICION_USD completado para Banking e IFRS.")

    # La salida operativa se agrupa por BOOK y luego se calcula CVA/DVA = IFRS - Banking.
    posicion_banking = _agrupar_posicion_por_book(df_banking)
    posicion_ifrs = _agrupar_posicion_por_book(df_ifrs)
    posicion_cva_dva = _calcular_cva_dva(posicion_ifrs, posicion_banking)
    registrar_log(logger, f"Posicion Banking agregada por BOOK: {len(posicion_banking)} filas.")
    registrar_log(logger, f"Posicion IFRS agregada por BOOK: {len(posicion_ifrs)} filas.")
    registrar_log(logger, f"Posicion CVA/DVA calculada por BOOK: {len(posicion_cva_dva)} filas.")

    tabla_banking = _construir_tabla_canonica(
        posicion_banking,
        fecha_corte,
        "Banking",
        logger=logger,
    )
    tabla_ifrs = _construir_tabla_canonica(
        posicion_ifrs,
        fecha_corte,
        "IFRS",
        logger=logger,
    )
    tabla_cva_dva = _construir_tabla_canonica(
        posicion_cva_dva,
        fecha_corte,
        "CVA/DVA",
        logger=logger,
    )
    tabla_swaps_detalle_fecha = pd.concat([tabla_banking, tabla_ifrs, tabla_cva_dva], ignore_index=True)
    tabla_swaps_detalle_fecha = _ordenar_tabla_swaps(tabla_swaps_detalle_fecha)

    # Se conserva el historico detallado por BOOK como soporte parametrizable.
    tabla_swaps_detalle = actualizar_datos_por_fecha(
        _resolver_fuente_detalle_swaps(),
        tabla_swaps_detalle_fecha,
        fecha_trabajo,
        "FECHA",
        "csv",
        confirmar_reemplazo=confirmar_reemplazo,
    )
    if tabla_swaps_detalle is None:
        registrar_log(logger, "Swaps cancelado por el usuario al detectar una fecha existente.")
        return None

    tabla_swaps_detalle = _ordenar_tabla_swaps(tabla_swaps_detalle)
    tabla_swaps = _consolidar_tabla_swaps_publicacion(tabla_swaps_detalle, logger=logger)

    ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE.parent.mkdir(parents=True, exist_ok=True)
    _guardar_csv_con_reintentos(
        tabla_swaps_detalle,
        ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE,
        logger=logger,
        descripcion="la tabla detalle de Swaps",
    )
    ARCHIVO_SALIDA_SWAPS_TABLA.parent.mkdir(parents=True, exist_ok=True)
    _guardar_csv_con_reintentos(
        tabla_swaps,
        ARCHIVO_SALIDA_SWAPS_TABLA,
        logger=logger,
        descripcion="la tabla oficial de Swaps",
    )
    _guardar_detalle_swaps_si_posible(
        df_banking,
        df_ifrs,
        posicion_banking,
        posicion_ifrs,
        posicion_cva_dva,
        tabla_swaps_detalle,
        tabla_swaps,
        logger=logger,
    )

    registrar_log(logger, f"Tabla Swaps detalle guardada en: {ARCHIVO_SALIDA_SWAPS_TABLA_DETALLE}")
    registrar_log(logger, f"Tabla Swaps guardada en: {ARCHIVO_SALIDA_SWAPS_TABLA}")
    registrar_log(logger, f"Detalle depurado Swaps guardado en: {ARCHIVO_SALIDA_SWAPS_DETALLE}")
    registrar_log(logger, "Swaps publicado por BOOK con LB_LT parametrico para Banking, IFRS y CVA/DVA.")
    registrar_log(logger, "Proceso Swaps finalizado correctamente.")

    # ADICION AUXILIAR: copia todas las hojas y tablas calculadas a la base separada.
    # Las salidas CSV/Excel y su lógica de reintentos no se modifican.
    guardar_tablas_auxiliares_modulo(
        "Swaps",
        fecha_corte,
        {
            "banking_depurado": df_banking,
            "ifrs_depurado": df_ifrs,
            "posicion_banking": posicion_banking,
            "posicion_ifrs": posicion_ifrs,
            "posicion_cva_dva": posicion_cva_dva,
            "posicion_detalle": tabla_swaps_detalle,
            "posicion_publicada": tabla_swaps,
        },
        logger=logger,
    )
    return tabla_swaps
