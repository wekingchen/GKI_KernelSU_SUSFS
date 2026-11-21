# pandora OS4.0.6.0：路线 A 原厂源码 / 路线 B Rust Binder 非刷机验证

记录日期：2026-11-21。唯一目标：将 4.0.6.0 的 ABI 根因逐项收敛，**不把未验证构建标记为可刷机**。承接
[pandora 4.0.6.0 OEM ABI 审计](pandora-os4-406-oem-abi-audit-2026-11-21.md)。

## 固定原始事实

- 设备 pandora，Android 17，OS4.0.6.0.XBLCNXM，slot B；现用原厂 6.12.69 + LKM Root。
- stock-input xm.zip SHA256：`bebb8754c16dd30c724fdba3687694e615e03342d6f5f55918cd06f1dca8cbb8`。
- 未验证 GKI 来源：`android16-6.12-2026-03_r74`，归档
  [pandora-os4-ota-candidate-OS4.0.6.0.XBLCNXM](https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-ota-candidate-OS4.0.6.0.XBLCNXM)，仅 Image / Module.symvers / config。
- 原厂 rust_binder.ko：`scmversion=g43b5ab7e247d`，SHA256：
  `ea5a84225ce1af3c8af7effed891aa91ed879a9d85780d40a31aa79d3fbcd34c`。
  它的 240 次导入中，71 次 Rust mangled 导入无法在 r74 候选 GKI 的 vmlinux 导出中解析。
- 原厂 Binder 的 Rust core crate 标识与 r74 GKI 不一致。已验证旧 R62 vmlinux 也没有这 71 个导出；旧 R62 AnyKernel3 并未打包 rust_binder.ko。
- 严格 OEM 模块图共检查 38,998 次导入，可比较出的不匹配 CRC 为 0，但剩余 71 个 Rust Binder 未解析与 27 个 zsmalloc 来源歧义。仍为 `BLOCKED`。

## 路线 B：同一次 GKI 构建产物的 Rust Binder 只读配对

新增 `scripts/xiaomi-os4/verify-rust-binder-gki-pair-readonly.py` 与
`test_audit_rust_binder_pair_readonly.py`。设计性质：**单独的诊断工具**，不写入
`check-ota-oem-abi.py` 的放行逻辑，绝不覆盖该工具现有 `BLOCKED` 报告。

1. 固定官方 r74 版本/commit、stock ZIP SHA、GKI Release 的 Module.symvers 与 final.config 的 SHA。
2. 对同一锁定源码运行原有 `build-ota-gki-baseline-candidate.sh` 的纯 GKI Image/modules 构建。
   不改内核配置/上游代码，不打包 boot、AnyKernel3，不上传可供刷写的 .ko 或 Image。
3. 从该构建输出提取 `drivers/android/binder/rust_binder.ko`，比对它的实际 ELF
   `__versions` / `__version_ext_names` / `__version_ext_crcs` 与同构建 GKI 的 vmlinux 导出 CRC。
   要求模块 vermagic 及 SHA 锁定的 Module.symvers 与存档一致。若配置未生成模块，明确 `BLOCKED`。
4. 再以原始 stock ZIP 完整重跑 OEM 依赖图，要求 71 / 24 / 3 的真实阻断仍在，不得借“候选 Binder 自身匹配”伪造 OEM 兼容。
5. 结果只可能是 `PASS_GKI_PAIR_ONLY` 或 `BLOCKED`。前者仅证明**候选新 Binder 与候选新 GKI 配对**；
   它完全不证明 Xiaomi 原厂 Binder 已可加载，也不证明系统会从哪一个分区供给和加载此模块。
   整机 OEM ABI gate 始终 `BLOCKED`。

一次性 GitHub Action 作为隔离诊断使用；验证结束应删除临时 workflow、保留测试和报告结论。
正式 OTA 构建的安全门禁不因这项实验改动。

### 若 GKI 配对通过，下一道仍需单独证明的门槛

- Android 17 的 Binder 运行时究竟使用哪一种实现，不能只看 boot.img 中没有 `binder.impl=rust`；
  必须确认**有效** cmdline/bootconfig、原厂模块加载和实际 Binder 服务行为。
- 若需要替换 system_dlkm 的 Rust Binder，需明确受信任的源码、签名、模块依赖、装载阶段、
  分区更新/恢复机制。单独替换 boot.img 的 AnyKernel3 无法自动提供所需系统模块。
- OEM 其余模块和设备功能的跨 OTA ABI/KMI、启动和恢复仍需独立验收。

## 路线 A：真正的 6.12.69 原厂源码，不能拿相似树代替

公开官方资料（2026-11-21 核对）：

- [MiCode/Xiaomi_Kernel_OpenSource `popsicle-w-oss`](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/popsicle-w-oss)
  确实标记支持 Xiaomi 17 / 17 Pro / 17 Pro Max；commit
  `45705be1220b4cfa8100516ad86711656c0b634e`（2026-03-09）。
  **但该分支 Makefile 为 6.11.0**，`android/ACK_SHA` 指向
  `android16-6.12-2025-06_r8` / 6.12.23。
  因此不能声称这套分支就是本 OTA 的 `6.12.69 g43b5ab7e247d` 精确原厂源码。
- [MiCode/kernel_devicetree `popsicle-w-oss`](https://github.com/MiCode/kernel_devicetree/tree/popsicle-w-oss)
  可为厂商 DTS/板级关系提供线索，但单独并非与 OEM Rust core 完全对应的可重建 GKI 源码。
- 社区项目即使基于 6.12.69、相同 SM8850/KMI 或能启动，也不能替代 OEM 源码身份和
  `rust_binder` 导入 CRC 的逐符号验证。

后续查找的**验收标准**：官方可追溯的内核源码 commit / Rust 构建参数 / Rust core 与 Binder crate
构建参数、相同的源码身份；可以重现原厂 Rust 导出及 Binder 71 个真实符号/CRC，
并能核对配置、工具链来源、vmlinux/Module.symvers。单有 `scmversion` 或 Clang/rustc 版本号不是充分证据。

## zsmalloc：vendor 与 system 两个独立来源，任何时候都不合并

| 来源 | 实际 zsmalloc.ko SHA256 | `zs_malloc` CRC | 匹配的消费者 |
| --- | --- | --- | --- |
| vendor_boot / vendor_dlkm（字节相同） | `350f7127f0a8cda912eea8dfe6d93dbf30e5b31832969aa44ee6161424eaed3e` | `0x1804f5bc` | vendor `node_cache`, vendor `zram` |
| system_dlkm | `b54598bea0a162cd2578f9d1490095fef148014de0c7dbaf012036b6adcbc465` | `0x36f39fe1` | system `zram` |

- **24 个同 CRC 多提供者**不自动去重，**3 个不同 CRC 多提供者**更不能自动选一份。
- 真机 `/proc/modules` 的 `node_cache / zram / zsmalloc` 和 vendor modules.load
  强烈支持当前 vendor 组合，但无法直接证明加载文件的 SHA/完整路径；未来版本不沿用无证据推断。
- 不将这两套模块的 SHA、CRC、导出和消费者依赖放入同一“可相互替换”的 ABI 池；只有
  从可信来源确认真实分区/装载选择后才能单独分析，各自报告、各自门禁。

**不可变安全边界：** 不解除 OTA OEM gate、不发布 fastboot boot/AnyKernel3、不持久刷机、不晋升
4.0.6 LKG、不改现用 4.0.6.0 + LKM Root，不覆盖原有 4.0.5.0 已验证 LKG。
