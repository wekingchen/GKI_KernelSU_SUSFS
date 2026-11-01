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
  echo boot_source=ACTIVE_SLOT_UNVERIFIED_OEM
  echo boot_oem_original_verified=NO
  echo boot_role=GKI_KERNEL_ANALYSIS_INPUT
  echo init_boot_source=ROOTED_ACTIVE_SLOT_MAY_BE_PATCHED
  echo init_boot_oem_original_verified=NO
  echo init_boot_role=DIAGNOSTIC_ONLY_NOT_FACTORY_IMAGE
  echo vendor_boot_source=ACTIVE_SLOT_UNVERIFIED_OEM
  echo dtbo_source=ACTIVE_SLOT_UNVERIFIED_OEM
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

rem Capture the live-mounted vendor / GKI module files with Root rights.
rem Use root tar streaming: adb pull itself runs as shell and can miss root-only files.
rem All streams are read-only on the phone; extraction happens on Windows.
echo.
echo [采集] 正在只读采集已挂载的 OEM / GKI 内核模块...
where tar >nul 2>nul
if errorlevel 1 (
  echo [错误] Windows 没有 tar.exe。请使用较新版本 Windows 10/11。
  exit /b 1
)
adb shell su -c "command -v tar" >nul 2>nul
if errorlevel 1 (
  echo [错误] 手机 Root 环境缺少 tar，无法完整采集模块。
  exit /b 1
)
mkdir "%OUT%\oem_modules" || exit /b 1
set "OEM_DIRS=0"
for %%V in (vendor_dlkm vendor odm_dlkm system_dlkm) do (
  adb shell su -c "test -d /%%V/lib/modules" >nul 2>nul
  if not errorlevel 1 (
    echo [读取] /%%V/lib/modules/ ...
    mkdir "%OUT%\oem_modules\%%V" || exit /b 1
    adb exec-out su -c "tar -C /%%V/lib/modules -cf - ." > "%OUT%\modules-%%V.tar"
    if errorlevel 1 (
      echo [错误] 无法通过 Root 只读提取 %%V 模块，请检查 su 权限。
      exit /b 1
    )
    for %%F in ("%OUT%\modules-%%V.tar") do if %%~zF LSS 1024 (
      echo [错误] 模块 TAR 异常小：%%V
      exit /b 1
    )
    tar -xf "%OUT%\modules-%%V.tar" -C "%OUT%\oem_modules\%%V"
    if errorlevel 1 (
      echo [错误] Windows 解包 %%V 模块失败，禁止生成不完整 xm.zip。
      exit /b 1
    )
    del /q "%OUT%\modules-%%V.tar"
    set /a OEM_DIRS+=1 >nul
  )
)
if "%OEM_DIRS%"=="0" (
  echo [错误] 手机没有检测到可读取的内核模块目录。
  exit /b 1
)

rem Build a full, bounded module archive plus exact count manifest.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$d='%OUT%\oem_modules';" ^
  "$m=@(Get-ChildItem -LiteralPath $d -File -Recurse | Where-Object { $_.Name -match '\.ko(\.zst|\.xz|\.gz)?$' });" ^
  "if($m.Count -lt 1){throw 'No kernel .ko files found'};" ^
  "if($m.Count -gt 4096){throw 'Too many .ko files'};" ^
  "$size=($m | Measure-Object -Property Length -Sum).Sum;" ^
  "if($size -gt 500MB){throw 'OEM modules exceed 500 MiB'};" ^
  "'MODULE_COUNT='+$m.Count | Set-Content -Encoding ascii -LiteralPath '%OUT%\oem-modules-count.txt';" ^
  "Compress-Archive -Path '%OUT%\oem_modules\*' -DestinationPath '%OUT%\oem-modules.zip' -CompressionLevel Optimal"
if errorlevel 1 (
  echo [错误] 模块清单或模块 ZIP 生成失败。已停止，未更新手机分区。
  exit /b 1
)
for %%F in ("%OUT%\oem-modules.zip") do if %%~zF LSS 128 (
  echo [错误] 模块压缩包大小异常。
  exit /b 1
)

echo.
echo [校验] 生成当前活动分区及模块的 SHA256 清单...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$files='boot.img','init_boot.img','vendor_boot.img','dtbo.img','oem-modules.zip';" ^
  "$o='%OUT%\SHA256SUMS.txt';" ^
  "if(Test-Path -LiteralPath $o){throw 'Unexpected existing SHA256 manifest'};" ^
  "foreach($f in $files){" ^
  "  $p=Join-Path '%OUT%' $f;" ^
  "  if(!(Test-Path -LiteralPath $p)){throw 'Missing file: '+$p};" ^
  "  $h=(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant();" ^
  "  Add-Content -Encoding ascii -LiteralPath $o -Value ($h+'  '+$f);" ^
  "}"
if errorlevel 1 (
  echo [错误] SHA256 清单生成失败。
  exit /b 1
)

echo [打包] 生成 %ZIP% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "Compress-Archive -Path '%OUT%\boot.img','%OUT%\init_boot.img','%OUT%\vendor_boot.img','%OUT%\dtbo.img','%OUT%\oem-modules.zip','%OUT%\oem-modules-count.txt','%OUT%\README.txt','%OUT%\SHA256SUMS.txt' -DestinationPath '%ZIP%' -CompressionLevel Optimal"
if errorlevel 1 (
  echo [错误] 最终 xm.zip 生成失败，禁止上传不完整输入。
  exit /b 1
)
for %%F in ("%ZIP%") do if %%~zF LSS 4096 (
  echo [错误] xm.zip 大小异常。
  exit /b 1
)

echo.
echo ================================================================
echo [成功] 已生成：%ZIP%
echo.
echo SHA256 清单：
type "%OUT%\SHA256SUMS.txt"
echo.
echo 下一步：
echo   1. 仅上传这个完整的 *-xm.zip 到固定 Release pandora-os4-stock-input；
echo   2. 该 Release 必须只保留一个 *xm.zip；
echo   3. GitHub 会自动检查版本并进行 OEM CRC/KMI 兼容性验证；
echo   4. 通过门禁生成的临时 boot 必须先用 fastboot boot 真机验证。
echo.
echo [只读确认] 没有向手机写入任何分区，Gen 3 LKG 不受影响。
echo ================================================================
endlocal
