"""Posicion acumulada de ``SPOT_CLIENTE`` a partir del Reporte de Caja.

Este archivo es la variante experimental ``Spot 2``. Esta separado de
``spot.py`` para poder probar el book SPOT_CLIENTE sin incluirlo todavia en la
posicion oficial ni en el intradia.

MAPA DEL FLUJO, PASO A PASO
===========================

1. :func:`ejecutar_spot` recibe la fecha, la base SQLite y el archivo de cierre.
2. :func:`_cargar_configuracion_spot` obtiene los DmOwnerTable permitidos.
3. :func:`_cargar_parametros_spot` carga el mapeo exclusivo de SPOT_CLIENTE.
4. Se calculan hashes del archivo y los parametros para evitar duplicados.
5. :func:`_leer_movimientos` filtra: owner permitido, USD, TRADE DATE del corte
   y BOOK=SPOT_CLIENTE.
6. ``Amount > 0`` se clasifica como compra y ``Amount < 0`` como venta.
7. Los movimientos se guardan con trazabilidad; una version anterior del mismo
   corte se conserva, pero se marca como no vigente.
8. :func:`_recalcular_posicion` aplica la formula:
   ``posicion_final = posicion_anterior + compras - ventas``.
9. Si falta la posicion anterior, se usa cero solo para continuar la prueba y
   se genera ``MISSING_PREVIOUS_POSITION``. Ese cero NO es un saldo oficial.
10. Los dias sin archivo se completan con ``CARRY_FORWARD``: compras y ventas
    cero, conservando el saldo del dia anterior.
11. :func:`_tabla_canonica` transforma el acumulado al formato Position Monitor.
12. Las tablas auxiliares, alertas y auditoria permiten reconstruir cada cambio.

DONDE HACER CAMBIOS
===================

* Book, nombre homologado, LB/LT, instrumento, moneda y estado activo:
  ``configuracion/param_spot_2.csv``. Para este book el instrumento es ``SPOT``.
* Owner tables admitidas y futura promocion al cierre: ``configuracion/risko.json``.
* Posicion inicial: usar :func:`registrar_posiciones_iniciales`; no escribirla
  directamente en SQLite ni reemplazar el cero dentro del motor.
* Signo de compra/venta y formula acumulada: son reglas financieras dentro de
  :func:`_leer_movimientos` y :func:`_recalcular_posicion`. Cambiarlas requiere
  conciliacion antes de habilitar ``incluir_en_cierre``.

La fuente Summit tiene extension ``.xls``, pero internamente es texto separado
por punto y coma. Los importes se calculan con :class:`Decimal` y se guardan
como texto decimal en SQLite para no introducir redondeos binarios.
"""

from __future__ import annotations

import csv
from contextlib import closing
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import getpass
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pandas as pd


RAIZ_RISKO = Path(__file__).resolve().parents[3]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0, str(RAIZ_RISKO))

from compartido.nucleo_risko.archivos import registrar_log
from compartido.nucleo_risko.base_datos import conectar_sqlite
from compartido.nucleo_risko.tablas_auxiliares import guardar_tablas_auxiliares_modulo
from compartido.nucleo_risko.rutas import (
    ARCHIVO_BASE_DATOS_POSITION_MONITOR,
    ARCHIVO_BASE_DATOS_RISKO_PRUEBAS,
    ARCHIVO_CONFIG_RISKO_VECTOR,
    ARCHIVO_PARAM_SPOT_2,
    CARPETA_INSUMOS,
)
from proyectos.position_monitor.procesos.parametros_libros import (
    cargar_parametros_libros,
    normalizar_clave_param,
)


# PUNTO DE CAMBIO CONTROLADO: este modulo procesa un solo book. Si se quiere
# agregar otro book, no basta con cambiar esta constante: se debe crear su mapeo
# y validar que no lo este procesando tambien spot.py para evitar doble conteo.
BOOK_OBJETIVO = "SPOT_CLIENTE"
ARCHIVO_INTERMEDIO_SPOT_2 = (
    RAIZ_RISKO
    / "datos"
    / "position_monitor"
    / "procesados"
    / "spot2_prueba.xlsx"
)

# AISLAMIENTO: estas tablas tienen nombres propios de SPOT_CLIENTE. No renombrar
# despues de comenzar las pruebas, pues se perderia la continuidad historica y
# la idempotencia veria la nueva tabla como si fuera una ejecucion inicial.
TABLA_HISTORICO_SPOT = "tbl_posicion_spot_cliente_acumulada"
TABLA_MOVIMIENTOS_SPOT = "tbl_movimientos_spot_cliente"
TABLA_ALERTAS_SPOT = "tbl_alertas_spot_cliente"
TABLA_EJECUCIONES_SPOT = "tbl_ejecuciones_spot_cliente"
TABLA_AUDITORIA_SPOT = "tbl_auditoria_spot_cliente"
TABLA_COMPRAS_VENTAS_BOOK_SPOT = "tbl_compras_ventas_spot_cliente_book"

ORIGEN_MOVIMIENTOS = "MOVIMIENTOS"
ORIGEN_CARRY = "CARRY_FORWARD"
ORIGEN_EXCEL = "EXCEL_INICIAL"
ORIGEN_INICIAL_CERO = "INICIAL_CERO"

CODIGOS_ALERTA = {
    "UNKNOWN_BOOK",
    "INACTIVE_BOOK",
    "MISSING_PREVIOUS_POSITION",
    "DUPLICATE_SOURCE_FILE",
    "SOURCE_FILE_CHANGE",
    "INVALID_AMOUNT",
    "INVALID_DATE",
    "HISTORICAL_REPROCESSING",
    "INITIAL_POSITION_CHANGE",
}

# PUNTO DE CAMBIO: la lista operativa se puede sobrescribir en risko.json,
# ``spot.owner_tables_incluidas``. Estos son solo valores de respaldo.
OWNER_TABLES_POR_DEFECTO = {
    "CONTADO",
    "FXFWD",
    "FXOPT_TR",
    "FXSPOT",
    "MM",
    "NOVADO",
    "SWAP",
}

# CONTRATO DEL INSUMO: si Summit cambia un encabezado, se ajusta aqui y se debe
# revisar tambien el acceso por nombre dentro de _leer_movimientos.
COLUMNAS_REQUERIDAS = (
    "GeneratedPK",
    "DmOwnerTable",
    "TradeId",
    "Book",
    "Desk",
    "EvType",
    "SettleCcy",
    "Amount",
    "TRADE DATE",
)
# Cambiar esta version cuando un filtro o formula altere el resultado para el
# mismo archivo. Al incluirla en la huella, el contrato nuevo se reprocesa.
VERSION_CONTRATO_CALCULO = "SPOT_2_TRADE_DATE_V1"



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

_ACTIVOS = {"SI", "S", "TRUE", "1", "ACTIVO", "ACTIVA", "YES"}
_INACTIVOS = {"NO", "N", "FALSE", "0", "INACTIVO", "INACTIVA"}


def _ahora() -> str:
    """Devuelve la hora local con zona para que la auditoria sea reproducible."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _usuario() -> str:
    """Identifica al usuario operativo; usa un valor seguro si el SO no responde."""
    try:
        return getpass.getuser() or "DESCONOCIDO"
    except Exception:
        return "DESCONOCIDO"


def _fecha(valor: object) -> date:
    """Acepta los formatos de fecha usados por interfaz, SQLite y Summit."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha no valida para Spot: {valor}")


def _fecha_texto(valor: object) -> str:
    """Estandariza fechas persistidas y mostradas a ``dd/mm/AAAA``."""
    return _fecha(valor).strftime("%d/%m/%Y")


def _decimal(valor: object) -> Decimal:
    """Convierte importes locales o Summit sin pasar por punto flotante.

    Acepta, entre otros, ``50.269.423,25`` y ``50,269,423.25``. PUNTO DE
    CAMBIO: agregar otro formato requiere pruebas para no alterar separadores.
    """
    texto = str(valor).strip().replace("\u00a0", "").replace(" ", "")
    if texto.startswith("(") and texto.endswith(")"):
        texto = f"-{texto[1:-1]}"
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            # Formato local: 50.269.423,25732988
            texto = texto.replace(".", "").replace(",", ".")
        else:
            # Formato Summit: 50,269,423.25732988
            texto = texto.replace(",", "")
    elif "," in texto:
        partes = texto.split(",")
        if len(partes) == 2 and len(partes[1]) != 3:
            texto = ".".join(partes)
        else:
            texto = "".join(partes)
    if not texto:
        raise InvalidOperation("valor vacio")
    resultado = Decimal(texto)
    if not resultado.is_finite():
        raise InvalidOperation("valor no finito")
    return resultado


def _decimal_texto(valor: Decimal | object) -> str:
    """Serializa Decimal sin notacion cientifica para guardarlo exactamente."""
    numero = valor if isinstance(valor, Decimal) else _decimal(valor)
    if numero == 0:
        return "0"
    return format(numero, "f")


def _cargar_configuracion_spot() -> dict:
    """Lee la configuracion transversal de Spot desde ``risko.json``.

    Spot 2 reutiliza solamente el bloque ``spot`` para conocer los owner tables
    permitidos y la ubicacion del Excel de saldos iniciales. Las banderas
    ``spot_2.incluir_en_cierre`` y ``spot_2.posicion_inicial_validada`` se
    evalúan fuera de este archivo, en el servicio que decide si publica o no.

    PUNTO DE CAMBIO: ``owner_tables_incluidas`` controla que familias de Summit
    llegan al filtro por book. No cambia el book objetivo SPOT_CLIENTE.
    """
    configuracion: dict = {}
    if ARCHIVO_CONFIG_RISKO_VECTOR.exists():
        with ARCHIVO_CONFIG_RISKO_VECTOR.open("r", encoding="utf-8") as archivo:
            raiz = json.load(archivo)
        configuracion = dict(raiz.get("spot") or {})

    owners = configuracion.get("owner_tables_incluidas") or sorted(
        OWNER_TABLES_POR_DEFECTO
    )
    configuracion["owner_tables_incluidas"] = {
        str(owner).strip().upper() for owner in owners if str(owner).strip()
    }
    if not configuracion["owner_tables_incluidas"]:
        raise ValueError("La configuracion Spot no tiene owner tables incluidas.")
    configuracion.setdefault(
        "archivo_excel_posiciones",
        str(
            RAIZ_RISKO
            / "proyectos"
            / "position_monitor"
            / "configuracion"
            / "param_posiciones_iniciales_spot.xlsx"
        ),
    )
    configuracion.setdefault("hoja_excel_posiciones", "Posiciones_Iniciales")
    return configuracion


def _resolver_ruta_db(
    ruta_db: str | Path | None = None,
    pruebas: bool = False,
) -> Path:
    """Decide en que SQLite se escribe, sin mezclar prueba y produccion.

    Prioridad: ruta explicita > base general de pruebas > base oficial. Para
    Spot 2 la interfaz entrega una ruta explicita dentro de ``pruebas/spot_2``.
    """
    if ruta_db is not None:
        return Path(ruta_db)
    if pruebas:
        return ARCHIVO_BASE_DATOS_RISKO_PRUEBAS
    return ARCHIVO_BASE_DATOS_POSITION_MONITOR


def _ruta_insumo(fecha_corte: date) -> Path:
    """Construye el nombre de cierre por defecto (version ``_000``).

    La interfaz de pruebas puede resolver otra version y pasarla directamente
    mediante ``ruta_insumo``; por eso la seleccion del archivo mas reciente no
    debe implementarse modificando esta funcion.
    """
    return CARPETA_INSUMOS / f"Cierre_ReporteCaja_{fecha_corte:%d%m%y}_000.xls"


def _hash_archivo(ruta: Path) -> str:
    """Calcula la huella del insumo usada para idempotencia y auditoria."""
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _valor_activo(valor: object) -> bool:
    """Normaliza las variantes permitidas de SI/NO del parametro de books."""
    clave = normalizar_clave_param(valor)
    if clave in _ACTIVOS:
        return True
    if clave in _INACTIVOS:
        return False
    raise ValueError(
        "Valor ACTIVO invalido en param_libros.csv para Spot: "
        f"{valor!r}. Use SI o NO."
    )


def _cargar_parametros_spot() -> tuple[dict[str, dict], dict[str, dict], str]:
    """Carga y valida el mapeo de SPOT_CLIENTE.

    PASO 3.1: primero busca el book en el parametro compartido de libros.
    PASO 3.2: si aun no esta promovido, usa ``param_spot_2.csv`` aislado.
    PASO 3.3: crea dos indices: uno por BOOK fuente y otro por posicion final.
    PASO 3.4: calcula una huella; cambiar cualquier atributo fuerza reproceso.

    PUNTO DE CAMBIO SEGURO: BOOK_HOMOL, LB_LT, INSTRUMENTO,
    MONEDA_POSICION y ACTIVO se administran en el CSV, no se fijan aqui.
    """
    # PASO 3.1 - Intentar el mapeo oficial compartido.
    parametros = cargar_parametros_libros()
    parametros = parametros.loc[parametros["_PRODUCTO_CLAVE"] == "SPOT"].copy()
    parametros = parametros.loc[
        parametros["BOOK"].map(normalizar_clave_param)
        == normalizar_clave_param(BOOK_OBJETIVO)
    ].copy()
    if parametros.empty:
        # PASO 3.2 - Mientras no este promovido, usar el parametro independiente.
        if not ARCHIVO_PARAM_SPOT_2.is_file():
            raise ValueError(
                "No existe el parametro aislado de Spot 2 para "
                f"BOOK = {BOOK_OBJETIVO}: {ARCHIVO_PARAM_SPOT_2}"
            )
        parametros = pd.read_csv(
            ARCHIVO_PARAM_SPOT_2,
            sep=",",
            encoding="utf-8-sig",
        )
        parametros.columns = [str(columna).strip() for columna in parametros.columns]
        requeridas = {
            "PRODUCTO",
            "BOOK",
            "BOOK_HOMOL",
            "LB_LT",
            "INSTRUMENTO",
            "MONEDA_POSICION",
            "ACTIVO",
        }
        faltantes = sorted(requeridas - set(parametros.columns))
        if faltantes:
            raise ValueError(
                "param_spot_2.csv no contiene todas las columnas requeridas: "
                + ", ".join(faltantes)
            )
        parametros = parametros.loc[
            parametros["PRODUCTO"].map(normalizar_clave_param).eq("SPOT")
            & parametros["BOOK"].map(normalizar_clave_param).eq(
                normalizar_clave_param(BOOK_OBJETIVO)
            )
        ].copy()
        if parametros.empty:
            raise ValueError(
                "param_spot_2.csv no contiene una definicion para "
                f"BOOK = {BOOK_OBJETIVO}."
            )

    # PASO 3.3 - Construir indices normalizados y comprobar aliases compatibles.
    por_book: dict[str, dict] = {}
    por_posicion: dict[str, dict] = {}
    serializables: list[dict] = []
    for _, fila in parametros.iterrows():
        book = str(fila["BOOK"]).strip()
        book_clave = normalizar_clave_param(book)
        nombre = str(fila["BOOK_HOMOL"]).strip() or book
        posicion_id = normalizar_clave_param(nombre)
        if not book_clave or not posicion_id:
            raise ValueError("Spot tiene un BOOK o BOOK_HOMOL vacio en param_libros.csv.")
        activo = _valor_activo(fila.get("ACTIVO", "SI"))
        # Estos campos alimentan directamente la tabla canonica del dashboard.
        definicion = {
            "BOOK": book,
            "BOOK_CLAVE": book_clave,
            "POSICION_ID": posicion_id,
            "POSICION_NOMBRE": nombre,
            "ACTIVO": activo,
            "LB_LT": str(fila["LB_LT"]).strip() or "No definido",
            "INSTRUMENTO": str(fila["INSTRUMENTO"]).strip() or "Derivados",
            "MONEDA_POSICION": str(fila["MONEDA_POSICION"]).strip() or "USD",
        }
        por_book[book_clave] = definicion

        existente = por_posicion.get(posicion_id)
        if existente:
            campos = ("POSICION_NOMBRE", "ACTIVO", "LB_LT", "INSTRUMENTO", "MONEDA_POSICION")
            diferentes = [campo for campo in campos if existente[campo] != definicion[campo]]
            if diferentes:
                raise ValueError(
                    "param_libros.csv tiene aliases Spot incompatibles para la "
                    f"posicion {nombre}: {', '.join(diferentes)}."
                )
        else:
            por_posicion[posicion_id] = definicion
        serializables.append(definicion)

    # PASO 3.4 - La huella evita considerar iguales dos corridas con mapeos distintos.
    huella = hashlib.sha256(
        json.dumps(
            sorted(serializables, key=lambda item: item["BOOK_CLAVE"]),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return por_book, por_posicion, huella


def _detectar_encabezado(ruta: Path) -> tuple[str, int, list[str], dict[str, int]]:
    """Encuentra el encabezado real aunque Summit agregue lineas preliminares.

    Se examinan como maximo 200 filas y las dos codificaciones historicas del
    reporte. PUNTO DE CAMBIO: si cambia el contrato de columnas, actualizar
    ``COLUMNAS_REQUERIDAS`` y revisar los accesos de ``_leer_movimientos``.
    """
    errores: list[str] = []
    requeridas = {nombre.casefold() for nombre in COLUMNAS_REQUERIDAS}
    for codificacion in ("cp1252", "latin1"):
        try:
            with ruta.open("r", encoding=codificacion, errors="strict", newline="") as archivo:
                for indice, fila in enumerate(csv.reader(archivo, delimiter=";")):
                    if indice >= 200:
                        break
                    nombres = [str(valor).strip() for valor in fila]
                    mapa = {nombre.casefold(): pos for pos, nombre in enumerate(nombres)}
                    if requeridas.issubset(mapa):
                        return codificacion, indice, nombres, mapa
        except UnicodeDecodeError as exc:
            errores.append(f"{codificacion}: {exc}")
    raise ValueError(
        "No se encontro el encabezado requerido del Reporte de Caja en las "
        "primeras 200 filas. Se exige TRADE DATE y las columnas "
        f"{', '.join(COLUMNAS_REQUERIDAS)}. Detalle: {'; '.join(errores)}"
    )


def _alerta(
    codigo: str,
    fecha_corte: str,
    detalle: str,
    *,
    posicion_id: str = "",
    book_original: str = "",
    fila_fuente: int | None = None,
) -> dict:
    """Construye una alerta validada antes de persistirla."""
    if codigo not in CODIGOS_ALERTA:
        raise ValueError(f"Codigo de alerta Spot no reconocido: {codigo}")
    return {
        "CODIGO": codigo,
        "FECHA": fecha_corte,
        "POSICION_ID": posicion_id,
        "BOOK_ORIGINAL": book_original,
        "FILA_FUENTE": fila_fuente,
        "DETALLE": detalle,
    }


def _leer_movimientos(
    ruta: Path,
    fecha_corte: date,
    por_book: dict[str, dict],
    owners_incluidos: set[str],
    logger=None,
) -> tuple[list[dict], list[dict]]:
    """Convierte el Reporte de Caja en movimientos auditables de SPOT_CLIENTE.

    Cada ``continue`` representa un filtro deliberado. Si se cambia uno, debe
    conciliarse cantidad de filas, compras, ventas y saldo final contra Summit.
    Las filas desconocidas o invalidas generan alertas cuando corresponde; las
    filas de otros universos simplemente no pertenecen a este modulo.
    """
    # PASO 5.1 - Localizar el encabezado y preparar el acceso por nombre.
    codificacion, fila_encabezado, _, mapa = _detectar_encabezado(ruta)
    fecha_objetivo = fecha_corte.strftime("%d/%m/%Y")
    registrar_log(
        logger,
        f"Spot: encabezado detectado en fila {fila_encabezado + 1}, "
        f"codificacion {codificacion}.",
    )

    movimientos: list[dict] = []
    alertas: list[dict] = []
    alertados: set[tuple[str, str]] = set()

    def campo(fila: list[str], nombre: str) -> str:
        # Devuelve vacio si una fila viene mas corta que el encabezado.
        indice = mapa[nombre.casefold()]
        return str(fila[indice]).strip() if indice < len(fila) else ""

    # PASO 5.2 - Recorrer el archivo desde la primera fila de datos.
    with ruta.open("r", encoding=codificacion, errors="strict", newline="") as archivo:
        lector = csv.reader(archivo, delimiter=";")
        for _ in range(fila_encabezado + 1):
            next(lector, None)

        for numero_fila, fila in enumerate(lector, start=fila_encabezado + 2):
            # FILTRO 1: aceptar solo las familias Summit habilitadas en risko.json.
            owner = campo(fila, "DmOwnerTable").upper()
            if owner not in owners_incluidos:
                continue

            # FILTRO 2: la posicion Spot 2 esta expresada exclusivamente en USD.
            moneda = campo(fila, "SettleCcy").upper()
            if moneda != "USD":
                continue

            # FILTRO 3: usar TRADE DATE, no la fecha de generacion del reporte.
            fecha_original = campo(fila, "TRADE DATE")
            try:
                fecha_movimiento = _fecha(fecha_original)
            except ValueError:
                alertas.append(
                    _alerta(
                        "INVALID_DATE",
                        fecha_objetivo,
                        f"TRADE DATE invalida: {fecha_original!r}.",
                        book_original=campo(fila, "Book"),
                        fila_fuente=numero_fila,
                    )
                )
                continue
            if fecha_movimiento != fecha_corte:
                continue

            # FILTRO 4: aislar SPOT_CLIENTE para no duplicar los books de spot.py.
            book_original = campo(fila, "Book")
            book_clave = normalizar_clave_param(book_original)
            if book_clave != normalizar_clave_param(BOOK_OBJETIVO):
                continue
            definicion = por_book.get(book_clave)
            posicion_id = definicion["POSICION_ID"] if definicion else ""
            posicion_nombre = definicion["POSICION_NOMBRE"] if definicion else ""
            publicable = bool(definicion and definicion["ACTIVO"])

            # PASO 5.3 - Alertar si el book objetivo no esta mapeado o esta inactivo.
            if definicion is None:
                llave = ("UNKNOWN_BOOK", book_clave)
                if llave not in alertados:
                    alertados.add(llave)
                    alertas.append(
                        _alerta(
                            "UNKNOWN_BOOK",
                            fecha_objetivo,
                            "El BOOK no esta definido para Spot en param_libros.csv; "
                            "sus movimientos no se agregan a la posicion oficial.",
                            book_original=book_original,
                        )
                    )
            elif not definicion["ACTIVO"]:
                llave = ("INACTIVE_BOOK", book_clave)
                if llave not in alertados:
                    alertados.add(llave)
                    alertas.append(
                        _alerta(
                            "INACTIVE_BOOK",
                            fecha_objetivo,
                            "El BOOK esta inactivo en param_libros.csv; sus movimientos "
                            "no se agregan a la posicion oficial.",
                            posicion_id=posicion_id,
                            book_original=book_original,
                        )
                    )

            # PASO 6.1 - Convertir Amount a Decimal exacto.
            amount_original = campo(fila, "Amount")
            try:
                amount = _decimal(amount_original)
            except (InvalidOperation, ValueError):
                alertas.append(
                    _alerta(
                        "INVALID_AMOUNT",
                        fecha_objetivo,
                        f"Amount invalido: {amount_original!r}.",
                        posicion_id=posicion_id,
                        book_original=book_original,
                        fila_fuente=numero_fila,
                    )
                )
                continue

            # REGLA FINANCIERA / PUNTO DE CAMBIO SENSIBLE:
            # positivo = compra; negativo = venta. Las ventas se guardan en
            # valor absoluto para aplicar despues compras - ventas.
            if amount > 0:
                tipo = "COMPRA"
                monto_usd = amount
            elif amount < 0:
                tipo = "VENTA"
                monto_usd = -amount
            else:
                tipo = "SIN_MOVIMIENTO"
                monto_usd = Decimal("0")

            # PASO 7 - Guardar todos los identificadores necesarios para volver
            # desde el agregado hasta la fila exacta del archivo fuente.
            movimientos.append(
                {
                    "FECHA": fecha_objetivo,
                    "SOURCE_ROW_ID": campo(fila, "GeneratedPK") or str(numero_fila),
                    "TRADE_ID": campo(fila, "TradeId"),
                    "PRODUCTO_ORIGEN": owner,
                    "BOOK_ORIGINAL": book_original,
                    "POSICION_ID": posicion_id,
                    "POSICION_NOMBRE": posicion_nombre,
                    "DESK": campo(fila, "Desk"),
                    "EVTYPE": campo(fila, "EvType"),
                    "SETTLE_CCY": moneda,
                    "AMOUNT_ORIGINAL": _decimal_texto(amount),
                    "TIPO_MOVIMIENTO": tipo,
                    "MONTO_USD": _decimal_texto(monto_usd),
                    "FILA_FUENTE": numero_fila,
                    "PUBLICABLE": 1 if publicable else 0,
                }
            )

    registrar_log(
        logger,
        f"Spot: {len(movimientos):,} movimientos USD del corte y "
        f"{len(alertas):,} alertas de lectura/mapeo.",
    )
    return movimientos, alertas


def _exportar_movimientos_intermedios(
    movimientos: list[dict],
    logger=None,
) -> Path:
    """Exporta el detalle filtrado justo antes de agrupar compras y ventas."""
    ARCHIVO_INTERMEDIO_SPOT_2.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(movimientos).to_excel(
        ARCHIVO_INTERMEDIO_SPOT_2,
        sheet_name="Movimientos_Spot_Cliente",
        index=False,
    )
    registrar_log(
        logger,
        "Spot 2: tabla intermedia previa a la agrupacion exportada en "
        f"{ARCHIVO_INTERMEDIO_SPOT_2} ({len(movimientos):,} filas).",
    )
    return ARCHIVO_INTERMEDIO_SPOT_2


def _crear_esquema(conexion) -> None:
    """Crea las seis tablas aisladas de Spot 2 si todavia no existen.

    * ejecuciones: una fila por intento y sus hashes;
    * movimientos: detalle de cada fila Summit y su version vigente;
    * compras/ventas: agregado de control por book;
    * alertas: inconsistencias operativas o financieras;
    * historico: saldo diario acumulado que alimenta el dashboard;
    * auditoria: valor anterior/nuevo de cada recalculo.

    ``CREATE IF NOT EXISTS`` no borra ni reinicia la historia existente.
    """
    conexion.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLA_EJECUCIONES_SPOT} (
            EJECUCION_ID TEXT PRIMARY KEY,
            FECHA_CORTE TEXT NOT NULL,
            ARCHIVO_FUENTE TEXT NOT NULL,
            RUTA_FUENTE TEXT NOT NULL,
            SHA256_FUENTE TEXT NOT NULL,
            SHA256_PARAMETROS TEXT NOT NULL,
            TAMANO_BYTES INTEGER NOT NULL,
            MODIFICADO_FUENTE TEXT,
            ORIGEN TEXT NOT NULL,
            ESTADO TEXT NOT NULL,
            USUARIO TEXT NOT NULL,
            INICIO TEXT NOT NULL,
            FIN TEXT,
            MENSAJE TEXT
        );

        CREATE TABLE IF NOT EXISTS {TABLA_MOVIMIENTOS_SPOT} (
            MOVIMIENTO_ID TEXT PRIMARY KEY,
            EJECUCION_ID TEXT NOT NULL,
            FECHA TEXT NOT NULL,
            SOURCE_ROW_ID TEXT,
            TRADE_ID TEXT,
            PRODUCTO_ORIGEN TEXT,
            BOOK_ORIGINAL TEXT,
            POSICION_ID TEXT,
            POSICION_NOMBRE TEXT,
            DESK TEXT,
            EVTYPE TEXT,
            SETTLE_CCY TEXT,
            AMOUNT_ORIGINAL TEXT,
            TIPO_MOVIMIENTO TEXT,
            MONTO_USD TEXT,
            ARCHIVO_FUENTE TEXT,
            FILA_FUENTE INTEGER,
            PUBLICABLE INTEGER NOT NULL,
            VIGENTE INTEGER NOT NULL,
            CREATED_AT TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {TABLA_COMPRAS_VENTAS_BOOK_SPOT} (
            FECHA TEXT NOT NULL,
            BOOK_CLAVE TEXT NOT NULL,
            BOOK_ORIGINAL TEXT NOT NULL,
            POSICION_ID TEXT,
            POSICION_NOMBRE TEXT,
            ESTADO_MAPEO TEXT NOT NULL,
            PUBLICABLE INTEGER NOT NULL,
            COMPRAS_USD TEXT NOT NULL,
            VENTAS_USD TEXT NOT NULL,
            MOVIMIENTO_NETO_USD TEXT NOT NULL,
            NUMERO_MOVIMIENTOS INTEGER NOT NULL,
            ARCHIVO_FUENTE TEXT NOT NULL,
            EJECUCION_ID TEXT NOT NULL,
            UPDATED_AT TEXT NOT NULL,
            PRIMARY KEY (FECHA, BOOK_CLAVE)
        );

        CREATE TABLE IF NOT EXISTS {TABLA_ALERTAS_SPOT} (
            ALERTA_ID TEXT PRIMARY KEY,
            EJECUCION_ID TEXT NOT NULL,
            FECHA TEXT NOT NULL,
            CODIGO TEXT NOT NULL,
            POSICION_ID TEXT,
            BOOK_ORIGINAL TEXT,
            FILA_FUENTE INTEGER,
            DETALLE TEXT NOT NULL,
            VIGENTE INTEGER NOT NULL,
            CREATED_AT TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS {TABLA_HISTORICO_SPOT} (
            FECHA TEXT NOT NULL,
            POSICION_ID TEXT NOT NULL,
            POSICION_NOMBRE TEXT NOT NULL,
            FECHA_ANTERIOR TEXT,
            POSICION_ANTERIOR TEXT NOT NULL,
            COMPRAS_USD TEXT NOT NULL,
            VENTAS_USD TEXT NOT NULL,
            MOVIMIENTO_NETO_USD TEXT NOT NULL,
            POSICION_FINAL_USD TEXT NOT NULL,
            ARCHIVO_FUENTE TEXT,
            EJECUCION_ID TEXT NOT NULL,
            TIPO_ORIGEN TEXT NOT NULL,
            ESTADO TEXT NOT NULL,
            TIENE_ALERTA INTEGER NOT NULL,
            DETALLE_ALERTA TEXT,
            USUARIO TEXT NOT NULL,
            CREATED_AT TEXT NOT NULL,
            UPDATED_AT TEXT NOT NULL,
            PRIMARY KEY (FECHA, POSICION_ID)
        );

        CREATE TABLE IF NOT EXISTS {TABLA_AUDITORIA_SPOT} (
            AUDITORIA_ID TEXT PRIMARY KEY,
            EJECUCION_ID TEXT NOT NULL,
            FECHA TEXT NOT NULL,
            POSICION_ID TEXT NOT NULL,
            VALOR_ANTERIOR TEXT,
            VALOR_NUEVO TEXT,
            MOTIVO TEXT NOT NULL,
            CREATED_AT TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_mov_spot_fecha_pos
            ON {TABLA_MOVIMIENTOS_SPOT} (FECHA, POSICION_ID, VIGENTE);
        CREATE INDEX IF NOT EXISTS idx_book_spot_fecha_publicable
            ON {TABLA_COMPRAS_VENTAS_BOOK_SPOT} (FECHA, PUBLICABLE);
        CREATE INDEX IF NOT EXISTS idx_alerta_spot_fecha
            ON {TABLA_ALERTAS_SPOT} (FECHA, POSICION_ID, VIGENTE);
        CREATE INDEX IF NOT EXISTS idx_ejec_spot_fuente
            ON {TABLA_EJECUCIONES_SPOT}
            (FECHA_CORTE, SHA256_FUENTE, SHA256_PARAMETROS, ESTADO);
        """
    )


def _insertar_alerta(conexion, ejecucion_id: str, datos: dict) -> None:
    """Persiste una alerta vigente asociada a una ejecucion y fecha."""
    conexion.execute(
        f"""
        INSERT INTO {TABLA_ALERTAS_SPOT} (
            ALERTA_ID, EJECUCION_ID, FECHA, CODIGO, POSICION_ID,
            BOOK_ORIGINAL, FILA_FUENTE, DETALLE, VIGENTE, CREATED_AT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            str(uuid.uuid4()),
            ejecucion_id,
            datos["FECHA"],
            datos["CODIGO"],
            datos.get("POSICION_ID", ""),
            datos.get("BOOK_ORIGINAL", ""),
            datos.get("FILA_FUENTE"),
            datos["DETALLE"],
            _ahora(),
        ),
    )


def _insertar_auditoria(
    conexion,
    ejecucion_id: str,
    fecha_texto: str,
    posicion_id: str,
    anterior: str | None,
    nuevo: str | None,
    motivo: str,
) -> None:
    """Registra como cambio trazable una creacion, modificacion o eliminacion."""
    conexion.execute(
        f"""
        INSERT INTO {TABLA_AUDITORIA_SPOT} (
            AUDITORIA_ID, EJECUCION_ID, FECHA, POSICION_ID,
            VALOR_ANTERIOR, VALOR_NUEVO, MOTIVO, CREATED_AT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            ejecucion_id,
            fecha_texto,
            posicion_id,
            anterior,
            nuevo,
            motivo,
            _ahora(),
        ),
    )


def _filas_historico_posicion(conexion, posicion_id: str) -> list[dict]:
    """Obtiene toda la cadena diaria de una posicion para recalcularla."""
    cursor = conexion.execute(
        f"SELECT * FROM {TABLA_HISTORICO_SPOT} WHERE POSICION_ID = ?",
        (posicion_id,),
    )
    columnas = [columna[0] for columna in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def _desactivar_alertas_desde(
    conexion,
    posicion_id: str,
    fecha_inicio: date,
    codigos: tuple[str, ...] = ("MISSING_PREVIOUS_POSITION",),
) -> None:
    """Invalida alertas recalculables desde una fecha; conserva su registro."""
    marcadores = ",".join("?" for _ in codigos)
    filas = conexion.execute(
        f"""
        SELECT ALERTA_ID, FECHA FROM {TABLA_ALERTAS_SPOT}
        WHERE POSICION_ID = ? AND VIGENTE = 1 AND CODIGO IN ({marcadores})
        """,
        (posicion_id, *codigos),
    ).fetchall()
    ids = [alerta_id for alerta_id, fecha_texto in filas if _fecha(fecha_texto) >= fecha_inicio]
    if ids:
        conexion.executemany(
            f"UPDATE {TABLA_ALERTAS_SPOT} SET VIGENTE = 0 WHERE ALERTA_ID = ?",
            [(alerta_id,) for alerta_id in ids],
        )


def _movimientos_posicion(conexion, posicion_id: str) -> dict[date, dict]:
    """Agrupa solo movimientos vigentes y publicables por dia.

    Aqui se suma ``MONTO_USD`` por tipo. El neto todavia no se calcula: se hace
    explicitamente en ``_recalcular_posicion`` para que la formula quede visible.
    """
    filas = conexion.execute(
        f"""
        SELECT FECHA, TIPO_MOVIMIENTO, MONTO_USD, ARCHIVO_FUENTE, EJECUCION_ID
        FROM {TABLA_MOVIMIENTOS_SPOT}
        WHERE POSICION_ID = ? AND PUBLICABLE = 1 AND VIGENTE = 1
        """,
        (posicion_id,),
    ).fetchall()
    acumulados: dict[date, dict] = {}
    for fecha_texto, tipo, monto_texto, archivo, ejecucion_id in filas:
        fecha_mov = _fecha(fecha_texto)
        datos = acumulados.setdefault(
            fecha_mov,
            {
                "COMPRAS": Decimal("0"),
                "VENTAS": Decimal("0"),
                "FILAS": 0,
                "ARCHIVO": archivo,
                "EJECUCION_ID": ejecucion_id,
            },
        )
        monto = _decimal(monto_texto)
        if tipo == "COMPRA":
            datos["COMPRAS"] += monto
        elif tipo == "VENTA":
            datos["VENTAS"] += monto
        datos["FILAS"] += 1
        datos["ARCHIVO"] = archivo
        datos["EJECUCION_ID"] = ejecucion_id
    return acumulados


def _guardar_compras_ventas_por_book(
    conexion,
    fecha_texto: str,
    por_book: dict[str, dict],
    archivo_fuente: str,
    ejecucion_id: str,
) -> None:
    """Materializa compras/ventas por BOOK sin afectar la posicion canonica.

    Esta tabla es el control mas directo para revisar si los signos y filtros
    quedaron bien antes de mirar el saldo acumulado.
    """
    resumen: dict[str, dict] = {}

    # Todos los BOOK parametrizados aparecen, aunque no tengan movimientos.
    for book_clave, definicion in por_book.items():
        resumen[book_clave] = {
            "BOOK_CLAVE": book_clave,
            "BOOK_ORIGINAL": definicion["BOOK"],
            "POSICION_ID": definicion["POSICION_ID"],
            "POSICION_NOMBRE": definicion["POSICION_NOMBRE"],
            "ESTADO_MAPEO": "ACTIVO" if definicion["ACTIVO"] else "INACTIVO",
            "PUBLICABLE": 1 if definicion["ACTIVO"] else 0,
            "COMPRAS": Decimal("0"),
            "VENTAS": Decimal("0"),
            "NUMERO_MOVIMIENTOS": 0,
        }

    movimientos = conexion.execute(
        f"""
        SELECT BOOK_ORIGINAL, TIPO_MOVIMIENTO, MONTO_USD
        FROM {TABLA_MOVIMIENTOS_SPOT}
        WHERE FECHA = ? AND VIGENTE = 1
        """,
        (fecha_texto,),
    ).fetchall()
    for book_original, tipo, monto_texto in movimientos:
        book_original = str(book_original or "").strip()
        book_clave = normalizar_clave_param(book_original)
        if not book_clave:
            book_clave = "BOOK_VACIO"
        datos = resumen.get(book_clave)
        if datos is None:
            datos = {
                "BOOK_CLAVE": book_clave,
                "BOOK_ORIGINAL": book_original or "(BOOK VACIO)",
                "POSICION_ID": "",
                "POSICION_NOMBRE": "",
                "ESTADO_MAPEO": "UNKNOWN_BOOK",
                "PUBLICABLE": 0,
                "COMPRAS": Decimal("0"),
                "VENTAS": Decimal("0"),
                "NUMERO_MOVIMIENTOS": 0,
            }
            resumen[book_clave] = datos
        monto = _decimal(monto_texto)
        if tipo == "COMPRA":
            datos["COMPRAS"] += monto
        elif tipo == "VENTA":
            datos["VENTAS"] += monto
        datos["NUMERO_MOVIMIENTOS"] += 1

    conexion.execute(
        f"DELETE FROM {TABLA_COMPRAS_VENTAS_BOOK_SPOT} WHERE FECHA = ?",
        (fecha_texto,),
    )
    actualizado = _ahora()
    conexion.executemany(
        f"""
        INSERT INTO {TABLA_COMPRAS_VENTAS_BOOK_SPOT} (
            FECHA, BOOK_CLAVE, BOOK_ORIGINAL, POSICION_ID, POSICION_NOMBRE,
            ESTADO_MAPEO, PUBLICABLE, COMPRAS_USD, VENTAS_USD,
            MOVIMIENTO_NETO_USD, NUMERO_MOVIMIENTOS, ARCHIVO_FUENTE,
            EJECUCION_ID, UPDATED_AT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                fecha_texto,
                datos["BOOK_CLAVE"],
                datos["BOOK_ORIGINAL"],
                datos["POSICION_ID"],
                datos["POSICION_NOMBRE"],
                datos["ESTADO_MAPEO"],
                datos["PUBLICABLE"],
                _decimal_texto(datos["COMPRAS"]),
                _decimal_texto(datos["VENTAS"]),
                _decimal_texto(datos["COMPRAS"] - datos["VENTAS"]),
                datos["NUMERO_MOVIMIENTOS"],
                archivo_fuente,
                ejecucion_id,
                actualizado,
            )
            for _, datos in sorted(resumen.items())
        ],
    )


def _upsert_historico(conexion, fila: dict) -> None:
    """Inserta el saldo diario o reemplaza esa fecha conservando la clave."""
    conexion.execute(
        f"""
        INSERT INTO {TABLA_HISTORICO_SPOT} (
            FECHA, POSICION_ID, POSICION_NOMBRE, FECHA_ANTERIOR,
            POSICION_ANTERIOR, COMPRAS_USD, VENTAS_USD,
            MOVIMIENTO_NETO_USD, POSICION_FINAL_USD, ARCHIVO_FUENTE,
            EJECUCION_ID, TIPO_ORIGEN, ESTADO, TIENE_ALERTA,
            DETALLE_ALERTA, USUARIO, CREATED_AT, UPDATED_AT
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(FECHA, POSICION_ID) DO UPDATE SET
            POSICION_NOMBRE = excluded.POSICION_NOMBRE,
            FECHA_ANTERIOR = excluded.FECHA_ANTERIOR,
            POSICION_ANTERIOR = excluded.POSICION_ANTERIOR,
            COMPRAS_USD = excluded.COMPRAS_USD,
            VENTAS_USD = excluded.VENTAS_USD,
            MOVIMIENTO_NETO_USD = excluded.MOVIMIENTO_NETO_USD,
            POSICION_FINAL_USD = excluded.POSICION_FINAL_USD,
            ARCHIVO_FUENTE = excluded.ARCHIVO_FUENTE,
            EJECUCION_ID = excluded.EJECUCION_ID,
            TIPO_ORIGEN = excluded.TIPO_ORIGEN,
            ESTADO = excluded.ESTADO,
            TIENE_ALERTA = excluded.TIENE_ALERTA,
            DETALLE_ALERTA = excluded.DETALLE_ALERTA,
            USUARIO = excluded.USUARIO,
            UPDATED_AT = excluded.UPDATED_AT
        """,
        tuple(
            fila[columna]
            for columna in (
                "FECHA",
                "POSICION_ID",
                "POSICION_NOMBRE",
                "FECHA_ANTERIOR",
                "POSICION_ANTERIOR",
                "COMPRAS_USD",
                "VENTAS_USD",
                "MOVIMIENTO_NETO_USD",
                "POSICION_FINAL_USD",
                "ARCHIVO_FUENTE",
                "EJECUCION_ID",
                "TIPO_ORIGEN",
                "ESTADO",
                "TIENE_ALERTA",
                "DETALLE_ALERTA",
                "USUARIO",
                "CREATED_AT",
                "UPDATED_AT",
            )
        ),
    )


def _recalcular_posicion(
    conexion,
    definicion: dict,
    fecha_inicio: date,
    fecha_minima_fin: date,
    ejecucion_id: str,
    motivo: str,
) -> None:
    """Reconstruye el saldo diario desde ``fecha_inicio`` hacia adelante.

    Orden de precedencia:

    1. una fila ``EXCEL_INICIAL`` es un ancla oficial y no se sobrescribe;
    2. con movimientos, aplica anterior + compras - ventas;
    3. sin movimientos, hace carry-forward del saldo anterior;
    4. sin ancla ni saldo anterior, usa cero y deja una alerta vigente.

    PUNTO DE CAMBIO SENSIBLE: esta es la formula financiera central. El cero de
    contingencia permite probar el flujo, pero no valida el saldo inicial.
    """
    posicion_id = definicion["POSICION_ID"]

    # PASO 8.1 - Separar historia existente, anclas manuales y movimientos vigentes.
    filas_anteriores = _filas_historico_posicion(conexion, posicion_id)
    por_fecha_anterior = {_fecha(fila["FECHA"]): fila for fila in filas_anteriores}
    anclas = {
        fecha_fila: fila
        for fecha_fila, fila in por_fecha_anterior.items()
        if fila["TIPO_ORIGEN"] == ORIGEN_EXCEL
    }
    movimientos = _movimientos_posicion(conexion, posicion_id)

    # PASO 8.2 - El recalculo se extiende hasta la ultima fecha afectada.
    fechas_relevantes = [fecha_minima_fin]
    fechas_relevantes.extend(fecha for fecha in por_fecha_anterior if fecha >= fecha_inicio)
    fechas_relevantes.extend(fecha for fecha in movimientos if fecha >= fecha_inicio)
    fecha_fin = max(fechas_relevantes)

    # PASO 8.3 - Buscar el saldo inmediatamente anterior al tramo recalculado.
    bases = [fecha for fecha in por_fecha_anterior if fecha < fecha_inicio]
    if bases:
        fecha_previa = max(bases)
        posicion_previa = _decimal(por_fecha_anterior[fecha_previa]["POSICION_FINAL_USD"])
        existe_previa = True
    else:
        # Este cero es transitorio y siempre debe quedar acompañado de alerta.
        fecha_previa = None
        posicion_previa = Decimal("0")
        existe_previa = False

    # Las alertas antiguas del mismo problema dejan de estar vigentes antes de
    # crear las nuevas; no se borran, para conservar auditoria.
    _desactivar_alertas_desde(conexion, posicion_id, fecha_inicio)
    deseadas: dict[date, dict] = {}
    fecha_actual = fecha_inicio
    while fecha_actual <= fecha_fin:
        # PASO 8.4 - Un saldo validado en Excel corta la cadena y se vuelve la
        # nueva base para todos los dias posteriores.
        if fecha_actual in anclas:
            ancla = anclas[fecha_actual]
            deseadas[fecha_actual] = ancla
            posicion_previa = _decimal(ancla["POSICION_FINAL_USD"])
            fecha_previa = fecha_actual
            existe_previa = True
            fecha_actual += timedelta(days=1)
            continue

        # PASO 8.5 - Determinar si el dia tiene operaciones o solo arrastre.
        datos_mov = movimientos.get(fecha_actual)
        crear_inicial_cero = (
            not existe_previa
            and datos_mov is None
            and fecha_actual == fecha_minima_fin
        )
        if not existe_previa and datos_mov is None and not crear_inicial_cero:
            fecha_actual += timedelta(days=1)
            continue

        # PASO 8.6 - FORMULA CENTRAL:
        # posicion_final = posicion_anterior + compras - ventas.
        compras = datos_mov["COMPRAS"] if datos_mov else Decimal("0")
        ventas = datos_mov["VENTAS"] if datos_mov else Decimal("0")
        neto = compras - ventas
        final = posicion_previa + neto
        # Etiquetar el origen permite diferenciar carga, carry y cero pendiente.
        if crear_inicial_cero:
            origen = ORIGEN_INICIAL_CERO
            archivo = "INICIAL_CERO_PENDIENTE"
        else:
            origen = ORIGEN_MOVIMIENTOS if datos_mov else ORIGEN_CARRY
            archivo = datos_mov["ARCHIVO"] if datos_mov else "CARRY_FORWARD"
        ejecucion_fila = datos_mov["EJECUCION_ID"] if datos_mov else ejecucion_id

        # PASO 8.7 - Hacer visible que la cadena comenzo sin saldo validado.
        if not existe_previa:
            if crear_inicial_cero:
                detalle_alerta = (
                    "La posicion activa no tiene saldo anterior ni movimientos en "
                    "el corte; se crea en cero para completar la tabla inicial. "
                    "El valor debe validarse o reemplazarse desde el Excel."
                )
            else:
                detalle_alerta = (
                    "No existe una posicion oficial anterior; se usa cero y el "
                    "proceso continua para mantener trazabilidad."
                )
            _insertar_alerta(
                conexion,
                ejecucion_id,
                _alerta(
                    "MISSING_PREVIOUS_POSITION",
                    fecha_actual.strftime("%d/%m/%Y"),
                    detalle_alerta,
                    posicion_id=posicion_id,
                ),
            )

        # PASO 8.8 - Preparar la foto diaria completa, no solo el valor final.
        ahora = _ahora()
        deseadas[fecha_actual] = {
            "FECHA": fecha_actual.strftime("%d/%m/%Y"),
            "POSICION_ID": posicion_id,
            "POSICION_NOMBRE": definicion["POSICION_NOMBRE"],
            "FECHA_ANTERIOR": fecha_previa.strftime("%d/%m/%Y") if fecha_previa else None,
            "POSICION_ANTERIOR": _decimal_texto(posicion_previa),
            "COMPRAS_USD": _decimal_texto(compras),
            "VENTAS_USD": _decimal_texto(ventas),
            "MOVIMIENTO_NETO_USD": _decimal_texto(neto),
            "POSICION_FINAL_USD": _decimal_texto(final),
            "ARCHIVO_FUENTE": archivo,
            "EJECUCION_ID": ejecucion_fila,
            "TIPO_ORIGEN": origen,
            "ESTADO": "PENDIENTE_ALERTAS",
            "TIENE_ALERTA": 0,
            "DETALLE_ALERTA": "",
            "USUARIO": _usuario(),
            "CREATED_AT": ahora,
            "UPDATED_AT": ahora,
        }
        posicion_previa = final
        fecha_previa = fecha_actual
        existe_previa = True
        fecha_actual += timedelta(days=1)

    # PASO 8.9 - Quitar del estado vigente filas que ya no corresponden al
    # nuevo calculo, registrando antes el valor eliminado en auditoria.
    for fecha_fila, fila_anterior in por_fecha_anterior.items():
        if fecha_fila < fecha_inicio or fecha_fila in anclas:
            continue
        if fecha_fila not in deseadas:
            _insertar_auditoria(
                conexion,
                ejecucion_id,
                fila_anterior["FECHA"],
                posicion_id,
                fila_anterior["POSICION_FINAL_USD"],
                None,
                motivo,
            )
            conexion.execute(
                f"DELETE FROM {TABLA_HISTORICO_SPOT} WHERE FECHA = ? AND POSICION_ID = ?",
                (fila_anterior["FECHA"], posicion_id),
            )

    # PASO 8.10 - Comparar, auditar y hacer upsert de cada saldo recalculado.
    for fecha_fila, fila_nueva in deseadas.items():
        if fecha_fila in anclas:
            continue
        fila_anterior = por_fecha_anterior.get(fecha_fila)
        anterior = fila_anterior["POSICION_FINAL_USD"] if fila_anterior else None
        nuevo = fila_nueva["POSICION_FINAL_USD"]
        if fila_anterior is None or any(
            fila_anterior[campo] != fila_nueva[campo]
            for campo in (
                "POSICION_ANTERIOR",
                "COMPRAS_USD",
                "VENTAS_USD",
                "MOVIMIENTO_NETO_USD",
                "POSICION_FINAL_USD",
                "TIPO_ORIGEN",
            )
        ):
            _insertar_auditoria(
                conexion,
                ejecucion_id,
                fila_nueva["FECHA"],
                posicion_id,
                anterior,
                nuevo,
                motivo,
            )
        _upsert_historico(conexion, fila_nueva)


def _actualizar_estado_alertas(conexion, posiciones: set[str] | None = None) -> None:
    """Sincroniza el estado resumido de cada saldo con sus alertas vigentes."""
    if posiciones:
        marcadores = ",".join("?" for _ in posiciones)
        filas = conexion.execute(
            f"SELECT FECHA, POSICION_ID FROM {TABLA_HISTORICO_SPOT} "
            f"WHERE POSICION_ID IN ({marcadores})",
            tuple(posiciones),
        ).fetchall()
    else:
        filas = conexion.execute(
            f"SELECT FECHA, POSICION_ID FROM {TABLA_HISTORICO_SPOT}"
        ).fetchall()
    for fecha_texto, posicion_id in filas:
        detalles = conexion.execute(
            f"""
            SELECT CODIGO, DETALLE FROM {TABLA_ALERTAS_SPOT}
            WHERE FECHA = ? AND POSICION_ID = ? AND VIGENTE = 1
            ORDER BY CODIGO, CREATED_AT
            """,
            (fecha_texto, posicion_id),
        ).fetchall()
        detalle = " | ".join(f"{codigo}: {texto}" for codigo, texto in detalles)
        conexion.execute(
            f"""
            UPDATE {TABLA_HISTORICO_SPOT}
            SET TIENE_ALERTA = ?, DETALLE_ALERTA = ?, ESTADO = ?
            WHERE FECHA = ? AND POSICION_ID = ?
            """,
            (
                1 if detalles else 0,
                detalle,
                "CON_ALERTA" if detalles else "OK",
                fecha_texto,
                posicion_id,
            ),
        )


def _resumen_desde_conexion(conexion, fecha_corte: date) -> pd.DataFrame:
    """Lee la foto enriquecida de una fecha para interfaz y diagnostico."""
    fecha_texto = fecha_corte.strftime("%d/%m/%Y")
    consulta = f"""
        SELECT FECHA, POSICION_ID, POSICION_NOMBRE, FECHA_ANTERIOR,
               POSICION_ANTERIOR, COMPRAS_USD, VENTAS_USD,
               MOVIMIENTO_NETO_USD, POSICION_FINAL_USD, TIPO_ORIGEN,
               ESTADO, TIENE_ALERTA, DETALLE_ALERTA, ARCHIVO_FUENTE,
               EJECUCION_ID, UPDATED_AT
        FROM {TABLA_HISTORICO_SPOT}
        WHERE FECHA = ?
        ORDER BY POSICION_NOMBRE
    """
    return pd.read_sql_query(consulta, conexion, params=(fecha_texto,))


def obtener_resumen_spot(
    fecha_trabajo: str | date,
    *,
    pruebas: bool = False,
    ruta_db: str | Path | None = None,
) -> pd.DataFrame:
    """Consulta una fecha ya calculada sin modificar saldos ni movimientos."""
    ruta = _resolver_ruta_db(ruta_db, pruebas=pruebas)
    with closing(conectar_sqlite(ruta)) as conexion:
        _crear_esquema(conexion)
        return _resumen_desde_conexion(conexion, _fecha(fecha_trabajo))


def arrastrar_spot_acumulado(
    fecha_trabajo: str | date,
    logger=None,
    *,
    pruebas: bool = False,
    ruta_db: str | Path | None = None,
) -> pd.DataFrame:
    """Publica el saldo Spot acumulado de un corte sin movimientos nuevos.

    Si el historico acumulado ya contiene todas las posiciones activas para la
    fecha, se limita a construir la tabla canonica. En caso contrario crea el
    carry-forward desde la ultima posicion anterior, con compras y ventas en
    cero y trazabilidad propia, sin requerir un Reporte de Caja.
    """
    # CARRY 1 - Resolver la fecha, el mapeo y el universo que debe aparecer.
    fecha_corte = _fecha(fecha_trabajo)
    fecha_texto = fecha_corte.strftime("%d/%m/%Y")
    ruta_base = _resolver_ruta_db(ruta_db, pruebas=pruebas)
    por_book, por_posicion, hash_parametros = _cargar_parametros_spot()
    posiciones_activas = {
        posicion_id
        for posicion_id, definicion in por_posicion.items()
        if definicion["ACTIVO"]
    }

    with closing(conectar_sqlite(ruta_base)) as conexion:
        _crear_esquema(conexion)
        # CARRY 2 - No volver a calcular si el corte ya contiene todo el universo.
        resumen = _resumen_desde_conexion(conexion, fecha_corte)
        presentes = set(resumen.get("POSICION_ID", pd.Series(dtype=str)).astype(str))

        if not posiciones_activas.issubset(presentes):
            # CARRY 3 - Un arrastre solo es valido si existe un dia base anterior.
            faltantes_sin_base: list[str] = []
            for posicion_id in sorted(posiciones_activas):
                filas = _filas_historico_posicion(conexion, posicion_id)
                if not any(_fecha(fila["FECHA"]) < fecha_corte for fila in filas):
                    faltantes_sin_base.append(posicion_id)
            if faltantes_sin_base:
                raise ValueError(
                    "Spot no puede trasladarse al corte porque no existe una "
                    "posicion acumulada anterior para: "
                    + ", ".join(faltantes_sin_base)
                )

            # CARRY 4 - Crear una ejecucion propia, aun cuando no haya archivo.
            ejecucion_id = (
                f"SPOT-CARRY-{fecha_corte:%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"
            )
            inicio = _ahora()
            fuente = "CARRY_FORWARD"
            hash_fuente = hashlib.sha256(
                f"{fuente}|{fecha_texto}".encode("utf-8")
            ).hexdigest()
            conexion.execute("BEGIN IMMEDIATE")
            conexion.execute(
                f"""
                INSERT INTO {TABLA_EJECUCIONES_SPOT} (
                    EJECUCION_ID, FECHA_CORTE, ARCHIVO_FUENTE, RUTA_FUENTE,
                    SHA256_FUENTE, SHA256_PARAMETROS, TAMANO_BYTES,
                    MODIFICADO_FUENTE, ORIGEN, ESTADO, USUARIO, INICIO, FIN,
                    MENSAJE
                ) VALUES (?, ?, ?, '', ?, ?, 0, NULL, ?, 'EN_PROCESO', ?, ?, NULL, '')
                """,
                (
                    ejecucion_id,
                    fecha_texto,
                    fuente,
                    hash_fuente,
                    hash_parametros,
                    ORIGEN_CARRY,
                    _usuario(),
                    inicio,
                ),
            )

            # CARRY 5 - Reutilizar el mismo motor; compras y ventas quedaran en cero.
            for posicion_id in sorted(posiciones_activas):
                _recalcular_posicion(
                    conexion,
                    por_posicion[posicion_id],
                    fecha_corte,
                    fecha_corte,
                    ejecucion_id,
                    "CARRY_FORWARD_FECHA_NO_HABIL",
                )
            _actualizar_estado_alertas(conexion, posiciones_activas)
            resumen = _resumen_desde_conexion(conexion, fecha_corte)
            conexion.execute(
                f"""
                UPDATE {TABLA_EJECUCIONES_SPOT}
                SET ESTADO = 'COMPLETADA', FIN = ?, MENSAJE = ?
                WHERE EJECUCION_ID = ?
                """,
                (
                    _ahora(),
                    f"{len(resumen)} posiciones trasladadas sin movimientos",
                    ejecucion_id,
                ),
            )
            conexion.commit()
            registrar_log(
                logger,
                "Spot: se creo el carry-forward acumulado para "
                f"{fecha_texto} ({len(resumen)} posiciones).",
            )
        else:
            registrar_log(
                logger,
                "Spot: el acumulado ya contiene el corte "
                f"{fecha_texto} ({len(resumen)} posiciones); no se recalcula.",
            )

        # CARRY 6 - Entregar exactamente el mismo contrato que una fecha con archivo.
        canonica = _tabla_canonica(resumen, por_posicion)
        canonica.attrs["resumen_spot"] = resumen
        _guardar_tablas_auxiliares_spot(
            conexion,
            ruta_base,
            fecha_texto,
            canonica,
            resumen,
            por_book,
            logger=logger,
        )
        return canonica


def _tabla_canonica(
    resumen: pd.DataFrame,
    por_posicion: dict[str, dict],
) -> pd.DataFrame:
    """Adapta el historico de Spot 2 al contrato comun de Position Monitor.

    PUNTO DE CAMBIO SEGURO: BOOK mostrado, moneda, LB/LT e INSTRUMENTO vienen
    de ``param_spot_2.csv``. En particular, SPOT_CLIENTE publica instrumento
    ``SPOT``; no hay una constante ``Derivados`` dentro del motor.
    """
    if resumen.empty:
        return pd.DataFrame(columns=COLUMNAS_POSICION)
    filas: list[dict] = []
    for _, fila in resumen.iterrows():
        posicion_id = str(fila["POSICION_ID"])
        definicion = por_posicion.get(posicion_id)
        if not definicion or not definicion["ACTIVO"]:
            continue
        # Solo las definiciones activas son candidatas a una futura publicacion.
        filas.append(
            {
                "FECHA": str(fila["FECHA"]),
                "PRODUCTO": "Spot",
                "BOOK": definicion["POSICION_NOMBRE"],
                # Se entrega texto decimal exacto. La capa transversal de
                # consolidacion aplica su contrato numerico legado al publicar.
                "POSICION": _decimal_texto(fila["POSICION_FINAL_USD"]),
                "MONEDA_POSICION": definicion["MONEDA_POSICION"],
                "LB_LT": definicion["LB_LT"],
                "INSTRUMENTO": definicion["INSTRUMENTO"],
                "COMPANY": "Colombia",
                "CLASIFICACION_CONTABLE": "NA",
                "BANKING_CVA_DVA": "Banking",
            }
        )
    return pd.DataFrame(filas, columns=COLUMNAS_POSICION)


def _guardar_tablas_auxiliares_spot(
    conexion,
    ruta_base: Path,
    fecha_texto: str,
    canonica: pd.DataFrame,
    resumen: pd.DataFrame,
    por_book: dict[str, dict],
    logger=None,
) -> None:
    """Replica los soportes Spot sin alterar las tablas transaccionales actuales.

    Estas copias alimentan consultas y diagnostico; la fuente de verdad del
    calculo sigue siendo la base transaccional indicada por ``ruta_base``.
    """
    consultas = {
        "compras_ventas_por_book": (
            f"SELECT * FROM {TABLA_COMPRAS_VENTAS_BOOK_SPOT} WHERE FECHA = ?",
            (fecha_texto,),
        ),
        "movimientos": (
            f"SELECT * FROM {TABLA_MOVIMIENTOS_SPOT} WHERE FECHA = ? AND VIGENTE = 1",
            (fecha_texto,),
        ),
        "alertas": (
            f"SELECT * FROM {TABLA_ALERTAS_SPOT} WHERE FECHA = ? AND VIGENTE = 1",
            (fecha_texto,),
        ),
        "ejecuciones": (
            f"SELECT * FROM {TABLA_EJECUCIONES_SPOT} WHERE FECHA_CORTE = ?",
            (fecha_texto,),
        ),
        "auditoria": (
            f"SELECT * FROM {TABLA_AUDITORIA_SPOT} WHERE FECHA = ?",
            (fecha_texto,),
        ),
    }
    tablas = {
        "posicion_canonica": canonica,
        "posicion_acumulada": resumen,
        "parametros_book": pd.DataFrame(list(por_book.values())),
    }
    tablas.update(
        {
            nombre: pd.read_sql_query(sql, conexion, params=params)
            for nombre, (sql, params) in consultas.items()
        }
    )

    # ADICION AUXILIAR: al usar una ruta de prueba temporal, su auxiliar queda
    # en esa misma carpeta; en operación normal resuelve a risko_auxiliar.db.
    guardar_tablas_auxiliares_modulo(
        "Spot_2_SPOT_CLIENTE",
        fecha_texto,
        tablas,
        ruta_db=ruta_base.with_name("risko_auxiliar.db"),
        logger=logger,
    )


def ejecutar_spot(
    fecha_trabajo: str,
    logger=None,
    *,
    pruebas: bool = False,
    ruta_db: str | Path | None = None,
    ruta_insumo: str | Path | None = None,
) -> pd.DataFrame:
    """Procesa el Reporte de Caja y retorna la tabla canonica de Spot.

    El resumen enriquecido que usa la interfaz queda en
    ``resultado.attrs['resumen_spot']`` para conservar el contrato historico de
    retorno (DataFrame canonico) con el resto de Position Monitor.
    """
    # PASO 1 - Normalizar fecha y resolver el archivo que se va a procesar.
    fecha_corte = _fecha(fecha_trabajo)
    fecha_texto = fecha_corte.strftime("%d/%m/%Y")
    ruta_fuente = Path(ruta_insumo) if ruta_insumo is not None else _ruta_insumo(fecha_corte)
    if not ruta_fuente.exists():
        raise FileNotFoundError(
            "Vector no dejo el Reporte de Caja para Spot: " f"{ruta_fuente}"
        )

    # PASOS 2 Y 3 - Cargar filtros operativos y mapeo del book.
    configuracion = _cargar_configuracion_spot()
    por_book, por_posicion, hash_parametros_libros = _cargar_parametros_spot()

    # PASO 4 - Las huellas identifican exactamente archivo + configuracion.
    hash_parametros = hashlib.sha256(
        (
            hash_parametros_libros
            + "|"
            + VERSION_CONTRATO_CALCULO
            + "|"
            + "|".join(sorted(configuracion["owner_tables_incluidas"]))
        ).encode("utf-8")
    ).hexdigest()
    hash_fuente = _hash_archivo(ruta_fuente)
    ruta_base = _resolver_ruta_db(ruta_db, pruebas=pruebas)

    registrar_log(logger, f"Spot: fuente {ruta_fuente}")
    tipo_base = "aislada" if ruta_db is not None else ("de pruebas" if pruebas else "oficial")
    registrar_log(logger, f"Spot: base {tipo_base} {ruta_base}")

    # PASO 4.1 - IDEMPOTENCIA: si ya existe la misma combinacion de huellas,
    # registrar el intento como OMITIDA y devolver el resultado existente.
    #
    # La validacion del archivo ocurre antes de crear tablas. Si el encabezado
    # o los datos son invalidos, la base queda completamente intacta.
    if ruta_base.exists():
        with closing(conectar_sqlite(ruta_base)) as conexion:
            existe_esquema = conexion.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (TABLA_EJECUCIONES_SPOT,),
            ).fetchone()
            repetida = None
            if existe_esquema:
                repetida = conexion.execute(
                    f"""
                    SELECT EJECUCION_ID FROM {TABLA_EJECUCIONES_SPOT}
                    WHERE FECHA_CORTE = ? AND SHA256_FUENTE = ?
                      AND SHA256_PARAMETROS = ? AND ESTADO = 'COMPLETADA'
                    ORDER BY FIN DESC LIMIT 1
                    """,
                    (fecha_texto, hash_fuente, hash_parametros),
                ).fetchone()
            if repetida:
                ejecucion_duplicada = (
                    f"SPOT-DUP-{fecha_corte:%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"
                )
                instante = _ahora()
                modificado_fuente = datetime.fromtimestamp(
                    ruta_fuente.stat().st_mtime
                ).astimezone().isoformat(timespec="seconds")
                _crear_esquema(conexion)
                conexion.execute("BEGIN IMMEDIATE")
                _guardar_compras_ventas_por_book(
                    conexion,
                    fecha_texto,
                    por_book,
                    ruta_fuente.name,
                    repetida[0],
                )
                conexion.execute(
                    f"""
                    INSERT INTO {TABLA_EJECUCIONES_SPOT} (
                        EJECUCION_ID, FECHA_CORTE, ARCHIVO_FUENTE, RUTA_FUENTE,
                        SHA256_FUENTE, SHA256_PARAMETROS, TAMANO_BYTES,
                        MODIFICADO_FUENTE, ORIGEN, ESTADO, USUARIO, INICIO, FIN,
                        MENSAJE
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'IDEMPOTENCIA', 'OMITIDA',
                              ?, ?, ?, ?)
                    """,
                    (
                        ejecucion_duplicada,
                        fecha_texto,
                        ruta_fuente.name,
                        str(ruta_fuente),
                        hash_fuente,
                        hash_parametros,
                        ruta_fuente.stat().st_size,
                        modificado_fuente,
                        _usuario(),
                        instante,
                        instante,
                        f"Archivo ya procesado en {repetida[0]}",
                    ),
                )
                _insertar_alerta(
                    conexion,
                    ejecucion_duplicada,
                    _alerta(
                        "DUPLICATE_SOURCE_FILE",
                        fecha_texto,
                        f"Archivo y parametros ya procesados en {repetida[0]}; "
                        "no se duplicaron movimientos ni posiciones.",
                    ),
                )
                conexion.commit()
                registrar_log(
                    logger,
                    "ALERTA DUPLICATE_SOURCE_FILE: el archivo y los parametros ya "
                    f"fueron procesados en {repetida[0]}; no se duplican registros.",
                )
                resumen = _resumen_desde_conexion(conexion, fecha_corte)
                canonica = _tabla_canonica(resumen, por_posicion)
                canonica.attrs["resumen_spot"] = resumen
                # ADICION AUXILIAR: refresca la foto aunque el archivo sea idempotente.
                _guardar_tablas_auxiliares_spot(
                    conexion,
                    ruta_base,
                    fecha_texto,
                    canonica,
                    resumen,
                    por_book,
                    logger=logger,
                )
                return canonica

    # PASOS 5 A 7 - Validar, filtrar, clasificar y preparar el detalle fuente.
    movimientos, alertas = _leer_movimientos(
        ruta_fuente,
        fecha_corte,
        por_book,
        configuracion["owner_tables_incluidas"],
        logger=logger,
    )
    _exportar_movimientos_intermedios(movimientos, logger=logger)

    # PASO 7.1 - Crear identificadores y metadatos de esta version de la carga.
    ejecucion_id = f"SPOT-{fecha_corte:%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"
    inicio = _ahora()
    usuario = _usuario()
    modificado = datetime.fromtimestamp(ruta_fuente.stat().st_mtime).astimezone().isoformat(
        timespec="seconds"
    )

    with closing(conectar_sqlite(ruta_base)) as conexion:
        # PASO 7.2 - Desde aqui todo el cambio transaccional se confirma junto.
        _crear_esquema(conexion)
        conexion.execute("BEGIN IMMEDIATE")
        # Detectar si se reemplaza otro archivo del mismo corte o una fecha pasada.
        anteriores = conexion.execute(
            f"""
            SELECT EJECUCION_ID, SHA256_FUENTE FROM {TABLA_EJECUCIONES_SPOT}
            WHERE FECHA_CORTE = ? AND ESTADO = 'COMPLETADA'
            ORDER BY FIN
            """,
            (fecha_texto,),
        ).fetchall()
        fechas_posteriores = conexion.execute(
            f"SELECT DISTINCT FECHA FROM {TABLA_HISTORICO_SPOT}"
        ).fetchall()
        es_historico = any(_fecha(fila[0]) > fecha_corte for fila in fechas_posteriores)

        conexion.execute(
            f"""
            INSERT INTO {TABLA_EJECUCIONES_SPOT} (
                EJECUCION_ID, FECHA_CORTE, ARCHIVO_FUENTE, RUTA_FUENTE,
                SHA256_FUENTE, SHA256_PARAMETROS, TAMANO_BYTES,
                MODIFICADO_FUENTE, ORIGEN, ESTADO, USUARIO, INICIO, FIN, MENSAJE
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'EN_PROCESO', ?, ?, NULL, '')
            """,
            (
                ejecucion_id,
                fecha_texto,
                ruta_fuente.name,
                str(ruta_fuente),
                hash_fuente,
                hash_parametros,
                ruta_fuente.stat().st_size,
                modificado,
                ORIGEN_MOVIMIENTOS,
                usuario,
                inicio,
            ),
        )

        # PASO 7.3 - Las versiones anteriores se conservan para auditoria, pero dejan de
        # participar en el calculo oficial.
        conexion.execute(
            f"UPDATE {TABLA_MOVIMIENTOS_SPOT} SET VIGENTE = 0 "
            "WHERE FECHA = ? AND VIGENTE = 1",
            (fecha_texto,),
        )
        conexion.execute(
            f"UPDATE {TABLA_ALERTAS_SPOT} SET VIGENTE = 0 "
            "WHERE FECHA = ? AND VIGENTE = 1",
            (fecha_texto,),
        )

        if anteriores and any(hash_anterior != hash_fuente for _, hash_anterior in anteriores):
            alertas.append(
                _alerta(
                    "SOURCE_FILE_CHANGE",
                    fecha_texto,
                    "El corte ya tenia otra version del archivo fuente; se recalcula "
                    "esta fecha y todo el historico posterior afectado.",
                )
            )
        if es_historico:
            alertas.append(
                _alerta(
                    "HISTORICAL_REPROCESSING",
                    fecha_texto,
                    "Se reprocesa una fecha anterior al ultimo historico disponible.",
                )
            )

        # PASO 7.4 - Insertar la nueva version del detalle y sus alertas.
        creado = _ahora()
        conexion.executemany(
            f"""
            INSERT INTO {TABLA_MOVIMIENTOS_SPOT} (
                MOVIMIENTO_ID, EJECUCION_ID, FECHA, SOURCE_ROW_ID, TRADE_ID,
                PRODUCTO_ORIGEN, BOOK_ORIGINAL, POSICION_ID, POSICION_NOMBRE,
                DESK, EVTYPE, SETTLE_CCY, AMOUNT_ORIGINAL, TIPO_MOVIMIENTO,
                MONTO_USD, ARCHIVO_FUENTE, FILA_FUENTE, PUBLICABLE, VIGENTE,
                CREATED_AT
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    ejecucion_id,
                    mov["FECHA"],
                    mov["SOURCE_ROW_ID"],
                    mov["TRADE_ID"],
                    mov["PRODUCTO_ORIGEN"],
                    mov["BOOK_ORIGINAL"],
                    mov["POSICION_ID"],
                    mov["POSICION_NOMBRE"],
                    mov["DESK"],
                    mov["EVTYPE"],
                    mov["SETTLE_CCY"],
                    mov["AMOUNT_ORIGINAL"],
                    mov["TIPO_MOVIMIENTO"],
                    mov["MONTO_USD"],
                    ruta_fuente.name,
                    mov["FILA_FUENTE"],
                    mov["PUBLICABLE"],
                    creado,
                )
                for mov in movimientos
            ],
        )
        _guardar_compras_ventas_por_book(
            conexion,
            fecha_texto,
            por_book,
            ruta_fuente.name,
            ejecucion_id,
        )
        for alerta in alertas:
            _insertar_alerta(conexion, ejecucion_id, alerta)

        # PASO 8 - Construir el universo afectado: movimiento, historia o activo.
        posiciones_con_movimiento = {
            mov["POSICION_ID"]
            for mov in movimientos
            if mov["PUBLICABLE"] and mov["POSICION_ID"]
        }
        posiciones_con_historia = {
            fila[0]
            for fila in conexion.execute(
                f"SELECT DISTINCT POSICION_ID FROM {TABLA_HISTORICO_SPOT}"
            ).fetchall()
            if fila[0] in por_posicion and por_posicion[fila[0]]["ACTIVO"]
        }
        # La salida siempre incluye el universo completo de posiciones activas.
        # Si una posicion no tiene historia ni movimientos, _recalcular_posicion
        # crea una fila inicial en cero, con alerta persistente de validacion.
        posiciones_activas = {
            posicion_id
            for posicion_id, definicion in por_posicion.items()
            if definicion["ACTIVO"]
        }
        afectadas = posiciones_con_movimiento | posiciones_con_historia | posiciones_activas

        # PASO 8.1 - Recalcular cada cadena desde el punto anterior mas cercano.
        for posicion_id in sorted(afectadas):
            anteriores_pos = _filas_historico_posicion(conexion, posicion_id)
            fechas_previas = [
                _fecha(fila["FECHA"])
                for fila in anteriores_pos
                if _fecha(fila["FECHA"]) < fecha_corte
            ]
            if fechas_previas:
                ultima = max(fechas_previas)
                inicio_recalculo = min(fecha_corte, ultima + timedelta(days=1))
            else:
                inicio_recalculo = fecha_corte
            _recalcular_posicion(
                conexion,
                por_posicion[posicion_id],
                inicio_recalculo,
                fecha_corte,
                ejecucion_id,
                "REPROCESO_MOVIMIENTOS" if anteriores else "CARGA_MOVIMIENTOS",
            )

        # PASO 9 - Reflejar alertas en cada saldo, cerrar ejecucion y confirmar.
        _actualizar_estado_alertas(conexion, afectadas)
        resumen = _resumen_desde_conexion(conexion, fecha_corte)
        conexion.execute(
            f"""
            UPDATE {TABLA_EJECUCIONES_SPOT}
            SET ESTADO = 'COMPLETADA', FIN = ?, MENSAJE = ?
            WHERE EJECUCION_ID = ?
            """,
            (
                _ahora(),
                f"{len(movimientos)} movimientos; {len(resumen)} posiciones; "
                f"{len(alertas)} alertas de fuente/mapeo",
                ejecucion_id,
            ),
        )
        conexion.commit()

        # PASOS 10 A 12 - Construir salida canonica y copiar soportes auxiliares.
        # ADICION AUXILIAR: copia todas las tablas Spot a la base separada.
        # La transacción y el esquema Spot existentes ya quedaron confirmados.
        canonica = _tabla_canonica(resumen, por_posicion)
        canonica.attrs["resumen_spot"] = resumen
        _guardar_tablas_auxiliares_spot(
            conexion,
            ruta_base,
            fecha_texto,
            canonica,
            resumen,
            por_book,
            logger=logger,
        )

    registrar_log(
        logger,
        f"Spot completado: {len(resumen)} posiciones acumuladas; ejecucion {ejecucion_id}.",
    )
    return canonica


def registrar_posiciones_iniciales(
    fecha_trabajo: str | date,
    posiciones: dict[str, Decimal | str | int],
    *,
    pruebas: bool = False,
    ruta_db: str | Path | None = None,
    archivo_fuente: str = "param_posiciones_iniciales_spot.xlsx",
    logger=None,
) -> pd.DataFrame:
    """Registra/reemplaza anclas validadas y recalcula el historico posterior.

    Esta es la via correcta para sustituir el cero preliminar. El valor recibido
    queda con origen ``EXCEL_INICIAL`` y tiene prioridad sobre movimientos o
    carries de esa misma fecha. Si cambia, todo saldo posterior se reconstruye.
    """
    # ANCLA 1 - Normalizar nombres de book/posicion y valores decimales.
    fecha_inicial = _fecha(fecha_trabajo)
    fecha_texto = fecha_inicial.strftime("%d/%m/%Y")
    por_book, por_posicion, hash_parametros = _cargar_parametros_spot()
    lookup = dict(por_book)
    lookup.update({clave: valor for clave, valor in por_posicion.items()})

    normalizadas: dict[str, tuple[dict, Decimal]] = {}
    for nombre, valor in posiciones.items():
        definicion = lookup.get(normalizar_clave_param(nombre))
        if not definicion:
            raise ValueError(
                f"La posicion inicial {nombre!r} no existe para Spot en param_libros.csv."
            )
        if not definicion["ACTIVO"]:
            raise ValueError(f"La posicion inicial {nombre!r} esta inactiva.")
        normalizadas[definicion["POSICION_ID"]] = (definicion, _decimal(valor))
    if not normalizadas:
        raise ValueError("No se recibieron posiciones iniciales para Spot.")

    # ANCLA 2 - Crear una huella del conjunto completo para evitar doble carga.
    contenido = json.dumps(
        {clave: _decimal_texto(valor) for clave, (_, valor) in normalizadas.items()},
        sort_keys=True,
    )
    hash_fuente = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    ejecucion_id = f"SPOT-INI-{fecha_inicial:%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"
    ruta_base = _resolver_ruta_db(ruta_db, pruebas=pruebas)
    ahora = _ahora()

    with closing(conectar_sqlite(ruta_base)) as conexion:
        _crear_esquema(conexion)
        # ANCLA 3 - Una carga identica ya completada no se repite.
        repetida = conexion.execute(
            f"""
            SELECT EJECUCION_ID FROM {TABLA_EJECUCIONES_SPOT}
            WHERE FECHA_CORTE = ? AND SHA256_FUENTE = ?
              AND SHA256_PARAMETROS = ? AND ORIGEN = ? AND ESTADO = 'COMPLETADA'
            LIMIT 1
            """,
            (fecha_texto, hash_fuente, hash_parametros, ORIGEN_EXCEL),
        ).fetchone()
        if repetida:
            registrar_log(logger, f"Posiciones iniciales ya importadas en {repetida[0]}.")
            return _resumen_desde_conexion(conexion, fecha_inicial)

        conexion.execute("BEGIN IMMEDIATE")
        conexion.execute(
            f"""
            INSERT INTO {TABLA_EJECUCIONES_SPOT} (
                EJECUCION_ID, FECHA_CORTE, ARCHIVO_FUENTE, RUTA_FUENTE,
                SHA256_FUENTE, SHA256_PARAMETROS, TAMANO_BYTES,
                MODIFICADO_FUENTE, ORIGEN, ESTADO, USUARIO, INICIO, FIN, MENSAJE
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 'EN_PROCESO', ?, ?, NULL, '')
            """,
            (
                ejecucion_id,
                fecha_texto,
                archivo_fuente,
                archivo_fuente,
                hash_fuente,
                hash_parametros,
                ahora,
                ORIGEN_EXCEL,
                _usuario(),
                ahora,
            ),
        )

        # ANCLA 4 - Reemplazar la foto inicial y auditar cualquier diferencia.
        for posicion_id, (definicion, valor) in normalizadas.items():
            existente = conexion.execute(
                f"""
                SELECT POSICION_FINAL_USD FROM {TABLA_HISTORICO_SPOT}
                WHERE FECHA = ? AND POSICION_ID = ?
                """,
                (fecha_texto, posicion_id),
            ).fetchone()
            valor_anterior = existente[0] if existente else None
            fila = {
                "FECHA": fecha_texto,
                "POSICION_ID": posicion_id,
                "POSICION_NOMBRE": definicion["POSICION_NOMBRE"],
                "FECHA_ANTERIOR": None,
                "POSICION_ANTERIOR": "0",
                "COMPRAS_USD": "0",
                "VENTAS_USD": "0",
                "MOVIMIENTO_NETO_USD": "0",
                "POSICION_FINAL_USD": _decimal_texto(valor),
                "ARCHIVO_FUENTE": archivo_fuente,
                "EJECUCION_ID": ejecucion_id,
                "TIPO_ORIGEN": ORIGEN_EXCEL,
                "ESTADO": "OK",
                "TIENE_ALERTA": 0,
                "DETALLE_ALERTA": "",
                "USUARIO": _usuario(),
                "CREATED_AT": ahora,
                "UPDATED_AT": ahora,
            }
            _upsert_historico(conexion, fila)
            if valor_anterior != fila["POSICION_FINAL_USD"]:
                _insertar_auditoria(
                    conexion,
                    ejecucion_id,
                    fecha_texto,
                    posicion_id,
                    valor_anterior,
                    fila["POSICION_FINAL_USD"],
                    "INITIAL_POSITION_CHANGE",
                )
                if valor_anterior is not None:
                    _insertar_alerta(
                        conexion,
                        ejecucion_id,
                        _alerta(
                            "INITIAL_POSITION_CHANGE",
                            fecha_texto,
                            "Cambio de posicion inicial; se recalculo el historico posterior.",
                            posicion_id=posicion_id,
                        ),
                    )

            # ANCLA 5 - Propagar el nuevo punto de partida hasta la ultima fecha.
            fechas_existentes = [
                _fecha(fila_db[0])
                for fila_db in conexion.execute(
                    f"SELECT FECHA FROM {TABLA_HISTORICO_SPOT} WHERE POSICION_ID = ?",
                    (posicion_id,),
                ).fetchall()
            ]
            fecha_fin = max(fechas_existentes) if fechas_existentes else fecha_inicial
            if fecha_fin > fecha_inicial:
                _recalcular_posicion(
                    conexion,
                    definicion,
                    fecha_inicial + timedelta(days=1),
                    fecha_fin,
                    ejecucion_id,
                    "INITIAL_POSITION_CHANGE",
                )

        _actualizar_estado_alertas(conexion, set(normalizadas))
        conexion.execute(
            f"""
            UPDATE {TABLA_EJECUCIONES_SPOT}
            SET ESTADO = 'COMPLETADA', FIN = ?, MENSAJE = ?
            WHERE EJECUCION_ID = ?
            """,
            (
                _ahora(),
                f"{len(normalizadas)} posiciones iniciales registradas",
                ejecucion_id,
            ),
        )
        resumen = _resumen_desde_conexion(conexion, fecha_inicial)
        conexion.commit()
    registrar_log(logger, f"Posiciones iniciales Spot registradas: {len(normalizadas)}.")
    return resumen


def _fecha_excel(valor: object) -> date:
    """Interpreta fechas de texto o el numero serial usado por Excel."""
    if isinstance(valor, (int, float)):
        return date(1899, 12, 30) + timedelta(days=int(valor))
    return _fecha(valor)


def importar_posiciones_iniciales_excel(
    *,
    pruebas: bool = False,
    ruta_db: str | Path | None = None,
    ruta_excel: str | Path | None = None,
    logger=None,
) -> pd.DataFrame:
    """Importa el Excel parametrico propio de Risko, nunca ReporteCaja.

    El archivo exige FECHA, POSICION, POSICION_FINAL_USD y ESTADO_PARAMETRO.
    Solo acepta filas ``VALIDADO`` y exige todas las posiciones activas por
    fecha; esto evita convertir accidentalmente un saldo parcial en ancla.
    """
    # EXCEL 1 - Resolver archivo y hoja desde risko.json, salvo ruta explicita.
    configuracion = _cargar_configuracion_spot()
    ruta = Path(ruta_excel or configuracion["archivo_excel_posiciones"])
    hoja = str(configuracion["hoja_excel_posiciones"])
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el Excel de posiciones Spot: {ruta}")

    aliases_fecha = {"FECHA", "FECHA_CORTE"}
    aliases_posicion = {"POSICION", "BOOK", "POSICION_NOMBRE"}
    aliases_valor = {"POSICION_FINAL_USD", "POSICION_FINAL", "VALOR_USD"}
    aliases_estado = {"ESTADO_PARAMETRO", "ESTADO"}
    # EXCEL 2 - Leer XLSX/XLSM o XLSB manteniendo los valores calculados.
    filas: list[list[object]] = []
    extension = ruta.suffix.lower()
    if extension in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RuntimeError("Se requiere openpyxl para leer el parametro Spot.") from exc
        libro = load_workbook(ruta, read_only=True, data_only=True)
        try:
            if hoja not in libro.sheetnames:
                raise ValueError(f"El Excel parametrico Spot no contiene la hoja {hoja!r}.")
            pagina = libro[hoja]
            for numero, fila in enumerate(pagina.iter_rows(values_only=True)):
                if numero >= 5000:
                    break
                filas.append(list(fila))
        finally:
            libro.close()
    elif extension == ".xlsb":
        # Compatibilidad de lectura; la ruta oficial parametrica es XLSX.
        try:
            from pyxlsb import open_workbook
        except ImportError as exc:
            raise RuntimeError("Se requiere pyxlsb para leer archivos .xlsb.") from exc
        with open_workbook(str(ruta)) as libro:
            if hoja not in libro.sheets:
                raise ValueError(f"El Excel parametrico Spot no contiene la hoja {hoja!r}.")
            with libro.get_sheet(hoja) as pagina:
                for numero, fila in enumerate(pagina.rows()):
                    if numero >= 5000:
                        break
                    filas.append([celda.v for celda in fila])
    else:
        raise ValueError(
            f"Formato no soportado para el parametro Spot: {ruta.suffix}. Use .xlsx."
        )

    # EXCEL 3 - Encontrar la tabla por aliases, aunque no inicie en la fila 1.
    encabezado = None
    indices = None
    indice_estado_parametro = None
    for numero, fila in enumerate(filas):
        claves = [normalizar_clave_param(valor) for valor in fila]
        indice_fecha = next((i for i, c in enumerate(claves) if c in aliases_fecha), None)
        indice_pos = next((i for i, c in enumerate(claves) if c in aliases_posicion), None)
        indice_valor = next((i for i, c in enumerate(claves) if c in aliases_valor), None)
        indice_estado = next((i for i, c in enumerate(claves) if c in aliases_estado), None)
        if None not in (indice_fecha, indice_pos, indice_valor):
            encabezado = numero
            indices = (indice_fecha, indice_pos, indice_valor)
            indice_estado_parametro = indice_estado
            break
    if encabezado is None or indices is None:
        raise ValueError(
            f"En la hoja {hoja!r} no se encontro la tabla parametrica. Se exigen "
            "los encabezados FECHA, POSICION y POSICION_FINAL_USD."
        )
    if indice_estado_parametro is None:
        raise ValueError(
            f"La tabla parametrica de {hoja!r} debe incluir ESTADO_PARAMETRO."
        )

    # EXCEL 4 - Validar book activo, estado VALIDADO, duplicados y valor.
    por_book, por_posicion, _ = _cargar_parametros_spot()
    lookup = dict(por_book)
    lookup.update(por_posicion)
    posiciones_esperadas = {
        posicion_id for posicion_id, datos in por_posicion.items() if datos["ACTIVO"]
    }
    por_fecha: dict[date, dict[str, Decimal]] = {}
    ids_por_fecha: dict[date, set[str]] = {}
    errores: list[str] = []
    i_fecha, i_pos, i_valor = indices
    for numero_fila, fila in enumerate(filas[encabezado + 1 :], start=encabezado + 2):
        if max(indices) >= len(fila):
            continue
        if fila[i_fecha] in (None, "") and fila[i_pos] in (None, ""):
            continue
        try:
            fecha_fila = _fecha_excel(fila[i_fecha])
        except ValueError as exc:
            errores.append(f"fila {numero_fila}: {exc}")
            continue
        posicion = str(fila[i_pos]).strip()
        if not posicion:
            errores.append(f"fila {numero_fila}: POSICION vacia")
            continue
        definicion = lookup.get(normalizar_clave_param(posicion))
        if not definicion or not definicion["ACTIVO"]:
            errores.append(
                f"fila {numero_fila}: posicion desconocida o inactiva {posicion!r}"
            )
            continue
        estado_parametro = (
            str(fila[indice_estado_parametro]).strip().upper()
            if indice_estado_parametro < len(fila)
            and fila[indice_estado_parametro] not in (None, "")
            else ""
        )
        estado_valido = estado_parametro == "VALIDADO"
        if not estado_valido:
            errores.append(
                f"fila {numero_fila}: ESTADO_PARAMETRO debe ser VALIDADO para "
                f"{definicion['POSICION_NOMBRE']}"
            )
        posicion_id = definicion["POSICION_ID"]
        if posicion_id in ids_por_fecha.setdefault(fecha_fila, set()):
            errores.append(
                f"fila {numero_fila}: posicion duplicada para {fecha_fila:%d/%m/%Y}: "
                f"{definicion['POSICION_NOMBRE']}"
            )
            continue
        try:
            valor = _decimal(fila[i_valor])
        except (InvalidOperation, ValueError):
            errores.append(
                f"fila {numero_fila}: POSICION_FINAL_USD vacia o invalida para "
                f"{definicion['POSICION_NOMBRE']}"
            )
            continue
        if not estado_valido:
            continue
        ids_por_fecha[fecha_fila].add(posicion_id)
        por_fecha.setdefault(fecha_fila, {})[definicion["POSICION_NOMBRE"]] = valor

    # EXCEL 5 - Cada fecha debe traer el universo completo de posiciones activas.
    for fecha_fila, ids_presentes in ids_por_fecha.items():
        faltantes = posiciones_esperadas - ids_presentes
        if faltantes:
            nombres = [por_posicion[posicion_id]["POSICION_NOMBRE"] for posicion_id in sorted(faltantes)]
            errores.append(
                f"{fecha_fila:%d/%m/%Y}: faltan posiciones activas: {', '.join(nombres)}"
            )
    if errores:
        raise ValueError(
            "El Excel parametrico Spot no supera la validacion:\n- "
            + "\n- ".join(errores)
        )
    if not por_fecha:
        raise ValueError("La tabla parametrica Spot no contiene posiciones para importar.")

    # EXCEL 6 - Registrar cada fecha como ancla y dejar al motor propagarla.
    resultado = pd.DataFrame()
    for fecha_fila in sorted(por_fecha):
        resultado = registrar_posiciones_iniciales(
            fecha_fila,
            por_fecha[fecha_fila],
            pruebas=pruebas,
            ruta_db=ruta_db,
            archivo_fuente=str(ruta),
            logger=logger,
        )
    return resultado


if __name__ == "__main__":
    ejecutar_spot(input("Ingrese fecha de trabajo (dd-mm-aaaa): ").strip())
