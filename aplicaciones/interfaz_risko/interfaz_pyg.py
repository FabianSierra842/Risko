"""Interfaz operativa PyG: calcula productos, consolida griegas y publica HTML."""
from __future__ import annotations
from datetime import date, timedelta
import csv
from pathlib import Path
import queue
import sys
import threading
from tkinter import filedialog, messagebox, ttk
import webbrowser
import customtkinter as ctk

RAIZ_RISKO = Path(__file__).resolve().parents[2]
if str(RAIZ_RISKO) not in sys.path:
    sys.path.insert(0,str(RAIZ_RISKO))
from aplicaciones.interfaz_risko.servicios import pyg as servicio
from proyectos.pyg.procesos.configuracion import cargar_configuracion, fecha
from proyectos.pyg.procesos.consolidacion import sumar

def filas_seleccionadas(datos,book='TODOS',producto='TODOS',componente='TODOS'):
    return [r for r in datos.get('detalle',[]) if
        (datos.get('periodo')=='MTD' or r['FECHA']==datos['fecha']) and
        (book=='TODOS' or r['BOOK']==book) and
        (producto=='TODOS' or r['PRODUCTO']==producto) and
        (componente=='TODOS' or r['COMPONENTE']==componente)]

def _cop(valor):
    return f'{valor:,.2f}'.replace(',','X').replace('.',',').replace('X','.')

class AppPyg:
    def __init__(self,root=None):
        ctk.set_appearance_mode('light')
        self.root = root or ctk.CTk()
        self.root.title('RISKO · PyG por griegas')
        self.root.geometry('1280x820')
        self.root.minsize(1000,650)
        self.root.configure(fg_color='#EEF2F9')
        self.root.grid_columnconfigure(1,weight=1)
        self.root.grid_rowconfigure(0,weight=1)
        self.cola = queue.Queue()
        self.resultado = None
        self.ocupado = False
        self.controles = []
        self.var_fecha = ctk.StringVar(value=(date.today()-timedelta(days=1)).strftime('%d/%m/%Y'))
        libros = servicio.libros_configurados()
        self.var_book = ctk.StringVar(value=libros[0] if libros else 'TODOS')
        self.var_periodo = ctk.StringVar(value='MTD')
        self.var_vector = ctk.BooleanVar(value=False)
        self.var_producto = ctk.StringVar(value='TODOS')
        self.var_griega = ctk.StringVar(value='TODOS')
        self._construir()
        self.root.after(100,self._drenar)

    def _construir(self):
        sidebar = ctk.CTkScrollableFrame(self.root,width=250,fg_color='#0A2040',corner_radius=0)
        sidebar.grid(row=0,column=0,sticky='nsew')
        ctk.CTkLabel(sidebar,text='RISKO',font=ctk.CTkFont(size=30,weight='bold'),text_color='white').pack(pady=(20,4))
        ctk.CTkLabel(sidebar,text='PyG · GRIEGAS',text_color='#BDD3EF').pack(pady=(0,20))
        for texto,variable,valores in [('Fecha de corte',self.var_fecha,None),('Libro',self.var_book,['TODOS',*servicio.libros_configurados()]),('Período',self.var_periodo,['DIARIO','MTD'])]:
            ctk.CTkLabel(sidebar,text=texto,text_color='#D2DEF0',anchor='w').pack(fill='x',padx=10)
            control = ctk.CTkEntry(sidebar,textvariable=variable) if valores is None else ctk.CTkOptionMenu(sidebar,variable=variable,values=valores)
            control.pack(fill='x',padx=10,pady=(2,12))
            self.controles.append(control)
        vector = ctk.CTkCheckBox(sidebar,text='Cargar insumos con Vector',variable=self.var_vector,text_color='white')
        vector.pack(padx=10,pady=10)
        self.controles.append(vector)
        for texto,comando in [('Importar libro SWAPS',self.run_importar_swaps),('Ejecutar cierre PyG',self.run_calcular),('Consolidar PyG',self.run_consolidar_local),('Generar tablero',self.run_tablero),('Publicar en portal',self.run_publicar)]:
            self._boton(sidebar,texto,comando)
        ctk.CTkLabel(sidebar,text='MÓDULOS INDIVIDUALES',text_color='#BDD3EF').pack(pady=(20,8))
        cfg = cargar_configuracion()
        productos = sorted({p for b in servicio.libros_configurados(cfg) for p in cfg['libros'][b]['productos']})
        for producto in productos:
            self._boton(sidebar,producto.title(),lambda p=producto:self.run_producto(p))
        pendientes = [b for b,v in cfg['libros'].items() if not v.get('habilitado')]
        if pendientes:
            ctk.CTkLabel(sidebar,text='Pendientes de insumos/metodología:\n'+', '.join(pendientes),text_color='#F8C77E',wraplength=220).pack(pady=18)
        cuerpo = ctk.CTkFrame(self.root,fg_color='transparent')
        cuerpo.grid(row=0,column=1,sticky='nsew',padx=24,pady=20)
        cuerpo.grid_columnconfigure(0,weight=1)
        cuerpo.grid_rowconfigure(3,weight=1)
        ctk.CTkLabel(cuerpo,text='Resultado por libro, producto y griega',font=ctk.CTkFont(size=24,weight='bold'),text_color='#172B4D').grid(row=0,column=0,sticky='w',pady=(0,14))
        kpis = ctk.CTkFrame(cuerpo,fg_color='transparent')
        kpis.grid(row=1,column=0,sticky='ew')
        self.kpis = {}
        for i,nombre in enumerate(['PYG_BANKING','CVA_DVA','PYG_IFRS']):
            kpis.grid_columnconfigure(i,weight=1)
            tarjeta = ctk.CTkFrame(kpis,fg_color='white')
            tarjeta.grid(row=0,column=i,sticky='ew',padx=4,pady=5)
            ctk.CTkLabel(tarjeta,text=nombre.replace('_',' '),text_color='#62718B').pack(pady=(12,0))
            valor = ctk.CTkLabel(tarjeta,text='—',font=ctk.CTkFont(size=23,weight='bold'))
            valor.pack(pady=(2,12))
            self.kpis[nombre] = valor
        filtros = ctk.CTkFrame(cuerpo,fg_color='transparent')
        filtros.grid(row=2,column=0,sticky='ew',pady=12)
        self.filtro_producto = ctk.CTkOptionMenu(filtros,variable=self.var_producto,values=['TODOS'],command=lambda _:self._render())
        self.filtro_producto.pack(side='left',padx=(0,8))
        self.filtro_griega = ctk.CTkOptionMenu(filtros,variable=self.var_griega,values=['TODOS'],command=lambda _:self._render())
        self.filtro_griega.pack(side='left')
        ctk.CTkButton(filtros,text='Exportar detalle',command=self._exportar,width=140).pack(side='right')
        tabla_frame = ctk.CTkFrame(cuerpo)
        tabla_frame.grid(row=3,column=0,sticky='nsew')
        tabla_frame.grid_columnconfigure(0,weight=1)
        tabla_frame.grid_rowconfigure(0,weight=1)
        columnas = ('FECHA','BOOK','PRODUCTO','COMPONENTE','VALOR_COP','VISTA')
        self.tabla = ttk.Treeview(tabla_frame,columns=columnas,show='headings')
        for c in columnas:
            self.tabla.heading(c,text=c.replace('_',' '))
            self.tabla.column(c,width=125,anchor='e' if c=='VALOR_COP' else 'w')
        self.tabla.grid(row=0,column=0,sticky='nsew')
        scroll = ttk.Scrollbar(tabla_frame,command=self.tabla.yview)
        scroll.grid(row=0,column=1,sticky='ns')
        self.tabla.configure(yscrollcommand=scroll.set)
        self.estado = ctk.CTkLabel(cuerpo,text='Sin resultados cargados.',anchor='w',text_color='#62718B')
        self.estado.grid(row=4,column=0,sticky='ew',pady=8)
        self.log = ctk.CTkTextbox(cuerpo,height=135)
        self.log.grid(row=5,column=0,sticky='ew')

    def _boton(self,padre,texto,comando):
        boton = ctk.CTkButton(padre,text=texto,command=comando,height=36,fg_color='#1A56B8')
        boton.pack(fill='x',padx=10,pady=4)
        self.controles.append(boton)

    def _alcance(self):
        return fecha(self.var_fecha.get()).isoformat(),dict(libro=self.var_book.get(),periodo=self.var_periodo.get())

    def _logger(self,mensaje):
        self.cola.put(('log',str(mensaje)))

    def _ejecutar(self,nombre,trabajo,completar):
        if self.ocupado:
            return
        self.ocupado = True
        for control in self.controles:
            control.configure(state='disabled')
        self.estado.configure(text=nombre+'…')
        def ejecutar():
            try:
                self.cola.put(('resultado',(completar,trabajo())))
            except Exception as error:
                self.cola.put(('error',str(error)))
        threading.Thread(target=ejecutar,daemon=True).start()

    def _drenar(self):
        try:
            while True:
                tipo,dato = self.cola.get_nowait()
                if tipo=='log':
                    self.log.insert('end',dato+'\n')
                    self.log.see('end')
                    continue
                self.ocupado=False
                for control in self.controles:
                    control.configure(state='normal')
                if tipo=='error':
                    self.estado.configure(text='Proceso sin completar. La tabla conserva el resultado anterior.')
                    self.log.insert('end','ERROR: '+dato+'\n')
                    messagebox.showerror('RISKO PyG',dato,parent=self.root)
                else:
                    completar,resultado=dato
                    completar(resultado)
        except queue.Empty:
            pass
        self.root.after(100,self._drenar)

    def _mostrar(self,resultado):
        self.resultado = resultado.to_dict() if hasattr(resultado,'to_dict') else resultado
        for campo,variable,control in [('PRODUCTO',self.var_producto,self.filtro_producto),('COMPONENTE',self.var_griega,self.filtro_griega)]:
            variable.set('TODOS')
            control.configure(values=['TODOS',*sorted({r[campo] for r in self.resultado['detalle']})])
        self._render()
        for c in self.resultado.get('calidad',[]):
            if c.get('estado')!='OK':
                self._logger(f"{c['control']}: {c['estado']} · {c['detalle']}")

    def _render(self):
        if self.resultado is None:
            return
        filas = filas_seleccionadas(self.resultado,producto=self.var_producto.get(),componente=self.var_griega.get())
        self.tabla.delete(*self.tabla.get_children())
        for r in filas:
            self.tabla.insert('', 'end',values=(r['FECHA'],r['BOOK'],r['PRODUCTO'],r['COMPONENTE'],_cop(r['VALOR_COP']),r['VISTA']))
        totales = sumar(filas)
        for k,widget in self.kpis.items():
            widget.configure(text=_cop(totales[k]),text_color='#B42318' if totales[k]<0 else '#087443')
        r=self.resultado
        self.estado.configure(text=f"{r['fecha']} · {r['periodo']} · {', '.join(r['libros'])} · {r['estado']} · conciliación {r['conciliacion']['estado']}")

    def _accion_calculo(self,producto=None):
        try:
            corte,kwargs=self._alcance()
        except ValueError as exc:
            messagebox.showerror('Fecha PyG',str(exc),parent=self.root)
            return
        cargar=self.var_vector.get()
        trabajo=(lambda:servicio.ejecutar_todo_pyg(corte,self._logger,cargar_insumos=cargar,**kwargs)) if producto is None else (
            lambda:servicio.ejecutar_producto_pyg(producto,corte,self._logger,cargar_insumos=cargar,**kwargs))
        self._ejecutar('Calculando PyG',trabajo,self._mostrar)

    def run_calcular(self):
        self._accion_calculo()

    def run_importar_swaps(self):
        ruta=filedialog.askopenfilename(parent=self.root,title='Libro mensual SWAPS',filetypes=[('Libro Excel','*.xlsm *.xlsx')])
        if not ruta:
            return
        def completar(datos):
            self.var_book.set('SWAPS')
            self.var_fecha.set(fecha(datos['fecha_corte']).strftime('%d/%m/%Y'))
            self.var_vector.set(False)
            self.estado.configure(text=f"SWAPS importado: {len(datos['snapshots'])} snapshots. Ejecute el cierre para calcular PyG.")
        self._ejecutar('Importando libro SWAPS',lambda:servicio.importar_swaps(ruta,self._logger),completar)

    def run_producto(self,producto):
        self._accion_calculo(producto)

    def _accion(self,nombre,funcion,completar):
        try:
            corte,kwargs=self._alcance()
        except ValueError as exc:
            messagebox.showerror('Fecha PyG',str(exc),parent=self.root)
            return
        self._ejecutar(nombre,lambda:funcion(corte,self._logger,**kwargs),completar)

    def run_consolidar_local(self):
        self._accion('Consolidando PyG',servicio.consolidar_pyg,self._mostrar)

    def run_tablero(self):
        self._accion('Generando tablero',servicio.generar_tablero,lambda ruta:(self.estado.configure(text=f'Tablero: {ruta}'),webbrowser.open(Path(ruta).resolve().as_uri())))

    def run_publicar(self):
        self._accion('Publicando PyG',servicio.publicar_tablero,lambda r:self.estado.configure(text=f"Publicado: {r['html']}"))

    def _exportar(self):
        if self.resultado is None:
            return
        archivo=filedialog.asksaveasfilename(parent=self.root,defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not archivo:
            return
        filas=filas_seleccionadas(self.resultado,producto=self.var_producto.get(),componente=self.var_griega.get())
        with open(archivo,'w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=['FECHA','FECHA_ANTERIOR','BOOK','PRODUCTO','COMPONENTE','VALOR_COP','VISTA','TIPO','ESTADO','PERIODO'])
            writer.writeheader()
            writer.writerows(filas)

    def run(self):
        self.root.mainloop()

def main():
    AppPyg().run()

if __name__=='__main__':
    main()
