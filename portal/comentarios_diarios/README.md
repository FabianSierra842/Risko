# Comentarios diarios del Portal RISKO

Esta carpeta contiene el comentario de mercado que el Portal RISKO muestra junto a la vista previa de cualquier dashboard. El comentario es transversal: para una misma fecha se presenta el mismo texto sin importar el módulo seleccionado.

## Cómo publicar un comentario

1. Copie `plantilla.md` dentro de la carpeta del año correspondiente.
2. Renombre la copia con la fecha exacta en formato `AAAA-MM-DD.md`. Por ejemplo: `2026/2026-08-19.md`.
3. Edite el contenido y guarde el archivo como texto UTF-8.
4. En el Portal RISKO seleccione la fecha y pulse **Actualizar**. No es necesario volver a publicar el dashboard ni reiniciar el portal.

La ubicación productiva es:

```text
Portal Riesgos de Mercado/
└── Comentarios diarios/
    ├── README.md
    ├── plantilla.md
    └── 2026/
        └── 2026-08-19.md
```

## Formato admitido

El formato oficial es Markdown (`.md`). Se permiten:

- títulos con `#`, `##` o `###`;
- párrafos separados por una línea en blanco;
- viñetas iniciadas con `-`;
- texto en negrita entre `**doble asterisco**`;
- tablas Markdown con encabezado y una fila separadora, por ejemplo
  `| Indicador | Valor |` seguida de `|---|---:|`.

También se admite un archivo `.txt` como contingencia, con el mismo nombre de fecha. Si existen ambos, el Portal prioriza el `.md`. No use Word, Excel, PDF, HTML ni JSON para los comentarios.

El archivo no debe superar 256 KB. Si no existe un archivo para la fecha seleccionada, el Portal lo indicará sin afectar la vista previa del dashboard.
