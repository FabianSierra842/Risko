"""Orquestación PyG: insumos, motores, SQLite, tablero y publicación por fecha."""
from __future__ import annotations
from datetime import datetime
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from compartido.nucleo_risko.rutas import CARPETA_DASHBOARDS_PORTAL
from proyectos.pyg.procesos.configuracion import (RAIZ_RISKO, configuracion, fecha, intervalos,
                                                libros_configurados, seleccionar_libros)
from proyectos.pyg.procesos.consolidacion import (calcular_cortes, guardar_calculos,
    leer_calculos, consolidar_calculos, sha256)
from proyectos.pyg.tableros.panel_pyg import build_dashboard

ARCHIVO_VECTOR = RAIZ_RISKO / 'Herramientas' / 'VECTOR' / 'VECTOR.py'
ARCHIVO_CONFIG_VECTOR = RAIZ_RISKO / 'proyectos' / 'pyg' / 'configuracion' / 'vector_pyg.json'

def _json_atomico(ruta,datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True,exist_ok=True)
    temporal = ruta.with_name('.'+ruta.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporal.write_text(json.dumps(datos,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        os.replace(temporal,ruta)
    finally:
        temporal.unlink(missing_ok=True)

def ejecutar_vector_pyg(fecha_trabajo,logger=None,*,libro='TODOS',periodo='MTD',config=None):
    cfg = configuracion(config)
    libros = seleccionar_libros(libro,cfg)
    if any(b!='OPCIONES' for b in libros):
        raise ValueError('Para SWAPS importe primero el libro mensual y desmarque Cargar insumos con Vector. Vector de fuentes primarias requiere el mapeo de sus archivos.')
    if not ARCHIVO_VECTOR.is_file():
        raise FileNotFoundError(f'No está instalado Vector en {ARCHIVO_VECTOR}. Puede calcular con snapshots locales.')
    vector = json.loads(ARCHIVO_CONFIG_VECTOR.read_text(encoding='utf-8'))
    vector['global_vars']['insumos_pyg'] = cfg['fuentes']['opciones']['carpeta_datasets']
    vector['global_vars']['datasets_opciones'] = cfg['fuentes']['opciones']['carpeta_origen']
    vector['logs_tpl'] = str(Path(cfg['rutas']['ejecuciones'])/'vector'/'{yyyy}-{mm}-{dd}')
    temporal = Path(cfg['rutas']['ejecuciones'])/f'vector_{uuid.uuid4().hex}.json'
    _json_atomico(temporal,vector)
    fechas = sorted({f for par in intervalos(fecha_trabajo,periodo,cfg) for f in par})
    try:
        for corte in fechas:
            if logger:
                logger(f'Vector PyG: snapshot {corte}.')
            proceso = subprocess.run([sys.executable,str(ARCHIVO_VECTOR),'--cli','--config',str(temporal),
                '--fecha',corte.strftime('%d/%m/%Y'),'--flow-name',cfg['vector']['flujo_dataset'],'--no-dry-run'],
                cwd=RAIZ_RISKO,text=True,capture_output=True,check=False,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if logger:
                for linea in (proceso.stdout+'\n'+proceso.stderr).splitlines():
                    logger(linea)
            if proceso.returncode:
                raise RuntimeError(f'Vector PyG falló en {corte}: {proceso.stderr}')
    finally:
        temporal.unlink(missing_ok=True)
    return {f.isoformat():Path(cfg['fuentes']['opciones']['carpeta_datasets'])/cfg['fuentes']['opciones']['patron'].format(fecha=f) for f in fechas}

def _preservar_snapshots(corte,periodo,libro,cfg):
    # Los motores leen copias estables, no el archivo que Vector podría reemplazar.
    from copy import deepcopy
    copia = deepcopy(cfg)
    for book in seleccionar_libros(libro,cfg):
        fuente = cfg['libros'][book]['fuente']
        datos = cfg['fuentes'][fuente]
        fechas = sorted({f for par in intervalos(corte,periodo,cfg) for f in par})
        rutas = [Path(datos['carpeta_datasets'])/datos['patron'].format(fecha=f) for f in fechas]
        faltantes = [str(p) for p in rutas if not p.is_file()]
        if faltantes:
            raise FileNotFoundError('Faltan snapshots PyG: '+', '.join(faltantes))
        destino = Path(cfg['rutas']['ejecuciones'])/uuid.uuid4().hex/'insumos'/book
        destino.mkdir(parents=True,exist_ok=True)
        for origen in rutas:
            antes = sha256(origen)
            shutil.copyfile(origen,destino/origen.name)
            if sha256(destino/origen.name)!=antes or sha256(origen)!=antes:
                raise RuntimeError(f'El snapshot cambió durante la copia: {origen}. Reintente la corrida.')
        copia['fuentes'][fuente]['carpeta_datasets'] = str(destino)
    return copia

def ejecutar_todo_pyg(fecha_trabajo,logger=None,*,libro='TODOS',periodo='MTD',cargar_insumos=True,config=None):
    cfg = configuracion(config)
    if cargar_insumos:
        ejecutar_vector_pyg(fecha_trabajo,logger,libro=libro,periodo=periodo,config=cfg)
    estable = _preservar_snapshots(fecha_trabajo,periodo,libro,cfg)
    calculos = calcular_cortes(fecha_trabajo,config=estable,libro=libro,periodo=periodo,logger=logger)
    # Primero se valida la corrida completa; una falla no mezcla productos nuevos con viejos.
    consolidar_calculos(calculos,fecha_trabajo,config=cfg,libro=libro,periodo=periodo)
    guardar_calculos(calculos,cfg['rutas']['base_datos'])
    resultado = consolidar_pyg(fecha_trabajo,logger,libro=libro,periodo=periodo,config=cfg)
    build_dashboard(resultado,Path(cfg['rutas']['publicados'])/'pyg.html')
    return resultado

def ejecutar_producto_pyg(producto,fecha_trabajo,logger=None,*,libro='TODOS',periodo='MTD',cargar_insumos=True,config=None):
    cfg = configuracion(config)
    if cargar_insumos:
        ejecutar_vector_pyg(fecha_trabajo,logger,libro=libro,periodo=periodo,config=cfg)
    estable = _preservar_snapshots(fecha_trabajo,periodo,libro,cfg)
    calculos = calcular_cortes(fecha_trabajo,config=estable,libro=libro,periodo=periodo,producto=producto,logger=logger)
    resultado = consolidar_calculos(calculos,fecha_trabajo,config=cfg,libro=libro,periodo=periodo,producto=producto)
    guardar_calculos(calculos,cfg['rutas']['base_datos'])
    return resultado

def consolidar_pyg(fecha_trabajo,logger=None,*,libro='TODOS',periodo='MTD',config=None):
    cfg = configuracion(config)
    calculos = leer_calculos(cfg['rutas']['base_datos'],fecha_trabajo)
    resultado = consolidar_calculos(calculos,fecha_trabajo,config=cfg,libro=libro,periodo=periodo)
    archivo = Path(cfg['rutas']['procesados'])/f"pyg_{resultado.fecha}_{libro}_{periodo}.json"
    _json_atomico(archivo,resultado.to_dict())
    if logger:
        logger(f'Consolidado {periodo}: {len(resultado.detalle)} contribuciones; conciliación {resultado.conciliacion["estado"]}.')
    return resultado

def cargar_resultado(fecha_trabajo,*,libro='TODOS',periodo='MTD',config=None):
    return consolidar_pyg(fecha_trabajo,libro=libro,periodo=periodo,config=config).to_dict()


def importar_swaps(ruta,logger=None,*,config=None):
    from proyectos.pyg.procesos.fx_snapshot import importar_libro_swaps
    cfg=configuracion(config)
    return importar_libro_swaps(ruta,cfg['fuentes']['swaps']['carpeta_datasets'],logger=logger)

def generar_tablero(fecha_trabajo,logger=None,*,libro='TODOS',periodo='MTD',config=None):
    cfg = configuracion(config)
    resultado = consolidar_pyg(fecha_trabajo,logger,libro=libro,periodo=periodo,config=cfg)
    salida = build_dashboard(resultado,Path(cfg['rutas']['publicados'])/'pyg.html')
    if logger:
        logger(f'Tablero generado: {salida}')
    return salida

def publicar_tablero(fecha_trabajo,logger=None,html_origen=None,*,libro='TODOS',periodo='MTD',config=None):
    cfg = configuracion(config)
    resultado = consolidar_pyg(fecha_trabajo,logger,libro=libro,periodo=periodo,config=cfg)
    estado = resultado.conciliacion['estado']
    if cfg.get('publicacion',{}).get('exigir_conciliacion',True) and estado!='OK':
        raise ValueError(f'PyG pendiente de conciliación ({estado}); revise el tablero local antes de publicar.')
    # Se regenera desde el corte verificado; no se copia un HTML de otro libro o fecha.
    origen = build_dashboard(resultado,Path(cfg['rutas']['publicados'])/'pyg.html')
    biblioteca = Path(cfg.get('publicacion',{}).get('biblioteca',CARPETA_DASHBOARDS_PORTAL))
    carpeta = biblioteca/'PyG'
    destino = carpeta/resultado.fecha
    destino.mkdir(parents=True,exist_ok=True)
    archivo = destino/'pyg.html'
    temporal = destino/f'.pyg.{uuid.uuid4().hex}.tmp'
    try:
        shutil.copyfile(origen,temporal)
        os.replace(temporal,archivo)
    finally:
        temporal.unlink(missing_ok=True)
    _json_atomico(carpeta/'dashboard.json',dict(schema_version=1,id='pyg',nombre='PyG',
        descripcion='Resultado por libro, producto y griega',archivo='pyg.html',configuracion={'habilitada':True}))
    ahora = datetime.now().astimezone()
    metadata = dict(schema_version=1,dashboard='PyG',fecha_posicion_solicitada=resultado.fecha,
        fecha_publicacion=ahora.date().isoformat(),fechas_datos=[resultado.fecha],archivo=archivo.name,
        sha256=sha256(archivo),tamano_bytes=archivo.stat().st_size,publicado_en=ahora.isoformat(),
        publicado_por=getpass.getuser(),estado=resultado.estado,tipo_corte='PYG',periodo=resultado.periodo,
        libros=resultado.libros,fecha_inicio=resultado.fecha_anterior,conciliacion=resultado.conciliacion,
        fuentes=resultado.fuentes,version_motor=resultado.version_motor)
    _json_atomico(destino/'publicacion.json',metadata)
    if logger:
        logger(f'PyG publicado: {archivo}')
    return dict(html=archivo,carpeta=destino,metadatos=destino/'publicacion.json',metadata=metadata)
