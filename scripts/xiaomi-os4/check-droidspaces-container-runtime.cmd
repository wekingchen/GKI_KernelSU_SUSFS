@echo off
setlocal
set SCRIPT_DIR=%~dp0
set REMOTE=/data/local/tmp/check-droidspaces-container-runtime.sh

if not exist "%SCRIPT_DIR%check-droidspaces-container-runtime.sh" (
  echo [ERROR] Missing check-droidspaces-container-runtime.sh next to this CMD file.
  exit /b 1
)

adb push "%SCRIPT_DIR%check-droidspaces-container-runtime.sh" %REMOTE%
if errorlevel 1 exit /b 1
adb shell su -c "chmod 700 %REMOTE% && %REMOTE%"
set RC=%ERRORLEVEL%
adb shell su -c "rm -f %REMOTE%" >nul 2>nul
exit /b %RC%
