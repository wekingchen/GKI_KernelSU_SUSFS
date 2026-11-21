@echo off
setlocal EnableExtensions
rem Xiaomi pandora OS4: READ ONLY. No flashing, Root changes, or phone writes.
rem Windows CMD cannot safely nest Android "for ... do" or awk quote strings in su -c.
rem Use simple device-side cat only and do all filtering on the Windows host.
where adb >nul 2>&1
if errorlevel 1 (
  echo ERROR: adb.exe not found. Run this script from platform-tools.
  exit /b 2
)
where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Windows PowerShell is required to strip kallsyms addresses.
  exit /b 2
)
set "DEVICE="
for /f "tokens=*" %%D in ('adb shell getprop ro.product.device 2^>nul') do set "DEVICE=%%D"
if /i not "%DEVICE%"=="pandora" (
  echo ERROR: expected pandora but got "%DEVICE%".
  exit /b 3
)
adb shell su -c "id" 2>nul | findstr /C:"uid=0(root)" >nul
if errorlevel 1 (
  echo ERROR: root shell is unavailable. No data collected.
  exit /b 4
)
set "OUT=pandora-live-abi-%RANDOM%"
mkdir "%OUT%" >nul 2>&1
if errorlevel 1 (
  echo ERROR: could not create an unused output folder.
  exit /b 5
)
set "PARTIAL=0"
echo === Xiaomi pandora identity and running kernel === > "%OUT%\identity.txt"
adb shell getprop ro.product.device >> "%OUT%\identity.txt"
adb shell getprop ro.mi.os.version.incremental >> "%OUT%\identity.txt"
adb shell getprop ro.boot.slot_suffix >> "%OUT%\identity.txt"
adb shell uname -r >> "%OUT%\identity.txt"
adb shell getprop sys.boot_completed >> "%OUT%\identity.txt"

rem This operation already succeeded on the user's actual OS4.0.6.0 Slot B device.
adb shell su -c "cat /proc/modules" > "%OUT%\loaded-modules.txt" 2>nul
if errorlevel 1 (
  echo ERROR: failed to read /proc/modules; do not trust this capture.
  exit /b 6
)
for %%F in ("%OUT%\loaded-modules.txt") do if %%~zF EQU 0 (
  echo ERROR: /proc/modules returned an empty file; capture failed.
  exit /b 6
)

rem No remote for/if/awk/grep; issue only simple su -c cat per file.
rem Empty individual modules.load files may mean that location is not mounted.
adb shell su -c "cat /vendor_dlkm/lib/modules/modules.load" > "%OUT%\vendor_dlkm-modules.load" 2>nul
adb shell su -c "cat /system_dlkm/lib/modules/modules.load" > "%OUT%\system_dlkm-modules.load" 2>nul
adb shell su -c "cat /vendor/lib/modules/modules.load" > "%OUT%\vendor-modules.load" 2>nul
adb shell su -c "cat /odm_dlkm/lib/modules/modules.load" > "%OUT%\odm_dlkm-modules.load" 2>nul
adb shell su -c "cat /lib/modules/modules.load" > "%OUT%\ramdisk-modules.load" 2>nul

(
  echo === vendor_dlkm ===
  findstr /I /C:"zram" /C:"zsmalloc" /C:"node_cache" /C:"rust_binder" "%OUT%\vendor_dlkm-modules.load"
  echo === system_dlkm ===
  findstr /I /C:"zram" /C:"zsmalloc" /C:"node_cache" /C:"rust_binder" "%OUT%\system_dlkm-modules.load"
  echo === vendor ===
  findstr /I /C:"zram" /C:"zsmalloc" /C:"node_cache" /C:"rust_binder" "%OUT%\vendor-modules.load"
  echo === odm_dlkm ===
  findstr /I /C:"zram" /C:"zsmalloc" /C:"node_cache" /C:"rust_binder" "%OUT%\odm_dlkm-modules.load"
  echo === ramdisk ===
  findstr /I /C:"zram" /C:"zsmalloc" /C:"node_cache" /C:"rust_binder" "%OUT%\ramdisk-modules.load"
) > "%OUT%\module-load-selection.txt"

rem Device-side: cat only. Windows findstr filters; PowerShell removes each address
rem and symbol type before anything is saved. Never store raw /proc/kallsyms.
adb shell su -c "cat /proc/kallsyms" 2>nul | findstr /I /C:"qcom_smem_get" /C:"ipc_log_string" /C:"qcom_scm_assign_mem" /C:"qmp_send" /C:"cdev_tevent_alloc" | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { $cols = $_ -split '\s+'; if ($cols.Count -ge 3) { $cols[2] } }" > "%OUT%\kernel-symbol-names.txt"

set "LOADFOUND=0"
for %%F in ("%OUT%\vendor_dlkm-modules.load" "%OUT%\system_dlkm-modules.load" "%OUT%\vendor-modules.load" "%OUT%\odm_dlkm-modules.load" "%OUT%\ramdisk-modules.load") do if %%~zF GTR 0 set /a LOADFOUND+=1 >nul
if "%LOADFOUND%"=="0" (
  echo WARNING: No modules.load file is accessible; exact module source remains unproven.
  set "PARTIAL=1"
)
for %%F in ("%OUT%\kernel-symbol-names.txt") do if %%~zF EQU 0 (
  echo WARNING: No requested kallsyms names found, or kallsyms access is restricted.
  echo WARNING: An empty symbol file is NOT evidence that the symbols are missing.
  set "PARTIAL=1"
)

echo.
echo READ-ONLY capture saved in "%OUT%"
if "%PARTIAL%"=="1" (
  echo Status: PARTIAL; check warnings above.
) else (
  echo Status: captured module lists and selected kallsyms names.
)
echo Files: identity.txt, loaded-modules.txt, module-load-selection.txt,
echo        *-modules.load, kernel-symbol-names.txt
echo No phone writes or reboot. No kernel addresses are stored.
endlocal
