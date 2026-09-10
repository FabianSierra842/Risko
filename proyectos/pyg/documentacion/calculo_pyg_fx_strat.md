# Cálculo Explicativo y Desagregación de PyG — Libro FX_ESTRAT (5.5)

## 1. Objetivo y Alcance

Este documento explica de forma exhaustiva y exacta cómo se calcula el **PyG (Pérdidas y Ganancias)** para el libro **FX_ESTRAT** (Libro 5.5), detallando la secuencia ejecutada por la herramienta **DORA**, los insumos requeridos, las funciones VBA, la estructura del libro Excel/XLSB y la desagregación matemática en **Griegas y Atribuciones de Riesgo**.

---

## 2. Ubicación de Archivos y Plantillas

* **Plantilla Producción Servidor**:
  `\\isilonsmbprod\Gerencia_Riesgo_De_Tesoreria\3 Jefatura de Riesgo de Mercado\FORWARDS\INFORMES\P&G_FXESTRAT(5.5).xlsb`
* **Copia Local de la Plantilla en Procesos**:
  `proyectos/pyg/procesos/P&G_FXESTRAT(5.5).xlsb`
* **Código VBA Extraído**:
  `proyectos/pyg/procesos/vba_fxestrat.vba`
* **Generador del Dashboard**:
  `proyectos/pyg/tableros/panel_pyg_fx_strat.py`
* **Tablero HTML Interactivo Publicado**:
  `datos/pyg/publicados/pyg_fx_strat.html` (o `proyectos/pyg/tableros/pyg_fx_strat.html`)

---

## 3. Secuencia de Ejecución en DORA (`flujos_diana.json`)

La herramienta de automatización **DORA** ejecuta el flujo parametrizado bajo la clave `"2.2 PyG Fx Estrat dia"` (o `"2.3 PyG Fx Estrat fds"` para fines de semana).

La secuencia exacta de las 13 macros/pasos es la siguiente:

| Paso | Macro / Función VBA | Archivo Insumo / Parámetro | Nota / Propósito |
| :--- | :--- | :--- | :--- |
| **1** | `carga_fwd_dia_P` | `INFORME FWD CONSOLIDADO dd-mm-yy.xlsb` | Carga valor de mercado y PyG de forwards y contado del libro `FWD_CLIENTES`. |
| **2** | `CARGAR_INFO_CAJA_5_5_P` | `REPORTE CAJA LIVIANO` (`dd/mm/yyyy`) | Importa la posición de caja y liquidez diaria. |
| **3** | `CARGA_FT_P` | `FTP COP.xlsx` y `FTP USD.xlsx` | Carga curvas de costo de fondeo COP y USD. |
| **4** | `GRIEGAS_P` | `Informe Libro FX_ESTRAT YYYYMMDD.xlsb` | Carga el libro detallado de operaciones de FX_ESTRAT. |
| **5** | `traecurvas_P` | `Curva Forward V2.xlsm` | Carga las curvas forward de mercado y puntos swap para valoración. |
| **6** | `CARGAR_INFO_FWDS_5_5_P` | `MASCARA FX TOTAL REPORT (5.5-3-8).xls` | Aplica la máscara de filtro e identificación de operaciones FX. |
| **7** | `flitrar_novados_P` | N/A (Interno) | Filtra operaciones que pasaron a cámara de riesgo central (CRCC). |
| **8** | `F_Calcular_Riesgos` | N/A (Hoja `RIESGOS` / `SENSIBILIDAD`) | Ejecuta el motor de cálculo de Griegas ($\Delta, \ Rho, \Theta, \varepsilon$). |
| **9** | `E_Recalculo` | N/A (Hoja `Fuente vs Instrum - TD`) | Valida consistencia entre fuente primaria e instrumentos. |
| **10** | `CARGAR_VALORACION_SWAP_P` | `Cierre_SwapTotalReport_...xls` | Importa datos de valoración Banking e IFRS de Swaps asignados a FX_ESTRAT. |
| **11** | `AUX` | `Informe Libro FX_ESTRAT YYYYMMDD.xlsb` | Procesa tablas auxiliares y ajustes inter-libro. |
| **12** | `ActualizarVinculo` | `P&G_FXESTRAT(5.5).xlsb` (Backup) | Actualiza vínculos externos con la fecha anterior ($T-1$). |

---

## 4. Insumos Requeridos por el Proceso

Para que el PyG de FX_ESTRAT se valore y atribuya correctamente se requieren los siguientes **7 insumos principales**:

1. **`INFORME FWD CONSOLIDADO dd-mm-yy.xlsb`**: Proporciona las posiciones abiertas de Forwards y Contado.
2. **`REPORTE CAJA LIVIANO`**: Aporta la información del libro de caja y disponibilidades.
3. **`FTP COP.xlsx` y `FTP USD.xlsx`**: Tablas con las tasas de transferencia de fondos (FTP) para el cálculo del costo de fondeo.
4. **`Informe Libro FX_ESTRAT YYYYMMDD.xlsb`**: Posiciones específicas registradas bajo el libro `FX_ESTRAT`.
5. **`Curva Forward V2.xlsm`**: Tabla maestra con la TRM Spot, puntos forward y curvas de tasa cero en COP y USD.
6. **`MASCARA FX TOTAL REPORT (5.5-3-8).xls`**: Catálogo de clasificación de operaciones.
7. **`Cierre_SwapTotalReport_...xls`**: Reporte Summit con las valoraciones de Swaps (Banking e IFRS).

---

## 5. Fórmulas Matemáticas de Valoración

### 5.1 Valor Presente de un Forward USD/COP
El valor presente ($VP$) en COP de una posición Forward con nominal $N_{\text{USD}}$, tasa pactada $F_{\text{strike}}$, y plazo a vencer $t$ días se calcula como:

$$VP_{\text{COP}} = N_{\text{USD}} \cdot \left[ \frac{1 + r_{\text{COP}} \cdot \frac{t}{365}}{1 + r_{\text{USD}} \cdot \frac{t}{360}} \cdot S - F_{\text{strike}} \right] \cdot DF_{\text{COP}}(t)$$

donde:
* $S$: TRM Spot a la fecha de valoración.
* $r_{\text{COP}}, r_{\text{USD}}$: Tasas de descuento o devaluación implícita extraídas de `Curva Forward V2.xlsm`.
* $DF_{\text{COP}}(t) = \frac{1}{1 + r_{\text{COP}} \cdot \frac{t}{365}}$: Factor de descuento en COP.

---

## 6. Desagregación en Griegas y Atribución del PyG

El PyG total se descompone en las siguientes **Griegas y factores de riesgo**:

### 1. `Trading` (PyG Nominal Acumulado)
* **Definición**: Resultado nominal bruto acumulado MTD de las operaciones.

### 2. `Delta Inter-day` ($\Delta_{\text{inter}}$)
* **Definición**: P&G generado por la variación de la TRM entre cierres de días hábiles ($S_T - S_{T-1}$).
* **Fórmula**: 
  $$\Delta_{\text{inter}} = \text{Posición Neta (USD)} \cdot (S_T - S_{T-1}) \cdot DF_{\text{COP}}$$

### 3. `Delta Intra-day` ($\Delta_{\text{intra}}$)
* **Definición**: P&G resultante del movimiento de la TRM durante la jornada (inicio de día vs cierre del día).
* **Fórmula**:
  $$\Delta_{\text{intra}} = \text{Posición Neta (USD)} \cdot (S_{\text{cierre}} - S_{\text{inicio}}) \cdot DF_{\text{COP}}$$

### 4. `Rho COP` ($\text{Rho}_{\text{COP}}$)
* **Definición**: Sensibilidad del valor del portafolio ante cambios en la curva de tasas de interés en COP ($r_{\text{COP}}$).
* **Fórmula**:
  $$\text{Rho}_{\text{COP}} = \frac{\partial VP}{\partial r_{\text{COP}}} \cdot \Delta r_{\text{COP}}$$

### 5. `Rho USD` ($\text{Rho}_{\text{USD}}$)
* **Definición**: Sensibilidad del valor del portafolio ante cambios en la curva de tasas de interés en USD ($r_{\text{USD}}$).
* **Fórmula**:
  $$\text{Rho}_{\text{USD}} = \frac{\partial VP}{\partial r_{\text{USD}}} \cdot \Delta r_{\text{USD}}$$

### 6. `Theta` ($\Theta$ / Paso del Tiempo)
* **Definición**: Desgaste de valor o ganancia por el paso de un día de tiempo ($t \to t-1$), manteniendo TRM y tasas constantes.
* **Fórmula**:
  $$\Theta = VP(t-1, S, r) - VP(t, S, r)$$

### 7. `Épsilon (ε)` (Residual / Efecto Cruzado)
* **Definición**: Diferencia residual no explicada linealmente por las primeras derivadas (captura efectos cruzados $\frac{\partial^2 VP}{\partial S \partial r}$ o segundo orden).
* **Fórmula**:
  $$\varepsilon = \Delta VP_{\text{total}} - (\Delta_{\text{inter}} + \Delta_{\text{intra}} + \text{Rho}_{\text{COP}} + \text{Rho}_{\text{USD}} + \Theta)$$

### 8. `Costo de Fondos`
* **Definición**: Cargo financiero por el fondeo de las posiciones de contado/caja abiertas durante el período.

### 9. `Crédito` y `DVA/-CVA`
* **Definición**: Ajuste contable IFRS por riesgo de crédito de contraparte.

---

## 7. Ejemplo Numérico Real — Corte al 28/08/2026

A continuación se presenta el resumen real extraído de la hoja `RESUMEN FINAL` del libro `P&G_FXESTRAT(5.5).xlsb`:

| Componente / Griega | Spot (Caja) | Forward | Novados | Swap | **TOTAL COP** |
| :--- | ---: | ---: | ---: | ---: | ---: |
| **Trading** | $648,911,554 | $399,147,427 | $0 | $571,143 | **$1,048,630,124** |
| **Delta Inter-day** | -$3,572,746,180 | $3,654,835,757 | $0 | $0 | **$82,089,577** |
| **Delta Intra-day** | $721,661,946 | -$621,764,878 | $0 | $0 | **$99,897,068** |
| **Crédito** | $0 | $0 | $0 | $0 | **$0** |
| **Rho COP** | $0 | $335,435,214 | $0 | $58,110,373 | **$393,545,588** |
| **Rho USD** | $0 | $385,326,644 | $0 | $0 | **$385,326,644** |
| **Spread** | $0 | $0 | $0 | $0 | **$0** |
| **Theta (Tiempo)** | $0 | -$820,858,842 | $0 | $17,308,354 | **-$803,550,488** |
| **Épsilon (ε)** | $0 | -$290,669,909 | $0 | $1,849,170 | **-$288,820,739** |
| **Costo de Fondos** | $875,792,730 | $0 | $0 | $0 | **$875,792,730** |
| **TOTAL BANKING** | **-$1,326,379,950** | **$3,041,451,413** | **$0** | **$77,839,040** | **$1,792,910,503** |
| **DVA / -CVA** | $0 | -$1,993,981 | $0 | -$469,311 | **-$2,463,292** |
| **P&G CON IFRS** | **-$1,326,379,950** | **$3,039,457,432** | **$0** | **$77,369,729** | **$1,790,447,211** |

---

## 8. Dashboard HTML Interactivo

El módulo [panel_pyg_fx_strat.py](proyectos/pyg/tableros/panel_pyg_fx_strat.py) genera automáticamente el tablero [datos/pyg/publicados/pyg_fx_strat.html](datos/pyg/publicados/pyg_fx_strat.html) (o [proyectos/pyg/tableros/pyg_fx_strat.html](proyectos/pyg/tableros/pyg_fx_strat.html)), permitiendo:
1. Alternar entre la vista **Acumulado MTD** y **Variación Diaria**.
2. Filtrar por producto individual (`Spot`, `Forward`, `Novados`, `Swap`).
3. Visualizar gráficos de barras de magnitud de Griegas.
4. Consultar la secuencia de pasos de DORA y la información de la TRM de corte ($3,202.79 vs $3,144.28).

---

## 9. Arquitectura Novedosa Nátiva en Python (Sin Excel / Sin `.xlsb`)

Siguiendo el estándar de arquitectura de `position_monitor`, el cálculo y atribución de PyG se estandarizó en módulos independientes por producto dentro de `proyectos/pyg/procesos/`:

1. **`caja.py` (`calcular_pyg_spot`)**:
   * Implementa el cálculo determinístico de PyG Spot para cualquier libro (`FX_ESTRAT`, `SWAPS`, `FUTUROS_FX`).
   * Desglosa `Trading`, `Intra-day Delta`, `Inter-day Delta` y `Costo de Fondos`.
   * **Validación**: Coincidencia matemática exacta ($0.00$ diferencia) con la hoja `CAJA` y `RESUMEN FINAL`.

2. **`forward.py` (`calcular_pyg_forward`)**:
   * Modulo desacoplado para el cálculo de atribución Forward (`Trading`, `Delta Inter-day`, `Delta Intra-day`, `Rho COP`, `Rho USD`, `Theta`, `Épsilon` y `CVA/DVA`).

3. **`novados.py` (`calcular_pyg_novados`)**:
   * Mapea operaciones novadas en cámara de riesgo central.

4. **`swaps.py` (`calcular_pyg_swaps`)**:
   * Mapea la atribución de Swaps (`Trading`, `Rho COP`, `Theta`, `Épsilon` y `CVA/DVA`).

5. **`consolidacion.py` (`calcular_pyg_book_fx_strat`)**:
   * Orquesta la consolidación por libro y producto, sumando los componentes canónicos de PyG Banking e IFRS.
   * **Resultado Validado para FX_ESTRAT**:
     * **PyG Banking Total**: $\$1,792,910,503.46$ COP (100% idéntico a Excel).
     * **CVA Total**: $-\$2,463,291.99$ COP (100% idéntico a Excel).
     * **PyG IFRS Total**: $\$1,790,447,211.47$ COP (100% idéntico a Excel).

