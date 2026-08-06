@echo off
setlocal
echo ========================================
echo   REBRANDING TOOL - INSTALLAZIONE DIPENDENZE
echo ========================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo ERRORE: Python non trovato.
    echo Installa Python 3.10 o superiore da https://www.python.org/downloads/
    echo Durante l'installazione lascia selezionata l'opzione "tcl/tk and IDLE".
    echo.
    pause
    exit /b 1
)

REM tkinter fa parte della libreria standard ma su alcune installazioni
REM Windows viene escluso: senza, l'applicazione non puo' partire.
py -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo ERRORE: il componente tkinter non e' installato.
    echo Reinstalla Python selezionando l'opzione "tcl/tk and IDLE".
    echo.
    pause
    exit /b 1
)

py -m pip install --upgrade pip
if errorlevel 1 goto :failed

py -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Verifica installazione...
py -c "import PIL, tkinter; print('OK: Pillow e tkinter disponibili')"
if errorlevel 1 goto :failed

echo.
echo Dipendenze installate con successo!
pause
exit /b 0

:failed
echo.
echo ERRORE: installazione delle dipendenze non riuscita.
echo Se sei su una rete aziendale potrebbe servire un proxy o un indice pip interno.
pause
exit /b 1
