# Mapa de produccion y ejemplos de calculo de Position Monitor

## Objetivo y fecha del levantamiento

Este documento deja trazabilidad, con corte al 4 de agosto de 2026, de:

- los codigos que participan en el flujo productivo de `Position Monitor`;
- los modulos que aun son piloto, soporte o esqueleto;
- el origen y nombre de cada archivo de entrada;
- la regla que convierte cada insumo en `POSICION`;
- un ejemplo numerico por modulo de posicion;
- el recorrido de la salida hasta `datos/base de datos/risko.db`.

La clasificacion se obtuvo del codigo que ejecuta la interfaz y se contrasto con
las tablas existentes en la base productiva. No se dedujo el estado solo por la
existencia de un boton o de un archivo Python.

## Resumen ejecutivo de produccion

La lista que ejecuta el boton `Ejecutar todo` esta definida en
`aplicaciones/interfaz_risko/servicios/position_monitor.py`:

```python
PRODUCTOS_EJECUCION_TOTAL = (
    "SPOT",
    "NOVADOS",
    "FORWARD",
    "OPCIONES",
    "SWAPS",
)
```

Estos son los cinco productos liberados para la corrida diaria: carga Vector,
calculo, tabla de producto, consolidacion y tablero. Renta Fija conserva su
codigo y tablas, pero su boton queda oculto y permanece fuera de `Ejecutar todo`
mientras Titulos este excluido del alcance del portal.

| Producto | Codigo principal | Flujo Vector | Tabla SQLite | Evidencia en `risko.db` al 04/08/2026 | Estado |
| --- | --- | --- | --- | --- | --- |
| Forward | `procesos/forward.py` | `01_Forward` | `tbl_posicion_forward` | 548 filas; ultimo corte 28/07/2026 | Produccion |
| Novados | `procesos/novados.py` | `02_Novados` | `tbl_posicion_novados` | 114 filas; ultimo corte 28/07/2026 | Produccion |
| Opciones | `procesos/opciones.py` | `04_Opciones` | `tbl_posicion_opciones` | 11 filas; ultimo corte 28/07/2026 | Produccion |
| Swaps | `procesos/swaps.py` | `05_Swaps` | `tbl_posicion_swaps` | 72 filas; ultimo corte 28/07/2026 | Produccion |
| Renta fija | `procesos/renta_fija.py` | `03_Renta_Fija` | `tbl_posicion_renta_fija` | 138 filas; ultimo corte 28/07/2026 | Fuera de corrida diaria |
| Spot | `procesos/spot.py` | `06_Spot` | `tbl_posicion_spot` | 6 filas; solo corte 22/06/2026 | Produccion |
| Cubrebonos | `procesos/cubrebonos.py` | Sin flujo | `tbl_posicion_cubrebonos` | Tabla no creada | Esqueleto |
| NDFTES | `procesos/ndftes.py` | Sin flujo | `tbl_posicion_ndftes` | Tabla no creada | Esqueleto |
| PP | `procesos/pp.py` | Sin flujo | `tbl_posicion_pp` | 0 filas | Esqueleto |

Los conteos son una fotografia de control, no una cantidad esperada permanente.

### Observacion de gobierno sobre alcance

Renta Fija, Cubrebonos, NDFTES y PP conservan su codigo y tablas, pero sus
botones están ocultos y no forman parte de `Ejecutar todo`. Antes de
reactivarlos deben validarse y ajustarse al nuevo formato de Position Monitor;
su existencia no cambia por sí sola el alcance del portal.

## Mapa de todos los codigos de `procesos`

| Archivo | Responsabilidad real | ¿Calcula posicion? | Clasificacion |
| --- | --- | --- | --- |
| `forward.py` | Forward Banking, IFRS y diferencia CVA/DVA | Si | Producto productivo |
| `novados.py` | Futuros/Novados por vencimiento y book | Si | Producto productivo |
| `opciones.py` | Sensibilidad spot y residual de opciones vencidas | Si | Producto productivo |
| `renta_fija.py` | Titulos desde valor presente de mercado | Si | Producto productivo |
| `swaps.py` | Flujos futuros en moneda de riesgo y CVA/DVA | Si | Producto productivo |
| `spot.py` | Movimientos USD de Reporte Caja sin DP y posicion diaria acumulada | Si | Piloto individual |
| `consolidacion.py` | Normaliza, guarda tablas y arma vistas consolidadas | No crea riesgo; consolida | Nucleo productivo transversal |
| `parametros_libros.py` | Homologa `BOOK`, `LB_LT`, instrumento y moneda | No | Nucleo productivo transversal |
| `validar_swaps.py` | Pruebas operativas de Swaps y sus publicaciones | No | Control de calidad |
| `posiciones_pendientes.py` | Devuelve el layout canonico vacio | No | Soporte para esqueletos |
| `cubrebonos.py` | Llama a `crear_tabla_pendiente` | No | Esqueleto |
| `ndftes.py` | Llama a `crear_tabla_pendiente` | No | Esqueleto |
| `pp.py` | Llama a `crear_tabla_pendiente` | No | Esqueleto |
| `Opciones_FF_V3.py` | Script historico usado como referencia metodologica | No participa en el servicio | Legado, no productivo |
| `__init__.py` | Expone imports del paquete | No | Infraestructura |

`Opciones_FF_V3.py` conserva su lectura historica de Curva Forward porque es un
script legado interactivo. El modulo productivo `opciones.py` no lo importa ni
depende de el.

## Flujo completo desde el archivo hasta la base

```text
Interfaz Risko
  -> servicio ejecutar_producto(producto, fecha)
  -> Vector ejecuta el flujo configurado en risko.json
  -> copia archivos desde red a datos/insumos
  -> procesos/{producto}.py valida y calcula la tabla canonica
  -> guardar_tabla_producto_position_monitor reemplaza esa FECHA en SQLite
  -> consolidar_position_monitor filtra las vistas publicables
  -> actualiza consolidada, actual e historico en risko.db
  -> genera el tablero desde SQLite
```

El contrato comun que retorna cada producto es:

| Columna | Significado |
| --- | --- |
| `FECHA` | Corte en formato `dd/mm/YYYY` |
| `PRODUCTO` | Nombre canonico del producto |
| `BOOK` | Libro original u homologado |
| `POSICION` | Exposicion en la unidad indicada |
| `MONEDA_POSICION` | Unidad de `POSICION` |
| `LB_LT` | Bancario, Tesoreria o No definido |
| `INSTRUMENTO` | Derivados o Renta_fija |
| `COMPANY` | Entidad/agencia |
| `CLASIFICACION_CONTABLE` | Clasificacion contable o `NA` |
| `BANKING_CVA_DVA` | Banking, IFRS o CVA/DVA |

La consolidacion no convierte todas las posiciones a una unica moneda. La
interpretacion de `POSICION` siempre depende de `MONEDA_POSICION`.

## Mapa de archivos de entrada

Vector copia todos los insumos a `datos/insumos` antes de calcular.

| Producto | Fuente de red | Patron o archivo | Regla de fecha |
| --- | --- | --- | --- |
| Forward | `\\SUMMITFS001\apl\Internos\GR\VALORACION_FWD` | `Cierre_Valoracion_FxFwd_ddmmaaaa_000.xls` y `Cierre_Valoracion_FxFwd_IFRS_ddmmaaaa_000.xls` | Fecha de corte |
| Novados | `\\SUMMITFS001\apl\Internos\GR\FUTURE_TOTAL` | `Cierre_FutureTotalReport_ddmmaa_000.xls` | Fecha de corte |
| Renta fija | `\\SUMMITFS001\apl\Internos\GR\TRADEPL` | `ReporteTitulos_ddmmaaaa.csv` | Fecha de corte |
| Opciones | `\\SUMMITFS001\apl\Internos\GR\FXOPTION_BASIC` | `USR_OPT_MANANA_ddmmaa_000.xls` | Siguiente dia habil; contiene el corte anterior |
| Opciones | `...\3 Jefatura de Riesgo de Mercado\BDB` | `ENTRADA2.xlsb` | Archivo estable de mercado |
| Opciones | `...\2 Jefatura de Compliance de Tesoreria\Insumos CT\Tasas` | `Insumo tasas.xlsx` | Archivo estable con historico por fecha |
| Swaps | `\\SUMMITFS001\apl\Internos\GR\SWAP_TOTAL` | `Cierre_SwapTotalReport_Flujos_ddmmaa_000.xls` y version IFRS | Ultimo habil si el corte no es habil |
| Spot | `\\SUMMITFS001\apl\Internos\GR\REP_CAJA` | `Cierre_ReporteCaja_ddmmaa_000.xls` | Fecha de corte |
| Spot, posicion inicial | `...\FORWARDS\INFORMES\2.CAJA` | `ReporteCaja(Sin DP).xlsb` | Bloque manual por fecha |

La ruta completa del nuevo historico TRM es:

```text
\\isilonsmbprod\Gerencia_Riesgo_De_Tesoreria\2 Jefatura de Compliance de Tesorería\Insumos CT\Tasas\Insumo tasas.xlsx
```

## Regla central de TRM despues del ajuste

Los modulos que antes pedian Curva Forward solo para leer la TRM eran
`opciones.py` y la version anterior de `spot.py`:

- Opciones toma curvas COP/USD y volatilidad desde `ENTRADA2.xlsb`;
- Spot ahora calcula una posicion acumulada directamente en USD y ya no usa TRM.

El flujo `04_Opciones` copia `Insumo tasas.xlsx`. El lector comun
`compartido/nucleo_risko/trm.py` aplica este contrato:

1. abre la hoja `TRM`;
2. lee solamente A:B;
3. exige `Fecha` en A y `FORMADA` en B;
4. busca la fecha de corte exacta;
5. devuelve un unico valor numerico;
6. falla si la fecha no existe, `FORMADA` esta vacia o hay valores duplicados
   diferentes.

No se usa `VIGENTE`, no se usa la ultima tasa anterior y no se vuelve a Curva
Forward como respaldo. Esto evita valorar un corte con una tasa de otra fecha.

Ejemplo verificado con el archivo real:

```text
Fecha solicitada: 03/08/2026
Fila encontrada:  03/08/2026 | FORMADA = 3230.44
TRM retornada:     3230.44
```

Para el 04/08/2026 la fila existia durante la revision, pero `FORMADA` estaba
vacia; el resultado correcto es detener el proceso hasta que el insumo se
actualice.

## Codigo 1: Novados

### Origen y preparacion

`novados.py` lee el archivo Future Total local como texto separado por `;`,
omite dos filas iniciales, normaliza nombres y convierte `VENCIMIENTO` y
`VALOR_SENSIBLE`.

### Calculo

```text
si VENCIMIENTO == FECHA_CORTE:
    POSICION = 0
en otro caso:
    POSICION = VALOR_SENSIBLE

salida = suma de POSICION por BOOK
```

### Ejemplo

Para corte `03/08/2026` y `BOOK = FUTUROS_FX`:

| Operacion | Vencimiento | Valor sensible | Posicion |
| --- | --- | ---: | ---: |
| A | 03/08/2026 | 120,000 USD | 0 USD |
| B | 10/08/2026 | -40,000 USD | -40,000 USD |

La posicion publicada del book es `0 + (-40,000) = -40,000 USD`. Luego
`param_libros.csv` puede homologar el book y completa `LB_LT`, instrumento y
moneda. El servicio reemplaza el corte en `tbl_posicion_novados`.

## Codigo 2: Forward

### Origen y preparacion

`forward.py` lee dos archivos: Banking e IFRS. Ambos se procesan con la misma
regla y se agregan por `BOOK`.

### Calculo por operacion

```text
si CORTE < F_VCTO:
    si CCY_COMPRA == COP o CCY_VENTA == COP:
        COMPRA -> VP_Y_USD_BUY
        VENTA  -> VP_Y_USD_SELL
    si no hay COP:
        VP_Y_USD_BUY + VP_Y_USD_SELL
si CORTE >= F_VCTO:
    si CCY_SETTLEMENT == COP o CORTE >= F_CUMPTO:
        0
    en otro caso:
        VP_Y_SETT_CCY_CVA
```

Despues calcula por book:

```text
POSICION_CVA_DVA = POSICION_IFRS - POSICION_BANKING
```

### Ejemplo

Para `FWD_CLIENTES` vigente:

- operacion COP comprada: `VP_Y_USD_BUY = 750,000`;
- operacion sin COP: `100,000 + (-25,000) = 75,000`;
- Banking del book: `825,000 USD`;
- IFRS del book: `835,000 USD`;
- CVA/DVA: `835,000 - 825,000 = 10,000 USD`.

`param_libros.csv` homologa `FWD_CLIENTES` a `FWD_Clientes`. Las tres vistas se
guardan en `tbl_posicion_forward`; IFRS se conserva en la tabla del producto,
pero no entra a las tablas consolidadas de visualizacion.

## Codigo 3: Opciones

### Origen y preparacion

`opciones.py` usa:

- el portafolio `USR_OPT_MANANA` del siguiente dia habil;
- `ENTRADA2.xlsb`, hoja `INFOVALMER`, para curvas COP/USD y volatilidades;
- `Insumo tasas.xlsx`, hoja `TRM`, para la TRM `FORMADA` exacta.

Para vigentes interpola tasas y smile, calcula volatilidad cubica y revalora la
opcion con Black-Scholes/Garman-Kohlhagen en dos escenarios de spot.

### Calculo de una opcion vigente

```text
spot_up   = TRM * 1.0025
spot_down = TRM * 0.9975
d_spot    = spot_up - spot_down

POSICION_SENSIBILIDAD_USD =
    (VALOR_UP_COP - VALOR_DOWN_COP) / d_spot
```

El valor de cada escenario incluye signo Buy/Sell, nominal y factor de
descuento. La volatilidad se recalcula en ambos escenarios.

Para vencidas:

```text
si cumplimiento == corte -> 0
si moneda de cumplimiento == COP -> 0
en otro caso -> valor de liquidacion reportado
```

### Ejemplo

Con TRM `3230.44`:

```text
spot_up   = 3230.44 * 1.0025 = 3238.5161
spot_down = 3230.44 * 0.9975 = 3222.3639
d_spot    = 16.1522
```

Si la revaloracion completa produce `112,038,050 COP` en up y
`103,961,950 COP` en down:

```text
POSICION = (112,038,050 - 103,961,950) / 16.1522
         = 500,000 USD
```

El detalle auxiliar se conserva por book, pero la tabla canonica productiva
suma todas las operaciones en una fila `BOOK = Opciones`. El servicio reemplaza
la fecha en `tbl_posicion_opciones`.

## Codigo 4: Renta fija

### Origen y preparacion

`renta_fija.py` lee `ReporteTitulos`, convierte fechas y enriquece:

- esquema contable con `param_librorf.csv`;
- equivalencia de moneda con `param_monedarf.csv`;
- book, `LB_LT`, instrumento y moneda con `param_libros.csv`.

Tambien calcula DVO1, sensibilidad de 100 pb y grupos de vencimiento como
soportes, pero esos campos no sustituyen la posicion publicada.

### Calculo

```text
POSICION = VP MDO Y COP
```

La salida agrupa por fecha, producto, book, moneda, `LB_LT`, instrumento,
company y vista Banking.

### Ejemplo

Dos titulos COP del mismo book y dimensiones:

| Titulo | VP MDO Y COP |
| --- | ---: |
| A | 1,200,000,000 COP |
| B | -200,000,000 COP |

La fila agrupada publica `1,000,000,000 COP` en
`tbl_posicion_renta_fija`. `CLASIFICACION_CONTABLE` conserva el primer esquema
del grupo.

## Codigo 5: Swaps

### Origen y preparacion

`swaps.py` carga Banking e IFRS. Si el corte no es habil busca como fuente el
ultimo dia habil y valida, cuando esta disponible, la fecha interna del archivo.

### Calculo por flujo

```text
si DATE < FECHA_CORTE:
    POSICION_USD = 0
si MONEDA EN RIESGO == COP:
    POSICION_USD = 0
en otro caso:
    POSICION_USD = VP MONEDA EN RIESGO
```

Luego suma por book y calcula:

```text
CVA_DVA = IFRS - Banking
```

Para publicacion, los libros de Tesoreria se colapsan en `BOOK = SWAPS`; los
libros bancarios `CFH` y `FVH` se conservan.

### Ejemplo

Para corte `03/08/2026`:

| Flujo | Fecha | Moneda riesgo | VP moneda riesgo | Posicion |
| --- | --- | --- | ---: | ---: |
| 1 | 02/08/2026 | USD | 50,000 | 0 |
| 2 | 10/08/2026 | COP | 80,000 | 0 |
| 3 | 10/08/2026 | USD | 150,000 | 150,000 |

Si Banking suma `150,000 USD` e IFRS `147,000 USD`, la vista CVA/DVA es
`147,000 - 150,000 = -3,000 USD`. Las vistas se guardan en
`tbl_posicion_swaps`.

## Codigo 6: Spot, piloto

### Origen y preparacion

`spot.py` detecta el encabezado variable del reporte semicolon-delimited, usa
`ValueDate` y procesa en USD los owners parametrizados:

- `SETTLECCY = USD`;
- `ValueDate = fecha de corte`;
- `DmOwnerTable` en `CONTADO, FXFWD, FXOPT_TR, FXSPOT, MM, NOVADO, SWAP`;
- `BOOK` activo y homologado para Spot en `param_libros.csv`.

`DPMT_TR` y monedas diferentes de USD no afectan la posicion. Los libros
desconocidos/inactivos se guardan en el detalle, generan alerta y no se agregan.

### Calculo acumulado

Los importes se calculan con `Decimal`:

```text
compras = suma(Amount > 0)
ventas = suma(abs(Amount < 0))
neto = compras - ventas
posicion_final = posicion_anterior + neto
```

Si falta un dia calendario se materializa `CARRY_FORWARD`. Si falta la posicion
anterior, se usa cero y queda `MISSING_PREVIOUS_POSITION`.

Ejemplo validado con el reporte real del 03/08/2026 para `FX_Estrat`:

```text
posicion anterior = 50,269,423.25732988
compras            =    310,858.70000
ventas             =              0
posicion final     = 50,580,281.95732988
```

La salida canónica sigue en `tbl_posicion_spot`; el histórico exacto, detalle,
alertas, ejecuciones y auditoría usan tablas auxiliares en la misma base. La
especificación completa está en `posicion_spot_acumulada.md`. Mientras negocio
autoriza la promoción, debe ejecutarse con `pruebas=True`.

## Codigo transversal: homologacion de libros

`parametros_libros.py` cruza por `PRODUCTO + BOOK`. Si existe configuracion:

- reemplaza el book por `BOOK_HOMOL`;
- asigna `LB_LT`;
- asigna `INSTRUMENTO`;
- asigna `MONEDA_POSICION`.

Ejemplo real del parametro Forward:

```text
PRODUCTO = Forward
BOOK original = FWD_CLIENTES
BOOK_HOMOL = FWD_Clientes
LB_LT = Tesoreria
INSTRUMENTO = Derivados
MONEDA_POSICION = USD
```

Si no hay mapa, conserva el book, usa los valores base o por defecto y registra
una alerta con `LB_LT = No definido` cuando corresponda.

## Codigo transversal: escritura y consolidacion

### Tabla por producto

El servicio recibe la tabla calculada y llama a
`guardar_tabla_producto_position_monitor`. Para la fecha seleccionada:

1. normaliza el layout;
2. lee la tabla SQLite existente;
3. elimina las filas de esa fecha;
4. anexa el nuevo resultado;
5. reemplaza la tabla fisica y recrea el indice de fecha.

Esto hace idempotente la repeticion de un corte: no debe duplicar la fecha.

### Tablas consolidadas

`consolidacion.py` conserva como publicables solamente `Banking` y `CVA/DVA`.
La vista `IFRS` queda en la tabla de producto, pero se excluye de:

- `tbl_posicion_consolidada`;
- `tbl_posicion_actual`;
- `tbl_posicion_historico`.

Ejemplo con el Forward anterior:

| Vista | Posicion | Tabla producto | Consolidada |
| --- | ---: | --- | --- |
| Banking | 825,000 | Si | Si |
| IFRS | 835,000 | Si | No |
| CVA/DVA | 10,000 | Si | Si |

`tbl_posicion_actual` queda con el corte solicitado. El historico solo conserva
fechas que son ultimo dia habil operativo del mes. Los CSV de `procesados` y
`publicados` son soportes de compatibilidad; la fuente oficial es SQLite.

## Salidas y puntos de control

| Producto | Soporte procesado principal | Tabla oficial |
| --- | --- | --- |
| Forward | `df_Insumo_FWD.xlsx`, `df_Insumo_FWD_IFRS.xlsx`, `df_Fwd_CVADVA.xlsx` | `tbl_posicion_forward` |
| Novados | `df_Insumo.xlsx`, `Tbl_Posicion_Novados.csv` | `tbl_posicion_novados` |
| Opciones | `Df_Insumo_Opciones_Depurado.xlsx`, `Tbl_Posicion_Opciones.csv` | `tbl_posicion_opciones` |
| Renta fija | `Tbl_Posicionrf.xlsx`, `Posicionrf.xlsx`, `Tbl_Posicion_Renta_Fija.csv` | `tbl_posicion_renta_fija` |
| Swaps | `Df_Insumo_Swaps_Depurado.xlsx`, `Tbl_Posicion_Swaps_Detalle.csv`, `Tbl_Posicion_Swaps.csv` | `tbl_posicion_swaps` |
| Spot | Reporte Caja + `configuracion/param_posiciones_iniciales_spot.xlsx` | `tbl_posicion_spot`, `tbl_posicion_spot_acumulada`, detalle/alertas/auditoria |

Controles minimos antes de publicar un corte:

1. Vector debe reportar una coincidencia por archivo esperado.
2. La fecha interna debe coincidir cuando el formato del proveedor la informa.
3. Opciones debe registrar la TRM `FORMADA` exacta usada; Spot acumulado no usa TRM.
4. No deben existir books sin mapa sin una alerta revisada.
5. La suma del soporte por book debe coincidir con la tabla del producto.
6. La fecha reemplazada no debe duplicarse en SQLite.
7. La consolidada debe excluir IFRS y conservar Banking/CVA-DVA.

## Archivos de codigo que gobiernan el recorrido

- `proyectos/position_monitor/configuracion/risko.json`: fuentes y pasos Vector.
- `aplicaciones/interfaz_risko/servicios/position_monitor.py`: seleccion y orden de productos.
- `proyectos/position_monitor/procesos/*.py`: reglas de calculo.
- `compartido/nucleo_risko/trm.py`: seleccion exacta de TRM `FORMADA`.
- `proyectos/position_monitor/procesos/parametros_libros.py`: homologaciones.
- `proyectos/position_monitor/procesos/consolidacion.py`: tablas de producto y consolidadas.
- `compartido/nucleo_risko/base_datos.py`: lectura y escritura SQLite.
- `proyectos/position_monitor/tableros/panel_position_monitor.py`: consumo para tablero.
