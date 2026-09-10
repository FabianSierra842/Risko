"""Motor Novados con valoración de cámara."""
def calcular_pyg_novados(fecha_corte,book='SWAPS',*,config=None,fecha_anterior=None,logger=None):
    from proyectos.pyg.procesos.fx_motores import calcular_fx
    return calcular_fx(fecha_corte,book.upper(),producto='NOVADOS',config=config,fecha_anterior=fecha_anterior,logger=logger)
