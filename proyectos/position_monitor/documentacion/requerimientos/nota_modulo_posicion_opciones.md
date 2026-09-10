# Nota previa de analisis del modulo de posicion de opciones para Risko

> Nota de vigencia (04/08/2026): este archivo documenta el script legado
> `Opciones_FF_V3.py`. El proceso productivo esta en `opciones.py`, usa
> `Insumo tasas.xlsx`/`TRM`/`FORMADA` y se describe en `posicion_opciones.md` y
> `mapa_produccion_y_ejemplos_calculo.md`.

## Objetivo

Documentar la logica actual de `Opciones_FF_V3.py` para reutilizar unicamente el calculo de posicion de opciones en Risko, separando:

- que insumos son realmente necesarios,
- como se calcula el delta,
- como debe quedar la regla de posicion final,
- y que vacios del requerimiento conviene cerrar antes de construir el modulo.

## Hallazgos principales

- El requerimiento formal de opciones indica que la posicion debe salir del **delta calculado en Python**, no del `Delta` que viene en el reporte.
- El script legado `Opciones_FF_V3.py` si calcula el delta propio de opciones, pero la variable final `Deltaopc` solo suma el delta de operaciones vigentes.
- La regla nueva del requerimiento para **vencidas no cumplidas** no esta integrada hoy en esa salida final de posicion.
- El archivo `USR_OPT_FWD_*.xls` no participa en el calculo del delta de opciones. En el script viejo aparece porque el archivo es monolitico y tambien procesa forwards.

## Archivos involucrados

### Insumo obligatorio para opciones

- `\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_MANANA_ddmmaa_000.xls`

Uso:

- contiene las operaciones de opciones,
- aporta las columnas de negocio para calcular plazo, moneda de cumplimiento, nominal, strike, tipo de opcion y book.

### Insumo secundario o de referencia

- `\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\INSUMOS\USR_OPT_FWD_ddmmaaaa_000.xls`

Uso:

- sirve como referencia de la regla de posicion de forwards,
- en el corte revisado trae solo `BOOK = OPCIONES_FX`,
- no es necesario para recalcular el delta de opciones,
- solo seria necesario si el modulo de opciones termina incorporando tambien alguna logica complementaria del libro forward asociado.

### Insumos de mercado que usa hoy el script legado

- `\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\Datos Mercado\Curva Forward V2.xlsm`
  - hoja `Matriz TC`
  - se usa para obtener la TRM spot.
- `\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb`
  - hoja `INFOVALMER`
  - columnas `A:C`: curva USD,
  - columnas `E:G`: curva COP,
  - columnas `I:N`: superficie de volatilidad.
- `\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\BDB\ENTRADA2.xlsb`
  - hoja `BASE`
  - se usa para construir la tabla de `Tasa Fix / TRM1` del legado.

## Columnas necesarias del archivo `USR_OPT_MANANA`

### Minimas para delta y posicion vigente

- `Trade Id`
- `Book`
- `Identificacion contraparte`
- `Posicion en la opcion`
- `Tipo de opcion`
- `Fecha de Vencimiento`
- `Fecha de Cumplimiento`
- `Nominal`
- `Precio de Ejercicio`
- `Moneda cumplimiento`
- `Modalidad Cumplimiento`

### De control o auditoria

- `Delta`
  - en el legado se renombra a `Delta 1` y queda solo como referencia del reporte.
- `Volatilidad`
- `Value Amount`
- `CVA Fair Value COP`
- `Spread CVA`
- `Moneda de la Prima`

## Paso a paso de la logica actual

### 1. Carga y depuracion del archivo de opciones

Fuente en el legado:

- `USR_OPT_MANANA_ddmmaa_000.xls`

Tratamiento actual:

- se lee como texto,
- se separa por `;`,
- se eliminan filas de encabezado operativo,
- se toma la fila de nombres como header real,
- se convierten fechas y numericos,
- se ordena por `Fecha de Vencimiento`,
- el `Delta` del archivo se renombra a `Delta 1`.

## 2. Determinacion de moneda de cumplimiento para valoracion

El legado crea una columna nueva:

- `Moneda Cumplimiento`

Regla:

- si `Identificacion contraparte` empieza por `4444` => `USD`
- en otro caso => `COP`

Observacion:

- esta columna derivada se usa para valorar y para el delta,
- pero la columna original `Moneda cumplimiento` se sigue usando en otras partes del script,
- en el corte revisado hay filas con `Moneda cumplimiento` vacia,
- no se encontraron diferencias entre la moneda fuente no vacia y la moneda derivada.

## 3. Calculo de plazo

- `Plazo = Fecha de Vencimiento - Fecha de valoracion`
- se expresa en dias.

## 4. Tasas de descuento

Para cada operacion:

- `Tasa Cop` se interpola desde la curva COP,
- `Tasa Usd` se interpola desde la curva USD.

Funcion usada:

- `Interpolacion_Tasa(...)`

## 5. Superficie de volatilidad

El legado usa la hoja `INFOVALMER` para construir:

- smile `10D PUT`,
- `25D PUT`,
- `ATM`,
- `25D CALL`,
- `10D CALL`.

Luego calcula por operacion:

- una volatilidad inicial por strike con `Zigma_Option(...)`,
- una volatilidad ajustada con `Volatilidad_cubic(...)`.

## 6. Formula de delta

Funcion usada:

- `delta_opcion(...)`

Formula para `T > 0`:

- `T = dias_a_vencimiento / 365`
- `d1 = [ln(S/K) + (Rd - Rf + 0.5 * sigma^2) * T] / [sigma * sqrt(T)]`
- Call:
  - `delta = exp(-Rf*T) * N(d1)`
- Put:
  - `delta = exp(-Rf*T) * (N(d1) - 1)`

Luego el delta se lleva a posicion multiplicando por signo y nominal:

- `BUY` => `+Nominal`
- `SELL` => `-Nominal`

En el legado:

- `Delta_trade = delta_opcion(...) * sign_nominal(Posicion en la opcion, Nominal)`

## 7. Regla especial en fecha de vencimiento

Aunque `delta_opcion()` tiene manejo para `T = 0`, la asignacion final del legado fuerza:

- si `Fecha de Vencimiento == fecha de corte` => `Delta = 0`

Es decir:

- el modulo viejo no deja delta residual el mismo dia del vencimiento.

## 8. Posicion actual que entrega realmente el legado

La salida final del script para opciones es:

- `Deltaopc = opc['Delta'].sum()`

Esto significa:

- suma solo el delta de operaciones vigentes,
- no incorpora aun la regla nueva de vencidas no cumplidas pedida en el requerimiento.

## Regla faltante para completar la posicion en Risko

El requerimiento funcional dice:

- la posicion debe salir del delta calculado en Python,
- y debe mapearse la posicion de operaciones vencidas no cumplidas.

Traduccion operativa propuesta:

- `Posicion final = Delta vigente + Posicion de vencidas no cumplidas`

### Regla de vencidas no cumplidas

Para operaciones con `Fecha de Vencimiento <= fecha de corte`:

- si `Fecha de Cumplimiento == fecha de corte` => `0`
- si `Fecha de Cumplimiento != fecha de corte` y `Moneda cumplimiento == COP` => `0`
- si `Fecha de Cumplimiento != fecha de corte` y `Moneda cumplimiento != COP` => tomar valor de liquidacion

## Como lo hace hoy el legado para ese residual

El script viejo no lo suma a `Deltaopc`, pero si calcula columnas auxiliares:

- `Tasa Fix`
- `Cuentas por Cumplir`
- `USD`
- `COP`

Funciones relacionadas:

- `tfix(...)`
- `Cuentas_Por_opc(...)`
- `Vencimiento(...)`

Eso quiere decir que hay dos caminos posibles para Risko:

- replicar la logica exacta del legado con `Tasa Fix` y formulas,
- o usar directamente un campo del reporte para el residual de vencidas no cumplidas, si negocio confirma que ese campo es la fuente oficial.

## Punto importante sobre el valor de liquidacion

Antes de construir el modulo conviene definir cual sera la fuente oficial del residual:

- opcion A: recalcularlo como hoy lo hace `Opciones_FF_V3.py`,
- opcion B: tomarlo directamente de una columna del reporte.

En el insumo de opciones existen campos candidatos, por ejemplo:

- `Value amount exercised Sett Ccy`
- `Value amount exercised COP`
- `VP Sett Ccy Y CVA`

Pero el script legado no usa esos campos para la posicion final de opciones. Por eso este punto debe cerrarse antes de implementar.

## Recomendacion de implementacion para Risko

### Alcance minimo recomendado

Construir un modulo nuevo de opciones con este flujo:

1. cargar `USR_OPT_MANANA`,
2. cargar TRM, curva USD, curva COP y superficie de volatilidad,
3. recalcular `Delta` propio por operacion,
4. separar vigentes vs vencidas/no cumplidas,
5. construir `POSICION = Delta + residual vencidas no cumplidas`,
6. agrupar por `BOOK`,
7. homologar con `param_libros.csv`,
8. publicar en el mismo layout canonico de Position Monitor.

### Ajustes tecnicos que Risko necesitara

- nuevas rutas en `param_rutas.csv` para el insumo de opciones,
- nuevas constantes de salida en `compartido/nucleo_risko/rutas.py`,
- un proceso `opciones.py`,
- integracion en `aplicaciones/interfaz_risko/servicios/position_monitor.py`,
- incluir opciones en `consolidacion.py`.

## Decisiones pendientes antes de programar

### 1. Granularidad de salida

Hay que confirmar si la salida debe quedar:

- por cada `Book` del archivo de opciones,
- o como una sola fila agregada tipo `OPCIONES_FX`.

Motivo:

- el insumo de opciones trae books reales como `EMPRESAR_BOG`, `CORPORAT_BOG`, `OCCIDENT_CEO`, etc.,
- pero la hoja `Salida` del requerimiento muestra una fila ejemplo con `BOOK = OPCIONES_FX`,
- y el script legado de opciones hoy suma todo en un unico `Deltaopc`.

### 2. Fuente oficial para vencidas no cumplidas

Hay que definir si se usara:

- la formula legado con `Tasa Fix`,
- o una columna ya calculada del reporte.

### 3. Normalizacion de moneda de cumplimiento

Hay que decidir si el modulo final trabajara con:

- la moneda derivada por prefijo de contraparte,
- la moneda fuente del reporte,
- o una regla unificada: usar fuente y completar vacios.

### 4. Parametrizacion de books historicos

En el corte actual revisado, los books del archivo de opciones si tienen cobertura en `param_libros.csv`.

Pero en la referencia historica de `opciones_20261028.xlsx` aparece al menos un book adicional:

- `COSTA_A_CEO`

Si la salida va por `BOOK`, ese valor deberia quedar homologado en `param_libros.csv`.

## Validaciones observadas en la revision

- `USR_OPT_MANANA_180626_000.xls`:
  - 2610 filas de operaciones,
  - books presentes: `ANTIOQUI_CEO`, `CORPORAT_BOG`, `EMPRESAR_BOG`, `INSTITUC_BOG`, `MEDIANA`, `OCCIDENT_CEO`,
  - 272 filas con `Moneda cumplimiento` vacia,
  - no se encontraron diferencias entre la moneda derivada por prefijo y la moneda fuente cuando la fuente no viene vacia.
- Para el corte revisado no aparecieron operaciones de opciones vencidas no cumplidas, por lo que esa regla debera probarse con un caso historico o sintetico.
- `USR_OPT_FWD_18062026_000.xls`:
  - 92 filas,
  - todas con `BOOK = OPCIONES_FX`.

## Conclusion practica

Si el objetivo inmediato es llevar solo la posicion de opciones a Risko, el archivo realmente indispensable es `USR_OPT_MANANA`, mas los insumos de mercado para recalcular delta.

`USR_OPT_FWD` no es necesario para el delta de opciones; solo sirve como referencia del libro forward asociado o de reglas compartidas.

La mayor definicion pendiente no es tecnica sino funcional:

- confirmar si la salida de Risko sera por `BOOK` real del archivo de opciones o en una sola fila `OPCIONES_FX`,
- y definir de donde saldra exactamente el residual de vencidas no cumplidas.
