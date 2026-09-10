# Position Monitor — corte preliminar intradía

## Alcance

El corte intradía es independiente del cierre oficial. Para el 18/08/2026
incluye únicamente la vista **Banking** de Forward, Novados, Opciones, Swap y
Spot. No calcula ni publica IFRS o CVA/DVA y no tiene productos pendientes.

La corrida no actualiza `tbl_posicion_actual`, `tbl_posicion_historico` ni las
tablas oficiales por producto. Spot se calcula sobre un clon de `risko.db` para
tomar como ancla la posición acumulada del 17/08/2026.

## Selección de versiones

Vector usa el patrón de la fecha y escoge el sufijo numérico más alto entre los
archivos completos. `_002` tiene precedencia sobre `_001`, y `_001` sobre
`_000`; una versión vacía o menor a 1 KB se ignora hasta que termine de
generarse. El nombre original se conserva para auditoría.

| Producto | Patrón |
|---|---|
| Forward | `USR_Posicion_Fwd_Intradia_ddmmaaaa_*.xls` |
| Novados | `USR_Posicion_Novado_Intradia_ddmmaa_*.xls` |
| Swap operaciones | `USR_Posicion_Swaps_Intraday_ddmmaa_*.xls` |
| Swap flujos | `USR_Posicion_Swaps_Intraday_Flujos_ddmmaa_*.xls` |
| Spot/Caja | `USR_Caja_Intradia_ddmmaa_*.xls` |
| Opciones | `USR_OPT_INTRADIA_ddmmaa_*.xls` |

Opciones también requiere `ENTRADA2.xlsb` para curvas y superficie, y
`Insumo tasas.xlsx` para el spot de reproceso.

## Spot de revaloración de Opciones

El spot intradía se resuelve por el encabezado `SETFX`, no por una letra fija.

El dashboard preliminar muestra este mismo valor en el banner azul, después de
la fecha de posición, con la etiqueta `PROMEDIO SETFX`. No se agrega como tabla
ni como tarjeta del cuerpo. El valor se transporta desde la revaloración de
Opciones; no se vuelve a leer ni se recalcula durante la construcción del HTML.
La información no aparece en el dashboard de cierre.
En el archivo del 18/08/2026 es el cuarto campo de datos después de `Fecha`
(columna E física de Excel) y vale **3.094,91**. La columna D física es `DIAS` y
no es numérica. Resolver por encabezado evita valorar con el campo equivocado si
se insertan o desplazan columnas.

## Resultado del 18/08/2026

Archivos seleccionados en la publicación:

| Producto | Archivo |
|---|---|
| Forward | `USR_Posicion_Fwd_Intradia_18082026_001.xls` |
| Novados | `USR_Posicion_Novado_Intradia_180826_002.xls` |
| Swap operaciones | `USR_Posicion_Swaps_Intraday_180826_001.xls` |
| Swap flujos | `USR_Posicion_Swaps_Intraday_Flujos_180826_001.xls` |
| Spot | `USR_Caja_Intradia_180826_001.xls` |
| Opciones | `USR_OPT_INTRADIA_180826_001.xls` |

Posición Banking canónica, antes de los filtros visuales del dashboard:

| Producto | Posición USD |
|---|---:|
| Forward | -189.391,22 |
| Novados | 1.330.803.956,74 |
| Opciones | -29.006.739,73 |
| Swap | 4.619.346,29 |
| Spot | -184.529.130,30 |
| **Total** | **1.121.698.041,78** |

Novados conserva `VALOR SENSIBLE` para las operaciones anteriores al corte. En
el proceso intradía únicamente, las operaciones cuya `FECHA NEGOCIACION`
coincide con la fecha del corte usan el `NOMINAL` firmado, porque Summit informa
su sensibilidad en cero durante el día. El cierre oficial conserva su lógica
original. En el archivo `_002` del 20/08/2026, cuatro operaciones aplican esta
regla y aumentan la posición de Novados en USD 4.000.000.

## Interfaz y trazabilidad

La interfaz distingue **Ejecutar cierre** de **Ejecutar intradía**. El segundo
publica el HTML con las marcas `PRELIMINAR INTRADÍA` y
`Solo Banking · Sin IFRS/CVA-DVA`.

`publicacion.json` conserva estado, productos incluidos y pendientes, controles
de calidad, archivo elegido, sufijo, tamaño y SHA-256 de cada insumo.
