@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

rem ================================================================
rem Xiaomi 17 Pro (pandora) OS4 固件输入采集器
rem 只读：不会 flash / erase / set_active，也不会写入任何手机分区。
rem 需要：Windows platform-tools、USB 调试、当前系统可正常开机、su Root 可用。
rem ================================================================

echo.
echo ================================================================
echo  小米 17 Pro OS4 固件输入采集器（只读）
echo ================================================================
echo  本脚本只读取当前活动 slot 的：
echo    boot / init_boot / vendor_boot / dtbo
echo  不会刷写、擦除、切换 slot 或修改任何分区。
echo ================================================================
echo.

where adb >nul 2>nul
if errorlevel 1 (
  echo [错误] 找不到 adb.exe。
  echo        请把本脚本放到 Android platform-tools 目录后再运行，
  echo        或把 platform-tools 加入 PATH。
  exit /b 1
)

adb get-state 1>nul 2>nul
if errorlevel 1 (
  echo [错误] 没有检测到已授权的 adb 设备。
  echo        1. 手机正常开机进入系统；
  echo        2. 打开 USB 调试；
  echo        3. 连接电脑并在手机上允许这台电脑调试。
  echo.
  adb devices
  exit /b 1
)

for /f "delims=" %%A in ('adb shell getprop ro.product.device') do set "DEVICE=%%A"
for /f "delims=" %%A in ('adb shell getprop ro.boot.slot_suffix') do set "SLOT=%%A"
for /f "delims=" %%A in ('adb shell getprop ro.mi.os.version.incremental') do set "OSBUILD=%%A"
if not defined OSBUILD for /f "delims=" %%A in ('adb shell getprop ro.build.version.incremental') do set "OSBUILD=%%A"
for /f "delims=" %%A in ('adb shell uname -r') do set "UNAME=%%A"

if /i not "%DEVICE%"=="pandora" (
  echo [错误] 设备不是 pandora。
  echo        当前检测到：%DEVICE%
  exit /b 1
)

if not "%SLOT%"=="_a" if not "%SLOT%"=="_b" (
  echo [错误] 无法识别当前活动 slot：%SLOT%
  exit /b 1
)

adb shell su -c id 2>nul | findstr /c:"uid=0(root)" >nul
if errorlevel 1 (
  echo [错误] 当前 adb shell 无法取得 su Root。
  echo.
  echo        此脚本需要 Root 才能只读访问 /dev/block/by-name/*。
  echo        请先确认新固件已经正常启动并恢复 Root，再重新运行。
  echo        不要为了本脚本去执行任何 fastboot flash。
  exit /b 1
)

echo [信息] 设备：%DEVICE%
echo [信息] 固件：%OSBUILD%
echo [信息] 内核：%UNAME%
echo [信息] 当前 slot：%SLOT%
echo.

if "%OSBUILD%"=="" set "OSBUILD=unknown"
set "OUT=pandora-stock-%OSBUILD%-%SLOT%"
set "ZIP=%OUT%-xm.zip"

if exist "%OUT%" (
  echo [错误] 输出目录已经存在：%OUT%
  echo        为避免覆盖之前采集的数据，本次停止。
  echo        请先确认并手工移动/删除旧目录后再运行。
  exit /b 1
)
if exist "%ZIP%" (
  echo [错误] 输出压缩包已经存在：%ZIP%
  echo        为避免覆盖旧版本，本次停止。
  echo        请先确认并手工移动/删除旧压缩包后再运行。
  exit /b 1
)

mkdir "%OUT%" || exit /b 1

(
  echo device=%DEVICE%
  echo build=%OSBUILD%
  echo uname=%UNAME%
  echo slot=%SLOT%
  echo collected_from_live_device=YES
  echo operation=READ_ONLY
  echo note=boot is used as CI stock input; other images are snapshots of the current active slot
  echo note2=if init_boot was patched for Root, init_boot.img is not a pristine factory image
) > "%OUT%\README.txt"

for %%P in (boot init_boot vendor_boot dtbo) do (
  echo [读取] %%P%SLOT% ...
  adb shell su -c "test -r /dev/block/by-name/%%P%SLOT%" >nul 2>nul
  if errorlevel 1 (
    echo [错误] 找不到或无法读取 /dev/block/by-name/%%P%SLOT%
    exit /b 1
  )

  adb exec-out su -c "cat /dev/block/by-name/%%P%SLOT%" > "%OUT%\%%P.img"
  if errorlevel 1 (
    echo [错误] 读取 %%P%SLOT% 失败。
    exit /b 1
  )

  for %%F in ("%OUT%\%%P.img") do if %%~zF LSS 4096 (
    echo [错误] %%P.img 文件异常小，停止。
    exit /b 1
  )
)

rem Capture active mounted modules. Device partitions remain read-only.
echo.
echo [采集] 新 OTA 当前挂载的 OEM / GKI 内核模块用于 CRC 校验...
mkdir "%OUT%\oem_modules" || exit /b 1
set "OEM_DIRS=0"
for %%V in (vendor_dlkm vendor odm_dlkm system_dlkm) do (
  adb shell su -c "test -d /%%V/lib/modules" >nul 2>nul
  if not errorlevel 1 (
    echo [读取] /%%V/lib/modules/ ...
    mkdir "%OUT%\oem_modules\%%V" || exit /b 1
    adb pull "/%%V/lib/modules/." "%OUT%\oem_modules\%%V" >nul
    if errorlevel 1 (
      echo [错误] 读取 OEM 内核模块失败。不得把不完整的 xm.zip 作为适配输入。
      exit /b 1
    )
    set /a OEM_DIRS+=1
  )
)
if "%OEM_DIRS%"=="0" (
  echo [错误] 未发现可读的内核模块目录，无法审查 OTA ABI。
  exit /b 1
)
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$d='%OUT%\oem_modules';" ^
  "$m=@(Get-ChildItem -LiteralPath $d -File -Recurse | Where-Object { $_.Name -match '\.ko(\.zst|\.xz|\.gz)?
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$files='boot.img','init_boot.img','vendor_boot.img','dtbo.img','oem-modules.zip';" ^
  "$o='%OUT%\SHA256SUMS.txt';" ^
  "foreach($f in $files){$h=(Get-FileHash -Algorithm SHA256 ('%OUT%\'+$f)).Hash.ToLower(); Add-Content -Encoding ascii $o ($h+'  '+$f)}"

if errorlevel 1 (
  echo [错误] SHA256 计算失败。
  exit /b 1
)

echo [打包] 生成 %ZIP% ...
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Compress-Archive -Path '%OUT%\boot.img','%OUT%\init_boot.img','%OUT%\vendor_boot.img','%OUT%\dtbo.img','%OUT%\oem-modules.zip','%OUT%\oem-modules-count.txt','%OUT%\README.txt','%OUT%\SHA256SUMS.txt' -DestinationPath '%ZIP%' -CompressionLevel Optimal"

if errorlevel 1 (
  echo [错误] 生成 xm.zip 失败。
  exit /b 1
)

echo.
echo ================================================================
echo [完成] 已生成：
echo   %ZIP%
echo.
echo SHA256 清单：
type "%OUT%\SHA256SUMS.txt"
echo.
echo 下一步：
echo   1. 不要解压这个 *-xm.zip；
echo   2. 上传到 GitHub 固定 prerelease：pandora-os4-stock-input；
echo   3. 同一个 Release 中必须只保留一个 *xm.zip；
echo   4. 新固件不要直接套用旧 fixture / 旧功能内核。
echo.
echo [安全确认] 本脚本没有修改手机任何分区。
echo ================================================================
endlocal
 });" ^
  "if($m.Count -lt 1){throw 'OEM module list is empty'};" ^
  "$sum=($m | Measure-Object -Property Length -Sum).Sum;" ^
  "if($sum -gt 500MB){throw 'OEM modules exceed 500 MB; stop for manual review'};" ^
  "'MODULE_COUNT='+$m.Count | Out-File -Encoding ascii '%OUT%\oem-modules-count.txt';" ^
  "Compress-Archive -Path '%OUT%\oem_modules\*' -DestinationPath '%OUT%\oem-modules.zip' -CompressionLevel Optimal"
if errorlevel 1 (
  echo [错误] 厂商模块采集失败，禁止产生不完整的 xm.zip。
  exit /b 1
)
echo.
echo [校验] 计算 SHA256 ...
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$files='boot.img','init_boot.img','vendor_boot.img','dtbo.img';" ^
  "$o='%OUT%\SHA256SUMS.txt';" ^
  "foreach($f in $files){$h=(Get-FileHash -Algorithm SHA256 ('%OUT%\'+$f)).Hash.ToLower(); Add-Content -Encoding ascii $o ($h+'  '+$f)}"

if errorlevel 1 (
  echo [错误] SHA256 计算失败。
  exit /b 1
)

echo [打包] 生成 %ZIP% ...
powershell -NoProfile -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Compress-Archive -Path '%OUT%\boot.img','%OUT%\init_boot.img','%OUT%\vendor_boot.img','%OUT%\dtbo.img','%OUT%\README.txt','%OUT%\SHA256SUMS.txt' -DestinationPath '%ZIP%' -CompressionLevel Optimal"

if errorlevel 1 (
  echo [错误] 生成 xm.zip 失败。
  exit /b 1
)

echo.
echo ================================================================
echo [完成] 已生成：
echo   %ZIP%
echo.
echo SHA256 清单：
type "%OUT%\SHA256SUMS.txt"
echo.
echo 下一步：
echo   1. 不要解压这个 *-xm.zip；
echo   2. 上传到 GitHub 固定 prerelease：pandora-os4-stock-input；
echo   3. 同一个 Release 中必须只保留一个 *xm.zip；
echo   4. 新固件不要直接套用旧 fixture / 旧功能内核。
echo.
echo [安全确认] 本脚本没有修改手机任何分区。
echo ================================================================
endlocal
