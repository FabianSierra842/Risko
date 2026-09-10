"""Snapshots normalizados del libro SWAPS y lectura de su archivo de referencia.

El importador nunca ejecuta macros ni recalcula/guarda el XLSM. Conserva las
entradas observadas y separa controles cacheados de los importes del motor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import math
import posixpath
from zipfile import ZipFile
from xml.etree import ElementTree as ET
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string as col

from proyectos.pyg.procesos.configuracion import configuracion, fecha, fecha_previa
from proyectos.pyg.procesos.opciones import _numero


@dataclass(frozen=True)
class SnapshotFX:
    fecha: date
    ruta: Path
    datos: dict

    @property
    def resumen(self):
        return pd.Series({'TRM': self.datos['mercado']['trm']})


def cargar_snapshot_fx(ruta, corte, book):
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(f'Falta snapshot {book}: {ruta}')
    datos = json.loads(ruta.read_text(encoding='utf-8'))
    if datos.get('schema_version') != 1 or datos.get('book') != book or fecha(datos['fecha']) != fecha(corte):
        raise ValueError(f'Snapshot FX incompatible con {book}/{corte}: {ruta.name}')
    if _numero(datos['mercado']['trm']) <= 0:
        raise ValueError('TRM del snapshot FX no positiva.')
    return SnapshotFX(fecha(corte),ruta,datos)


def cargar_par_fx(corte, book, *, config=None, fecha_anterior=None):
    cfg = configuracion(config)
    corte = fecha(corte)
    anterior = fecha(fecha_anterior) if fecha_anterior is not None else fecha_previa(corte,cfg)
    if anterior >= corte:
        raise ValueError('El snapshot anterior debe preceder al corte.')
    libro = cfg['libros'].get(book,{})
    if 'fuente' not in libro:
        raise ValueError(f'{book}: falta configurar la fuente de snapshots normalizados.')
    fuente = cfg['fuentes'][libro['fuente']]
    def leer(dia):
        return cargar_snapshot_fx(Path(fuente['carpeta_datasets'])/fuente['patron'].format(fecha=dia),dia,book)
    return leer(anterior),leer(corte),cfg


def _numero_celda(valor, contexto, *, vacio_cero=False):
    if valor in (None,'') and vacio_cero:
        return 0.0
    try:
        return _numero(valor)
    except (TypeError,ValueError) as exc:
        raise ValueError(f'{contexto}: se requiere un importe/tasa válido.') from exc


def _fecha_excel(valor):
    if isinstance(valor,(int,float)) and not isinstance(valor,bool):
        if not math.isfinite(valor):
            raise ValueError('Fecha Excel no finita.')
        return (datetime(1899,12,30)+timedelta(days=valor)).date()
    return fecha(valor)


def ultimas_filas_con_id(ruta,nombres):
    """Ignora filas solo formateadas; no limita el maestro a 1000/5000 filas."""
    ns='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    relacion='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    salida={nombre:8 for nombre in nombres}
    with ZipFile(ruta) as z:
        relaciones={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for hoja in ET.fromstring(z.read('xl/workbook.xml')).find(ns+'sheets'):
            nombre=hoja.attrib['name']
            if nombre not in salida:
                continue
            target=relaciones[hoja.attrib[relacion]]
            archivo=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            with z.open(archivo) as entrada:
                for _,fila in ET.iterparse(entrada,events=('end',)):
                    if fila.tag != ns+'row':
                        continue
                    for celda in fila:
                        coord=celda.attrib.get('r','')
                        if coord.rstrip('0123456789')!='A':
                            continue
                        valor=celda.find(ns+'v')
                        inline=celda.find(ns+'is')
                        if (valor is not None and valor.text not in (None,'')) or (inline is not None and ''.join(inline.itertext()).strip()):
                            salida[nombre]=max(salida[nombre],int(fila.attrib['r']))
                    fila.clear()
    return salida


def importar_libro_swaps(ruta, destino, *, logger=None):
    """Extrae estados por día disponibles; conserva controles de origen abiertos.

    El universo SWAPS sigue el resumen: excluye ARBITR_DER y FX_ESTRAT del
    maestro Swap, y clasifica SWAPSNOVADO separadamente del Forward SWAPS.
    """
    ruta,destino = Path(ruta).resolve(),Path(destino).resolve()
    if not ruta.is_file():
        raise FileNotFoundError(ruta)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    finales=ultimas_filas_con_id(ruta,('Forwards','SWAP'))
    wb = load_workbook(ruta,read_only=True,data_only=True,keep_links=False)
    try:
        limites = {'Parametros':(20,4),'PORTAFOLIO':(75,58),'Tasas':(359,56),
            'Forwards':(finales['Forwards'],50),'Novados':(8,77),'CAJA SWAP':(36,59),
            'GRIEGAS SWAP':(35,73),'SWAP':(finales['SWAP'],207),'PYG Recuponing':(34,12),
            'Hoja de controles':(20,5)}
        tablas = {}
        for hoja,(filas,columnas) in limites.items():
            if hoja not in wb:
                raise ValueError(f'Falta hoja requerida: {hoja}')
            tablas[hoja] = list(wb[hoja].iter_rows(max_row=filas,max_col=columnas,values_only=True))
        def celda(hoja,r,c):
            return tablas[hoja][r-1][col(c)-1] if isinstance(c,str) else tablas[hoja][r-1][c-1]
        def numero(hoja,r,c,**kw):
            return _numero_celda(celda(hoja,r,c),f'{hoja}!{c}{r}',**kw)
        corte = fecha(celda('Parametros',1,'A'))
        inicio = corte.replace(day=1)
        ancla = inicio-timedelta(days=1)
        if fecha(celda('PORTAFOLIO',4,'A')) != ancla:
            raise ValueError('PORTAFOLIO!A4 no contiene el cierre del mes anterior.')
        avisos = [dict(control='Origen',estado='ADVERTENCIA',detalle='Snapshot extraído del libro mensual. Los insumos primarios y Payments Report requieren conciliación.')]
        for r in range(3,21):
            estado = celda('Hoja de controles',r,'D')
            if isinstance(estado,str) and estado.strip().lower() not in ('ok',''):
                avisos.append(dict(control=str(celda('Hoja de controles',r,'B')),estado='ADVERTENCIA',detalle=estado))
        for hoja,c in [('Forwards','W'),('Novados','X')]:
            fecha_cache = celda(hoja,2,c)
            if fecha_cache is not None and fecha(fecha_cache) != corte:
                avisos.append(dict(control=f'Corte cacheado {hoja}',estado='ADVERTENCIA',
                    detalle=f'{fecha(fecha_cache)} frente a portada {corte}; el motor recalcula usando mercado fechado.'))
        operaciones = {'FORWARD':[], 'NOVADOS':[]}
        ids = set()
        for r in range(7,len(tablas['Forwards'])+1):
            row = tablas['Forwards'][r-1]
            if row[0] in (None,''):
                continue
            clasificacion = str(row[12]).strip().upper()
            if clasificacion not in {'SWAPS','SWAPSNOVADO'}:
                continue
            producto = 'NOVADOS' if clasificacion == 'SWAPSNOVADO' else 'FORWARD'
            ident = str(row[0]).strip()
            if ident in ids:
                raise ValueError(f'Trade ID FX duplicado: {ident}')
            ids.add(ident)
            if str(row[4]).upper() != 'USDCOP':
                raise ValueError(f'Par FX no implementado para {ident}: {row[4]}')
            operaciones[producto].append(dict(trade_id=ident,tipo=str(row[1]).upper(),
                emision=_fecha_excel(row[2]).isoformat(),vencimiento=_fecha_excel(row[3]).isoformat(),
                cumplimiento=_fecha_excel(row[10]).isoformat(),nominal=_numero(row[5]),strike=_numero(row[6]),
                spot_contrato=_numero(row[9]),modalidad=str(row[7]).upper(),
                moneda=str(row[13]).upper(),clasificacion=clasificacion))
        # Fixing por fecha: usa la primera tabla B:C identificada en el libro.
        fix = {}
        for r in range(70,len(tablas['Tasas'])+1):
            dia,valor = celda('Tasas',r,'B'),celda('Tasas',r,'C')
            if isinstance(dia,(datetime,date)) and isinstance(valor,(int,float)) and valor>0:
                clave = fecha(dia).isoformat()
                if clave in fix and not math.isclose(fix[clave],valor,abs_tol=.000001):
                    raise ValueError(f'Tasas contiene fixings incompatibles para {clave}')
                fix[clave] = float(valor)
        estados=[]
        credito_fwd = 0.0
        ultimo = ancla
        for dia in [ancla+timedelta(days=i) for i in range((corte-ancla).days+1)]:
            r = 4+(dia-ancla).days
            trm = numero('PORTAFOLIO',r,'B')
            tasas_r = next((j+1 for j,row in enumerate(tablas['Tasas'][:36])
                            if isinstance(row[1],(datetime,date)) and fecha(row[1])==dia),None)
            if tasas_r is None:
                raise ValueError(f'No hay curvas fechadas para {dia}')
            mercado = dict(trm=trm,spot_compra=numero('Tasas',tasas_r,'D'),spot_venta=numero('Tasas',tasas_r,'C'),
                           spread=numero('Forwards',3,'W'),fixings={k:v for k,v in fix.items() if k<=dia.isoformat()})
            mercado['fixings'][dia.isoformat()]=trm
            for nombre,primera in [('implicita',10),('usd',26),('cop',42)]:
                mercado[nombre] = [[numero('Tasas',3,c),numero('Tasas',tasas_r,c)] for c in range(primera,primera+15)]
            caja = dict(saldo_usd=numero('CAJA SWAP',r,'F'),trm=trm)
            if dia != ancla:
                caja.update(compras_usd=numero('CAJA SWAP',r,'T',vacio_cero=True)+numero('CAJA SWAP',r,'Y',vacio_cero=True),
                    compras_cop=numero('CAJA SWAP',r,'U',vacio_cero=True)+numero('CAJA SWAP',r,'Z',vacio_cero=True),
                    ventas_usd=numero('CAJA SWAP',r,'V',vacio_cero=True)+numero('CAJA SWAP',r,'AA',vacio_cero=True),
                    ventas_cop=numero('CAJA SWAP',r,'W',vacio_cero=True)+numero('CAJA SWAP',r,'AB',vacio_cero=True),
                    ftp_cop=numero('CAJA SWAP',r,'AL'),ajuste_cop=numero('CAJA SWAP',r,'AM'),
                    ftp_usd=numero('CAJA SWAP',r,'AP'),ajuste_usd=numero('CAJA SWAP',r,'AQ'))
            swaps=[]
            # Los bloques se identifican por fecha; no por el texto del encabezado.
            columna=8 if dia==ancla else 10+(dia.day-1)*6
            if dia!=ancla and fecha(celda('SWAP',1,columna+3))!=dia:
                raise ValueError(f'Bloque SWAP desalineado para {dia}')
            pagos_vacios=0
            for j in range(9,len(tablas['SWAP'])+1):
                row=tablas['SWAP'][j-1]
                if row[0] in (None,'') or str(row[2]).upper() in {'ARBITR_DER','FX_ESTRAT','FVH'}:
                    continue
                try:
                    emision,fin=_fecha_excel(row[4]),_fecha_excel(row[5])
                except (TypeError,ValueError) as exc:
                    raise ValueError(f'SWAP fila {j}: fechas de operación faltantes.') from exc
                if emision>dia:
                    continue
                bk,ifr=row[columna-1],row[columna]
                if bk in (None,'') and ifr in (None,'') and fin<dia:
                    bk=ifr=0.0
                pago=0.0 if dia==ancla else row[columna+1]
                if pago in (None,''):
                    # Excel trata una celda vacía de Payments como cero. Se
                    # conserva esa convención con advertencia, no como validación.
                    pagos_vacios+=1
                    pago=0.0
                swaps.append(dict(trade_id=str(row[0]).strip(),banking=_numero_celda(bk,f'SWAP fila {j} Banking {dia}'),
                    ifrs=_numero_celda(ifr,f'SWAP fila {j} IFRS {dia}'),pago_cop=_numero(pago)))
            if len({x['trade_id'] for x in swaps}) != len(swaps):
                raise ValueError(f'Trade ID Swap duplicado para {dia}')
            factores={}
            controles={}
            if dia!=ancla:
                gr=dia.day+2
                if fecha(celda('GRIEGAS SWAP',gr,'A'))!=dia:
                    raise ValueError(f'Griegas Swap desalineadas para {dia}')
                for componente,c in dict(THETA='L',DELTA_PYG='M',DELTA_OTRAS='N',RHO_USD='O',RHO_COP='P',
                    RHO_DTF='Q',RHO_IPC='R',RHO_OTRAS='S',TRADING='T').items():
                    factores[componente]=numero('GRIEGAS SWAP',gr,c)
                ir=next((j+1 for j,row in enumerate(tablas['PORTAFOLIO'][40:75],40)
                         if isinstance(row[0],(datetime,date)) and fecha(row[0])==dia),None)
                if ir is None:
                    raise ValueError(f'No hay control IFRS Forward para {dia}')
                referencia_fwd=sum(numero('PORTAFOLIO',r,c,vacio_cero=True) for c in ('H','I','J','K'))
                ref_ifrs=sum(numero('PORTAFOLIO',ir,c,vacio_cero=True) for c in ('H','I','J','K'))
                credito_fwd+=ref_ifrs-referencia_fwd
                controles=dict(FORWARD=dict(PYG_BANKING=referencia_fwd),NOVADOS=dict(PYG_BANKING=numero('PORTAFOLIO',r,'R')),
                    SWAPS=dict(PYG_BANKING=numero('PORTAFOLIO',r,'E'),PYG_IFRS=numero('PORTAFOLIO',ir,'E')),
                    CAJA=dict(PYG_BANKING=numero('PORTAFOLIO',r,'T')+numero('CAJA SWAP',r,'AJ')))
            calidad=list(avisos)
            if pagos_vacios:
                calidad.append(dict(control='Payments Report',estado='ADVERTENCIA',detalle=f'{pagos_vacios} celdas vacías tratadas como cero según Excel; falta confirmar la fuente de pagos.'))
            calidad.append(dict(control='Universo SWAPS',estado='ADVERTENCIA',detalle='Maestro mensual disponible al corte; revisar altas/bajas históricas. Excluye ARBITR_DER y FX_ESTRAT como el resumen SWAPS.'))
            recup=0.0
            if dia!=ancla:
                rr=dia.day+2
                recup=numero('PYG Recuponing',rr,'C')-numero('PYG Recuponing',rr,'B')
            datos=dict(schema_version=1,book='SWAPS',fecha=dia.isoformat(),mercado=mercado,caja=caja,swaps=swaps,
                operaciones={p:[op for op in ops if fecha(op['emision'])<=dia] for p,ops in operaciones.items()},
                credito_acumulado_cop=dict(FORWARD=credito_fwd,NOVADOS=0.0),recuponing_nivel_cop=recup,
                factores_swap=factores,controles=controles,calidad=calidad,
                origen=dict(archivo=ruta.name,sha256=huella,corte_libro=corte.isoformat(),modo='EXTRACCION_LIBRO_MENSUAL'))
            estados.append(datos)
            ultimo=dia
        if hashlib.sha256(ruta.read_bytes()).hexdigest()!=huella:
            raise RuntimeError('El libro cambió durante su lectura; reintente la importación.')
    finally:
        wb.close()
    # Solo después de validar todos los días se publican snapshots de la carga.
    destino.mkdir(parents=True,exist_ok=True)
    rutas=[]
    for datos in estados:
        archivo=destino/f"Dataset SWAPS {fecha(datos['fecha']):%Y%m%d}.json"
        temporal=archivo.with_suffix('.json.tmp')
        temporal.write_text(json.dumps(datos,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        temporal.replace(archivo)
        rutas.append(archivo)
    if logger:
        logger(f'Importados {len(rutas)} snapshots SWAPS hasta {ultimo}. Original XLSM conservado.')
    return dict(fecha_corte=corte.isoformat(),snapshots=rutas,sha256_origen=huella,calidad=avisos)
