@echo off
setlocal
cd /d "%~dp0"

if not exist "scripts\install.ps1" (
    echo [ERROR] scripts\install.ps1 was not found.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
if errorlevel 1 (
    echo.
    echo [ERROR] Setup did not complete. Fix the issue above and run start.bat again.
    pause
    exit /b 1
)

echo.
echo Starting Scout...
".venv\Scripts\python.exe" -m src
set "SCOUT_EXIT=%ERRORLEVEL%"

echo.
if not "%SCOUT_EXIT%"=="0" (
    echo Scout exited with code %SCOUT_EXIT%.
) else (
    echo Scout exited.
)
pause
exit /b %SCOUT_EXIT%