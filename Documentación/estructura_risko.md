# Estructura de Risko

## Objetivo

Ordenar Risko para que la interfaz sea la cara del sistema, `position_monitor` sea un proyecto trazable y las funciones reutilizables queden separadas del codigo especifico de cada producto.

La vista integrada de componentes, datos, publicación y ejecución local está en
[Arquitectura de RISKO y Portal RISKO](ARQUITECTURA_RISKO_PORTAL.md).

## Estructura actual

```text
Proyecto Risko/
  aplicaciones/
    interfaz_risko/
      interfaz_risko.py
      servicios/
        position_monitor.py

  compartido/
    nucleo_risko/
      archivos.py
      base_datos.py
      fechas.py
      rutas.py

  proyectos/
    position_monitor/
      configuracion/
      procesos/
        novados.py
        forward.py
        renta_fija.py
        consolidacion.py
      tableros/
      documentacion/
      legado/

  datos/
    insumos/
    base de datos/
      risko.db
      risko_pruebas.db
    position_monitor/
      procesados/
      publicados/

  Herramientas/
    dashy/

  ejecuciones/
    position_monitor/
```

## Criterio de organizacion

- `aplicaciones/`: interfaces y puntos de entrada.
- `compartido/`: utilidades comunes a varios proyectos.
- `proyectos/`: logica operativa por iniciativa.
- `datos/insumos/`: archivos fuente compartidos.
- `datos/base de datos/`: bases SQLite oficiales y de pruebas.
- `datos/position_monitor/procesados/`: salidas intermedias y tablas por producto.
- `datos/position_monitor/publicados/`: exportaciones de compatibilidad y HTML.
- `Herramientas/`: herramientas locales, incluido `dashy`.
- `ejecuciones/`: logs y evidencias de corrida.

## Position Monitor

### Modulos operativos

- `proyectos/position_monitor/procesos/novados.py`
  - carga el insumo de Novados
  - depura
  - genera su tabla canonica

- `proyectos/position_monitor/procesos/forward.py`
  - carga Banking e IFRS
  - depura
  - genera Banking, IFRS, CVA/DVA y la tabla canonica de Forward

- `proyectos/position_monitor/procesos/renta_fija.py`
  - carga el reporte de titulos
  - enriquece y arma las salidas operativas
  - genera la tabla canonica de renta fija para el dashboard

- `proyectos/position_monitor/procesos/consolidacion.py`
  - toma las tablas canonicas de los productos
  - actualiza `datos/base de datos/risko.db`
  - actualiza `tbl_posicion_consolidada`
  - actualiza `tbl_posicion_actual`
  - actualiza `tbl_posicion_historico`
  - intenta exportar CSV de compatibilidad

### Nucleo compartido usado por Position Monitor

- `compartido/nucleo_risko/archivos.py`
  - lectura de archivos
  - reemplazo por fecha
  - log comun

- `compartido/nucleo_risko/base_datos.py`
  - conexion SQLite
  - lectura y escritura de tablas
  - reemplazo de datos por fecha
  - creacion de tablas auxiliares e indices

- `compartido/nucleo_risko/fechas.py`
  - calculo de fecha operativa
  - dias habiles

- `compartido/nucleo_risko/rutas.py`
  - rutas canonicas del proyecto

## Datos

### Insumos

Los insumos ya no viven dentro del proyecto.

Ahora la ubicacion comun es:

- `datos/insumos/`

Aqui caen los archivos cargados por Vector o cargados manualmente para cualquier proyecto futuro.

### Procesados de Position Monitor

Las salidas intermedias quedan en:

- `datos/position_monitor/procesados/`

Estas salidas ya no son la fuente maestra. Se conservan como soportes
operativos, migracion o compatibilidad con procesos externos.

Archivos clave:

- `Tbl_Novados_Posicion.csv`
- `Tbl_Posicion_Forward.csv`
- `Tbl_Posicion_Renta_Fija.csv`
- `tbl_posicion_consolidada.csv`

Adicionalmente se conservan archivos de detalle y trazabilidad como:

- `df_Insumo.xlsx`
- `df_Insumo_FWD.xlsx`
- `df_Insumo_FWD_IFRS.xlsx`
- `Tbl_Posicion_FWD.xlsx`
- `Tbl_Posicion_FWD_IFRS.xlsx`
- `df_Fwd_CVADVA.xlsx`
- `Tbl_Posicionrf.xlsx`
- `Posicionrf.xlsx`

### Base de datos Risko

La fuente oficial para la interfaz y la consolidacion es:

- `datos/base de datos/risko.db`

La base de pruebas y auxiliares es:

- `datos/base de datos/risko_pruebas.db`

Tablas principales:

- `tbl_posicion_forward`
- `tbl_posicion_novados`
- `tbl_posicion_opciones`
- `tbl_posicion_renta_fija`
- `tbl_posicion_swaps`
- `tbl_posicion_consolidada`
- `tbl_posicion_actual`
- `tbl_posicion_historico`

### Publicados de Position Monitor

Las copias publicadas de compatibilidad son:

- `datos/position_monitor/publicados/tbl_posicion_actual.csv`
- `datos/position_monitor/publicados/tbl_posicion_historico.csv`

El HTML final queda en:

- `datos/position_monitor/publicados/panel_position_monitor.html`

## Flujo operativo

### Flujo por producto

1. se toma el archivo fuente desde `datos/insumos/`
2. se genera una tabla canonica
3. se actualiza la tabla del producto en `risko.db`
4. se actualizan `tbl_posicion_consolidada`, `tbl_posicion_actual` e `historico`
5. la interfaz consulta SQLite y puede exportar a CSV/Excel

### Flujo del tablero

`Generar tablero` hace dos cosas:

1. consolida la fecha seleccionada desde SQLite
2. arma el HTML con `Herramientas/dashy`

## Dashy

`dashy` se toma desde:

- `Herramientas/dashy`

La interfaz permite escoger:

- `Herramientas`
- o `Herramientas/dashy`

## Interfaz Risko

La interfaz vive en:

- `aplicaciones/interfaz_risko/interfaz_risko.py`

El servicio que orquesta Position Monitor esta en:

- `aplicaciones/interfaz_risko/servicios/position_monitor.py`

Desde ahi se ejecutan:

1. `Novados`
2. `Forward`
3. `Opciones`
4. `Renta fija`
5. `Swaps`
6. `Generar tablero`

## Como probar

### 1. Abrir la interfaz

```powershell
python aplicaciones\interfaz_risko\interfaz_risko.py
```

### 2. Probar compilacion

```powershell
python -m compileall aplicaciones compartido proyectos
```

### 3. Consolidar desde SQLite

```powershell
@'
from proyectos.position_monitor.procesos.consolidacion import consolidar_position_monitor
print(consolidar_position_monitor(fecha_corte="22/06/2026"))
'@ | python -
```

### 4. Generar tablero desde consola

```powershell
@'
from aplicaciones.interfaz_risko.servicios.position_monitor import generar_tablero
print(generar_tablero(ruta_dashy=r"Herramientas\dashy"))
'@ | python -
```

### 5. Probar un producto puntual

Ejemplo con Forward:

```powershell
@'
from proyectos.position_monitor.procesos.forward import ejecutar_forward
resultado = ejecutar_forward("22-05-2026", confirmar_reemplazo=False)
print(resultado.head())
'@ | python -
```

## Como anexar nuevas posiciones

Cuando entre un nuevo producto:

1. crear un modulo nuevo en `proyectos/position_monitor/procesos/`
2. agregar su flujo de carga en Vector
3. hacer que el modulo valide insumos locales en `datos/insumos/`
4. retornar la tabla canonica de posicion
5. conectarlo en el servicio de la interfaz
6. mapear su tabla en `consolidacion.py`
7. validar que aparezca en `tbl_posicion_actual` dentro de `risko.db`
8. despues revisar el tablero y la exportacion CSV/Excel

## Control de versiones

La base de exclusiones esta en:

- `.gitignore`

Ese archivo deja por fuera:

- caches
- logs
- insumos
- procesados
- publicados temporales
- bases SQLite (`datos/base de datos/*.db` y archivos auxiliares)

## Carpetas antiguas

- `Desarrollo/`
- `Position Monitor/`

Se dejaron solo como referencia de migracion y cada una conserva un `leeme_migracion.md`.
