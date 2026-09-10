[CmdletBinding()]
param(
    [Parameter()]
    [string]$Produccion = "\\ISILONSMBPROD\Gerencia_Riesgo_De_Tesoreria\Portal Riesgos de Mercado"
)

$ErrorActionPreference = "Stop"

$Instalador = Join-Path $Produccion "Sistema Portal\Instalador\Instalar Portal RISKO.exe"
$IdPrueba = [Guid]::NewGuid().ToString("N")
$RaizPrueba = Join-Path $env:TEMP "risko_readonly_verify_$IdPrueba"
$Instalacion = Join-Path $RaizPrueba "PortalRisko\Launcher"
$Accesos = Join-Path $RaizPrueba "Shortcuts"
$LocalAppData = Join-Path $RaizPrueba "LocalAppData"
$ConfiguracionesProduccion = Join-Path $Produccion "Configuraciones"

$VariablesAnteriores = @{
    LOCALAPPDATA = $env:LOCALAPPDATA
    PORTAL_RISKO_INSTALL_DIR = $env:PORTAL_RISKO_INSTALL_DIR
    PORTAL_RISKO_SHORTCUT_DIR = $env:PORTAL_RISKO_SHORTCUT_DIR
    PORTAL_RISKO_PRODUCCION = $env:PORTAL_RISKO_PRODUCCION
    PORTAL_RISKO_CONFIG_DIR = $env:PORTAL_RISKO_CONFIG_DIR
    PORTAL_RISKO_PUBLICADOS = $env:PORTAL_RISKO_PUBLICADOS
    PORTAL_RISKO_APLICACIONES = $env:PORTAL_RISKO_APLICACIONES
}

function Get-ProductionConfigSnapshot {
    if (-not (Test-Path -LiteralPath $ConfiguracionesProduccion -PathType Container)) {
        return @()
    }
    return @(
        Get-ChildItem -LiteralPath $ConfiguracionesProduccion -Recurse -File |
            Sort-Object FullName |
            ForEach-Object {
                "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)"
            }
    )
}

function Remove-OrphanedReadOnlyTests {
    $TempResuelto = [IO.Path]::GetFullPath($env:TEMP)
    $Procesos = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq "PortalRisko.exe" -and
                $_.ExecutablePath -like (Join-Path $env:TEMP "risko_readonly_verify_*")
            }
    )
    foreach ($Proceso in $Procesos) {
        $EjecutableResuelto = [IO.Path]::GetFullPath($Proceso.ExecutablePath)
        if (
            $EjecutableResuelto.StartsWith(
                $TempResuelto,
                [StringComparison]::OrdinalIgnoreCase
            ) -and
            $EjecutableResuelto -match "risko_readonly_verify_[0-9a-f]+"
        ) {
            Stop-Process -Id $Proceso.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    Start-Sleep -Milliseconds 250
    foreach ($Carpeta in Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter "risko_readonly_verify_*") {
        $CarpetaResuelta = [IO.Path]::GetFullPath($Carpeta.FullName)
        if (
            $CarpetaResuelta.StartsWith(
                $TempResuelto,
                [StringComparison]::OrdinalIgnoreCase
            ) -and
            $Carpeta.Name -match "^risko_readonly_verify_[0-9a-f]+$"
        ) {
            Remove-Item -LiteralPath $CarpetaResuelta -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    Remove-OrphanedReadOnlyTests
    if (-not (Test-Path -LiteralPath $Instalador -PathType Leaf)) {
        throw "No se encontro el instalador: $Instalador"
    }

    New-Item -ItemType Directory -Path $RaizPrueba | Out-Null
    $Antes = Get-ProductionConfigSnapshot

    $env:LOCALAPPDATA = $LocalAppData
    $env:PORTAL_RISKO_INSTALL_DIR = $Instalacion
    $env:PORTAL_RISKO_SHORTCUT_DIR = $Accesos
    $env:PORTAL_RISKO_PRODUCCION = $Produccion

    $ProcesoInstalador = Start-Process `
        -FilePath $Instalador `
        -ArgumentList "--install-test" `
        -Wait `
        -PassThru `
        -WindowStyle Hidden
    if ($ProcesoInstalador.ExitCode -ne 0) {
        throw "El instalador termino con codigo $($ProcesoInstalador.ExitCode)."
    }

    $Launcher = Join-Path $Instalacion "PortalRisko.exe"
    $MarcadorInstalacion = Join-Path $Instalacion "install.json"
    if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) {
        throw "El instalador no preparo el Launcher local."
    }
    $InfoInstalacion = Get-Content -LiteralPath $MarcadorInstalacion -Raw |
        ConvertFrom-Json

    # El release productivo completo tiene mas de mil archivos. Para aislar la
    # prueba de permisos de la latencia/antivirus SMB se usa un release minimo,
    # de solo lectura, que recorre la misma logica del Launcher compilado.
    $ProduccionPrueba = Join-Path $RaizPrueba "ProduccionSoloLectura"
    $SistemaPrueba = Join-Path $ProduccionPrueba "Sistema Portal"
    $ReleasePrueba = Join-Path $SistemaPrueba "Versiones\2.1.3-test\PortalRisko"
    New-Item -ItemType Directory -Path $ReleasePrueba -Force | Out-Null
    $EjecutablePrueba = Join-Path $ReleasePrueba "PortalRisko.exe"
    Copy-Item -LiteralPath "$env:SystemRoot\System32\where.exe" -Destination $EjecutablePrueba
    $HashPrueba = (
        Get-FileHash -Algorithm SHA256 -LiteralPath $EjecutablePrueba
    ).Hash.ToLowerInvariant()
    $ManifiestoPrueba = [ordered]@{
        schema_version = 1
        app = "Portal RISKO"
        version = "2.1.3-test"
        entrypoint = "Versiones/2.1.3-test/PortalRisko/PortalRisko.exe"
        entrypoint_sha256 = $HashPrueba
        dashboards_dir = "Dashboards"
        applications_dir = "Aplicaciones"
        config_dir = "Configuraciones"
    } | ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText(
        (Join-Path $SistemaPrueba "portal.json"),
        $ManifiestoPrueba,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Get-ChildItem -LiteralPath $ProduccionPrueba -Recurse -File |
        ForEach-Object { $_.IsReadOnly = $true }

    $env:PORTAL_RISKO_PRODUCCION = $ProduccionPrueba
    $ProcesoLauncher = Start-Process `
        -FilePath $Launcher `
        -ArgumentList "--self-test" `
        -Wait `
        -PassThru `
        -WindowStyle Hidden
    if ($ProcesoLauncher.ExitCode -ne 0) {
        throw "El Launcher termino con codigo $($ProcesoLauncher.ExitCode)."
    }

    $MarcadorRelease = Get-ChildItem `
        -LiteralPath (Join-Path $LocalAppData "PortalRisko\App") `
        -Recurse `
        -File `
        -Filter ".release.json" |
        Select-Object -First 1
    if ($null -eq $MarcadorRelease) {
        throw "El Launcher no preparo la version productiva en cache local."
    }
    $InfoRelease = Get-Content -LiteralPath $MarcadorRelease.FullName -Raw |
        ConvertFrom-Json

    # Simula un Launcher anterior que intenta pasar la antigua ruta compartida.
    # La aplicacion vigente debe ignorarla y escribir solo en LOCALAPPDATA.
    $env:PORTAL_RISKO_PRODUCCION = $Produccion
    $env:PORTAL_RISKO_CONFIG_DIR = $ConfiguracionesProduccion
    $env:PORTAL_RISKO_PUBLICADOS = Join-Path $Produccion "Dashboards"
    $env:PORTAL_RISKO_APLICACIONES = Join-Path $Produccion "Aplicaciones"
    $PortalFuente = Join-Path $PSScriptRoot "script.py"
    $SalidaPortal = @(& python $PortalFuente --self-test 2>&1)
    $CodigoPortal = $LASTEXITCODE
    if ($CodigoPortal -ne 0) {
        throw "La autoprueba del Portal termino con codigo $CodigoPortal."
    }

    $ConfiguracionesLocales = Join-Path $LocalAppData "PortalRisko\Configuraciones"
    if (-not (Test-Path -LiteralPath $ConfiguracionesLocales -PathType Container)) {
        throw "El Portal no creo la carpeta local de configuraciones."
    }

    $Despues = Get-ProductionConfigSnapshot
    if (Compare-Object -ReferenceObject $Antes -DifferenceObject $Despues) {
        throw "La carpeta productiva de configuraciones cambio durante la prueba."
    }

    $LogLauncher = Join-Path $LocalAppData "PortalRisko\Launcher\launcher.log"
    $LineasAutoprueba = @(
        Get-Content -LiteralPath $LogLauncher |
            Where-Object { $_ -match "SELF-TEST" } |
            Select-Object -Last 8
    )

    [pscustomobject]@{
        InstallerExit = $ProcesoInstalador.ExitCode
        InstalledLauncherVersion = $InfoInstalacion.launcher_version
        LauncherExit = $ProcesoLauncher.ExitCode
        CachedTestReleaseVersion = $InfoRelease.version
        PortalSelfTestExit = $CodigoPortal
        LocalConfig = $ConfiguracionesLocales
        ProductionConfigUnchanged = $true
        ShortcutCreated = Test-Path -LiteralPath (Join-Path $Accesos "Portal RISKO.lnk")
        LauncherSelfTest = $LineasAutoprueba -join "`n"
        PortalSelfTest = $SalidaPortal -join "`n"
    }
}
finally {
    foreach ($Nombre in $VariablesAnteriores.Keys) {
        Set-Item -Path "Env:$Nombre" -Value $VariablesAnteriores[$Nombre]
    }

    $RaizResuelta = [IO.Path]::GetFullPath($RaizPrueba)
    $TempResuelto = [IO.Path]::GetFullPath($env:TEMP)
    $NombreRaiz = Split-Path -Leaf $RaizResuelta
    if (
        $RaizResuelta.StartsWith($TempResuelto, [StringComparison]::OrdinalIgnoreCase) -and
        $NombreRaiz.StartsWith("risko_readonly_verify_")
    ) {
        Remove-Item -LiteralPath $RaizResuelta -Recurse -Force -ErrorAction SilentlyContinue
    }
}
