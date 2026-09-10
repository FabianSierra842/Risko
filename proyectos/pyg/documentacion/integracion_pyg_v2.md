# Decisiones y pendientes de la integración PyG

Implementación basada en la lectura de `Opciones_FF_V3`, sin ejecutarlo ni
modificar el motor de posición o el portal. La entrega debe evaluarse como una
implementación preliminar hasta conciliar un corte de producción.

| Área | Decisión |
| --- | --- |
| Fuente de cálculo | Opciones y derivados FX se revaloran desde carteras y mercado. Swap calcula el total desde VP/pagos por operación y recibe factores diarios del Informe Libro de Swaps; su atribución todavía depende de esa fuente externa. |
| Unidades | Cada contribución está en COP. La posición delta USD es una magnitud diferente. |
| Atribución | Revaloración secuencial; no suma Gamma de nuevo al efecto completo del spot. |
| Nuevos/otros | Diferencia de cartera actual frente a cartera anterior revalorada; requiere eventos para separar trading, bajas y ajustes. |
| Crédito | Diferencia entre ajustes IFRS-Banking de ambos cortes, no la variación IFRS sumada nuevamente a Banking. |
| CXC | Se conservan hasta cumplimiento y se convierten a COP. El flujo realizado USD/delivery queda convertido a la tasa de cumplimiento, sin seguir revalorándose en el derivado; el saldo posterior pertenece a Caja. |
| Primas | Se usan firmadas; primas USD requieren tasa explícita o fixing de emisión. Se reconoce la columna `Moneda de la  Prima` de FF_V3. |
| Volatilidad | Spline natural con colas fijas 10/90 delta; una superficie inválida o sin convergencia detiene la valoración. |
| Caja | No se inventan tasas de fondeo. Columnas de fondeo/ajustes son entradas explícitas con control visible. |
| Histórico | Diarios por fecha/book/producto; MTD exige intervalos completos. Los hashes deben coincidir entre todos los productos del libro y entre días que comparten snapshot. |
| Publicación | Un único dashboard PyG con carpeta por fecha y manifiestos compatibles; portal sin cambios. |

Pendientes que requieren datos o definición funcional:

- Conciliar con snapshots y reportes reales todas las correcciones de convenciones
  respecto de FF_V3, en especial fixing, primas, cumplimiento y cambio de mes.
- Confirmar el calendario operativo esperado (diario calendario o hábil Colombia).
- Incorporar fuentes de fondeo y ajustes que FF_V3 deja en cero.
- Para **Novados**, conciliar el motor de cámara con operaciones activas reales;
  FF_V3 no implementaba su atribución.
- Para **Swaps**, completar ingestión primaria de pagos y valoración por
  curvas/flujos. El motor ya calcula desde VP y pagos por operación y consume
  las griegas del Informe Libro de Swaps.
- Para **FX_ESTRAT**, mapear los archivos DORA/Summit al cálculo validado. La
  documentación local describe macros y fórmulas generales, pero faltan sus
  fuentes completas y pruebas de conciliación. No es correcto trasladar las
  convenciones del book Opciones sin esa validación.

Los módulos de Novados y Swaps están integrados para el book **SWAPS** mediante
el [nuevo importador y motores](integracion_libro_swaps.md). Conservan errores
explícitos ante insumos faltantes, sin usar las constantes del diseño anterior.

Los documentos y evidencias anteriores de esta carpeta se conservan como
antecedentes. Sus afirmaciones de validación corresponden al diseño anterior y
no certifican la versión 2.
