"""Entrega reproducible del código, documentación y referencias del proyecto."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

RAIZ=Path(__file__).resolve().parents[1]
DIRECTORIOS_OMITIDOS={'.git','.venv','__pycache__','.pytest_cache','.vscode',
                      'datos','ejecuciones','entregas','distribucion'}
SUFIJOS_OMITIDOS={'.pyc','.pyo','.db','.sqlite','.sqlite3','.log','.tmp','.zip'}


def archivos_proyecto(raiz=RAIZ):
    raiz=Path(raiz).resolve()
    archivos=[]
    for carpeta,subcarpetas,nombres in os.walk(raiz):
        relativa=Path(carpeta).relative_to(raiz)
        subcarpetas[:]=[n for n in subcarpetas if n not in DIRECTORIOS_OMITIDOS]
        if relativa.as_posix() in ('portal/configuraciones','proyectos/pyg/documentacion/evidencias'):
            subcarpetas[:]=[]
            continue
        if relativa.as_posix()=='portal/comentarios_diarios':
            subcarpetas[:]=[n for n in subcarpetas if not n.isdigit()]
        for nombre in nombres:
            archivo=Path(carpeta)/nombre
            if archivo.suffix.lower() in SUFIJOS_OMITIDOS or nombre.startswith('~$'):
                continue
            if nombre in ('.DS_Store','Thumbs.db') or (nombre.startswith('.env') and nombre!='.env.example'):
                continue
            if archivo.is_symlink():
                continue
            archivos.append(archivo)
    return sorted(archivos,key=lambda p:p.relative_to(raiz).as_posix())


def empaquetar(destino,raiz=RAIZ):
    raiz=Path(raiz).resolve()
    destino=Path(destino).resolve()
    destino.parent.mkdir(parents=True,exist_ok=True)
    temporal=destino.with_suffix('.zip.tmp')
    entradas=[]
    with ZipFile(temporal,'w',ZIP_DEFLATED,compresslevel=9) as zipfile:
        for archivo in archivos_proyecto(raiz):
            contenido=archivo.read_bytes()
            nombre=archivo.relative_to(raiz).as_posix()
            informacion=ZipInfo('Risko/'+nombre)
            informacion.create_system=3
            informacion.external_attr=(0o100755 if archivo.suffix in ('.sh','.command') else 0o100644)<<16
            informacion.compress_type=ZIP_DEFLATED
            zipfile.writestr(informacion,contenido)
            entradas.append(dict(ruta=nombre,bytes=len(contenido),sha256=hashlib.sha256(contenido).hexdigest()))
        manifiesto=dict(proyecto='Risko',creado_en=datetime.now().astimezone().isoformat(),archivos=entradas,
            exclusiones=['Entornos virtuales y cachés','Datos y ejecuciones generadas','Preferencias personales y comentarios diarios del portal','Evidencias históricas de datos operativos'])
        zipfile.writestr('Risko/MANIFIESTO_ENTREGA.json',json.dumps(manifiesto,ensure_ascii=False,indent=2))
    with ZipFile(temporal) as zipfile:
        if corrupto:=zipfile.testzip():
            raise ValueError(f'ZIP inválido: {corrupto}')
    temporal.replace(destino)
    resumen=dict(zip=str(destino),bytes=destino.stat().st_size,archivos=len(entradas),
                 sha256=hashlib.sha256(destino.read_bytes()).hexdigest())
    destino.with_suffix('.sha256').write_text(f"{resumen['sha256']}  {destino.name}\n",encoding='ascii')
    return resumen


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino',default=str(RAIZ/'entregas'/f'Risko_{datetime.now():%Y%m%d}.zip'))
    args=parser.parse_args()
    print(json.dumps(empaquetar(args.destino),ensure_ascii=False,indent=2))
