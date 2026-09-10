# Manual operativo de Position Monitor en RISKO

## Objetivo y alcance

Este manual explica cómo ejecutar, consolidar, validar y publicar Position
Monitor desde la interfaz RISKO. También identifica los archivos que Vector debe
cargar para cada posición y diferencia las dos publicaciones disponibles:

- el **cierre oficial**, que se consolida antes de publicarse; y
- el **preliminar intradía**, que se calcula de forma aislada y se publica
  directamente desde **Ejecutar intradía**.

El botón **Ejecutar cierre** invoca los seis módulos liberados para
la corrida diaria:

1. Spot.
2. Novados.
3. Forward.
4. Renta Fija.
5. Opciones.
6. Swaps.

Renta Fija calcula y guarda `tbl_posicion_renta_fija`, entra al consolidado y
se publica para COP, USD, EUR y UVR. Cubrebonos, NDFTES y PP permanecen ocultos.

## Regla de fecha

- Ingrese la fecha de corte como `dd-mm-YYYY`. Ejemplo: `06-08-2026`.
- La fecha no puede ser futura. El portal habilita sábados, domingos y festivos
  cuando existe una publicación válida para esa fecha.
- En una fecha no hábil, cada producto aplica su propia regla: Spot publica sin
  variación el último acumulado, Novados conserva la última posición disponible,
  Forward usa el archivo cuyo `PARAMETRO FECHA Y` coincide con el corte,
  Opciones conserva su lógica vigente y Swaps usa los cierres exactos Banking e
  IFRS del día.
- El proceso genera y consolida un corte independiente por cada fecha no hábil;
  no arrastra Forward ni Swaps desde el último día hábil.

Ejemplo del puente del 7 de agosto de 2026:

| Fecha | Estado | Tratamiento |
| --- | --- | --- |
| 06-08-2026 | Jueves hábil | Ejecutar y publicar la posición |
| 07-08-2026 | Festivo en Colombia | Ejecutar con las reglas de fecha no hábil |
| 08-08-2026 | Sábado | Recalcular Forward, Opciones y Swaps; arrastrar Novados y Spot |
| 09-08-2026 | Domingo | Recalcular Forward, Opciones y Swaps; arrastrar Novados y Spot |
| 10-08-2026 | Lunes hábil | Ejecutar el nuevo corte |

## Archivos esperados por posición

Vector toma los archivos de sus fuentes oficiales y los copia temporalmente a:

```text
datos/insumos/
```

No copie ni renombre manualmente archivos para simular otra fecha. El botón
**Ejecutar cierre** limpia primero esta carpeta local y vuelve a cargar los
insumos de la fecha seleccionada.

### Forward

Archivos obligatorios Banking e IFRS para la fecha de corte. En día hábil se
espera normalmente:

```text
Cierre_Valoracion_FxFwd_{ddmmyyyy}_000.xls
Cierre_Valoracion_FxFwd_IFRS_{ddmmyyyy}_000.xls
```

Ejemplo para `06-08-2026`:

```text
Cierre_Valoracion_FxFwd_06082026_000.xls
Cierre_Valoracion_FxFwd_IFRS_06082026_000.xls
```

Para sábados, domingos o festivos, Summit puede mantener la fecha de generación
en el nombre y avanzar el sufijo (`_001`, `_002`, `_003`, etc.). RISKO revisa
los archivos de la familia y selecciona únicamente aquel cuyo encabezado
`PARAMETRO FECHA Y` coincida con la fecha solicitada. Después lo copia al nombre
local exacto que consume el cálculo. No se debe escoger el archivo solamente por
su nombre.

Ejemplo para el festivo `07-08-2026`: se usan
`Cierre_Valoracion_FxFwd_06082026_001.xls` y
`Cierre_Valoracion_FxFwd_IFRS_06082026_001.xls`, porque ambos declaran
`PARAMETRO FECHA Y = 07082026`.

Parámetros usados:

```text
proyectos/position_monitor/configuracion/param_rutas.csv
proyectos/position_monitor/configuracion/param_libros.csv
```

Tabla maestra de salida: `tbl_posicion_forward`.

### Novados

Archivo obligatorio:

```text
Cierre_FutureTotalReport_{ddmmyy}_000.xls
```

Ejemplo para `06-08-2026`:

```text
Cierre_FutureTotalReport_060826_000.xls
```

Parámetros usados:

```text
proyectos/position_monitor/configuracion/param_rutas.csv
proyectos/position_monitor/configuracion/param_libros.csv
```

Tabla maestra de salida: `tbl_posicion_novados`.

En una fecha no hábil no se busca otro archivo Summit: se copia a la nueva fecha
la última posición de Novados anterior al corte. Los archivos especiales de
sábado o domingo no se usan mientras esta regla esté vigente.

### Opciones

Archivos obligatorios:

```text
USR_OPT_MANANA_{siguiente_habil_ddmmyy}_000.xls
ENTRADA2.xlsb
Insumo tasas.xlsx
```

El portafolio `USR_OPT_MANANA` corresponde al siguiente día hábil de Colombia,
no necesariamente al día calendario siguiente. Para el corte `06-08-2026`, el
archivo esperado es:

```text
USR_OPT_MANANA_100826_000.xls
```

`Insumo tasas.xlsx` debe contener en la hoja `TRM` un valor `FORMADA` único y no
vacío para la fecha exacta del corte. Si falta esa fecha, el proceso no usa una
TRM anterior como reemplazo.

Parámetro de libros usado:

```text
proyectos/position_monitor/configuracion/param_libros.csv
```

Tabla maestra de salida: `tbl_posicion_opciones`.

Esta lógica no cambia para fines de semana: se utiliza el mismo
`USR_OPT_MANANA` correspondiente al siguiente hábil y el `ENTRADA2.xlsb`
vigente, pero la revaloración se ejecuta con la fecha exacta del corte. Hasta
que exista un histórico de Entrada 2, no se reemplaza este comportamiento.

### Swaps

Archivos obligatorios:

```text
Cierre_SwapTotalReport_Flujos_{ddmmyy}_000.xls
Cierre_SwapTotalReport_IFRS_Flujos_{ddmmyy}_000.xls
```

Ejemplo para `06-08-2026`:

```text
Cierre_SwapTotalReport_Flujos_060826_000.xls
Cierre_SwapTotalReport_IFRS_Flujos_060826_000.xls
```

La fecha interna de valoración de ambos reportes debe coincidir con la fecha de
corte seleccionada.

Para fines de semana también son obligatorios los dos cierres exactos del día.
Swaps se recalcula y vuelve a agruparse; no se conserva la posición del último
día hábil.

Parámetros usados:

```text
proyectos/position_monitor/configuracion/param_rutas.csv
proyectos/position_monitor/configuracion/param_libros.csv
```

Tabla maestra de salida: `tbl_posicion_swaps`.

### Renta Fija

Archivo obligatorio:

```text
ReporteTitulos_{ddmmyyyy}.csv
```

Ejemplo para `06-08-2026`:

```text
ReporteTitulos_06082026.csv
```

Parámetros obligatorios:

```text
proyectos/position_monitor/configuracion/param_rutas.csv
proyectos/position_monitor/configuracion/param_libros.csv
proyectos/position_monitor/configuracion/param_librorf.csv
proyectos/position_monitor/configuracion/param_monedarf.csv
```

Tabla maestra de salida: `tbl_posicion_renta_fija`.

La salida y los workbooks operativos conservan COP, USD, EUR y UVR. En fechas no hábiles se usa el miembro del
último hábil con sufijo `_1`, `_2`, `_3`, etc., cuya fecha interna corresponde
al corte, y se copia al nombre local de la fecha solicitada.

Renta Fija forma parte de **Ejecutar cierre** y también conserva su botón
individual. Ambos caminos actualizan `tbl_posicion_renta_fija` y el consolidado.

### Spot

Spot forma parte de **Ejecutar cierre** y también conserva su botón individual. Su
flujo espera:

```text
Cierre_ReporteCaja_{ddmmyy}_000.xls
Insumo tasas.xlsx
```

También usa:

```text
proyectos/position_monitor/configuracion/param_libros.csv
proyectos/position_monitor/configuracion/param_posiciones_iniciales_spot.xlsx
```

El Excel de posiciones iniciales debe contener la hoja
`Posiciones_Iniciales`. Cuando se requiera crear o reemplazar las anclas del
acumulado, presione el ícono **⚙** situado junto a **Spot** y seleccione
**Cargar / recalcular Spot acumulado**. El cálculo aplica:

```text
posición final = posición anterior + compras USD - ventas USD
```

El nombre del archivo fuente conserva `ReporteCaja`, pero la tabla canónica
publica siempre `PRODUCTO = Spot`. El histórico legado con `PRODUCTO = Caja` se
homologa también como `Spot`.

Tablas principales: `tbl_posicion_spot` y
`tbl_posicion_spot_acumulada`.

En sábados, domingos y festivos no se carga ni procesa un nuevo Reporte de Caja
porque no existe flujo. RISKO toma las posiciones existentes en
`tbl_posicion_spot_acumulada` para la fecha —generadas como `CARRY_FORWARD`— y
las publica sin variación en `tbl_posicion_spot` y en el consolidado del corte.

### Cubrebonos, NDFTES y PP

Estos módulos no se muestran en la interfaz ni se invocan desde **Ejecutar
todo**. Actualmente retornan tablas vacías de control, no tienen archivos de
entrada oficiales, flujo Vector ni cálculo productivo, y se excluyen del
tablero hasta que se implementen, se ajusten al nuevo formato y se liberen sus
flujos.

## Procedimiento completo en la interfaz

### 1. Preparar la corrida

1. Abra RISKO y ubique **Position Monitor**.
2. Escriba la fecha como `dd-mm-YYYY`.
3. Para producción, confirme que **Usar base de pruebas** esté desactivado.
4. Confirme en las fuentes oficiales que existen todos los archivos descritos
   para esa fecha.
5. Cierre CSV o Excel de salida que estén abiertos para evitar bloqueos de
   escritura de las copias operativas.

### 2. Ejecutar las posiciones

1. Presione **Ejecutar cierre**.
2. Espere el mensaje **Cierre completo finalizado**.
3. En día hábil, revise el log y confirme Spot, Novados, Forward, Renta Fija,
   Opciones y Swaps. En fecha no hábil confirme Forward, Renta Fija, Opciones y
   Swaps, y el arrastre de Novados y del acumulado Spot.
4. Confirme que Cubrebonos, NDFTES y PP no fueron invocados por la corrida
   automática.
5. No publique si el log muestra `ERROR`, un archivo faltante, una TRM ausente o
   una fecha interna diferente.

**Ejecutar cierre** realiza estas acciones:

```text
Limpia datos/insumos
  -> Vector carga los archivos de la fecha
  -> resuelve los insumos según la regla hábil/no hábil
  -> calcula los módulos liberados aplicables al corte
  -> guarda las tablas de producto en risko.db
  -> consolida la fecha
  -> aplica el alcance de publicación al construir el tablero
  -> genera el tablero local
```

### 3. Ejecutar el consolidador final

Después de una corrida completa, presione **Consolidar posición**. Este paso
final vuelve a leer las tablas maestras de SQLite, aplica las homologaciones y
refresca:

```text
tbl_posicion_consolidada
tbl_posicion_actual
tbl_posicion_historico
```

La consolidación:

- reemplaza la misma fecha y no duplica posiciones;
- conserva fechas anteriores;
- publica las vistas `Banking` y `CVA/DVA`;
- excluye `IFRS` de las tablas consolidadas publicables;
- lleva a `tbl_posicion_historico` únicamente el último día calendario de cada
  mes.

### Cierre mensual e histórico

La fecha oficial del histórico es siempre el último día calendario del mes, no
el último día hábil. Solo puede quedar una fecha de cierre por mes.

Ejemplos:

| Fin de mes | Fecha histórica | Tratamiento |
| --- | --- | --- |
| Viernes 31-07-2026 | 31-07-2026 | Corrida normal de día hábil |
| Domingo 31-05-2026 | 31-05-2026 | Corrida no hábil; no se guarda además el viernes 29 |
| Festivo 31 del mes | Día 31 | Corrida no hábil con las reglas de cada producto |

Procedimiento:

1. Ejecute el último día calendario mediante **Ejecutar cierre**, aunque sea
   sábado, domingo o festivo.
2. En fecha no hábil, confirme el carry-forward de Spot y Novados, la selección
   de Forward por `PARAMETRO FECHA Y`, la lógica vigente de Opciones y los
   cierres exactos de Swaps.
3. Presione **Consolidar posición**. El corte entra a
   `tbl_posicion_consolidada` y, por ser fin de mes calendario, también a
   `tbl_posicion_historico`.
4. Valide que el histórico contenga la fecha final del mes y no el último día
   hábil anterior.
5. Genere y publique el tablero.

La actualización es idempotente: al corregir y volver a consolidar la misma
fecha, RISKO reemplaza las filas de esa fecha y producto; no agrega duplicados y
no elimina cierres de meses anteriores. Si se reprocesa un mes antiguo,
publique primero ese corte y luego vuelva a consolidar la última fecha operativa
para restaurar `tbl_posicion_actual` al corte más reciente.

### 4. Validar antes de publicar

En **Tabla DB**, cargue cada tabla de producto y luego
`tbl_posicion_actual`. Confirme:

- la única fecha visible en `tbl_posicion_actual` es la fecha seleccionada;
- tanto en día hábil como en fecha no hábil aparecen `Spot`, `Forward`,
  `Novados`, `Titulos`, `Opciones` y `Swap`; en fecha no hábil Spot debe
  coincidir con el último acumulado disponible;
- `Titulos` contiene las monedas COP, USD, EUR y UVR;
- no existen libros vacíos;
- `POSICION` es numérica;
- la moneda y las dimensiones requeridas están informadas;
- las sumas son razonables frente al cierre anterior;
- no aparece la vista `IFRS` en `tbl_posicion_actual`;
- los conteos pueden cambiar diariamente y no deben validarse contra un número
  fijo.

Revise `tbl_alertas_spot` y confirme que Spot no tenga alertas pendientes antes
de publicar.

### 5. Publicar el cierre en el portal RISKO

1. Confirme que **Usar base de pruebas** esté desactivado. Ninguna base de
   pruebas puede publicarse en el portal de producción.
2. Después del consolidador final, presione **Generar tablero** para revisar la
   versión local. Este paso sirve como vista previa.
3. Verifique en el tablero que la fecha de posición sea la seleccionada, que la
   publicación corresponda a cierre y que no aparezcan alertas ni datos de otra
   fecha.
4. Regrese a la interfaz y presione **Publicar en portal**. El botón vuelve a
   generar el tablero desde las tablas oficiales vigentes y luego copia el HTML
   y su manifiesto al portal; por ello siempre debe usarse después de la última
   consolidación o corrección.
5. Espere el mensaje de publicación terminada y revise la ruta informada.
6. Abra **Portal RISKO**, ingrese a **Portfolio Position Monitor** y seleccione
   la fecha publicada. Confirme que el tablero abra, que muestre la fecha de
   posición correcta y que corresponda al cierre oficial.
7. Revise `publicacion.json`. Para un cierre debe registrar `estado = CIERRE`,
   `fecha_posicion_solicitada` igual al corte y `fechas_datos` sin fechas ajenas.
   También conserva usuario, hora, tamaño y hash SHA-256 del HTML.

La copia se realiza sobre la carpeta de la fecha seleccionada. Si durante el día
se publicó un preliminar intradía para esa misma fecha, la publicación del cierre
reemplaza el HTML y `publicacion.json` preliminares. No dé por terminado el
cierre hasta validar en el portal esta sustitución.

En **Posición actual**, la gráfica y su tabla separan la posición por moneda. La
tabla incluye la columna `Moneda` y presenta en el pie un total independiente
para cada moneda visible; COP y USD nunca se suman entre sí. La misma regla se
aplica al pie de la tabla de detalle. Cuando COP y USD están visibles al mismo
tiempo, la gráfica presenta COP en el eje izquierdo y USD en el derecho. Ambos
ejes comparten el mismo cero. En el cierre, sus rangos se relacionan con la TRM
`FORMADA` de la fecha exacta. En el preliminar intradía se usa exclusivamente el
promedio `SETFX` del corte, tanto para Opciones como para la escala COP/USD; ese
flujo no consulta TRM `FORMADA`. La tasa solo calibra la altura comparable de
las barras: las etiquetas, el hover y la tabla conservan cada posición en su
moneda original.

La gráfica de **Histórico** aplica la misma separación y abreviaturas. Si el
universo filtrado contiene COP y USD, cada combinación de categoría y moneda es
una serie distinta: COP usa el eje izquierdo y USD el derecho, con cero común y
escala TRM. Si el histórico disponible contiene una sola moneda, se muestra un
único eje con el título y las abreviaturas de esa moneda.

El universo visible se controla en:

```text
proyectos/position_monitor/configuracion/dashboard_publicacion.json
```

La configuración filtra el tablero actual, el histórico y, por extensión, el
HTML que se copia al portal. No elimina registros de SQLite. Actualmente:

- permite únicamente los books liberados en `allowed_books`;
- incluye `Titulos` y el book `Renta_Fija_ME` de los demás productos;
- excluye `Cubrebonos`, `NDFTES` y `PP` mediante `exclude_products`;
- puede ampliarse cuando Riesgo libere un book o producto; en ese momento se
  debe incorporar también a **Ejecutar cierre** si corresponde.

La publicación separa dos conceptos:

- `fecha_posicion_solicitada`: fecha del corte que verá el usuario;
- `fecha_publicacion`: fecha calendario en que se copió el tablero al portal.

Por eso es válido publicar el 10 de agosto una posición correspondiente al 6 de
agosto, siempre que `fechas_datos` contenga únicamente `2026-08-06`.

## Ejecución y publicación intradía

El intradía es un corte **preliminar** e independiente del cierre oficial. Se
publica únicamente con vista **Banking** para Forward, Novados, Opciones, Swap y
Spot. No incluye Renta Fija, IFRS ni CVA/DVA.

La corrida no actualiza `tbl_posicion_actual`, `tbl_posicion_historico` ni las
tablas oficiales por producto. Tampoco requiere ejecutar **Consolidar posición**,
**Generar tablero** o **Publicar en portal** por separado: el botón **Ejecutar
intradía** carga los insumos, calcula, genera el HTML y publica el preliminar en
una sola operación.

### Archivos intradía

Vector ejecuta el flujo `10_Position_Monitor_Intradia` y busca los siguientes
archivos para la fecha seleccionada:

| Producto | Patrón esperado |
| --- | --- |
| Forward | `USR_Posicion_Fwd_Intradia_ddmmaaaa_*.xls` |
| Novados | `USR_Posicion_Novado_Intradia_ddmmaa_*.xls` |
| Swap operaciones | `USR_Posicion_Swaps_Intraday_ddmmaa_*.xls` |
| Swap flujos | `USR_Posicion_Swaps_Intraday_Flujos_ddmmaa_*.xls` |
| Spot/Caja | `USR_Caja_Intradia_ddmmaa_*.xls` |
| Opciones | `USR_OPT_INTRADIA_ddmmaa_*.xls` |

Opciones también necesita `ENTRADA2.xlsb` para las curvas y la superficie, e
`Insumo tasas.xlsx` para el spot de reproceso.

Cuando hay varias versiones, RISKO elige el sufijo numérico más alto: `_002`
tiene precedencia sobre `_001`, y `_001` sobre `_000`. Un archivo vacío o menor
a 1 KB se considera incompleto y no se selecciona. El nombre, sufijo, tamaño y
hash del archivo elegido quedan registrados para auditoría.

### Reglas del cálculo preliminar

- **Opciones:** obtiene el promedio `SETFX` por el encabezado del reporte y lo
  usa tanto para la revaloración como para calibrar la escala COP/USD del
  tablero. El intradía no consulta TRM `FORMADA`.
- **Spot:** usa un clon aislado de `risko.db` para tomar como ancla la posición
  acumulada del día anterior, sin modificar la base oficial.
- **Novados:** conserva `VALOR SENSIBLE` para operaciones anteriores. Solo en el
  intradía, una operación negociada en la fecha del corte usa el `NOMINAL`
  firmado cuando Summit reporta sensibilidad cero.
- **Forward y Swap:** se construyen con los últimos reportes intradía completos
  elegidos para la fecha.

### Procedimiento en la interfaz

1. Abra RISKO, ubique **Position Monitor** e ingrese la fecha como
   `dd-mm-YYYY`.
2. Desactive **Usar base de pruebas**. El preliminar solo se publica desde la
   base de producción.
3. Confirme que los seis reportes intradía y los insumos adicionales de
   Opciones estén disponibles y completamente generados.
4. Presione **Ejecutar intradía**.
5. Lea el mensaje de confirmación. Debe indicar que se publicará una posición
   preliminar solo Banking, sin IFRS/CVA-DVA y con promedio `SETFX`. Presione
   **Sí** para continuar.
6. Espere el estado **Preliminar intradía publicado**. No cierre RISKO mientras
   Vector, el cálculo o la copia al portal sigan en curso.
7. Revise el log. Confirme los archivos y sufijos seleccionados, los cinco
   productos incluidos, el promedio `SETFX` y la ruta final de publicación. No
   continúe si aparece `ERROR`, un insumo incompleto o una advertencia de
   calidad que no haya sido explicada.
8. Abra **Portal RISKO**, ingrese a **Portfolio Position Monitor** y seleccione
   la fecha. El encabezado debe mostrar **PRELIMINAR INTRADÍA**,
   **Solo Banking · Sin IFRS/CVA-DVA** y el **PROMEDIO SETFX** utilizado.
9. Revise `publicacion.json`: debe indicar `estado = PRELIMINAR_INTRADIA`, vista
   `Banking`, la fecha efectiva del corte, los productos incluidos, las fuentes
   elegidas y los controles de calidad.

### Sustitución por el cierre oficial

El preliminar y el cierre de una misma fecha se publican en la misma carpeta y
con el mismo nombre de HTML. Por eso:

1. Ejecute el intradía antes del cierre oficial.
2. Al finalizar el día, ejecute **Ejecutar cierre**, **Consolidar posición** y
   **Publicar en portal**.
3. Confirme que desaparecieron las marcas de preliminar y que
   `publicacion.json` registra `estado = CIERRE`.

No ejecute ni publique un intradía después del cierre, salvo que exista una
instrucción operativa expresa para reemplazar temporalmente el tablero oficial.

## Salidas y trazabilidad

Fuente maestra de datos:

```text
datos/base de datos/risko.db
```

Soportes e intermedios:

```text
datos/base de datos/risko_auxiliar.db
datos/position_monitor/procesados/
```

Copias operativas y tablero local:

```text
datos/position_monitor/publicados/tbl_posicion_actual.csv
datos/position_monitor/publicados/tbl_posicion_historico.csv
datos/position_monitor/publicados/panel_position_monitor.html
```

Publicación del portal:

```text
Portal Riesgos de Mercado/
  Dashboards/
    Portfolio Position Monitor/
      YYYY-MM-DD/
        portfolio_position_monitor.html
        publicacion.json
```

`publicacion.json` registra las fechas efectivas, usuario, hora, tamaño y hash
SHA-256 del tablero publicado.

## Errores comunes

### Novados muestra un error al separar la fecha

Use `dd-mm-YYYY`; por ejemplo, `06-08-2026`. No use barras en la entrada de la
interfaz para la corrida completa.

### Vector no encuentra un archivo

Revise el nombre exacto y la fecha codificada. No continúe con un archivo de
otro día y no lo renombre para forzar el proceso.

### Opciones no encuentra TRM FORMADA

Revise `Insumo tasas.xlsx`, hoja `TRM`. Debe existir un único valor `FORMADA`
para el corte exacto.

### Swaps rechaza la fecha

La fecha dentro de los archivos Banking e IFRS debe coincidir con el corte y con
el nombre de los archivos.

### Un CSV no se actualiza porque está abierto

Cierre el archivo y vuelva a ejecutar **Consolidar posición**. Revise siempre
SQLite: la base puede haber quedado actualizada aunque la copia CSV estuviera
bloqueada.

### La interfaz no permite publicar

Desactive **Usar base de pruebas**. La base de pruebas no se puede publicar en
el portal de producción.

### El portal no muestra una fecha de fin de semana

Confirme que esa fecha haya sido consolidada y publicada, y que el portal activo
sea la versión 2.1.4 o superior. Una fecha no hábil sin `publicacion.json` válido
permanece deshabilitada.

### El intradía elige un sufijo anterior

Confirme que el archivo de sufijo más alto haya terminado de generarse y pese al
menos 1 KB. Mientras esté vacío o incompleto, RISKO conserva la última versión
completa disponible.

### El portal todavía muestra PRELIMINAR después del cierre

El consolidador no publica por sí solo. Con la base de pruebas desactivada,
presione **Publicar en portal** después de la última consolidación y confirme en
`publicacion.json` que `estado` sea `CIERRE`.

## Lista de chequeo de cierre

- [ ] Fecha escrita como `dd-mm-YYYY` y confirmada como hábil o no hábil.
- [ ] En día hábil están los insumos de Spot, Novados, Forward, Opciones y
      Swaps; en fecha no hábil están los de Forward, Opciones y Swaps.
- [ ] **Usar base de pruebas** desactivado para producción.
- [ ] **Ejecutar cierre** terminó sin errores.
- [ ] **Consolidar posición** terminó sin errores.
- [ ] `tbl_posicion_actual` contiene únicamente la fecha seleccionada.
- [ ] Están los productos aplicables al tipo de fecha; no hay filas IFRS
      publicables y Spot conserva el acumulado en fechas no hábiles.
- [ ] El alcance de `dashboard_publicacion.json` corresponde a los books y
      productos autorizados.
- [ ] Tablero regenerado después del consolidador final.
- [ ] Fecha efectiva del tablero revisada.
- [ ] Publicación terminada y `publicacion.json` revisado.
- [ ] El portal no muestra la marca **PRELIMINAR INTRADÍA** para el cierre.
- [ ] Si es cierre mensual, `tbl_posicion_historico` contiene únicamente el
      último día calendario del mes y no el último hábil anterior.

## Lista de chequeo intradía

- [ ] Fecha escrita como `dd-mm-YYYY`.
- [ ] **Usar base de pruebas** desactivado.
- [ ] Los seis reportes intradía, `ENTRADA2.xlsb` e `Insumo tasas.xlsx` están
      disponibles y completos.
- [ ] Se aceptó la confirmación de publicación preliminar.
- [ ] **Ejecutar intradía** terminó sin errores ni alertas de calidad pendientes.
- [ ] El log confirma los cinco productos, los sufijos elegidos y el promedio
      `SETFX`.
- [ ] El portal muestra **PRELIMINAR INTRADÍA**, solo Banking y sin IFRS/CVA-DVA.
- [ ] `publicacion.json` registra `PRELIMINAR_INTRADIA`, la fecha correcta, las
      fuentes y los controles de calidad.
- [ ] Al cierre del día, el cierre oficial se consolidó y volvió a publicar para
      reemplazar el preliminar.
