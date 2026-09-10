# Spot 2 — prueba de cierre y ruta de promoción

## Separación operativa

Spot 2 procesa exclusivamente `SPOT_CLIENTE` con el reporte
`Cierre_ReporteCaja_ddmmaa_*.xls`. No consume `USR_Caja_Intradia` y su prueba no
participa en la consolidación ni en la publicación de Position Monitor.

La interfaz expone la acción **Probar Spot 2 · cierre** dentro de la
configuración de Spot. Vector copia el insumo a
`datos/position_monitor/pruebas/spot_2/cierre/insumos` y el cálculo usa la base
aislada `risko_spot_2_cierre_pruebas.db`.

El mapeo permanece en `param_spot_2.csv`, separado de `param_libros.csv`. Esto
evita que el motor Spot principal y Spot 2 agreguen dos veces `SPOT_CLIENTE`.
La salida canónica homologa `BOOK=Spot_Cliente` e `INSTRUMENTO=SPOT`.

## Configuración de promoción

`risko.json` contiene el bloque:

```json
"spot_2": {
  "modo": "PRUEBAS_CIERRE",
  "incluir_en_cierre": false,
  "incluir_en_intradia": false,
  "book_exclusivo": "SPOT_CLIENTE",
  "requiere_posicion_inicial_validada": true,
  "posicion_inicial_validada": false
}
```

Con los interruptores en `false`, Spot 2 no puede modificar la salida oficial.
El servicio de cierre ya tiene preparado el anexo de su tabla canónica, pero
solo se activa cuando `incluir_en_cierre=true`. Además, bloquea la promoción si
`posicion_inicial_validada` sigue en `false`.

## Requisitos antes de incluirlo

1. Registrar y conciliar la posición inicial oficial de `SPOT_CLIENTE` para la
   fecha anterior al primer cierre que se vaya a procesar.
2. Reprocesar varios cierres consecutivos y validar compras, ventas, movimiento
   neto, carry-forward y reprocesos históricos.
3. Confirmar que `SPOT_CLIENTE` siga fuera de las filas Spot de
   `param_libros.csv`; mientras Spot 2 sea el dueño de ese book, incluirlo allí
   produciría doble conteo.
4. Cambiar `posicion_inicial_validada` a `true`.
5. Cambiar `incluir_en_cierre` a `true`. A partir de ese momento, la fila
   canónica de Spot 2 se anexará al producto Spot antes de guardar y consolidar.

La integración intradía queda fuera de alcance. `incluir_en_intradia` permanece
en `false` y no está conectado al preliminar actual.

## Prueba ejecutada

Con `Cierre_ReporteCaja_140826_000.xls`, Spot 2 procesó 668 movimientos de
`SPOT_CLIENTE`:

| Concepto | USD |
|---|---:|
| Compras | 119.453.137,61 |
| Ventas | 109.372.443,26 |
| Movimiento neto | 10.080.694,35 |
| Posición experimental 14/08/2026 | 10.080.694,35 |

El 17/08/2026 no tuvo archivo de cierre. El proceso no buscó un reporte
intradía: conservó la posición de **USD 10.080.694,35** mediante la cadena de
carry-forward 14→15→16→17 de agosto, siempre con compras y ventas en cero.

El 14/08 mantiene la alerta `MISSING_PREVIOUS_POSITION` porque todavía no se ha
registrado el saldo oficial anterior. El cálculo parte explícitamente de cero:
USD 10.080.694,35 corresponde solo a compras menos ventas del 14/08, no a un
acumulado oficial. El carry del 17/08 usa ese resultado experimental y quedó en
estado `OK`.
