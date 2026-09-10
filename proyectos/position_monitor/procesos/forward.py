from __future__ import annotations

from pathlib import Path
import re
import shutil
import sys

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
    ARCHIVO_INSUMO_FORWARD_DEPURADO,
    ARCHIVO_INSUMO_FORWARD_IFRS_DEPURADO,
    ARCHIVO_PARAM_RUTAS,
    ARCHIVO_SALIDA_FORWARD_CVA_DVA,
)
from proyectos.position_monitor.procesos.parametros_libros import (
    VALOR_LB_LT_NO_DEFINIDO,
    enriquecer_con_parametros_libros,
)


COLUMNAS_POSICION = [
    # Estructura canonica que consumen los tableros y archivos consolidados
    # de Position Monitor. Mantener este orden evita diferencias entre Banking,
    # IFRS y CVA/DVA al concatenar las tablas finales.
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

# Campos monetarios que llegan como texto desde el archivo Summit y deben
# convertirse a numerico antes de aplicar las reglas de posicion.
COLUMNAS_NUMERICAS_FORWARD = [
    "VP_Y_USD_BUY",
    "VP_Y_USD_SELL",
    "VALOR_LIQ",
    "VP_Y_SETT_CCY_CVA"
]


def _cargar_parametros_rutas() -> pd.DataFrame:
    """Carga la tabla central de rutas usada para localizar insumos Forward."""
    return leer_csv(ARCHIVO_PARAM_RUTAS, sep=",", encoding="latin-1")


def _fila_parametro(df_parametros: pd.DataFrame, detalle: str) -> pd.Series:
    """Obtiene la configuracion exacta de una ruta dentro de param_rutas.csv."""
    fila = df_parametros.loc[df_parametros["Detalle"].astype(str).str.strip() == detalle]
    if fila.empty:
        raise ValueError(f"No se encontro la configuracion {detalle} en param_rutas.csv")
    return fila.iloc[0]


def _ruta_desde_parametro(fila: pd.Series, sufijo: str) -> Path:
    """Construye la ruta completa del archivo esperado para la fecha de trabajo."""
    ruta_base = str(fila["Ruta"]).strip()
    nombre_archivo = str(fila["Nombre_Archivo"]).strip()
    return Path(f"{ruta_base}{nombre_archivo}{sufijo}")


def _leer_insumo_forward(ruta_archivo: Path) -> pd.DataFrame:
    """Lee el reporte Forward exportado por Summit con el formato operativo esperado."""
    return pd.read_csv(
        ruta_archivo,
        sep=";",
        skiprows=5,
        encoding="latin1",
        engine="python",
        index_col=False,
        on_bad_lines="skip",
    )


def _leer_fecha_objetivo_forward(ruta_archivo: Path) -> pd.Timestamp | None:
    """Lee ``PARAMETRO FECHA Y``, que identifica el corte real del reporte."""
    with ruta_archivo.open("r", encoding="latin1", errors="replace") as archivo:
        for _ in range(6):
            linea = archivo.readline()
            if not linea:
                break
            coincidencia = re.search(
                r"PARAMETRO\s+FECHA\s+Y\s*:\s*;\s*(\d{8})",
                linea,
                flags=re.IGNORECASE,
            )
            if coincidencia is not None:
                fecha = pd.to_datetime(
                    coincidencia.group(1),
                    format="%d%m%Y",
                    errors="coerce",
                )
                return None if pd.isna(fecha) else fecha.normalize()
    return None


def _resolver_fuente_forward_por_fecha(
    fecha_corte: pd.Timestamp,
    fila_summit: pd.Series,
) -> Path:
    """Localiza el reporte cuyo corte interno coincide con la fecha solicitada.

    Summit conserva los cortes no habiles como miembros de una familia: el
    nombre mantiene la fecha de generacion y el sufijo ``_001``, ``_002`` o
    superior avanza el ``PARAMETRO FECHA Y``. Por eso el encabezado es la
    autoridad para escoger un archivo de fin de semana.
    """
    carpeta = Path(str(fila_summit["Ruta"]).strip())
    prefijo = str(fila_summit["Nombre_Archivo"]).strip()
    fecha_nombre = fecha_corte.strftime("%d%m%Y")
    exacto = carpeta / f"{prefijo}{fecha_nombre}_000.xls"
    if exacto.is_file() and _leer_fecha_objetivo_forward(exacto) == fecha_corte:
        return exacto

    patron_nombre = re.compile(
        rf"^{re.escape(prefijo)}(?P<base>\d{{8}})_(?P<secuencia>\d{{3}})\.xls$",
        flags=re.IGNORECASE,
    )
    candidatos: list[tuple[pd.Timestamp, int, Path]] = []
    if carpeta.is_dir():
        for ruta in carpeta.glob(f"{prefijo}*.xls"):
            coincidencia = patron_nombre.match(ruta.name)
            if coincidencia is None:
                continue
            if _leer_fecha_objetivo_forward(ruta) != fecha_corte:
                continue
            fecha_base = pd.to_datetime(
                coincidencia.group("base"),
                format="%d%m%Y",
                errors="coerce",
            )
            if pd.isna(fecha_base):
                continue
            candidatos.append(
                (
                    fecha_base.normalize(),
                    int(coincidencia.group("secuencia")),
                    ruta,
                )
            )

    if not candidatos:
        raise FileNotFoundError(
            "No se encontro un reporte Forward cuyo PARAMETRO FECHA Y sea "
            f"{fecha_corte.strftime('%d/%m/%Y')} en {carpeta} para el prefijo {prefijo}."
        )

    return max(candidatos, key=lambda item: (item[0], item[1]))[2]


def preparar_insumos_forward(fecha_trabajo: str, logger=None) -> dict[str, Path]:
    """Copia Banking e IFRS al nombre local que consume el calculo existente."""
    fecha_corte = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_corte):
        raise ValueError(f"Fecha no valida para preparar insumos Forward: {fecha_trabajo}")
    fecha_corte = fecha_corte.normalize()
    parametros = _cargar_parametros_rutas()
    sufijo_local = f"{fecha_corte.strftime('%d%m%Y')}_000.xls"
    configuraciones = {
        "banking": ("Forward_Summit", "Forward_Local"),
        "ifrs": ("Forward_IFRS_Summit", "Forward_IFRS_Local"),
    }
    rutas: dict[str, Path] = {}
    for vista, (detalle_summit, detalle_local) in configuraciones.items():
        fuente = _resolver_fuente_forward_por_fecha(
            fecha_corte,
            _fila_parametro(parametros, detalle_summit),
        )
        destino = _ruta_desde_parametro(
            _fila_parametro(parametros, detalle_local),
            sufijo_local,
        )
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fuente, destino)
        registrar_log(
            logger,
            f"Forward {vista}: corte {fecha_corte.strftime('%d/%m/%Y')} "
            f"resuelto desde {fuente.name} y copiado como {destino.name}.",
        )
        rutas[vista] = destino
    return rutas


def _cargar_insumos_forward(fecha_trabajo: str, logger=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga los insumos Banking e IFRS que Vector dejo en datos/insumos."""
    fecha_valor = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_valor):
        raise ValueError(f"Fecha no valida para cargar insumos Forward: {fecha_trabajo}")
    df_parametros = _cargar_parametros_rutas()

    # Los archivos Summit se nombran con la fecha en formato ddmmaaaa_000.xls.
    sufijo = f"{fecha_valor.strftime('%d%m%Y')}_000.xls"

    # Cada llave representa una vista contable del Forward. Para cada vista se
    # consulta una configuracion fuente en Summit y una configuracion destino local.
    configuraciones = {"banking": "Forward_Local", "ifrs": "Forward_IFRS_Local"}
    insumos: dict[str, pd.DataFrame] = {}

    for llave, detalle_local in configuraciones.items():
        fila_local = _fila_parametro(df_parametros, detalle_local)

        ruta_local = _ruta_desde_parametro(fila_local, sufijo)

        registrar_log(logger, f"Insumo Forward {llave} esperado por Vector: {ruta_local}")

        if not ruta_local.exists():
            raise FileNotFoundError(
                "Vector no dejo el insumo Forward "
                f"{llave} para la fecha seleccionada: {ruta_local}"
            )

        df_insumo = _leer_insumo_forward(ruta_local)
        registrar_log(
            logger,
            f"Insumo Forward {llave} cargado: {df_insumo.shape[0]} filas, {df_insumo.shape[1]} columnas.",
        )
        insumos[llave] = df_insumo

    return insumos["banking"], insumos["ifrs"]


def _depurar_forward_posicion(
    df_forward: pd.DataFrame,
    fecha_trabajo: str,
    etiqueta_banking_cva_dva: str,
    logger=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normaliza el detalle Forward y resume la posicion por book.

    Devuelve dos objetos: el detalle depurado, util para auditoria del insumo,
    y una tabla agregada con la estructura estandar de Position Monitor. La
    etiqueta recibida identifica si el resultado pertenece a Banking o IFRS.
    """
    
    df_forward = df_forward.copy()
    df_forward.columns = df_forward.columns.str.strip()

    # El reporte original trae muchas columnas de soporte operativo,
    # sensibilidad, CVA y validaciones que no participan en el calculo de
    # posicion. Se eliminan con errors="ignore" porque el layout puede variar
    # levemente entre cortes o versiones exportadas por Summit.
    columnas_descartar = [
        "NIT CONTRAPARTE",
        "FOLDER",
        "SPOT RATE TD",
        "TS FWD",
        "RESET RATE",
        "RESET RATE 3RA",
        "F_INICIO_TO",
        "RESET DATE 2",
        "DIAS_VCTO_Y",
        "DIAS_CTO_Y",
        "SPOT DAYS Y",
        "SPOT DAYS Y 3RA.",
        "TS_CC_Y_T+K_BUY",
        "TS_CC_Y_T+K_SELL",
        "TS_CC_Y_T+K_3RA",
        "TS_CC_Y_BUY_VCTO",
        "TS_CC_Y_SELL_VCTO",
        "TS_CC_Y_SETT_VCTO",
        "TS_CC_Y_SETT_CTO",
        "DIAS_VCTO_X",
        "DIAS_CTO_X",
        "SPOT DAYS X",
        "SPOT DAYS X 3RA.",
        "TS_CC_X_T+K_BUY",
        "TS_CC_X_T+K_SELL",
        "TS_CC_X T+K 3RA",
        "TS CC_X BUY VCTO",
        "TS CC_X SELL VCTO",
        "TS CC_X SETT VCTO",
        "TS CC_X SETT CTO",
        "VP Y CCY SELL",
        "VP Y CCY BUY",
        "FWD CONSOLIDADO",
        "VALIDACION",
        "VALIDACIÓN",
        "VALIDACIÃƒâ€œN",
        "VALIDACIÃƒÆ’Ã¢â‚¬Å“N",
        "VP X CCY SELL",
        "VP X CCY BUY",
        "VP X USD SELL",
        "VP X USD BUY",
        "VP X COP SELL",
        "VP X COP BUY",
        "VALOR Y COP",
        "VALOR X COP",
        "VP X SETT CCY CVA",
        "P&G Diario",
        "TO PT/FT",
        "SPOT RATE Y",
        "SPOT RATE Y 3RA",
        "SPOT RATE X",
        "SPOT RATE X 3RA",
        "VALOR ACC Y COP",
        "VALOR ACC X COP",
        "P&G DIARIO ACC",
        "PATRIMONIO X",
        "PATRIMONIO Y",
        "NETO PATRIMONIO",
        "CORPORATE ID",
        "LINK ID",
        "TERM DATE",
        "CUSTOMER GROUP",
        "NETTING (ISDA)",
        "SEGMENTO COMERCIAL",
        "CUSTOMERRATING",
        "ACTIVO/PASIVO",
        "CVA CURVE",
        "SPREAD CVA X",
        "TASA DESCUENTO COP X",
        "FUTURE VALUE COP DER X",
        "FUTURE VALUE COP OBLI X",
        "CVA FAIR VALUE COP X",
        "DIFERENCIA CVA COP X",
        "SPREAD CVA Y",
        "TASA DESCUENTO COP Y",
        "FUTURE VALUE COP DER Y",
        "FUTURE VALUE COP OBLI Y",
        "CVA FAIR VALUE COP Y",
        "DIFERENCIA CVA COP Y",
        "NIVEL",
        "Delta Full Valuation Ã‚Â  1 USD",
        "Delta Full Valuation Ãƒâ€šÃ‚Â  1 USD",
        "VALOR SENSIBLE",
        "VLR SENSIBLE - Ã‚Â  NOMINAL",
        "VLR SENSIBLE - Ã‚Â  NOMINAL USD",
        "VLR SENSIBLE - Ãƒâ€šÃ‚Â  NOMINAL",
        "VLR SENSIBLE - Ãƒâ€šÃ‚Â  NOMINAL USD",
        "COMPONENTE CAMBIARIO",
        "ACUM. COMPONENTE Ã‚Â  CAMBIARIO",
        "ACUM. COMPONENTE Ãƒâ€šÃ‚Â  CAMBIARIO",
        "COMP. CAMBIARIO Ã‚Â  CIERRE AÃƒâ€˜O ANTERIOR",
        "COMP. CAMBIARIO Ãƒâ€šÃ‚Â  CIERRE AÃƒÆ’Ã¢â‚¬ËœO ANTERIOR",
        "VLR. COMP. CAMBIARIO Ã‚Â  AÃƒâ€˜O FISCAL",
        "VLR. COMP. CAMBIARIO Ãƒâ€šÃ‚Â  AÃƒÆ’Ã¢â‚¬ËœO FISCAL",
        "TAX_ID",
    ]
    df_forward = df_forward.drop(columns=columnas_descartar, errors="ignore")
    
    # Homologa nombres de columnas con espacios y caracteres especiales a
    # identificadores simples. Esto facilita las reglas vectorizadas de pandas
    # y reduce errores por diferencias de escritura en el insumo.
    df_forward = df_forward.rename(
        columns={
            "TRADE ID": "TRADE_ID",
            "CONTRAPARTE": "CONTRAPARTE",
            "PAR MONEDAS": "PAR_MONEDAS",
            "MODALIDAD": "MODALIDAD",
            "COMPANY": "COMPANY",
            "BOOK": "BOOK",
            "FINALIDAD": "FINALIDAD",
            "BUY/SELL": "BUY_SELL",
            "MONTO COMPRA": "MONTO_COMPRA",
            "CCY COMPRA": "CCY_COMPRA",
            "MONTO VENTA": "MONTO_VENTA",
            "CCY VENTA": "CCY_VENTA",
            "CCY SETTLEMENT": "CCY_SETTLEMENT",
            "F_APER": "F_APER",
            "F_VCTO": "F_VCTO",
            "F_CUMPTO": "F_CUMPTO",
            "VP Y USD SELL": "VP_Y_USD_SELL",
            "VP Y USD BUY": "VP_Y_USD_BUY",
            "VP Y COP SELL": "VP_Y_COP_SELL",
            "VP Y COP BUY": "VP_Y_COP_BUY",
            "VALOR LIQ": "VALOR_LIQ",
            "INTERNO/EXTERNO": "INTERNO_EXTERNO",
            "VP Sett Ccy Y": "VP_Y_SETT_CCY_CVA",
            "VP Y SETT CCY CVA": "VP_Y_SETT_CCY_CVA"
        }
    )

    fecha_corte = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_corte):
        raise ValueError(f"Fecha no valida para Forward: {fecha_trabajo}")

    # La fecha de corte se guarda como date para compararla directamente contra
    # vencimiento y cumplimiento, sin componentes de hora.
    df_forward["CORTE"] = fecha_corte.date()
    df_forward["F_VCTO"] = pd.to_datetime(
        df_forward["F_VCTO"].astype(str).str.strip(),
        format="%d/%m/%y",
        errors="coerce",
    ).dt.date
    df_forward["F_CUMPTO"] = pd.to_datetime(
        df_forward["F_CUMPTO"].astype(str).str.strip(),
        format="%d/%m/%y",
        errors="coerce",
    ).dt.date

    # Los valores monetarios llegan con separadores de miles y tipo texto. La
    # conversion a numerico deja NaN cuando el valor no es interpretable, en vez
    # de detener todo el proceso por una celda puntual.
    for columna in COLUMNAS_NUMERICAS_FORWARD:
        if columna not in df_forward.columns:
            continue
        df_forward[columna] = pd.to_numeric(
            df_forward[columna].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )

    df_forward["BUY_SELL"] = df_forward["BUY_SELL"].astype(str).str.strip()
    df_forward["CCY_COMPRA"] = df_forward["CCY_COMPRA"].astype(str).str.strip()
    df_forward["CCY_VENTA"] = df_forward["CCY_VENTA"].astype(str).str.strip()
    df_forward["CCY_SETTLEMENT"] = df_forward["CCY_SETTLEMENT"].astype(str).str.strip()
    
    # Regla de posicion:
    # =SI(CORTE<F_VCTO;
    #     SI(O(CCY_COMPRA="COP";CCY_VENTA="COP");
    #        SI(BUY_SELL="COMPRA";VP_Y_USD_BUY;SI(BUY_SELL="VENTA";VP_Y_USD_SELL;0));
    #        VP_Y_USD_BUY+VP_Y_USD_SELL);
    #     SI(O(CCY_SETTLEMENT="COP";CORTE>=F_CUMPTO);0;VP_Y_SETT_CCY_CVA))
    tiene_cop_compra_venta = (df_forward["CCY_COMPRA"] == "COP") | (df_forward["CCY_VENTA"] == "COP")
    liquida_cop_o_cumplido = (df_forward["CCY_SETTLEMENT"] == "COP") | (
        df_forward["CORTE"] >= df_forward["F_CUMPTO"]
    )

    posicion_vigente = np.where(
        tiene_cop_compra_venta,
        np.where(
            df_forward["BUY_SELL"] == "COMPRA",
            df_forward["VP_Y_USD_BUY"],
            np.where(df_forward["BUY_SELL"] == "VENTA", df_forward["VP_Y_USD_SELL"], 0),
        ),
        df_forward["VP_Y_USD_BUY"] + df_forward["VP_Y_USD_SELL"],
    )
    posicion_vencida = np.where(liquida_cop_o_cumplido, 0, df_forward["VP_Y_SETT_CCY_CVA"])
    df_forward["POSICION"] = np.where(
        df_forward["CORTE"] < df_forward["F_VCTO"],
        posicion_vigente,
        posicion_vencida,
    )

    # Agrega la posicion por book y completa las dimensiones desde param_libros.
    tabla_posicion = df_forward.groupby(["BOOK"], as_index=False)["POSICION"].sum()
    tabla_posicion["FECHA"] = fecha_corte.strftime("%d/%m/%Y")
    tabla_posicion["PRODUCTO"] = "Forward"
    tabla_posicion = enriquecer_con_parametros_libros(
        tabla_posicion,
        producto="Forward",
        logger=logger,
        default_lb_lt=VALOR_LB_LT_NO_DEFINIDO,
        default_instrumento="Derivados",
        default_moneda_posicion="USD",
    )
    tabla_posicion["COMPANY"] = "Colombia"
    tabla_posicion["CLASIFICACION_CONTABLE"] = "NA"
    tabla_posicion["BANKING_CVA_DVA"] = etiqueta_banking_cva_dva
    tabla_posicion = tabla_posicion[COLUMNAS_POSICION]
    return df_forward, tabla_posicion


def _construir_tabla_cva_dva(
    tabla_ifrs: pd.DataFrame,
    tabla_banking: pd.DataFrame,
    fecha_trabajo: str,
    logger=None,
) -> pd.DataFrame:
    """Calcula la posicion CVA/DVA como diferencia entre IFRS y Banking.

    La tabla resultante mantiene la misma estructura de salida que las tablas
    base. Cuando un book existe en una sola fuente se completa la otra posicion
    con cero para no perder diferencias contables.
    """
    fecha_corte = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_corte):
        raise ValueError(f"Fecha no valida para Forward: {fecha_trabajo}")

    # Outer join para conservar books presentes solo en IFRS o solo en Banking.
    df_cva_dva = tabla_ifrs[["BOOK", "POSICION"]].merge(
        tabla_banking[["BOOK", "POSICION"]],
        on="BOOK",
        how="outer",
        suffixes=("_IFRS", "_BANKING"),
    )
    df_cva_dva[["POSICION_IFRS", "POSICION_BANKING"]] = df_cva_dva[
        ["POSICION_IFRS", "POSICION_BANKING"]
    ].fillna(0)
    # La exposicion CVA/DVA se interpreta como el exceso de IFRS frente a Banking.
    df_cva_dva["POSICION"] = df_cva_dva["POSICION_IFRS"] - df_cva_dva["POSICION_BANKING"]
    df_cva_dva["FECHA"] = fecha_corte.strftime("%d/%m/%Y")
    df_cva_dva["PRODUCTO"] = "Forward"
    df_cva_dva = enriquecer_con_parametros_libros(
        df_cva_dva,
        producto="Forward",
        logger=logger,
        default_lb_lt=VALOR_LB_LT_NO_DEFINIDO,
        default_instrumento="Derivados",
        default_moneda_posicion="USD",
    )
    df_cva_dva["COMPANY"] = "Colombia"
    df_cva_dva["CLASIFICACION_CONTABLE"] = "NA"
    df_cva_dva["BANKING_CVA_DVA"] = "CVA/DVA"
    return df_cva_dva[COLUMNAS_POSICION]


def ejecutar_forward(
    fecha_trabajo: str,
    logger=None,
    confirmar_reemplazo: bool = True,
) -> pd.DataFrame | None:
    """Ejecuta el flujo completo de Forward para una fecha de trabajo.

    Coordina carga de insumos, depuracion, calculo de Banking/IFRS/CVA-DVA,
    actualizacion de la salida CVA/DVA y escritura de evidencias depuradas.
    Retorna la tabla Forward consolidada calculada en memoria.
    """
    registrar_log(logger, "Inicia proceso Forward.")
    registrar_log(logger, f"Fecha de trabajo Forward: {fecha_trabajo}.")

    # Insumos base: Forward Banking y Forward IFRS exportados desde Summit.
    df_forward, df_forward_ifrs = _cargar_insumos_forward(fecha_trabajo, logger=logger)

    # Cada fuente se depura con la misma regla de posicion; solo cambia la
    # etiqueta contable que queda en la columna BANKING_CVA_DVA.
    df_forward_depurado, tabla_forward_banking = _depurar_forward_posicion(
        df_forward,
        fecha_trabajo,
        "Banking",
        logger=logger,
    )
    df_forward_ifrs_depurado, tabla_forward_ifrs = _depurar_forward_posicion(
        df_forward_ifrs,
        fecha_trabajo,
        "IFRS",
        logger=logger,
    )
    tabla_forward_cva_dva = _construir_tabla_cva_dva(
        tabla_forward_ifrs,
        tabla_forward_banking,
        fecha_trabajo,
        logger=logger,
    )
    # Consolida las tres vistas para devolver el resultado completo en memoria.
    tabla_forward = pd.concat(
        [tabla_forward_banking, tabla_forward_ifrs, tabla_forward_cva_dva],
        ignore_index=True,
    )

    # Solo se conserva la salida CVA/DVA; las tablas Forward historicas y de
    # pruebas se calculan en memoria pero ya no se exportan desde este proceso.
    tabla_forward_cva_dva = actualizar_datos_por_fecha(
        ARCHIVO_SALIDA_FORWARD_CVA_DVA,
        tabla_forward_cva_dva,
        fecha_trabajo,
        "FECHA",
        "xlsx",
        confirmar_reemplazo=False,
    )

    # Escritura fisica de evidencias depuradas y CVA/DVA. Se crean las carpetas
    # necesarias antes de exportar el detalle operativo.
    ARCHIVO_INSUMO_FORWARD_DEPURADO.parent.mkdir(parents=True, exist_ok=True)
    df_forward_depurado.to_excel(ARCHIVO_INSUMO_FORWARD_DEPURADO, index=False)
    df_forward_ifrs_depurado.to_excel(ARCHIVO_INSUMO_FORWARD_IFRS_DEPURADO, index=False)
    tabla_forward_cva_dva.to_excel(ARCHIVO_SALIDA_FORWARD_CVA_DVA, index=False)

    registrar_log(logger, f"Detalle Forward Banking guardado en: {ARCHIVO_INSUMO_FORWARD_DEPURADO}")
    registrar_log(logger, f"Detalle Forward IFRS guardado en: {ARCHIVO_INSUMO_FORWARD_IFRS_DEPURADO}")
    registrar_log(logger, f"Tabla Forward CVA/DVA guardada en: {ARCHIVO_SALIDA_FORWARD_CVA_DVA}")

    # ADICION AUXILIAR: copia los DataFrames de soporte a risko_auxiliar.db.
    # No reemplaza ni modifica ninguno de los Excel calculados arriba.
    guardar_tablas_auxiliares_modulo(
        "Forward",
        fecha_trabajo,
        {
            "insumo_banking_depurado": df_forward_depurado,
            "insumo_ifrs_depurado": df_forward_ifrs_depurado,
            "posicion_banking": tabla_forward_banking,
            "posicion_ifrs": tabla_forward_ifrs,
            "posicion_cva_dva": tabla_forward_cva_dva,
            "posicion_consolidada": tabla_forward,
        },
        logger=logger,
    )
    return tabla_forward
