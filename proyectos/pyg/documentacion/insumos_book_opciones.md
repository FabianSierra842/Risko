# Insumos — primer book de PyG: Opciones

## Insumos comunes del book

| Insumo | Archivo local Vector | Uso |
|---|---|---|
| Referencia mensual oficial | `PYG_OPCIONES_MES_REFERENCIA.xlsb` | Histórico diario, C1:H22, Banking, CVA, IFRS y Épsilon |
| Posiciones publicadas | `risko.db` | Control read-only de filas 19/22; no calcula PyG |
| Mercado | `ENTRADA2.xlsb` | Curvas COP/USD, superficie de volatilidad y tasas fix |
| TRM formada | `Insumo tasas.xlsx` | Spot de cierre por fecha |
| Control del código base | `Curva Forward V2.xlsm` | TRM usada por `Opciones_FF_V3.py`; solo control de transición |
| Snapshot diario D/D-1 | `Dataset Libro de Opciones YYYYMMDD.xlsx` | Portafolio y mercado históricos preservados |

## Producto Forward

| Insumo | Origen | Uso específico |
|---|---|---|
| `USR_OPT_FWD_ddmmaaaa_000.xls` | Summit `VALORACION_FWD` | Operaciones del sublibro Forward, nominal, tasa pactada, vencimiento, modalidad y moneda de liquidación |
| Dataset D-1, hoja `Forwards` | `INFORME_PYTHON` | Cartera inicial para Theta, Delta PyG y Rho |
| Dataset D-1/D, `Tasas_COP`, `Tasas_USD`, `tff` | `INFORME_PYTHON` | Descuento y tasas de fijación |
| Dataset D-1/D, `Resumen` | `INFORME_PYTHON` | Valor Banking/IFRS, CVA y conciliación |
| `tbl_posicion_forward` | snapshot `risko.db` | Control de posición Banking/IFRS del book Opciones |

Contribuciones ejecutadas: Theta, Delta PyG, Rho, Trading, Épsilon y CVA. Vega
es cero para Forward.

## Producto Opciones

| Insumo | Origen | Uso específico |
|---|---|---|
| `USR_OPT_MANANA_ddmmaa_000.xls` de T+1 hábil | Summit `FXOPTION_BASIC` | Portafolio de opciones del corte: CALL/PUT, BUY/SELL, nominal, strike, fechas, modalidad y moneda |
| Dataset D-1, hoja `Opciones` | `INFORME_PYTHON` | Cartera para los escenarios de atribución |
| `Tasas_COP` y `Tasas_USD` D-1/D | Dataset diario | Rho y descuento Garman-Kohlhagen |
| `Superficie_Volatilidad` D-1/D | Dataset diario / `ENTRADA2` | Vega y smile 10P, 25P, ATM, 25C, 10C |
| `tfd` e `Insumo tasas.xlsx` | Dataset / Compliance | TRM y fixing de vencimientos |
| `Resumen` D-1/D | Dataset diario | Valor Banking/IFRS, CVA y conciliación |
| `tbl_posicion_opciones` | snapshot `risko.db` | Control de Delta posición; no se suma a `DELTA_PYG` |

Contribuciones ejecutadas: Theta, Delta PyG, Rho, Vega, Trading, Épsilon y CVA.

## Producto Caja

| Insumo | Origen | Uso específico |
|---|---|---|
| `USR_CAJA_OPT_FUT_ddmmaa_000.xls` | Summit `REP_CAJA` | Compras/ventas del book `OPCIONES_FX`, montos y tasas |
| `Caja_Ini` y `Caja` D-1/D | Dataset diario | Inventario inicial, movimientos y saldo USD/COP |
| TRM D-1/D | `Insumo tasas.xlsx` / Dataset | `DELTA_PYG = saldo USD D-1 × variación TRM` |
| Primas, fees, vencimientos y cumplimientos | cartera Opciones/Forward del Dataset | Trading intradía y variación de inventario |
| `tbl_posicion_spot` | snapshot `risko.db`, book Opciones | Control de la posición de Caja |
| Tasas de fondeo COP/USD | hoy embebidas en `CAJA OPCIONES` | Costo de fondos acumulado |

Contribuciones ejecutadas: Delta PyG, Trading y costo de fondos. Theta, Rho,
Vega y CVA son cero.

## Insumos pendientes de mapear oficialmente

1. **Tasas de fondeo de Caja:** el libro usa para este corte 12 % E.A. COP y
   3,65 % USD 30 días en celdas, pero no identifica una fuente ALM versionada.
2. **PyG contable diario/SAP por producto:** necesario para calcular Épsilon sin
   depender del residual de `RESUMEN FINAL`.
3. **Snapshots históricos de `ENTRADA2.xlsb`:** el archivo de BDB se sobreescribe;
   para cortes pasados el único mercado preservado está dentro de cada Dataset.
4. **Eventos inmutables:** altas, bajas, ejercicios, vencimientos, primas y fees
   deben guardarse por fecha para reconstruir Trading sin usar el libro mensual.

Hasta mapear esos cuatro puntos, `PYG_OPCIONES_MES.xlsb` sigue siendo el baseline
histórico oficial y la salida se etiqueta `PRELIMINAR`.
