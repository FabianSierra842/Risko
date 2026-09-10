# Cálculo específico del módulo Spot

## Propósito

Este documento describe únicamente cómo el módulo `Spot` transforma el
`Reporte de Caja` en la posición diaria acumulada por posición de riesgo.

La implementación está en:

```text
proyectos/position_monitor/procesos/spot.py
```

## 1. Fuente diaria

Vector copia el archivo:

```text
\\SUMMITFS001\apl\Internos\GR\REP_CAJA\Cierre_ReporteCaja_DDMMYY_000.xls
```

Aunque termina en `.xls`, el archivo es texto separado por `;`.

Para calcular se usan estos campos:

```text
GeneratedPK
DmOwnerTable
TradeId
Book
Desk
EvType
SettleCcy
Amount
ValueDate
TRADE DATE
```

La fecha del movimiento es `ValueDate` para los books existentes. Para
`SPOT_CLIENTE` se usa `TRADE DATE`. La columna `VALUE DATE` no sustituye
ninguno de esos campos.

## 2. Filtros

Una fila general puede afectar la posición solamente si:

```text
DmOwnerTable ∈ {CONTADO, FXFWD, FXOPT_TR, FXSPOT, MM, NOVADO, SWAP}
SettleCcy = USD
columna de fecha aplicable = fecha de corte
```

La columna aplicable es `TRADE DATE` para `SPOT_CLIENTE` y `ValueDate` para
los demas books.

Las monedas diferentes de USD no producen movimiento directo. `DPMT_TR` queda
excluido del flujo general, pero se admite como excepción de colaterales cuando
cumple simultáneamente:

```text
DmOwnerTable = DPMT_TR
Book = FWD_CLIENTES
EvType ∈ {FEE, INT}
SettleCcy = USD
ValueDate = fecha de corte
```

Esta excepción replica el filtro del libro operativo
`ReporteCaja(con DP).xlsb` y sus movimientos alimentan `FWD_Clientes`.

## 3. Universo de posiciones

La salida siempre contiene las 13 posiciones activas siguientes:

| Posición de salida | BOOK que la alimenta |
|---|---|
| `FWD_Clientes` | `FWD_CLIENTES` |
| `Pos_propia` | `FWD_POSICION`, `POSI_PROPIA` |
| `FX_Estrat` | `FX_ESTRAT` |
| `Cubre_Bac` | `CUBRE_BAC` |
| `Filiales` | `FWD_FILIALES` |
| `Swaps` | `SWAPS` |
| `Renta_Fija_ME` | `RF_ME_TRADIN`, `RF_ME_FV_OCI` |
| `Opciones` | `OPCIONES_FX` |
| `Futuros_FX` | `FUTUROS_FX` |
| `Trading` | `TRADING` |
| `FVH` | `FVH` |
| `FacturasUSD` | `FACTURASUSD` |
| `CFH` | `CFH` |

El mapeo vive en `param_libros.csv`. Dos BOOK pueden terminar en la misma
posición; primero se homologan y luego se suman.

Un BOOK que no aparezca en este mapeo se guarda en el detalle con alerta
`UNKNOWN_BOOK`, pero no afecta la posición oficial.

## 4. Compra y venta por registro

El signo de `Amount` define el movimiento:

```text
si Amount > 0:
    tipo = COMPRA
    monto_usd = Amount

si Amount < 0:
    tipo = VENTA
    monto_usd = abs(Amount)

si Amount = 0:
    tipo = SIN_MOVIMIENTO
    monto_usd = 0
```

Ejemplos:

| Amount | Tipo | Monto que se agrega |
|---:|---|---:|
| `1000000.25` | COMPRA | `1000000.25` en compras |
| `-350000.75` | VENTA | `350000.75` en ventas |
| `0` | SIN_MOVIMIENTO | `0` |

## 5. Agrupación diaria

Después del mapeo, para cada fecha y posición:

```text
COMPRAS_USD = suma de montos clasificados como COMPRA
VENTAS_USD  = suma de montos clasificados como VENTA

MOVIMIENTO_NETO_USD = COMPRAS_USD - VENTAS_USD
```

No se aplica valor absoluto al neto.

## 6. Posición anterior

El proceso busca el último saldo oficial anterior de la misma posición.

### Existe saldo del día anterior

Se usa como `POSICION_ANTERIOR`.

### Existe saldo, pero faltan días calendario

Se crean los días faltantes con:

```text
COMPRAS_USD = 0
VENTAS_USD = 0
POSICION_FINAL_USD = POSICION_ANTERIOR
TIPO_ORIGEN = CARRY_FORWARD
```

Esto también aplica a sábados, domingos y festivos.

### No existe saldo anterior

La posición anterior se toma como cero y se genera
`MISSING_PREVIOUS_POSITION`.

Si tampoco hay movimientos, la posición se muestra así:

```text
POSICION_ANTERIOR = 0
COMPRAS_USD = 0
VENTAS_USD = 0
POSICION_FINAL_USD = 0
TIPO_ORIGEN = INICIAL_CERO
ESTADO = CON_ALERTA
```

Esto garantiza que la tabla inicial muestre las 13 posiciones. El valor cero es
un marcador pendiente, no un saldo aprobado.

## 7. Fórmula final

Para cada posición:

```text
POSICION_FINAL_USD =
    POSICION_ANTERIOR
    + COMPRAS_USD
    - VENTAS_USD
```

La posición final conserva el signo.

Todos los importes se calculan con `Decimal` y no se redondean durante el
proceso.

## 8. Salida real del 03/08/2026 sin posición inicial aprobada

| Posición | Anterior | Compras | Ventas | Neto | Final | Origen |
|---|---:|---:|---:|---:|---:|---|
| `CFH` | 0 | 0 | 0 | 0 | 0 | `INICIAL_CERO` |
| `Cubre_Bac` | 0 | 1.500.000,00000 | 10.487.637,50000 | -8.987.637,50000 | -8.987.637,50000 | `MOVIMIENTOS` |
| `FVH` | 0 | 0 | 0 | 0 | 0 | `INICIAL_CERO` |
| `FWD_Clientes` | 0 | 48.980.672,61000 | 57.099.949,06000 | -8.119.276,45000 | -8.119.276,45000 | `MOVIMIENTOS` |
| `FX_Estrat` | 0 | 310.858,70000 | 0 | 310.858,70000 | 310.858,70000 | `MOVIMIENTOS` |
| `FacturasUSD` | 0 | 0 | 0 | 0 | 0 | `INICIAL_CERO` |
| `Filiales` | 0 | 0 | 0 | 0 | 0 | `INICIAL_CERO` |
| `Futuros_FX` | 0 | 550.000,00000 | 0 | 550.000,00000 | 550.000,00000 | `MOVIMIENTOS` |
| `Opciones` | 0 | 6.500.000,00000 | 8.541.582,35000 | -2.041.582,35000 | -2.041.582,35000 | `MOVIMIENTOS` |
| `Pos_propia` | 0 | 0 | 0 | 0 | 0 | `INICIAL_CERO` |
| `Renta_Fija_ME` | 0 | 0 | 0 | 0 | 0 | `INICIAL_CERO` |
| `Swaps` | 0 | 200.190,48000 | 504.758,89000 | -304.568,41000 | -304.568,41000 | `MOVIMIENTOS` |
| `Trading` | 0 | 599.344,92000 | 599.344,92000 | 0 | 0 | `MOVIMIENTOS` |

Los valores de compras y ventas coinciden con `TABLA ORGANIZADA` del libro
`ReporteCaja(Sin DP).xlsb`. Este ejemplo es anterior a la incorporación de la
excepción de colaterales DP.

### Validación de colaterales del 18/08/2026

El filtro de `ReporteCaja(con DP).xlsb` encuentra 18 movimientos de
`DPMT_TR / FWD_CLIENTES / FEE / USD` para la fecha:

```text
Compras USD =   3.372,40000
Ventas USD  = 489.822,49000
Neto USD    = -486.450,09000
```

Risko obtiene los mismos valores directamente del Reporte de Caja, sin leer ni
modificar el libro auxiliar.

## 9. Ejemplo con posición inicial aprobada

Para `FX_Estrat`, si el Excel registra al 01/08/2026:

```text
POSICION_FINAL_USD = 50.269.423,25732988
```

El 02/08 se crea el carry:

```text
Posición 02/08/2026 = 50.269.423,25732988
```

El 03/08:

```text
Posición anterior = 50.269.423,25732988
Compras           =    310.858,70000
Ventas            =              0
Neto              =    310.858,70000
Posición final    = 50.580.281,95732988
```

## 10. Reemplazo de los ceros iniciales

El archivo propio de Risko
`configuracion/param_posiciones_iniciales_spot.xlsx`, hoja
`Posiciones_Iniciales`, contiene las 13 posiciones y las columnas:

```text
FECHA | POSICION | POSICION_FINAL_USD | ESTADO_PARAMETRO | OBSERVACION
```

Las 13 filas deben tener valor y estado `VALIDADO`. Al usar
`Cargar parámetros Spot`:

1. se registran los saldos aprobados como `EXCEL_INICIAL`;
2. se reemplazan los ceros o saldos anteriores;
3. se crea `CARRY_FORWARD` para días sin movimiento;
4. se recalculan todas las fechas posteriores;
5. se guardan el valor anterior y el nuevo en `tbl_auditoria_spot`.

El flujo es únicamente parámetro XLSX → base. Risko no escribe sobre este
parámetro ni sobre los libros `ReporteCaja(Sin DP).xlsb` o
`ReporteCaja(con DP).xlsb`.

## 11. Tablas resultantes

| Tabla | Contenido |
|---|---|
| `tbl_posicion_spot` | Contrato canónico que consume Position Monitor |
| `tbl_posicion_spot_acumulada` | Anterior, compras, ventas, neto y final exactos |
| `tbl_compras_ventas_spot_book` | Compras, ventas y neto por cada BOOK original, incluidos parametrizados en cero y no mapeados |
| `tbl_movimientos_spot` | Detalle por fila del Reporte Caja |
| `tbl_alertas_spot` | Errores y posiciones pendientes |
| `tbl_ejecuciones_spot` | Archivo, hash, usuario y estado de ejecución |
| `tbl_auditoria_spot` | Cambios de valores por reproceso |

## 12. Regla resumida

```text
Reporte Caja
    → filtrar owner, USD y ValueDate
    → homologar BOOK a una de 13 posiciones
    → separar compras y ventas por signo
    → agrupar por posición
    → buscar posición anterior
    → completar días faltantes
    → posición final = anterior + compras - ventas
    → guardar resumen, detalle, alertas y auditoría
```

`tbl_posicion_spot` conserva solamente la posición final neta homologada y es
la tabla que alimenta el consolidado/dashboard. La tabla secundaria
`tbl_compras_ventas_spot_book` es informativa y no se incorpora al consolidado.
