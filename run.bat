@echo off
setlocal
echo ========================================
echo   REBRANDING TOOL - AVVIO DIRETTO
echo ========================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato. Esegui prima install_dependencies.bat
    pause
    exit /b 1
)

py "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo L'applicazione si e' chiusa con un errore.
    echo Controlla i file nella cartella logs.
    pause
    exit /b 1
)
