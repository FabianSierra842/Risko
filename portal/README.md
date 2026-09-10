# Portal RISKO

Portal de escritorio para consultar los dashboards HTML publicados de Riesgo de
Mercado. El código fuente y los scripts de despliegue viven en
`Proyecto Risko\portal`; producción utiliza esta estructura:

El flujo completo desde los cálculos de RISKO hasta el cliente local está en
[Arquitectura de RISKO y Portal RISKO](../Documentación/ARQUITECTURA_RISKO_PORTAL.md).

```text
\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado
├── Dashboards\                       HTML publicados
├── Aplicaciones\                     ejecutables visibles en el portal
├── Configuraciones\                  favoritos y vistas por usuario
└── Sistema Portal\
    ├── portal.json                   versión activa
    ├── Instalador\
    │   └── Instalar Portal RISKO.exe único archivo que se comparte
    ├── Versiones\
    │   └── 2.0.6\PortalRisko\        aplicación y dependencias inmutables
    └── Legado\                       respaldo de la distribución anterior
```

## Arquitectura de inicio rápido

El usuario ejecuta `Instalar Portal RISKO.exe` una sola vez. Es un instalador
autocontenido que:

1. valida su contenido con SHA-256;
2. instala el launcher fijo en
   `%LOCALAPPDATA%\PortalRisko\Launcher`;
3. crea `Portal RISKO.lnk` en el escritorio y el menú Inicio;
4. abre inmediatamente el launcher local.

El acceso directo apunta al disco local, no al fileserver. Por ello la ventana
de carga aparece rápidamente incluso en portátiles. El runtime Python del
launcher también queda local y no tiene que extraerse en cada apertura.

En cada inicio el launcher consulta solamente
`Sistema Portal\portal.json`. Si hay una versión nueva, copia una vez la
aplicación completa a `%LOCALAPPDATA%\PortalRisko\App`, valida el ejecutable y
lo abre localmente. Si la versión ya está instalada, únicamente valida su
integridad. El launcher conserva además el último manifiesto válido como
contingencia cuando el servidor no responde.

El launcher es fijo: una publicación normal actualiza únicamente la aplicación
y el manifiesto. Solo se debe regenerar el instalador cuando cambie la lógica,
el icono o los recursos del propio launcher.

## Desarrollo

Desde la raíz de `Proyecto Risko`:

```powershell
python portal\script.py
python portal\script.py --self-test
```

Variables de entorno admitidas:

- `PORTAL_RISKO_PUBLICADOS`: cambia la biblioteca de dashboards.
- `PORTAL_RISKO_APLICACIONES`: cambia la biblioteca de ejecutables.
- `PORTAL_RISKO_CONFIG_DIR`: cambia la carpeta de configuraciones.
- `PORTAL_RISKO_ROOT`: cambia la raíz del proyecto de desarrollo.
- `PORTAL_RISKO_PRODUCCION`: cambia la raíz productiva consultada por el
  launcher; se usa principalmente en validaciones controladas.

## Publicar una versión del portal

Para una actualización ordinaria:

```powershell
powershell -ExecutionPolicy Bypass -File portal\publicar_portal.ps1 `
  -Version 2.1.13
```

Para cambiar también el launcher y regenerar el instalador:

```powershell
powershell -ExecutionPolicy Bypass -File portal\publicar_portal.ps1 `
  -Version 2.0.8 -ActualizarLanzador
```

También se puede ejecutar `compilar_risko.bat`. Los releases son inmutables:
nunca se debe reutilizar un número de versión.

## Entrega a usuarios

Compartir únicamente:

```text
\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado\
Sistema Portal\Instalador\Instalar Portal RISKO.exe
```

El usuario lo ejecuta una vez. Después debe usar el acceso `Portal RISKO` que
queda en su escritorio o menú Inicio. No se comparte un `.lnk` de red ni se
abren directamente los ejecutables guardados en `Versiones`.

## Publicar Portfolio Position Monitor

En `aplicaciones\interfaz_risko`, seleccionar la fecha y usar **Publicar en
portal**. El proceso:

1. genera el HTML de desarrollo;
2. lo copia atómicamente a
   `Dashboards\Portfolio Position Monitor\AAAA-MM-DD`;
3. guarda `publicacion.json` con usuario, fecha, fechas reales de los datos,
   tamaño y SHA-256;
4. lo deja disponible en el siguiente refresco del portal.

La base de pruebas está bloqueada para publicaciones de producción.

## Agregar dashboards por carpeta

No es necesario cambiar el código ni publicar otra versión del Portal para
agregar un dashboard. Cree una carpeta dentro de `Dashboards`, copie el HTML y
presione **Actualizar** en el Portal. La estructura mínima es:

```text
Dashboards\
└── Riesgo de Liquidez\
    └── dashboard.html
```

Sin configuración adicional, el recurso se identifica por el nombre de la
carpeta y su fecha se toma, en orden, de `publicacion.json`, de una carpeta o
nombre con fecha (`AAAA-MM-DD`) y finalmente de la modificación del HTML. Para
conservar varias fechas se recomienda una subcarpeta por fecha:

```text
Dashboards\Riesgo de Liquidez\2026-08-18\dashboard.html
```

En el modo simple el Portal sirve el HTML sin modificarlo y no habilita
configuraciones de filtros.

Para parametrizar nombre, descripción, archivo principal y configuraciones por
usuario, agregue `dashboard.json` en la raíz del dashboard. Hay un manifiesto
listo para copiar en `portal\ejemplos\dashboard.json`. `archivo` admite un
nombre o patrón; `configuracion.habilitada` debe ser `true` para insertar la
barra de guardar/restaurar filtros. Los controles HTML deben tener `id`, `name`
o `data-filter`; Dashy ya cumple este contrato.

## Configuraciones y vista previa

Dentro de un dashboard parametrizado, **Guardar** crea una configuración con los filtros
actuales y **Actualizar** aplica a la vista la configuración guardada
seleccionada. **Marcar favorita** define cuál configuración se usa para generar
la vista previa del dashboard en el portal; si no hay favorita, la vista previa
usa la presentación predeterminada. La configuración activa y la favorita se
guardan por usuario Windows y se comparten entre las fechas de un mismo
dashboard lógico.
