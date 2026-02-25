@echo off
echo ========================================
echo   REBRANDING TOOL - INSTALLAZIONE DIPENDENZE
echo ========================================
echo.
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
echo.
echo Dipendenze installate con successo!
pause
