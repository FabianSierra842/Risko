# Guia de calculo de posiciones - Position Monitor Risko

**Version:** 2.0 - Julio 2026  
**Modulo:** Position Monitor  
**Publico:** Jefatura de Riesgo de Mercado - Banco de Bogota

## Arquitectura general

```text
Interfaz Risko
    -> ejecuta flujo Vector de la fecha seleccionada
datos/insumos/
    -> quedan los archivos locales cargados por Vector
proyectos/position_monitor/procesos/{producto}.py
    -> valida insumos, calcula y retorna tabla canonica
datos/base de datos/risko.db
    -> guarda tablas de producto y tablas consolidadas
Interfaz Risko / Tablero
    -> consulta SQLite por fecha y permite exportar CSV o Excel
```

Los CSV en `datos/position_monitor/procesados` y
`datos/position_monitor/publicados` son copias operativas o de compatibilidad.
La fuente maestra es:

```text
datos/base de datos/risko.db
```

La base para pruebas y auxiliares es:

```text
datos/base de datos/risko_pruebas.db
```

## Tabla canonica de posicion

Todos los modulos deben retornar una tabla con estas columnas:

| Columna | Tipo esperado | Descripcion |
| --- | --- | --- |
| `FECHA` | `dd/mm/YYYY` | Fecha del corte |
| `PRODUCTO` | texto | Producto homologado |
| `BOOK` | texto | Libro o mesa |
| `POSICION` | numero | Valor de posicion en su moneda nativa |
| `MONEDA_POSICION` | texto | Moneda/unidad de la posicion |
| `LB_LT` | texto | Bancario, Tesoreria o No definido |
| `INSTRUMENTO` | texto | Derivados, Renta_fija u otra familia |
| `COMPANY` | texto | Entidad o agencia |
| `CLASIFICACION_CONTABLE` | texto | AFS, HTM, Trading, NA, etc. |
| `BANKING_CVA_DVA` | texto | Banking, IFRS o CVA/DVA |

`TRM`, `POSICION_COP` y `POSICION_USD` no hacen parte del contrato canonico
vigente de consolidacion. Si un modulo requiere TRM para un calculo interno, lo
debe documentar dentro de su proceso.

## Modulo 1 - Novados

### Fuente

Vector carga el archivo de Future Total desde Summit hacia `datos/insumos`.

### Regla de posicion

Los novados son futuros cambiarios. La posicion se calcula sobre el campo de
exposicion sensible del reporte:

- si el vencimiento es la fecha de corte, la posicion se lleva a `0`;
- si el vencimiento es posterior a la fecha de corte, se conserva la exposicion;
- se agrupa por `BOOK`;
- la moneda de posicion usual es `USD`.

### Salida

El modulo retorna la tabla canonica y el servicio la guarda en:

```text
tbl_posicion_novados
```

## Modulo 2 - Forward

### Fuente

Vector carga:

- archivo Summit Banking;
- archivo Summit IFRS.

### Regla de posicion Banking

La posicion depende de vencimiento y monedas:

```text
Si fecha_corte < F_VCTO:
    Si CCY_COMPRA == COP -> usar VP de compra
    Si CCY_VENTA == COP  -> usar VP de venta
    Otro caso            -> VP_COMPRA + VP_VENTA

Si fecha_corte >= F_VCTO:
    Si settlement ya esta cumplido o liquida en COP -> 0
    Otro caso                                      -> VP pendiente de settlement
```

### Vistas

El modulo calcula:

- `Banking`;
- `IFRS`;
- `CVA/DVA = IFRS - Banking`.

La consolidacion conserva `Banking` y `CVA/DVA` en las tablas publicables.

### Salida

El servicio guarda la tabla en:

```text
tbl_posicion_forward
```

## Modulo 3 - Opciones

### Fuente

Vector carga:

- portafolio de opciones del siguiente dia habil;
- `ENTRADA2.xlsb`;
- `Insumo tasas.xlsx`, hoja `TRM`, usando la columna `FORMADA` de la fecha exacta.

### Regla de posicion

El modulo no publica el valor teorico ni el delta analitico como posicion. Para
operaciones vigentes publica la sensibilidad spot del portafolio:

```text
POSICION_SENSIBILIDAD_USD = dV_COP / dSpot
```

Flujo:

1. lee el portafolio de opciones;
2. valida que Vector haya cargado insumos de mercado para la fecha seleccionada;
3. construye escenarios de TRM `+/-0.25%`;
4. recalcula volatilidad y valor COP de cada operacion en cada escenario;
5. calcula la diferencia centrada `(valor_up_cop - valor_down_cop) / d_spot`;
6. usa esa sensibilidad como posicion de vigentes;
7. aplica reglas de liquidacion para vencidas no cumplidas;
8. agrupa a la salida canonica del producto.

`POSICION_DELTA_USD` queda solo como referencia de control. `Opciones_FF_V3.py`
es una referencia metodologica historica; el modulo productivo no depende de ese
archivo.

### Salida

El servicio guarda la tabla en:

```text
tbl_posicion_opciones
```

## Modulo 4 - Renta Fija / Titulos

### Fuente

Vector carga el reporte de Titulos/TRADEPL hacia `datos/insumos`.

### Parametros

El modulo usa:

- `param_libros.csv` para `LB_LT`, `INSTRUMENTO` y moneda esperada por book;
- `param_librorf.csv` para clasificacion contable;
- `param_monedarf.csv` para equivalencias de moneda.

### Regla de posicion

La posicion se toma desde la valoracion del titulo y se interpreta segun la
moneda del instrumento:

- COP: posicion en pesos;
- USD/EUR u otras monedas: se conserva segun la definicion del modulo;
- UVR: se conserva como unidad UVR cuando aplique.

Cada fila puede representar un titulo individual. La consolidacion no colapsa
automaticamente a una fila por book; las agregaciones se hacen en tablero o en
consultas segun la necesidad.

### Salida

El servicio guarda la tabla en:

```text
tbl_posicion_renta_fija
```

## Modulo 5 - Swaps

### Fuente

Vector carga:

- archivo Summit Swaps Banking;
- archivo Summit Swaps IFRS.

### Regla de posicion

La posicion se calcula desde el valor presente de los flujos en la moneda de
riesgo. El modulo arma las vistas:

- `Banking`;
- `IFRS`;
- `CVA/DVA = IFRS - Banking`.

El proceso valida que la informacion interna del archivo corresponda a la fecha
seleccionada.

### Salida

El servicio guarda la tabla principal en:

```text
tbl_posicion_swaps
```

Cuando existe detalle operativo, tambien puede quedar en:

```text
datos/position_monitor/procesados/Tbl_Posicion_Swaps_Detalle.csv
```

Ese detalle es soporte operativo, no tabla de base de datos. Si el CSV o el
workbook de soporte esta abierto, el proceso debe registrar el aviso y continuar
con la tabla oficial `tbl_posicion_swaps`.

## Modulo 6 - Spot / Contado

Spot esta en pruebas y no debe escribir en `risko.db`.

Para pruebas controladas debe usarse:

```text
datos/base de datos/risko_pruebas.db
```

El codigo para activarlo desde el servicio y la interfaz quedo comentado. Si se
prueba temporalmente, debe guardarse con:

```python
guardar_tabla_producto_position_monitor("SPOT", tabla, fecha, pruebas=True)
```

## Proceso de consolidacion

### Al ejecutar un producto

```text
1. La interfaz envia producto y fecha.
2. El servicio ejecuta el flujo Vector del producto.
3. Vector deja insumos en datos/insumos.
4. El modulo valida insumos locales y calcula la tabla canonica.
5. El servicio guarda la tabla de producto en risko.db.
6. La consolidacion reemplaza esa FECHA en las tablas consolidadas.
7. La interfaz muestra la informacion de la fecha seleccionada.
```

### Al ejecutar todo

```text
1. Se limpia datos/insumos si la opcion esta activa.
2. Se ejecutan los flujos Vector de productos activos.
3. Se calculan Forward, Novados, Opciones, Swaps y Renta Fija.
4. Cada tabla de producto se guarda en risko.db.
5. Se consolida una sola vez la fecha seleccionada.
6. Se genera el tablero.
```

### Tablas que actualiza

| Tabla | Uso |
| --- | --- |
| `tbl_posicion_consolidada` | Historico consolidado por producto/fecha |
| `tbl_posicion_actual` | Foto de la fecha seleccionada o ultima disponible |
| `tbl_posicion_historico` | Cierres operativos de mes |

La consolidacion excluye `IFRS` de estas tres tablas y conserva `Banking` y
`CVA/DVA`.

### Reejecucion de una fecha

Si se ejecuta nuevamente la misma fecha:

- se eliminan de la tabla de producto las filas anteriores de esa fecha;
- se insertan las nuevas filas;
- se reemplaza la misma fecha en el consolidado;
- no se duplican posiciones.

Por eso ya no existe la opcion de acumular posiciones desde la interfaz.

## Consulta en interfaz

La interfaz consulta SQLite directamente:

- `Tabla DB`: selecciona la tabla;
- `Pruebas`: cambia entre `risko.db` y `risko_pruebas.db`;
- fecha de corte: filtra por `FECHA` o `CORTE` cuando la tabla tiene esa columna;
- exportacion: genera CSV o Excel desde la vista cargada.

## Parametros de enriquecimiento

### `param_libros.csv`

Mapea cada `BOOK` a dimensiones de negocio:

```csv
PRODUCTO,BOOK,LB_LT,INSTRUMENTO,MONEDA_POSICION
Forward,FWD_Clientes,Tesoreria,Derivados,USD
Titulos,Colchon,Bancario,Renta_fija,UVR
```

### `param_librorf.csv`

Mapea esquemas contables de Renta Fija a categorias como `AFS`, `HTM` o
`Trading`.

### `param_monedarf.csv`

Mapea monedas de titulos a equivalencias operativas.

## Validaciones operativas

Antes de dar por buena una posicion:

1. confirmar que Vector cargo los insumos de la fecha;
2. ejecutar el producto desde la interfaz;
3. cargar la tabla de producto desde `Tabla DB`;
4. validar que la fecha seleccionada tenga filas;
5. cargar `tbl_posicion_actual`;
6. exportar a CSV o Excel si se necesita soporte externo;
7. generar tablero si aplica.

## Glosario

| Termino | Significado |
| --- | --- |
| `risko.db` | Base SQLite principal de Risko |
| `risko_pruebas.db` | Base SQLite para auxiliares y pruebas |
| `Vector` | Herramienta que carga insumos a `datos/insumos` |
| `FECHA` | Fecha de corte de la posicion |
| `BOOK` | Libro, mesa o agrupador operativo |
| `LB_LT` | Libro Bancario / Libro de Tesoreria |
| `Banking` | Vista bajo norma local |
| `IFRS` | Vista bajo norma internacional, no publicable en consolidados |
| `CVA/DVA` | Ajuste de valor por riesgo de contraparte/riesgo propio |
