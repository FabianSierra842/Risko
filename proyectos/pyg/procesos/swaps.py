"""Motor Swap desde VP Banking/IFRS y pagos por Trade ID."""
def calcular_pyg_swaps(fecha_corte,book='SWAPS',*,config=None,fecha_anterior=None,logger=None):
    from proyectos.pyg.procesos.fx_motores import calcular_swap_fx
    return calcular_swap_fx(fecha_corte,book.upper(),config=config,fecha_anterior=fecha_anterior,logger=logger)
