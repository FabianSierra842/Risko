# Posicion Swaps

## Objetivo del modulo

El modulo `swaps.py` calcula la posicion de `Swap` para tres vistas contables:

- `Banking`
- `IFRS`
- `CVA/DVA`

El resultado oficial se publica por `BOOK`, ya no agregado por `LB_LT`.

## Resumen funcional vigente

Comportamiento actual:

- la fecha elegida por el usuario define la `FECHA` publicada;
- si esa fecha es no habil, el insumo se toma del ultimo dia habil;
- se validan y leen dos reportes locales cargados por Vector, uno Banking y otro IFRS;
- se calcula `POSICION_USD` por flujo;
- luego se agrega por `BOOK`;
- despues se calcula `CVA/DVA = IFRS - Banking`;
- finalmente se enriquece cada `BOOK` con `param_libros.csv`.

## Archivos y parametros involucrados

Configuracion:

- `proyectos/position_monitor/configuracion/param_rutas.csv`
- `proyectos/position_monitor/configuracion/param_libros.csv`

Llaves de `param_rutas.csv` usadas:

- `Swaps_Banking_Local`
- `Swaps_IFRS_Local`

Las llaves Summit pertenecen a la configuracion de Vector. El modulo Python usa
las rutas locales para validar insumos en `datos/insumos`.

Salidas:

- `datos/position_monitor/procesados/Tbl_Posicion_Swaps.csv`
- `datos/position_monitor/procesados/Tbl_Posicion_Swaps_Detalle.csv`
- `datos/position_monitor/procesados/Df_Insumo_Swaps_Depurado.xlsx`

Solo `Tbl_Posicion_Swaps.csv` alimenta la tabla oficial `tbl_posicion_swaps` en
SQLite. El detalle es soporte operativo en CSV/Excel y no debe crear tablas en
`risko.db`.

## Estructura canonica publicada

La tabla final usa:

```python
[
    "FECHA",
    "PRODUCTO",
    "BOOK",
    "POSICION",
    "MONEDA_POSICION",
    "LB_LT",
    "INSTRUMENTO",
    "COMPANY",
    "CLASIFICACION_CONTABLE",
    "BANKING_CVA_DVA",
]
```

Valores fijos de `Swap`:

- `PRODUCTO = Swap`
- `CLASIFICACION_CONTABLE = NA`

## Regla de fecha

### Fecha de corte

La fecha recibida por interfaz se convierte con:

- `pd.to_datetime(..., dayfirst=True)`

Si no se puede convertir:

- el proceso falla con `ValueError`.

### Fecha fuente del insumo

El proceso usa:

- la misma fecha si es habil;
- el ultimo dia habil si la fecha de corte no es habil.

Esto se resuelve con:

- `Es_Dia_Habil`
- `Ultimo_Dia_Habil`

## Construccion de rutas

Los archivos de Swaps usan sufijo:

```text
ddmmaa_000.xls
```

Ejemplo:

- `160626_000.xls`

Se construyen dos rutas locales esperadas:

- local Banking
- local IFRS

## Validacion y lectura de archivos

### Validacion

Para cada vista contable:

- Vector debe haber dejado el archivo en `datos/insumos`;
- si no existe localmente, el proceso falla.

### Lectura

Los reportes se leen con:

- separador `;`
- `skiprows=3`
- codificacion `latin1`
- `on_bad_lines="skip"`

El parser tambien:

- limpia espacios de nombres de columna;
- elimina columnas `Unnamed`;
- elimina la columna `FILA` si existe.

## Validacion de fecha interna del archivo

Cada archivo trae una fecha en el encabezado.

El modulo:

1. lee la segunda linea del archivo;
2. busca una fecha con regex `dd/mm/YYYY`;
3. la convierte a `Timestamp`;
4. la compara contra la fecha fuente esperada.

Si la fecha interna no coincide con la fecha fuente:

- el proceso falla.

Si no logra leer la fecha interna:

- deja log;
- continua con la fecha fuente parametrizada.

## Columnas requeridas del insumo

La depuracion exige estas columnas:

```python
[
    "TRADE ID",
    "PAY/REC",
    "FREQ",
    "FREQ_RESET",
    "MODALIDAD",
    "START",
    "END",
    "FIXING",
    "FECHA FX FIXING",
    "NOTIONAL",
    "NOTIONAL CCY",
    "DATE",
    "FLOWS",
    "TYPE",
    "FLOWS_SETT_CCY",
    "CLIENTE",
    "ID_TYPE",
    "ID_CONTRAPARTE",
    "CCS/IRS",
    "BOOK",
    "DESK",
    "COMPANY",
    "MONEDA EN RIESGO",
    "Flujo en Moneda en Riesgo",
    "VP MONEDA EN RIESGO",
]
```

Si falta alguna:

- el proceso falla con `ValueError`.

## Conversiones aplicadas en la depuracion

### Fechas

Se convierten estas columnas:

- `START`
- `END`
- `FIXING`
- `FECHA FX FIXING`
- `DATE`

### Numericos

Se convierten:

- `NOTIONAL`
- `FLOWS`
- `Flujo en Moneda en Riesgo`
- `VP MONEDA EN RIESGO`

### Textos normalizados

El modulo:

- reemplaza `BOOK` vacio por `Sin_Book`;
- lleva `MONEDA EN RIESGO` a mayuscula;
- guarda `FECHA_VALORACION_ARCHIVO` como soporte.

## Regla exacta de `POSICION_USD`

La formula es:

```python
if DATE < fecha_valoracion:
    POSICION_USD = 0
elif MONEDA EN RIESGO == "COP":
    POSICION_USD = 0
else:
    POSICION_USD = VP MONEDA EN RIESGO
```

Interpretacion:

- un flujo ya vencido no aporta posicion;
- un flujo cuyo riesgo esta en `COP` tampoco aporta posicion USD;
- el resto toma como posicion el `VP MONEDA EN RIESGO`.

## Agrupacion intermedia

Despues del calculo por flujo, la posicion se agrupa por:

```python
BOOK
```

La funcion `_agrupar_posicion_por_book` suma:

- `POSICION_USD`

y conserva una `COMPANY` representativa por `BOOK`.

## Regla de `CVA/DVA`

El calculo usa:

```python
CVA_DVA = IFRS - Banking
```

La implementacion hace:

- `outer join` por `BOOK`;
- llena vacios con cero;
- conserva books presentes solo en una de las dos vistas.

## Parametrizacion por `param_libros.csv`

La clasificacion final de cada `BOOK` sale de `param_libros.csv`.

Campos resueltos:

- `BOOK_HOMOL`
- `LB_LT`
- `INSTRUMENTO`
- `MONEDA_POSICION`

La clave usada es:

- `PRODUCTO = Swap`
- `BOOK`

Tambien puede resolver por `BOOK_HOMOL` si la tabla base ya viene homologada.

### Regla de alerta

Si un `BOOK` no existe en la parametrizacion:

- el proceso escribe alerta en log;
- `LB_LT = No definido`;
- se conserva el `BOOK` original.

### Estado actual del mapa

Hoy la parametrizacion vigente marca como bancarios:

- `CFH`
- `FVH`

## Construccion de la tabla canonica

La funcion `_construir_tabla_canonica` se ejecuta tres veces:

- una para `Banking`
- una para `IFRS`
- una para `CVA/DVA`

Cada llamada:

- toma la tabla agregada por `BOOK`;
- la enriquece con `param_libros.csv`;
- arma la estructura canonica.

## Historico detalle y publicacion oficial

### Historico detalle

`tabla_swaps_detalle_fecha` es la union de:

- Banking
- IFRS
- CVA/DVA

Luego pasa por `actualizar_datos_por_fecha` sobre:

- `Tbl_Posicion_Swaps_Detalle.csv`

### Publicacion oficial

La salida oficial se reconstruye desde el detalle historico con `_consolidar_tabla_swaps_publicacion`.

Hoy esa funcion:

- normaliza fecha y etiquetas contables;
- vuelve a enriquecer con `param_libros.csv`;
- garantiza defaults de `COMPANY` y `CLASIFICACION_CONTABLE`;
- publica una fila por `BOOK` y vista contable.

Importante:

- `Tbl_Posicion_Swaps.csv` y `Tbl_Posicion_Swaps_Detalle.csv` quedan al mismo nivel de detalle por `BOOK`;
- ya no existe la agregacion final a `BOOK = SWAP` en la ruta activa del modulo.

## Archivos adicionales de soporte

El workbook `Df_Insumo_Swaps_Depurado.xlsx` guarda:

- `Banking_Depurado`
- `IFRS_Depurado`
- `Posicion_Banking`
- `Posicion_IFRS`
- `Posicion_CVA_DVA`
- `Tabla_Canonica_Detalle`
- `Tabla_Canonica_Total`

## Funciones legacy que siguen en el archivo

En `swaps.py` aun existen elementos heredados del esquema anterior:

- `BOOK_TOTAL_SWAPS`
- `MAPA_LB_LT_PUBLICACION`
- `_normalizar_lb_lt_publicacion`
- `_resumir_posicion_total`

Hoy no participan en la ruta principal que publica por `BOOK`, pero siguen declarados en el archivo.

## Logs que genera el modulo

El proceso registra:

- inicio del proceso;
- fecha de trabajo;
- uso de ultimo dia habil si aplica;
- rutas locales;
- validacion de archivos cargados por Vector;
- tamano de Banking e IFRS;
- fecha interna detectada;
- fin de depuracion;
- fin de calculo de `POSICION_USD`;
- cantidad de filas por `BOOK` en Banking, IFRS y CVA/DVA;
- guardado del detalle;
- guardado de la tabla oficial;
- guardado del workbook de soporte.

Si el CSV o workbook de soporte esta abierto, el modulo registra el aviso y
continua con la tabla oficial de Swaps para que la consolidacion no se bloquee.

## Errores tipicos

`No se encontro la configuracion ... en param_rutas.csv`

- falta alguna llave de swaps en `param_rutas.csv`

`No se encontro el insumo de Swaps ...`

- Vector no dejo el archivo local esperado en `datos/insumos`

`La fecha interna del archivo ... no coincide ...`

- el archivo local cargado por Vector no corresponde a la fecha fuente esperada

`El insumo de Swaps no contiene todas las columnas requeridas`

- cambio el layout del reporte fuente

`ALERTA mapa_lb_lt`

- aparecio un `BOOK` no parametrizado

## Agregacion de books de Tesoreria en "SWAPS"

Despues de enriquecer con `param_libros.csv`, los books cuyo `LB_LT == "TESORERIA"`
(comparacion sin tildes, sin mayusculas) se relabelen como:

```python
BOOK = "SWAPS"
```

Luego la tabla se agrupa por todas las columnas canonicas excepto `POSICION`, sumando
`POSICION`. El resultado son exactamente tres books en la salida consolidable:

| BOOK | LB_LT |
|---|---|
| `CFH` | Bancario |
| `FVH` | Bancario |
| `SWAPS` | Tesoreria |

Cada uno de estos tres books tiene tres filas: `Banking`, `IFRS` y `CVA/DVA`.

El archivo de detalle (`Tbl_Posicion_Swaps_Detalle.csv`) conserva los books
originales sin colapsar, para trazabilidad.

## Resumen ejecutivo de la regla

La posicion de Swaps hoy:

- se calcula por flujo en USD;
- apaga flujos vencidos y flujos con riesgo `COP`;
- agrega por `BOOK`;
- separa `Banking`, `IFRS` y `CVA/DVA`;
- toma `LB_LT` desde `param_libros.csv`;
- colapsa todos los books de Tesoreria a `BOOK = "SWAPS"`;
- publica exactamente tres books: `CFH`, `FVH` y `SWAPS`.
