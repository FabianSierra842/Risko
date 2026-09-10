import holidays
from datetime import datetime, timedelta   


FESTIVOS_CO = holidays.Colombia()


def Primer_Dia_Habil_Mes(fecha=None):
        # Calcula el primer dia habil del mes de la fecha recibida.
        # Si no se recibe fecha, toma la fecha actual del sistema.
        if fecha is None:
                fecha = datetime.now().date()
        elif isinstance(fecha, datetime):
                fecha = fecha.date()

        # Se usan festivos de Colombia y se descartan sabados y domingos.
        festivos_co = holidays.Colombia(years=fecha.year)
        primer_dia = fecha.replace(day=1)

        while primer_dia.weekday() >= 5 or primer_dia in festivos_co:
                primer_dia += timedelta(days=1)

        return primer_dia


def Es_Primer_Dia_Habil_Mes(fecha=None):
        # Retorna True cuando la fecha indicada coincide con el primer dia habil.
        # Esta validacion se usa para mostrar el recordatorio de historicos.
        if fecha is None:
                fecha = datetime.now().date()
        elif isinstance(fecha, datetime):
                fecha = fecha.date()

        return fecha == Primer_Dia_Habil_Mes(fecha)

def Calcula_Fecha():
        # Fecha correcta (ayer)
        ayer = datetime.now() - timedelta(days=1)
    
        # Retrocede mientras sea fin de semana o festivo
        while ayer.weekday() >= 5 or ayer.date() in FESTIVOS_CO:
            ayer -= timedelta(days=1)

        F_Ayer = ayer.strftime("%d-%m-%Y")

        return F_Ayer


def Es_Dia_Habil(fecha):
        if fecha is None:
                fecha = datetime.now().date()
        elif isinstance(fecha, datetime):
                fecha = fecha.date()

        return fecha.weekday() < 5 and fecha not in FESTIVOS_CO


def Ultimo_Dia_Habil(fecha):
        if fecha is None:
                fecha = datetime.now().date()
        elif isinstance(fecha, datetime):
                fecha = fecha.date()

        fecha = fecha - timedelta(days=1)
        while not Es_Dia_Habil(fecha):
                fecha -= timedelta(days=1)

        return fecha


def Dias_No_Habiles_Desde_Ultimo_Habil(fecha):
        if fecha is None:
                fecha = datetime.now().date()
        elif isinstance(fecha, datetime):
                fecha = fecha.date()

        if Es_Dia_Habil(fecha):
                return 0

        return (fecha - Ultimo_Dia_Habil(fecha)).days
