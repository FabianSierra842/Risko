"""Motores monetarios Forward, cámara/Novados, Swap y Caja del libro SWAPS.

Las valoraciones del derivado FX se recalculan. Swap usa VP por Trade ID y
pagos de la fuente; sus factores proceden del Informe Libro de Swaps y el
residual se calcula contra el PyG por operación. No se reutiliza posición USD
como si fuese una contribución monetaria.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import timedelta
import math

from proyectos.pyg.procesos.configuracion import fecha
from proyectos.pyg.procesos.opciones import _numero
from proyectos.pyg.procesos.fx_snapshot import cargar_par_fx
from proyectos.pyg.procesos.atribucion import resultado_producto
from proyectos.pyg.procesos.caja import atribuir_caja


def interpolar(nodos,plazo):
    puntos=[(_numero(x),_numero(y)) for x,y in nodos]
    if not puntos or any(y<=-1 or x<0 for x,y in puntos):
        raise ValueError('Curva FX vacía o con tasas fuera de dominio.')
    if any(puntos[i][0]>=puntos[i+1][0] for i in range(len(puntos)-1)):
        raise ValueError('Nodos FX duplicados o desordenados.')
    if plazo<=puntos[0][0]:
        return puntos[0][1]
    if plazo>=puntos[-1][0]:
        return puntos[-1][1]
    for (x0,y0),(x1,y1) in zip(puntos,puntos[1:]):
        if x0<=plazo<=x1:
            return y0+(y1-y0)*(plazo-x0)/(x1-x0)
    raise ValueError('No se pudo interpolar la curva FX.')


def _fijacion(mercado,dia,corte):
    if dia==corte:
        valor=_numero(mercado['trm'])
    else:
        if dia.isoformat() not in mercado['fixings']:
            raise ValueError(f'Falta fixing FX exacto para {dia}.')
        valor=_numero(mercado['fixings'][dia.isoformat()])
    if valor<=0:
        raise ValueError('Fixing FX no positivo.')
    return valor


def _valor_operacion(op,corte,mercado,inicio,*,camara=False):
    emision,vencimiento,cumplimiento=(fecha(op[c]) for c in ('emision','vencimiento','cumplimiento'))
    n,k=_numero(op['nominal']),_numero(op['strike'])
    if n<0 or k<=0 or emision>vencimiento or cumplimiento<vencimiento:
        raise ValueError(f"Operación FX inválida: {op['trade_id']}")
    if op['tipo'] not in ('COMPRA','VENTA') or op['moneda'] not in ('COP','USD'):
        raise ValueError('Dirección o moneda FX no soportada.')
    if op['modalidad'] not in ('SIN ENTREGA','CON ENTREGA','NDF','DF','DELIVERY','NON DELIVERY'):
        raise ValueError(f"Modalidad FX no soportada: {op['modalidad']}")
    signo=1 if op['tipo']=='COMPRA' else -1
    nd=op['modalidad'] in ('SIN ENTREGA','NDF','NON DELIVERY')
    if emision>corte or (cumplimiento<inicio and cumplimiento<=corte):
        return dict(mv=0.0,cxc=0.0,flujo=0.0,total=0.0)
    spot=_numero(mercado['spot_compra' if signo>0 else 'spot_venta'])
    if spot<=0:
        raise ValueError('Spot FX no positivo.')
    t=(cumplimiento-corte).days
    mv=cxc=flujo=0.0
    if corte<vencimiento:
        rc=interpolar(mercado['cop'],t)
        ru=interpolar(mercado['usd'],t)
        tau=t/365
        if camara:
            # Precio de cámara de Novados: sin descuento al valor del contrato.
            forward=_numero(mercado['trm'])*math.exp((math.log1p(rc)-math.log1p(ru))*tau)
            mv=signo*n*(forward-k)
        else:
            # La curva implícita conserva su base respecto a COP/USD. Durante
            # cada escenario solo se sustituye el factor atribuido.
            origen_base=mercado.get('base_curvas',mercado)
            ri0=interpolar(origen_base['implicita'],t)
            ru0=interpolar(origen_base['usd'],t)
            rc0=interpolar(origen_base['cop'],t)
            base=math.log1p(ri0)+math.log1p(ru0)-math.log1p(rc0)
            ri=math.expm1(math.log1p(rc)-math.log1p(ru)+base)
            ri-=(signo*_numero(mercado['spread'])/2)
            if ri<=-1:
                raise ValueError('Tasa implícita ajustada fuera de dominio.')
            mv=signo*n*(spot-k*math.exp(-math.log1p(ri)*tau))*math.exp(-math.log1p(ru)*tau)
    else:
        fixing=_fijacion(mercado,vencimiento,corte)
        payoff=signo*n*(fixing-k)
        if corte<cumplimiento:
            if camara:
                cxc=payoff
            elif nd:
                cxc=payoff*(_numero(mercado['trm'])/fixing if op['moneda']=='USD' else 1)
            else:
                cxc=signo*n*(_numero(mercado['trm'])-k)
        elif cumplimiento>=inicio:
            if camara or (nd and op['moneda']=='COP'):
                flujo=payoff
            else:
                spot_pago=_fijacion(mercado,cumplimiento,corte)
                flujo=payoff*spot_pago/fixing if nd else signo*n*(spot_pago-k)
    total=mv+cxc+flujo
    if not math.isfinite(total):
        raise ValueError('Valoración FX no finita.')
    return dict(mv=mv,cxc=cxc,flujo=flujo,total=total)


def valorar_fx(cartera,corte,mercado,*,inicio=None,camara=False):
    corte=fecha(corte)
    inicio=fecha(inicio) if inicio else corte.replace(day=1)
    ids=[str(op['trade_id']) for op in cartera]
    if len(ids)!=len(set(ids)):
        raise ValueError('Trade ID FX duplicado.')
    detalle=[dict(trade_id=op['trade_id'],**_valor_operacion(op,corte,mercado,inicio,camara=camara)) for op in cartera]
    return math.fsum(row['total'] for row in detalle),detalle


def _resultado(producto,anterior,actual,componentes,escenarios,cva,cfg,calidad):
    calidad=[*actual.datos.get('calidad',[]),*calidad]
    controles=actual.datos.get('controles',{}).get(producto,{})
    resultado=resultado_producto(producto,anterior,actual,componentes,escenarios,cva_dva=cva,
                                 config=cfg,controles=controles,calidad=calidad)
    if 'EPSILON' in componentes:
        residual=abs(componentes['EPSILON'])
        total=abs(resultado.componentes['PYG_BANKING'])
        limite=float(cfg.get('calculo',{}).get('umbral_residual_swap',.07))
        excede=residual>max(total*limite,resultado.conciliacion['tolerancia_cop'])
        resultado.conciliacion.update(residual_cop=componentes['EPSILON'],
            residual_ratio=residual/total if total else None,umbral_residual=limite)
        if excede:
            resultado.conciliacion['estado']='DIFERENCIA'
            resultado.calidad.append(dict(control='Residual Swap',estado='DIFERENCIA',
                detalle=f'El residual supera {limite:.0%} del PyG del producto. Revisar atribución.'))
    return resultado


def calcular_fx(fecha_corte,book='SWAPS',*,producto='FORWARD',config=None,fecha_anterior=None,logger=None):
    anterior,actual,cfg=cargar_par_fx(fecha_corte,book,config=config,fecha_anterior=fecha_anterior)
    if producto not in ('FORWARD','NOVADOS'):
        raise ValueError('Producto FX inválido.')
    camara=producto=='NOVADOS'
    cartera0=anterior.datos['operaciones'][producto]
    cartera1=actual.datos['operaciones'][producto]
    m0,m1=anterior.datos['mercado'],actual.datos['mercado']
    inicio=actual.fecha.replace(day=1)
    def valorar(cartera,dia,mercado):
        return valorar_fx(cartera,dia,mercado,inicio=inicio,camara=camara)
    base,d0=valorar(cartera0,anterior.fecha,m0)
    escenario=deepcopy(m0)
    escenario['base_curvas']=deepcopy(m0)
    escenario['fixings']=m1['fixings']
    theta,_=valorar(cartera0,actual.fecha,escenario)
    for k in ('trm','spot_compra','spot_venta'):
        escenario[k]=m1[k]
    delta,_=valorar(cartera0,actual.fecha,escenario)
    escenario['cop']=m1['cop']
    rho_cop,_=valorar(cartera0,actual.fecha,escenario)
    escenario['usd']=m1['usd']
    rho_usd,_=valorar(cartera0,actual.fecha,escenario)
    escenario['base_curvas']=m1
    escenario['spread']=m1['spread']
    base_spread,_=valorar(cartera0,actual.fecha,escenario)
    final,d1=valorar(cartera1,actual.fecha,m1)
    componentes=dict(THETA=theta-base,DELTA_PYG=delta-theta,RHO_COP=rho_cop-delta,
        RHO_USD=rho_usd-rho_cop,BASE_SPREAD=base_spread-rho_usd,NUEVOS_OTROS=final-base_spread)
    credito=_numero(actual.datos['credito_acumulado_cop'][producto])-_numero(anterior.datos['credito_acumulado_cop'][producto])
    calidad=[dict(control='Método',estado='ADVERTENCIA',detalle=(
        'Cámara CRCC sin descuento; revaloración secuencial y eventos hasta cumplimiento.' if camara else
        'Curvas efectivas ACT/365, base implícita y spread; tiempo, spot, COP, USD y base en secuencia. Requiere conciliar diferencias frente a Excel.')),
        dict(control='Crédito',estado='ADVERTENCIA',detalle='Cambio del ajuste acumulado IFRS-Banking de la fuente, separado de la revaloración FX nativa.')]
    return _resultado(producto,anterior,actual,componentes,
        dict(BASE=base,THETA=theta,DELTA=delta,RHO_COP=rho_cop,RHO_USD=rho_usd,BASE_SPREAD=base_spread,ACTUAL=final,
             detalle_anterior=d0,detalle_actual=d1),credito,cfg,calidad)


def calcular_swap_fx(fecha_corte,book='SWAPS',*,config=None,fecha_anterior=None,logger=None):
    anterior,actual,cfg=cargar_par_fx(fecha_corte,book,config=config,fecha_anterior=fecha_anterior)
    def indexar(snapshot):
        rows=snapshot.datos['swaps']
        indice={str(r['trade_id']):r for r in rows}
        if len(indice)!=len(rows):
            raise ValueError('Trade ID Swap duplicado.')
        return indice
    antes,ahora=indexar(anterior),indexar(actual)
    detalle=[]
    for ident in sorted(set(antes)|set(ahora)):
        old,new=antes.get(ident),ahora.get(ident)
        if new is None:
            raise ValueError(f'Swap {ident} desapareció: se requiere cierre explícito y pago de liquidación.')
        b0,i0=(_numero(old[k]) if old else 0.0 for k in ('banking','ifrs'))
        b1,i1=(_numero(new[k]) for k in ('banking','ifrs'))
        if 'pago_acumulado_cop' in new and (old is None or 'pago_acumulado_cop' in old):
            pago=_numero(new['pago_acumulado_cop'])-(_numero(old['pago_acumulado_cop']) if old else 0)
        elif (actual.fecha-anterior.fecha).days==1:
            pago=_numero(new['pago_cop'])
        else:
            raise ValueError('El intervalo Swap requiere pagos acumulados o todos los días intermedios.')
        detalle.append(dict(trade_id=ident,VP_ANTERIOR=b0,VP_ACTUAL=b1,PAGO_COP=pago,
            PYG_BANKING=b1-b0+pago,PYG_IFRS=i1-i0+pago,CVA_DVA=(i1-b1)-(i0-b0)))
    banking=math.fsum(r['PYG_BANKING'] for r in detalle)
    credito=math.fsum(r['CVA_DVA'] for r in detalle)
    recup=_numero(actual.datos['recuponing_nivel_cop'])-_numero(anterior.datos['recuponing_nivel_cop'])
    factores=actual.datos['factores_swap']
    requeridos={'THETA','DELTA_PYG','DELTA_OTRAS','RHO_COP','RHO_USD','RHO_DTF','RHO_IPC','RHO_OTRAS','TRADING'}
    if set(factores)!=requeridos:
        raise ValueError('Atribución Swap incompleta o con factores desconocidos.')
    if (actual.fecha-anterior.fecha).days!=1:
        raise ValueError('Las griegas Swap son diarias: consolide los intervalos calendario completos.')
    componentes={k:_numero(v) for k,v in factores.items()}
    componentes['EPSILON']=banking-math.fsum(componentes.values())
    calidad=[dict(control='Atribución Swap',estado='ADVERTENCIA',detalle='Factores diarios del Informe Libro de Swaps; total independiente = variación VP + Payments por Trade ID.'),
        dict(control='Recuponing',estado='ADVERTENCIA',detalle=f'Ajuste IFRS adicional del intervalo: {recup:.2f} COP. Requiere confirmar fuente y posición ajustada.')]
    return _resultado('SWAPS',anterior,actual,componentes,
        dict(detalle_operaciones=detalle,RECUPONING=recup,CVA_MERCADO=credito),credito+recup,cfg,calidad)


def costo_fondos(caja,trm):
    saldo=_numero(caja['saldo_usd'])
    cop,aj_cop,usd,aj_usd=(_numero(caja[k]) for k in ('ftp_cop','ajuste_cop','ftp_usd','ajuste_usd'))
    if cop<=-1 or aj_cop<=-1:
        raise ValueError('FTP COP fuera de dominio.')
    tasa_cop=(1+cop)*(1+aj_cop)-1
    # Corrige el -1 fuera del paréntesis en AO del libro (sesgo de 1 COP/día).
    costo_cop=-saldo*trm*math.expm1(math.log1p(tasa_cop)/365)
    costo_usd=saldo*(usd+aj_usd)/360*trm
    return dict(COP=costo_cop,USD=costo_usd,TOTAL=costo_cop+costo_usd)


def calcular_caja_fx(fecha_corte,book='SWAPS',*,config=None,fecha_anterior=None,logger=None):
    anterior,actual,cfg=cargar_par_fx(fecha_corte,book,config=config,fecha_anterior=fecha_anterior)
    c0,c1=anterior.datos['caja'],actual.datos['caja']
    b,bc,v,vc=(_numero(c1[k]) for k in ('compras_usd','compras_cop','ventas_usd','ventas_cop'))
    saldo0,saldo1=_numero(c0['saldo_usd']),_numero(c1['saldo_usd'])
    if not math.isclose(saldo0+b-v,saldo1,abs_tol=.01,rel_tol=0):
        raise ValueError('Caja no concilia saldo inicial + compras - ventas con saldo final.')
    if (not b and bc) or (not v and vc):
        raise ValueError('Caja contiene movimiento COP sin monto USD.')
    trm0,trm1=_numero(c0['trm']),_numero(c1['trm'])
    componentes=atribuir_caja(saldo_usd_anterior=saldo0,trm_anterior=trm0,trm_actual=trm1,
        compras_usd=b,compras_tasa=bc/b if b else 0,ventas_usd=v,ventas_tasa=vc/v if v else 0)
    if (actual.fecha-anterior.fecha).days!=1:
        raise ValueError('Fondeo de Caja exige los intervalos calendario diarios completos.')
    fondos=costo_fondos(c1,trm1)
    componentes['COSTO_FONDOS']=fondos['TOTAL']
    return _resultado('CAJA',anterior,actual,componentes,
        dict(SALDO_ANTERIOR=saldo0,SALDO_ACTUAL=saldo1,FONDEO_COP=fondos['COP'],FONDEO_USD=fondos['USD']),0,cfg,
        [dict(control='FTP COP',estado='ADVERTENCIA',detalle='Se corrige el paréntesis de AO: saldo COP × ((1+tasa)^(1/365) − 1). Diferencia esperada de 1 COP/día frente al Excel.')])
