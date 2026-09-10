param(
    [string]$Version = "2.0.6",
    [switch]$ActualizarLanzador
)

Write-Warning "Este comando fue unificado. Se usara publicar_portal.ps1."
& (Join-Path $PSScriptRoot "publicar_portal.ps1") `
    -Version $Version `
    -ActualizarLanzador:$ActualizarLanzador
