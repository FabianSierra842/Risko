# Control Vector para carga de insumos Risko

## Objetivo

`Risko` usa `Herramientas/VECTOR/VECTOR.py` como capa operativa de carga de
archivos antes de ejecutar los calculos de Position Monitor.

La configuracion vigente esta en:

- `proyectos/position_monitor/configuracion/risko.json`

El objetivo es que la interfaz pueda:

- limpiar la carpeta local de insumos cuando se requiera;
- ejecutar todos los modulos en orden;
- ejecutar un modulo individual sin limpiar los demas insumos;
- validar que los archivos esperados existen antes del calculo;
- dejar logs de la carga en la carpeta de registros de Risko.

## Carpeta local de trabajo

Todos los flujos copian insumos a:

- `datos/insumos`

La limpieza de esta carpeta es un flujo separado. Por eso se puede probar un
producto puntual sin borrar los insumos ya cargados.

## Flujos configurados

| Flujo Vector | Uso | Fuente principal |
| --- | --- | --- |
| `00_Limpiar_Insumos` | elimina insumos locales temporales | `datos/insumos` |
| `01_Forward` | carga Forward Banking e IFRS | `\\SUMMITFS001\apl\Internos\GR\VALORACION_FWD` |
| `02_Novados` | carga Novados | `\\SUMMITFS001\apl\Internos\GR\FUTURE_TOTAL` |
| `03_Renta_Fija` | carga Titulos | `\\SUMMITFS001\apl\Internos\GR\TRADEPL` |
| `04_Opciones` | carga Opciones, mercado auxiliar e historico TRM | Summit, BDB y Compliance de Tesoreria |
| `05_Swaps` | carga Swaps Banking e IFRS | `\\SUMMITFS001\apl\Internos\GR\SWAP_TOTAL` |
| `06_Spot` | carga Spot/Caja e historico TRM | Summit y Compliance de Tesoreria |

## Regla especial de opciones

Los archivos de opciones se generan al dia habil siguiente y contienen la
informacion del dia habil anterior.

Ejemplo:

- corte `22/06/2026`
- archivo usado: `USR_OPT_MANANA_230626_000.xls`

Por eso el flujo `04_Opciones` usa la variable:

- `{next_bday_ddmmyy}`

El modulo de opciones ya no exige `USR_OPT_FWD`. La excepcion que aun sigue
fuera de Summit es:

- `ENTRADA2.xlsb`

Este archivo sigue viniendo de la carpeta BDB mientras se migra su fuente.

La TRM de Opciones ya no se toma de `Curva Forward V2.xlsm`. Vector copia el
archivo estable `Insumo tasas.xlsx` desde Compliance de Tesoreria y el modulo
selecciona en la hoja `TRM` la fila de la fecha de corte.

## Ejecucion desde la interfaz

La interfaz de `Risko` expone estos controles:

- `Limpiar insumos`: ejecuta solo `00_Limpiar_Insumos`.
- `Ejecutar todo`: limpia, carga cada modulo con Vector, calcula productos,
  consolida y genera el dashboard.
- Botones por producto: ejecutan el flujo Vector del producto y luego su
  calculo, sin limpiar la carpeta completa.
- `Generar tablero`: reconsolida desde SQLite, usa CSV procesados solo como
  fallback temporal, y exporta el HTML.

## Ejecucion por CLI

Validacion seca de un flujo:

```powershell
python Herramientas\VECTOR\VECTOR.py --cli --config proyectos\position_monitor\configuracion\risko.json --fecha 22/06/2026 --flow-name 04_Opciones --dry-run
```

Ejecucion real de un flujo:

```powershell
python Herramientas\VECTOR\VECTOR.py --cli --config proyectos\position_monitor\configuracion\risko.json --fecha 22/06/2026 --flow-name 04_Opciones --no-dry-run
```

Validacion seca de todos los flujos:

```powershell
python Herramientas\VECTOR\VECTOR.py --cli --config proyectos\position_monitor\configuracion\risko.json --fecha 22/06/2026 --all --dry-run
```

## Reglas de consolidacion posteriores a la carga

La carga de archivos no publica posicion. Despues de Vector, cada modulo Python
produce su tabla canonica y `consolidacion.py`:

- conserva solo `Banking` y `CVA/DVA` en las tablas consolidadas;
- excluye `IFRS` de la consolidada, aunque el producto lo pueda calcular;
- actualiza la tabla del producto en `datos/base de datos/risko.db`;
- reemplaza la fecha ejecutada en `tbl_posicion_consolidada` y `tbl_posicion_actual`;
- publica en `tbl_posicion_historico` solo fechas de cierre operativo de mes;
- intenta refrescar los CSV publicados solo como copia de compatibilidad.

Los modulos de producto no deben copiar insumos desde las fuentes. Deben validar
que Vector haya dejado los archivos locales esperados en `datos/insumos`.

## TRM

La consolidacion vigente no homogeneiza posiciones a COP/USD. Si un modulo
necesita TRM para su calculo interno, debe documentar esa dependencia y validar
que el insumo local exista.

La referencia historica de TRM oficial es:

- `\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\2 Jefatura de Compliance de Tesorería\Insumos CT\Tasas\Insumo tasas.xlsx`

Hoja:

- `TRM`

Contrato de lectura:

- columna A: `Fecha`;
- columna B: `FORMADA`.

Vector copia ese workbook a `datos/insumos/Insumo tasas.xlsx` en los flujos
`04_Opciones` y `06_Spot`. La consulta exige una coincidencia exacta de fecha.
Si la fecha no existe o `FORMADA` esta vacia, el proceso se detiene; no usa
`VIGENTE`, no retrocede a otra fecha y no vuelve a `Curva Forward V2.xlsm`.
