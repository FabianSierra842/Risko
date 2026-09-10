# Posicion Forward

## Objetivo del modulo

El modulo `forward.py` calcula la posicion de `Forward` para tres vistas contables:

- `Banking`
- `IFRS`
- `CVA/DVA`

La logica principal es:

1. leer dos archivos fuente, uno Banking y otro IFRS;
2. aplicar la misma formula de posicion a ambos;
3. agrupar por `BOOK`;
4. calcular `CVA/DVA = IFRS - Banking`;
5. devolver en memoria la tabla canonica completa.

## Estado actual de publicacion

Este punto es importante porque hoy el comportamiento real del codigo no coincide con versiones historicas del flujo.

Comportamiento actual:

- el modulo retorna en memoria la tabla completa de `Forward`;
- esa tabla se guarda en `tbl_posicion_forward` cuando el producto se ejecuta desde interfaz;
- el modulo si exporta soportes depurados y el archivo de `CVA/DVA`;
- el modulo hoy no escribe explicitamente `Tbl_Posicion_Forward.csv`.

Implicacion:

- al ejecutar el boton de `Forward`, el servicio guarda primero la tabla en SQLite y luego consolida la fecha;
- si luego se usa un flujo que reconsolida sin tablas en memoria, la carga de `Forward` se toma de `risko.db`;
- los archivos procesados quedan como soporte o fallback temporal.

## Archivos y parametros involucrados

Configuracion:

- `proyectos/position_monitor/configuracion/param_rutas.csv`
- `proyectos/position_monitor/configuracion/param_libros.csv`

Llaves de `param_rutas.csv` usadas:

- `Forward_Local`
- `Forward_IFRS_Local`

Las llaves Summit quedan del lado de Vector/configuracion de carga. El modulo
Python valida los archivos locales que Vector debio dejar en `datos/insumos`.

Soportes generados:

- `datos/position_monitor/procesados/df_Insumo_FWD.xlsx`
- `datos/position_monitor/procesados/df_Insumo_FWD_IFRS.xlsx`
- `datos/position_monitor/procesados/df_Fwd_CVADVA.xlsx`

## Estructura canonica esperada

La salida devuelta en memoria usa estas columnas:

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

Valores fijos de `Forward`:

- `PRODUCTO = Forward`
- `COMPANY = Colombia`
- `CLASIFICACION_CONTABLE = NA`

## Paso a paso del flujo

### 1. Construccion de rutas

La fecha llega, por ejemplo:

- `16-06-2026`

El modulo arma el sufijo:

```text
ddmmaaaa_000.xls
```

Ejemplo:

- `16062026_000.xls`

Para cada vista contable, el modulo resuelve:

- una ruta local de insumo.

### 2. Validacion del insumo local

Para Banking e IFRS:

- Vector debe haber dejado los archivos en `datos/insumos`;
- el modulo valida las rutas locales `Forward_Local` y `Forward_IFRS_Local`;
- si falta alguno, el proceso falla con `FileNotFoundError`.

Si el archivo local no existe:

- el proceso falla con `FileNotFoundError`.

### 3. Lectura del insumo

Ambos archivos se leen con:

- separador `;`
- `skiprows=5`
- codificacion `latin1`
- `on_bad_lines="skip"`

Los dos archivos comparten layout y por eso usan el mismo parser.

## Depuracion del detalle

### Columnas monetarias convertidas a numero

La lista exacta es:

```python
[
    "VP_Y_USD_BUY",
    "VP_Y_USD_SELL",
    "VALOR_LIQ",
    "VP_Y_SETT_CCY_CVA",
]
```

### Columnas descartadas

El modulo elimina una lista larga de columnas operativas, de sensibilidad, CVA, netting y validaciones.

La intencion funcional de esa limpieza es dejar solo:

- identificadores de la operacion;
- `BOOK`;
- fechas clave;
- monedas de compra, venta y settlement;
- valores monetarios que si entran al calculo.

La lista exacta vive en `columnas_descartar` dentro de `forward.py`. Incluye, entre otras:

- `NIT CONTRAPARTE`
- `FOLDER`
- `RESET RATE`
- `DIAS_VCTO_Y`
- `VP X USD SELL`
- `P&G Diario`
- `NETTING (ISDA)`
- `CVA CURVE`
- `DIFERENCIA CVA COP X`
- `DIFERENCIA CVA COP Y`

## Renombres aplicados

El modulo homologa los nombres del layout fuente a nombres simples en mayuscula con guion bajo.

Renombres principales:

```python
{
    "TRADE ID": "TRADE_ID",
    "PAR MONEDAS": "PAR_MONEDAS",
    "BUY/SELL": "BUY_SELL",
    "CCY COMPRA": "CCY_COMPRA",
    "CCY VENTA": "CCY_VENTA",
    "CCY SETTLEMENT": "CCY_SETTLEMENT",
    "F_VCTO": "F_VCTO",
    "F_CUMPTO": "F_CUMPTO",
    "VP Y USD SELL": "VP_Y_USD_SELL",
    "VP Y USD BUY": "VP_Y_USD_BUY",
    "VALOR LIQ": "VALOR_LIQ",
    "VP Sett Ccy Y": "VP_Y_SETT_CCY_CVA",
    "VP Y SETT CCY CVA": "VP_Y_SETT_CCY_CVA",
}
```

## Conversiones y campos auxiliares

### Fechas

La fecha de corte se convierte con `dayfirst=True`.

Despues el modulo crea:

- `CORTE = fecha_corte.date()`

Tambien convierte:

- `F_VCTO` con formato exacto `%d/%m/%y`
- `F_CUMPTO` con `dayfirst=True`

### Textos de control

El modulo limpia:

- `BUY_SELL`
- `CCY_COMPRA`
- `CCY_VENTA`
- `CCY_SETTLEMENT`

## Regla exacta de calculo de la posicion

La formula implementada en codigo es esta:

```python
if CORTE < F_VCTO:
    if CCY_COMPRA == "COP" or CCY_VENTA == "COP":
        if BUY_SELL == "COMPRA":
            POSICION = VP_Y_USD_BUY
        elif BUY_SELL == "VENTA":
            POSICION = VP_Y_USD_SELL
        else:
            POSICION = 0
    else:
        POSICION = VP_Y_USD_BUY + VP_Y_USD_SELL
else:
    if CCY_SETTLEMENT == "COP" or CORTE >= F_CUMPTO:
        POSICION = 0
    else:
        POSICION = VP_Y_SETT_CCY_CVA
```

Interpretacion funcional:

- si el corte es anterior al vencimiento, la operacion sigue viva;
- si en esa fase alguna pata es `COP`, el signo operativo depende de `BUY_SELL`;
- si ninguna pata es `COP`, la exposicion se calcula como suma de los VP en USD;
- si la operacion ya paso a la fase posterior al vencimiento, la exposicion se apaga si liquida en `COP` o si ya se cumplio;
- en caso contrario, usa `VP_Y_SETT_CCY_CVA`.

## Agregacion y enriquecimiento

### Agrupacion base

Despues del calculo por operacion, el modulo agrupa por:

```python
BOOK
```

La primera tabla agregada es:

```python
tabla_posicion = df_forward.groupby(["BOOK"], as_index=False)["POSICION"].sum()
```

### Parametrizacion por `param_libros.csv`

Luego se resuelven:

- `BOOK_HOMOL`
- `LB_LT`
- `INSTRUMENTO`
- `MONEDA_POSICION`

La clave de busqueda es:

- `PRODUCTO = Forward`
- `BOOK`

Si el `BOOK` ya viene homologado, el helper tambien puede resolver por `BOOK_HOMOL`.

Si no hay definicion:

- se deja alerta en log;
- `LB_LT = No definido`.

## Construccion de Banking e IFRS

La funcion `_depurar_forward_posicion` se ejecuta dos veces:

- una con `etiqueta_banking_cva_dva = Banking`
- una con `etiqueta_banking_cva_dva = IFRS`

La formula de posicion es la misma en ambos casos.

La unica diferencia entre las dos tablas es la etiqueta final en `BANKING_CVA_DVA`.

## Regla de `CVA/DVA`

La funcion `_construir_tabla_cva_dva` hace:

1. `outer join` por `BOOK` entre IFRS y Banking;
2. reemplaza vacios con cero;
3. calcula:

```python
POSICION = POSICION_IFRS - POSICION_BANKING
```

Esto conserva:

- books presentes solo en IFRS;
- books presentes solo en Banking;
- diferencias contables cuando una vista tenga cero y la otra no.

## Persistencia actual del modulo

### Lo que si se guarda

- el detalle depurado Banking;
- el detalle depurado IFRS;
- la tabla historica de `CVA/DVA` en Excel.

### Lo que no escribe hoy el codigo

Aunque existe la ruta `Tbl_Posicion_Forward.csv` en `rutas.py`, el modulo actual no la exporta explicitamente en `ejecutar_forward`.

La actualizacion por fecha solo se aplica a:

- `df_Fwd_CVADVA.xlsx`

## Trazas de depuracion actuales del codigo

El codigo actual incluye instrucciones de depuracion:

- `df_forward.info()`

Eso significa que hoy el modulo:

- imprime estructura del DataFrame en consola;
- deja una traza adicional util para revisar layout de insumos.

## Logs que genera el modulo

El proceso registra:

- inicio del proceso;
- fecha de trabajo;
- rutas locales de Banking e IFRS;
- validacion de archivos cargados por Vector;
- tamano de cada insumo;
- guardado del detalle Banking;
- guardado del detalle IFRS;
- guardado del archivo `CVA/DVA`.

## Errores tipicos

`No se encontro la configuracion ... en param_rutas.csv`

- falta alguna llave de Forward en `param_rutas.csv`

`No se encontro el insumo Forward ...`

- Vector no dejo el archivo local esperado en `datos/insumos`

`Fecha no valida para Forward`

- la fecha no pudo convertirse

`ALERTA mapa_lb_lt`

- existe un `BOOK` que no esta definido en `param_libros.csv`

## Resumen ejecutivo de la regla

La posicion de Forward hoy:

- se calcula por operacion y luego por `BOOK`;
- depende del estado relativo entre corte, vencimiento y cumplimiento;
- trata distinto operaciones con pata `COP` y operaciones sin pata `COP`;
- publica tres vistas: `Banking`, `IFRS` y `CVA/DVA`;
- enriquece `LB_LT` e `INSTRUMENTO` desde `param_libros.csv`;
- se consolida por memoria cuando se ejecuta desde interfaz.
