from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import sys
import uuid
import unicodedata

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from scipy.stats import norm


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from compartido.nucleo_risko.archivos import actualizar_datos_por_fecha, guardar_csv_si_posible, registrar_log
from compartido.nucleo_risko.fechas import Es_Dia_Habil
from compartido.nucleo_risko.tablas_auxiliares import guardar_tablas_auxiliares_modulo
from compartido.nucleo_risko.rutas import (
    ARCHIVO_INSUMO_OPCIONES_DEPURADO,
    ARCHIVO_LOCAL_INSUMO_TASAS,
    ARCHIVO_LOCAL_OPCIONES_MERCADO,
    ARCHIVO_SALIDA_OPCIONES_TABLA,
    CARPETA_INSUMOS_POSITION_MONITOR,
)
from compartido.nucleo_risko.trm import obtener_trm_formada
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

DELTA_NODOS = np.array([0.10, 0.25, 0.50, 0.75, 0.90], dtype=float)
COLUMNAS_FECHA_OPCIONES = [
    "FECHA_DE_EMISION",
    "FECHA_DE_VENCIMIENTO",
    "FECHA_DE_CUMPLIMIENTO",
    "FECHA_PRIMA",
    "FECHA_FEE",
]
COLUMNAS_NUMERICAS_OPCIONES = [
    "NOMINAL",
    "PRECIO_DE_EJERCICIO",
    "VOLATILIDAD",
    "DELTA",
    "VALUE_AMOUNT",
    "VALUE_AMOUNT_EXERCISED_SETT_CCY",
    "VALUE_AMOUNT_EXERCISED_COP",
    "MONTO_EJERCICIO",
    "VP_SETT_CCY_Y_CVA",
]


@dataclass(frozen=True)
class MercadoOpciones:
    trm: float
    curva_usd: pd.DataFrame
    curva_cop: pd.DataFrame
    superficie_vol: pd.DataFrame


def _normalizar_nombre_columna(nombre: object) -> str:
    texto = unicodedata.normalize("NFKD", str(nombre).strip())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.upper()
    texto = texto.replace("&", " ")
    texto = "".join(caracter if caracter.isalnum() else "_" for caracter in texto)
    while "__" in texto:
        texto = texto.replace("__", "_")
    return texto.strip("_")


def _normalizar_texto(valor: object) -> str:
    return str(valor).strip().replace("nan", "").replace("None", "")


def _serie_numerica(serie: pd.Series) -> pd.Series:
    texto = (
        serie.where(serie.notna(), "")
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("\xa0", "", regex=False)
        .str.strip()
    )
    return pd.to_numeric(texto, errors="coerce")


def _fecha_trabajo_a_timestamp(fecha_trabajo: str) -> pd.Timestamp:
    fecha_valor = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_valor):
        raise ValueError(f"Fecha no valida para Opciones: {fecha_trabajo}")
    return fecha_valor.normalize()


def _ruta_local_opciones_manana(fecha_valor: pd.Timestamp) -> Path:
    sufijo = fecha_valor.strftime("%d%m%y")
    return CARPETA_INSUMOS_POSITION_MONITOR / f"USR_OPT_MANANA_{sufijo}_000.xls"


def _siguiente_dia_habil(fecha_valor: pd.Timestamp) -> pd.Timestamp:
    fecha_archivo = fecha_valor + pd.Timedelta(days=1)
    while not Es_Dia_Habil(fecha_archivo.date()):
        fecha_archivo += pd.Timedelta(days=1)
    return fecha_archivo


def _validar_insumo_vector(ruta_local: Path, nombre: str, logger=None) -> Path:
    registrar_log(logger, f"Insumo Opciones esperado por Vector [{nombre}]: {ruta_local}")
    if not ruta_local.exists():
        raise FileNotFoundError(
            "Vector no dejo el insumo de Opciones requerido "
            f"[{nombre}] para la fecha seleccionada: {ruta_local}"
        )
    return ruta_local


def _validar_insumos_locales(fecha_valor: pd.Timestamp, logger=None) -> dict[str, Path]:
    fecha_archivo = _siguiente_dia_habil(fecha_valor)
    ruta_opciones_manana = _ruta_local_opciones_manana(fecha_archivo)
    registrar_log(
        logger,
        "Opciones usa archivos del siguiente dia habil: "
        f"corte {fecha_valor.strftime('%d/%m/%Y')} -> archivo {fecha_archivo.strftime('%d/%m/%Y')}.",
    )
    rutas = {
        "opciones_manana": _validar_insumo_vector(
            ruta_opciones_manana,
            "USR_OPT_MANANA",
            logger=logger,
        ),
        "entrada2_mercado": _validar_insumo_vector(
            ARCHIVO_LOCAL_OPCIONES_MERCADO,
            "ENTRADA2",
            logger=logger,
        ),
        "historico_trm": _validar_insumo_vector(
            ARCHIVO_LOCAL_INSUMO_TASAS,
            "Historico TRM",
            logger=logger,
        ),
    }

    for nombre, ruta in rutas.items():
        registrar_log(logger, f"Insumo Opciones validado en ruta local [{nombre}]: {ruta}")
    return rutas


def _leer_reporte_opciones(ruta_archivo: Path) -> pd.DataFrame:
    bruto = pd.read_csv(
        ruta_archivo,
        sep="\t",
        engine="python",
        encoding="latin-1",
    )
    columna_texto = bruto.columns[0]
    detalle = bruto[columna_texto].astype(str).str.split(";", expand=True)
    detalle = detalle.drop(index=[0, 1, 2]).reset_index(drop=True)

    encabezados = [_normalizar_nombre_columna(valor) for valor in detalle.loc[0].tolist()]
    detalle = detalle.iloc[1:].reset_index(drop=True)
    detalle.columns = encabezados
    detalle = detalle.loc[:, [columna for columna in detalle.columns if columna]]
    detalle = detalle.loc[:, ~detalle.columns.duplicated(keep="last")]

    for columna in COLUMNAS_FECHA_OPCIONES:
        if columna in detalle.columns:
            detalle[columna] = pd.to_datetime(detalle[columna], dayfirst=True, errors="coerce")

    for columna in COLUMNAS_NUMERICAS_OPCIONES:
        if columna in detalle.columns:
            detalle[columna] = _serie_numerica(detalle[columna])

    columnas_texto = [
        "TRADE_ID",
        "BOOK",
        "IDENTIFICACION_CONTRAPARTE",
        "DETALLE_DE_LA_CONTRAPARTE",
        "POSICION_EN_LA_OPCION",
        "TIPO_DE_OPCION",
        "MONEDA_DE_LA_PRIMA",
        "MONEDA_CUMPLIMIENTO",
        "MODALIDAD_CUMPLIMIENTO",
        "OFICINA_CEO",
    ]
    for columna in columnas_texto:
        if columna in detalle.columns:
            detalle[columna] = detalle[columna].fillna("").astype(str).str.strip()

    return detalle


def _leer_reporte_opciones_fwd_referencia(ruta_archivo: Path) -> pd.DataFrame:
    bruto = pd.read_csv(
        ruta_archivo,
        sep="\t",
        engine="python",
        encoding="latin-1",
    )
    columna_texto = bruto.columns[0]
    detalle = bruto[columna_texto].astype(str).str.split(";", expand=True)
    encabezados = [_normalizar_nombre_columna(valor) for valor in detalle.loc[4].tolist()]
    detalle = detalle.iloc[5:].reset_index(drop=True)
    detalle.columns = encabezados
    detalle = detalle.loc[:, [columna for columna in detalle.columns if columna]]
    detalle = detalle.loc[:, ~detalle.columns.duplicated(keep="last")]
    return detalle


def _construir_curva_desde_xlsb(
    ruta_archivo: Path,
    usecols: str,
    nrows: int,
    columna_tasa: str,
) -> pd.DataFrame:
    curva = pd.read_excel(
        ruta_archivo,
        engine="pyxlsb",
        sheet_name="INFOVALMER",
        skiprows=2,
        nrows=nrows,
        usecols=usecols,
        header=None,
    )
    curva = curva.iloc[1:].reset_index(drop=True)
    curva.columns = ["PLAZO_TEXTO", "PLAZO_INFERIOR", columna_tasa]
    curva["PLAZO_INFERIOR"] = _serie_numerica(curva["PLAZO_INFERIOR"])
    curva[columna_tasa] = _serie_numerica(curva[columna_tasa])
    curva["PLAZO_SUPERIOR"] = curva["PLAZO_INFERIOR"].shift(-1).fillna(curva["PLAZO_INFERIOR"])
    return curva[["PLAZO_INFERIOR", "PLAZO_SUPERIOR", columna_tasa]]


def _construir_superficie_volatilidad(ruta_archivo: Path) -> pd.DataFrame:
    superficie = pd.read_excel(
        ruta_archivo,
        engine="pyxlsb",
        sheet_name="INFOVALMER",
        skiprows=2,
        nrows=18,
        usecols="I:N",
        header=None,
    )
    superficie = superficie.iloc[1:].reset_index(drop=True)
    superficie.columns = [
        "PLAZO_INFERIOR",
        "VOL_10D_PUT",
        "VOL_25D_PUT",
        "VOL_ATM",
        "VOL_25D_CALL",
        "VOL_10D_CALL",
    ]
    for columna in superficie.columns:
        superficie[columna] = _serie_numerica(superficie[columna])
    superficie["PLAZO_SUPERIOR"] = superficie["PLAZO_INFERIOR"].shift(-1).fillna(superficie["PLAZO_INFERIOR"])
    return superficie[
        [
            "PLAZO_INFERIOR",
            "PLAZO_SUPERIOR",
            "VOL_10D_PUT",
            "VOL_25D_PUT",
            "VOL_ATM",
            "VOL_25D_CALL",
            "VOL_10D_CALL",
        ]
    ]


def _cargar_mercado_opciones(
    ruta_entrada2: Path,
    ruta_historico_trm: Path,
    fecha_corte: pd.Timestamp,
    logger=None,
) -> MercadoOpciones:
    return MercadoOpciones(
        trm=obtener_trm_formada(fecha_corte, ruta_historico_trm, logger=logger),
        curva_usd=_construir_curva_desde_xlsb(ruta_entrada2, "A:C", 18, "TASA_USD"),
        curva_cop=_construir_curva_desde_xlsb(ruta_entrada2, "E:G", 13, "TASA_COP"),
        superficie_vol=_construir_superficie_volatilidad(ruta_entrada2),
    )


def _fila_rango_por_plazo(plazo: float, tabla: pd.DataFrame) -> pd.Series:
    if tabla.empty:
        raise ValueError("La tabla de mercado requerida esta vacia.")

    if plazo <= tabla.iloc[0]["PLAZO_INFERIOR"]:
        return tabla.iloc[0]

    mascara = tabla["PLAZO_INFERIOR"] <= plazo
    if not mascara.any():
        return tabla.iloc[0]

    indice = mascara[mascara].index[-1]
    return tabla.loc[indice]


def _interpolar_desde_rango(
    plazo: float,
    plazo_inferior: float,
    plazo_superior: float,
    tasa_inferior: float,
    tasa_superior: float,
) -> float:
    if pd.isna(plazo_inferior) or pd.isna(plazo_superior):
        return 0.0
    if plazo_superior == plazo_inferior:
        return float(tasa_inferior)
    proporcion_inferior = 1 - ((plazo - plazo_inferior) / (plazo_superior - plazo_inferior))
    return float((proporcion_inferior * tasa_inferior) + ((1 - proporcion_inferior) * tasa_superior))


def _interpolar_tasa_plazo(plazo: float, tabla: pd.DataFrame, columna_tasa: str) -> float:
    if plazo <= 0:
        return 0.0

    fila = _fila_rango_por_plazo(plazo, tabla)
    plazo_inferior = float(fila["PLAZO_INFERIOR"])
    plazo_superior = float(fila["PLAZO_SUPERIOR"])
    tasa_inferior = float(fila[columna_tasa])

    if plazo_superior == plazo_inferior:
        return tasa_inferior

    fila_superior = tabla.loc[tabla["PLAZO_INFERIOR"] == plazo_superior]
    if fila_superior.empty:
        tasa_superior = tasa_inferior
    else:
        tasa_superior = float(fila_superior.iloc[0][columna_tasa])

    return _interpolar_desde_rango(
        plazo,
        plazo_inferior,
        plazo_superior,
        tasa_inferior,
        tasa_superior,
    )


def _interpolar_spline(delta_objetivo: float, nodos_volatilidad: np.ndarray) -> float:
    delta_ajustado = float(np.clip(delta_objetivo, DELTA_NODOS[0], DELTA_NODOS[-1]))
    spline = CubicSpline(DELTA_NODOS, nodos_volatilidad, bc_type="natural", extrapolate=True)
    return float(spline(delta_ajustado))


def _volatilidad_cubic(
    spot: float,
    strike: float,
    plazo: int,
    tasa_cop: float,
    tasa_usd: float,
    delta_atm: float,
    vol_10put: float,
    vol_25put: float,
    vol_atm: float,
    vol_25call: float,
    vol_10call: float,
    tipo_opcion: str,
    factor_descuento: float,
    error: float = 0.0,
    iteraciones_maximas: int = 100,
) -> float:
    if plazo <= 0:
        return 0.0

    ajuste = float(factor_descuento) if factor_descuento not in (0, None) and not pd.isna(factor_descuento) else 1.0
    sigma_anterior = 0.0
    sigma_actual = float(delta_atm)
    tipo_opcion = _normalizar_texto(tipo_opcion).upper()
    signo = 1 if tipo_opcion == "CALL" else -1

    smile_put = np.array([vol_10put, vol_25put, vol_atm, vol_25call, vol_10call], dtype=float)
    smile_call = smile_put[::-1]
    delta_iteracion = 0.50

    for _ in range(iteraciones_maximas):
        if sigma_actual <= 0:
            return 0.0

        d1 = (
            np.log(spot / strike)
            + ((tasa_cop - tasa_usd + (sigma_actual**2) * 0.5) * plazo / 365)
        ) / (sigma_actual * np.sqrt(plazo / 365))

        ajuste_fix = 0 if signo == 1 else -1
        delta_iteracion = (norm.cdf(d1) + ajuste_fix) / ajuste
        sigma_anterior = sigma_actual

        if tipo_opcion == "PUT":
            sigma_actual = _interpolar_spline(abs(delta_iteracion), smile_put)
        else:
            sigma_actual = _interpolar_spline(delta_iteracion, smile_call)

        if abs(sigma_anterior - sigma_actual) <= error:
            break

    if tipo_opcion == "PUT":
        if abs(delta_iteracion) <= DELTA_NODOS[0]:
            return float(smile_put[0])
        if abs(delta_iteracion) >= DELTA_NODOS[-1]:
            return float(smile_put[-1])
    else:
        if delta_iteracion <= DELTA_NODOS[0]:
            return float(smile_call[0])
        if delta_iteracion >= DELTA_NODOS[-1]:
            return float(smile_call[-1])

    return float(sigma_actual)


def _delta_opcion(
    fecha_corte: pd.Timestamp,
    fecha_vencimiento: pd.Timestamp,
    spot: float,
    strike: float,
    tasa_cop: float,
    tasa_usd: float,
    sigma: float,
    tipo_opcion: str,
) -> float:
    if pd.isna(fecha_vencimiento) or sigma <= 0:
        return 0.0

    tiempo = (fecha_vencimiento - fecha_corte).days / 365.0
    if tiempo <= 0:
        return 0.0

    tipo_normalizado = _normalizar_texto(tipo_opcion).upper()
    signo = 1 if tipo_normalizado == "CALL" else -1
    d1 = (
        np.log(spot / strike)
        + ((tasa_cop - tasa_usd + (sigma**2) * 0.5) * tiempo)
    ) / (sigma * np.sqrt(tiempo))
    ajuste_fix = 0 if signo == 1 else -1
    return float(np.exp(-tasa_usd * tiempo) * (norm.cdf(d1) + ajuste_fix))


def _signo_posicion(posicion_en_opcion: str) -> int:
    return -1 if _normalizar_texto(posicion_en_opcion).upper() == "SELL" else 1


_BUMP_TASA = 0.0025  # 0.25% para escenarios de sensibilidad spot


def _valor_opcion_escenario(
    spot: float,
    strike: float,
    plazo: int,
    tasa_usd: float,
    tasa_cop: float,
    sigma: float,
    tipo: str,
) -> float:
    """Valor de revaloracion de una opcion FX en un escenario de spot, en COP por USD nominal."""
    if plazo <= 0 or sigma <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    T = plazo / 365.0
    d1 = (np.log(spot / strike) + (tasa_cop - tasa_usd + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    tipo_n = _normalizar_texto(tipo).upper()
    if tipo_n == "CALL":
        return spot * np.exp(-tasa_usd * T) * norm.cdf(d1) - strike * np.exp(-tasa_cop * T) * norm.cdf(d2)
    return strike * np.exp(-tasa_cop * T) * norm.cdf(-d2) - spot * np.exp(-tasa_usd * T) * norm.cdf(-d1)


def _calcular_sensibilidad_spot_opcion(
    spot_base: float,
    strike: float,
    plazo: int,
    tasa_cop: float,
    tasa_usd: float,
    vol_10put: float,
    vol_25put: float,
    vol_atm: float,
    vol_25call: float,
    vol_10call: float,
    tipo_opcion: str,
    factor_descuento: float,
    posicion_en_opcion: str,
    nominal: float,
) -> dict[str, float]:
    """Calcula sensibilidad dV_COP/dSpot por diferencias centradas."""
    if plazo <= 0 or nominal == 0 or spot_base <= 0:
        return {
            "SPOT_UP": 0.0,
            "SPOT_DOWN": 0.0,
            "VOLATILIDAD_UP": 0.0,
            "VOLATILIDAD_DOWN": 0.0,
            "VALOR_ESCENARIO_UP_COP": 0.0,
            "VALOR_ESCENARIO_DOWN_COP": 0.0,
            "POSICION_SENSIBILIDAD_USD": 0.0,
        }

    spot_up = spot_base * (1 + _BUMP_TASA)
    spot_down = spot_base * (1 - _BUMP_TASA)
    d_spot = spot_up - spot_down
    fd = factor_descuento if factor_descuento > 0 else 1.0
    signo_pos = _signo_posicion(posicion_en_opcion)

    volatilidad_up = _volatilidad_cubic(
        spot=spot_up,
        strike=strike,
        plazo=plazo,
        tasa_cop=tasa_cop,
        tasa_usd=tasa_usd,
        delta_atm=vol_atm,
        vol_10put=vol_10put,
        vol_25put=vol_25put,
        vol_atm=vol_atm,
        vol_25call=vol_25call,
        vol_10call=vol_10call,
        tipo_opcion=tipo_opcion,
        factor_descuento=fd,
    )
    volatilidad_down = _volatilidad_cubic(
        spot=spot_down,
        strike=strike,
        plazo=plazo,
        tasa_cop=tasa_cop,
        tasa_usd=tasa_usd,
        delta_atm=vol_atm,
        vol_10put=vol_10put,
        vol_25put=vol_25put,
        vol_atm=vol_atm,
        vol_25call=vol_25call,
        vol_10call=vol_10call,
        tipo_opcion=tipo_opcion,
        factor_descuento=fd,
    )
    valor_up = _valor_opcion_escenario(
        spot_up,
        strike,
        plazo,
        tasa_usd,
        tasa_cop,
        volatilidad_up,
        tipo_opcion,
    )
    valor_down = _valor_opcion_escenario(
        spot_down,
        strike,
        plazo,
        tasa_usd,
        tasa_cop,
        volatilidad_down,
        tipo_opcion,
    )
    valor_up_cop = signo_pos * (valor_up / fd) * nominal
    valor_down_cop = signo_pos * (valor_down / fd) * nominal
    sensibilidad = (valor_up_cop - valor_down_cop) / d_spot if d_spot != 0 else 0.0
    return {
        "SPOT_UP": spot_up,
        "SPOT_DOWN": spot_down,
        "VOLATILIDAD_UP": volatilidad_up,
        "VOLATILIDAD_DOWN": volatilidad_down,
        "VALOR_ESCENARIO_UP_COP": valor_up_cop,
        "VALOR_ESCENARIO_DOWN_COP": valor_down_cop,
        "POSICION_SENSIBILIDAD_USD": sensibilidad,
    }


def _resolver_moneda_cumplimiento_regla(df_opciones: pd.DataFrame) -> pd.Series:
    moneda_fuente = df_opciones["MONEDA_CUMPLIMIENTO"].fillna("").astype(str).str.strip()
    moneda_prima = df_opciones["MONEDA_DE_LA_PRIMA"].fillna("").astype(str).str.strip()
    moneda_prefijo = np.where(
        df_opciones["IDENTIFICACION_CONTRAPARTE"].fillna("").astype(str).str[:4] == "4444",
        "USD",
        "COP",
    )
    moneda_prefijo = pd.Series(moneda_prefijo, index=df_opciones.index, dtype="object")
    return moneda_fuente.where(moneda_fuente.ne(""), moneda_prima.where(moneda_prima.ne(""), moneda_prefijo))


def _valor_liquidacion_reporte(df_opciones: pd.DataFrame) -> pd.Series:
    if "VALUE_AMOUNT_EXERCISED_SETT_CCY" in df_opciones.columns:
        return df_opciones["VALUE_AMOUNT_EXERCISED_SETT_CCY"].fillna(0.0)
    if "VP_SETT_CCY_Y_CVA" in df_opciones.columns:
        return df_opciones["VP_SETT_CCY_Y_CVA"].fillna(0.0)
    if "MONTO_EJERCICIO" in df_opciones.columns:
        return df_opciones["MONTO_EJERCICIO"].fillna(0.0)
    return pd.Series(0.0, index=df_opciones.index, dtype="float64")


def _calcular_detalle_opciones(
    df_opciones: pd.DataFrame,
    fecha_corte: pd.Timestamp,
    mercado: MercadoOpciones,
) -> pd.DataFrame:
    detalle = df_opciones.copy()
    detalle["FECHA_CORTE"] = fecha_corte
    detalle["MONEDA_CUMPLIMIENTO_REGLA"] = _resolver_moneda_cumplimiento_regla(detalle)
    detalle["VALOR_LIQUIDACION_REPORTE"] = _valor_liquidacion_reporte(detalle)

    detalle["PLAZO"] = (detalle["FECHA_DE_VENCIMIENTO"] - fecha_corte).dt.days.fillna(0).astype(int)
    dias_entre_vencimiento_y_cumplimiento = (
        detalle["FECHA_DE_CUMPLIMIENTO"] - detalle["FECHA_DE_VENCIMIENTO"]
    ).dt.days.fillna(0).astype(int)
    detalle["PLAZO_CUMPLIMIENTO"] = detalle["PLAZO"] + dias_entre_vencimiento_y_cumplimiento

    columnas_mercado = {
        "TASA_COP": [],
        "TASA_USD": [],
        "DIAS_INF_USD": [],
        "DIAS_SUP_USD": [],
        "TASA_INF_USD": [],
        "TASA_SUP_USD": [],
        "TASA_VAL_USD_CUMP": [],
        "FACTOR_DE_DESCUENTO": [],
        "DIAS_INF_SUPERFICIE": [],
        "DIAS_SUP_SUPERFICIE": [],
        "VOL_10D_PUT": [],
        "VOL_25D_PUT": [],
        "VOL_ATM": [],
        "VOL_25D_CALL": [],
        "VOL_10D_CALL": [],
        "VOLATILIDAD_CUBICA": [],
        "SPOT_UP": [],
        "SPOT_DOWN": [],
        "VOLATILIDAD_UP": [],
        "VOLATILIDAD_DOWN": [],
        "VALOR_ESCENARIO_UP_COP": [],
        "VALOR_ESCENARIO_DOWN_COP": [],
        "DELTA_UNITARIO_CALCULADO": [],
        "POSICION_DELTA_USD": [],
        "POSICION_SENSIBILIDAD_USD": [],
        "POSICION_BUMP_USD": [],
    }

    for fila in detalle.itertuples(index=False):
        plazo = int(getattr(fila, "PLAZO"))
        plazo_cumplimiento = int(getattr(fila, "PLAZO_CUMPLIMIENTO"))

        if plazo <= 0:
            for columna in columnas_mercado:
                columnas_mercado[columna].append(0.0)
            continue

        tasa_cop = _interpolar_tasa_plazo(plazo, mercado.curva_cop, "TASA_COP")
        tasa_usd = _interpolar_tasa_plazo(plazo, mercado.curva_usd, "TASA_USD")

        if plazo_cumplimiento > 0:
            fila_usd_cumplimiento = _fila_rango_por_plazo(plazo_cumplimiento, mercado.curva_usd)
            dias_inf_usd = float(fila_usd_cumplimiento["PLAZO_INFERIOR"])
            dias_sup_usd = float(fila_usd_cumplimiento["PLAZO_SUPERIOR"])
            tasa_inf_usd = float(fila_usd_cumplimiento["TASA_USD"])
            fila_tasa_sup_usd = mercado.curva_usd.loc[mercado.curva_usd["PLAZO_INFERIOR"] == dias_sup_usd]
            tasa_sup_usd = (
                tasa_inf_usd
                if fila_tasa_sup_usd.empty
                else float(fila_tasa_sup_usd.iloc[0]["TASA_USD"])
            )
            # Se conserva la formula del legado: el factor se interpola con el plazo
            # de vencimiento, no con el plazo de cumplimiento.
            tasa_val_usd_cump = _interpolar_desde_rango(
                plazo,
                dias_inf_usd,
                dias_sup_usd,
                tasa_inf_usd,
                tasa_sup_usd,
            )
            factor_descuento = float(
                np.exp((tasa_val_usd_cump * plazo_cumplimiento) / 365)
                / np.exp((tasa_usd * plazo) / 365)
            )
        else:
            dias_inf_usd = 0.0
            dias_sup_usd = 0.0
            tasa_inf_usd = 0.0
            tasa_sup_usd = 0.0
            tasa_val_usd_cump = 0.0
            factor_descuento = 1.0

        fila_superficie = _fila_rango_por_plazo(plazo, mercado.superficie_vol)
        dias_inf_sup = float(fila_superficie["PLAZO_INFERIOR"])
        dias_sup_sup = float(fila_superficie["PLAZO_SUPERIOR"])

        fila_superficie_sup = mercado.superficie_vol.loc[
            mercado.superficie_vol["PLAZO_INFERIOR"] == dias_sup_sup
        ]
        if fila_superficie_sup.empty:
            fila_superficie_sup = fila_superficie.to_frame().T

        vol_10put = _interpolar_desde_rango(
            plazo,
            dias_inf_sup,
            dias_sup_sup,
            float(fila_superficie["VOL_10D_PUT"]),
            float(fila_superficie_sup.iloc[0]["VOL_10D_PUT"]),
        )
        vol_25put = _interpolar_desde_rango(
            plazo,
            dias_inf_sup,
            dias_sup_sup,
            float(fila_superficie["VOL_25D_PUT"]),
            float(fila_superficie_sup.iloc[0]["VOL_25D_PUT"]),
        )
        vol_atm = _interpolar_desde_rango(
            plazo,
            dias_inf_sup,
            dias_sup_sup,
            float(fila_superficie["VOL_ATM"]),
            float(fila_superficie_sup.iloc[0]["VOL_ATM"]),
        )
        vol_25call = _interpolar_desde_rango(
            plazo,
            dias_inf_sup,
            dias_sup_sup,
            float(fila_superficie["VOL_25D_CALL"]),
            float(fila_superficie_sup.iloc[0]["VOL_25D_CALL"]),
        )
        vol_10call = _interpolar_desde_rango(
            plazo,
            dias_inf_sup,
            dias_sup_sup,
            float(fila_superficie["VOL_10D_CALL"]),
            float(fila_superficie_sup.iloc[0]["VOL_10D_CALL"]),
        )

        volatilidad_cubica = _volatilidad_cubic(
            spot=mercado.trm,
            strike=float(getattr(fila, "PRECIO_DE_EJERCICIO")),
            plazo=plazo,
            tasa_cop=tasa_cop,
            tasa_usd=tasa_usd,
            delta_atm=vol_atm,
            vol_10put=vol_10put,
            vol_25put=vol_25put,
            vol_atm=vol_atm,
            vol_25call=vol_25call,
            vol_10call=vol_10call,
            tipo_opcion=str(getattr(fila, "TIPO_DE_OPCION")),
            factor_descuento=factor_descuento,
        )

        delta_unitario = _delta_opcion(
            fecha_corte=fecha_corte,
            fecha_vencimiento=getattr(fila, "FECHA_DE_VENCIMIENTO"),
            spot=mercado.trm,
            strike=float(getattr(fila, "PRECIO_DE_EJERCICIO")),
            tasa_cop=tasa_cop,
            tasa_usd=tasa_usd,
            sigma=volatilidad_cubica,
            tipo_opcion=str(getattr(fila, "TIPO_DE_OPCION")),
        )
        posicion_delta = delta_unitario * _signo_posicion(str(getattr(fila, "POSICION_EN_LA_OPCION"))) * float(
            getattr(fila, "NOMINAL")
        )

        columnas_mercado["TASA_COP"].append(tasa_cop)
        columnas_mercado["TASA_USD"].append(tasa_usd)
        columnas_mercado["DIAS_INF_USD"].append(dias_inf_usd)
        columnas_mercado["DIAS_SUP_USD"].append(dias_sup_usd)
        columnas_mercado["TASA_INF_USD"].append(tasa_inf_usd)
        columnas_mercado["TASA_SUP_USD"].append(tasa_sup_usd)
        columnas_mercado["TASA_VAL_USD_CUMP"].append(tasa_val_usd_cump)
        columnas_mercado["FACTOR_DE_DESCUENTO"].append(factor_descuento)
        columnas_mercado["DIAS_INF_SUPERFICIE"].append(dias_inf_sup)
        columnas_mercado["DIAS_SUP_SUPERFICIE"].append(dias_sup_sup)
        columnas_mercado["VOL_10D_PUT"].append(vol_10put)
        columnas_mercado["VOL_25D_PUT"].append(vol_25put)
        columnas_mercado["VOL_ATM"].append(vol_atm)
        columnas_mercado["VOL_25D_CALL"].append(vol_25call)
        columnas_mercado["VOL_10D_CALL"].append(vol_10call)
        columnas_mercado["VOLATILIDAD_CUBICA"].append(volatilidad_cubica)
        columnas_mercado["DELTA_UNITARIO_CALCULADO"].append(delta_unitario)
        columnas_mercado["POSICION_DELTA_USD"].append(posicion_delta)

        # Sensibilidad spot por diferencias centradas; FF_V3 queda solo como referencia metodologica.
        # POSICION_SENSIBILIDAD_USD = dV_COP/dSpot.
        # Unidades: COP / (COP/USD) = USD, comparable con delta * nominal.
        strike = float(getattr(fila, "PRECIO_DE_EJERCICIO"))
        tipo_opc = str(getattr(fila, "TIPO_DE_OPCION"))
        nom = float(getattr(fila, "NOMINAL"))
        # El valor COP de cada escenario se calcula dentro del helper.
        sensibilidad = _calcular_sensibilidad_spot_opcion(
            spot_base=mercado.trm,
            strike=strike,
            plazo=plazo,
            tasa_cop=tasa_cop,
            tasa_usd=tasa_usd,
            vol_10put=vol_10put,
            vol_25put=vol_25put,
            vol_atm=vol_atm,
            vol_25call=vol_25call,
            vol_10call=vol_10call,
            tipo_opcion=tipo_opc,
            factor_descuento=factor_descuento,
            posicion_en_opcion=str(getattr(fila, "POSICION_EN_LA_OPCION")),
            nominal=nom,
        )
        for columna in (
            "SPOT_UP",
            "SPOT_DOWN",
            "VOLATILIDAD_UP",
            "VOLATILIDAD_DOWN",
            "VALOR_ESCENARIO_UP_COP",
            "VALOR_ESCENARIO_DOWN_COP",
            "POSICION_SENSIBILIDAD_USD",
        ):
            columnas_mercado[columna].append(sensibilidad[columna])
        # Alias temporal para mantener compatibilidad con soportes previos.
        columnas_mercado["POSICION_BUMP_USD"].append(sensibilidad["POSICION_SENSIBILIDAD_USD"])

    for columna, valores in columnas_mercado.items():
        detalle[columna] = valores

    vencimiento = detalle["FECHA_DE_VENCIMIENTO"].dt.normalize()
    cumplimiento = detalle["FECHA_DE_CUMPLIMIENTO"].dt.normalize()
    moneda_cumplimiento = detalle["MONEDA_CUMPLIMIENTO_REGLA"].fillna("").astype(str).str.strip().str.upper()

    es_vigente = fecha_corte < vencimiento
    cumple_hoy = cumplimiento == fecha_corte
    vence_y_liquida_en_cop = moneda_cumplimiento == "COP"

    detalle["REGLA_POSICION"] = np.where(
        es_vigente,
        "SENSIBILIDAD_SPOT_VIGENTE",
        np.where(
            cumple_hoy,
            "VENCIDA_CUMPLE_HOY_CERO",
            np.where(
                vence_y_liquida_en_cop,
                "VENCIDA_NO_CUMPLIDA_COP_CERO",
                "VENCIDA_NO_CUMPLIDA_VALOR_LIQUIDACION",
            ),
        ),
    )

    detalle["POSICION_VENCIDA_NO_CUMPLIDA_USD"] = np.where(
        es_vigente | cumple_hoy | vence_y_liquida_en_cop,
        0.0,
        detalle["VALOR_LIQUIDACION_REPORTE"].fillna(0.0),
    )

    # Posicion final: sensibilidad spot para vigentes; valor liquidacion para vencidas.
    detalle["POSICION_FINAL_USD"] = np.where(
        es_vigente,
        detalle["POSICION_SENSIBILIDAD_USD"],
        detalle["POSICION_VENCIDA_NO_CUMPLIDA_USD"],
    )

    return detalle


def _construir_tabla_posicion_por_book(
    detalle: pd.DataFrame,
    fecha_corte: pd.Timestamp,
    logger=None,
) -> pd.DataFrame:
    """Tabla canonica de Opciones desagregada por BOOK (para archivo auxiliar)."""
    tabla = detalle.groupby("BOOK", as_index=False)["POSICION_FINAL_USD"].sum()
    tabla = tabla.rename(columns={"POSICION_FINAL_USD": "POSICION"})
    tabla["FECHA"] = fecha_corte.strftime("%d/%m/%Y")
    tabla["PRODUCTO"] = "Opciones"
    tabla = enriquecer_con_parametros_libros(
        tabla,
        producto="Opciones",
        logger=logger,
        default_lb_lt=VALOR_LB_LT_NO_DEFINIDO,
        default_instrumento="Derivados",
        default_moneda_posicion="USD",
    )
    tabla["COMPANY"] = "Colombia"
    tabla["CLASIFICACION_CONTABLE"] = "NA"
    tabla["BANKING_CVA_DVA"] = "Banking"
    return tabla[COLUMNAS_POSICION]


def _construir_tabla_posicion(
    detalle: pd.DataFrame,
    fecha_corte: pd.Timestamp,
    logger=None,
) -> pd.DataFrame:
    """Tabla canonica con BOOK='Opciones' para la consolidacion (no hay CVA/DVA)."""
    posicion_total = pd.to_numeric(detalle["POSICION_FINAL_USD"], errors="coerce").fillna(0.0).sum()
    return pd.DataFrame([{
        "FECHA": fecha_corte.strftime("%d/%m/%Y"),
        "PRODUCTO": "Opciones",
        "BOOK": "Opciones",
        "POSICION": posicion_total,
        "MONEDA_POSICION": "USD",
        "LB_LT": "Trading",
        "INSTRUMENTO": "Derivados",
        "COMPANY": "Colombia",
        "CLASIFICACION_CONTABLE": "NA",
        "BANKING_CVA_DVA": "Banking",
    }])


def _construir_resumen_control(
    fecha_corte: pd.Timestamp,
    rutas: dict[str, Path],
    mercado: MercadoOpciones,
    detalle: pd.DataFrame,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"CLAVE": "Fecha de corte", "VALOR": fecha_corte.strftime("%d-%m-%Y")},
            {"CLAVE": "TRM spot", "VALOR": mercado.trm},
            {"CLAVE": "Archivo opciones manana", "VALOR": str(rutas["opciones_manana"])},
            {"CLAVE": "Archivo mercado ENTRADA2", "VALOR": str(rutas["entrada2_mercado"])},
            {"CLAVE": "Archivo historico TRM", "VALOR": str(rutas["historico_trm"])},
            {"CLAVE": "Filas opciones procesadas", "VALOR": len(detalle)},
            {
                "CLAVE": "Regla vigentes",
                "VALOR": "Posicion = sensibilidad spot: dV_COP/dSpot con escenarios +/-0.25% [USD]",
            },
            {
                "CLAVE": "Regla vencidas no cumplidas",
                "VALOR": "Si cumplimiento = corte o moneda cumplimiento = COP => 0; en otro caso usa VP Sett Ccy Y CVA",
            },
        ]
    )


def ejecutar_opciones(
    fecha_trabajo: str,
    logger=None,
    confirmar_reemplazo: bool = True,
) -> pd.DataFrame | None:
    """Calcula y publica la posicion de opciones en el layout canonico de Risko.

    Reglas de negocio implementadas:
    - Operaciones vigentes: la posicion se toma de la sensibilidad spot dV_COP/dSpot.
    - Operaciones vencidas o en fecha de vencimiento: la posicion ya no usa delta.
    - Vencidas no cumplidas:
      - si la fecha de cumplimiento coincide con la fecha de corte => posicion 0,
      - si la moneda de cumplimiento es COP => posicion 0,
      - en otro caso => se toma el valor de liquidacion reportado en `VP Sett Ccy Y CVA`.

    Para una fecha de corte, el modulo usa el archivo de opciones publicado el
    siguiente dia habil en Summit, porque ese reporte contiene la informacion
    del dia habil anterior.
    """

    registrar_log(logger, "Inicia proceso Opciones.")
    registrar_log(logger, f"Fecha de trabajo Opciones: {fecha_trabajo}.")

    fecha_corte = _fecha_trabajo_a_timestamp(fecha_trabajo)
    rutas = _validar_insumos_locales(fecha_corte, logger=logger)

    detalle_opciones = _leer_reporte_opciones(rutas["opciones_manana"])
    registrar_log(
        logger,
        f"Reporte de opciones cargado: {detalle_opciones.shape[0]} filas y {detalle_opciones.shape[1]} columnas.",
    )

    mercado = _cargar_mercado_opciones(
        rutas["entrada2_mercado"],
        rutas["historico_trm"],
        fecha_corte,
        logger=logger,
    )
    registrar_log(logger, f"TRM spot usada en Opciones: {mercado.trm:,.6f}")

    detalle_calculado = _calcular_detalle_opciones(detalle_opciones, fecha_corte, mercado)
    tabla_posicion = _construir_tabla_posicion(detalle_calculado, fecha_corte, logger=logger)
    tabla_posicion_por_book = _construir_tabla_posicion_por_book(detalle_calculado, fecha_corte, logger=logger)

    tabla_posicion_actualizada = actualizar_datos_por_fecha(
        ARCHIVO_SALIDA_OPCIONES_TABLA,
        tabla_posicion,
        fecha_trabajo,
        "FECHA",
        "csv",
        confirmar_reemplazo=confirmar_reemplazo,
    )
    if tabla_posicion_actualizada is None:
        registrar_log(logger, "Opciones cancelado por el usuario al detectar una fecha existente.")
        return None

    resumen_control = _construir_resumen_control(
        fecha_corte,
        rutas,
        mercado,
        detalle_calculado,
    )

    ARCHIVO_INSUMO_OPCIONES_DEPURADO.parent.mkdir(parents=True, exist_ok=True)
    temporal_excel = ARCHIVO_INSUMO_OPCIONES_DEPURADO.with_name(
        f".{ARCHIVO_INSUMO_OPCIONES_DEPURADO.stem}.{uuid.uuid4().hex}.tmp.xlsx"
    )
    try:
        with pd.ExcelWriter(temporal_excel, engine="openpyxl", mode="w") as writer:
            detalle_calculado.to_excel(writer, sheet_name="Detalle", index=False)
            tabla_posicion_por_book.to_excel(writer, sheet_name="Posicion_Por_Book", index=False)
            resumen_control.to_excel(writer, sheet_name="Control", index=False)
        try:
            os.replace(temporal_excel, ARCHIVO_INSUMO_OPCIONES_DEPURADO)
        except PermissionError:
            registrar_log(
                logger,
                "No se pudo actualizar el Excel de soporte de Opciones porque "
                "esta abierto o bloqueado. La tabla oficial y SQLite continuan.",
            )
    finally:
        temporal_excel.unlink(missing_ok=True)

    ARCHIVO_SALIDA_OPCIONES_TABLA.parent.mkdir(parents=True, exist_ok=True)
    guardar_csv_si_posible(tabla_posicion_actualizada, ARCHIVO_SALIDA_OPCIONES_TABLA, logger=logger)

    registrar_log(logger, f"Detalle Opciones guardado en: {ARCHIVO_INSUMO_OPCIONES_DEPURADO}")
    registrar_log(logger, f"Tabla Opciones guardada en: {ARCHIVO_SALIDA_OPCIONES_TABLA}")

    # ADICION AUXILIAR: guarda una copia consultable de cada hoja/tabla de soporte.
    # Los archivos Excel y CSV anteriores continúan siendo las salidas operativas actuales.
    guardar_tablas_auxiliares_modulo(
        "Opciones",
        fecha_trabajo,
        {
            "detalle_calculado": detalle_calculado,
            "posicion_por_book": tabla_posicion_por_book,
            "control": resumen_control,
            "curva_usd": mercado.curva_usd,
            "curva_cop": mercado.curva_cop,
            "superficie_volatilidad": mercado.superficie_vol,
            "posicion": tabla_posicion_actualizada,
        },
        logger=logger,
    )
    return tabla_posicion_actualizada
