@echo off
setlocal EnableExtensions
rem Xiaomi 17 Pro / pandora - read-only live ABI facts. No flash, push, or device writes.
where adb >nul 2>&1
if errorlevel 1 (
  echo ERROR: adb.exe is not in PATH. Run from platform-tools.
  exit /b 2
)
set "DEVICE="
for /f "tokens=*" %%D in ('adb shell getprop ro.product.device 2^>nul') do set "DEVICE=%%D"
if /i not "%DEVICE%"=="pandora" (
  echo ERROR: expected pandora. Read-only capture aborted.
  exit /b 3
)
adb shell su -c "id" | findstr /C:"uid=0(root)" >nul
if errorlevel 1 (
  echo ERROR: a working root shell is required.
  exit /b 4
)
set "OUT=pandora-live-abi-%RANDOM%"
mkdir "%OUT%" >nul 2>&1
if errorlevel 1 exit /b 5
echo === Xiaomi pandora identity and running kernel === > "%OUT%\identity.txt"
adb shell getprop ro.product.device >> "%OUT%\identity.txt"
adb shell getprop ro.mi.os.version.incremental >> "%OUT%\identity.txt"
adb shell getprop ro.boot.slot_suffix >> "%OUT%\identity.txt"
adb shell uname -r >> "%OUT%\identity.txt"
adb shell getprop sys.boot_completed >> "%OUT%\identity.txt"
adb shell su -c "cat /proc/modules" > "%OUT%\loaded-modules.txt"
rem Read only: module load lists may not exist in every Android build.
adb shell su -c "for p in /vendor_dlkm/lib/modules/modules.load /system_dlkm/lib/modules/modules.load /vendor/lib/modules/modules.load /odm_dlkm/lib/modules/modules.load; do if [ -f $p ]; then echo FILE:$p; grep -E '(zram|zsmalloc|node_cache|rust_binder)' $p; fi; done" > "%OUT%\module-load-selection.txt"
rem Strip kernel addresses with awk. Only selected symbol NAMES are kept locally.
adb shell su -c "awk '{print $3}' /proc/kallsyms" | findstr /C:"qcom_smem_get" /C:"ipc_log_string" /C:"qcom_scm_assign_mem" /C:"qmp_send" /C:"cdev_tevent_alloc" /C:"__ksymtab_qcom_smem_get" /C:"__ksymtab_ipc_log_string" /C:"__ksymtab_qcom_scm_assign_mem" > "%OUT%\kernel-symbol-names.txt"
echo.
echo READ-ONLY evidence saved in: %OUT%
echo Files: identity.txt, loaded-modules.txt, module-load-selection.txt, kernel-symbol-names.txt
echo No file has been written to the phone. Do not share raw kallsyms addresses.
endlocal
