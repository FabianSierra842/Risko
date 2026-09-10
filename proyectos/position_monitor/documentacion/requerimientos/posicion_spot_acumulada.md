# Posición Spot acumulada desde Reporte de Caja

## 1. Objetivo y estado

El módulo existente `Spot` de Risko calcula la posición diaria acumulada en USD
por posición de riesgo a partir del `Reporte de Caja` sin DP. No se creó otro
módulo, otra aplicación ni otra base de datos.

La implementación reutiliza:

- el botón individual `Spot` de la interfaz actual;
- el hilo de trabajo en segundo plano de la interfaz;
- el flujo Vector `06_Spot`;
- `param_libros.csv` como fuente de verdad del mapeo;
- `tbl_posicion_spot` como tabla canónica del producto;
- `risko.db` o `risko_pruebas.db`, según el modo seleccionado.

Spot continúa fuera de `Ejecutar todo` mientras termina la validación funcional.
La prueba descrita en este documento se hizo en una base temporal y no modificó
`risko.db`.

## 2. Archivos y procedencia

| Uso | Ruta | Tratamiento |
|---|---|---|
| Fuente diaria Summit | `\\SUMMITFS001\apl\Internos\GR\REP_CAJA\Cierre_ReporteCaja_DDMMYY_000.xls` | Vector copia el archivo del corte a `datos/insumos` |
| Libro operativo sin DP | `\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\FORWARDS\INFORMES\2.CAJA\ReporteCaja(Sin DP).xlsb` | Referencia para validar compras/ventas; Risko no lo modifica ni toma de allí posiciones iniciales |
| Libro con DP | `...\2.CAJA\ReporteCaja(con DP).xlsb` | No se usa en este cálculo |
| Parámetro inicial Spot | `proyectos/position_monitor/configuracion/param_posiciones_iniciales_spot.xlsx` | Única fuente Excel para las posiciones iniciales aprobadas |
| Mapeo oficial | `proyectos/position_monitor/configuracion/param_libros.csv` | Define BOOK, posición homologada, estado, libro de riesgo e instrumento |
| Configuración | `proyectos/position_monitor/configuracion/risko.json` | Owners incluidos y ubicación del Excel paramétrico propio |
| Base productiva | `datos/base de datos/risko.db` | Solo cuando la interfaz no está en modo pruebas |
| Base de pruebas | `datos/base de datos/risko_pruebas.db` | Se usa al activar `Usar base de pruebas` |

Aunque la fuente Summit termina en `.xls`, internamente es texto delimitado por
punto y coma. No se abre con Excel para calcular.

## 3. Componentes de código

| Archivo | Responsabilidad |
|---|---|
| `proyectos/position_monitor/procesos/spot.py` | Lectura, validación, cálculo decimal, acumulado, persistencia, auditoría e importación del parámetro propio |
| `proyectos/position_monitor/procesos/parametros_libros.py` | Normalización común de libros y soporte del indicador `ACTIVO` |
| `aplicaciones/interfaz_risko/servicios/position_monitor.py` | Ejecuta Spot, publica la tabla canónica y entrega el resumen a la UI |
| `aplicaciones/interfaz_risko/interfaz_risko.py` | Botón Spot y acción unidireccional `Cargar parámetros Spot` |
| `herramientas/VECTOR/VECTOR.py` | Copia el reporte Summit mediante el flujo `06_Spot` |

## 4. Lectura robusta

El lector:

1. prueba `CP1252` y luego `Latin-1`;
2. busca el encabezado en las primeras 200 filas;
3. exige los nombres `GeneratedPK`, `DmOwnerTable`, `TradeId`, `Book`,
   `Desk`, `EvType`, `SettleCcy`, `Amount`, `ValueDate` y `TRADE DATE`;
4. usa `TRADE DATE` para `SPOT_CLIENTE` y `ValueDate` para los dem?s books;
   la columna `VALUE DATE` no sustituye ninguno de esos campos;
5. recorre el archivo como flujo de filas, sin cargar todo el reporte en memoria;
6. detiene el proceso antes de crear o actualizar tablas si falta el encabezado.

Los owners incluidos son parametrizables en `risko.json`:

```text
CONTADO, FXFWD, FXOPT_TR, FXSPOT, MM, NOVADO, SWAP
```

`DPMT_TR` no está incluido. Las cajas cuya `SettleCcy` no es USD no tienen
efecto directo en la posición.

## 5. Mapeo BOOK a posición

Los libros que alimentan la posición oficial se confirmaron contra los grupos de
`TABLA ORGANIZADA` del libro sin DP.

| BOOK de Reporte Caja | Posición normalizada | LB/LT | Instrumento | Activo |
|---|---|---|---|---|
| `SPOT_CLIENTE` | `Spot_Cliente` | Trading | SPOT | S? |
| `FWD_CLIENTES` | `FWD_Clientes` | Tesorería | Derivados | Sí |
| `FWD_POSICION` | `Pos_propia` | Bancario | Derivados | Sí |
| `POSI_PROPIA` | `Pos_propia` | Bancario | Derivados | Sí |
| `FX_ESTRAT` | `FX_Estrat` | Tesorería | Derivados | Sí |
| `CUBRE_BAC` | `Cubre_Bac` | Bancario | Derivados | Sí |
| `FWD_FILIALES` | `Filiales` | Bancario | Renta fija | Sí |
| `SWAPS` | `Swaps` | Tesorería | Derivados | Sí |
| `RF_ME_TRADIN` | `Renta_Fija_ME` | Tesorería | Renta fija | Sí |
| `RF_ME_FV_OCI` | `Renta_Fija_ME` | Tesorería | Renta fija | Sí |
| `OPCIONES_FX` | `Opciones` | Tesorería | Derivados | Sí |
| `FUTUROS_FX` | `Futuros_FX` | Tesorería | Derivados | Sí |
| `TRADING` | `Trading` | Tesorería | Renta fija | Sí |
| `FVH` | `FVH` | Bancario | Renta fija | Sí |
| `FACTURASUSD` | `FacturasUSD` | Bancario | Derivados | Sí |
| `CFH` | `CFH` | Bancario | Derivados | Sí |

Dos aliases pueden alimentar la misma posición. Por ejemplo,
`FWD_POSICION` y `POSI_PROPIA` se agrupan en `Pos_propia`; no se publican como
dos posiciones diferentes.

`SPOT_CLIENTE` es una posici?n oficial y usa `TRADE DATE`.
Otros libros comerciales observados el 03/08/2026, como
`CORPORAT_BOG`, `EMPRESAR_BOG`, `PYME_EMPRESA`, `MEDIANA`, `MONEDAS`,
`INSTITUC_BOG`, `GASTOS_BDB`, `REMESAS` y `ORIENTE_CEO`, no aparecen como
grupos de posición en `TABLA ORGANIZADA`. Por eso no se agregan oficialmente y
se conservan en el detalle con alerta `UNKNOWN_BOOK`.

Una inconsistencia entre aliases de una misma posición en `ACTIVO`, `LB_LT`,
`INSTRUMENTO` o moneda bloquea el proceso antes de publicar.

## 6. Cálculo de movimientos

Para un registro incluido cuya `SettleCcy` sea USD y cuya fecha aplicable
(`TRADE DATE` o `ValueDate`) coincida exactamente con el corte:

```text
Amount > 0  → COMPRA = Amount
Amount < 0  → VENTA  = abs(Amount)
Amount = 0  → SIN_MOVIMIENTO
```

Por fecha y posición normalizada:

```text
compras_t = suma de compras USD
ventas_t  = suma de ventas USD
neto_t    = compras_t - ventas_t
```

Todos esos cálculos usan `Decimal`. No se usa `float` ni se redondean resultados
intermedios.

## 7. Posición acumulada

```text
posición_final_t = posición_anterior_t + compras_t - ventas_t
```

La posición final conserva el signo. Puede ser positiva, negativa o cero.

Si hay una posición anterior pero no hay movimientos, se materializa el día con
`TIPO_ORIGEN = CARRY_FORWARD`. Esto incluye sábados, domingos y festivos. Si el
último dato disponible es anterior al día calendario previo, se crean todos los
días faltantes antes del corte.

Si una posición tiene movimientos y no existe posición anterior, el cálculo
continúa desde cero y queda la alerta persistente
`MISSING_PREVIOUS_POSITION`.

## 8. Ejemplo exacto del requerimiento

Para `FX_Estrat`:

```text
Posición anterior:  50.269.423,25732988
Compras 03/08/26:      310.858,70000
Ventas 03/08/26:             0
Movimiento neto:       310.858,70000
Posición final:     50.580.281,95732988
```

El valor persistido es `50580281.95732988`, exactamente, sin recorte de
decimales.

## 9. Resultado real del archivo 03/08/2026

La fuente real tenía 1.973 registros USD del corte después de filtrar owners.
Los agregados oficiales coincidieron con `TABLA ORGANIZADA`:

| Posición/libro | Compras USD | Ventas USD | Neto USD |
|---|---:|---:|---:|
| `FWD_Clientes` | 48.980.672,61000 | 57.099.949,06000 | -8.119.276,45000 |
| `Pos_propia` | 0 | 0 | 0 |
| `FX_Estrat` | 310.858,70000 | 0 | 310.858,70000 |
| `Cubre_Bac` | 1.500.000,00000 | 10.487.637,50000 | -8.987.637,50000 |
| `Filiales` | 0 | 0 | 0 |
| `Swaps` | 200.190,48000 | 504.758,89000 | -304.568,41000 |
| `Renta_Fija_ME` | 0 | 0 | 0 |
| `Opciones` | 6.500.000,00000 | 8.541.582,35000 | -2.041.582,35000 |
| `Futuros_FX` | 550.000,00000 | 0 | 550.000,00000 |
| `Trading` | 599.344,92000 | 599.344,92000 | 0 |
| `FVH` | 0 | 0 | 0 |
| `FacturasUSD` | 0 | 0 | 0 |
| `CFH` | 0 | 0 | 0 |

Las 13 posiciones activas siempre generan una fila. Cuando no existe historia ni
movimiento, la posición nace en cero con `TIPO_ORIGEN = INICIAL_CERO` y alerta
`MISSING_PREVIOUS_POSITION`. El cero permite mostrar el universo completo, pero
queda explícitamente pendiente de validación o reemplazo desde el Excel. Cuando
exista una posición inicial aprobada, se conservará diariamente por
`CARRY_FORWARD`.

## 10. Posiciones iniciales y Excel paramétrico

Las posiciones iniciales se diligencian exclusivamente en:

```text
proyectos/position_monitor/configuracion/param_posiciones_iniciales_spot.xlsx
```

La hoja `Posiciones_Iniciales` contiene la tabla de Excel
`tbl_param_posiciones_iniciales_spot` con las 13 posiciones y estos campos:

```text
FECHA, POSICION, POSICION_FINAL_USD, ESTADO_PARAMETRO, OBSERVACION
```

Para importar, las 13 filas deben tener un valor numérico y
`ESTADO_PARAMETRO = VALIDADO`. Si falta una posición, hay duplicados o un valor
está vacío, no se modifica la base.

La interfaz ofrece únicamente `Cargar parámetros Spot`, que importa las anclas
y recalcula fechas posteriores. No existe sincronización base → Excel y Risko
no escribe sobre `ReporteCaja(Sin DP).xlsb`.

## 11. Tablas de base de datos

### `tbl_posicion_spot`

Contrato canónico que usa el consolidado actual:

```text
FECHA, PRODUCTO, BOOK, POSICION, MONEDA_POSICION, LB_LT,
INSTRUMENTO, COMPANY, CLASIFICACION_CONTABLE, BANKING_CVA_DVA
```

### `tbl_posicion_spot_acumulada`

Una fila única por `FECHA + POSICION_ID` con:

```text
posición anterior, fecha anterior, compras, ventas, neto, posición final,
archivo, ejecución, origen, estado, alerta, usuario y marcas de tiempo
```

### `tbl_movimientos_spot`

Detalle trazable por fila fuente: GeneratedPK, trade, owner/producto, book
original, posición normalizada, desk, evento, moneda, Amount firmado, tipo de
movimiento, monto USD, archivo y número de fila.

En un reproceso, la versión anterior queda con `VIGENTE = 0`; no se borra.

### `tbl_compras_ventas_spot_book`

Tabla secundaria por `FECHA + BOOK_ORIGINAL` con compras, ventas, movimiento
neto, número de movimientos, posición homologada, estado del mapeo y bandera
publicable. Incluye:

- todos los BOOK configurados para Spot, incluso si están en cero;
- los BOOK observados en el reporte que no están mapeados;
- separación de aliases que terminan en una misma posición normalizada.

Esta tabla es consultable desde el selector de la interfaz, pero no alimenta el
consolidado ni el dashboard. El consolidado recibe únicamente la posición final
neta de `tbl_posicion_spot`.

### `tbl_alertas_spot`

Alertas persistentes, consultables desde el selector actual de tablas.

### `tbl_ejecuciones_spot`

Registra archivo, ruta, tamaño, fecha de modificación, hash SHA-256 de fuente,
hash de parámetros, usuario, inicio, fin y estado.

### `tbl_auditoria_spot`

Conserva valor anterior, valor nuevo y motivo por posición/fecha cuando un
reproceso o un cambio de ancla altera el histórico.

Los importes de las tablas auxiliares se guardan como texto decimal exacto.
SQLite no ofrece un tipo decimal fijo y guardarlos como `REAL` introduciría
representación binaria.

## 12. Idempotencia y reproceso

La identidad de una ejecución combina:

```text
fecha de corte + SHA-256 del archivo + SHA-256 del mapeo/owners
```

Si la misma combinación ya terminó correctamente, el proceso devuelve el
resultado existente y no duplica movimientos ni historia.

Si cambia el archivo o la parametrización:

1. se inactiva la versión vigente de movimientos/alertas del corte;
2. se inserta la nueva versión;
3. se recalcula la fecha;
4. se recalculan las fechas posteriores afectadas;
5. se guardan valores anterior/nuevo en auditoría;
6. la transacción se confirma solo al terminar todo.

## 13. Códigos de alerta

| Código | Ejemplo | Efecto oficial |
|---|---|---|
| `UNKNOWN_BOOK` | `SPOT_CLIENTE` no está parametrizado para Spot | El detalle se conserva y no se agrega |
| `INACTIVE_BOOK` | BOOK definido con `ACTIVO = NO` | El detalle se conserva y no se agrega |
| `MISSING_PREVIOUS_POSITION` | Hay compras/ventas sin historia previa | Calcula desde cero y marca la posición |
| `DUPLICATE_SOURCE_FILE` | Mismo hash y mismos parámetros | No duplica; se informa en el log |
| `SOURCE_FILE_CHANGE` | El corte ya tenía otro hash | Reprocesa y audita |
| `INVALID_AMOUNT` | `Amount` vacío o no decimal | La fila no se agrega y queda alerta |
| `INVALID_DATE` | `ValueDate` ilegible | La fila no se agrega y queda alerta |
| `HISTORICAL_REPROCESSING` | Se procesa un corte anterior al último | Recalcula hacia adelante |
| `INITIAL_POSITION_CHANGE` | Cambia el valor manual del 01/08 | Recalcula hacia adelante y audita |

## 14. Procedimiento para el corte 03/08/2026

1. Activar `Usar base de pruebas` en la interfaz.
2. Completar las 13 posiciones del 01/08/2026 en
   `param_posiciones_iniciales_spot.xlsx` y marcarlas `VALIDADO`.
3. Pulsar `Cargar parámetros Spot`.
4. Seleccionar fecha `03/08/2026`.
5. Ejecutar el botón `Spot`.
6. Revisar el resumen acumulado mostrado.
7. Consultar `tbl_alertas_spot` y `tbl_movimientos_spot` desde el selector de
   tablas para revisar excepciones/detalle.
8. Comparar las posiciones finales con el control del libro operativo.
9. Solo después de la aprobación funcional, repetir fuera del modo pruebas.

## 15. Evidencia automática

`tests/test_spot.py` cubre:

- compra, venta, cero y precisión decimal;
- varias operaciones y aliases en una posición;
- book desconocido e inactivo;
- ausencia de posición anterior;
- fin de semana y `CARRY_FORWARD`;
- encabezado variable y uso de `ValueDate`;
- archivo repetido;
- reproceso histórico;
- cambio de posición inicial.

La suite completa al 04/08/2026 ejecutó 13 pruebas correctamente, incluidas las
cuatro pruebas del lector histórico de TRM.

## 16. Supuestos pendientes de aprobación funcional

1. El archivo paramétrico nuevo contiene las 13 posiciones, pero sus saldos
   están pendientes de diligenciar y validar. Mientras tanto aparecen en cero
   con alerta; esos ceros no equivalen a saldos aprobados.
2. Los libros comerciales quedan excluidos porque sus valores no forman parte de
   los grupos de posición de `TABLA ORGANIZADA`. El resultado real del 03/08
   confirmó el mapeo uno a uno de los libros oficiales.
3. La posición acumulada USD ya no requiere TRM ni Curva Forward. El flujo
   `06_Spot` todavía puede copiar `Insumo tasas.xlsx` por compatibilidad, pero el
   nuevo cálculo no depende de ese archivo.
4. Spot sigue como ejecución individual/piloto hasta que Riesgo apruebe las
   posiciones iniciales y los resultados finales.
