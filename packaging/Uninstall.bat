@echo off
setlocal
title TVPAINT / LAYER EXPORTER - Uninstall
cd /d "%~dp0"
if exist "%~dp0unins000.exe" (
    start "" "%~dp0unins000.exe"
    exit /b 0
)
if not exist "%~dp0venv\Scripts\python.exe" goto missing
for /f "tokens=1,* delims==" %%A in ('type "%~dp0venv\pyvenv.cfg" ^| findstr /b "home ="') do for /f "tokens=*" %%P in ("%%B") do set "TVPE_BASE_PYTHON=%%P\python.exe"
if not defined TVPE_BASE_PYTHON goto missing
rem This launcher removes itself only after the validated uninstall succeeds.
(
    "%TVPE_BASE_PYTHON%" -I "%~dp0uninstall.py"
    if errorlevel 1 (
        pause
        exit /b 1
    )
    pause
    del "%~f0"
    exit 0
)
:missing
echo The Python installation could not be found. Run Install.bat to repair it, then uninstall again.
pause
exit /b 1
