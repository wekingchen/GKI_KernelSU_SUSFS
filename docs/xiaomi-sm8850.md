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

### Validation levels

Do not conflate these states:

1. **CI integration validated** — patch/config integration, kernel compilation and final validation pass.
2. **Physical boot validated** — the resulting AnyKernel package boots on the Xiaomi 17 Pro.
3. **Feature behavior validated** — the individual feature has been exercised on-device and its runtime behavior confirmed.

Run #74 proved the optional features individually at level 1. Runs #75/#76 proved the combined full profile at level 1. Run #76 has currently reached level 2 plus a short basic-use sanity check. The optional features still need individual runtime checks before they are described as fully device-validated.

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

The #76 full image has passed boot and initial basic-use checks on `pandora`. The next stage is runtime verification of the optional features, preferably without changing the kernel between checks:

- confirm ZRAM backend/compression behavior
- confirm BBG is initialized and its interface/logging behaves normally
- confirm Re-Kernel runtime interface
- confirm NoMount runtime state
- confirm DroidSpaces and NTSync behavior
- confirm networking additions are present without regressions

Only after those checks should the full optional stack be labeled fully validated on `pandora`. `pudding` and `popsicle` remain same-platform build targets but are not yet physically validated.
