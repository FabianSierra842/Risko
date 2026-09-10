# Análisis de Inconsistencias — Lógica de Posiciones Risko

> Nota vigente: este documento conserva hallazgos historicos del flujo anterior
> basado en CSV y conversiones dentro de `consolidacion.py`. Desde julio de
> 2026 la fuente maestra es `datos/base de datos/risko.db` y la consolidacion
> no recalcula `TRM`, `POSICION_COP` ni `POSICION_USD`.

**Versión:** 1.1 — Junio 2026  
**Módulo:** Position Monitor  
**Archivo fuente principal:** `proyectos/position_monitor/procesos/consolidacion.py`

---

## 1. Bug Corregido — TRM: columna incorrecta (VIGENTE vs. FORMADA)

### Descripción
La función `_cargar_trm()` en `consolidacion.py` priorizaba la columna **VIGENTE** sobre **FORMADA**:

```python
# Antes (incorrecto):
columna_valor = "VIGENTE" if "VIGENTE" in trm.columns else "FORMADA"

# Después (correcto):
columna_valor = "FORMADA" if "FORMADA" in trm.columns else "VIGENTE"
```

### Impacto
- La TRM **FORMADA** es la tasa de cierre oficial publicada por el Banco de la República.
- La TRM **VIGENTE** puede ser la tasa intradiaria, que no corresponde al valor de cierre.
- Usar VIGENTE en lugar de FORMADA generaba que las conversiones COP↔USD quedaran con una tasa diferente a la del cierre de mercado, afectando la comparabilidad entre fechas.

### Módulos afectados
`consolidacion.py` → `_cargar_trm()` → todas las conversiones `POSICION_COP` y `POSICION_USD`.

---

## 2. Bug Corregido — UVR: conversión omitida en Renta Fija

### Descripción
Para títulos denominados en **UVR** (Unidad de Valor Real), la lógica anterior en `_enriquecer_posiciones_monedas()` trataba la posición como si ya estuviera en pesos (COP):

```python
# Antes (incorrecto para UVR):
posicion_esta_en_usd = moneda.eq("USD") & producto_clave.ne("TITULOS")
POSICION_COP = posicion   # ← asumía que UVR ya era COP
POSICION_USD = posicion / trm
```

### Comportamiento correcto
La posición de títulos UVR viene del TRADEPL en **UVR nominales**. La conversión correcta es:

```
POSICION_COP = POSICION_UVR × valor_UVR_del_día   (hoja "UVR" de Insumo tasas.xlsx)
POSICION_USD = POSICION_COP / TRM_FORMADA
```

### Nueva lógica implementada
```python
# Correcto (v1.1):
es_uvr = moneda.eq("UVR")
if es_uvr.any():
    uvr_tasa = _asignar_uvr_por_fecha(tabla, logger=logger)
    posicion_cop = posicion.where(~es_uvr, posicion * uvr_tasa)
posicion_usd = posicion_cop / trm
```

### Módulos afectados
`consolidacion.py` → `_enriquecer_posiciones_monedas()` → columnas `POSICION_COP` y `POSICION_USD` para todos los títulos UVR (ej. TES UVR, bonos hipotecarios UVR).

---

## 3. Inconsistencia — Tildes y caracteres especiales en nombres de Book

### Descripción
Los nombres de books en los parámetros (`param_libros.csv`, `param_librorf.csv`) pueden contener tildes (ej. `"Tesorería"`, `"Derivación"`), mientras que los datos provenientes de Summit llegan con o sin tildes dependiendo del encoding.

### Problema de agrupación
Al hacer el join entre la tabla de posición y `param_libros` por la columna `BOOK`:
- `"Tesoreria"` ≠ `"Tesorería"` → el registro queda `LB_LT = "No definido"` en lugar del valor correcto.
- El módulo `parametros_libros.py` hace el join sobre el nombre original del book sin normalizar tildes.

### Síntoma observable
- Books aparecen con `LB_LT = "No definido"` a pesar de existir en el parámetro.
- Posiciones en renta fija que deberían quedar en "Tesoreria" aparecen como "No definido".

### Recomendación
Normalizar ambas columnas antes del join en `enriquecer_con_parametros_libros()`:

```python
# En parametros_libros.py, antes del merge:
df["_BOOK_NORM"] = df["BOOK"].apply(_normalizar_texto)
param["_BOOK_NORM"] = param["BOOK"].apply(_normalizar_texto)
df = df.merge(param, on="_BOOK_NORM", how="left")
```

Donde `_normalizar_texto()` elimina tildes y pasa a mayúsculas (ya existe en `consolidacion.py`, se puede mover a `nucleo_risko`).

---

## 4. Inconsistencia — Renta Fija: no agrupa por Book antes de publicar

### Descripción
La función `_construir_tabla_canonica()` en `renta_fija.py` crea **una fila por título** (un bono = una fila), no por book. El CSV `Tbl_Posicion_Renta_Fija.csv` puede contener cientos de líneas para el mismo book.

### Impacto
- La consolidación acumula correctamente (suma) al calcular `POSICION_COP` y `POSICION_USD`.
- Sin embargo, el tablero Dashy y las tablas `tbl_posicion_actual.csv` muestran filas individuales por título, lo que puede ser confuso si la expectativa es "una fila por book".
- Para los módulos de derivados (Forward, Swaps, Novados), la posición **sí** viene ya agrupada por book.

### Recomendación
Decidir si la posición de Titulos debe mostrarse por book (agrupada) o por título individual. Si se decide agrupar:

```python
# Posible agrupación en _construir_tabla_canonica():
tabla = tabla.groupby(
    ["FECHA", "PRODUCTO", "BOOK", "MONEDA_POSICION", "LB_LT",
     "INSTRUMENTO", "COMPANY", "CLASIFICACION_CONTABLE", "BANKING_CVA_DVA"],
    as_index=False
)["POSICION"].sum()
```

---

## 5. Inconsistencia — MONEDA_POSICION default "USD" para Titulos COP

### Descripción
En `_normalizar_tabla_posicion()` (consolidacion.py):

```python
df["MONEDA_POSICION"] = df["MONEDA_POSICION"].replace({"": "USD", "nan": "USD", "None": "USD"})
```

El valor por defecto para campos vacíos es `"USD"`. Para instrumentos de renta fija (Titulos) en COP, si la columna `MONEDA_POSICION` llega vacía, quedaría marcada incorrectamente como USD.

### Impacto potencial
- Un título COP sin moneda explícita sería tratado como si su posición estuviera en USD.
- Se calcularía `POSICION_COP = POSICION × TRM` en lugar de `POSICION_COP = POSICION`.
- El resultado sería una posición en COP ~3.500x mayor que la real.

### Recomendación
Para el producto `Titulos`, el default debería ser `"COP"` en lugar de `"USD"`:

```python
es_titulo = df["PRODUCTO"].apply(_normalizar_nombre_columna).eq("TITULOS")
df.loc[es_titulo & mascara_vacia, "MONEDA_POSICION"] = "COP"
df.loc[~es_titulo & mascara_vacia, "MONEDA_POSICION"] = "USD"
```

---

## 6. Inconsistencia — BANKING_CVA_DVA: variantes no mapeadas

### Descripción
El `MAPA_BANKING` en `consolidacion.py` cubre:
```python
{"BANKING": "Banking", "IFRS": "IFRS", "CVA_DVA": "CVA/DVA", "CVA/DVA": "CVA/DVA", "CVA DVA": "CVA/DVA"}
```

Sin embargo, si los módulos exportan valores como `"Banking "` (con espacio), `"CVA-DVA"` (con guion), o `"cva/dva"` (minúsculas), no serán reconocidos por el mapa y quedarán con el valor literal.

### Impacto
- El filtro `VISTAS_PUBLICABLES = {"BANKING", "CVA_DVA", "CVA/DVA", "CVA DVA"}` excluiría IFRS de la publicación, pero no excluiría variantes mal escritas.
- Registros con `BANKING_CVA_DVA = "CVA-DVA"` (con guion) quedarían publicados cuando no deberían, o viceversa.

### Verificar
Revisar el output de cada módulo para confirmar que los valores son exactamente uno de: `Banking`, `IFRS`, `CVA/DVA`.

---

## 7. Inconsistencia — Histórico: lógica de fin de mes operativo

### Descripción
La función `_es_fin_mes_operativo()` determina si una fecha es el último día hábil del mes mirando si el **siguiente día hábil** está en un mes diferente. Esto es correcto.

Sin embargo, el archivo `tbl_posicion_historico.csv` fue eliminado (por Codex) y quedó vacío. El histórico se reconstruye automáticamente al ejecutar la consolidación en el último día hábil de cada mes; **no hay mecanismo de reconstrucción retroactiva** a partir del archivo consolidado.

### Recomendación
Si se necesita reconstruir el histórico desde `tbl_posicion_consolidada.csv`, ejecutar:

```python
from proyectos.position_monitor.procesos.consolidacion import (
    _leer_publicado_si_existe, _filtrar_fin_mes_historico, _enriquecer_posiciones_monedas
)
from compartido.nucleo_risko.rutas import ARCHIVO_POSICION_CONSOLIDADA, ARCHIVO_POSICION_HISTORICO

consolidada = _leer_publicado_si_existe(ARCHIVO_POSICION_CONSOLIDADA)
consolidada = _enriquecer_posiciones_monedas(consolidada)
historico = _filtrar_fin_mes_historico(consolidada)
historico.to_csv(ARCHIVO_POSICION_HISTORICO, index=False, encoding="utf-8-sig")
```

---

## 8. Inconsistencia — Debug hardcodeado en Forward

### Descripción
En `forward.py` existe una exportación de debug a una ruta local hardcodeada:

```python
df.to_excel("C:\\Desarrollo\\df_forward.xlsx")  # ← línea de debug
```

### Impacto
- Falla en producción si `C:\Desarrollo\` no existe.
- Genera un archivo sensible fuera del proyecto.

### Acción recomendada
Eliminar esa línea de `forward.py`.

---

## 9. Inconsistencia — Spot: print en lugar de logger

### Descripción
En `spot.py` existe al menos una línea `print(df_insumo_spot)` que debería usar `registrar_log(logger, ...)` para consistencia con los demás módulos.

---

## Resumen de inconsistencias

| # | Módulo | Severidad | Estado |
|---|--------|-----------|--------|
| 1 | consolidacion.py — TRM FORMADA | Alta | **Corregido v1.1** |
| 2 | consolidacion.py — UVR no convertía | Alta | **Corregido v1.1** |
| 3 | parametros_libros.py — tildes en BOOK | Media | Pendiente |
| 4 | renta_fija.py — no agrupa por Book | Media | Decisión de negocio |
| 5 | consolidacion.py — default COP/USD | Media | Pendiente |
| 6 | consolidacion.py — variantes BANKING | Baja | Pendiente |
| 7 | historico.csv — eliminado, sin reconstrucción | Alta | Pendiente |
| 8 | forward.py — debug hardcodeado | Alta | Pendiente |
| 9 | spot.py — print en lugar de logger | Baja | Pendiente |
