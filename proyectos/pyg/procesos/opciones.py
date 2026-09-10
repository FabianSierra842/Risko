"""Atribucion diaria preliminar del PyG de opciones FX.

El modulo reproduce el orden de revaloracion observado en ``Opciones_FF_V3``
sin importar ni modificar ningun componente de Position Monitor. La hoja
``PYG`` del libro diario se usa solo como control posterior, nunca como insumo
del resultado calculado.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from scipy.stats import norm
import holidays


RAIZ_RISKO = Path(__file__).resolve().parents[3]
ARCHIVO_CONFIG = Path(__file__).resolve().parents[1] / "configuracion" / "pyg.json"
CARPETA_PROCESADOS = RAIZ_RISKO / "datos" / "pyg" / "procesados"

DELTA_NODOS = np.array([0.10, 0.25, 0.50, 0.75, 0.90], dtype=float)
COLUMNAS_VOL = ("10 D PUT", "25 D PUT", "ATM", "25 D CALL", "10 D CALL")
COMPONENTES_CONTROL = {
    "THETA": "Theta_Opc",
    "DELTA_PYG": "Delta_Opc",
    "RHO": "Rho_Opc",
    "VEGA": "Vega_Opc",
    "NUEVOS_OTROS": "Nuevos_Opc",
    "PYG_BANKING": "PYG_Opc",
}


@dataclass(frozen=True)
class SnapshotOpciones:
    fecha: date
    ruta: Path
    opciones: pd.DataFrame
    resumen: pd.Series
    curva_usd: pd.DataFrame
    curva_cop: pd.DataFrame
    superficie_vol: pd.DataFrame
    tasas_fix: pd.DataFrame
    control_legacy: dict[str, float]


@dataclass(frozen=True)
class ResultadoPygOpciones:
    fecha: str
    fecha_anterior: str
    producto: str
    estado: str
    componentes: dict[str, float]
    escenarios: dict[str, float]
    mercado: dict[str, float]
    conciliacion: dict[str, float | str | None]
    fuentes: dict[str, str]
    calidad: list[dict[str, str]]

    def to_dict(self) -> dict:
        return asdict(self)


def cargar_configuracion(ruta: str | Path | None = None) -> dict:
    from proyectos.pyg.procesos.configuracion import cargar_configuracion as cargar
    return cargar(ruta)


def _fecha(valor: str | date | datetime | pd.Timestamp) -> date:
    if isinstance(valor, (date, datetime, pd.Timestamp)):
        marca = pd.Timestamp(valor)
    else:
        texto = str(valor).strip()
        if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
            marca = pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
        else:
            marca = pd.to_datetime(texto, dayfirst=True, errors="coerce")
    if pd.isna(marca):
        raise ValueError(f"Fecha no valida para PyG: {valor}")
    return marca.date()


def _numero(valor: object, defecto: float = 0.0) -> float:
    numero = pd.to_numeric(valor, errors="coerce")
    if pd.isna(numero) or not np.isfinite(float(numero)):
        raise ValueError(f"Importe o tasa no finito para PyG: {valor!r}")
    return float(numero)


def _texto(valor: object) -> str:
    if pd.isna(valor):
        return ""
    return str(valor).strip().upper()


def _valor_resumen(resumen: pd.Series, columna: str) -> float:
    if columna not in resumen.index:
        raise KeyError(f"La hoja Resumen no contiene la columna requerida: {columna}")
    return _numero(resumen[columna])


def _validar_columnas(tabla: pd.DataFrame, requeridas: set[str], contexto: str) -> None:
    faltantes = sorted(requeridas.difference(tabla.columns))
    if faltantes:
        raise ValueError(f"Faltan columnas en {contexto}: {', '.join(faltantes)}")


def _fechas_columna(serie: pd.Series, contexto: str) -> pd.Series:
    def convertir(valor):
        if isinstance(valor, (int, float, np.integer, np.floating)):
            numero = _numero(valor)
            if numero >= 19000101:
                return pd.to_datetime(str(int(numero)), format="%Y%m%d", errors="coerce")
            return pd.Timestamp("1899-12-30") + pd.to_timedelta(numero, unit="D")
        try:
            return pd.Timestamp(_fecha(valor))
        except (TypeError, ValueError):
            return pd.NaT
    fechas = serie.map(convertir)
    if fechas.isna().any():
        raise ValueError(f"Fechas invalidas en {contexto}")
    return pd.to_datetime(fechas).dt.normalize()


def _normalizar_opciones(opciones: pd.DataFrame) -> pd.DataFrame:
    opciones = opciones.copy()
    opciones.columns = opciones.columns.astype(str).str.strip()
    # El snapshot de FF_V3 usa dos espacios en «Moneda de la  Prima».
    for alias in ('Moneda de la  Prima', 'Moneda de la Prima'):
        if alias in opciones and 'Moneda Prima' not in opciones:
            opciones = opciones.rename(columns={alias: 'Moneda Prima'})
    _validar_columnas(opciones, {
        "Trade Id", "Posición en la opción", "Tipo de opción", "Fecha de Vencimiento",
        "Fecha de Cumplimiento", "Nominal", "Precio de Ejercicio", "Modalidad Cumplimiento",
        "Moneda cumplimiento", "Fecha de Emisión", "Valor Total Prima",
    }, "Opciones")
    if opciones["Trade Id"].isna().any() or opciones["Trade Id"].astype(str).str.strip().eq("").any():
        raise ValueError("Opciones contiene identificadores vacios")
    if opciones["Trade Id"].astype(str).str.strip().duplicated().any():
        raise ValueError("Opciones contiene Trade Id duplicados")
    for columna in ("Fecha de Emisión", "Fecha de Vencimiento", "Fecha de Cumplimiento"):
        opciones[columna] = _fechas_columna(opciones[columna], columna)
    if (opciones["Fecha de Cumplimiento"] < opciones["Fecha de Vencimiento"]).any():
        raise ValueError("Cumplimiento anterior al vencimiento en Opciones")
    if (opciones["Fecha de Emisión"] > opciones["Fecha de Vencimiento"]).any():
        raise ValueError("Emision posterior al vencimiento en Opciones")
    for columna in ("Nominal", "Precio de Ejercicio", "Valor Total Prima"):
        opciones[columna] = opciones[columna].map(_numero)
    if (opciones["Nominal"] < 0).any() or (opciones["Precio de Ejercicio"] <= 0).any():
        raise ValueError("Opciones requiere nominal no negativo y strike positivo")
    permitidos = {
        "Posición en la opción": {"BUY", "SELL"}, "Tipo de opción": {"PUT", "CALL"},
        "Moneda cumplimiento": {"COP", "USD"},
        "Modalidad Cumplimiento": {"DELIVERY", "NON DELIVERY"},
    }
    for columna, valores in permitidos.items():
        opciones[columna] = opciones[columna].map(_texto)
        if not opciones[columna].isin(valores).all():
            raise ValueError(f"Valor no admitido en Opciones/{columna}")
    return opciones


def _normalizar_curva(tabla: pd.DataFrame, columnas: tuple[str, ...]) -> pd.DataFrame:
    tabla = tabla.dropna(how="all").copy()
    tabla.columns = tabla.columns.astype(str).str.strip()
    _validar_columnas(tabla, {"Plazo Inferior", "Plazo Superior", *columnas}, "Curvas/superficie")
    if tabla.empty:
        raise ValueError("Curva o superficie vacia")
    for columna in ("Plazo Inferior", "Plazo Superior", *columnas):
        tabla[columna] = tabla[columna].map(_numero)
    tabla = tabla.sort_values("Plazo Inferior").reset_index(drop=True)
    if tabla["Plazo Inferior"].duplicated().any() or (tabla["Plazo Superior"] < tabla["Plazo Inferior"]).any():
        raise ValueError("Nodos de curva duplicados o rangos invalidos")
    if any(c in COLUMNAS_VOL for c in columnas) and (tabla[list(columnas)] <= 0).any().any():
        raise ValueError("La superficie requiere volatilidades positivas")
    return tabla


def _normalizar_fix(tabla: pd.DataFrame) -> pd.DataFrame:
    tabla = tabla.dropna(how="all").copy()
    tabla.columns = tabla.columns.astype(str).str.strip()
    _validar_columnas(tabla, {"FECHA", "TRM1"}, "tfd")
    if tabla.empty:
        return pd.DataFrame(columns=["FECHA", "TRM1"])
    tabla["FECHA"] = _fechas_columna(tabla["FECHA"], "tfd.FECHA").dt.strftime("%Y%m%d").astype(int)
    tabla["TRM1"] = tabla["TRM1"].map(_numero)
    if (tabla["TRM1"] <= 0).any() or tabla["FECHA"].duplicated().any():
        raise ValueError("tfd requiere fixing positivo y fechas unicas")
    return tabla.sort_values("FECHA").reset_index(drop=True)


def _leer_control_pyg(ruta: Path, nombre_hoja: str) -> dict[str, float]:
    try:
        tabla = pd.read_excel(ruta, sheet_name=nombre_hoja)
    except (ValueError, FileNotFoundError):
        return {}
    if tabla.empty or "Nombres" not in tabla.columns or len(tabla.columns) < 2:
        return {}
    valores = pd.to_numeric(tabla.iloc[:, 1], errors="coerce")
    return {
        str(nombre).strip(): float(valor)
        for nombre, valor in zip(tabla["Nombres"], valores)
        if pd.notna(nombre) and pd.notna(valor) and np.isfinite(valor)
    }


def cargar_snapshot(ruta: str | Path, fecha_snapshot: str | date | datetime) -> SnapshotOpciones:
    archivo = Path(ruta)
    if not archivo.is_file():
        raise FileNotFoundError(f"No existe el dataset diario de Opciones: {archivo}")
    fecha_corte = _fecha(fecha_snapshot)
    with pd.ExcelFile(archivo) as libro:
        hojas = libro.sheet_names
    requeridas = {
        "Opciones", "Resumen", "Tasas_USD", "Tasas_COP",
        "Superficie_Volatilidad", "tfd",
    }
    faltantes = sorted(requeridas.difference(hojas))
    if faltantes:
        raise ValueError(f"El dataset {archivo.name} no tiene las hojas: {', '.join(faltantes)}")

    opciones = pd.read_excel(archivo, sheet_name="Opciones")
    resumen_df = pd.read_excel(archivo, sheet_name="Resumen")
    if len(resumen_df) != 1:
        raise ValueError(f"Resumen requiere exactamente una fila en {archivo.name}")
    resumen_df.columns = resumen_df.columns.astype(str).str.strip()
    resumen = resumen_df.iloc[0]
    for marcador in ("FECHA", "Fecha", "FECHA_CORTE", "Fecha_Corte"):
        if marcador in resumen and _fechas_columna(pd.Series([resumen[marcador]]), marcador).iloc[0].date() != fecha_corte:
            raise ValueError(f"Fecha interna de {archivo.name} no coincide con {fecha_corte}")
    if _valor_resumen(resumen, "TRM") <= 0:
        raise ValueError("Resumen.TRM debe ser positiva")
    _valor_resumen(resumen, "Opccva")
    curva_usd = _normalizar_curva(pd.read_excel(archivo, sheet_name="Tasas_USD"), ("Tasas USD",))
    curva_cop = _normalizar_curva(pd.read_excel(archivo, sheet_name="Tasas_COP"), ("Tasas COP",))
    superficie = _normalizar_curva(pd.read_excel(archivo, sheet_name="Superficie_Volatilidad"), COLUMNAS_VOL)
    tasas_fix = _normalizar_fix(pd.read_excel(archivo, sheet_name="tfd"))
    opciones = _normalizar_opciones(opciones)
    if (opciones["Fecha de Emisión"] > pd.Timestamp(fecha_corte)).any():
        raise ValueError(f"Snapshot {archivo.name} contiene operaciones emitidas despues del corte")

    return SnapshotOpciones(
        fecha=fecha_corte,
        ruta=archivo,
        opciones=opciones,
        resumen=resumen,
        curva_usd=curva_usd,
        curva_cop=curva_cop,
        superficie_vol=superficie,
        tasas_fix=tasas_fix,
        control_legacy=_leer_control_pyg(archivo, "PYG"),
    )


def resolver_ruta_dataset(fecha_corte: str | date, config: dict | None = None) -> Path:
    cfg = config or cargar_configuracion()
    fuente = cfg["fuentes"]["opciones"]
    return Path(fuente["carpeta_datasets"]) / fuente["patron"].format(fecha=_fecha(fecha_corte))


def resolver_fecha_anterior(fecha_corte: str | date, config: dict | None = None) -> date:
    cfg = config or cargar_configuracion()
    candidato = _fecha(fecha_corte) - timedelta(days=1)
    calendario = str(cfg.get("calculo", {}).get("calendario", "CALENDARIO")).upper()
    if calendario not in {"CALENDARIO", "HABIL_CO"}:
        raise ValueError(f"Calendario PyG no admitido: {calendario}")
    if calendario == "HABIL_CO":
        festivos = holidays.Colombia(years=[candidato.year - 1, candidato.year])
        while candidato.weekday() >= 5 or candidato in festivos:
            candidato -= timedelta(days=1)
    return candidato


def _fila_rango(plazo: float, tabla: pd.DataFrame) -> pd.Series:
    mascara = tabla["Plazo Inferior"] <= plazo
    return tabla.loc[mascara[mascara].index[-1]] if mascara.any() else tabla.iloc[0]


def _valor_nodo(tabla: pd.DataFrame, plazo_inferior: float, columna: str) -> float:
    exacta = tabla.loc[tabla["Plazo Inferior"].eq(plazo_inferior), columna]
    if not exacta.empty and pd.notna(exacta.iloc[0]):
        return float(exacta.iloc[0])
    return float(_fila_rango(plazo_inferior, tabla)[columna])


def _interpolar(plazo: float, tabla: pd.DataFrame, columna: str) -> float:
    if plazo <= 0:
        return 0.0
    fila = _fila_rango(plazo, tabla)
    inferior = float(fila["Plazo Inferior"])
    superior = float(fila["Plazo Superior"])
    tasa_inf = float(fila[columna])
    if inferior == superior:
        return tasa_inf
    tasa_sup = _valor_nodo(tabla, superior, columna)
    proporcion_inf = 1.0 - ((plazo - inferior) / (superior - inferior))
    return (proporcion_inf * tasa_inf) + ((1.0 - proporcion_inf) * tasa_sup)


def _smile(plazo: int, superficie: pd.DataFrame) -> np.ndarray:
    if plazo <= 0:
        return np.zeros(5)
    return np.array([_interpolar(plazo, superficie, columna) for columna in COLUMNAS_VOL])


def _volatilidad_cubica(
    spot: float,
    strike: float,
    plazo: int,
    tasa_cop: float,
    tasa_usd: float,
    smile: np.ndarray,
    tipo: str,
    factor_descuento: float,
) -> float:
    tipo = _texto(tipo)
    if plazo <= 0 or spot <= 0 or strike <= 0 or tipo not in {'CALL', 'PUT'}:
        raise ValueError('Parámetros inválidos para interpolar volatilidad.')
    smile = np.asarray(smile, dtype=float)
    if smile.shape != (5,) or not np.isfinite(smile).all() or (smile <= 0).any():
        raise ValueError('Smile requiere cinco volatilidades positivas y finitas.')
    ajuste = _numero(factor_descuento)
    if ajuste <= 0:
        raise ValueError('Factor de descuento no positivo.')
    volatilidades = smile if tipo == "PUT" else smile[::-1]
    sigma = float(smile[2])
    spline = CubicSpline(DELTA_NODOS, volatilidades, bc_type="natural", extrapolate=False)
    for _ in range(100):
        d1 = (
            np.log(spot / strike)
            + (tasa_cop - tasa_usd + 0.5 * sigma**2) * plazo / 365.0
        ) / (sigma * np.sqrt(plazo / 365.0))
        delta = (norm.cdf(d1) + (-1 if tipo == "PUT" else 0)) / ajuste
        # FF_V3 fija las colas en los nodos 10/90 delta. No extrapolar durante
        # la iteración evita volatilidades negativas fuera de esos nodos.
        nodo = np.clip(abs(delta), DELTA_NODOS[0], DELTA_NODOS[-1])
        siguiente = float(spline(nodo))
        if not np.isfinite(siguiente) or siguiente <= 0:
            raise ValueError('Interpolación de volatilidad no positiva o no finita.')
        if abs(siguiente - sigma) <= 1e-12:
            return siguiente
        sigma = siguiente
    raise ValueError('La volatilidad por delta no converge; revise la superficie.')


def _valor_bsm(
    spot: float, strike: float, plazo: int, tasa_usd: float,
    tasa_cop: float, sigma: float, tipo: str,
) -> float:
    spot, strike, plazo, tasa_usd, tasa_cop, sigma = (
        _numero(v) for v in (spot, strike, plazo, tasa_usd, tasa_cop, sigma))
    tipo = _texto(tipo)
    if spot <= 0 or strike <= 0 or plazo < 0 or sigma < 0 or tipo not in {'CALL', 'PUT'}:
        raise ValueError('Parámetros inválidos para valorar la opción.')
    tiempo = plazo / 365.0
    signo = 1 if tipo == 'CALL' else -1
    if plazo == 0 or sigma == 0:
        return max(signo * (spot * np.exp(-tasa_usd * tiempo) - strike * np.exp(-tasa_cop * tiempo)), 0.0)
    d1 = (np.log(spot / strike) + (tasa_cop - tasa_usd + 0.5 * sigma**2) * tiempo) / (
        sigma * np.sqrt(tiempo)
    )
    d2 = d1 - sigma * np.sqrt(tiempo)
    if tipo == "CALL":
        return spot * np.exp(-tasa_usd * tiempo) * norm.cdf(d1) - strike * np.exp(-tasa_cop * tiempo) * norm.cdf(d2)
    return strike * np.exp(-tasa_cop * tiempo) * norm.cdf(-d2) - spot * np.exp(-tasa_usd * tiempo) * norm.cdf(-d1)


def revalorar_cartera(opciones, *, fecha_valor, spot, curva_cop, curva_usd,
                       superficie_vol, tasas_fix, inicio_periodo=None):
    """Valor de mercado, cuentas por cumplir y eventos del período, todos en COP."""
    corte = pd.Timestamp(fecha_valor)
    inicio = pd.Timestamp(inicio_periodo or corte.date().replace(day=1))
    if _numero(spot) <= 0:
        raise ValueError("El spot debe ser positivo.")
    registros = []
    for _, fila in opciones.iterrows():
        venc, cumple = pd.Timestamp(fila["Fecha de Vencimiento"]), pd.Timestamp(fila["Fecha de Cumplimiento"])
        emision = pd.Timestamp(fila["Fecha de Emisión"])
        if pd.isna(venc) or pd.isna(cumple) or emision > corte or cumple < venc:
            raise ValueError("Fechas de operación incompatibles con la valoración.")
        plazo, pc = (venc-corte).days, (cumple-corte).days
        n, k = _numero(fila["Nominal"]), _numero(fila["Precio de Ejercicio"])
        tipo, lado = _texto(fila["Tipo de opción"]), _texto(fila["Posición en la opción"])
        modalidad, moneda = _texto(fila["Modalidad Cumplimiento"]), _texto(fila["Moneda cumplimiento"])
        signo = 1 if lado == 'BUY' else -1
        mv = cxc = flujo = prima = 0.0
        if plazo > 0:
            rc, ru = _interpolar(plazo,curva_cop,'Tasas COP'), _interpolar(plazo,curva_usd,'Tasas USD')
            ruc = _interpolar(pc,curva_usd,'Tasas USD')
            factor = np.exp(ruc*pc/365)/np.exp(ru*plazo/365)
            sigma = _volatilidad_cubica(spot,k,plazo,rc,ru,_smile(plazo,superficie_vol),tipo,factor)
            mv = signo*n*_valor_bsm(spot,k,plazo,ru,rc,sigma,tipo)/factor
        else:
            if plazo == 0:
                fixing = spot
            else:
                seleccion = tasas_fix.loc[tasas_fix.FECHA.eq(int(venc.strftime('%Y%m%d'))),'TRM1']
                if len(seleccion) != 1:
                    raise ValueError(f"Falta fixing exacto de Opciones para {venc.date()}.")
                fixing = _numero(seleccion.iloc[0])
            if fixing <= 0:
                raise ValueError('Fixing de Opciones no positivo.')
            payoff = max(fixing-k,0) if tipo=='CALL' else max(k-fixing,0)
            if corte < cumple:
                if modalidad == 'NON DELIVERY':
                    cxc = signo*n*payoff*(spot/fixing if moneda=='USD' else 1)
                elif payoff > 0:
                    cxc = signo*n*(spot-k)*(1 if tipo=='CALL' else -1)
            elif cumple >= inicio:
                if modalidad == 'NON DELIVERY' and moneda == 'COP':
                    flujo = signo*n*payoff
                elif payoff > 0:
                    # La cuenta deja de revalorarse al liquidarse. Desde ese
                    # momento el saldo USD pertenece a Caja, no a Opciones.
                    if corte == cumple:
                        spot_cumplimiento = spot
                    else:
                        fijacion = tasas_fix.loc[tasas_fix.FECHA.eq(int(cumple.strftime('%Y%m%d'))), 'TRM1']
                        if len(fijacion) != 1:
                            raise ValueError(f'Falta conversión al cumplimiento de Opciones para {cumple.date()}.')
                        spot_cumplimiento = _numero(fijacion.iloc[0])
                    if spot_cumplimiento <= 0:
                        raise ValueError('Tasa al cumplimiento no positiva.')
                    flujo = (signo*n*payoff*spot_cumplimiento/fixing if modalidad == 'NON DELIVERY'
                             else signo*n*(spot_cumplimiento-k)*(1 if tipo == 'CALL' else -1))
        if inicio <= emision <= corte:
            prima = _numero(fila['Valor Total Prima'])
            moneda_prima = _texto(fila.get('Moneda Prima',fila.get('Moneda de la  Prima',fila.get('Moneda de la Prima',moneda))))
            if prima and moneda_prima == 'USD':
                if 'Tasa Prima' in fila and pd.notna(fila['Tasa Prima']):
                    tasa_prima = _numero(fila['Tasa Prima'])
                else:
                    fijacion = tasas_fix.loc[tasas_fix.FECHA.eq(int(emision.strftime('%Y%m%d'))),'TRM1']
                    if len(fijacion)!=1:
                        raise ValueError(f'Falta conversión de prima USD para {emision.date()}.')
                    tasa_prima = _numero(fijacion.iloc[0])
                if tasa_prima<=0:
                    raise ValueError('Tasa de prima no positiva.')
                prima *= tasa_prima
            elif moneda_prima not in {'COP','USD'}:
                raise ValueError('Moneda de prima no soportada.')
        registros.append(dict(TRADE_ID=str(fila['Trade Id']),VALOR_COP=float(mv),CXC_COP=float(cxc),
                              FLUJO_COP=float(flujo),PRIMA_COP=float(prima),TOTAL_COP=float(mv+cxc+flujo+prima)))
    detalle = pd.DataFrame(registros,columns=['TRADE_ID','VALOR_COP','CXC_COP','FLUJO_COP','PRIMA_COP','TOTAL_COP'])
    return float(detalle.TOTAL_COP.sum()),detalle


def _calidad(snapshot_anterior: SnapshotOpciones, snapshot_actual: SnapshotOpciones) -> list[dict[str, str]]:
    controles = []
    for nombre, valor, detalle in (
        ("Cartera anterior", not snapshot_anterior.opciones.empty, f"{len(snapshot_anterior.opciones):,} operaciones"),
        ("Resumen anterior", "ValoropcPYG" in snapshot_anterior.resumen.index, snapshot_anterior.ruta.name),
        ("Mercado anterior", not snapshot_anterior.superficie_vol.empty, "Curvas COP/USD y superficie"),
        ("Mercado actual", not snapshot_actual.superficie_vol.empty, "Curvas COP/USD y superficie"),
        ("Control legacy", bool(snapshot_actual.control_legacy), "Hoja PYG opcional"),
    ):
        controles.append({"control": nombre, "estado": "OK" if valor else "ADVERTENCIA", "detalle": detalle})
    return controles


def calcular_pyg_opciones(fecha_corte, *, config=None, fecha_anterior=None, logger=None):
    from proyectos.pyg.procesos.configuracion import configuracion
    from proyectos.pyg.procesos.atribucion import resultado_producto, control_pyg
    cfg = configuracion(config)
    fecha_actual = _fecha(fecha_corte)
    previa = _fecha(fecha_anterior) if fecha_anterior is not None else resolver_fecha_anterior(fecha_actual,cfg)
    if previa >= fecha_actual:
        raise ValueError('El snapshot anterior debe preceder al corte.')
    anterior = cargar_snapshot(resolver_ruta_dataset(previa,cfg),previa)
    actual = cargar_snapshot(resolver_ruta_dataset(fecha_actual,cfg),fecha_actual)
    s0,s1 = _valor_resumen(anterior.resumen,'TRM'),_valor_resumen(actual.resumen,'TRM')
    inicio = fecha_actual.replace(day=1)
    def valorar(cartera,cuando,spot,cop,usd,vol,fix):
        return revalorar_cartera(cartera,fecha_valor=cuando,spot=spot,curva_cop=cop,curva_usd=usd,
                                superficie_vol=vol,tasas_fix=fix,inicio_periodo=inicio)
    base,d0 = valorar(anterior.opciones,previa,s0,anterior.curva_cop,anterior.curva_usd,anterior.superficie_vol,anterior.tasas_fix)
    theta,_ = valorar(anterior.opciones,fecha_actual,s0,anterior.curva_cop,anterior.curva_usd,anterior.superficie_vol,actual.tasas_fix)
    delta,_ = valorar(anterior.opciones,fecha_actual,s1,anterior.curva_cop,anterior.curva_usd,anterior.superficie_vol,actual.tasas_fix)
    rho,_ = valorar(anterior.opciones,fecha_actual,s1,actual.curva_cop,actual.curva_usd,anterior.superficie_vol,actual.tasas_fix)
    vega,_ = valorar(anterior.opciones,fecha_actual,s1,actual.curva_cop,actual.curva_usd,actual.superficie_vol,actual.tasas_fix)
    final,d1 = valorar(actual.opciones,fecha_actual,s1,actual.curva_cop,actual.curva_usd,actual.superficie_vol,actual.tasas_fix)
    # Opccva es el nivel IFRS del mercado; los eventos son comunes a ambas vistas.
    cva = (_valor_resumen(actual.resumen,'Opccva')-float(d1.VALOR_COP.sum()))-(
            _valor_resumen(anterior.resumen,'Opccva')-float(d0.VALOR_COP.sum()))
    controles = control_pyg(actual,dict(THETA='Theta_Opc',DELTA_PYG='Delta_Opc',RHO='Rho_Opc',VEGA='Vega_Opc',
                                       NUEVOS_OTROS='Nuevos_Opc',PYG_BANKING='PYG_Opc'))
    calidad = _calidad(anterior,actual)
    calidad.append(dict(control='Convenciones corregidas',estado='ADVERTENCIA',
        detalle='CXC COP hasta cumplimiento; fixing exacto; descuento a settlement; primas por moneda. Requiere conciliación funcional frente a FF_V3.'))
    resultado = resultado_producto('OPCIONES',anterior,actual,
        dict(THETA=theta-base,DELTA_PYG=delta-theta,RHO=rho-delta,VEGA=vega-rho,NUEVOS_OTROS=final-vega),
        dict(BASE=base,THETA=theta,DELTA=delta,RHO=rho,VEGA=vega,ACTUAL=final),
        cva_dva=cva,config=cfg,controles=controles,calidad=calidad)
    if logger:
        logger(f"PyG Opciones: {resultado.componentes['PYG_BANKING']:,.2f} COP; {resultado.conciliacion['estado']}.")
    return resultado


def guardar_resultado(resultado: ResultadoPygOpciones, carpeta: str | Path | None = None) -> dict[str, Path]:
    destino = Path(carpeta) if carpeta else CARPETA_PROCESADOS
    destino.mkdir(parents=True, exist_ok=True)
    sufijo = resultado.fecha.replace("-", "")
    archivo_json = destino / f"pyg_opciones_{sufijo}.json"
    archivo_csv = destino / "pyg_opciones_historico.csv"
    temporal = archivo_json.with_suffix(".json.tmp")
    temporal.write_text(json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(archivo_json)

    fila = {
        "FECHA": resultado.fecha,
        "FECHA_ANTERIOR": resultado.fecha_anterior,
        "PRODUCTO": resultado.producto,
        "ESTADO": resultado.estado,
        **resultado.componentes,
        **resultado.mercado,
        "CONCILIACION": resultado.conciliacion["estado"],
    }
    historico = pd.read_csv(archivo_csv) if archivo_csv.exists() else pd.DataFrame()
    if "FECHA" in historico.columns:
        historico = historico.loc[historico["FECHA"].astype(str) != resultado.fecha]
    historico = pd.concat([historico, pd.DataFrame([fila])], ignore_index=True)
    historico.sort_values("FECHA", inplace=True)
    historico.to_csv(archivo_csv, index=False, encoding="utf-8-sig")
    return {"json": archivo_json, "historico": archivo_csv}


__all__ = [
    "ResultadoPygOpciones", "calcular_pyg_opciones", "cargar_configuracion",
    "cargar_snapshot", "guardar_resultado", "resolver_fecha_anterior",
    "resolver_ruta_dataset", "revalorar_cartera",
]
