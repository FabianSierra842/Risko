# Ejemplo de carpeta de dashboard

Copie `dashboard.json` a la raíz de un dashboard solamente cuando necesite
guardar y restaurar filtros por usuario. El campo `archivo` puede contener el
nombre fijo del HTML o un patrón, por ejemplo `dashboard_*.html`.

Los controles configurables del HTML deben tener `id`, `name` o `data-filter`.
Los dashboards generados con Dashy son compatibles de forma automática.

Estructura recomendada:

```text
Dashboards\
└── Dashboard de ejemplo\
    ├── dashboard.json
    ├── 2026-08-17\
    │   └── dashboard.html
    └── 2026-08-18\
        └── dashboard.html
```

Si no se copia `dashboard.json`, el portal igualmente descubre el HTML por el
nombre de la carpeta y la fecha. En ese modo no modifica el dashboard ni
muestra la barra de configuraciones.
