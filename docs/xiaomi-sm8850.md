# Xiaomi 17 Series / SM8850 — Android 16 / Linux 6.12.23

This target is intentionally separate from the repository's generic GKI workflows. It exists to debug Xiaomi 17-series boot compatibility without changing the existing Generic GKI behavior.

## Verified device scope

| Marketing name | Codename | Platform | Target |
|---|---|---|---|
| Xiaomi 17 | `pudding` | Qualcomm SM8850 | supported |
| Xiaomi 17 Pro | `pandora` | Qualcomm SM8850 | supported / primary |
| Xiaomi 17 Pro Max | `popsicle` | Qualcomm SM8850 | supported |

Xiaomi's MiCode `popsicle-w-oss` branch identifies Xiaomi 17 / 17 Pro / 17 Pro Max as `release-w-qcom-sm8850`:

- https://github.com/MiCode/Xiaomi_Kernel_OpenSource/tree/popsicle-w-oss

Important: that MiCode BSP tree reports Linux 6.11 at its root. It is useful as the public Xiaomi SM8850 vendor/BSP reference, but it is **not** used here as the 6.12.23 boot Image source.

## Stock GKI reference versus public source

Public firmware reports for this family use a stock kernel release matching:

```text
6.12.23-android16-5-g75e9b1c7ae7c-abogki463945075-4k
```

The exact Xiaomi/Google source commit represented by `g75e9b1c7ae7c` is not currently identifiable as a public ACK commit. This repository therefore does not pretend that an unrelated public commit is the stock source.

The first reproducible public baseline is pinned separately:

- ACK line: `android16-6.12-2025-06`
- release tag: `android16-6.12-2025-06_r51`
- common commit: `5a0e85dd9db068df8f0cdff9be76fe4211bd8af9`
- KMI generation: `5`
- Clang: `r536225`
- page size: 4K
- LTO: thin
- stable KMI enforcement: kept enabled

This late 2025-06 respin includes Xiaomi-specific KMI symbol-list additions that are absent from some earlier respins. It is a public compatibility baseline, not a claim of byte-identical stock provenance.

The immutable values live in:

```text
.github/config/xiaomi-sm8850-android16-6.12.23.env
```

## Root and SUSFS pins

The first diagnostic revision pins:

- ReSukiSU: `3c1882886dbbb54f4aae7ddf205f8ccde32c2a34`
- SUSFS `gki-android16-6.12`: `7d91da2d2ce056d1abf378d9199aaf1072d37ab0`
- AnyKernel3: `dca9dc370838d919d56c1f59ec78b27a14a72c68`

ReSukiSU is integrated in-tree and the final Image must contain `CONFIG_KSU=y`. No LKM build is used by this target.

SUSFS application is strict: the patch is dry-run first, patch failure is fatal, and any generated `.rej` file fails the build. There is no `patch ... || true` path.

## Diagnostic variants

Run the workflow **Android Kernel Build - Xiaomi 17 Series SM8850**.

- `base`: pinned public ACK baseline only. No KernelSU/ReSukiSU and no SUSFS.
- `resukisu`: same baseline + ReSukiSU built-in, using its GKI tracepoint hook.
- `resukisu-susfs`: same baseline + ReSukiSU built-in + SUSFS inline hook and SUSFS kernel patch.
- `all`: builds all three independently.

Test in that order on the device:

1. If `base` does not boot, stop. The failure is below ReSukiSU/SUSFS and the next comparison must be against the stock `boot.img` / stock Image and vendor-module KMI.
2. If `base` boots but `resukisu` does not, isolate ReSukiSU integration/config.
3. If `resukisu` boots but `resukisu-susfs` does not, isolate SUSFS patch/config.

Do not move to extra patches until variant C boots.

## CI guardrails

Before an artifact is uploaded, the workflow verifies the configuration embedded in the **actual built Image** using `scripts/extract-ikconfig`. It requires:

- ARM64
- Linux 6.12.23
- `android16-5`
- 4K page size
- KMI generation 5 source constants
- `CONFIG_MODVERSIONS=y`
- `CONFIG_GENDWARFKSYMS=y`
- `CONFIG_MODULE_SCMVERSION=y`
- KMI enforcement and strict symbol-list mode still enabled
- `CONFIG_KSU=y` for variants B/C
- ReSukiSU tracepoint hook for B
- `CONFIG_KSU_SUSFS=y` and required SUSFS options for C
- no patch reject files

This target does **not** remove `kmi_symbol_list_strict_mode`, protected exports, `check_defconfig`, or the standard module-versioning controls.

## AnyKernel3 behavior

The generated ZIP is intentionally boot-only and device-scoped:

- `do.devicecheck=1`
- only the selected codename is accepted
- `BLOCK=boot`
- `IS_SLOT_DEVICE=auto`
- `SLOT_SELECT=active`
- `PATCH_VBMETA_FLAG=0`
- `NO_VBMETA_PARTITION_PATCH=1`
- `split_boot`
- `flash_boot`

The package is created from a whitelist containing only `Image`, `anykernel.sh`, `META-INF/`, and `tools/`. CI rejects any packaged `boot.img`, `init_boot.img`, `vendor_boot.img`, `vendor_kernel_boot.img`, `dtbo.img`, or `vbmeta.img`.

On Android boot header v4 devices with a separate `init_boot`, `split_boot` / `flash_boot` lets AnyKernel3 replace the boot kernel payload without modifying the first-stage ramdisk.

## What is deliberately disabled in this lane

No NoMount, BBG, DroidSpaces, NTSync, extra ptrace patch, Unicode patch, networking extras, Re-Kernel, KPM, or other experimental feature is added.

The existing Generic GKI workflows remain unchanged.

## Data needed to identify the original bootloop conclusively

The workflow changes above make the experiment controlled, but they do not retroactively prove why an older Generic GKI ZIP bootlooped.

For an exact stock-versus-failed comparison, collect:

```sh
uname -a
uname -r
cat /proc/version
getprop ro.product.device
getprop ro.build.version.release
getprop ro.build.version.incremental
getprop ro.build.version.security_patch
getprop ro.boot.slot_suffix
getconf PAGESIZE
zcat /proc/config.gz > stock-config.txt 2>/dev/null || true
ls -la /sys/fs/pstore
cat /sys/fs/pstore/* 2>/dev/null
```

Most useful files to preserve/upload:

1. current stock `boot.img`
2. the previous non-booting AnyKernel3 ZIP or its `Image`
3. `vendor_boot.img` and `init_boot.img`
4. pstore/console-ramoops captured immediately after a failed boot

With those, compare the stock and failed Images by kernel release, embedded config, size/layout, KMI-related config, and early-boot/module-load errors instead of inferring the cause from `uname -r` alone.
