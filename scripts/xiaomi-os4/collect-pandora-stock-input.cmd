@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Xiaomi 17 Pro / pandora stock partition collector
rem READ-ONLY: never flashes, erases, writes, or changes slots.
rem Requires adb and working root (su) on the currently booted system.

where adb >nul 2>nul
if errorlevel 1 (
  echo [ERROR] adb.exe was not found in PATH.
  exit /b 1
)

for /f "delims=" %%A in ('adb shell getprop ro.product.device') do set "DEVICE=%%A"
for /f "delims=" %%A in ('adb shell getprop ro.boot.slot_suffix') do set "SLOT=%%A"
for /f "delims=" %%A in ('adb shell getprop ro.mi.os.version.incremental') do set "OSBUILD=%%A"
if not defined OSBUILD for /f "delims=" %%A in ('adb shell getprop ro.build.version.incremental') do set "OSBUILD=%%A"

if /i not "%DEVICE%"=="pandora" (
  echo [ERROR] Expected device pandora, got "%DEVICE%".
  exit /b 1
)
if not "%SLOT%"=="_a" if not "%SLOT%"=="_b" (
  echo [ERROR] Unexpected slot suffix "%SLOT%".
  exit /b 1
)

adb shell su -c id | findstr /c:"uid=0(root)" >nul
if errorlevel 1 (
  echo [ERROR] Root is required to read current partition images.
  exit /b 1
)

set "OUT=pandora-stock-%OSBUILD%-%SLOT%"
if "%OSBUILD%"=="" set "OUT=pandora-stock-unknown-%SLOT%"
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"

echo device=%DEVICE%>"%OUT%\README.txt"
echo build=%OSBUILD%>>"%OUT%\README.txt"
echo slot=%SLOT%>>"%OUT%\README.txt"
echo collected_from_live_device=YES>>"%OUT%\README.txt"
echo operation=READ_ONLY>>"%OUT%\README.txt"

for %%P in (boot init_boot vendor_boot dtbo) do (
  echo [INFO] Reading %%P%SLOT% ...
  adb exec-out su -c "cat /dev/block/by-name/%%P%SLOT%" > "%OUT%\%%P.img"
  if errorlevel 1 (
    echo [ERROR] Failed to read %%P%SLOT%.
    exit /b 1
  )
  for %%F in ("%OUT%\%%P.img") do if %%~zF LSS 4096 (
    echo [ERROR] %%P.img is unexpectedly small.
    exit /b 1
  )
)

powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$files='boot.img','init_boot.img','vendor_boot.img','dtbo.img';" ^
  "$o='%OUT%\SHA256SUMS.txt';" ^
  "Remove-Item $o -ErrorAction SilentlyContinue;" ^
  "foreach($f in $files){$h=(Get-FileHash -Algorithm SHA256 ('%OUT%\'+$f)).Hash.ToLower(); Add-Content -Encoding ascii $o ($h+'  '+$f)}"

if errorlevel 1 (
  echo [ERROR] Failed to calculate SHA256.
  exit /b 1
)

set "ZIP=%OUT%-xm.zip"
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop'; Compress-Archive -Path '%OUT%\boot.img','%OUT%\init_boot.img','%OUT%\vendor_boot.img','%OUT%\dtbo.img','%OUT%\README.txt','%OUT%\SHA256SUMS.txt' -DestinationPath '%ZIP%' -CompressionLevel Optimal"

if errorlevel 1 (
  echo [ERROR] Failed to create xm.zip.
  exit /b 1
)

echo.
echo [OK] Stock input created:
echo   %ZIP%
echo.
type "%OUT%\SHA256SUMS.txt"
echo.
echo This package only contains partitions read from the current slot.
echo No partition was modified.
endlocal
