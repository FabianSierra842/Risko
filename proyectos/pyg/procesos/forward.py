"""Atribución Forward del book Opciones mediante revaloración de snapshots."""
from __future__ import annotations
from datetime import timedelta
import math
import pandas as pd
from proyectos.pyg.procesos.opciones import (
    ResultadoPygOpciones, _fecha, _numero, _texto, _interpolar, _fechas_columna,
    _normalizar_fix, cargar_snapshot, resolver_ruta_dataset, resolver_fecha_anterior)
from proyectos.pyg.procesos.configuracion import configuracion
from proyectos.pyg.procesos.atribucion import resultado_producto, control_pyg

ResultadoPygForward = ResultadoPygOpciones

def cargar_forwards(ruta):
    tabla = pd.read_excel(ruta,sheet_name="Forwards").dropna(how="all")
    requeridas = {"Emisión","Vencimiento","Cumplimiento","Operación","Nominal","T.Forward","Modalidad","Moneda_Cumplimiento"}
    if faltan := requeridas.difference(tabla.columns):
        raise ValueError("Forwards: faltan columnas "+", ".join(sorted(faltan)))
    for c in ("Emisión","Vencimiento","Cumplimiento"):
        tabla[c] = _fechas_columna(tabla[c],f"Forwards.{c}")
    for c in ("Nominal","T.Forward"):
        tabla[c] = tabla[c].map(_numero)
    for c,permitidos in (("Operación",{"COMPRA","VENTA"}),("Modalidad",{"DF","NDF"}),("Moneda_Cumplimiento",{"COP","USD"})):
        tabla[c] = tabla[c].map(_texto)
        if not tabla[c].isin(permitidos).all():
            raise ValueError(f"Forwards: valor inválido en {c}")
    if (tabla.Nominal<0).any() or (tabla['T.Forward']<=0).any() or (tabla.Cumplimiento<tabla.Vencimiento).any() or (tabla['Emisión']>tabla.Vencimiento).any():
        raise ValueError("Forwards: nominal, strike o fechas inválidas.")
    return tabla

def fixing_forward(vencimiento,fecha_valor,spot,tasas_fix):
    if vencimiento.date()==fecha_valor:
        return spot
    # FF_V3 usa la fila del día siguiente al fixing. La suma debe ser calendario.
    objetivo = int((vencimiento+pd.Timedelta(days=1)).strftime('%Y%m%d'))
    fila = tasas_fix.loc[tasas_fix.FECHA.eq(objetivo),'TRM1']
    if len(fila)!=1:
        raise ValueError(f"Falta fixing Forward tff para {objetivo}.")
    valor = _numero(fila.iloc[0])
    if valor<=0:
        raise ValueError("Fixing Forward no positivo.")
    return valor

def revalorar_forward(cartera,*,fecha_valor,spot,curva_cop,curva_usd,tasas_fix,inicio_periodo=None):
    """Tasas continuas ACT/365. COP; cuentas USD convertidas hasta liquidación."""
    fecha_valor = _fecha(fecha_valor)
    spot = _numero(spot)
    if spot <= 0:
        raise ValueError('Spot Forward no positivo.')
    inicio = pd.Timestamp(inicio_periodo or fecha_valor.replace(day=1))
    corte = pd.Timestamp(fecha_valor)
    total = mercado = cxc = realizados = 0.0
    detalle = []
    for indice,fila in cartera.iterrows():
        n,k = _numero(fila['Nominal']),_numero(fila['T.Forward'])
        signo = 1 if fila['Operación']=='COMPRA' else -1
        venc,cump = pd.Timestamp(fila.Vencimiento),pd.Timestamp(fila.Cumplimiento)
        if fila['Emisión']>corte:
            raise ValueError("Cartera Forward contiene emisión posterior al corte.")
        plazo = (venc-corte).days
        valor_mv = valor_cxc = flujo = 0.0
        if plazo>0:
            rc = _interpolar(plazo,curva_cop,'Tasas COP')
            ru = _interpolar(plazo,curva_usd,'Tasas USD')
            valor_mv = signo*n*(spot*math.exp(-ru*plazo/365)-k*math.exp(-rc*plazo/365))
        else:
            fix = fixing_forward(venc,fecha_valor,spot,tasas_fix)
            payoff = signo*n*(fix-k)
            if corte<cump:
                if fila.Modalidad == 'NDF':
                    valor_cxc = payoff*(spot/fix if fila.Moneda_Cumplimiento == 'USD' else 1)
                else:
                    valor_cxc = signo*n*(spot-k)
            elif cump>=inicio:
                if fila.Modalidad == 'NDF' and fila.Moneda_Cumplimiento == 'COP':
                    flujo = payoff
                else:
                    spot_cumplimiento = fixing_forward(cump,fecha_valor,spot,tasas_fix)
                    flujo = (payoff*spot_cumplimiento/fix if fila.Modalidad == 'NDF'
                             else signo*n*(spot_cumplimiento-k))
        mercado += valor_mv
        cxc += valor_cxc
        realizados += flujo
        total += valor_mv+valor_cxc+flujo
        detalle.append(dict(FILA=str(indice),MTM_COP=valor_mv,CXC_COP=valor_cxc,FLUJO_COP=flujo))
    return total,dict(MTM_COP=mercado,CXC_COP=cxc,REALIZADO_COP=realizados,detalle=detalle)

def calcular_pyg_forward(fecha_corte,book="OPCIONES",*,config=None,fecha_anterior=None,logger=None):
    if book.upper()!='OPCIONES':
        from proyectos.pyg.procesos.fx_motores import calcular_fx
        return calcular_fx(fecha_corte,book.upper(),producto='FORWARD',config=config,fecha_anterior=fecha_anterior,logger=logger)
    cfg = configuracion(config)
    corte = _fecha(fecha_corte)
    previa = _fecha(fecha_anterior) if fecha_anterior is not None else resolver_fecha_anterior(corte,cfg)
    if previa>=corte:
        raise ValueError("El snapshot anterior debe preceder al corte.")
    anterior = cargar_snapshot(resolver_ruta_dataset(previa,cfg),previa)
    actual = cargar_snapshot(resolver_ruta_dataset(corte,cfg),corte)
    cartera0,cartera1 = cargar_forwards(anterior.ruta),cargar_forwards(actual.ruta)
    fix0 = _normalizar_fix(pd.read_excel(anterior.ruta,sheet_name='tff'))
    fix1 = _normalizar_fix(pd.read_excel(actual.ruta,sheet_name='tff'))
    s0,s1 = _numero(anterior.resumen.TRM),_numero(actual.resumen.TRM)
    inicio = corte.replace(day=1)
    def valorar(cartera,cuando,s,cop,usd,fix):
        return revalorar_forward(cartera,fecha_valor=cuando,spot=s,curva_cop=cop,curva_usd=usd,tasas_fix=fix,inicio_periodo=inicio)
    base,d0 = valorar(cartera0,previa,s0,anterior.curva_cop,anterior.curva_usd,fix0)
    theta,_ = valorar(cartera0,corte,s0,anterior.curva_cop,anterior.curva_usd,fix1)
    delta,_ = valorar(cartera0,corte,s1,anterior.curva_cop,anterior.curva_usd,fix1)
    rho,_ = valorar(cartera0,corte,s1,actual.curva_cop,actual.curva_usd,fix1)
    final,d1 = valorar(cartera1,corte,s1,actual.curva_cop,actual.curva_usd,fix1)
    # Forcva es un nivel IFRS. Compara con el nivel Banking de mercado, no con flujos.
    ifrs0,ifrs1 = _numero(anterior.resumen['Forcva']),_numero(actual.resumen['Forcva'])
    cva = (ifrs1-d1['MTM_COP'])-(ifrs0-d0['MTM_COP'])
    controles = control_pyg(actual,dict(THETA='Theta_Forward',DELTA_PYG='Delta_Forward',RHO='Rho_Forward',NUEVOS_OTROS='Nuevos_Forward',PYG_BANKING='PYG_Forward'))
    resultado = resultado_producto('FORWARD',anterior,actual,dict(THETA=theta-base,DELTA_PYG=delta-theta,RHO=rho-delta,NUEVOS_OTROS=final-rho),
        dict(BASE=base,THETA=theta,DELTA=delta,RHO=rho,ACTUAL=final),cva_dva=cva,config=cfg,controles=controles,
        calidad=[dict(control='Método',estado='OK',detalle='Carteras y mercado; referencia FF_V3, CXC persistente hasta cumplimiento.')])
    if logger:
        logger(f"Forward calculado: {resultado.componentes['PYG_BANKING']:,.2f} COP.")
    return resultado
