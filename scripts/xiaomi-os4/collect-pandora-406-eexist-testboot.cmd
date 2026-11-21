@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem pandora OS4.0.6 EEXIST-shim FASTBOOT-BOOT-ONLY read-only verification.
rem NO root required. NO phone writes, reboot, fastboot flash, insmod or modprobe.
where adb >nul 2>&1 || (
  echo ERROR: adb is required in PATH.
  exit /b 2
)
where powershell.exe >nul 2>&1 || (
  echo ERROR: Windows PowerShell is required.
  exit /b 2
)
set "OUT=pandora-406-eexist-live-%RANDOM%"
mkdir "%OUT%" >nul 2>&1 || exit /b 2

adb get-state > "%OUT%\adb-state.txt" 2>&1
findstr /x /c:"device" "%OUT%\adb-state.txt" >nul || (
  echo ERROR: adb device is not ready.
  type "%OUT%\adb-state.txt"
  exit /b 3
)

(
  echo device=
  echo build=
  echo slot=
  echo uname=
  echo boot_completed=
) > "%OUT%\identity.raw.txt"
adb shell getprop ro.product.device > "%OUT%\device.txt" 2>&1
adb shell getprop ro.mi.os.version.incremental > "%OUT%\build.txt" 2>&1
adb shell getprop ro.boot.slot_suffix > "%OUT%\slot.txt" 2>&1
adb shell uname -r > "%OUT%\uname.txt" 2>&1
adb shell getprop sys.boot_completed > "%OUT%\boot-completed.txt" 2>&1

rem Never save raw /proc/cmdline. Extract only the experiment token and KSU guard.
adb shell cat /proc/cmdline 2>nul | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { [regex]::Matches($_, '(?:pandora_rust_binder_eexist=[A-Za-z0-9_-]+|module_blacklist=[A-Za-z0-9_,.-]+)') | ForEach-Object { $_.Value } }" > "%OUT%\filtered-kernel-params.txt"

adb shell cat /sys/module/binder/parameters/impl > "%OUT%\binder-impl.txt" 2>nul
adb shell cat /sys/module/binder/parameters/active_impl > "%OUT%\binder-active-impl.txt" 2>nul

rem Redact all module load addresses. Only retain four module names + size/user counts.
adb shell cat /proc/modules 2>nul | powershell.exe -NoProfile -NonInteractive -Command "$input | ForEach-Object { $c = $_ -split '\s+'; if ($c.Count -ge 3 -and $c[0] -in @('rust_binder','zsmalloc','zram','node_cache','binder_linux','kernelsu')) { $c[0] + ' size=' + $c[1] + ' users=' + $c[2] } }" > "%OUT%\loaded-modules-redacted.txt"

adb shell "if [ -r /sys/module/rust_binder/initstate ]; then cat /sys/module/rust_binder/initstate; else echo ABSENT; fi" > "%OUT%\rust-binder-initstate.txt" 2>nul
adb shell cat /proc/sys/kernel/modules_disabled > "%OUT%\modules-disabled.txt" 2>nul

rem These two commands exercise Android Binder without changing device state.
adb shell service check activity > "%OUT%\binder-service-activity.txt" 2>&1
adb shell service check package > "%OUT%\binder-service-package.txt" 2>&1

rem Match only our fixed kernel warning; never save the full kernel log.
adb shell logcat -b kernel -d 2>nul | findstr /C:"pandora: rust_binder load request satisfied as EEXIST for C-Binder experiment" > "%OUT%\shim-kernel-log.txt"

rem GNU Note hashes remain read-only runtime source evidence for the vendor memory stack.
adb shell sha256sum /sys/module/zsmalloc/notes/.note.gnu.build-id > "%OUT%\loaded-zsmalloc-note-sha.txt" 2>nul
adb shell sha256sum /sys/module/zram/notes/.note.gnu.build-id > "%OUT%\loaded-zram-note-sha.txt" 2>nul
adb shell sha256sum /sys/module/node_cache/notes/.note.gnu.build-id > "%OUT%\loaded-node-cache-note-sha.txt" 2>nul

del /q "%OUT%\identity.raw.txt" >nul 2>&1
(
  echo Status: READ-ONLY EEXIST SHIM TESTBOOT EVIDENCE
  echo Expected device/build: pandora / OS4.0.6.0.XBLCNXM
  echo Expected experiment token: pandora_rust_binder_eexist=1
  echo Expected Binder request state: c
  echo Expected rust_binder module state under shim: ABSENT
  echo Expected vendor zsmalloc/zram/node_cache to remain loaded.
  echo service check is read-only Binder liveness evidence, not a complete Android functional test.
  echo No raw cmdline, raw kernel log, or kernel addresses are stored.
  echo No phone writes, root command, reboot, module insertion or flash operation is performed.
) > "%OUT%\README.txt"

powershell.exe -NoProfile -NonInteractive -Command "Compress-Archive -LiteralPath '%OUT%' -DestinationPath '%OUT%.zip' -Force" >nul 2>&1
if errorlevel 1 (
  echo WARNING: ZIP creation failed. Upload folder "%OUT%" instead.
) else (
  echo Evidence archive: "%OUT%.zip"
)
echo READ-ONLY snapshot saved in "%OUT%".
endlocal
