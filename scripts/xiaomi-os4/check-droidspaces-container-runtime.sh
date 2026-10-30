#!/system/bin/sh
# Xiaomi 17 Pro OS4 / DroidSpaces runtime closed-loop checker
# Read-only: does not change cgroups, namespaces, limits, or kernel state.
set -u

echo "Xiaomi 17 Pro OS4 / DroidSpaces container runtime read-only check v2"
echo

echo "[1] Host kernel / boot / root"
uname -r
getprop sys.boot_completed
id
echo

host_pid_ns="$(readlink /proc/1/ns/pid 2>/dev/null || true)"
host_ipc_ns="$(readlink /proc/1/ns/ipc 2>/dev/null || true)"
echo "[2] Host namespace references"
echo "HOST_PID_NS=$host_pid_ns"
echo "HOST_IPC_NS=$host_ipc_ns"
echo

echo "[3] DroidSpaces cgroup + pids + namespace closed-loop"
found_container=0
overall_pid_iso=0
overall_ipc_iso=0
for d in /sys/fs/cgroup/droidspaces/*; do
  [ -d "$d" ] || continue
  found_container=1
  echo "===== CONTAINER_CGROUP:$d ====="

  if [ -f "$d/pids.max" ]; then
    pmax="$(cat "$d/pids.max" 2>/dev/null || true)"
    echo "pids.max=$pmax"
  else
    pmax=""
    echo "pids.max=MISSING"
  fi

  if [ -f "$d/pids.current" ]; then
    pcur="$(cat "$d/pids.current" 2>/dev/null || true)"
    echo "pids.current=$pcur"
  else
    pcur=""
  fi

  if [ -f "$d/pids.events" ]; then
    echo "pids.events:"
    cat "$d/pids.events"
  fi

  case "$pmax:$pcur" in
    [0-9]*:[0-9]*)
      if [ "$pcur" -le "$pmax" ] 2>/dev/null; then
        echo "[PASS] pids.current <= pids.max"
      else
        echo "[FAIL] pids.current exceeds pids.max"
      fi
      ;;
    max:*) echo "[FAIL] pids.max is unlimited (max)" ;;
  esac

  seen=" "
  container_pid=""
  container_pid_ns=""
  container_ipc_ns=""
  for f in $(find "$d" -type f -name cgroup.procs 2>/dev/null); do
    while IFS= read -r p; do
      [ -n "$p" ] || continue
      [ -d "/proc/$p" ] || continue
      case "$seen" in *" $p "*) continue ;; esac
      seen="$seen$p "

      pns="$(readlink "/proc/$p/ns/pid" 2>/dev/null || true)"
      ins="$(readlink "/proc/$p/ns/ipc" 2>/dev/null || true)"
      comm="$(cat "/proc/$p/comm" 2>/dev/null || true)"
      nspid="$(awk '/^NSpid:/{for(i=2;i<=NF;i++) printf "%s%s", $i, (i<NF?"/":""); print ""}' "/proc/$p/status" 2>/dev/null || true)"
      echo "PROCESS pid=$p comm=$comm pidns=$pns ipcns=$ins nspid=$nspid cgroup=$f"

      # CLONE_NEWPID changes the namespace of subsequently forked children,
      # not the intermediate caller itself. Therefore scan all cgroup tasks
      # and select a process whose PID namespace actually differs from host.
      if [ -z "$container_pid" ] && [ -n "$pns" ] && [ "$pns" != "$host_pid_ns" ]; then
        container_pid="$p"
        container_pid_ns="$pns"
        container_ipc_ns="$ins"
      fi
    done < "$f"
  done

  if [ -n "$container_pid" ]; then
    echo "CONTAINER_PROCESS_PID=$container_pid"
    echo "CONTAINER_PID_NS=$container_pid_ns"
    echo "CONTAINER_IPC_NS=$container_ipc_ns"
    if [ "$container_pid_ns" != "$host_pid_ns" ]; then
      echo "[PASS] PID namespace isolated"
      overall_pid_iso=1
    else
      echo "[FAIL] PID namespace matches host"
    fi
    if [ -n "$container_ipc_ns" ] && [ "$container_ipc_ns" != "$host_ipc_ns" ]; then
      echo "[PASS] IPC namespace isolated"
      overall_ipc_iso=1
    else
      echo "[FAIL] IPC namespace matches host"
    fi
  else
    echo "[FAIL] no live task with a PID namespace different from host was found"
  fi
done

if [ "$found_container" -eq 0 ]; then
  echo "[WAIT] no /sys/fs/cgroup/droidspaces/<container> found - start one test container first"
fi
echo

echo "[4] Kernel/module regression markers"
grep -E '^(node_cache|zram|zsmalloc|kernelsu|rust_binder) ' /proc/modules 2>/dev/null || true
markers="$(dmesg 2>/dev/null | grep -Ei 'Unknown symbol|disagrees about version|kernel BUG|Oops|Call trace:' || true)"
if [ -n "$markers" ]; then
  echo "[WARN] kernel regression marker(s) found; context follows:"
  dmesg 2>/dev/null | grep -Ei -B 35 -A 90 'Unknown symbol|disagrees about version|kernel BUG|Oops|Call trace:' | tail -n 320
else
  echo "[PASS] no Unknown symbol / version disagreement / BUG / Oops / Call trace marker"
fi
echo

echo "[5] Summary"
[ "$found_container" -eq 1 ] && echo "CONTAINER_CGROUP=FOUND" || echo "CONTAINER_CGROUP=NOT_FOUND"
[ "$overall_pid_iso" -eq 1 ] && echo "PID_NAMESPACE_RUNTIME=PASS" || echo "PID_NAMESPACE_RUNTIME=FAIL"
[ "$overall_ipc_iso" -eq 1 ] && echo "IPC_NAMESPACE_RUNTIME=PASS" || echo "IPC_NAMESPACE_RUNTIME=FAIL"
echo "READ_ONLY_CHECK=YES"
