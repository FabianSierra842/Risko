from __future__ import annotations

from pathlib import Path

import pandas as pd


# ──────────────────────────────────────────────────────────────────
# Política de confirmación de reemplazo de datos por fecha.
# Se inyecta para NO acoplar la capa de datos a una GUI: por defecto usa un
# messagebox de tkinter (uso de los scripts standalone), pero una aplicación
# (p. ej. la interfaz Risko) puede sobreescribirla con una política sin ventanas
# modales mediante configurar_confirmador_reemplazo().
# ──────────────────────────────────────────────────────────────────
_confirmador_reemplazo = None  # callable(titulo: str, mensaje: str) -> bool


def configurar_confirmador_reemplazo(callback) -> None:
    """Define cómo se confirma el reemplazo de datos existentes para una fecha.

    callback recibe (titulo, mensaje) y devuelve True para reemplazar.
    Pasar None restaura el comportamiento por defecto (messagebox de tkinter).
    """
    global _confirmador_reemplazo
    _confirmador_reemplazo = callback


def _confirmar_reemplazo_por_defecto(titulo: str, mensaje: str) -> bool:
    """Confirmación por defecto: messagebox de tkinter si hay entorno gráfico."""
    try:
        from tkinter import messagebox
        return bool(messagebox.askyesno(titulo, mensaje))
    except Exception:
        # Sin entorno gráfico disponible: reemplaza por defecto.
        return True


def registrar_log(logger, mensaje: str) -> None:
    if logger is not None:
        logger(mensaje)


def leer_csv(ruta: str | Path, **kwargs) -> pd.DataFrame:
    ruta_archivo = Path(ruta)
    if not ruta_archivo.exists():
        raise FileNotFoundError(f"No se encontro el archivo: {ruta_archivo}")
    return pd.read_csv(ruta_archivo, **kwargs)


def leer_excel(ruta: str | Path, **kwargs) -> pd.DataFrame:
    ruta_archivo = Path(ruta)
    if not ruta_archivo.exists():
        raise FileNotFoundError(f"No se encontro el archivo: {ruta_archivo}")
    return pd.read_excel(ruta_archivo, **kwargs)


def leer_csv_con_codificaciones(
    ruta: str | Path,
    codificaciones: tuple[str, ...] = ("utf-8-sig", "utf-8", "latin1"),
    **kwargs,
) -> pd.DataFrame:
    ultimo_error: Exception | None = None

    for codificacion in codificaciones:
        try:
            return leer_csv(ruta, encoding=codificacion, **kwargs)
        except UnicodeDecodeError as exc:
            ultimo_error = exc

    raise RuntimeError(f"No fue posible leer el archivo CSV: {ruta}") from ultimo_error


def guardar_csv_si_posible(df: pd.DataFrame, ruta: str | Path, logger=None) -> bool:
    """Exporta un CSV sin bloquear el flujo si Excel mantiene abierto el archivo."""
    ruta_archivo = Path(ruta)
    ruta_archivo.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(ruta_archivo, index=False, encoding="utf-8-sig")
    except PermissionError:
        registrar_log(
            logger,
            "No se pudo actualizar el CSV porque esta abierto o bloqueado. "
            f"La tabla queda disponible en la base SQLite: {ruta_archivo}",
        )
        return False
    return True


def actualizar_datos_por_fecha(
    ruta_salida: str | Path,
    df_nuevo: pd.DataFrame,
    fecha_corte,
    columna_fecha: str,
    tipo_archivo: str,
    confirmar_reemplazo: bool = True,
) -> pd.DataFrame | None:
    ruta_salida = Path(ruta_salida)
    if not ruta_salida.exists():
        return df_nuevo.copy()

    if tipo_archivo == "csv":
        df_salida = leer_csv_con_codificaciones(ruta_salida, keep_default_na=False)
    elif tipo_archivo == "xlsx":
        df_salida = leer_excel(ruta_salida, keep_default_na=False)
    else:
        raise ValueError(f"Tipo de archivo no soportado: {tipo_archivo}")

    df_salida.columns = [str(col).strip() for col in df_salida.columns]
    df_nuevo = df_nuevo.copy()
    df_nuevo.columns = [str(col).strip() for col in df_nuevo.columns]

    if columna_fecha not in df_salida.columns:
        return df_nuevo

    columnas_salida = {col.strip(): col for col in df_salida.columns}
    renombrar_columnas = {
        col: columnas_salida[col.strip()]
        for col in df_nuevo.columns
        if col.strip() in columnas_salida
    }
    df_nuevo = df_nuevo.rename(columns=renombrar_columnas)

    columnas_nuevas = [col for col in df_nuevo.columns if col not in df_salida.columns]
    df_nuevo = df_nuevo.reindex(columns=list(df_salida.columns) + columnas_nuevas)

    fecha_corte = pd.to_datetime(fecha_corte, dayfirst=True, errors="coerce").date()
    fechas_salida = pd.to_datetime(
        df_salida[columna_fecha],
        dayfirst=True,
        errors="coerce",
    ).dt.date

    if fecha_corte not in fechas_salida.values:
        return pd.concat([df_salida, df_nuevo], ignore_index=True)

    if confirmar_reemplazo:
        confirmador = _confirmador_reemplazo or _confirmar_reemplazo_por_defecto
        continuar = confirmador(
            "Banco de Bogota",
            "La informacion para la fecha de corte seleccionada ya existe.\n"
            "Desea continuar y reemplazarla?",
        )
        if not continuar:
            return None

    df_salida = df_salida.loc[fechas_salida != fecha_corte]
    return pd.concat([df_salida, df_nuevo], ignore_index=True)
