# PyG Risko: guía técnica y cuaderno de estudio

**Edición:** 10 de septiembre de 2026. **Motor documentado:** `pyg-2.1`.
**Código de referencia:** [commit af4f625](https://github.com/FabianSierra842/Risko/commit/af4f625c380494628b9f6163e849c46a75669fce).

Esta guía explica cómo se construye el PyG que existe hoy en Risko, qué significa cada componente, cómo se calcula cada producto y cómo comprobar sus resultados. Los ejemplos de cálculo son **sintéticos y educativos**. Las diferencias del libro real se presentan por separado, con su corte y alcance.

El flujo está implementado y sigue en estado **PRELIMINAR**. Una prueba sintética correcta o una conciliación `OK` del programa no constituye una aprobación metodológica o contable. En particular, el producto Swap todavía depende de VP, pagos y factores externos; no cuenta con un valorador nativo completo por flujos.

La documentación se entrega como archivo independiente del ZIP anterior. No cambia los motores ni el portal. Las versiones Markdown, HTML y PDF contienen la misma guía; los scripts adjuntos permiten repetir los ejemplos con el código documentado.

## Índice

- [1. Cómo estudiar esta guía](#1-cómo-estudiar-esta-guía)
- [2. Qué está implementado](#2-qué-está-implementado)
- [3. Identidad del resultado y explicación por factores](#3-identidad-del-resultado-y-explicación-por-factores)
- [4. Insumos y convenciones que hay que comprobar](#4-insumos-y-convenciones-que-hay-que-comprobar)
- [5. Book OPCIONES: productos y ejemplos](#5-book-opciones-productos-y-ejemplos)
- [6. Book SWAPS: productos y ejemplos](#6-book-swaps-productos-y-ejemplos)
- [7. Consolidación: de productos a book y de días a MTD](#7-consolidación-de-productos-a-book-y-de-días-a-mtd)
- [8. Conciliación, diagnóstico y publicación](#8-conciliación-diagnóstico-y-publicación)
- [9. Estado real de la implementación y trabajo pendiente](#9-estado-real-de-la-implementación-y-trabajo-pendiente)
- [10. Mapa técnico para leer el proyecto](#10-mapa-técnico-para-leer-el-proyecto)
- [11. Ejercicios para comprobar la comprensión](#11-ejercicios-para-comprobar-la-comprensión)
- [12. Fuentes y alcance de las referencias](#12-fuentes-y-alcance-de-las-referencias)
- [13. Inventario exacto de insumos y paquete que se debe entregar](#13-inventario-exacto-de-insumos-y-paquete-que-se-debe-entregar)

## 1. Cómo estudiar esta guía

La lectura recomendada sigue este orden:

1. Entender la diferencia entre posición, valoración y PyG, y entre Banking e IFRS.
2. Seguir el recorrido de un cierre desde los insumos hasta el HTML publicado.
3. Resolver primero Caja y Forward: permiten ver signos, monedas y efectos sin la complejidad de la volatilidad.
4. Estudiar Opciones, Novados y Swaps, conservando las convenciones propias de cada book.
5. Revisar consolidación, controles y limitaciones; después ejecutar los ejemplos y contestar los ejercicios finales.

### 1.1 Tres preguntas distintas

| Pregunta | Magnitud | Ejemplo |
| --- | --- | --- |
| ¿Cuánto vale el contrato hoy? | Valor presente, VP o MTM, en COP | Un derivado vale 1.200.000 COP. |
| ¿A qué riesgo está expuesto? | Posición o sensibilidad, con unidad propia | Delta de 50.000 USD. |
| ¿Cuánto ganó o perdió durante el intervalo? | PyG, en COP | El valor cambió 200.000 COP y se recibieron 30.000 COP: PyG 230.000 COP. |

La posición que Risko ya consolida no basta para reconstruir todo el PyG. También hacen falta el mercado de ambos cortes, las operaciones de ambos cortes y los eventos: primas, vencimientos, pagos, altas, bajas y ajustes. El resultado de PyG tiene que explicar una **variación monetaria**, no simplemente mostrar las sensibilidades actuales.

### 1.2 Vocabulario y signos

| Símbolo o término | Significado en esta guía |
| --- | --- |
| `t0`, `t1` | Fecha anterior y fecha actual del intervalo. |
| `S`, TRM, spot | Precio de un USD expresado en COP/USD. Algunas fuentes distinguen TRM y spot de compra/venta. |
| `N` | Nominal positivo en USD de opciones y derivados FX. El nominal de un swap depende de sus patas. |
| `K` | Strike o tasa pactada en COP/USD para derivados FX. |
| `q` | Signo: +1 para compra/BUY, −1 para venta/SELL. CALL/PUT es otra característica, no el signo de la posición. |
| `r_c`, `r_u` | Tasas COP y USD. OPCIONES recibe tasas continuas; SWAPS recibe tasas efectivas. |
| `τ` | Tiempo en años. En los ejemplos FX se usa días reales/365. |
| `σ` | Volatilidad anual en decimal: 12% se ingresa como `0.12`. |
| `Φ(x)` | Probabilidad acumulada de la distribución normal estándar, utilizada en opciones. |
| CXC | Cuenta pendiente de cumplimiento, firmada: un valor negativo representa una obligación. |
| Banking | Vista del resultado económico de mercado definida por el motor y sus eventos. |
| IFRS | Vista ajustada según los niveles y ajustes IFRS recibidos de la fuente; no es una certificación de cumplimiento contable. |
| CVA/DVA | Nombre de la columna de ajuste que conecta ambas vistas. El programa recibe o deriva ajustes; no implementa un modelo completo de exposición, probabilidad de incumplimiento y recuperación. |
| MTD | Acumulado desde el cierre del mes anterior hasta el corte solicitado. |
| Snapshot | Copia de cartera, mercado y controles identificada por fecha. |
| Revaloración | Volver a calcular el valor cambiando uno o varios insumos. |

Un ingreso o ganancia se registra positivo; un egreso o pérdida, negativo. Una prima ya firmada no debe multiplicarse otra vez por el signo BUY/SELL. Los importes de atribución del dashboard se expresan siempre en COP.

En el texto se usa la notación española `1.234,56`; los scripts Python y JSON usan `1234.56`. Los cálculos se hacen sin redondear cada paso y las tablas muestran normalmente dos decimales. Puede haber diferencias de un centavo al sumar cifras ya redondeadas.

## 2. Qué está implementado

Un **book** identifica un universo de negocio. Un **producto** identifica el instrumento o actividad dentro del book. El book SWAPS contiene cuatro productos, uno de los cuales también se llama SWAPS.

| Book | Producto | Cómo se obtiene Banking | Cómo se explica | Estado de la fuente |
| --- | --- | --- | --- | --- |
| OPCIONES | OPCIONES | Valorador de opciones europeas vanilla, CXC, liquidaciones y primas | Tiempo, spot, tasas conjuntas, volatilidad, nuevos/otros | Snapshots XLSX diarios; pendiente de conciliación productiva del motor corregido. |
| OPCIONES | FORWARD | Valor FX descontado con curvas continuas, cuentas y liquidaciones | Tiempo, spot, tasas conjuntas, nuevos/otros | Mismo snapshot; convenciones de `tff` propias de esta fuente. |
| OPCIONES | CAJA | Saldo USD, movimientos y tasas de negociación | Delta interday, trading, delta intraday y complementos explícitos | Fondeo y ajustes se reciben como importes; no se estiman si faltan. |
| SWAPS | FORWARD | Valor FX nativo con curvas efectivas, curva implícita y spread | Tiempo, spot, COP, USD, base/spread, nuevos/otros | JSON normalizado; hoy se importa del libro mensual. |
| SWAPS | NOVADOS | Valor de cámara sin descuento, conforme al modelo implementado | Tiempo, spot, COP, USD, nuevos/otros; base/spread queda en cero en este modelo | Falta contraste con cartera activa y liquidaciones reales de cámara. |
| SWAPS | SWAPS | Cambio de VP externo por operación más pago | Factores diarios externos y residual calculado | No hay valoración ni sensibilidades nativas completas por flujos Swap. |
| SWAPS | CAJA | Saldo, movimientos, TRM y fondeo FTP calculado | Delta interday, trading, delta intraday y costo de fondos | Contrato diario con verificación de saldo final. |
| FX_ESTRAT | Sus productos configurados | No habilitado | No disponible para cierre | Falta mapeo y conciliación de sus fuentes propias. |

`TODOS` significa los books habilitados, actualmente OPCIONES y SWAPS: **siete combinaciones book/producto**. No significa que FX_ESTRAT esté calculado. Tampoco incorpora Títulos o Arbitraje al alcance de estos motores.

### 2.1 Flujo de trabajo

```text
OPCIONES: snapshots diarios XLSX ← Vector o archivos locales
SWAPS: libro mensual XLSM → importador → snapshots diarios JSON
                                  │
                                  ▼
                selección: corte + book + DIARIO/MTD
                                  │
                                  ▼
           copias estables de insumos y huellas SHA-256
                                  │
                                  ▼
              cálculo de cada producto y cada intervalo
                                  │
                                  ▼
          validaciones aritméticas, de fechas y de alcance
                                  │
                                  ▼
                 persistencia transaccional en SQLite
                                  │
                                  ▼
          consolidación → JSON de resultado → HTML local
                                  │
                     conciliación requerida = OK
                                  │
                                  ▼
            carpeta Dashboards/PyG de la biblioteca
                                  │
                                  ▼
                   Portal Risko existente
```

El portal consulta la carpeta publicada; no calcula PyG ni necesita conocer las fórmulas. La interfaz PyG organiza la carga, el cálculo, la consolidación, la revisión y la publicación. El dashboard presenta las filas ya calculadas y permite filtrarlas.

### 2.2 Función de las herramientas

| Herramienta o módulo | Responsabilidad |
| --- | --- |
| `interfaz_pyg.py` | Seleccionar fecha/book/período; importar libro; ejecutar cierre o producto; ver resultados, exportar y publicar. Arranca sin cifras inventadas. |
| `servicios/pyg.py` | Coordinar etapas y conservar copias estables; genera y publica desde el corte solicitado. |
| Vector | Copiar snapshots OPCIONES de la fuente configurada. Es una herramienta externa y no es el motor de cálculo. |
| `fx_snapshot.py` | Leer el XLSM SWAPS sin ejecutar macros y producir JSON diarios, incluyendo el ancla disponible. |
| Motores por producto | Valorar o integrar fuentes y producir componentes, escenarios y controles. |
| `consolidacion.py` | Normalizar contribuciones, controlar identidades, persistir y sumar diarios/MTD sin duplicar totales. |
| `panel_pyg.py` | Construir un HTML autocontenido: filtros, contribuciones, matriz, gráficos y CSV. |
| `Opciones_FF_V3.py` | Referencia metodológica estudiada. No se importa ni se ejecuta para producir el nuevo PyG. |
| Position Monitor | Flujo de posición existente. Sus cálculos y el portal se conservaron sin cambios. |

## 3. Identidad del resultado y explicación por factores

### 3.1 El PyG no es solamente la diferencia de VP

Para una cartera con los eventos correctamente reconocidos:

```text
PyG Banking del intervalo = VP final − VP inicial + flujos netos del intervalo
```

Por ejemplo, si antes de pagar un cupón el derivado vale 1.000.000 COP, después vale 800.000 COP y se recibieron 300.000 COP:

```text
PyG = 800.000 − 1.000.000 + 300.000 = 100.000 COP
```

Ignorar el pago mostraría una pérdida de 200.000 COP. Sumar el pago dos veces mostraría una ganancia falsa de 400.000 COP. Para contratos nuevos también hay que considerar el desembolso o prima inicial; para bajas, el evento de cierre.

En Opciones y Forward, el motor construye un nivel compuesto:

```text
W(t) = mercado vivo(t) + CXC pendiente(t)
     + liquidaciones reconocidas desde el inicio del mes(t)
     + primas firmadas reconocidas desde el inicio del mes(t) [solo Opciones]

PyG del intervalo = W(t1) − W(t0)
```

Ambos niveles se calculan con el **mismo inicio de período**. Así, una liquidación del mes presente en los dos cortes se cancela al restarlos. En el primer día del mes, la base usa el mercado/CXC del cierre anterior y no arrastra las primas o liquidaciones ya reconocidas en el mes previo. Esto exige conservar las operaciones y eventos necesarios en los snapshots: una fila desaparecida no equivale automáticamente a una liquidación correctamente explicada.

### 3.2 Banking, ajuste e IFRS

Si `B(t)` es el nivel de mercado Banking e `I(t)` su nivel IFRS comparable:

```text
A(t) = I(t) − B(t)
Ajuste PyG CVA/DVA = A(t1) − A(t0)
PyG IFRS = PyG Banking + Ajuste PyG CVA/DVA
```

Ejemplo: `B0 = 1.000.000`, `I0 = 970.000`, `B1 = 1.200.000`, `I1 = 1.155.000`, sin pagos.

```text
Banking = 1.200.000 − 1.000.000 = 200.000
A0 = 970.000 − 1.000.000 = −30.000
A1 = 1.155.000 − 1.200.000 = −45.000
CVA/DVA = −45.000 − (−30.000) = −15.000
IFRS = 200.000 − 15.000 = 185.000 COP
```

`I1 − I0 = 185.000` ya es el resultado IFRS de este ejemplo. Sumárselo otra vez a Banking duplicaría el mercado. El programa no calcula probabilidades de incumplimiento ni una separación detallada entre CVA y DVA. En Swap, el campo común CVA/DVA incluye además la variación de recuponing; esta particularidad se explica en su capítulo.

### 3.3 Qué significa “por griegas” en Risko

Las sensibilidades diferenciales describen cómo cambia el valor ante un movimiento pequeño. Una expansión aproximada suele expresarse así:

```text
ΔV ≈ Theta × Δtiempo + Delta × ΔS + ½ × Gamma × (ΔS)²
     + Rho × Δtasa + Vega × Δvolatilidad + otros efectos
```

En los valoradores nativos de este PyG, los importes se obtienen principalmente con **revaloraciones completas y secuenciales**, no multiplicando las sensibilidades guardadas en posición. Para Opciones:

| Nivel | Cartera | Fecha | Spot | Tasas | Volatilidad |
| --- | --- | --- | --- | --- | --- |
| `W0` BASE | Anterior | Anterior | Anterior | Anteriores | Anterior |
| `Wt` THETA | Anterior | Actual | Anterior | Anteriores | Anterior |
| `Ws` DELTA | Anterior | Actual | Actual | Anteriores | Anterior |
| `Wr` RHO | Anterior | Actual | Actual | Actuales | Anterior |
| `Wv` VEGA | Anterior | Actual | Actual | Actuales | Actual |
| `W1` ACTUAL | Actual | Actual | Actual | Actuales | Actual |

```text
THETA        = Wt − W0
DELTA_PYG    = Ws − Wt
RHO          = Wr − Ws
VEGA         = Wv − Wr
NUEVOS_OTROS = W1 − Wv
Suma         = W1 − W0 = PyG Banking
```

**Nivel y contribución son distintos.** `escenarios.THETA` guarda un nivel revalorado; `componentes.THETA` guarda la diferencia respecto a BASE. No se deben sumar los niveles de escenarios como si fueran contribuciones.

El orden distribuye efectos cruzados. En el orden tiempo → spot → tasas → volatilidad, la contribución de volatilidad se mide después de actualizar el spot y las tasas. Cambiar el orden puede cambiar cada componente, aunque el total final sea igual. El smile por delta también puede cambiar la volatilidad efectiva al mover el spot o las tasas, aun conservando la superficie de entrada anterior.

`DELTA_PYG` incluye la respuesta no lineal de la revaloración al spot. Por eso no se suma otra Gamma al resultado completo. Ejemplo puramente didáctico: para una función de valor cuadrática con Delta 50.000 USD, Gamma 1.000 USD²/COP y movimiento de 10 COP/USD:

```text
Efecto lineal = 50.000 × 10 = 500.000 COP
Efecto cuadrático = ½ × 1.000 × 10² = 50.000 COP
Revaloración completa por spot = 550.000 COP
```

Si el motor ya asignó 550.000 a DELTA_PYG, añadir 50.000 como Gamma produciría 600.000 y rompería la identidad. Gamma tampoco aparece como una contribución independiente calculada por el motor actual.

### 3.4 Lectura de los componentes

| Componente | Lectura correcta |
| --- | --- |
| THETA | Cambio al avanzar la fecha con los demás insumos de escenario fijados; alrededor de vencimientos también intervienen los fixings/eventos reconocidos por el motor. |
| DELTA_PYG | Efecto monetario completo del escenario de spot de derivados; en Swap es un factor importado. |
| DELTA_INTERDAY | Saldo USD anterior de Caja multiplicado por cambio de TRM. |
| DELTA_INTRADAY | Efecto de revalorar el neto negociado en Caja hasta la TRM de cierre. |
| RHO | Cambio conjunto de curvas COP/USD en el book OPCIONES. |
| RHO_COP, RHO_USD | Cambios separados en SWAPS FX; en producto Swap proceden del reporte. |
| RHO_DTF, RHO_IPC, RHO_OTRAS | Factores del reporte Swap; no son sensibilidades nativas de todos los productos. |
| BASE_SPREAD | Efecto de actualizar base implícita y spread del Forward SWAPS, después de COP/USD. |
| VEGA | Efecto de sustituir la superficie de volatilidad en Opciones. |
| TRADING | Margen de compras/ventas casadas en Caja; en Swap es un factor externo. |
| NUEVOS_OTROS | Cambio entre cartera actual y anterior revalorada. Puede mezclar altas, bajas, primas y ajustes; no es trading puro. |
| COSTO_FONDOS, AJUSTES | Importes firmados. Fondeo se calcula en Caja SWAPS y se recibe explícito en Caja OPCIONES. |
| EPSILON | Parte del Banking Swap que no explica la suma de factores externos. No prueba que esos factores sean correctos. |

### 3.5 Por qué cada riesgo produce una ganancia o una pérdida

**Descontar significa expresar hoy un dinero que se recibe o paga después.** Si se reciben 1.000 COP dentro de un año y la tasa efectiva anual es 10%, su valor presente es `1.000/1,10 = 909,09 COP`. Si la tasa sube a 11%, baja a `1.000/1,11 = 900,90`. El ingreso futuro no cambió; cambió su valor de hoy. Para una obligación, la misma disminución del valor presente del pago mejora el valor neto del contrato. Esta diferencia entre una pata que se recibe y otra que se paga explica muchos signos de Rho.

**Delta:** una compra de USD se beneficia de una subida del USD/COP, manteniendo lo demás fijo. Una venta tiene el efecto contrario. En una opción, también importa CALL/PUT:

| Posición vanilla | Derecho u obligación económica | Efecto esperado de subir spot, con los demás parámetros de la fórmula fijos |
| --- | --- | --- |
| BUY CALL | Derecho a comprar USD a K | El valor sube. |
| SELL CALL | Obligación frente al comprador de la CALL | El valor firmado baja. |
| BUY PUT | Derecho a vender USD a K | El valor baja. |
| SELL PUT | Obligación frente al comprador de la PUT | El valor firmado sube. |

Estos signos orientan la revisión de una operación aislada. Un book puede combinar muchas posiciones opuestas y, con smile por delta, el escenario también incorpora la interacción ya descrita. Por ello no se deduce el signo de todo el book leyendo una sola etiqueta de producto.

**Theta:** al pasar un día disminuye el tiempo disponible para que una opción termine favorablemente, pero también cambian los descuentos y pueden ocurrir fixings o pagos. En una opción comprada suele observarse desgaste del valor temporal; no hay una regla universal que obligue a que todo THETA sea negativo. En un Forward, el paso del tiempo modifica el descuento de sus dos patas aun cuando el spot no cambie. En el ejemplo Forward OPCIONES, el nivel baja de 1.351.997,55 a 1.308.599,78 COP al pasar de 31 a 30 días: esa resta, −43.397,77, es el Theta del escenario.

**Rho COP y USD:** para una compra Forward sin base ni spread, el contrato recibe económicamente USD y paga COP. Al subir la tasa COP se reduce el valor presente de la obligación COP, lo que mejora su valor; al subir la tasa USD se reduce el valor presente de los USD recibidos, lo que lo empeora. En el ejemplo SWAPS, RHO_COP es +872.209,39 y RHO_USD es −465.383,21. En OPCIONES se cambian ambas curvas en un único paso: RHO puede ser negativo aunque una de las dos subidas por separado favorezca a la posición.

**Vega:** una opción vanilla comprada puede beneficiarse de mayor dispersión futura porque conserva el derecho de ejercer favorablemente y dejar vencer sin ejercicio cuando el payoff sea cero. Aumentar la volatilidad eleva su valor bajo la fórmula vanilla, manteniendo los demás parámetros fijos; vender esa misma opción invierte el signo. Pasar de 20% a 21% de volatilidad equivale a **un punto porcentual**, es decir, `0.01` en decimal; no equivale a un movimiento de `1.00`. En la CALL del ejemplo, sustituir únicamente la superficie 20% por 21% lleva el valor de 23.040,67 a 23.666,78 COP: Vega PyG +626,11.

**Base y spread:** la relación entre curvas COP/USD no necesariamente reproduce toda la curva implícita observada. La base guarda esa diferencia de la fuente y el spread ajusta la valoración según la dirección. En el Forward SWAPS se preserva la base anterior al medir cada Rho, y solo después se incorpora la base/spread actual. No se trata de un segundo movimiento de spot ni de un costo que deba volver a sumarse en Caja.

**Crédito y ajustes IFRS:** el nivel de mercado puede mejorar mientras empeora el ajuste de crédito, de modo que la ganancia IFRS sea menor que Banking. El nombre CVA se asocia conceptualmente al riesgo de incumplimiento de la contraparte, y DVA al efecto del riesgo propio sobre obligaciones; una lectura de apoyo es [Counterparty Risk FAQ, de Damiano Brigo](https://arxiv.org/abs/1111.1331). **Risko no estima aquí esos riesgos por separado**. En esta versión el monto se obtiene del puente de niveles descrito, o de ajustes recibidos. Para saber qué contiene realmente hay que revisar la semántica de la fuente, especialmente recuponing en Swap.

### 3.6 Cómo distinguir flujo de liquidación y PyG con una misma operación

Supóngase que al inicio de un intervalo el derivado o su cuenta vale 9.000 COP. Al corte siguiente, la cuenta pendiente vale 10.064,52. Todavía no se ha pagado nada:

```text
PyG del primer intervalo = 10.064,52 − 9.000 = 1.064,52 COP
```

Después se liquida por 10.064,52 sin cambiar su valor entre el corte anterior y el pago:

```text
VP/CXC final = 0
VP/CXC inicial = 10.064,52
Flujo recibido = +10.064,52
PyG del intervalo de pago = 0 − 10.064,52 + 10.064,52 = 0 COP
```

En la representación mensual `W`, antes del pago hay CXC 10.064,52 y flujo cero; después hay CXC cero y flujo acumulado 10.064,52. `W` no cambia por el mero traslado. El efectivo recibido es **10.064,52**, mientras que el PyG de los dos intervalos es **1.064,52**, porque ya había un valor de 9.000 al inicio.

Si el cobro fue en USD, los USD pasan al inventario de Caja. Para atribuir un movimiento posterior de TRM se utiliza ese inventario y su momento de entrada; no se reabre el flujo ya liquidado del derivado a la TRM nueva. El modelo de integración de movimientos debe garantizar esta separación.

## 4. Insumos y convenciones que hay que comprobar

El [anexo 13](#13-inventario-exacto-de-insumos-y-paquete-que-se-debe-entregar) amplía este resumen con archivos, columnas obligatorias, nodos de curva, formatos, fechas y fuentes primarias por producto.

### 4.1 Book OPCIONES

Archivo por fecha: `Dataset Libro de Opciones AAAAMMDD.xlsx`. Un cierre diario necesita dos archivos; MTD requiere el ancla y la cadena de días del calendario configurado.

| Hoja | Contenido usado |
| --- | --- |
| `Resumen` | TRM, saldo `Cajausd`, niveles IFRS `Opccva` y `Forcva`. |
| `Opciones` | Identificación, BUY/SELL, CALL/PUT, nominal, strike, fechas, modalidad y moneda de cumplimiento, prima firmada y su moneda/tasa. |
| `Forwards` | Nominal, tasa forward pactada, compra/venta, emisión, vencimiento, cumplimiento, DF/NDF y moneda. |
| `Caja` | Fila diaria con compras/ventas USD y tasas; fondeo y ajustes si existen. |
| `Tasas_COP`, `Tasas_USD` | Curvas continuas en decimal con rangos de plazo. |
| `Superficie_Volatilidad` | Smile por plazo: 10D PUT, 25D PUT, ATM, 25D CALL y 10D CALL, en decimal. |
| `tfd` | Fixings exactos de Opciones; conversiones históricas de primas y cumplimientos. |
| `tff` | Fixings Forward según la convención de fila del día calendario siguiente de esta fuente. |
| `PYG` | Controles opcionales de resultados. No alimentan el Banking calculado. |

El cargador común requiere mercado de Opciones incluso al ejecutar Forward o Caja del mismo book. Por eso un snapshot parcial con solo una hoja de producto puede resultar insuficiente. El [contrato detallado de insumos](contrato_insumos_pyg.md) enumera nombres exactos de columnas y controles.

### 4.2 Book SWAPS

Archivo normalizado por fecha: `Dataset SWAPS AAAAMMDD.json`, `schema_version = 1`. El importador lee valores guardados del XLSM, sin ejecutar sus macros ni actualizar vínculos externos. La fecha de portada no garantiza que todas las hojas tengan cálculos actualizados.

| Bloque JSON | Información |
| --- | --- |
| `fecha`, `book`, `schema_version` | Identificación inequívoca del snapshot. |
| `mercado` | TRM, spots de compra/venta, curvas COP/USD/implícita efectivas, spread y fixings. |
| `operaciones.FORWARD`, `operaciones.NOVADOS` | Operaciones, nominal, signo, strike y fechas. |
| `swaps` | Trade ID, VP Banking, VP IFRS y pago explícito por operación. |
| `factores_swap` | Nueve contribuciones monetarias diarias tomadas del reporte. |
| `caja` | Saldo, movimientos USD/COP, TRM y FTP con ajustes. |
| `credito_acumulado_cop` | Ajustes acumulados Forward y Novados que se diferencian entre cortes. |
| `recuponing_nivel_cop` | Nivel de ajuste cuya variación entra en el resultado IFRS Swap. |
| `controles`, `calidad` | Referencias de conciliación y advertencias de la extracción. |

El filtro de operaciones debe aplicarse a todo el maestro, sin límites fijos por fila. En el producto Swap del book SWAPS se excluyen los desks FX_ESTRAT, ARBITR_DER y FVH según el importador. El maestro mensual reconstruido retrospectivamente no reemplaza un registro histórico completo de eventos.

### 4.3 Convenciones que no se pueden intercambiar

| Convención | OPCIONES | SWAPS FX |
| --- | --- | --- |
| Tasas | Continuas anuales | Efectivas anuales |
| Descuento | `exp(−r × τ)` | `(1 + r)^−τ` |
| Plazo Forward vivo | Hasta vencimiento | Hasta cumplimiento, mientras siga antes del vencimiento |
| Curva implícita/spread | No se añade un factor separado | Sí para Forward; no para Novados |
| Fixing histórico | `tfd` exacto; `tff` con etiqueta del día siguiente | Mapa JSON con la fecha exacta |
| Fondeo Caja | Importe recibido | Cálculo FTP diario COP/365 y USD/360 |

Por ejemplo, 10% efectivo anual equivale a tasa continua `ln(1,10) = 0,09531018`, aproximadamente 9,531018%. Ingresar `0.10` como tasa continua no representa la misma curva. Además, un punto básico es `0.0001` en decimal y un punto porcentual de volatilidad es `0.01`; confundirlos produce errores de escala.

## 5. Book OPCIONES: productos y ejemplos

Este capítulo describe los motores de `opciones.py`, `forward.py`, `caja.py` y `atribucion.py` tal como están implementados. Sus tres productos son **OPCIONES**, **FORWARD** y **CAJA**. Todos los resultados monetarios finales están en COP. Los ejemplos son sintéticos, reproducibles y usan el intervalo **31 de julio de 2026 → 1 de agosto de 2026**; elegir el cambio de mes permite mostrar la función del cierre anterior como ancla del PyG mensual.

Las cifras de tablas usan punto de miles y coma decimal. Las expresiones de Python usan punto decimal. Las tasas se entregan al motor en forma decimal: 8 % se escribe `0.08`; una volatilidad de 20 % se escribe `0.20`.

### 5.1. Qué significa atribuir el PyG a griegas

En este book se revalora la cartera anterior varias veces, sustituyendo grupos de entradas en un orden fijo. Cada contribución es la diferencia entre dos escenarios consecutivos. Por ejemplo, `DELTA_PYG` mide la variación monetaria al cambiar el spot en el tercer escenario; no es la sensibilidad delta expresada en USD ni la fórmula aproximada delta × cambio de spot. El método captura en ese paso la no linealidad de la valoración. No se produce una fila independiente GAMMA.

El orden implementado es **tiempo → spot → tasas COP/USD → volatilidad → cartera actual**. Forward omite el paso volatilidad. Alterar ese orden puede redistribuir el resultado entre componentes, aunque el total siga igual. Cuando el smile no es plano, el cambio de spot también modifica la volatilidad interpolada por delta, incluso conservando la misma superficie: esto forma parte del escenario Delta actual. Por ello no debe interpretarse cada nombre como una derivada parcial aislada de cualquier interacción.

Para una fecha y una cartera, los motores suman:

`W = valor de mercado + cuenta por cumplir + flujos realizados del período + primas del período`

En Forward no hay primas. Los flujos y las primas se incluyen desde el primer día del mes del corte; usar el mismo inicio en ambos extremos permite obtener el cambio diario sin duplicarlos. La cartera debe conservar la información de los eventos que esos niveles necesitan.

**Banking** es la suma de contribuciones. El ajuste de crédito agregado del book se obtiene de dos niveles comparables:

`G(t) = nivel de mercado IFRS(t) − nivel de mercado Banking(t)`

`CVA_DVA del día = G(t1) − G(t0)`

`PyG IFRS = PyG Banking + CVA_DVA del día`

`Resumen.Opccva` y `Resumen.Forcva` se interpretan como **niveles IFRS de mercado**, no como PyG ni como niveles de CVA aislados. El motor no calcula probabilidad de incumplimiento ni separa CVA y DVA. Si el productor de datos usa otro significado, hay que corregir el contrato antes de conciliar.

### 5.2. Opciones vanilla de divisas

#### 5.2.1. Insumos y signos

La hoja `Opciones` aporta identificador único, BUY/SELL, CALL/PUT, nominal USD, strike COP/USD, emisión, vencimiento, cumplimiento, modalidad DELIVERY/NON DELIVERY, moneda de cumplimiento y prima. `Resumen` aporta TRM y el nivel IFRS `Opccva`; `Tasas_COP`, `Tasas_USD` y `Superficie_Volatilidad` aportan el mercado. `tfd` aporta los fixings exactos por fecha. `PYG`, si existe, aporta controles de comparación.

Se usa `q = +1` para BUY y `q = −1` para SELL. El nominal es no negativo. Una CALL paga por subida de USD/COP; una PUT, por bajada. Un comprador tiene valor positivo de la opción antes de descontar su prima; el vendedor tiene el signo contrario.

#### 5.2.2. Valoración viva

Sean `S` el spot COP/USD, `K` el strike COP/USD, `N` el nominal USD, `T = días al vencimiento / 365`, `r_COP` y `r_USD` tasas continuas anuales y `σ` volatilidad anual. Las tasas se interpolan linealmente por plazo a partir de las bandas y nodos del archivo.

```text
d1 = [ln(S/K) + (r_COP − r_USD + σ²/2) × T] / (σ × √T)
d2 = d1 − σ × √T

CALL por USD = S × exp(−r_USD × T) × Φ(d1)
             − K × exp(−r_COP × T) × Φ(d2)

PUT por USD = K × exp(−r_COP × T) × Φ(−d2)
            − S × exp(−r_USD × T) × Φ(−d1)
```

`Φ` es la distribución normal acumulada. Estas son las fórmulas de dos tasas para una opción europea de divisas. El código aplica adicionalmente la siguiente convención de desfase entre vencimiento y cumplimiento:

```text
Tc = días al cumplimiento / 365
A  = exp(r_USD(Tc) × Tc) / exp(r_USD(T) × T)
Valor Banking COP = q × N × precio por USD / A
```

Si cumplimiento y vencimiento coinciden, `A = 1`. Este factor reproduce la convención implementada; su adecuación a cada modalidad contractual necesita la conciliación funcional pendiente y no debe sustituirse por otra convención en una hoja auxiliar sin dejar constancia.

La superficie contiene 10D PUT, 25D PUT, ATM, 25D CALL y 10D CALL. Primero se interpola cada columna por plazo. Después se usa un spline cúbico natural sobre deltas absolutas 0,10; 0,25; 0,50; 0,75; 0,90, invirtiendo las volatilidades para CALL. Se empieza con ATM y se itera porque delta depende de volatilidad. La delta usada aquí es `(Φ(d1) − 1)/A` para PUT y `Φ(d1)/A` para CALL. Las colas se fijan en 10D/90D; no se extrapola el spline. Se rechazan volatilidades no positivas y falta de convergencia tras 100 iteraciones. Esta definición exacta de delta debe reconciliarse con la fuente del smile; no debe confundirse con otra convención de delta spot o ajustada por prima.

#### 5.2.3. Del valor al PyG: ejemplo completo

Cartera anterior: BUY CALL por **100 USD**, strike **3.000 COP/USD**, emisión 1 de julio, vencimiento y cumplimiento 1 de diciembre de 2026. La prima de julio no entra como un flujo nuevo de agosto. En la base faltan 123 días; en el corte, 122.

Mercado anterior: spot 3.100, tasa COP 8 %, tasa USD 4 %, volatilidad plana 20 %. Mercado actual: spot 3.120, tasa COP 8,1 %, tasa USD 4,2 %, volatilidad plana 21 %. El 1 de agosto se añade una **SELL PUT por 50 USD**, strike 3.200, mismo vencimiento/cumplimiento, con **prima recibida de +25.000 COP**. La prima se suministra con su signo.

En la CALL base, `T = 123/365`, `d1 = 0,4565764423`, `d2 = 0,3404753999`. El precio por USD es **218,3582960232 COP/USD**, por lo que su valor es `100 × 218,3582960232 = 21.835,8296023154 COP`.

| Escenario | Entradas sustituidas respecto al anterior | Nivel W, COP |
|---|---|---:|
| BASE | Cartera, fecha y mercado anteriores | 21.835,829602 |
| THETA | Fecha 1 de agosto; sigue spot 3.100, tasas 8 %/4 %, vol 20 % | 21.765,955909 |
| DELTA | Spot pasa a 3.120 | 23.119,912506 |
| RHO | Tasas pasan a 8,1 % COP y 4,2 % USD | 23.040,666089 |
| VEGA | Volatilidad pasa a 21 % | 23.666,780495 |
| ACTUAL | Añade la PUT vendida y su prima | 40.186,017837 |

La PUT vendida vale **−8.480,762658 COP**. Por tanto, el cambio de cartera es `−8.480,762658 + 25.000 = +16.519,237342 COP`. El ejemplo escoge una prima distinta del valor del modelo para hacer visible esa contribución.

| Contribución | Resta de escenarios | PyG, COP |
|---|---|---:|
| THETA | 21.765,955909 − 21.835,829602 | −69,873694 |
| DELTA_PYG | 23.119,912506 − 21.765,955909 | +1.353,956597 |
| RHO | 23.040,666089 − 23.119,912506 | −79,246416 |
| VEGA | 23.666,780495 − 23.040,666089 | +626,114406 |
| NUEVOS_OTROS | 40.186,017837 − 23.666,780495 | +16.519,237342 |
| **PYG_BANKING** | **40.186,017837 − 21.835,829602** | **+18.350,188235** |

Si el ajuste de crédito pasa de **−5 a −8 COP**, `CVA_DVA = −8 − (−5) = −3 COP`, y **PyG IFRS = 18.347,188235 COP**. Para este ejemplo, `Opccva` anterior sería `21.835,829602 − 5 = 21.830,829602`; el actual sería `(23.666,780495 − 8.480,762658) − 8 = 15.178,017837`. La prima de 25.000 es un evento común a Banking e IFRS; no se resta al calcular el nivel de crédito.

`NUEVOS_OTROS` es un residual entre carteras a mercado actual. Además de operaciones nuevas, puede contener bajas, modificaciones o diferencias de eventos. Su nombre no certifica que todo el monto corresponda a negociación nueva.

#### 5.2.4. Vencimiento, cuenta por cumplir y cobro/pago

Una opción vencida deja de tener valor de mercado vivo. Si todavía no cumple, conserva una cuenta por cobrar o pagar. Para una CALL NON DELIVERY el payoff unitario es `max(fixing − K, 0)`; para PUT es `max(K − fixing, 0)`.

| Modalidad | Cuenta pendiente antes del cumplimiento |
|---|---|
| NON DELIVERY, COP | `q × N × payoff` |
| NON DELIVERY, USD | `q × N × payoff / fixing × spot actual` |
| DELIVERY ejercida, CALL | `q × N × (spot actual − K)` |
| DELIVERY ejercida, PUT | `−q × N × (spot actual − K)` |

En DELIVERY, la condición de ejercicio se decide con el fixing de vencimiento. Una cuenta originada por una opción ejercida puede cambiar de valor con el spot hasta cumplir; no se vuelve a aplicar `max` a su valor posterior.

Ejemplo: BUY CALL NON DELIVERY USD, nominal 100, strike 3.000, fixing de vencimiento 3.100 el **1 de agosto**, cumplimiento **3 de agosto**. El payoff es `100 × (3.100 − 3.000) = 10.000 COP`, equivalente a `10.000 / 3.100 = 3,2258064516 USD`. El 2 de agosto, con spot 3.120, la cuenta vale **10.064,516129 COP**. Al liquidar el 3 de agosto con spot 3.120, pasa a flujo realizado por ese mismo valor y la cuenta pendiente pasa a cero. El 4 de agosto, aunque el spot suba a 3.300, el flujo de Opciones permanece **10.064,516129 COP**: la exposición de los USD ya recibidos corresponde a Caja.

En Opciones, el día del vencimiento se utiliza el spot del escenario; después se exige el fixing de la **fecha exacta de vencimiento** en `tfd`. Para convertir un pago ya liquidado se exige el fixing de la fecha exacta de cumplimiento. No se utiliza la fila más próxima.

#### 5.2.5. Prima y limitaciones específicas

`Valor Total Prima` ya debe venir firmado: prima pagada negativa; recibida positiva. El motor no cambia el signo según BUY/SELL. La moneda de prima puede ser distinta de la de cumplimiento; se admite `Moneda Prima` y los alias originales `Moneda de la Prima` / `Moneda de la  Prima`. Si no existe esa columna, se usa la moneda de cumplimiento como valor de respaldo, una convención que debe revisarse en los insumos.

Una prima de **−5 USD** con `Tasa Prima = 3.100` se incorpora como `−5 × 3.100 = −15.500 COP`, incluso si el spot del corte es 3.120. Si no se entrega tasa explícita, se requiere el fixing exacto de la emisión en `tfd`.

La prima se ubica en el período por la **fecha de emisión**; todavía no existe un calendario separado de pagos de primas. Las carteras diarias deben preservar operaciones y eventos necesarios para reconstruir flujos del mes; una operación que desaparece sin evento explícito puede contaminar `NUEVOS_OTROS`. Las convenciones de settlement, superficie, primas y controles requieren conciliación con snapshots reales de OPCIONES, que no estuvieron disponibles en la validación entregada. Los ejemplos y las pruebas sintéticas verifican las fórmulas implementadas, no sustituyen esa conciliación.

### 5.3. Forward del book OPCIONES

#### 5.3.1. Valoración y atribución

No debe confundirse con el Forward del book SWAPS: este motor usa **tasas continuas ACT/365**. Sus datos están en `Forwards`, las curvas COP/USD, `tff` y `Resumen.Forcva`.

```text
q = +1 para COMPRA USD, −1 para VENTA USD
T = días hasta vencimiento / 365
V = q × N × [S × exp(−r_USD × T) − K × exp(−r_COP × T)]
```

`N` está en USD y `K` y `S` en COP/USD. Con tasas cero, comprar 100 USD a 3.000 y valorar con spot 3.100 produce `100 × (3.100 − 3.000) = +10.000 COP`; vender el mismo contrato produce −10.000.

La atribución es `THETA = W_tiempo − W_base`, `DELTA_PYG = W_spot − W_tiempo`, `RHO = W_tasas − W_spot`, `NUEVOS_OTROS = W_actual − W_tasas`. RHO agrupa ambas curvas; no se desglosa COP y USD en este motor.

#### 5.3.2. Ejemplo con tasas, spot y nueva operación

Cartera anterior: COMPRA de **100.000 USD** a **4.000**, emitida el 1 de julio, vencimiento y cumplimiento el **31 de agosto de 2026**. El 31 de julio quedan 31 días; el 1 de agosto, 30. Mercado anterior: spot 4.000, tasas continuas 8 % COP y 4 % USD. Mercado actual: spot 4.050, tasas 8,1 % COP y 4,2 % USD. La cartera actual añade una VENTA de **20.000 USD** a **4.060**, emitida el 1 de agosto y con el mismo vencimiento/cumplimiento.

```text
V_base = 100.000 × [4.000 × exp(−0,04 × 31/365)
                    − 4.000 × exp(−0,08 × 31/365)]
       = 1.351.997,547476 COP

V_nueva = −20.000 × [4.050 × exp(−0,042 × 30/365)
                     − 4.060 × exp(−0,081 × 30/365)]
        = −59.661,895863 COP
```

| Escenario | Nivel W, COP | Diferencia respecto al anterior, COP |
|---|---:|---:|
| BASE: 31 de julio, mercado anterior | 1.351.997,547476 | — |
| THETA: 1 de agosto, mercado anterior | 1.308.599,778039 | −43.397,769438 |
| DELTA: cambia spot a 4.050 | 6.292.188,414241 | +4.983.588,636202 |
| RHO: cambian tasas a 8,1 % y 4,2 % | 6.258.496,947534 | −33.691,466707 |
| ACTUAL: añade la nueva venta | 6.198.835,051671 | −59.661,895863 |
| **PYG_BANKING** | **ACTUAL − BASE** | **+4.846.837,504194** |

Si el nivel de ajuste de crédito pasa de −2.000 a −2.500 COP, `CVA_DVA = −500` y **PyG IFRS = 4.846.337,504194 COP**. Los niveles fuente `Forcva` serían `V_mercado_base − 2.000` y `V_mercado_actual − 2.500`.

#### 5.3.3. Fixing y cumplimiento

El forward NDF tiene payoff firmado `q × N × (fixing − K)`, que puede ser positivo o negativo. Si liquida en COP, la cuenta permanece por ese valor. Si liquida en USD, la cuenta pendiente se convierte como `payoff / fixing × spot actual`. En DF, se conserva el valor económico `q × N × (spot actual − K)` hasta el cumplimiento. Al liquidar, la conversión se fija a la tasa de cumplimiento, manteniendo el flujo en el período y evitando volver a revalorarlo dentro de Forward.

**Convención de `tff`:** en la fecha de vencimiento se usa el spot del escenario; cuando la fecha ya pasó se busca en `tff` la fila del **día calendario siguiente** al vencimiento. El valor de esa fila representa el fixing del vencimiento conforme a FF_V3. Para un vencimiento el 31 de agosto se busca **1 de septiembre**, no se suma `1` al entero `20260831`. La misma regla se usa para recuperar la conversión del cumplimiento pasado. Es distinta de la convención de `tfd` de Opciones y debe respetarse al generar snapshots.

El ejemplo de cuenta por cumplir USD de la sección Opciones produce los mismos **3,2258064516 USD** y **10.064,516129 COP** para una COMPRA NDF de 100 USD con strike 3.000 y fixing 3.100, pero las filas de `tff` son **2 de agosto** para vencimiento el día 1 y **4 de agosto** para cumplimiento el día 3.

Este motor no tiene un valuador separado de basis/spread, ni integra flujos de nuevas operaciones fuera de la cartera suministrada. Conserva detalle por índice de fila; el contrato actual de `Forwards` no exige un identificador único de negociación. Para una conciliación operativa por transacción conviene completar esa trazabilidad en el productor de insumos.

### 5.4. Caja del book OPCIONES

#### 5.4.1. Qué explica cada componente

Caja explica el resultado cambiario del saldo USD anterior y las compras/ventas del corte. El saldo anterior se toma de `Resumen.Cajausd`; la fila diaria de `Caja` suministra montos y tasas agregadas. Debe existir exactamente una fila explícita para el corte, incluso si no hubo operaciones. Cuando hay varias negociaciones, el productor de la fila debe usar tasas promedio ponderadas por monto para que representen los flujos agregados.

Sean `B` compras USD, `V` ventas USD, `Kb` tasa de compra, `Kv` tasa de venta, `S0` TRM anterior, `S1` TRM actual y `Q0` saldo anterior USD:

```text
DELTA_INTERDAY = Q0 × (S1 − S0)
TRADING        = min(B, V) × (Kv − Kb)
DELTA_INTRADAY = (B − V) × (S1 − Kb), si B ≥ V
               (B − V) × (S1 − Kv), si B < V
```

El interday revalora el inventario que existía antes. Trading realiza el margen de la parte comprada y vendida en el día. Intraday marca a cierre la parte neta que queda comprada o vendida. La suma de trading e intraday coincide algebraicamente con `B × (S1 − Kb) + V × (Kv − S1)`; esta igualdad sirve como control independiente.

`Costo_Fondos_COP` y `Ajustes_PyG_COP`, cuando existen, se suman **con el signo recibido**. En este book el motor **no calcula tasas de fondeo**: necesita el costo ya expresado en COP. Si falta la columna, reporta `NO_INCLUIDO`; no inventa una tasa ni interpreta la ausencia como un costo validado de cero. El CVA/DVA de Caja es cero por diseño actual, por lo que Banking e IFRS coinciden.

#### 5.4.2. Ejemplo calculado

Saldo anterior **100.000 USD**, TRM anterior **4.000**, TRM actual **4.020**. Se compran **50.000 USD a 4.005** y se venden **30.000 USD a 4.010**. La fuente entrega costo de fondos **−40.000 COP** y ajustes **+5.000 COP**.

| Componente | Operación | Resultado COP |
|---|---|---:|
| DELTA_INTERDAY | 100.000 × (4.020 − 4.000) | +2.000.000 |
| TRADING | 30.000 × (4.010 − 4.005) | +150.000 |
| DELTA_INTRADAY | (50.000 − 30.000) × (4.020 − 4.005) | +300.000 |
| COSTO_FONDOS | Dato firmado recibido | −40.000 |
| AJUSTES | Dato firmado recibido | +5.000 |
| **PYG_BANKING** | **Suma de las cinco filas** | **+2.415.000** |
| CVA_DVA | Convención actual | 0 |
| **PYG_IFRS** | **Banking + CVA_DVA** | **+2.415.000** |

Control directo de las operaciones: `50.000 × 15 + 30.000 × (−10) = 450.000 COP`, igual a `150.000 + 300.000`. Si no existen otros movimientos, el saldo esperado pasa a `100.000 + 50.000 − 30.000 = 120.000 USD`. **La Caja OPCIONES actual no valida ese puente contra el saldo actual**; debe controlarse en el productor del dataset o en conciliación. Tampoco agrega por sí sola flujos de cumplimiento o primas provenientes de los otros motores: el productor de Caja debe incorporarlos al saldo y a los movimientos correspondientes, sin duplicar el PyG realizado del derivado.

Si predominan las ventas, por ejemplo saldo 10 USD, TRM 3.100→3.120, compras 50 USD a 3.105 y ventas 80 USD a 3.110, los componentes son `+200`, `+250` y `(50−80)×(3.120−3.110)=−300`, total **150 COP** antes de fondeo/ajustes. El signo negativo del neto vendido es esencial.

## 6. Book SWAPS: productos y ejemplos

Este capítulo describe las fórmulas implementadas en `proyectos/pyg/procesos/fx_motores.py` y las fuentes extraídas por `fx_snapshot.py`. Los ejemplos son sintéticos, en COP; los nominales de Forward y Novados se expresan en USD y las tasas en tanto por uno. Se conserva precisión completa durante el cálculo y solo se redondea al presentar.

El book SWAPS contiene productos **FORWARD, NOVADOS, SWAPS y CAJA**. Book y producto son dimensiones distintas: `book=SWAPS, producto=SWAPS` identifica los contratos Swap de ese book. No incluye FX_ESTRAT. En el importador, el maestro Swap excluye los desks ARBITR_DER, FX_ESTRAT y FVH; los Forward se seleccionan por clasificación SWAPS y los Novados por SWAPSNOVADO.

El PyG es un flujo durante un intervalo. Un VP de 100 millones no representa 100 millones de ganancia: para medirla hay que comparar contra el VP anterior y reconocer pagos. Los factores del dashboard son contribuciones monetarias en COP, no sensibilidades como USD de delta o COP por punto básico.

#### Tasas y fechas

- Forward y Novados de este book utilizan tasas efectivas anuales y ACT/365: `τ = días calendario hasta cumplimiento / 365`.
- Las curvas se interpolan linealmente en tasa entre plazos; fuera de los nodos se mantiene el extremo. No se permiten nodos duplicados/desordenados, plazos negativos o tasas menores o iguales a −100%.
- El plazo de valoración llega a **cumplimiento**; **vencimiento** determina cuándo termina el derivado y nace la cuenta por cobrar/pagar. Si difieren, ambas fechas son necesarias.
- Una compra de USD tiene signo `q=+1`; una venta, `q=−1`. Nominal y strike se almacenan positivos.
- El motor exige fixings exactos en vencimiento y, cuando corresponde, cumplimiento. No toma automáticamente la cotización disponible más cercana.

### 6.1. Producto FORWARD del book SWAPS

#### Valoración antes del vencimiento

Definiciones: `N` nominal USD; `K` strike COP/USD; `S` spot de compra o venta según dirección; `rCOP`, `rUSD`, `rI` tasas efectivas de las curvas COP, USD e implícita al plazo; `sp` spread de la fuente.

```text
b = ln(1 + rI) + ln(1 + rUSD) − ln(1 + rCOP)
rA = exp[ln(1 + rCOP) − ln(1 + rUSD) + b] − 1 − q × sp/2
VP = q × N × [S − K/(1 + rA)^τ] / (1 + rUSD)^τ
```

`b` conserva la base de la curva implícita respecto a COP/USD. En el escenario de Rho COP se cambia únicamente COP; en Rho USD se cambia USD manteniendo la base anterior. La base y el spread actuales solo entran en su propio escenario. Cuando base y spread son cero, la fórmula se reduce a:

```text
VP = q × N × [S/(1+rUSD)^τ − K/(1+rCOP)^τ]
```

La fuente del maestro es `Forwards!A:N`. `Tasas` aporta curvas y spot fechado; `Forwards!W3` aporta el spread observado del libro. El importador conserva ese spread único al reconstruir días del mes: no dispone de un histórico diario independiente de spread.

#### Atribución y ejemplo numérico

Operación compradora de USD 100.000, strike 4.050, emitida el 01/08/2026, vencimiento y cumplimiento 30/11/2026. Corte anterior 01/09/2026 (90 días); actual 02/09/2026 (89 días). No hay nuevas operaciones ni pagos en el intervalo. Se usan curvas planas para que la interpolación no altere los números.

| Entrada | Anterior | Actual |
| --- | ---: | ---: |
| Spot de compra = venta = TRM, COP/USD | 4.000 | 4.020 |
| Tasa COP efectiva anual | 10% | 11% |
| Tasa USD efectiva anual | 4% | 4,5% |
| Base logarítmica `b` | 0 | 0,001 |
| Spread `sp`, tanto por uno | 0 | 0,002 |
| Curva implícita | `1,10/1,04 − 1` | `exp[ln(1,11)−ln(1,045)+0,001]−1` |

Cada fila revalora **la misma cartera anterior** cambiando un factor adicional. Una contribución es el VP de la fila menos el VP de la fila anterior.

| Escenario | Valor completo, COP | Contribución, COP |
| --- | ---: | ---: |
| BASE: cartera y mercado del 01/09, 90 días | 557.291,97 | — |
| THETA: fecha 02/09, mercado anterior, 89 días | 496.549,97 | −60.742,00 |
| DELTA_PYG: además spot actual 4.020 | 2.477.514,32 | +1.980.964,35 |
| RHO_COP: además curva COP actual 11% | 3.349.723,71 | +872.209,39 |
| RHO_USD: además curva USD actual 4,5% | 2.884.340,50 | −465.383,21 |
| BASE_SPREAD: además base y spread actuales | 2.890.026,00 | +5.685,50 |
| NUEVOS_OTROS: cartera actual y mercado actual | 2.890.026,00 | 0,00 |

```text
VP anterior = 100.000 × [4.000/(1,04)^(90/365) − 4.050/(1,10)^(90/365)]
            = 557.291,970659 COP
PyG Banking = VP actual − VP anterior
            = 2.890.026,000726 − 557.291,970659
            = 2.332.734,030067 COP
```

La suma sin redondear de las seis contribuciones es exactamente el cambio total. `NUEVOS_OTROS` reúne altas y cambios de cartera o eventos no explicados en los pasos anteriores; no permite afirmar que todo ese importe sea margen comercial. El orden de atribución importa: las interacciones se asignan al factor que se incorpora después. No son derivadas multiplicadas por shocks.

#### Crédito y liquidación

El ajuste acumulado `A` se obtiene de la diferencia entre los controles IFRS y Banking de `PORTAFOLIO`; el importador acumula esa diferencia diaria. `CVA_DVA = A_actual − A_anterior`. Ejemplo didáctico adicional: `A_anterior=−20.000`, `A_actual=−25.000`: crédito diario `−5.000` y PyG IFRS `2.327.734,03 COP`. Esta atribución de crédito sigue siendo una fuente externa; el motor no estima exposición futura ni probabilidad de incumplimiento.

Al vencimiento, el payoff firmado es `q × N × (fixing_vencimiento − K)`. Para NDF pagadero en COP, ese importe queda como cuenta y después como flujo realizado. Para NDF pagadero en USD, el motor divide por el fixing de vencimiento y convierte la cuenta a COP con la TRM mientras permanece pendiente. Al pagar, congela la conversión con el fixing de cumplimiento.

Ejemplo: compra USD 100, strike 3.000, fixing de vencimiento 3.100: payoff COP `100 × 100 = 10.000`; cuenta USD `10.000/3.100 = 3,225806`. Con TRM de cumplimiento 3.120, flujo COP `10.000 × 3.120/3.100 = 10.064,52`. Si después la TRM pasa a 3.300, el flujo liquidado registrado en Forward permanece en 10.064,52; su variación diaria posterior es cero. La exposición posterior en efectivo pertenece a Caja. Para delivery el motor utiliza el equivalente neto `q × N × (TRM − K)` mientras está pendiente, y la tasa de cumplimiento al liquidar.

### 6.2. Producto NOVADOS del book SWAPS

#### Método de cámara

Se importa del mismo maestro FX con clasificación SWAPSNOVADO. Su precio y valor antes de vencimiento son:

```text
F_cámara = TRM × [(1+rCOP)/(1+rUSD)]^τ
VP_cámara = q × N × (F_cámara − K)
```

El valor de cámara **no lleva descuento final**. Tampoco incorpora la base implícita ni el spread del Forward bilateral. No se debe aplicar a Novados el VP descontado del producto Forward. En los insumos normalizados actuales IFRS = Banking para Novados; el importador fija su ajuste acumulado de crédito en cero siguiendo el libro.

#### Ejemplo numérico

Con la misma operación y los mismos cambios de TRM y curvas del ejemplo anterior:

```text
F anterior = 4.000 × (1,10/1,04)^(90/365)
VP anterior = 100.000 × (F anterior − 4.050) = 570.544,08 COP
F actual = 4.020 × (1,11/1,045)^(89/365)
VP actual = 100.000 × (F actual − 4.050) = 2.958.679,24 COP
PyG Banking = 2.958.679,237966 − 570.544,077290 = 2.388.135,16 COP
```

| Escenario | VP, COP | Contribución, COP |
| --- | ---: | ---: |
| BASE | 570.544,08 | — |
| THETA | 508.224,93 | −62.319,14 |
| DELTA_PYG | 2.535.766,06 | +2.027.541,12 |
| RHO_COP | 3.436.056,87 | +900.290,81 |
| RHO_USD | 2.958.679,24 | −477.377,63 |
| BASE_SPREAD | 2.958.679,24 | 0,00 |
| NUEVOS_OTROS | 2.958.679,24 | 0,00 |

Los totales se calculan con precisión completa; sumar las contribuciones impresas puede diferir un centavo. El tratamiento actual mantiene el payoff al vencimiento y cumplimiento, sin una ingesta separada de llamados diarios de margen o flujos de variación de la cámara. Para una conciliación operativa completa se debe verificar que el contrato de fuente entregue la valoración y los eventos que corresponden a esta convención. En el libro real revisado no existen operaciones SWAPSNOVADO; el ejemplo y las pruebas con operaciones activas validan que el motor puede producir un importe distinto de cero.

#### Por qué no se deben mezclar dos formas de registrar la liquidación diaria

Como ejemplo conceptual de un contrato con ajustes diarios en efectivo, una compra de 100 USD cuyo precio de referencia pasa de 4.100 a 4.112 produce `100×12 = 1.200 COP` de variación. Hay dos representaciones posibles si la fuente y los eventos son coherentes:

| Representación | Cálculo del mismo resultado |
| --- | --- |
| Nivel acumulado contra una referencia fija K=4.000 | Nivel anterior 10.000; actual 11.200; diferencia 1.200 COP. |
| Valor reiniciado a cero tras cada liquidación | VP posterior al ajuste anterior 0; VP posterior al ajuste actual 0; efectivo recibido durante el intervalo 1.200: PyG `0−0+1.200`. |

Sumar la diferencia de los niveles acumulados **y** el mismo efectivo de variación produciría 2.400 y duplicaría el resultado. El modelo Novados actual calcula la variación de su nivel contra el strike; todavía debe integrarse y conciliarse el tratamiento real de ajustes de cámara. Este ejemplo explica el principio de registro, no establece una regla contractual CRCC.

### 6.3. Producto SWAPS del book SWAPS

#### Qué calcula hoy y qué depende de otra fuente

La identidad económica es `PyG Banking = ΔVP Banking + pagos netos recibidos`. Una recepción de cupón tiene signo positivo; un pago realizado, negativo. Se aplica por Trade ID y luego se suma. El VP debería proceder de la valoración de los flujos remanentes de cada contrato, utilizando calendarios, proyecciones, descuentos y condiciones contractuales. **La implementación actual recibe los VP ya calculados**: no reconstruye esos flujos ni recalcula curvas de cada Swap.

El importador toma VP Banking, VP IFRS y Payments de los bloques diarios de `SWAP`; recibe THETA, DELTA_PYG, DELTA_OTRAS, RHO_USD, RHO_COP, RHO_DTF, RHO_IPC, RHO_OTRAS y TRADING de `GRIEGAS SWAP!L:T`, procedentes del Informe Libro de Swaps. Son contribuciones monetarias externas, no sensibilidades a las que el motor aplique un shock. El control total se calcula por separado de su suma:

```text
PyG_B = Σ(VP_B,actual − VP_B,anterior + pago)
Δcrédito = Σ[(VP_I,actual − VP_B,actual) − (VP_I,anterior − VP_B,anterior)]
Δrecuponing = nivel_actual − nivel_anterior
CVA_DVA mostrado = Δcrédito + Δrecuponing
PyG_IFRS = PyG_B + CVA_DVA
EPSILON = PyG_B − suma(factores monetarios externos)
```

El campo `CVA_DVA` agrupa hoy crédito y recuponing, por lo que no debe interpretarse todo su importe como crédito puro. La evidencia conserva `CVA_MERCADO` y `RECUPONING` por separado. El importador define el nivel de recuponing como `PYG Recuponing!C − B`; su significado y fuente primaria requieren confirmación.

#### Cómo sería la valoración propia por flujos — pendiente de implementar

En un IRS de una moneda que recibe tasa fija y paga variable, sin intercambio de principal, la estructura básica es:

```text
Cupón fijo_j = nominal_j × tasa fija × fracción de año_j
Cupón variable_j = nominal_j × tasa proyectada o fijada_j × fracción de año_j
VP = Σ_j descuento(t,pago_j) × (cupón fijo_j − cupón variable_j)
```

Una tasa ya fijada debe venir del fixing histórico; una tasa futura proviene de la curva de proyección del índice. Para una tasa simple de un periodo, `F(t;T0,T1) = [P_proy(t,T0)/P_proy(t,T1) − 1]/α`. La curva de descuento puede ser distinta de la de proyección según contrato y colateral. La regla concreta de DTF, IPC, IBR, SOFR u otro índice no se reemplaza por una misma tasa genérica: requiere su convención contractual.

Ejemplo conceptual, **no implementado como motor Swap nativo**: IRS COP que recibe 8% nominal simple y paga una tasa variable, nominal COP 100.000.000, con dos cupones pendientes y fracción de año 0,25 en cada uno. No hay pago durante el día observado. Se dan las tasas proyectadas y los descuentos como entradas didácticas:

| Flujo | Tasa variable anterior | Descuento anterior | Tasa variable actual | Descuento actual |
| --- | ---: | ---: | ---: | ---: |
| Cupón 1 | 7,0% | 0,980 | 7,2% | 0,981 |
| Cupón 2 | 7,5% | 0,960 | 7,8% | 0,961 |

```text
Cupón fijo de cada fecha = 100.000.000 × 0,08 × 0,25 = 2.000.000
Variables anteriores = 1.750.000 y 1.875.000
VP anterior = (2.000.000−1.750.000)×0,980 + (2.000.000−1.875.000)×0,960
            = 245.000 + 120.000 = 365.000 COP
Variables actuales = 1.800.000 y 1.950.000
VP actual = (2.000.000−1.800.000)×0,981 + (2.000.000−1.950.000)×0,961
          = 196.200 + 48.050 = 244.250 COP
PyG = 244.250 − 365.000 + 0 pagos = −120.750 COP
```

La subida de tasas proyectadas aumenta los pagos variables y reduce el valor de recibir fijo. Un motor completo volvería a valorar estos mismos flujos en escenarios sucesivos de fecha, divisas y curvas para obtener sus contribuciones propias. Para un Swap de monedas debe valorar cada pata en su moneda, incluir intercambios de principal cuando apliquen y convertir coherentemente a COP con las curvas, bases y divisas de su contrato. Este ejemplo de IRS no especifica esas otras estructuras ni sustituye sus convenciones. Hoy Risko recibe `365.000` y `244.250` como VP externos y calcula su diferencia; la construcción de esos VP es la ampliación pendiente.

#### Cómo se obtendría Rho desde esos flujos, paso a paso

Para aislar la contribución de curvas en el IRS didáctico, mantengamos fecha, nominales, cupones fijos y eventos constantes. Primero cambiaremos las proyecciones variables y después los factores de descuento:

| Paso conceptual | Cálculo | Nivel COP | Contribución COP |
| --- | --- | ---: | ---: |
| Base | `250.000×0,980 + 125.000×0,960` | 365.000 | — |
| Solo proyección actual | `200.000×0,980 + 50.000×0,960` | 244.000 | −121.000 |
| Además descuento actual | `200.000×0,981 + 50.000×0,961` | 244.250 | +250 |
| Total de curvas | `244.250−365.000` | | **−120.750** |

La proyección empeora la posición porque aumenta los pagos variables. El descuento de este ejemplo mejora ligeramente el valor de los flujos netos positivos porque sus factores suben. Esta tabla separa proyección y descuento para enseñar el mecanismo; **no es un desglose nuevo disponible hoy en el tablero Swap**.

Si se invierte el orden, actualizar primero el descuento de los flujos anteriores da `250.000×0,981 + 125.000×0,961 = 365.375`, contribución +375. Después actualizar proyección lleva a 244.250, contribución −121.125. La suma vuelve a ser −120.750, pero cada parte cambia: muestra concretamente por qué debe fijarse el orden de atribución.

Para un Swap de monedas, una atribución Delta nativa tendría que conservar los flujos y curvas del escenario y cambiar solo las cotizaciones utilizadas para convertir las patas a COP. Rho USD cambiaría la curva o conjunto de curvas USD definido por metodología; Rho DTF/IPC cambiaría los insumos del índice correspondiente según sus reglas de proyección. No basta con multiplicar todo el nominal por el cambio de una tasa: primero hay que identificar qué pagos cambian, sus fechas, moneda y descuento. Ese desarrollo sigue pendiente en el producto Swap; los nueve factores actuales llegan del reporte externo.

#### Ejemplo con cupón, crédito y recuponing

| Entrada de una operación | Anterior, COP | Actual, COP |
| --- | ---: | ---: |
| VP Banking | 100.000.000 | 99.000.000 |
| VP IFRS | 99.500.000 | 98.300.000 |
| Ajuste IFRS − Banking | −500.000 | −700.000 |
| Nivel de recuponing | 50.000 | 70.000 |

Durante el día se recibe un cupón de **3.000.000 COP**:

```text
PyG Banking = 99.000.000 − 100.000.000 + 3.000.000 = +2.000.000
PyG IFRS antes de recuponing = 98.300.000 − 99.500.000 + 3.000.000 = +1.800.000
Δcrédito = −700.000 − (−500.000) = −200.000
Δrecuponing = 70.000 − 50.000 = +20.000
CVA_DVA mostrado = −200.000 + 20.000 = −180.000
PyG IFRS final = 2.000.000 − 180.000 = +1.820.000 COP
```

Mirar solo el cambio de VP mostraría una pérdida de un millón, omitiendo el cupón. Si el VP descendiera exactamente por el cupón recibido, el PyG sería cero: es el traslado de valor del contrato a efectivo, no una ganancia nueva.

Supónganse los siguientes factores enviados por el informe:

| Factor | COP |
| --- | ---: |
| THETA | 300.000 |
| DELTA_PYG | 800.000 |
| DELTA_OTRAS | 20.000 |
| RHO_COP | 400.000 |
| RHO_USD | 100.000 |
| RHO_DTF | 150.000 |
| RHO_IPC | 0 |
| RHO_OTRAS | 30.000 |
| TRADING | 100.000 |
| Suma explicada por la fuente | 1.900.000 |
| EPSILON calculado | 100.000 |
| Banking total | 2.000.000 |

El residual representa `100.000/2.000.000 = 5%`. Su límite configurable actual es 7%, junto con la tolerancia absoluta en COP: se marca DIFERENCIA si `abs(EPSILON) > max(abs(Banking) × 7%, tolerancia_COP)`. Un residual inferior al umbral no prueba que la atribución sea económicamente correcta; también deben comparar los controles disponibles y revisar las advertencias de origen.

Si un Trade ID anterior desaparece del corte actual, el motor exige un cierre explícito en lugar de inventar la liquidación. Con pagos diarios requiere intervalos de un día calendario. Existe soporte de pagos acumulados para obtener su cambio, pero la atribución por factores Swap sigue siendo diaria: para MTD se necesitan todos los intervalos. En la importación del libro, Payments vacío se trata como cero con advertencia, reproduciendo una convención del Excel todavía pendiente de validar con Payments Report.

### 6.4. Producto CAJA del book SWAPS

#### Inventario, trading y compras/ventas del día

Sean `Q0` saldo USD anterior; `B` compras USD; `V` ventas USD; `kb` precio medio de compra; `kv` precio medio de venta; `S0` y `S1` las TRM anterior y actual. Los precios medios se obtienen dividiendo el movimiento total COP por el movimiento total USD de cada lado.

```text
Q1 = Q0 + B − V
DELTA_INTERDAY = Q0 × (S1 − S0)
TRADING = min(B,V) × (kv − kb)
DELTA_INTRADAY = (B−V) × [S1 − (kb si B≥V; kv si B<V)]
```

El control de inventario exige `Q1 = Q0+B−V` con tolerancia absoluta de 0,01 USD. Un movimiento COP sin monto USD o una tasa de negociación faltante no se interpreta como cero. La separación trading/intradía usa precios medios agregados; no identifica un emparejamiento FIFO de cada operación.

#### Fondeo diario

Usa el saldo final USD `Q1` y TRM actual. FTP COP y ajuste COP se combinan multiplicativamente como tasas efectivas anuales; FTP USD y ajuste USD se suman y se prorratean por 360:

```text
rCOP_total = (1+FTP_COP) × (1+ajuste_COP) − 1
Fondeo_COP = −Q1 × S1 × [(1+rCOP_total)^(1/365) − 1]
Fondeo_USD = Q1 × S1 × (FTP_USD + ajuste_USD) / 360
COSTO_FONDOS = Fondeo_COP + Fondeo_USD
PyG Banking = DELTA_INTERDAY + TRADING + DELTA_INTRADAY + COSTO_FONDOS
```

Con saldo USD positivo, el término COP representa costo y el USD ingreso bajo esta convención; con saldo negativo se invierten. El código no capitaliza una tasa USD nominal como si fuera efectiva anual. El mismo PyG se muestra en IFRS porque esta Caja no incorpora ajuste de crédito.

#### Ejemplo numérico

Saldo anterior USD 100.000; TRM anterior 4.000 y actual 4.020. Compra USD 25.000 a 4.005 y venta USD 10.000 a 4.010. FTP COP 12% EA, ajuste COP 1% EA, FTP USD 4% y ajuste USD 0,5%.

```text
Compras COP = 25.000 × 4.005 = 100.125.000
Ventas COP = 10.000 × 4.010 = 40.100.000
Saldo final = 100.000 + 25.000 − 10.000 = 115.000 USD
Delta interday = 100.000 × (4.020 − 4.000) = +2.000.000 COP
Trading = 10.000 × (4.010 − 4.005) = +50.000 COP
Delta intraday = 15.000 × (4.020 − 4.005) = +225.000 COP
PyG antes de fondeo = +2.275.000 COP
rCOP_total = 1,12 × 1,01 − 1 = 13,12% EA
Fondeo COP = −115.000 × 4.020 × [(1,1312)^(1/365) − 1] = −156.168,53 COP
Fondeo USD = 115.000 × 4.020 × (0,04+0,005)/360 = +57.787,50 COP
Costo de fondos neto = −98.381,03 COP
PyG Banking = PyG IFRS = +2.176.618,97 COP
```

Se puede comprobar el PyG antes de fondeo con una segunda identidad que no usa la descomposición:

```text
Saldo_final × TRM_actual − saldo_anterior × TRM_anterior − compras_COP + ventas_COP
= 115.000 × 4.020 − 100.000 × 4.000 − 100.125.000 + 40.100.000
= 2.275.000 COP
```

La fuente es `CAJA SWAP`: saldo en F; compras/ventas T:W y Y:AB; tasas AL, AM, AP y AQ. El cálculo nativo corrige el paréntesis de fondeo COP de la columna AO: el `−1` queda dentro del factor diario. La diferencia documentada frente al Excel de referencia es +1 COP por día para el motor corregido; no se añade un ajuste compensatorio.

### 6.5. Reproducibilidad y límites del ejemplo

`ejemplos_swaps.py` reconstruye todos estos valores, compara las fórmulas de Forward y Novados contra la función nativa y verifica Swap y Caja con importes conocidos. Usa únicamente datos sintéticos; no requiere abrir el libro real y no modifica sus insumos. El escenario adicional de crédito Forward y el ejemplo corto de liquidación son cálculos manuales ilustrativos, separados del cuadro principal de escenarios.

La descripción corresponde al motor actual, no a una certificación de cierre productivo. La conciliación del libro SWAPS real del 08/09/2026 continúa en DIFERENCIA, con diferencias de universo Swap, referencias Forward cacheadas, residual Forward y convención de fondeo ya documentadas en `integracion_libro_swaps.md`. Persisten dependencias de VP, factores, pagos, crédito y recuponing externos. La reconstrucción histórica parte del maestro mensual disponible al corte, por lo que debe revisarse la integridad de altas, bajas y eventos.

## 7. Consolidación: de productos a book y de días a MTD

### 7.1 Ejemplo pequeño de los siete resultados

Este es un ejemplo adicional de consolidación, distinto de las carteras de los capítulos de producto. Corresponde al corte sintético **31/08/2026 → 01/09/2026** usado en el [dashboard de ejemplo del repositorio](../../../ejemplos/pyg/Dashboards/PyG/2026-09-01/pyg.html). Aquí las curvas FX son cero y las opciones están vacías a propósito; el ejemplo de opciones vivas del capítulo 5 sí produce todas sus contribuciones.

| Book | Producto | Banking COP | Ajuste COP | IFRS COP |
| --- | --- | ---: | ---: | ---: |
| OPCIONES | OPCIONES | 0 | 0 | 0 |
| OPCIONES | FORWARD | 2.000 | −2 | 1.998 |
| OPCIONES | CAJA | 20.000 | 0 | 20.000 |
| **Subtotal OPCIONES** | | **22.000** | **−2** | **21.998** |
| SWAPS | FORWARD | 2.000 | −2 | 1.998 |
| SWAPS | NOVADOS | 200 | 0 | 200 |
| SWAPS | SWAPS | 15 | −2 | 13 |
| SWAPS | CAJA | 150 | 0 | 150 |
| **Subtotal SWAPS** | | **2.365** | **−4** | **2.361** |
| **TOTAL** | | **24.365** | **−6** | **24.359** |

Los dos Forward son compras distintas de 100 USD con cambio de spot de 3.100 a 3.120: `100 × 20 = 2.000 COP` en cada book. El Novado compra 10 USD y aporta `10 × 20 = 200`. Caja OPCIONES conserva 1.000 USD sin operaciones: `1.000 × 20 = 20.000`. Caja SWAPS usa el ejemplo corto de compras 50/ventas 80 del capítulo 5 y aporta 150. El Swap tiene VP Banking `1.000 → 1.010` y pago `5`, por lo que aporta `1.010 − 1.000 + 5 = 15`; su ajuste pasa de −100 a −102 y no cambia recuponing.

El total Banking se obtiene sumando los siete Banking. El ajuste se suma una sola vez: `−2−2−2 = −6`. IFRS es `24.365−6 = 24.359`. **No se suman Banking e IFRS entre sí.** Los subtotales y el total de la tabla son presentaciones de las mismas filas, no nuevas contribuciones.

Al filtrar solo producto FORWARD, el tablero puede sumar los dos books: Banking `4.000`, ajuste `−4`, IFRS `3.996`. Para revisar uno de los motores hay que filtrar también el book. Si se selecciona una sola griega, los KPI representan esa selección; no deben interpretarse como el total sin filtros del producto.

### 7.2 Diario y MTD

Con el calendario vigente, un corte DIARIO 02/09/2026 compara 01/09→02/09. Un MTD 02/09 requiere dos intervalos: 31/08→01/09 y 01/09→02/09. Para MTD 08/09 se necesitan el ancla 31/08 y los ocho cierres de septiembre.

Ejemplo independiente de dos días:

| Día | Banking COP | Ajuste COP | IFRS COP |
| --- | ---: | ---: | ---: |
| 1 | +1.000 | −20 | +980 |
| 2 | −300 | +5 | −295 |
| **MTD al 2** | **+700** | **−15** | **+685** |

```text
Banking MTD = 1.000 − 300 = 700
Ajuste MTD = −20 + 5 = −15
IFRS MTD = 980 − 295 = 685 = 700 − 15
```

Los diarios se guardan como diarios; no se suman a la vez filas diarias y filas MTD. El acumulado se construye al consultar el alcance. Aunque una identidad de niveles pueda telescopar entre extremos, la atribución por factores requiere la cadena diaria para conservar los cambios de mercado, cartera y eventos de cada intervalo.

`CALENDARIO` es la configuración activa. El coordinador también conoce `HABIL_CO`, pero **Swap y Caja SWAPS exigen intervalos de un día calendario**. Cambiar a hábiles no habilita saltar sábados, domingos o festivos en esos motores. Tampoco se rellena automáticamente un día faltante con cero.

### 7.3 Controles de consistencia histórica

Antes de consolidar se comprueba:

1. Que estén todos los productos habilitados del book y todos los intervalos solicitados.
2. Que la fecha anterior de cada resultado sea la esperada.
3. Que todos los resultados procedan de la versión de motor configurada.
4. Que los productos de un mismo book/fecha usen exactamente el mismo snapshot, verificado con SHA-256.
5. Que el snapshot actual de un día coincida con el snapshot anterior del siguiente.

Por ejemplo, si se corrige el snapshot del 1 de septiembre después de ejecutar Forward pero antes de ejecutar Caja, no basta con que ambos archivos se llamen igual. Los hashes distintos impiden mezclarlos. Hay que recalcular los productos afectados y los intervalos que usan ese snapshot: 31/08→01/09 y 01/09→02/09, si están dentro del alcance.

### 7.4 Qué se guarda en SQLite

| Tabla | Contenido y clave |
| --- | --- |
| `tbl_pyg_calculos` | Resultado diario completo en JSON; clave fecha/book/producto. Conserva escenarios, componentes, controles, fuentes y versión. |
| `tbl_pyg_diario` | Contribuciones monetarias; clave fecha/book/producto/componente/vista. |
| `tbl_pyg_ejecuciones` | Evidencia de cada corrida, identificador, fecha de ejecución y contenido. |

La fila de contribución tiene este contrato:

```text
FECHA | FECHA_ANTERIOR | BOOK | PRODUCTO | COMPONENTE | VALOR_COP
VISTA | TIPO | ESTADO | PERIODO
```

`VISTA` es `Banking` o `CVA/DVA`; `PERIODO` almacenado es `DIARIO`. Banking e IFRS se derivan; no se guardan como otras filas de atribución que luego puedan sumarse por accidente. Tampoco se admiten RHO agregado y RHO_COP/RHO_USD simultáneos dentro del resultado de un mismo producto.

Una corrida completa se calcula y valida antes de persistir; las escrituras de esa corrida comparten una transacción. Un reproceso sustituye solo fecha/book/producto de su alcance, evitando duplicados. La creación del HTML ocurre después del guardado: un fallo al generar el tablero no implica que se haya deshecho una persistencia ya completada.

## 8. Conciliación, diagnóstico y publicación

### 8.1 Tres comprobaciones diferentes

| Comprobación | Qué demuestra | Qué no demuestra |
| --- | --- | --- |
| Identidad interna | Suma de componentes = Banking; Banking + ajuste = IFRS | Que la cartera o la metodología sean correctas. |
| Comparación con controles | Coincidencia con las referencias suministradas y reconocidas | Independencia de origen de esas referencias, ni validación de componentes sin referencia. |
| Conciliación funcional | Revisión de fuentes, convenciones, eventos y resultados reales | No se obtiene automáticamente por pasar las dos anteriores. |

El control total `PYG_BANKING` debe existir para poder obtener conciliación `OK`. Además, todos los componentes reconocidos que vengan como control deben estar dentro de la tolerancia absoluta configurada, actualmente **2 COP**. Un control no reconocido por el motor no se convierte automáticamente en una validación adicional. Si solo se entregó el total Banking, un `OK` no prueba por separado cada griega o el ajuste de crédito.

En SWAPS, el cálculo del total por operación y la suma de factores se hacen por vías separadas, pero VP, factores y controles pueden depender del mismo libro o sistema fuente. La independencia aritmética no equivale a independencia de origen.

### 8.2 Estados

| Estado | Interpretación |
| --- | --- |
| `PRELIMINAR` | Etiqueta del resultado de esta versión, incluso si la conciliación es OK. |
| Conciliación `OK` | Controles disponibles reconocidos dentro de tolerancia y controles adicionales del motor satisfechos. |
| Conciliación `DIFERENCIA` | Algún control no coincide, o el residual Swap excede el límite. |
| Conciliación `SIN_REFERENCIA` | Falta el control total Banking; puede existir cálculo válido sin referencia. |
| Calidad `ADVERTENCIA` | Dependencia o convención que requiere revisión; no necesariamente bloquea publicar por sí sola. |
| Calidad `NO_INCLUIDO` | Falta un complemento, por ejemplo fondeo OPCIONES; su ausencia no equivale a un cero validado. |

El residual Swap bloquea `OK` cuando:

```text
abs(EPSILON) > max(0,07 × abs(PyG Banking Swap), 2 COP)
```

Con Banking 2.000.000 y residual 100.000, el cociente es 5% y no excede 140.000. Si el residual fuera 200.000, excedería el umbral. Si Banking es cero, el control absoluto sigue funcionando; el cociente no se calcula dividiendo por cero.

### 8.3 Cómo investigar una diferencia

| Síntoma | Revisión concreta |
| --- | --- |
| Diferencia muy grande en el primer día del mes | Ancla, primas/liquidaciones anteriores y mismo inicio de período al valorar ambos extremos. |
| PyG inesperado al vencimiento | Fecha de fixing, modalidad, moneda, persistencia CXC y fecha de cumplimiento. |
| Resultado cambia por aproximadamente la TRM | Posible confusión entre USD y COP o falta de conversión. |
| Rho muy diferente de la hoja auxiliar | Tasas continuas frente a efectivas, bases 365/360, plazo vencimiento/cumplimiento, base y orden de escenarios. |
| Nuevos/otros grande | Altas, bajas, modificaciones, primas y eventos; no asignarlo íntegro a trading sin revisarlos. |
| Swap cae en un pago de cupón | Comprobar que el pago entra con signo correcto y no queda omitido ni duplicado. |
| Caja falla en saldo | Verificar compras/ventas, movimientos de cumplimiento, saldos firmados y eventos de efectivo. |
| Total coincide pero residual Swap es grande | Revisar factores externos; el residual se calcula para visibilizar lo no explicado. |
| Faltan productos o hashes no coinciden | Recalcular el alcance y los intervalos que comparten el snapshot corregido. |
| Portada actual, cálculo de hoja antiguo | Revisar fechas por hoja y valores cacheados; importar no recalcula Excel ni macros. |

### 8.4 Publicación en el portal

El servicio vuelve a consolidar desde SQLite para la fecha, book y período elegidos. Regenera el HTML de ese resultado y, por defecto, exige conciliación `OK`. Esta condición no elimina las advertencias ni cambia la etiqueta PRELIMINAR.

```text
Dashboards/
  PyG/
    dashboard.json
    AAAA-MM-DD/
      pyg.html
      publicacion.json
```

`publicacion.json` registra el hash y tamaño del HTML, corte, período, books, fecha inicial, fuentes, versión de motor y estado de conciliación. El portal conserva su contrato existente y presenta el archivo publicado.

La documentación y el dashboard sintético incluidos en GitHub son material de entrega. **Subirlos a GitHub no equivale a publicar un cierre productivo en la carpeta de red.** El cierre real revisado sigue bloqueado por sus diferencias de conciliación.

## 9. Estado real de la implementación y trabajo pendiente

### 9.1 Lo observado en el libro SWAPS aportado

Estas cifras son evidencia de la revisión del archivo de referencia, **no los datos de los ejemplos de estudio**. Corte de portada: 08/09/2026. El original se conserva y no se ejecutaron sus macros.

| Hallazgo documentado | Consecuencia |
| --- | --- |
| Las hojas Forward y Novados guardan cálculos del 01/09 aunque la portada dice 08/09. | El mercado fechado y las celdas calculadas deben revisarse por separado. |
| El filtro agregado FX_ESTRAT del Swap terminaba en fila 1033, mientras el total llegaba a 1921. | Una operación fuera del universo queda en el resumen; aplicar el filtro completo explica 22.451.760,10 COP de diferencia del día 8. |
| Banking Forward nativo MTD: 1.741.170.600,83 COP; reporte: 1.756.110.106,54 COP. | La diferencia de 14.939.505,71 COP coincide con el épsilon acumulado del libro; no se incorpora como ajuste para forzar igualdad. |
| Paréntesis del fondeo COP en la fórmula AO de Caja. | La corrección produce +1 COP/día frente al libro: +8 COP en el acumulado revisado. |
| Universo SWAPSNOVADO vacío. | El cero del corte real no valida todavía la metodología con Novados activos. |

El detalle y las fuentes de esos hallazgos están en [Integración del libro SWAPS](integracion_libro_swaps.md). La conciliación real continúa en `DIFERENCIA`.

### 9.2 Pendientes por producto y por flujo

| Alcance | Falta resolver para completar la validación o independencia del cálculo |
| --- | --- |
| Opciones | Snapshots reales y aceptación de smile, delta de superficie, primas por emisión, descuento a cumplimiento, CXC y liquidación. |
| Forward OPCIONES | Conciliar curvas continuas, fixing `tff`, modalidad/moneda, eventos y trazabilidad por operación. El contrato actual no exige Trade ID en esta hoja. |
| Caja OPCIONES | Fuente de fondeo/ajustes y puente automático a saldo actual; hoy no verifica ese puente ni integra automáticamente eventos de los otros productos. |
| Forward SWAPS | Resolver residual frente al reporte y eventos históricos; spread histórico propio, pues la importación reutiliza el spread observado del libro. |
| Novados SWAPS | Cartera activa real, precios y variación diaria de cámara, pagos, multiplicadores y contrato de fuente. No inferir liquidación diaria completa a partir de un valor sin descuento. |
| Swap | Fuentes primarias de pagos, VP y recuponing; motor por flujos/curvas; factores nativos y conciliación de universos. Payments vacíos hoy heredan cero con advertencia. |
| Caja SWAPS | Conciliar fuente de movimientos y aceptar la corrección de fondeo y la convención de saldo final. |
| FX_ESTRAT | Mapear sus archivos DORA/Summit y su metodología; habilitar solo después de probar sus productos con datos propios. |
| Histórico y eventos | Confirmar altas, bajas, liquidaciones, primas y conservación de la cadena al cambiar el mes o reprocesar insumos. |
| Posición vs PyG | Existe una ruta de control de posiciones en la configuración, pero el resultado actual devuelve `posiciones_control={}`. No hay una conciliación automática efectiva con posición en esta versión. |

La correspondencia de los flujos entre derivados y Caja merece revisión conjunta: una liquidación traslada valor a efectivo. El derivado conserva su resultado realizado y Caja incorpora la exposición posterior y sus flujos de negociación adecuados. No se debe reconocer como trading de Caja, por segunda vez, el ingreso ya explicado por el derivado.

## 10. Mapa técnico para leer el proyecto

| Archivo | Qué estudiar |
| --- | --- |
| [configuracion.py](../procesos/configuracion.py) | `configuracion`, `fecha`, `intervalos`, `seleccionar_libros`: rutas, fechas y alcance. |
| [opciones.py](../procesos/opciones.py) | `_valor_bsm`, `_volatilidad_cubica`, `revalorar_cartera`, `calcular_pyg_opciones`: precio, eventos y escenarios. |
| [forward.py](../procesos/forward.py) | `fixing_forward`, `revalorar_forward`, `calcular_pyg_forward`: rama OPCIONES y envío a otros books. |
| [caja.py](../procesos/caja.py) | `atribuir_caja`, `calcular_pyg_spot`: identidad de operaciones y complementos OPCIONES. |
| [fx_snapshot.py](../procesos/fx_snapshot.py) | `importar_libro_swaps`, `cargar_par_fx`: extracción del libro y contrato JSON. |
| [fx_motores.py](../procesos/fx_motores.py) | `valorar_fx`, `calcular_fx`, `calcular_swap_fx`, `costo_fondos`, `calcular_caja_fx`: cuatro productos SWAPS. |
| [swaps.py](../procesos/swaps.py), [novados.py](../procesos/novados.py) | Adaptadores de entrada a los motores normalizados. |
| [atribucion.py](../procesos/atribucion.py) | `resultado_producto`: totales, ajuste y comparación con controles. |
| [consolidacion.py](../procesos/consolidacion.py) | `calcular_intervalo`, `guardar_calculos`, `consolidar_calculos`, `sumar`: filas, controles y persistencia. |
| [Servicio PyG](../../../aplicaciones/interfaz_risko/servicios/pyg.py) | `ejecutar_todo_pyg`, `ejecutar_producto_pyg`, `publicar_tablero`: recorrido operativo. |
| [Interfaz PyG](../../../aplicaciones/interfaz_risko/interfaz_pyg.py) | Controles de usuario, tareas y actualización de resultados. |
| [panel_pyg.py](../tableros/panel_pyg.py) | HTML, filtros y totales del tablero. |

### 10.1 Configuración que conviene conocer

Archivo: [pyg.json](../configuracion/pyg.json). Las rutas relativas se resuelven desde la raíz Risko; `RISKO_PYG_CONFIG` permite usar un archivo alternativo.

| Clave | Valor vigente | Sentido |
| --- | --- | --- |
| `version` | `2` | Versión del esquema de configuración. |
| `calculo.version_motor` | `pyg-2.1` | Versión exigida para consolidar cálculos. |
| Snapshot SWAPS `schema_version` | `1` | Versión del contrato JSON de insumos; no es la versión del motor. |
| `calculo.calendario` | `CALENDARIO` | Intervalos de todos los días. |
| `calculo.tolerancia_conciliacion_cop` | `2.0` | Tolerancia absoluta para referencias reconocidas. |
| `calculo.umbral_residual_swap` | `0.07` | Fracción relativa máxima del residual, con piso de tolerancia absoluta. |
| `libros` | SWAPS y OPCIONES habilitados | Fuente efectiva del alcance del coordinador. |
| `publicacion.exigir_conciliacion` | `true` | Impide publicar cortes con DIFERENCIA o SIN_REFERENCIA. |
| `rutas.base_datos` | `datos/pyg/pyg.db` | SQLite del nuevo PyG, separado del flujo de posición. |

El calendario, los criterios de valoración y los controles deben responder a una definición operativa acordada. Cambiar una tolerancia para ocultar una diferencia no resuelve su causa.

### 10.2 Reproducir los ejemplos

Desde la raíz del proyecto, con las dependencias PyG instaladas:

```powershell
.\.venv\Scripts\python.exe proyectos/pyg/documentacion/ejemplos/ejemplos_opciones.py
.\.venv\Scripts\python.exe proyectos/pyg/documentacion/ejemplos/ejemplos_swaps.py
```

Los scripts imprimen JSON con valores sin redondear. No requieren los archivos operativos ni escriben en la base PyG. El ejemplo Swap crea snapshots sintéticos temporales y los elimina al finalizar. Algunas secciones llaman directamente a las funciones de valoración y reconstruyen la secuencia, por lo que no sustituyen un cierre completo a través del servicio ni validan el adaptador de Excel.

Se adjuntan los [resultados OPCIONES](ejemplos/resultados_opciones.json) y [resultados SWAPS](ejemplos/resultados_swaps.json), obtenidos al ejecutar los scripts. Los ajustes de crédito elegidos para los ejercicios y el IRS ilustrativo por flujos son datos o cálculos didácticos identificados; no se presentan como estimaciones de un motor crediticio o de un valorador Swap ya implementado.

La batería de la entrega base obtuvo **36 pruebas PyG aprobadas y 2 omitidas** por falta de datasets externos. Cubrió cálculos monetarios, eventos, signos, consolidación, persistencia, publicación y conservación del XLSM. Las pruebas de posición que dependen de `Herramientas/dashy` no estaban disponibles con esa herramienta en esta copia; ese resultado no debe confundirse con una validación total del proyecto.

## 11. Ejercicios para comprobar la comprensión

Intente resolverlos antes de leer la respuesta.

| Ejercicio | Datos y pregunta |
| --- | --- |
| 1. Forward y signo | Tasas cero. Se venden 1.000 USD a K=4.000. El spot sube de 4.020 a 4.030. Sin eventos: ¿cuál es el PyG? |
| 2. Prima | Se compra una opción cuyo valor inicial es 800 COP y se paga una prima de 800 COP ese día. No cambia el mercado. ¿Qué resultado aporta la nueva operación? |
| 3. CXC USD | Payoff 20.000 COP, fixing 4.000 y cuenta pendiente USD. El spot pasa de 4.000 a 4.040. ¿Cuántos USD son y cuánto cambia su valor COP? |
| 4. Swap y pago | VP pasa de 8.000 a 7.000 COP y se recibe un cupón de 1.000. ¿Hay pérdida? |
| 5. Crédito | Banking diario 900 COP; ajuste de nivel IFRS−Banking pasa de −100 a −140. ¿Cuál es IFRS diario? |
| 6. Caja con neto vendedor | Compras 50 USD a 3.105, ventas 80 a 3.110, cierre 3.120. Sin inventario anterior ni fondeo: ¿trading, intraday y total? |
| 7. Residual | Banking Swap 10.000 COP y factores 9.000. Con límite 7% y tolerancia 2 COP, ¿supera el control? |
| 8. MTD incompleto | Se tienen 31/08→01/09 y 02/09→03/09. ¿Se puede publicar MTD al 03/09? |

### Respuestas razonadas

1. `q=−1`: VP anterior `−1.000×20 = −20.000`; VP actual `−1.000×30 = −30.000`; **PyG −10.000 COP**. Una venta de USD pierde cuando sube el spot, bajo estas condiciones.
2. `VP + prima firmada = 800 + (−800) = 0`. **Resultado inicial cero**. Sumar una prima positiva por error daría 1.600.
3. `20.000/4.000 = 5 USD`; valor actual `5×4.040 = 20.200`. **Variación +200 COP** mientras siga pendiente. Tras liquidar, la conversión del flujo se congela y la exposición posterior corresponde a Caja.
4. `7.000−8.000+1.000 = 0`. **No hay pérdida** en ese intervalo: el valor se trasladó a efectivo.
5. Ajuste diario `−140−(−100)=−40`; **IFRS 860 COP**. No se suma el nivel completo −140 al Banking diario.
6. Trading `50×(3.110−3.105)=250`; intraday `(50−80)×(3.120−3.110)=−300`; **total −50 COP**. Con el saldo anterior de 10 USD del ejemplo previo se añadirían 200 y el total sería 150.
7. Residual `10.000−9.000=1.000`, límite `max(700,2)=700`. **Sí: DIFERENCIA**, aunque los factores más residual sumen exactamente el total.
8. **No**. Falta 01/09→02/09; el programa exige intervalos completos y coherencia de snapshots.

## 12. Fuentes y alcance de las referencias

La descripción de Risko y las cifras de los ejemplos se contrastaron con los archivos de código enlazados y con los scripts adjuntos. Para decisiones de fuente se consultaron `Opciones_FF_V3.py`, el XLSM SWAPS aportado y su análisis, manteniendo las diferencias de la implementación visibles. Los documentos anteriores del repositorio pueden describir un diseño previo; esta guía identifica específicamente `pyg-2.1`.

Como apoyo conceptual, el código oficial de [QuantLib para procesos Black-Scholes y Garman-Kohlhagen](https://github.com/lballabio/QuantLib/blob/master/ql/processes/blackscholesprocess.cpp) muestra la formulación de divisas con tasas doméstica y extranjera. Risko usa sus propias funciones; esta referencia no valida su convención de smile o settlement.

El [motor de descuento de Swaps de QuantLib](https://github.com/lballabio/QuantLib/blob/master/ql/pricingengines/swap/discountingswapengine.cpp) ilustra la valoración de patas a partir de flujos y factores de descuento. El ejemplo por flujos de esta guía explica ese principio, mientras que Risko todavía recibe el VP Swap desde la fuente.

La explicación de [mark-to-market de CME](https://www.cmegroup.com/education/courses/introduction-to-futures/mark-to-market) ayuda a distinguir liquidación diaria y variación de valor. Es una referencia conceptual sobre futuros; **no establece la metodología contractual de CRCC ni valida por sí sola el modelo de Novados implementado**.

Referencias externas consultadas el 10/09/2026. Las convenciones operativas aplicables a cada contrato deben confirmarse en sus fuentes propias y en la conciliación pendiente.

## 13. Inventario exacto de insumos y paquete que se debe entregar

Este anexo responde qué archivos y datos hacen falta para calcular PyG. Se basa en los **campos que realmente lee `pyg-2.1`**, no solo en los nombres de archivos del proceso anterior. Distingue tres etapas que requieren entregas diferentes:

| Etapa | Qué se debe entregar | Qué puede hacer la versión actual |
| --- | --- | --- |
| Calcular con el formato ya integrado | Snapshots OPCIONES XLSX y snapshots SWAPS JSON, o el XLSM SWAPS compatible para importarlos | Ejecutar los motores y generar el cierre local. |
| Conciliar y publicar un corte | Además, controles diarios reconocidos y revisión de las dependencias y diferencias | Comparar resultados; la publicación normal exige conciliación OK. |
| Construir el PyG desde fuentes primarias, sin depender del libro mensual | Reportes de contratos, curvas, mercado, eventos, pagos, saldos, fondeo y valoraciones descritos en este anexo | Requiere completar adaptadores y, para Swap, el valorador por flujos y su atribución nativa. Entregar los archivos no activa funciones todavía inexistentes. |

**No es necesario entregar por duplicado todos los archivos primarios para ejecutar si ya se dispone de snapshots completos y correctos.** Sí son necesarios para trazar y conciliar los datos o para construir esos snapshots de manera independiente.

### 13.1 Paquete mínimo operativo: fechas, nombres y carpetas

Para un corte **DIARIO del 08/09/2026**, con el calendario vigente, se requieren los estados del **07/09 y 08/09**. Para **MTD al 08/09**, se requieren **nueve snapshots por book**: 31/08 y cada fecha del 01/09 al 08/09, incluidos sábado y domingo. No basta el archivo del día 8 y una copia cualquiera del mes anterior.

| Book y forma de entrega | Nombre exacto o patrón esperado | Ubicación local configurada | Contenido |
| --- | --- | --- | --- |
| OPCIONES, anterior | `Dataset Libro de Opciones 20260907.xlsx` | `datos/pyg/insumos/` | Cartera, mercado, saldos y niveles al 07/09. |
| OPCIONES, actual | `Dataset Libro de Opciones 20260908.xlsx` | `datos/pyg/insumos/` | Estado al 08/09, movimientos del día y controles. |
| SWAPS, anterior | `Dataset SWAPS 20260907.json` | `datos/pyg/insumos/swaps/` | Estado normalizado al 07/09. |
| SWAPS, actual | `Dataset SWAPS 20260908.json` | `datos/pyg/insumos/swaps/` | Estado normalizado al 08/09 y sus pagos/factores/movimientos. |
| SWAPS, alternativa de carga | `PYG SWAPS_MES.xlsm`, seleccionado desde la interfaz | La ruta donde se entregue; el importador escribe los JSON en la carpeta anterior | Debe conservar el layout esperado, el ancla y todos los días; no ejecuta macros ni actualiza cálculos guardados. |

Los patrones se configuran en `fuentes.opciones.patron` y `fuentes.swaps.patron`. Las fechas de los datos tienen que coincidir con las solicitadas. El productor debe incluir fecha de corte y origen verificables: un nombre actualizado no convierte una valoración antigua en valoración del día.

El servicio Vector actual ejecuta solamente el flujo `01_Dataset_Book_Opciones`. No ejecuta automáticamente el flujo de reportes primarios ni convierte `ENTRADA2.xlsb` o los archivos Summit a un snapshot nuevo. Para SWAPS, la operación vigente es importar el libro o suministrar directamente el JSON normalizado.

Si los archivos fuente se sobreescriben diariamente, hay que conservar una copia por fecha. Como organización de entrega de fuentes, se puede usar `fuentes_originales/2026-09-08/` y colocar allí cada original. Esa carpeta es una propuesta de archivo histórico; **no reemplaza las rutas y nombres de entrada del motor**.

### 13.2 Matriz de mercado y riesgo: qué necesita cada producto

En esta tabla, «sí» significa insumo económico consumido por el producto. «Común» indica que el cargador lo exige por compartir el snapshot, aunque ese producto no lo utilice en su fórmula. «Externo» significa resultado recibido, no cálculo nativo.

| Insumo | Opciones / OPCIONES | Forward / OPCIONES | Caja / OPCIONES | Forward / SWAPS | Novados / SWAPS | Swap / SWAPS | Caja / SWAPS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TRM de ambos cortes | Sí | Sí | Sí | Sí | Sí | Común para metadatos | Sí |
| Spot compra y venta | No separado | No separado | Tasas negociadas propias | Sí | Bloque FX común; precio usa TRM | No | Tasas derivadas de movimientos |
| Curva COP | Continua | Continua | Común | Efectiva | Efectiva | VP/factores externos hoy | No para valorar caja |
| Curva USD | Continua | Continua | Común | Efectiva | Efectiva | VP/factores externos hoy | No para valorar caja |
| Curva implícita forward | No directa | No directa | No | Sí | No en su fórmula | No directa hoy | No |
| Spread forward por fecha | No | No | No | Sí | Campo de escenario; sin efecto en la fórmula | No | No |
| Superficie de volatilidad | Sí | Común | Común | No | No | No genérica: depende de contratos futuros | No |
| Fixings históricos | `tfd`, según eventos | `tff`, según eventos; `tfd` común | `tfd` común | Según vencimientos/pagos | Según vencimientos/pagos | Incluidos en VP externos hoy | TRM y movimientos |
| FTP COP/USD | No | No | Costo en COP recibido | No | No | No genérico en el motor actual | Sí, tasas y ajustes diarios |
| Nivel IFRS o ajuste recibido | `Opccva` | `Forcva`; `Opccva` común | `Opccva` común; crédito Caja cero | Ajuste acumulado | Ajuste acumulado, cero en importador actual | VP IFRS + recuponing | Crédito Caja cero |

En OPCIONES, el archivo debe contener las seis hojas comunes incluso al ejecutar solo Caja o Forward: `Opciones`, `Resumen`, `Tasas_USD`, `Tasas_COP`, `Superficie_Volatilidad` y `tfd`. Forward añade `Forwards` y `tff`; Caja añade `Caja`. Una cartera de opciones vacía se representa mediante una hoja sin operaciones **pero con sus encabezados obligatorios**. Las curvas y la superficie comunes no pueden estar vacías.

### 13.3 Curvas: nombres, unidades, nodos y transformación

#### 13.3.1 Lo que se debe pedir de cada curva

Para cada fecha y cada curva se necesita: nombre económico de la curva, moneda, fecha de valoración, nodos de plazo en días, valor de cada nodo, tipo de cotización, base de días, forma de capitalización y fuente. Para reconstruir una curva desde instrumentos también se necesitan las cotizaciones y convenciones de esos instrumentos; **el motor actual recibe curvas ya construidas y no hace un bootstrap desde depósitos, swaps o futuros**.

La moneda y capitalización del contrato normalizado no se deducen del formato visual de Excel. Una celda que muestra `12%` debe tener valor numérico `0.12`, no `12`. Los campos de texto `%`, separadores de miles o fechas dentro de una columna de tasa deben normalizarse antes de entregar los datos.

| Curva concreta | Entrada actual | Unidad y convención | Se necesita para |
| --- | --- | --- | --- |
| Cero COP del book OPCIONES | Hoja `Tasas_COP`, columna `Tasas COP` | Tasa continua anual en decimal; tiempo días/365 | Descuento COP de Opciones/Forward y escenario Rho. |
| Cero USD del book OPCIONES | Hoja `Tasas_USD`, columna `Tasas USD` | Tasa continua anual en decimal; tiempo días/365 | Descuento USD y ajuste a cumplimiento de Opciones; Forward. |
| Implícita o devaluación SWAPS | `mercado.implicita`; desde `Tasas!J:X` | Tasa efectiva anual en decimal; tiempo días/365 | Valoración Forward y mantenimiento de su base respecto de COP/USD. No son puntos forward. |
| USD SWAPS | `mercado.usd`; desde `Tasas!Z:AN` | Tasa efectiva anual en decimal | Forward y Novados. |
| COP SWAPS | `mercado.cop`; desde `Tasas!AP:BD` | Tasa efectiva anual en decimal | Forward y Novados. |
| FTP COP | `caja.ftp_cop`, `caja.ajuste_cop` | Tasas efectivas anuales en decimal; cálculo diario /365 | Fondeo de Caja SWAPS sobre saldo final. No reemplaza curva de descuento de derivados. |
| FTP USD | `caja.ftp_usd`, `caja.ajuste_usd` | Tasas anuales prorrateadas /360, en decimal | Fondeo de Caja SWAPS. No es la curva USD de valoración. |

**Todos los nodos de una curva deben corresponder a la misma fecha de corte.** Para Rho se necesitan las curvas de ambos extremos del intervalo; para MTD, las de cada snapshot diario. No se debe usar la curva actual para reconstruir todos los días anteriores.

#### 13.3.2 Layout de curvas OPCIONES

Las dos hojas requieren exactamente estos nombres de columnas:

```text
Tasas_COP: Plazo Inferior | Plazo Superior | Tasas COP
Tasas_USD: Plazo Inferior | Plazo Superior | Tasas USD
```

Ejemplo sintético de bandas de una curva COP continua:

| Plazo Inferior | Plazo Superior | Tasas COP |
| ---: | ---: | ---: |
| 0 | 30 | 0.0800 |
| 30 | 90 | 0.0810 |
| 90 | 365 | 0.0830 |
| 365 | 365 | 0.0850 |

La tasa de cada fila pertenece al **nodo inferior**. Para interpolar dentro de una banda se busca el valor del nodo superior en la fila que tenga ese `Plazo Inferior`. Por ello se debe entregar una banda completa por tramo y una fila de cierre para el último nodo; no basta una tabla con los extremos pero sin la tasa de cada nodo.

Ejemplo a 60 días: se usa la banda 30→90, con tasas 0,081 y 0,083:

```text
r(60) = 0,081 + (0,083−0,081) × (60−30)/(90−30) = 0,082
```

El cargador ordena por `Plazo Inferior`, rechaza inferiores duplicados y superiores menores que inferiores. No certifica la calidad económica de la curva ni exige un conjunto único de tenores para todos los archivos. Se deben suministrar nodos suficientes para el vencimiento máximo y, en Opciones, también para el cumplimiento máximo. El caso de plazo cero se trata en las funciones de valoración; no se debe inferir de él que falta una curva positiva en plazo.

#### 13.3.3 Layout y quince nodos de SWAPS

El JSON usa pares `[plazo_en_dias, tasa_decimal]`. Ejemplo de formato, **curva sintética abreviada y no los valores reales**:

```json
{
  "cop": [[1, 0.10], [30, 0.102], [90, 0.104], [365, 0.108]],
  "usd": [[1, 0.04], [30, 0.041], [90, 0.042], [365, 0.045]],
  "implicita": [[1, 0.0576923077], [30, 0.0585975024],
                [90, 0.0595009597], [365, 0.0602870813]]
}
```

El contrato JSON permite una cantidad variable de nodos. Deben llegar ordenados, con plazo no negativo, sin duplicados y con tasas mayores que −1. La función interpola linealmente en tasa y mantiene el nodo extremo fuera de la cobertura. Que el código pueda extrapolar manteniendo un extremo no demuestra que sea adecuado para una operación muy larga: se debe revisar la cobertura del mercado.

El importador XLSM, en cambio, lee **quince nodos por curva** desde las posiciones del layout. En el libro de referencia se verificaron estos plazos, iguales para las tres curvas:

| Plazo, días | Implícita | USD | COP |
| ---: | --- | --- | --- |
| 1 | J | Z | AP |
| 7 | K | AA | AQ |
| 14 | L | AB | AR |
| 30 | M | AC | AS |
| 60 | N | AD | AT |
| 90 | O | AE | AU |
| 180 | P | AF | AV |
| 270 | Q | AG | AW |
| 360 | R | AH | AX |
| 720 | S | AI | AY |
| 1080 | T | AJ | AZ |
| 1800 | U | AK | BA |
| 2520 | V | AL | BB |
| 3600 | W | AM | BC |
| 5400 | X | AN | BD |

Los plazos están en la **fila 3 de `Tasas`**; las tasas se leen en la fila cuya fecha de columna B coincida con el snapshot, buscada entre las primeras 36 filas. Los encabezados del libro identifican J como `DEVALUACION SUMMIT`, Z como `CURVA USD EFECTIVA` y AP como `TASA COP EFECTIVA`. **El nodo 360 representa 360 días; el motor sigue usando 365 como denominador anual.**

#### 13.3.4 Qué se necesita exactamente de `Curva Forward V2.xlsm`

El archivo se identifica como fuente de mercado en la configuración y en los antecedentes. Su función cambia según el flujo:

| Flujo | Lectura comprobada o documentada | Uso real en esta versión |
| --- | --- | --- |
| Referencia `Opciones_FF_V3.py` | Hoja `Matriz TC`, `iloc[0,2]` con la lectura estándar de pandas: celda C2 bajo ese layout | Obtiene el spot de referencia. No significa que el motor OPCIONES nuevo lea una curva forward de ese archivo. |
| Libro SWAPS, macro histórica `traecurvas_P` | El análisis del libro identifica `CURVAS!A30:AU30` como bloque copiado a `Tasas` | El importador Python lee las tres curvas ya almacenadas en `Tasas`; no abre directamente ese archivo externo ni ejecuta la macro. |
| Motor nuevo OPCIONES | Lee únicamente curvas y TRM del dataset diario | Si se entregan snapshots completos, no necesita abrir `Curva Forward V2.xlsm` para ese cálculo. |
| Adaptador futuro de fuentes SWAPS | Se necesitan copias históricas del archivo y su layout por fecha | Debe confirmar columnas, separadores, unidades y transformación exacta del bloque externo hacia las tres curvas. No se ha implementado ese adaptador. |

Para trabajar desde fuentes primarias, necesito **la versión de `Curva Forward V2.xlsm` de cada fecha**, con `CURVAS` y `Matriz TC`, sus fechas efectivas y valores guardados, además de una descripción de qué significa cada columna. Una copia actual sin historia no basta para reconstruir Rho MTD. La correspondencia completa de `A30:AU30` se debe comprobar contra el archivo fuente; no basta renombrar todo el bloque como «curva forward».

Si el proveedor entrega **outrights** o **puntos forward**, necesito además su escala, spot de referencia, convención bid/ask, fecha valor y fecha final de cada nodo. El motor no acepta indistintamente esos datos como si fueran tasas efectivas:

```text
Si puntos está en COP/USD sin otra escala:
F(d) = S + puntos(d)

Para convertir un outright a la tasa implícita del modelo simple:
r_implícita(d) = [F(d)/S]^(365/d) − 1

Para convertir una tasa efectiva a continua equivalente:
r_continua = ln(1 + r_efectiva)
```

Ejemplo de la transformación, sin spread y con escala explícita: spot `4.000`, puntos `+20 COP/USD` a `30 días`; outright `4.020`. La tasa implícita es `(4.020/4.000)^(365/30)−1`, aproximadamente **0,06256071 = 6,256071% EA**. **No se debe ingresar `20` ni `4.020` en `mercado.implicita`**. Si «20 puntos» representa otra escala o otro tipo de spot, la conversión cambia. La transformación debe validarse en el adaptador de origen, no improvisarse al cargar el JSON.

Tampoco se reemplaza una curva implícita de mercado por `COP−USD` sin más. Esa resta es una aproximación con determinadas convenciones; el motor SWAPS conserva la base de la curva observada respecto a ambas curvas.

#### 13.3.5 Superficie de volatilidad para Opciones

La hoja `Superficie_Volatilidad` necesita estas siete columnas:

```text
Plazo Inferior | Plazo Superior | 10 D PUT | 25 D PUT
ATM | 25 D CALL | 10 D CALL
```

Cada fila corresponde a un nodo de plazo y aporta cinco **volatilidades outright**, positivas y en decimal. Ejemplo de una fila: `30 | 90 | 0.15 | 0.14 | 0.13 | 0.135 | 0.145`. Debe existir también la fila de 90 días para aportar las volatilidades del extremo superior; se sigue la misma convención de bandas de las curvas.

Para usar una superficie primaria necesito identificar fecha, par USD/COP, definición de ATM, definición de delta, tratamiento de prima, day count y unidades. El código itera sobre deltas absolutas `[0.10, 0.25, 0.50, 0.75, 0.90]`, invierte el orden para CALL y usa su ajuste a cumplimiento. Una superficie en **ATM/Risk Reversal/Butterfly** requiere convertir cotizaciones a las cinco volatilidades esperadas con la convención del proveedor; ese convertidor no está implementado. No se deben colocar RR o BF directamente en columnas de volatilidad outright.

#### 13.3.6 TRM, spots y fixings: tres insumos distintos

| Insumo | Dato que necesito | Uso |
| --- | --- | --- |
| TRM de corte | Fecha económica y COP/USD positivo de cada snapshot | Caja, Novados, metadatos y escenarios según producto. |
| Spot de valoración | Valor por lado de compra/venta cuando la fuente SWAPS los diferencia | Forward vivo; no debe confundirse con la tasa pactada de la operación. |
| Tasa pactada o strike | COP/USD contractual por operación | Es parte de la negociación y permanece fija salvo una modificación documentada. |
| Fixing histórico | Fecha exacta a la que corresponde la tasa, valor y convención de etiqueta | Payoff al vencimiento y conversiones posteriores. |
| Tasa de prima | Tasa aplicada al pago/cobro de la prima USD, o fixing de emisión bajo la convención actual | Evita convertir primas viejas con la TRM nueva. |

`tfd` y `tff` tienen columnas `FECHA`, `TRM1`: las fechas deben ser únicas y cada TRM debe ser un número finito y positivo. En `tfd`, después del vencimiento se busca la fecha económica exacta. En `tff`, después de esa fecha se busca la fila del **día calendario siguiente**, conforme a la convención heredada. Por ejemplo, fixing económico del 31/08 se entrega con etiqueta 31/08 en `tfd`, pero 01/09 en `tff`. En el día del vencimiento los motores usan el spot del escenario. El JSON SWAPS etiqueta `mercado.fixings` con la fecha económica exacta, sin el desplazamiento de `tff`.

El histórico tiene que cubrir todos los vencimientos/cumplimientos reconocidos y las emisiones con primas USD sin tasa explícita. `tfd`/`tff` pueden estar vacíos con encabezados cuando no hay ningún evento que los requiera; un fixing necesario ausente no se completa con la tasa más cercana. Debe revisarse también el puente del cambio de mes, no solo los contratos todavía vivos.

### 13.4 Diccionario del snapshot OPCIONES por hoja y producto

Los nombres siguientes son los del lector actual. Cada campo numérico debe ser finito y corresponder a la fecha del snapshot. Las columnas pueden incluir información adicional, pero no sustituir los encabezados obligatorios.

#### 13.4.1. Diccionario de `Resumen`

Los encabezados siguientes son sensibles a su escritura. La hoja debe contener exactamente una fila de datos.

| Campo exacto | Tipo y unidad | Obligatoriedad | Uso concreto |
| --- | --- | --- | --- |
| `TRM` | Número positivo, COP por USD; ejemplo `4000.00`. | En ambos snapshots, siempre. | Spot de valoración y traducción de moneda. Construye el escenario Delta y el PyG del saldo de Caja. No debe confundirse con el strike contractual ni con una tasa de interés. |
| `Opccva` | Importe firmado en COP. | En ambos snapshots, siempre por el cargador común. | Nivel de valor de mercado IFRS de Opciones. El motor calcula el PyG de crédito como la variación de `(nivel IFRS − valor de mercado Banking recalculado)`. No ingresar aquí el PyG diario, ni solamente el ajuste CVA, ni la suma de cartera más primas y liquidaciones. |
| `Forcva` | Importe firmado en COP. | En ambos snapshots al calcular Forward. | Nivel de valor de mercado IFRS de Forward. Se compara con el MTM Banking recalculado para obtener la variación de CVA/DVA. |
| `Cajausd` | Saldo neto firmado en USD. | En el snapshot anterior de cada intervalo que calcule Caja. | Inventario inicial del día. Un saldo `−500000` es una posición corta de USD, no un error. En una cadena diaria se necesita el saldo en cada corte porque será inicial del siguiente. |
| `FECHA` o `Fecha` o `FECHA_CORTE` o `Fecha_Corte` | Fecha. Se recomienda `2026-09-08`. | Opcional en el lector; recomendable para trazabilidad. | Si alguno está presente debe coincidir con la fecha solicitada para el archivo. Si hay varios, todos los presentes se validan. |
| `ValoropcPYG` | Importe histórico de referencia, COP. | Opcional. | Su presencia se registra en un control de calidad; no se usa para calcular el PyG nuevo. |

El motor no reconstruye `Cajausd` del book OPCIONES leyendo todos los pagos de derivados. Lo recibe ya consolidado en `Resumen`. Por eso, además del número, conviene pedir el soporte del saldo: saldo del cierre anterior, compras, ventas, primas, liquidaciones y demás abonos/cargos USD que lo expliquen. Esa conciliación de saldos es un control operativo adicional; no debe presentarse como una comprobación automática ya implementada para este book.


#### 13.4.2. Cartera de Opciones: hoja `Opciones`

Cada fila representa una operación. El formato soportado es una opción FX vanilla europea `CALL` o `PUT`, con nominal USD y strike COP/USD. Un campo adicional de tipo de estructura no convierte al motor en un valorador de barreras, asiáticas, americanas u otras opciones exóticas.

| Campo exacto | Tipo/unidad y ejemplo | Regla | Para qué se necesita |
| --- | --- | --- | --- |
| `Trade Id` | Texto; `OPT-000123`. | Obligatorio, no vacío y único dentro del snapshot. | Identifica la operación para trazabilidad y detalle. Conservar el mismo identificador entre días. |
| `Posición en la opción` | `BUY` o `SELL`. | Obligatorio. | `BUY` multiplica el valor de la opción por `+1`; `SELL`, por `−1`. No reemplaza el signo explícito de la prima. |
| `Tipo de opción` | `CALL` o `PUT`. | Obligatorio. | Define el derecho económico y el payoff. |
| `Fecha de Emisión` | Fecha; `2026-09-08`. | Obligatoria; no puede estar después del corte ni del vencimiento. | Determina si la operación puede estar en la cartera del corte y si su prima pertenece al período. |
| `Fecha de Vencimiento` | Fecha; `2026-12-08`. | Obligatoria. | Determina el plazo de valoración, el vencimiento y la fecha de fixing del payoff. |
| `Fecha de Cumplimiento` | Fecha; `2026-12-10`. | Obligatoria; igual o posterior al vencimiento. | Determina cuánto tiempo queda una cuenta por cumplir y cuándo se convierte en flujo liquidado. En operaciones vivas también afecta el ajuste de descuento entre vencimiento y cumplimiento. |
| `Nominal` | Número no negativo, USD; `1000000`. | Obligatorio. | Escala la valoración y el payoff. No ingresar un nominal COP ni repetir el signo de compra/venta. |
| `Precio de Ejercicio` | Número positivo, COP/USD; `4000`. | Obligatorio. | Strike contractual. Es fijo para una operación existente salvo un evento contractual soportado. |
| `Modalidad Cumplimiento` | `DELIVERY` o `NON DELIVERY`. | Obligatoria. | Distingue entrega física del intercambio de un diferencial; afecta las cuentas por cumplir y el flujo. |
| `Moneda cumplimiento` | `COP` o `USD`. | Obligatoria. | Indica la moneda del diferencial/liquidación. Una cuenta en USD sigue variando con el spot antes de pagarse. |
| `Valor Total Prima` | Importe firmado en su moneda; compra pagada `−20000`, venta cobrada `+20000`. | Obligatorio; cero si corresponde y está sustentado. | Flujo de prima del período. El código suma este importe con su signo: no transforma automáticamente una prima positiva en negativa por ser `BUY`. |
| `Moneda Prima` | `COP` o `USD`. | Condicional: se recomienda entregarla siempre que exista prima. | Evita asumir que la moneda de prima coincide con la moneda de cumplimiento. Se aceptan también `Moneda de la  Prima` —dos espacios entre «la» y «Prima»— y `Moneda de la Prima`. |
| `Tasa Prima` | Número positivo, COP/USD; `3980`. | Obligatoria si la prima USD no nula del período no tiene fixing de emisión en `tfd`. | Convierte la prima USD a COP a una tasa histórica explícita. Si está disponible, tiene prioridad sobre la búsqueda por fecha. |

Si no se entrega una columna de moneda de prima, el lector conserva la convención heredada de usar `Moneda cumplimiento`. Se recomienda no depender de esa inferencia. Si la columna sí existe pero su valor está vacío, ese vacío no debe considerarse una moneda válida.

El reconocimiento de prima vigente usa `Fecha de Emisión`; no consume una columna separada de fecha efectiva de pago de prima. Por tanto, una prima diferida, parcial o renegociada necesita una definición/mapeo adicional antes de afirmar que queda correctamente modelada. Tampoco se consume un libro separado de eventos de cancelación de Opciones: hay que conservar las operaciones y fechas necesarias para explicar primas y liquidaciones del mes. La desaparición de una operación entre snapshots puede terminar en `NUEVOS_OTROS`; ese residuo por sí solo no identifica el motivo.


#### 13.4.3. Forward del book OPCIONES: hoja `Forwards`

No confundir este producto con el Forward del book SWAPS: el formato y las convenciones de tasas difieren. Para OPCIONES se necesitan las ocho columnas siguientes en ambos snapshots, además del mercado común, `Resumen.Forcva` y `tff`.

| Campo exacto | Tipo/unidad | Regla y función |
| --- | --- | --- |
| `Emisión` | Fecha. | Obligatoria; no posterior al vencimiento ni al corte. Permite detectar operaciones nuevas. |
| `Vencimiento` | Fecha. | Obligatoria. Fecha que determina plazo y fixing del diferencial. |
| `Cumplimiento` | Fecha. | Obligatoria; no anterior al vencimiento. Determina permanencia de CXC y liquidación. |
| `Operación` | `COMPRA` o `VENTA`. | Obligatoria. Compra USD tiene signo `+1`; venta, `−1`. |
| `Nominal` | USD no negativos; `1000000`. | Obligatorio. Monto contractual. |
| `T.Forward` | COP/USD positivo; `4050`. | Obligatorio. Tasa forward **pactada en la operación**, no cotización nueva del mercado ni puntos forward. |
| `Modalidad` | `DF` o `NDF`. | Obligatoria. Entrega física o liquidación de diferencias. |
| `Moneda_Cumplimiento` | `COP` o `USD`. | Obligatoria. Moneda de la cuenta/liquidación. |

Se recomienda conservar identificador de operación, contraparte y book en el archivo para auditoría, pero el lector vigente de esta hoja no exige ni concilia un identificador único: su detalle se identifica por índice de fila. Esa diferencia respecto a `Opciones.Trade Id` debe conocerse al revisar altas, bajas y posibles duplicados. Que el archivo sea legible no prueba la integridad de su inventario.

Para un forward vivo, el núcleo calcula `signo × nominal × [spot × exp(−rUSD × plazo/365) − strike × exp(−rCOP × plazo/365)]`. Por eso los inputs económicos son spot, dos curvas, strike, nominal, lado y plazo. Las fechas de cumplimiento, modalidad, moneda y fijaciones son adicionales para cubrir todo el ciclo de vida después del vencimiento. No se usa una curva de puntos forward independiente en este motor OPCIONES.


#### 13.4.4. Caja del book OPCIONES: hoja `Caja`

El motor toma `Cajausd` y `TRM` del snapshot anterior, `TRM` del actual, y exactamente una fila de `Caja` con la fecha actual. Aunque no haya operaciones se debe entregar esa fila con montos cero; una hoja vacía no representa automáticamente un día sin movimientos.

| Campo exacto | Unidad | Obligación y función |
| --- | --- | --- |
| `Fecha` | Fecha del corte. | Obligatoria. Debe existir exactamente una fila seleccionable para esa fecha. |
| `Compras_Monto_USD` | USD no negativos. | Obligatorio. Total de USD comprados del día bajo el filtro del book. |
| `Compras_Tasa` | COP/USD. | Encabezado obligatorio; valor positivo si hubo compras. Tasa promedio ponderada por nominal USD, no media simple de las tasas de los trades. |
| `Ventas_Monto_USD` | USD no negativos. | Obligatorio. Total de USD vendidos del día. |
| `Ventas_Tasa` | COP/USD. | Encabezado obligatorio; valor positivo si hubo ventas. Tasa promedio ponderada por nominal USD. |
| `Costo_Fondos_COP` | COP firmado. | Opcional en el lector, pero necesario para incluir fondeo de este book. Se suma como componente `COSTO_FONDOS`. No es una tasa. |
| `Ajustes_PyG_COP` | COP firmado. | Opcional en el lector, necesario cuando existan ajustes que deban incluirse. Se suma como componente `AJUSTES`. Debe tener soporte externo. |

Si falta fondeo o ajuste, se informa `NO_INCLUIDO`. No se deduce una tasa FTP del archivo de Opciones ni se reconstruye el fondeo desde `PYG.CostoFondos`. Entregar un cero explícito y justificado es distinto de omitir la fuente.

Ejemplo de agregación de compras: `100000 USD a 4000` y `300000 USD a 4020` generan compras totales de `400000 USD`, contravalor `1.606.000.000 COP` y tasa ponderada `4015 COP/USD`. Ingresar la media simple `4010` introduciría `2.000.000 COP` de error en ese contravalor. Se deben conservar los trades primarios que explican el total, la fecha de operación, la moneda, el book y las exclusiones.

Para el PyG, el saldo previo explica `DELTA_INTERDAY = saldoUSD × (spot actual − spot anterior)`. Los flujos del día generan `TRADING = min(compras, ventas) × (tasa venta − tasa compra)` y el remanente `DELTA_INTRADAY = (compras − ventas) × (spot actual − tasa del lado neto)`. Saldos y movimientos son datos distintos: no se debe usar el saldo final como saldo inicial.


#### 13.4.5. Controles de comparación que se deben pedir

La hoja `PYG` tiene una columna `Nombres` y una segunda columna numérica. El motor lee esa segunda columna por posición; no selecciona automáticamente «la columna del último día» de una tabla mensual. El snapshot debe llevar ahí el control diario de su corte, en COP y con el signo correcto. Un control MTD no sirve como control de un intervalo diario.

| Producto | Total Banking necesario para poder declarar `OK` | Desglose adicional que se compara si existe |
| --- | --- | --- |
| Opciones | `PYG_Opc` | `Theta_Opc`, `Delta_Opc`, `Rho_Opc`, `Vega_Opc`, `Nuevos_Opc`. |
| Forward | `PYG_Forward` | `Theta_Forward`, `Delta_Forward`, `Rho_Forward`, `Nuevos_Forward`. |
| Caja | `Caja_Dia` | `Delta_Caja`, comparado contra `DELTA_INTERDAY`. |

Estos controles nunca son insumos para generar la cifra calculada. También conviene solicitar soporte IFRS y ajuste CVA/DVA por fecha/producto, porque un total Banking conciliado no verifica independientemente la separación de crédito. El mensual `PYG_OPCIONES_MES*.xlsb`, hoja `RESUMEN FINAL` rango `C1:H22`, y `GRIEGAS OPC` sirven como referencias operativas adicionales; el motor nuevo no depende de copiar sus resultados para valorar.


#### 13.4.6. Qué fuentes primarias explican estos snapshots

El archivo `Opciones_FF_V3.py` conserva la referencia histórica de construcción del book. Se estudia como código; no se importa ni se ejecuta automáticamente desde la interfaz PyG. Los archivos siguientes permiten reconstruir/conciliar el origen de los datos, pero tenerlos en `datos/pyg/insumos` **no construye por sí solo** el snapshot normalizado.

| Archivo primario/referencia | Ubicación configurada o leída | Qué aporta y qué hace hoy la integración |
| --- | --- | --- |
| `USR_OPT_MANANA_{next_bday_ddmmyy}_000.xls` | Vector: `SUMMITFS001/apl/Internos/GR/FXOPTION_BASIC`; FF_V3 lee la copia en `BDB/INSUMOS`. | Reporte de operaciones de Opciones. Vector configura el sufijo con día hábil siguiente; FF_V3 histórico solicita día/mes/año manualmente. Hay que comprobar la fecha económica del contenido, no sólo el nombre. |
| `USR_OPT_FWD_{ddmmyyyy}_000.xls` | Vector: `SUMMITFS001/apl/Internos/GR/VALORACION_FWD`; FF_V3 lee `BDB/INSUMOS`. | Operaciones, condiciones y valoración externa de Forward del book Opciones. |
| `USR_CAJA_OPT_FUT_{ddmmyy}_000.xls` | Vector: `SUMMITFS001/apl/Internos/GR/REP_CAJA`; FF_V3 lee `BDB/INSUMOS`. | Trades y movimientos que se agregan a compras/ventas y tasas de Caja. |
| `ENTRADA2.xlsb`, hoja `INFOVALMER` | `BDB/ENTRADA2.xlsb`. | FF_V3 lee USD en `A:C`, COP en `E:G`, y superficie en `I:N`, con `skiprows=2`. Lee 18 filas USD/smile y 13 COP; después normaliza nodos. Esas cifras son parámetros del importador histórico, no límites económicos recomendados para un futuro importador. |
| `ENTRADA2.xlsb`, hoja `BASE` | Misma ubicación. | FF_V3 lee fechas en `A` y TRM en `E`, con `skiprows=1`, `nrows=43`; construye `tfd` y `tff` con sus desplazamientos históricos. El nuevo motor recibe las tablas ya construidas y exige fechas exactas. |
| `Curva Forward V2.xlsm`, hoja `Matriz TC` | `Datos Mercado/Curva Forward V2.xlsm`. | FF_V3 toma el spot de `iloc[0,2]` después de `read_excel` con encabezado estándar; corresponde a `C2` en esa lectura. Para este book no lee aquí una curva completa de puntos forward. El motor nuevo recibe ese spot en `Resumen.TRM`. |
| `Insumo tasas.xlsx` | Vector: `2 Jefatura de Compliance de Tesorería/Insumos CT/Tasas`. | Está registrado como «Histórico TRM formada» en el flujo de primarios. No aparece como una lectura directa de los tres motores nuevos ni del FF_V3 revisado. No asumir un mapeo de hojas/columnas que el código no define. |
| `PYG_OPCIONES_MES*.xlsb` | `BDB/OPCIONES/P&G OPCIONES MES`. | Referencia mensual; el flujo configurado la renombra `PYG_OPCIONES_MES_REFERENCIA.xlsb`. No sustituye un snapshot diario. |
| `risko.db` | Base de posiciones publicada; copia prevista en `datos/pyg/insumos`. | Copia prevista para control de posición; hoy no se ejecuta conciliación automática con esa base. No contiene por sí sola las curvas y eventos necesarios para atribuir PyG. |

Los tres reportes Summit históricos terminan en `.xls`, pero FF_V3 los abre como texto (`read_csv`, tabulador, `latin-1`) y después separa campos con `;`. La extensión no prueba que sean Excel binario. Un futuro importador directo debe respetar el formato real, los encabezados y el corte; no se resuelve únicamente cambiando la extensión.

En Caja, FF_V3 filtra `TRADE DATE` por corte, `DmOwnerTable` por `FXSPOT`/`FXOPT_TR`, `Book` por `OPCIONES_FX` y `SettleCcy` por `USD`; diferencia `CCY COMPRA` y `CCY VENTA` y aplica una lista concreta de contrapartes/libros en `NOMBRE DE CLIENTE`. Lee `MONTO VENDIDO` y `MONTO COMPRADO` para formar los contravalores y promedios ponderados. Esos filtros forman parte del alcance económico del book y deben conciliarse al implementar un cargador primario.

El FF_V3 también conserva código de `USR_OPT_NOV_...` y `ENTRADA2.xlsb/NOVADOS`, pero su salida de griegas Novados no constituye un motor completo del nuevo book OPCIONES. No deben confundirse esos archivos de referencia con los Novados habilitados actualmente en el book SWAPS.

**Lo que hace Vector desde la interfaz hoy:** `ejecutar_vector_pyg` invoca exclusivamente `01_Dataset_Book_Opciones` para copiar los snapshots de las fechas requeridas. `vector_pyg.json` también contiene flujos de primarios, referencia mensual y posiciones, pero esa función no los ejecuta. Por tanto, el requerimiento operativo inmediato es disponer de los datasets diarios ya construidos; para eliminar esa dependencia se necesita implementar, verificar y conciliar el mapeo desde cada fuente primaria.

### 13.5 Diccionario SWAPS: JSON, columnas del XLSM y fuentes primarias

Esta sección distingue dos niveles. **Implementado** significa que el código actual lee y utiliza ese dato. **Antecedente del libro** identifica una fuente descrita en el análisis del XLSM; no significa que Python ya abra directamente ese archivo. Esta separación importa: hoy el cálculo SWAPS lee snapshots JSON; el importador permite generarlos desde `PYG SWAPS_MES.xlsm`. Aún se debe sustituir esa extracción por conectores a los insumos primarios y conciliar sus cifras.

#### 13.5.1. Qué entregar para ejecutar hoy

Se necesita un `PYG SWAPS_MES.xlsm` actualizado, guardado después de recalcular Excel, con fecha de corte en `Parametros!A1`, cierre del mes anterior en `PORTAFOLIO!A4` y estados diarios de todas las fechas calendario hasta el corte. El importador usa valores guardados (`data_only=True`), no ejecuta macros ni recalcula Excel. Una celda con fórmula sin resultado guardado no constituye un dato válido. Un archivo cuya portada está actualizada puede conservar cálculos o insumos antiguos en otras hojas: hay que contrastar sus fechas.

El importador crea `datos/pyg/insumos/swaps/Dataset SWAPS AAAAMMDD.json`. Para calcular el 8 de septiembre se requiere, como mínimo, el estado del 7 y del 8; para un MTD al 8 de septiembre se requieren el cierre del 31 de agosto y los estados del 1, 2, 3, 4, 5, 6, 7 y 8 de septiembre. Cada día necesita sus movimientos propios. Los fines de semana no se eliminan: los factores Swap y el fondeo de Caja actualmente se procesan en intervalos calendario de un día.

Un snapshot tiene estos bloques:

| Ruta JSON | Contenido y exigencia |
|---|---|
| `schema_version` | Entero `1`. Obligatorio. |
| `book` | Texto exacto `SWAPS`. Obligatorio. |
| `fecha` | Fecha del estado, formato `AAAA-MM-DD`; debe coincidir con el corte solicitado. |
| `mercado` | TRM, cotizaciones spot, curvas, spread y fixings. Obligatorio para Forward/Novados; la TRM también se valida al abrir cualquier snapshot. |
| `operaciones.FORWARD` | Lista completa de contratos elegibles del estado. Una lista vacía expresa cero contratos; no reemplazar contratos desconocidos por una lista vacía. |
| `operaciones.NOVADOS` | Lista de contratos novados a cámara, con el mismo contrato de campos FX. |
| `credito_acumulado_cop.FORWARD` y `.NOVADOS` | Nivel acumulado del ajuste IFRS menos Banking por producto. El motor usa la diferencia entre estados. |
| `swaps` | Lista de valoraciones Banking/IFRS y pagos por Trade ID. |
| `factores_swap` | Nueve contribuciones monetarias diarias, en COP. |
| `recuponing_nivel_cop` | Nivel del ajuste de valor por recuponing, en COP. Se utiliza su variación entre estados. |
| `caja` | Saldos, movimientos del día y tasas de fondeo. |
| `controles` | Totales de referencia por producto, separados de los componentes calculados. Sin un control Banking disponible no se obtiene una conciliación OK. |
| `calidad` y `origen` | Advertencias, archivo original, SHA-256 y fecha del libro. Aportan trazabilidad; no son factores de PyG. |

Todos los valores financieros deben ser números finitos, sin `NaN`, infinito, textos como `N/A` ni errores de Excel. El JSON no lleva separadores de miles: `1000000`, `0.12`, `3950.25`. Todos los importes finales y factores PyG se expresan en COP. Una tasa decimal `0.12` representa 12%; `12` representaría 1.200% y produciría una valoración económicamente incorrecta aunque fuera un número.

#### 13.5.2. Mercado que comparten Forward y Novados

Los dos estados deben conservar los datos de mercado observados en cada fecha. No sirve sobrescribir la curva anterior con la curva de hoy: se perdería la separación entre Theta, Delta y Rho.

| Campo | Unidad, ejemplo y uso | Lectura implementada en XLSM |
|---|---|---|
| `mercado.trm` | COP por USD; ejemplo `4000.00`. Conversión, fijaciones del corte y precio de cámara de Novados. Debe ser positiva. | `PORTAFOLIO!B`, fila `4 + días desde cierre del mes anterior`. |
| `mercado.spot_compra` | COP por USD. Cotización utilizada para una operación `COMPRA` en el Forward bilateral. | `Tasas!D`, fila cuya fecha de columna B coincide con el estado. |
| `mercado.spot_venta` | COP por USD. Cotización utilizada para una operación `VENTA`. | `Tasas!C`, en esa misma fila fechada. |
| `mercado.implicita` | Lista de pares (15 en la extracción XLSM) `[plazo_días, tasa_efectiva_anual_decimal]`. Es una curva de tasas implícitas, no una lista de precios forward ni puntos forward. | Plazos `Tasas!J3:X3`; tasas de `J:X` en la fila del estado. |
| `mercado.usd` | Lista de pares (15 en la extracción XLSM) de plazo en días y tasa USD efectiva anual decimal. | Plazos `Tasas!Z3:AN3`; tasas de `Z:AN` en la fila del estado. |
| `mercado.cop` | Lista de pares (15 en la extracción XLSM) de plazo en días y tasa COP efectiva anual decimal. | Plazos `Tasas!AP3:BD3`; tasas de `AP:BD` en la fila del estado. |
| `mercado.spread` | Diferencia de tasa anual en decimal aplicada con signo y dividida por dos a la tasa implícita bilateral. Ejemplo: `0.002` = 20 puntos básicos anuales; el semispread es 10 pb. No son 20 COP de puntos forward. | `Forwards!W3`. El importador propaga el valor disponible a todos los estados extraídos; no reconstruye un histórico de spread que el libro no conserva. |
| `mercado.fixings` | Diccionario de fecha exacta a COP/USD: `{"2026-09-07":4000.00}`. Requerido cuando vence o se paga un contrato. | Pares fecha/TRM de `Tasas!B:C`, desde fila 70 hasta 359; se conservan los de fecha igual o anterior al corte y se agrega la TRM del propio corte. |

La fila diaria de `Tasas` se localiza por fecha dentro de las primeras 36 filas, no por el número de fila de `PORTAFOLIO`. En el libro observado la fila de una misma fecha puede ser diferente entre esas hojas.

La interpolación de tasas es lineal entre los plazos en días; fuera del primer o último plazo se mantiene la tasa extrema. Los nodos deben estar estrictamente ordenados, sin duplicados, con plazo no negativo y tasa mayor que -100%. El tiempo de valoración es días calendario hasta cumplimiento dividido por 365.

**Novados:** el valor de cámara implementado utiliza TRM y curvas COP/USD, con precio forward sin descuento del valor del contrato. No utiliza la curva implícita ni el spread para generar ese precio. Sin embargo, hoy comparte el envoltorio de datos del Forward: el flujo de cálculo accede a cotizaciones spot, spread y fixings. Conviene entregar el bloque `mercado` completo incluso cuando solo se ejecuta Novados; no inventar una sensibilidad a la curva implícita cuando el método de cámara no la utiliza.

**Fuente primaria pendiente de conexión directa:** el análisis del libro identifica `Curva Forward V2.xlsm`, hoja `CURVAS`, rango `A30:AU30`, cargado a través de `Parametros!B11`. Python todavía lee las curvas ya distribuidas en `Tasas`. El mapeo exacto de las 47 celdas del origen hacia los tres bloques de 15 nodos debe confirmarse en el archivo primario antes de construir un conector. Si el proveedor entrega outrights o puntos forward, se deben convertir a la convención de tasa implícita requerida, con spot, plazos y capitalización identificados; no se pueden pegar como si fueran tasas.

#### 13.5.3. Forward bilateral del book SWAPS: contratos y eventos

El universo se extrae de `Forwards!A:N`, desde fila 7 hasta la última fila que tiene Trade ID en A. La columna M clasifica: `SWAPS` va a `FORWARD`; `SWAPSNOVADO` va a `NOVADOS`. Se aceptan exclusivamente operaciones cuyo par en E sea `USDCOP`. Los Trade ID no pueden duplicarse, incluso entre las dos clasificaciones durante la importación.

| Campo JSON | Campo del XLSM | Requisito y ejemplo |
|---|---|---|
| `trade_id` | A | Identificador estable y único. Ejemplo `FWD-001`. Mantenerlo entre fechas; no regenerarlo cada día. |
| `tipo` | B | Texto `COMPRA` o `VENTA`; desde la perspectiva del banco. Compra USD lleva signo positivo y venta USD negativo. |
| `emision` | C | Fecha contractual de operación, `AAAA-MM-DD`. No posterior a vencimiento. El importador solo incluye contratos emitidos al corte. |
| `vencimiento` | D | Fecha en que se fija el resultado. Es distinta de cumplimiento cuando hay plazo de liquidación. |
| Par verificado durante la importación | E | Debe ser `USDCOP`; no se guarda un segundo par FX en el contrato normalizado actual. |
| `nominal` | F | Magnitud en USD, no negativa. Ejemplo `1000000`. La dirección no se codifica como nominal negativo. |
| `strike` | G | Forward contractual en COP/USD, positivo. Ejemplo `4050.00`. |
| `modalidad` | H | `SIN ENTREGA`, `NDF` o `NON DELIVERY`; o `CON ENTREGA`, `DF` o `DELIVERY`. Determina tratamiento del resultado y la cuenta por cobrar. |
| `spot_contrato` | J | Spot contractual COP/USD. El importador exige que sea numérico y lo conserva; el motor de valoración actual no lo usa como factor separado ni lo exige en un JSON construido directamente. |
| `cumplimiento` | K | Fecha de pago o liquidación, igual o posterior a vencimiento. |
| `clasificacion` | M | `SWAPS` o `SWAPSNOVADO`; dirige el producto al importar el XLSM. Se conserva como metadata; no es obligatoria en un JSON construido directamente, donde la lista `FORWARD` o `NOVADOS` ya identifica el producto. |
| `moneda` | N | Moneda de cumplimiento `COP` o `USD`. La columna E identifica el par; la N identifica la moneda del pago. No son intercambiables. |

Cliente I y portafolio L forman parte del extracto original, pero no se utilizan como campos de valoración en el JSON actual. Para una futura ingesta primaria conviene conservarlos como trazabilidad, además del book, sistema origen y estado operativo del contrato.

Se requiere el maestro del estado anterior y del actual, incluyendo contratos que vencieron o se liquidaron durante el período. La cartera no debe contener solo contratos vivos de hoy: al eliminar un contrato sin conservar su vencimiento/pago se puede perder el PyG realizado. El importador filtra por emisión y mantiene registros del maestro mensual; ese maestro retrospectivo requiere revisar altas, bajas, anulaciones y modificaciones históricas contra snapshots diarios originales.

Los fixings son **condicionados por eventos**. Antes del vencimiento, el contrato necesita spot y curvas. Desde el vencimiento, requiere la TRM exacta de la fecha de vencimiento. Para NDF pagadero en USD o una operación con entrega que llega a cumplimiento, también se necesita el fixing de cumplimiento para expresar el flujo realizado en COP. Un fixing del día vecino no sustituye al contractual. No se usa la curva forward de hoy para inventar un fixing pasado.

Ejemplo del dato requerido: contrato NDF compra USD 1.000.000, strike 4.050 COP/USD, vence el 7 y paga USD el 9. El 8 se requiere fixing del 7 y TRM del 8 para la cuenta por cobrar en USD; al calcular el día 9 se necesita también la TRM de pago del 9. En estados posteriores se conserva la conversión del flujo a la tasa del 9, para no atribuir otra vez al derivado el movimiento cambiario posterior de la Caja.

**Crédito:** `credito_acumulado_cop.FORWARD` es un nivel acumulado del ajuste externo IFRS menos Banking. El motor calcula `nivel_actual - nivel_anterior`. En la extracción mensual empieza en cero en el ancla y acumula la diferencia diaria de los controles reportados. No debe recibirse un PyG IFRS completo en ese campo: provocaría contabilizar otra vez el componente de mercado.

**Referencia de origen:** `MASCARA FX TOTAL REPORT (5.5-3-8).xls`, hoja `Mapeo Deriva. ESTRAT`, columnas `C:P`, filtro del VBA `Field 12 = "SWAPS"`, carga el maestro `Forwards!A:N`. Esta trazabilidad procede del análisis de macros; el conector directo al archivo de máscara aún no está implementado.

#### 13.5.4. Novados: insumos adicionales y límites de la equivalencia

Se entrega el mismo contrato anterior, separado en `operaciones.NOVADOS`, con clasificación `SWAPSNOVADO`. Deben existir las curvas COP/USD y TRM de cada fecha, estado contractual, vencimiento, cumplimiento y fixings de los eventos. Una lista vacía solo corresponde si no hay contratos novados; en el libro real analizado el universo era vacío y por eso el resultado fue cero.

El método de cámara actual no ingiere un archivo de márgenes diarios, garantías o efectivo de cámara. Tampoco introduce descuento bilateral en el valor de Novados. Si el procedimiento definitivo exige conciliar liquidación diaria de diferencias, se deben entregar los reportes de liquidación de cámara por contrato y fecha, con la metodología de matching correspondiente; su conector no existe todavía. Se debe evitar sumar esos flujos sobre el valor actual sin acordar el tratamiento, para no duplicar resultado.

`credito_acumulado_cop.NOVADOS` existe en ambos estados y se fija en cero en la importación del libro, reproduciendo la convención observada de IFRS igual a Banking. Cero es la convención de esa fuente, no una afirmación universal de que cualquier producto novado siempre tenga ajuste crediticio nulo.

El control externo diario se obtiene de `PORTAFOLIO!R`, fila del día, y se guarda como `controles.NOVADOS.PYG_BANKING`.

#### 13.5.5. Swaps IRS/CCS: valoraciones, pagos y factores externos

El motor actual **no vuelve a valorar cada pata de un IRS o CCS a partir de contratos y curvas**. Calcula el PyG por Trade ID, por separado de los factores con la variación del VP Banking/IFRS que entrega la fuente, más sus pagos. Después atribuye ese total usando factores monetarios externos del Informe Libro de Swaps. Para correr este método hay que entregar ambos grupos de información.

| Campo JSON por registro de `swaps` | Unidad y regla |
|---|---|
| `trade_id` | Identificador único y estable que enlaza maestro, valoración Banking, valoración IFRS y pagos. |
| `banking` | VP neto Banking del contrato al cierre, en COP y con signo económico. Un activo positivo y un pasivo negativo no deben convertirse ambos a valores absolutos. Requerido en ambos estados. |
| `ifrs` | VP neto IFRS del mismo contrato y fecha, en COP, bajo la misma orientación de signo y perímetro. Requerido en ambos estados. |
| `pago_cop` | Flujo neto **del día** por Trade ID, en COP. Positivo cuando lo recibe el banco; negativo cuando lo paga. Campo obligatorio para el estado actual del intervalo diario; un día sin pago debe tener cero confirmado. |
| `pago_acumulado_cop` | Alternativa admitida por el motor para obtener el pago del intervalo por diferencia de acumulados, si está presente consistentemente en los estados. El importador XLSM actual no lo genera. No elimina el requisito de intervalos diarios para los factores Swap. |

Un registro nuevo se compara con VP anterior cero. Si un Trade ID existente desaparece, el motor falla: se necesita un cierre explícito, con VP actual cero cuando corresponda y el pago de liquidación. La desaparición silenciosa no demuestra que no haya PyG.

El maestro proviene de `SWAP!A:G`, desde fila 9: A Trade ID, B cliente, C book, D CCS/IRS, E Trade Date, F End Date y G Customer Group. La extracción actual utiliza A/C/E/F para identificar, filtrar y fechar; excluye `ARBITR_DER`, `FX_ESTRAT` y `FVH` en columna C y omite operaciones todavía no emitidas. La clasificación debe conciliarse con el dato primario: el análisis del VBA también identifica una exclusión FVH en un campo del reporte fuente, y no debe suponerse que todos los sistemas usan esa etiqueta en la misma columna.

La extracción recorre la última fila real con ID, sin limitar el maestro a 1.033 ni a 5.000 filas. El VP del cierre del mes anterior está en H/I. Para el día calendario `d`, el índice de columna Banking es `10 + (d - 1) × 6`, IFRS es la siguiente y Payments la siguiente. El día 1 usa J/K/L; el día 2 P/Q/R; el día 8 AZ/BA/BB. La fecha del bloque se valida en fila 1, columna Banking + 3. No se toman como PyG calculado las columnas cacheadas de resultado: se vuelve a calcular la diferencia de VP y los pagos por contrato.

Cuando ambas valoraciones están vacías y la fecha final del contrato ya pasó, el importador las convierte a cero. Si se trata de un contrato vigente, una valoración vacía es un error. Una celda Payments vacía se convierte a cero siguiendo el comportamiento del Excel, pero deja advertencia: **esto permite estudiar la extracción; no confirma que se haya recibido y conciliado el reporte de pagos**.

Para producir pagos fiables se requiere un reporte con, como mínimo, Trade ID, identificador del evento o flujo, fecha valor, estado de pago, moneda original, importe original con signo, tasa de conversión a COP y monto COP. Cuando una operación tiene varios pagos el día, se deben agrupar sin duplicar eventos. Estas son las especificaciones del insumo pendiente; el JSON actual recibe su neto `pago_cop`. La fuente física exacta de `Payments Report` todavía no está trazada, y los reportes de flujos utilizados para posición no demuestran por sí solos que contengan los pagos realizados necesarios.

##### Los nueve factores obligatorios de Swap

`factores_swap` debe tener exactamente estas claves. Los importes son **contribuciones PyG diarias en COP**, no sensibilidades ni posición en divisa. Por ejemplo, `RHO_COP = 2500000` significa 2,5 millones COP de PyG atribuido al movimiento de tasas COP; no significa un DV01 de 2,5 millones que deba volver a multiplicarse por puntos básicos.

| Campo JSON | Fuente implementada: `GRIEGAS SWAP`, fila `día + 2` |
|---|---|
| `THETA` | L: paso del tiempo. |
| `DELTA_PYG` | M: efecto FX USD. |
| `DELTA_OTRAS` | N: otras divisas, según la agrupación del informe. |
| `RHO_USD` | O: tasas USD. |
| `RHO_COP` | P: tasas COP. |
| `RHO_DTF` | Q: factor DTF. |
| `RHO_IPC` | R: factor IPC. |
| `RHO_OTRAS` | S: otras curvas/tasas. |
| `TRADING` | T: negociación/actividad atribuida por el informe. |

La fecha de `GRIEGAS SWAP!A` en esa fila debe coincidir con el día. El estado del cierre previo puede llevar factores vacíos porque se utilizan los factores del día actual. Se calcula `EPSILON = PyG Banking por VP y pagos - suma de los nueve factores`; ese residual no debe recibirse como una griega adicional ni rellenarse para forzar una conciliación.

La fuente antecedente es `Informe Libro de Swaps AAAAMMDD.xlsb`, hoja `Historico Griegas PyG`, cuya macro copia el bloque del mes a `GRIEGAS SWAP`. Las hojas `MERCADO-BALANCE` y `RIESGOS LIBRO` contienen riesgos/posiciones útiles para control; no sustituyen el histórico de contribuciones monetarias.

##### Recuponing y ajuste de crédito

`recuponing_nivel_cop` representa el ajuste de valor `Fair Value con ajuste - Fair Value`, en COP; el motor agrega su **variación** al ajuste IFRS del intervalo. La extracción usa `PYG Recuponing!C - B`, fila `día + 2`. No se debe entregar en este campo el ajuste PyG diario, porque al restarlo otra vez se transformaría en una segunda diferencia.

La extracción del libro fija el nivel del ancla mensual en cero. Esto exige confirmar que sea la base correcta del ajuste que llega al mes: si existe un nivel previo distinto de cero, se necesita el estado real de cierre anterior en el snapshot normalizado para medir correctamente el primer día. No basta con que haya una cifra de ajuste al corte actual.

El cálculo completo del ajuste todavía depende de una fuente externa. El análisis describe `Ajuste recuponing` con contratos, tasas/índices, VP de patas, rating, curva CVA, próxima fecha de recouponing y ajuste de flujos, pero no identifica una carga primaria diaria completa. Los reportes Banking/IFRS de flujos alimentan posiciones USD; presentan diferencias entre versiones manual y parametrizada del VBA. Antes de automatizarlos se deben definir la regla vigente, la fuente de valores ajustados y el nivel anterior.

#### 13.5.6. Caja del book SWAPS: saldos, movimientos y fondeo

La Caja no necesita una curva forward para su PyG mercado. Necesita saldos USD, compras y ventas efectivas del día, sus contravalores COP, TRM anterior/actual y tasas de fondeo. Curvas y tasas de FTP tienen funciones distintas: el FTP no reemplaza la curva COP/USD de valoración del Forward.

| Campo de `caja` | Unidad y exigencia | Fuente implementada en `CAJA SWAP`, fila del día |
|---|---|---|
| `saldo_usd` | USD con signo; saldo de cierre. Se exige tanto el anterior como el actual. | F. |
| `trm` | COP/USD, positiva; cierre del estado. Debe ser coherente con la TRM común. | Se toma de `PORTAFOLIO!B`, no del valor cacheado de una tasa promedio de Caja. |
| `compras_usd` | USD comprados durante ese día, magnitud no negativa. Cero explícito si no hubo compras. | T + Y. |
| `compras_cop` | COP efectivamente pagados por esas compras, magnitud positiva si hay compras. | U + Z. |
| `ventas_usd` | USD vendidos durante el día, magnitud no negativa. | V + AA. |
| `ventas_cop` | COP recibidos por esas ventas. | W + AB. |
| `ftp_cop` | Tasa anual efectiva decimal COP. Ejemplo `0.12`. | AL. |
| `ajuste_cop` | Ajuste de tasa anual efectiva decimal. Ejemplo `0.005`. | AM. |
| `ftp_usd` | Tasa nominal anual USD, base 360, decimal. Ejemplo `0.0365`. | AP. |
| `ajuste_usd` | Ajuste de tasa USD decimal, sumado a FTP USD. | AQ. |

Los movimientos y las cuatro tasas de fondeo se requieren en el estado actual de cada intervalo; el ancla solo requiere saldo y TRM. El saldo debe cumplir `saldo_actual = saldo_anterior + compras_usd - ventas_usd` con tolerancia de 0,01 USD. No se acepta contravalor COP cuando el monto USD correspondiente es cero. Las tasas promedio se derivan como contravalor COP / monto USD, evitando promediar tasas sin ponderación.

Los bloques T:W y Y:AB se suman. Si se generan snapshots desde fuentes primarias, hay que identificar el origen del segundo bloque y comprobar que no replique movimientos ya incluidos en el primero. Un pago de derivado en USD que entra a la Caja debe reflejarse en el inventario y movimientos de Caja de forma coherente con el cierre del derivado; esta reconciliación no se garantiza copiando saldos aislados.

El motor utiliza el **saldo final** y la TRM del día para fondeo. Combina las tasas COP como `(1 + ftp_cop) × (1 + ajuste_cop) - 1`; no como una suma simple. La tasa USD sí es `ftp_usd + ajuste_usd`. Esta convención se verificó en `CAJA SWAP!AN` y `AR`. El costo COP diario aplica capitalización efectiva con base 365; el componente USD usa base 360. Si no se desea un ajuste, se debe entregar cero expresamente.

La fuente antecedente de movimientos es `REPORTE CAJA LIVIANO`, hoja `TABLA ORGANIZADA!AP4:AS34`, copiada a `CAJA SWAP!T5:W35`. El antecedente de FTP COP es `FTP COP.xlsx`, hoja `Curva COP`, celdas D12/L12/E12, y el de FTP USD `FTP USD.xlsx`, hoja `Curva USD`, D11/E11. El código actual **no abre estos FTP directamente**: consume AL/AM/AP/AQ ya distribuidos en el libro. Por ello, la correspondencia exacta de las celdas fuente a cada tasa/ajuste debe confirmarse al conectar esos archivos, usando las etiquetas y las fórmulas actuales, sin inferirla solo del nombre de una celda.

#### 13.5.7. Referencias para poder cerrar la conciliación

No basta con insumos que permitan obtener un número. Para poder declarar que ese número coincide con la fuente de control se requieren referencias independientes del mismo producto, book, fecha, moneda y perímetro. Se almacenan en `controles.PRODUCTO` y no deben reutilizarse como aporte económico de mercado.

| Control JSON | Extracción actual |
|---|---|
| `controles.FORWARD.PYG_BANKING` | Suma H+I+J+K de `PORTAFOLIO`, fila diaria Banking. |
| Crédito Forward externo | Misma suma H+I+J+K en bloque IFRS menos Banking; bloque IFRS se busca por fecha entre filas 41 y 75. Se acumula para poblar `credito_acumulado_cop.FORWARD`. |
| `controles.NOVADOS.PYG_BANKING` | `PORTAFOLIO!R`, fila diaria. |
| `controles.SWAPS.PYG_BANKING` | `PORTAFOLIO!E`, fila diaria Banking. |
| `controles.SWAPS.PYG_IFRS` | `PORTAFOLIO!E`, fila coincidente del bloque IFRS. |
| `controles.CAJA.PYG_BANKING` | `PORTAFOLIO!T` más `CAJA SWAP!AJ`, fila diaria. Incluye el fondeo reportado. |

La fuente antecedente Forward es `INFORME FWD CONSOLIDADO DD-MM-AA.xlsb`. Su hoja `Macro!C3/C6/C7` contiene fecha/TRM/EUR; `INFORME BOOKS!AK4/AK42` son VP de mercado/internos y `AL4/AL42` PyG de mercado/internos del book SWAPS. `INFORME IFRS` contiene el equivalente IFRS. `BOOKS CONTADO` y `BOOKS NOVADO` contienen las referencias de contado y cámara. La extracción actual lee el destino `PORTAFOLIO`; para un conector directo hay que verificar las celdas específicas vigentes de todas esas hojas.

Los reportes `Cierre_SwapTotalReport_DDMMAA_000.xls` Banking y `Cierre_SwapTotalReport_IFRS_DDMMAA_000.xls` son el antecedente de los VP Swap; el análisis ubica B = Trade ID y BD = `VP_NET_COP`. Son reportes que las macros abren como texto delimitado por punto y coma pese a su extensión `.xls`: no se debe asumir formato Excel binario por el sufijo. Hay que preservar fecha de reporte y clave de operación para cruzarlos con el maestro.

### 13.6 Fuentes adicionales para una valoración Swap propia por flujos

Las tablas anteriores permiten operar el método actual basado en VP y factores externos. Para reemplazarlos por valoración propia, los siguientes datos son requisitos de diseño. Los nombres en esta tabla son **campos propuestos para acordar con el productor**, no columnas que el motor ya esté leyendo.

| Grupo | Información concreta que hay que entregar |
| --- | --- |
| Identificación | `trade_id`, sistema de origen, book, desk, contraparte, estado, versión de operación y tipo de contrato: IRS, CCS, basis u otra estructura definida. |
| Condiciones por pata | `leg_id`, moneda, dirección pagar/recibir, nominal, fechas de inicio/fin, fijo/flotante, índice, tenor del índice, tasa fija, spread contractual y multiplicador cuando aplique. |
| Cronograma | Fecha inicial/final de cada período de devengo, fecha de fixing, fecha de pago, frecuencia, regla de generación, períodos irregulares y amortización del nominal. |
| Convenciones de tasa | Day count por pata, capitalización simple/compuesta, forma de acumular el índice, calendario, ajuste de día hábil, desfase de fixing/pago y reglas de observación si corresponden. No deducirlas únicamente de la moneda. |
| Flujos futuros | Identificador de flujo, trade/pata, tipo de flujo —cupón, principal, amortización, ajuste—, fecha valor, moneda, importe conocido o componentes para proyectarlo y signo. |
| Fixings | Índice, fecha de observación efectiva, valor, unidad y fuente. Un cupón ya fijado no se vuelve a proyectar con la curva nueva. |
| Curvas de proyección | Identificador real de cada curva, moneda/índice asociado, fecha, nodos y representación —tasas cero, factores de descuento o forwards— con su capitalización. Debe existir una asignación explícita de curva a pata/índice. |
| Curvas de descuento | Identificador, moneda, fecha, nodos y factores/tasas; regla contractual o de colateral que decide cuál curva descuenta cada flujo. No asumir que es siempre la misma curva de proyección. |
| Divisas y basis | Tipos de cambio por par y fecha, convención directa/inversa, curva de basis cuando se use y tratamiento de intercambios de principal para CCS. |
| Pagos realizados | Trade ID, identificador de flujo/evento, fecha valor y fecha de registro, estado confirmado/anulado, moneda, importe firmado, tasa histórica de conversión y monto COP. |
| Cambios de contrato | Altas, cancelaciones, terminaciones anticipadas, recouponing, modificaciones de nominal/strike/tasa y su fecha efectiva. Se requiere enlazar la versión anterior con la nueva. |
| Ajustes IFRS | Para mantener el método actual: niveles IFRS comparables y recuponing por fecha. Solo si se decide construir además un motor crediticio: metodología y datos de crédito, recuperación, netting, colateral y exposición necesarios para ese alcance adicional. |

No puedo identificar una curva interna específica de DTF, IPC, IBR, SOFR u otro índice únicamente viendo el nombre de una griega en el resumen. Para cada índice que exista en los contratos necesito el archivo real, la definición de sus nodos y las reglas que ya utiliza el valorador de origen. Una categoría `RHO_IPC` en COP no contiene una curva de inflación ni su historia de índices.

De manera semejante, el reporte de posición de flujos no equivale automáticamente a un reporte de pagos realizados. Necesito distinguir el monto pendiente, el monto efectivamente pagado, los reversos y las fechas: usar todo el cronograma como Payments reconocería cobros o pagos antes de que ocurran.

### 13.7 Qué controles deben acompañar los insumos

Para cada fecha y combinación book/producto, el paquete de conciliación debe identificar:

| Dato de control | Contenido requerido |
| --- | --- |
| Alcance | Fecha económica, hora/estado de cierre, book, producto, moneda, universo y exclusiones. |
| Cartera | Cantidad de operaciones, nominales y lista de Trade ID; identificar altas/bajas/cambios cuando sea posible. Forward OPCIONES todavía no obliga un ID, pero se necesita del origen para una revisión por operación. |
| Valoración | VP Banking e IFRS comparables de ambos extremos, aclarando si incluyen CXC o solo mercado vivo. Para `Opccva`/`Forcva` se necesita mercado vivo conforme al contrato del motor. |
| Eventos | Primas, pagos, vencimientos, liquidaciones y ajustes del intervalo, con signo y soporte. |
| Resultado | Banking diario, ajuste de crédito, IFRS diario y griegas diarias disponibles; separar MTD de DIARIO. |
| Caja | Saldo anterior, movimientos y saldo final en USD; importes COP, fondeo y ajustes con su soporte. |
| Trazabilidad | Nombre y versión del archivo fuente, fecha efectiva y responsables funcionales de explicar una diferencia. Los hashes se registran al preservar snapshots. |

El resultado que se quiere comparar **no debe introducirse como un ajuste arbitrario del motor para lograr coincidencia**. Por ejemplo, un residual Forward del reporte no reemplaza un evento faltante, y una prima cobrada no se convierte en un segundo TRADING si ya está en el resultado de la operación nueva.

La hoja de control del XLSM y las comparaciones diarias son útiles, pero sus resultados pueden proceder del mismo sistema que los VP. Al solicitar un control independiente conviene identificar quién lo produce y a partir de qué datos; el código no puede demostrar esa independencia leyendo únicamente una cifra.

### 13.8 Solicitud concreta de archivos para la siguiente revisión

Este es el paquete que necesito, organizado por propósito. Se debe entregar para ambos cortes de una prueba diaria o para toda la cadena de un MTD.

| Prioridad | Entrega | Detalle mínimo |
| --- | --- | --- |
| 1. Ejecutar OPCIONES | `Dataset Libro de Opciones AAAAMMDD.xlsx` | Todas las hojas y columnas del apartado 13.4; cartera, curvas/smile, fixings, niveles IFRS, Caja y controles por fecha. |
| 1. Ejecutar SWAPS | `PYG SWAPS_MES.xlsm` compatible y completo, o los JSON `Dataset SWAPS AAAAMMDD.json` | Layout del apartado 13.5, ancla, VP Banking/IFRS, pagos, factores, mercado y Caja. |
| 2. Revisar mercado de origen | `Curva Forward V2.xlsm`, `ENTRADA2.xlsb` e histórico de TRM de cada fecha | `CURVAS`, `Matriz TC`, `INFOVALMER`, `BASE`; fecha y convención de cada dato. `Insumo tasas.xlsx` requiere confirmar su layout primario. |
| 2. Revisar carteras OPCIONES | `USR_OPT_MANANA_…`, `USR_OPT_FWD_…`, `USR_CAJA_OPT_FUT_…` | Reportes íntegros con fecha económica identificada y formato real de texto/Excel. |
| 2. Revisar carteras/resultados FX SWAPS | `MASCARA FX TOTAL REPORT (5.5-3-8).xls`, `INFORME FWD CONSOLIDADO DD-MM-AA.xlsb` | Maestro y clasificación, referencias Banking/IFRS, contado y novados del universo SWAPS. |
| 2. Revisar Swap | `Cierre_SwapTotalReport_DDMMAA_000.xls`, `Cierre_SwapTotalReport_IFRS_DDMMAA_000.xls` e `Informe Libro de Swaps AAAAMMDD.xlsb` | VP por Trade ID y contribuciones diarias del mismo corte; no solo posición o DV01. |
| 2. Completar pagos y recuponing | **Fuente de Payments Report por confirmar** y soporte del ajuste de recuponing | Pagos realizados y reversos por Trade ID/fecha; nivel de recuponing anterior y actual, no solo cambio diario. |
| 2. Revisar Caja y fondeo | `REPORTE CAJA LIVIANO`, `FTP COP.xlsx`, `FTP USD.xlsx` y origen del bloque adicional de Caja | Movimientos sin duplicados, saldo previo/final y tasas/ajustes con fecha. Para Caja OPCIONES: costo y ajustes firmados en COP. |
| 2. Revisar Novados activos | Maestro activo y reporte de cámara correspondiente | Precio de referencia, contrato, nominal/multiplicador, moneda, liquidaciones diarias y reglas de registro. El nombre exacto de ese reporte se debe confirmar con el área fuente. |
| 3. Sustituir VP/factores Swap externos | Contratos, cronogramas, curvas por índice/moneda, fixings y eventos del apartado 13.6 | Se necesita implementar el adaptador y el valorador; no es una carga ya disponible en la interfaz. |

Para los nombres con fechas, el formato importa. En las fuentes configuradas de OPCIONES se distingue `USR_OPT_FWD_{ddmmyyyy}_000.xls` de `USR_CAJA_OPT_FUT_{ddmmyy}_000.xls`; `USR_OPT_MANANA_{next_bday_ddmmyy}_000.xls` se identifica por el siguiente hábil, por lo que hay que comprobar qué cierre representa su contenido. En SWAPS, `Informe Libro de Swaps` usa `AAAAMMDD`, y los reportes `Cierre_SwapTotalReport` de referencia usan `DDMMAA`.

Los datos para FX_ESTRAT son otro paquete: no se obtienen cambiando la etiqueta de SWAPS. Harían falta sus propios contratos, mercado, Caja, pagos, FTP, valoraciones y reglas de clasificación. Los flujos de copia que aparecen en la configuración son antecedentes; no constituyen un motor FX_ESTRAT habilitado. `ReporteTitulos_*.csv` queda fuera de los productos actuales, y `EXP.xlsx` no tiene uso confirmado en estos motores.

### 13.9 Ejemplos de errores de entrega que impiden una atribución correcta

| Entrega incorrecta | Entrega que se necesita |
| --- | --- |
| Solo `Curva Forward V2.xlsm` de hoy | Mercado histórico de cada snapshot; curvas COP/USD y, donde aplica, implícita, superficie, spot y fixings. |
| Curva de puntos `20`, tratada como tasa | Identificar escala y convertir con spot/plazo a la tasa requerida; guardar la convención de origen. |
| Tasa EA en la columna continua de OPCIONES | Convertir a tasa continua equivalente o usar una fuente ya normalizada correctamente. |
| Solo nominal y vencimiento del contrato | Incluir dirección, strike, emisión, cumplimiento, modalidad y moneda; Opciones añade CALL/PUT y prima. |
| VP o delta de posición en lugar de PyG por griega Swap | Contribución **diaria en COP** para cada una de las nueve claves. |
| Payments en blanco porque no se tiene el archivo | Reporte de pagos confirmado; cero solo si se verificó que no hubo pago. El cero heredado del importador queda advertido. |
| `Opccva = CVA del día` | Nivel IFRS de mercado vivo en COP del corte. |
| `recuponing_nivel_cop = cambio del día` | Nivel de ajuste anterior y actual; el motor calcula su diferencia. |
| Caja con la media simple de tasas de operaciones | Contravalores COP y montos USD para obtener promedios ponderados. |
| Fórmulas Excel sin valores guardados | Archivo correctamente calculado por su productor y guardado, con fecha verificada. Python no refresca vínculos ni ejecuta sus macros. |

**La entrega inmediata más útil es un par de snapshots completos de OPCIONES y un corte SWAPS con pagos y controles soportados.** Para probar todo el ciclo, el par debe incluir al menos una operación nueva, una prima USD, un vencimiento con cumplimiento posterior y una liquidación. Para validar MTD se necesita además el ancla y todos los días intermedios. Los nombres de fuentes no identificadas, en especial Payments y liquidación de cámara, permanecen explícitamente pendientes; no se ha supuesto un archivo inexistente.
