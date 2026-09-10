# Modulo Opciones en Risko

## Objetivo

El modulo `proyectos/position_monitor/procesos/opciones.py` calcula y publica la
posicion de opciones FX dentro de Position Monitor.

La posicion oficial de operaciones vigentes es la **sensibilidad spot** del
portafolio:

```text
POSICION_SENSIBILIDAD_USD = dV_COP / dSpot
```

Se calcula por diferencias finitas centradas con escenarios de TRM `+/-0.25%`.
La unidad resultante es USD porque:

```text
COP / (COP/USD) = USD
```

Importante: la posicion no es el valor teorico de la opcion ni se publica como
resultado de Black-Scholes. La valoracion teorica se usa solo como motor
intermedio para revalorar el portafolio en cada escenario de spot.

`Opciones_FF_V3.py` queda solo como referencia metodologica historica. El modulo
actual no lo importa, no lo ejecuta y no depende de ese archivo.

La salida canonica del producto es:

```text
FECHA | PRODUCTO | BOOK | POSICION | MONEDA_POSICION | LB_LT | INSTRUMENTO | COMPANY | CLASIFICACION_CONTABLE | BANKING_CVA_DVA
```

## Fuentes e insumos

El modulo lee siempre los insumos locales desde:

```text
datos/insumos
```

La carga de esos insumos debe hacerse desde Vector con el flujo `04_Opciones`
para la fecha seleccionada en la interfaz.

| Archivo | Origen | Contenido |
| --- | --- | --- |
| `USR_OPT_MANANA_ddmmaa_000.xls` | Summit `\\SUMMITFS001\apl\Internos\GR\FXOPTION_BASIC` | Libro de opciones |
| `ENTRADA2.xlsb` | Carpeta BDB | Curvas USD/COP y superficie de volatilidad |
| `Insumo tasas.xlsx` | Compliance de Tesoreria, hoja `TRM` | TRM `FORMADA` de la fecha exacta |

Regla de fecha del archivo Summit:

```text
El archivo generado en T+1 contiene la informacion de T.
Para corte 22/06/2026 se usa USR_OPT_MANANA_230626_000.xls.
```

Antes de calcular, el proceso valida que Vector haya dejado los insumos
esperados para la fecha de corte. Si falta un archivo, el proceso se detiene con
un mensaje explicito.

## Base de datos y salidas

La fuente maestra de consulta para la interfaz es SQLite.

| Entorno | Base | Tabla |
| --- | --- | --- |
| Produccion | `datos/base de datos/risko.db` | `tbl_posicion_opciones` |
| Pruebas | `datos/base de datos/risko_pruebas.db` | `tbl_posicion_opciones` |

Los archivos en `datos/position_monitor/procesados` se mantienen como soportes
operativos:

| Archivo | Uso |
| --- | --- |
| `Tbl_Posicion_Opciones.csv` | Copia de compatibilidad de la salida canonica |
| `Df_Insumo_Opciones_Depurado.xlsx` | Detalle auditado, posicion por book y control |

## Flujo de calculo

### 1. Lectura del portafolio

El reporte `USR_OPT_MANANA` se lee como texto separado por `;`.

El modulo:

- elimina cabeceras tecnicas;
- normaliza nombres de columnas;
- convierte fechas y numericos;
- conserva las columnas necesarias para posicion y liquidacion.

Columnas clave:

| Columna | Uso |
| --- | --- |
| `BOOK` | Libro de la operacion |
| `TIPO_DE_OPCION` | CALL o PUT |
| `POSICION_EN_LA_OPCION` | BUY o SELL |
| `NOMINAL` | Nominal en USD |
| `PRECIO_DE_EJERCICIO` | Strike en COP/USD |
| `FECHA_DE_VENCIMIENTO` | Fecha de vencimiento |
| `FECHA_DE_CUMPLIMIENTO` | Fecha de settlement |
| `MONEDA_CUMPLIMIENTO_REGLA` | Moneda usada para regla de vencidas |
| `Value amount exercised Sett Ccy` | Valor de liquidacion principal para vencidas |
| `VP Sett Ccy Y CVA` | Fallback de liquidacion si falta la columna principal |

### 2. Mercado

Desde los insumos complementarios se carga:

- TRM `FORMADA` desde la hoja `TRM`, columna B, para la fecha de corte de la columna A;
- curva COP;
- curva USD;
- superficie de volatilidad smile por plazo:
  `VOL_10D_PUT`, `VOL_25D_PUT`, `VOL_ATM`, `VOL_25D_CALL`, `VOL_10D_CALL`.

Para cada operacion vigente se calcula:

```text
PLAZO = fecha_vencimiento - fecha_corte
PLAZO_CUMPLIMIENTO = fecha_cumplimiento - fecha_corte
```

Luego se interpolan tasas COP y USD y se calcula el factor de descuento:

```text
fd = exp(tasa_cump * T_cump) / exp(tasa_venc * T_venc)
```

### 3. Volatilidad

El modulo interpola la superficie por plazo y resuelve la volatilidad cubica con
el mismo esquema usado por la referencia FF_V3.

Para la sensibilidad spot, la volatilidad no se congela en la TRM base. Se
recalcula para cada escenario:

```text
vol_up   = volatilidad_cubic(spot_up, ...)
vol_down = volatilidad_cubic(spot_down, ...)
```

Esto mantiene el calculo alineado con la metodologia de escenarios.

### 4. Sensibilidad spot para vigentes

Para cada operacion vigente:

```text
spot_up   = TRM * 1.0025
spot_down = TRM * 0.9975
d_spot    = spot_up - spot_down
```

En cada escenario se revalora la opcion en COP por USD de nominal. Esa
valoracion es un insumo tecnico, no la posicion publicada.

```text
valor_up_cop   = signo * (valor_escenario_up   / fd) * nominal
valor_down_cop = signo * (valor_escenario_down / fd) * nominal

signo = +1 para BUY
signo = -1 para SELL
```

La posicion oficial de la operacion es:

```text
POSICION_SENSIBILIDAD_USD =
    (valor_up_cop - valor_down_cop) / d_spot
```

Interpretacion:

- valor positivo: exposicion larga a USD/TRM;
- valor negativo: exposicion corta a USD/TRM;
- magnitud comparable con `delta * nominal`, pero calculada por sensibilidad del
  valor COP frente al spot.

`POSICION_DELTA_USD` se conserva solo como referencia analitica de control.
`POSICION_BUMP_USD` se mantiene como alias temporal de
`POSICION_SENSIBILIDAD_USD` para compatibilidad con soportes anteriores.

### 5. Regla para vencidas no cumplidas

Para operaciones no vigentes se aplica esta regla:

| Condicion | Posicion |
| --- | --- |
| `fecha_cumplimiento == fecha_corte` | `0` |
| `moneda_cumplimiento == COP` | `0` |
| Otro caso | `Value amount exercised Sett Ccy` |

Si la columna principal de liquidacion no existe, se usa `VP Sett Ccy Y CVA` como
fallback operativo.

## Regla final de posicion

| Estado de la operacion | `REGLA_POSICION` | `POSICION_FINAL_USD` |
| --- | --- | --- |
| Vigente | `SENSIBILIDAD_SPOT_VIGENTE` | `POSICION_SENSIBILIDAD_USD` |
| Vencida y cumple hoy | `VENCIDA_CUMPLE_HOY_CERO` | `0` |
| Vencida no cumplida en COP | `VENCIDA_NO_CUMPLIDA_COP_CERO` | `0` |
| Vencida no cumplida en otra moneda | `VENCIDA_NO_CUMPLIDA_VALOR_LIQUIDACION` | Valor de liquidacion |

## Construccion de tabla canonica

El detalle se agrupa primero por `BOOK` para soporte interno. Luego la salida
oficial para consolidacion colapsa el producto a una fila:

```text
BOOK            = "Opciones"
PRODUCTO        = "Opciones"
POSICION        = sum(POSICION_FINAL_USD)
MONEDA_POSICION = "USD"
LB_LT           = "Tesoreria"
INSTRUMENTO     = "Derivados"
BANKING_CVA_DVA = "Banking"
```

No se genera fila CVA/DVA para opciones.

## Columnas relevantes del detalle

| Columna | Descripcion |
| --- | --- |
| `PLAZO` | Dias a vencimiento desde fecha de corte |
| `PLAZO_CUMPLIMIENTO` | Dias a cumplimiento |
| `TASA_COP` | Tasa COP interpolada |
| `TASA_USD` | Tasa USD interpolada |
| `FACTOR_DE_DESCUENTO` | Ajuste entre vencimiento y cumplimiento |
| `VOLATILIDAD_CUBICA` | Volatilidad base calculada con TRM |
| `SPOT_UP` | Escenario TRM +0.25% |
| `SPOT_DOWN` | Escenario TRM -0.25% |
| `VOLATILIDAD_UP` | Volatilidad recalculada con `SPOT_UP` |
| `VOLATILIDAD_DOWN` | Volatilidad recalculada con `SPOT_DOWN` |
| `VALOR_ESCENARIO_UP_COP` | Valor COP del portafolio en escenario up |
| `VALOR_ESCENARIO_DOWN_COP` | Valor COP del portafolio en escenario down |
| `POSICION_DELTA_USD` | Delta analitico por nominal, solo control |
| `POSICION_SENSIBILIDAD_USD` | Sensibilidad spot oficial para vigentes |
| `POSICION_BUMP_USD` | Alias temporal de compatibilidad |
| `POSICION_VENCIDA_NO_CUMPLIDA_USD` | Valor de liquidacion para vencidas aplicables |
| `REGLA_POSICION` | Regla aplicada |
| `POSICION_FINAL_USD` | Posicion usada para consolidar |

## Relacion con FF_V3

La guia historica `Opciones_FF_V3.py` se uso para validar la metodologia, no como
dependencia tecnica.

El patron tomado de esa referencia es:

1. construir escenarios de spot alrededor de la TRM;
2. recalcular volatilidad y valor de la opcion en cada escenario;
3. medir la sensibilidad central del valor COP frente al spot;
4. usar esa sensibilidad como posicion en USD.

Por eso, si `Opciones_FF_V3.py` cambia o se elimina, el modulo productivo de
Risko debe seguir funcionando mientras sus insumos locales existan.

## Ejemplo resumido

Trade:

```text
CALL SELL
Nominal = 5,000,000 USD
TRM = 4,100
Strike = 4,050
```

Escenarios:

```text
spot_up   = 4,100 * 1.0025 = 4,110.25
spot_down = 4,100 * 0.9975 = 4,089.75
d_spot    = 20.50
```

Si la revaloracion del portafolio da:

```text
valor_up_cop   = -785,000,000
valor_down_cop = -705,000,000
```

Entonces:

```text
POSICION_SENSIBILIDAD_USD =
    (-785,000,000 - (-705,000,000)) / 20.50
  = -3,902,439 USD
```

El signo negativo indica exposicion corta a USD/TRM para ese trade.

## Validaciones de soporte

Si el resultado luce distinto al esperado:

1. Abrir `Df_Insumo_Opciones_Depurado.xlsx`, hoja `Control`.
2. Verificar que TRM, fecha e insumos correspondan a la fecha seleccionada.
3. Revisar `Detalle.REGLA_POSICION` para confirmar si la operacion fue vigente o vencida.
4. Comparar `POSICION_SENSIBILIDAD_USD` contra `POSICION_DELTA_USD` solo como control.
5. Revisar `SPOT_UP`, `SPOT_DOWN`, `VOLATILIDAD_UP` y `VOLATILIDAD_DOWN` si hay diferencias grandes.
6. Validar que la suma de `Posicion_Por_Book.POSICION` coincida con la fila canonica publicada.

Si falta un insumo, revisar que Vector haya copiado para la fecha:

- `USR_OPT_MANANA_*`;
- `ENTRADA2.xlsb`;
- `Insumo tasas.xlsx`.

## Archivos relacionados

- `proyectos/position_monitor/procesos/opciones.py`
- `proyectos/position_monitor/procesos/Opciones_FF_V3.py` solo como referencia historica
- `aplicaciones/interfaz_risko/servicios/position_monitor.py`
- `proyectos/position_monitor/procesos/consolidacion.py`
- `proyectos/position_monitor/configuracion/param_libros.csv`
