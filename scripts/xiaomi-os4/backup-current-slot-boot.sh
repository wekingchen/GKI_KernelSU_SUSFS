#!/system/bin/sh
# Xiaomi 17 Pro / pandora OS4：只读备份当前可启动 slot 的关键启动分区。
# 用途：第一轮 OS4 自定义内核测试前建立可恢复基线。
# 不写任何 block device，不切换 slot，不调用 fastboot，不修改 AVB。
set -eu
umask 077

[ "$(id -u)" = "0" ] || {
  echo "请以 Root 运行此脚本"
  exit 1
}

MODEL="$(getprop ro.product.device)"
BUILD="$(getprop ro.build.version.incremental)"
RELEASE="$(uname -r)"
SLOT="$(getprop ro.boot.slot_suffix)"

[ "$MODEL" = "pandora" ] || { echo "设备不是 pandora：$MODEL"; exit 1; }
[ "$BUILD" = "OS4.0.5.0.XBLCNXM" ] || { echo "系统版本不匹配：$BUILD"; exit 1; }
case "$SLOT" in
  _a|_b) ;;
  *) echo "无法确认 A/B slot：$SLOT"; exit 1 ;;
esac

OUT="/sdcard/Download/pandora-OS4.0.5.0-current-slot-backup"
mkdir -p "$OUT"
INFO="$OUT/README.txt"

{
  echo "用途：小米17 Pro OS4 第一轮自定义内核测试前的当前可启动分区备份"
  echo "device=$MODEL"
  echo "build=$BUILD"
  echo "uname=$RELEASE"
  echo "slot=$SLOT"
  echo "date_utc=$(date -u)"
  echo
  echo "注意：这是当前正在使用的可启动状态备份；设备当前使用 LKM Root，因此不宣称它是完全未修改的官方原始 boot。"
  echo "但它可作为本机同版本、同 slot 的已知可启动恢复基线。"
  echo
} > "$INFO"

copied=0
for part in boot init_boot vendor_boot dtbo; do
  SRC="/dev/block/by-name/${part}${SLOT}"
  [ -e "$SRC" ] || {
    echo "SKIP ${part}${SLOT}: partition not found" | tee -a "$INFO"
    continue
  }
  DST="$OUT/${part}${SLOT}.img"
  echo "正在只读备份 ${part}${SLOT} ..."
  dd if="$SRC" of="$DST" bs=4194304 2>>"$INFO"
  [ -s "$DST" ] || { echo "备份失败：$part"; exit 1; }
  sha256sum "$DST" | tee -a "$INFO"
  copied=$((copied + 1))
done

[ "$copied" -gt 0 ] || { echo "没有成功备份任何启动分区"; exit 1; }

echo >> "$INFO"
echo "完成：共备份 $copied 个分区。不要把这些镜像上传到公共 GitHub。" | tee -a "$INFO"
echo "目录：$OUT"
echo "下一步请将 README.txt 和 boot${SLOT}.img 提供给项目做离线校验；其它镜像先留作本机恢复。"
