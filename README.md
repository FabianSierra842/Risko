# Risko

Proyecto de consolidación de riesgo y publicación de dashboards HTML.
Este repositorio corresponde a **Risko**, separado del proyecto **Infocupos**.

| Componente | Ubicación |
| --- | --- |
| Interfaz de posición | `aplicaciones/interfaz_risko/interfaz_risko.py` |
| Position Monitor | `proyectos/position_monitor/` |
| Interfaz PyG | `aplicaciones/interfaz_risko/interfaz_pyg.py` |
| Motores, consolidación y dashboard PyG | `proyectos/pyg/` |
| Portal existente | `portal/` |
| Utilidades compartidas | `compartido/` |

## Ejecutar PyG

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe aplicaciones/interfaz_risko/interfaz_pyg.py
```

También puede abrir `INICIAR_PYG.bat` después de instalar las dependencias.

- Book **OPCIONES**: snapshots diarios del libro de Opciones; productos Opciones,
  Forward y Caja.
- Book **SWAPS**: botón **Importar libro SWAPS** para extraer snapshots del XLSM;
  productos Forward, Novados, Swaps y Caja. Luego ejecute el cierre Diario o MTD.
- **TODOS** consolida los dos books cuando hay insumos completos para el mismo
  corte. FX_ESTRAT conserva su identidad y requiere fuentes específicas.

El flujo genera contribuciones en COP, SQLite con historial de ejecuciones y
un HTML autocontenido. La publicación conserva el contrato del portal:

```text
Dashboards/PyG/dashboard.json
Dashboards/PyG/AAAA-MM-DD/pyg.html
Dashboards/PyG/AAAA-MM-DD/publicacion.json
```

La integración PyG no modifica el código del portal ni los cálculos de posición.

## Estado y validación

PyG es **preliminar**. Hay pruebas de los motores, fechas, publicación y
consolidación por libro. El libro SWAPS aportado permitió ejecutar un cierre
real y encontrar diferencias de filtros, fechas y fondeo que requieren
conciliación funcional. No se fuerza el resultado para coincidir con Excel.

Verificación de esta entrega: **36 pruebas PyG correctas y 2 omitidas** por
falta de datasets externos. La ventana PyG y el HTML se verificaron en Windows.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_pyg_flujo.py tests/test_pyg_swaps_libro.py tests/test_pyg_opciones.py tests/test_dashboard_pyg.py tests/test_referencia_pyg_mensual.py -q
```

Los tests antiguos de integración con Opciones requieren sus datasets externos.
Las pruebas del dashboard de posición requieren la herramienta interna
`Herramientas/dashy`, ausente en esta copia del proyecto. Vector también es una
herramienta externa; la importación local de SWAPS y el dashboard PyG funcionan
sin ella. Los archivos operativos de red se configuran en cada entorno.

## Documentación

- [Guía técnica y ejemplos numéricos de PyG](proyectos/pyg/documentacion/GUIA_TECNICA_Y_EJEMPLOS_PYG.md): fórmulas, escenarios por producto, consolidación, controles y ejercicios resueltos.
- [Inventario exacto de insumos por producto](proyectos/pyg/documentacion/GUIA_TECNICA_Y_EJEMPLOS_PYG.md#13-inventario-exacto-de-insumos-y-paquete-que-se-debe-entregar): archivos, hojas, columnas, curvas, nodos, fechas, fixings, pagos y fuentes pendientes; incluido en el PDF.
- [Descargar guía en PDF](proyectos/pyg/documentacion/GUIA_TECNICA_Y_EJEMPLOS_PYG.pdf) · [HTML para lectura local](proyectos/pyg/documentacion/GUIA_TECNICA_Y_EJEMPLOS_PYG.html) · [Scripts y resultados de los ejemplos](proyectos/pyg/documentacion/ejemplos/).
- [Operación PyG](proyectos/pyg/README.md).
- [Integración y diferencias del libro SWAPS](proyectos/pyg/documentacion/integracion_libro_swaps.md).
- [Contrato de insumos](proyectos/pyg/documentacion/contrato_insumos_pyg.md).
- [Análisis del flujo de Risko](Documentación/analisis_flujo_risko_previo_pyg.md).
- [Dashboard sintético de ejemplo](ejemplos/pyg/Dashboards/PyG/2026-09-01/pyg.html).

## Empaquetado

```powershell
.\.venv\Scripts\python.exe scripts/empaquetar_risko.py
```

El ZIP incluye un manifiesto de archivos y hashes y deja un SHA-256 junto al
archivo de entrega. Excluye entornos virtuales, datos generados, preferencias
personales y comentarios operativos del portal.

[Descargar entrega ZIP](distribucion/Risko_20260910.zip) ·
[SHA-256](distribucion/Risko_20260910.sha256)

Los datos generados, bases SQLite, copias de insumos y entornos virtuales quedan
fuera del control de versiones. El XLSM de referencia que ya existía en este
repositorio se conserva sin cambios; no se incorporan nuevas carteras ni
resultados operativos generados en esta entrega.
