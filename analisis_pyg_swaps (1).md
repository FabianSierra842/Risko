# Análisis técnico y funcional completo de `PYG SWAPS_MES.xlsm`

**Archivo analizado:** `PYG SWAPS_MES.xlsm`  
**Fecha de corte contenida en el libro:** 08/09/2026  
**Clave VBA informada:** `CLAVE`  
**Objetivo de este documento:** identificar de manera exhaustiva los insumos, archivos, reglas de negocio, transformaciones, dependencias, controles y estados históricos necesarios para reproducir en código el PYG diario de **Forwards, Swaps, Novados y Caja**, incluyendo la reconciliación Banking/IFRS y señalando las dependencias adicionales del libro.

---

## 0. Resumen ejecutivo

El archivo no es únicamente un consolidado de resultados. Funciona simultáneamente como:

1. repositorio mensual de posiciones y valoraciones;
2. maestro operativo de swaps;
3. motor de valoración y atribución de Forwards/Novados;
4. consolidación de PYG de Swaps proveniente de Summit y del Informe Libro de Swaps;
5. cálculo de PYG de Caja y costo de fondos;
6. reconciliador Banking vs IFRS;
7. módulo de recuponing/CVA-DVA;
8. comparador contra contabilidad;
9. conjunto de controles operativos de calidad;
10. mecanismo de persistencia mediante el archivo histórico del corte anterior.

La conclusión principal es que **el PYG diario es stateful**: para calcular el día `t` no basta con cargar los archivos de `t`. Se necesita información de `t-1` o un snapshot persistido del estado previo.

En términos de datos, el motor completo necesita:

```text
OPERACIONES
+ VALORACIONES t / t-1
+ FLUJOS / LIQUIDACIONES
+ CURVAS Y FX t / t-1
+ GRIEGAS / ATRIBUCIÓN
+ FTP / COSTO DE FONDOS
+ ESTADO HISTÓRICO
+ REGLAS DE CLASIFICACIÓN
+ CONTROLES CONTABLES
```

### Archivos únicos parametrizados

La hoja `Parametros` contiene 16 referencias B1:B16, pero varias son el mismo archivo usado para finalidades diferentes. El proceso se reduce aproximadamente a **13 fuentes físicas únicas**, más el archivo/snapshot histórico anterior.

Para el alcance **Forward + Swap + Novados + Caja**, dejando Títulos fuera y tratando `EXP.xlsx` como pendiente de validación, el núcleo práctico queda en alrededor de **11 fuentes únicas + estado anterior**, con una dependencia adicional crítica que el libro no deja plenamente trazada: **`Payments Report` por Trade ID para Swaps**.

### Hallazgos críticos para una migración

- El PYG de Swap por operación es explícitamente:

  \[
  PYG_t = VP_t - VP_{t-1} + Payment_t
  \]

  La fuente exacta que llena `Payments Report` en la hoja `SWAP` **no queda identificada de forma completa en las macros parametrizadas**.

- Los Novados se originan filtrando el universo de Forwards por `SWAPSNOVADO`, pero **no son simplemente un Forward con otro nombre**: la hoja `Novados` implementa lógica propia de valoración de cámara/CRCC.

- El libro mantiene Banking e IFRS por separado y calcula CVA-DVA por diferencia entre ambos universos.

- El histórico del corte anterior es una dependencia real. `RESUMEN FINAL` contiene referencias directas al libro anterior.

- El libro analizado tiene un vínculo al archivo del **06/09/2026**, mientras su fecha de corte es **08/09/2026**; el propio control de actualización del vínculo marca `Revisar`.

- Existen versiones manuales y parametrizadas de varias macros. Los botones visibles no siempre ejecutan la versión `_P`; por tanto, **el flujo operacional real puede diferir del flujo parametrizado**.

- Existe una discrepancia especialmente importante en la carga de posición USD IFRS: la macro manual y la parametrizada aplican filtros y columnas de suma diferentes. Debe ser validado con negocio antes de homologar el proceso.

- `EXP.xlsx` se carga a `Parametros!O:AT`, pero existe un probable error VBA (`lastRow` vs `lastRow1`) y no se identificó una dependencia directa clara de las fórmulas principales sobre ese bloque.

- La hoja `SWAP` contiene cerca de **1,5 millones de celdas** y aproximadamente **195 mil fórmulas**. Su diseño histórico horizontal no debería replicarse en una solución nueva.

---

# 1. Alcance y metodología del análisis

Se inspeccionaron:

- las 25 hojas del workbook;
- fórmulas y referencias entre hojas;
- proyecto VBA y macros;
- macros parametrizadas y manuales;
- rutas de la hoja `Parametros`;
- vínculo externo del workbook;
- nombres definidos;
- hojas ocultas;
- controles explícitos de la hoja `Hoja de controles`;
- lógica de fin/inicio de mes;
- estructuras de Forwards, Novados, Swaps, Caja y Recuponing;
- reconciliaciones con Summit, Informe Libro de Swaps y contabilidad.

Para evitar mezclar certeza con interpretación, se utilizan tres niveles:

| Nivel | Significado |
|---|---|
| **Confirmado** | Regla observada directamente en una fórmula, macro, filtro, ruta o referencia del workbook. |
| **Inferido** | Interpretación funcional consistente con nombres, cálculos y relaciones del libro. |
| **Pendiente de negocio** | Hay evidencia parcial o versiones contradictorias; requiere validación funcional. |

---

# 2. Anatomía del workbook

El archivo contiene 25 hojas.

| # | Hoja | Estado | Dimensión aproximada | Fórmulas | Rol principal |
|---:|---|---|---|---:|---|
| 1 | `RESUMEN FINAL` | Visible | A1:AQ341 | 707 | Consolidación Banking/IFRS, factores, variaciones diarias y límites. |
| 2 | `PORTAFOLIO` | Visible | A1:BF362 | 1.821 | Serie mensual de PYG, VP, posiciones y conciliaciones agregadas. |
| 3 | `CAJA SWAP` | Visible | A1:BG362 | 923 | PYG de caja, posición USD, trading, delta y costo de fondos. |
| 4 | `GRIEGAS SWAP` | Visible | A1:BP361 | 126 | Histórico de factores PYG y sensibilidades del Informe Libro de Swaps. |
| 5 | `SWAP` | Visible | A1:GY1048576 | 195.561 | Maestro de swaps + valoración Banking/IFRS + pagos + PYG diario por día. |
| 6 | `CAJA SWAP ARBITR` | Oculta | A1:AJ49 | 758 | Caja de arbitraje; carga activa actualmente comentada. |
| 7 | `TITULOS` | Visible | A1:CH2439 | 8.699 | Títulos asociados al book SWAPS. |
| 8 | `CORTOS` | Visible | A1:BU361 | 0 | Componente complementario de títulos/cortos. |
| 9 | `PYG Recuponing` | Visible | A1:L361 | 286 | Ajuste de PYG y posición por recuponing. |
| 10 | `Ajuste recuponing` | Visible | A1:CO1048576 | 167 | Datos y fórmulas detalladas de CVA/recouponing por operación. |
| 11 | `RIESGOS LIBRO` | Visible | A1:BS99 | 0 | Copia del riesgo proveniente del Informe Libro de Swaps. |
| 12 | `GRIEGAS ARBITRAJE` | Oculta | A1:AY54 | 81 | Griegas de arbitraje; flujo actualmente comentado. |
| 13 | `Tasas` | Visible | A1:BD359 | 310 | Histórico de curvas, TRM y datos de mercado usados por FX. |
| 14 | `Forwards` | Visible | A1:AY1000 | 36.796 | Motor bottom-up de valoración/atribución de Forward. |
| 15 | `Novados` | Visible | A1:BY298 | 11.361 | Motor específico de Novados y cámara/CRCC. |
| 16 | `Fuente vs Instrum - TD` | Visible | A1:AH127 | 16 | Pivot/agregación de factores Forward/Novados. |
| 17 | `Hoja2` | Oculta | B3:H14 | 0 | Hoja auxiliar. |
| 18 | `RESUMEN MENSUAL` | Visible | A1:IU48 | 103 | Recálculo y acumulados mensuales. |
| 19 | `AUX` | Visible | A1:P44578 | 1.174 | Staging de valoraciones, conciliaciones, riesgo y Trade IDs. |
| 20 | `CUADRE CONTABLE` | Visible | B2:G23 | 8 | Reconciliación con IFRS/COLGAAP. |
| 21 | `SAP IFRS 871` | Visible | A1:M6995 | 8.502 | Base contable IFRS. |
| 22 | `COLGAAP` | Visible | A1:K952 | 0 | Base contable local/Banking. |
| 23 | `Hoja1` | Oculta | A1:P36 | 165 | Auxiliar histórica. |
| 24 | `Hoja de controles` | Visible | B2:E20 | 36 | Controles y tolerancias del proceso. |
| 25 | `Parametros` | Visible | A1:BI45 | 0 | Fecha de corte, rutas y staging `EXP`. |

## 2.1 Implicación arquitectónica

La hoja `SWAP` tiene una estructura de base mensual **horizontal**. Cada día consume un bloque repetido de columnas. Esto hace que el Excel sea útil como herramienta operativa, pero es una arquitectura inadecuada para un motor programático moderno.

En una migración se recomienda reemplazarla por tablas normalizadas del tipo:

```text
swap_valuation
--------------
valuation_date
trade_id
accounting_basis   # BANKING / IFRS
vp_net_cop
payment_cop
pyg_cop
cva_dva_change
```

---

# 3. Parámetros y rutas físicas

## 3.1 Fecha y parámetros generales

`Parametros` contiene:

| Celda | Valor actual | Uso |
|---|---|---|
| A1 | 08/09/2026 | Fecha parametrizada. |
| A2 | 08/09/2026 | Fecha de corte utilizada por varias cargas. |
| C1 | `08` | Día calendario del mes para ubicar la valoración SWAP. |
| C2 | Ruta de `EXP.xlsx` | Carga auxiliar hacia `Parametros!O:AT`. |

La fecha principal visible del reporte se encuentra además en el nombre definido:

```text
Fecha = 'RESUMEN FINAL'!$C$3
```

## 3.2 Inventario de rutas B1:B16

| Parámetro | Fuente | Macro/uso | Fuente interna concreta | Destino principal | ¿Núcleo PYG? |
|---|---|---|---|---|---|
| **B1** | `INFORME FWD CONSOLIDADO 08-09-26.xlsb` | `carga_fwd_dia_P` | `Macro`, `INFORME BOOKS`, `INFORME IFRS`, `BOOKS CONTADO`, `BOOKS NOVADO` | `PORTAFOLIO`, `RESUMEN FINAL` | **Sí** |
| **B2** | `REPORTE CAJA LIVIANO` | `CARGAR_INFO_CAJA_5_P` | `TABLA ORGANIZADA!AP4:AS34` | `CAJA SWAP!T:W` | **Sí** |
| **B3** | `FTP COP.xlsx` | `CARGA_FT_P` | `Curva COP!D12`, `L12`, `E12` | `CAJA SWAP!AL:AM` y bloque espejo | **Sí** |
| **B4** | `FTP USD.xlsx` | `CARGA_FT_P` | `Curva USD!D11`, `E11` | `CAJA SWAP!AP:AQ` | **Sí** |
| **B5** | `Informe Libro de Swaps 20260908.xlsb` | `GRIEGAS_P` | `MERCADO-BALANCE`, `Historico Griegas PyG`, `RIESGOS LIBRO` | `GRIEGAS SWAP`, `PORTAFOLIO`, `RIESGOS LIBRO` | **Sí** |
| **B6** | `ReporteTitulos_08092026.csv` | `Carga_Titulos_P` | CSV delimitado `;`, filtro Field 20=`SWAPS` | `TITULOS` | Condicional |
| **B7** | `Cierre_SwapTotalReport_080926_000.xls` | `Carga_Sw_Nuevos_P` | SwapTotal Banking | Maestro `SWAP!A:G` | **Sí** |
| **B8** | mismo SwapTotal Banking | `CARGAR_VALORACION_SWAP_P` | B = Trade ID; BD = VP_NET_COP | `AUX!A:B` -> `SWAP` | **Sí** |
| **B9** | `Cierre_SwapTotalReport_IFRS_080926_000.xls` | `CARGAR_VALORACION_SWAP_P` | B = Trade ID; BD = VP_NET_COP | `AUX!D:E` -> `SWAP` | **Sí para IFRS** |
| **B10** | `Cierre_SwapTotalReport_IFRS_Flujos_080926_000.xls` | `Carga_Posi_USD_P` | filtros de posición USD | `PYG Recuponing!H` | **Sí para recuponing/IFRS** |
| **B11** | `Curva Forward V2.xlsm` | `traecurvas_P` | `CURVAS!A30:AU30` | `Tasas!J:...` | **Sí** |
| **B12** | `MASCARA FX TOTAL REPORT (5.5-3-8).xls` | `CARGAR_INFO_FWDS_P` | `Mapeo Deriva. ESTRAT`, filtro Field 12=`SWAPS` | `Forwards!A:N` | **Sí** |
| **B13** | mismo SwapTotal Banking | `Llamadarectangular_P` | Trade IDs y fecha de reporte | `AUX!G:H` | Control/conciliación |
| **B14** | mismo Informe Libro de Swaps | `Llamadarectangular_P` | `SWAPS`, `RIESGOS LIBRO` | `AUX!I:J`, delta informe | Control/conciliación |
| **B15** | `Cierre_SwapTotalReport_Flujos_080926_000.xls` | `Llamadarectangular_P` | AJ/AO/AS | `AUX!L:N` | Riesgo/control |
| **B16** | mismo SwapTotal Flujos Banking | `Carga_Posi_USD_P_Banking` | filtros de posición USD | `PYG Recuponing!K` | **Sí para posición Banking** |
| **C2** | `EXP.xlsx` | `CARGAR_VALORACION_SWAP_P` | A:AF | `Parametros!O:AT` | **Pendiente de validar** |

## 3.3 Fuentes físicas únicas

B7/B8/B13 son el mismo reporte.  
B5/B14 son el mismo Informe Libro de Swaps.  
B15/B16 son el mismo reporte de flujos Banking.

Por eso, físicamente se tienen:

1. FWD Consolidado.
2. Reporte Caja Liviano.
3. FTP COP.
4. FTP USD.
5. Informe Libro de Swaps.
6. Reporte Títulos — si Títulos permanece en alcance.
7. Swap Total Banking.
8. Swap Total IFRS.
9. Swap Total IFRS Flujos.
10. Curva Forward.
11. Máscara FX Total Report.
12. Swap Total Banking Flujos.
13. EXP.xlsx — pendiente de confirmar si sigue siendo necesario.
14. Snapshot/libro histórico del corte anterior.

---

# 4. Vínculo histórico: dependencia de `t-1`

El workbook contiene un vínculo externo explícito a:

```text
HISTORIA/2026/PYG SWAPS_MES_2026-09-06.xlsm
```

El archivo actual tiene corte 08/09/2026.

En `RESUMEN FINAL`, el bloque de histórico —principalmente columnas `AA:AF`— lee directamente valores del libro anterior, por ejemplo:

```text
'[1]RESUMEN FINAL'!$C$43
'[1]RESUMEN FINAL'!$D$43
...
```

Después, el bloque diario calcula variaciones de la forma:

```text
valor actual - valor del archivo anterior
```

Por ejemplo, en IFRS:

```text
S43 = C43 - AA43
T43 = D43 - AB43
...
```

## 4.1 Regla funcional

El proceso distingue entre:

- **valor acumulado/cierre actual**;
- **valor acumulado/cierre anterior**;
- **movimiento diario**.

Por tanto, la lógica debería formalizarse como:

\[
PYG^{diario}_{t,factor,producto}
=
PYG^{acumulado}_{t,factor,producto}
-
PYG^{acumulado}_{t-1,factor,producto}
\]

cuando el factor se maneja acumulado.

## 4.2 Problema del corte analizado

La hoja `Hoja de controles` tiene:

```text
Actualización vinculo reporte t-2 = Revisar
```

El histórico apuntado es 06/09/2026 y no 07/09/2026. Esto puede ser legítimo si el 07 no fue corte válido, pero el libro **no incorpora explícitamente un calendario hábil en esta comparación**; por eso el sistema nuevo debe resolver `previous_valid_business_date`, no simplemente `date - 1`.

## 4.3 Recomendación

No abrir el Excel de ayer desde el nuevo código. Persistir una tabla:

```text
pyg_snapshot
------------
valuation_date
product
accounting_basis
factor
amount_cop
position_usd
source_run_id
```

---

# 5. Arquitectura de consolidación en `RESUMEN FINAL`

El resumen Banking organiza los productos por columnas y factores por filas.

## 5.1 Factores Banking

El bloque principal usa, conceptualmente:

| Fila | Factor |
|---:|---|
| 7 | Trading |
| 8 | Delta USD |
| 9 | Delta JPY/EUR |
| 10 | Rho COP |
| 11 | Rho USD |
| 12 | Rho DTF |
| 13 | Rho IPC |
| 14 | Rho JPY/EUR |
| 15 | Theta |
| 16 | Épsilon / Residual |
| 17 | Costo de fondos |
| 18 | Total Banking |
| 20 | Delta / posición Banking |

Productos:

- Forward;
- SWAP;
- Caja;
- Novados;
- Títulos.

La lógica del residual es esencialmente:

\[
Residual = PYG_{total} - \sum FactoresExplicados
\]

## 5.2 IFRS

El bloque IFRS comienza alrededor de la fila 42:

- fila 43: total IFRS;
- fila 44: CVA-DVA;
- fila 45: Ajuste Recuponing;
- filas 49-50: delta IFRS de book SWAP/arbitraje.

Ejemplos confirmados:

```text
D44 = D43 - D18
```

por lo que el ajuste CVA-DVA de Swap agregado es la diferencia entre PYG IFRS y Banking.

El ajuste de recuponing se toma de:

```text
RESUMEN FINAL!D45 = 'PYG Recuponing'!G34
```

## 5.3 Contabilidad

`CUADRE CONTABLE` compara los resultados del motor contra:

- `COLGAAP` para Banking;
- `SAP IFRS 871` para IFRS.

Ejemplos:

```text
PYG SWAP Banking = COLGAAP cuentas 412930 + 412932 - 512930 - 512932
Delta SWAP Banking = cuentas 1354 - 2215
```

Para IFRS se utilizan sumas por cuentas de `SAP IFRS 871`.

Estas bases contables no son necesariamente un insumo para **calcular** el PYG económico, pero sí son un insumo para **validar y cerrar el proceso diario**.

---

# 6. FORWARDS — análisis completo

## 6.1 Dos capas diferentes

Forward tiene dos fuentes que no deben confundirse.

### Capa A: reporte agregado `INFORME FWD CONSOLIDADO`

Se usa como fuente top-down de PYG/VP reportado y datos de mercado.

### Capa B: `MASCARA FX TOTAL REPORT` + `Curva Forward V2`

Se utiliza para reconstruir operación por operación la valoración y la atribución de PYG.

La solución nueva debería conservar ambas durante la transición:

```text
motor bottom-up -> resultado calculado
FWD consolidado -> benchmark/control independiente
```

---

## 6.2 Macro `carga_fwd_dia_P`

**Ruta:** `Parametros!B1`.

### Hoja `Macro`

Se toman:

- `C3`: fecha;
- `C6`: TRM;
- `C7`: EUR.

### Hoja `INFORME BOOKS`

Para book SWAPS:

- `AK4`: VP mercado;
- `AK42`: VP internos;
- `AL4`: PYG mercado;
- `AL42`: PYG internos.

Para `ARBITR_DER` se usa el bloque `AY/AZ`.

### Hoja `INFORME IFRS`

Se repite una estructura equivalente para IFRS.

### Hojas `BOOKS CONTADO` y `BOOKS NOVADO`

Se extraen PYG/VP de contado y Novados.

### Destino

Principalmente `PORTAFOLIO`, en dos bloques:

- Banking/local;
- IFRS.

También se actualiza la fecha del reporte y variables de mercado.

---

## 6.3 Macro `CARGAR_INFO_FWDS_P`

**Ruta:** `Parametros!B12`.

Abre:

```text
MASCARA FX TOTAL REPORT (5.5-3-8).xls
```

Hoja:

```text
Mapeo Deriva. ESTRAT
```

Regla de filtro confirmada:

```text
Field 12 = "SWAPS"
```

Se copian 14 campos fuente `C:P` hacia `Forwards!A:N`.

### Estructura cruda de `Forwards`

| Col. | Campo |
|---|---|
| A | TRADE ID |
| B | TIPO — COMPRA/VENTA |
| C | OPERACIÓN / Trade Date |
| D | DE VENC / vencimiento |
| E | MONEDA |
| F | VALOR / nominal |
| G | FWD contractual |
| H | MODALIDAD |
| I | CLIENTE |
| J | SPOT contractual |
| K | Liq / fecha de liquidación |
| L | Portafolio |
| M | CONCATENA / clasificación |
| N | CUMPLIMIENTO / moneda de cumplimiento |

Después de cargar A:N, la macro copia las fórmulas de `O:AX` hacia las filas cargadas.

---

# 7. Curvas y mercado para Forward

## 7.1 Macro `traecurvas_P`

**Ruta:** `Parametros!B11`.

Abre `Curva Forward V2.xlsm`, hoja `CURVAS`, y copia:

```text
A30:AU30
```

como un nuevo snapshot en la hoja `Tasas`, comenzando alrededor de la columna J.

`Tasas` actúa como histórico de mercado del mes.

## 7.2 Bloques de curva identificados

Las fórmulas de `Forwards` utilizan:

| Bloque `Tasas` | Uso observado |
|---|---|
| `J:X` | tasa implícita / estructura forward |
| `Z:AN` | curva/tasa USD |
| `AP:BD` | curva/tasa COP |
| `B:F` | TRM/Spot/valores FX por fecha y modalidad |
| `B70:C132` aprox. | TRM fix por fecha de vencimiento/liquidación |

La lógica usa interpolación por plazo mediante `HLOOKUP` entre nodos de curva.

## 7.3 Necesidad de t y t-1

El motor contiene explícitamente:

- fecha anterior `Q2`;
- fecha actual `W2`;
- curva COP anterior/actual;
- curva USD anterior/actual;
- tasa implícita anterior/actual;
- TRM anterior/actual.

Esto confirma que para atribución correcta se deben preservar snapshots de mercado diarios.

---

# 8. Valoración Forward operación por operación

La hoja `Forwards` contiene dos estados de la misma operación:

### Estado t-1

- plazo liquidación `P`;
- tasa implícita `Q`;
- tasa COP `R`;
- tasa USD `S`;
- TRM/valoración contable `T`;
- VP FWD COP `U`.

### Estado t

- plazo `V`;
- tasa implícita `W`;
- tasa COP `X`;
- tasa USD `Y`;
- TRM/valoración contable `Z`;
- VP FWD COP `AA`.

## 8.1 Reglas de vigencia

Las fórmulas ponen la valoración en cero o vacío cuando la operación:

- aún no ha iniciado (`trade date > valuation date`);
- ya venció/liquidó antes del corte;
- no cumple condiciones específicas de fecha de liquidación.

## 8.2 Regla Compra/Venta

La dirección de la operación controla el signo de VP y sensibilidades.

Por ejemplo, la sensibilidad de posición en `AK` usa conceptualmente:

```text
COMPRA -> + nominal
VENTA  -> - nominal
```

si la operación sigue vigente.

En las fórmulas de VP se utiliza un signo equivalente, aunque la expresión financiera puede aparecer invertida por la forma en que se define el payoff.

## 8.3 Modalidad `SIN ENTREGA`

La modalidad `SIN ENTREGA` activa tratamientos específicos:

- definición de plazo;
- fecha usada para settlement;
- lookup de TRM;
- componente Base/Vencimientos;
- liquidación COP/USD.

Por tanto, la modalidad debe ser un atributo obligatorio en el modelo de datos.

---

# 9. PYG diario de Forward

La columna `AB` se denomina `Diario`.

La fórmula confirma conceptualmente:

\[
PYG^{FWD}_t
=
VP_t - VP_{t-1}
+ PYG^{liq,USD}_t
+ PYG^{liq,COP}_t
\]

En Excel:

```text
AB = (AA - U) + AP + AT
```

sujeto a reglas de vigencia/fechas.

## 9.1 Atribución

| Columna | Factor |
|---|---|
| AC | Cambiario interday |
| AD | Cambiario intraday |
| AE | Curva COP |
| AF | Curva USD |
| AG | Spread |
| AH | Base - Vctos |
| AI | Trading - Nuevas |
| AJ | Tiempo |

La columna `AJ` es explícitamente un cierre:

\[
Tiempo = PYG - \sum_{AC:AI}
\]

Por tanto, `Tiempo` es funcionalmente un Theta/residual temporal, no un cálculo independiente puro en todos los casos.

## 9.2 Liquidaciones

| Col. | Campo |
|---|---|
| AM | Liquidación USD |
| AN | Liquidación ayer USD |
| AO | Liquidación hoy USD |
| AP | Total PYG USD |
| AQ | Liquidación COP |
| AR | Liquidación ayer COP |
| AS | Liquidación hoy COP |
| AT | Total PYG COP |
| AU | Delta liquidación |
| AV | Rho COP liquidación |
| AW | Rho USD liquidación |
| AX | Theta liquidación |

La columna `AX` vuelve a actuar como cierre de la atribución de la liquidación:

\[
Theta_{liq} = PYG_{liq} - Delta_{liq} - RhoCOP_{liq} - RhoUSD_{liq}
\]

---

# 10. Insumos mínimos del motor Forward

## Operación

- Trade ID;
- tipo compra/venta;
- Trade Date;
- fecha de vencimiento;
- fecha de liquidación;
- par de monedas;
- nominal;
- tasa Forward;
- Spot;
- modalidad;
- moneda de cumplimiento;
- book/portafolio;
- clasificación `M/CONCATENA`.

## Mercado t y t-1

- TRM;
- curva implícita/forward;
- curva COP;
- curva USD;
- fixing de liquidación;
- spread configurado si aplica.

## Estado

- VP previo;
- status de operación;
- liquidaciones ya reconocidas.

---

# 11. NOVADOS — origen y regla de clasificación

La macro:

```text
flitrar_novados
```

filtra `Forwards` mediante:

```text
Field 13 = "SWAPSNOVADO"
```

Es decir:

> **La fuente operativa de Novados es la misma Máscara FX que alimenta Forwards.**

No se requiere un archivo de operaciones Novado separado para la lógica bottom-up.

Esto permite un pipeline de ingestión único:

```text
MASCARA FX
   ↓
normalización de operaciones FX
   ↓
clasificación
   ├── Forward normal
   └── SWAPSNOVADO -> Novado
```

---

# 12. NOVADOS — diferencia crítica frente a Forward

Aunque nacen del mismo universo, la hoja `Novados` contiene una lógica de valoración adicional de **cámara/CRCC**.

Encabezados observados:

| Col. | Campo |
|---|---|
| AB | TRM - Contable |
| AC | VP FWD COP |
| AD | Valoración cámara |
| AE | Diario |
| AF | Cámara |
| AG | Cambiario interday |
| AH | Precios FWD (delta) |
| AI | Valoración interday CRCC |
| AJ | Delta Interday CRCC |
| AK | Cambiario Intraday |
| AL | Precios FWD COP |
| AM | Valoración nueva |
| AN | Curva COP Cámara |
| AO | Curva COP |
| AP | Puntos FWD USD |
| AQ | Valoración nueva |
| AR | Curva USD Cámara |
| AS | Curva USD |
| AT | Spread |
| AU | Base - Vctos |
| AV | Trading - Nuevas |
| AW | Precios FWD Completo |
| AX | Valoración CRCC |
| AY | Tiempo CRCC |
| AZ | Sensibilidad |
| BC | Sensibilidad Novados |
| BF | compra |
| BG | venta |
| BH | neto |

## 12.1 Dos PYG visibles

La hoja diferencia:

- `AE = Diario`, basado en VP FWD;
- `AF = Cámara`, basado en valoración de cámara.

También calcula explícitamente una atribución CRCC.

## 12.2 Regla funcional

Para una migración:

- **se puede reutilizar la ingestión de Forward**;
- **no se debe asumir que la valoración/atribución Novado es idéntica a Forward**;
- debe existir un componente específico CRCC/cámara.

## 12.3 Posición Novado

Se calcula compra, venta y neto, y la sensibilidad depende de vigencia y dirección de la operación.

---

# 13. `Fuente vs Instrum - TD`

Esta hoja funciona como una capa de agregación/pivot para los factores calculados en `Forwards` y `Novados`.

No debe tratarse como un archivo de entrada independiente.

El macro `E_Recalculo` actualiza el resumen mensual y refresca la tabla dinámica, lo que evidencia que:

```text
Forwards/Novados detallados
        ↓
Fuente vs Instrum - TD
        ↓
RESUMEN FINAL
```

En el nuevo motor esta capa podría reemplazarse por agregaciones SQL/Pandas-equivalentes —en implementación— del tipo:

```text
GROUP BY valuation_date, product, factor, book
```

---

# 14. SWAPS — maestro de operaciones

La hoja `SWAP` contiene como columnas base:

| Col. | Campo |
|---|---|
| A | Trade ID |
| B | Cliente |
| C | Book |
| D | CCS/IRS |
| E | Trade Date |
| F | End Date |
| G | Customer Group |

## 14.1 Macro `Carga_Sw_Nuevos_P`

**Ruta:** `Parametros!B7`.

Abre el Swap Total Banking como texto delimitado por `;`.

Filtros confirmados:

```text
Field 13 = fecha de corte
Field 7 <> "FVH"
```

Después agrega las nuevas operaciones al final del maestro `SWAP`.

## 14.2 Regla de exclusión `FVH`

`FVH` se excluye de la carga de nuevos Swaps y aparece también en filtros de posición/recuponing.

Por tanto, esta clasificación debe conservarse explícitamente como regla de elegibilidad.

## 14.3 Riesgo de re-ejecución

La macro **agrega** registros. No se observa una garantía fuerte de idempotencia o `upsert` por Trade ID antes de insertar.

En un motor nuevo debe existir:

```text
PRIMARY KEY / UNIQUE (trade_id)
```

o, si una operación puede tener varias legs/registros, una clave compuesta documentada.

---

# 15. SWAPS — valoración Banking e IFRS

## 15.1 Macro `CARGAR_VALORACION_SWAP_P`

### Banking

**Ruta:** `Parametros!B8`.

Del reporte:

- columna B -> Trade ID;
- columna BD -> `VP_NET_COP`.

Se almacena temporalmente en:

```text
AUX!A = Trade ID Banking
AUX!B = VP_NET_COP Banking
```

### IFRS

**Ruta:** `Parametros!B9`.

Se almacena en:

```text
AUX!D = Trade ID IFRS
AUX!E = VP_NET_COP IFRS
```

### Cruce por Trade ID

En la hoja `SWAP`:

```text
GU = VLOOKUP Trade ID contra AUX Banking
GV = VLOOKUP Trade ID contra AUX IFRS
```

Por tanto, **Trade ID es la clave operacional primaria del cálculo de valoración**.

---

# 16. SWAPS — estructura temporal por día

El VBA usa:

```vb
colBanking = 10 + (dia - 1) * 6
colIFRS    = colBanking + 1
```

El día calendario se toma de:

```text
Parametros!C1
```

Cada día consume 6 columnas:

```text
VP Banking
VP IFRS
Payments Report
PYG Banking
PYG IFRS
CVA-DVA
```

Ejemplo de un bloque:

| Col. | Significado |
|---|---|
| H | VP Banking previo |
| I | VP IFRS previo |
| J | VP Banking actual |
| K | VP IFRS actual |
| L | Payments Report |
| M | PYG Banking |
| N | PYG IFRS |
| O | cambio CVA-DVA |

El siguiente día repite el patrón.

---

# 17. Fórmula central del PYG Swap

Fórmulas confirmadas:

```text
M9 = IF(J9="",0,J9-H9+L9)
N9 = IF(K9="",0,K9-I9+L9)
```

Por tanto:

\[
\boxed{PYG^{Banking}_t=VP^{Banking}_t-VP^{Banking}_{t-1}+Payments_t}
\]

\[
\boxed{PYG^{IFRS}_t=VP^{IFRS}_t-VP^{IFRS}_{t-1}+Payments_t}
\]

La lógica de CVA-DVA del bloque es:

```text
O9 = (K9-J9) - (I9-H9)
```

es decir:

\[
\Delta(CVA-DVA)_t =
(VP^{IFRS}_t-VP^{Banking}_t)
-
(VP^{IFRS}_{t-1}-VP^{Banking}_{t-1})
\]

---

# 18. `Payments Report` — dependencia crítica no totalmente trazada

La columna de pago/flujo es una entrada directa a la fórmula del PYG.

Sin ella:

\[
VP_t - VP_{t-1}
\]

mezcla:

- movimiento económico de mercado;
- cupón pagado/recibido;
- amortización;
- flujo de principal.

El PYG correcto necesita neutralizar/incorporar el flujo según la convención del libro.

## 18.1 Hallazgo

No se identificó en las macros parametrizadas analizadas una asignación inequívoca de un archivo/campo hacia **cada celda `Payments Report` por Trade ID** de la hoja `SWAP`.

Los reportes de flujos B15/B16 alimentan riesgo/posición, pero la escritura de `Payments Report` por operación no queda clara.

## 18.2 Requerimiento para negocio

Debe documentarse:

```text
source_file
source_field
trade_id_field
flow_date_field
currency
sign convention
conversion to COP
aggregation rule
payment types included/excluded
```

Este es el **principal gap funcional** antes de reemplazar el cálculo de PYG Swap.

---

# 19. Griegas y atribución de PYG Swap

## 19.1 Fuente

`Parametros!B5`:

```text
Informe Libro de Swaps 20260908.xlsb
```

Macro:

```text
GRIEGAS_P
```

## 19.2 `MERCADO-BALANCE`

Se extraen:

- B5: factor/tasa EUR;
- B6: factor/tasa JPY;
- B36: componente USD;
- B38: componente EUR;
- B40: componente JPY.

Se calcula:

\[
DeltaSwap = f_{USD} + EUR_m \cdot f_{EUR} + \frac{f_{JPY}}{JPY_m}
\]

Ese resultado se agrega a `PORTAFOLIO` como posición/sensibilidad.

## 19.3 `Historico Griegas PyG`

La macro determina:

```text
first_day_of_month
DIF = fecha_corte - first_day_of_month
```

Luego selecciona el bloque correspondiente del histórico y lo copia a `GRIEGAS SWAP`.

## 19.4 Factores que alimentan `RESUMEN FINAL`

Para el book Swap se identifican:

| Factor | Fuente aproximada `GRIEGAS SWAP` |
|---|---|
| Trading | T35 |
| Delta USD | M35 |
| Delta EUR/JPY | N35 |
| Rho USD | O35 |
| Rho COP | P35 |
| Rho DTF | Q35 |
| Rho IPC | R35 |
| Rho EUR/JPY | S35 |
| Theta | L35 |

El residual se calcula como:

\[
Residual_{swap}=PYG_{swap}-Trading-Delta-Rhos-Theta
\]

## 19.5 Implicación si ya existe código Delta

Si el nuevo desarrollo ya calcula Delta, todavía faltan para replicar la atribución actual:

- Trading;
- Rho COP;
- Rho USD;
- Rho DTF;
- Rho IPC;
- Rho EUR/JPY;
- Theta;
- residual/reconciliación.

Una migración incremental puede consumir inicialmente estos factores del Informe Libro de Swaps y reemplazarlos uno a uno.

---

# 20. RIESGOS LIBRO

`GRIEGAS_P` copia:

```text
RIESGOS LIBRO!A1:BS100
```

del Informe Libro de Swaps hacia la hoja local.

No es el motor de valoración del Swap, pero sí alimenta:

- posiciones de riesgo;
- controles;
- comparaciones contra Delta calculado;
- reportes de límites.

Debe tratarse como fuente de validación/riesgo si el objetivo del nuevo módulo incluye el cierre operativo completo.

---

# 21. Conciliación Summit vs maestro vs Informe Libro

Macro parametrizada:

```text
Llamadarectangular_P
```

Usa B13, B14 y B15.

## 21.1 SwapTotal Banking B13

La macro:

1. parsea el archivo;
2. crea un indicador `ISNUMBER(...)` para validar fecha/campo;
3. filtra el universo relevante;
4. filtra una lista de books/customer groups;
5. lleva Trade IDs a `AUX!G`;
6. lleva la fecha del reporte a `AUX!G1`.

Books/customer groups observados:

```text
ANTIOQUI_CEO
CORPORAT_BOG
COSTA_A_CEO
EMPRESAR_BOG
INSTITUC_BOG
MEDIANA
OCCIDENT_CEO
ORIENTE_CEO
PYME_EMPRESA
SWAPS
```

## 21.2 Informe Libro B14

Se cargan Trade IDs del libro en `AUX!I` y Delta del informe en `AUX!I1`.

## 21.3 Comparaciones

`AUX` usa `VLOOKUP` para comprobar si:

```text
Trade ID Summit existe en maestro SWAP
Trade ID Summit existe en Informe Libro
```

Esto debe convertirse en un control de integridad referencial del nuevo proceso.

---

# 22. B15 — información de riesgo por operación

Del Swap Total Flujos Banking se copian:

| Campo fuente | Destino AUX | Interpretación |
|---|---|---|
| AJ | L | CCS/IRS |
| AO | M | Moneda en riesgo |
| AS | N | VP moneda en riesgo |

Esto se utiliza en tablas dinámicas/riesgo, no como sustituto evidente de `Payments Report`.

---

# 23. CAJA — fuente y movimientos

## 23.1 Fuente

`Parametros!B2` -> `REPORTE CAJA LIVIANO`.

Macro:

```text
CARGAR_INFO_CAJA_5_P
```

Copia:

```text
TABLA ORGANIZADA!AP4:AS34
```

hacia:

```text
CAJA SWAP!T5:W35
```

El bloque representa compras/ventas en USD y su contravalor COP.

La carga de `CAJA SWAP ARBITR` está comentada, por lo que el flujo activo parametrizado está concentrado en `CAJA SWAP`.

---

# 24. CAJA — posición y tasas promedio

Columnas principales:

| Col. | Significado |
|---|---|
| B | Compra USD |
| C | Compra COP |
| D | Venta USD |
| E | Venta COP |
| F | Saldo dólares |
| G | TRM/tasa promedio compra |
| H | TRM/tasa promedio venta |
| I | TRM de cierre |

El saldo evoluciona como:

\[
SaldoUSD_t = SaldoUSD_{t-1}+CompraUSD_t-VentaUSD_t
\]

La tasa de compra:

\[
TasaCompra_t=\frac{CompraCOP_t}{CompraUSD_t}
\]

La tasa de venta:

\[
TasaVenta_t=\frac{VentaCOP_t}{VentaUSD_t}
\]

---

# 25. CAJA — PYG por factores

## 25.1 Trading

Fórmula confirmada:

\[
Trading_t=
\min(CompraUSD_t,VentaUSD_t)
\times
(TasaVenta_t-TasaCompra_t)
\]

## 25.2 Delta intradía

Excel calcula el efecto del desbalance del propio día:

\[
(Compra-\min(Compra,Venta))(TRM-TasaCompra)
+
(Venta-\min(Compra,Venta))(TasaVenta-TRM)
\]

## 25.3 Delta interday

Confirmado:

\[
Delta^{interday}_t=(TRM_t-TRM_{t-1})\cdot SaldoUSD_{t-1}
\]

## 25.4 PYG mercado de Caja

La columna `AZ` consolida:

```text
SUM(K:M)
```

por tanto:

\[
PYG^{Caja,mercado}=Trading+Delta_{intra}+Delta_{inter}
\]

---

# 26. CAJA — costo de fondos / FTP

## 26.1 FTP COP

`Parametros!B3` -> `FTP COP.xlsx`.

Hoja `Curva COP`:

```text
D12 = TASA_COP
L12 = Ajuste
E12 = PL_COP
```

La tasa final:

\[
FT_{COP}=TASA_{COP}+Ajuste
\]

Se guarda en `CAJA SWAP`.

## 26.2 FTP USD

`Parametros!B4` -> `FTP USD.xlsx`.

Hoja `Curva USD`:

```text
D11 = TASA_USD
E11 = PL_USD
```

## 26.3 Fórmulas de costo

La hoja calcula componentes COP y USD y los suma.

En el bloque observado:

```text
AJ = AO + AS
AK = acumulado de AJ
```

Para COP se utiliza una tasa efectiva diaria derivada de la tasa anual. Para USD se usa base nominal/360.

Conceptualmente:

\[
CostoFondos_t=CostoCOP_t+CostoUSD_t
\]

Y el PYG total de Caja es:

\[
PYG^{Caja,total}
=
Trading+Delta_{intra}+Delta_{inter}+CostoFondos
\]

`RESUMEN FINAL` muestra costo de fondos como factor separado, lo que permite distinguir PYG de mercado y financiación.

---

# 27. Estado inicial de Caja

La celda `CAJA SWAP!F4` funciona como saldo USD inicial del mes.

La macro de inicio de mes busca la fecha del último día del mes anterior y copia el saldo de cierre a `F4`.

Por tanto, el motor nuevo necesita:

```text
opening_cash_usd_balance
```

como estado inicial de cada período.

No es correcto reconstruir el saldo únicamente a partir de movimientos del mes si no se dispone del saldo de apertura.

---

# 28. Recuponing — estructura

`PYG Recuponing` contiene:

| Col. | Campo |
|---|---|
| B | Fair Value |
| C | Fair Value con ajuste |
| D | Ajuste |
| E | PYG sin ajuste |
| F | PYG con ajuste |
| G | Total Ajuste PYG |
| H | Posición Archivo |
| I | Total Ajuste Posición |
| J | Nueva posición |
| K | Posición Banking |

Reglas:

\[
AjusteFV=C-B
\]

\[
PYG_{sin ajuste,t}=FV_t-FV_{t-1}
\]

\[
PYG_{con ajuste,t}=FV^{aj}_t-FV^{aj}_{t-1}
\]

\[
AjustePYG=PYG_{con ajuste}-PYG_{sin ajuste}
\]

La nueva posición:

\[
NuevaPosicion = PosicionArchivo + AjustePosicion
\]

---

# 29. `Ajuste recuponing`

La hoja tiene campos detallados de la operación y del ajuste CVA, entre ellos:

- Trade ID;
- cliente;
- desk/book;
- CCS/IRS;
- modalidad;
- trade/start/end date;
- legs PAY y REC;
- tasas, índices, spreads y frecuencias;
- VP PAY/REC;
- `VP_NET_COP`;
- saldos/amortización;
- customer group;
- netting ISDA;
- rating;
- CVA curve;
- `CVA FAIR VALUE COP`;
- fecha próximo recouponing;
- días a recouponing;
- tasa IBR;
- spread CVA;
- valor futuro;
- `VP Cop con Ajuste CVA`;
- cambio CVA;
- ajuste CVA flujos;
- PAY/REC ajustados;
- ajuste en posición.

`PYG Recuponing` resume columnas como `BW`, `CF` y `CO` de esta hoja.

## 29.1 Gap de ingestión

No se identificó una macro de carga parametrizada claramente dedicada a poblar todo `Ajuste recuponing` desde una fuente externa diaria.

Por tanto, se debe confirmar si esta hoja:

- se llena manualmente;
- es resultado de una macro no usada;
- recibe datos de otro workbook/proceso;
- conserva datos de períodos anteriores.

---

# 30. Posición USD IFRS y Banking — reglas y discrepancia

Este punto requiere especial atención.

## 30.1 Macro manual `Carga_Posi_USD_IFRS`

La versión manual:

```text
Field 37 <> FVH
Field 41 = USD
Field 13 < Fecha
```

Suma:

```text
AP
```

Y escribe en `PYG Recuponing!H`.

## 30.2 Macro parametrizada `Carga_Posi_USD_P`

Ruta `B10`:

```text
Field 37 <> FVH
Field 41 = USD
Field 13 > Fecha
```

Suma:

```text
AS
```

Y escribe también en `PYG Recuponing!H`.

## 30.3 Banking `Carga_Posi_USD_P_Banking`

Ruta `B16`:

```text
Field 37 <> FVH
Field 41 = USD
Field 13 >= Fecha
```

Suma:

```text
AS
```

Y escribe en `PYG Recuponing!K`.

## 30.4 Conclusión

Hay **version drift** entre la macro IFRS manual y la parametrizada:

- cambia el operador de fecha (`<` vs `>`);
- cambia la columna sumada (`AP` vs `AS`).

Esto no puede homologarse por inferencia. Debe validarse cuál es la regla vigente.

Adicionalmente, el botón visible asociado a posición IFRS puede ejecutar la versión manual, no necesariamente la `_P`. Por eso el comportamiento real del usuario puede no coincidir con las rutas parametrizadas.

---

# 31. CVA-DVA

A nivel de Swap por operación:

\[
\Delta CVA/DVA_t
=
(VP^{IFRS}_t-VP^{Banking}_t)
-
(VP^{IFRS}_{t-1}-VP^{Banking}_{t-1})
\]

A nivel agregado, `RESUMEN FINAL` calcula:

\[
PYG^{CVA/DVA}=PYG^{IFRS}-PYG^{Banking}
\]

Debe mantenerse separado del PYG Banking para poder reconciliar ambos marcos contables.

---

# 32. `EXP.xlsx` — dependencia dudosa

La macro de valoración abre:

```text
Parametros!C2 -> EXP.xlsx
```

Copia A:AF hacia:

```text
Parametros!O:AT
```

Los encabezados observados incluyen:

```text
GeneratedPK
DmOwnerTable
TradeId
ExtTradeId
PorC
ProductGroup
Book
Desk
EvType
SettleCcy
OrigCcy
Ccy
Amount
Cust
ValueDate
IndexChar
Company
GrossAmountReceivable
GrossAmountPayable
AmountReceivable
AmountPayable
...
```

## 32.1 Probable bug VBA

La macro calcula:

```vb
lastRow1 = wsEXP.Cells(...).End(xlUp).Row
```

pero pega usando:

```vb
Resize(lastRow, 32)
```

`lastRow` corresponde al cálculo anterior de la hoja `SWAP`, no a `EXP`.

Lo lógico sería usar `lastRow1`.

## 32.2 Uso no evidente

No se identificaron fórmulas principales que dependan claramente de `Parametros!O:AT` para el PYG diario.

**Clasificación:** `Pendiente de negocio / legacy`.

No debería convertirse automáticamente en una dependencia obligatoria del nuevo motor sin confirmar su finalidad.

---

# 33. TITULOS — dependencia condicional

Aunque el usuario está focalizando el desarrollo en Forward, Swap, Novados y Caja, el libro actual también suma Títulos.

## 33.1 Fuente

`Parametros!B6`:

```text
ReporteTitulos_08092026.csv
```

Macro `Carga_Titulos_P`:

- parsea 76 campos separados por `;`;
- fuerza campos 6 y 7 a fecha DMY;
- filtra `Field 20 = SWAPS`;
- copia A:BS a `TITULOS`;
- agrega la fecha de corte en columna A.

Si el objetivo es reproducir **el total exacto de `RESUMEN FINAL`**, Títulos es obligatorio.

Si el objetivo es un nuevo módulo exclusivo de derivados FX/Swap/Caja, puede quedar fuera mediante una frontera funcional explícita.

---

# 34. Controles operativos existentes

La hoja `Hoja de controles` es muy valiosa porque define tolerancias que pueden convertirse en pruebas de aceptación del nuevo código.

| Control | Fórmula/criterio | Tolerancia observada |
|---|---|---:|
| Caja actualizada | fecha en `CAJA SWAP` | misma fecha del corte |
| FTP actualizado | fecha en bloque FTP de Caja | misma fecha |
| Griegas actualizadas | fecha en `GRIEGAS SWAP` | misma fecha |
| Total operaciones | `AUX!G1` vs fecha corte | igualdad |
| PYG vs Informe | diferencia total vs `GRIEGAS SWAP!K35` | **80 MM COP** |
| Delta vs Informe | Delta Informe - Delta consolidado | **160.000** |
| Control contable PYG Swap | lookup contable | **5.000 COP** |
| Control contable volumen Caja | posición vs contabilidad | **5 USD** |
| Control contable PYG Caja | PYG vs contabilidad | **1.200 COP** |
| Vínculo reporte anterior | diferencia de fechas | <= 1 día según fórmula actual |
| Residual Forward | residual / PYG | **5%** |
| Residual Swap | residual / PYG | **7%** |
| Residual Novados | residual / PYG | **5%** |
| Residual Títulos | residual / PYG | **5%** |
| Diferencia Delta IFRS | `RESUMEN FINAL!J49` | **7 MM** |
| FWD consolidado vs Informe Swap | diferencia | **50 MM COP** |
| Diferencia Títulos | nominal vs informe | **0** |
| Diferencia posición Banking | posición Recuponing vs resumen | **2 MM** |

## 34.1 Observaciones de calidad

### Control Delta IFRS

La fórmula observada usa:

```text
IF(C17 > 7000000,"Revisar","ok")
```

sin `ABS`.

Esto significa que una diferencia negativa grande podría no disparar el control. Debe validarse si es intencional o defecto.

### Controles con `fecha - 1`

Algunos controles contables buscan literalmente:

```text
fecha_corte - 1
```

Esto puede fallar en fines de semana/festivos. El nuevo motor debería usar **día hábil anterior válido**.

---

# 35. Control de residual

El residual es un elemento central de gobierno del PYG.

Para cada producto:

\[
Residual = PYGTotal - PYGExplicado
\]

Se monitorea como porcentaje del PYG total.

Tolerancias:

- Forward: 5%;
- Swap: 7%;
- Novados: 5%;
- Títulos: 5%.

Esto implica que el objetivo del motor no es únicamente producir un PYG correcto, sino producir **atribución suficientemente explicativa**.

---

# 36. Inicio de mes — estado que debe preservarse

`InicioMes2` muestra qué datos son considerados estado entre meses.

## 36.1 Curvas

- archiva `Tasas!A5:BD36` hacia un bloque histórico;
- copia la última curva como punto inicial del nuevo mes;
- limpia las curvas diarias nuevas.

## 36.2 Caja

- busca el último día del mes anterior;
- toma el saldo USD final;
- lo coloca como saldo inicial `F4`;
- limpia movimientos y FTP diarios.

## 36.3 PORTAFOLIO

- lleva fecha/TRM/EUR del cierre anterior a la fila de apertura;
- limpia PYG/VP diarios del nuevo mes.

## 36.4 SWAP

Limpia únicamente los bloques de valoraciones/pagos del mes:

```text
J:L
P:R
V:X
AB:AD
...
FV:FX
```

El maestro A:G permanece.

## 36.5 Recuponing/Griegas/Títulos

Se limpian bloques mensuales.

## 36.6 Implicación para código

Debe persistirse como mínimo:

```text
closing_market_snapshot
closing_cash_position
open_swap_master
last_swap_valuation_by_trade
last_ifrs_valuation_by_trade
last_pyg_accumulated_by_factor
recuponing_state
```

No es necesario replicar el concepto de “reiniciar hojas”; una base histórica normalizada elimina esa operación destructiva.

---

# 37. `BackUp` y persistencia

La macro `BackUp` guarda el workbook en:

```text
\ISILONSMBPROD\...\SWAP\HISTORIA\2026\PYG SWAPS_MES_YYYY-MM-DD.xlsm
```

Observaciones:

1. el año `2026` está hardcodeado;
2. usa `SaveAs`, por lo que cambia la identidad/ruta del workbook activo;
3. el histórico cumple una función de persistencia y fuente para el siguiente corte.

En código debería reemplazarse por persistencia transaccional y un artefacto de salida versionado.

---

# 38. Nombres definidos rotos y deuda técnica

El workbook contiene muchos nombres definidos con `#REF!`, por ejemplo:

```text
CAUSACIONUSD
COMPRASFWD
DEVCCE
FEMISION
PLAZO...
REEXPRESIONCOP
SALDO...
TASACOP
TASAUSD
TRM
VALORACIONCOP
VALORACIONUSD
VN...
```

El nombre funcional confirmado es:

```text
Fecha = 'RESUMEN FINAL'!$C$3
```

También existen nombres de Essbase/SmartView.

## Implicación

El nuevo desarrollo no debe intentar migrar nombres definidos como si todos fueran reglas vigentes. Muchos son residuos históricos.

---

# 39. Macros identificadas

## Módulo 1

```text
carga_fwd_dia
carga_fwd_dia_P
CARGA_FONDEO
CARGA_FT
CARGA_FT_P
CARGAR_INFO_CAJA_5_5
CARGAR_INFO_CAJA_5_P
CARGAR_VALORACION_SWAP
CARGAR_VALORACION_SWAP_P
GRIEGAS
GRIEGAS_P
SWAP
carga_dia
portafolio_tes
copiaseguridad
traecurvas
traecurvas_P
CARGAR_INFO_FWDS
CARGAR_INFO_FWDS_P
flitrar_novados
E_Recalculo
```

## Módulo 2

```text
reinicio_mes
Macro1
Tasa_Mes
InicioMes
InicioMes2
Macro2
```

## Módulo 3

```text
Llamadarectangular_Haga_clic_en
Llamadarectangular_P
```

## Módulo 4

```text
MES
```

## Módulo 5

```text
Carga_Titulos
Carga_Titulos_PP
Carga_Titulos_P
```

## Módulo 6

```text
Carga_Posi_USD_IFRS
Carga_Posi_USD_P
Carga_Posi_USD_P_Banking
```

## Módulo 7

```text
Carga_Sw_Nuevos
Carga_Sw_Nuevos_P
BackUp
```

---

# 40. Botones vs macros parametrizadas

Un hallazgo importante es que varios botones están asociados todavía a versiones manuales.

Ejemplos identificados:

```text
BackUp
CARGAR_INFO_CAJA_5_5
CARGA_FT
Carga_Sw_Nuevos
Carga_Titulos
GRIEGAS
InicioMes2
carga_fwd_dia
CARGAR_VALORACION_SWAP
Carga_Posi_USD_IFRS
Carga_Posi_USD_P_Banking
Llamadarectangular_Haga_clic_en
traecurvas
CARGAR_INFO_FWDS
flitrar_novados
E_Recalculo
```

Mientras existen paralelamente:

```text
..._P
```

que leen las rutas de `Parametros`.

## Implicación

Para diseñar el nuevo sistema hay que escoger conscientemente:

- **regla operacional vigente** — lo que realmente ejecuta el usuario mediante botones;
- **regla parametrizada objetivo** — lo que intentan hacer las macros `_P`.

No deben mezclarse sin revisión, especialmente en posición IFRS/recuponing.

---

# 41. Orden lógico de ejecución diario

El libro no tiene un único orquestador que encapsule todo. La siguiente secuencia se deduce de las dependencias y debería confirmarse con el operador, pero es una base sólida para automatización.

## Fase 0 — corte

1. Definir fecha de corte.
2. Resolver día hábil anterior.
3. Resolver rutas de los archivos.
4. Validar que todos los archivos correspondan a la fecha.

## Fase 1 — mercado/top-down

5. Cargar FWD Consolidado.
6. Cargar curvas Forward.
7. Cargar FTP COP/USD.

## Fase 2 — operaciones FX

8. Cargar Máscara FX.
9. Valorar Forwards.
10. Filtrar Novados.
11. Ejecutar lógica Novados/CRCC.
12. Actualizar `Fuente vs Instrum - TD` / agregados.

## Fase 3 — Caja

13. Cargar Reporte Caja.
14. Calcular posición, trading y delta.
15. Calcular costo de fondos.

## Fase 4 — Swaps

16. Cargar swaps nuevos.
17. Cargar VP Banking.
18. Cargar VP IFRS.
19. Incorporar Payments/flows.
20. Calcular PYG Banking/IFRS y CVA-DVA.
21. Cargar griegas del Informe Libro.
22. Cargar información de riesgo/conciliación.

## Fase 5 — Recuponing

23. Cargar/calcular posición USD IFRS.
24. Cargar/calcular posición USD Banking.
25. Calcular ajustes de recuponing.

## Fase 6 — opcionales/contabilidad

26. Cargar Títulos, si están en alcance.
27. Cargar/actualizar bases contables.
28. Ejecutar conciliaciones.

## Fase 7 — cierre

29. Consolidar `RESUMEN FINAL`.
30. Comparar contra snapshot previo.
31. Ejecutar todos los controles.
32. Persistir snapshot de cierre.
33. Generar reporte/backup.

---

# 42. Data contract recomendado

## 42.1 `calendar`

```text
valuation_date
previous_business_date
month_start_date
is_business_day
```

## 42.2 `fx_market`

```text
valuation_date
trm
EURCOP_or_EURUSD_as_required
JPY_factor_as_required
source
```

## 42.3 `curve_points`

```text
valuation_date
curve_name      # COP / USD / FORWARD_IMPLIED
term_days
rate
source
```

## 42.4 `fx_trade_master`

```text
trade_id
product_class   # FORWARD / NOVADO
side            # COMPRA / VENTA
trade_date
maturity_date
settlement_date
currency_pair
notional
forward_rate
spot_trade
settlement_mode
settlement_currency
client
book
portfolio
classification
```

## 42.5 `swap_trade_master`

```text
trade_id
client
book
instrument_type # CCS / IRS
trade_date
end_date
customer_group
fvh_flag
```

## 42.6 `swap_valuation`

```text
valuation_date
trade_id
accounting_basis # BANKING / IFRS
vp_net_cop
source
```

## 42.7 `swap_payment`

```text
payment_date
trade_id
payment_type
currency
amount_original
fx_rate
amount_cop
sign
source
```

## 42.8 `swap_pyg_factor`

```text
valuation_date
book
factor
amount_cop
source
```

Factores:

```text
TRADING
DELTA_USD
DELTA_EUR
DELTA_JPY
RHO_COP
RHO_USD
RHO_DTF
RHO_IPC
RHO_EUR
THETA
RESIDUAL
```

## 42.9 `cash_movements`

```text
valuation_date
buy_usd
buy_cop
sell_usd
sell_cop
adjustment_buy_usd
adjustment_buy_cop
adjustment_sell_usd
adjustment_sell_cop
```

## 42.10 `funding_rates`

```text
valuation_date
currency
base_rate
adjustment
pl_adjustment
final_rate
```

## 42.11 `recuponing`

```text
valuation_date
trade_id
fair_value
fair_value_adjusted
pyg_unadjusted
pyg_adjusted
position_file
position_adjustment
banking_position
```

## 42.12 `pyg_snapshot`

```text
valuation_date
accounting_basis
product
factor
amount_cop
position_usd
run_id
```

---

# 43. Reglas de negocio transversales

## 43.1 Fecha hábil

Nunca asumir `t-1 calendario` como corte anterior.

## 43.2 Trade ID

Debe ser la clave de reconciliación para Swaps y, cuando aplique, FX.

## 43.3 Signos

Formalizar en un único catálogo:

```text
COMPRA
VENTA
PAY
RECEIVE
activo
pasivo
```

Evitar replicar signos implícitos dispersos en fórmulas.

## 43.4 Operaciones nuevas

El componente Trading diferencia operaciones cuyo `trade_date = valuation_date`.

## 43.5 Operaciones vencidas

Después de vencimiento/liquidación, VP y sensibilidades deben dejar de contribuir, salvo la liquidación correspondiente.

## 43.6 `SIN ENTREGA`

Debe disparar reglas especiales de fixing/settlement.

## 43.7 `FVH`

Se excluye en diversos procesos de Swap.

## 43.8 Banking vs IFRS

Nunca combinar valoraciones antes de calcular la diferencia CVA-DVA/recuponing.

## 43.9 Residual

Todo PYG no explicado debe quedar visible y controlado; no debe “desaparecer” en ajustes manuales.

---

# 44. Matriz producto -> insumos

| Insumo | Forward | Novados | Swap | Caja |
|---|:---:|:---:|:---:|:---:|
| Máscara FX | ✓ | ✓ |  |  |
| FWD Consolidado | ✓ control/top-down | ✓ top-down |  | puede aportar contado |  |
| Curva Forward | ✓ | ✓ |  |  |
| TRM t/t-1 | ✓ | ✓ | posición/riesgo indirecto | ✓ |
| Curva COP t/t-1 | ✓ | ✓ | griegas externas |  |
| Curva USD t/t-1 | ✓ | ✓ | griegas externas |  |
| SwapTotal Banking |  |  | ✓ |  |
| SwapTotal IFRS |  |  | ✓ |  |
| Payments/flows por Trade ID |  |  | **✓ crítico** |  |
| Informe Libro de Swaps |  |  | ✓ griegas/risgo |  |
| Reporte Caja Liviano |  |  |  | ✓ |
| FTP COP |  |  |  | ✓ |
| FTP USD |  |  |  | ✓ |
| Recuponing/posición USD |  |  | ✓ IFRS |  |
| Snapshot t-1 | ✓ | ✓ | ✓ | ✓ |

---

# 45. Archivos mínimos para un PYG diario funcional

## Escenario A — replicar el libro completo actual

Obligatorios:

1. FWD Consolidado.
2. Reporte Caja Liviano.
3. FTP COP.
4. FTP USD.
5. Informe Libro de Swaps.
6. Reporte Títulos.
7. SwapTotal Banking.
8. SwapTotal IFRS.
9. SwapTotal IFRS Flujos.
10. Curva Forward.
11. Máscara FX.
12. SwapTotal Banking Flujos.
13. fuente efectiva de Payments Report.
14. estado/snapshot anterior.
15. datos contables si se exige cierre de controles.
16. `EXP.xlsx` solo si negocio confirma que sigue vigente.

## Escenario B — PYG de Forward + Swap + Novados + Caja, sin Títulos

Obligatorios:

1. FWD Consolidado — al menos como benchmark durante migración.
2. Máscara FX.
3. Curva Forward/mercado.
4. Reporte Caja.
5. FTP COP.
6. FTP USD.
7. SwapTotal Banking.
8. SwapTotal IFRS — si se requiere IFRS.
9. Informe Libro de Swaps — hasta reemplazar todos los factores por código propio.
10. reportes de flujos/posición para recuponing.
11. Payments por Trade ID.
12. snapshot de `t-1`.

---

# 46. Insumos que faltan si ya existe el código de Delta

El usuario indicó que ya existe código de posición Delta. Para completar PYG no basta ese módulo.

## 46.1 Valoración

Se requiere:

```text
VP Forward t / t-1
VP Novado t / t-1
VP Swap Banking t / t-1
VP Swap IFRS t / t-1
```

## 46.2 Flujos

```text
liquidaciones Forward
liquidaciones Novado
cupones Swap
amortizaciones Swap
principal exchanges
cash movements
```

## 46.3 Mercado

```text
TRM t/t-1
curva COP t/t-1
curva USD t/t-1
curva implícita Forward t/t-1
fixings
```

## 46.4 Otros factores

```text
Trading
Rhos
Theta
CVA-DVA
Recuponing
Costo de Fondos
Residual
```

---

# 47. Arquitectura recomendada para migrar a Python/servicio

```text
                    ┌────────────────────────┐
                    │      File Resolver      │
                    │ fecha / rutas / control │
                    └───────────┬────────────┘
                                │
               ┌────────────────┴────────────────┐
               │                                 │
       ┌───────▼────────┐                ┌───────▼────────┐
       │ Ingesta Mercado │                │ Ingesta Trades │
       │ curvas, TRM, FTP│                │ FX, Swap, flows│
       └───────┬────────┘                └───────┬────────┘
               │                                 │
       ┌───────▼─────────────────────────────────▼───────┐
       │              Normalización / Data Quality       │
       └───────────────┬─────────────────────────────────┘
                       │
       ┌───────────────┼───────────────────────────────┐
       │               │               │               │
┌──────▼──────┐ ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
│Forward Engine│ │Novado/CRCC  │ │ Swap Engine │ │ Cash Engine │
└──────┬──────┘ └──────┬──────┘ └─────┬──────┘ └──────┬──────┘
       │               │               │               │
       └───────────────┴───────┬───────┴───────────────┘
                               │
                    ┌──────────▼──────────┐
                    │ PYG Attribution     │
                    │ Delta/Rho/Theta/... │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Banking / IFRS      │
                    │ CVA + Recuponing    │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Consolidation       │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Controls / Reconcile│
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ Snapshot / Reporting│
                    └─────────────────────┘
```

---

# 48. Diseño modular recomendado

```text
pyg/
├── config/
│   ├── settings.py
│   └── paths.py
├── calendar/
│   └── business_dates.py
├── ingestion/
│   ├── fwd_consolidated.py
│   ├── fx_mask.py
│   ├── swap_total.py
│   ├── swap_flows.py
│   ├── libro_swaps.py
│   ├── cash_report.py
│   ├── curves.py
│   ├── ftp.py
│   └── accounting.py
├── models/
│   ├── forward.py
│   ├── novado.py
│   ├── swap.py
│   ├── cash.py
│   └── common.py
├── valuation/
│   ├── forward.py
│   ├── novado_crcc.py
│   └── swap.py
├── attribution/
│   ├── delta.py
│   ├── rho.py
│   ├── theta.py
│   ├── trading.py
│   └── residual.py
├── ifrs/
│   ├── cva_dva.py
│   └── recuponing.py
├── controls/
│   ├── source_controls.py
│   ├── reconciliation.py
│   └── residuals.py
├── persistence/
│   └── snapshots.py
└── reporting/
    └── summary.py
```

---

# 49. Validaciones de ingestión obligatorias

Antes de calcular:

## Archivo

- existe;
- se puede leer;
- no está vacío;
- corresponde a la fecha de corte;
- tiene las columnas esperadas.

## Operaciones

- Trade ID no nulo;
- Trade ID no duplicado inesperadamente;
- fechas válidas;
- nominal numérico;
- moneda soportada;
- book válido;
- modalidad válida.

## Mercado

- curva para `t`;
- curva para `t-1`;
- nodos suficientes para interpolar;
- TRM disponible;
- no existen saltos/valores nulos.

## Swap

- todos los Trade IDs del maestro tienen valoración o una razón válida de ausencia;
- todas las operaciones con payment tienen flujo reconocido;
- Banking e IFRS se pueden reconciliar.

---

# 50. Pruebas de aceptación recomendadas

Además de replicar la `Hoja de controles`, crear pruebas por Trade ID.

## Forward

Para una muestra de operaciones:

```text
VP_t nuevo == VP_t Excel
VP_t-1 nuevo == VP_t-1 Excel
PYG diario == AB Excel
Delta == AC+AD según convención
Rho COP == AE
Rho USD == AF
Trading == AI
Theta == AJ
```

## Novado

Comparar:

```text
VP Forward
Valoración cámara
PYG Diario
PYG Cámara
Delta CRCC
Curva COP Cámara
Curva USD Cámara
Tiempo CRCC
posición neta
```

## Swap

Por Trade ID:

```text
VP Banking
VP IFRS
Payment
PYG Banking
PYG IFRS
CVA-DVA
```

## Caja

Por fecha:

```text
saldo USD
trading
delta intraday
delta interday
costo COP
costo USD
PYG diario
PYG acumulado
```

---

# 51. Puntos que deben validarse con negocio antes de cerrar la especificación

## P0 — crítico

### 1. Fuente de `Payments Report`

¿Cuál archivo/campo alimenta el payment por Trade ID y cuál es la convención de signos?

### 2. Posición USD IFRS vigente

¿Cuál lógica es la oficial?

**Manual:**

```text
Field13 < Fecha, suma AP
```

**Parametrizada:**

```text
Field13 > Fecha, suma AS
```

### 3. Día anterior válido

¿El vínculo al 06/09 para corte 08/09 es correcto por calendario hábil o es un atraso?

## P1 — alta

### 4. Uso vigente de `EXP.xlsx`

¿Es requerido para un cálculo que no se observa directamente en las fórmulas?

### 5. Fuente de `Ajuste recuponing`

¿Cómo se actualiza diariamente esta hoja?

### 6. Títulos

¿El nuevo motor de PYG debe mantener Títulos dentro del consolidado o se separará definitivamente?

## P2 — media

### 7. Macros manuales vs `_P`

¿Cuáles son hoy las macros oficialmente utilizadas por operación?

### 8. Arbitraje

La lógica aparece en hojas/bloques pero varias cargas están comentadas. Confirmar si está fuera de alcance.

---

# 52. Riesgos técnicos detectados

## 52.1 Dependencia de posición física de columnas

Varias macros dependen de letras de columnas fijas (`BD`, `AS`, etc.). Un cambio de formato del reporte rompe silenciosamente el proceso.

**Recomendación:** mapear por nombre de encabezado.

## 52.2 `End(xlDown)`

Múltiples macros utilizan `End(xlDown)`, sensible a huecos en datos.

**Recomendación:** identificar última fila robustamente y validar continuidad.

## 52.3 Macros no idempotentes

Varias cargas agregan al final.

**Recomendación:** `upsert` por clave y fecha.

## 52.4 Año hardcodeado

`BackUp` usa 2026.

## 52.5 `fecha - 1` calendario

Puede fallar fines de semana/festivos.

## 52.6 Nombres definidos rotos

No deben migrarse sin depuración.

## 52.7 Version drift

Manual y parametrizado no siempre son equivalentes.

## 52.8 Fórmulas de cierre

Theta/Residual absorben diferencias. Al replicar el resultado hay que decidir si se desea:

- imitar exactamente el cierre Excel;
- o calcular un Theta económico independiente y dejar todo lo restante en residual.

---

# 53. Recomendación de estrategia de migración

## Fase 1 — réplica controlada

Objetivo: igualar Excel.

- consumir las mismas fuentes;
- mantener Informe Libro para griegas;
- reproducir Forward/Novado/Caja;
- reproducir Swap VP + Payments;
- guardar snapshots;
- emitir controles equivalentes.

## Fase 2 — independencia gradual

- reemplazar Delta externo por módulo propio;
- reemplazar Rho;
- reemplazar Theta;
- eliminar dependencias de pivots y Excel histórico.

## Fase 3 — motor definitivo

- valoraciones y atribuciones propias;
- Excel solo como benchmark temporal;
- fuentes leídas de interfaces estables;
- trazabilidad por run y Trade ID.

---

# 54. Tabla final: archivo -> campo -> regla -> producto

| Archivo | Hoja/campo | Transformación | Producto/uso |
|---|---|---|---|
| FWD Consolidado | Macro C3 | fecha | corte |
| FWD Consolidado | Macro C6 | TRM | Forward/Caja/control |
| FWD Consolidado | Macro C7 | EUR | riesgo/FX |
| FWD Consolidado | Informe Books AK/AL | VP/PYG | Forward Banking top-down |
| FWD Consolidado | Informe IFRS AK/AL | VP/PYG | Forward IFRS top-down |
| FWD Consolidado | Books Contado | VP/PYG | contado/caja |
| FWD Consolidado | Books Novado | VP/PYG | Novado benchmark |
| Máscara FX | Field12=SWAPS | filtrar book | Forward/Novado |
| Máscara FX | C:P | normalizar campos | Forward/Novado |
| Curva Forward | CURVAS A30:AU30 | snapshot | valoración FX |
| Reporte Caja | AP:AS | compras/ventas | Caja |
| FTP COP | D12 + L12 | tasa final | costo fondos |
| FTP COP | E12 | PL | costo fondos |
| FTP USD | D11 | tasa USD | costo fondos |
| FTP USD | E11 | PL | costo fondos |
| SwapTotal Banking | B | Trade ID | maestro/valoración |
| SwapTotal Banking | BD | VP_NET_COP | VP Banking |
| SwapTotal IFRS | B | Trade ID | cruce IFRS |
| SwapTotal IFRS | BD | VP_NET_COP | VP IFRS |
| SwapTotal Flujos | AJ/AO/AS | tipo/moneda/VP riesgo | riesgo/control |
| Informe Libro | Historico Griegas PyG | copia del corte | factores PYG |
| Informe Libro | Mercado-Balance | delta multimoneda | posición/riesgo |
| Informe Libro | RIESGOS LIBRO | copia | controles |
| IFRS Flujos | filtros | posición USD | Recuponing IFRS |
| Banking Flujos | filtros | posición USD | Recuponing Banking |
| Histórico PYG | RESUMEN FINAL | snapshot anterior | variación diaria |
| EXP | A:AF | copia a Parametros | pendiente de validar |

---

# 55. Checklist de insumos para correr el día

Antes de lanzar el cálculo, debería existir un checklist automático como:

```text
[ ] fecha de corte válida
[ ] fecha hábil anterior resuelta
[ ] FWD Consolidado disponible y con fecha correcta
[ ] Máscara FX disponible
[ ] Curva Forward t disponible
[ ] Curva Forward t-1 disponible
[ ] Reporte Caja disponible
[ ] FTP COP disponible
[ ] FTP USD disponible
[ ] SwapTotal Banking disponible
[ ] SwapTotal IFRS disponible
[ ] SwapTotal Banking Flujos disponible
[ ] SwapTotal IFRS Flujos disponible
[ ] Informe Libro de Swaps disponible
[ ] Payments por Trade ID disponible
[ ] snapshot t-1 disponible
[ ] posición de apertura Caja disponible
[ ] maestro de swaps actualizado
[ ] contabilidad disponible, si se ejecutará cierre contable
[ ] Títulos disponibles, si están dentro del alcance
```

---

# 56. Salidas mínimas del nuevo proceso

## Detalle

### Forward

```text
trade_id
vp_t_minus_1
vp_t
liquidation_pyg
daily_pyg
delta_interday
delta_intraday
rho_cop
rho_usd
spread
base_maturity
trading
theta
```

### Novado

Agregar además:

```text
camera_valuation
camera_pyg
crcc_interday_valuation
crcc_delta
crcc_cop_curve_effect
crcc_usd_curve_effect
crcc_theta
```

### Swap

```text
trade_id
vp_banking_t_minus_1
vp_banking_t
vp_ifrs_t_minus_1
vp_ifrs_t
payment
pyg_banking
pyg_ifrs
cva_dva_change
```

### Caja

```text
opening_usd
buy_usd
sell_usd
closing_usd
buy_rate
sell_rate
trm
trading
delta_intraday
delta_interday
funding_cop
funding_usd
pyg_total
```

## Agregado

```text
valuation_date
basis
product
factor
amount_cop
```

---

# 57. Trazabilidad requerida

Cada resultado debería poder responder:

```text
¿Qué archivo lo originó?
¿Qué fila/Trade ID?
¿Qué corte?
¿Qué curva?
¿Qué versión del código?
¿Qué payment/flujo?
¿Qué fórmula/regla?
¿Qué snapshot previo?
```

Se recomienda un `run_id` único por ejecución.

---

# 58. Conclusión funcional

Para reproducir la lógica del archivo, el PYG diario no puede construirse únicamente con una posición Delta.

El cálculo completo requiere cuatro grandes capas:

## 1. Revaluación

\[
VP_t - VP_{t-1}
\]

para cada producto/operación.

## 2. Flujos

```text
liquidaciones
payments
cupones
amortizaciones
principal
movimientos de caja
```

## 3. Explicación del movimiento

```text
Trading
Delta
Rho
Theta
Spread
Base/Vencimiento
Costo de fondos
CVA-DVA
Recuponing
Residual
```

## 4. Estado y reconciliación

```text
snapshot anterior
Banking
IFRS
contabilidad
Informe Libro
FWD Consolidado
controles de tolerancia
```

La fórmula más importante a preservar para Swap es:

\[
\boxed{PYG_t = VP_t - VP_{t-1} + Payment_t}
\]

Y la decisión técnica más importante es **no copiar la estructura física del Excel**, sino convertir sus reglas en un modelo normalizado, persistente e idempotente.

---

# 59. Prioridades inmediatas para continuar el desarrollo

Antes de programar el motor de PYG completo, recomiendo cerrar en este orden:

1. **Definir oficialmente la fuente de `Payments Report` por Trade ID.**
2. **Confirmar la lógica vigente de posición USD IFRS/recuponing.**
3. **Formalizar el calendario de día hábil anterior.**
4. **Decidir si Títulos forma parte del alcance.**
5. **Confirmar si `EXP.xlsx` tiene una función vigente.**
6. **Confirmar cómo se actualiza `Ajuste recuponing`.**
7. **Establecer el data contract de operaciones, valoraciones, flujos y mercado.**
8. **Implementar snapshots persistentes.**
9. **Replicar los controles actuales como pruebas automáticas.**
10. **Comparar por Trade ID y factor contra Excel antes de retirar la dependencia del libro.**

---

# 60. Apéndice — hallazgos de control del archivo analizado

En el corte revisado se observan, entre otros:

- Caja: `ok`.
- FTP: `ok`.
- Griegas: `ok`.
- Total operaciones: `Revisar` por diferencia de fecha en `AUX!G1`.
- PYG vs Informe: dentro de tolerancia.
- Delta vs Informe: dentro de tolerancia, muy cerca del umbral.
- vínculo reporte anterior: `Revisar`.
- residual Forward: `ok`.
- residual Swap: `Revisar`.
- residual Títulos: `Revisar`.
- diferencia Delta IFRS: `ok` según fórmula vigente.
- FWD Consolidado vs Informe Swap: `ok`.
- diferencia Títulos: `ok`.
- diferencia posición Banking: `ok`.

Estos resultados no deben tomarse como prueba de que las cifras cacheadas del workbook estén listas para un benchmark definitivo; varios controles indican que el corte requiere refresco/revisión.

---

# 61. Apéndice — qué NO conviene replicar literalmente

No replicar:

- 6 columnas por cada día del mes en `SWAP`;
- copias manuales de fórmulas;
- `VLOOKUP/HLOOKUP` como mecanismo de integración;
- enlaces al workbook del día anterior;
- rutas hardcodeadas por año;
- macro botones que abren diálogos;
- nombres definidos rotos;
- estados mensuales borrados y recopiados;
- `End(xlDown)` como detección de última fila;
- dependencia de letras físicas de columna del archivo fuente.

Sí replicar:

- reglas de elegibilidad;
- fórmulas económicas;
- sign convention;
- granularidad Trade ID;
- distinción Banking/IFRS;
- Payments;
- acumulados/snapshot;
- controles y tolerancias;
- reconciliación contra fuentes independientes.

---

# 62. Resultado final del análisis

La lógica de negocio del libro puede sintetizarse como:

```text
FORWARD
  operaciones FX + curvas + TRM + liquidaciones
  -> VP t/t-1
  -> PYG
  -> Delta/Rho/Trading/Theta/Residual

NOVADO
  subconjunto SWAPSNOVADO de FX
  + curvas + reglas CRCC/cámara
  -> VP / cámara
  -> PYG y factores CRCC

SWAP
  maestro persistente
  + VP Banking t/t-1
  + VP IFRS t/t-1
  + Payments
  -> PYG Banking/IFRS
  -> CVA-DVA
  + Informe Libro
  -> Trading/Delta/Rho/Theta/Residual
  + recuponing

CAJA
  compras/ventas USD-COP
  + saldo inicial
  + TRM
  -> Trading + Delta intra/inter
  + FTP COP/USD
  -> costo de fondos

TODOS
  + snapshot previo
  + controles
  + reconciliación contable
  -> RESUMEN FINAL diario
```

Este es el conjunto de lógica e insumos que debería servir como especificación funcional de base para construir el nuevo proceso de PYG diario.
