"""Controles offline con carteras simples y resultados calculables a mano."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import sqlite3
import subprocess
import shutil
import pandas as pd
import pytest

from proyectos.pyg.procesos.configuracion import cargar_configuracion, intervalos
from proyectos.pyg.procesos.consolidacion import consolidar_calculos, leer_calculos
from proyectos.pyg.procesos.opciones import _valor_bsm, revalorar_cartera, calcular_pyg_opciones
from proyectos.pyg.procesos.forward import revalorar_forward, fixing_forward
from proyectos.pyg.procesos.caja import atribuir_caja
from aplicaciones.interfaz_risko.servicios import pyg
from proyectos.pyg.tableros.panel_pyg import PYG_CORE_JS, build_dashboard

OPC_COLS = ['Trade Id','Identificación contraparte','Posición en la opción','Tipo de opción',
            'Fecha de Vencimiento','Fecha de Cumplimiento','Nominal','Precio de Ejercicio',
            'Modalidad Cumplimiento','Moneda cumplimiento','Fecha de Emisión','Valor Total Prima','TAX_ID']

def curva(moneda,tasa=0):
    return pd.DataFrame({'Plazo Inferior':[0,365],'Plazo Superior':[365,365],f'Tasas {moneda}':[tasa,tasa]})

def snapshot(carpeta,corte,spot,credito,pyg_fwd=0,pyg_caja=0):
    ruta=carpeta/f'Dataset Libro de Opciones {corte:%Y%m%d}.xlsx'
    resumen=pd.DataFrame([dict(FECHA=corte,TRM=spot,Opccva=0,Forcva=100*(spot-3000)-credito,
                              Cajausd=1000,Valor_Opciones=0,ValoropcPYG=0)])
    fwd=pd.DataFrame([{'Emisión':date(2026,7,1),'Vencimiento':date(2026,12,1),
        'Cumplimiento':date(2026,12,2),'Operación':'COMPRA','Nominal':100,'T.Forward':3000,
        'Modalidad':'NDF','Moneda_Cumplimiento':'COP'}])
    caja=pd.DataFrame([dict(Fecha=corte,Compras_Monto_USD=0,Compras_Tasa=0,Ventas_Monto_USD=0,Ventas_Tasa=0,
                           Costo_Fondos_COP=0,Ajustes_PyG_COP=0)])
    vol=pd.DataFrame({'Plazo Inferior':[0,365],'Plazo Superior':[365,365],
        **{c:[.15,.15] for c in ['10 D PUT','25 D PUT','ATM','25 D CALL','10 D CALL']}})
    with pd.ExcelWriter(ruta) as writer:
        for hoja,tabla in {'Opciones':pd.DataFrame(columns=OPC_COLS),'Forwards':fwd,'Caja':caja,
            'Resumen':resumen,'Tasas_COP':curva('COP'),'Tasas_USD':curva('USD'),'Superficie_Volatilidad':vol,
            'tfd':pd.DataFrame(columns=['FECHA','TRM1']),'tff':pd.DataFrame(columns=['FECHA','TRM1']),
            'PYG':pd.DataFrame({'Nombres':['PYG_Opc','PYG_Forward','Caja_Dia'],'Valor':[0,pyg_fwd,pyg_caja]})}.items():
            tabla.to_excel(writer,sheet_name=hoja,index=False)
    return ruta

@pytest.fixture
def entorno(tmp_path):
    cfg=cargar_configuracion()
    cfg['libros']['SWAPS']['habilitado']=False
    cfg['rutas']={k:str(tmp_path/k/('pyg.db' if k=='base_datos' else '')) for k in cfg['rutas']}
    insumos=tmp_path/'inputs'
    insumos.mkdir()
    cfg['fuentes']['opciones']['carpeta_datasets']=str(insumos)
    cfg['publicacion']['biblioteca']=str(tmp_path/'Dashboards')
    snapshot(insumos,date(2026,7,31),3100,10)
    snapshot(insumos,date(2026,8,1),3110,12,1000,10000)
    snapshot(insumos,date(2026,8,2),3090,13,-2000,-20000)
    return cfg

def test_mtd_real_desde_cartera_suma_intervalos_y_no_duplica_ifrs(entorno):
    r=pyg.ejecutar_todo_pyg('02/08/2026',cargar_insumos=False,config=entorno)
    assert r.totales['PYG_BANKING']==pytest.approx(-11000)
    assert r.totales['CVA_DVA']==pytest.approx(-3)
    assert r.totales['PYG_IFRS']==pytest.approx(-11003)
    assert r.conciliacion['estado']=='OK'
    assert r.fechas_calculadas==['2026-08-01','2026-08-02']
    assert all(f['COMPONENTE'] not in {'PYG_BANKING','PYG_IFRS'} for f in r.detalle)
    assert all(f['PERIODO']=='DIARIO' for f in r.detalle)
    assert Path(entorno['rutas']['publicados'],'pyg.html').is_file()

def test_reproceso_idempotente_y_diario_separado(entorno):
    a=pyg.ejecutar_todo_pyg('02/08/2026',cargar_insumos=False,config=entorno)
    b=pyg.ejecutar_todo_pyg('02/08/2026',cargar_insumos=False,config=entorno)
    assert a.totales==b.totales
    with sqlite3.connect(entorno['rutas']['base_datos']) as db:
        assert db.execute('select count(*) from tbl_pyg_diario').fetchone()[0]==len(a.detalle)
        assert db.execute('select count(*) from tbl_pyg_ejecuciones').fetchone()[0]==2
    d=pyg.consolidar_pyg('02/08/2026',periodo='DIARIO',config=entorno)
    assert d.totales['PYG_BANKING']==pytest.approx(-22000)
    assert d.totales['CVA_DVA']==pytest.approx(-1)

def test_mtd_no_admite_saltos_ni_producto_ausente(entorno):
    pyg.ejecutar_todo_pyg('02/08/2026',periodo='DIARIO',cargar_insumos=False,config=entorno)
    with pytest.raises(ValueError,match='incompleto'):
        pyg.consolidar_pyg('02/08/2026',periodo='MTD',config=entorno)
    calculos=leer_calculos(entorno['rutas']['base_datos'],'02/08/2026')
    with pytest.raises(ValueError,match='incompleto'):
        consolidar_calculos(calculos[:-1],'02/08/2026',periodo='DIARIO',config=entorno)

def test_falla_calculo_no_altera_cierre_anterior(entorno,monkeypatch):
    pyg.ejecutar_todo_pyg('01/08/2026',periodo='DIARIO',cargar_insumos=False,config=entorno)
    anterior=leer_calculos(entorno['rutas']['base_datos'],'02/08/2026')
    def fallo(*args,**kwargs):
        raise ValueError('Insumo corrupto')
    monkeypatch.setattr('proyectos.pyg.procesos.caja.calcular_pyg_spot',fallo)
    with pytest.raises(ValueError,match='corrupto'):
        pyg.ejecutar_todo_pyg('02/08/2026',periodo='DIARIO',cargar_insumos=False,config=entorno)
    assert leer_calculos(entorno['rutas']['base_datos'],'02/08/2026')==anterior

def test_publicacion_mismo_contrato_portal_corte_y_hash(entorno):
    from proyectos.pyg.procesos.consolidacion import sha256
    pyg.ejecutar_todo_pyg('02/08/2026',cargar_insumos=False,config=entorno)
    pub=pyg.publicar_tablero('02/08/2026',config=entorno)
    carpeta=Path(entorno['publicacion']['biblioteca'])/'PyG'
    assert pub['html']==carpeta/'2026-08-02'/'pyg.html'
    manifest=json.loads((carpeta/'dashboard.json').read_text(encoding='utf-8'))
    meta=json.loads(pub['metadatos'].read_text(encoding='utf-8'))
    assert manifest['archivo']=='pyg.html' and manifest['configuracion']['habilitada']
    assert meta['sha256']==sha256(pub['html'])
    assert meta['fechas_datos']==['2026-08-02']
    assert meta['estado']=='PRELIMINAR'
    assert meta['periodo']=='MTD'

def test_control_no_se_usa_como_calculo_y_bloquea_publicacion(entorno):
    folder=Path(entorno['fuentes']['opciones']['carpeta_datasets'])
    snapshot(folder,date(2026,8,2),3090,13,999999999,888888888)
    r=pyg.ejecutar_todo_pyg('02/08/2026',cargar_insumos=False,config=entorno)
    assert r.totales['PYG_BANKING']==pytest.approx(-11000)
    assert r.conciliacion['estado']=='DIFERENCIA'
    with pytest.raises(ValueError,match='conciliación'):
        pyg.publicar_tablero('02/08/2026',config=entorno)
    assert not Path(entorno['publicacion']['biblioteca']).exists()

def test_caja_trading_y_delta_ventas_mayores():
    c=atribuir_caja(saldo_usd_anterior=10,trm_anterior=3100,trm_actual=3120,
        compras_usd=50,compras_tasa=3105,ventas_usd=80,ventas_tasa=3110)
    assert c==dict(DELTA_INTERDAY=200,TRADING=250,DELTA_INTRADAY=-300)
    assert sum(c.values())==150

def test_forward_cero_tasas_compra_y_venta_y_fix_fin_mes():
    fwd=pd.DataFrame([{'Emisión':pd.Timestamp('2026-07-01'),'Vencimiento':pd.Timestamp('2026-08-31'),
        'Cumplimiento':pd.Timestamp('2026-09-02'),'Operación':'COMPRA','Nominal':100,'T.Forward':3000,'Modalidad':'NDF','Moneda_Cumplimiento':'COP'}])
    kwargs=dict(fecha_valor=date(2026,8,1),spot=3100,curva_cop=curva('COP'),curva_usd=curva('USD'),tasas_fix=pd.DataFrame())
    assert revalorar_forward(fwd,**kwargs)[0]==pytest.approx(10000)
    fwd['Operación']='VENTA'
    assert revalorar_forward(fwd,**kwargs)[0]==pytest.approx(-10000)
    assert fixing_forward(pd.Timestamp('2026-08-31'),date(2026,9,1),3200,pd.DataFrame({'FECHA':[20260901],'TRM1':[3150]}))==3150

def test_opciones_cxc_usd_convertida_y_persistente_hasta_cumplimiento():
    opcion=pd.DataFrame([dict(zip(OPC_COLS,['a','444400','BUY','CALL',pd.Timestamp('2026-08-01'),pd.Timestamp('2026-08-03'),
        100,3000,'NON DELIVERY','USD',pd.Timestamp('2026-07-01'),0,'a']))])
    vol=pd.DataFrame({'Plazo Inferior':[0,365],'Plazo Superior':[365,365],**{c:[.15,.15] for c in ['10 D PUT','25 D PUT','ATM','25 D CALL','10 D CALL']}})
    args=dict(spot=3120,curva_cop=curva('COP'),curva_usd=curva('USD'),superficie_vol=vol,
              tasas_fix=pd.DataFrame({'FECHA':[20260801],'TRM1':[3100]}))
    pendiente,detalle=revalorar_cartera(opcion,fecha_valor=date(2026,8,2),**args)
    assert pendiente==pytest.approx(100*100/3100*3120)
    assert detalle.VALOR_COP.sum()==0
    pagado,detalle=revalorar_cartera(opcion,fecha_valor=date(2026,8,3),**args)
    assert pagado==pytest.approx(10000*3120/3100)
    assert detalle.CXC_COP.sum()==0
    args.update(spot=3300,tasas_fix=pd.DataFrame({'FECHA':[20260801,20260803],'TRM1':[3100,3120]}))
    posterior,_=revalorar_cartera(opcion,fecha_valor=date(2026,8,4),**args)
    assert posterior==pytest.approx(pagado)


def test_forward_cxc_usd_y_flujo_fijado_al_liquidarse():
    fwd=pd.DataFrame([{'Emisión':pd.Timestamp('2026-07-01'),'Vencimiento':pd.Timestamp('2026-08-01'),
        'Cumplimiento':pd.Timestamp('2026-08-03'),'Operación':'COMPRA','Nominal':100,'T.Forward':3000,
        'Modalidad':'NDF','Moneda_Cumplimiento':'USD'}])
    args=dict(spot=3120,curva_cop=curva('COP'),curva_usd=curva('USD'),
              tasas_fix=pd.DataFrame({'FECHA':[20260802,20260804],'TRM1':[3100,3120]}))
    pendiente,d0=revalorar_forward(fwd,fecha_valor=date(2026,8,2),**args)
    pagado,d1=revalorar_forward(fwd,fecha_valor=date(2026,8,3),**args)
    assert pendiente==pytest.approx(10000*3120/3100)
    assert pagado==pytest.approx(pendiente)
    assert d0['CXC_COP']==pendiente and d1['CXC_COP']==0
    args['spot']=3300
    posterior,_=revalorar_forward(fwd,fecha_valor=date(2026,8,4),**args)
    assert posterior==pytest.approx(pagado)


def test_opciones_motor_completo_con_cartera_viva_griegas_y_prima_nueva(entorno):
    # Control analítico independiente: curvas y smile planos, settlement al expiry.
    import math
    def bsm(s,k,dias,ru,rc,vol,tipo):
        t=dias/365
        d1=(math.log(s/k)+(rc-ru+.5*vol**2)*t)/(vol*math.sqrt(t))
        d2=d1-vol*math.sqrt(t)
        cdf=lambda x:(1+math.erf(x/math.sqrt(2)))/2
        if tipo=='CALL':
            return s*math.exp(-ru*t)*cdf(d1)-k*math.exp(-rc*t)*cdf(d2)
        return k*math.exp(-rc*t)*cdf(-d2)-s*math.exp(-ru*t)*cdf(-d1)
    venc=date(2026,12,1)
    previa,actual=date(2026,7,31),date(2026,8,1)
    t0,t1=(venc-previa).days,(venc-actual).days
    base=100*bsm(3100,3000,t0,.04,.08,.2,'CALL')
    theta=100*bsm(3100,3000,t1,.04,.08,.2,'CALL')
    delta=100*bsm(3120,3000,t1,.04,.08,.2,'CALL')
    rho=100*bsm(3120,3000,t1,.042,.081,.2,'CALL')
    vega=100*bsm(3120,3000,t1,.042,.081,.21,'CALL')
    nuevo=-50*bsm(3120,3200,t1,.042,.081,.21,'PUT')
    esperados=dict(THETA=theta-base,DELTA_PYG=delta-theta,RHO=rho-delta,
        VEGA=vega-rho,NUEVOS_OTROS=nuevo+25000,PYG_BANKING=vega+nuevo+25000-base)
    carpeta=Path(entorno['fuentes']['opciones']['carpeta_datasets'])
    for dia,s,ru,rc,vol,mv,credito in [(previa,3100,.04,.08,.2,base,5),(actual,3120,.042,.081,.21,vega+nuevo,8)]:
        ruta=carpeta/f'Dataset Libro de Opciones {dia:%Y%m%d}.xlsx'
        ops=[dict(zip(OPC_COLS,['viva','1','BUY','CALL',venc,venc,100,3000,'NON DELIVERY','COP',date(2026,7,1),0,'a']))]
        if dia==actual:
            ops.append(dict(zip(OPC_COLS,['nueva','2','SELL','PUT',venc,venc,50,3200,'NON DELIVERY','COP',actual,25000,'b'])))
        resumen=pd.read_excel(ruta,sheet_name='Resumen')
        resumen['TRM']=float(s)
        resumen['Opccva']=float(mv-credito)
        superficie=pd.DataFrame({'Plazo Inferior':[0,365],'Plazo Superior':[365,365],
            **{c:[vol,vol] for c in ['10 D PUT','25 D PUT','ATM','25 D CALL','10 D CALL']}})
        with pd.ExcelWriter(ruta,mode='a',if_sheet_exists='replace',engine='openpyxl') as w:
            for nombre,tabla in {'Opciones':pd.DataFrame(ops),'Resumen':resumen,
                'Tasas_COP':curva('COP',rc),'Tasas_USD':curva('USD',ru),'Superficie_Volatilidad':superficie,
                'PYG':pd.DataFrame({'Nombres':['PYG_Opc'],'Valor':[esperados['PYG_BANKING']]})}.items():
                tabla.to_excel(w,sheet_name=nombre,index=False)
    r=calcular_pyg_opciones(actual,config=entorno)
    for componente,valor in esperados.items():
        assert r.componentes[componente]==pytest.approx(valor,abs=1e-7)
    assert r.componentes['CVA_DVA']==pytest.approx(-3,abs=1e-7)
    assert r.conciliacion['estado']=='OK'


def test_moneda_prima_del_snapshot_ff_no_se_confunde_con_cumplimiento():
    from proyectos.pyg.procesos.opciones import _normalizar_opciones
    opcion=pd.DataFrame([dict(zip(OPC_COLS,['prima','1','BUY','CALL',date(2026,12,1),date(2026,12,1),
        0,3000,'NON DELIVERY','COP',date(2026,8,1),-5,'a']))])
    opcion['Moneda de la  Prima']='USD'
    opcion['Tasa Prima']=3100
    opcion=_normalizar_opciones(opcion)
    superficie=pd.DataFrame({'Plazo Inferior':[0,365],'Plazo Superior':[365,365],
        **{c:[.2,.2] for c in ['10 D PUT','25 D PUT','ATM','25 D CALL','10 D CALL']}})
    total,detalle=revalorar_cartera(opcion,fecha_valor=date(2026,8,1),spot=3120,
        curva_cop=curva('COP'),curva_usd=curva('USD'),superficie_vol=superficie,tasas_fix=pd.DataFrame())
    assert total==-15500 and detalle.PRIMA_COP.sum()==-15500

def test_paridad_opciones_call_put():
    import math
    c=_valor_bsm(3100,3000,365,.04,.10,.15,'CALL')
    p=_valor_bsm(3100,3000,365,.04,.10,.15,'PUT')
    assert c-p==pytest.approx(3100*math.exp(-.04)-3000*math.exp(-.10))


def test_volatilidad_colas_y_parametros_invalidos_no_ocultan_valor():
    from proyectos.pyg.procesos.opciones import _volatilidad_cubica
    import numpy as np
    smile=np.array([.15,.16,.17,.18,.19])
    assert _volatilidad_cubica(5000,1000,30,0,0,smile,'CALL',1)==pytest.approx(.15)
    assert _valor_bsm(3100,3000,30,0,0,0,'CALL')==100
    assert _valor_bsm(3100,3000,0,0,0,.2,'PUT')==0
    with pytest.raises(ValueError,match='inválidos'):
        _valor_bsm(3100,3000,30,0,0,-.2,'CALL')
    with pytest.raises(ValueError,match='positivas'):
        _volatilidad_cubica(3100,3000,30,0,0,np.array([.1,.1,0,.1,.1]),'CALL',1)

def test_sin_datos_no_hay_ceros_ni_cifras_de_ejemplo():
    from proyectos.pyg.procesos.novados import calcular_pyg_novados
    from proyectos.pyg.procesos.swaps import calcular_pyg_swaps
    for motor in (calcular_pyg_novados,calcular_pyg_swaps):
        with pytest.raises((ValueError,FileNotFoundError)):
            motor('02/08/2026',book='FX_ESTRAT')

def test_dashboard_filtros_book_periodo_griega_y_cva_sin_doble_conteo():
    if not shutil.which('node'):
        pytest.skip('Node no disponible')
    rows=[dict(FECHA=d,BOOK=b,PRODUCTO='FORWARD',COMPONENTE=c,VALOR_COP=v,VISTA=w)
          for d,b,c,v,w in [('2026-08-01','A','THETA',10,'Banking'),('2026-08-02','A','THETA',20,'Banking'),
                            ('2026-08-02','A','CVA_DVA',-2,'CVA/DVA'),('2026-08-02','B','THETA',99,'Banking')]]
    data=dict(fecha='2026-08-02',periodo='MTD',periodos_disponibles=['DIARIO','MTD'],detalle=rows)
    script=PYG_CORE_JS+'\nconst data='+json.dumps(data)+';\n'
    script+="console.log(JSON.stringify([RiskoPyg.totals(RiskoPyg.selected(data,{BOOK:'A',periodo:'MTD'})),RiskoPyg.totals(RiskoPyg.selected(data,{BOOK:'A',periodo:'DIARIO'})),RiskoPyg.matrix(RiskoPyg.selected(data,{BOOK:'B'}))]));"
    salida=json.loads(subprocess.run(['node','-e',script],capture_output=True,text=True,check=True).stdout)
    assert salida[0]['ifrs']==28 and salida[1]['ifrs']==18
    assert salida[2][0]['book']=='B' and salida[2][0]['banking']==99

def test_snapshots_distintos_en_puente_mtd_exigen_recalcular(entorno):
    pyg.ejecutar_todo_pyg('02/08/2026',cargar_insumos=False,config=entorno)
    calculos=leer_calculos(entorno['rutas']['base_datos'],'02/08/2026')
    c=next(c for c in calculos if c['fecha']=='2026-08-02' and c['producto']=='FORWARD')
    c['fuentes']['anterior']['sha256']='otra-version'
    with pytest.raises(ValueError,match='incompatibles'):
        consolidar_calculos(calculos,'02/08/2026',config=entorno)


def test_diario_rechaza_mezclar_productos_de_snapshots_distintos(entorno):
    pyg.ejecutar_todo_pyg('02/08/2026',periodo='DIARIO',cargar_insumos=False,config=entorno)
    calculos=leer_calculos(entorno['rutas']['base_datos'],'02/08/2026')
    calculos[0]['fuentes']['actual']['sha256']='snapshot-reemplazado'
    with pytest.raises(ValueError,match='incompatibles'):
        consolidar_calculos(calculos,'02/08/2026',periodo='DIARIO',config=entorno)

def test_cambio_de_mes_ancla_calendario_completo():
    cfg=cargar_configuracion()
    assert intervalos('02/08/2026','MTD',cfg)==[(date(2026,7,31),date(2026,8,1)),(date(2026,8,1),date(2026,8,2))]
    cfg['calculo']['calendario']='HABIL_CO'
    assert intervalos('03/08/2026','MTD',cfg)==[(date(2026,7,31),date(2026,8,3))]

def test_opciones_dato_invalido_y_falta_snapshot_son_errores(entorno):
    from proyectos.pyg.procesos.opciones import _numero
    with pytest.raises(ValueError,match='no finito'):
        _numero(float('nan'))
    with pytest.raises(FileNotFoundError):
        calcular_pyg_opciones('03/08/2026',config=entorno)
    with pytest.raises(ValueError,match='preceder'):
        calcular_pyg_opciones('02/08/2026',fecha_anterior='03/08/2026',config=entorno)

def test_ui_filtra_y_suma_filas_del_resultado_sin_constantes():
    from aplicaciones.interfaz_risko.interfaz_pyg import filas_seleccionadas
    from proyectos.pyg.procesos.consolidacion import sumar
    data=dict(fecha='2026-08-02',periodo='DIARIO',detalle=[
        dict(FECHA='2026-08-01',BOOK='A',PRODUCTO='FORWARD',COMPONENTE='THETA',VISTA='Banking',VALOR_COP=99),
        dict(FECHA='2026-08-02',BOOK='A',PRODUCTO='FORWARD',COMPONENTE='THETA',VISTA='Banking',VALOR_COP=12)])
    assert sumar(filas_seleccionadas(data))['PYG_IFRS']==12
    assert filas_seleccionadas(data,book='B')==[]
