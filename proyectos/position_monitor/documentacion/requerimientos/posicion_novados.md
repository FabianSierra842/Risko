# Posicion Novados

## Objetivo del modulo

El modulo `novados.py` calcula la posicion de `Novados` para una fecha de corte y la devuelve en el formato canonico que consume `Position Monitor`.

El proceso hace cinco cosas principales:

1. valida que Vector haya dejado el archivo local en `datos/insumos`;
2. lee el insumo local;
3. depura el detalle crudo;
4. calcula la posicion por `BOOK`;
5. retorna la tabla canonica para que el servicio la guarde en `tbl_posicion_novados`.

## Archivos y parametros involucrados

Entradas de configuracion:

- `proyectos/position_monitor/configuracion/param_rutas.csv`
- `proyectos/position_monitor/configuracion/param_libros.csv`

Llaves de `param_rutas.csv` usadas:

- `Novados_Local`

La carga desde Summit la hace Vector. El modulo usa `Novados_Local` para validar
el insumo en `datos/insumos`.

Salidas:

- `datos/position_monitor/procesados/Tbl_Posicion_Novados.csv`
- `datos/position_monitor/procesados/df_Insumo.xlsx`

Compatibilidad historica:

- si existe `Tbl_Novados_Posicion.csv` y aun no existe `Tbl_Posicion_Novados.csv`, el modulo copia el archivo legado al nombre nuevo antes de procesar.

## Estructura canonica que publica

La salida final siempre debe traer estas columnas:

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

Valores fijos de `Novados`:

- `PRODUCTO = Novados`
- `COMPANY = Colombia`
- `CLASIFICACION_CONTABLE = NA`
- `BANKING_CVA_DVA = Banking`

## Paso a paso del flujo

### 1. Inicio y migracion del nombre legado

La funcion `ejecutar_novados`:

- registra el inicio del proceso;
- registra la fecha de trabajo recibida;
- revisa si existe la salida vieja `Tbl_Novados_Posicion.csv`;
- si la salida nueva no existe, la copia con el nombre oficial `Tbl_Posicion_Novados.csv`.

Esto evita perder historico al cambiar el nombre del archivo consolidable.

### 2. Construccion de rutas del insumo

La fecha de trabajo llega en formato de interfaz, por ejemplo:

- `16-06-2026`

Con esa fecha el modulo construye un sufijo asi:

```text
ddmmaa_000.xls
```

Ejemplo:

- `160626_000.xls`

Luego arma la ruta local esperada:

- una ruta local en `datos/insumos`.

### 3. Validacion del archivo local

Si Vector dejo el archivo local:

- el proceso continua;
- deja log de lectura/validacion.

Si el archivo local no existe:

- el proceso falla con `FileNotFoundError`.

### 4. Lectura del archivo fuente

El insumo se lee con:

- separador `;`
- `skiprows=2`
- codificacion `latin1`

El DataFrame resultante es el detalle crudo de Novados.

## Depuracion del detalle

### Columnas descartadas

Antes del calculo, el modulo elimina columnas operativas que no usa para posicion.

Lista exacta actual:

```python
[
    "EXTERNAL ID",
    "TRADE ID OTC",
    "CLIENTE OTC",
    "ID CONTRATO",
    "No. CONTRATOS",
    "PRECIO PACTADO",
    "TRADER",
    "VALOR PACTADO",
    "VALOR MERCADO",
    "PRECIO MERCADO (Y)",
    "MTM TOTAL PESOS",
    "PRECIO MERCADO (Y-1)",
    "MTM DIA PESOS",
    "FOLDER",
    "COMPANY",
    "Delta Full Valuation   1 USD",
    "VLR SENSIBLE -   NOMINAL",
    "VLR SENSIBLE -   NOMINAL USD",
    "COMPONENTE CAMBIARIO",
    "ACUM. COMPONENTE   CAMBIARIO",
    "COMP. CAMBIARIO   CIERRE AÑO ANTERIOR",
    "VLR. COMP. CAMBIARIO   AÑO FISCAL",
]
```

### Renombres aplicados

Despues del descarte, el modulo homologa varias columnas:

```python
{
    "TRADE ID": "TRADE_ID",
    "FECHA NEGOCIACION": "FECHA_NEGOCIACION",
    "PAR MONEDAS": "PAR_MONEDAS",
    "COMPRA/VENTA": "COMPRA_VENTA",
    "VENCIMIENTO": "VENCIMIENTO",
    "NOMINAL": "NOMINAL",
    "DESK": "DESK",
    "VALOR SENSIBLE": "VALOR_SENSIBLE",
}
```

### Conversiones clave

La fecha de corte se convierte con `pd.to_datetime(..., dayfirst=True)`.

Luego:

- `VENCIMIENTO` se convierte con formato exacto `%d/%m/%y`
- `VALOR_SENSIBLE` se convierte a numerico quitando comas

Adicionalmente se crea:

- `CORTE = fecha_corte.date()`

## Regla de calculo de la posicion

La logica de posicion es simple y directa:

```python
if VENCIMIENTO == CORTE:
    POSICION = 0
else:
    POSICION = VALOR_SENSIBLE
```

Interpretacion:

- si la operacion vence exactamente el dia del corte, ya no aporta posicion;
- si no vence ese dia, la posicion es el `VALOR_SENSIBLE`.

## Agregacion y homologacion final

### Agrupacion

El detalle ya calculado se agrupa asi:

```python
tabla_posicion = df_insumo.groupby(["BOOK"], as_index=False)["POSICION"].sum()
```

Es decir:

- la primera agregacion real es por `BOOK`;
- no hay separacion adicional por mesa, moneda ni contraparte en la salida canonica.

### Enriquecimiento con `param_libros.csv`

Despues de agrupar, la tabla se enriquece con:

- `BOOK_HOMOL`
- `LB_LT`
- `INSTRUMENTO`
- `MONEDA_POSICION`

La busqueda se hace contra `param_libros.csv` usando:

- `PRODUCTO = Novados`
- `BOOK`

Si no existe definicion:

- el proceso registra una alerta;
- `LB_LT` queda como `No definido`;
- `BOOK` se conserva tal como llego.

## Escritura del historico por fecha

La tabla final pasa por `actualizar_datos_por_fecha`, que:

- busca si ya existe informacion para la misma `FECHA`;
- reemplaza esa fecha si el usuario confirma;
- conserva el resto del historico.

La columna llave usada para el reemplazo es:

- `FECHA`

El formato de salida es:

- `csv`

## Archivos generados

Salida consolidable:

- `Tbl_Posicion_Novados.csv`

Soporte de detalle:

- `df_Insumo.xlsx`

## Logs que genera el modulo

El proceso deja trazas para:

- inicio del proceso;
- fecha de trabajo;
- ruta local esperada;
- validacion del archivo cargado por Vector;
- tamano del insumo cargado;
- migracion del archivo legado si aplica;
- cancelacion por fecha existente;
- guardado de la tabla final y del detalle.

## Errores tipicos

`No se encontro la configuracion ... en param_rutas.csv`

- falta la llave `Novados_Local`

`No se encontro el insumo de Novados`

- Vector no dejo el archivo local esperado en `datos/insumos`

`Fecha no valida para Novados`

- la fecha recibida por interfaz no pudo convertirse

`ALERTA mapa_lb_lt`

- aparecio un `BOOK` no parametrizado en `param_libros.csv`

## Resumen ejecutivo de la regla

La posicion de Novados hoy es:

- `VALOR_SENSIBLE` por operacion;
- cero si la operacion vence en la fecha de corte;
- agrupada por `BOOK`;
- homologada con `param_libros.csv`;
- publicada como una sola vista `Banking`.
