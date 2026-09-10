"""Consolidación de atribuciones calculadas: diarios completos y acumulado MTD."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import importlib
import json
import math
from pathlib import Path
import sqlite3
import uuid
from proyectos.pyg.procesos.configuracion import configuracion, fecha, intervalos, seleccionar_libros

COMPONENTES = ("THETA", "DELTA_PYG", "DELTA_INTERDAY", "DELTA_INTRADAY", "DELTA_OTRAS", "RHO", "RHO_COP", "RHO_USD",
               "RHO_DTF", "RHO_IPC", "RHO_OTRAS", "BASE_SPREAD", "VEGA",
               "TRADING", "NUEVOS_OTROS", "AJUSTES", "COSTO_FONDOS", "EPSILON")
MOTORES = {"OPCIONES": ("opciones", "calcular_pyg_opciones"), "FORWARD": ("forward", "calcular_pyg_forward"),
           "CAJA": ("caja", "calcular_pyg_spot"), "NOVADOS": ("novados", "calcular_pyg_novados"),
           "SWAPS": ("swaps", "calcular_pyg_swaps")}

@dataclass(frozen=True)
class ResultadoPygConsolidado:
    fecha: str
    fecha_anterior: str
    estado: str
    detalle: list[dict]
    totales: dict
    totales_producto: dict
    mercado: dict
    conciliacion: dict
    fuentes: dict
    posiciones_control: dict
    calidad: list[dict]
    periodo: str = "MTD"
    libros: list[str] = field(default_factory=list)
    fechas_calculadas: list[str] = field(default_factory=list)
    periodos_disponibles: list[str] = field(default_factory=lambda: ["DIARIO"])
    totales_book: dict = field(default_factory=dict)
    version_motor: str = "pyg-2"

    def to_dict(self):
        return asdict(self)

def numero(valor, nombre):
    try:
        n = float(valor)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{nombre}: valor numérico obligatorio.") from exc
    if not math.isfinite(n):
        raise ValueError(f"{nombre}: no se admite NaN ni infinito.")
    return n

def sha256(ruta):
    digest = hashlib.sha256()
    with Path(ruta).open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()

def calcular_intervalo(corte, anterior, book, producto, config, logger=None):
    if producto not in MOTORES:
        raise ValueError(f"No existe motor PyG para {producto}.")
    modulo, nombre = MOTORES[producto]
    motor = getattr(importlib.import_module(f"proyectos.pyg.procesos.{modulo}"), nombre)
    kwargs = dict(config=config, fecha_anterior=anterior, logger=logger)
    if producto != "OPCIONES":
        kwargs["book"] = book
    elif book != "OPCIONES":
        raise ValueError("El adaptador de Opciones requiere el book OPCIONES.")
    resultado = motor(corte, **kwargs).to_dict()
    if fecha(resultado["fecha"]) != corte or fecha(resultado["fecha_anterior"]) != anterior:
        raise ValueError(f"{book}/{producto}: intervalo del motor distinto del solicitado.")
    comp = resultado["componentes"]
    if "RHO" in comp and any(k in comp for k in ("RHO_COP", "RHO_USD")):
        raise ValueError("No se suman RHO y sus desgloses simultáneamente.")
    banking = {k: numero(comp[k], k) for k in COMPONENTES if k in comp}
    total, cva, ifrs = (numero(comp[k], k) for k in ("PYG_BANKING", "CVA_DVA", "PYG_IFRS"))
    tolerancia = float(config["calculo"].get("tolerancia_conciliacion_cop", 2))
    if not banking or not math.isclose(sum(banking.values()), total, abs_tol=tolerancia, rel_tol=1e-12):
        raise ValueError(f"{book}/{producto}: griegas no concilian con Banking.")
    if not math.isclose(total+cva, ifrs, abs_tol=tolerancia, rel_tol=1e-12):
        raise ValueError(f"{book}/{producto}: Banking + CVA/DVA no coincide con IFRS.")
    filas = [dict(FECHA=corte.isoformat(), FECHA_ANTERIOR=anterior.isoformat(), BOOK=book,
                  PRODUCTO=producto, COMPONENTE=k, VALOR_COP=v,
                  VISTA="CVA/DVA" if k == "CVA_DVA" else "Banking", TIPO="ATRIBUCION",
                  ESTADO="PRELIMINAR", PERIODO="DIARIO") for k,v in {**banking,"CVA_DVA":cva}.items()]
    fuentes = {k: dict(ruta=v,sha256=sha256(v)) for k,v in resultado.get("fuentes",{}).items()
               if isinstance(v,str) and Path(v).is_file()}
    return dict(fecha=corte.isoformat(),fecha_anterior=anterior.isoformat(),book=book,producto=producto,
                filas=filas,resultado=resultado,fuentes=fuentes,version_motor=config["calculo"].get("version_motor","pyg-2"))

def calcular_cortes(fecha_corte, *, config=None, libro="TODOS", periodo="MTD", producto=None, logger=None):
    cfg = configuracion(config)
    calculos = []
    for book in seleccionar_libros(libro,cfg):
        for anterior,corte in intervalos(fecha_corte,periodo,cfg):
            for prod in cfg["libros"][book]["productos"]:
                if producto and prod != producto.upper():
                    continue
                if logger:
                    logger(f"PyG {book}/{prod}: {anterior} → {corte}.")
                calculos.append(calcular_intervalo(corte,anterior,book,prod,cfg,logger))
    if not calculos:
        raise ValueError("El producto no pertenece al alcance seleccionado.")
    return calculos

def guardar_calculos(calculos,ruta_db):
    """Una transacción por corrida; reemplaza solo producto/book/fecha procesados."""
    Path(ruta_db).parent.mkdir(parents=True,exist_ok=True)
    ejecucion = uuid.uuid4().hex
    conexion = sqlite3.connect(ruta_db,timeout=30)
    try:
        with conexion:
            conexion.execute("CREATE TABLE IF NOT EXISTS tbl_pyg_calculos (fecha TEXT,book TEXT,producto TEXT,fecha_anterior TEXT,ejecucion_id TEXT,contenido TEXT,PRIMARY KEY(fecha,book,producto))")
            conexion.execute("CREATE TABLE IF NOT EXISTS tbl_pyg_diario (FECHA TEXT,FECHA_ANTERIOR TEXT,BOOK TEXT,PRODUCTO TEXT,COMPONENTE TEXT,VALOR_COP REAL,VISTA TEXT,TIPO TEXT,ESTADO TEXT,PERIODO TEXT,PRIMARY KEY(FECHA,BOOK,PRODUCTO,COMPONENTE,VISTA))")
            conexion.execute("CREATE TABLE IF NOT EXISTS tbl_pyg_ejecuciones (id TEXT PRIMARY KEY,creado_en TEXT,contenido TEXT)")
            conexion.execute("INSERT INTO tbl_pyg_ejecuciones VALUES (?,?,?)",(ejecucion,datetime.now().astimezone().isoformat(),json.dumps(calculos,ensure_ascii=False,allow_nan=False)))
            cols = ("FECHA","FECHA_ANTERIOR","BOOK","PRODUCTO","COMPONENTE","VALOR_COP","VISTA","TIPO","ESTADO","PERIODO")
            for c in calculos:
                clave = (c["fecha"],c["book"],c["producto"])
                conexion.execute("DELETE FROM tbl_pyg_diario WHERE FECHA=? AND BOOK=? AND PRODUCTO=?",clave)
                conexion.executemany("INSERT INTO tbl_pyg_diario VALUES (?,?,?,?,?,?,?,?,?,?)",[tuple(f[k] for k in cols) for f in c["filas"]])
                conexion.execute("INSERT OR REPLACE INTO tbl_pyg_calculos VALUES (?,?,?,?,?,?)",(*clave,c["fecha_anterior"],ejecucion,json.dumps(c,ensure_ascii=False,allow_nan=False)))
    finally:
        conexion.close()
    return ejecucion

def leer_calculos(ruta_db,corte):
    if not Path(ruta_db).is_file():
        raise FileNotFoundError("No hay cálculos PyG guardados. Ejecute primero los módulos.")
    conexion = sqlite3.connect(Path(ruta_db).resolve().as_uri()+"?mode=ro",uri=True)
    try:
        conexion.execute("PRAGMA query_only=ON")
        return [json.loads(f[0]) for f in conexion.execute("SELECT contenido FROM tbl_pyg_calculos WHERE fecha<=? ORDER BY fecha,book,producto",(fecha(corte).isoformat(),))]
    finally:
        conexion.close()

def sumar(filas):
    totales = {k:0.0 for k in COMPONENTES}
    banking = cva = 0.0
    for fila in filas:
        valor = numero(fila["VALOR_COP"],"VALOR_COP")
        if fila["VISTA"] == "CVA/DVA":
            cva += valor
        else:
            banking += valor
            totales[fila["COMPONENTE"]] = totales.get(fila["COMPONENTE"],0)+valor
    return {**totales,"PYG_BANKING":banking,"CVA_DVA":cva,"CVA":cva,"PYG_IFRS":banking+cva}

def consolidar_calculos(calculos,fecha_corte,*,config=None,libro="TODOS",periodo="MTD",producto=None):
    cfg = configuracion(config)
    corte = fecha(fecha_corte)
    libros = seleccionar_libros(libro,cfg)
    calendario = intervalos(corte,periodo,cfg)
    indice = {}
    for c in calculos:
        clave = (c["fecha"],c["book"],c["producto"])
        if clave in indice:
            raise ValueError(f"Cálculo PyG duplicado: {clave}.")
        indice[clave] = c
    elegidos,faltantes = [],[]
    for anterior,actual in calendario:
        for book in libros:
            for prod in cfg["libros"][book]["productos"]:
                if producto and prod != producto.upper():
                    continue
                clave = (actual.isoformat(),book,prod)
                c = indice.get(clave)
                if c is None or c["fecha_anterior"] != anterior.isoformat():
                    faltantes.append("/".join(clave))
                    continue
                if c.get("version_motor") != cfg["calculo"].get("version_motor","pyg-2"):
                    raise ValueError(f"Recalcule {clave}: procede de otra versión del motor.")
                elegidos.append(c)
    if faltantes:
        raise ValueError("PyG incompleto; faltan intervalos/productos: "+", ".join(faltantes))
    if not elegidos:
        raise ValueError("No hay resultados para el alcance seleccionado.")
    snapshots = {}
    for c in elegidos:
        for rol,dia in (('anterior',c['fecha_anterior']),('actual',c['fecha'])):
            clave = (c['book'],dia)
            huella = c.get('fuentes',{}).get(rol,{}).get('sha256')
            if not huella:
                raise ValueError(f"Falta trazabilidad del snapshot {clave}/{c['producto']}; recalcule el cierre.")
            if clave in snapshots and snapshots[clave] != huella:
                raise ValueError(f"Snapshots incompatibles para {clave}: recalcule los productos y la cadena desde {dia}.")
            snapshots[clave] = huella
    detalle = [f for c in elegidos for f in c["filas"]]
    estados = [c["resultado"].get("conciliacion",{}).get("estado","SIN_REFERENCIA") for c in elegidos]
    conciliacion = "OK" if all(e=="OK" for e in estados) else ("DIFERENCIA" if "DIFERENCIA" in estados else "SIN_REFERENCIA")
    calidad = [dict(control=f"{c['fecha']} · {c['book']} · {c['producto']}",estado=estados[i],detalle="Control independiente del cálculo") for i,c in enumerate(elegidos)]
    for c in elegidos:
        for control in c["resultado"].get("calidad",[]):
            if control.get("estado") != "OK":
                calidad.append(dict(control=f"{c['book']}/{c['producto']} · {control.get('control','Dato')}",estado=control.get("estado","ADVERTENCIA"),detalle=str(control.get("detalle",""))))
    calidad=list({(c['control'],c['estado'],c['detalle']):c for c in calidad}.values())
    return ResultadoPygConsolidado(fecha=corte.isoformat(),fecha_anterior=calendario[0][0].isoformat(),estado="PRELIMINAR",
        detalle=detalle,totales=sumar(detalle),totales_producto={p:sumar([f for f in detalle if f['PRODUCTO']==p]) for p in sorted({f['PRODUCTO'] for f in detalle})},
        totales_book={b:sumar([f for f in detalle if f['BOOK']==b]) for b in libros},mercado=elegidos[-1]['resultado'].get('mercado',{}),
        conciliacion=dict(estado=conciliacion,productos_ok=estados.count('OK'),productos_total=len(estados),intervalos_completos=True,alcance_completo=producto is None),
        fuentes={f"{c['fecha']}/{c['book']}/{c['producto']}":c['fuentes'] for c in elegidos},posiciones_control={},calidad=calidad,
        periodo=periodo.upper(),libros=libros,fechas_calculadas=sorted({c['fecha'] for c in elegidos}),
        periodos_disponibles=['DIARIO','MTD'] if periodo.upper()=='MTD' else ['DIARIO'],version_motor=cfg['calculo'].get('version_motor','pyg-2'))

def calcular_pyg_consolidado(fecha_corte,*,config=None,libro="TODOS",periodo="MTD",logger=None):
    calculos = calcular_cortes(fecha_corte,config=config,libro=libro,periodo=periodo,logger=logger)
    return consolidar_calculos(calculos,fecha_corte,config=config,libro=libro,periodo=periodo)

def calcular_pyg_book_fx_strat(fecha_corte,logger=None,*,config=None,periodo="MTD"):
    return calcular_pyg_consolidado(fecha_corte,config=config,libro="FX_ESTRAT",periodo=periodo,logger=logger).to_dict()
