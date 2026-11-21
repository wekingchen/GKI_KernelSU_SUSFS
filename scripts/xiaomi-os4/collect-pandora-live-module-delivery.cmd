@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem pandora OS4.0.6: READ ONLY runtime Binder and zsmalloc provenance.
rem Only adb shell getprop / cat / sha256sum and Windows-side filtering.
rem NO adb push, phone write, fastboot, reboot, insmod or module replacement.
where adb >nul 2>&1
if errorlevel 1 (
  echo ERROR: adb is required in PATH.
  exit /b 2
)
where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Windows PowerShell is required for safe address redaction.
  exit /b 2
)
set "DEVICE="
set "OSBUILD="
set "KREL="
set "ADBSTATE="
set "PROBE=%TEMP%\pandora-live-probe-%RANDOM%-%RANDOM%"
adb get-state > "%PROBE%-state.txt" 2> "%PROBE%-error.txt"
if errorlevel 1 (
  echo ERROR: adb cannot access exactly one device.
  type "%PROBE%-error.txt" 2>nul
  del /q "%PROBE%-state.txt" "%PROBE%-error.txt" >nul 2>&1
  exit /b 2
)
set /p ADBSTATE=<"%PROBE%-state.txt"
if /i not "%ADBSTATE%"=="device" (
  echo ERROR: adb state is "%ADBSTATE%", expected "device".
  del /q "%PROBE%-state.txt" "%PROBE%-error.txt" >nul 2>&1
  exit /b 2
)
adb shell getprop ro.product.device > "%PROBE%-device.txt" 2>> "%PROBE%-error.txt"
if errorlevel 1 goto :probe_failed
adb shell getprop ro.mi.os.version.incremental > "%PROBE%-build.txt" 2>> "%PROBE%-error.txt"
if errorlevel 1 goto :probe_failed
adb shell uname -r > "%PROBE%-krel.txt" 2>> "%PROBE%-error.txt"
if errorlevel 1 goto :probe_failed
set /p DEVICE=<"%PROBE%-device.txt"
set /p OSBUILD=<"%PROBE%-build.txt"
set /p KREL=<"%PROBE%-krel.txt"
del /q "%PROBE%-state.txt" "%PROBE%-error.txt" "%PROBE%-device.txt" "%PROBE%-build.txt" "%PROBE%-krel.txt" >nul 2>&1
if not defined DEVICE (
  echo ERROR: adb returned an empty ro.product.device.
  exit /b 2
)
if not defined OSBUILD (
  echo ERROR: adb returned an empty ro.mi.os.version.incremental.
  exit /b 2
)
if not defined KREL (
  echo ERROR: adb returned an empty uname -r.
  exit /b 2
)
if /i not "%DEVICE%"=="pandora" (
  echo ERROR: expected pandora, got "%DEVICE%".
  exit /b 3
)
if /i not "%OSBUILD%"=="OS4.0.6.0.XBLCNXM" (
  echo ERROR: expected OS4.0.6.0.XBLCNXM, got "%OSBUILD%".
  exit /b 3
)
if /i not "%KREL%"=="6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k" (
  echo ERROR: unexpected running kernel "%KREL%".
  exit /b 3
)
goto :probe_ok

:probe_failed
echo ERROR: adb identity probe failed.
type "%PROBE%-error.txt" 2>nul
del /q "%PROBE%-state.txt" "%PROBE%-error.txt" "%PROBE%-device.txt" "%PROBE%-build.txt" "%PROBE%-krel.txt" >nul 2>&1
exit /b 2

:probe_ok
adb shell su -c "id" 2>nul | findstr /C:"uid=0(root)" >nul
if errorlevel 1 (
  echo ERROR: root is unavailable.
  exit /b 4
)
set "OUT=pandora-live-module-delivery-%RANDOM%"
mkdir "%OUT%" >nul 2>&1
if errorlevel 1 (
  echo ERROR: could not create a local output folder.
  exit /b 5
)
(
  echo device=pandora
  echo build=OS4.0.6.0.XBLCNXM
) > "%OUT%\identity.txt"
for /f "tokens=*" %%S in ('adb shell getprop ro.boot.slot_suffix 2^>nul') do >> "%OUT%\identity.txt" echo %%S
>> "%OUT%\identity.txt" echo %KREL%
adb shell getprop sys.boot_completed >> "%OUT%\identity.txt"
adb shell getprop ro.boot.verifiedbootstate >> "%OUT%\verified-boot-state.txt"
adb shell getprop ro.boot.vbmeta.device_state >> "%OUT%\verified-boot-state.txt"

rem Do NOT save raw cmdline: it can include sensitive boot parameters.
rem Only emit binder.impl=... tokens from live effective /proc/cmdline.
adb shell su -c "cat /proc/cmdline" 2>nul | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { [regex]::Matches($_, 'binder\.impl=[A-Za-z0-9_-]+') | ForEach-Object { $_.Value } }" > "%OUT%\binder-impl-cmdline.txt"
rem bootconfig is one key per line; store ONLY matching Binder lines.
adb shell su -c "cat /proc/bootconfig" 2>nul | findstr /I /C:"binder.impl" > "%OUT%\binder-impl-bootconfig.txt"

rem Android common can choose Rust Binder through sysfs before rust_binder.ko
rem is loaded. Read both the requested implementation and the newer read-only
rem active implementation when present. Missing files remain UNKNOWN.
adb shell su -c "cat /sys/module/binder/parameters/impl" > "%OUT%\binder-impl-sysfs.txt" 2>nul
adb shell su -c "cat /sys/module/binder/parameters/active_impl" > "%OUT%\binder-active-impl-sysfs.txt" 2>nul

rem module list: strip kernel load addresses and section addresses on Windows.
adb shell su -c "cat /proc/modules" 2>nul | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { $c = $_ -split '\s+'; if ($c.Count -ge 3 -and $c[0] -in @('rust_binder','zsmalloc','zram','node_cache','binder_linux')) { $c[0] + ' size=' + $c[1] + ' users=' + $c[2] } }" > "%OUT%\loaded-modules-redacted.txt"
adb shell su -c "cat /proc/sys/kernel/modules_disabled" > "%OUT%\modules-disabled.txt" 2>nul
adb shell su -c "cat /sys/module/rust_binder/initstate" > "%OUT%\rust-binder-initstate.txt" 2>nul

rem SHA of files visible in mounted partitions is evidence of CURRENT FILES,
rem NOT proof of which exact binary the kernel actually loaded.
adb shell su -c "sha256sum /system_dlkm/lib/modules/%KREL%/kernel/drivers/android/binder/rust_binder.ko" > "%OUT%\system-rust-binder-file-sha.txt" 2>nul
adb shell su -c "sha256sum /system_dlkm/lib/modules/%KREL%/kernel/mm/zsmalloc.ko" > "%OUT%\system-zsmalloc-file-sha.txt" 2>nul
adb shell su -c "sha256sum /system_dlkm/lib/modules/%KREL%/kernel/drivers/block/zram/zram.ko" > "%OUT%\system-zram-file-sha.txt" 2>nul
adb shell su -c "sha256sum /vendor_dlkm/lib/modules/zsmalloc.ko" > "%OUT%\vendor-zsmalloc-file-sha.txt" 2>nul
adb shell su -c "sha256sum /vendor_dlkm/lib/modules/zram.ko" > "%OUT%\vendor-zram-file-sha.txt" 2>nul
adb shell su -c "sha256sum /vendor_dlkm/lib/modules/node_cache.ko" > "%OUT%\vendor-node-cache-file-sha.txt" 2>nul

rem Kernel sysfs exposes GNU build-id ELF Note bytes for some loaded modules.
rem Hash only the binary note; do not save addresses or raw note contents.
rem A matching note is NOT a proof of the full in-memory ELF or its source path.
rem Missing sysfs note must remain UNKNOWN; no module load/unload is attempted.
adb shell su -c "sha256sum /sys/module/rust_binder/notes/.note.gnu.build-id" > "%OUT%\loaded-rust-binder-note-sha.txt" 2>nul
adb shell su -c "sha256sum /sys/module/zsmalloc/notes/.note.gnu.build-id" > "%OUT%\loaded-zsmalloc-note-sha.txt" 2>nul
adb shell su -c "sha256sum /sys/module/zram/notes/.note.gnu.build-id" > "%OUT%\loaded-zram-note-sha.txt" 2>nul
adb shell su -c "sha256sum /sys/module/node_cache/notes/.note.gnu.build-id" > "%OUT%\loaded-node-cache-note-sha.txt" 2>nul

rem GKI non-flattened system_dlkm metadata lives in lib/modules/<uname -r>/.
rem Keep root-level files only as secondary layout evidence for OEM variants.
adb shell su -c "cat /system_dlkm/lib/modules/%KREL%/modules.load" > "%OUT%\system-modules.load" 2>nul
adb shell su -c "cat /system_dlkm/lib/modules/%KREL%/modules.dep" > "%OUT%\system-modules.dep" 2>nul
adb shell su -c "cat /system_dlkm/lib/modules/modules.load" > "%OUT%\system-root-modules.load" 2>nul
adb shell su -c "cat /system_dlkm/lib/modules/modules.dep" > "%OUT%\system-root-modules.dep" 2>nul
adb shell su -c "cat /vendor_dlkm/lib/modules/modules.load" > "%OUT%\vendor-modules.load" 2>nul
adb shell su -c "cat /vendor_dlkm/lib/modules/modules.dep" > "%OUT%\vendor-modules.dep" 2>nul
adb shell su -c "cat /proc/mounts" 2>nul | findstr /I /C:"system_dlkm" /C:"vendor_dlkm" > "%OUT%\dlkm-mounts.txt"

(
  echo Status: READ-ONLY LIVE FILESYSTEM EVIDENCE
  echo Binder loaded module byte SHA: NOT PROVEN BY FILE HASH ALONE
  echo Vendor/system zsmalloc sources are intentionally separated.
  echo Empty modules.load or SHA output can indicate inaccessible locations.
  echo Empty binder-impl-cmdline means no matching token was observed, NOT a proven C implementation.
  echo binder-impl-sysfs and active-impl are read-only runtime selection evidence when present.
  echo Optional loaded module build-id NOTE hashes are NOT complete binary identity.
  echo Missing sysfs notes remain UNKNOWN and are not errors.
  echo system modules.load is read from lib/modules/%KREL% first; root layout is secondary.
  echo No raw kernel addresses or raw /proc/cmdline are stored.
  echo No partition, module, root, boot or AVB settings were changed.
) > "%OUT%\README.txt"
echo.
rem Packaging is PC-local only, so users can upload one ZIP without manual steps.
rem If local archive creation fails, the evidence folder remains available.
powershell.exe -NoProfile -NonInteractive -Command "Compress-Archive -LiteralPath '%OUT%' -DestinationPath '%OUT%.zip' -Force" >nul 2>&1
if errorlevel 1 (
  echo WARNING: Local ZIP could not be created. Use the folder "%OUT%".
) else (
  echo Evidence archive: "%OUT%.zip"
)
echo READ-ONLY snapshot saved in "%OUT%".
echo File hashes are not proof of actual loaded ELF contents.
echo No phone writes. No flash or reboot.
endlocal
