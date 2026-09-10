# PyG Risko

Para estudiar el cálculo: [guía técnica con fórmulas y ejemplos por producto](documentacion/GUIA_TECNICA_Y_EJEMPLOS_PYG.md), también en [PDF](documentacion/GUIA_TECNICA_Y_EJEMPLOS_PYG.pdf) y [HTML](documentacion/GUIA_TECNICA_Y_EJEMPLOS_PYG.html). Los [scripts de ejemplo](documentacion/ejemplos/) permiten repetir los valores sin datos operativos.

Flujo independiente de Position Monitor: carga snapshots, calcula atribuciones
diarias, guarda resultados en SQLite, consolida por libro/producto/griega y
genera un único HTML compatible con el Portal Risko existente.

## Estado verificable

- Implementados: motores del book **OPCIONES** para **Opciones, Forward y Caja**,
  consolidación diaria/MTD, interfaz operativa, dashboard y publicación por fecha.
- Implementados: motores del book **SWAPS** para **Forward, Novados, Swaps y Caja**,
  e importación del libro mensual a snapshots JSON por fecha.
- Validación actual: carteras sintéticas y contraste con el libro SWAPS aportado.
  El corte real presenta diferencias de conciliación; no está liberado a producción.
- **FX_ESTRAT permanece separado y deshabilitado**: el resumen del libro SWAPS
  excluye explícitamente las operaciones de ese desk. Se retiraron los importes
  constantes y los resultados supuestos del diseño anterior.
- La referencia `Opciones_FF_V3.py` se estudia como fuente metodológica; no se
  importa ni ejecuta. El portal y los motores de posición no se modifican.

## Ejecución

```powershell
python -m pip install -r proyectos/pyg/requisitos.txt
python aplicaciones/interfaz_risko/interfaz_pyg.py
```

La configuración está en `configuracion/pyg.json`; `RISKO_PYG_CONFIG` permite
escoger otro archivo. Las rutas relativas se resuelven desde la raíz Risko.

Para ejecutar sin Vector con datasets ya disponibles:

```python
from aplicaciones.interfaz_risko.servicios.pyg import ejecutar_todo_pyg
resultado = ejecutar_todo_pyg(
    "02/08/2026", libro="OPCIONES", periodo="MTD", cargar_insumos=False
)
```

El ejemplo requiere los archivos reales correspondientes; no genera cifras de
demostración si faltan. La interfaz arranca vacía y permite elegir fecha, libro,
DIARIO/MTD, carga Vector, cierre completo o módulo individual.

Para el book SWAPS, use **Importar libro SWAPS**, seleccione el XLSM y ejecute
el cierre con Vector desmarcado. El original se conserva y se extraen los días
disponibles, incluido el ancla del mes anterior. Los motores no ejecutan macros
ni copian el total del resumen como su PyG calculado.

## Flujo y persistencia

```text
Vector / snapshots locales por fecha
  → copia estable en ejecuciones/pyg/<id>/insumos
  → motores por producto (cartera y mercado)
  → comprobación de suma de contribuciones y Banking + CVA/DVA = IFRS
  → datos/pyg/pyg.db
  → consolidación con comprobación de intervalos completos
  → datos/pyg/publicados/pyg.html
  → Dashboards/PyG/AAAA-MM-DD/pyg.html + publicacion.json
```

`tbl_pyg_calculos` conserva cada resultado diario por fecha/book/producto.
`tbl_pyg_diario` contiene las contribuciones. `tbl_pyg_ejecuciones` conserva
resultados, escenarios y hashes por corrida. Las escrituras de una corrida
comparten una transacción; un reproceso sustituye solo su alcance.

Contrato de filas:

```text
FECHA | FECHA_ANTERIOR | BOOK | PRODUCTO | COMPONENTE | VALOR_COP
VISTA | TIPO | ESTADO | PERIODO
```

Las filas son siempre diarias. `VISTA` es Banking o CVA/DVA; IFRS se deriva y no
se guarda como otra contribución sumable. MTD suma los intervalos desde el cierre
del mes anterior, con calendario `CALENDARIO` por defecto o `HABIL_CO` explícito.
Una fecha, producto o puente de snapshots ausente detiene la consolidación.
Todos los productos de un mismo libro y día deben usar la misma versión del
snapshot, incluso cuando se ejecutan individualmente.

## Cálculo y controles

Opciones revalora la cartera anterior cambiando tiempo, spot, tasas y volatilidad
en secuencia. Forward aplica tiempo, spot y tasas. Cada diferencia es una
atribución monetaria; Delta PyG ya incluye la respuesta no lineal al spot, por
lo que no se añade una Gamma aparte. `NUEVOS_OTROS` conserva el cambio residual
entre carteras, sin presentarlo como trading puro.

Caja atribuye saldo USD anterior por variación de TRM, trading de compras/ventas
y variación intradía del neto. Fondeo y ajustes solo entran si se suministran las
columnas `Costo_Fondos_COP` y `Ajustes_PyG_COP`; su ausencia queda visible.

Los niveles IFRS `Resumen.Opccva` y `Resumen.Forcva` se comparan con el valor de
mercado Banking de cada fecha. El ajuste es la variación de **IFRS − Banking**.
Los controles de la hoja `PYG` no alimentan los importes calculados. La referencia
mensual antigua queda disponible como material de comparación, fuera del motor.

La nueva implementación corrige convenciones de FF_V3: conversión CXC USD a
COP, persistencia de cuentas hasta cumplimiento, fixing Forward con suma de un
día calendario, descuento a settlement y primas por moneda. El alias de FF_V3
`Moneda de la  Prima` se reconoce sin confundirlo con la moneda de cumplimiento.
Las cuentas USD se convierten hasta liquidación; el flujo realizado queda a
la tasa de cumplimiento y el saldo posterior pertenece a Caja. Las sonrisas
de volatilidad inválidas o que no convergen producen error. Estas diferencias
requieren conciliación funcional con datos reales antes de liberar producción.

## Portal y publicación

No hay cambios en `portal/`. El servicio publica:

```text
Dashboards/PyG/dashboard.json
Dashboards/PyG/AAAA-MM-DD/pyg.html
Dashboards/PyG/AAAA-MM-DD/publicacion.json
```

El tablero contiene filtros de fecha, período, libro, producto, griega y vista,
matriz y gráficos por contribución y exportación CSV. Todos los totales se
derivan de las filas filtradas. Es autocontenido y no requiere Dashy instalado.

La publicación usa la base PyG para reconstruir el corte seleccionado y registra
hash, fecha efectiva, período, libros, fuentes y estado. Por defecto exige
conciliación `OK`; el estado sigue siendo `PRELIMINAR`, nunca se inventa una
validación oficial. `publicacion.biblioteca` permite probar en un destino local.

## Verificación

```powershell
python -m pytest tests/test_pyg_flujo.py tests/test_pyg_opciones.py tests/test_dashboard_pyg.py tests/test_referencia_pyg_mensual.py -q
```

Los casos de integración antiguos dependientes de datasets productivos están
marcados como opcionales. Sus cifras son referencias históricas, no una garantía
de que el motor corregido coincida sin revisar las diferencias metodológicas.

La batería adicional `tests/test_pyg_swaps_libro.py` verifica cámara, pagos,
recuponing, fondeo, importación y el cierre de los cuatro productos SWAPS.

Consulte [el manual operativo](documentacion/DETALLE_OPERATIVO_PYG.md) y
[las decisiones de integración](documentacion/integracion_pyg_v2.md).
El [contrato de insumos](documentacion/contrato_insumos_pyg.md) detalla hojas,
campos, convenciones y fuentes pendientes para la conciliación productiva.
La [integración del libro SWAPS](documentacion/integracion_libro_swaps.md)
explica su universo, fuentes, diferencias verificadas y límites actuales.
