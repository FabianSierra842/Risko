from __future__ import annotations

from contextlib import closing
from datetime import datetime
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import uuid


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from proyectos.position_monitor.procesos.consolidacion import (
    TABLA_POSICION_ACTUAL,
    TABLA_POSICION_HISTORICO,
    TABLA_POSICION_NOVADOS,
    columnas_tabla_position_monitor,
    consolidar_position_monitor,
    guardar_tabla_producto_position_monitor,
    leer_tabla_position_monitor,
    listar_tablas_position_monitor,
)
from compartido.nucleo_risko.fechas import Es_Dia_Habil
from compartido.nucleo_risko.rutas import (
    ARCHIVO_BASE_DATOS_POSITION_MONITOR,
    ARCHIVO_BASE_DATOS_SPOT_2_CIERRE_PRUEBAS,
    ARCHIVO_PANEL_POSITION_MONITOR_INTRADIA,
    ARCHIVO_CONFIG_RISKO_VECTOR,
    ARCHIVO_VECTOR_PY,
    CARPETA_DASHBOARDS_PORTAL,
    CARPETA_INSUMOS_SPOT_2_CIERRE,
)


# Evita que Windows abra una ventana de consola al lanzar Vector desde una app
# de ventana (sin consola). En otros sistemas el flag no existe y vale 0.
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


FLUJOS_VECTOR_PRODUCTO = {
    "FORWARD": "01_Forward",
    "NOVADOS": "02_Novados",
    "RENTA_FIJA": "03_Renta_Fija",
    "OPCIONES": "04_Opciones",
    "SWAPS": "05_Swaps",
    "SPOT": "06_Spot",
    # TODO: agregar flujos Vector cuando existan los insumos oficiales.
    # "CUBREBONOS": "07_Cubrebonos",
    # "NDFTES": "08_NDFTES",
    # "PP": "09_PP",
}
PRODUCTOS_EJECUCION_TOTAL = (
    "SPOT",
    "NOVADOS",
    "FORWARD",
    "RENTA_FIJA",
    "OPCIONES",
    "SWAPS",
)

# Modulos visibles para validacion individual que todavia no pueden alimentar
# el consolidado ni la corrida diaria de produccion.
PRODUCTOS_SOLO_MODULO_INDIVIDUAL: tuple[str, ...] = ()

# Permanecen fuera de la corrida diaria hasta su liberacion formal.
PRODUCTOS_FUERA_EJECUCION_TOTAL = (
    "CUBREBONOS",
    "NDFTES",
    "PP",
)
FLUJO_VECTOR_INTRADIA = "10_Position_Monitor_Intradia"
FLUJO_VECTOR_SPOT_2_CIERRE_PRUEBAS = "11_Spot_2_Cierre_Pruebas"


def _fecha_trabajo_normalizada(fecha_trabajo: str):
    import pandas as pd

    fecha = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha no valida: {fecha_trabajo}")
    return fecha.normalize()


def _es_fecha_no_habil(fecha_trabajo: str) -> bool:
    return not Es_Dia_Habil(_fecha_trabajo_normalizada(fecha_trabajo).date())


def _productos_ejecucion_total(fecha_trabajo: str) -> tuple[str, ...]:
    _fecha_trabajo_normalizada(fecha_trabajo)
    return PRODUCTOS_EJECUCION_TOTAL


def _arrastrar_ultima_posicion_novados(
    fecha_trabajo: str,
    *,
    pruebas: bool = False,
    logger=None,
):
    """Replica la ultima posicion Novados anterior para un corte no habil."""
    import pandas as pd

    fecha_corte = _fecha_trabajo_normalizada(fecha_trabajo)
    historico = leer_tabla_position_monitor(
        TABLA_POSICION_NOVADOS,
        pruebas=pruebas,
        limite=None,
    )
    if historico is None or historico.empty or "FECHA" not in historico.columns:
        raise FileNotFoundError(
            "No existe una posicion anterior de Novados para trasladar al fin de semana."
        )

    fechas = pd.to_datetime(historico["FECHA"], dayfirst=True, errors="coerce")
    anteriores = fechas.loc[fechas < fecha_corte]
    if anteriores.empty:
        raise ValueError(
            "No existe una posicion de Novados anterior a "
            f"{fecha_corte.strftime('%d/%m/%Y')}."
        )
    fecha_fuente = anteriores.max().normalize()
    tabla = historico.loc[fechas.eq(fecha_fuente)].copy()
    tabla["FECHA"] = fecha_corte.strftime("%d/%m/%Y")
    if logger is not None:
        logger(
            "Novados: fecha no habil; se mantiene sin recalculo la posicion de "
            f"{fecha_fuente.strftime('%d/%m/%Y')} para el corte "
            f"{fecha_corte.strftime('%d/%m/%Y')} ({len(tabla)} filas)."
        )
    return tabla


def listar_tablas_db(pruebas: bool = False) -> list[str]:
    return listar_tablas_position_monitor(pruebas=pruebas)


def _formatos_fecha_sql(fecha_trabajo: str) -> tuple[str, str, str]:
    import pandas as pd

    fecha = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha no valida para consultar la base: {fecha_trabajo}")
    return (
        fecha.strftime("%d/%m/%Y"),
        fecha.strftime("%d-%m-%Y"),
        fecha.strftime("%Y-%m-%d"),
    )


def cargar_tabla_db(
    nombre_tabla: str,
    pruebas: bool = False,
    fecha_trabajo: str | None = None,
    limite: int | None = 5000,
):
    if fecha_trabajo:
        columnas = columnas_tabla_position_monitor(nombre_tabla, pruebas=pruebas)
        columna_fecha = next((col for col in ("FECHA", "CORTE") if col in columnas), None)
        if columna_fecha:
            fechas = _formatos_fecha_sql(fecha_trabajo)
            return leer_tabla_position_monitor(
                nombre_tabla,
                where=f'"{columna_fecha}" IN (?, ?, ?)',
                params=fechas,
                pruebas=pruebas,
                limite=limite,
            )
    return leer_tabla_position_monitor(nombre_tabla, pruebas=pruebas, limite=limite)


def _fecha_para_vector(fecha_trabajo: str) -> str:
    import pandas as pd

    fecha = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha no valida para Vector: {fecha_trabajo}")
    return fecha.strftime("%d/%m/%Y")


def ejecutar_flujo_vector(
    nombre_flujo: str,
    fecha_trabajo: str,
    logger=None,
    obligatorio: bool = True,
) -> None:
    if not ARCHIVO_VECTOR_PY.exists() or not ARCHIVO_CONFIG_RISKO_VECTOR.exists():
        mensaje = (
            "No se encontro la configuracion de Vector para cargar insumos "
            f"({ARCHIVO_VECTOR_PY}, {ARCHIVO_CONFIG_RISKO_VECTOR})."
        )
        if obligatorio:
            raise FileNotFoundError(mensaje)
        if logger:
            logger(mensaje)
        return

    comando = [
        sys.executable,
        str(ARCHIVO_VECTOR_PY),
        "--cli",
        "--config",
        str(ARCHIVO_CONFIG_RISKO_VECTOR),
        "--fecha",
        _fecha_para_vector(fecha_trabajo),
        "--flow-name",
        nombre_flujo,
        "--no-dry-run",
    ]
    if logger:
        logger(f"Vector: ejecutando flujo {nombre_flujo}.")
    resultado = subprocess.run(
        comando,
        cwd=str(RAIZ_RISKO),
        text=True,
        capture_output=True,
        check=False,
        creationflags=_SIN_VENTANA,
    )
    salida = "\n".join(parte for parte in (resultado.stdout, resultado.stderr) if parte.strip())
    if logger and salida.strip():
        for linea in salida.strip().splitlines():
            logger(f"Vector | {linea}")
    if resultado.returncode != 0:
        raise RuntimeError(f"Vector fallo en el flujo {nombre_flujo}.")


def _configuracion_spot_2() -> dict:
    if not ARCHIVO_CONFIG_RISKO_VECTOR.is_file():
        return {}
    with ARCHIVO_CONFIG_RISKO_VECTOR.open("r", encoding="utf-8") as archivo:
        return dict((json.load(archivo).get("spot_2") or {}))


def _spot_2_habilitado_en_cierre() -> bool:
    configuracion = _configuracion_spot_2()
    habilitado = bool(configuracion.get("incluir_en_cierre", False))
    if habilitado and not bool(configuracion.get("posicion_inicial_validada", False)):
        raise ValueError(
            "Spot 2 no puede incluirse en el cierre: primero debe validarse y "
            "marcarse posicion_inicial_validada=true en risko.json."
        )
    return habilitado


def _anexar_spot_2_al_cierre(
    tabla_spot,
    fecha_trabajo: str,
    *,
    fecha_no_habil: bool,
    pruebas: bool,
    logger=None,
):
    """Anexa Spot 2 solo cuando el interruptor de promocion esta habilitado."""
    if not _spot_2_habilitado_en_cierre():
        return tabla_spot

    import pandas as pd
    from proyectos.position_monitor.procesos import spot_2

    if fecha_no_habil:
        tabla_spot_2 = spot_2.arrastrar_spot_acumulado(
            fecha_trabajo,
            logger=logger,
            pruebas=pruebas,
        )
    else:
        tabla_spot_2 = spot_2.ejecutar_spot(
            fecha_trabajo,
            logger=logger,
            pruebas=pruebas,
        )

    resumen_principal = tabla_spot.attrs.get("resumen_spot")
    combinado = pd.concat([tabla_spot, tabla_spot_2], ignore_index=True)
    combinado.attrs["resumen_spot"] = resumen_principal
    combinado.attrs["spot_2"] = tabla_spot_2.attrs.get("resumen_spot")
    if logger:
        logger(
            "Spot 2 incluido en el cierre por configuracion: "
            f"{len(tabla_spot_2)} fila(s) canonica(s)."
        )
    return combinado


def ejecutar_producto(
    producto: str,
    fecha_trabajo: str,
    logger=None,
    cargar_insumos: bool = True,
    consolidar: bool = True,
    pruebas: bool = False,
    retornar_canonica: bool = False,
):
    producto = producto.upper().strip()
    if producto in PRODUCTOS_SOLO_MODULO_INDIVIDUAL and consolidar:
        consolidar = False
        if logger is not None:
            logger(
                f"{producto}: ejecucion individual de pruebas; se omite la "
                "consolidacion de Position Monitor."
            )
    tabla_respuesta = None
    fecha_no_habil = _es_fecha_no_habil(fecha_trabajo)
    if producto == "SPOT" and fecha_no_habil:
        from proyectos.position_monitor.procesos.spot import arrastrar_spot_acumulado

        tabla = arrastrar_spot_acumulado(
            fecha_trabajo,
            logger=logger,
            pruebas=pruebas,
        )
        tabla_respuesta = tabla.attrs.get("resumen_spot")
        tabla = _anexar_spot_2_al_cierre(
            tabla,
            fecha_trabajo,
            fecha_no_habil=True,
            pruebas=pruebas,
            logger=logger,
        )
    elif producto == "NOVADOS" and fecha_no_habil:
        tabla = _arrastrar_ultima_posicion_novados(
            fecha_trabajo,
            pruebas=pruebas,
            logger=logger,
        )
    else:
        if cargar_insumos and producto in FLUJOS_VECTOR_PRODUCTO:
            if producto == "FORWARD" and fecha_no_habil:
                from proyectos.position_monitor.procesos.forward import (
                    preparar_insumos_forward,
                )

                preparar_insumos_forward(fecha_trabajo, logger=logger)
            elif producto == "RENTA_FIJA" and fecha_no_habil:
                from proyectos.position_monitor.procesos.renta_fija import (
                    preparar_insumo_renta_fija,
                )

                preparar_insumo_renta_fija(fecha_trabajo, logger=logger)
            else:
                ejecutar_flujo_vector(
                    FLUJOS_VECTOR_PRODUCTO[producto],
                    fecha_trabajo,
                    logger=logger,
                )

        if producto == "NOVADOS":
            from proyectos.position_monitor.procesos.novados import ejecutar_novados

            tabla = ejecutar_novados(fecha_trabajo, logger=logger)
        elif producto == "FORWARD":
            from proyectos.position_monitor.procesos.forward import ejecutar_forward

            tabla = ejecutar_forward(fecha_trabajo, logger=logger)
        elif producto == "OPCIONES":
            from proyectos.position_monitor.procesos.opciones import ejecutar_opciones

            tabla = ejecutar_opciones(fecha_trabajo, logger=logger)
        elif producto == "RENTA_FIJA":
            from proyectos.position_monitor.procesos.renta_fija import ejecutar_renta_fija

            tabla = ejecutar_renta_fija(fecha_trabajo, logger=logger)
        elif producto == "SWAPS":
            from proyectos.position_monitor.procesos.swaps import ejecutar_swaps

            tabla = ejecutar_swaps(fecha_trabajo, logger=logger)
        elif producto == "SPOT":
            from proyectos.position_monitor.procesos.spot import ejecutar_spot

            tabla = ejecutar_spot(fecha_trabajo, logger=logger, pruebas=pruebas)
            tabla_respuesta = tabla.attrs.get("resumen_spot")
            tabla = _anexar_spot_2_al_cierre(
                tabla,
                fecha_trabajo,
                fecha_no_habil=False,
                pruebas=pruebas,
                logger=logger,
            )
        elif producto == "CUBREBONOS":
            from proyectos.position_monitor.procesos.cubrebonos import ejecutar_cubrebonos

            tabla = ejecutar_cubrebonos(fecha_trabajo, logger=logger)
        elif producto == "NDFTES":
            from proyectos.position_monitor.procesos.ndftes import ejecutar_ndftes

            tabla = ejecutar_ndftes(fecha_trabajo, logger=logger)
        elif producto == "PP":
            from proyectos.position_monitor.procesos.pp import ejecutar_pp

            tabla = ejecutar_pp(fecha_trabajo, logger=logger)
        else:
            raise ValueError(f"Producto no soportado: {producto}")

    if tabla is None:
        return None

    guardar_tabla_producto_position_monitor(
        producto,
        tabla,
        fecha_trabajo,
        pruebas=pruebas,
        logger=logger,
    )

    if consolidar and not tabla.empty:
        consolidar_position_monitor(
            fecha_corte=fecha_trabajo,
            tablas=[tabla],
            logger=logger,
            pruebas=pruebas,
        )
    elif tabla.empty and logger is not None:
        logger(f"{producto}: tabla canonica vacia; se actualizo la tabla de producto y se omitio consolidacion.")
    if retornar_canonica:
        return tabla
    return tabla_respuesta if tabla_respuesta is not None else tabla


def importar_iniciales_spot_desde_excel(
    logger=None,
    pruebas: bool = False,
):
    """Importa las anclas desde el Excel parametrico propio de Risko."""
    from proyectos.position_monitor.procesos.spot import (
        importar_posiciones_iniciales_excel,
    )

    return importar_posiciones_iniciales_excel(pruebas=pruebas, logger=logger)


def _inicializar_base_spot_2_cierre_pruebas() -> Path:
    """Crea una copia SQLite aislada una sola vez para probar Spot 2 al cierre."""
    destino = ARCHIVO_BASE_DATOS_SPOT_2_CIERRE_PRUEBAS
    if destino.is_file():
        return destino
    if not ARCHIVO_BASE_DATOS_POSITION_MONITOR.is_file():
        raise FileNotFoundError(
            f"No existe la base de cierre para inicializar Spot 2: {ARCHIVO_BASE_DATOS_POSITION_MONITOR}"
        )

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")
    try:
        with closing(sqlite3.connect(str(ARCHIVO_BASE_DATOS_POSITION_MONITOR))) as origen, closing(
            sqlite3.connect(str(temporal))
        ) as copia:
            origen.backup(copia)
        os.replace(temporal, destino)
    finally:
        if temporal.exists():
            temporal.unlink()
    return destino


def ejecutar_spot_2_cierre_pruebas(
    fecha_trabajo: str,
    logger=None,
    *,
    cargar_insumo: bool = True,
) -> dict:
    """Ejecuta Spot 2 con Caja de cierre; no consolida ni publica posicion."""
    fecha = _fecha_trabajo_normalizada(fecha_trabajo)
    fecha_no_habil = not Es_Dia_Habil(fecha.date())
    if cargar_insumo and not fecha_no_habil:
        ejecutar_flujo_vector(
            FLUJO_VECTOR_SPOT_2_CIERRE_PRUEBAS,
            fecha_trabajo,
            logger=logger,
        )

    from proyectos.position_monitor.procesos.intradia import seleccionar_archivo_intradia
    from proyectos.position_monitor.procesos.spot_2 import (
        arrastrar_spot_acumulado,
        ejecutar_spot,
    )

    ruta_insumo = None
    if not fecha_no_habil:
        ruta_insumo = seleccionar_archivo_intradia(
            CARPETA_INSUMOS_SPOT_2_CIERRE,
            f"Cierre_ReporteCaja_{fecha:%d%m%y}_*.xls",
            tamano_minimo_bytes=1024,
        )
    ruta_db = _inicializar_base_spot_2_cierre_pruebas()
    if logger:
        fuente = ruta_insumo.name if ruta_insumo is not None else "carry-forward sin archivo"
        logger(f"Spot 2 cierre aislado: fuente {fuente}.")
        logger(f"Spot 2 cierre aislado: base de pruebas {ruta_db}.")

    if fecha_no_habil:
        tabla = arrastrar_spot_acumulado(
            fecha.strftime("%d-%m-%Y"),
            logger=logger,
            ruta_db=ruta_db,
        )
    else:
        tabla = ejecutar_spot(
            fecha.strftime("%d-%m-%Y"),
            logger=logger,
            ruta_db=ruta_db,
            ruta_insumo=ruta_insumo,
        )
    return {
        "tabla": tabla,
        "resumen": tabla.attrs.get("resumen_spot"),
        "ruta_db": ruta_db,
        "ruta_insumo": ruta_insumo,
        "tipo_corte": "CIERRE_CARRY" if fecha_no_habil else "CIERRE_ARCHIVO",
        "publicado": False,
    }


def limpiar_insumos_risko(fecha_trabajo: str, logger=None) -> None:
    ejecutar_flujo_vector("00_Limpiar_Insumos", fecha_trabajo, logger=logger)


def ejecutar_todo_position_monitor(
    fecha_trabajo: str,
    ruta_dashy: str | None = None,
    logger=None,
    limpiar_insumos: bool = True,
    pruebas: bool = False,
):
    tablas = []
    if limpiar_insumos:
        limpiar_insumos_risko(fecha_trabajo, logger=logger)

    productos = _productos_ejecucion_total(fecha_trabajo)
    if logger and _es_fecha_no_habil(fecha_trabajo):
        logger(
            "Fecha no habil: Spot se incluye con la misma posicion acumulada "
            "del ultimo corte disponible, sin cargar un nuevo flujo de caja."
        )

    for producto in productos:
        if logger:
            logger(f"Ejecutando modulo completo: {producto}.")
        tabla = ejecutar_producto(
            producto,
            fecha_trabajo,
            logger=logger,
            cargar_insumos=True,
            consolidar=False,
            pruebas=pruebas,
            retornar_canonica=True,
        )
        if tabla is not None:
            tablas.append(tabla)

    tablas_con_filas = [tabla for tabla in tablas if tabla is not None and not tabla.empty]
    rutas = consolidar_position_monitor(
        fecha_corte=fecha_trabajo,
        tablas=tablas_con_filas,
        logger=logger,
        pruebas=pruebas,
    )
    salida = generar_tablero(
        fecha_trabajo,
        ruta_dashy=ruta_dashy,
        logger=logger,
        consolidar=False,
        pruebas=pruebas,
    )
    return {"tablas": tablas, "rutas": rutas, "dashboard": salida}


def ejecutar_intradia_position_monitor(
    fecha_trabajo: str,
    ruta_dashy: str | None = None,
    logger=None,
    *,
    cargar_insumos: bool = True,
    publicar: bool = False,
) -> dict:
    """Calcula el corte Banking intradía en aislamiento del cierre oficial."""
    if cargar_insumos:
        ejecutar_flujo_vector(
            FLUJO_VECTOR_INTRADIA,
            fecha_trabajo,
            logger=logger,
        )

    from proyectos.position_monitor.procesos.intradia import (
        calcular_position_monitor_intradia,
    )
    from proyectos.position_monitor.tableros.panel_position_monitor import (
        build_dashboard,
        read_historical_position_data,
    )

    resultado = calcular_position_monitor_intradia(fecha_trabajo, logger=logger)
    if logger is not None:
        logger(
            "Intradía: el promedio SETFX "
            f"{resultado.promedio_setfx:,.6f} es la única tasa usada para "
            "Opciones y para calibrar los ejes COP/USD; no se consulta TRM FORMADA."
        )
    historico = read_historical_position_data(pruebas=False)
    historico = historico.loc[
        historico["BANKING_CVA_DVA"].astype(str).str.strip().str.upper().eq("BANKING")
    ].copy()
    salida = build_dashboard(
        ruta_dashy=ruta_dashy,
        fecha_publicacion=datetime.now().astimezone().isoformat(timespec="seconds"),
        current_df=resultado.posicion,
        historical_df=historico,
        output_path=ARCHIVO_PANEL_POSITION_MONITOR_INTRADIA,
        estado_corte=resultado.estado,
        productos_pendientes=resultado.productos_pendientes,
        promedio_setfx=resultado.promedio_setfx,
        advertencias=[
            item["detalle"]
            for item in resultado.calidad
            if item.get("estado", "").upper() not in {"OK", "COMPLETADO"}
        ],
    )
    publicacion = None
    if publicar:
        publicacion = publicar_tablero(
            fecha_trabajo,
            ruta_dashy=ruta_dashy,
            logger=logger,
            html_origen=salida,
            pruebas=False,
            estado_corte=resultado.estado,
            vista_contable=resultado.vista_contable,
            productos_incluidos=sorted(resultado.posicion["PRODUCTO"].unique().tolist()),
            productos_pendientes=resultado.productos_pendientes,
            fechas_datos_override=[resultado.fecha],
            fuentes=resultado.fuentes,
            calidad=resultado.calidad,
        )
    return {
        "tabla": resultado.posicion,
        "resultado": resultado,
        "dashboard": salida,
        "publicacion": publicacion,
    }


def consolidar_posicion(fecha_trabajo: str, logger=None, pruebas: bool = False) -> dict:
    """Consolida todas las tablas procesadas existentes para la fecha indicada."""
    return consolidar_position_monitor(fecha_corte=fecha_trabajo, logger=logger, pruebas=pruebas)


def cargar_posicion_actual(fecha_trabajo: str | None = None, pruebas: bool = False):
    return cargar_tabla_db(
        TABLA_POSICION_ACTUAL,
        pruebas=pruebas,
        fecha_trabajo=fecha_trabajo,
        limite=None,
    )


def cargar_posicion_historica(fecha_trabajo: str | None = None, pruebas: bool = False):
    return cargar_tabla_db(
        TABLA_POSICION_HISTORICO,
        pruebas=pruebas,
        fecha_trabajo=fecha_trabajo,
        limite=None,
    )


def generar_tablero(
    fecha_trabajo: str | None = None,
    ruta_dashy: str | None = None,
    logger=None,
    consolidar: bool = True,
    pruebas: bool = False,
):
    from proyectos.position_monitor.tableros.panel_position_monitor import build_dashboard

    if consolidar:
        consolidar_position_monitor(fecha_corte=fecha_trabajo, logger=logger, pruebas=pruebas)
    fecha_generacion = datetime.now().astimezone().isoformat(timespec="seconds")
    salida = build_dashboard(
        ruta_dashy=ruta_dashy,
        pruebas=pruebas,
        fecha_publicacion=fecha_generacion,
    )
    if logger is not None:
        logger(f"Tablero generado en: {salida}")
    return salida


def _fecha_posicion_iso(fecha_trabajo: str) -> str:
    import pandas as pd

    fecha = pd.to_datetime(fecha_trabajo, dayfirst=True, errors="coerce")
    if pd.isna(fecha):
        raise ValueError(f"Fecha de posicion no valida: {fecha_trabajo}")
    return fecha.date().isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _fechas_posiciones_actuales(pruebas: bool = False) -> list[str]:
    import pandas as pd

    tabla = cargar_posicion_actual(pruebas=pruebas)
    if tabla is None or tabla.empty or "FECHA" not in tabla.columns:
        return []
    valores = pd.to_datetime(tabla["FECHA"], dayfirst=True, errors="coerce").dropna()
    return sorted({fecha.date().isoformat() for fecha in valores})


def publicar_tablero(
    fecha_trabajo: str,
    ruta_dashy: str | None = None,
    logger=None,
    html_origen: str | Path | None = None,
    pruebas: bool = False,
    estado_corte: str = "CIERRE",
    vista_contable: str | None = None,
    productos_incluidos: list[str] | None = None,
    productos_pendientes: list[str] | None = None,
    fechas_datos_override: list[str] | None = None,
    fuentes: dict | None = None,
    calidad: list[dict] | None = None,
) -> dict:
    """
    Publica atomically Portfolio Position Monitor en la biblioteca del portal.

    La fecha seleccionada identifica la posicion solicitada y su carpeta. La
    fecha efectiva contenida en los datos y la fecha real de publicacion se
    registran por separado para mantener la trazabilidad.
    """
    if pruebas:
        raise ValueError(
            "La base de pruebas no se puede publicar en el portal de produccion."
        )

    fecha_posicion = _fecha_posicion_iso(fecha_trabajo)
    origen = Path(html_origen) if html_origen else Path(
        generar_tablero(
            fecha_trabajo,
            ruta_dashy=ruta_dashy,
            logger=logger,
            consolidar=False,
            pruebas=False,
        )
    )
    origen = origen.resolve()
    if not origen.is_file():
        raise FileNotFoundError(f"No se encontro el HTML para publicar: {origen}")

    carpeta_dashboard = CARPETA_DASHBOARDS_PORTAL / "Portfolio Position Monitor"
    carpeta_destino = carpeta_dashboard / fecha_posicion
    carpeta_destino.mkdir(parents=True, exist_ok=True)
    destino = carpeta_destino / "portfolio_position_monitor.html"

    # Este manifiesto hace explícita la integración opcional con las
    # configuraciones del Portal. Los dashboards que no lo tengan se publican
    # en modo simple y se identifican solamente por carpeta y fecha.
    dashboard_manifest = {
        "schema_version": 1,
        "id": "portfolio-position-monitor",
        "nombre": "Portfolio Position Monitor",
        "descripcion": "Posición consolidada de Tesorería por fecha, incluidos cortes intradía identificados como preliminares.",
        "cobertura": "Riesgo de Mercado",
        "audiencia": "Tesorería",
        "archivo": "portfolio_position_monitor.html",
        "configuracion": {"habilitada": True},
    }
    manifest_path = carpeta_dashboard / "dashboard.json"
    temporal_manifest = carpeta_dashboard / (
        f".{manifest_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporal_manifest.write_text(
            json.dumps(dashboard_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporal_manifest, manifest_path)
    finally:
        if temporal_manifest.exists():
            temporal_manifest.unlink()

    temporal_html = carpeta_destino / (
        f".{destino.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        shutil.copyfile(origen, temporal_html)
        os.replace(temporal_html, destino)
    finally:
        if temporal_html.exists():
            temporal_html.unlink()

    fechas_datos = (
        sorted(set(fechas_datos_override))
        if fechas_datos_override is not None
        else _fechas_posiciones_actuales(pruebas=False)
    )
    ahora = datetime.now().astimezone()
    fecha_publicacion = ahora.date().isoformat()
    publicado_en = ahora.isoformat(timespec="seconds")
    metadata = {
        "schema_version": 1,
        "dashboard": "Portfolio Position Monitor",
        "fecha_posicion_solicitada": fecha_posicion,
        "fecha_publicacion": fecha_publicacion,
        "fechas_datos": fechas_datos,
        "archivo": destino.name,
        "sha256": _sha256(destino),
        "tamano_bytes": destino.stat().st_size,
        "publicado_en": publicado_en,
        "publicado_por": (
            f"{os.environ.get('USERDOMAIN', socket.gethostname())}"
            f"\\{os.environ.get('USERNAME', getpass.getuser())}"
        ),
        "origen_desarrollo": str(origen),
        "estado": estado_corte,
        "tipo_corte": (
            "INTRADÍA"
            if str(estado_corte).upper() in {"INTRADIA", "INTRADÍA", "PRELIMINAR_INTRADIA"}
            else "CIERRE"
        ),
        "vista_contable": vista_contable,
        "productos_incluidos": productos_incluidos or [],
        "productos_pendientes": productos_pendientes or [],
        "fuentes": fuentes or {},
        "calidad": calidad or [],
    }
    metadata_path = carpeta_destino / "publicacion.json"
    temporal_metadata = carpeta_destino / (
        f".{metadata_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporal_metadata.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporal_metadata, metadata_path)
    finally:
        if temporal_metadata.exists():
            temporal_metadata.unlink()

    if logger is not None:
        logger(f"Tablero publicado en: {destino}")
        if fechas_datos and fecha_posicion not in fechas_datos:
            logger(
                "ADVERTENCIA: la fecha de posicion solicitada es "
                f"{fecha_posicion}, pero las posiciones actuales corresponden a "
                f"{', '.join(fechas_datos)}."
            )

    return {
        "html": destino,
        "metadata": metadata_path,
        "fecha_posicion": fecha_posicion,
        "fecha_publicacion": fecha_publicacion,
        "fechas_datos": fechas_datos,
        "sha256": metadata["sha256"],
    }
