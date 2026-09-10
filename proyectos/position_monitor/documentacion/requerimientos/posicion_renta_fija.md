# Posicion Renta Fija

## Objetivo del modulo

El modulo `renta_fija.py` transforma el reporte de titulos en una tabla canonica de `Position Monitor`.

Ademas de la tabla consolidable, el modulo genera un workbook operativo con varias vistas utiles para analisis.

## Archivos y parametros involucrados

Configuracion:

- `proyectos/position_monitor/configuracion/param_rutas.csv`
- `proyectos/position_monitor/configuracion/param_libros.csv`
- `proyectos/position_monitor/configuracion/param_librorf.csv`
- `proyectos/position_monitor/configuracion/param_monedarf.csv`

Llaves de `param_rutas.csv` usadas:

- `Titulos_Summit`
- `Titulos_Local`

La carga desde la fuente operativa la hace Vector. El modulo usa `Titulos_Local`
para validar el archivo que debe existir en `datos/insumos`.

Salidas:

- `datos/position_monitor/procesados/Tbl_Posicion_Renta_Fija.csv`
- `datos/position_monitor/procesados/Tbl_Posicionrf.xlsx`
- `datos/position_monitor/procesados/Posicionrf.xlsx`

## Estructura canonica publicada

La salida consolidable usa estas columnas:

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

Valores fijos del producto:

- `PRODUCTO = Titulos`
- `BANKING_CVA_DVA = Banking`

Monedas liberadas:

- `USD`
- `COP`
- `EUR`
- `UVR`

Todas estas monedas son procesadas y escritas tanto en la tabla canónica como en los workbooks operativos.

## Paso a paso del flujo

### 1. Resolucion de fecha de trabajo

Si la fecha no llega:

- el modulo usa `Calcula_Fecha()`

Si la fecha llega:

- la convierte con `pd.to_datetime(..., dayfirst=True)`

Si no puede convertirla:

- falla con `ValueError`.

### 2. Construccion de rutas del archivo fuente

El nombre del archivo no usa el mismo patron que derivados.

La fecha se transforma a:

```text
ddmmYYYY
```

Luego el modulo consulta:

- cuantos dias no habiles han pasado desde el ultimo habil;
- si son cero, el sufijo esperado es `ddmmYYYY.csv`;
- si son mayores a cero, el sufijo esperado es `ddmmYYYY_n.csv`.

Ejemplo conceptual:

- habil: `16062026.csv`
- no habil con dos dias desde el ultimo habil: `16062026_2.csv`

La ruta local siempre queda con:

- `ddmmYYYY.csv`

## Lectura del reporte fuente

El archivo de titulos llega con una estructura no tabular directa.

El parser hace esto:

1. lee el archivo con separador tab (`\t`);
2. toma la columna `REPORTE TITULOS;`;
3. la divide por `;`;
4. expande el resultado a muchas columnas;
5. elimina filas iniciales de encabezado tecnico;
6. toma una fila como nombres definitivos;
7. elimina las dos ultimas columnas;
8. intenta convertir columnas a numerico cuando se puede.

### Columnas exactas requeridas del reporte de titulos

Para rastrear, validar o incorporar un nuevo archivo insumo al proceso, este debe contener exactamente las siguientes columnas (después de la separación por punto y coma `;`):

1. **`FECHA INFORME`**: Fecha del corte (formato `dd/mm/yyyy`). Es validada contra la fecha solicitada en la ejecución.
2. **`BOOK`**: Nombre del libro contable/operativo (ej. `TRADING`, `RF_ME_FV_OCI`, `OBLIGATORIAS`).
3. **`VP MDO Y CCY`**: Valor presente de mercado de la posición en la moneda del título. Se utiliza como el valor de `POSICION`.
4. **`MONEDA DEL TITULO`**: Moneda del instrumento (ej. `COP`, `USD`). Solo las posiciones en COP y USD son procesadas y publicadas.
5. **`COMPANY`**: Entidad/Agencia propietaria del título (ej. `BDB_COLOMBIA`).
6. **`ESQUEMA CONTABLE`**: Esquema contable (ej. `AFS`, `HTM`), utilizado para mapear el libro contable auxiliar vía `param_librorf.csv`.
7. **`LEGALNAME`**: Razon social o emisor legal. Permite clasificar la posición en `Deuda Publica` o `Deuda Privada`.
8. **`DURACION MODIFICADA`**: Utilizada para calcular la sensibilidad `DVO1` y la métrica `SENSIBILIDAD 100PBS`.
9. **`FECHA VENCIMIENTO`**: Fecha de vencimiento del título (`dd/mm/yyyy`), usada para calcular los años restantes y definir el `GRUPO VENCIMIENTO`.
10. **`TIPO INVERSION`**: Clasificación del instrumento (ej. `TF`, `TREAS`, `TIP`, `IPC`, `IBR`, `NOTES`, `LETRA`), base para mapear a la columna agrupada `TITULOS`.
11. **`SECURITY TYPE`**: Tipo de título (ej. `CD`, `BOND`), usado junto con `TIPO INVERSION` para clasificar títulos como `CDT`, `BONOS ME`, etc.
12. **Fechas operativas**: `FECHA EMISION`, `FECHA COMPRA`, `FECHA CUMPLIMIENTO` (son convertidas automáticamente a tipo fecha).

### Fechas convertidas

El parser convierte estas columnas:

- `FECHA INFORME`
- `FECHA EMISION`
- `FECHA VENCIMIENTO`
- `FECHA COMPRA`
- `FECHA CUMPLIMIENTO`

Todas usan el formato:

- `%d/%m/%Y`

## Enriquecimientos del reporte

### 1. Clasificacion contable de apoyo

Desde `param_librorf.csv` el modulo crea:

- `TIPO LIBRO CONTABLE`

La llave usada es:

- `ESQUEMA CONTABLE`

### 2. Clasificacion de moneda de apoyo

Desde `param_monedarf.csv` el modulo crea:

- `TIPO MONEDA`

La llave usada es:

- `MONEDA DEL TITULO`

### 3. Clasificacion oficial `LB_LT`

La clasificacion final publicada ya no sale de `param_librorf.csv`.

Hoy el valor oficial de:

- `LB_LT`
- `INSTRUMENTO`

sale de `param_libros.csv`, usando:

- `PRODUCTO = Titulos`
- `BOOK`

Si no existe un `BOOK` en la tabla:

- el proceso deja alerta;
- `LB_LT = No definido`.

## Variables derivadas de negocio

### Tipo de emisor

El modulo marca `TIPO EMISOR` como `Deuda Publica` solo si `LEGALNAME` esta en una lista cerrada de emisores publicos.

Si no esta en esa lista:

- queda como `Deuda Privada`.

### Sensibilidades

Se crean estas metricas:

```python
DVO1 = (DURACION MODIFICADA * 0.0001) * VP MDO Y CCY
SENSIBILIDAD 100PBS = DVO1 * 100
VALOR 100PBS = VP MDO Y CCY - SENSIBILIDAD 100PBS
```

### Grupo de vencimiento

Se calcula:

```python
anios = (FECHA VENCIMIENTO - FECHA INFORME).days / 365
```

Regla:

- `< 3`: `Corto Plazo`
- `>= 3 y < 5`: `Mediano Plazo`
- `>= 5`: `Largo Plazo`

### Clasificacion `TITULOS`

El modulo reasigna el producto visible segun `TIPO INVERSION`, `SECURITY TYPE` y `MONEDA DEL TITULO`.

Mapeos implementados:

- `TF` + `CD` -> `CDT`
- `TF` + moneda `USD` o `EUR` -> `BONOS ME`
- `TREAS` -> `BONOS ME`
- `TIP` -> `T.HIPOTECARIA`
- `TF` + moneda `COP` o `UVR` -> `BONOS`
- `IPC` o `IBR` -> `BONOS`
- `NOTES` o `LETRA` -> `NOTAS`
- `TDAAI`, `TDABI`, `TDAA`, `TDAB`, `TDS` -> `OBLIGATORIAS`

Si no cumple ninguna condicion:

- se deja el valor original de `TIPO INVERSION`.

### Tipo de tasa

El codigo actual define:

```python
if TIPO_INVERSION == "IPC" and TIPO_INVERSION == "IBR":
    TIPO_TASA = "Variable"
else:
    TIPO_TASA = "Fija"
```

Observacion importante:

- esa condicion nunca puede ser verdadera;
- por lo tanto, en el comportamiento actual del codigo `TIPO TASA` termina siempre como `Fija`.

Se documenta asi porque la meta de este documento es describir el comportamiento real del modulo.

## Construccion de la posicion operativa

La vista operativa `posicion` usa:

- `Fecha = FECHA INFORME`
- `Book = BOOK`
- `Agencia = COMPANY`
- `Producto = TITULOS`
- `Posicion = VP MDO Y CCY`
- `LB/LT = LB_LT`
- `Der/TF = Renta fija`
- `Moneda = MONEDA DEL TITULO`

Esta vista es la base del workbook operativo.

Antes de construirla se filtra `MONEDA DEL TITULO` para conservar las monedas habilitadas (COP, USD, EUR y UVR). Por tanto, al exportar `Posicionrf.xlsx` se observan estas cuatro monedas.

## Construccion de la tabla canonica

La salida consolidable construye una fila por BOOK y MONEDA, no por titulo individual.

La misma regla de alcance conserva COP, USD, EUR y UVR antes del agrupamiento.

Primero crea una tabla intermedia con:

- `FECHA = FECHA INFORME`
- `BOOK = BOOK`
- `POSICION = VP MDO Y CCY`
- `MONEDA_POSICION = MONEDA DEL TITULO`
- `COMPANY = COMPANY`
- `CLASIFICACION_CONTABLE = ESQUEMA CONTABLE`
- `PRODUCTO = Titulos`
- `LB_LT` desde `param_libros.csv`
- `INSTRUMENTO` desde `param_libros.csv`
- `BANKING_CVA_DVA = Banking`

Luego agrupa por:

```python
["FECHA", "PRODUCTO", "BOOK", "MONEDA_POSICION",
 "LB_LT", "INSTRUMENTO", "COMPANY", "BANKING_CVA_DVA"]
```

Sumando `POSICION` y conservando el primer `CLASIFICACION_CONTABLE` del grupo.

Este agrupamiento consolida multiples titulos del mismo BOOK y moneda en una sola fila.
Un book como `TRADING` en USD que tenga 10 titulos USD quedara como una sola fila
con la suma de sus VP MDO Y CCY.

### Nota sobre TRADE_CORTA

El book `TRADE_CORTA` fue incorporado en `param_libros.csv` con:

```
PRODUCTO  = Titulos
LB_LT     = Tesoreria
INSTRUMENTO = Renta_fija
MONEDA_POSICION = MULTI
```

Sin esta entrada el book quedaba como `LB_LT = No definido`.

## Escritura del historico por fecha

La tabla canonica pasa por `actualizar_datos_por_fecha` con:

- archivo `Tbl_Posicion_Renta_Fija.csv`
- llave `FECHA`
- formato `csv`

Esto reemplaza solo la fecha procesada y conserva el resto del historico.

## Workbook operativo adicional

El archivo `Tbl_Posicionrf.xlsx` se genera con cinco hojas:

- `Detalle`
- `Libros`
- `Agencias`
- `Estructura`
- `Moneda`

Las hojas resumen se construyen con `pivot_table` sobre la vista operativa.

La funcion `_actualizar_excel`:

- intenta leer la hoja previa;
- concatena con el nuevo corte;
- elimina indices duplicados conservando el ultimo;
- ordena por indice.

## Archivos generados

Tabla consolidable:

- `Tbl_Posicion_Renta_Fija.csv`

Workbook operativo:

- `Tbl_Posicionrf.xlsx`

Detalle operativo exportado:

- `Posicionrf.xlsx`

## Logs que genera el modulo

El proceso registra:

- fecha de trabajo;
- ruta local;
- validacion del archivo cargado por Vector;
- cancelacion por fecha existente;
- guardado del CSV consolidable;
- guardado del workbook operativo.

## Errores tipicos

`No se encontro la configuracion ... en param_rutas.csv`

- falta la llave de titulos en `param_rutas.csv`

`No se encontro el archivo fuente de renta fija`

- Vector no dejo el archivo local esperado para la fecha en `datos/insumos`

`Fecha no valida para renta fija`

- la fecha recibida no pudo convertirse

`ALERTA mapa_lb_lt`

- hay `BOOK` de titulos sin definicion en `param_libros.csv`

## Resumen ejecutivo de la regla

La posicion de renta fija hoy es:

- `VP MDO Y CCY` por titulo;
- agregada por `BOOK` y `MONEDA_POSICION` (no titulo a titulo);
- con `LB_LT` oficial parametrico;
- con varias variables de analisis adicionales;
- y con una sola vista consolidable `Banking`.
