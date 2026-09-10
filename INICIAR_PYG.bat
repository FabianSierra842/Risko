@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" aplicaciones\interfaz_risko\interfaz_pyg.py
) else (
    python aplicaciones\interfaz_risko\interfaz_pyg.py
)
if errorlevel 1 pause
endlocal
