# Mapa LB_LT parametrico

## Objetivo del componente

El archivo `param_libros.csv` y el helper `parametros_libros.py` definen la logica central para homologar:

- `BOOK`
- `LB_LT`
- `INSTRUMENTO`
- `MONEDA_POSICION`

Su objetivo es que todos los productos de `Position Monitor` usen una sola fuente de verdad para clasificar books.

## Fuente oficial

La fuente vigente es:

- `proyectos/position_monitor/configuracion/param_libros.csv`

El helper que la consume es:

- `proyectos/position_monitor/procesos/parametros_libros.py`

## Estructura requerida de la tabla

La tabla debe traer exactamente estas columnas:

```csv
PRODUCTO,BOOK,LB_BT,BOOK_HOMOL,LB_LT,INSTRUMENTO,MONEDA_POSICION
```

Descripcion funcional:

- `PRODUCTO`: nombre canonico del producto
- `BOOK`: nombre original del insumo
- `LB_BT`: referencia operativa Bancario/Trading
- `BOOK_HOMOL`: nombre final homologado
- `LB_LT`: clasificacion final que se publica
- `INSTRUMENTO`: familia que se publica
- `MONEDA_POSICION`: moneda por defecto cuando aplica

## Productos soportados hoy

El helper normaliza estos nombres de producto:

- `NOVADO` o `NOVADOS` -> `Novados`
- `FORWARD` -> `Forward`
- `SWAP` o `SWAPS` -> `Swap`
- `TITULO`, `TITULOS` o `RENTA_FIJA` -> `Titulos`

## Paso a paso de la logica interna

### 1. Lectura y limpieza de `param_libros.csv`

La funcion `cargar_parametros_libros`:

- lee el CSV con `latin-1`;
- recorta nombres de columna;
- valida que existan todas las columnas requeridas;
- limpia espacios y valores vacios;
- normaliza el nombre de producto;
- crea claves tecnicas para busqueda.

### 2. Claves tecnicas que construye

El helper crea:

- `_PRODUCTO_CLAVE`
- `_BOOK_CLAVE`
- `_BOOK_HOMOL_CLAVE`

Todas estas claves:

- quitan tildes;
- convierten a mayuscula;
- reemplazan separadores por `_`.

Ejemplos:

- `Renta Fija ME` -> `RENTA_FIJA_ME`
- `Cubre_Bac` -> `CUBRE_BAC`
- `Titulos` -> `TITULOS`

## Validaciones que aplica

### Duplicados por `PRODUCTO + BOOK`

Si el CSV trae mas de una fila para la misma combinacion:

- `PRODUCTO`
- `BOOK`

el helper falla con `ValueError`.

### Conflictos por llave de busqueda

El helper permite buscar tanto por:

- `BOOK` original
- `BOOK_HOMOL`

Por eso crea una tabla de lookup ampliada.

Si dos filas distintas terminan produciendo la misma llave de busqueda pero con atributos incompatibles en:

- `BOOK_HOMOL`
- `LB_LT`
- `INSTRUMENTO`
- `MONEDA_POSICION`

el helper tambien falla con `ValueError`.

## Como resuelve la homologacion

La funcion principal es:

```python
enriquecer_con_parametros_libros(df_base, producto, ...)
```

Requisitos de la tabla base:

- debe existir la columna `BOOK`

La funcion hace esto:

1. limpia `BOOK`;
2. construye una clave normalizada del `BOOK`;
3. filtra `param_libros.csv` por el producto pedido;
4. arma una tabla de lookup por `BOOK` y por `BOOK_HOMOL`;
5. hace `merge` contra la tabla base;
6. completa columnas homologadas.

## Reglas de prioridad al completar columnas

### `BOOK`

Si existe `BOOK_HOMOL` en la parametrizacion:

- el `BOOK` publicado se reemplaza por `BOOK_HOMOL`

Si no existe:

- se conserva el `BOOK` original

### `LB_LT`

Prioridad:

1. `LB_LT` de `param_libros.csv`
2. `LB_LT` que ya traia la tabla base
3. default recibido por parametro

### `INSTRUMENTO`

Prioridad:

1. `INSTRUMENTO` de `param_libros.csv`
2. `INSTRUMENTO` que ya traia la tabla base
3. default recibido por parametro

### `MONEDA_POSICION`

Prioridad:

1. `MONEDA_POSICION` de `param_libros.csv`
2. `MONEDA_POSICION` que ya traia la tabla base
3. default recibido por parametro

## Regla obligatoria para faltantes

Si un `BOOK` no tiene definicion para el producto solicitado:

- se registra una alerta de negocio en log;
- el `BOOK` se conserva;
- `LB_LT` queda con el default recibido;
- en los procesos actuales ese default es `No definido`.

Mensaje de alerta actual:

```text
ALERTA mapa_lb_lt: no se encontro definicion en param_libros.csv para <Producto> en los BOOK: ...
```

## Productos que hoy usan este helper

- `Novados`
- `Forward`
- `Swap`
- `Titulos`

## Uso actual por producto

### Novados

Usa el helper despues de agrupar por `BOOK`.

Completa:

- `BOOK`
- `LB_LT`
- `INSTRUMENTO`
- `MONEDA_POSICION`

### Forward

Usa el helper:

- en Banking
- en IFRS
- en `CVA/DVA`

Ademas puede resolver books que ya vienen homologados por el flujo previo.

### Swap

Usa el helper:

- al construir las tablas de Banking, IFRS y `CVA/DVA`
- al reconstruir la publicacion oficial historica

### Titulos

Usa el helper sobre el detalle del reporte de titulos para definir el `LB_LT` oficial por `BOOK`.

## Mantenimiento esperado

Cada vez que aparezca un `BOOK` nuevo:

1. agregar fila en `param_libros.csv`
2. definir `PRODUCTO`
3. definir `BOOK_HOMOL`
4. definir `LB_LT`
5. definir `INSTRUMENTO`
6. definir `MONEDA_POSICION` cuando aplique
7. volver a ejecutar el producto
8. confirmar que no queden alertas `No definido`

## Resumen ejecutivo de la regla

`param_libros.csv` es hoy la fuente oficial de clasificacion de books en `Position Monitor`.

La logica implementada:

- busca por producto y `BOOK`;
- acepta tambien books ya homologados;
- rechaza duplicados y conflictos;
- publica alerta visible cuando falta una definicion;
- evita que los productos asuman `Trading` por defecto cuando el mapa no existe.
