# Indice de documentacion tecnica de Position Monitor

## Objetivo

Este indice agrupa la documentacion detallada de los modulos activos de `Position Monitor`.

Los documentos de esta carpeta describen:

- el paso a paso real del codigo;
- las reglas de negocio implementadas hoy;
- la forma como se calcula `POSICION`;
- las homologaciones y parametrizaciones usadas;
- los archivos de entrada y salida;
- los puntos de control y alertas.

## Documentos disponibles

- `mapa_lb_lt_parametrico.md`
  Define la logica central de `param_libros.csv` y como se resuelven `BOOK`, `LB_LT`, `INSTRUMENTO` y `MONEDA_POSICION`.

- `posicion_novados.md`
  Explica la carga del archivo de Novados, la depuracion del insumo y la regla de posicion por vencimiento.

- `posicion_forward.md`
  Explica la logica de `Forward` para Banking, IFRS y CVA/DVA, incluyendo la formula exacta de posicion.

- `posicion_renta_fija.md`
  Explica el parser del reporte de titulos, los enriquecimientos contables y el armado de la tabla canonica.

- `posicion_swaps.md`
  Explica la lectura de los reportes de Swaps, la validacion de fecha interna, la regla de `POSICION_USD` y la publicacion por `BOOK`.

- `posicion_spot_acumulada.md`
  Explica la lectura de Reporte Caja sin DP, el mapeo de libros, el acumulado
  diario con `Decimal`, las posiciones iniciales, alertas, reprocesos y tablas
  de auditoria de Spot.

- `calculo_modulo_spot.md`
  Explica exclusivamente la formula Spot, el tratamiento de cada BOOK y la
  salida de las 13 posiciones para el corte 03/08/2026.

- `consolidacion_position_monitor.md`
  Explica como se normalizan las tablas por producto y como se actualizan `tbl_posicion_consolidada`, `tbl_posicion_actual` y `tbl_posicion_historico` en SQLite.

- `base_datos_risko.md`
  Documenta las bases `risko.db` y `risko_pruebas.db`, el catalogo de tablas, la API SQLite y la regla de escritura por fecha.

- `base_datos_auxiliar.md`
  Documenta `risko_auxiliar.db`, la función global de copias por módulo, el
  catálogo y el inventario de tablas de soporte.

- `control_vector_carga_insumos.md`
  Define los flujos de carga de insumos con Vector, las fuentes Summit, la regla especial de opciones y la ejecucion desde interfaz/CLI.

- `guia_flujo_integracion_posiciones.md`
  Guia transversal de integracion, interfaz, servicio y tablero.

- `mapa_produccion_y_ejemplos_calculo.md`
  Mapea los codigos productivos y no productivos, sus archivos fuente, ejemplos
  numericos de calculo y el recorrido final hasta SQLite.

## Orden sugerido de lectura

1. `mapa_lb_lt_parametrico.md`
2. `posicion_novados.md`
3. `posicion_forward.md`
4. `posicion_renta_fija.md`
5. `posicion_swaps.md`
6. `posicion_spot_acumulada.md`
7. `calculo_modulo_spot.md`
8. `base_datos_risko.md`
9. `base_datos_auxiliar.md`
10. `consolidacion_position_monitor.md`
11. `control_vector_carga_insumos.md`
12. `guia_flujo_integracion_posiciones.md`
13. `mapa_produccion_y_ejemplos_calculo.md`

## Nota importante

La prioridad de esta documentacion es describir el comportamiento real del codigo actual.

Si algun requerimiento historico o archivo Excel funcional dice algo diferente, debe prevalecer lo que hoy ejecutan los modulos Python, salvo que se haga un cambio funcional explicito.
