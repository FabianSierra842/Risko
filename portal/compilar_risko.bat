@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publicar_portal.ps1" %*
if errorlevel 1 (
    echo.
    echo La publicacion no se completo. Revise el error anterior.
    pause
    exit /b 1
)
echo.
pause
