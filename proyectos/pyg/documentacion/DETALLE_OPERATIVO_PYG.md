# Operación del PyG por griegas

1. Configure las rutas locales en `proyectos/pyg/configuracion/pyg.json`.
2. Disponga de los snapshots completos de cada fecha requerida. Para MTD con
   calendario diario hacen falta el cierre del mes anterior y todos los días
   hasta el corte. Si el proceso usa exclusivamente días hábiles, configure
   `calculo.calendario=HABIL_CO` explícitamente.
3. Abra `aplicaciones/interfaz_risko/interfaz_pyg.py`; seleccione libro y período.
   Para SWAPS, **Importar libro SWAPS** prepara los snapshots fechados del XLSM.
4. Mantenga **Cargar insumos con Vector** si la herramienta está instalada y las
   fuentes son accesibles. Desmárquela para usar snapshots locales.
5. **Ejecutar cierre PyG** calcula todos los productos habilitados, conserva los
   insumos, guarda la corrida y construye el tablero. Los botones individuales
   guardan exclusivamente el producto seleccionado.
6. **Consolidar PyG** reúne los cálculos guardados; exige todos los productos e
   intervalos del alcance. No descarga datos ni sustituye cálculos faltantes.
7. Revise la tabla, griegas, Banking/CVA-DVA/IFRS y controles. Los avisos de
   fondeo ausente o diferencias de referencia requieren resolución funcional.
8. **Generar tablero** reconstruye la vista desde SQLite y abre el HTML local.
9. **Publicar en portal** publica `Dashboards/PyG/AAAA-MM-DD/` con el contrato ya
   soportado por el portal. Requiere la conciliación configurada. Una nueva
   publicación de la misma fecha reemplaza el contenido anterior de esa fecha.

No se ejecutan cálculos al abrir la ventana. Cambiar el selector de libro o fecha
no cambia automáticamente los datos mostrados: la etiqueta inferior conserva
el alcance del resultado cargado. Un error conserva ese resultado anterior y lo
indica expresamente. Los filtros de producto/griega actúan sobre las filas
visibles y sus totales; **Exportar detalle** guarda esa selección en CSV.

Los históricos antiguos de PyG en CSV/JSON no se importan automáticamente porque
pueden proceder de cifras fijas o de la referencia mensual. La nueva base es
`datos/pyg/pyg.db`. Para incorporar un corte histórico hay que recalcularlo con
sus snapshots y verificar sus controles.

FX_ESTRAT permanece visible como pendiente de metodología/insumos y fuera de los
libros habilitados. Sus cifras históricas de demostración no se publican.
