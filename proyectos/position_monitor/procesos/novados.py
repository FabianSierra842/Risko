from __future__ import annotations

from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from compartido.nucleo_risko.archivos import (
    actualizar_datos_por_fecha,
    guardar_csv_si_posible,
    leer_csv,
    registrar_log,
)
from compartido.nucleo_risko.tablas_auxiliares import guardar_tablas_auxiliares_modulo
from compartido.nucleo_risko.rutas import (
    ARCHIVO_INSUMO_NOVADOS_DEPURADO,
    ARCHIVO_PARAM_RUTAS,
    ARCHIVO_SALIDA_NOVADOS,
    ARCHIVO_SALIDA_NOVADOS_LEGACY,
)
from proyectos.position_monitor.procesos.parametros_libros import (
    VALOR_LB_LT_NO_DEFINIDO,
    enriquecer_con_parametros_libros,
)


# Estructura esperada por la salida consolidable de Position Monitor.
# Mantener este orden evita diferencias al anexar o reemplazar datos por fecha.
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


def _cargar_parametros_rutas() -> pd.DataFrame:
    """Carga el catalogo de rutas usado para localizar insumos de Novados."""
    return leer_csv(ARCHIVO_PARAM_RUTAS, sep=",", encoding="latin-1")


def _fila_parametro(df_parametros: pd.DataFrame, detalle: str) -> pd.Series:
    """Obtiene la fila de configuracion asociada a un detalle de param_rutas.csv."""
    fila = df_parametros.loc[df_parametros["Detalle"].astype(str).str.strip() == detalle]
    if fila.empty:
        raise ValueError(f"No se encontro la configuracion {detalle} en param_rutas.csv")
    return fila.iloc[0]


def _ruta_desde_parametro(fila: pd.Series, sufijo: str) -> Path:
    """Construye la ruta final del archivo a partir de Ruta, Nombre_Archivo y sufijo."""
    ruta_base = str(fila["Ruta"]).strip()
    nombre_archivo = str(fila["Nombre_Archivo"]).strip()
    return Path(f"{ruta_base}{nombre_archivo}{sufijo}")


def _resolver_fuente_tabla_novados() -> Path:
    """Selecciona la tabla existente que se usara como base para actualizar la fecha."""
    if ARCHIVO_SALIDA_NOVADOS.exists():
        return ARCHIVO_SALIDA_NOVADOS
    if ARCHIVO_SALIDA_NOVADOS_LEGACY.exists():
        return ARCHIVO_SALIDA_NOVADOS_LEGACY
    return ARCHIVO_SALIDA_NOVADOS


def _migrar_salida_novados_legada(logger=None) -> None:
    """Copia la salida legada al nombre actual cuando aun no existe la salida nueva."""
    if ARCHIVO_SALIDA_NOVADOS.exists() or not ARCHIVO_SALIDA_NOVADOS_LEGACY.exists():
        return

    ARCHIVO_SALIDA_NOVADOS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ARCHIVO_SALIDA_NOVADOS_LEGACY, ARCHIVO_SALIDA_NOVADOS)
    registrar_log(
        logger,
        "Se migro la salida consolidable legada de Novados a "
        f"{ARCHIVO_SALIDA_NOVADOS.name}.",
    )


def _cargar_insumo_novados(fecha_trabajo: str, logger=None) -> pd.DataFrame:
    """Carga el archivo diario de Novados que Vector dejo en datos/insumos."""
    fecha_trabajo = fecha_trabajo.strip()
    df_parametros = _cargar_parametros_rutas()

    fila_local = _fila_parametro(df_parametros, "Novados_Local")

    # Los archivos de Novados usan sufijo ddmmaa_000.xls aunque se leen como texto CSV.
    dia, mes, anio = fecha_trabajo.split("-")
    sufijo = f"{dia}{mes}{anio[-2:]}_000.xls"

    ruta_local = _ruta_desde_parametro(fila_local, sufijo)

    registrar_log(logger, f"Insumo Novados esperado por Vector: {ruta_local}")

    if not ruta_local.exists():
        raise FileNotFoundError(
            "Vector no dejo el insumo de Novados para la fecha seleccionada: "
            f"{ruta_local}"
        )

    # El proveedor entrega un archivo separado por punto y coma con dos filas de cabecera.
    df_insumo = pd.read_csv(
        ruta_local,
        sep=";",
        skiprows=2,
        encoding="latin1",
        engine="python",
    )
    registrar_log(
        logger,
        f"Insumo Novados cargado: {df_insumo.shape[0]} filas, {df_insumo.shape[1]} columnas.",
    )
    return df_insumo


def _depurar_novados(
    df_insumo: pd.DataFrame,
    fecha_trabajo: str,
    logger=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Depura el insumo y genera la posicion agregada por book."""
    df_insumo = df_insumo.copy()
    df_insumo.columns = df_insumo.columns.str.strip()

    # Se eliminan columnas operativas que no alimentan la salida consolidable.
    columnas_descartar = [
        "EXTERNAL ID",
        "TRADE ID OTC",
        "CLIENTE OTC",
        "ID CONTRATO",
        "No. CONTRATOS",
        "PRECIO PACTADO",
        "TRADER",
        "VALOR PACTADO",
        "VALOR MERCADO",
        "PRECIO MERCADO (Y)",
        "MTM TOTAL PESOS",
        "PRECIO MERCADO (Y-1)",
        "MTM DIA PESOS",
        "FOLDER",
        "COMPANY",
        "Delta Full Valuation   1 USD",
        "VLR SENSIBLE -   NOMINAL",
        "VLR SENSIBLE -   NOMINAL USD",
        "COMPONENTE CAMBIARIO",
        "ACUM. COMPONENTE   CAMBIARIO",
        "COMP. CAMBIARIO   CIERRE AÑO ANTERIOR",
        "VLR. COMP. CAMBIARIO   AÑO FISCAL",
    ]
    df_insumo = df_insumo.drop(columns=columnas_descartar, errors="ignore")

    # Normaliza nombres para que el resto del flujo no dependa de espacios o tildes.
    df_insumo = df_insumo.rename(
        columns={
            "TRADE ID": "TRADE_ID",
            "FECHA NEGOCIACION": "FECHA_NEGOCIACION",
            "PAR MONEDAS": "PAR_MONEDAS",
            "COMPRA/VENTA": "COMPRA_VENTA",
            "VENCIMIENTO": "VENCIMIENTO",
            "NOMINAL": "NOMINAL",
            "DESK": "DESK",
            "VALOR SENSIBLE": "VALOR_SENSIBLE",
        }
    )

    fecha_corte = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_corte):
        raise ValueError(f"Fecha no valida para Novados: {fecha_trabajo}")

    # Convierte vencimiento y valor sensible a tipos calculables.
    df_insumo["VENCIMIENTO"] = pd.to_datetime(
        df_insumo["VENCIMIENTO"].astype(str).str.strip(),
        format="%d/%m/%y",
        errors="coerce",
    ).dt.date
    df_insumo["VALOR_SENSIBLE"] = pd.to_numeric(
        df_insumo["VALOR_SENSIBLE"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    # Las operaciones que vencen en la fecha de corte no aportan posicion remanente.
    df_insumo["POSICION"] = np.where(
        df_insumo["VENCIMIENTO"] == fecha_corte.date(),
        0,
        df_insumo["VALOR_SENSIBLE"],
    )
    df_insumo["CORTE"] = fecha_corte.date()

    # Resume la posicion por book y la lleva al formato comun de Position Monitor.
    tabla_posicion = df_insumo.groupby(["BOOK"], as_index=False)["POSICION"].sum()
    tabla_posicion["FECHA"] = fecha_corte.strftime("%d/%m/%Y")
    tabla_posicion["PRODUCTO"] = "Novados"
    tabla_posicion = enriquecer_con_parametros_libros(
        tabla_posicion,
        producto="Novados",
        logger=logger,
        default_lb_lt=VALOR_LB_LT_NO_DEFINIDO,
        default_instrumento="Derivados",
        default_moneda_posicion="USD",
    )
    tabla_posicion["COMPANY"] = "Colombia"
    tabla_posicion["CLASIFICACION_CONTABLE"] = "NA"
    tabla_posicion["BANKING_CVA_DVA"] = "Banking"

    tabla_posicion = tabla_posicion[COLUMNAS_POSICION]
    return df_insumo, tabla_posicion


def ejecutar_novados(
    fecha_trabajo: str,
    logger=None,
    confirmar_reemplazo: bool = True,
) -> pd.DataFrame | None:
    """Ejecuta el proceso completo de Novados para una fecha de trabajo."""
    registrar_log(logger, "Inicia proceso Novados.")
    registrar_log(logger, f"Fecha de trabajo Novados: {fecha_trabajo}.")

    # Asegura continuidad con salidas historicas antes de recalcular la fecha.
    _migrar_salida_novados_legada(logger=logger)
    df_insumo = _cargar_insumo_novados(fecha_trabajo, logger=logger)
    df_insumo, tabla_posicion = _depurar_novados(
        df_insumo,
        fecha_trabajo,
        logger=logger,
    )

    # Reemplaza o anexa la fecha procesada en la tabla acumulada.
    tabla_posicion = actualizar_datos_por_fecha(
        _resolver_fuente_tabla_novados(),
        tabla_posicion,
        fecha_trabajo,
        "FECHA",
        "csv",
        confirmar_reemplazo=confirmar_reemplazo,
    )
    if tabla_posicion is None:
        registrar_log(logger, "Novados cancelado por el usuario al detectar una fecha existente.")
        return None

    # Guarda tanto el detalle depurado como la salida consolidable final.
    ARCHIVO_INSUMO_NOVADOS_DEPURADO.parent.mkdir(parents=True, exist_ok=True)
    df_insumo.to_excel(ARCHIVO_INSUMO_NOVADOS_DEPURADO, index=False)

    guardar_csv_si_posible(tabla_posicion, ARCHIVO_SALIDA_NOVADOS, logger=logger)
    
    registrar_log(logger, f"Detalle Novados guardado en: {ARCHIVO_INSUMO_NOVADOS_DEPURADO}")
    registrar_log(logger, f"Tabla Novados guardada en: {ARCHIVO_SALIDA_NOVADOS}")

    # ADICION AUXILIAR: replica las tablas calculadas sin cambiar el Excel ni el CSV vigentes.
    guardar_tablas_auxiliares_modulo(
        "Novados",
        fecha_trabajo,
        {
            "insumo_depurado": df_insumo,
            "posicion": tabla_posicion,
        },
        logger=logger,
    )
    return tabla_posicion
