# Base de datos auxiliar de Risko

## Objetivo

`risko_auxiliar.db` centraliza las tablas de detalle, control e intermedias que
cada módulo ya calcula. Esta base es independiente de `risko.db` y
`risko_pruebas.db`.

La adición no redirige ni elimina ninguna salida existente. Los Excel, CSV y
tablas oficiales continúan escribiéndose exactamente en sus destinos actuales;
al final de cada cálculo se guarda una copia adicional en la base auxiliar.

## Ruta

```text
datos/base de datos/risko_auxiliar.db
```

La constante central es
`ARCHIVO_BASE_DATOS_RISKO_AUXILIAR` en
`compartido/nucleo_risko/rutas.py`.

## Función global

La función compartida está en
`compartido/nucleo_risko/tablas_auxiliares.py`:

```python
from compartido.nucleo_risko.tablas_auxiliares import (
    guardar_tablas_auxiliares_modulo,
)

guardar_tablas_auxiliares_modulo(
    "Mi_Modulo",
    fecha_trabajo,
    {
        "detalle": df_detalle,
        "control": df_control,
        "posicion": df_posicion,
    },
    logger=logger,
)
```

La función recibe el nombre del módulo, el corte y un diccionario de tablas. El
nombre físico queda normalizado como `aux_<modulo>_<nombre_logico>`.

Cada fila recibe tres metadatos:

| Columna | Uso |
| --- | --- |
| `AUX_FECHA_CORTE` | Corte al que pertenece la foto |
| `AUX_MODULO` | Módulo que produjo el DataFrame |
| `AUX_CARGADO_EN` | Fecha y hora de la copia auxiliar |

Un reproceso sustituye únicamente las filas con el mismo
`AUX_FECHA_CORTE`; los demás cortes se conservan. La tabla
`tbl_catalogo_auxiliar` permite descubrir el nombre lógico, la tabla física,
el último corte, el número de filas y el estado de cada carga.

El catálogo incluye desde la inicialización el inventario completo. Una entrada
queda en `PENDIENTE_EJECUCION` hasta que el módulo produzca su primera copia; la
tabla física se crea en esa ejecución para no inventar columnas ni cargar
archivos antiguos con un corte incorrecto.

## Inventario agregado

| Módulo | Tablas auxiliares generadas al ejecutar |
| --- | --- |
| Forward | insumos Banking/IFRS depurados; posiciones Banking, IFRS, CVA/DVA y consolidada |
| Novados | insumo depurado y posición |
| Opciones | detalle calculado, posición por book, control, curvas USD/COP, superficie de volatilidad y posición |
| Renta Fija | reporte enriquecido, posición operativa, vistas por libro/agencia/estructura/moneda y posición canónica |
| Swaps | Banking/IFRS depurados, posiciones Banking/IFRS/CVA-DVA, detalle y publicación |
| Spot | posición canónica/acumulada, parámetros por book, compras y ventas, movimientos, alertas, ejecuciones y auditoría |
| Cubrebonos, NDFTES y PP | tabla vacía `posicion_pendiente` hasta implementar su regla de negocio |

## Ubicación de los bloques nuevos

En cada archivo el punto está marcado con el comentario `ADICION AUXILIAR`:

- `proyectos/position_monitor/procesos/forward.py`
- `proyectos/position_monitor/procesos/novados.py`
- `proyectos/position_monitor/procesos/opciones.py`
- `proyectos/position_monitor/procesos/renta_fija.py`
- `proyectos/position_monitor/procesos/swaps.py`
- `proyectos/position_monitor/procesos/spot.py`
- `proyectos/position_monitor/procesos/posiciones_pendientes.py`

## Aislamiento de errores

La base auxiliar es soporte, no una dependencia del cálculo. Si SQLite está
bloqueado o una tabla no puede copiarse, la función registra una advertencia y
el módulo conserva sus salidas originales. El catálogo marca `ERROR` cuando fue
posible registrar el incidente.
