# Xiaomi 17 Series / SM8850 — Android 16 / Linux 6.12.23

This target is intentionally isolated from the repository's generic GKI workflows. The repository can keep following `zzh20188/GKI_KernelSU_SUSFS:dev` while Xiaomi-specific compatibility work remains on `xiaomi-sm8850-pandora`.

## Branch maintenance model

- `dev` tracks upstream `zzh20188/GKI_KernelSU_SUSFS:dev` as closely as possible.
- `xiaomi-sm8850-pandora` contains only Xiaomi/SM8850-specific workflow, pins, validation and packaging.
- Upstream feature changes should land/sync into `dev` first, then `dev` is merged into the Xiaomi branch.
- Xiaomi compatibility changes should not be copied back into generic `build.yml` unless they are genuinely generic fixes.

At the time this Xiaomi lane was reviewed, the local and upstream `dev` heads were identical at `29428612f180915f64e9b7c231e17705290e87b5`.

## Verified device scope

| Marketing name | Codename | Platform | Target |
|---|---|---|---|
| Xiaomi 17 | `pudding` | Qualcomm SM8850 | supported |
| Xiaomi 17 Pro | `pandora` | Qualcomm SM8850 | primary |
| Xiaomi 17 Pro Max | `popsicle` | Qualcomm SM8850 | supported |

Xiaomi's MiCode `popsicle-w-oss` branch identifies the family as `release-w-qcom-sm8850`. Its root BSP tree is Linux 6.11, so it is a vendor/BSP reference and is not used as the 6.12.23 boot Image source.

## Stock evidence

The uploaded Xiaomi 17 Pro OS3.0.319.0.WBLCNXM boot image contains:

```text
6.12.23-android16-5-g75e9b1c7ae7c-abogki463945075-4k
```

The older generic build that bootlooped used:

```text
6.12.23-android16-5-g13ff069897df9-ab10024759-4k
```

Its Action log proves `g13ff069...` was the actual then-current head of Google's `deprecated/android16-6.12-2025-06` source, not merely a cosmetic local-version string. Therefore matching only `6.12.23 / android16-5 / 4K` is not sufficient evidence of Xiaomi vendor-module compatibility.

## Source profiles

The Xiaomi workflow now exposes two immutable source profiles.

### `gold-cctv` — default diagnostic baseline

This uses the public source family referenced by the Droidspaces Xiaomi 17-series entry and by the known-booting Gold 6.12.23 package:

- repo: `cctv18/android_gki_kernel_common`
- branch family: `android16-6.12-2025-06`
- pinned commit: `9e91eb74a201e8cee839c8db6d642ff9b8408388`

This is deliberately described as a **Gold-compatible public source line**, not proof that this exact commit produced the binary Gold ZIP already tested on the phone. The branch moved over time, so the Xiaomi workflow pins the commit rather than following its moving head.

### `ack-r51` — clean official control

This keeps the late official ACK 2025-06 respin as a second controlled baseline:

- tag: `android16-6.12-2025-06_r51`
- commit: `5a0e85dd9db068df8f0cdff9be76fe4211bd8af9`
- KMI generation: 5
- Clang: `r536225`

Both profiles use the same pinned ACK toolchain/build-support snapshot, but intentionally use different build methods:

- `gold-cctv`: direct `make gki_defconfig Image`, matching the public Gold/cctv18 build family and producing only the boot kernel Image. This avoids Kleaf's unrelated system-DLKM module collection requirement.
- `ack-r51`: `//common:kernel_aarch64_dist` through Kleaf/Bazel with ThinLTO and KMI enforcement intact.

The exact build method and final LTO setting are recorded in each artifact's `build-metadata.txt`.

## Current custom builder

The Xiaomi lane has completed the original A/B/C compatibility ladder and is now a selectable custom builder.

Physical validation on Xiaomi 17 Pro (`pandora`):

- A / base: run #60 — booted and short hardware/stability check passed.
- B / ReSukiSU: run #62 — booted; Manager reported version code 35184; root authorization worked.
- C / ReSukiSU + SUSFS: run #63 — booted; SUSFS v2.3.0 was visible and working.
- Full feature candidate: run #76 — booted successfully and showed no immediate abnormal behavior during the initial post-boot check.

The #76 full candidate keeps the proven C foundation and simultaneously enables every Xiaomi optional feature that passed the individual CI matrix, except KPM:

- SUSFS extra features
- ZRAM/LZ4 enhancement
- Baseband Guard (BBG)
- Re-Kernel
- NoMount
- Android 16 / 6.12 networking feature set
- DroidSpaces
- NTSync
- CVE-2026-43499 / CVE-2026-53163 fix chain

KPM remains disabled because the current ReSukiSU main used by this lane does not declare `CONFIG_KPM`; the Xiaomi integration intentionally rejects an unsupported KPM request instead of pretending it is enabled.

### Recommended workflow defaults

The Xiaomi workflow is intentionally usable without editing YAML. Its `workflow_dispatch` defaults represent the currently recommended Xiaomi 17 Pro configuration:

- Xiaomi 17 Pro (`pandora`), Gold/cctv18 6.12.23 source, ReSukiSU + SUSFS
- SUSFS extras, ZRAM/LZ4K/LZ4KD, Baseband Guard, Re-Kernel, networking, DroidSpaces/NTSync and the CVE fix chain enabled
- KPM disabled because current ReSukiSU main does not declare `CONFIG_KPM`
- **NoMount disabled by default.** ReSukiSU users staying on Magic Mount do not need NoMount merely to use modules. Enable it only when intentionally using the NoMount VFS injection/Metamodule path.
- AnyKernel3-only artifact upload by default

The GUI also exposes Xiaomi 17 (`pudding`) and Xiaomi 17 Pro Max (`popsicle`). They share the SM8850 build lane but have not received the same physical validation as `pandora`.

PR CI is deliberately different from the user-facing defaults: its `full` combination smoke still enables NoMount so the optional integration continues to receive regression coverage.

## Validation levels

Do not conflate these states:

1. **CI integration validated** — patch/config integration, kernel compilation and final validation pass.
2. **Physical boot validated** — the resulting AnyKernel package boots on the Xiaomi 17 Pro.
3. **Feature behavior validated** — the individual feature has been exercised on-device and its runtime behavior confirmed.

Run #74 proved the optional features individually at level 1. Runs #75/#76 proved the combined full profile at level 1. Run #76 reached level 2 and, on 2026-09-28, several optional features were additionally verified on the running Xiaomi 17 Pro without changing the kernel:

| Feature | On-device evidence | Status |
|---|---|---|
| ZRAM | `/dev/block/zram0` active as 12 GiB swap; LZ4K/LZ4KD backends registered; current HyperOS algorithm remains `lzo-rle` | runtime validated |
| Baseband Guard | live `baseband_guard` dmesg events marked real processes by SELinux domain | runtime validated |
| SUSFS extras | `ksu_susfs v2.3.0 show enabled_features` reported SPOOF_UNAME, HIDE_KSU_SUSFS_SYMBOLS, SPOOF_CMDLINE_OR_BOOTCONFIG, OPEN_REDIRECT and SUS_MAP | runtime interface validated |
| Networking | BBR registered and selected at runtime; IPSet symbols present; iptables nat/mangle/raw/filter tables present; CIFS registered | runtime validated |
| NTSync | `/dev/ntsync` misc device exists and NTSync runtime symbols/initcall are present | runtime validated |
| DroidSpaces prerequisites | IPC/PID/User namespaces were created successfully with `unshare`; PID namespace child ran as PID 1 | kernel/runtime prerequisites validated; full userspace workload pending |
| Re-Kernel | built-in symbols are present and a read-only Generic Netlink `GET_VERSION` probe returned `11.7` from the running kernel | runtime userspace ABI validated; individual hook behavior not destructively exercised |
| NoMount | built-in symbols are present and a read-only NoMount `NM_CMD_GET_VERSION` probe returned `20` from the running kernel | runtime userspace ABI validated; path-rule behavior not modified during validation |
| CVE fix chain | patch/config/build validation passed | do not intentionally trigger the vulnerabilities on the device |

These levels are intentionally conservative: built-in symbol presence is not treated as proof that a userspace protocol or every hook path has been exercised.

## Root and SUSFS tracking

The normal custom build follows the upstream branches but records the exact resolved commits in every artifact for reproducibility.

Current physically proven foundation:

- ReSukiSU: `fa8311f632a215b5381ec644627c6198d1e8a13e`, tag `v4.2.0-rc3`, version code `35184`
- SUSFS `gki-android16-6.12`: `b213c54126fb243595ce7876e91d84d6e0861fec`, version `v2.3.0`
- AnyKernel3: `dca9dc370838d919d56c1f59ec78b27a14a72c68`

ReSukiSU is built in with `CONFIG_KSU=y`; no LKM mode is used. SUSFS application is fail-fast: dry-run first, patch failure is fatal, and any `.rej` file fails the build.

## Full candidate provenance

The physically boot-tested #76 full artifact was built from workflow commit:

```text
adce911ce19573f148ada2c066f2b52b93a97bdf
```

Its validated release is:

```text
6.12.23-android16-5-g9e91eb74a201-xiaomi-4k
```

Feature source commits recorded by the artifact include:

- ZRAM patch stack: `2844bf492f557fb39113fc93a2dd1602e05790d7`
- Re-Kernel: `ac08296174d7fb2801c0eee1084f067a34f8a0fe`
- NoMount: `6b1be186322d4e0bdc465cf27f6fc0d3679087c6`
- DroidSpaces: `b24eec0194e9b0ce8981152eba4603b40bf919e5`

Artifact checksums:

```text
Image
49c26004039b0230ff207c7183483685ff9556a106c31d95866eb609b7f23277

Xiaomi17Series-pandora-Android16-6.12.23-resukisu-susfs-AnyKernel3.zip
998535cb5f0946460011a1398fff5e933300b29f3ab680e1ded33ec78b6004fa
```

## CI guardrails

The final built Image must pass checks for:

- ARM64 / Linux 6.12.23 / `android16-5`
- 4K page size
- KMI generation 5
- `CONFIG_MODVERSIONS=y`
- `CONFIG_GENDWARFKSYMS=y`
- deterministic local version with no accidental trailing `+`
- exact pinned Gold source commit
- resolved ReSukiSU/SUSFS provenance when enabled
- requested optional feature configs present in the final config
- no patch reject files

The `gold-cctv` lane intentionally builds only the kernel Image using the known-compatible direct-make path. The `ack-r51` profile remains the clean Kleaf/Bazel control lane.

PR CI first runs `bash -n` over the Xiaomi scripts. Normal regression CI is then reduced to two profiles:

- `baseline`: the physically proven ReSukiSU + SUSFS core with optional features off.
- `full`: all currently CI-supported Xiaomi optional features enabled together, except KPM.

The earlier #74 ten-profile matrix remains the evidence that each optional integration also compiles independently.

## Cache strategy

The Xiaomi Gold path uses three safe cache layers:

- immutable Gold common Git object store
- pinned r536225 toolchain bundle
- ccache compiler objects

The common source cache is never used as a dirty modified working tree: every build creates a fresh checkout before applying ReSukiSU, SUSFS and optional features. The kernel `out/` directory is deliberately not cached.

A warm baseline build has demonstrated approximately 99.9% incremental ccache hits and roughly two minutes for the Image compilation phase.

## AnyKernel3 behavior

The package is boot-only and device-scoped. It contains only the kernel Image plus the required AnyKernel3 scripts/tools.

It targets `boot`, auto-detects the active slot, disables vbmeta flag patching, and uses `split_boot; flash_boot;`. It does not package or flash `init_boot`, `vendor_boot`, `vendor_kernel_boot`, `dtbo` or `vbmeta`.

## Next device-validation stage

The #76 full image has passed boot, initial basic-use checks and the runtime checks recorded above on `pandora`. Keep this exact kernel installed while closing the remaining gaps:

- optionally exercise a safe real Re-Kernel hook path; its Generic Netlink userspace ABI is already proven
- optionally exercise a disposable NoMount path rule; its userspace ABI is already proven
- run an actual DroidSpaces userspace/container workload; namespace creation and NTSync are already proven
- continue normal-use regression observation; do not intentionally exploit-test the CVE fixes

The full stack should only be described as fully behavior-validated after those remaining userspace paths are exercised. `pudding` and `popsicle` remain same-platform build targets but are not yet physically validated.

## 上游同步策略

Xiaomi 17 系列支持已经完全合入默认分支 `dev`，不依赖长期功能分支。为降低 fork 与上游同步时的冲突概率，Xiaomi 定制尽量只放在 fork 独有的文件和目录中：

- `.github/workflows/xiaomi-sm8850-dispatch.yml`
- `.github/workflows/kernel-xiaomi-sm8850.yml`
- `.github/config/xiaomi-sm8850-android16-6.12.23.env`
- `scripts/xiaomi-sm8850/`
- `docs/xiaomi-sm8850.md`

日常同步 `zzh20188/GKI_KernelSU_SUSFS:dev` 时应使用正常的 GitHub **Sync fork / Update branch / merge** 流程，不要使用强制 reset、强制 push 或 “Discard commits” 把本地 `dev` 覆盖成上游 `dev`。

正常 merge 同步只会更新上游发生变化的文件，以上 fork 独有文件会继续保留。只有当上游未来新增同名 Xiaomi 文件或修改同一路径时，才需要人工处理冲突。

同步完成后建议手动运行一次 **Xiaomi 17 系列 - 自定义内核**。只要该工作流仍能看到并成功调用本地 `kernel-xiaomi-sm8850.yml`，即可确认 Xiaomi 定制没有在同步过程中丢失。

### 误点 Discard commits 的恢复

仓库保留长期恢复分支 `xiaomi-sm8850-stable`。该分支不参与日常上游同步，用于保存已经确认可用的 Xiaomi 17 系列实现。

如果误操作导致默认分支 `dev` 被重置为上游状态，不要继续强制同步或删除恢复分支。恢复方式是将 `xiaomi-sm8850-stable` 合并回 `dev`；如果上游此时已有新提交，则先以正常 Pull Request / merge 的方式合并二者并处理实际冲突。

恢复完成后应确认以下 fork 独有路径重新存在：

- `.github/workflows/xiaomi-sm8850-dispatch.yml`
- `.github/workflows/kernel-xiaomi-sm8850.yml`
- `.github/config/xiaomi-sm8850-android16-6.12.23.env`
- `scripts/xiaomi-sm8850/`
- `docs/xiaomi-sm8850.md`

然后运行一次 **Xiaomi 17 系列 - 自定义内核** 做 CI 验证。不要通过删除 `xiaomi-sm8850-stable`、强制 reset 或 force push 来“清理”恢复历史。

### 稳定分支与恢复层级

为了避免日常 `dev` 开发、上游同步或误点 **Discard commits** 影响已经验证过的 Xiaomi 方案，仓库采用三层恢复结构：

- `dev`：日常开发与上游同步分支。
- `xiaomi-sm8850-stable`：可移动的稳定恢复点。只有在对应版本完成 CI 且已确认真机正常后才推进；不需要用户手动维护。
- `xiaomi-sm8850-lkg-20260928`：永久保留的 Last Known Good（LKG）里程碑，指向首个完成合并且对应实现已在 Xiaomi 17 Pro / pandora 真机验证的提交。该分支不随 `dev` 或 `stable` 更新。

正常情况下用户只使用 `dev`。不要对 `xiaomi-sm8850-stable` 或 LKG 分支执行 Sync fork、Discard commits、force push、reset 或删除操作。

如果未来 `dev` 被误重置，优先从 `xiaomi-sm8850-stable` 通过正常 PR / merge 恢复；如果 stable 本身也存在疑问，则使用 `xiaomi-sm8850-lkg-20260928` 作为最后兜底。恢复过程禁止 force push 覆盖历史。

### 自动看门狗

默认分支 `dev` 内置 `.github/workflows/xiaomi-sm8850-watchdog.yml`：

- 每天定时检查一次；
- Xiaomi 关键 workflow、配置、脚本或本文档发生改动时立即检查；
- 校验 Xiaomi 关键路径是否仍存在；
- 校验 dispatcher 仍调用本地 `kernel-xiaomi-sm8850.yml`；
- 校验 `xiaomi-sm8850-stable` 与固定 LKG 分支仍存在；
- 校验 LKG 仍指向预期提交，没有被意外移动；
- 异常时让该 Actions 运行明确失败并显示错误摘要，并在可行时从 stable 向 dev 创建普通恢复 PR；
- 不执行自动 merge、force push、reset 或分支删除。

由于 GitHub 的 scheduled workflow 只能依赖默认分支中的 workflow 文件，如果整个 `dev` 被 **Discard commits** 重置成上游、连 watchdog 文件本身一起消失，同仓库 Action 无法继续自检。因此另保留一个低频外部兜底，只检查 watchdog 文件以及 stable/LKG 分支是否仍存在；日常完整检查由 GitHub Actions 完成。

