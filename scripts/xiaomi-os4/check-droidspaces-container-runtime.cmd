@echo off
setlocal
echo Xiaomi 17 Pro OS4 / DroidSpaces container runtime read-only check
echo.
echo [1] Host kernel / boot / root
adb shell uname -r
adb shell getprop sys.boot_completed
adb shell su -c id
echo.
echo [2] Host namespace references
adb shell su -c "echo HOST_PID_NS=$(readlink /proc/1/ns/pid); echo HOST_IPC_NS=$(readlink /proc/1/ns/ipc)"
echo.
echo [3] DroidSpaces cgroup + pids + namespace closed-loop
adb shell su -c "hostpid=$(readlink /proc/1/ns/pid); hostipc=$(readlink /proc/1/ns/ipc); found=0; for d in /sys/fs/cgroup/droidspaces/*; do [ -d \"$d\" ] || continue; found=1; echo ===== CONTAINER_CGROUP:$d =====; if [ -f \"$d/pids.max\" ]; then echo -n 'pids.max='; cat \"$d/pids.max\"; else echo 'pids.max=MISSING'; fi; if [ -f \"$d/pids.current\" ]; then echo -n 'pids.current='; cat \"$d/pids.current\"; fi; if [ -f \"$d/pids.events\" ]; then echo 'pids.events:'; cat \"$d/pids.events\"; fi; first=''; for f in $(find \"$d\" -type f -name cgroup.procs 2>/dev/null); do p=$(head -n 1 \"$f\" 2>/dev/null); if [ -n \"$p\" ] && [ -d \"/proc/$p\" ]; then first=$p; echo PROCESS_CGROUP=$f; echo PROCESS_PID=$p; break; fi; done; if [ -n \"$first\" ]; then cpid=$(readlink /proc/$first/ns/pid); cipc=$(readlink /proc/$first/ns/ipc); cmnt=$(readlink /proc/$first/ns/mnt); cuts=$(readlink /proc/$first/ns/uts); echo CONTAINER_PID_NS=$cpid; echo CONTAINER_IPC_NS=$cipc; echo CONTAINER_MNT_NS=$cmnt; echo CONTAINER_UTS_NS=$cuts; [ \"$cpid\" != \"$hostpid\" ] && echo '[PASS] PID namespace isolated' || echo '[FAIL] PID namespace matches host'; [ \"$cipc\" != \"$hostipc\" ] && echo '[PASS] IPC namespace isolated' || echo '[FAIL] IPC namespace matches host'; else echo '[WARN] no live process found under this cgroup'; fi; done; [ \"$found\" = 1 ] || echo '[WAIT] no /sys/fs/cgroup/droidspaces/<container> found - start one test container first'"
echo.
echo [4] Kernel/module regression markers
adb shell "cat /proc/modules | grep -E '^(node_cache|zram|zsmalloc|kernelsu|rust_binder) ' || true"
adb shell su -c "dmesg | grep -Ei 'Unknown symbol|disagrees about version|kernel BUG|Oops|Call trace|rust_binder' | tail -n 120"
echo.
echo Expected:
echo   - at least one CONTAINER_CGROUP
echo   - pids.max is a number, not max
echo   - pids.current is below pids.max
echo   - PID namespace isolated = PASS
echo   - IPC namespace isolated = PASS
echo   - no kernelsu LKM and no ABI/kernel crash markers
endlocal
