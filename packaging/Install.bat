@echo off
setlocal
title TVPAINT / LAYER EXPORTER
cd /d "%~dp0"
if not defined TVPE_APP set "TVPE_APP=%LOCALAPPDATA%\TVPaintLayerExporter"
if not exist "%TVPE_APP%" mkdir "%TVPE_APP%"
if not exist "%TVPE_APP%" goto failed
set "TVPE_LOG=%TVPE_APP%\setup.log"
echo [%DATE% %TIME%] START BAT setup>>"%TVPE_LOG%"
powershell.exe -NoProfile -NonInteractive -Command "Write-Host ''; if ($Host.UI.SupportsVirtualTerminal -and -not (Test-Path Env:NO_COLOR)) { Write-Host (([char]27)+'[1;38;2;255;153;51m  TVPAINT / LAYER EXPORTER'+([char]27)+'[0m') } else { Write-Host '  TVPAINT / LAYER EXPORTER' -ForegroundColor DarkYellow }; Write-Host '  Guided Installation - Fabien Glasse' -ForegroundColor DarkGray; Write-Host ''"
echo.
set "TVPE_BANNER_SHOWN=1"
echo Each step asks before making changes. Choose N to stop.
echo.
echo Installation log:
echo %TVPE_LOG%
echo.
if exist "%TVPE_APP%\python\python.exe" goto private_python
call py -3 -c "import sys,tkinter; assert sys.version_info >= (3,10) and sys.maxsize > 2**32" >nul 2>&1
if not errorlevel 1 goto existing_python
echo A suitable Python installation was not found.
echo.
echo.
powershell.exe -NoProfile -NonInteractive -Command "if ($Host.UI.SupportsVirtualTerminal -and -not (Test-Path Env:NO_COLOR)) { Write-Host (([char]27)+'[1;38;2;255;153;51m  PREPARATION / DOWNLOAD PYTHON'+([char]27)+'[0m') } else { Write-Host '  PREPARATION / DOWNLOAD PYTHON' -ForegroundColor DarkYellow }"
echo.
echo Download Python 3.13.13 from python.org and check its publisher.
echo.
choice /C YN /N /M "Download Python now? [Y/N] "
if errorlevel 2 goto cancelled
echo [%DATE% %TIME%] P1 download official Python installer>>"%TVPE_LOG%"
set "TVPE_DOWNLOAD=%TVPE_APP%\python-3.13.13-amd64.exe"
curl.exe --fail --location --proto =https --tlsv1.2 "https://www.python.org/ftp/python/3.13.13/python-3.13.13-amd64.exe" --output "%TVPE_DOWNLOAD%"
if errorlevel 1 goto failed
powershell.exe -NoProfile -NonInteractive -Command "$s=Get-AuthenticodeSignature -LiteralPath $env:TVPE_DOWNLOAD; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'O=Python Software Foundation'){Write-Error 'Python publisher verification failed'; exit 1}; Write-Output $s.SignerCertificate.Subject"
if errorlevel 1 goto failed
echo [%DATE% %TIME%] P1 publisher signature verified>>"%TVPE_LOG%"
echo.
echo.
powershell.exe -NoProfile -NonInteractive -Command "if ($Host.UI.SupportsVirtualTerminal -and -not (Test-Path Env:NO_COLOR)) { Write-Host (([char]27)+'[1;38;2;255;153;51m  PREPARATION / INSTALL PYTHON'+([char]27)+'[0m') } else { Write-Host '  PREPARATION / INSTALL PYTHON' -ForegroundColor DarkYellow }"
echo.
echo Install Python for your Windows account.
echo.
choice /C YN /N /M "Install Python now? [Y/N] "
if errorlevel 2 goto cancelled
echo [%DATE% %TIME%] P2 launch official Python installer>>"%TVPE_LOG%"
start /wait "" "%TVPE_DOWNLOAD%" /passive InstallAllUsers=0 Include_launcher=0 InstallLauncherAllUsers=0 Include_test=0 Include_doc=0 Include_pip=1 Include_tcltk=1 AssociateFiles=0 Shortcuts=0 PrependPath=0 TargetDir="%TVPE_APP%\python"
if errorlevel 1 goto failed
:private_python
"%TVPE_APP%\python\python.exe" -I "%~dp0setup_steps.py"
if errorlevel 1 goto failed
goto success
:existing_python
echo [%DATE% %TIME%] P1/P2 skipped: compatible Python already installed>>"%TVPE_LOG%"
call py -3 -I "%~dp0setup_steps.py"
if errorlevel 1 goto failed
:success
echo.
echo.
powershell.exe -NoProfile -NonInteractive -Command "Write-Host '  SETUP COMPLETE' -ForegroundColor Cyan"
echo.
echo Open TVPaint, then use the TVPaint Layer Exporter desktop shortcut.
echo.
pause
exit /b 0
:cancelled
echo [%DATE% %TIME%] User stopped setup>>"%TVPE_LOG%"
echo.
powershell.exe -NoProfile -NonInteractive -Command "Write-Host '  Setup stopped. Run Install.bat again when ready.' -ForegroundColor Yellow"
echo.
pause
exit /b 2
:failed
echo [%DATE% %TIME%] Setup failed or was cancelled>>"%TVPE_LOG%"
echo.
powershell.exe -NoProfile -NonInteractive -Command "Write-Host '  Setup did not finish. Keep the error above and the log for the studio.' -ForegroundColor Red"
echo.
echo Installation log:
echo %TVPE_LOG%
echo.
pause
exit /b 1
