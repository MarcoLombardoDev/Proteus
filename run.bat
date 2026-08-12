@echo off
setlocal
echo ========================================
echo   REBRANDING TOOL - RUN FROM SOURCE
echo ========================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Run install_dependencies.bat first.
    pause
    exit /b 1
)

py "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo The application exited with an error.
    echo Check the files in the logs folder.
    pause
    exit /b 1
)
