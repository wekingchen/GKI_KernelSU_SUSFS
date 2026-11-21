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
for /f "tokens=*" %%D in ('adb shell getprop ro.product.device 2^>nul') do set "DEVICE=%%D"
for /f "tokens=*" %%B in ('adb shell getprop ro.mi.os.version.incremental 2^>nul') do set "OSBUILD=%%B"
if /i not "%DEVICE%"=="pandora" (
  echo ERROR: expected pandora, got "%DEVICE%".
  exit /b 3
)
if /i not "%OSBUILD%"=="OS4.0.6.0.XBLCNXM" (
  echo ERROR: expected OS4.0.6.0.XBLCNXM, got "%OSBUILD%".
  exit /b 3
)
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
adb shell getprop ro.boot.slot_suffix >> "%OUT%\identity.txt"
adb shell uname -r >> "%OUT%\identity.txt"
adb shell getprop sys.boot_completed >> "%OUT%\identity.txt"
adb shell getprop ro.boot.verifiedbootstate >> "%OUT%\verified-boot-state.txt"
adb shell getprop ro.boot.vbmeta.device_state >> "%OUT%\verified-boot-state.txt"

rem Do NOT save raw cmdline: it can include sensitive boot parameters.
rem Only emit binder.impl=... tokens from live effective /proc/cmdline.
adb shell su -c "cat /proc/cmdline" 2>nul | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { [regex]::Matches($_, 'binder\.impl=[A-Za-z0-9_-]+') | ForEach-Object { $_.Value } }" > "%OUT%\binder-impl-cmdline.txt"
rem bootconfig is one key per line; store ONLY matching Binder lines.
adb shell su -c "cat /proc/bootconfig" 2>nul | findstr /I /C:"binder.impl" > "%OUT%\binder-impl-bootconfig.txt"

rem module list: strip kernel load addresses and section addresses on Windows.
adb shell su -c "cat /proc/modules" 2>nul | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { $c = $_ -split '\s+'; if ($c.Count -ge 3 -and $c[0] -in @('rust_binder','zsmalloc','zram','node_cache','binder_linux')) { $c[0] + ' size=' + $c[1] + ' users=' + $c[2] } }" > "%OUT%\loaded-modules-redacted.txt"
adb shell su -c "cat /proc/sys/kernel/modules_disabled" > "%OUT%\modules-disabled.txt" 2>nul
adb shell su -c "cat /sys/module/rust_binder/initstate" > "%OUT%\rust-binder-initstate.txt" 2>nul

rem SHA of files visible in mounted partitions is evidence of CURRENT FILES,
rem NOT proof of which exact binary the kernel actually loaded.
adb shell su -c "sha256sum /system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/kernel/drivers/android/binder/rust_binder.ko" > "%OUT%\system-rust-binder-file-sha.txt" 2>nul
adb shell su -c "sha256sum /system_dlkm/lib/modules/6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k/kernel/mm/zsmalloc.ko" > "%OUT%\system-zsmalloc-file-sha.txt" 2>nul
adb shell su -c "sha256sum /vendor_dlkm/lib/modules/zsmalloc.ko" > "%OUT%\vendor-zsmalloc-file-sha.txt" 2>nul
adb shell su -c "sha256sum /vendor_dlkm/lib/modules/zram.ko" > "%OUT%\vendor-zram-file-sha.txt" 2>nul
adb shell su -c "sha256sum /vendor_dlkm/lib/modules/node_cache.ko" > "%OUT%\vendor-node-cache-file-sha.txt" 2>nul

rem Kernel sysfs exposes GNU build-id ELF Note bytes for some loaded modules.
rem Hash only the binary note; do not save addresses or raw note contents.
rem A matching note is NOT a proof of the full in-memory ELF or its source path.
rem Missing sysfs note must remain UNKNOWN; no module load/unload is attempted.
adb shell su -c "sha256sum /sys/module/rust_binder/notes/.note.gnu.build-id" > "%OUT%\\loaded-rust-binder-note-sha.txt" 2>nul
adb shell su -c "sha256sum /sys/module/zsmalloc/notes/.note.gnu.build-id" > "%OUT%\\loaded-zsmalloc-note-sha.txt" 2>nul
adb shell su -c "sha256sum /sys/module/zram/notes/.note.gnu.build-id" > "%OUT%\\loaded-zram-note-sha.txt" 2>nul
adb shell su -c "sha256sum /sys/module/node_cache/notes/.note.gnu.build-id" > "%OUT%\\loaded-node-cache-note-sha.txt" 2>nul

rem Separate source manifests; never merge vendor and system selection files.
adb shell su -c "cat /system_dlkm/lib/modules/modules.load" > "%OUT%\system-modules.load" 2>nul
adb shell su -c "cat /system_dlkm/lib/modules/modules.dep" > "%OUT%\system-modules.dep" 2>nul
adb shell su -c "cat /vendor_dlkm/lib/modules/modules.load" > "%OUT%\vendor-modules.load" 2>nul
adb shell su -c "cat /vendor_dlkm/lib/modules/modules.dep" > "%OUT%\vendor-modules.dep" 2>nul
adb shell su -c "cat /proc/mounts" 2>nul | findstr /I /C:"system_dlkm" /C:"vendor_dlkm" > "%OUT%\dlkm-mounts.txt"

(
  echo Status: READ-ONLY LIVE FILESYSTEM EVIDENCE
  echo Binder loaded module byte SHA: NOT PROVEN BY FILE HASH ALONE
  echo Vendor/system zsmalloc sources are intentionally separated.
  echo Empty modules.load or SHA output can indicate inaccessible locations.
  echo Empty binder-impl-cmdline means no matching token was observed, NOT a proven C implementation.
  echo Optional loaded module build-id NOTE hashes are NOT complete binary identity.\n  echo Missing sysfs notes remain UNKNOWN and are not errors.\n  echo No raw kernel addresses or raw /proc/cmdline are stored.
  echo No partition, module, root, boot or AVB settings were changed.
) > "%OUT%\README.txt"
echo.
echo READ-ONLY snapshot saved in "%OUT%".
echo File hashes are not proof of actual loaded ELF contents.
echo No phone writes. No flash or reboot.
endlocal
