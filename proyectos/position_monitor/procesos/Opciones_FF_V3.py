# -*- coding: utf-8 -*-
"""
Created on Wed Nov  5 15:03:45 2025

@author: svaneg4
"""
import openpyxl
import datetime
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
#import numpy_financial as npf
from datetime import date
import xlwings as xw
import datetime
from datetime import datetime, timedelta
from pandas.tseries.offsets import BDay
from scipy.stats import norm
import calendar
import time


inicio = time.perf_counter()
fv = input('Inserte fecha de valoración "yyyymmdd": ')
fval = datetime(year=int(fv[0:4]), month=int(fv[4:6]), day=int(fv[6:8]))
trm_full = pd.read_excel(
    r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\Datos Mercado\Curva Forward V2.xlsm",
    engine='openpyxl',  # Mejor para .xlsm
    sheet_name="Matriz TC"
)
trm=float(trm_full.iloc[0, 2])
#trm=3767.94
del trm_full
Dia = input('Inserte DIA: ')
Mes = input('Inserte MES: ')
Año = input('Inserte AÑO: ')
#hoy=date.today()
Año1 = str(int(Año) - 2000)


# import subprocess
# import sys

# archivo = r"C:\Librerias\pyxlsb-1.0.10.tar.gz"
# try:
#     subprocess.check_call([sys.executable, "-m", "pip", "install", archivo])
#     print("Instalación completada correctamente.")
# except subprocess.CalledProcessError as e:
#     print("Error durante la instalación:", e)


'////////////////////////////////////////// FUNCIONES ////////////////////////////////////'

'* Funciones generales ////////////////////////////////////////////////////////////////'

def VLookup(lookup_value, col2search, table_array, col2return, approx_match=False):
    if approx_match:
        look_idx_row = table_array[col2search].searchsorted(lookup_value)
        idx_col = table_array.columns.get_loc(col2return)
        if lookup_value in table_array[col2search].values:
            return table_array.iloc[look_idx_row, idx_col]
        idx_row = look_idx_row - 1 if look_idx_row > 0 else 0
        return table_array.iloc[idx_row, idx_col]

    copy_tb_array = table_array.copy()
    if type(lookup_value) is not list:
        df_target = pd.DataFrame({"Target Value": [lookup_value]})
    else:
        df_target = pd.DataFrame({"Target Value": lookup_value})
    
    df_target[col2return] = ""
    
    df_target.set_index("Target Value", inplace=True)
    if col2search == col2return:
        copy_tb_array['Copy'] = copy_tb_array[col2search]
        copy_tb_array.set_index(col2search, inplace=True)
        df_target[col2return] = df_target.index.map(copy_tb_array['Copy'])
    else:
        copy_tb_array.set_index(col2search, inplace=True)
        df_target[col2return] = df_target.index.map(copy_tb_array[col2return])
    
    if type(lookup_value) is not list:
        return df_target.iloc[0,0]
    return df_target

def Interpolacion_Tasa(plazo, Rango_Tasas, Moneda):
    if plazo <= 0:
        return 0
    else:
        Lim_Inf = VLookup(plazo, 'Plazo Inferior', Rango_Tasas, 'Plazo Inferior', True)
        Lim_Sup = VLookup(plazo, 'Plazo Inferior', Rango_Tasas, 'Plazo Superior', True)
        if Lim_Inf == Lim_Sup:
            PorLimInf = 1
        else:
            PorLimInf = 1 - (plazo - Lim_Inf) / (Lim_Sup - Lim_Inf)
        
        if Moneda == "COP":
            Tasa_Inf = VLookup(Lim_Inf, 'Plazo Inferior', Rango_Tasas, 'Tasas COP', True)
            Tasa_sup = VLookup(Lim_Sup, 'Plazo Inferior', Rango_Tasas, 'Tasas COP', True)  
        else:
            Tasa_Inf = VLookup(Lim_Inf, 'Plazo Inferior', Rango_Tasas, 'Tasas USD', True)
            Tasa_sup = VLookup(Lim_Sup, 'Plazo Inferior', Rango_Tasas, 'Tasas USD', True)
        return PorLimInf * Tasa_Inf + (1 - PorLimInf) * Tasa_sup

def convert_to_float(value):
    return float(value.replace(',', ''))

def sumar_si_conjunto(df, suma_col, condiciones):

    for col, vals in condiciones.items():
        df = df[df[col].isin(vals)]
        
    return df[suma_col].sum()

def suma_si(dataframe, columna_condicion, valor_condicion, columna_suma):
    return dataframe[dataframe[columna_condicion] == valor_condicion][columna_suma].sum()



'1. funciones para valoración de opciones /////////////////////////////////////////////'

def Zigma_Option(Spot, Strike, Rango_Tasas, Rd, Rf, T):
    Lim_Inf = VLookup(T,'Plazo Inferior', Rango_Tasas, 'Plazo Inferior', True)
    Lim_Sup = VLookup(T,'Plazo Inferior', Rango_Tasas, 'Plazo Superior', True)

    if T <= 0:
        return 0
    
    PorLimInf = 1 if Lim_Inf == Lim_Sup else 1 - (T - Lim_Inf) / (Lim_Sup - Lim_Inf)

    # 10 D PUT
    Tasa_Inf = VLookup(Lim_Inf, 'Plazo Inferior', Rango_Tasas, '10 D PUT', True)
    Tasa_sup = VLookup(Lim_Sup, 'Plazo Inferior', Rango_Tasas, '10 D PUT', True)  
    Z10P = PorLimInf * Tasa_Inf + (1 - PorLimInf) * Tasa_sup

    # 25 D PUT
    Tasa_Inf = VLookup(Lim_Inf, 'Plazo Inferior', Rango_Tasas, '25 D PUT', True)
    Tasa_sup = VLookup(Lim_Sup, 'Plazo Inferior', Rango_Tasas, '25 D PUT', True)
    z25P = PorLimInf * Tasa_Inf + (1 - PorLimInf) * Tasa_sup

    # ATM
    Tasa_Inf = VLookup(Lim_Inf, 'Plazo Inferior', Rango_Tasas, 'ATM', True)  
    Tasa_sup = VLookup(Lim_Sup, 'Plazo Inferior', Rango_Tasas, 'ATM', True)
    ZATM = PorLimInf * Tasa_Inf + (1 - PorLimInf) * Tasa_sup

    # 25 D CALL
    Tasa_Inf = VLookup(Lim_Inf, 'Plazo Inferior', Rango_Tasas, '25 D CALL', True)
    Tasa_sup = VLookup(Lim_Sup, 'Plazo Inferior', Rango_Tasas, '25 D CALL', True)
    Z25C = PorLimInf * Tasa_Inf + (1 - PorLimInf) * Tasa_sup

    # 10 D CALL
    Tasa_Inf = VLookup(Lim_Inf,'Plazo Inferior', Rango_Tasas, '10 D CALL', True)
    Tasa_sup = VLookup(Lim_Sup, 'Plazo Inferior', Rango_Tasas, '10 D CALL', True)
    Z10C = PorLimInf * Tasa_Inf + (1 - PorLimInf) * Tasa_sup

    S_10P1 = Spot * np.exp(-norm.ppf(np.exp(Rf * T / 365) * 9 / 10) * Z10P * np.sqrt(T / 365) + (Rd - Rf + (Z10P ** 2) / 2) * (T / 365))
    S_25P1 = Spot * np.exp(-norm.ppf(np.exp(Rf * T / 365) * 3 / 4) * z25P * np.sqrt(T / 365) + (Rd - Rf + (z25P ** 2) / 2) * (T / 365))
    S_ATM1 = Spot * np.exp(((Rd - Rf) + (ZATM ** 2) / 2) * T / 365)
    S_25C1 = Spot * np.exp(-norm.ppf(np.exp(Rf * T / 365) * 1 / 4) * Z25C * np.sqrt(T / 365) + (Rd - Rf + (Z25C ** 2) / 2) * (T / 365))
    S_10C1 = Spot * np.exp(-(norm.ppf(np.exp(Rf * T / 365) * 1 / 10)) * Z10C * np.sqrt(T / 365) + (Rd - Rf + (Z10C ** 2) / 2) * (T / 365))

    X10P = (np.log(S_25P1 / Strike) * np.log(S_ATM1 / Strike) * np.log(S_25C1 / Strike) * np.log(S_10C1 / Strike)) / (np.log(S_25P1 / S_10P1) * np.log(S_ATM1 / S_10P1) * np.log(S_25C1 / S_10P1) * np.log(S_10C1 / S_10P1))
    X25P = (np.log(Strike / S_10P1) * np.log(S_ATM1 / Strike) * np.log(S_25C1 / Strike) * np.log(S_10C1 / Strike)) / (np.log(S_25P1 / S_10P1) * np.log(S_ATM1 / S_25P1) * np.log(S_25C1 / S_25P1) * np.log(S_10C1 / S_25P1))
    XATM = (np.log(Strike / S_10P1) * np.log(Strike / S_25P1) * np.log(S_25C1 / Strike) * np.log(S_10C1 / Strike)) / (np.log(S_ATM1 / S_10P1) * np.log(S_ATM1 / S_25P1) * np.log(S_25C1 / S_ATM1) * np.log(S_10C1 / S_ATM1))
    X25C = (np.log(Strike / S_10P1) * np.log(Strike / S_25P1) * np.log(Strike / S_ATM1) * np.log(S_10C1 / Strike)) / (np.log(S_25C1 / S_10P1) * np.log(S_25C1 / S_25P1) * np.log(S_25C1 / S_ATM1) * np.log(S_10C1 / S_25C1))
    X10C = (np.log(Strike / S_10P1) * np.log(Strike / S_25P1) * np.log(Strike / S_ATM1) * np.log(Strike / S_25C1)) / (np.log(S_10C1 / S_10P1) * np.log(S_10C1 / S_25P1) * np.log(S_10C1 / S_ATM1) * np.log(S_10C1 / S_25C1))

    if Strike >= S_10C1:
        return Z10C
    elif Strike <= S_10P1:
        return Z10P
    return X10P * Z10P + X25P * z25P + XATM * ZATM + X25C * Z25C + X10C * Z10C

def cubic_spline1(input_column, output_column, X):
    input_count = len(input_column)
    output_count = len(output_column)

    if input_count != output_count:
        return "Something's messed up! The number of indices in input_column and output_column don't match!"

    xin = np.array(input_column)
    yin = np.array(output_column)

    n = input_count
    yt = np.zeros(n + 1)
    u = np.zeros(n)
    yt[0] = 0
    u[0] = 0

    for i in range(1, n - 1):
        sig = (xin[i] - xin[i - 1]) / (xin[i + 1] - xin[i - 1])[0]
        p = sig[0] * yt[i - 1] + 2
        
        yt[i] = (sig[0] - 1) / p
        u[i] = (yin[i + 1] - yin[i]) / (xin[i + 1][0] - xin[i][0]) - (yin[i] - yin[i - 1]) / (xin[i][0] - xin[i - 1][0])
        u[i] = (6 * u[i] / (xin[i + 1][0] - xin[i - 1][0]) - sig[0] * u[i - 1]) / p

    qn = 0
    un = 0
    yt[n] = (un - qn * u[n - 1]) / (qn * yt[n - 1] + 1)

    for k in range(n - 1, 0, -1):
        yt[k] = yt[k] * yt[k + 1] + u[k]

    klo = 0
    khi = n - 1

    while khi - klo > 1:
        k = (khi + klo) // 2
        if xin[k] > X:
            khi = k
        else:
            klo = k

    h = xin[khi] - xin[klo]
    a = (xin[khi] - X) / h
    b = (X - xin[klo]) / h
    Y = a * yin[klo] + b * yin[khi] + ((a ** 3 - a) * yt[klo] + (b ** 3 - b) * yt[khi]) * (h ** 2) / 6

    return Y

def Volatilidad_cubic(Spot, Strike, plazo, tasa_cop, tasa_usd, deltaatm, Deltas, volatilidades, error, itmax, tipo, ajuste):
    sigma_final = 0
    sigma_siguiente = deltaatm
    it = 0

    vol_put = [volatilidades.iloc[0], volatilidades.iloc[3], volatilidades.iloc[6], volatilidades.iloc[9], volatilidades.iloc[12]]
    vol_call = [volatilidades.iloc[12], volatilidades.iloc[9], volatilidades.iloc[6], volatilidades.iloc[3], volatilidades.iloc[0]]
    
    if tipo == "CALL":
        signo = 1
    elif tipo == "PUT":
        signo = -1

    while abs(sigma_final - sigma_siguiente) > float(error) and it < int(itmax):
        # dmas = (np.log(Spot / Strike) + ((tasa_cop - tasa_usd + (sigma_siguiente**2) / 2) * plazo / 365)) / (sigma_siguiente * np.sqrt(plazo / 365))
        dmas = (np.log(Spot / Strike) + ((tasa_cop - tasa_usd + (sigma_siguiente**2) * 0.5) * plazo / 365)) / (sigma_siguiente * np.sqrt(plazo / 365))
        fix = lambda x: -1 if x == -1-0.5 else 0 #En VBA se usa la funcion fix la cual retorna 0 si signo=1 y -1 si signo =-1
        delta_siguiente = (norm.cdf(dmas) + fix(signo - 0.5)) / ajuste
        # delta_siguiente = (norm.cdf(dmas) + (signo - 0.5)//1) / ajuste
        sigma_final = sigma_siguiente
        if tipo == "PUT":
            sigma_siguiente = cubic_spline1(Deltas, vol_put, abs(delta_siguiente))
        elif tipo == "CALL":
            sigma_siguiente = cubic_spline1(Deltas, vol_call, delta_siguiente)
        
        it += 1
    if tipo == "PUT" and abs(delta_siguiente) <= 0.1:
        return vol_put[0]
    elif tipo == "PUT" and abs(delta_siguiente) >= 0.9:
        return vol_put[4]
    elif tipo == "CALL" and delta_siguiente <= 0.1:
        return vol_call[0]
    elif tipo == "CALL" and delta_siguiente >= 0.9:
        return vol_call[4]
    else:
        return sigma_siguiente[0]


def Volatilidad_cubic2(Spot, Strike, plazo, tasa_cop, tasa_usd, deltaatm, Deltas, volatilidades, error, itmax, tipo, ajuste):
    """
    Calcula la volatilidad implícita ajustada mediante interpolación cúbica.
    
    - Spot: precio del subyacente
    - Strike: precio de ejercicio
    - plazo: días a vencimiento
    - tasa_cop, tasa_usd: tasas locales y USD
    - deltaatm: delta ATM inicial
    - Deltas: DataFrame con los deltas (0.1, 0.25, 0.5, 0.75, 0.9)
    - volatilidades: DataFrame o Series con las volatilidades de esa fila
    - error: tolerancia de convergencia
    - itmax: iteraciones máximas
    - tipo: "CALL" o "PUT"
    - ajuste: factor de ajuste (generalmente 1)
    """
    import numpy as np
    from scipy.stats import norm
    
    # Inicialización
    sigma_final = 0
    sigma_siguiente = deltaatm
    it = 0

    # Extraemos las volatilidades de la fila
    # Suponemos que las columnas de volatilidades están en orden: 10PUT, 25PUT, ATM, 25CALL, 10CALL
    if isinstance(volatilidades, pd.DataFrame):
        vals = volatilidades.iloc[0].values
    else:  # Series
        vals = volatilidades.values

    if len(vals) != 5:
        raise ValueError("Volatilidades debe contener exactamente 5 columnas: 10PUT, 25PUT, ATM, 25CALL, 10CALL")

    vol_put = vals
    vol_call = vals[::-1]  # invertimos para CALL

    # Determinamos signo
    if tipo.upper() == "CALL":
        signo = 1
    elif tipo.upper() == "PUT":
        signo = -1
    else:
        raise ValueError("Tipo de opción debe ser 'CALL' o 'PUT'")

    # Iteración de convergencia
    while abs(sigma_final - sigma_siguiente) > float(error) and it < int(itmax):
        dmas = (np.log(Spot / Strike) + ((tasa_cop - tasa_usd + 0.5 * sigma_siguiente**2) * plazo / 365)) / (sigma_siguiente * np.sqrt(plazo / 365))

        # Fix: emula la función VBA
        fix = lambda x: -1 if x == -0.5 else 0
        delta_siguiente = (norm.cdf(dmas) + fix(signo - 0.5)) / ajuste

        sigma_final = sigma_siguiente

        # Interpolación cúbica
        if tipo.upper() == "PUT":
            sigma_siguiente = cubic_spline1(Deltas, vol_put, abs(delta_siguiente))
        elif tipo.upper() == "CALL":
            sigma_siguiente = cubic_spline1(Deltas, vol_call, delta_siguiente)

        it += 1

    # Manejo de extremos
    if tipo.upper() == "PUT":
        if abs(delta_siguiente) <= 0.1:
            return vol_put[0]
        elif abs(delta_siguiente) >= 0.9:
            return vol_put[4]
    elif tipo.upper() == "CALL":
        if delta_siguiente <= 0.1:
            return vol_call[0]
        elif delta_siguiente >= 0.9:
            return vol_call[4]

    return sigma_siguiente








def Valor_Opcion(Spot, Strike, plazo, Rf, Rd, Zigma, tipo):
    if plazo <= 0:
        return 0
    else:
        Delt1 = (np.log(Spot / Strike) + (Rd - Rf + ((Zigma ** 2) * 0.5)) * (plazo / 365)) / (Zigma * ((plazo / 365) ** 0.5))
        Delt2 = Delt1 - Zigma * ((plazo / 365) ** 0.5)
        
        if tipo == "CALL":
            return Spot * np.exp(-Rf * (plazo / 365)) * norm.cdf(Delt1) - Strike * np.exp(-Rd * (plazo / 365)) * norm.cdf(Delt2)
        else:
            return Strike * np.exp(-Rd * (plazo / 365)) * norm.cdf(-Delt2) - Spot * np.exp(-Rf * (plazo / 365)) * norm.cdf(-Delt1) 
        
def calculate_valor_libro(plazo, operacion, moneda_cump, bs_ajustado, nominal, spot):
    if plazo <= 0:
        return 0
    signo = 1 if operacion == "BUY" else -1
    if moneda_cump == "USD":
        return signo*(bs_ajustado*nominal)/spot
    return signo*(bs_ajustado*nominal)


def tfix(plazo,vencimiento,matriz,ff,Spot=trm):
    if plazo<0:
        if vencimiento>matriz['FECHA'][0]:
            return   VLookup(vencimiento,'FECHA', matriz, 'TRM1',approx_match=True)
        else:   
            return   VLookup(int(ff),'FECHA', matriz, 'TRM1',approx_match=True)
    elif plazo==0:
        return Spot
    else:
        return 0
        

    
def Cuentas_Por_opc(Moneda_Liq, Fix_Date, Value_Date, Fecha, tipo, Strike, Monto, Operacion, R_Desc, Tasa_Liquidacion, Modalidad):
    # Check for Modalidad
    if Modalidad == "NON DELIVERY":
        if Fecha > Fix_Date:
            return 0
        elif Fecha < Fix_Date:
            return 0
        else:
            OP2 = 1 if Operacion == "BUY" else -1
            if tipo == "CALL":
                if Tasa_Liquidacion > Strike:
                    if Moneda_Liq == "USD":
                        return (Tasa_Liquidacion - Strike) * Monto / Tasa_Liquidacion * np.exp(-(Value_Date - Fecha).days / 365 * R_Desc) * OP2
                    else:
                        return (Tasa_Liquidacion - Strike) * Monto * np.exp(-(Value_Date - Fecha).days / 365 * R_Desc) * OP2
                else:
                    return 0
            else:
                if Tasa_Liquidacion < Strike:
                    if Moneda_Liq == "USD":
                        return (Strike - Tasa_Liquidacion) * Monto / Tasa_Liquidacion * np.exp(-(Value_Date - Fecha).days / 365 * R_Desc) * OP2
                    else:
                        return (Strike - Tasa_Liquidacion) * Monto * np.exp(-(Value_Date - Fecha).days / 365 * R_Desc) * OP2
                else:
                    return 0
    else:
        return 0    
    
def Vencimiento(Moneda, Moneda_Liq, Modalidad, Fix_Date, Fecha, tipo, Strike, Monto, Operacion, Tasa_Liquidacion, Value_Date):
    if Fecha > Fix_Date or Fecha >= Value_Date:
        OP = 1 if Operacion == "BUY" else -1
        if Modalidad == "NON DELIVERY":
            if tipo == "CALL":
                if Tasa_Liquidacion > Strike:
                    if Moneda == Moneda_Liq:
                        if Moneda == "USD":
                            return (Tasa_Liquidacion - Strike) * Monto / Tasa_Liquidacion * OP
                        else:
                            return (Tasa_Liquidacion - Strike) * Monto * OP
                    else:
                        return 0
                else:
                    return 0
            else:
                if Tasa_Liquidacion < Strike:
                    if Moneda == Moneda_Liq:
                        if Moneda == "USD":
                            return (Strike - Tasa_Liquidacion) * Monto / Tasa_Liquidacion * OP
                        else:
                            return (Strike - Tasa_Liquidacion) * Monto * OP
                    else:
                        return 0
                else:
                    return 0
        else:
            if tipo == "CALL":
                if Tasa_Liquidacion > Strike:
                    if Moneda == "USD":
                        return Monto * OP
                    else:
                        return -Monto * Strike * OP
                else:
                    return 0
            else:
                if Tasa_Liquidacion < Strike:
                    if Moneda == "USD":
                        return -Monto * OP
                    else:
                        return Monto * Strike * OP
                else:
                    return 0
    else:
        return 0    
    
 
def delta_opcion(Fecha, Fecha_Vencimiento, Spot, Strike, Rd, Rf, sigma, Tipo_Opcion):
    if Tipo_Opcion == "CALL":
        Tip = 1
    else:
        Tip = -1
    
    T = (Fecha_Vencimiento - Fecha).days / 365.0
    
    if T < 0:
        return 0
    elif T == 0:
        if Spot >= Strike:
            return Tip
        else:
            return 0
    elif T > 0:
        # delta1p = (np.log(Spot / Strike) + ((Rd - Rf + (sigma ** 2) / 2) * T)) / (sigma * np.sqrt(T))
        delta1p = (np.log(Spot / Strike) + ((Rd - Rf + (sigma ** 2) * 0.5) * T)) / (sigma * np.sqrt(T))
        fix = lambda x: -1 if x == -1-0.5 else 0 #En VBA se usa la funcion fix la cual retorna 0 si signo=1 y -1 si signo =-1
        return np.exp(-Rf * T) * (norm.cdf(delta1p) + fix(Tip - 0.5))    

    
def difvalconCVA(ID,PLAZO,FAIRVALUECVA,VALORSUMMIT):       

    if ID == "":
     return ""
    elif PLAZO <= 0:
     return 0
    else:
     return FAIRVALUECVA - VALORSUMMIT


def difvalsinCVA(ID,MONEDA,VLRLIBRO,TC,VALORSUMMIT):
    if ID=="":
        return ""
    else:
        if MONEDA=="USD":
            return (VLRLIBRO*TC)-VALORSUMMIT
        else:
            return VLRLIBRO-VALORSUMMIT

def calcular_BS_CVA(ID, SPREADCVA, BSAJUSTADO, PLAZO):
    if ID == "":
        return ""
    elif SPREADCVA == "":
        return BSAJUSTADO
    else:
        return BSAJUSTADO * np.exp((-SPREADCVA / 100) * PLAZO / 365)


def ValorLibroCVA(PLAZO,OPERACION, MONEDA, BSCVA, NOMINAL, TC):
    if PLAZO <= 0:
        return 0
    else:
        signo = 1 if OPERACION == "BUY" else -1
        if MONEDA == "USD":
            return signo * (BSCVA * NOMINAL) / TC
        else:
            return signo * (BSCVA * NOMINAL)
        
        
def DifrevCVA (ID,PLAZO, VLRLIBROCVA, FAIRVALUECVA):        
    if ID == "":
        return ""
    elif PLAZO <= 0:
        return 0
    else:
        return VLRLIBROCVA - FAIRVALUECVA        
    
def DifporCVA(ID, PLAZO, MONEDA, VLRLIBROCVA, VLRLIBRO, TC):
    if ID == "":
        return ""
    elif PLAZO <= 0:
        return 0
    else:
        if MONEDA == "USD":
            return VLRLIBROCVA * TC - VLRLIBRO * TC
        else:
            return VLRLIBROCVA - VLRLIBRO    
            

'2. funciones para valoración de forwards /////////////////////////////////////////////'

def VP_FLUJO_COP(Tforward,Nominal,Plazo,Tasacop,Operación):
    if Plazo<=0:
        return 0
    else:
        if Operación=="COMPRA":
            return ((Tforward*Nominal)*np.exp(-Plazo/365*Tasacop))*-1
        else:
            return ((Tforward*Nominal)*np.exp(-Plazo/365*Tasacop))


def VP_FLUJO_USD(Tforward,Nominal,Plazo,Tasausd,Operación):
    if Plazo<=0:
        return 0
    else:
        if Operación=="COMPRA":
            return ((Nominal)*np.exp(-Plazo/365*Tasausd))
        else:
            return ((Nominal)*np.exp(-Plazo/365*Tasausd))*-1 
        
def Vlr_forward(Plazo,Moneda,VP_flujo_Cop,VP_flujo_Usd,tc):
    if Plazo<=0:
        return 0
    else:
        if Moneda=='USD':
          return  ((VP_flujo_Cop+(VP_flujo_Usd*tc))/tc)
        else:
          return  (VP_flujo_Cop+(VP_flujo_Usd*tc)) 

def tfixfor(plazo,vencimiento,matriz):
    if plazo<0:
        return VLookup(vencimiento+1,'FECHA', matriz, 'TRM1')
    else:
        if plazo==0:
            return trm
        else:
            return 0 
        
def tfixforr(plazo,vencimiento,matriz,tc):
    if plazo<0:
        return VLookup(vencimiento+1,'FECHA', matriz, 'TRM1')
    else:
        if plazo==0:
            return tc
        else:
            return 0        
        
def tfixforr2(plazo, vencimiento, matriz, tc):
    """
    Devuelve la tasa fix interpolada para un forward.
    Corrige la suma de días para usar pd.Timedelta.
    """
    if plazo < 0:
        # Sumar 1 día usando pd.Timedelta
        vencimiento_mas1 = vencimiento + pd.Timedelta(days=1)
        return VLookup(vencimiento_mas1, 'FECHA', matriz, 'TRM1')
    elif plazo == 0:
        return tc
    else:
        return 0        
        
def Cuentas_Por_FWD(Moneda_Liq, Fix_Date, Value_Date, Fecha, Forward, Monto, Operacion, R_Desc, Tasa_Fix, Modalidad):
    if Modalidad=="NDF":
        if Fecha > Fix_Date or Fix_Date==Value_Date:
            return 0
        elif Fecha < Fix_Date:
            return 0
        else:
            FW2 = 1 if Operacion == "COMPRA" else -1
            if Moneda_Liq == "USD":
                return (Tasa_Fix - Forward) * Monto / Tasa_Fix * np.exp(-(Value_Date - Fecha).days/365 * R_Desc) * FW2
            else:
                return (Tasa_Fix - Forward) * Monto * np.exp(-(Value_Date - Fecha).days/365 * R_Desc) * FW2
            
def Vencimiento_FWD(Moneda, Moneda_Liq, Modalidad, Fix_Date, Fecha, Forward, Monto, Operacion, Tasa_Fix, Value_Date):
    OP = 1 if Operacion == "COMPRA" else -1

    if Fecha > Fix_Date or Fecha > Value_Date:
        if Modalidad == "NDF":
            if Moneda == "COP":
                if Moneda_Liq == "COP":
                    return OP * Monto * (Tasa_Fix - Forward)
                else:
                    return 0
            else:
                if Moneda_Liq == "COP":
                    return 0
                else:
                    return OP * Monto * (Tasa_Fix - Forward) / Tasa_Fix
        else:
            if Moneda == "COP":
                return -OP * Monto * Forward
            else:
                return OP * Monto
    else:
        return 0            


'3. funciones para valoración de novados /////////////////////////////////////////////'

def pos_usd(VCTO,NOMINAL,FVAL,DELTA):
        if VCTO<FVAL:
            return ""
        elif VCTO==FVAL:
            return 0
        else:
            return float(NOMINAL*DELTA)
        
def vlr_pac(VCTO,FVAL,NOMINAL,PRECIO):
    if VCTO<FVAL:
        return 0
    else:
        return float(NOMINAL*PRECIO)        

def pla(FECHA,FVAL):
    if (FECHA-FVAL).days<0:
        return 0
    else:
        return (FECHA-FVAL).days
    
def fwd_cal(PLAZO,TRM,TCOP,TUSD):
    if PLAZO<0:
        return 0
    elif PLAZO==0:
        return TRM
    else:
        return TRM*np.exp(PLAZO/365*(TCOP-TUSD))    

def Px(VCTO,FVAL):
    if VCTO<FVAL:
        return 0
    else:
        return VLookup(VCTO,'Fecha',pnov,'Fwd Ajustado',True)    
    
def MTM_ACUM(VCTO,FVAL,PX,PXPACTADO,NOMINAL):
    if VCTO<FVAL:
        return 0
    else:
        return (PX-PXPACTADO)*NOMINAL
    
def PXT1(VCTO,FVAL,TRADEDATE,PT1):
    if VCTO<FVAL or TRADEDATE==FVAL:
        return 0
    else:
        return VLookup (VCTO,'Fecha',PT1,'Outright',True)
    
def MTMD(VCTO,FVAL,PXT,PX,PXPACTADO,NOMINAL):
    if VCTO<FVAL:
        return 0
    else:
        if PXT==0:
            return (PX-PXPACTADO)*NOMINAL
        else:
            return (PX-PXT)*NOMINAL    
    
def P_INI(VCTO,FVAL,PT1):
    if VCTO<FVAL or VCTO==0:
        return 0
    else:
        return  VLookup (VCTO,'Fecha',PT1,'Outright',True)


 
def MDÍA(VCTO,FVAL,DF,col_cri,col_suma):
    if VCTO<FVAL or VCTO==0:
        return 0
    else:
        return  suma_si(DF,col_cri,VCTO,col_suma)


'4. funciones para cálculo caja /////////////////////////////////////////////'

def FPYFeeusd(FECHA,MONEDA):
    flt1={'Fecha de Emisión':[FECHA],
          'Moneda de la  Prima': [MONEDA],
          }
    return sumar_si_conjunto(opc, 'Valor Total Prima', flt1)


def FPYFeecop(FECHA,MONEDA):
    flt1={'Fecha de Emisión':[FECHA],
          'Moneda de la  Prima': [MONEDA],
          'Posición en la opción': ['SELL','BUY']
          }
 
    flt2={
          'Fecha Fee':[FECHA],
          'Moneda Fee':[MONEDA]
          }
    return sumar_si_conjunto(opc, 'Valor Total Prima', flt1)   + sumar_si_conjunto(opc, 'Fee', flt2)

def LIQderusd(FECHA):
    global fwd, opc
    flt1={'Fecha de Vencimiento':[FECHA]
          }
 
    flt2={
          'Vencimiento':[FECHA]
          }
    flt3={
          'Moneda cumplimiento':['USD'],
          'Fecha de Vencimiento':[FECHA]
          }
    
    return sumar_si_conjunto(opc, 'USD', flt1)*0   + sumar_si_conjunto(fwd, 'USD', flt2) + sumar_si_conjunto(opc, 'Cuentas por Cumplir', flt3)*0

def LIQderCop(FECHA):
    global fwd, opc
    flt1={'Fecha de Vencimiento':[FECHA]
          }
    flt2={'Vencimiento':[FECHA]
          }
    return sumar_si_conjunto(opc, 'COP', flt1)*0   + sumar_si_conjunto(fwd, 'COP', flt2)  

def Cumforopt(FECHA):
    global fwd, opc
    flt1={'Fecha de Cumplimiento':[FECHA],
          'Moneda cumplimiento':['USD']
          }
    
    flt2={'Fecha de Cumplimiento':[FECHA],
          'Modalidad Cumplimiento':['DELIVERY'],
          'Moneda cumplimiento':['COP']
          }
    
    flt3={'Cumplimiento':[FECHA],
          'Moneda_Cumplimiento':['USD'],
    
          }
        
    
    return sumar_si_conjunto(opc, 'USD', flt1) + sumar_si_conjunto(opc, 'USD', flt2)  + sumar_si_conjunto(fwd, 'USD', flt3)
   
    
def Cumforoptcop(FECHA):
    global fwd, opc
    flt1={'Fecha de Cumplimiento':[FECHA],
          'Moneda cumplimiento':['COP']
          }
    
    
    flt2={'Cumplimiento':[FECHA],
          'Moneda_Cumplimiento':['COP'],
    
          }
        
    
    return sumar_si_conjunto(opc, 'COP', flt1) +  sumar_si_conjunto(fwd, 'COP', flt2)   


def CXCUSD(FECHA):
    global fwd, opc
    flt1={'Fecha de Vencimiento':[FECHA],
          'Moneda cumplimiento':['USD']
          }

    flt2={'Vencimiento':[FECHA],
          'Moneda_Cumplimiento':['USD'],
    
          }
        
    return sumar_si_conjunto(opc, 'Cuentas por Cumplir', flt1) +  sumar_si_conjunto(fwd, 'CXC', flt2)
   
def CXCCOP(FECHA):
    global fwd, opc
    flt1={'Fecha de Vencimiento':[FECHA],
          'Moneda cumplimiento':['COP']
          }

    flt2={'Vencimiento':[FECHA],
          'Moneda_Cumplimiento':['COP'],
    
          }
        
    return sumar_si_conjunto(opc, 'Cuentas por Cumplir', flt1) +  sumar_si_conjunto(fwd, 'CXC', flt2)
    



'/////////////////////////////////////////// Función Valora OPCIÓN ////////////////////////////////////////////////////////////////////////'

def valora_libopcion(base,tc, curvacop,curvausd, curvavol,fechav,tasaf):
    
    global fecha_ult
    base["Moneda Cumplimiento"] = np.where(
        base["Identificación contraparte"].str[:4] == "4444",
        "USD",
        "COP"
    )
    
    base["Plazo"] = (base["Fecha de Vencimiento"] - fechav).dt.days
    
    
    base["Tasa Cop"] = base["Plazo"].apply(
        lambda p: 0 if p <= 0 else Interpolacion_Tasa(p, curvacop, "COP")
    )
    
    
    base["Tasa Usd"] = base["Plazo"].apply(
        lambda p: 0 if p <= 0 else Interpolacion_Tasa(p, curvausd, "USD")
    )
    
    
    base["Volatilidad1"] = base.apply(
        lambda r: Zigma_Option(
            tc,
            float(r["Precio de Ejercicio"]),
            curvavol,
            r["Tasa Cop"],
            r["Tasa Usd"],
            r["Plazo"]
        ),
        axis=1
    )
     
    
    base["Plazo Cumplimiento"] = (
        base["Plazo"] +
        (base["Fecha de Cumplimiento"] - base["Fecha de Vencimiento"]).dt.days
    )
    
    
    
    base["Dias inf USD"] = np.where(
        base["Plazo"] <= 0,
        0,
        base["Plazo Cumplimiento"].apply(
            lambda x: VLookup(x, 'Plazo Inferior', curvausd, 'Plazo Inferior', True)
        )
    )
    
    
    
    base["Dias Sup USD"] = np.where(
        base["Plazo"] <= 0,
        0,
        base["Plazo Cumplimiento"].apply(
            lambda x: VLookup(x, 'Plazo Inferior', curvausd, 'Plazo Superior', True)
        )
    )
    
    
    
    base["Tasa Inf USD"] = np.where(
        base["Plazo Cumplimiento"] <= 0,
        0,
        base["Dias inf USD"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvausd, "Tasas USD", True)
        )
    )
    
    
    base["Tasa Sup USD"] = np.where(
        base["Plazo Cumplimiento"] <= 0,
        0,
        base["Dias Sup USD"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvausd, "Tasas USD", True)
        )
    )
     
    
    
    
    base["Tasa Val USD Cump"] = np.where(
        base["Plazo Cumplimiento"] <= 0,
        0,
        base["Tasa Inf USD"] +
        (base["Tasa Sup USD"] - base["Tasa Inf USD"]) *
        ((base["Plazo"] - base["Dias inf USD"]) /
         (base["Dias Sup USD"] - base["Dias inf USD"]))
    )


    base['Factor De Descuento'] = (np.exp((base['Tasa Val USD Cump'] * base['Plazo Cumplimiento'])/365))/(np.exp((base['Tasa Usd']*base['Plazo'])/365))


    base["Dias Inf SUP"] = np.where(
        base["Plazo"] <= 0,
        0,
        base["Plazo"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "Plazo Inferior", True)
        )
    )
    
    base["Dias Sup SUP"] = np.where(
        base["Plazo"] <= 0,
        0,
        base["Plazo"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "Plazo Superior", True)
        )
    )
    
    
    base["Tasa Inf 10PUT"] = np.where(
        base["Dias Inf SUP"] <= 0,
        0,
        base["Dias Inf SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "10 D PUT", True)
        )
    )
    
    
    base["Tasa Sup 10PUT"] = np.where(
        base["Dias Sup SUP"] <= 0,
        0,
        base["Dias Sup SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "10 D PUT", True)
        )
    )


    values = (base['Tasa Inf 10PUT']+(base['Tasa Sup 10PUT']-base['Tasa Inf 10PUT'])*((base['Plazo']-base['Dias Inf SUP'])/(base['Dias Sup SUP']-base['Dias Inf SUP'])))
    base['Delta_10PUT'] = values.where(base.Plazo > 0, other=0)



    base["Tasa Inf 25PUT"] = np.where(
        base["Dias Inf SUP"] <= 0,
        0,
        base["Dias Inf SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "25 D PUT", True)
        )
    )
    
    
    base["Tasa Sup 25PUT"] = np.where(
        base["Dias Sup SUP"] <= 0,
        0,
        base["Dias Sup SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "25 D PUT", True)
        )
    )

    values = (base['Tasa Inf 25PUT']+(base['Tasa Sup 25PUT']-base['Tasa Inf 25PUT'])*((base['Plazo']-base['Dias Inf SUP'])/(base['Dias Sup SUP']-base['Dias Inf SUP'])))
    base['Delta_25PUT'] = values.where(base.Plazo > 0, other=0)

    base["Tasa Inf ATM"] = np.where(
        base["Dias Inf SUP"] <= 0,
        0,
        base["Dias Inf SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "ATM", True)
        )
    )
    
    # Tasa Superior ATM
    base["Tasa Sup ATM"] = np.where(
        base["Dias Sup SUP"] <= 0,
        0,
        base["Dias Sup SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "ATM", True)
        )
    )
    values = (base['Tasa Inf ATM']+(base['Tasa Sup ATM']-base['Tasa Inf ATM'])*((base['Plazo']-base['Dias Inf SUP'])/(base['Dias Sup SUP']-base['Dias Inf SUP'])))
    base['Delta_ATM'] = values.where(base.Plazo > 0, other=0)

    # Tasa Inferior 25CALL
    base["Tasa Inf 25CALL"] = np.where(
        base["Dias Inf SUP"] <= 0,
        0,
        base["Dias Inf SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "25 D CALL", True)
        )
    )
    
    # Tasa Superior 25CALL
    base["Tasa Sup 25CALL"] = np.where(
        base["Dias Sup SUP"] <= 0,
        0,
        base["Dias Sup SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "25 D CALL", True)
        )
    )

    values = (base['Tasa Inf 25CALL']+(base['Tasa Sup 25CALL']-base['Tasa Inf 25CALL'])*((base['Plazo']-base['Dias Inf SUP'])/(base['Dias Sup SUP']-base['Dias Inf SUP'])))
    base['Delta_25CALL'] = values.where(base.Plazo > 0, other=0)

    base["Tasa Inf 10CALL"] = np.where(
        base["Dias Inf SUP"] <= 0,
        0,
        base["Dias Inf SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "10 D CALL", True)
        )
    )
    
    base["Tasa Sup 10CALL"] = np.where(
        base["Dias Sup SUP"] <= 0,
        0,
        base["Dias Sup SUP"].apply(
            lambda x: VLookup(x, "Plazo Inferior", curvavol, "10 D CALL", True)
        )
    )


    values = (base['Tasa Inf 10CALL']+(base['Tasa Sup 10CALL']-base['Tasa Inf 10CALL'])*((base['Plazo']-base['Dias Inf SUP'])/(base['Dias Sup SUP']-base['Dias Inf SUP'])))
    base['Delta_10CALL'] = values.where(base.Plazo > 0, other=0)



     
    d= [0.1,0.25,0.50,0.75,0.90]  
    Dlta=pd.DataFrame({'Deltas':d})
    sur=base.loc[:, 'Delta_10PUT':'Delta_10CALL']



    base[['Precio de Ejercicio']] = base[['Precio de Ejercicio']].apply(pd.to_numeric)


    base["Volatilidad Ajustada Cubic Funcion"] = base.apply(
     lambda row: 0 if row["Plazo"] <= 0 else Volatilidad_cubic(
        tc,
        row['Precio de Ejercicio'],
        row["Plazo"],
        row["Tasa Cop"],
        row["Tasa Usd"],
        row["Delta_ATM"],
        Dlta,
        pd.DataFrame(sur.loc[row.name, :]),
        0,
        100,
        row["Tipo de opción"],
        row["Factor De Descuento"]
        ),
        axis=1
    )

# Convertir a float
    base["Volatilidad Ajustada Cubic Funcion"] = base["Volatilidad Ajustada Cubic Funcion"].astype(float)
    base["Volatilidad"] = base["Volatilidad"].astype(float)
    
    
    base['Diferencia Vana-Volga']=(base['Volatilidad Ajustada Cubic Funcion']-base['Volatilidad1'])
    
    base["BS"] = base.apply(
        lambda row: Valor_Opcion(
            tc,
            row["Precio de Ejercicio"],
            row["Plazo"],
            row["Tasa Usd"],
            row["Tasa Cop"],
            row["Volatilidad Ajustada Cubic Funcion"],
            row["Tipo de opción"]
        ),
        axis=1
    )  
     


    base['Factor de Descuento1']=np.exp((base['Tasa Val USD Cump']*base['Plazo Cumplimiento'])/365)/np.exp((base['Tasa Usd']*base['Plazo'])/365)
    base['BS Ajustado']=base['BS']/base['Factor de Descuento1']

    base[['Nominal']] = base[['Nominal']].apply(pd.to_numeric)
    
    print('Valor Libro Cálculado')  
    base['Valor Libro (CRNCY)'] = base.apply(lambda row: calculate_valor_libro(row['Plazo'],
                                                                                                    row['Posición en la opción'],
                                                                                                        row['Moneda Cumplimiento'],
                                                                                                        row['BS Ajustado'],
                                                                                                        row['Nominal'],
                                                                                                        tc), axis=1)

    


    base['Fecha de Vencimiento'] = pd.to_datetime(base['Fecha de Vencimiento'], errors='coerce')
    base['Fecha de Vencimiento']=base['Fecha de Vencimiento'].dt.strftime("%Y%m%d").astype(int)

         
    base['Tasa Fix'] = base.apply(lambda row: tfix(row['Plazo'],
                                                                                                        row['Fecha de Vencimiento'],
                                                                                                        tasaf,
                                                                                                        mesu,
                                                                                                        tc), axis=1)    





    base['Fecha de Vencimiento'] = base['Fecha de Vencimiento'].apply(lambda x: pd.to_datetime(str(x), format='%Y%m%d'))   
    

    base['Cuentas por Cumplir'] = base.apply(lambda row: Cuentas_Por_opc(row['Moneda cumplimiento'],
                                                                                                    row['Fecha de Vencimiento'],
                                                                                                    row['Fecha de Cumplimiento'],
                                                                                                    fechav, # Fecha de valoracion, validar si esta cambia
                                                                                                    row['Tipo de opción'],
                                                                                                    row['Precio de Ejercicio'],
                                                                                                    row['Nominal'],
                                                                                          row['Posición en la opción'],
                                                                                                    0, # ingresar FRA si se necesita
                                                                                                    row['Tasa Fix'], #tasa fix
                                                                                                    row['Modalidad Cumplimiento']), axis=1)


   

    base['USD'] = base.apply(lambda row: Vencimiento("USD",
                                                                                                    row['Moneda cumplimiento'],#ok
                                                                                                    row['Modalidad Cumplimiento'],#ok,
                                                                                                    row['Fecha de Vencimiento'], #ok 
                                                                                                    fechav,
                                                                                                    row['Tipo de opción'],#ok
                                                                                          row['Precio de Ejercicio'],#ok
                                                                                                    row['Nominal'], #ok
                                                                                                    row['Posición en la opción'], #ok
                                                                                                    row['Tasa Fix'], 
                                                                                                    row['Fecha de Cumplimiento']),axis=1)
                                                                                                    

    base['COP'] = base.apply(lambda row: Vencimiento("COP",
                                                                                                    row['Moneda cumplimiento'],#ok
                                                                                                    row['Modalidad Cumplimiento'],#ok,
                                                                                                    row['Fecha de Vencimiento'], #ok 
                                                                                                    fechav,
                                                                                                    row['Tipo de opción'],#ok
                                                                                          row['Precio de Ejercicio'],#ok
                                                                                                    row['Nominal'], #ok
                                                                                                    row['Posición en la opción'], #ok
                                                                                                    row['Tasa Fix'], 
                                                                                                    row['Fecha de Cumplimiento']),axis=1)


    #base['COP'].sum()



    sign_nominal = lambda operacion, nominal: -nominal if operacion=="SELL" else nominal
    base['Delta'] = base.apply(lambda row: delta_opcion(fechav,
                                                                                   row['Fecha de Vencimiento'],
                                                                                   tc,
                                                                                   row['Precio de Ejercicio'],
                                                                                   row['Tasa Cop'],
                                                                                   row['Tasa Usd'],
                                                                                   row['Volatilidad Ajustada Cubic Funcion'],
                                                                                   row['Tipo de opción']) * sign_nominal(row['Posición en la opción'], row['Nominal'])
                                                                                   if row['Fecha de Vencimiento'] != fechav else 0, axis=1)



    base["Estructura"] = np.where(base.iloc[:, 1] == "", "N", "EV") 

    base['Fee']=base['Fee'].apply(pd.to_numeric)
    base['Fecha Fee']=pd.to_datetime(base['Fecha Fee'],dayfirst=True)
    base['Fee'].fillna(0, inplace=True)
    base['Fecha Fee'].fillna(0, inplace=True)
    base['Valor Total Prima']=base['Valor Total Prima'].apply(pd.to_numeric)
    base['Valor Total Prima'].fillna(0, inplace=True)

    for i in range(len(base)):
        if base['Moneda cumplimiento'][i] == "":
            base['Moneda cumplimiento'][i] = base['Moneda de la  Prima'][i]

    base[['Value Amount']] = base[['Value Amount']].apply(pd.to_numeric)    
    base['DifechavSINCVA'] = base.apply(lambda row: difvalsinCVA(row['Trade Id'],
                                                                                   row['Moneda cumplimiento'],
                                                                                   row['Valor Libro (CRNCY)'],
                                                                                   tc,
                                                                                   row['Value Amount']), axis=1)        
            
    base[['CVA Fair Value COP']] = base[['CVA Fair Value COP']].apply(pd.to_numeric)      
    base['DifechavCONCVA'] = base.apply(lambda row: difvalconCVA(row['Trade Id'],
                                                                                   row['Plazo'],
                                                                                   row['CVA Fair Value COP'],
                                                                                   row['Value Amount']), axis=1)        
     

    base[['Spread CVA']] = base[['Spread CVA']].apply(pd.to_numeric)          
    base['BS_CVA'] = base.apply(lambda row: calcular_BS_CVA(row['Trade Id'],
                                                                                   row['Spread CVA'],
                                                                                   row['BS Ajustado'],
                                                                                   row['Plazo']), axis=1)     

            
    base['ValorLibroCVA'] = base.apply(lambda row: ValorLibroCVA(row['Plazo'],
                                                                                   row['Posición en la opción'],
                                                                                   row['Moneda cumplimiento'],
                                                                                   row['BS_CVA'],
                                                                                   row['Nominal'],
                                                                                   tc), axis=1)          
            
    base['DifrevCVA'] = base.apply(lambda row: DifrevCVA(row['Trade Id'],
                                                                                   row['Plazo'],
                                                                                   row['ValorLibroCVA'],
                                                                                   row['CVA Fair Value COP']), axis=1)     

        
            
    base['DifporCVA'] = base.apply(lambda row: DifporCVA(row['Trade Id'],
                                                                                   row['Plazo'],
                                                                                   row['Moneda cumplimiento'],
                                                                                   row['ValorLibroCVA'],
                                                                                   row['Valor Libro (CRNCY)'],tc), axis=1)   




    valport= ValorOPT(base,tc)
    valportcva =ValorOPTCVA(base,tc)
    
    vput=Vencimientosopc(base, 'PUT', fecha_ult)
    vcall=Vencimientosopc(base, 'CALL', fecha_ult)
    vtot=vput+vcall 

    primaput=calcular_primas(base, 'PUT', fecha_ult)
    primacall=calcular_primas(base, 'CALL', fecha_ult)
    ptot=primaput+primacall
    caja=vtot+ptot
    
    cxcu= base['Cuentas por Cumplir'].sum()
    cxcopc = base.loc[(base['Moneda cumplimiento'] == 'COP'), 'Cuentas por Cumplir'].sum() + (tc * base.loc[base['Moneda cumplimiento'] == "USD", 'Cuentas por Cumplir']).sum()
    
    total=valport +caja +cxcu
    total2=valport + cxcopc    

    return valport, valportcva, caja,cxcu,total,total2

'/////////////////////////////////////////// Función Valora OPCIÓN ////////////////////////////////////////////////////////////////////////'


'/////////////////////////////////////////// Función Valora FORWARD ////////////////////////////////////////////////////////////////////////'

def valora_libforward(base,tc, curvacop,curvausd,fecha,tsaf):
    
    global fecha_ult

    base['Plazo']=((base['Vencimiento']-fecha)/ np.timedelta64(1, 'D')).astype(int)
    
    L=[]
    for i in range(len(base)):
        if base['Plazo'][i] <= 0:
            k=0
        else:    
            k=Interpolacion_Tasa(base['Plazo'][i], curvacop, "COP")
            #k= float("".join([str(x) for x in k]))
        L.append(k)
    Tcop = pd.DataFrame({'Tasa Cop':L})
    base = pd.concat([base,Tcop], axis=1) 
    del Tcop

    L=[]
    for i in range(len(base)):
        if base['Plazo'][i] <= 0:
            k=0
        else:  
            k=Interpolacion_Tasa(base['Plazo'][i], curvausd, 'USD')
            #k= float("".join([str(x) for x in k]))
        L.append(k)
    Tusd = pd.DataFrame({'Tasa Usd':L})
    base = pd.concat([base,Tusd], axis=1)
    del Tusd

        
    base['VP Flujo COP']=base.apply(lambda row: VP_FLUJO_COP(row['T.Forward'],row['Nominal'],row['Plazo'],row['Tasa Cop'],row['Operación']),axis=1) 
            
    base['VP Flujo USD']=base.apply(lambda row: VP_FLUJO_USD(row['T.Forward'],row['Nominal'],row['Plazo'],row['Tasa Usd'],row['Operación']),axis=1) 

    'REVISAR LA MONEDA DE CUMPLIMIENTO'


    base['Valor Forward']=base.apply(lambda row: Vlr_forward(row['Plazo'],row['Moneda_Cumplimiento'],row['VP Flujo COP'],row['VP Flujo USD'],tc),axis=1) 
    base['Vencimiento']=base['Vencimiento'].dt.strftime("%Y%m%d").astype(int)
    base['Tasa Fix']=base.apply(lambda row: tfixforr(row['Plazo'],row['Vencimiento'],tsaf,tc),axis=1)
    base['Vencimiento'] = base['Vencimiento'].apply(lambda x: pd.to_datetime(str(x), format='%Y%m%d'))    
    base['CXC']=base.apply(lambda row: Cuentas_Por_FWD(row['Moneda_Cumplimiento'],row['Vencimiento'],row['Cumplimiento'],fval,row['T.Forward'],row['Nominal'],row['Operación'],0,row['Tasa Fix'],row['Modalidad']),axis=1)
    base['USD']=base.apply(lambda row: Vencimiento_FWD('USD',row['Moneda_Cumplimiento'],row['Modalidad'],row['Cumplimiento'],fval,row['T.Forward'],row['Nominal'],row['Operación'],row['Tasa Fix'],row['Vencimiento']),axis=1)
    base['COP']=base.apply(lambda row: Vencimiento_FWD('COP',row['Moneda_Cumplimiento'],row['Modalidad'],row['Cumplimiento'],fval,row['T.Forward'],row['Nominal'],row['Operación'],row['Tasa Fix'],row['Vencimiento']),axis=1)

    valorfor=ValorFWD(base,tc)
    valorforcva=ValorPFWDCVA(base)
    cxcfor = base.loc[
        (base['Vencimiento'] > fecha_ult) & (base['Moneda_Cumplimiento'] == 'COP'), 
        'CXC'
    ].sum() + (base.loc[base['Moneda_Cumplimiento'] == "USD", 'Tasa Fix'] *
                base.loc[base['Moneda_Cumplimiento'] == "USD", 'CXC']).sum()

    venfor= calcular_forwards(base, fecha_ult)      
    
    total= valorfor + cxcfor + venfor

    return valorfor, valorforcva, cxcfor, venfor, total



def valora_libforward2(base,tc, curvacop,curvausd,fecha,tsaf):
    
    global fecha_ult
    #fecha_str = fecha.strftime("%Y%m%d")
    base['Plazo']=((base['Vencimiento']-fecha)/ np.timedelta64(1, 'D')).astype(int)
    
    L=[]
    for i in range(len(base)):
        if base['Plazo'][i] <= 0:
            k=0
        else:    
            k=Interpolacion_Tasa(base['Plazo'][i], curvacop, "COP")
            #k= float("".join([str(x) for x in k]))
        L.append(k)
    Tcop = pd.DataFrame({'Tasa Cop':L})
    base = pd.concat([base,Tcop], axis=1) 
    del Tcop

    L=[]
    for i in range(len(base)):
        if base['Plazo'][i] <= 0:
            k=0
        else:  
            k=Interpolacion_Tasa(base['Plazo'][i], curvausd, 'USD')
            #k= float("".join([str(x) for x in k]))
        L.append(k)
    Tusd = pd.DataFrame({'Tasa Usd':L})
    base = pd.concat([base,Tusd], axis=1)
    del Tusd

        
    base['VP Flujo COP']=base.apply(lambda row: VP_FLUJO_COP(row['T.Forward'],row['Nominal'],row['Plazo'],row['Tasa Cop'],row['Operación']),axis=1) 
            
    base['VP Flujo USD']=base.apply(lambda row: VP_FLUJO_USD(row['T.Forward'],row['Nominal'],row['Plazo'],row['Tasa Usd'],row['Operación']),axis=1) 

    'REVISAR LA MONEDA DE CUMPLIMIENTO'


    base['Valor Forward']=base.apply(lambda row: Vlr_forward(row['Plazo'],row['Moneda_Cumplimiento'],row['VP Flujo COP'],row['VP Flujo USD'],tc),axis=1) 
    base['Vencimiento']=base['Vencimiento'].dt.strftime("%Y%m%d").astype(int)
    base['Tasa Fix']=base.apply(lambda row: tfixforr(row['Plazo'],row['Vencimiento'],tsaf,tc),axis=1)
    base['Vencimiento'] = base['Vencimiento'].apply(lambda x: pd.to_datetime(str(x), format='%Y%m%d'))    
    base['CXC']=base.apply(lambda row: Cuentas_Por_FWD(row['Moneda_Cumplimiento'],row['Vencimiento'],row['Cumplimiento'],fecha,row['T.Forward'],row['Nominal'],row['Operación'],0,row['Tasa Fix'],row['Modalidad']),axis=1)
    base['USD']=base.apply(lambda row: Vencimiento_FWD('USD',row['Moneda_Cumplimiento'],row['Modalidad'],row['Cumplimiento'],fecha,row['T.Forward'],row['Nominal'],row['Operación'],row['Tasa Fix'],row['Vencimiento']),axis=1)
    base['COP']=base.apply(lambda row: Vencimiento_FWD('COP',row['Moneda_Cumplimiento'],row['Modalidad'],row['Cumplimiento'],fecha,row['T.Forward'],row['Nominal'],row['Operación'],row['Tasa Fix'],row['Vencimiento']),axis=1)

    valorfor=ValorFWD(base,tc)
    valorforcva=ValorPFWDCVA(base)
    cxcfor = base.loc[(base['Moneda_Cumplimiento'] == 'COP'), 'CXC'].sum() + (tc * base.loc[base['Moneda_Cumplimiento'] == "USD", 'CXC']).sum()

    venfor= calcular_forwards(base, fecha_ult)      
    
    total= valorfor + cxcfor 

    return valorfor, valorforcva, cxcfor, venfor, total, base





'/////////////////////////////////////////// Función Valora FORWARD ////////////////////////////////////////////////////////////////////////'


#pnov=pd.read_excel(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\ENTRADA2.xlsx", sheet_name="NOVADOS", skiprows=2, nrows=557, usecols='A:C')


'/////////////////////////////////////////// Función Valora NOVADOS ////////////////////////////////////////////////////////////////////////'

# def ValoraNov(nov1,NovxV,fval,curvacop,curvasud,pnovt1,pnov,tc,fv):

#     nov['FECHA NEGOCIACION']=pd.to_datetime(nov['FECHA NEGOCIACION'],dayfirst=True)
#     nov['VENCIMIENTO']=pd.to_datetime(nov['VENCIMIENTO'],dayfirst=True)

#     #del new

#     nov.sort_values(by='FECHA NEGOCIACION', inplace=True)
#     nov.reset_index(inplace=True,drop=True)

#     valores_unicos = nov[['VENCIMIENTO']].drop_duplicates()
#     valores_unicos.reset_index(inplace=True,drop=True)


#     nov1=nov[['TRADE ID',
#          'FECHA NEGOCIACION',
#          'VENCIMIENTO',
#          'PRECIO PACTADO',
#          'NOMINAL',
#          'COMPRA/VENTA']]

#     nov1['TRADER']=nov['TRADER']
#     nov1['BOOK']=nov['BOOK']
#     nov1['Delta Full Valuation 1 USD']=nov['Delta Full Valuation 1 USD']

#     #del nov
                
#     nov1['TRADE ID']=nov1['TRADE ID'].apply(convert_to_float)            
#     nov1['PRECIO PACTADO']=nov1['PRECIO PACTADO'].apply(convert_to_float)
#     nov1['NOMINAL']=nov1['NOMINAL'].apply(convert_to_float)
#     nov1['Delta Full Valuation 1 USD']=nov1['Delta Full Valuation 1 USD'].apply(convert_to_float)          
#     nov1['Posición_USD']=nov1.apply(lambda row: pos_usd(row['VENCIMIENTO'],row['NOMINAL'],fval,row['Delta Full Valuation 1 USD']),axis=1)
#     nov1['Posición_USD']=nov1['Posición_USD'].apply(pd.to_numeric) 
#     nov1['Valor Pactado']=nov1.apply(lambda row: vlr_pac(row['VENCIMIENTO'],fval,row['NOMINAL'],row['PRECIO PACTADO']),axis=1)



#     'BORRAR CUANDO ESTÉ LISTO'

#     '////////////////////////////'''

   

       
#     pnov['Plazo']=pnov.apply(lambda row: pla(row['Fecha'],fval), axis=1)    
#     pnov['Tasa Cop']=pnov.apply(lambda row: Interpolacion_Tasa(row['Plazo'],curvacop,"COP"), axis=1) 
#     pnov['Tasa Usd']=pnov.apply(lambda row: Interpolacion_Tasa(row['Plazo'],curvasud,"USD"), axis=1) 
#     pnov['Fwd Calculado']=pnov.apply(lambda row: fwd_cal(row['Plazo'],tc,row['Tasa Cop'],row['Tasa Usd']), axis=1) 
#     pnov['Ajuste']= pnov['Fwd Calculado']-pnov['Outright']
#     values = ((-1*pnov['Ajuste'])+pnov['Fwd Calculado'])
#     pnov['Fwd Ajustado'] = values.where(pnov.Plazo >= 0, other=0)
#     pnov['DVO1']=pnov['Pts. Forward']+tc
#     pnov['Fecha']=pnov['Fecha'].dt.strftime("%Y%m%d").astype(int)
#     nov1['VENCIMIENTO']=nov1['VENCIMIENTO'].dt.strftime("%Y%m%d").astype(int)
#     nov1['Px(T)']=nov1.apply(lambda row: Px(row['VENCIMIENTO'],int(fv)), axis=1)
#     values = ((nov1['Px(T)'])*nov1['NOMINAL'])
#     nov1['VM_COP'] = values.where(nov1.Posición_USD != 0, other=0)
#     nov1['VM_COP'].sum()

#     nov1['MTM(ACUMULADO)']=nov1.apply(lambda row: MTM_ACUM(row['VENCIMIENTO'],int(fv),row['Px(T)'],row['PRECIO PACTADO'],row['NOMINAL']), axis=1)
#     pnovt1=pd.read_excel(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\ENTRADA2.xlsx", sheet_name="NOVADOS", skiprows=2, nrows=557, usecols='H:I')
#     pnovt1.columns=['Fecha','Outright']
#     pnovt1['Fecha']=pnovt1['Fecha'].dt.strftime("%Y%m%d").astype(int)
#     nov1['FECHA NEGOCIACION']=nov1['FECHA NEGOCIACION'].dt.strftime("%Y%m%d").astype(int)   
#     nov1['PX(T-1)']=nov1.apply(lambda row: PXT1(row['VENCIMIENTO'],int(fv),row['FECHA NEGOCIACION'],pnovt1),axis=1)

#     nov1['MTM DÍA']=nov1.apply(lambda row: MTMD(row['VENCIMIENTO'],int(fv),row['PX(T-1)'],row['Px(T)'],row['PRECIO PACTADO'],row['NOMINAL']),axis=1)
#     nov1['MTM DÍA'].sum()

#     NovxV = valores_unicos
#     NovxV['VENCIMIENTO']=NovxV['VENCIMIENTO'].dt.strftime("%Y%m%d").astype(int)
#     del valores_unicos


#     NovxV['PX_INICIAL']=NovxV.apply(lambda row: P_INI(row['VENCIMIENTO'],int(fv),pnovt1),axis=1)
#     NovxV['PX_FINAL']=NovxV.apply(lambda row: P_INI(row['VENCIMIENTO'],int(fv),pnov),axis=1)

        
#     NovxV['MTM DÍA']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','MTM DÍA'),axis=1)
#     NovxV['MTM TOTAL']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','MTM(ACUMULADO)'),axis=1)
#     NovxV['VALOR MERCADO']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','VM_COP'),axis=1)
#     NovxV['POSICIÓN_USD']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','Posición_USD'),axis=1)

#     return NovxV

'/////////////////////////////////////////// Función Valora NOVADOS ////////////////////////////////////////////////////////////////////////'


'//////////////////////////////////////////// funciónes cálculo PYG////////////////////////////////////////////////////////////////////////'

'OPCIONES'
def ValorPOPTUSD(base):
    flt1={
          'Moneda cumplimiento':['USD']
          }
    
    return sumar_si_conjunto(base, 'Valor Libro (CRNCY)', flt1) 

#ValorPOPTUSD(opc)


def ValorPOPTCOP(base):
    flt1={
          'Moneda cumplimiento':['COP']
          }
    
    return sumar_si_conjunto(base, 'Valor Libro (CRNCY)', flt1) 


#ValorPOPTCOP(opc)

def ValorOPT(base,tc):
   return ValorPOPTCOP(base)+(ValorPOPTUSD(base)*tc)


def ValorPOPTUSDCVA(base):
    flt1={
          'Moneda cumplimiento':['USD']
          }
    
    return sumar_si_conjunto(base, 'ValorLibroCVA', flt1)

#ValorPOPTUSDCVA(opc)    


def ValorPOPTCOPCVA(base):
    flt1={
          'Moneda cumplimiento':['COP']
          }
    
    return sumar_si_conjunto(base, 'ValorLibroCVA', flt1) 


#ValorPOPTCOPCVA(opc)

def ValorOPTCVA(base,tc):
   return ValorPOPTCOPCVA(base)+(ValorPOPTUSDCVA(base)*tc)


def PORTPUTOPTUSD(base, fecha):
    # Aplicar las condiciones
    condicion = (
        (base['Posición en la opción'] == "BUY") &
        (base['Tipo de opción'] == "PUT") &
        (base['Fecha de Vencimiento'] > fecha)
    )
    
    condicion2 = (
        (base['Posición en la opción'] == "SELL") &
        (base['Tipo de opción'] == "PUT") &
        (base['Fecha de Vencimiento'] > fecha)
    )
    
    # Sumar los valores correspondientes de la columna J
    return base.loc[condicion, 'Nominal'].sum() - base.loc[condicion2, 'Nominal'].sum()

def PORTCALLOPTUSD(base, fecha):
    # Aplicar las condiciones
    condicion = (
        (base['Posición en la opción'] == "BUY") &
        (base['Tipo de opción'] == "CALL") &
        (base['Fecha de Vencimiento'] > fecha)
    )
    
    condicion2 = (
        (base['Posición en la opción'] == "SELL") &
        (base['Tipo de opción'] == "CALL") &
        (base['Fecha de Vencimiento'] > fecha)
    )
    
    # Sumar los valores correspondientes de la columna J
    return base.loc[condicion, 'Nominal'].sum() - base.loc[condicion2, 'Nominal'].sum()


def PORTOPTUSD(base,fecha):
    return PORTPUTOPTUSD(base, fecha) + PORTCALLOPTUSD(base, fecha)
    
    
def DELTAPUTOPTUSD(base, fecha):

    condicion = (
        (base['Tipo de opción'] == "PUT") &
        (base['Fecha de Vencimiento'] > fecha))
    
    return base.loc[condicion, 'Delta'].sum()

    

def DELTACALLOPTUSD(base, fecha):

    condicion = (
        (base['Tipo de opción'] == "CALL") &
        (base['Fecha de Vencimiento'] > fecha))
    
    return base.loc[condicion, 'Delta'].sum()   

def DELTAOPT(base,fecha):
    DELTAPUTOPTUSD(base, fecha) + DELTACALLOPTUSD(base, fecha)
     
def VALPUTOPT(base,tc):
    condicion = (
        (base['Tipo de opción'] == "PUT") &
        (base['Moneda cumplimiento'] == "COP"))
        
    condicion2 = (
        (base['Tipo de opción'] == "PUT") &
        (base['Moneda cumplimiento'] == "USD"))        
        
    
    return base.loc[condicion, 'Valor Libro (CRNCY)'].sum() + (base.loc[condicion2, 'Valor Libro (CRNCY)'].sum()) * tc

def VALCALLOPT(base,tc):
    condicion = (
        (base['Tipo de opción'] == "CALL") &
        (base['Moneda cumplimiento'] == "COP"))
        
    condicion2 = (
        (base['Tipo de opción'] == "CALL") &
        (base['Moneda cumplimiento'] == "USD"))       
          
    return base.loc[condicion, 'Valor Libro (CRNCY)'].sum() + (base.loc[condicion2, 'Valor Libro (CRNCY)'].sum()) * tc

def VALTOTALOPT(base,tc):
    return VALCALLOPT(base,tc) + VALPUTOPT(base,tc)

def Vencimientosopc(base, Tipo, fecha_parametro):

    # Asegurar tipo datetime
    #base[' Emisión'] = pd.to_datetime(base[' Emisión'])
    #fecha_parametro = pd.to_datetime(fecha_parametro)

    # ---- PARTE 1 ----
    # SUMA( SI(F=Tipo, SI(O="COP", SI(Emisión > fecha, Z))) )
    filtro1 = (
        (base['Tipo de opción'] == Tipo) &
        (base['Moneda cumplimiento'] == "COP") &
        (base['Fecha de Vencimiento'] > fecha_parametro)
    )
    parte1 = base.loc[filtro1, 'COP'].sum()

    # ---- PARTE 2 ----
    # SUMA( SI(F=Tipo, SI(N="DELIVERY", SI(Emisión > fecha, Y * W))) )
    filtro2 = (
        (base['Tipo de opción'] == Tipo) &
        (base['Modalidad Cumplimiento'] == "DELIVERY") &
        (base['Fecha de Vencimiento'] > fecha_parametro)
    )
    parte2 = (base.loc[filtro2, 'USD'] * base.loc[filtro2, 'Tasa Fix']).sum()

    # Resultado final
    return parte1 + parte2


def calcular_primas(base, Tipo, fecha_objetivo):

    # Convertir columna a fecha
    #base[' Fecha de Emisión'] = pd.to_datetime(base[' Emisión'])
    fecha_objetivo = pd.to_datetime(fecha_objetivo)

    # Filtro general (ya NO usa Operación)
    filtro = (
        (base['Tipo de opción'] == Tipo) &   # PUT o CALL
        (base['Moneda cumplimiento'] == "COP") &     
        (base['Fecha de Emisión'] > fecha_objetivo)
    )

    # Sumar todas las primas sin importar BUY o SELL
    total_primas = base.loc[filtro, 'Valor Total Prima'].sum()

    return total_primas


def delta_opc(base,tc,curvavol,tasaf,fechault,fechav):
    
    base=base.copy()
    d= [0.1,0.25,0.50,0.75,0.90]  
    Dlta=pd.DataFrame({'Deltas':d})
    sur=base.loc[:, 'Delta_10PUT':'Delta_10CALL']

    def calc_vol(row):
        if row['Plazo'] <= 0:
            return 0
        return Volatilidad_cubic(tc,
                                 row['Precio de Ejercicio'],
                                 row['Plazo'],
                                 row['Tasa Cop'],
                                 row['Tasa Usd'],
                                 row['Delta_ATM'],
                                 Dlta,
                                 pd.DataFrame(sur.loc[row.name, :]),
                                 0, 100,
                                 row['Tipo de opción'],
                                 row['Factor De Descuento'])
    base['Volatilidad Ajustada Cubic Funcion'] = base.apply(calc_vol, axis=1).astype(float)
     
    base[['Volatilidad Ajustada Cubic Funcion']] = base[['Volatilidad Ajustada Cubic Funcion']].astype(float)
    base[['Volatilidad']] = base[['Volatilidad']].astype(float)
    print("volcalculada")

    base['BS'] = base.apply(
        lambda row: Valor_Opcion(tc,
                                 row['Precio de Ejercicio'],
                                 row['Plazo'],
                                 row['Tasa Usd'],
                                 row['Tasa Cop'],
                                 row['Volatilidad Ajustada Cubic Funcion'],
                                 row['Tipo de opción']),
        axis=1
    )
    base['BS Ajustado'] = base['BS'] / base['Factor de Descuento1']
    
   

    
    
    base['Valor Libro (CRNCY)'] = base.apply(lambda row: calculate_valor_libro(row['Plazo'],
                                                                                                    row['Posición en la opción'],
                                                                                                        row['Moneda Cumplimiento'],
                                                                                                        row['BS Ajustado'],
                                                                                                        row['Nominal'],
                                                                                                        tc), axis=1)
    print("vlrlibro")
    
    base['Fecha de Vencimiento']=base['Fecha de Vencimiento'].dt.strftime("%Y%m%d").astype(int)
    
    base['Tasa Fix'] = base.apply(lambda row: tfix(row['Plazo'],
                                                                                                        row['Fecha de Vencimiento'],
                                                                                                        tasaf,
                                                                                                        fechault,
                                                                                                        tc), axis=1) 
    base['Fecha de Vencimiento'] = base['Fecha de Vencimiento'].apply(lambda x: pd.to_datetime(str(x), format='%Y%m%d')) 
    
    base['Cuentas por Cumplir'] = base.apply(lambda row: Cuentas_Por_opc(row['Moneda cumplimiento'],
                                                                                                    row['Fecha de Vencimiento'],
                                                                                                    row['Fecha de Cumplimiento'],
                                                                                                    fechav, # Fecha de valoracion, validar si esta cambia
                                                                                                    row['Tipo de opción'],
                                                                                                    row['Precio de Ejercicio'],
                                                                                                    row['Nominal'],
                                                                                          row['Posición en la opción'],
                                                                                                    0, # ingresar FRA si se necesita
                                                                                                    row['Tasa Fix'], #tasa fix
                                                                                                    row['Modalidad Cumplimiento']), axis=1)
    
    filtro1 = (base['Moneda cumplimiento'] == "USD") 
    parte1 = (base.loc[filtro1, 'Cuentas por Cumplir'].sum())*tc
    
    filtro1 = (base['Moneda cumplimiento'] == "COP") 
    parte2 = (base.loc[filtro1, 'Cuentas por Cumplir'].sum())
    
    cxc=parte1+parte2
    
    valport= ValorOPT(base,tc)
    
    return valport, cxc

def rhocop_opc_mascara(base, tc, curvacop, plazo_inf, plazo_sup):


    # --- Copia local ---
    base_local = base.copy()
    #base_local.columns = base_local.columns.str.strip()

    # ============================================================
    # 1. Construcción de máscara por plazos (curva COP / días USD)
    # ============================================================
    tabla_rangos = curvacop[['Plazo Inferior', 'Plazo Superior']].drop_duplicates().reset_index(drop=True)
    mask_rango = (tabla_rangos['Plazo Inferior'] == plazo_inf) & (tabla_rangos['Plazo Superior'] == plazo_sup)

    if not mask_rango.any():
        raise ValueError("No se encontró un rango coincidente en la curva COP.")

    idx = tabla_rangos.index[mask_rango][0]
    rangos_a_usar = [idx] if idx == 0 else [idx-1, idx]

    mask = pd.Series(False, index=base_local.index)
    for i in rangos_a_usar:
        inf = tabla_rangos.at[i, 'Plazo Inferior']
        sup = tabla_rangos.at[i, 'Plazo Superior']
        # Cruce por días USD
        mask |= (base_local['Dias inf USD'] <= sup) & (base_local['Dias Sup USD'] >= inf)

    # ============================================================
    # 2. Tasa COP (solo filas dentro de la máscara)
    # ============================================================
    base_local['Tasa Cop'] = base_local.index.map(
        lambda i: Interpolacion_Tasa(base_local.at[i, 'Plazo'], curvacop, "COP")
        if mask.loc[i] and base_local.at[i, 'Plazo'] > 0
        else base_local.at[i, 'Tasa Cop'] if 'Tasa Cop' in base_local.columns else 0.0
    )

    # ============================================================
    # 3. Volatilidad ajustada cubic (solo máscara)
    # ============================================================
    d = [0.1, 0.25, 0.50, 0.75, 0.90]
    Dlta = pd.DataFrame({'Deltas': d})
    sur = base_local.loc[:, 'Delta_10PUT':'Delta_10CALL']

    def vol_cubic(i):
        if not mask.loc[i] or base_local.at[i, 'Plazo'] <= 0:
            return base_local.at[i, 'Volatilidad Ajustada Cubic Funcion'] if 'Volatilidad Ajustada Cubic Funcion' in base_local.columns else 0.0
        return float(
            Volatilidad_cubic(
                tc,
                base_local.at[i, 'Precio de Ejercicio'],
                base_local.at[i, 'Plazo'],
                base_local.at[i, 'Tasa Cop'],
                base_local.at[i, 'Tasa Usd'],
                base_local.at[i, 'Delta_ATM'],
                Dlta,
                pd.DataFrame(sur.loc[i, :]),
                0,
                100,
                base_local.at[i, 'Tipo de opción'],
                base_local.at[i, 'Factor De Descuento']
            )
        )

    base_local['Volatilidad Ajustada Cubic Funcion'] = base_local.index.map(vol_cubic).astype(float)

    # ============================================================
    # 4. Valor Opción BS (solo máscara)
    # ============================================================
    base_local['BS'] = base_local.index.map(
        lambda i: Valor_Opcion(
            tc,
            base_local.at[i, 'Precio de Ejercicio'],
            base_local.at[i, 'Plazo'],
            base_local.at[i, 'Tasa Usd'],
            base_local.at[i, 'Tasa Cop'],
            base_local.at[i, 'Volatilidad Ajustada Cubic Funcion'],
            base_local.at[i, 'Tipo de opción']
        ) if mask.loc[i] else base_local.at[i, 'BS'] if 'BS' in base_local.columns else 0.0
    )

    # ============================================================
    # 5. BS Ajustado
    # ============================================================
    base_local['Factor de Descuento1'] = (
        np.exp((base_local['Tasa Val USD Cump'] * base_local['Plazo Cumplimiento']) / 365) /
        np.exp((base_local['Tasa Usd'] * base_local['Plazo']) / 365)
    ).astype(float)

    base_local['BS Ajustado'] = base_local.index.map(
        lambda i: base_local.at[i, 'BS'] / base_local.at[i, 'Factor de Descuento1']
        if mask.loc[i] else base_local.at[i, 'BS Ajustado'] if 'BS Ajustado' in base_local.columns else 0.0
    )

    # ============================================================
    # 6. Valor Libro (solo máscara)
    # ============================================================
    base_local['Nominal'] = pd.to_numeric(base_local['Nominal'])

    base_local['Valor Libro (CRNCY)'] = base_local.index.map(
        lambda i: calculate_valor_libro(
            base_local.at[i, 'Plazo'],
            base_local.at[i, 'Posición en la opción'],
            base_local.at[i, 'Moneda Cumplimiento'],
            base_local.at[i, 'BS Ajustado'],
            base_local.at[i, 'Nominal'],
            tc
        ) if mask.loc[i] else base_local.at[i, 'Valor Libro (CRNCY)'] if 'Valor Libro (CRNCY)' in base_local.columns else 0.0
    )

    # ============================================================
    # 7. Valor Portafolio
    # ============================================================
    valport = float(ValorOPT(base_local, tc))

    return  valport,base_local


def rhousdopc(base, tc, curvausd, plazo_inf, plazo_sup):
    base_local = base.copy()
    
    # --- FILTRO POR RANGOS ---
    tabla_rangos = curvausd[['Plazo Inferior', 'Plazo Superior']].drop_duplicates().reset_index(drop=True)
    mask_rango = (tabla_rangos['Plazo Inferior'] == plazo_inf) & (tabla_rangos['Plazo Superior'] == plazo_sup)
    
    if not mask_rango.any():
        raise ValueError("No se encontró un rango coincidente en la curva.")
    
    idx = tabla_rangos.index[mask_rango][0]
    
    # Rangos a usar
    if idx == 0:
        rangos_a_usar = [idx]
    else:
        rangos_a_usar = [idx-1, idx]
    
    mask = pd.Series(False, index=base_local.index)
    for i in rangos_a_usar:
        inf = tabla_rangos.at[i, 'Plazo Inferior']
        sup = tabla_rangos.at[i, 'Plazo Superior']
        mask |= (base_local['Dias inf USD'] <= sup) & (base_local['Dias Sup USD'] >= inf)
    
    base_filtro = base_local.loc[mask].copy()
    
    # --- CÁLCULOS ---
    # Tasa USD
    base_filtro['Tasa Usd'] = base_filtro['Plazo'].apply(
        lambda p: float(Interpolacion_Tasa(p, curvausd, 'USD')) if p > 0 else 0.0
    )
    
    # Tasa Inf USD
    base_filtro['Tasa Inf USD'] = base_filtro.apply(
        lambda row: float(VLookup(row["Dias inf USD"], 'Plazo Inferior', curvausd, 'Tasas USD', True)) 
        if row["Plazo Cumplimiento"] > 0 else 0.0, axis=1
    )
    
    # Tasa Sup USD
    base_filtro['Tasa Sup USD'] = base_filtro.apply(
        lambda row: float(VLookup(row["Dias Sup USD"], 'Plazo Inferior', curvausd, 'Tasas USD', True)) 
        if row["Plazo Cumplimiento"] > 0 else 0.0, axis=1
    )
    
    # Tasa Valor USD Cumplimiento
    def tasa_val(row):
        if row["Plazo Cumplimiento"] <= 0:
            return 0.0
        return float(
            row["Tasa Inf USD"] + (row["Tasa Sup USD"] - row["Tasa Inf USD"]) *
            ((row["Plazo"] - row["Dias inf USD"]) / (row["Dias Sup USD"] - row["Dias inf USD"]))
        )
    base_filtro['Tasa Val USD Cump'] = base_filtro.apply(tasa_val, axis=1)
    
    # Factor Descuento
    base_filtro['Factor De Descuento'] = (
        np.exp((base_filtro['Tasa Val USD Cump'] * base_filtro['Plazo Cumplimiento']) / 365) /
        np.exp((base_filtro['Tasa Usd'] * base_filtro['Plazo']) / 365)
    ).astype(float)
    
    # Volatilidad ajustada cubic
    def vol_cubic(row, i):
        if row["Plazo"] <= 0:
            return 0.0
        return float(
            Volatilidad_cubic(
                tc, row['Precio de Ejercicio'], row["Plazo"], row["Tasa Cop"],
                row["Tasa Usd"], row["Delta_ATM"], Dlta, pd.DataFrame(sur.loc[i, :]),
                0, 100, row["Tipo de opción"], row["Factor De Descuento"]
            )
        )
    base_filtro['Volatilidad Ajustada Cubic Funcion'] = [
        float(vol_cubic(row, i)) for i, row in base_filtro.iterrows()
    ]
    
    # Valor Opción BS
    base_filtro['BS'] = base_filtro.apply(
        lambda row: float(
            Valor_Opcion(
                tc, row["Precio de Ejercicio"], row["Plazo"], row["Tasa Usd"], row["Tasa Cop"],
                row["Volatilidad Ajustada Cubic Funcion"], row["Tipo de opción"]
            )
        ), axis=1
    )
    
    # Factor de Descuento 1
    base_filtro['Factor de Descuento1'] = (
        np.exp((base_filtro['Tasa Val USD Cump'] * base_filtro['Plazo Cumplimiento']) / 365) /
        np.exp((base_filtro['Tasa Usd'] * base_filtro['Plazo']) / 365)
    ).astype(float)
    
    # BS Ajustado
    base_filtro['BS Ajustado'] = (base_filtro['BS'] / base_filtro['Factor de Descuento1']).astype(float)
    
    # Valor Libro
    base_filtro['Valor Libro (CRNCY)'] = base_filtro.apply(
        lambda row: float(
            calculate_valor_libro(
                row['Plazo'], row['Posición en la opción'], row['Moneda Cumplimiento'], 
                row['BS Ajustado'], row['Nominal'], tc
            )
        ), axis=1
    )
    
    # Actualiza base local
    base_local.update(base_filtro)
    
    # Valport final
    valport = float(ValorOPT(base_local, tc))
    
    return valport, base_local


def vega_opc_filtrado_opt(base, tc, curvavol, plazo_inf, plazo_sup):
    base_local = base.copy()
    
    # Tabla de rangos
    tabla_rangos = curvavol[['Plazo Inferior', 'Plazo Superior']].drop_duplicates().reset_index(drop=True)
    
    # Identificar el índice del rango ingresado
    mask_rango = (tabla_rangos['Plazo Inferior'] == plazo_inf) & (tabla_rangos['Plazo Superior'] == plazo_sup)
    idx = tabla_rangos.index[mask_rango][0]
    
    # Determinar rangos a usar
    if idx == 0:
        rangos_a_usar = [idx]  # Solo el primero
    else:
        rangos_a_usar = [idx-1, idx]  # Rango anterior + rango actual
    
    # Construir la máscara para filtrar filas
    mask = pd.Series(False, index=base_local.index)
    for i in rangos_a_usar:
        inf = tabla_rangos.at[i, 'Plazo Inferior']
        sup = tabla_rangos.at[i, 'Plazo Superior']
        mask |= (base_local['Dias Inf SUP'] >= inf) & (base_local['Dias Sup SUP'] <= sup)
    
    base_filtro = base_local.loc[mask].copy()

    # --- A partir de aquí seguir con todos los cálculos como en la versión optimizada ---
    # Columnas a procesar
    columnas = ['10PUT', '25PUT', 'ATM', '25CALL', '10CALL']
    column_mapping = {
        '10PUT': '10 D PUT',
        '25PUT': '25 D PUT',
        'ATM': 'ATM',
        '25CALL': '25 D CALL',
        '10CALL': '10 D CALL'
    }

    for col in columnas:
        col_name = column_mapping[col]
        base_filtro[f'Tasa Inf {col}'] = base_filtro['Dias Inf SUP'].apply(
            lambda x: 0 if x <= 0 else VLookup(x, 'Plazo Inferior', curvavol, col_name, True)
        )
        base_filtro[f'Tasa Sup {col}'] = base_filtro['Dias Sup SUP'].apply(
            lambda x: 0 if x <= 0 else VLookup(x, 'Plazo Inferior', curvavol, col_name, True)
        )
        values = (
            base_filtro[f'Tasa Inf {col}'] +
            (base_filtro[f'Tasa Sup {col}'] - base_filtro[f'Tasa Inf {col}']) *
            ((base_filtro['Plazo'] - base_filtro['Dias Inf SUP']) /
             (base_filtro['Dias Sup SUP'] - base_filtro['Dias Inf SUP']))
        )
        base_filtro[f'Delta_{col}'] = values.where(base_filtro['Plazo'] > 0, other=0)

    # Volatilidad ajustada cubic
    d = [0.1, 0.25, 0.50, 0.75, 0.90]
    Dlta = pd.DataFrame({'Deltas': d})
    sur = base_filtro.loc[:, 'Delta_10PUT':'Delta_10CALL']

    vol_ajustada = []
    for i in base_filtro.index:
        if base_filtro.at[i, "Plazo"] <= 0:
            vol_ajustada.append(0)
        else:
            vol = Volatilidad_cubic(
                tc,
                base_filtro.at[i, 'Precio de Ejercicio'],
                base_filtro.at[i, 'Plazo'],
                base_filtro.at[i, 'Tasa Cop'],
                base_filtro.at[i, 'Tasa Usd'],
                base_filtro.at[i, 'Delta_ATM'],
                Dlta,
                pd.DataFrame(sur.loc[i, :]),
                0,
                100,
                base_filtro.at[i, "Tipo de opción"],
                base_filtro.at[i, "Factor De Descuento"]
            )
            vol_ajustada.append(vol)

    base_filtro['Volatilidad Ajustada Cubic Funcion'] = pd.Series(vol_ajustada, index=base_filtro.index).astype(float)

    # BS y valor ajustado
    base_filtro['BS'] = base_filtro.apply(
        lambda row: Valor_Opcion(
            tc,
            row["Precio de Ejercicio"],
            row["Plazo"],
            row["Tasa Usd"],
            row["Tasa Cop"],
            row["Volatilidad Ajustada Cubic Funcion"],
            row["Tipo de opción"]
        ), axis=1
    )

    base_filtro['BS Ajustado'] = base_filtro['BS'] / base_filtro['Factor de Descuento1']

    base_filtro['Valor Libro (CRNCY)'] = base_filtro.apply(
        lambda row: calculate_valor_libro(
            row['Plazo'],
            row['Posición en la opción'],
            row['Moneda Cumplimiento'],
            row['BS Ajustado'],
            row['Nominal'],
            tc
        ), axis=1
    )

    # Actualizar valores en dataframe original
    base_local.update(base_filtro)
    valport = ValorOPT(base_local, tc)

    return valport, base_local








'OPCIONES'


'FORWARDS'


def ValorPFWDUSD(base):
    flt1={
          'Moneda_Cumplimiento':['USD']
          }
    
    return sumar_si_conjunto(base, 'Valor Forward', flt1) 


def ValorPFWDCOP(base):
    flt1={
          'Moneda_Cumplimiento':['COP']
          }
    
    return sumar_si_conjunto(base, 'Valor Forward', flt1) 

def ValorFWD(base,tc):
   return ValorPFWDCOP(base)+(ValorPFWDUSD(base)*tc)



def sumar_si_conjunto1(base, valor_col, filtro):
    # Aplicar el filtro
    filtro_aplicado = base.query(filtro)
    # Sumar los valores de la columna especificada
    return filtro_aplicado[valor_col].sum()


def ValorPFWDCVAEXT(base):
    
    flt1='Plazo > 0'
           
    return sumar_si_conjunto1(base, 'CVA_Fair_Value_COP_Y', flt1)

def sumar_si_conjunto2(df, suma_col, criterio_col1, criterio1, criterio_col2, criterio2):
    # Filtrar el DataFrame según los criterios
    filtro = (df[criterio_col1] == criterio1) & (df[criterio_col2] <= criterio2)
    # Sumar los valores en la columna de suma
    return df.loc[filtro, suma_col].sum()

def ValorPFWDCVAINT(base):
    flt1={
          'Interno/Externo':['INTERNO']
          }
             
    return sumar_si_conjunto(base, 'Valor_y_cop', flt1) + sumar_si_conjunto2(base, 'Valor_y_cop','Interno/Externo' ,'INTERNO','Plazo',0)

def ValorPFWDCVA(base):
    return ValorPFWDCVAINT(base)+ValorPFWDCVAEXT(base)

def calcular_forwards(base, fecha_parametro):

    # Convertir fecha de vencimiento a datetime
    #base[' Fecha Vencimiento'] = pd.to_datetime(base[' Fecha Vencimiento'])
    fecha_parametro = pd.to_datetime(fecha_parametro)

    # Filtro general: F > fecha
    filtro_fecha = base['Vencimiento'] > fecha_parametro

    # -------------------
    # PARTE 1
    # -------------------
    # SI(K="COP", COP, USD*TasaFix)
    parte1 = base.loc[filtro_fecha].apply(
        lambda row: row['COP'] if row['Moneda_Cumplimiento'] == "COP"
                    else row['USD'] * row['Tasa Fix'],
        axis=1
    ).sum()

    # -------------------
    # PARTE 2
    # -------------------
    # SI(J="DF", USD*TasaFix, 0)
    parte2 = base.loc[filtro_fecha].apply(
        lambda row: row['USD'] * row['Tasa Fix']
                    if row['Modalidad'] == "DF"
                    else 0,
        axis=1
    ).sum()

    # Resultado final
    return parte1 + parte2

def delta_forward_mod(base, tc, tsaf, fecha_ult, ini=None, final=None):
    base_local = base.copy()

    # --- Máscara ---
    if ini is not None and final is not None:
        mask = (base_local['Plazo'] >= ini) & (base_local['Plazo'] < final)
    else:
        mask = pd.Series(True, index=base_local.index)

    # --- Valor Forward solo en las filas filtradas ---
    base_local['Valor Forward'] = 0  # Inicializamos
    base_local.loc[mask, 'Valor Forward'] = base_local.loc[mask].apply(
        lambda row: Vlr_forward(
            row['Plazo'], row['Moneda_Cumplimiento'], row['VP Flujo COP'], row['VP Flujo USD'], tc
        ),
        axis=1
    )

    # --- Tasa Fix solo en la máscara ---
    base_local['Tasa Fix'] = 0
    base_local.loc[mask, 'Tasa Fix'] = base_local.loc[mask].apply(
        lambda row: tfixforr2(row['Plazo'], row['Vencimiento'], tsaf, tc),
        axis=1
    )

    base_local['CXC']=base_local.apply(lambda row: Cuentas_Por_FWD(row['Moneda_Cumplimiento'],row['Vencimiento'],row['Cumplimiento'],fval,row['T.Forward'],row['Nominal'],row['Operación'],0,row['Tasa Fix'],row['Modalidad']),axis=1)

    # --- Valor total del portafolio ---
    valorfor = ValorFWD(base_local, tc)

    #filtro = (base_local['Moneda_Cumplimiento'] == 'USD') & (base_local['Plazo'].isin([-1, -2, -3]))

    # --- CXC solo considerando COP y USD ---
    cxcfor = (
    base_local.loc[(base_local['Vencimiento'] > fecha_ult) & (base_local['Moneda_Cumplimiento'] == 'COP'), 'CXC'].sum()
    + (tc * base_local.loc[base_local['Moneda_Cumplimiento'] == "USD", 'CXC'].sum()) )
    

    
    #filtro2 = (fwd['Moneda_Cumplimiento'] == 'USD') & (fwd['Plazo'].isin([0]))

    #porcumplir = fwd.loc[filtro, 'USD'].sum()+ fwd.loc[filtro2, 'CXC'].sum()

    #fwd.loc[(fwd['Plazo'] == 0) & (fwd['Moneda_Cumplimiento'] == 'USD'), 'CXC'].sum() 

    #Deltafor =  fwd['VP Flujo USD'].sum() + porcumplir

    return valorfor, cxcfor


def rhocop_for_mod(base, tc, curvacop, ini=None, final=None):
    base_local = base.copy()

    # --- Máscara ---
    if ini is not None and final is not None:
        mask = (base_local['Plazo'] >= ini) & (base_local['Plazo'] < final)
    else:
        mask = pd.Series(True, index=base_local.index)

    # --- Tasa COP ---
    # Inicializamos con los valores originales para preservar las filas fuera de la máscara
    if 'Tasa Cop' not in base_local.columns:
        base_local['Tasa Cop'] = 0  # Si no existe, inicializamos con 0

    # Solo recalculamos filas que cumplen la máscara y plazo > 0
    base_local.loc[mask & (base_local['Plazo'] > 0), 'Tasa Cop'] = [
        Interpolacion_Tasa(base_local.at[i, 'Plazo'], curvacop, "COP") 
        for i in base_local.loc[mask & (base_local['Plazo'] > 0)].index
    ]

    # --- VP Flujo COP ---
    # Se recalcula para todas las filas porque depende de 'Tasa Cop'
    base_local['VP Flujo COP'] = base_local.apply(
        lambda row: VP_FLUJO_COP(row['T.Forward'], row['Nominal'], row['Plazo'], row['Tasa Cop'], row['Operación']),
        axis=1
    )

    # --- Valor Forward ---
    # Se calcula para todas las filas
    base_local['Valor Forward'] = base_local.apply(
        lambda row: Vlr_forward(row['Plazo'], row['Moneda_Cumplimiento'], row['VP Flujo COP'], row['VP Flujo USD'], tc),
        axis=1
    )

    # --- Valor total del portafolio ---
    valorfor = ValorFWD(base_local, tc)

    return valorfor


def rhousd_for_mod(base, tc, curvausd, ini=None, final=None):
    base_local = base.copy()

    # --- Máscara ---
    if ini is not None and final is not None:
        mask = (base_local['Plazo'] >= ini) & (base_local['Plazo'] < final)
    else:
        mask = pd.Series(True, index=base_local.index)

    # --- Tasa USD ---
    if 'Tasa Usd' not in base_local.columns:
        base_local['Tasa Usd'] = 0  # Inicializamos si no existe

    # Solo recalculamos filas que cumplen la máscara y plazo > 0
    base_local.loc[mask & (base_local['Plazo'] > 0), 'Tasa Usd'] = [
        Interpolacion_Tasa(base_local.at[i, 'Plazo'], curvausd, 'USD')
        for i in base_local.loc[mask & (base_local['Plazo'] > 0)].index
    ]

    # --- VP Flujo USD ---
    # Se recalcula para todas las filas porque depende de 'Tasa Usd'
    base_local['VP Flujo USD'] = base_local.apply(
        lambda row: VP_FLUJO_USD(row['T.Forward'], row['Nominal'], row['Plazo'], row['Tasa Usd'], row['Operación']),
        axis=1
    )

    # --- Valor Forward ---
    # Se calcula para todas las filas
    base_local['Valor Forward'] = base_local.apply(
        lambda row: Vlr_forward(row['Plazo'], row['Moneda_Cumplimiento'], row['VP Flujo COP'], row['VP Flujo USD'], tc),
        axis=1
    )

    # --- Valor total del portafolio ---
    valorfor = ValorFWD(base_local, tc)

    return valorfor


    
'FORWARDS'


'NOVADOS'

def VENNOV(base):
    condicion = (base['Posición_USD'] == 0) | (base['Posición_USD'] == "")
    
    return base.loc[condicion, 'MTM(ACUMULADO)'].sum()    


'NOVADOS'


'CAJA'

def CAJAUSD(fecha):
    Historia_caja['Fecha'] = pd.to_datetime(Historia_caja['Fecha'])
    fecha = pd.to_datetime(fecha)
    fila = Historia_caja.loc[Historia_caja['Fecha'] == fecha]
    n=fila.index[0]
    return Historia_caja['Caja_Usd'][n]

def CAJACOP(fecha):
    Historia_caja['Fecha'] = pd.to_datetime(Historia_caja['Fecha'])
    fila = Historia_caja.loc[Historia_caja['Fecha'] == fecha]
    n=fila.index[0]
    return Historia_caja['Caja_Cop'][n]

def CAJATOTAL(fecha,tc):
    return CAJACOP(fecha)+(CAJAUSD(fecha)*tc)

'CAJA'


'//////////////////////////////////////////// funciónes cálculo PYG////////////////////////////////////////////////////////////////////////'
#import subprocess
#import sys
#archivo = r"D:\Librerias\pyxlsb-1.0.10-py2.py3-none-any.whl"
#subprocess.run([sys.executable, "-m", "pip", "install", archivo])

'/////////////////////////////////////////// INSUMOS ////////////////////////////////////////////////////////////////////////'


#df = pd.read_excel('archivo.xlsb', engine='pyxlsb', sheet_name='Hoja1')
# ws = xw.Book(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\ENTRADA2.xlsb")
# ws.save(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\ENTRADA2.xlsx")
# ws.close()

'Tasas dolar'

tusd=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="INFOVALMER", skiprows=2, nrows=18, usecols='A:C')
tusd=tusd.drop(17)
new_col=[tusd.iat[1,1],tusd.iat[2,1],tusd.iat[3,1],tusd.iat[4,1],tusd.iat[5,1],tusd.iat[6,1],tusd.iat[7,1],tusd.iat[8,1],tusd.iat[9,1],tusd.iat[10,1],tusd.iat[11,1],tusd.iat[12,1],tusd.iat[13,1],tusd.iat[14,1],tusd.iat[15,1],tusd.iat[16,1],tusd.iat[16,1]]
tusd.insert(loc=2, column='Plazo Superior', value=new_col)
tusd.columns=['Plazo','Plazo Inferior','Plazo Superior','Tasas USD']

'Tasas pesos'

tcop=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="INFOVALMER", skiprows=2, nrows=13, usecols='E:G')
new_col=[tcop.iat[1,1],tcop.iat[2,1],tcop.iat[3,1],tcop.iat[4,1],tcop.iat[5,1],tcop.iat[6,1],tcop.iat[7,1],tcop.iat[8,1],tcop.iat[9,1],tcop.iat[10,1],tcop.iat[11,1],tcop.iat[12,1],tcop.iat[12,1]]
tcop.insert(loc=2, column='Plazo Superior', value=new_col)
tcop.columns=['Plazo','Plazo Inferior','Plazo Superior','Tasas COP']

'superficie volatilidad'

surf=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="INFOVALMER", skiprows=2, nrows=18, usecols='I:N')
new_col=[surf.iat[1,0],surf.iat[2,0],surf.iat[3,0],surf.iat[4,0],surf.iat[5,0],surf.iat[6,0],surf.iat[7,0],surf.iat[8,0],surf.iat[9,0],surf.iat[10,0],surf.iat[11,0],surf.iat[12,0],surf.iat[13,0],surf.iat[14,0],surf.iat[15,0],surf.iat[16,0],surf.iat[16,0],0]
surf.insert(loc=1, column='Plazo Superior', value=new_col)
surf.columns=['Plazo Inferior','Plazo Superior','10 D PUT', '25 D PUT', 'ATM', '25 D CALL', '10 D CALL']
surf=surf.drop(17)

surf.iat[0,0]

#import win32com.client as win32
#fname = r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_OPT_MANANA_190624_000.xls"
#excel = win32.gencache.EnsureDispatch('Excel.Application')
#wb = excel.Workbooks.Open(fname)
#wb.SaveAs(fname+"x", FileFormat = 51)    #FileFormat = 51 is for .xlsx extension
#wb.Close()                               #FileFormat = 56 is for .xls extension
#excel.Application.Quit()


'/////////////////////////////////////////// INSUMOS ////////////////////////////////////////////////////////////////////////'

'Convertir el insumo de xls a xlsx para poder abrirlo con PANDAS'
'Este paso se podría omitir si estuviera disponible la librería xlrd'

'/////////////////////////////////////////// OPCIONES DIA ////////////////////////////////////////////////////////////////////////'

#ws = xw.Book(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_OPT_MANANA_" + Dia + Mes + Año1 + "_000.xls")
#ws.save(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_OPT_MANANA_" + Dia + Mes + Año1 + "_000.xlsx")
#ws.close()
'Cerrar la aplicación de Excel'

'Se realiza texto en columnas para el DF del insumo'

opc=pd.read_csv(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_MANANA_" + Dia + Mes + Año1 + "_000.xls", sep='\t', engine='python', encoding='latin-1')
max_pyc = opc['BANCO DE BOGOTÁ'].str.split(';').transform(len).max()
opc[[f'BANCO DE BOGOTÁ_{x}' for x in range(max_pyc)]]=opc['BANCO DE BOGOTÁ'].str.split(';', expand=True)
opc=opc.drop(opc.columns[0], axis=1)

opc=opc.drop([0,1,2])
opc.reset_index(inplace=True,drop=True)
nm=opc.loc[0,:].values.tolist()
opc=opc.set_axis(nm, axis=1)
opc=opc.drop(0)
opc.reset_index(inplace=True,drop=True)
opc.columns = opc.columns.str.strip()


# eliminar columnas
opc = opc.drop(columns=[
    opc.columns[4], opc.columns[5], opc.columns[13],
    'Folder', 'Deal ID',
    'Información Tributaria', 'Comentarios'
])

# mover columnas a posiciones específicas
def mover_col(df, col, pos):
    serie = df.pop(col)
    df.insert(pos, col, serie)

mover_col(opc, 'Modalidad Cumplimiento', 14)
mover_col(opc, 'Moneda cumplimiento', 15)
mover_col(opc, 'Tipo Estructura', 30)
mover_col(opc, 'Volatilidad', 32)

# convertir fechas
cols = ['Fecha de Emisión','Fecha de Vencimiento','Fecha de Cumplimiento']
opc[cols] = opc[cols].apply(pd.to_datetime, dayfirst=True)

# ordenar
opc = opc.sort_values('Fecha de Vencimiento').reset_index(drop=True)


opc.rename(columns={"Delta": "Delta 1"}, inplace=True)

opc["Moneda Cumplimiento"] = np.where(
    opc["Identificación contraparte"].str[:4] == "4444",
    "USD",
    "COP"
)

opc["Plazo"] = (opc["Fecha de Vencimiento"] - fval).dt.days


opc["Tasa Cop"] = opc["Plazo"].apply(
    lambda p: 0 if p <= 0 else Interpolacion_Tasa(p, tcop, "COP")
)


opc["Tasa Usd"] = opc["Plazo"].apply(
    lambda p: 0 if p <= 0 else Interpolacion_Tasa(p, tusd, "USD")
)


opc["Volatilidad1"] = opc.apply(
    lambda r: Zigma_Option(
        trm,
        float(r["Precio de Ejercicio"]),
        surf,
        r["Tasa Cop"],
        r["Tasa Usd"],
        r["Plazo"]
    ),
    axis=1
)
 

opc["Plazo Cumplimiento"] = (
    opc["Plazo"] +
    (opc["Fecha de Cumplimiento"] - opc["Fecha de Vencimiento"]).dt.days
)



opc["Dias inf USD"] = np.where(
    opc["Plazo"] <= 0,
    0,
    opc["Plazo Cumplimiento"].apply(
        lambda x: VLookup(x, 'Plazo Inferior', tusd, 'Plazo Inferior', True)
    )
)



opc["Dias Sup USD"] = np.where(
    opc["Plazo"] <= 0,
    0,
    opc["Plazo Cumplimiento"].apply(
        lambda x: VLookup(x, 'Plazo Inferior', tusd, 'Plazo Superior', True)
    )
)



opc["Tasa Inf USD"] = np.where(
    opc["Plazo Cumplimiento"] <= 0,
    0,
    opc["Dias inf USD"].apply(
        lambda x: VLookup(x, "Plazo Inferior", tusd, "Tasas USD", True)
    )
)


opc["Tasa Sup USD"] = np.where(
    opc["Plazo Cumplimiento"] <= 0,
    0,
    opc["Dias Sup USD"].apply(
        lambda x: VLookup(x, "Plazo Inferior", tusd, "Tasas USD", True)
    )
)
 



opc["Tasa Val USD Cump"] = np.where(
    opc["Plazo Cumplimiento"] <= 0,
    0,
    opc["Tasa Inf USD"] +
    (opc["Tasa Sup USD"] - opc["Tasa Inf USD"]) *
    ((opc["Plazo"] - opc["Dias inf USD"]) /
     (opc["Dias Sup USD"] - opc["Dias inf USD"]))
)




opc['Factor De Descuento'] = (np.exp((opc['Tasa Val USD Cump'] * opc['Plazo Cumplimiento'])/365))/(np.exp((opc['Tasa Usd']*opc['Plazo'])/365))



opc["Dias Inf SUP"] = np.where(
    opc["Plazo"] <= 0,
    0,
    opc["Plazo"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "Plazo Inferior", True)
    )
)

opc["Dias Sup SUP"] = np.where(
    opc["Plazo"] <= 0,
    0,
    opc["Plazo"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "Plazo Superior", True)
    )
)


opc["Tasa Inf 10PUT"] = np.where(
    opc["Dias Inf SUP"] <= 0,
    0,
    opc["Dias Inf SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "10 D PUT", True)
    )
)


opc["Tasa Sup 10PUT"] = np.where(
    opc["Dias Sup SUP"] <= 0,
    0,
    opc["Dias Sup SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "10 D PUT", True)
    )
)


values = (opc['Tasa Inf 10PUT']+(opc['Tasa Sup 10PUT']-opc['Tasa Inf 10PUT'])*((opc['Plazo']-opc['Dias Inf SUP'])/(opc['Dias Sup SUP']-opc['Dias Inf SUP'])))
opc['Delta_10PUT'] = values.where(opc.Plazo > 0, other=0)



opc["Tasa Inf 25PUT"] = np.where(
    opc["Dias Inf SUP"] <= 0,
    0,
    opc["Dias Inf SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "25 D PUT", True)
    )
)


opc["Tasa Sup 25PUT"] = np.where(
    opc["Dias Sup SUP"] <= 0,
    0,
    opc["Dias Sup SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "25 D PUT", True)
    )
)

values = (opc['Tasa Inf 25PUT']+(opc['Tasa Sup 25PUT']-opc['Tasa Inf 25PUT'])*((opc['Plazo']-opc['Dias Inf SUP'])/(opc['Dias Sup SUP']-opc['Dias Inf SUP'])))
opc['Delta_25PUT'] = values.where(opc.Plazo > 0, other=0)

opc["Tasa Inf ATM"] = np.where(
    opc["Dias Inf SUP"] <= 0,
    0,
    opc["Dias Inf SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "ATM", True)
    )
)

# Tasa Superior ATM
opc["Tasa Sup ATM"] = np.where(
    opc["Dias Sup SUP"] <= 0,
    0,
    opc["Dias Sup SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "ATM", True)
    )
)

values = (opc['Tasa Inf ATM']+(opc['Tasa Sup ATM']-opc['Tasa Inf ATM'])*((opc['Plazo']-opc['Dias Inf SUP'])/(opc['Dias Sup SUP']-opc['Dias Inf SUP'])))
opc['Delta_ATM'] = values.where(opc.Plazo > 0, other=0)

# Tasa Inferior 25CALL
opc["Tasa Inf 25CALL"] = np.where(
    opc["Dias Inf SUP"] <= 0,
    0,
    opc["Dias Inf SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "25 D CALL", True)
    )
)

# Tasa Superior 25CALL
opc["Tasa Sup 25CALL"] = np.where(
    opc["Dias Sup SUP"] <= 0,
    0,
    opc["Dias Sup SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "25 D CALL", True)
    )
)

values = (opc['Tasa Inf 25CALL']+(opc['Tasa Sup 25CALL']-opc['Tasa Inf 25CALL'])*((opc['Plazo']-opc['Dias Inf SUP'])/(opc['Dias Sup SUP']-opc['Dias Inf SUP'])))
opc['Delta_25CALL'] = values.where(opc.Plazo > 0, other=0)

opc["Tasa Inf 10CALL"] = np.where(
    opc["Dias Inf SUP"] <= 0,
    0,
    opc["Dias Inf SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "10 D CALL", True)
    )
)

opc["Tasa Sup 10CALL"] = np.where(
    opc["Dias Sup SUP"] <= 0,
    0,
    opc["Dias Sup SUP"].apply(
        lambda x: VLookup(x, "Plazo Inferior", surf, "10 D CALL", True)
    )
)


values = (opc['Tasa Inf 10CALL']+(opc['Tasa Sup 10CALL']-opc['Tasa Inf 10CALL'])*((opc['Plazo']-opc['Dias Inf SUP'])/(opc['Dias Sup SUP']-opc['Dias Inf SUP'])))
opc['Delta_10CALL'] = values.where(opc.Plazo > 0, other=0)



 
d= [0.1,0.25,0.50,0.75,0.90]  
Dlta=pd.DataFrame({'Deltas':d})
sur=opc.loc[:, 'Delta_10PUT':'Delta_10CALL']



opc[['Precio de Ejercicio']] = opc[['Precio de Ejercicio']].apply(pd.to_numeric)


opc["Volatilidad Ajustada Cubic Funcion"] = opc.apply(
    lambda row: 0 if row["Plazo"] <= 0 else Volatilidad_cubic(
        trm,
        row['Precio de Ejercicio'],
        row["Plazo"],
        row["Tasa Cop"],
        row["Tasa Usd"],
        row["Delta_ATM"],
        Dlta,
        pd.DataFrame(sur.loc[row.name, :]),
        0,
        100,
        row["Tipo de opción"],
        row["Factor De Descuento"]
    ),
    axis=1
)

# Convertir a float
opc["Volatilidad Ajustada Cubic Funcion"] = opc["Volatilidad Ajustada Cubic Funcion"].astype(float)
opc["Volatilidad"] = opc["Volatilidad"].astype(float)


opc['Diferencia Vana-Volga']=(opc['Volatilidad Ajustada Cubic Funcion']-opc['Volatilidad1'])

opc["BS"] = opc.apply(
    lambda row: Valor_Opcion(
        trm,
        row["Precio de Ejercicio"],
        row["Plazo"],
        row["Tasa Usd"],
        row["Tasa Cop"],
        row["Volatilidad Ajustada Cubic Funcion"],
        row["Tipo de opción"]
    ),
    axis=1
)  


opc['Factor de Descuento1']=np.exp((opc['Tasa Val USD Cump']*opc['Plazo Cumplimiento'])/365)/np.exp((opc['Tasa Usd']*opc['Plazo'])/365)
opc['BS Ajustado']=opc['BS']/opc['Factor de Descuento1']

opc[['Nominal']] = opc[['Nominal']].apply(pd.to_numeric)
opc['Valor Libro (CRNCY)'] = opc.apply(lambda row: calculate_valor_libro(row['Plazo'],
                                                                                                    row['Posición en la opción'],
                                                                                                    row['Moneda Cumplimiento'],
                                                                                                    row['BS Ajustado'],
                                                                                                    row['Nominal'],
                                                                                                    trm), axis=1)

tfd=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="BASE", skiprows=1, nrows=43, usecols='A')
new=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="BASE", skiprows=1, nrows=43, usecols='E')
tfd['TRM']=new
del new

tfd['FECHA'] = pd.to_datetime('1899-12-30') + pd.to_timedelta(tfd['FECHA'], unit='D')

L=[]
for i in range(len(tfd)):
    lastBusinessDay = tfd.iat[i,0]
    shift = lastBusinessDay + BDay(1)
    L.append(shift)
FCH = pd.DataFrame({'FECHAH':L})
tfd['FECHAH']=FCH
tfd=tfd.drop([41, 42])

if fval.month == 1:
    mes_anterior = 12
    año_anterior = fval.year - 1
else:
    mes_anterior = fval.month - 1
    año_anterior = fval.year

# Último día del mes anterior
ultimo_dia = calendar.monthrange(año_anterior, mes_anterior)[1]

# Crear la fecha
ultimo_dia_mes_anterior = datetime(año_anterior, mes_anterior, ultimo_dia)

# Convertir a string en formato "yyyymmdd"
mesu = ultimo_dia_mes_anterior.strftime("%Y%m%d")



tfd['FECHA']=tfd['FECHA'].dt.strftime("%Y%m%d").astype(int)
tfd['FECHAH']=tfd['FECHAH'].dt.strftime("%Y%m%d").astype(int)

dict = {'FECHA':[mesu],
        'TRM':[tfd.iat[0,1]],
        'FECHAH':[tfd.iat[0,0]]}

r1=pd.DataFrame(dict)
tfd = r1._append(tfd, ignore_index = True)

tfd= tfd[tfd['FECHA'] != 0]
tfd = tfd.reset_index(drop=True)



tfd["TRM1"] = tfd["FECHAH"].apply(lambda x: VLookup(x, "FECHA", tfd, "TRM"))


tfd["TRM1"] = tfd["TRM1"].replace(0.0, np.nan).ffill().fillna(0)


tfd.loc[0, "FECHA"] = int(tfd.loc[0, "FECHA"])  # convertir primera fila a int
tfd.loc[1, "FECHA"] = 0  # asignar 0 a segunda fila
tfd["FECHA"] = tfd["FECHA"].where(~tfd["FECHA"].duplicated(), 0)  # duplicados a 0


tfd = tfd[tfd["FECHA"] != 0].reset_index(drop=True)

opc['Fecha de Vencimiento'] = pd.to_datetime(opc['Fecha de Vencimiento'], errors='coerce')
opc['Fecha de Vencimiento']=opc['Fecha de Vencimiento'].dt.strftime("%Y%m%d").astype(int)






    
opc['Tasa Fix'] = opc.apply(lambda row: tfix(row['Plazo'],
                                                                                                    row['Fecha de Vencimiento'],
                                                                                                    tfd,
                                                                                                    mesu,
                                                                                                    trm), axis=1)    





opc['Fecha de Vencimiento'] = opc['Fecha de Vencimiento'].apply(lambda x: pd.to_datetime(str(x), format='%Y%m%d'))   
ff =  int(fval.strftime("%Y%m%d"))    

opc['Cuentas por Cumplir'] = opc.apply(lambda row: Cuentas_Por_opc(row['Moneda cumplimiento'],
                                                                                                row['Fecha de Vencimiento'],
                                                                                                row['Fecha de Cumplimiento'],
                                                                                                fval, # Fecha de valoracion, validar si esta cambia
                                                                                                row['Tipo de opción'],
                                                                                                row['Precio de Ejercicio'],
                                                                                                row['Nominal'],
                                                                                      row['Posición en la opción'],
                                                                                                0, # ingresar FRA si se necesita
                                                                                                row['Tasa Fix'], #tasa fix
                                                                                                row['Modalidad Cumplimiento']), axis=1)




opc['USD'] = opc.apply(lambda row: Vencimiento("USD",
                                                                                                row['Moneda cumplimiento'],#ok
                                                                                                row['Modalidad Cumplimiento'],#ok,
                                                                                                row['Fecha de Vencimiento'], #ok 
                                                                                                fval,
                                                                                                row['Tipo de opción'],#ok
                                                                                      row['Precio de Ejercicio'],#ok
                                                                                                row['Nominal'], #ok
                                                                                                row['Posición en la opción'], #ok
                                                                                                row['Tasa Fix'], 
                                                                                                row['Fecha de Cumplimiento']),axis=1)
                                                                                                

opc['COP'] = opc.apply(lambda row: Vencimiento("COP",
                                                                                                row['Moneda cumplimiento'],#ok
                                                                                                row['Modalidad Cumplimiento'],#ok,
                                                                                                row['Fecha de Vencimiento'], #ok 
                                                                                                fval,
                                                                                                row['Tipo de opción'],#ok
                                                                                      row['Precio de Ejercicio'],#ok
                                                                                                row['Nominal'], #ok
                                                                                                row['Posición en la opción'], #ok
                                                                                                row['Tasa Fix'], 
                                                                                                row['Fecha de Cumplimiento']),axis=1)




sign_nominal = lambda operacion, nominal: -nominal if operacion=="SELL" else nominal
opc['Delta'] = opc.apply(lambda row: delta_opcion(fval,
                                                                               row['Fecha de Vencimiento'],
                                                                               trm,
                                                                               row['Precio de Ejercicio'],
                                                                               row['Tasa Cop'],
                                                                               row['Tasa Usd'],
                                                                               row['Volatilidad Ajustada Cubic Funcion'],
                                                                               row['Tipo de opción']) * sign_nominal(row['Posición en la opción'], row['Nominal'])
                                                                               if row['Fecha de Vencimiento'] != fval else 0, axis=1)



opc["Estructura"] = np.where(opc.iloc[:, 1] == "", "N", "EV")

opc['Fee']=opc['Fee'].apply(pd.to_numeric)
opc['Fecha Fee']=pd.to_datetime(opc['Fecha Fee'],dayfirst=True)
opc['Fee'].fillna(0, inplace=True)
opc['Fecha Fee'].fillna(0, inplace=True)
opc['Valor Total Prima']=opc['Valor Total Prima'].apply(pd.to_numeric)
opc['Valor Total Prima'].fillna(0, inplace=True)

for i in range(len(opc)):
    if opc['Moneda cumplimiento'][i] == "":
        opc['Moneda cumplimiento'][i] = opc['Moneda de la  Prima'][i]

opc[['Value Amount']] = opc[['Value Amount']].apply(pd.to_numeric)    
opc['DifValSINCVA'] = opc.apply(lambda row: difvalsinCVA(row['Trade Id'],
                                                                               row['Moneda cumplimiento'],
                                                                               row['Valor Libro (CRNCY)'],
                                                                               trm,
                                                                               row['Value Amount']), axis=1)        
        
opc[['CVA Fair Value COP']] = opc[['CVA Fair Value COP']].apply(pd.to_numeric)      
opc['DifValCONCVA'] = opc.apply(lambda row: difvalconCVA(row['Trade Id'],
                                                                               row['Plazo'],
                                                                               row['CVA Fair Value COP'],
                                                                               row['Value Amount']), axis=1)        
 

opc[['Spread CVA']] = opc[['Spread CVA']].apply(pd.to_numeric)          
opc['BS_CVA'] = opc.apply(lambda row: calcular_BS_CVA(row['Trade Id'],
                                                                               row['Spread CVA'],
                                                                               row['BS Ajustado'],
                                                                               row['Plazo']), axis=1)     

        
opc['ValorLibroCVA'] = opc.apply(lambda row: ValorLibroCVA(row['Plazo'],
                                                                               row['Posición en la opción'],
                                                                               row['Moneda cumplimiento'],
                                                                               row['BS_CVA'],
                                                                               row['Nominal'],
                                                                               trm), axis=1)          
        
opc['DifrevCVA'] = opc.apply(lambda row: DifrevCVA(row['Trade Id'],
                                                                               row['Plazo'],
                                                                               row['ValorLibroCVA'],
                                                                               row['CVA Fair Value COP']), axis=1)     

    
        
opc['DifporCVA'] = opc.apply(lambda row: DifporCVA(row['Trade Id'],
                                                                               row['Plazo'],
                                                                               row['Moneda cumplimiento'],
                                                                               row['ValorLibroCVA'],
                                                                               row['Valor Libro (CRNCY)'],trm), axis=1)   

# opc.columns

#opc['Nominal'].sum()
#opc['Plazo'].sum()
#opc['Valor Libro (CRNCY)'].sum()
# opc['Delta'].sum()

'FULL TERMINATIONN'

entrada = input("FULL TERMINATION VIGENTES(SI/NO): ")
if entrada =="SI":
    operaciones=['2270659CO','2270662CO','2270665CO','2274526CO','2274529CO','2274532CO']
    for operacion in operaciones:
        print(operacion)
        valor_buscado = operacion
        fila = opc.loc[opc['Trade Id'] == valor_buscado]
        opc['Cuentas por Cumplir'][fila.index[0]]=0
        opc['USD'][fila.index[0]]=0
        opc['COP'][fila.index[0]]=0
        opc['Delta'][fila.index[0]]=0
    print("Verifique valoración")   
else:
    print("Continue con el proceso")        
    
valportnuevo= ValorOPT(opc,trm)
valportcvanuevo =ValorOPTCVA(opc,trm)
Nuevosprodopc = opc.loc[opc['Fecha de Emisión'] == fval, ['Valor Total Prima', 'Valor Libro (CRNCY)']].sum().sum()
Deltaopc = opc['Delta'].sum()
cxcopc= opc['Cuentas por Cumplir'].sum() 

fecha_ult = datetime.strptime(mesu, "%Y%m%d")
venciput=Vencimientosopc(opc, 'PUT', fecha_ult)
primasput=calcular_primas(opc, 'PUT', fecha_ult)
vencicall=Vencimientosopc(opc, 'CALL', fecha_ult)
primascall=calcular_primas(opc, 'CALL', fecha_ult)

cxcopc1 =   opc.loc[
        (opc['Fecha de Vencimiento'] > fecha_ult) & (opc['Moneda cumplimiento'] == 'COP'), 
        'Cuentas por Cumplir'
    ].sum() + (trm *
                opc.loc[opc['Moneda cumplimiento'] == "USD", 'Cuentas por Cumplir']).sum()
              
               
cxcus =   (opc.loc[opc['Moneda cumplimiento'] == "USD", 'Cuentas por Cumplir']).sum()             

vencitot= venciput+vencicall
primastot=primasput+primascall

cajaopc=vencitot+primastot

valoropcgriega=valportnuevo+cxcopc+cajaopc

opccva= opc.loc[(opc['Moneda cumplimiento'] == 'COP'), 
        'ValorLibroCVA'].sum() + (trm * opc.loc[opc['Moneda cumplimiento'] == "USD", 'ValorLibroCVA']).sum()



        
'/////////////////////////////////////////// OPCIONES DIA ////////////////////////////////////////////////////////////////////////'


'///////////////////////////////////////////// CARGUE FORWARDS /////////////////////////////////////////////////////'


#ws = xw.Book(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_OPT_FWD_" + Dia + Mes + Año + "_000.xls")
#ws.save(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_OPT_FWD_" + Dia + Mes + Año + "_000.xlsx")
#ws.close()


#opc=pd.read_csv(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_MANANA_" + Dia + Mes + Año1 + "_000.xls", sep='\t', engine='python', encoding='latin-1')

fwd=pd.read_csv(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_FWD_" + Dia + Mes + Año + "_000.xls", sep='\t', engine='python', encoding='latin-1')
fwd.columns=['BANCO DE BOGOTA']
max_pyc = fwd['BANCO DE BOGOTA'].str.split(';').transform(len).max()
fwd[[f'BANCO DE BOGOTA_{x}' for x in range(max_pyc)]]=fwd['BANCO DE BOGOTA'].str.split(';', expand=True)
fwd=fwd.drop(fwd.columns[0], axis=1)
nm=fwd.iloc[4].values.tolist()
fwd=fwd.drop([0,1,2,3,4])
fwd.columns=nm
fwd = fwd.iloc[:,:-1]
fwd=fwd.reset_index(drop=True)
del nm


new=['TRADE ID',
 'NIT CONTRAPARTE',
 'CONTRAPARTE',
 'BUY/SELL',
 'F_APER',
 'F_VCTO',
 'F_CUMPTO',
 'MONTO VENTA',
 'TS FWD',
 'MODALIDAD',
 'CCY SETTLEMENT',
 'VALOR Y COP',
 'VALOR X COP',
 'VP Sett Ccy X',
 'VP Sett Ccy Y',
 'P&G Diario',
 'VALOR LIQ',
 'INTERNO/EXTERNO',
 'BOOK',
 'CUSTOMER GROUP',
 'NETTING (ISDA)',
 'SEGMENTO COMERCIAL',
 'CUSTOMERRATING',
 'ACTIVO/PASIVO',
 'CVA CURVE',
 'SPREAD CVA Y',
 'CVA FAIR VALUE COP Y',
 'DIFERENCIA CVA COP Y',
 'PAR MONEDAS',
 'COMPANY',
 'FOLDER',
 'FINALIDAD',
 'MONTO COMPRA',
 'CCY COMPRA',
 'CCY VENTA',
 'SPOT RATE TD',
 'RESET RATE',
 'RESET RATE 3RA',
 'F_INICIO_TO',
 'RESET DATE 2',
 'DIAS_VCTO_Y',
 'DIAS_CTO_Y',
 'SPOT DAYS Y',
 'SPOT DAYS Y 3RA.',
 'TS_CC_Y_T+K_BUY',
 'TS_CC_Y_T+K_SELL',
 'TS_CC_Y_T+K_3RA',
 'TS_CC_Y_BUY_VCTO',
 'TS_CC_Y_SELL_VCTO',
 'TS_CC_Y_SETT_VCTO',
 'TS_CC_Y_SETT_CTO',
 'DIAS_VCTO_X',
 'DIAS_CTO_X',
 'SPOT DAYS X',
 'SPOT DAYS X 3RA.',
 'TS_CC_X_T+K_BUY',
 'TS_CC_X_T+K_SELL',
 'TS_CC_X T+K 3RA',
 'TS CC_X BUY VCTO',
 'TS CC_X SELL VCTO',
 'TS CC_X SETT VCTO',
 'TS CC_X SETT CTO',
 'VP Y CCY SELL',
 'VP Y CCY BUY',
 'VP Y USD SELL',
 'VP Y USD BUY',
 'VP Y COP SELL',
 'VP Y COP BUY',
 'VP X CCY SELL',
 'VP X CCY BUY',
 'VP X USD SELL',
 'VP X USD BUY',
 'VP X COP SELL',
 'VP X COP BUY',
 'TO PT/FT',
 'SPOT RATE Y',
 'SPOT RATE Y 3RA',
 'SPOT RATE X',
 'SPOT RATE X 3RA',
 'VALOR ACC Y COP',
 'VALOR ACC X COP',
 'P&G DIARIO ACC',
 'PATRIMONIO X',
 'PATRIMONIO Y',
 'NETO PATRIMONIO',
 'CORPORATE ID',
 'LINK ID',
 'TERM DATE',
 'SPREAD CVA X',
 'TASA DESCUENTO COP X',
 'FUTURE VALUE COP DER X',
 'FUTURE VALUE COP OBLI X',
 'CVA FAIR VALUE COP X',
 'DIFERENCIA CVA COP X',
 'TASA DESCUENTO COP Y',
 'FUTURE VALUE COP DER Y',
 'FUTURE VALUE COP OBLI Y',
 'NIVEL',
 'Delta Full Valuation \xa0 1 USD',
 'VALOR SENSIBLE',
 'VLR SENSIBLE - \xa0 NOMINAL',
 'VLR SENSIBLE - \xa0 NOMINAL USD',
 'COMPONENTE CAMBIARIO',
 'ACUM. COMPONENTE \xa0 CAMBIARIO',
 'COMP. CAMBIARIO \xa0 CIERRE AÑO ANTERIOR',
 'VLR. COMP. CAMBIARIO \xa0 AÑO FISCAL']

fwd = fwd[new]

L=[]
for i in range(len(fwd)):
    if fwd['BUY/SELL'][i] == "VENTA":
        k= fwd['MONTO VENTA'][i]
    else:
        k= fwd['MONTO COMPRA'][i]
    L.append(k)
nom = pd.DataFrame({'Nominal':L})

fwd['MONTO VENTA']=nom
del nom

    
    
fwd.drop(fwd.iloc[:, fwd.columns.get_loc('PAR MONEDAS'):], inplace=True, axis=1)
del new



rn=['ID', 'NIT', 'Contraparte', 'Operación', 'Emisión',
       'Vencimiento', 'Cumplimiento', 'Nominal', 'T.Forward', 'Modalidad', 'Moneda_Cumplimiento',
       'Valor_y_cop', 'Valor_x_cop', 'VP_Sett_Ccy_X', 'VP_Sett_Ccy_Y',
       'P&G_Diario', 'Valor_Liq', 'Interno/Externo', 'Book', 'Customer_Group',
       'Netting_(ISDA)', 'Segmento_Comercial', 'Customerrating',
       'Activo/Pasivo', 'CVA_curve', 'Spread_Cva_Y', 'CVA_Fair_Value_COP_Y',
       'Diferencia_CVA_COP_Y']
fwd.columns = rn
del rn

fwd['Valor_Liq']=fwd['VP_Sett_Ccy_Y']
fwd['Emisión']=pd.to_datetime(fwd['Emisión'],dayfirst=True)
fwd['Vencimiento']=pd.to_datetime(fwd['Vencimiento'],dayfirst=True)
fwd['Cumplimiento']=pd.to_datetime(fwd['Cumplimiento'],dayfirst=True)
fwd['Nominal']=fwd['Nominal'].apply(convert_to_float)
fwd['T.Forward']=fwd['T.Forward'].apply(convert_to_float)
fwd['Valor_y_cop']=fwd['Valor_y_cop'].apply(convert_to_float)
fwd['Valor_x_cop']=fwd['Valor_x_cop'].apply(convert_to_float)
fwd['VP_Sett_Ccy_X']=fwd['VP_Sett_Ccy_X'].apply(convert_to_float)
fwd['VP_Sett_Ccy_Y']=fwd['VP_Sett_Ccy_Y'].apply(convert_to_float)
fwd['P&G_Diario']=fwd['P&G_Diario'].apply(convert_to_float)
fwd['Valor_Liq']=fwd['Valor_Liq'].apply(convert_to_float)
fwd[['Spread_Cva_Y']]=fwd[['Spread_Cva_Y']].apply(pd.to_numeric)
fwd.sort_values(by='Vencimiento', inplace=True)
fwd.reset_index(inplace=True,drop=True)
fwd['Plazo']=((fwd['Vencimiento']-fval)/ np.timedelta64(1, 'D')).astype(int)
fwd['CVA_Fair_Value_COP_Y'] = fwd['CVA_Fair_Value_COP_Y'].apply(
    lambda x: float(str(x).replace(',', '')) 
    if pd.notnull(x) and str(x).strip() != '' else None
)



L=[]
for i in range(len(fwd)):
    if fwd['Plazo'][i] <= 0:
        k=0
    else:    
        k=Interpolacion_Tasa(fwd['Plazo'][i], tcop, "COP")
        #k= float("".join([str(x) for x in k]))
    L.append(k)
Tcop = pd.DataFrame({'Tasa Cop':L})
fwd = pd.concat([fwd,Tcop], axis=1) 
del Tcop

L=[]
for i in range(len(fwd)):
    if fwd['Plazo'][i] <= 0:
        k=0
    else:  
        k=Interpolacion_Tasa(fwd['Plazo'][i], tusd, 'USD')
        #k= float("".join([str(x) for x in k]))
    L.append(k)
Tusd = pd.DataFrame({'Tasa Usd':L})
fwd = pd.concat([fwd,Tusd], axis=1)
del Tusd

    
fwd['VP Flujo COP']=fwd.apply(lambda row: VP_FLUJO_COP(row['T.Forward'],row['Nominal'],row['Plazo'],row['Tasa Cop'],row['Operación']),axis=1) 
        
fwd['VP Flujo USD']=fwd.apply(lambda row: VP_FLUJO_USD(row['T.Forward'],row['Nominal'],row['Plazo'],row['Tasa Usd'],row['Operación']),axis=1) 

'REVISAR LA MONEDA DE CUMPLIMIENTO'


fwd['Valor Forward']=fwd.apply(lambda row: Vlr_forward(row['Plazo'],row['Moneda_Cumplimiento'],row['VP Flujo COP'],row['VP Flujo USD'],trm),axis=1) 
    


tfd1=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="BASE", skiprows=1, nrows=43, usecols='A')
new=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="BASE", skiprows=1, nrows=43, usecols='E')
tfd1['TRM']=new
del new

tfd1['FECHA'] = pd.to_datetime('1899-12-30') + pd.to_timedelta(tfd1['FECHA'], unit='D')

L=[]
for i in range(len(tfd1)):
    lastBusinessDay = tfd1.iat[i,0]
    shift = lastBusinessDay + BDay(1)
    L.append(shift)
FCH1 = pd.DataFrame({'FECHAH':L})
dict = {
        'FECHAH':[tfd1.iat[0,0]]}

r1=pd.DataFrame(dict)
FCH1 = r1._append(FCH1, ignore_index = True)

tfd1['FECHAH']=FCH1
tfd1=tfd1.drop([41, 42])

tfd1['FECHA']=tfd1['FECHA'].dt.strftime("%Y%m%d").astype(int)
tfd1['FECHAH']=tfd1['FECHAH'].dt.strftime("%Y%m%d").astype(int)

L=[]
for i in range(len(tfd1)):
    #print(i)
    if i == 0:
        k=tfd1.iat[0,1]
    else:
        if VLookup(tfd1['FECHAH'][i], 'FECHA', tfd1, 'TRM')==0.0:
            k=L[i-1]
        else:
            k=VLookup(tfd1['FECHAH'][i],'FECHA', tfd1, 'TRM')
    L.append(k)
    
TRM1 = pd.DataFrame({'TRM1':L})
tfd1['TRM1']=TRM1
tfd1['TRM1']=tfd1['TRM1'].fillna(0)




fwd['Vencimiento']=fwd['Vencimiento'].dt.strftime("%Y%m%d").astype(int)
fwd['Tasa Fix']=fwd.apply(lambda row: tfixfor(row['Plazo'],row['Vencimiento'],tfd1),axis=1)
fwd['Vencimiento'] = fwd['Vencimiento'].apply(lambda x: pd.to_datetime(str(x), format='%Y%m%d'))    
fwd['CXC']=fwd.apply(lambda row: Cuentas_Por_FWD(row['Moneda_Cumplimiento'],row['Vencimiento'],row['Cumplimiento'],fval,row['T.Forward'],row['Nominal'],row['Operación'],0,row['Tasa Fix'],row['Modalidad']),axis=1)
fwd['USD']=fwd.apply(lambda row: Vencimiento_FWD('USD',row['Moneda_Cumplimiento'],row['Modalidad'],row['Cumplimiento'],fval,row['T.Forward'],row['Nominal'],row['Operación'],row['Tasa Fix'],row['Vencimiento']),axis=1)
fwd['COP']=fwd.apply(lambda row: Vencimiento_FWD('COP',row['Moneda_Cumplimiento'],row['Modalidad'],row['Cumplimiento'],fval,row['T.Forward'],row['Nominal'],row['Operación'],row['Tasa Fix'],row['Vencimiento']),axis=1)

cols_to_move = [
    'Plazo', 'Tasa Cop', 'Tasa Usd', 'VP Flujo COP', 'VP Flujo USD',
    'Valor Forward', 'Tasa Fix', 'CXC', 'USD', 'COP'
]

# Todas las columnas del dataframe
cols = list(fwd.columns)

# Posición donde insertar (antes de 'Valor_y_cop')
insert_pos = cols.index('Valor_y_cop')

# Sacar las columnas a mover del orden actual
for c in cols_to_move:
    cols.remove(c)

# Insertarlas en el nuevo orden
new_cols = cols[:insert_pos] + cols_to_move + cols[insert_pos:]

# Reordenar dataframe
fwd = fwd[new_cols]

valorfornuevo=ValorFWD(fwd,trm)
valorforcvanuevo=ValorPFWDCVA(fwd)

Nuevosprodfor = fwd.loc[fwd['Emisión'] == fval, 'Valor_y_cop'].sum()
filtro = (fwd['Moneda_Cumplimiento'] == 'USD') & (fwd['Plazo'].isin([-1, -2, -3]))
filtro2 = (fwd['Moneda_Cumplimiento'] == 'USD') & (fwd['Plazo'].isin([0]))

porcumplir = fwd.loc[filtro, 'USD'].sum()+ fwd.loc[filtro2, 'CXC'].sum()

#fwd.loc[(fwd['Plazo'] == 0) & (fwd['Moneda_Cumplimiento'] == 'USD'), 'CXC'].sum() 

Deltafor =  fwd['VP Flujo USD'].sum() + porcumplir
#Deltafor =  fwd['VP Flujo USD'].sum() 
fecha_ult = datetime.strptime(mesu, "%Y%m%d")

# if fwd['Moneda_Cumplimiento'] == "USD":
#     fwd['Tasa Fix']*fwd['CXC'] 
cxcfor = fwd.loc[
    (fwd['Vencimiento'] > fecha_ult) & (fwd['Moneda_Cumplimiento'] == 'COP'), 
    'CXC'
].sum() + (fwd.loc[fwd['Moneda_Cumplimiento'] == "USD", 'Tasa Fix'] *
            fwd.loc[fwd['Moneda_Cumplimiento'] == "USD", 'CXC']).sum()
           
cxcfor1 = fwd.loc[
    (fwd['Vencimiento'] > fecha_ult) & (fwd['Moneda_Cumplimiento'] == 'COP'), 
    'CXC'
].sum() + (trm *
            fwd.loc[fwd['Moneda_Cumplimiento'] == "USD", 'CXC']).sum()           

venfor= calcular_forwards(fwd, fecha_ult)      


forwardsgri=valorfornuevo+cxcfor+venfor  


forcva = fwd.loc[(fwd['Plazo'] > 0), 'CVA_Fair_Value_COP_Y'].sum() +  (fwd.loc[(fwd['Interno/Externo'] == 'INTERNO'), 'Valor_y_cop'].sum()-
        fwd.loc[
            (fwd['Interno/Externo'] == 'INTERNO') & (fwd['Plazo'] <= 0), 
            'Valor_y_cop'
        ].sum())         
  
 

'///////////////////////////////////////////// CARGUE FORWARDS /////////////////////////////////////////////////////'



'///////////////////////////////////////////// CARGUE NOVADOS /////////////////////////////////////////////////////'


# ws = xw.Book(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_OPT_NOV_" + Dia + Mes + Año1 + "_000.xls")
# ws.save(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_OPT_NOV_" + Dia + Mes + Año1 + "_000.xlsx")
# ws.close()


#fwd=pd.read_csv(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_FWD_" + Dia + Mes + Año + "_000.xls", sep='\t', engine='python', encoding='latin-1')

nov=pd.read_csv(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_NOV_" + Dia + Mes + Año1 + "_000.xls", sep='\t', engine='python', encoding='latin-1' )
nov.columns=['BANCO DE BOGOTA']
max_pyc = nov['BANCO DE BOGOTA'].str.split(';').transform(len).max()
nov[[f'BANCO DE BOGOTA_{x}' for x in range(max_pyc)]]=nov['BANCO DE BOGOTA'].str.split(';', expand=True)
nov=nov.drop(nov.columns[0], axis=1)
nm=nov.iloc[1].values.tolist()
nov=nov.drop([0,1])
nov.columns=nm

nov=nov.reset_index(drop=True)
del nm


nov.columns=['PRODUCTO',
  'TRADE ID',
  ' EXTERNAL ID',
  'TRADE ID OTC',
  'CLIENTE OTC',
  'FECHA NEGOCIACION',
  'ID CONTRATO',
  'PAR MONEDAS',
  'No. CONTRATOS',
  'PRECIO PACTADO',
  'TRADER',
  'COMPRA/VENTA',
  'VENCIMIENTO',
  'NOMINAL',
  'VALOR PACTADO',
  'VALOR MERCADO',
  'PRECIO MERCADO (Y)',
  'MTM TOTAL PESOS',
  'PRECIO MERCADO (Y-1)',
  'MTM DIA PESOS',
  'FOLDER',
  'COMPANY',
  'BOOK',
  'DESK',
  'Delta Full Valuation 1 USD',
  'VALOR SENSIBLE',
  'VLR SENSIBLE - NOMINAL',
  'VLR SENSIBLE - NOMINAL USD',
  'COMPONENTE CAMBIARIO',
  'ACUM. COMPONENTE CAMBIARIO',
  'COMP. CAMBIARIO CIERRE AÑO ANTERIOR',
  'VLR. COMP. CAMBIARIO AÑO FISCAL']


new=['TRADE ID',
      'FECHA NEGOCIACION',
      'VENCIMIENTO',
      'PRECIO PACTADO',
      'NOMINAL',
      'COMPRA/VENTA',
      'VALOR PACTADO',
      'VALOR MERCADO',
      'PRECIO MERCADO (Y)',
      'MTM TOTAL PESOS',
      'PRECIO MERCADO (Y-1)',
      'MTM DIA PESOS',
      'TRADER',
      'BOOK',
      'DESK',
      'Delta Full Valuation 1 USD',
      'VALOR SENSIBLE',
      'VLR SENSIBLE - NOMINAL',
      'VLR SENSIBLE - NOMINAL USD',
      'COMPONENTE CAMBIARIO',
      'ACUM. COMPONENTE CAMBIARIO',
      'COMP. CAMBIARIO CIERRE AÑO ANTERIOR',
      'VLR. COMP. CAMBIARIO AÑO FISCAL',
      'PRODUCTO',
      ' EXTERNAL ID',
      'TRADE ID OTC',
      'CLIENTE OTC',
      'ID CONTRATO',
      'PAR MONEDAS',
      'No. CONTRATOS',
      'FOLDER',
      'COMPANY',
      'ACUM. COMPONENTE CAMBIARIO']

if len(nov.columns) > 0 and len(nov) > 0:

    nov = nov[new]
    
    nov['FECHA NEGOCIACION']=pd.to_datetime(nov['FECHA NEGOCIACION'],dayfirst=True)
    nov['VENCIMIENTO']=pd.to_datetime(nov['VENCIMIENTO'],dayfirst=True)
    
    del new
    
    nov.sort_values(by='FECHA NEGOCIACION', inplace=True)
    nov.reset_index(inplace=True,drop=True)
    
    valores_unicos = nov[['VENCIMIENTO']].drop_duplicates()
    valores_unicos.reset_index(inplace=True,drop=True)
    
    
    nov1=nov[['TRADE ID',
          'FECHA NEGOCIACION',
          'VENCIMIENTO',
          'PRECIO PACTADO',
          'NOMINAL',
          'COMPRA/VENTA']]
    
    nov1['TRADER']=nov['TRADER']
    nov1['BOOK']=nov['BOOK']
    nov1['Delta Full Valuation 1 USD']=nov['Delta Full Valuation 1 USD']
    
    del nov
                
    nov1['TRADE ID']=nov1['TRADE ID'].apply(convert_to_float)            
    nov1['PRECIO PACTADO']=nov1['PRECIO PACTADO'].apply(convert_to_float)
    nov1['NOMINAL']=nov1['NOMINAL'].apply(convert_to_float)
    nov1['Delta Full Valuation 1 USD']=nov1['Delta Full Valuation 1 USD'].apply(convert_to_float)          
    nov1['Posición_USD']=nov1.apply(lambda row: pos_usd(row['VENCIMIENTO'],row['NOMINAL'],fval,row['Delta Full Valuation 1 USD']),axis=1)
    nov1['Posición_USD']=nov1['Posición_USD'].apply(pd.to_numeric) 
    nov1['Valor Pactado']=nov1.apply(lambda row: vlr_pac(row['VENCIMIENTO'],fval,row['NOMINAL'],row['PRECIO PACTADO']),axis=1)
    
    
    
    'BORRAR CUANDO ESTÉ LISTO'
    
    '////////////////////////////'''
    
    
    
    pnov=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="NOVADOS", skiprows=2, nrows=557, usecols='A:C')
    pnov['Fecha'] = pd.to_datetime('1899-12-30') + pd.to_timedelta(pnov['Fecha'], unit='D')
    
       
    pnov['Plazo']=pnov.apply(lambda row: pla(row['Fecha'],fval), axis=1)    
    pnov['Tasa Cop']=pnov.apply(lambda row: Interpolacion_Tasa(row['Plazo'],tcop,"COP"), axis=1) 
    pnov['Tasa Usd']=pnov.apply(lambda row: Interpolacion_Tasa(row['Plazo'],tusd,"USD"), axis=1) 
    pnov['Fwd Calculado']=pnov.apply(lambda row: fwd_cal(row['Plazo'],trm,row['Tasa Cop'],row['Tasa Usd']), axis=1) 
    pnov['Ajuste']= pnov['Fwd Calculado']-pnov['Outright']
    values = ((-1*pnov['Ajuste'])+pnov['Fwd Calculado'])
    pnov['Fwd Ajustado'] = values.where(pnov.Plazo >= 0, other=0)
    pnov['DVO1']=pnov['Pts. Forward']+trm
    pnov['Fecha']=pnov['Fecha'].dt.strftime("%Y%m%d").astype(int)
    nov1['VENCIMIENTO']=nov1['VENCIMIENTO'].dt.strftime("%Y%m%d").astype(int)
    nov1['Px(T)']=nov1.apply(lambda row: Px(row['VENCIMIENTO'],int(fv)), axis=1)
    values = ((nov1['Px(T)'])*nov1['NOMINAL'])
    nov1['VM_COP'] = values.where(nov1.Posición_USD != 0, other=0)
    nov1['VM_COP'].sum()
    
    nov1['MTM(ACUMULADO)']=nov1.apply(lambda row: MTM_ACUM(row['VENCIMIENTO'],int(fv),row['Px(T)'],row['PRECIO PACTADO'],row['NOMINAL']), axis=1)
    pnovt1=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb", engine='pyxlsb', sheet_name="NOVADOS", skiprows=2, nrows=557, usecols='H:I')
    pnovt1.columns=['Fecha','Outright']
    pnovt1['Fecha']=pnovt1['Fecha'].dt.strftime("%Y%m%d").astype(int)
    nov1['FECHA NEGOCIACION']=nov1['FECHA NEGOCIACION'].dt.strftime("%Y%m%d").astype(int)   
    nov1['PX(T-1)']=nov1.apply(lambda row: PXT1(row['VENCIMIENTO'],int(fv),row['FECHA NEGOCIACION'],pnovt1),axis=1)
    
    #nov1['MTM DÍA']=nov1.apply(lambda row: MTMD(row['VENCIMIENTO'],int(fv),row['PX(T-1)'],row['Px(T)'],row['PRECIO PACTADO'],row['NOMINAL']),axis=1)
    nov1['MTM DÍA'].sum()
    
    NovxV = valores_unicos
    NovxV['VENCIMIENTO']=NovxV['VENCIMIENTO'].dt.strftime("%Y%m%d").astype(int)
    del valores_unicos
    
    
    NovxV['PX_INICIAL']=NovxV.apply(lambda row: P_INI(row['VENCIMIENTO'],int(fv),pnovt1),axis=1)
    NovxV['PX_FINAL']=NovxV.apply(lambda row: P_INI(row['VENCIMIENTO'],int(fv),pnov),axis=1)
    
        
    NovxV['MTM DÍA']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','MTM DÍA'),axis=1)
    NovxV['MTM TOTAL']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','MTM(ACUMULADO)'),axis=1)
    NovxV['VALOR MERCADO']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','VM_COP'),axis=1)
    NovxV['POSICIÓN_USD']=NovxV.apply(lambda row: MDÍA(row['VENCIMIENTO'],int(fv),nov1,'VENCIMIENTO','Posición_USD'),axis=1)
    


    def VENNOV(base):
        condicion = (base['Posición_USD'] == 0) | (base['Posición_USD'] == "")
    
        return base.loc[condicion, 'MTM(ACUMULADO)'].sum() 

    Liq= nov1['MTM DÍA'].sum()
    Venc=VENNOV(nov1)

else:
    Liq=0
    Venc=0

  
fc=fval-timedelta(days=1)
fk =  int(fc.strftime("%Y%m%d"))

nc=str(fk)
Llave=fecha_datetime = pd.to_datetime(nc, format='%Y%m%d')

if fc.month != fval.month:
    #histv=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Informe Libro de Opciones " + mesu[0:4] + mesu[4:6] + mesu[-2:] + ".xlsx", sheet_name="VCTOS", skiprows=6, nrows=35, usecols='A:C')
    histtotal=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + mesu[0:4] + mesu[4:6] + mesu[-2:] + ".xlsx", sheet_name="VCTOS", skiprows=0, nrows=15, usecols='A:C')
    #histv.columns =['Fecha','Vcto_Diario','Liquid']
    histtotal.columns =['Acumulado','Vcto','Liquid']
    #Venmes= histv['Vcto_Diario'].sum()
    #liqmes= histv['Liquid'].sum()
    #histtotal.iat[int(mesu[4:6]):1]=Venmes
    #histtotal.iat[int(mesu[4:6]):2]=liqmes
    #histtotal.iloc[(int(mesu[4:6])+1):, 1:3]=0
    Vm=histtotal['Vcto'].sum()
    lm=histtotal['Liquid'].sum()
    #histtotal['Vcto'][13]=Vm
    #histtotal['Liquid'][13]=lm
    #histv= pd.DataFrame({'Fecha': [fval], 'Vcto_Diario': [Venc], 'Liquid': [Liq]})
    #Venmes= histv['Vcto_Diario'].sum()
    #liqmes= histv['Liquid'].sum()
    #Vcto= Venmes+Vm
    #liq=liqmes+lm
    Vcto= Vm
    liq=lm
    
else:
    #histv=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\Informe Libro de Opciones " + nc + ".xlsx", sheet_name="VCTOS", skiprows=6, nrows=35, usecols='A:C')
    histtotal=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + nc + ".xlsx", sheet_name="VCTOS", skiprows=0, nrows=15, usecols='A:C')
    #histv.columns =['Fecha','Vcto_Diario','Liquid']
    #histtotal.columns =['Acumulado','Vcto','Liquid']
    #nueva_fila = pd.DataFrame({'Fecha': [fval], 'Vcto_Diario': [Venc], 'Liquid': [Liq]})
    #fila = histv[histv['Fecha'] == Llave].index[0]
    #histv = histv.drop(histv.index[fila+1:])
    #histv = pd.concat([histv, nueva_fila], ignore_index=True)
    #Venmes= histv['Vcto_Diario'].sum()
    #liqmes= histv['Liquid'].sum()
    #Vcto= Venmes+histtotal['Vcto'][13]
    #liq=liqmes+histtotal['Liquid'][13]
    Vcto=histtotal['Vcto'][13]
    liq=histtotal['Liquid'][13]

    if len(nov)<1: 
        Vcto=0
        
"Agregar acumulado en del dataframe histotal"    

histtotal = histtotal.dropna(how='all')

# def VALNOV(base):
#     condicion = (base['Posición_USD'] != 0)
    
#     return base.loc[condicion, 'MTM(ACUMULADO)'].sum() 

# def VENCNOV(base,fec):
#     condicion = (base['VENCIMIENTO'] == fec)
    
#     return base.loc[condicion, 'NOMINAL'].sum() 

# nov1.columns

# VMercado=nov1['VM_COP'].sum()
# LibroNov=VALNOV(nov1)+Vcto
# MTMTotal=nov1['MTM(ACUMULADO)'].sum()
# MTMDiario=nov1['MTM DÍA'].sum()
# Venc=VENNOV(nov1)
# PosicionUSD=nov1['Posición_USD'].sum()
# VencimientosD=VENCNOV(nov1,ff)

# ResultadoNov=pd.DataFrame({'Valor': ['Valor_Mercado','Libro_Novados','MTM_Total','MTM_Diario','Vencimientos','Posicion_USD','Vencimientos_Dia'], 
#                            'Dato': [VMercado,LibroNov,MTMTotal,MTMDiario,Venc,PosicionUSD,VencimientosD]})





# ws = xw.Book(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_CAJA_OPT_FUT_" + Dia + Mes + Año1 + "_000.xls")
# ws.save(r"\\atlas30\Gerencia_Riesgo_De_Tesoreria\2 IDENTIFICACION Y MEDICION  DE RIESGOS DE TESORERIA\BDB\INSUMOS\USR_CAJA_OPT_FUT_" + Dia + Mes + Año1 + "_000.xlsx")
# ws.close()

'//////////////////////////////////////////////////////// CARGUE CAJA///////////////////////////////////////////////////////////////'


#nov=pd.read_csv(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_NOV_" + Dia + Mes + Año1 + "_000.xls", sep='\t', engine='python', encoding='latin-1' )

cj=pd.read_csv(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_CAJA_OPT_FUT_" + Dia + Mes + Año1 + "_000.xls", sep='\t', engine='python', encoding='latin-1' )
cj.columns=['BANCO DE BOGOTA']
max_pyc = cj['BANCO DE BOGOTA'].str.split(';').transform(len).max()
cj[[f'BANCO DE BOGOTA_{x}' for x in range(max_pyc)]]=cj['BANCO DE BOGOTA'].str.split(';', expand=True)
cj=cj.drop(cj.columns[0], axis=1)
nm=cj.iloc[5].values.tolist()
cj=cj.drop([0,1,2,3,4,5])
cj.columns=nm

cj['TRADE DATE']=pd.to_datetime(cj['TRADE DATE'],dayfirst=True) 
cj1 = cj[cj['TRADE DATE'] == fval]
del cj
cj1 = cj1.reset_index(drop=True)
cj1['MONTO VENDIDO']=cj1['MONTO VENDIDO'].apply(convert_to_float)
cj1['MONTO COMPRADO']=cj1['MONTO COMPRADO'].apply(convert_to_float) 

flt1={'DmOwnerTable':['FXSPOT','FXOPT_TR'],
      'Book': ['OPCIONES_FX'],
      'SettleCcy': ['USD'],
      'CCY COMPRA':['USD'],
      'NOMBRE DE CLIENTE':['CAMARA DE RIESGO CENTRAL CONTRAPARTE DE COLOMBIA S.A.','FWD_CLIENTES','FWD_POSICION','FX_ESTRAT','SWAPS','ARBITRAJE_SWAPS','SPOT_CLIENTE','FWD CLIENTES','FWD POSICION','FX ESTRAT','ARBITRAJE SWAPS','SPOT CLIENTE']
      }


SMV_Compra=sumar_si_conjunto(cj1, 'MONTO VENDIDO', flt1)
Monto_Compra=sumar_si_conjunto(cj1, 'MONTO COMPRADO', flt1)
if Monto_Compra==0:
    TasaC=0 
else:    
    TasaC=SMV_Compra/Monto_Compra
    
del flt1

flt1={'DmOwnerTable':['FXSPOT','FXOPT_TR'],
      'Book': ['OPCIONES_FX'],
      'SettleCcy': ['USD'],
      'CCY VENTA':['USD'],
      'NOMBRE DE CLIENTE':['CAMARA DE RIESGO CENTRAL CONTRAPARTE DE COLOMBIA S.A.','FWD_CLIENTES','FWD_POSICION','FX_ESTRAT','SWAPS','ARBITRAJE_SWAPS','SPOT_CLIENTE','FWD CLIENTES','FWD POSICION','FX ESTRAT','ARBITRAJE SWAPS','SPOT CLIENTE']
      }

Monto_Venta=sumar_si_conjunto(cj1, 'MONTO VENDIDO', flt1)
SMV_Venta=sumar_si_conjunto(cj1, 'MONTO COMPRADO', flt1)
if Monto_Venta==0:
    TasaV=0 
else:    
    TasaV=SMV_Venta/Monto_Venta

del flt1

nc=str(fk)
if fc.month != fval.month:
    fecha_inicio = fval.replace(day=1)

    # Primer día del siguiente mes (maneja diciembre automáticamente)
    fecha_fin = fecha_inicio + relativedelta(months=1)

    # =========================
    # 3️⃣ Crear rango de fechas del mes
    # =========================
    fechas_mes = pd.date_range(
        start=fecha_inicio,
        end=fecha_fin,
        inclusive="left"   # reemplaza closed='left' (más moderno)
    )

    Historia_caja4=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + nc[0:4] + nc[4:6] + nc[-2:] + ".xlsx", sheet_name="Caja", skiprows=0, nrows=42, usecols='A:O')
    fila = Historia_caja4.index[Historia_caja4['Fecha'] == fecha_ult]
    valor = Historia_caja4.loc[fila, 'Caja_Usd']
    valor2 = Historia_caja4.loc[fila, 'Caja_Cop']
    
    del Historia_caja4
    
    Historia_caja = pd.DataFrame({
        "Fecha": fechas_mes
    })

    # =========================
    # 4️⃣ Agregar operaciones
    # =========================
    df_operaciones = pd.DataFrame({
        'Compras_Monto_USD': [Monto_Compra],
        'Compras_Tasa': [TasaC],
        'Ventas_Monto_USD': [Monto_Venta],
        'Ventas_Tasa': [TasaV]
    })

    Historia_caja = pd.concat(
        [Historia_caja, df_operaciones.reindex(Historia_caja.index)],
        axis=1
    )

    # =========================
    # 5️⃣ Leer archivo Excel
    # =========================
    # nombre_archivo = (
    #     f"Informe Libro de Opciones "
    #     f"{mesu[0:4]}{mesu[4:6]}{mesu[-2:]}.xlsx"
    # )

    # ruta = Path(
    #     r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria"
    #     r"\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON"
    # ) / nombre_archivo

    # df_excel = pd.read_excel(
    #     ruta,
    #     sheet_name="Caja_Ini",
    #     header=None
    #)

    # =========================
    # 6️⃣ Obtener caja inicial
    # =========================
    cajausd_ini = float(valor)
    cajacop_ini = float(valor2)

    caj = pd.DataFrame({
        'cajausd_ini': [cajausd_ini],
        'cajacop_ini': [cajacop_ini]
    })

else:
    df = pd.read_excel(
    r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones "
    + nc[0:4] + nc[4:6] + nc[-2:] + ".xlsx",
    sheet_name="Caja_Ini",
    header=None
    )

    cajausd_ini = float(df.iloc[1, 0])
    cajacop_ini = float(df.iloc[1, 1])
    Historia_caja=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + nc[0:4] + nc[4:6] + nc[-2:] + ".xlsx", sheet_name="Caja", skiprows=0, nrows=42, usecols='A:E')
    Historia_caja.columns=['Fecha','Compras_Monto_USD','Compras_Tasa','Ventas_Monto_USD','Ventas_Tasa']
    Historia_caja.fillna(0, inplace=True)
    fila = Historia_caja.index[Historia_caja['Fecha'] == fval]
    Historia_caja['Compras_Monto_USD'][fila]=Monto_Compra
    Historia_caja['Compras_Tasa'][fila]=TasaC
    Historia_caja['Ventas_Monto_USD'][fila]=Monto_Venta
    Historia_caja['Ventas_Tasa'][fila]=TasaV
    #inv_ini=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\Informe Libro de Opciones " + nc[0:4] + nc[4:6] + nc[-2:] + ".xlsx", sheet_name="Caja", skiprows=5, nrows=2, usecols='B')

    caj = pd.DataFrame()
    caj['cajausd_ini']= [cajausd_ini]
    caj['cajacop_ini']= [cajacop_ini]

'FALTA INSERTAR CAJA ACUMULADA DEL FIN DEL MES ANTERIRO'

Historia_caja['FP&Fee_Usd']= Historia_caja.apply(lambda row: FPYFeeusd(row['Fecha'],'USD'),axis=1)
Historia_caja['FP&Fee_Cop']= Historia_caja.apply(lambda row: FPYFeecop(row['Fecha'],'COP'),axis=1)
Historia_caja['LiqDerUsd']= Historia_caja.apply(lambda row: LIQderusd(row['Fecha']),axis=1)
Historia_caja['LiqDerCop']= Historia_caja.apply(lambda row: LIQderCop(row['Fecha']),axis=1)
Historia_caja['Cump_FWD_OPT_USD']= Historia_caja.apply(lambda row: Cumforopt(row['Fecha']),axis=1)    
Historia_caja['Cump_FWD_OPT_COP']= Historia_caja.apply(lambda row: Cumforoptcop(row['Fecha']),axis=1)  
Historia_caja['CXCUSD']= Historia_caja.apply(lambda row: CXCUSD(row['Fecha']),axis=1)  
Historia_caja['CXCCOP']= Historia_caja.apply(lambda row: CXCCOP(row['Fecha']),axis=1) 


'FALTA LIQUIDADCIÓN FORWARDS NOVADOS'


L=[]
for i in range(len(Historia_caja)):
    #print(i)
    if Historia_caja['Fecha'][i]>fval:
        k=0
    else:
        if i==0:
           k=cajausd_ini+Historia_caja['Compras_Monto_USD'][i]-Historia_caja['Ventas_Monto_USD'][i]+Historia_caja['FP&Fee_Usd'][i]+Historia_caja['Cump_FWD_OPT_USD'][i] 
        else:
            k=L[i-1]+Historia_caja['Compras_Monto_USD'][i]-Historia_caja['Ventas_Monto_USD'][i]+Historia_caja['FP&Fee_Usd'][i]+Historia_caja['Cump_FWD_OPT_USD'][i]
    L.append(k)

Cajaus = pd.DataFrame({'Cajaus':L})
Historia_caja['Caja_Usd']=Cajaus
del Cajaus

Historia_caja['Caja_Usd'].sum()

L=[]
for i in range(len(Historia_caja)):
    #print(i)
    if Historia_caja['Fecha'][i]>fval:
        k=0
    else:
        if i==0:
           k=cajacop_ini-((Historia_caja['Compras_Monto_USD'][i]*Historia_caja['Compras_Tasa'][i])-(Historia_caja['Ventas_Monto_USD'][i]*Historia_caja['Ventas_Tasa'][i]))+Historia_caja['FP&Fee_Cop'][i]      #+Historia_caja['LiqDerCop'][i]+Historia_caja['CXCCOP'][i]
        else:
            k=L[i-1]-((Historia_caja['Compras_Monto_USD'][i]*Historia_caja['Compras_Tasa'][i])-(Historia_caja['Ventas_Monto_USD'][i]*Historia_caja['Ventas_Tasa'][i]))+Historia_caja['FP&Fee_Cop'][i]+Historia_caja['Cump_FWD_OPT_COP'][i]
    L.append(k)

Cajacop = pd.DataFrame({'Cajacop':L})
Historia_caja['Caja_Cop']=Cajacop
del Cajacop

Historia_caja['Caja_Cop'].sum()

cajausdn=CAJAUSD(fval)
cajacopn=CAJACOP(fval)
cajatot = CAJATOTAL(fval,trm)

fila = Historia_caja[Historia_caja['Fecha'] == fval]

k=fila['Compras_Monto_USD'].sum() - fila['Ventas_Monto_USD'].sum()
if k > 0:
    tas=fila['Compras_Tasa'].sum()
else:
    tas=fila['Ventas_Tasa'].sum()
    

Intra = (min(fila['Compras_Monto_USD'].sum(), fila['Ventas_Monto_USD'].sum()))*(fila['Ventas_Tasa'].sum()-fila['Compras_Tasa'].sum())
saltrm = (fila['Compras_Monto_USD'].sum() - fila['Ventas_Monto_USD'].sum())*(trm - tas )
nuevoscaja= Intra + saltrm





res = pd.DataFrame()
res['Valor_Opciones']= [valportnuevo]
res['Valor_Forwards']= [valorfornuevo]
res['Valor_Novados']= [Vcto]
res['Cajausd'] = [cajausdn]
res['Cajacop'] = [cajacopn]
res['Cajatotal'] = [cajatot]
res['Valor_Libro']= [valportnuevo + valorfornuevo + Vcto + cajatot]
res['Valor_Opciones_CVA'] = [valportcvanuevo]
res['Valor_Forwards_CVA']= [valorforcvanuevo]
res['Valor_Libro_CVA'] = [valportcvanuevo + valorforcvanuevo + Vcto + cajatot]
res['VencimientosOpcput'] = [venciput]
res['VencimientosOpccall'] = [vencicall]
res['VencimientosOpctotal'] = [vencitot]
res['PrimasOpcput'] = [primasput]
res['PrimasOpccall'] = [primascall]
res['PrimasOpctotal'] = [primastot]
res['CajaOpc'] = [cajaopc]
res['Cuentasporcumpliropc'] = [cxcopc1]
res['ValoropcPYG']= [valoropcgriega]
res['CajaFor'] = [venfor]
res['Cuentasporcumplirfor'] = [cxcfor]
res['ValorfowPYG'] = [forwardsgri]
res['Posiciónusd_Opc'] = [Deltaopc]
res['Posiciónusd_For'] = [Deltafor]
res['Posiciónusd_Caja'] = [cajausdn]
res['Opccva'] = [opccva]
res['Forcva'] = [forcva]
res['TRM'] = [trm]






"////// CÁLCULO PYG POR PRODUCTO /////////////////////////"

print("INICIO CALCULO PYG")


fvalan = fval- timedelta(days=1)
fva = fvalan.strftime("%Y%m%d")
#TRMAN = float(input('Inserte TRM valoración día anterior: '))


Opt=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva +".xlsx", sheet_name="Opciones")
Ant=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva +".xlsx", sheet_name="Resumen") 

Opt.columns = Opt.columns.str.strip()

cajausant = Ant['Cajausd'][0]
opcant = Ant['Valor_Opciones'][0]
forant = Ant['Valor_Forwards'][0]
novant = Ant['Valor_Novados'][0]
cajaant = Ant['Cajausd'][0]
libant = Ant['Valor_Libro'][0]
trmant = Ant['TRM'][0]
vlropcant = Ant['ValoropcPYG'][0]
vlrfowant = Ant['ValorfowPYG'][0]
opccvaant = Ant['Opccva'][0]
forcvaant = Ant['Forcva'][0]



deltacaja = cajaant * (trm-trmant)

col_final = Opt.columns.get_loc('TAX_ID')  # posición (índice) de la columna TAX_ID
optr = Opt.iloc[:, :col_final + 1]  # selecciona desde la primera hasta TAX_ID inclusive

optr["Identificación contraparte"] = optr["Identificación contraparte"].astype(str)


#if fc.month != fval.month:
 #   optr= optr[optr[' Fecha de Cumplimiento'] > fecha_ult]



USD=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva + ".xlsx", sheet_name="Tasas_USD", usecols='A:D')
COP=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva + ".xlsx", sheet_name="Tasas_COP", usecols='A:D')
VOL=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva + ".xlsx", sheet_name="Superficie_Volatilidad", usecols='A:G')
VEG=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva + ".xlsx", sheet_name="Vega", usecols='A:E')
tasaantfix=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva + ".xlsx", sheet_name="tfd", usecols='A:D')
tasaantfixf=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva + ".xlsx", sheet_name="tff", usecols='A:D')

#del Moneda
#del L


#x,y=valora_libopcion(base,tc, curvacop,curvausd, curvavol,fechav)
"1. se valora cambiando fecha a hoy"
thetaopt,y,z,g,ktheta,extra=valora_libopcion(optr, trmant, COP, USD, VOL, fval,tasaantfix)
deltaopt,y,z,g,kdelta,extra=valora_libopcion(optr, trm, COP, USD, VOL, fval,tasaantfix)
rhoopt,y,z,g,krho,extra=valora_libopcion(optr, trm, tcop, tusd, VOL, fval,tasaantfix)
vegaopt,y,z,g,kvega,extra=valora_libopcion(optr, trm, tcop, tusd, surf, fval,tasaantfix)

"Falta tener en cuenta Vencimientos mes(griesgas) y primas mes para clacular el pyg"

if fc.month != fval.month:
    pygthetaopc = ktheta-opcant
else:
    pygthetaopc = ktheta-vlropcant
    
#pygthetaopc = ktheta-vlropcant
pygdeltaopc = kdelta - ktheta
pygrhoopc = krho-kdelta
pygvegaopc = kvega-krho
pygnuevosopc= valoropcgriega - kvega
pygopc= pygthetaopc+pygdeltaopc+pygrhoopc+pygvegaopc+pygnuevosopc

print("PYG OPCIONES CALCULADO")


Fow=pd.read_excel(r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fva + ".xlsx", sheet_name="Forwards", usecols='A:K,V,AB,AK')

#if fc.month != fval.month:
#    Fow= Fow[Fow['Cumplimiento'] > fecha_ult]


x,y,z,i,ftheta =valora_libforward(Fow,trmant, COP,USD,fval,tasaantfixf)
x,y,z,i,fdelta =valora_libforward(Fow,trm, COP,USD,fval,tasaantfixf)
x,y,z,i,frho =valora_libforward(Fow,trm, tcop, tusd,fval,tasaantfixf)

if fc.month != fval.month:
    pygthetafor = ftheta-forant
else:    
    pygthetafor = ftheta-vlrfowant
    
pygdeltafor = fdelta-ftheta
pygrhofor = frho-fdelta
pygnuevosfor = forwardsgri - frho
pygfor= pygthetafor+pygdeltafor+pygrhofor+pygnuevosfor

print("PYG FORWARDS CALCULADO")


"//////////////////// Para Caja calcular: nuevos productos y pyg por variación trm//////////////////7"

pygcaja=deltacaja+nuevoscaja

thetalibro=pygthetaopc+pygthetafor
deltalibro=pygdeltaopc+pygdeltafor+deltacaja
rholibro=pygrhoopc+pygrhofor
vegalibro=pygvegaopc
nuevoslibro=pygnuevosopc+pygnuevosfor+nuevoscaja
pyglibro=thetalibro+deltalibro+rholibro+vegalibro+nuevoslibro
pygopccva=opccva-opccvaant
pygforcva=forcva-forcvaant



diapyg =  fval.strftime("%Y%m%d")

print("PYG CALCULADO")


"//////////////////// CÁLCULOS GRIEGAS DIA//////////////////7///////////////////////////////////////////////"


"//////////////////// DELTA//////////////////7///////////////////////////////////////////////"


"////////////DELTA OPCIONES////////////////////////////////////"

fwd['CXC'].sum()

print("INICIO CALCULO DELTA")
opc1=opc
var025 = np.array([0.0025, 0.0050, 0.0075])   # 4 variaciones 0.25%
var1   = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])  # 6 variaciones 1%
var10  = np.array([0.10,0.20])                                # 1 variación 10%

# Ordenar de mayor a menor
variaciones_pos = np.sort(np.concatenate([var10, var1, var025]))[::-1]

# --- Variaciones NEGATIVAS (simétricas, ordenadas de menor a mayor) ---
variaciones_neg = -variaciones_pos[::-1]

# --- Unir todo con el 0 al centro ---
variaciones = np.concatenate([variaciones_pos, [0], variaciones_neg])

# Convertir a porcentaje
de_opc = pd.DataFrame({
    "Cambio (%)": (variaciones * 100).round(2)
})

de_opc['Spot']=(1+(de_opc['Cambio (%)']/100))*trm


resultados = de_opc.apply(
    lambda row: delta_opc(opc1, row['Spot'], surf, tfd, mesu, fval),
    axis=1
)

de_opc['Valor_Libro(COP)'] = resultados.str[0]
#de_opc['Otra_Columna'] = resultados.str[1]

#de_opc['Valor_Libro(COP)']= de_opc.apply(lambda row: delta_opc(opc1,row['Spot'],surf,tfd,mesu,fval)[0],axis=1)
de_opc['Cambio_Valor_Libro(COP)']=de_opc['Valor_Libro(COP)']-de_opc['Valor_Libro(COP)'][11]

deltas = []

for i in range(len(de_opc)):
    if i == 0:  # primera fila -> forward difference
        delta = (de_opc.loc[i+1, 'Valor_Libro(COP)'] - de_opc.loc[i, 'Valor_Libro(COP)']) / \
                (de_opc.loc[i+1, 'Spot'] - de_opc.loc[i, 'Spot'])
    elif i == len(de_opc)-1:  # última fila -> backward difference
        delta = (de_opc.loc[i, 'Valor_Libro(COP)'] - de_opc.loc[i-1, 'Valor_Libro(COP)']) / \
                (de_opc.loc[i, 'Spot'] - de_opc.loc[i-1, 'Spot'])
    else:  # diferencias centradas
        delta = (de_opc.loc[i+1, 'Valor_Libro(COP)'] - de_opc.loc[i-1, 'Valor_Libro(COP)']) / \
                (de_opc.loc[i+1, 'Spot'] - de_opc.loc[i-1, 'Spot'])
    deltas.append(delta)

de_opc['Delta(USD)'] = deltas
de_opc.loc[11, 'Delta(USD)'] = de_opc.loc[11, 'Delta(USD)'] + cxcus

gammas = []

for i in range(len(de_opc)):
    if i == 0:  # primera fila -> usar forward difference sobre delta
        gamma = (de_opc.loc[i+1, 'Delta(USD)'] - de_opc.loc[i, 'Delta(USD)']) / \
                (de_opc.loc[i+1, 'Spot'] - de_opc.loc[i, 'Spot'])
    elif i == len(de_opc)-1:  # última fila -> backward difference
        gamma = (de_opc.loc[i, 'Delta(USD)'] - de_opc.loc[i-1, 'Delta(USD)']) / \
                (de_opc.loc[i, 'Spot'] - de_opc.loc[i-1, 'Spot'])
    else:  # diferencias centradas
        gamma = (de_opc.loc[i+1, 'Delta(USD)'] - de_opc.loc[i-1, 'Delta(USD)']) / \
                (de_opc.loc[i+1, 'Spot'] - de_opc.loc[i-1, 'Spot'])
    gammas.append(gamma)

de_opc['Gamma'] = gammas
cxctot = pd.DataFrame()
cxctot['OPC'] = resultados.str[1]



"////////////DELTA OPCIONES////////////////////////////////////"


"////////////DELTA FORWARDS////////////////////////////////////"

Fow2=fwd
var025 = np.array([0.0025, 0.0050, 0.0075])   # 4 variaciones 0.25%
var1   = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])  # 6 variaciones 1%
var10  = np.array([0.10,0.20])                                # 1 variación 10%

# Ordenar de mayor a menor
variaciones_pos = np.sort(np.concatenate([var10, var1, var025]))[::-1]

# --- Variaciones NEGATIVAS (simétricas, ordenadas de menor a mayor) ---
variaciones_neg = -variaciones_pos[::-1]

# --- Unir todo con el 0 al centro ---
variaciones = np.concatenate([variaciones_pos, [0], variaciones_neg])

# Convertir a porcentaje
de_for = pd.DataFrame({
    "Cambio (%)": (variaciones * 100).round(2)
})

de_for['Spot']=(1+(de_for['Cambio (%)']/100))*trm


resultados = de_for.apply(
    lambda row: delta_forward_mod(Fow2,row['Spot'],tfd1,mesu),
    axis=1
)


de_for['Valor_Libro(COP)'] = resultados.str[0]
#de_opc['Otra_Columna'] = resultados.str[1]
cxctot['FOW'] = resultados.str[1]
#de_for['Valor_Libro(COP)']= de_for.apply(lambda row: delta_forward_mod(Fow1,row['Spot'],tfd1,mesu)[0],axis=1)
de_for['Cambio_Valor_Libro(COP)']=de_for['Valor_Libro(COP)']-de_for['Valor_Libro(COP)'][11]



de_for['Delta(USD)'] = (
    (de_for['Cambio_Valor_Libro(COP)'].shift(-1) - de_for['Cambio_Valor_Libro(COP)'].shift(-2)) / (de_for['Spot'].shift(-1) - de_for['Spot'].shift(-2)) +
    (de_for['Cambio_Valor_Libro(COP)'] - de_for['Cambio_Valor_Libro(COP)'].shift(-1)) / (de_for['Spot'] - de_for['Spot'].shift(-1))
) / 2


filtro = (Fow2['Moneda_Cumplimiento'] == 'USD') & (Fow2['Plazo'].isin([-1, -2, -3]))
filtro2 = (Fow2['Moneda_Cumplimiento'] == 'USD') & (Fow2['Plazo'].isin([0]))

porcumplir = Fow2.loc[filtro, 'USD'].sum()+ Fow2.loc[filtro2, 'CXC'].sum()
de_for['Delta(USD)'] = de_for['Delta(USD)'] + porcumplir
#de_for.loc[11, 'Delta(USD)'] = de_for.loc[11, 'Delta(USD)'] - porcumplir


"////////////DELTA FORWARDS////////////////////////////////////"


"////////////DELTA LIBRO////////////////////////////////////"


de_tot = pd.DataFrame({
    "Cambio (%)": (variaciones * 100).round(2)
})

de_tot['Spot']=(1+(de_tot['Cambio (%)']/100))*trm


resultados = de_tot.apply(
    lambda row: CAJATOTAL(fval,row['Spot']),
    axis=1
)


cxctot['CAJA'] = resultados

de_tot['Valor_Libro(COP)'] = (cxctot['CAJA']+de_for['Valor_Libro(COP)']+de_opc['Valor_Libro(COP)']+Vcto)-(cxctot['FOW']+ cxctot['OPC'])+(cxcopc1+cxcfor1)


de_tot['Cambio_Valor_Libro(COP)']=de_tot['Valor_Libro(COP)']-(valportnuevo + valorfornuevo + Vcto + cajatot)

deltas = []

for i in range(len(de_tot)):
    if i == 0:  # primera fila -> forward difference
        delta = (de_tot.loc[i+1, 'Valor_Libro(COP)'] - de_tot.loc[i, 'Valor_Libro(COP)']) / \
                (de_tot.loc[i+1, 'Spot'] - de_tot.loc[i, 'Spot'])
    elif i == len(de_tot)-1:  # última fila -> backward difference
        delta = (de_tot.loc[i, 'Valor_Libro(COP)'] - de_tot.loc[i-1, 'Valor_Libro(COP)']) / \
                (de_tot.loc[i, 'Spot'] - de_tot.loc[i-1, 'Spot'])
    else:  # diferencias centradas
        delta = (de_tot.loc[i+1, 'Valor_Libro(COP)'] - de_tot.loc[i-1, 'Valor_Libro(COP)']) / \
                (de_tot.loc[i+1, 'Spot'] - de_tot.loc[i-1, 'Spot'])
    deltas.append(delta)

de_tot['Delta(USD)'] = deltas
#de_tot.loc[11, 'Delta(USD)'] = de_tot.loc[11, 'Delta(USD)'] + cxcus

gammas = []

for i in range(len(de_tot)):
    if i == 0:  # primera fila -> usar forward difference sobre delta
        gamma = (de_tot.loc[i+1, 'Delta(USD)'] - de_tot.loc[i, 'Delta(USD)']) / \
                (de_tot.loc[i+1, 'Spot'] - de_tot.loc[i, 'Spot'])
    elif i == len(de_tot)-1:  # última fila -> backward difference
        gamma = (de_tot.loc[i, 'Delta(USD)'] - de_tot.loc[i-1, 'Delta(USD)']) / \
                (de_tot.loc[i, 'Spot'] - de_tot.loc[i-1, 'Spot'])
    else:  # diferencias centradas
        gamma = (de_tot.loc[i+1, 'Delta(USD)'] - de_tot.loc[i-1, 'Delta(USD)']) / \
                (de_tot.loc[i+1, 'Spot'] - de_tot.loc[i-1, 'Spot'])
    gammas.append(gamma)

de_tot['Gamma'] = gammas


print("CALCULO DELTA TERMIANDO")
"////////////DELTA LIBRO////////////////////////////////////"


"////////////VEGA////////////////////////////////////"


print("INICIO CALCULO VEGA")

Vallibbase = valportnuevo + valorfornuevo + Vcto + cajatot
cols_shock = ["10 D PUT", "25 D PUT", "ATM", "25 D CALL", "10 D CALL"]
Vega = pd.DataFrame(0.0, index=surf.index, columns=cols_shock)


# vega_opc(opc1, trm, surf)[0]
# vega_opc_moderno(opc1, trm, surf)
# vega_opc_filtrado(opc1, trm, surf, 14, 22)[0]

for col in cols_shock:
    for fila in surf.index:
        
        inicio = surf.at[fila, 'Plazo Inferior']
        fin = surf.at[fila, 'Plazo Superior']
    
        # 1) Guardar valor original
        valor_original = surf.loc[fila, col]
    
        # 2) Aplicar shock
        surf.loc[fila, col] = valor_original + 0.0001
    
        # 3) Recalcular valor libro
        valor_libro_shock = vega_opc_filtrado_opt(opc1, trm, surf,inicio,fin)[0]+ valorfornuevo + Vcto + cajatot
        #Valor_com= vega_opc(opc1, trm, surf)+ valorfornuevo + Vcto + cajatot
        # 4) Vega = diferencia
        vega_act = valor_libro_shock - Vallibbase
    
        # 5) Guardar en matriz final
        Vega.loc[fila, col] = vega_act
    
        # 6) Restaurar valor original
        surf.loc[fila, col] = valor_original
        
        print(valor_libro_shock)

# Calculamos la suma de cada columna
total = Vega.sum()

# Agregamos la fila 'Total' al final
Vega.loc['Total'] = total
Vega['Total'] = Vega.sum(axis=1)

print("FIN CALCULO VEGA")


"////////////VEGA////////////////////////////////////"



"//////////////////// RHOUSD//////////////////7///////////////////////////////////////////////"

print("INICIO CALCULO RHOUSD")


Fow1=fwd

columnas_deseadas = [
    'ID', 'NIT', 'Contraparte', 'Operación', 'Emisión', 'Vencimiento',
    'Cumplimiento', 'Nominal', 'T.Forward', 'Modalidad',
    'Moneda_Cumplimiento', 'Valor_y_cop', 'Interno/Externo',
    'CVA_Fair_Value_COP_Y', 'Plazo'
]

# Reordenar y mantener solo esas columnas
Fow1 = Fow1.reindex(columns=columnas_deseadas)
Fow1_copy = Fow1.copy()  # crea una copia completa de Fow1


cols_shock=['Valor Libro']
RhoOOUSD = pd.DataFrame(0.0, index=tusd.index, columns=cols_shock)
RhoFUSD = pd.DataFrame(0.0, index=tusd.index, columns=cols_shock)
RhoLibro= pd.DataFrame(0.0, index=tusd.index, columns=cols_shock)

#rhousd_opc_moderno(opc1, trm, tusd,surf,1,7)[0]

for fila in tusd.index:
    
    inicio = tusd.at[fila, 'Plazo Inferior']
    fin = tusd.at[fila, 'Plazo Superior']

    # 1) Guardar valor original
    valor_original = tusd.loc[fila, 'Tasas USD']

    # 2) Aplicar shock
    tusd.loc[fila, 'Tasas USD'] = valor_original + 0.0001

    # 3) Recalcular valor libro
    valor_libro_opciones = rhousdopc(opc1, trm, tusd,inicio,fin)[0]
    valor_libro_forward = valora_libforward(Fow1_copy,trm, tcop, tusd,fval,tasaantfixf)[0]

    #+ valorfornuevo + Vcto + cajatot
    #Valor_com= vega_opc(opc1, trm, surf)+ valorfornuevo + Vcto + cajatot
    # 4) Vega = diferencia
    #vega_act = valor_libro_shock - Vallibbase

    # 5) Guardar en matriz final
    RhoOOUSD.loc[fila, 'Valor Libro'] = valor_libro_opciones
    RhoFUSD.loc[fila, 'Valor Libro'] = valor_libro_forward
    RhoLibro.loc[fila, 'Valor Libro'] = valor_libro_opciones+valor_libro_forward+cajatot+Vcto

    # 6) Restaurar valor original
    tusd.loc[fila, 'Tasas USD'] = valor_original
    
    print(fila)



RhoOOUSD['PVO1'] = RhoOOUSD['Valor Libro']-valportnuevo
RhoFUSD['PVO1'] = RhoFUSD['Valor Libro']-valorfornuevo
RhoLibro['PVO1'] = RhoLibro['Valor Libro']-(valportnuevo + valorfornuevo + Vcto + cajatot)

print("FIN CALCULO RHOUSD")


"//////////////////// RHOUSD//////////////////7///////////////////////////////////////////////"



"//////////////////// RHOCOP//////////////////7///////////////////////////////////////////////"

print("INICIO CALCULO RHOCOP")
#rhocop_opc_mascara(opc1, trm, tcop,1,34)[0]



cols_shock=['Valor Libro']
#rhocop_opc_moderno(opc1, trm, tcop,surf,1,7)
RhoOCOP = pd.DataFrame(0.0, index=tcop.index, columns=cols_shock)
RhoFCOP = pd.DataFrame(0.0, index=tusd.index, columns=cols_shock)
RhoLibroCOP = pd.DataFrame(0.0, index=tusd.index, columns=cols_shock)
for fila in tcop.index:
    
    inicio = tcop.at[fila, 'Plazo Inferior']
    fin = tcop.at[fila, 'Plazo Superior']

    # 1) Guardar valor original
    valor_original = tcop.loc[fila, 'Tasas COP']

    # 2) Aplicar shock
    tcop.loc[fila, 'Tasas COP'] = valor_original + 0.0001

    # 3) Recalcular valor libro
    valor_libro_opciones = rhocop_opc_mascara(opc1, trm, tcop,inicio,fin)[0]
    valor_libro_forward = valora_libforward(Fow1_copy,trm, tcop, tusd,fval,tasaantfixf)[0]
    
    #+ valorfornuevo + Vcto + cajatot
    #Valor_com= vega_opc(opc1, trm, surf)+ valorfornuevo + Vcto + cajatot
    # 4) Vega = diferencia
    #vega_act = valor_libro_shock - Vallibbase

    # 5) Guardar en matriz final
    RhoOCOP.loc[fila, 'Valor Libro'] = valor_libro_opciones
    RhoFCOP.loc[fila, 'Valor Libro'] = valor_libro_forward
    RhoLibroCOP.loc[fila, 'Valor Libro'] = valor_libro_opciones+valor_libro_forward+cajatot+Vcto
    

    # 6) Restaurar valor original
    tcop.loc[fila, 'Tasas COP'] = valor_original
    Fow1_copy = Fow1.copy() 
    
    print(fila)


RhoOCOP['PVO1'] = RhoOCOP['Valor Libro']-valportnuevo
RhoFCOP['PVO1'] = RhoFCOP['Valor Libro']-valorfornuevo
RhoLibroCOP['PVO1'] = RhoLibroCOP['Valor Libro']-(valportnuevo + valorfornuevo + Vcto + cajatot)

print("FIN CALCULO RHOCOP")
"//////////////////// RHOCOP//////////////////7///////////////////////////////////////////////"



"////////////////////THETA//////////////////7///////////////////////////////////////////////"
    
print("INICIO CALCULO THETA")

Fow1_copy = Fow1.copy()    
fvap = fval + timedelta(days=1)
opc_copy = opc.copy()

columnas = [
    'Trade Id', 'Structure Id', 'Identificación contraparte',
    'Detalle de la contraparte', 'Posición en la opción',
    'Tipo de opción', 'Fecha de Emisión', 'Fecha de Vencimiento',
    'Fecha de Cumplimiento', 'Nominal', 'Precio de Ejercicio',
    'Valor Total Prima', 'Moneda de la  Prima', 'Modalidad Cumplimiento',
    'Moneda cumplimiento', 'Fecha prima', 'Volatilidad', 'Trader',
    'Oficina / CEO', 'Tasa Interes Main', 'Tasa Interes Money', 'Fee',
    'Moneda Fee', 'Fecha Fee', 'Black & Scholes', 'Value Amount',
    'Value amount exercised Sett Ccy', 'Tipo Estructura', 'Book',
    'Monto Ejercicio', 'Corporate ID', 'Customer Group', 'Netting (ISDA)',
    'SegmentoComercial', 'CustomerRating', 'Activo/Pasivo', 'CVA Curve',
    'Spread CVA', 'Tasa Descuento COP', 'Expected Loss',
    'CVA Black & Sholes', 'CVA Fair Value COP', 'VP Premium CVA COP',
    'Nivel', 'VP Sett Ccy Y CVA', 'TAX_ID'
]

opc_copy = opc_copy[columnas]   


thefowa=valora_libforward2(Fow1_copy,trm, tcop, tusd,fvap,tfd1)[4]
theopca=valora_libopcion(opc_copy, trm, tcop, tusd, surf, fvap,tfd)[5]
fhh=[fval,fvap]

the_opc= pd.DataFrame()
the_opc['Fecha']=fhh
the_opc['Valor_Libro']=[valportnuevo,theopca]
the_opc['Theta']=[theopca-valportnuevo,0]

the_for= pd.DataFrame()
the_for['Fecha']=fhh
the_for['Valor_Libro']=[valorfornuevo,thefowa]
the_for['Theta']=[thefowa-valorfornuevo,0]

the_lib= pd.DataFrame()
the_lib['Fecha']=fhh
the_lib['Valor_Libro']=[(valportnuevo + valorfornuevo + Vcto + cajatot),(theopca + thefowa + Vcto + cajatot)]
the_lib['Theta']=[(theopca + thefowa + Vcto + cajatot)-(valportnuevo + valorfornuevo + Vcto + cajatot),0]


print("FIN CALCULO THETA")

"////////////////////THETA//////////////////7///////////////////////////////////////////////"



"////////////////////PYGVOL//////////////////7///////////////////////////////////////////////"


cols = ['10 D PUT', '25 D PUT', 'ATM','25 D CALL', '10 D CALL']


varvol=(surf[cols]-VOL[cols])*10000
pygvol=varvol*VEG

pygvol.columns=cols
total = pygvol.sum()

# Agregamos la fila 'Total' al final
pygvol.loc['Total'] = total
pygvol['Total'] = pygvol.sum(axis=1)

"////////////////////PYGVOL//////////////////7///////////////////////////////////////////////"

Posiciónlib=de_opc.loc[11, 'Delta(USD)']+Deltafor+cajausdn

nombres=["Theta", "Delta", "Rho", "Vega","Nuevos","PYG","Theta_Caja","Delta_Caja","Rho_Caja","Vega_Caja","Nuevos_Caja","Caja_Dia","Theta_Forward","Delta_Forward","Rho_Forward","Vega_Forward","Nuevos_Forward",
         "PYG_Forward","Theta_Opc","Delta_Opc","Rho_Opc","Vega_Opc","Nuevos_Opc","PYG_Opc","Theta_Novados","Delta_Novados","Rho_Novados","Residual","Nuevos_Novados",
                  "PYG_Novados","CostoFondos","Utilidad_CF","","","Posición_caja_USD","Posición_For_USD","Posición_Opc","Posición_Opc_Sen","Posición_Novados",
                  "Posición_Libro","","PYG Opciones con CVA","PYG Forwards con CVA"]


val=[thetalibro,deltalibro,rholibro,vegalibro,nuevoslibro,pyglibro,0,deltacaja,0,0,nuevoscaja,(deltacaja+nuevoscaja),pygthetafor,pygdeltafor,pygrhofor,0,pygnuevosfor,pygfor,
     pygthetaopc,pygdeltaopc,pygrhoopc,pygvegaopc,pygnuevosopc,pygopc,0,0,0,0,0,0,0,0,0,0,cajausdn,Deltafor,Deltaopc,de_opc.loc[11, 'Delta(USD)'],0,Posiciónlib,0,pygopccva,pygforcva]

#del PYG
PYG=pd.DataFrame()
PYG['Nombres'] = nombres
#globals()[diapyg] = PYG

PYG[diapyg]=val


fwd['Diferencia_CVA_COP_Y'] = (
    fwd['Diferencia_CVA_COP_Y']
    .astype(str)
    .str.replace(',', '', regex=False)
    .astype(float)
)


dataframes = {
    'PYG': PYG,
    'tff': tfd1,
    'tfd': tfd,
    'VCTOS': histtotal,
    'Superficie_Volatilidad': surf,
    'Tasas_COP': tcop,
    'Tasas_USD': tusd,
    'Caja': Historia_caja,
    #'Novados_Por_Vencimiento': NovxV,
    #'Novados': nov1,
    'Forwards': fwd,
    'Opciones': opc,
    'Resumen' : res,
    'Caja_Ini': caj,
    'DeltaOPC' : de_opc,
    'DeltaFOR' : de_for,
    'DeltaLIB' : de_tot,
    'Vega' : Vega,
    'RhoUSDOPC' : RhoOOUSD,
    'RhoUSDFOR' : RhoFUSD,
    'RhoLIB' : RhoLibro,
    'RhoCOPOPC' : RhoOCOP,
    'RhoCOPFOR' : RhoFCOP,
    'RhoCOPLIB' : RhoLibroCOP, 
    'ThetaOPC' : the_opc, 
    'ThetaFOR' : the_for,
    'ThetaLIB' : the_lib,
    'Variaciónvol' : varvol,
    'PYGvol' : pygvol  
}

ruta_guardado = r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\Dataset Libro de Opciones " + fv + ".xlsx"

# Usamos ExcelWriter para guardar múltiples hojas
with pd.ExcelWriter(ruta_guardado, engine='openpyxl') as writer:
    for nombre_hoja, df in dataframes.items():
        df.to_excel(writer, sheet_name=nombre_hoja, index=False)

print("Archivo Excel creado con éxito usando pandas.")



"///Generar salida Estandar////////////////////////////////"
from openpyxl import load_workbook, Workbook
from openpyxl.utils import range_boundaries
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Border, Alignment, Color
import gc

ruta = r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\RIESGO_OPCIONES.xlsm"

#book = load_workbook(ruta, keep_vba=True)           



#wb = load_workbook(ruta)

# -------------------------------
# Función para copiar valores y formatos
# ----------------------------
#---




from openpyxl.styles import Font, PatternFill, Border, Alignment, Color

def rgb_to_argb(rgb):
    """
    Convierte un color 'RGB' o 'RRGGBB' a formato 'aRGB' (8 dígitos) requerido por openpyxl.
    """
    if rgb is None:
        return None
    rgb = str(rgb)  # asegúrate de que sea string
    rgb = rgb.replace("0x", "").replace("#", "")  # limpiar prefijos si los hay
    if len(rgb) == 6:  # si es RRGGBB, agregamos FF al inicio para alfa
        return "FF" + rgb.upper()
    elif len(rgb) == 8:  # ya es aRGB
        return rgb.upper()
    else:
        return None

def copiar_rango(ws, rango_origen, celda_destino):
    min_col, min_row, max_col, max_row = range_boundaries(rango_origen)
    dest_col, dest_row = range_boundaries(f"{celda_destino}:{celda_destino}")[0:2]

    for i, fila in enumerate(range(min_row, max_row + 1)):
        for j, col in enumerate(range(min_col, max_col + 1)):
            celda_origen = ws.cell(row=fila, column=col)
            celda_dest = ws.cell(row=dest_row + i, column=dest_col + j)

            # Valor
            celda_dest.value = celda_origen.value

            # Estilo
            if celda_origen.has_style:
                f = celda_origen.font
                celda_dest.font = Font(
                    name=f.name, size=f.size, bold=f.bold, italic=f.italic,
                    vertAlign=f.vertAlign, underline=f.underline, strike=f.strike,
                    color=rgb_to_argb(getattr(f.color, "rgb", None))
                )

                fill = celda_origen.fill
                if fill and fill.fill_type:
                    start_rgb = rgb_to_argb(getattr(fill.start_color, "rgb", None))
                    end_rgb = rgb_to_argb(getattr(fill.end_color, "rgb", None))
                    celda_dest.fill = PatternFill(
                        fill_type=fill.fill_type,
                        start_color=Color(rgb=start_rgb) if start_rgb else None,
                        end_color=Color(rgb=end_rgb) if end_rgb else None
                    )

                b = celda_origen.border
                celda_dest.border = Border(
                    left=b.left, right=b.right, top=b.top, bottom=b.bottom,
                    diagonal=b.diagonal, diagonal_direction=b.diagonal_direction,
                    outline=b.outline, vertical=b.vertical, horizontal=b.horizontal
                )

                a = celda_origen.alignment
                celda_dest.alignment = Alignment(
                    horizontal=a.horizontal, vertical=a.vertical,
                    text_rotation=a.text_rotation, wrap_text=a.wrap_text,
                    shrink_to_fit=a.shrink_to_fit, indent=a.indent
                )

                celda_dest.number_format = celda_origen.number_format



# -----------------------------
# Función para encontrar última columna con datos en fila específica
# -----------------------------
# def ultima_columna_hoja(ruta, hoja, fila=4):
#     book = load_workbook(ruta, keep_vba=True)
#     ws = book[hoja]
#     ultima_col = 0
#     for col in range(1, ws.max_column + 1):
#         if ws.cell(row=fila, column=col).value not in (None, ""):
#             ultima_col = col
#     return ultima_col

# -----------------------------
# Columnas filtradas
# -----------------------------
opc_columnas_1 = [
    'Trade Id','Structure Id','Identificación contraparte','Detalle de la contraparte',
    'Posición en la opción','Tipo de opción','Fecha de Emisión','Fecha de Vencimiento',
    'Fecha de Cumplimiento','Nominal','Precio de Ejercicio','Valor Total Prima',
    'Moneda de la  Prima','Modalidad Cumplimiento','Moneda cumplimiento',
    'Plazo','Tasa Cop','Tasa Usd','Volatilidad','BS','Tasa Interes Main',
    'Valor Libro (CRNCY)','Tasa Fix','Cuentas por Cumplir','USD','COP',
    'Tasa Interes Money','Fee','Delta','Oficina / CEO','Estructura','BS Ajustado',
    'Trader','Plazo Cumplimiento','Dias inf USD','Dias Sup USD','Tasa Inf USD',
    'Tasa Sup USD','Tasa Val USD Cump','Factor De Descuento','Dias Inf SUP','Dias Sup SUP',
    'Tasa Inf 10PUT','Tasa Sup 10PUT','Delta_10PUT','Tasa Inf 25PUT','Tasa Sup 25PUT',
    'Delta_25PUT','Tasa Inf ATM','Tasa Sup ATM','Delta_ATM','Tasa Inf 25CALL','Tasa Sup 25CALL',
    'Delta_25CALL','Tasa Inf 10CALL','Tasa Sup 10CALL','Delta_10CALL',
    'Volatilidad Ajustada Cubic Funcion','Diferencia Vana-Volga','Factor de Descuento1'
]

opc_columnas_2 = ['DifValSINCVA','DifValCONCVA','BS_CVA','ValorLibroCVA','DifrevCVA','DifporCVA']

opc_columnas_3 = ['Black & Scholes','Value Amount','Delta 1','Book']
opc_fl = ['Black & Scholes','Value Amount','Delta 1']
opc[opc_fl] = opc[opc_fl].astype(float)

opc['Structure Id'] = pd.to_numeric(opc['Structure Id'], errors='ignore')
opc['Oficina / CEO'] = pd.to_numeric(opc['Oficina / CEO'], errors='ignore')

# opc['num'] = opc['Structure Id'].str.extract(r'^(\d+)', expand=False).astype(int)
# opc['suffix'] = opc['Structure Id'].str.extract(r'^\d+(.*)', expand=False).fillna('')

# opc = opc.sort_values(by=['num', 'suffix']).drop(columns=['num', 'suffix'])

opc_columnas_4 = ['Customer Group',
                           'Netting (ISDA)',
                        'SegmentoComercial',
                           'CustomerRating',
                            'Activo/Pasivo',
                                'CVA Curve',
                               'Spread CVA',
                       'Tasa Descuento COP',
                            'Expected Loss',
                       'CVA Black & Sholes',
                       'CVA Fair Value COP']

opc_fl = ['Identificación contraparte','Spread CVA','Tasa Interes Main','Tasa Interes Money','Fee',
'Tasa Descuento COP',
     'Expected Loss',
'CVA Black & Sholes',
'CVA Fair Value COP']
opc[opc_fl] = opc[opc_fl].astype(float)


fwd['Operación'] = fwd['Operación'].replace({
    'COMPRA': 'BUY',
    'VENTA': 'SELL'
})

fwd_columnas_1 = ['ID','NIT','Contraparte','Operación','Emisión','Vencimiento',
                   'Cumplimiento','Nominal','T.Forward','Modalidad','Moneda_Cumplimiento',
                   'Plazo','Tasa Cop','Tasa Usd','VP Flujo COP','VP Flujo USD','Netting_(ISDA)',
                   'Valor Forward','Tasa Fix','CXC','USD','COP']

fwd_columnas_2 = ['Valor_y_cop','Valor_x_cop','VP_Sett_Ccy_X','VP_Sett_Ccy_Y','P&G_Diario',
                   'Valor_Liq','Interno/Externo','Book','Customer_Group','Netting_(ISDA)',
                   'Segmento_Comercial','Customerrating','Activo/Pasivo','CVA_curve',
                   'Spread_Cva_Y','CVA_Fair_Value_COP_Y','Diferencia_CVA_COP_Y']

fwd_fl = ['ID','NIT','Netting_(ISDA)']

fwd[fwd_fl] = fwd[fwd_fl].apply(pd.to_numeric, errors='coerce')




caja_columnas_1 = ['Fecha','Compras_Monto_USD','Compras_Tasa','Ventas_Monto_USD','Ventas_Tasa',
                    'FP&Fee_Usd','FP&Fee_Cop','LiqDerUsd','LiqDerCop']

caja_columnas_2 = ['Caja_Usd','Caja_Cop','CXCUSD','CXCCOP','Cump_FWD_OPT_USD','Cump_FWD_OPT_COP']
colvol=['10 D PUT', '25 D PUT', 'ATM',
       '25 D CALL', '10 D CALL']

RibroCOP=RhoLibroCOP.iloc[:-6]
ROCOP=RhoOCOP.iloc[:-2]
RFCOP=RhoFCOP.iloc[:-6]
riesgos_columnas = {
    "de_tot": (de_tot, 7, 0),
    "de_opc": (de_opc, 44, 0),
    "de_for": (de_for, 44, 7),
    "Vega": (Vega, 7, 8),
    "RhoLibro": (RhoLibro, 7, 18),
    "RhoLibroCOP": (RibroCOP, 7, 22),
    "RhoOOUSD": (RhoOOUSD, 7, 27),
    "RhoOCOP": (ROCOP, 7, 31),
    "RhoFUSD": (RhoFUSD, 7, 35),
    "RhoFCOP": (RFCOP, 7, 39),
    "the_opc": (the_opc, 39, 0),
    "the_lib": (the_lib, 31, 7),
    "the_for": (the_for, 39, 7)
}

# -----------------------------
# Filtrar DataFrames
# -----------------------------
opc_filtrado_1 = opc[opc_columnas_1]
opc_filtrado_2 = opc[opc_columnas_2]
opc_filtrado_3 = opc[opc_columnas_3]
fwd_filtrado_1 = fwd[fwd_columnas_1]
fwd_filtrado_2 = fwd[fwd_columnas_2]

fwd_filtrado_2['Diferencia_CVA_COP_Y'] = (
    fwd_filtrado_2['Diferencia_CVA_COP_Y']
    .astype(str)
    .str.replace(',', '', regex=False)
    .astype(float)
)

Historia_caja_filtrado_1 = Historia_caja[caja_columnas_1]
Historia_caja_filtrado_2 = Historia_caja[caja_columnas_2]
volfil =VOL[colvol]
# -----------------------------
# Detectar columna destino para PYG
# -----------------------------

col_destino_pyg_zero=fval.day

# -----------------------------
# Escribir todos los DataFrames
# -----------------------------
# 


"//////////////////////////////////// PRUEBA2 ///////////////////////////////////////////////////////////"

ruta = r"\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\OPCIONES\INFORME_PYTHON\RIESGO_OPCIONES.xlsm"


from openpyxl.utils import range_boundaries

def borrar_rango(ws, rango):
    min_col, min_row, max_col, max_row = range_boundaries(rango)

    for fila in ws.iter_rows(
        min_row=min_row,
        max_row=max_row,
        min_col=min_col,
        max_col=max_col
    ):
        for celda in fila:
            celda.value = None

def pegar_dataframe_valores(df, ws, startrow=0, startcol=0):
    """
    Pega SOLO valores (sin fórmulas, sin estilos).
    startrow y startcol son base 0 (como pandas).
    """
    for i, fila in enumerate(df.itertuples(index=False)):
        for j, valor in enumerate(fila):
            ws.cell(
                row=startrow + i + 1,
                column=startcol + j + 1,
                value=valor
            )
            

from openpyxl import load_workbook
from datetime import datetime
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
# -----------------------------
# Abrir plantilla (con macros)
# -----------------------------
wb = load_workbook(ruta, keep_vba=True)

Val = input("Hábil SI/NO: ").upper()

# =============================
# MERCADO
# =============================
ws = wb["Mercado"]

ws["B3"] = fval
ws["B4"] = trm

if Val == "SI":
    copiar_rango(ws, "J29:L584", "M29")

pegar_dataframe_valores(tusd[['Tasas USD']], ws, 7, 2)
pegar_dataframe_valores(tcop.iloc[:-2][['Tasas COP']], ws, 7, 6)
pegar_dataframe_valores(
    surf[['10 D PUT','25 D PUT','ATM','25 D CALL','10 D CALL']],
    ws, 28, 1
)

# =============================
# OPCIONES
# =============================
ws = wb["Opciones"]
borrar_rango(ws, "A8:CJ10000")
pegar_dataframe_valores(opc_filtrado_1, ws, 7, 0)
pegar_dataframe_valores(opc_filtrado_2, ws, 7, 82)
pegar_dataframe_valores(opc_filtrado_3, ws, 7, 66)

# =============================
# FORWARDS
# =============================
ws = wb["Forwards"]
borrar_rango(ws, "A8:AO10000")
pegar_dataframe_valores(fwd_filtrado_1, ws, 7, 0)
pegar_dataframe_valores(fwd_filtrado_2, ws, 7, 23)

# =============================
# CAJA
# =============================
ws = wb["Caja"]
ws["B7"] = cajausd_ini
ws["B8"] = cajacop_ini

pegar_dataframe_valores(Historia_caja_filtrado_1, ws, 12, 0)
pegar_dataframe_valores(Historia_caja_filtrado_2, ws, 12, 11)

# =============================
# SERIE BALANCE (DESPLAZAMIENTO)
# =============================
ws = wb["Serie Balance"]

ultima_fila = ws.max_row
ultima_col = 20  # A:T

# 1. Copiar fila 2 en adelante a memoria
datos = []
for fila in range(2, ultima_fila + 1):
    datos.append([
        ws.cell(row=fila, column=col).value
        for col in range(1, ultima_col + 1)
    ])

# 2. Pegarlos una fila abajo (fila 3 en adelante)
for i, fila_datos in enumerate(datos, start=3):
    for col, valor in enumerate(fila_datos, start=1):
        ws.cell(row=i, column=col).value = valor

# 3. Limpiar fila 2
for col in range(1, ultima_col + 1):
    ws.cell(row=2, column=col).value = None
    
ws["A2"] = fval
ws["B2"] = cajausdn
ws["C2"] = cajausdn * trm
ws["D2"] = cajacopn
ws["E2"] = cajacopn + (cajausdn * trm)
ws["F2"] = cxcopc1+cxcfor1
ws["G2"] = valorfornuevo
ws["H2"] = valportnuevo
ws["I2"] = Vcto
ws["J2"] = valportnuevo + valorfornuevo + Vcto + cajatot
ws["K2"] = pyglibro
ws["N2"] = thetalibro
ws["O2"] = deltalibro
ws["P2"] = rholibro
ws["Q2"] = vegalibro
ws["R2"] = nuevoslibro
ws["S2"] = opccva
ws["T2"] = forcva

ws["X3"] = datetime.strptime(mesu, "%Y%m%d")

# =============================
# BALANCE
# =============================
ws = wb["Balance"]
ws["B35"] = thetalibro
ws["B36"] = deltalibro
ws["B37"] = rholibro
ws["B38"] = vegalibro
ws["B39"] = nuevoslibro

# =============================
# PYG
# =============================
ws = wb["PYG"]
pegar_dataframe_valores(
    PYG.iloc[:, 1].to_frame(),
    ws,
    3,
    col_destino_pyg_zero
)

# =============================
# PYG VOLATILIDAD
# =============================
if Val == "SI":
    ws = wb["PYG Volatilidad"]
    copiar_rango(ws, "B5:G21", "J5")

    pegar_dataframe_valores(volfil, ws, 4, 10)
    pegar_dataframe_valores(VEG, ws, 25, 10)
    pegar_dataframe_valores(varvol, ws, 25, 2)

    pygvol_clean = pygvol[pygvol.isna().sum(axis=1) < 3]
    pegar_dataframe_valores(pygvol_clean, ws, 46, 2)

# =============================
# RIESGOS
# =============================
ws = wb["Riesgos"]
for _, (df, row, col) in riesgos_columnas.items():
    pegar_dataframe_valores(df, ws, row, col)

# =============================
# COPIA FINAL PYG → BALANCE
# =============================
copiar_rango(wb["PYG"], "AG4:AG8", "C35")

# -----------------------------
# GUARDAR (UNA SOLA VEZ)
# -----------------------------
wb.save(ruta)
wb.close()

del wb

gc.collect()

print("✔ Archivo generado correctamente SIN errores de reparación")

fin = time.perf_counter()

print("Tiempo de ejecución:", (fin - inicio)/60, "minutos")


#with pd.ExcelWriter(
#     ruta,
#     engine="openpyxl",
#     mode="a",
#     if_sheet_exists="overlay",
#     engine_kwargs={"keep_vba": True}
# ) as writer:

#     Val = input('Hábil SI/NO: ')
#     if Val == "SI":
#         ws = writer.book["Mercado"]
#         copiar_rango(ws, "J29:L584", "M29")

#     # -------------------------------
#     # Copiar "PYG Volatilidad" B5:G21 -> J5
#     # -------------------------------
#         wat = writer.book["PYG Volatilidad"]
#         copiar_rango(wat, "B5:G21", "J5")

#     # Guardar cambios
#     #wb.save(ruta)
    

#     ws["B3"] = fval
#     ws["B4"] = trm
    
#     wa = writer.book["Caja"]
#     wa["B7"] = cajausd_ini
#     wa["B8"] = cajacop_ini
    
#     tcop=tcop.iloc[:-2]

    
#     # Mercado
#     tusd[['Tasas USD']].to_excel(writer, sheet_name="Mercado", startrow=7, startcol=2, index=False, header=False)
#     tcop[['Tasas COP']].to_excel(writer, sheet_name="Mercado", startrow=7, startcol=6, index=False, header=False)
#     surf[['10 D PUT','25 D PUT','ATM','25 D CALL','10 D CALL']].to_excel(writer, sheet_name="Mercado", startrow=28, startcol=1, index=False, header=False)

#     # Opciones
#     opc_filtrado_1.to_excel(writer, sheet_name="Opciones", startrow=7, startcol=0, index=False, header=False)
#     opc_filtrado_2.to_excel(writer, sheet_name="Opciones", startrow=7, startcol=83, index=False, header=False)

#     # Forwards
#     fwd_filtrado_1.to_excel(writer, sheet_name="Forwards", startrow=7, startcol=0, index=False, header=False)
#     fwd_filtrado_2.to_excel(writer, sheet_name="Forwards", startrow=7, startcol=23, index=False, header=False)

#     # Caja
#     Historia_caja_filtrado_1.to_excel(writer, sheet_name="Caja", startrow=12, startcol=0, index=False, header=False)
#     Historia_caja_filtrado_2.to_excel(writer, sheet_name="Caja", startrow=12, startcol=11, index=False, header=False)

#     ws_sb = writer.book["Serie Balance"]

#     ultima_fila_sb = ws_sb.max_row
#     ultima_col_sb = 20  # columna T

#     # Mover datos hacia abajo (de abajo hacia arriba)
#     for fila in range(ultima_fila_sb, 2, -1):
#         for col in range(1, ultima_col_sb + 1):
#             ws_sb.cell(row=fila + 1, column=col).value = ws_sb.cell(row=fila, column=col).value

#     # Limpiar fila 2 (A2:T2)
#     for col in range(1, ultima_col_sb + 1):
#         ws_sb.cell(row=2, column=col).value = None

#     ws_sb["A2"] = fval
#     ws_sb["B2"] = cajausdn
#     ws_sb["C2"] = cajausdn*trm
#     ws_sb["D2"] = cajacopn
#     ws_sb["E2"] = cajacopn + (cajausdn*trm)
#     ws_sb["F2"] = 0
#     ws_sb["G2"] = valorfornuevo
#     ws_sb["H2"] = valportnuevo
#     ws_sb["I2"] = Vcto
#     ws_sb["J2"] = valportnuevo + valorfornuevo + Vcto + cajatot
#     ws_sb["K2"] = pyglibro
#     ws_sb["N2"] = thetalibro
#     ws_sb["O2"] = deltalibro
#     ws_sb["P2"] = rholibro
#     ws_sb["Q2"] = vegalibro
#     ws_sb["R2"] = nuevoslibro
#     ws_sb["S2"] = 0
#     ws_sb["T2"] = 0

#     mesu_dt = datetime.strptime(mesu, "%Y%m%d")

#     ws_sb["X3"] = mesu_dt
   
#     ws_sa = writer.book["Balance"]
#     ws_sa["B35"] = thetalibro
#     ws_sa["B36"] = deltalibro
#     ws_sa["B37"] = rholibro
#     ws_sa["B38"] = vegalibro
#     ws_sa["B39"] = nuevoslibro

#     # PYG (solo segunda columna, columna mínima 33)
#     PYG.iloc[:, 1].to_excel(writer, sheet_name="PYG", startrow=3, startcol=col_destino_pyg_zero, index=False, header=False)

#     # PYG Volatilidad
    
#     if Val == "SI":
#         VEG.to_excel(writer, sheet_name="PYG Volatilidad", startrow=25, startcol=10, index=False, header=False)
#         varvol.to_excel(writer, sheet_name="PYG Volatilidad", startrow=25, startcol=2, index=False, header=False)
#         pygvol = pygvol[pygvol.isna().sum(axis=1) < 3]
#         pygvol.to_excel(writer, sheet_name="PYG Volatilidad", startrow=46, startcol=2, index=False, header=False)
    
    
        
#     # Riesgos
#     for df_name, (df, row, col) in riesgos_columnas.items():
#         df.to_excel(writer, sheet_name="Riesgos", startrow=row, startcol=col, index=False, header=False)


#     ws_pyg = writer.book["PYG"]  
#     ws_balance = writer.book["Balance"]

#     copiar_rango(ws_pyg, "AG4:AG8", "C35")

# # Guardar cambios
#     #wb.save(ruta)

# print("Rango copiado de 'PYG' a 'Balance' correctamente.")