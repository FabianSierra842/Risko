# Mapa funcional — PyG / Book Opciones

## Semántica correcta

El dashboard es genérico y su primer book es `OPCIONES`. El corte del
13/08/2026 es acumulado mensual desde el 31/07/2026.

`RESUMEN FINAL!C1:H22` separa:

- filas 7–14: contribuciones al PyG;
- fila 15: total Banking;
- fila 16: CVA;
- fila 17: total IFRS;
- filas 19/22: posiciones Banking/IFRS en USD.

Las filas 19/22 no son PyG. Se consultan en `risko.db` solo para validar el
portafolio usado; el resultado publicado contiene `DELTA_PYG`, no Delta posición.

## Mapeo C1:H22

| Componente canónico | Fila | Forward | Opciones | Caja |
|---|---:|---|---|---|
| `THETA` | 7 | `GRIEGAS OPC!AG16` | `AG22` | 0 |
| `DELTA_PYG` | 8 | `AG17` | `AG23` | `CAJA OPCIONES!M36` |
| `RHO` | 9 | `AG18` | `AG24` | 0 |
| `VEGA` | 10 | 0 | `AG25` | 0 |
| `TRADING` | 11 | `AG20` | `AG26` | `K36+L36` |
| `AJUSTES` | 12 | 0 | 0 | 0 |
| `COSTO_FONDOS` | 13 | 0 | 0 | `AH36` |
| `EPSILON` | 14 | residual | residual | 0 |
| `PYG_BANKING` | 15 | `PORTAFOLIO!I36+J36` | `G36` | `F48+F13` |
| `CVA` | 16 | IFRS−Banking | IFRS−Banking | 0 |
| `PYG_IFRS` | 17 | `PORTAFOLIO!I75+J75` | `G75` | Banking |

El motor vuelve a sumar las columnas diarias de `GRIEGAS OPC` y valida las
identidades Banking/CVA/IFRS. La máxima diferencia del corte es COP 1,1262,
explicada por redondeos de Caja; la tolerancia parametrizada es COP 2.

## Resultado MTD del 13/08/2026

| Contribución | Forward | Opciones | Caja | Book Opciones |
|---|---:|---:|---:|---:|
| Theta | -151.914.095,65 | 286.935.531,80 | 0,00 | 135.021.436,15 |
| Delta PyG | -1.004.053.315,51 | 459.227.091,26 | 343.808.150,98 | -201.018.073,26 |
| Rho | -29.703.089,36 | -76.968.534,19 | 0,00 | -106.671.623,55 |
| Vega | 0,00 | -14.400.284,85 | 0,00 | -14.400.284,85 |
| Trading | 46.650.610,42 | 139.529.524,57 | 300.085.000,00 | 486.265.134,98 |
| Ajustes | 0,00 | 0,00 | 0,00 | 0,00 |
| Costo fondos | 0,00 | 0,00 | -149.734.465,23 | -149.734.465,23 |
| Épsilon | -32.043.408,40 | 38.379.145,03 | 0,00 | 6.335.736,63 |
| **Banking** | **-1.171.063.298,49** | **832.702.473,60** | **494.158.685,82** | **155.797.860,86** |
| CVA | 1.861.249,08 | -37.268.900,69 | 0,00 | -35.407.651,55 |
| **IFRS** | **-1.169.202.049,42** | **795.433.572,91** | **494.158.685,82** | **120.390.209,31** |

## Control de posiciones

| Producto PyG | Tabla Position Monitor | Banking USD | IFRS USD |
|---|---|---:|---:|
| Forward | `tbl_posicion_forward`, book Opciones | 29.916.435,95 | 29.915.849,18 |
| Opciones | `tbl_posicion_opciones`, book Opciones | -29.366.297,96 | -29.366.297,96 |
| Caja | `tbl_posicion_spot`, book Opciones | 5.170.474,12 | 5.170.474,12 |

La diferencia máxima contra las filas 19/22 es menor a USD 0,000001.

## Hallazgos del código base

`Opciones_FF_V3.py` construye escenarios diarios de fecha, spot, curvas y
volatilidad. Sin embargo, los datasets históricos regenerados no conservan
todos los ajustes pegados en `GRIEGAS OPC`; por ejemplo, algunas asignaciones de
Theta y Delta de los días 3, 6 y 10 de agosto difieren del libro mensual. Por
eso no se sobreescriben esos ajustes con un recálculo retrospectivo.

En el último día, 13/08/2026, los motores independientes sí reprodujeron los
controles diarios del Dataset:

| Producto | Atribución calculada | Diferencia máxima contra hoja `PYG` |
|---|---|---:|
| Opciones | Theta, Delta PyG, Rho, Vega y nuevos/otros | COP 0,000012 por componente; COP 0,000001 en total |
| Forward | Theta, Delta PyG, Rho y nuevos/otros | COP 0,000000015 |
| Caja | Delta PyG y nuevos/otros | COP 0,0000026 |

La reconstrucción futura debe guardar cada corrida diaria inmutable y luego
acumularla. Hasta completar ese backfill, el estado sigue siendo `PRELIMINAR`.
