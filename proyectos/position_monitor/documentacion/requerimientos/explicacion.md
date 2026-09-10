# Explicación de negocio de Swaps y Opciones en Risko

> Nota de vigencia (04/08/2026): este documento conserva una explicacion del
> analisis inicial. Para la implementacion actual de Opciones, incluida la
> sensibilidad spot y la TRM `FORMADA` desde `Insumo tasas.xlsx`, consultar
> `posicion_opciones.md` y `mapa_produccion_y_ejemplos_calculo.md`.

## 1. Qué está midiendo realmente Position Monitor

Lo primero importante es esto: `Position Monitor` no siempre está midiendo el "valor total del negocio" ni el "fair value completo" de cada operación.

Lo que está intentando medir es, más bien, la **posición o exposición que sigue viva para la fecha de corte**.

Eso cambia bastante la lectura:

- en `Swaps`, la lógica actual mira **flujos futuros que todavía siguen expuestos**;
- en `Opciones`, la lógica actual mira **delta mientras la opción sigue viva**;
- y cuando la opción ya no está viva, deja de tratarla como sensibilidad y la trata como **residual de liquidación**.

Si uno no tiene clara esa idea, puede esperar una cifra y el módulo le va a entregar otra.

## 2. Desde lo más básico: qué es un Swap

Un `swap` sobre divisas puede leerse, en términos simples, como un negocio donde dos partes intercambian flujos futuros en monedas distintas.

Para Position Monitor, el punto práctico no es "revalorar el contrato completo desde cero", sino preguntar:

**qué flujos todavía faltan y en cuáles todavía tengo riesgo en moneda distinta de COP**.

### Idea intuitiva

Si un flujo:

- ya se pagó, ya no genera posición;
- si el flujo pendiente está en `COP`, la lógica actual lo deja en `0` para este reporte;
- si el flujo pendiente está en una moneda en riesgo distinta de `COP`, la lógica toma el `VP MONEDA EN RIESGO`.

Entonces, en este módulo, el swap no se está leyendo como "un solo derivado gigante", sino como una **suma de flujos**.

## 3. Desde lo más básico: qué es una Opción

Una `opción` es el derecho, pero no la obligación, de comprar o vender una moneda a una tasa pactada (`strike`) en una fecha futura o alrededor de ella, según la estructura.

### Conceptos mínimos

- `Call`: derecho a comprar.
- `Put`: derecho a vender.
- `Strike`: tasa pactada.
- `Spot`: tasa de mercado del día, en este caso la `TRM` usada por el módulo.
- `Nominal`: monto base de la operación.
- `Buy`: el banco está comprado en la opción.
- `Sell`: el banco está vendido en la opción.

### Qué significa el delta

El `delta` responde a esta idea:

**si el spot se mueve un poco, cuánto cambia la exposición de la opción**.

En lenguaje sencillo, el delta convierte una opción en una especie de "equivalente aproximado en USD".

Ejemplo simple:

- si una opción vigente tiene `delta = 0.40`,
- y el nominal es `1,000,000 USD`,
- una compra (`BUY`) aporta aproximadamente `+400,000 USD` de posición;
- una venta (`SELL`) aporta aproximadamente `-400,000 USD`.

Eso no es el valor total de la prima ni el P&G completo. Es la **sensibilidad de posición**.

## 4. Qué hace exactamente Swaps hoy en Risko

El comportamiento real que hoy tiene `proyectos/position_monitor/procesos/swaps.py` es este.

### Paso 1. Toma una fecha de corte

La fecha que el usuario escoge en la interfaz es la fecha de corte oficial de la salida.

### Paso 2. Si el día no es hábil, usa el último día hábil como fuente

Si la fecha elegida no es hábil:

- la salida sigue quedando con la fecha que escogió el usuario;
- pero el archivo fuente que se usa para leer la información es el del último día hábil anterior.

Esto es importante porque negocio puede ver, por ejemplo, una salida con fecha domingo, pero alimentada con el viernes.

### Paso 3. Lee dos universos contables

Lee dos reportes:

- `Banking`
- `IFRS`

Luego ambos pasan por la misma regla.

### Paso 4. Depura el insumo

Deja solo columnas relevantes y limpia tipos, pero la lógica de posición de negocio realmente depende sobre todo de:

- `DATE`
- `MONEDA EN RIESGO`
- `VP MONEDA EN RIESGO`
- `BOOK`

### Paso 5. Regla exacta de posición por flujo

La regla implementada hoy es esta:

```text
si DATE < fecha_corte => POSICION_USD = 0
si DATE >= fecha_corte y MONEDA EN RIESGO = COP => POSICION_USD = 0
si DATE >= fecha_corte y MONEDA EN RIESGO != COP => POSICION_USD = VP MONEDA EN RIESGO
```

### Qué significa en negocio

- un flujo pasado ya no existe para posición;
- un flujo pendiente en `COP` no deja exposición para esta métrica;
- un flujo pendiente en moneda en riesgo distinta de `COP` sí deja exposición, y se toma su valor presente.

### Matiz importante

La condición es `DATE < fecha_corte`, no `DATE <= fecha_corte`.

Eso significa que:

- si el flujo cae exactamente el mismo día de corte,
- ese flujo todavía entra a evaluación;
- solo quedará en cero si su `MONEDA EN RIESGO` es `COP`.

Ese detalle sí es deliberado en la implementación actual.

### Paso 6. Agrupa por BOOK

Después de calcular la posición por flujo, el módulo suma por `BOOK`.

O sea:

- primero piensa flujo por flujo;
- después entrega una posición agregada por libro.

### Paso 7. Construye tres vistas

Se publican:

- `Banking`
- `IFRS`
- `CVA/DVA`

Y `CVA/DVA` se calcula como:

```text
CVA/DVA = IFRS - Banking
```

## 5. Mi lectura de negocio sobre Swaps

Para el requerimiento funcional revisado, la lógica de `Swaps` sí está bien aplicada.

De hecho, está muy alineada con el Excel funcional:

- elimina flujos anteriores a la fecha de corte;
- elimina flujos con moneda en riesgo `COP`;
- toma `VP MONEDA EN RIESGO` en los demás casos;
- y calcula `IFRS - Banking`.

### Lo que sí conviene entender

Esto **no** es una valoración integral del swap.

Es una regla de posición operativa para el tablero.

Si alguien espera que la cifra represente:

- el MTM total del swap,
- el nocional neto,
- o toda la exposición económica del contrato,

se puede confundir, porque este módulo no está diseñado para eso.

## 6. Qué hace exactamente Opciones hoy en Risko

El comportamiento real que hoy tiene `proyectos/position_monitor/procesos/opciones.py` es este.

## 6.1. Insumos que usa

El módulo siempre busca los archivos en `datos/insumos`.

Usa:

- `USR_OPT_MANANA_ddmmaa_000.xls`
- `USR_OPT_FWD_ddmmaaaa_000.xls`
- `ENTRADA2.xlsb`
- `Curva Forward V2.xlsm`

### Qué aporta cada uno

- `USR_OPT_MANANA`: trae las operaciones.
- `USR_OPT_FWD`: hoy se carga como referencia y control operativo, no como insumo matemático de la fórmula final.
- `ENTRADA2.xlsb`: trae curvas y superficie de volatilidad.
- `Curva Forward V2.xlsm`: aporta la `TRM spot`.

## 6.2. Qué columnas del negocio le importan de verdad

Para entender la lógica, las columnas más importantes son:

- `BOOK`
- `Fecha de Vencimiento`
- `Fecha de Cumplimiento`
- `Nominal`
- `Precio de Ejercicio`
- `Tipo de Opción`
- `Posición en la opción`
- `Moneda cumplimiento`
- `Moneda de la prima`
- `VP Sett Ccy Y CVA`

## 6.3. Cómo calcula la posición de una opción vigente

Mientras la opción sigue viva, la posición sale del `delta`.

La secuencia real es:

### Paso 1. Calcula el plazo

Calcula:

- `PLAZO = Fecha de Vencimiento - fecha de corte`
- `PLAZO_CUMPLIMIENTO = plazo hasta cumplimiento`

### Paso 2. Trae tasas de mercado

Interpola:

- tasa `COP`
- tasa `USD`

según el plazo de la operación.

### Paso 3. Trae la superficie de volatilidad

Para el plazo correspondiente, interpola los nodos de smile:

- `10D PUT`
- `25D PUT`
- `ATM`
- `25D CALL`
- `10D CALL`

### Paso 4. Ajusta una volatilidad cúbica

No usa solo una volatilidad plana.

Hace un ajuste con `spline` cúbico para obtener una volatilidad más consistente con el tipo de opción y su delta.

En negocio, esto significa que la opción no se está valorando con una sola volatilidad "promedio", sino con una sonrisa de volatilidad.

### Paso 5. Calcula el delta unitario

La fórmula base es la de Black-Scholes para FX:

```text
T = dias_a_vencimiento / 365
d1 = [ln(S/K) + (Rd - Rf + 0.5*sigma^2)*T] / [sigma*sqrt(T)]
```

Luego:

- `Call = exp(-Rf*T) * N(d1)`
- `Put = exp(-Rf*T) * (N(d1) - 1)`

Donde:

- `S` es el spot (`TRM`);
- `K` es el strike;
- `Rd` es la tasa COP;
- `Rf` es la tasa USD;
- `sigma` es la volatilidad ajustada.

### Paso 6. Lo lleva a posición

Después aplica signo por compra o venta:

- `BUY => +1`
- `SELL => -1`

Y calcula:

```text
POSICION_DELTA_USD = DELTA_UNITARIO * signo * NOMINAL
```

Eso es lo que aporta cada opción vigente.

### Qué significa técnicamente "revalorar" en este módulo

Aquí hay un matiz importante.

En el módulo actual de Risko, `Opciones` no publica como salida final el precio teórico completo de Black-Scholes de cada trade.

Lo que sí hace es:

- tomar mercado del día;
- reconstruir tasas y superficie;
- recalcular la volatilidad consistente con la sonrisa;
- recalcular el `delta` con ese mercado;
- y convertir ese delta a posición.

Entonces, si uno lo dice con precisión:

- **sí hay revaloración técnica del insumo de mercado**;
- pero la salida final no es "precio teórico de la opción", sino **posición delta o residual de liquidación**.

### Qué columnas técnicas genera el cálculo

Para cada trade el módulo deja, entre otras, estas columnas intermedias:

- `PLAZO`
- `PLAZO_CUMPLIMIENTO`
- `TASA_COP`
- `TASA_USD`
- `FACTOR_DE_DESCUENTO`
- `VOL_10D_PUT`
- `VOL_25D_PUT`
- `VOL_ATM`
- `VOL_25D_CALL`
- `VOL_10D_CALL`
- `VOLATILIDAD_CUBICA`
- `DELTA_UNITARIO_CALCULADO`
- `POSICION_DELTA_USD`

Eso permite auditar el cálculo fila por fila.

### Cómo arma las curvas

Desde `ENTRADA2.xlsb`, hoja `INFOVALMER`, toma:

- columnas `A:C` para curva USD;
- columnas `E:G` para curva COP;
- columnas `I:N` para la superficie de volatilidad.

La `TRM` spot la toma desde `Curva Forward V2.xlsm`, hoja `Matriz TC`.

### Cómo interpola tasas

Para un plazo cualquiera, el módulo no busca un solo nodo exacto.

Hace esto:

1. ubica el rango donde cae el plazo;
2. toma un `plazo inferior` y un `plazo superior`;
3. toma la tasa del nodo inferior y la del superior;
4. interpola linealmente.

La forma conceptual es:

```text
proporcion_inferior = 1 - ((plazo - plazo_inferior) / (plazo_superior - plazo_inferior))
tasa_plazo = proporcion_inferior * tasa_inferior + (1 - proporcion_inferior) * tasa_superior
```

Eso se hace tanto para la curva `COP` como para la curva `USD`.

### Cómo usa el plazo de cumplimiento

Además del plazo hasta vencimiento, el código calcula:

```text
PLAZO_CUMPLIMIENTO = PLAZO + (Fecha de Cumplimiento - Fecha de Vencimiento)
```

Con eso obtiene un `FACTOR_DE_DESCUENTO` que se usa dentro del ajuste de volatilidad:

```text
FACTOR_DE_DESCUENTO =
exp((tasa_usd_cumplimiento * plazo_cumplimiento) / 365)
/
exp((tasa_usd_vencimiento * plazo_vencimiento) / 365)
```

Este punto es técnico pero importante:

- el factor no entra a la fórmula final de delta;
- entra en la iteración que busca la volatilidad consistente con la sonrisa para esa operación.

### Cómo construye la sonrisa de volatilidad

La superficie le entrega cinco nodos por plazo:

- `10D PUT`
- `25D PUT`
- `ATM`
- `25D CALL`
- `10D CALL`

El módulo trabaja con nodos de delta:

```text
[0.10, 0.25, 0.50, 0.75, 0.90]
```

Y hace dos cosas:

1. interpola primero por plazo los cinco nodos;
2. después interpola por delta con `spline` cúbico natural.

### Cómo obtiene la volatilidad cúbica

La función técnica hace una iteración.

La lógica es esta:

1. arranca con `sigma = vol_atm`;
2. calcula un `d1` provisional;
3. de ese `d1` obtiene un delta provisional;
4. con ese delta va a la sonrisa y toma una nueva `sigma` por `spline`;
5. repite hasta converger o llegar al máximo de iteraciones.

La estructura conceptual es:

```text
sigma_0 = vol_atm
delta_iteracion = 0.50

repetir:
    d1 = [ln(S/K) + (Rd - Rf + 0.5*sigma^2)*T] / [sigma*sqrt(T)]
    delta_iteracion = delta_con_ajuste(d1)
    sigma_nueva = spline(smile, delta_iteracion)
hasta convergencia
```

Detalles finos de implementación:

- para `PUT` usa el smile en orden natural;
- para `CALL` usa el smile invertido;
- si el delta cae fuera del rango, el código recorta al extremo más cercano;
- si `PLAZO <= 0`, deja la volatilidad y el delta en `0`.

### Fórmula exacta del delta que sí publica el módulo

Con la `sigma` ya ajustada, el delta final se calcula así:

```text
T = plazo / 365
d1 = [ln(S/K) + (Rd - Rf + 0.5*sigma^2)*T] / [sigma*sqrt(T)]
```

Luego:

- `CALL = exp(-Rf*T) * N(d1)`
- `PUT = exp(-Rf*T) * (N(d1) - 1)`

Y finalmente:

```text
POSICION_DELTA_USD = DELTA_UNITARIO_CALCULADO * signo(BUY/SELL) * NOMINAL
```

### Qué pasa si el trade ya no tiene plazo positivo

Si `PLAZO <= 0`, el módulo no intenta seguir valorizando delta.

En ese caso:

- deja en `0` las columnas técnicas de mercado de esa fila;
- y luego la posición final la resuelve con la regla de vencidas o cumplimiento.

### Aclaración sobre la palabra "flujo" en opciones

En `Swaps`, la unidad natural es el flujo.

En `Opciones`, técnicamente la unidad que procesa el módulo es el `trade` o la operación del reporte.

Entonces, cuando abajo hablo de "ejemplo de un flujo" en opciones, en realidad se trata de **una fila/trade del archivo**.

### Ejemplo real 1: una opción vigente del corte 18-06-2026

Tomando una fila real del archivo procesado:

- `TRADE_ID = 2235157CO`
- `BOOK = CORPORAT_BOG`
- `TIPO_DE_OPCION = CALL`
- `POSICION_EN_LA_OPCION = SELL`
- `NOMINAL = 1,100,000`
- `STRIKE = 4,185.00`
- `FECHA_CORTE = 18/06/2026`
- `FECHA_DE_VENCIMIENTO = 02/07/2027`
- `FECHA_DE_CUMPLIMIENTO = 06/07/2027`
- `PLAZO = 379`
- `PLAZO_CUMPLIMIENTO = 383`
- `TRM = 3,439.91`

Mercado interpolado que usó el módulo:

- `TASA_COP = 0.1162580809625764`
- `TASA_USD = 0.03177989877143732`
- `FACTOR_DE_DESCUENTO = 1.000348333517284`

Smile interpolado para ese plazo:

- `VOL_10D_PUT = 0.1465258064516129`
- `VOL_25D_PUT = 0.1466258064516129`
- `VOL_ATM = 0.1535990322580645`
- `VOL_25D_CALL = 0.1715918279569892`
- `VOL_10D_CALL = 0.1960516129032258`

Volatilidad final que resolvió la iteración:

- `VOLATILIDAD_CUBICA = 0.1668765920747999`

Ahora la fórmula:

```text
T = 379 / 365 = 1.0383561643835617

d1 =
[ln(3439.91 / 4185.00) + (0.1162580809625764 - 0.03177989877143732 + 0.5*0.1668765920747999^2) * 1.0383561643835617]
/
[0.1668765920747999 * sqrt(1.0383561643835617)]

d1 = -0.5521124788095965
```

Luego:

```text
N(d1) = 0.2904356463998502

Delta Call =
exp(-0.03177989877143732 * 1.0383561643835617) * 0.2904356463998502

Delta Call = 0.2810080090642372
```

Como es `SELL`, el signo es `-1`.

Entonces:

```text
POSICION_DELTA_USD =
0.2810080090642372 * (-1) * 1,100,000

POSICION_DELTA_USD = -309,108.8099706609
```

Y como el trade sigue vigente:

- `REGLA_POSICION = DELTA_VIGENTE`
- `POSICION_FINAL_USD = -309,108.8099706609`

Eso significa:

- la opción todavía está viva;
- por eso el módulo no usa valor de liquidación;
- usa delta recalculado con mercado del día;
- y el aporte de esa sola operación al libro es `-309,108.81 USD`.

### Ejemplo real 2: una opción vencida que cumple justo el día de corte

Otra fila real del mismo corte:

- `TRADE_ID = 2231144CO`
- `BOOK = EMPRESAR_BOG`
- `TIPO_DE_OPCION = PUT`
- `POSICION_EN_LA_OPCION = SELL`
- `NOMINAL = 10,000`
- `STRIKE = 4,393.70`
- `FECHA_DE_VENCIMIENTO = 17/06/2026`
- `FECHA_DE_CUMPLIMIENTO = 18/06/2026`
- `MONEDA_CUMPLIMIENTO_REGLA = COP`
- `VALOR_LIQUIDACION_REPORTE = -9,534,537.52`

Aun así, la salida final queda:

- `REGLA_POSICION = VENCIDA_CUMPLE_HOY_CERO`
- `POSICION_FINAL_USD = 0`

¿Por qué?

Porque la regla de negocio dice:

```text
si Fecha de Cumplimiento = fecha de corte => posición 0
```

Este ejemplo es útil porque muestra que:

- el reporte sí puede traer un valor de liquidación;
- pero ese valor no siempre se usa;
- primero manda la regla de negocio de cumplimiento.

### Qué no vi en este corte

En el corte del `18/06/2026` sí aparecieron:

- `DELTA_VIGENTE`
- `VENCIDA_CUMPLE_HOY_CERO`
- `VENCIDA_NO_CUMPLIDA_COP_CERO`

No apareció un caso de:

- `VENCIDA_NO_CUMPLIDA_VALOR_LIQUIDACION`

O sea, en este corte no encontré una opción ya vencida, no cumplida y con moneda de cumplimiento distinta de `COP` para mostrar ese último camino con un ejemplo real.

## 6.4. Qué pasa cuando la opción ya venció

Aquí está la parte más importante del negocio.

La lógica actual distingue entre:

- opción vigente;
- opción vencida o que vence en la fecha de corte.

La condición exacta es:

```text
si fecha_corte < fecha_vencimiento => la opción sigue vigente
si fecha_corte >= fecha_vencimiento => ya no se trata como opción viva
```

O sea:

- el mismo día del vencimiento ya no usa delta;
- eso está alineado con la lógica histórica del legado.

## 6.5. Regla exacta para vencidas no cumplidas

Si la opción ya no está vigente, la posición final ya no sale del delta.

Se aplica esta regla:

```text
si fecha_cumplimiento = fecha_corte => 0
si fecha_cumplimiento != fecha_corte y moneda_cumplimiento = COP => 0
si fecha_cumplimiento != fecha_corte y moneda_cumplimiento != COP => valor de liquidación
```

### Qué significa en negocio

- si hoy justo se cumple, el residual se considera cerrado para esta métrica;
- si no se ha cumplido, pero el cumplimiento será en `COP`, la posición queda en `0`;
- si no se ha cumplido y el cumplimiento será en moneda distinta de `COP`, entonces ya no se mide por delta sino por el valor pendiente de liquidar.

## 6.6. De dónde sale el valor de liquidación

La implementación actual tomó como fuente principal:

- `VP Sett Ccy Y CVA`

Y dejó `fallback` técnico a:

- `Value amount exercised Sett Ccy`
- `Monto Ejercicio`

Esto se hizo porque el requerimiento funcional pedía tomar el valor de liquidación registrado en la columna `BM`, y en la estructura operativa actual la mejor correspondencia encontrada fue ese campo principal con esos respaldos.

## 6.7. Regla de moneda de cumplimiento cuando viene vacía

La lógica actual no se queda bloqueada si `Moneda cumplimiento` viene vacía.

Hace esta resolución:

1. usa `Moneda cumplimiento` si viene informada;
2. si no viene, usa `Moneda de la prima`;
3. si tampoco viene, aplica una regla auxiliar:
   `si la identificación de contraparte empieza por 4444 => USD; de lo contrario => COP`.

Esto no es una fórmula financiera. Es una decisión operativa para no dejar la regla de vencidas sin moneda de referencia.

## 6.8. Cómo queda la posición final

La lógica final por trade es esta:

```text
si está vigente => POSICION_FINAL_USD = POSICION_DELTA_USD
si venció y cumple hoy => POSICION_FINAL_USD = 0
si venció y no cumple hoy, pero liquida en COP => POSICION_FINAL_USD = 0
si venció y no cumple hoy, y no liquida en COP => POSICION_FINAL_USD = VALOR_LIQUIDACION_REPORTE
```

Después de eso:

- se suma por `BOOK`;
- se homologa con `param_libros.csv`;
- y se publica en el layout estándar de Risko.

## 7. Mi lectura de negocio sobre Opciones

Mi conclusión es que la lógica actual de `Opciones` está bien aplicada en lo esencial, pero con matices que sí vale la pena tener presentes.

### Lo que sí está correctamente alineado

- la posición de opciones vigentes sale del delta calculado en Python;
- no depende del delta que venga reportado en el archivo;
- las vencidas no cumplidas siguen la regla pedida por el requerimiento funcional;
- el mismo día del vencimiento ya no se usa delta;
- la salida final se entrega por `BOOK`.

### El punto más importante a tener en cuenta

El legado grande (`Opciones_FF_V3.py`) mezcla varias cosas:

- valoración de libro,
- griegas,
- shocks,
- y una sensibilidad numérica a nivel portafolio.

En cambio, el módulo nuevo de Risko hace algo más limpio y auditable para Position Monitor:

- calcula delta por operación,
- aplica la regla de vencidas,
- y luego agrega.

Eso es consistente con el requerimiento funcional, pero puede no dar exactamente el mismo número que una sensibilidad de libro calculada por shocks finitos sobre todo el portafolio.

No es necesariamente un error. Es una diferencia de metodología.

## 8. Dónde sí podría haber ajustes futuros

Si negocio quiere cerrar por completo cualquier duda, yo revisaría estos tres puntos.

### 1. Fuente oficial del residual de vencidas no cumplidas

Hoy quedó:

- `VP Sett Ccy Y CVA` como fuente principal.

Eso parece razonable con el requerimiento revisado, pero vale la pena confirmar que siempre corresponde a la columna `BM` esperada para todas las versiones del reporte.

### 2. Metodología exacta de delta

Hoy quedó:

- delta analítico por trade, con curvas y superficie.

Si negocio quisiera replicar exactamente una sensibilidad de libro del script legado, habría que rehacer el enfoque con shocks de portafolio, no solo con delta por operación.

### 3. Regla auxiliar de moneda de cumplimiento

Si en el futuro aparece un caso donde:

- `Moneda cumplimiento` esté vacía,
- `Moneda de la prima` también esté vacía,

entonces la regla por prefijo de contraparte pasa a ser importante y convendría validarla con negocio.

## 9. Conclusión corta

Si lo resumimos en una sola frase:

- `Swaps` hoy mide **flujos futuros en moneda en riesgo distinta de COP**, usando `VP MONEDA EN RIESGO`.
- `Opciones` hoy mide **delta mientras la opción está viva** y **valor residual o cero cuando ya venció**, según la moneda y la fecha de cumplimiento.

Mi lectura actual es:

- en `Swaps`, la aplicación está prácticamente exacta frente al requerimiento;
- en `Opciones`, la lógica central también está bien aplicada, pero la cifra final depende de tres decisiones metodológicas que conviene tener presentes: fuente del residual, delta analítico por trade y normalización de moneda de cumplimiento.

## 10. Cómo leer una cifra sin confundirse

Si ves una cifra de `Swaps`, léela así:

**esto es lo que sigue expuesto por flujos futuros según la regla del tablero**.

Si ves una cifra de `Opciones`, léela así:

**esto es lo que hoy se comporta como exposición delta, más cualquier residual pendiente de liquidar que ya no debe tratarse como opción viva**.

Esa es la forma correcta de interpretar lo que hoy está calculando Risko.
