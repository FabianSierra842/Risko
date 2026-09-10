# Ejemplos para estudiar el PyG

Estos archivos acompañan la [guía técnica](../GUIA_TECNICA_Y_EJEMPLOS_PYG.md), también disponible en [PDF](../GUIA_TECNICA_Y_EJEMPLOS_PYG.pdf) y [HTML](../GUIA_TECNICA_Y_EJEMPLOS_PYG.html).

Todos los datos son sintéticos. Los scripts usan funciones del motor `pyg-2.1`; no requieren las carteras reales, no publican tableros y no escriben en SQLite. Los resultados JSON conservan precisión completa para contrastar las tablas redondeadas de la guía.

Desde la raíz Risko, con las dependencias del proyecto instaladas:

```powershell
.\.venv\Scripts\python.exe proyectos/pyg/documentacion/ejemplos/ejemplos_opciones.py
.\.venv\Scripts\python.exe proyectos/pyg/documentacion/ejemplos/ejemplos_swaps.py
```

| Archivo | Contenido |
| --- | --- |
| [ejemplos_opciones.py](ejemplos_opciones.py) | Opciones vanilla con prima nueva, Forward y Caja del book OPCIONES; escenarios, crédito didáctico, conversión de CXC y prima USD. |
| [resultados_opciones.json](resultados_opciones.json) | Salida verificada de ese script. |
| [ejemplos_swaps.py](ejemplos_swaps.py) | Forward, Novados, Swap con cupón/recuponing y Caja con FTP. Incluye un IRS por flujos como modelo de estudio, expresamente fuera del motor Swap actual. |
| [resultados_swaps.json](resultados_swaps.json) | Salida verificada de ese script. |

Los ejemplos comprueban fórmulas y algunos resultados esperados. No sustituyen las pruebas del flujo completo ni la conciliación operativa. El script SWAPS crea snapshots temporales para el ejemplo de VP/pagos y los retira al finalizar.

La guía documenta los valores de crédito introducidos a mano, la dependencia externa de VP/factores Swap y las convenciones pendientes de aceptación funcional. Cambiar el motor puede cambiar los resultados: al actualizar la metodología también deben revisarse los ejemplos y regenerarse sus salidas.
