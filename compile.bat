@echo off
setlocal
echo ========================================
echo   PROTEUS - BUILD EXECUTABLE
echo ========================================
echo.

py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.10 or newer and try again.
    pause
    exit /b 1
)

echo Starting the build...
py "%~dp0build.py"

echo.
echo Press any key to close...
pause >nul
