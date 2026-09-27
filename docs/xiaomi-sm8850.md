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

## Diagnostic variants

For either source profile:

- `base`: source only, no KernelSU and no SUSFS.
- `resukisu`: same source + ReSukiSU built-in using tracepoint hook.
- `resukisu-susfs`: same source + ReSukiSU built-in + strict SUSFS integration.
- `all`: builds all three independently.

Recommended first phone test:

1. `gold-cctv / base`
2. if it boots, `gold-cctv / resukisu`
3. if that boots, `gold-cctv / resukisu-susfs`
4. use `ack-r51 / base` as the clean-source control if needed

This ladder isolates source compatibility from ReSukiSU and SUSFS.

## Root and SUSFS pins

The diagnostic lane currently pins:

- ReSukiSU: `3c1882886dbbb54f4aae7ddf205f8ccde32c2a34`
- SUSFS `gki-android16-6.12`: `7d91da2d2ce056d1abf378d9199aaf1072d37ab0`
- AnyKernel3: `dca9dc370838d919d56c1f59ec78b27a14a72c68`

ReSukiSU is built in with `CONFIG_KSU=y`; no LKM mode is used.

SUSFS application is fail-fast: dry-run first, patch failure is fatal, and any `.rej` file fails the build. The Xiaomi lane does not use the generic `patch ... || true` behavior.

## CI guardrails

The final built Image must pass checks for:

- ARM64 / Linux 6.12.23 / `android16-5`
- 4K page size
- KMI generation 5
- `CONFIG_MODVERSIONS=y`
- `CONFIG_GENDWARFKSYMS=y`
- `CONFIG_MODULE_SCMVERSION=y`
- `CONFIG_CFI_CLANG=y`
- final LTO mode recorded from the built Image config
- source definition still contains `kmi_enforced = True`
- source definition still contains `kmi_symbol_list_strict_mode = True`
- source definition still contains `trim_nonlisted_kmi = True`
- runtime KMI enforcement applies to the `ack-r51` Kleaf control; `gold-cctv` intentionally builds only `Image` and does not request the system-DLKM module set
- exact pinned source commit
- exact pinned ReSukiSU/SUSFS commits when enabled
- no patch reject files

The generic workflow's ABI/KMI source edits are intentionally not inherited. The `gold-cctv` lane follows the source defconfig's own LTO choice, while `ack-r51` explicitly uses ThinLTO.

## AnyKernel3 behavior

The package is boot-only and device-scoped. It contains only `Image`, `anykernel.sh`, `META-INF/` and `tools/`.

It targets `boot`, auto-detects the active slot, disables vbmeta flag patching, and uses `split_boot; flash_boot;`. It does not package or flash `init_boot`, `vendor_boot`, `vendor_kernel_boot`, `dtbo` or `vbmeta`.

## Deliberately disabled for first boot

No NoMount, BBG, DroidSpaces, NTSync, extra ptrace patch, Unicode workaround, networking extras, Re-Kernel, KPM, ZRAM tweaks or unrelated CVE patch stack is added to this lane.

Those capabilities can continue to arrive from upstream on `dev`, but they should only be enabled for Xiaomi after the A/B/C compatibility ladder is proven stable.
