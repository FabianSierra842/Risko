# Integración del libro SWAPS

Se contrastó el análisis aportado con las fórmulas y valores guardados de
`PYG SWAPS_MES.xlsm`, corte de portada 08/09/2026. El archivo original no se
modifica y no se ejecutan sus macros.

## Flujo implementado

```text
PYG SWAPS_MES.xlsm
  → importador de hojas, fechas, operaciones, mercado, VP y pagos
  → Dataset SWAPS AAAAMMDD.json (ancla y días disponibles)
  → Forward / Novados / Swaps / Caja
  → contribuciones diarias y evidencia por operación en SQLite
  → suma MTD con intervalos completos
  → interfaz PyG y un único HTML por fecha
```

La interfaz incorpora **Importar libro SWAPS**. Al terminar selecciona ese
book y la fecha del archivo; la carga Vector queda desmarcada. **Ejecutar
cierre PyG** calcula los productos con los snapshots importados. También se
puede suministrar el mismo contrato JSON desde un proceso de fuentes primarias.

## Universo y métodos

| Producto | Método y fuentes |
| --- | --- |
| Forward | Operaciones de `Forwards!A:N` clasificadas `SWAPS`; curvas efectivas COP, USD e implícita de `Tasas` y spot por fecha. Revaloración secuencial tiempo, spot, COP, USD, base/spread, nuevos/otros. Cuentas y liquidaciones hasta cumplimiento. |
| Novados | Clasificación `SWAPSNOVADO` de la misma fuente; valoración de cámara sin descuento: nominal firmado × (precio forward de cámara − strike). Curvas COP/USD y atribución propia. No se reutiliza el valor descontado del Forward. |
| Swaps | Maestro por Trade ID, VP Banking e IFRS y Payments del bloque diario. PyG = VP actual − VP previo + pago. Factores diarios de `GRIEGAS SWAP!L:T`, procedentes del Informe Libro de Swaps. Épsilon = total por operación − suma de factores. |
| Caja | Movimientos USD/COP, saldo anterior, TRM y FTP COP/USD de `CAJA SWAP`. Trading, delta intra/inter y fondeo; conciliación de saldo inicial + compras − ventas. |

**SWAPS y FX_ESTRAT son universos diferentes en este archivo.** El resumen
SWAPS excluye los desks `ARBITR_DER` y `FX_ESTRAT` del maestro Swap. Python
aplica el filtro a todas las operaciones. El book `FX_ESTRAT` continúa sin
habilitar porque faltan sus archivos específicos; no se le asignan cifras de
SWAPS cambiando una etiqueta.

Para Forward el ajuste de crédito proviene de la diferencia acumulada entre
los resultados IFRS y Banking del reporte fuente en `PORTAFOLIO`. Su cambio
diario se incorpora aparte del Banking recalculado. Para Novados el libro
define IFRS igual a Banking. En Swaps se calcula el cambio de `(VP IFRS − VP
Banking)` por operación y se añade el cambio del nivel de recuponing.

La atribución Swap aún depende de los factores del Informe Libro: no es una
revaloración independiente de todos los flujos Swap. El total por operación
sí se calcula separadamente a partir de VP y pagos. Este límite queda visible
en los controles y en la evidencia del resultado.

## Diferencias verificadas

1. La portada tiene fecha 08/09/2026; las hojas Forward y Novados guardan
   cálculos con fecha 01/09/2026. El motor utiliza el mercado del día solicitado,
   no presenta sus celdas calculadas como si pertenecieran al día 8.
2. El filtro agregado de `FX_ESTRAT` en la hoja SWAP termina en la fila 1033,
   mientras la suma total alcanza la fila 1921. Una operación posterior al
   límite queda incluida indebidamente en el resumen SWAPS. Aplicar el filtro
   completo explica la diferencia de **22.451.760,10 COP** del día 8 entre el
   cálculo nuevo de Swap y el total del resumen. No se replica ese límite fijo.
3. La fórmula de fondeo COP en `CAJA SWAP!AO` ubica `−1` fuera del factor de
   interés. Se usa `−saldoUSD × TRM × ((1+tasaEA)^(1/365) − 1)`. La diferencia
   frente a Excel es **1 COP por día**, **8 COP** en el acumulado revisado.
4. El Banking Forward nativo acumulado al día 8 es **1.741.170.600,83 COP**.
   El total del reporte es **1.756.110.106,54 COP**. La diferencia de
   **14.939.505,71 COP** coincide con el épsilon acumulado que ya muestra el
   libro. No se añade ese control al motor para forzar una coincidencia.
5. No hay operaciones clasificadas `SWAPSNOVADO` en el universo importado.
   El cero de ese corte es consecuencia de una cartera vacía. Las pruebas
   sintéticas verifican un Novado activo con PyG distinto de cero.

La conciliación real sigue en **DIFERENCIA**. El dashboard local sirve para
revisión; el servicio de publicación productiva exige resolver la conciliación.
Un residual Swap superior al 7% también impide declarar el producto conciliado,
aunque el total coincida.

## Dependencias que conserva esta etapa

- El libro mensual proporciona el maestro disponible al corte. La
  reconstrucción retrospectiva requiere revisar bajas y eventos históricos.
- Las celdas vacías de Payments se interpretan como cero según la fórmula del
  Excel, y se informa cuántas hubo. Hace falta confirmar su fuente primaria
  para retirar la dependencia de la hoja.
- Los controles cacheados y las referencias a otro archivo no sustituyen
  una conciliación productiva independiente.
- Recuponing mantiene el nivel de ajuste de la fuente; su ingestión completa
  y la discrepancia de posición IFRS entre macros siguen pendientes.
- El flujo importado es calendario diario. Swap y fondeo requieren los días
  intermedios; no se omiten al sumar MTD.
- El importador no incorpora Títulos ni Arbitraje, fuera del alcance de estos
  cuatro motores. Tampoco ejecuta las macros de ingestión DORA/Summit.

Las pruebas cubren cálculos monetarios, signo, liquidación, cámara, fondeo,
pagos ausentes, bajas sin evento, CVA/recuponing, referencias separadas,
persistencia, publicación y conservación del XLSM original.
