from __future__ import annotations

from pathlib import Path
import sys
import unicodedata

import pandas as pd


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from compartido.nucleo_risko.archivos import leer_csv, registrar_log
from compartido.nucleo_risko.rutas import ARCHIVO_PARAM_LIBROS


COLUMNAS_PARAM_LIBROS = [
    "PRODUCTO",
    "BOOK",
    "LB_BT",
    "BOOK_HOMOL",
    "LB_LT",
    "INSTRUMENTO",
    "MONEDA_POSICION",
]

COLUMNA_ACTIVO = "ACTIVO"

VALOR_LB_LT_NO_DEFINIDO = "No definido"

MAPA_PRODUCTOS = {
    "NOVADO": "Novados",
    "NOVADOS": "Novados",
    "FORWARD": "Forward",
    "OPCION": "Opciones",
    "OPCIONES": "Opciones",
    "SWAP": "Swap",
    "SWAPS": "Swap",
    "TITULO": "Titulos",
    "TITULOS": "Titulos",
    "RENTA_FIJA": "Titulos",
    "SPOT": "Spot",
    "CUBREBONOS": "Cubrebonos",
    "CUBRE_BONOS": "Cubrebonos",
    "NDFTES": "NDFTES",
    "NDF_TES": "NDFTES",
    "PP": "PP",
}


def _normalizar_texto_clave(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.upper()
    texto = "".join(caracter if caracter.isalnum() else "_" for caracter in texto)
    while "__" in texto:
        texto = texto.replace("__", "_")
    return texto.strip("_")


def normalizar_clave_param(valor: object) -> str:
    """Normaliza BOOK/posicion con la misma regla usada por param_libros."""
    return _normalizar_texto_clave(valor)


def normalizar_producto_param(valor: object) -> str:
    texto = str(valor).strip()
    clave = _normalizar_texto_clave(texto)
    if not clave:
        return texto
    return MAPA_PRODUCTOS.get(clave, texto)


def _normalizar_serie_texto(serie: pd.Series) -> pd.Series:
    return serie.fillna("").astype(str).str.strip().replace({"nan": "", "None": ""})


def cargar_parametros_libros() -> pd.DataFrame:
    df_parametros = leer_csv(ARCHIVO_PARAM_LIBROS, sep=",", encoding="latin-1")
    df_parametros = df_parametros.copy()
    df_parametros.columns = [str(columna).strip() for columna in df_parametros.columns]

    faltantes = [columna for columna in COLUMNAS_PARAM_LIBROS if columna not in df_parametros.columns]
    if faltantes:
        raise ValueError(
            "param_libros.csv no contiene todas las columnas requeridas. "
            f"Faltan: {', '.join(faltantes)}"
        )

    for columna in COLUMNAS_PARAM_LIBROS:
        df_parametros[columna] = _normalizar_serie_texto(df_parametros[columna])

    # ACTIVO es opcional para no romper los productos existentes. Cuando la
    # columna o el valor no existe, la definicion conserva el comportamiento
    # historico y se considera activa. Spot si la usa como fuente de verdad.
    if COLUMNA_ACTIVO not in df_parametros.columns:
        df_parametros[COLUMNA_ACTIVO] = "SI"
    else:
        df_parametros[COLUMNA_ACTIVO] = _normalizar_serie_texto(
            df_parametros[COLUMNA_ACTIVO]
        ).replace({"": "SI"})

    df_parametros["PRODUCTO"] = df_parametros["PRODUCTO"].apply(normalizar_producto_param)
    df_parametros["_PRODUCTO_CLAVE"] = df_parametros["PRODUCTO"].apply(_normalizar_texto_clave)
    df_parametros["_BOOK_CLAVE"] = df_parametros["BOOK"].apply(_normalizar_texto_clave)
    df_parametros["_BOOK_HOMOL_CLAVE"] = df_parametros["BOOK_HOMOL"].apply(_normalizar_texto_clave)
    df_parametros["_MONEDA_CLAVE"] = df_parametros["MONEDA_POSICION"].apply(
        _normalizar_texto_clave
    )

    duplicados = (
        # Un mismo BOOK puede tener una fila por moneda (caso NDFTES). Lo que
        # no se permite es duplicar exactamente producto + book + moneda.
        df_parametros.groupby(
            ["_PRODUCTO_CLAVE", "_BOOK_CLAVE", "_MONEDA_CLAVE"],
            dropna=False,
        )
        .size()
        .reset_index(name="FILAS")
    )
    duplicados = duplicados.loc[duplicados["FILAS"] > 1]
    if not duplicados.empty:
        raise ValueError(
            "param_libros.csv tiene definiciones duplicadas por PRODUCTO + BOOK + MONEDA. "
            f"Registros: {duplicados.to_dict(orient='records')}"
        )

    return df_parametros


def enriquecer_con_parametros_libros(
    df_base: pd.DataFrame,
    producto: str,
    logger=None,
    default_lb_lt: str = VALOR_LB_LT_NO_DEFINIDO,
    default_instrumento: str | None = None,
    default_moneda_posicion: str | None = None,
) -> pd.DataFrame:
    if "BOOK" not in df_base.columns:
        raise ValueError("La tabla base debe contener la columna BOOK para homologar param_libros.")

    df_base = df_base.copy()
    df_base["BOOK"] = _normalizar_serie_texto(df_base["BOOK"])
    df_base["_BOOK_CLAVE"] = df_base["BOOK"].apply(_normalizar_texto_clave)

    producto_canonico = normalizar_producto_param(producto)
    producto_clave = _normalizar_texto_clave(producto_canonico)
    df_parametros = cargar_parametros_libros()
    df_producto = df_parametros.loc[
        df_parametros["_PRODUCTO_CLAVE"] == producto_clave,
        [
            "_BOOK_CLAVE",
            "_BOOK_HOMOL_CLAVE",
            "BOOK_HOMOL",
            "LB_LT",
            "INSTRUMENTO",
            "MONEDA_POSICION",
        ],
    ].rename(
        columns={
            "BOOK_HOMOL": "BOOK_HOMOL_PARAM",
            "LB_LT": "LB_LT_PARAM",
            "INSTRUMENTO": "INSTRUMENTO_PARAM",
            "MONEDA_POSICION": "MONEDA_POSICION_PARAM",
        }
    ).copy()

    df_lookup = pd.concat(
        [
            df_producto.assign(_LOOKUP_CLAVE=df_producto["_BOOK_CLAVE"]),
            df_producto.loc[
                _normalizar_serie_texto(df_producto["BOOK_HOMOL_PARAM"]).ne("")
            ].assign(_LOOKUP_CLAVE=df_producto["_BOOK_HOMOL_CLAVE"]),
        ],
        ignore_index=True,
    )
    columnas_consistencia = [
        "BOOK_HOMOL_PARAM",
        "LB_LT_PARAM",
        "INSTRUMENTO_PARAM",
        "MONEDA_POSICION_PARAM",
    ]
    conflictos_lookup = []
    for lookup_clave, grupo in df_lookup.groupby("_LOOKUP_CLAVE", dropna=False):
        if not lookup_clave:
            continue
        for columna in columnas_consistencia:
            valores = [valor for valor in _normalizar_serie_texto(grupo[columna]).unique().tolist() if valor]
            if len(valores) > 1:
                conflictos_lookup.append(
                    {"LOOKUP": lookup_clave, "COLUMNA": columna, "VALORES": valores}
                )
    if conflictos_lookup:
        raise ValueError(
            "param_libros.csv tiene definiciones incompatibles para una misma llave de busqueda. "
            f"Conflictos: {conflictos_lookup}"
        )
    df_lookup = df_lookup.drop_duplicates(subset="_LOOKUP_CLAVE", keep="first")

    df = df_base.merge(
        df_lookup.drop(columns=["_BOOK_CLAVE", "_BOOK_HOMOL_CLAVE"], errors="ignore"),
        left_on="_BOOK_CLAVE",
        right_on="_LOOKUP_CLAVE",
        how="left",
    )

    libros_sin_mapa = (
        df.loc[_normalizar_serie_texto(df["LB_LT_PARAM"]).eq(""), "BOOK"]
        .drop_duplicates()
        .tolist()
    )
    if libros_sin_mapa:
        registrar_log(
            logger,
            "ALERTA mapa_lb_lt: no se encontro definicion en param_libros.csv para "
            f"{producto_canonico} en los BOOK: {', '.join(libros_sin_mapa)}. "
            "Se publicaran con LB_LT = 'No definido'.",
        )

    book_homol = _normalizar_serie_texto(df["BOOK_HOMOL_PARAM"])
    df["BOOK"] = book_homol.where(book_homol.ne(""), df["BOOK"])

    lb_lt_param = _normalizar_serie_texto(df["LB_LT_PARAM"])
    lb_lt_base = _normalizar_serie_texto(df["LB_LT"]) if "LB_LT" in df.columns else pd.Series("", index=df.index)
    df["LB_LT"] = lb_lt_param.where(
        lb_lt_param.ne(""),
        lb_lt_base.where(lb_lt_base.ne(""), default_lb_lt),
    )

    if default_instrumento is not None:
        instrumento_param = _normalizar_serie_texto(df["INSTRUMENTO_PARAM"])
        instrumento_base = (
            _normalizar_serie_texto(df["INSTRUMENTO"])
            if "INSTRUMENTO" in df.columns
            else pd.Series("", index=df.index)
        )
        df["INSTRUMENTO"] = instrumento_param.where(
            instrumento_param.ne(""),
            instrumento_base.where(instrumento_base.ne(""), default_instrumento),
        )

    if default_moneda_posicion is not None:
        moneda_param = _normalizar_serie_texto(df["MONEDA_POSICION_PARAM"])
        moneda_base = (
            _normalizar_serie_texto(df["MONEDA_POSICION"])
            if "MONEDA_POSICION" in df.columns
            else pd.Series("", index=df.index)
        )
        df["MONEDA_POSICION"] = moneda_param.where(
            moneda_param.ne(""),
            moneda_base.where(moneda_base.ne(""), default_moneda_posicion),
        )

    return df.drop(
        columns=[
            "_BOOK_CLAVE",
            "_LOOKUP_CLAVE",
            "BOOK_HOMOL_PARAM",
            "LB_LT_PARAM",
            "INSTRUMENTO_PARAM",
            "MONEDA_POSICION_PARAM",
        ],
        errors="ignore",
    )
