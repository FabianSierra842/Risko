# Operación, publicación y rollback de Portal RISKO

Este documento describe cómo está distribuido Portal RISKO, cómo reciben las
actualizaciones los usuarios y cómo regresar de forma segura a una versión
anterior.

## Ubicaciones

Desarrollo y control de versiones:

```text
\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\
3 Jefatura de Riesgo de Mercado\Proyecto Risko\portal
```

Producción:

```text
\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\
Portal Riesgos de Mercado
├── Dashboards\                         dashboards HTML publicados
├── Aplicaciones\                       aplicaciones visibles en el portal
├── Configuraciones\                    preferencias por usuario
└── Sistema Portal\
    ├── portal.json                     manifiesto de la versión activa
    ├── Instalador\
    │   └── Instalar Portal RISKO.exe   instalador que se comparte una sola vez
    ├── Versiones\
    │   └── <versión>\
    │       ├── release.json            manifiesto inmutable de esa versión
    │       └── PortalRisko\             ejecutable y runtime de la aplicación
    └── Legado\                         respaldos de distribuciones anteriores
```

El acceso directo del usuario apunta al launcher instalado en:

```text
%LOCALAPPDATA%\PortalRisko\Launcher
```

En cada inicio, el launcher consulta `Sistema Portal\portal.json`. Si cambia la
versión o el hash, copia y valida la aplicación en
`%LOCALAPPDATA%\PortalRisko\App` y después la ejecuta localmente. El launcher,
el instalador y el acceso directo no necesitan regenerarse para una
actualización ordinaria de la aplicación.

## Publicar una versión

Las versiones publicadas son inmutables. Nunca se debe sobrescribir o
reutilizar un número existente.

1. Cambiar `APP_VERSION` en `script.py`.
2. Ejecutar las pruebas desde la carpeta `portal`:

   ```powershell
   python -m py_compile script.py
   python script.py --self-test
   git status --short
   ```

3. Publicar indicando siempre la nueva versión de forma explícita:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass `
     -File .\publicar_portal.ps1 -Version 2.1.13
   ```

4. Verificar que `Sistema Portal\portal.json` tenga la nueva versión, que el
   ejecutable exista y que su SHA-256 coincida con `entrypoint_sha256`.
5. Crear el tag Git correspondiente después de una publicación satisfactoria:

   ```powershell
   git tag -a v2.0.9 -m "Portal RISKO 2.0.9"
   ```

La opción `-ActualizarLanzador` solo se usa cuando cambia `launcher.py`, el
instalador o sus recursos. No se requiere para cambios normales en
`script.py`.

## Rollback seguro

Un rollback no elimina la versión nueva ni recompila la aplicación. Solamente
activa el manifiesto inmutable de una versión anterior. Los usuarios que ya
tengan el portal abierto continuarán en su sesión actual; el cambio se aplica
en su próximo inicio.

Ejecutar desde PowerShell y cambiar únicamente `$VersionObjetivo`:

```powershell
$VersionObjetivo = "2.0.6"
$Sistema = "\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado\Sistema Portal"
$PortalActivo = Join-Path $Sistema "portal.json"
$Release = Join-Path $Sistema "Versiones\$VersionObjetivo\release.json"

if ($VersionObjetivo -notmatch "^[A-Za-z0-9._-]+$") {
    throw "Número de versión inválido."
}
if (-not (Test-Path -LiteralPath $Release -PathType Leaf)) {
    throw "No existe el manifiesto de la versión $VersionObjetivo."
}

$Manifiesto = Get-Content -LiteralPath $Release -Raw | ConvertFrom-Json
if ([string]$Manifiesto.version -ne $VersionObjetivo) {
    throw "La versión del release.json no coincide."
}

$Ejecutable = Join-Path $Sistema (
    ([string]$Manifiesto.entrypoint).Replace("/", "\")
)
$SistemaResuelto = [IO.Path]::GetFullPath($Sistema)
$EjecutableResuelto = [IO.Path]::GetFullPath($Ejecutable)
if (-not $EjecutableResuelto.StartsWith(
    $SistemaResuelto,
    [StringComparison]::OrdinalIgnoreCase
)) {
    throw "El manifiesto apunta fuera de Sistema Portal."
}
if (-not (Test-Path -LiteralPath $EjecutableResuelto -PathType Leaf)) {
    throw "No existe el ejecutable de la versión objetivo."
}

$HashReal = (
    Get-FileHash -LiteralPath $EjecutableResuelto -Algorithm SHA256
).Hash.ToLowerInvariant()
$HashEsperado = ([string]$Manifiesto.entrypoint_sha256).ToLowerInvariant()
if ($HashReal -ne $HashEsperado) {
    throw "El SHA-256 del ejecutable no coincide. Rollback cancelado."
}

$Respaldos = Join-Path $Sistema "Legado\Manifiestos"
New-Item -ItemType Directory -Force -Path $Respaldos | Out-Null
Copy-Item -LiteralPath $PortalActivo -Destination (
    Join-Path $Respaldos ("portal-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
)

$Temporal = Join-Path $Sistema (
    ".rollback." + [Guid]::NewGuid().ToString("N") + ".tmp"
)
Copy-Item -LiteralPath $Release -Destination $Temporal
Move-Item -LiteralPath $Temporal -Destination $PortalActivo -Force

$Activo = Get-Content -LiteralPath $PortalActivo -Raw | ConvertFrom-Json
if ([string]$Activo.version -ne $VersionObjetivo) {
    throw "No fue posible activar la versión solicitada."
}
Write-Host "Portal RISKO $VersionObjetivo activado correctamente."
```

Para volver posteriormente a la versión más nueva se ejecuta el mismo
procedimiento usando su número como `$VersionObjetivo`.

## Verificación posterior

Después de publicar o hacer rollback:

1. Confirmar la versión activa:

   ```powershell
   Get-Content "\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado\Sistema Portal\portal.json"
   ```

2. Abrir el acceso directo local de Portal RISKO.
3. Confirmar que la ventana de carga muestre la versión esperada.
4. Confirmar que el portal abra y encuentre los dashboards publicados.
5. Revisar, si fuera necesario:

   ```text
   %LOCALAPPDATA%\PortalRisko\Logs\launcher.log
   ```

## Reglas operativas

- No editar archivos dentro de `Sistema Portal\Versiones\<versión>`.
- No borrar versiones anteriores; son la base del rollback.
- No apuntar `portal.json` a una carpeta temporal o a un ejecutable sin validar.
- No compartir un ejecutable ubicado en el fileserver como acceso diario.
- Compartir solamente `Instalar Portal RISKO.exe` con usuarios nuevos.
- Una actualización de la aplicación no requiere reinstalar el launcher.
