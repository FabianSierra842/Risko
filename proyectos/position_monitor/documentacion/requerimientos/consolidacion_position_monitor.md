# Consolidacion de Position Monitor

## Objetivo del modulo

`proyectos/position_monitor/procesos/consolidacion.py` es la capa que une las
tablas canonicas de productos y actualiza la base SQLite principal:

- `datos/base de datos/risko.db`

Su responsabilidad es:

- normalizar columnas y valores;
- guardar tablas de producto por fecha;
- reemplazar el corte de una fecha sin duplicar informacion;
- consolidar productos en una vista transversal;
- excluir `IFRS` de las tablas publicables;
- mantener `tbl_posicion_actual`, `tbl_posicion_consolidada` y
  `tbl_posicion_historico`;
- exportar CSV de compatibilidad cuando sea posible.

La consolidacion no recalcula posiciones ni conversiones de moneda. La posicion
se conserva en `POSICION` y su unidad la define `MONEDA_POSICION`.

## Bases SQLite

| Base | Ruta | Uso |
| --- | --- | --- |
| Principal | `datos/base de datos/risko.db` | Tablas oficiales y vistas consolidadas |
| Pruebas | `datos/base de datos/risko_pruebas.db` | Auxiliares, pruebas y productos no liberados |

La ruta principal se define en `ARCHIVO_BASE_DATOS_RISKO` y la de pruebas en
`ARCHIVO_BASE_DATOS_RISKO_PRUEBAS`.

## Tablas oficiales

| Tabla | Descripcion |
| --- | --- |
| `tbl_posicion_forward` | Salida canonica de Forward |
| `tbl_posicion_novados` | Salida canonica de Novados |
| `tbl_posicion_opciones` | Salida canonica de Opciones |
| `tbl_posicion_renta_fija` | Salida canonica de Titulos/Renta Fija |
| `tbl_posicion_swaps` | Salida canonica de Swaps |
| `tbl_posicion_consolidada` | Consolidado historico sin IFRS |
| `tbl_posicion_actual` | Foto de la fecha seleccionada |
| `tbl_posicion_historico` | Cierres operativos de mes |

El detalle de Swaps no se guarda en SQLite. Se genera como soporte CSV/Excel por
el modulo `swaps.py` y no participa en consolidacion.

`tbl_posicion_spot` esta reservado para pruebas y no debe existir en
`risko.db`. Para Spot se debe usar `risko_pruebas.db`.

## Contrato canonico

La consolidacion espera estas columnas base:

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

Si un producto entrega nombres ligeramente distintos, `MAPA_COLUMNAS`,
`MAPA_PRODUCTOS` y `MAPA_BANKING` absorben diferencias conocidas. Aun asi, el
modulo de producto debe intentar entregar la tabla ya canonica.

## Flujo al ejecutar un producto

Cuando la interfaz ejecuta un producto:

1. `servicios/position_monitor.py` ejecuta el flujo Vector del producto.
2. Vector copia los insumos a `datos/insumos`.
3. El modulo Python valida esos insumos locales y calcula la tabla canonica.
4. El servicio llama `guardar_tabla_producto_position_monitor(producto, tabla, fecha)`.
5. La tabla de producto en SQLite reemplaza solo la `FECHA` ejecutada.
6. `consolidar_position_monitor(fecha_corte=fecha, tablas=[tabla])` actualiza
   las tablas transversales.

Esto evita depender de CSV abiertos en Excel para escribir la informacion
oficial.

## Flujo al consolidar sin tablas en memoria

Cuando se llama:

```python
consolidar_position_monitor(fecha_corte="30/06/2026")
```

el modulo usa `cargar_tablas_desde_procesados(...)`:

1. intenta leer primero las tablas de producto desde `risko.db`;
2. si una tabla no existe, intenta usar el CSV procesado legacy;
3. si logra leer un CSV legacy, lo migra a SQLite;
4. filtra por la fecha solicitada;
5. concatena y normaliza las tablas disponibles.

La ruta de CSV es transitoria y existe solo para migracion/compatibilidad.

## Regla de reemplazo por fecha

Para tablas de producto se usa `actualizar_dataframe_por_fecha_sqlite(...)`:

- normaliza `FECHA` a `dd/mm/YYYY`;
- elimina de la tabla existente las filas de esa fecha;
- inserta las filas nuevas de esa misma fecha;
- conserva las demas fechas.

Por eso reejecutar una fecha actualiza el corte en vez de acumular duplicados.

## Consolidado, actual e historico

`tbl_posicion_consolidada`:

- fusiona el consolidado existente con la nueva fecha/producto;
- conserva fechas anteriores;
- elimina `IFRS`;
- ordena por `FECHA`, `PRODUCTO`, `BOOK` y `BANKING_CVA_DVA`.

`tbl_posicion_actual`:

- si llega `fecha_corte`, queda con esa fecha exacta;
- si no llega fecha, toma la fecha maxima disponible por producto;
- excluye `IFRS`.

`tbl_posicion_historico`:

- reemplaza la fecha/producto igual que el consolidado;
- conserva solo cierres operativos de mes;
- excluye `IFRS`.

## Vistas publicables

Las tablas consolidadas conservan:

- `Banking`
- `CVA/DVA`

`IFRS` puede existir en las tablas de producto, pero no se publica en
`tbl_posicion_consolidada`, `tbl_posicion_actual` ni `tbl_posicion_historico`.

## CSV de compatibilidad

Despues de actualizar SQLite, el modulo intenta exportar:

- `datos/position_monitor/procesados/tbl_posicion_consolidada.csv`
- `datos/position_monitor/publicados/tbl_posicion_actual.csv`
- `datos/position_monitor/publicados/tbl_posicion_historico.csv`

Si alguno esta abierto en Excel, la base SQLite queda actualizada y el log
informa que no pudo refrescar esa copia CSV. Ese error ya no debe detener el
proceso.

## API disponible

```python
from proyectos.position_monitor.procesos.consolidacion import (
    listar_tablas_position_monitor,
    columnas_tabla_position_monitor,
    leer_tabla_position_monitor,
    guardar_tabla_producto_position_monitor,
    consolidar_position_monitor,
)

print(listar_tablas_position_monitor())
print(columnas_tabla_position_monitor("tbl_posicion_actual"))

df = leer_tabla_position_monitor("tbl_posicion_actual")
guardar_tabla_producto_position_monitor("FORWARD", df_forward, "30/06/2026")
consolidar_position_monitor(fecha_corte="30/06/2026")
```

## Tablas auxiliares

Las tablas auxiliares van a `risko_pruebas.db` por defecto:

```python
from proyectos.position_monitor.procesos.consolidacion import (
    crear_tabla_auxiliar,
    guardar_tabla_auxiliar,
    leer_tabla_auxiliar,
)

crear_tabla_auxiliar("aux_validacion", {"fecha": "TEXT", "resultado": "TEXT"})
guardar_tabla_auxiliar("aux_validacion", df_validacion, if_exists="replace")
df_validacion = leer_tabla_auxiliar("aux_validacion")
```

## Spot en pruebas

Spot sigue fuera de `Ejecutar todo`, pero su boton individual, flujo Vector y
rama de servicio ya estan habilitados. Debe probarse con `pruebas=True`.

Ejemplo:

```python
from proyectos.position_monitor.procesos.spot import ejecutar_spot
from proyectos.position_monitor.procesos.consolidacion import guardar_tabla_producto_position_monitor

tabla = ejecutar_spot("03/08/2026", logger=print, pruebas=True)
guardar_tabla_producto_position_monitor("SPOT", tabla, "03/08/2026", pruebas=True, logger=print)
```

La escritura debe conservar `pruebas=True` hasta la aprobacion funcional. El
detalle del acumulado y sus tablas esta en `posicion_spot_acumulada.md`.

## Errores tipicos

`No se encontraron salidas procesadas para consolidar Position Monitor`

- no habia tablas de producto en SQLite ni CSV legacy disponibles.

`Fecha no valida para consolidacion`

- la fecha enviada no pudo convertirse.

`No hubo filas para consolidar con la fecha seleccionada`

- la fecha pedida no existe en las tablas cargadas.

`El producto SPOT esta marcado como pruebas`

- se intento guardar Spot en `risko.db`; usar `pruebas=True`.

## Resumen operativo

La consolidacion actual:

- usa SQLite como fuente maestra;
- reemplaza por fecha cuando se reejecuta un producto;
- lee CSV solo como fallback temporal;
- no acumula duplicados por reejecucion;
- excluye `IFRS` de vistas publicables;
- permite tablas auxiliares en `risko_pruebas.db`;
- exporta CSV solo como copia de compatibilidad.
