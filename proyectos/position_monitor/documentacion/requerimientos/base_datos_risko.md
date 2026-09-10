# Base de datos Risko

## Objetivo

La base de datos oficial de Risko vive en SQLite para evitar bloqueos de escritura
cuando un CSV queda abierto en Excel y para centralizar la consulta desde la
interfaz.

Los CSV que siguen existiendo en `datos/position_monitor/procesados` y
`datos/position_monitor/publicados` son copias de compatibilidad o soportes
operativos. La fuente maestra para la interfaz y la consolidacion es SQLite.

## Ubicaciones

| Base | Ruta | Uso |
| --- | --- | --- |
| Principal | `datos/base de datos/risko.db` | Tablas oficiales de Position Monitor y consolidados |
| Pruebas | `datos/base de datos/risko_pruebas.db` | Pruebas y productos no liberados |
| Auxiliar | `datos/base de datos/risko_auxiliar.db` | Detalles, controles e intermedios de todos los módulos |

Las bases `.db`, `.db-wal`, `.db-shm` y archivos temporales similares no se
versionan en Git. La carpeta se conserva con `datos/base de datos/.gitkeep`.

## Modulos de codigo

| Archivo | Responsabilidad |
| --- | --- |
| `compartido/nucleo_risko/base_datos.py` | Helpers genericos de SQLite: conectar, listar, leer, escribir, crear tablas e indices |
| `compartido/nucleo_risko/rutas.py` | Rutas canonicas `ARCHIVO_BASE_DATOS_RISKO` y `ARCHIVO_BASE_DATOS_RISKO_PRUEBAS` |
| `proyectos/position_monitor/procesos/consolidacion.py` | API operativa de tablas Position Monitor y proceso de consolidacion |
| `aplicaciones/interfaz_risko/servicios/position_monitor.py` | Lectura filtrada por fecha, ejecucion de productos y conexion con la UI |
| `aplicaciones/interfaz_risko/interfaz_risko.py` | Selector de tablas DB, filtro por fecha y exportacion a CSV/Excel |

## Catalogo de tablas principales

| Tabla | Base | Descripcion |
| --- | --- | --- |
| `tbl_posicion_forward` | `risko.db` | Salida canonica de Forward por fecha |
| `tbl_posicion_novados` | `risko.db` | Salida canonica de Novados por fecha |
| `tbl_posicion_opciones` | `risko.db` | Salida canonica de Opciones por fecha |
| `tbl_posicion_renta_fija` | `risko.db` | Salida canonica de Titulos/Renta Fija por fecha |
| `tbl_posicion_swaps` | `risko.db` | Salida canonica de Swaps por fecha |
| `tbl_posicion_consolidada` | `risko.db` | Historico consolidado por producto y fecha, sin IFRS |
| `tbl_posicion_actual` | `risko.db` | Foto de la fecha seleccionada o ultima fecha disponible |
| `tbl_posicion_historico` | `risko.db` | Historico publicado de cierres operativos de mes |

El detalle operativo de Swaps se conserva como soporte en CSV/Excel:

- `datos/position_monitor/procesados/Tbl_Posicion_Swaps_Detalle.csv`
- `datos/position_monitor/procesados/Df_Insumo_Swaps_Depurado.xlsx`

Ese detalle no hace parte de `risko.db` ni de la consolidacion. Si el archivo de
soporte esta abierto, el modulo debe registrar el aviso y continuar con la tabla
oficial `tbl_posicion_swaps`.

`tbl_posicion_spot` no hace parte de `risko.db` por ahora. Spot sigue en
pruebas y debe apuntar a `risko_pruebas.db` hasta que se libere.

## Contrato canonico de posicion

Las tablas de producto que entran a consolidacion deben entregar, como minimo,
estas columnas:

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

Reglas practicas:

- `FECHA` se normaliza a `dd/mm/YYYY`.
- `POSICION` debe llegar numerica y en la moneda indicada por
  `MONEDA_POSICION`.
- `BANKING_CVA_DVA` puede traer `Banking`, `IFRS` o `CVA/DVA`; las tablas
  consolidadas publicables excluyen `IFRS`.
- La consolidacion no recalcula `TRM`, `POSICION_COP` ni `POSICION_USD`; esas
  columnas no son parte del contrato canonico vigente.

## Regla de escritura por fecha

Cuando se ejecuta un producto desde la interfaz:

1. Vector carga los insumos en `datos/insumos`.
2. El modulo del producto valida que esos insumos locales existan.
3. El modulo calcula la tabla canonica.
4. El servicio llama `guardar_tabla_producto_position_monitor(...)`.
5. SQLite reemplaza las filas de esa `FECHA` en la tabla del producto y conserva
   las demas fechas.
6. `consolidar_position_monitor(...)` actualiza `tbl_posicion_consolidada`,
   `tbl_posicion_actual` y `tbl_posicion_historico`.

Por eso ya no existe un modo de "acumular posiciones" desde la interfaz. Si se
ejecuta nuevamente la misma fecha, esa fecha se actualiza.

## API operativa

Funciones principales en `proyectos/position_monitor/procesos/consolidacion.py`:

```python
from proyectos.position_monitor.procesos.consolidacion import (
    listar_tablas_position_monitor,
    leer_tabla_position_monitor,
    guardar_tabla_producto_position_monitor,
    consolidar_position_monitor,
)

tablas = listar_tablas_position_monitor()
df = leer_tabla_position_monitor("tbl_posicion_actual")
guardar_tabla_producto_position_monitor("FORWARD", df_forward, "30/06/2026")
consolidar_position_monitor(fecha_corte="30/06/2026")
```

Para reemplazar por fecha se debe usar:

```python
guardar_tabla_producto_position_monitor(producto, tabla, fecha_corte)
```

Para reemplazar una tabla completa:

```python
from proyectos.position_monitor.procesos.consolidacion import guardar_tabla_position_monitor

guardar_tabla_position_monitor("mi_tabla", df, if_exists="replace")
```

## Tablas auxiliares y pruebas

Las nuevas copias de soporte por módulo se guardan en la base separada
`risko_auxiliar.db` mediante la función global:

```python
from compartido.nucleo_risko.tablas_auxiliares import guardar_tablas_auxiliares_modulo

guardar_tablas_auxiliares_modulo(
    "Forward",
    "03/08/2026",
    {"detalle": df_detalle, "posicion": df_posicion},
)
```

Consultar `base_datos_auxiliar.md` para el inventario completo y la convención
de nombres. Los aliases siguientes se conservan por compatibilidad para pruebas
manuales en `risko_pruebas.db`:

```python
from proyectos.position_monitor.procesos.consolidacion import (
    crear_tabla_auxiliar,
    guardar_tabla_auxiliar,
    leer_tabla_auxiliar,
)

crear_tabla_auxiliar("aux_param_trm", {"fecha": "TEXT", "trm": "REAL"})
guardar_tabla_auxiliar("aux_param_trm", df_trm, if_exists="replace")
df_trm = leer_tabla_auxiliar("aux_param_trm")
```

Si una prueba necesita leer la base principal, pasar `pruebas=False` en las
funciones que lo soportan. Si una prueba necesita una base diferente, pasar
`ruta_db=...`.

## Spot en pruebas

Spot no debe escribir en `risko.db` hasta nueva validacion. El boton, el flujo
`06_Spot` y la rama de servicio ya estan habilitados; para una prueba controlada
se debe activar `Usar base de pruebas` en la interfaz o pasar `pruebas=True`:

```python
from proyectos.position_monitor.procesos.spot import ejecutar_spot
from proyectos.position_monitor.procesos.consolidacion import guardar_tabla_producto_position_monitor

tabla = ejecutar_spot("03/08/2026", logger=print, pruebas=True)
guardar_tabla_producto_position_monitor("SPOT", tabla, "03/08/2026", pruebas=True, logger=print)
```

El historico acumulado, movimientos, alertas, ejecuciones y auditoria se guardan
en tablas auxiliares de la misma base. Consultar `posicion_spot_acumulada.md`.

## Consulta desde la interfaz

La interfaz consulta siempre SQLite:

- el selector `Tabla DB` lista tablas de `risko.db`;
- el switch `Pruebas` cambia a `risko_pruebas.db`;
- la fecha seleccionada filtra tablas que tengan columna `FECHA` o `CORTE`;
- la carga generica limita a 5000 filas para que la UI no se bloquee;
- las vistas `Actual` e `Historico` leen sin limite.

La exportacion a CSV o Excel se hace desde la vista filtrada que esta cargada en
la interfaz, no desde los archivos legacy.

## Migracion temporal desde CSV

El 2026-07-01 se cargo la informacion disponible de los CSV actuales a
`risko.db`. Ese proceso fue temporal para arrancar la base; hacia adelante la
operacion normal es ejecutar desde la interfaz para que SQLite quede actualizado.

Los CSV legacy pueden eliminarse cuando el equipo lo decida, siempre que la base
principal ya tenga la informacion requerida y no haya un proceso externo que aun
los consuma.

## Consultas utiles

Listar tablas:

```powershell
@'
from proyectos.position_monitor.procesos.consolidacion import listar_tablas_position_monitor
print(listar_tablas_position_monitor())
'@ | python -
```

Validar una fecha:

```powershell
@'
from proyectos.position_monitor.procesos.consolidacion import leer_tabla_position_monitor
df = leer_tabla_position_monitor("tbl_posicion_actual", where='"FECHA" = ?', params=("30/06/2026",))
print(df.shape)
'@ | python -
```

Revisar integridad SQLite:

```powershell
@'
import sqlite3
from compartido.nucleo_risko.rutas import ARCHIVO_BASE_DATOS_RISKO
with sqlite3.connect(ARCHIVO_BASE_DATOS_RISKO) as cx:
    print(cx.execute("PRAGMA integrity_check").fetchone()[0])
'@ | python -
```
