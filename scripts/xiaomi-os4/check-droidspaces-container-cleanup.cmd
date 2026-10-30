@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "NAME=%~1"
if "%NAME%"=="" set "NAME=test"

echo Xiaomi 17 Pro OS4 / DroidSpaces cgroup cleanup check
echo Container: %NAME%
echo.

adb get-state >nul 2>&1
if errorlevel 1 (
  echo [FAIL] ADB device not found.
  exit /b 1
)

adb shell su -c "NAME='%NAME%'; D=/sys/fs/cgroup/droidspaces/$NAME; echo ===KERNEL===; uname -r; echo ===TARGET===; echo $D; if [ -e \"$D\" ]; then echo CLEANUP_RESULT=FAIL; echo '[stale cgroup still exists]'; find \"$D\" -maxdepth 2 -type f \( -name cgroup.procs -o -name pids.current -o -name pids.max \) -print -exec sh -c 'echo --- $1; cat $1 2>/dev/null' sh {} \;; else echo CLEANUP_RESULT=PASS; fi; echo ===DROIDSPACES_TREE===; find /sys/fs/cgroup/droidspaces -maxdepth 2 -type d -print 2>/dev/null || true"

endlocal
