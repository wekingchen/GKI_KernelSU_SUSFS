#!/system/bin/sh
# 在小米17 Pro OS4 手机 Root Shell 执行：只读采集厂商模块，用于离线 ABI 检查。
# 不读取用户文件、账号、网络日志，不刷机，不写入系统分区。
set -eu
umask 077

[ "$(id -u)" = "0" ] || { echo "请用 su -c 'sh /sdcard/Download/collect-oem-modules.sh' 运行"; exit 1; }
BUILD="$(getprop ro.build.version.incremental)"
RELEASE="$(uname -r)"
[ "$BUILD" = "OS4.0.5.0.XBLCNXM" ] || { echo "系统版本不一致：$BUILD，已停止"; exit 1; }
[ "$RELEASE" = "6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k" ] || {
  echo "原厂内核与已记录版本不一致：$RELEASE，已停止"
  exit 1
}
OUT="/sdcard/Download"
ARCH="$OUT/pandora-OS4.0.5.0-OEM-modules-READONLY.tar.gz"
INFO="$OUT/pandora-OS4.0.5.0-OEM-modules-README.txt"
mkdir -p "$OUT"
{
  echo "目的：只读备份厂商 .ko 模块并进行离线 ABI 比对，禁止直接刷机"
  echo "ro.build.version.incremental=$BUILD"
  echo "ro.build.version.release=$(getprop ro.build.version.release)"
  echo "uname -r=$RELEASE"
  echo "date=$(date -u)"
  echo
  echo "已挂载模块目录："
} > "$INFO"

# 仅列举固定系统模块目录。不能使用外部提供的任意路径。
set --
for path in /vendor_dlkm/lib/modules /system_dlkm/lib/modules /odm_dlkm/lib/modules /vendor/lib/modules /system/lib/modules; do
  if [ -d "$path" ]; then
    echo "$path" >> "$INFO"
    set -- "$@" "${path#/}"
  fi
done
[ "$#" -gt 0 ] || { echo "找不到厂商模块目录，已停止"; exit 1; }

# 不使用 tar -h：只归档明确指定的系统模块目录，不跟随内部软链接访问其它目录。
# 如果归档中的 .ko 只是软链接，离线审计会判为证据不足，不会声称兼容。
echo "只读打包系统模块目录（不跟随任意软链接）..."
tar -c -z -f "$ARCH" -C / "$@"
[ -s "$ARCH" ] || { echo "没有成功生成模块包"; exit 1; }
echo "包大小：$(du -h "$ARCH" | head -n 1)" | tee -a "$INFO"
sha256sum "$ARCH" >> "$INFO"
echo "完成。文件位于："
echo "  $ARCH"
echo "  $INFO"
echo "这仅为原厂模块快照，上传后仍需 CRC 与厂商依赖审核。"
