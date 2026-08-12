@echo off
setlocal
echo ========================================
echo   PROTEUS - INSTALL DEPENDENCIES
echo ========================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo During setup, keep the "tcl/tk and IDLE" option selected.
    echo.
    pause
    exit /b 1
)

REM tkinter is part of the standard library but some Windows installs skip it;
REM without it the application cannot start.
py -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo ERROR: the tkinter component is not installed.
    echo Reinstall Python with the "tcl/tk and IDLE" option selected.
    echo.
    pause
    exit /b 1
)

py -m pip install --upgrade pip
if errorlevel 1 goto :failed

py -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Verifying the installation...
py -c "import PIL, tkinter; print('OK: Pillow and tkinter are available')"
if errorlevel 1 goto :failed

echo.
echo Dependencies installed successfully.
pause
exit /b 0

:failed
echo.
echo ERROR: dependency installation failed.
echo On a corporate network you may need a proxy or an internal pip index.
pause
exit /b 1
