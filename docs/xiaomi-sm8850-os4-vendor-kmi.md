# 小米 17 Pro / pandora — OS 4 原厂驱动 ABI 核验

> 状态：**审计器自测已通过，原厂模块尚未采集，不能判断 R62 可刷或兼容。**
>
> 只适用精确目标：`OS4.0.5.0.XBLCNXM`，Android 17，内核 `6.12.69-android16-6-g43b5ab7e247d-abogki561813157-4k`。

## 为什么要先做这一项

编译 [R62 基线 #5](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/40840008157) 已成功。它产生：

- `Image` 和 `vmlinux.zst`；
- `vmlinux.symvers`：18,725 条；
- `Module.symvers`：19,323 条；
- `final.config`、`build-metadata.txt`。

但这个公共 R62 的源码提交是 `e2b8ca7c8d0551a6124b1a7322f5ae532845f1b5`，不等于小米原厂已观察到的 `g43b5ab7e247d`。公开的 MiCode `popsicle-w-oss` 目前 `Makefile` 是 6.11.0，不能当作当前 OS4 的精确原厂 6.12.69 源码。

下一步应以原厂 **vendor_dlkm、system_dlkm、odm_dlkm 等模块**的实际 CRC，比较我们的 R62 `vmlinux` 导出符号。不需要先下载超过 12 GB 的完整 Fastboot 包；可以利用手机已拥有的 LKM Root 只读采集正在使用的厂商模块。采集仅是取得分析证据，不会替换内核。

## 手机端：只读采集 OS4 厂商模块

1. 在手机浏览器打开 [采集脚本](https://github.com/wekingchen/GKI_KernelSU_SUSFS/blob/os4/pandora-6.12.69-adaptation-20261029/scripts/xiaomi-os4/collect-oem-modules.sh)，下载原始文件并保存为 `Download/collect-oem-modules.sh`；**不要执行其他版本或来源的脚本**。
2. 在原来可执行 `su -c id` 的手机终端执行：

```sh
su -c 'sh /sdcard/Download/collect-oem-modules.sh'
```

3. 成功后，`Download` 下应有两个文件：
   - `pandora-OS4.0.5.0-OEM-modules-READONLY.tar.gz`：仅指定系统模块目录。
   - `pandora-OS4.0.5.0-OEM-modules-README.txt`：系统版本、内核版本、模块目录、打包哈希。

**约束与注意事项：**

- 脚本强制核验原厂系统版本及 `uname -r`，不一致就退出；不写分区、不禁用 SELinux、不使用 `dd` 或 Fastboot。
- 只备份固定的系统模块目录；不主动访问 `/data`、应用文件、通讯记录和个人信息；`tar` 不追踪内部软链接。可能有未采集的符号依赖，后续只能认定“证据不足”。
- 打包只读，但写入 `Download` 会消耗手机存储；检查空间后再运行。生成的模块包可能较大，上传前注意大小和接收方式。
- 如果因只读系统限制、tar 选项、链接或空间而失败，**不要修改系统分区或强行关闭安全机制**。保留终端错误信息，先修正采集方式。

## 离线分析端：比对 R62 与小米原厂模块

准备从 #5 下载的 `NOFLASH-pandora-OS4-R62-baseline-Image-ABI`，以及上面的模块压缩包。解压至不同目录。

```bash
mkdir -p stock_modules r62
tar -xzf pandora-OS4.0.5.0-OEM-modules-READONLY.tar.gz -C stock_modules
# 从 #5 Artifact 解压 Module.symvers 到 r62 目录
python3 -m pip install pyelftools==0.32
python3 scripts/xiaomi-os4/audit-vendor-kmi.py \
  --symvers r62/Module.symvers \
  --modules stock_modules \
  --output os4-vendor-kmi-report.json
```

也可用 GitHub CLI 在电脑下载 #5：`gh run download 40840008157 -R wekingchen/GKI_KernelSU_SUSFS -n NOFLASH-pandora-OS4-R62-baseline-Image-ABI -D r62`。

**审计器有 3 种结论（都不代表可刷）：**

| 状态 | 解释 |
| --- | --- |
| `CRC_CONFLICT_DETECTED` | OEM 模块要求的某个已识别 vmlinux 符号 CRC 与候选 R62 不同；高风险，阻止刷机 |
| `INCOMPLETE_EVIDENCE` | 原厂模块不全、缺符号版本、导出提供者不明或无法解析等；需要更多真实数据 |
| `NO_CRC_CONFLICT_IN_CHECKED_SYMBOLS_ONLY` | **仅已比较的 CRC 没发现冲突**，不代表 ABI 全面兼容，更不代表可刷机 |

审计 JSON 始终包含 `safe_to_flash: false`。报告中会逐模块列出 `vermagic`、CRC 格式、匹配数、冲突数、待确认外部符号；不会凭 `uname -r` 相同就判为兼容。

## CI 已验证与缺失的证据

- [ABI 自测 #1](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/40846894839) 在 GitHub Runner 上真实编译 ARM64 ELF 模拟模块，普通和扩展 `__versions`、CRC 匹配/冲突、缺版本、损坏 ELF、压缩模块漏检，**7 项测试全部通过**。
- 这不是原厂模块的实际审计；目前 **没有 OS4.0.5.0 的厂商模块输入**，因此不存在真实 CRC 匹配结论。
- 下一阶段仍需精确版本原厂 `boot.img`（最好从官方 Fastboot 包获得；现有 LKM Root 的 live boot 可能已被修改）、`vendor_dlkm` / `system_dlkm` 的完整内容、加载顺序与 OEM 模块间依赖、签名与 KMI namespace、设备树/固件差异，再在安全恢复手段确认后才能考虑刷机。
- 蜂窝网络、VoLTE/IMS、双卡、摄像头、指纹、Wi-Fi、蓝牙等功能只有真机检查能最终验证。

**不把本项检查变成 PIDs Controller 专项，也不恢复 OS3 工作流。** 保留现有 OS4 原厂内核 + LKM Root，PR #14 在真实 ABI 验证完成前继续保持草稿。
