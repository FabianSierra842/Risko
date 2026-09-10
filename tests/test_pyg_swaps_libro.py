from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import math
import pytest

from proyectos.pyg.procesos.configuracion import cargar_configuracion
from proyectos.pyg.procesos.fx_motores import valorar_fx, costo_fondos, calcular_swap_fx
from proyectos.pyg.procesos.fx_snapshot import importar_libro_swaps
from aplicaciones.interfaz_risko.servicios import pyg


def mercado(spot):
    return dict(trm=spot,spot_compra=spot,spot_venta=spot,spread=0,fixings={},
                cop=[[1,0],[365,0]],usd=[[1,0],[365,0]],implicita=[[1,0],[365,0]])


def operacion(ident='f',nominal=100):
    return dict(trade_id=ident,tipo='COMPRA',emision='2026-07-01',vencimiento='2026-12-01',
                cumplimiento='2026-12-01',nominal=nominal,strike=3000,spot_contrato=3100,
                modalidad='SIN ENTREGA',moneda='COP')


@pytest.fixture
def entorno_fx(tmp_path):
    cfg=cargar_configuracion()
    cfg['libros']['OPCIONES']['habilitado']=False
    cfg['rutas']={k:str(tmp_path/k/('pyg.db' if k=='base_datos' else '')) for k in cfg['rutas']}
    carpeta=tmp_path/'inputs'
    carpeta.mkdir()
    cfg['fuentes']['swaps']['carpeta_datasets']=str(carpeta)
    cfg['publicacion']['biblioteca']=str(tmp_path/'Dashboards')
    for dia,spot,bk,ifr,pago,credito,saldo in [('2026-08-31',3100,1000,900,0,-5,10),('2026-09-01',3120,1010,908,5,-7,-20)]:
        caja=dict(saldo_usd=saldo,trm=spot,compras_usd=50,compras_cop=155250,ventas_usd=80,ventas_cop=248800,
                  ftp_cop=0,ajuste_cop=0,ftp_usd=0,ajuste_usd=0)
        factores=dict(THETA=2,DELTA_PYG=3,DELTA_OTRAS=0,RHO_COP=4,RHO_USD=0,RHO_DTF=0,RHO_IPC=0,RHO_OTRAS=0,TRADING=6)
        datos=dict(schema_version=1,book='SWAPS',fecha=dia,mercado=mercado(spot),caja=caja,
            operaciones=dict(FORWARD=[operacion()],NOVADOS=[operacion('n',10)]),
            swaps=[dict(trade_id='swap',banking=bk,ifrs=ifr,pago_cop=pago)],factores_swap=factores,
            credito_acumulado_cop=dict(FORWARD=credito,NOVADOS=0),recuponing_nivel_cop=0,calidad=[],
            controles=dict(FORWARD=dict(PYG_BANKING=2000),NOVADOS=dict(PYG_BANKING=200),
                SWAPS=dict(PYG_BANKING=15,PYG_IFRS=13),CAJA=dict(PYG_BANKING=150)))
        (carpeta/f"Dataset SWAPS {dia.replace('-','')}.json").write_text(json.dumps(datos),encoding='utf-8')
    return cfg


def modificar_actual(cfg,editar):
    archivo=Path(cfg['fuentes']['swaps']['carpeta_datasets'])/'Dataset SWAPS 20260901.json'
    d=json.loads(archivo.read_text(encoding='utf-8'))
    editar(d)
    archivo.write_text(json.dumps(d),encoding='utf-8')


def test_cierre_swaps_cuatro_productos_calculados_sin_totales_de_excel(entorno_fx):
    r=pyg.ejecutar_todo_pyg('01/09/2026',libro='SWAPS',cargar_insumos=False,config=entorno_fx)
    assert r.totales['PYG_BANKING']==pytest.approx(2365)
    assert r.totales['CVA_DVA']==pytest.approx(-4)
    assert r.totales['PYG_IFRS']==pytest.approx(2361)
    assert r.conciliacion['estado']=='OK'
    assert set(r.totales_producto)=={'FORWARD','NOVADOS','CAJA','SWAPS'}
    pub=pyg.publicar_tablero('01/09/2026',libro='SWAPS',config=entorno_fx)
    assert pub['html'].is_file()


def test_swap_neutraliza_pago_y_separa_cva_y_recuponing(entorno_fx):
    modificar_actual(entorno_fx,lambda d:d.update(recuponing_nivel_cop=3))
    r=calcular_swap_fx('01/09/2026',config=entorno_fx)
    assert r.componentes['PYG_BANKING']==15
    assert r.componentes['CVA_DVA']==1
    assert r.componentes['PYG_IFRS']==16
    assert r.escenarios['detalle_operaciones'][0]['PAGO_COP']==5
    assert r.escenarios['RECUPONING']==3


def test_swap_sin_pago_explicito_o_baja_sin_evento_no_cierra(entorno_fx):
    modificar_actual(entorno_fx,lambda d:d['swaps'][0].update(pago_cop=None))
    with pytest.raises(ValueError):
        calcular_swap_fx('01/09/2026',config=entorno_fx)
    modificar_actual(entorno_fx,lambda d:d.update(swaps=[]))
    with pytest.raises(ValueError,match='desapareció'):
        calcular_swap_fx('01/09/2026',config=entorno_fx)


def test_residual_swap_excesivo_no_pasa_solo_por_coincidir_total(entorno_fx):
    modificar_actual(entorno_fx,lambda d:d['factores_swap'].update(TRADING=0))
    r=calcular_swap_fx('01/09/2026',config=entorno_fx)
    assert r.componentes['PYG_BANKING']==15
    assert r.componentes['EPSILON']==6
    assert r.conciliacion['estado']=='DIFERENCIA'
    assert r.conciliacion['residual_ratio']==pytest.approx(.4)


def test_consolida_opciones_y_swaps_en_un_solo_dashboard(entorno_fx,tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('generadores_pyg',Path(__file__).with_name('test_pyg_flujo.py'))
    generadores=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generadores)
    carpeta=tmp_path/'opciones'
    carpeta.mkdir()
    generadores.snapshot(carpeta,date(2026,8,31),3100,10)
    generadores.snapshot(carpeta,date(2026,9,1),3120,12,2000,20000)
    entorno_fx['libros']['OPCIONES']['habilitado']=True
    entorno_fx['fuentes']['opciones']['carpeta_datasets']=str(carpeta)
    r=pyg.ejecutar_todo_pyg('01/09/2026',libro='TODOS',cargar_insumos=False,config=entorno_fx)
    assert set(r.libros)=={'OPCIONES','SWAPS'}
    assert r.totales['PYG_BANKING']==pytest.approx(24365)
    assert r.totales['CVA_DVA']==pytest.approx(-6)
    assert r.conciliacion['productos_total']==7
    assert r.conciliacion['estado']=='OK'


def test_referencia_no_alimenta_motor_y_diferencia_impide_publicar(entorno_fx):
    modificar_actual(entorno_fx,lambda d:d['controles']['FORWARD'].update(PYG_BANKING=999999))
    r=pyg.ejecutar_todo_pyg('01/09/2026',libro='SWAPS',cargar_insumos=False,config=entorno_fx)
    assert r.totales_producto['FORWARD']['PYG_BANKING']==pytest.approx(2000)
    assert r.conciliacion['estado']=='DIFERENCIA'
    with pytest.raises(ValueError,match='conciliación'):
        pyg.publicar_tablero('01/09/2026',libro='SWAPS',config=entorno_fx)


def test_camara_novado_no_descuenta_valor_y_forward_si():
    m=mercado(3100)
    m.update(cop=[[1,.10],[365,.10]],usd=[[1,.04],[365,.04]],implicita=[[1,1.10/1.04-1],[365,1.10/1.04-1]])
    op=operacion()
    op['vencimiento']=op['cumplimiento']='2027-09-01'
    fwd,_=valorar_fx([op],date(2026,9,1),m)
    novado,_=valorar_fx([op],date(2026,9,1),m,camara=True)
    assert fwd==pytest.approx(100*(3100/1.04-3000/1.1))
    assert novado==pytest.approx(100*(3100*1.1/1.04-3000))
    assert novado==pytest.approx(fwd*1.1)


def test_fondeo_no_tiene_sesgo_un_peso_y_tasa_cero_da_cero():
    caja=dict(saldo_usd=100,ftp_cop=0,ajuste_cop=0,ftp_usd=0,ajuste_usd=0)
    assert costo_fondos(caja,3100)['TOTAL']==0
    caja.update(ftp_cop=.12,ftp_usd=.0365)
    r=costo_fondos(caja,3100)
    assert r['COP']==pytest.approx(-310000*((1.12)**(1/365)-1),abs=1e-7)
    assert r['USD']==pytest.approx(310000*.0365/360)


def test_forward_cumplido_conserva_realizado_y_no_revalua_caja():
    op=operacion()
    op.update(vencimiento='2026-09-01',cumplimiento='2026-09-03',moneda='USD')
    m=mercado(3120)
    m['fixings']={'2026-09-01':3100,'2026-09-03':3120}
    pendiente,_=valorar_fx([op],'2026-09-02',m)
    liquidado,_=valorar_fx([op],'2026-09-03',m)
    assert pendiente==pytest.approx(10000*3120/3100)
    assert pendiente==pytest.approx(liquidado)
    m.update(trm=3300,spot_compra=3300,spot_venta=3300)
    posterior,_=valorar_fx([op],'2026-09-04',m)
    assert posterior==pytest.approx(liquidado)


def test_importador_libro_real_lee_original_y_advierte_fechas(tmp_path):
    origen=Path(__file__).resolve().parents[1]/'PYG SWAPS_MES.xlsm'
    if not origen.exists():
        pytest.skip('Libro de referencia no incluido en este entorno')
    import hashlib
    antes=hashlib.sha256(origen.read_bytes()).hexdigest()
    r=importar_libro_swaps(origen,tmp_path/'snapshots')
    assert r['fecha_corte']=='2026-09-08'
    assert len(r['snapshots'])==9
    assert any('cacheado' in c['control'] for c in r['calidad'])
    assert antes==hashlib.sha256(origen.read_bytes()).hexdigest()
    datos=json.loads(r['snapshots'][-1].read_text(encoding='utf-8'))
    assert datos['book']=='SWAPS'
    assert all(op['clasificacion']=='SWAPS' for op in datos['operaciones']['FORWARD'])
    assert all(op['clasificacion']=='SWAPSNOVADO' for op in datos['operaciones']['NOVADOS'])


def test_maestro_sin_limite_fijo_y_filas_solo_formateadas(tmp_path):
    from openpyxl import Workbook
    from proyectos.pyg.procesos.fx_snapshot import ultimas_filas_con_id
    ruta=tmp_path/'maestro.xlsx'
    wb=Workbook()
    wb.active.title='SWAP'
    wb.active['A5005']='ultimo_trade'
    wb.active['A1000000'].number_format='0.00'
    wb.save(ruta)
    wb.close()
    assert ultimas_filas_con_id(ruta,('SWAP',))['SWAP']==5005
