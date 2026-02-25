@echo off
echo ========================================
echo   REBRANDING TOOL - COMPILAZIONE
echo ========================================
echo.

REM Verifica che Python sia disponibile
py --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato!
    echo Installa Python 3.x e riprova.
    pause
    exit /b 1
)

REM Esegui lo script di build
echo Avvio processo di compilazione...
py build.py

echo.
echo Premi un tasto per chiudere...
pause >nul
