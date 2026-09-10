"""Tablero PyG autocontenido: todos sus importes se derivan del detalle diario."""

from __future__ import annotations

from datetime import date
from html import escape
import json
import math
from pathlib import Path
import re
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from proyectos.pyg.procesos.consolidacion import ResultadoPygConsolidado

RAIZ_RISKO = Path(__file__).resolve().parents[3]
CARPETA_PUBLICADOS = RAIZ_RISKO / "datos" / "pyg" / "publicados"

# Funciones puras compartidas por tarjetas, matriz, detalle y exportación.
PYG_CORE_JS = r"""
const RiskoPyg = (() => {
  const amount = row => Number(row.VALOR_COP);
  const isCva = row => row.VISTA === 'CVA/DVA';
  function selected(data, filters) {
    const cutoff = filters.fecha || data.fecha;
    const period = filters.periodo || data.periodo || 'DIARIO';
    const first = cutoff.slice(0, 7) + '-01';
    if (!(data.periodos_disponibles || ['DIARIO']).includes(period)) return [];
    return data.detalle.filter(row =>
      (period === 'MTD' ? row.FECHA >= first && row.FECHA <= cutoff : row.FECHA === cutoff) &&
      ['BOOK', 'PRODUCTO', 'COMPONENTE', 'VISTA'].every(key => !filters[key] || filters[key] === 'TODOS' || row[key] === filters[key]));
  }
  function totals(rows) {
    const banking = rows.filter(row => !isCva(row)).reduce((sum, row) => sum + amount(row), 0);
    const cva = rows.filter(isCva).reduce((sum, row) => sum + amount(row), 0);
    return {banking, cva, ifrs: banking + cva, count: rows.length};
  }
  function matrix(rows) {
    const groups = new Map();
    rows.forEach(row => {
      const key = JSON.stringify([row.BOOK, row.PRODUCTO]);
      if (!groups.has(key)) groups.set(key, {book: row.BOOK, producto: row.PRODUCTO, rows: [], components: {}});
      const group = groups.get(key);
      group.rows.push(row);
      if (!isCva(row)) group.components[row.COMPONENTE] = (group.components[row.COMPONENTE] || 0) + amount(row);
    });
    return [...groups.values()].map(group => ({...group, ...totals(group.rows)}))
      .sort((a, b) => a.book.localeCompare(b.book) || a.producto.localeCompare(b.producto));
  }
  const csvColumns = ['FECHA', 'FECHA_ANTERIOR', 'BOOK', 'PRODUCTO', 'COMPONENTE', 'VALOR_COP', 'VISTA', 'TIPO', 'ESTADO', 'PERIODO'];
  function csv(rows) {
    const cell = value => {
      let text = String(value ?? '');
      if (typeof value !== 'number' && /^[=+@\-\t\r]/.test(text)) text = "'" + text;
      return '"' + text.replaceAll('"', '""') + '"';
    };
    return '\ufeff' + [csvColumns.map(cell).join(';'), ...rows.map(row => csvColumns.map(key => cell(row[key])).join(';'))].join('\r\n');
  }
  return {selected, totals, matrix, csv};
})();
if (typeof window !== 'undefined') window.RiskoPyg = RiskoPyg;
"""


def _preparar_datos(resultado: ResultadoPygConsolidado | dict) -> dict:
    datos = dict(resultado.to_dict() if hasattr(resultado, "to_dict") else resultado)
    date.fromisoformat(datos["fecha"])
    filas = []
    grupos: dict[tuple, set[str]] = {}
    for original in datos.get("detalle", []):
        fila = dict(original)
        for clave in ("FECHA", "BOOK", "PRODUCTO", "COMPONENTE", "VALOR_COP"):
            if clave not in fila:
                raise ValueError(f"Detalle PyG sin campo requerido {clave}.")
        date.fromisoformat(str(fila["FECHA"]))
        fila["VALOR_COP"] = float(fila["VALOR_COP"])
        if not math.isfinite(fila["VALOR_COP"]):
            raise ValueError("El detalle PyG contiene un importe no finito.")
        fila.setdefault("VISTA", "Banking")
        fila.setdefault("PERIODO", "DIARIO")
        fila.setdefault("ESTADO", datos.get("estado", "SIN_VALIDAR"))
        if fila["VISTA"] not in {"Banking", "CVA/DVA"}:
            raise ValueError("El detalle admite contribuciones Banking o CVA/DVA; IFRS se deriva de ambas.")
        if fila["PERIODO"] != "DIARIO":
            raise ValueError("El tablero requiere contribuciones diarias para evitar duplicar el acumulado MTD.")
        if fila["COMPONENTE"] in {"PYG_BANKING", "PYG_IFRS", "TOTAL", "TOTAL_BANKING"}:
            raise ValueError("El detalle contiene un total sumable junto con sus contribuciones.")
        clave_grupo = tuple(fila[c] for c in ("FECHA", "BOOK", "PRODUCTO", "VISTA"))
        grupos.setdefault(clave_grupo, set()).add(fila["COMPONENTE"])
        filas.append(fila)
    for componentes in grupos.values():
        if "RHO" in componentes and {"RHO_COP", "RHO_USD"} & componentes:
            raise ValueError("El detalle duplica RHO: debe contener el total o su desglose por moneda.")
        if "DELTA_PYG" in componentes and {"DELTA_INTERDAY", "DELTA_INTRADAY"} & componentes:
            raise ValueError("El detalle duplica DELTA_PYG y su desglose.")
    datos["detalle"] = filas
    datos.setdefault("periodo", "DIARIO")
    datos.setdefault("periodos_disponibles", ["DIARIO"])
    if datos["periodo"] not in datos["periodos_disponibles"]:
        datos["periodo"] = datos["periodos_disponibles"][0]
    return datos


def build_dashboard(
    resultado: ResultadoPygConsolidado | dict,
    ruta_salida: str | Path | None = None,
) -> Path:
    datos = _preparar_datos(resultado)
    salida = Path(ruta_salida) if ruta_salida else CARPETA_PUBLICADOS / "pyg.html"
    salida.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(datos, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")

    def opciones(valores, seleccionado=None):
        return "".join(
            f'<option value="{escape(str(v), quote=True)}"'
            f'{" selected" if v == seleccionado else ""}>{escape(str(v))}</option>'
            for v in valores
        )

    fechas = sorted({datos["fecha"], *datos.get("fechas_calculadas", []), *(r["FECHA"] for r in datos["detalle"])})
    filtros = [
        '<label>Fecha de corte<select id="f-fecha" data-filter="FECHA">' + opciones(fechas, datos["fecha"]) + "</select></label>",
        '<label>Período<select id="f-periodo" data-filter="PERIODO">' + opciones(datos["periodos_disponibles"], datos["periodo"]) + "</select></label>",
    ]
    for campo, etiqueta in (("BOOK", "Libro"), ("PRODUCTO", "Producto"), ("COMPONENTE", "Griega / componente"), ("VISTA", "Vista")):
        valores = sorted({str(r[campo]) for r in datos["detalle"]})
        filtros.append(f'<label>{etiqueta}<select id="f-{campo.lower()}" data-filter="{campo}">' + opciones(["TODOS", *valores]) + "</select></label>")
    controles = "".join(
        f'<li><strong>{escape(str(c.get("control", "Control")))}</strong>'
        f'<span class="quality-status">{escape(str(c.get("estado", "SIN_VALIDAR")))}</span>'
        f'<p>{escape(str(c.get("detalle", "")))}</p></li>'
        for c in datos.get("calidad", [])
    ) or "<li>No se reportaron controles de calidad.</li>"
    trm = datos.get("mercado", {}).get("TRM_ACTUAL")
    mercado_texto = f"TRM del corte: {float(trm):,.2f} COP/USD" if trm is not None and math.isfinite(float(trm)) else "TRM del corte: no informada"
    plantilla = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RISKO · PyG · __FECHA__</title>
<style>
:root{--navy:#0a2040;--blue:#1a56b8;--ink:#172b4d;--muted:#657796;--bg:#edf2f9;--line:#d7e0ef;--pos:#087443;--neg:#b42318}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Segoe UI,Arial,sans-serif}header{background:linear-gradient(120deg,var(--navy),#164783);color:white;padding:24px max(24px,calc((100vw - 1540px)/2))}.kicker{font-size:11px;letter-spacing:.15em;color:#abc7ef;font-weight:700}h1{margin:4px 0;font-size:29px}.subtitle{color:#d5e4f7}.wrap{max-width:1540px;margin:auto;padding:20px 24px 36px}.toolbar{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin-bottom:15px}label{font-size:11px;color:var(--muted);font-weight:700}select,button{display:block;max-width:235px;min-height:38px;margin-top:4px;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:white;color:var(--ink);font:inherit}button{cursor:pointer;background:var(--blue);color:white;padding:8px 16px}button:focus-visible,select:focus-visible{outline:3px solid #70a1e7;outline-offset:2px}.badge{display:inline-block;margin-top:9px;padding:4px 10px;border-radius:6px;background:#fff3d8;color:#754b00;font-size:11px;font-weight:800}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}.card,.panel{background:white;border:1px solid var(--line);border-radius:10px;box-shadow:0 3px 10px #16386a0b}.card{padding:16px}.card small{display:block;color:var(--muted);font-weight:700;text-transform:uppercase;font-size:11px}.card strong{display:block;font-size:23px;margin-top:7px;font-variant-numeric:tabular-nums}.note,.foot{font-size:12px;color:var(--muted)}.note{margin-top:4px}.panel{padding:17px;min-width:0;margin-top:14px}.panel-head{display:flex;gap:12px;justify-content:space-between;align-items:center;flex-wrap:wrap}h2{font-size:16px;margin:0 0 12px}.scroll{overflow:auto;max-height:520px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{padding:9px 10px;border-bottom:1px solid #e9eef6;text-align:left}th{font-size:11px;color:var(--muted);background:white;position:sticky;top:0}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}.pos{color:var(--pos)}.neg{color:var(--neg)}.layout{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}.bars{display:grid;gap:9px}.bar-item{display:grid;grid-template-columns:140px 1fr 150px;align-items:center;gap:12px;font-size:12px}.bar-value{text-align:right;font-variant-numeric:tabular-nums}.bar-track{height:10px;background:#eef2f7;border-radius:9px;overflow:hidden}.bar{display:block;height:100%;border-radius:9px;background:#23a36d}.bar.neg{background:#da5148}ul.quality{margin:0;padding:0;list-style:none}.quality li{padding:9px 0;border-bottom:1px solid #edf1f7}.quality p{margin:3px 0;font-size:12px;color:var(--muted)}.quality-status{float:right;font-size:11px;margin-left:12px}.empty{padding:18px;color:var(--muted)}.foot{margin-top:10px}.warning{color:#855000;background:#fff5df;border:1px solid #efdcad;padding:10px;border-radius:6px;margin-bottom:14px}@media(max-width:1050px){.grid{grid-template-columns:1fr 1fr}.layout{grid-template-columns:1fr}}@media(max-width:570px){.grid{grid-template-columns:1fr}.wrap{padding:14px}.bar-item{grid-template-columns:105px 1fr 105px}select{max-width:180px}}
</style></head><body>
<header><div class="kicker">RISKO · RIESGO DE MERCADO</div><h1>PyG</h1><div class="subtitle">Resultado __PERIODO__ por book, producto y contribución</div><div class="subtitle">Corte publicado: __FECHA__ · Base: __BASE__</div><span class="badge">__ESTADO__</span></header>
<main class="wrap">
 <div class="toolbar">__FILTROS__<button id="exportar" type="button">Exportar detalle CSV</button></div>
 <div class="warning" id="alcance" role="status"></div>
 <section class="grid" aria-label="Totales de la selección">
  <div class="card"><small>PyG Banking</small><strong id="k-banking">—</strong><div class="note">Contribuciones de Banking</div></div>
  <div class="card"><small>CVA / DVA</small><strong id="k-cva">—</strong><div class="note">Ajuste de valoración seleccionado</div></div>
  <div class="card"><small>PyG IFRS</small><strong id="k-ifrs">—</strong><div class="note">Banking + CVA / DVA seleccionados</div></div>
  <div class="card"><small>Contribuciones</small><strong id="k-count">—</strong><div class="note" id="n-count">Selección actual</div></div>
 </section>
 <section class="layout"><article class="panel"><h2>Atribución por griegas y componentes</h2><div class="bars" id="barras"></div><p class="foot">Valores COP de las contribuciones seleccionadas.</p></article><aside class="panel"><h2>Calidad del corte publicado</h2><div class="scroll"><ul class="quality">__CONTROLES__</ul></div><div class="foot">Conciliación: <b>__CONCILIACION__</b><br>__MERCADO__</div></aside></section>
 <section class="panel"><h2>Matriz libro × producto × contribución</h2><div class="scroll"><table><thead id="matriz-head"></thead><tbody id="matriz"></tbody></table></div><div class="foot">La matriz y los indicadores usan exactamente las mismas filas filtradas.</div></section>
 <section class="panel"><div class="panel-head"><h2>Detalle diario del resultado</h2><span class="note" id="n-detalle"></span></div><div class="scroll"><table><thead><tr><th>Fecha</th><th>Libro</th><th>Producto</th><th>Componente / griega</th><th>Vista</th><th class="num">Valor COP</th><th>Estado</th></tr></thead><tbody id="detalle"></tbody></table></div><div class="foot" id="paginacion"></div></section>
</main>
<script id="pyg-data" type="application/json">__PAYLOAD__</script>
<script id="pyg-core">__CORE__</script>
<script>
'use strict';
const DATA=JSON.parse(document.getElementById('pyg-data').textContent);
const $=id=>document.getElementById(id);
const COP=new Intl.NumberFormat('es-CO',{style:'currency',currency:'COP',maximumFractionDigits:2,minimumFractionDigits:0});
const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const tone=value=>value<0?'neg':value>0?'pos':'';
const numberCell=value=>`<td class="num ${tone(value)}">${COP.format(value)}</td>`;
let detalleLimite=250;
function filters(){return {fecha:$('f-fecha').value,periodo:$('f-periodo').value,BOOK:$('f-book').value,PRODUCTO:$('f-producto').value,COMPONENTE:$('f-componente').value,VISTA:$('f-vista').value};}
function render(){
 const f=filters(),rows=RiskoPyg.selected(DATA,f),total=RiskoPyg.totals(rows),groups=RiskoPyg.matrix(rows);
 [['banking',total.banking],['cva',total.cva],['ifrs',total.ifrs]].forEach(([key,value])=>{$('k-'+key).textContent=rows.length?COP.format(value):'—';$('k-'+key).className=tone(value);});
 $('k-count').textContent=String(rows.length);
 $('n-count').textContent=`${new Set(rows.map(row=>row.BOOK)).size} libro(s) · ${new Set(rows.map(row=>row.PRODUCTO)).size} producto(s)`;
 const scope=f.periodo==='MTD'?`Acumulado mensual hasta ${f.fecha}`:`Resultado diario del ${f.fecha}`;
 $('alcance').textContent=scope+' · '+(rows.length?'Estado del corte: '+DATA.estado:'Sin datos para esta selección.')+(DATA.periodos_disponibles.includes('MTD')?'':' · Esta publicación contiene únicamente el cálculo diario.');
 const byComp=new Map();rows.forEach(row=>{const key=row.COMPONENTE+' · '+row.VISTA;byComp.set(key,(byComp.get(key)||0)+row.VALOR_COP);});
 const bars=[...byComp].sort((a,b)=>Math.abs(b[1])-Math.abs(a[1])),max=Math.max(1,...bars.map(item=>Math.abs(item[1])));
 $('barras').innerHTML=bars.map(([key,value])=>`<div class="bar-item"><span>${html(key.replaceAll('_',' '))}</span><div class="bar-track"><span class="bar ${tone(value)}" style="width:${Math.abs(value)/max*100}%"></span></div><span class="bar-value ${tone(value)}">${COP.format(value)}</span></div>`).join('')||'<p class="empty">Sin contribuciones para esta selección.</p>';
 const components=[...new Set(rows.filter(row=>row.VISTA==='Banking').map(row=>row.COMPONENTE))].sort();
 $('matriz-head').innerHTML='<tr><th>Libro</th><th>Producto</th>'+components.map(key=>`<th class="num">${html(key.replaceAll('_',' '))}</th>`).join('')+'<th class="num">Banking</th><th class="num">CVA / DVA</th><th class="num">IFRS</th></tr>';
 $('matriz').innerHTML=groups.map(group=>`<tr><td>${html(group.book)}</td><td>${html(group.producto)}</td>${components.map(key=>numberCell(group.components[key]||0)).join('')}${numberCell(group.banking)}${numberCell(group.cva)}${numberCell(group.ifrs)}</tr>`).join('')||`<tr><td colspan="${components.length+5}" class="empty">Sin datos.</td></tr>`;
 $('detalle').innerHTML=rows.slice(0,detalleLimite).map(row=>`<tr><td>${html(row.FECHA)}</td><td>${html(row.BOOK)}</td><td>${html(row.PRODUCTO)}</td><td>${html(row.COMPONENTE.replaceAll('_',' '))}</td><td>${html(row.VISTA)}</td>${numberCell(row.VALOR_COP)}<td>${html(row.ESTADO)}</td></tr>`).join('')||'<tr><td colspan="7" class="empty">Sin datos.</td></tr>';
 $('n-detalle').textContent=`${rows.length} filas · ${f.periodo}`;
 $('paginacion').textContent='';
 if(rows.length>detalleLimite){const button=document.createElement('button');button.type='button';button.textContent=`Mostrar siguientes ${Math.min(250,rows.length-detalleLimite)} filas`;button.onclick=()=>{detalleLimite+=250;render();};$('paginacion').appendChild(button);}
 $('exportar').disabled=rows.length===0;
}
document.querySelectorAll('select[data-filter]').forEach(select=>select.addEventListener('change',()=>{detalleLimite=250;render();}));
$('exportar').addEventListener('click',()=>{const f=filters(),blob=new Blob([RiskoPyg.csv(RiskoPyg.selected(DATA,f))],{type:'text/csv;charset=utf-8;'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`pyg_${f.fecha}_${f.periodo}.csv`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);});
render();
</script></body></html>"""
    sustituciones = {
        "__FECHA__": escape(datos["fecha"]),
        "__BASE__": escape(str(datos.get("fecha_anterior", "No informada"))),
        "__PERIODO__": escape(datos["periodo"]),
        "__ESTADO__": escape(str(datos.get("estado", "SIN_VALIDAR"))),
        "__FILTROS__": "".join(filtros),
        "__CONTROLES__": controles,
        "__CONCILIACION__": escape(str(datos.get("conciliacion", {}).get("estado", "SIN_VALIDAR"))),
        "__MERCADO__": escape(mercado_texto),
        "__CORE__": PYG_CORE_JS,
        "__PAYLOAD__": payload,
    }
    # Una sola sustitución evita interpretar como marcadores los datos del usuario.
    html = re.sub(r"__[A-Z]+__", lambda match: sustituciones[match.group()], plantilla)
    temporal = salida.with_name(f".{salida.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporal.write_text(html, encoding="utf-8")
        temporal.replace(salida)
    finally:
        temporal.unlink(missing_ok=True)
    return salida


__all__ = ["build_dashboard"]
