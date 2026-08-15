@echo off
setlocal

py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Run install_dependencies.bat first. 1>&2
    if "%~1"=="" pause
    exit /b 3
)

rem Arguments mean the command line: no banner, no pause, and the exit code is
rem passed straight through. A scheduled job must never wait for a keypress.
if not "%~1"=="" (
    py "%~dp0main.py" %*
    exit /b %errorlevel%
)

echo ========================================
echo   PROTEUS - RUN FROM SOURCE
echo ========================================
echo.

py "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo The application exited with an error.
    echo Check the files in the logs folder.
    pause
    exit /b 1
)
