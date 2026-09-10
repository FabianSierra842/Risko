[CmdletBinding()]
param(
    [Parameter()]
    [ValidatePattern("^[A-Za-z0-9._-]+$")]
    [string]$Version = "2.1.13",

    [Parameter()]
    [switch]$ActualizarLanzador
)

$ErrorActionPreference = "Stop"

$PortalDesarrollo = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProyectoRisko = (Resolve-Path (Join-Path $PortalDesarrollo "..")).ProviderPath
$Produccion = "\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado"
$Dashboards = Join-Path $Produccion "Dashboards"
$Aplicaciones = Join-Path $Produccion "Aplicaciones"
$Configuraciones = Join-Path $Produccion "Configuraciones"
$Comentarios = Join-Path $Produccion "Comentarios diarios"
$SistemaPortal = Join-Path $Produccion "Sistema Portal"
$Instaladores = Join-Path $SistemaPortal "Instalador"
$Releases = Join-Path $SistemaPortal "Versiones"
$Legado = Join-Path $SistemaPortal "Legado"
$ReleaseFinal = Join-Path $Releases $Version
$ManifiestoProduccion = Join-Path $SistemaPortal "portal.json"
$InstaladorProduccion = Join-Path $Instaladores "Instalar Portal RISKO.exe"
$CompilarLanzador = $ActualizarLanzador -or -not (
    Test-Path -LiteralPath $InstaladorProduccion -PathType Leaf
)

if (
    (Test-Path -LiteralPath $ReleaseFinal) -or
    (Test-Path -LiteralPath (Join-Path $Produccion "releases\$Version"))
) {
    throw "La version $Version ya existe. Las versiones publicadas son inmutables; use un numero nuevo."
}

$Requeridos = @(
    (Join-Path $PortalDesarrollo "script.py"),
    (Join-Path $PortalDesarrollo "assets\portal-risko.ico")
)
if ($CompilarLanzador) {
    $Requeridos += @(
        (Join-Path $PortalDesarrollo "launcher.py"),
        (Join-Path $PortalDesarrollo "instalador_launcher.py")
    )
}
foreach ($RutaRequerida in $Requeridos) {
    if (-not (Test-Path -LiteralPath $RutaRequerida -PathType Leaf)) {
        throw "No se encontro el archivo requerido: $RutaRequerida"
    }
}

& python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller no esta disponible en el Python activo."
}

$IdCompilacion = [Guid]::NewGuid().ToString("N")
$RaizTemporal = Join-Path $env:TEMP "risko_portal_build_$IdCompilacion"
$DistAplicacion = Join-Path $RaizTemporal "dist_app"
$DistLanzador = Join-Path $RaizTemporal "dist_launcher"
$DistInstalador = Join-Path $RaizTemporal "dist_installer"
$WorkAplicacion = Join-Path $RaizTemporal "work_app"
$WorkLanzador = Join-Path $RaizTemporal "work_launcher"
$WorkInstalador = Join-Path $RaizTemporal "work_installer"
$Specs = Join-Path $RaizTemporal "specs"
$ReleaseTemporal = Join-Path $Releases ".$Version.$IdCompilacion.tmp"
$VersionInfoAplicacion = Join-Path $RaizTemporal "version_info_app.txt"
$VersionInfoLanzador = Join-Path $RaizTemporal "version_info_launcher.txt"
$VersionInfoInstalador = Join-Path $RaizTemporal "version_info_installer.txt"
$PayloadLanzador = Join-Path $RaizTemporal "launcher_payload.zip"
$ManifiestoPaquete = Join-Path $RaizTemporal "launcher-package.json"
$Utf8SinBom = New-Object System.Text.UTF8Encoding($false)

$RecursosInterfaz = Join-Path $ProyectoRisko "aplicaciones\interfaz_risko\assets"
$LogoPequeno = Join-Path $ProyectoRisko "Herramientas\dashy\logo-risko-56.png"
$LogoGrande = Join-Path $RecursosInterfaz "logo-risko-alta-resolucion.png"
$LogoBanco = Join-Path $RecursosInterfaz "escudo-banco-bogota-sin-fondo.png"
$IconoPortal = Join-Path $PortalDesarrollo "assets\portal-risko.ico"
$SeparadorDatos = [IO.Path]::PathSeparator
$ArgumentosDatos = @()
foreach ($Logo in @($LogoPequeno, $LogoGrande, $LogoBanco, $IconoPortal)) {
    if (Test-Path -LiteralPath $Logo -PathType Leaf) {
        $ArgumentosDatos += @("--add-data", "$Logo$SeparadorDatos.")
    }
}

$PartesVersion = @()
foreach ($Parte in $Version.Split(".")) {
    if ($Parte -match "^\d+$") {
        $PartesVersion += [int]$Parte
    }
    else {
        $PartesVersion += 0
    }
}
while ($PartesVersion.Count -lt 4) {
    $PartesVersion += 0
}
$TuplaVersion = "$($PartesVersion[0]), $($PartesVersion[1]), $($PartesVersion[2]), $($PartesVersion[3])"

function New-VersionInfo {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Description,
        [Parameter(Mandatory)]
        [string]$InternalName,
        [Parameter(Mandatory)]
        [string]$OriginalFilename
    )

    $Content = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($TuplaVersion),
    prodvers=($TuplaVersion),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '240A04B0',
        [
          StringStruct('CompanyName', 'Banco de Bogota'),
          StringStruct('FileDescription', '$Description'),
          StringStruct('FileVersion', '$Version'),
          StringStruct('InternalName', '$InternalName'),
          StringStruct('LegalCopyright', 'Banco de Bogota'),
          StringStruct('OriginalFilename', '$OriginalFilename'),
          StringStruct('ProductName', 'Portal RISKO'),
          StringStruct('ProductVersion', '$Version')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [0x240A, 1200])])
  ]
)
"@
    [IO.File]::WriteAllText($Path, $Content, $Utf8SinBom)
}

function Move-PreviousDistribution {
    $OldReleases = Join-Path $Produccion "releases"
    if (Test-Path -LiteralPath $OldReleases -PathType Container) {
        foreach ($OldRelease in Get-ChildItem -LiteralPath $OldReleases -Force) {
            $Destination = Join-Path $Releases $OldRelease.Name
            if (-not (Test-Path -LiteralPath $Destination)) {
                Move-Item -LiteralPath $OldRelease.FullName -Destination $Destination
            }
        }
        if ((Get-ChildItem -LiteralPath $OldReleases -Force | Measure-Object).Count -eq 0) {
            [IO.Directory]::Delete($OldReleases)
        }
    }

    $PreviousItems = @(
        (Join-Path $Produccion "PortalRisko.exe"),
        (Join-Path $Produccion "Acceso Portal RISKO.lnk"),
        (Join-Path $Produccion "portal.json")
    )
    $PreviousItems += @(
        Get-ChildItem -LiteralPath $Produccion -Directory -Filter "_launcher_runtime_*" |
            Select-Object -ExpandProperty FullName
    )
    $PreviousItems = @(
        $PreviousItems | Where-Object { Test-Path -LiteralPath $_ }
    )

    if ($PreviousItems.Count -gt 0) {
        $Archive = Join-Path $Legado (
            "Distribucion anterior " + (Get-Date -Format "yyyyMMdd-HHmmss")
        )
        New-Item -ItemType Directory -Force -Path $Archive | Out-Null
        foreach ($Item in $PreviousItems) {
            $Resolved = [IO.Path]::GetFullPath($Item)
            $ProductionResolved = [IO.Path]::GetFullPath($Produccion)
            if (-not $Resolved.StartsWith(
                $ProductionResolved,
                [StringComparison]::OrdinalIgnoreCase
            )) {
                throw "Se rechazo mover una ruta fuera de produccion: $Resolved"
            }
            Move-Item -LiteralPath $Resolved -Destination $Archive
        }
    }

    if (Test-Path -LiteralPath $OldReleases -PathType Container) {
        $Remaining = @(Get-ChildItem -LiteralPath $OldReleases -Force)
        if ($Remaining.Count -gt 0) {
            $Archive = Join-Path $Legado (
                "Releases anteriores " + (Get-Date -Format "yyyyMMdd-HHmmss")
            )
            Move-Item -LiteralPath $OldReleases -Destination $Archive
        }
    }
}

try {
    New-Item -ItemType Directory -Force -Path $RaizTemporal, $Specs | Out-Null
    New-VersionInfo `
        -Path $VersionInfoAplicacion `
        -Description "Portal RISKO" `
        -InternalName "PortalRisko" `
        -OriginalFilename "PortalRisko.exe"
    New-VersionInfo `
        -Path $VersionInfoLanzador `
        -Description "Lanzador local Portal RISKO" `
        -InternalName "PortalRiskoLauncher" `
        -OriginalFilename "PortalRisko.exe"
    New-VersionInfo `
        -Path $VersionInfoInstalador `
        -Description "Instalador Portal RISKO" `
        -InternalName "PortalRiskoInstaller" `
        -OriginalFilename "Instalar Portal RISKO.exe"

    Write-Host "[1/5] Compilando aplicacion Portal RISKO $Version..."
    $ArgsAplicacion = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--icon", $IconoPortal,
        "--version-file", $VersionInfoAplicacion,
        "--name", "PortalRisko",
        "--distpath", $DistAplicacion,
        "--workpath", $WorkAplicacion,
        "--specpath", $Specs
    ) + $ArgumentosDatos + @((Join-Path $PortalDesarrollo "script.py"))
    & python @ArgsAplicacion
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo la compilacion de la aplicacion."
    }

    if ($CompilarLanzador) {
        Write-Host "[2/5] Compilando Launcher local de inicio rapido..."
        $ArgsLanzador = @(
            "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onedir",
            "--windowed",
            "--icon", $IconoPortal,
            "--version-file", $VersionInfoLanzador,
            "--name", "PortalRisko",
            "--contents-directory", "_runtime",
            "--distpath", $DistLanzador,
            "--workpath", $WorkLanzador,
            "--specpath", $Specs
        ) + $ArgumentosDatos + @((Join-Path $PortalDesarrollo "launcher.py"))
        & python @ArgsLanzador
        if ($LASTEXITCODE -ne 0) {
            throw "Fallo la compilacion del Launcher."
        }

        $CarpetaLanzadorCompilado = Join-Path $DistLanzador "PortalRisko"
        $ExeLanzadorCompilado = Join-Path $CarpetaLanzadorCompilado "PortalRisko.exe"
        if (-not (Test-Path -LiteralPath $ExeLanzadorCompilado -PathType Leaf)) {
            throw "No se genero $ExeLanzadorCompilado"
        }

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::CreateFromDirectory(
            $CarpetaLanzadorCompilado,
            $PayloadLanzador,
            [IO.Compression.CompressionLevel]::Optimal,
            $false
        )
        $HashLanzador = (
            Get-FileHash -LiteralPath $ExeLanzadorCompilado -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        $HashPayload = (
            Get-FileHash -LiteralPath $PayloadLanzador -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        $Paquete = [ordered]@{
            schema_version = 1
            launcher_version = $Version
            launcher_executable = "PortalRisko.exe"
            launcher_sha256 = $HashLanzador
            payload_sha256 = $HashPayload
            created_at = (Get-Date).ToString("o")
        }
        [IO.File]::WriteAllText(
            $ManifiestoPaquete,
            ($Paquete | ConvertTo-Json -Depth 4),
            $Utf8SinBom
        )

        Write-Host "[3/5] Empaquetando instalador autocontenido..."
        $DatosInstalador = $ArgumentosDatos + @(
            "--add-data", "$PayloadLanzador$SeparadorDatos.",
            "--add-data", "$ManifiestoPaquete$SeparadorDatos."
        )
        $ArgsInstalador = @(
            "-m", "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--icon", $IconoPortal,
            "--version-file", $VersionInfoInstalador,
            "--name", "Instalar Portal RISKO",
            "--distpath", $DistInstalador,
            "--workpath", $WorkInstalador,
            "--specpath", $Specs
        ) + $DatosInstalador + @(
            (Join-Path $PortalDesarrollo "instalador_launcher.py")
        )
        & python @ArgsInstalador
        if ($LASTEXITCODE -ne 0) {
            throw "Fallo la compilacion del instalador."
        }
    }
    else {
        Write-Host "[2/5] Conservando el Launcher local existente."
        Write-Host "[3/5] Conservando el instalador autocontenido existente."
    }

    $AplicacionCompilada = Join-Path $DistAplicacion "PortalRisko"
    $ExeAplicacionCompilada = Join-Path $AplicacionCompilada "PortalRisko.exe"
    if (-not (Test-Path -LiteralPath $ExeAplicacionCompilada -PathType Leaf)) {
        throw "No se genero $ExeAplicacionCompilada"
    }

    Write-Host "[4/5] Publicando release inmutable..."
    New-Item -ItemType Directory -Force -Path @(
        $Produccion,
        $Dashboards,
        $Aplicaciones,
        $Configuraciones,
        $Comentarios,
        $SistemaPortal,
        $Instaladores,
        $Releases,
        $Legado
    ) | Out-Null
    New-Item -ItemType Directory -Path $ReleaseTemporal | Out-Null
    Copy-Item `
        -LiteralPath $AplicacionCompilada `
        -Destination (Join-Path $ReleaseTemporal "PortalRisko") `
        -Recurse

    $ExeRelease = Join-Path $ReleaseTemporal "PortalRisko\PortalRisko.exe"
    $Hash = (
        Get-FileHash -Algorithm SHA256 -LiteralPath $ExeRelease
    ).Hash.ToLowerInvariant()
    $PublicadoEn = (Get-Date).ToString("o")
    $PublicadoPor = "$env:USERDOMAIN\$env:USERNAME"
    $RutaRelativaExe = "Versiones/$Version/PortalRisko/PortalRisko.exe"

    $Manifiesto = [ordered]@{
        schema_version = 1
        app = "Portal RISKO"
        version = $Version
        entrypoint = $RutaRelativaExe
        entrypoint_sha256 = $Hash
        dashboards_dir = "Dashboards"
        applications_dir = "Aplicaciones"
        config_dir = "Configuraciones"
        comments_dir = "Comentarios diarios"
        project_root = $ProyectoRisko
        published_at = $PublicadoEn
        published_by = $PublicadoPor
    }
    $JsonManifiesto = $Manifiesto | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText(
        (Join-Path $ReleaseTemporal "release.json"),
        $JsonManifiesto,
        $Utf8SinBom
    )
    Move-Item -LiteralPath $ReleaseTemporal -Destination $ReleaseFinal

    Write-Host "[5/5] Activando version y ordenando produccion..."
    if ($CompilarLanzador) {
        $InstaladorCompilado = Join-Path $DistInstalador "Instalar Portal RISKO.exe"
        if (-not (Test-Path -LiteralPath $InstaladorCompilado -PathType Leaf)) {
            throw "No se genero $InstaladorCompilado"
        }
        $InstaladorTemporal = Join-Path $Instaladores ".$IdCompilacion.installer.tmp"
        Copy-Item -LiteralPath $InstaladorCompilado -Destination $InstaladorTemporal
        Move-Item `
            -LiteralPath $InstaladorTemporal `
            -Destination $InstaladorProduccion `
            -Force
    }

    $ManifiestoTemporal = Join-Path $SistemaPortal ".$IdCompilacion.portal.tmp"
    [IO.File]::WriteAllText($ManifiestoTemporal, $JsonManifiesto, $Utf8SinBom)
    Move-Item `
        -LiteralPath $ManifiestoTemporal `
        -Destination $ManifiestoProduccion `
        -Force

    Move-PreviousDistribution

    Write-Host ""
    Write-Host "Portal RISKO $Version publicado correctamente."
    Write-Host "Compartir una sola vez: $InstaladorProduccion"
    Write-Host "Manifiesto activo: $ManifiestoProduccion"
    Write-Host "Release: $ReleaseFinal"
    Write-Host "SHA-256 aplicacion: $Hash"
}
finally {
    if (Test-Path -LiteralPath $RaizTemporal) {
        $TemporalResuelto = [IO.Path]::GetFullPath($RaizTemporal)
        $TempRaizResuelta = [IO.Path]::GetFullPath($env:TEMP)
        if ($TemporalResuelto.StartsWith(
            $TempRaizResuelta,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item -LiteralPath $TemporalResuelto -Recurse -Force
        }
    }
    if (Test-Path -LiteralPath $ReleaseTemporal) {
        $ReleaseTemporalResuelto = [IO.Path]::GetFullPath($ReleaseTemporal)
        $ReleasesResuelto = [IO.Path]::GetFullPath($Releases)
        if ($ReleaseTemporalResuelto.StartsWith(
            $ReleasesResuelto,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item -LiteralPath $ReleaseTemporalResuelto -Recurse -Force
        }
    }
}
