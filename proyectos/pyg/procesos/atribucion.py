"""Construcción común de resultados y conciliación contra controles separados."""
from __future__ import annotations
from proyectos.pyg.procesos.opciones import ResultadoPygOpciones, _numero


def resultado_producto(producto, anterior, actual, componentes, escenarios, *,
                       cva_dva, config, controles=None, calidad=None):
    componentes = {k:_numero(v) for k,v in componentes.items()}
    banking = sum(componentes.values())
    componentes.update(PYG_BANKING=banking,CVA_DVA=_numero(cva_dva),PYG_IFRS=banking+_numero(cva_dva))
    controles = controles or {}
    diferencias = {k:componentes[k]-_numero(v) for k,v in controles.items() if k in componentes}
    tolerancia = float(config.get("calculo",{}).get("tolerancia_conciliacion_cop",2))
    estado = "SIN_REFERENCIA" if "PYG_BANKING" not in diferencias else (
        "OK" if all(abs(v)<=tolerancia for v in diferencias.values()) else "DIFERENCIA")
    return ResultadoPygOpciones(
        fecha=actual.fecha.isoformat(),fecha_anterior=anterior.fecha.isoformat(),producto=producto,
        estado="PRELIMINAR",componentes=componentes,escenarios=escenarios,
        mercado=dict(TRM_ANTERIOR=_numero(anterior.resumen["TRM"]),TRM_ACTUAL=_numero(actual.resumen["TRM"]),
                     VARIACION_TRM=_numero(actual.resumen["TRM"])-_numero(anterior.resumen["TRM"])),
        conciliacion=dict(estado=estado,diferencias_componentes=diferencias,tolerancia_cop=tolerancia),
        fuentes=dict(anterior=str(anterior.ruta),actual=str(actual.ruta)),calidad=calidad or [])


def control_pyg(snapshot, mapa):
    return {componente:snapshot.control_legacy[nombre] for componente,nombre in mapa.items()
            if nombre in snapshot.control_legacy}
