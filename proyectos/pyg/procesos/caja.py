"""PyG Caja: inventario anterior, trading y variación intradía de operaciones."""
from __future__ import annotations
import pandas as pd
from proyectos.pyg.procesos.opciones import (ResultadoPygOpciones,_fecha,_numero,_fechas_columna,
    cargar_snapshot,resolver_ruta_dataset,resolver_fecha_anterior)
from proyectos.pyg.procesos.configuracion import configuracion
from proyectos.pyg.procesos.atribucion import resultado_producto,control_pyg
ResultadoPygSpot = ResultadoPygOpciones

def atribuir_caja(*,saldo_usd_anterior,trm_anterior,trm_actual,compras_usd,compras_tasa,ventas_usd,ventas_tasa):
    valores = {k:_numero(v) for k,v in locals().items()}
    b,v = valores['compras_usd'],valores['ventas_usd']
    if b<0 or v<0 or valores['trm_anterior']<=0 or valores['trm_actual']<=0:
        raise ValueError('Caja: compras/ventas deben ser positivas y TRM mayor que cero.')
    if (b and compras_tasa<=0) or (v and ventas_tasa<=0):
        raise ValueError('Caja: tasa de negociación obligatoria cuando hay operaciones.')
    return dict(DELTA_INTERDAY=saldo_usd_anterior*(trm_actual-trm_anterior),
                TRADING=min(b,v)*(ventas_tasa-compras_tasa),
                DELTA_INTRADAY=(b-v)*(trm_actual-(compras_tasa if b>=v else ventas_tasa)))

def calcular_pyg_spot(fecha_corte,book='OPCIONES',*,config=None,fecha_anterior=None,logger=None):
    if book.upper()!='OPCIONES':
        from proyectos.pyg.procesos.fx_motores import calcular_caja_fx
        return calcular_caja_fx(fecha_corte,book.upper(),config=config,fecha_anterior=fecha_anterior,logger=logger)
    cfg = configuracion(config)
    corte = _fecha(fecha_corte)
    previa = _fecha(fecha_anterior) if fecha_anterior is not None else resolver_fecha_anterior(corte,cfg)
    if previa>=corte:
        raise ValueError('El snapshot anterior debe preceder al corte.')
    anterior = cargar_snapshot(resolver_ruta_dataset(previa,cfg),previa)
    actual = cargar_snapshot(resolver_ruta_dataset(corte,cfg),corte)
    caja = pd.read_excel(actual.ruta,sheet_name='Caja').dropna(how='all')
    necesarias = {'Fecha','Compras_Monto_USD','Compras_Tasa','Ventas_Monto_USD','Ventas_Tasa'}
    if faltan := necesarias.difference(caja.columns):
        raise ValueError('Caja: faltan columnas '+', '.join(sorted(faltan)))
    caja['Fecha'] = _fechas_columna(caja.Fecha,'Caja.Fecha')
    movimiento = caja.loc[caja.Fecha.eq(pd.Timestamp(corte))]
    if len(movimiento)!=1:
        raise ValueError(f'Caja requiere una fila diaria explícita (incluso sin movimientos) para {corte}.')
    fila = movimiento.iloc[0]
    saldo = _numero(anterior.resumen['Cajausd'])
    b,v = _numero(fila.Compras_Monto_USD),_numero(fila.Ventas_Monto_USD)
    kb = _numero(fila.Compras_Tasa) if b else 0.0
    kv = _numero(fila.Ventas_Tasa) if v else 0.0
    componentes = atribuir_caja(saldo_usd_anterior=saldo,trm_anterior=_numero(anterior.resumen.TRM),trm_actual=_numero(actual.resumen.TRM),
                               compras_usd=b,compras_tasa=kb,ventas_usd=v,ventas_tasa=kv)
    calidad = []
    for fuente,componente in (('Costo_Fondos_COP','COSTO_FONDOS'),('Ajustes_PyG_COP','AJUSTES')):
        if fuente in fila.index:
            componentes[componente] = _numero(fila[fuente])
        else:
            calidad.append(dict(control=componente,estado='NO_INCLUIDO',detalle=f'Sin fuente {fuente}; no se supone tasa ni ajuste.'))
    controles = control_pyg(actual,dict(PYG_BANKING='Caja_Dia',DELTA_INTERDAY='Delta_Caja'))
    return resultado_producto('CAJA',anterior,actual,componentes,dict(SALDO_USD_ANTERIOR=saldo,COMPRAS_USD=b,VENTAS_USD=v),
                              cva_dva=0,config=cfg,controles=controles,calidad=calidad)
