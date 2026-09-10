"""Ejemplos didácticos SWAPS; contrasta fórmulas con motores sin datos reales."""
from copy import deepcopy
from datetime import date
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'proyectos/pyg').is_dir())
sys.path.insert(0, str(ROOT))
from proyectos.pyg.procesos.fx_motores import valorar_fx, costo_fondos, calcular_swap_fx
from proyectos.pyg.procesos.caja import atribuir_caja
from proyectos.pyg.procesos.configuracion import cargar_configuracion


def mercado(s, rc, ru, base=0.0, spread=0.0):
    ri = math.expm1(math.log1p(rc) - math.log1p(ru) + base)
    return dict(trm=s, spot_compra=s, spot_venta=s, spread=spread, fixings={},
                cop=[[1, rc], [365, rc]], usd=[[1, ru], [365, ru]],
                implicita=[[1, ri], [365, ri]])


def ejemplos():
    op = dict(trade_id='DIDACTICO', tipo='COMPRA', emision='2026-08-01',
              vencimiento='2026-11-30', cumplimiento='2026-11-30',
              nominal=100000, strike=4050, modalidad='SIN ENTREGA', moneda='COP')
    m0, m1 = mercado(4000, .10, .04), mercado(4020, .11, .045, .001, .002)
    resultado = {}
    for camara in (False, True):
        def valor(dia, m):
            # Fórmula independiente de la función valorar_fx para curvas planas.
            tau = (date(2026, 11, 30) - date.fromisoformat(dia)).days / 365
            rc, ru = m['cop'][0][1], m['usd'][0][1]
            if camara:
                calculado = 100000 * (m['trm'] * ((1 + rc) / (1 + ru)) ** tau - 4050)
            else:
                mb = m.get('base_curvas', m)
                b = math.log1p(mb['implicita'][0][1]) + math.log1p(mb['usd'][0][1]) - math.log1p(mb['cop'][0][1])
                ri = math.expm1(math.log1p(rc) - math.log1p(ru) + b) - m['spread'] / 2
                calculado = 100000 * (m['spot_compra'] - 4050 / (1 + ri) ** tau) / (1 + ru) ** tau
            nativo = valorar_fx([op], dia, m, camara=camara)[0]
            assert math.isclose(calculado, nativo, abs_tol=.00001)
            return nativo
        vals = {'BASE': valor('2026-09-01', m0)}
        e = deepcopy(m0)
        e['base_curvas'] = deepcopy(m0)
        vals['THETA'] = valor('2026-09-02', e)
        for k in ('trm', 'spot_compra', 'spot_venta'):
            e[k] = m1[k]
        vals['DELTA_PYG'] = valor('2026-09-02', e)
        e['cop'] = m1['cop']
        vals['RHO_COP'] = valor('2026-09-02', e)
        e['usd'] = m1['usd']
        vals['RHO_USD'] = valor('2026-09-02', e)
        e['base_curvas'], e['spread'] = m1, m1['spread']
        vals['BASE_SPREAD'] = valor('2026-09-02', e)
        vals['NUEVOS_OTROS'] = valor('2026-09-02', m1)
        parejas = list(vals.items())
        contrib = {k: v - parejas[i-1][1] for i, (k, v) in enumerate(parejas) if i}
        total = vals['NUEVOS_OTROS'] - vals['BASE']
        assert math.isclose(math.fsum(contrib.values()), total, abs_tol=.00001)
        resultado['NOVADOS' if camara else 'FORWARD'] = dict(escenarios=vals, contribuciones=contrib, PYG_BANKING=total)

    caja = dict(saldo_usd=115000, ftp_cop=.12, ajuste_cop=.01, ftp_usd=.04, ajuste_usd=.005)
    factores = atribuir_caja(saldo_usd_anterior=100000, trm_anterior=4000, trm_actual=4020,
                            compras_usd=25000, compras_tasa=4005, ventas_usd=10000, ventas_tasa=4010)
    fondos = costo_fondos(caja, 4020)
    assert math.isclose(fondos['COP'], -115000*4020*((1.12*1.01)**(1/365)-1), abs_tol=.00001)
    assert fondos['USD'] == 115000*4020*(.04+.005)/360
    assert math.fsum(factores.values()) == 115000*4020 - 100000*4000 - 25000*4005 + 10000*4010
    resultado['CAJA'] = dict(contribuciones=factores, fondeo=fondos, PYG_BANKING=math.fsum(factores.values())+fondos['TOTAL'])

    fijo = 100000000 * .08 * .25
    vp0 = math.fsum((fijo - 100000000 * r * .25) * d for r, d in [(.07, .980), (.075, .960)])
    vp1 = math.fsum((fijo - 100000000 * r * .25) * d for r, d in [(.072, .981), (.078, .961)])
    assert math.isclose(vp0, 365000, abs_tol=.00001)
    assert math.isclose(vp1, 244250, abs_tol=.00001)
    resultado['MODELO_FUTURO_IRS_NO_IMPLEMENTADO'] = dict(VP_ANTERIOR=vp0, VP_ACTUAL=vp1, PYG=vp1-vp0)
    vp_solo_proyeccion = 200000*.980 + 50000*.960
    vp_solo_descuento = 250000*.981 + 125000*.961
    assert vp_solo_proyeccion == 244000
    assert vp_solo_descuento == 365375
    resultado['MODELO_FUTURO_IRS_NO_IMPLEMENTADO'].update(
        VP_SOLO_PROYECCION=vp_solo_proyeccion,
        RHO_PROYECCION_PRIMERO=vp_solo_proyeccion-vp0,
        RHO_DESCUENTO_DESPUES=vp1-vp_solo_proyeccion,
        VP_SOLO_DESCUENTO=vp_solo_descuento,
        RHO_DESCUENTO_PRIMERO=vp_solo_descuento-vp0,
        RHO_PROYECCION_DESPUES=vp1-vp_solo_descuento)

    f = dict(THETA=300000, DELTA_PYG=800000, DELTA_OTRAS=20000, RHO_COP=400000,
             RHO_USD=100000, RHO_DTF=150000, RHO_IPC=0, RHO_OTRAS=30000, TRADING=100000)
    with TemporaryDirectory(prefix='ejemplo_swaps_') as carpeta:
        cfg = cargar_configuracion()
        cfg['fuentes']['swaps']['carpeta_datasets'] = carpeta
        for dia, bk, ifrs, pago, recup in [('2026-09-01', 100000000, 99500000, 0, 50000),
                                           ('2026-09-02', 99000000, 98300000, 3000000, 70000)]:
            datos = dict(schema_version=1, book='SWAPS', fecha=dia, mercado=m0,
                         swaps=[dict(trade_id='S1', banking=bk, ifrs=ifrs, pago_cop=pago)],
                         factores_swap=f, recuponing_nivel_cop=recup, calidad=[],
                         controles={'SWAPS': dict(PYG_BANKING=2000000, PYG_IFRS=1820000)})
            (Path(carpeta) / f"Dataset SWAPS {dia.replace('-', '')}.json").write_text(json.dumps(datos), encoding='utf-8')
        r = calcular_swap_fx('2026-09-02', config=cfg, fecha_anterior='2026-09-01')
        assert r.componentes['PYG_BANKING'] == 2000000
        assert r.componentes['CVA_DVA'] == -180000
        assert r.componentes['PYG_IFRS'] == 1820000
        assert r.componentes['EPSILON'] == 100000
        assert r.conciliacion['estado'] == 'OK'
        resultado['SWAPS'] = dict(componentes=r.componentes, evidencia=r.escenarios)
    return resultado


if __name__ == '__main__':
    print(json.dumps(ejemplos(), ensure_ascii=False, indent=2))
