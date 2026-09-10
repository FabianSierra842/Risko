"""Ejemplos sintéticos de estudio para el book OPCIONES; no guarda cifras productivas."""
from datetime import date
import json
import math
from pathlib import Path
import sys

RAIZ = next(p for p in Path(__file__).resolve().parents if (p / 'proyectos/pyg').is_dir())
sys.path.insert(0, str(RAIZ))
import pandas as pd
from proyectos.pyg.procesos.opciones import _valor_bsm, revalorar_cartera
from proyectos.pyg.procesos.forward import revalorar_forward
from proyectos.pyg.procesos.caja import atribuir_caja


def curva(moneda, tasa):
    return pd.DataFrame({'Plazo Inferior': [0, 365], 'Plazo Superior': [365, 365],
                         f'Tasas {moneda}': [tasa, tasa]})


def superficie(sigma):
    return pd.DataFrame({'Plazo Inferior': [0, 365], 'Plazo Superior': [365, 365],
                         **{c: [sigma, sigma] for c in ['10 D PUT', '25 D PUT', 'ATM', '25 D CALL', '10 D CALL']}})


def opcion(identificador, lado, tipo, nominal, strike, emision, prima):
    return {'Trade Id': identificador, 'Posición en la opción': lado, 'Tipo de opción': tipo,
            'Fecha de Vencimiento': date(2026, 12, 1), 'Fecha de Cumplimiento': date(2026, 12, 1),
            'Nominal': nominal, 'Precio de Ejercicio': strike, 'Fecha de Emisión': emision,
            'Valor Total Prima': prima, 'Modalidad Cumplimiento': 'NON DELIVERY',
            'Moneda cumplimiento': 'COP', 'Moneda Prima': 'COP'}


def ejecutar():
    previa, corte = date(2026, 7, 31), date(2026, 8, 1)
    c0 = pd.DataFrame([opcion('call_previa', 'BUY', 'CALL', 100, 3000, date(2026, 7, 1), 0)])
    c1 = pd.concat([c0, pd.DataFrame([opcion('put_nueva', 'SELL', 'PUT', 50, 3200, corte, 25000)])], ignore_index=True)
    def vo(cartera, fecha, s, rc, ru, vol):
        return revalorar_cartera(cartera, fecha_valor=fecha, spot=s, curva_cop=curva('COP', rc),
            curva_usd=curva('USD', ru), superficie_vol=superficie(vol), tasas_fix=pd.DataFrame(), inicio_periodo=corte)[0]
    niveles = dict(BASE=vo(c0, previa, 3100, .08, .04, .20),
                   THETA=vo(c0, corte, 3100, .08, .04, .20),
                   DELTA=vo(c0, corte, 3120, .08, .04, .20),
                   RHO=vo(c0, corte, 3120, .081, .042, .20),
                   VEGA=vo(c0, corte, 3120, .081, .042, .21),
                   ACTUAL=vo(c1, corte, 3120, .081, .042, .21))
    componentes = dict(zip(['THETA', 'DELTA_PYG', 'RHO', 'VEGA', 'NUEVOS_OTROS'],
                          [b-a for a,b in zip(list(niveles.values()), list(niveles.values())[1:])]))
    componentes.update(PYG_BANKING=niveles['ACTUAL']-niveles['BASE'], CVA_DVA=-3,
                       PYG_IFRS=niveles['ACTUAL']-niveles['BASE']-3)
    plazo=(date(2026,12,1)-previa).days
    t=plazo/365
    d1=(math.log(3100/3000)+(.08-.04+.5*.20**2)*t)/(.20*math.sqrt(t))
    d2=d1-.20*math.sqrt(t)
    fwd0 = pd.DataFrame([{'Emisión': pd.Timestamp('2026-07-01'), 'Vencimiento': pd.Timestamp('2026-08-31'),
        'Cumplimiento': pd.Timestamp('2026-08-31'), 'Operación': 'COMPRA', 'Nominal': 100000,
        'T.Forward': 4000, 'Modalidad': 'NDF', 'Moneda_Cumplimiento': 'COP'}])
    fwd1 = pd.concat([fwd0, pd.DataFrame([{'Emisión': pd.Timestamp(corte), 'Vencimiento': pd.Timestamp('2026-08-31'),
        'Cumplimiento': pd.Timestamp('2026-08-31'), 'Operación': 'VENTA', 'Nominal': 20000,
        'T.Forward': 4060, 'Modalidad': 'NDF', 'Moneda_Cumplimiento': 'COP'}])], ignore_index=True)
    def vf(cartera, fecha, s, rc, ru):
        return revalorar_forward(cartera, fecha_valor=fecha, spot=s, curva_cop=curva('COP',rc),
            curva_usd=curva('USD',ru), tasas_fix=pd.DataFrame(), inicio_periodo=corte)[0]
    niveles_fwd=dict(BASE=vf(fwd0,previa,4000,.08,.04),THETA=vf(fwd0,corte,4000,.08,.04),
        DELTA=vf(fwd0,corte,4050,.08,.04),RHO=vf(fwd0,corte,4050,.081,.042),ACTUAL=vf(fwd1,corte,4050,.081,.042))
    componentes_fwd=dict(zip(['THETA','DELTA_PYG','RHO','NUEVOS_OTROS'],
        [b-a for a,b in zip(list(niveles_fwd.values()),list(niveles_fwd.values())[1:])]))
    componentes_fwd.update(PYG_BANKING=niveles_fwd['ACTUAL']-niveles_fwd['BASE'],CVA_DVA=-500,
        PYG_IFRS=niveles_fwd['ACTUAL']-niveles_fwd['BASE']-500)
    caja=atribuir_caja(saldo_usd_anterior=100000,trm_anterior=4000,trm_actual=4020,
                      compras_usd=50000,compras_tasa=4005,ventas_usd=30000,ventas_tasa=4010)
    caja.update(COSTO_FONDOS=-40000,AJUSTES=5000)
    caja.update(PYG_BANKING=sum(caja.values()),CVA_DVA=0)
    caja['PYG_IFRS']=caja['PYG_BANKING']
    salida=dict(opciones=dict(plazo_base=plazo,plazo_actual=plazo-1,d1=d1,d2=d2,
        call_unidad=_valor_bsm(3100,3000,plazo,.04,.08,.20,'CALL'),
        nueva_put_mtm=-50*_valor_bsm(3120,3200,plazo-1,.042,.081,.21,'PUT'),
        escenarios=niveles,componentes=componentes),
        forward=dict(escenarios=niveles_fwd,componentes=componentes_fwd),caja=caja,
        cxc_usd=dict(payoff_cop=10000,payoff_usd=10000/3100,cxc_al_3120=10000/3100*3120),
        prima_usd=dict(prima_usd=-5,tasa_prima=3100,prima_cop=-15500))
    # Controles didácticos: fórmula normal con erf y valores publicados en la guía.
    normal = lambda x: (1 + math.erf(x / math.sqrt(2))) / 2
    call_manual = 3100*math.exp(-.04*t)*normal(d1)-3000*math.exp(-.08*t)*normal(d2)
    assert math.isclose(salida['opciones']['call_unidad'], call_manual, rel_tol=0, abs_tol=1e-9)
    for calculado, esperado in ((componentes['PYG_BANKING'], 18350.188235),
                                (componentes_fwd['PYG_BANKING'], 4846837.504194),
                                (caja['PYG_BANKING'], 2415000)):
        assert math.isclose(calculado, esperado, rel_tol=0, abs_tol=1e-5)
    for valores in (componentes, componentes_fwd, caja):
        suma = math.fsum(v for k,v in valores.items() if k not in {'PYG_BANKING','CVA_DVA','PYG_IFRS'})
        assert math.isclose(suma, valores['PYG_BANKING'], rel_tol=0, abs_tol=1e-7)
        assert math.isclose(valores['PYG_BANKING'] + valores['CVA_DVA'], valores['PYG_IFRS'], rel_tol=0, abs_tol=1e-7)
    print(json.dumps(salida,ensure_ascii=False,indent=2))
    return salida


if __name__ == '__main__':
    ejecutar()
