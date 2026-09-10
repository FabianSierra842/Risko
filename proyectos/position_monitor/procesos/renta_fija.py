# Procesa el reporte de títulos de renta fija y genera las salidas operativas,
# la tabla canónica de Position Monitor y las tablas de consulta auxiliares.
from __future__ import annotations

# Renta Fija participa en el cierre productivo, la consolidacion y el portal.

# Dependencias estándar para manejar rutas y habilitar importaciones desde la raíz.
from pathlib import Path
import shutil
import sys

# Dependencias para transformar, clasificar y resumir los datos.
import numpy as np
import pandas as pd


# Permite importar los módulos compartidos cuando este archivo se ejecuta directamente.
RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

# Utilidades compartidas para leer, actualizar y guardar archivos del proyecto.
from compartido.nucleo_risko.archivos import (
    actualizar_datos_por_fecha,
    guardar_csv_si_posible,
    leer_csv,
    registrar_log,
)
from compartido.nucleo_risko.fechas import (
    Calcula_Fecha,
    Dias_No_Habiles_Desde_Ultimo_Habil,
    Ultimo_Dia_Habil,
)
from compartido.nucleo_risko.tablas_auxiliares import guardar_tablas_auxiliares_modulo
from compartido.nucleo_risko.rutas import (
    ARCHIVO_DETALLE_RENTA_FIJA,
    ARCHIVO_PARAM_LIBRORF,
    ARCHIVO_PARAM_MONEDARF,
    ARCHIVO_PARAM_RUTAS,
    ARCHIVO_SALIDA_RENTA_FIJA,
    ARCHIVO_SALIDA_RENTA_FIJA_TABLA,
)
from proyectos.position_monitor.procesos.parametros_libros import (
    VALOR_LB_LT_NO_DEFINIDO,
    enriquecer_con_parametros_libros,
)


# Estructura y orden esperado de las columnas en la salida canónica.
COLUMNAS_POSICION = [
    "FECHA",
    "PRODUCTO",
    "BOOK",
    "POSICION",
    "MONEDA_POSICION",
    "LB_LT",
    "INSTRUMENTO",
    "COMPANY",
    "BANKING_CVA_DVA",
]

MONEDAS_RENTA_FIJA_HABILITADAS = frozenset({"COP", "USD", "EUR", "UVR"})


def _actualizar_excel(ruta: Path, hoja: str, df_nuevo: pd.DataFrame) -> pd.DataFrame:
    """Combina una hoja histórica con datos nuevos y conserva el último dato por índice."""
    try:
        # Recupera la hoja existente para mantener la historia de fechas procesadas.
        df_historico = pd.read_excel(ruta, sheet_name=hoja, index_col=0)
        df_final = pd.concat([df_historico, df_nuevo])
        # Si una fecha está repetida, prioriza la versión recién procesada.
        df_final = df_final[~df_final.index.duplicated(keep="last")]
        return df_final.sort_index()
    except Exception:
        # Si el archivo o la hoja no existen, inicia la salida con los datos nuevos.
        return df_nuevo


def _normalizar_fecha(fecha_trabajo: str | None = None) -> pd.Timestamp:
    """Obtiene y valida la fecha usada para localizar y actualizar la información diaria."""
    # Sin una fecha explícita, usa la fecha hábil calculada por el núcleo.
    if fecha_trabajo in (None, ""):
        fecha_trabajo = Calcula_Fecha()

    # Interpreta el valor recibido en formato día/mes/año.
    fecha_valor = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha_valor):
        raise ValueError(f"Fecha no valida para renta fija: {fecha_trabajo}")

    return fecha_valor


def _cargar_parametros_rutas() -> pd.DataFrame:
    """Carga el catálogo que define las ubicaciones de los archivos de entrada."""
    return leer_csv(ARCHIVO_PARAM_RUTAS, encoding="latin-1")


def _fila_parametro(df_parametros: pd.DataFrame, detalle: str) -> pd.Series:
    """Busca una configuración de ruta por nombre y exige que esté definida."""
    fila = df_parametros.loc[df_parametros["Detalle"].astype(str).str.strip() == detalle]
    if fila.empty:
        raise ValueError(f"No se encontro la configuracion {detalle} en param_rutas.csv")
    return fila.iloc[0]


def _ruta_titulos(fecha_valor: pd.Timestamp, df_parametros: pd.DataFrame) -> Path:
    """Construye la ruta del reporte de títulos correspondiente a la fecha procesada."""
    # El archivo diario de Vector incorpora la fecha sin separadores.
    fecha_texto = fecha_valor.strftime("%d%m%Y")

    # Une la carpeta, el prefijo configurado y la fecha para formar la ruta completa.
    fila_local = _fila_parametro(df_parametros, "Titulos_Local")
    return Path(
        f"{str(fila_local['Ruta']).strip()}{str(fila_local['Nombre_Archivo']).strip()}{fecha_texto}.csv"
    )


def _nombre_archivo_fuente_titulos(fecha_valor: pd.Timestamp, prefijo: str) -> str:
    """Resuelve el miembro Summit que representa exactamente la fecha de corte."""
    fecha_corte = fecha_valor.normalize()
    dias_no_habiles = Dias_No_Habiles_Desde_Ultimo_Habil(fecha_corte.to_pydatetime())
    if dias_no_habiles == 0:
        return f"{prefijo}{fecha_corte.strftime('%d%m%Y')}.csv"

    ultimo_habil = Ultimo_Dia_Habil(fecha_corte.to_pydatetime())
    return f"{prefijo}{ultimo_habil.strftime('%d%m%Y')}_{dias_no_habiles}.csv"


def preparar_insumo_renta_fija(
    fecha_trabajo: str,
    logger=None,
) -> Path:
    """Copia al nombre local diario el reporte exacto de Renta Fija en Summit."""
    fecha_valor = _normalizar_fecha(fecha_trabajo)
    parametros = _cargar_parametros_rutas()
    fila_summit = _fila_parametro(parametros, "Titulos_Summit")
    carpeta_summit = Path(str(fila_summit["Ruta"]).strip())
    prefijo = str(fila_summit["Nombre_Archivo"]).strip()
    fuente = carpeta_summit / _nombre_archivo_fuente_titulos(fecha_valor, prefijo)
    destino = _ruta_titulos(fecha_valor, parametros)

    if not fuente.is_file():
        raise FileNotFoundError(
            "No se encontro el reporte de Renta Fija para el corte "
            f"{fecha_valor.strftime('%d/%m/%Y')}: {fuente}"
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fuente, destino)
    registrar_log(
        logger,
        f"Renta Fija: corte {fecha_valor.strftime('%d/%m/%Y')} resuelto desde "
        f"{fuente.name} y copiado como {destino.name}.",
    )
    return destino


def _filtrar_monedas_habilitadas(
    datos: pd.DataFrame,
    columna: str,
) -> pd.DataFrame:
    """Conserva solamente las monedas liberadas para cierre y publicacion."""
    monedas = datos[columna].fillna("").astype(str).str.strip().str.upper()
    return datos.loc[monedas.isin(MONEDAS_RENTA_FIJA_HABILITADAS)].copy()


def _leer_reporte_titulos(ruta_local: Path) -> pd.DataFrame:
    """Lee el archivo de Vector y lo transforma en una tabla con tipos utilizables."""
    # El archivo es tabulado, pero sus campos útiles vienen separados por punto y coma.
    reporte = pd.read_csv(ruta_local, sep="\t", engine="python", encoding="latin-1")
    cantidad_columnas = reporte["REPORTE TITULOS;"].str.split(";").transform(len).max()
    reporte[[f"REPORTE_TITULOS_{indice}" for indice in range(cantidad_columnas)]] = (
        reporte["REPORTE TITULOS;"].str.split(";", expand=True)
    )
    # Descarta encabezados técnicos y usa la primera fila útil como nombres de columnas.
    reporte = reporte.drop(reporte.columns[0], axis=1)
    reporte = reporte.drop([0, 1]).reset_index(drop=True)
    nombres = reporte.loc[0, :].values.tolist()
    reporte = reporte.set_axis(nombres, axis=1).drop(0).reset_index(drop=True)
    reporte.columns = reporte.columns.str.strip()
    reporte = reporte.iloc[:, :-2]
    # Convierte cada columna a número cuando todos sus valores lo permiten.
    def convertir_columna_numerica(columna: pd.Series) -> pd.Series:
        try:
            return pd.to_numeric(columna)
        except (TypeError, ValueError):
            return columna

    reporte = reporte.apply(convertir_columna_numerica)

    # Normaliza las fechas relevantes; los valores inválidos se convierten en NaT.
    columnas_fecha = [
        "FECHA INFORME",
        "FECHA EMISION",
        "FECHA VENCIMIENTO",
        "FECHA COMPRA",
        "FECHA CUMPLIMIENTO",
    ]
    for columna in columnas_fecha:
        reporte[columna] = pd.to_datetime(reporte[columna], format="%d/%m/%Y", errors="coerce")

    return reporte


def _enriquecer_reporte(reporte: pd.DataFrame, logger=None) -> pd.DataFrame:
    """Añade clasificaciones, parámetros de libros y métricas de riesgo al reporte."""
    reporte = reporte.copy()
    # Carga las equivalencias contables y monetarias utilizadas por renta fija.
    libros = leer_csv(ARCHIVO_PARAM_LIBRORF, encoding="latin-1")
    monedas = leer_csv(ARCHIVO_PARAM_MONEDARF, encoding="latin-1")

    # Traduce el esquema contable y la moneda a las categorías internas.
    reporte["TIPO LIBRO CONTABLE"] = reporte["ESQUEMA CONTABLE"].map(
        libros.set_index("Clasificación")["Libro"]
    )
    reporte["TIPO MONEDA"] = reporte["MONEDA DEL TITULO"].map(
        monedas.set_index("Moneda")["Equivalencia"]
    )

    # Asigna BOOK, COMPANY, LB/LT e INSTRUMENTO con el catálogo común de libros.
    reporte = enriquecer_con_parametros_libros(
        reporte,
        producto="Titulos",
        logger=logger,
        default_lb_lt=VALOR_LB_LT_NO_DEFINIDO,
        default_instrumento="Renta_fija",
    )

    # Separa los emisores definidos como públicos del resto de emisores privados.
    reporte["TIPO EMISOR"] = np.where(
        reporte["LEGALNAME"].isin(
            [
                "FINANCIERA DE DESARROLLO TERRITORIAL",
                "DIRECCION DEL TESORO NACIONAL",
                "FONDO PARA FINANCIAMIENTO DEL SECTOR AGROPECUARIO",
                "REPUBLICA DE PANAMA",
                "US TREASURY",
                "REPUBLIC OF COSTA RICA",
                "REPUBLICA FEDERAL DE ALEMANIA",
                "BANCO NACIONAL DE PANAMA",
                "EMPRESAS PUBLICAS DE MEDELLIN E.S.P.",
                "SECRETARIA DE HACIENDA DISTRITAL",
            ]
        ),
        "Deuda Publica",
        "Deuda Privada",
    )

    # Calcula la sensibilidad del valor presente ante movimientos de tasas. VP MDO Y COP
    reporte["DVO1"] = (reporte["DURACION MODIFICADA"] * 0.0001) * reporte["VP MDO Y CCY"]
    reporte["SENSIBILIDAD 100PBS"] = reporte["DVO1"] * 100
    reporte["VALOR 100PBS"] = reporte["VP MDO Y CCY"] - reporte["SENSIBILIDAD 100PBS"]

    # Clasifica el vencimiento por años restantes desde la fecha del informe.
    anios = (reporte["FECHA VENCIMIENTO"] - reporte["FECHA INFORME"]).dt.days / 365
    reporte["GRUPO VENCIMIENTO"] = np.where(
        anios < 3,
        "Corto Plazo",
        np.where((anios >= 3) & (anios < 5), "Mediano Plazo", "Largo Plazo"),
    )

    # Agrupa los instrumentos por producto usando tipo de inversión, título y moneda.
    condiciones = [
        (reporte["TIPO INVERSION"] == "TF") & (reporte["SECURITY TYPE"] == "CD"),
        (reporte["TIPO INVERSION"] == "TF") & (reporte["MONEDA DEL TITULO"].isin(["USD", "EUR"])),
        (reporte["TIPO INVERSION"] == "TREAS"),
        (reporte["TIPO INVERSION"] == "TIP"),
        (reporte["TIPO INVERSION"] == "TF") & (reporte["MONEDA DEL TITULO"].isin(["COP", "UVR"])),
        (reporte["TIPO INVERSION"].isin(["IPC", "IBR"])),
        (reporte["TIPO INVERSION"].isin(["NOTES", "LETRA"])),
        (reporte["TIPO INVERSION"].isin(["TDAAI", "TDABI", "TDAA", "TDAB", "TDS"])),
    ]
    valores = [
        "CDT",
        "BONOS ME",
        "BONOS ME",
        "T.HIPOTECARIA",
        "BONOS",
        "BONOS",
        "NOTAS",
        "OBLIGATORIAS",
    ]
    reporte["TITULOS"] = np.select(condiciones, valores, default=reporte["TIPO INVERSION"])
    # Aplica la regla vigente para determinar si la tasa es variable o fija.
    reporte["TIPO TASA"] = np.where(
        (reporte["TIPO INVERSION"] == "IPC") & (reporte["TIPO INVERSION"] == "IBR"),
        "Variable",
        "Fija",
    )
    return reporte


def _construir_posicion_operativa(reporte: pd.DataFrame) -> pd.DataFrame:
    """Selecciona y renombra los campos usados por el workbook operativo."""
    # Alimenta la hoja de detalle y las vistas resumidas de la exportación.
    reporte = _filtrar_monedas_habilitadas(reporte, "MONEDA DEL TITULO")

    posicion = pd.DataFrame()
    posicion["Fecha"] = reporte["FECHA INFORME"]
    posicion["Book"] = reporte["BOOK"]
    posicion["Agencia"] = reporte["COMPANY"]
    posicion["Producto"] = reporte["TITULOS"]
    posicion["Posición"] = reporte["VP MDO Y CCY"]
    posicion["LB/LT"] = reporte["LB_LT"]
    posicion["Der/TF"] = "Renta fija"
    posicion["Moneda"] = reporte["MONEDA DEL TITULO"]
    return posicion.set_index("Fecha")


def _construir_tabla_canonica(reporte: pd.DataFrame) -> pd.DataFrame:
    """Construye la salida estándar que Position Monitor consolida por fecha."""
    reporte = _filtrar_monedas_habilitadas(reporte, "MONEDA DEL TITULO")
    # Homologa nombres, formatos y valores por defecto al esquema común.
    tabla = pd.DataFrame(
        {
            "FECHA": reporte["FECHA INFORME"].dt.strftime("%d/%m/%Y"),
            "PRODUCTO": "Titulos",
            "BOOK": reporte["BOOK"],
            "POSICION": reporte["VP MDO Y CCY"],
            "MONEDA_POSICION": reporte["MONEDA DEL TITULO"],
            "LB_LT": reporte["LB_LT"].fillna(VALOR_LB_LT_NO_DEFINIDO),
            "INSTRUMENTO": reporte["INSTRUMENTO"].fillna("Renta_fija"),
            "COMPANY": reporte["COMPANY"].fillna("Colombia"),
            "BANKING_CVA_DVA": "Banking",
        }
    )

    # Define las dimensiones que identifican una posición única.
    groupby_cols = [
        "FECHA", "PRODUCTO", "BOOK", "MONEDA_POSICION",
        "LB_LT", "INSTRUMENTO", "COMPANY", "BANKING_CVA_DVA",
    ]
    # Suma las posiciones que comparten todas las dimensiones.
    tabla_agg = (
        tabla.groupby(groupby_cols, as_index=False, dropna=False)
        # CLASIFICACION_CONTABLE está desactivada y no se incluye en la salida.
        # .agg(POSICION=("POSICION", "sum"), CLASIFICACION_CONTABLE=("CLASIFICACION_CONTABLE", "first"))
        .agg(POSICION=("POSICION", "sum"))
    )
    # Devuelve las columnas en el orden exigido por Position Monitor.
    return tabla_agg[COLUMNAS_POSICION]


def _exportar_resultados_operativos(posicion: pd.DataFrame) -> None:
    """Genera el workbook histórico y el archivo independiente de detalle."""
    # Crea las carpetas de salida cuando aún no existen.
    ARCHIVO_SALIDA_RENTA_FIJA.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO_DETALLE_RENTA_FIJA.parent.mkdir(parents=True, exist_ok=True)

    # Resume la posición diaria por libro, agencia, estructura y moneda.
    libros = posicion.pivot_table(index="Fecha", columns="Book", values="Posición", aggfunc="sum")
    agencias = posicion.pivot_table(index="Fecha", columns="Agencia", values="Posición", aggfunc="sum")
    estructura = posicion.pivot_table(index="Fecha", columns="LB/LT", values="Posición", aggfunc="sum")
    monedas = posicion.pivot_table(index="Fecha", columns="Moneda", values="Posición", aggfunc="sum")

    # Actualiza cada hoja con la historia previa y reemplaza las fechas repetidas.
    with pd.ExcelWriter(ARCHIVO_SALIDA_RENTA_FIJA, engine="openpyxl", mode="w") as writer:
        _actualizar_excel(ARCHIVO_SALIDA_RENTA_FIJA, "Detalle", posicion).to_excel(
            writer,
            sheet_name="Detalle",
            index=True,
        )
        _actualizar_excel(ARCHIVO_SALIDA_RENTA_FIJA, "Libros", libros).to_excel(
            writer,
            sheet_name="Libros",
        )
        _actualizar_excel(ARCHIVO_SALIDA_RENTA_FIJA, "Agencias", agencias).to_excel(
            writer,
            sheet_name="Agencias",
        )
        _actualizar_excel(ARCHIVO_SALIDA_RENTA_FIJA, "Estructura", estructura).to_excel(
            writer,
            sheet_name="Estructura",
        )
        _actualizar_excel(ARCHIVO_SALIDA_RENTA_FIJA, "Moneda", monedas).to_excel(
            writer,
            sheet_name="Moneda",
        )

    # Publica además una copia plana del detalle, sin usar la fecha como índice.
    posicion.reset_index().to_excel(ARCHIVO_DETALLE_RENTA_FIJA, index=False)


def ejecutar_renta_fija(
    fecha_trabajo: str | None = None,
    logger=None,
    confirmar_reemplazo: bool = True,
) -> pd.DataFrame | None:
    """Orquesta la lectura, transformación y exportación completa de renta fija."""
    # 1. Define la fecha que controla el insumo y la actualización de la salida.
    fecha_valor = _normalizar_fecha(fecha_trabajo)
    registrar_log(logger, f"Fecha de trabajo renta fija: {fecha_valor.strftime('%d-%m-%Y')}.")

    # 2. Obtiene de parámetros la ubicación exacta del archivo diario de Vector.
    df_parametros = _cargar_parametros_rutas()
    ruta_local = _ruta_titulos(fecha_valor, df_parametros)

    registrar_log(logger, f"Insumo renta fija esperado por Vector: {ruta_local}")

    # Detiene el proceso con un mensaje claro cuando el insumo no está disponible.
    if not ruta_local.exists():
        raise FileNotFoundError(
            "Vector no dejo el insumo de renta fija para la fecha seleccionada: "
            f"{ruta_local}"
        )

    # 3. Limpia la estructura del archivo y agrega clasificaciones de negocio.
    reporte = _leer_reporte_titulos(ruta_local)
    fechas_informe = reporte["FECHA INFORME"].dropna().dt.normalize().unique()
    if len(fechas_informe) != 1 or pd.Timestamp(fechas_informe[0]) != fecha_valor.normalize():
        fechas_texto = ", ".join(
            pd.Timestamp(fecha).strftime("%d/%m/%Y") for fecha in fechas_informe
        ) or "sin fecha"
        raise ValueError(
            "El reporte de Renta Fija no corresponde al corte solicitado. "
            f"Esperado: {fecha_valor.strftime('%d/%m/%Y')}; encontrado: {fechas_texto}."
        )
    reporte = _enriquecer_reporte(reporte, logger=logger)

    # 4. Construye la tabla canónica y actualiza únicamente la fecha procesada.
    tabla_canonica = _construir_tabla_canonica(reporte)
    tabla_canonica = actualizar_datos_por_fecha(
        ARCHIVO_SALIDA_RENTA_FIJA_TABLA,
        tabla_canonica,
        fecha_valor.strftime("%d-%m-%Y"),
        "FECHA",
        "csv",
        confirmar_reemplazo=confirmar_reemplazo,
    )
    # Permite cancelar sin sobrescribir cuando ya hay datos para la fecha.
    if tabla_canonica is None:
        registrar_log(logger, "Renta fija cancelada por el usuario al detectar una fecha existente.")
        return None

    # Conserva COP, USD, EUR y UVR, incluyendo los registros historicos recuperados desde
    # Tbl_Posicion_Renta_Fija.csv.
    tabla_canonica = _filtrar_monedas_habilitadas(
        tabla_canonica,
        "MONEDA_POSICION",
    )

    # 5. Genera las vistas operativas y guarda la tabla canónica en CSV.
    posicion_operativa = _construir_posicion_operativa(reporte)
    _exportar_resultados_operativos(posicion_operativa)
    guardar_csv_si_posible(tabla_canonica, ARCHIVO_SALIDA_RENTA_FIJA_TABLA, logger=logger)

    registrar_log(logger, f"Tabla renta fija guardada en: {ARCHIVO_SALIDA_RENTA_FIJA_TABLA}")
    registrar_log(logger, f"Workbook renta fija guardado en: {ARCHIVO_SALIDA_RENTA_FIJA}")

    # 6. Replica las tablas relevantes en la base auxiliar para consultas posteriores.
    # ADICION AUXILIAR: replica el detalle y las vistas del workbook en risko_auxiliar.db.
    # La construcción y escritura de los Excel/CSV existentes permanece intacta.
    guardar_tablas_auxiliares_modulo(
        "Renta_Fija",
        fecha_valor,
        {
            "reporte_enriquecido": reporte,
            "posicion_operativa": posicion_operativa.reset_index(),
            "posicion_por_libro": posicion_operativa.pivot_table(
                index="Fecha", columns="Book", values="Posición", aggfunc="sum"
            ).reset_index(),
            "posicion_por_agencia": posicion_operativa.pivot_table(
                index="Fecha", columns="Agencia", values="Posición", aggfunc="sum"
            ).reset_index(),
            "posicion_por_estructura": posicion_operativa.pivot_table(
                index="Fecha", columns="LB/LT", values="Posición", aggfunc="sum"
            ).reset_index(),
            "posicion_por_moneda": posicion_operativa.pivot_table(
                index="Fecha", columns="Moneda", values="Posición", aggfunc="sum"
            ).reset_index(),
            "posicion_canonica": tabla_canonica,
        },
        logger=logger,
    )
    # Devuelve la tabla final para su consumo desde la interfaz u otros módulos.
    return tabla_canonica
