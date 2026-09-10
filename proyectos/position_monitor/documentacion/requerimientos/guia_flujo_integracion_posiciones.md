# Guia de flujo e integracion de nuevas posiciones en Position Monitor

## Objetivo

Esta guia describe como fluye hoy una posicion desde la carga de insumos hasta
la base SQLite y como agregar un producto nuevo sin romper la consolidacion.

La fuente oficial ya no son los CSV. La operacion vigente es:

```text
Interfaz Risko
  -> Vector carga insumos en datos/insumos
  -> modulo Python valida insumos locales
  -> modulo produce tabla canonica
  -> servicio guarda tabla de producto en risko.db por FECHA
  -> consolidacion actualiza tbl_posicion_consolidada, actual e historico
  -> interfaz consulta SQLite y exporta la vista filtrada si se requiere
```

## Archivos principales

| Archivo | Responsabilidad |
| --- | --- |
| `aplicaciones/interfaz_risko/interfaz_risko.py` | Pantalla principal, filtros, selector de tablas DB y exportacion |
| `aplicaciones/interfaz_risko/servicios/position_monitor.py` | Dispatcher entre UI, Vector, productos, SQLite y tablero |
| `proyectos/position_monitor/procesos/consolidacion.py` | API SQLite y consolidacion |
| `compartido/nucleo_risko/base_datos.py` | Helpers genericos SQLite |
| `compartido/nucleo_risko/rutas.py` | Rutas canonicas del proyecto |
| `Herramientas/VECTOR/VECTOR.py` | Carga de insumos desde fuentes operativas |

Documentos relacionados:

- `base_datos_risko.md`
- `consolidacion_position_monitor.md`
- `control_vector_carga_insumos.md`
- `mapa_lb_lt_parametrico.md`
- documentos `posicion_*.md` de cada producto

## Flujo desde la interfaz

El usuario selecciona una fecha y ejecuta un producto o `Ejecutar todo`.

Botones de producto activos:

- `Novados`
- `Forward`
- `Opciones`
- `Renta fija`
- `Swaps`

Spot esta comentado porque sigue en pruebas.

Cuando se ejecuta un producto:

1. el servicio identifica el flujo Vector asociado;
2. Vector carga los archivos requeridos a `datos/insumos`;
3. el modulo del producto valida que esos insumos existan para la fecha;
4. el modulo retorna una tabla canonica;
5. el servicio guarda esa tabla en `risko.db`;
6. la consolidacion actualiza las tablas transversales;
7. la interfaz muestra informacion filtrada por la fecha seleccionada.

## Responsabilidad de Vector

Toda carga de insumos debe estar en Vector. Los modulos de producto ya no deben
copiar archivos desde Summit, BDB u otras fuentes.

El modulo de producto debe:

- leer rutas locales esperadas desde `param_rutas.csv` o `rutas.py`;
- validar que Vector dejo el archivo en `datos/insumos`;
- fallar con un mensaje claro si falta el insumo;
- calcular la tabla canonica.

El modulo de producto no debe:

- copiar archivos desde la fuente operativa;
- limpiar `datos/insumos`;
- decidir flujos de carga;
- escribir directamente a la base principal si esta siendo ejecutado desde UI.

## Contrato canonico

Toda posicion que entra a consolidacion debe tener estas columnas:

```python
COLUMNAS_POSICION = [
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

Recomendaciones:

- `FECHA`: usar `dd/mm/YYYY`.
- `PRODUCTO`: usar el nombre de negocio estable: `Forward`, `Novados`,
  `Opciones`, `Titulos`, `Swap`.
- `POSICION`: numerica, sin separadores de miles como texto.
- `MONEDA_POSICION`: moneda nativa de la posicion.
- `BANKING_CVA_DVA`: usar `Banking`, `IFRS` o `CVA/DVA`.

La consolidacion tiene mapas de homologacion, pero deben ser una red de
seguridad. El modulo nuevo debe intentar entregar datos limpios.

## Escritura en SQLite

El servicio guarda la tabla de producto con:

```python
guardar_tabla_producto_position_monitor(producto, tabla, fecha_trabajo, logger=logger)
```

Esto actualiza la tabla correspondiente:

| Producto | Tabla |
| --- | --- |
| `FORWARD` | `tbl_posicion_forward` |
| `NOVADOS` | `tbl_posicion_novados` |
| `OPCIONES` | `tbl_posicion_opciones` |
| `RENTA_FIJA` / `TITULOS` | `tbl_posicion_renta_fija` |
| `SWAPS` / `SWAP` | `tbl_posicion_swaps` |

La escritura reemplaza la `FECHA` ejecutada y conserva las demas fechas. No se
requiere un modo de acumulacion.

## Consolidacion

Despues de guardar la tabla de producto, el servicio llama:

```python
consolidar_position_monitor(fecha_corte=fecha_trabajo, tablas=[tabla], logger=logger)
```

Si se ejecuta `Generar tablero` o `Consolidar` sin tablas en memoria, la
consolidacion lee primero las tablas de producto desde `risko.db`. Solo usa CSV
procesados como fallback temporal para migracion.

Tablas actualizadas:

- `tbl_posicion_consolidada`
- `tbl_posicion_actual`
- `tbl_posicion_historico`

Reglas:

- se reemplaza la fecha ejecutada;
- se excluye `IFRS` de las tablas publicables;
- `historico` conserva solo cierres operativos de mes;
- los CSV publicados se intentan refrescar solo como compatibilidad.

## Consulta y exportacion desde la interfaz

La interfaz tiene un selector `Tabla DB`:

- lista tablas de `risko.db`;
- puede apuntar a `risko_pruebas.db` con el switch `Pruebas`;
- filtra por la fecha seleccionada cuando la tabla tiene `FECHA` o `CORTE`;
- permite exportar la vista cargada a CSV o Excel.

Esto permite revisar cualquier tabla sin abrir ni bloquear archivos CSV.

## Como agregar un producto nuevo

### Paso 1. Crear o ajustar el modulo de producto

Crear un archivo en:

```text
proyectos/position_monitor/procesos/nuevo_producto.py
```

El modulo debe exponer una funcion:

```python
def ejecutar_nuevo_producto(fecha_trabajo: str, logger=None) -> pd.DataFrame | None:
    ...
```

Esa funcion debe validar insumos locales cargados por Vector y retornar
`COLUMNAS_POSICION`.

### Paso 2. Agregar el flujo en Vector

Editar:

```text
proyectos/position_monitor/configuracion/risko.json
```

Agregar un flujo que copie los insumos requeridos a `datos/insumos`. Si se usa
`param_rutas.csv`, agregar las llaves locales necesarias.

### Paso 3. Registrar el producto en el servicio

Editar:

```text
aplicaciones/interfaz_risko/servicios/position_monitor.py
```

Agregar el flujo Vector:

```python
FLUJOS_VECTOR_PRODUCTO = {
    "NUEVO_PRODUCTO": "07_Nuevo_Producto",
}
```

Agregar la ejecucion:

```python
elif producto == "NUEVO_PRODUCTO":
    from proyectos.position_monitor.procesos.nuevo_producto import ejecutar_nuevo_producto

    tabla = ejecutar_nuevo_producto(fecha_trabajo, logger=logger)
```

El guardado y la consolidacion ya ocurren al final de `ejecutar_producto`.

### Paso 4. Registrar la tabla en consolidacion

Editar:

```text
proyectos/position_monitor/procesos/consolidacion.py
```

Agregar una constante:

```python
TABLA_POSICION_NUEVO_PRODUCTO = "tbl_posicion_nuevo_producto"
```

Agregar el mapeo:

```python
TABLAS_PRODUCTO = {
    "NUEVO_PRODUCTO": TABLA_POSICION_NUEVO_PRODUCTO,
}
```

Si el producto debe entrar cuando se consolida sin tablas en memoria, agregarlo
a `cargar_tablas_desde_procesados(...)` para que lea desde SQLite y, si aplica,
desde un CSV legacy temporal.

### Paso 5. Agregar el boton en la interfaz

Editar:

```text
aplicaciones/interfaz_risko/interfaz_risko.py
```

Agregar el producto al bloque de botones y llamar:

```python
command=lambda: self.ejecutar_proceso("NUEVO_PRODUCTO")
```

Tambien incluirlo en los controles que se deshabilitan durante una ejecucion.

### Paso 6. Validar

Prueba minima:

1. ejecutar Vector en seco para el flujo nuevo;
2. ejecutar solo el producto desde la interfaz;
3. revisar que exista su tabla en `risko.db`;
4. cargar la tabla desde el selector `Tabla DB`;
5. consolidar la fecha;
6. revisar `tbl_posicion_actual`;
7. generar tablero si aplica;
8. exportar la vista desde la interfaz y validar el archivo.

Consulta rapida:

```powershell
@'
from proyectos.position_monitor.procesos.consolidacion import listar_tablas_position_monitor
print(listar_tablas_position_monitor())
'@ | python -
```

## Como agregar una tabla auxiliar

Para pruebas, parametros temporales o validaciones:

```python
from proyectos.position_monitor.procesos.consolidacion import (
    crear_tabla_auxiliar,
    guardar_tabla_auxiliar,
    leer_tabla_auxiliar,
)

crear_tabla_auxiliar("aux_mi_prueba", {"fecha": "TEXT", "valor": "REAL"})
guardar_tabla_auxiliar("aux_mi_prueba", df, if_exists="replace")
df = leer_tabla_auxiliar("aux_mi_prueba")
```

Esto apunta a `datos/base de datos/risko_pruebas.db`.

## Spot

Spot esta en pruebas y no debe escribirse en `risko.db`.

Para probarlo:

1. activar `Usar base de pruebas` en la interfaz;
2. importar las posiciones iniciales con `Excel -> base Spot`;
3. ejecutar el boton individual `Spot`;
4. revisar `tbl_posicion_spot_acumulada`, `tbl_alertas_spot` y
   `tbl_movimientos_spot` desde el selector actual.

No agregar `tbl_posicion_spot` a la base principal hasta que el proceso quede
validado. El flujo `06_Spot`, la rama de servicio y el boton ya estan activos.
Consultar `posicion_spot_acumulada.md` para la logica completa.

## Checklist minimo

- flujo Vector creado o actualizado;
- modulo valida insumos locales en `datos/insumos`;
- modulo retorna `COLUMNAS_POSICION`;
- producto agregado al servicio;
- tabla agregada al mapeo de consolidacion;
- boton o entrada agregada a la interfaz;
- prueba en `risko_pruebas.db` si el producto no esta liberado;
- prueba de reemplazo al reejecutar la misma fecha;
- validacion de `tbl_posicion_actual` con la fecha seleccionada;
- exportacion CSV/Excel revisada desde la interfaz.
