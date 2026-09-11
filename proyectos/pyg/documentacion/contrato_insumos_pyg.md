# Insumos para conciliar el nuevo PyG

El [anexo 13 de la guía técnica](GUIA_TECNICA_Y_EJEMPLOS_PYG.md#13-inventario-exacto-de-insumos-y-paquete-que-se-debe-entregar), incluido también en el [PDF](GUIA_TECNICA_Y_EJEMPLOS_PYG.pdf), amplía este contrato con diccionarios completos por hoja/producto, campos JSON, trazabilidad al XLSM, nodos de curvas y solicitud concreta de fuentes primarias.

El motor del book **OPCIONES** lee el
snapshot diario `Dataset Libro de Opciones AAAAMMDD.xlsx`. No usa los resultados
de la hoja `PYG` ni el Excel mensual para generar sus cifras.

El book **SWAPS** también está habilitado mediante snapshots JSON y el
[importador mensual](integracion_libro_swaps.md). Este documento describe
primero Opciones y luego las fuentes primarias aún necesarias para retirar
completamente la dependencia del Excel en los otros productos.

## Archivo diario del book Opciones

| Hoja | Campos utilizados |
| --- | --- |
| Resumen | Una fila: `TRM`, `Opccva`, `Forcva`, `Cajausd`. Si existe `FECHA`, `Fecha`, `FECHA_CORTE` o `Fecha_Corte`, debe coincidir con el archivo. |
| Opciones | `Trade Id`, `Posición en la opción`, `Tipo de opción`, `Fecha de Emisión`, `Fecha de Vencimiento`, `Fecha de Cumplimiento`, `Nominal`, `Precio de Ejercicio`, `Modalidad Cumplimiento`, `Moneda cumplimiento`, `Valor Total Prima`. |
| Opciones: prima | `Moneda Prima` o el alias de FF_V3 `Moneda de la  Prima`. Si no existe, se conserva la moneda de cumplimiento como convención heredada, que debe revisarse en la conciliación. `Tasa Prima` es opcional; una prima USD sin ella requiere fixing de emisión en `tfd`. |
| Forwards | `Emisión`, `Vencimiento`, `Cumplimiento`, `Operación`, `Nominal`, `T.Forward`, `Modalidad`, `Moneda_Cumplimiento`. |
| Caja | Una fila explícita para el corte, aun sin operaciones: `Fecha`, `Compras_Monto_USD`, `Compras_Tasa`, `Ventas_Monto_USD`, `Ventas_Tasa`. |
| Caja: complementos | `Costo_Fondos_COP` y `Ajustes_PyG_COP`, importes firmados. Su ausencia se informa como `NO_INCLUIDO`; no se inventa una tasa. |
| Tasas_COP | `Plazo Inferior`, `Plazo Superior`, `Tasas COP`. |
| Tasas_USD | `Plazo Inferior`, `Plazo Superior`, `Tasas USD`. |
| Superficie_Volatilidad | `Plazo Inferior`, `Plazo Superior`, `10 D PUT`, `25 D PUT`, `ATM`, `25 D CALL`, `10 D CALL`. |
| tfd | `FECHA`, `TRM1`. Fixing exacto de Opciones y conversiones históricas de primas/cumplimientos. |
| tff | `FECHA`, `TRM1`. La referencia Forward ubica la tasa del vencimiento en la fila del día calendario siguiente; el motor conserva esa convención. |
| PYG | Opcional: `Nombres` y una segunda columna numérica con controles diarios independientes. |

Las tasas de las curvas son continuas ACT/365 y se suministran en decimales;
las volatilidades también son decimales. El nominal es USD y el strike es
COP/USD. Los resultados de atribución están en COP. Se admiten `BUY`/`SELL`,
`CALL`/`PUT`, `DELIVERY`/`NON DELIVERY` en Opciones; `COMPRA`/`VENTA`, `DF`/`NDF`
en Forward; monedas `COP`/`USD`. Las primas se reciben firmadas.

`Opccva` y `Forcva` son **niveles de valoración IFRS**, no ajustes CVA ni PyG
diario. El ajuste PyG de crédito es la variación de `(IFRS − Banking)` entre
ambos cortes. `Cajausd` del snapshot anterior es el saldo inicial de Caja.

El snapshot debe conservar las operaciones y eventos necesarios para reconocer
primas y liquidaciones del mes. Si una operación desaparece de la cartera sin
su evento correspondiente, el residuo `NUEVOS_OTROS` no permite determinar por
sí solo si fue una baja, una liquidación o un ajuste. Esto debe contrastarse
con el libro operativo antes de usar la atribución en producción.

Los controles reconocidos son `PYG_Opc`, `Theta_Opc`, `Delta_Opc`, `Rho_Opc`,
`Vega_Opc`, `Nuevos_Opc`, `PYG_Forward`, `Theta_Forward`, `Delta_Forward`,
`Rho_Forward`, `Nuevos_Forward`, `Caja_Dia` y `Delta_Caja`. Se exige el total de
cada producto para declarar conciliación `OK`; las contribuciones adicionales
presentes también se comparan. Un total diario validado no equivale a una
validación independiente de todas las griegas ni del ajuste CVA/DVA.

## Cortes necesarios

Para una primera conciliación diaria hacen falta dos snapshots consecutivos y
el control operativo del segundo. Conviene incluir un corte con operaciones
nuevas, primas, vencimientos o liquidaciones. Para MTD se necesita además la
cadena completa desde el cierre del mes anterior según el calendario elegido.

Las cuentas por cumplir se conservan hasta liquidación. Las cuentas USD se
convierten a la TRM de cada corte; el flujo liquidado queda convertido a la
tasa de cumplimiento. Desde entonces la exposición de efectivo corresponde
a Caja. Estas convenciones corrigen diferencias encontradas en FF_V3 y
requieren aceptación funcional mediante conciliación.

## Insumos que faltan para completar otros motores

| Alcance pendiente | Información necesaria |
| --- | --- |
| Novados | Layout real de operaciones, precios de cámara por fecha, liquidación diaria, multiplicadores y monedas, eventos, y atribución/control esperado. FF_V3 no desarrolla sus griegas. |
| Swaps | Operaciones y flujos, curvas de proyección y descuento, fijaciones, convenciones por producto, eventos y PyG de referencia. FF_V3 no incluye su motor. |
| FX_ESTRAT | Archivos DORA/Summit y macros o fórmulas efectivamente usadas para saldos, eventos, valoración y conciliación por producto. |

Los motores SWAPS/Novados actuales procesan el contrato normalizado. Para
habilitar FX_ESTRAT hay que mapear sus fuentes específicas y conciliar los
resultados. Ningún motor produce importes de ejemplo cuando faltan insumos.
