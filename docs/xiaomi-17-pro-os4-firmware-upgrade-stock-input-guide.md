# 小米 17 Pro（pandora）OS4 固件升级后的 stock input 操作指南

> **自动化更新（2026-11-01）**：只需在 OTA 后按本指南采集并替换固定 Release 的 `*-xm.zip`。新版 [OTA 自动识别与纯 GKI 候选基线工作流](../.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml) 已配置 Release 更新触发和每日补查：自动审计、比对固件版本、尝试解析官方 GKI 源码并生成**不能刷机**的研究候选。需要立即重试时仍可在 OTA 主工作流手动运行，但不是正常操作的必需步骤。详见 [自动化边界及人机验证门禁](xiaomi-17-pro-os4-ota-auto-baseline.md)。


> 适用设备：Xiaomi 17 Pro / `pandora`  
> 用途：HyperOS / OS4 升级后，为新的内核适配建立**可信、版本化、可追溯**的 boot 输入。  
> 原则：**先只读采集，后适配，再生成临时启动镜像。禁止直接把旧 fixture / 旧功能内核套到新固件。**

---

## 一、什么时候需要重新做这套流程

### 不需要重新提供 xm.zip

只要手机仍是**同一个 HyperOS build**，例如当前已经完成固化的：

```text
OS4.0.5.0.XBLCNXM
```

后续不管重新编译多少次 BakaSU / SUSFS / NoMount 内核，都不需要再次提供 `boot.img` 或 `xm.zip`。

### 需要重新做一次

只要系统升级到了新的 build，例如：

```text
OS4.0.5.0.XBLCNXM
        ↓
OS4.0.x.x.XBLCNXM
```

就必须重新建立一次 stock input。

原因是新固件可能改变：

- boot header；
- GKI 内核；
- KMI / Android GKI tag；
- vendor 模块；
- init_boot / vendor_boot / dtbo；
- boot 签名或其它启动元数据。

因此**不同固件 build 的 fixture 绝不跨版本复用**。

---

# 二、升级完成后先做什么

## 1. 先正常启动新固件

完成 OTA / 完整包升级后，先让手机**正常启动进入 Android 桌面一次**。

不要一升级完就先临时启动旧自定义内核。

需要确认：

- 系统可以正常进入桌面；
- 当前显示的 HyperOS / OS4 版本确实是新版本；
- 手机基本功能正常；
- 当前运行的是新固件自己的正常启动环境。

建议在 Windows platform-tools 中记录：

```cmd
adb shell getprop ro.product.device
adb shell getprop ro.mi.os.version.incremental
adb shell getprop ro.boot.slot_suffix
adb shell uname -r
```

小米 17 Pro 应至少满足：

```text
device = pandora
slot   = _a 或 _b
```

## 2. 确认 Root 已经恢复

自动采集脚本要读取 `/dev/block/by-name/*`，因此需要当前系统能执行：

```cmd
adb shell su -c id
```

应看到类似：

```text
uid=0(root)
```

如果新固件升级后 Root 暂时失效：

- 先处理新固件的 Root；
- 不要为了运行采集脚本去执行未知的 `fastboot flash`；
- 不要拿旧固件的自定义 boot 当作新固件 stock 输入。

> 注意：如果 Root 是通过修改 `init_boot` 获得的，那么脚本采集到的 `init_boot.img` 可能已经是 Root 修改后的版本。  
> **CI 的 stock-input 核心来源是 `boot.img`。** 其它分区镜像同时保存，主要用于记录和恢复参考，不能自动宣称为“纯净原厂镜像”。

---

# 三、Windows 端准备

需要：

1. Android Platform Tools；
2. 手机打开“USB 调试”；
3. USB 连接电脑；
4. 手机上允许当前电脑进行 USB 调试；
5. 当前系统有可用的 `su` Root。

仓库已经提供只读脚本：

```text
scripts/xiaomi-os4/collect-pandora-stock-input.cmd
```

建议把它放到 Windows 的 `platform-tools` 目录，例如：

```text
D:\platform-tools\
├─ adb.exe
├─ fastboot.exe
└─ collect-pandora-stock-input.cmd
```

---

# 四、运行只读采集脚本

## 1. 先确认 adb 正常

打开 CMD：

```cmd
cd /d D:\platform-tools
adb devices
```

应看到设备状态为：

```text
device
```

不能是：

```text
unauthorized
offline
```

## 2. 运行脚本

CMD：

```cmd
collect-pandora-stock-input.cmd
```

或者 PowerShell：

```powershell
.\collect-pandora-stock-input.cmd
```

脚本会自动：

1. 检查 `adb.exe`；
2. 检查 adb 连接；
3. 确认设备代号必须是 `pandora`；
4. 自动识别当前 slot：`_a` 或 `_b`；
5. 读取当前 OS build；
6. 读取当前 `uname -r`；
7. 检查 `su` Root；
8. **只读**读取当前活动 slot 的：
   - `boot`
   - `init_boot`
   - `vendor_boot`
   - `dtbo`
9. **只读采集当前挂载的 vendor_dlkm / vendor / odm_dlkm / system_dlkm 内核模块**，随 ZIP 提供 OEM CRC/KMI 实际校验输入；不可访问或没有 .ko 时停止并提示；
10. 自动计算四张镜像及模块压缩包的 SHA256；
11. 自动生成 `README.txt`；
12. 自动打成一个新的 `*-xm.zip`。

脚本明确不会执行：

```text
fastboot flash
fastboot erase
fastboot set_active
dd of=...
分区写入
slot 切换
```

---

# 五、脚本运行后会得到什么

假设新固件版本是 `OS4.x.x.x.XBLCNXM`，当前 slot 是 `_a`，目录中会出现类似：

```text
pandora-stock-OS4.x.x.x.XBLCNXM-_a\
├─ boot.img
├─ init_boot.img
├─ vendor_boot.img
├─ dtbo.img
├─ oem-modules.zip（新 OTA 必需）
├─ oem-modules-count.txt
├─ README.txt
└─ SHA256SUMS.txt

pandora-stock-OS4.x.x.x.XBLCNXM-_a-xm.zip
```

**真正需要上传的是最后这个 `*-xm.zip`。**

新版本需要使用**更新后的采集脚本**。旧版仅含分区的 xm.zip 不足以自动检查厂商模块 ABI/KMI，自动化会停在分析报告阶段，不会生成待测 boot。上传包含模块的新版 ZIP 可能比旧版本大，属于正常现象。

不要手工：

- 解压后只上传 `boot.img`；
- 把四张镜像分开上传；
- 修改里面的文件；
- 重新压缩成其它目录结构；
- 把旧版本和新版本同时放进一个 ZIP。

脚本生成的 ZIP 直接使用即可。

---

# 六、上传到哪里

固定 stock-input prerelease：

**https://github.com/wekingchen/GKI_KernelSU_SUSFS/releases/tag/pandora-os4-stock-input**

这个 Release 只用于**当前待适配固件的 stock 输入**，不是内核下载 Release。

## 上传前必须先处理旧 xm.zip

导入流程采用 fail-closed 设计：

> 固定 Release 中必须且只能存在 **1 个 `*xm.zip`**。

因此升级到新固件时：

1. 先在自己电脑上保留旧版本 `xm.zip` 备份；
2. 打开上面的 `pandora-os4-stock-input` prerelease；
3. 点击 **Edit release**；
4. 在 Assets / Attach binaries 区域删除旧固件的 `*xm.zip`；
5. 把刚刚新生成的：
   `pandora-stock-<新版本>-<slot>-xm.zip`
   拖进去上传；
6. 等上传完全结束；
7. 点击 **Update release**。

不要同时保留：

```text
旧版本-xm.zip
新版本-xm.zip
```

否则 Action 会主动失败，避免拿错版本。

---

# 七、上传后自动检查与构建候选（无需手动启动）

固定 Release 中的最新 `*-xm.zip` 更新后，现行主工作流是：

**[小米17 Pro OS4 / OTA 自动识别与非刷机 GKI 基线候选](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml)**

工作流监听 `pandora-os4-stock-input` 的 Release 发布/编辑事件，同时设有每日补查。**只替换已发布 Release 中的附件不保证触发 edited 事件**，因此不能承诺立刻开始，但无需你每天手动运行；紧急需要立即检查时，可在上述工作流点击 `Run workflow`（`dev`），不会重复执行已适配的版本。

自动步骤包括：

1. 校验固定 Release 中只有一个有效 `*xm.zip`，比对固件 build、boot 头、内核版本与 SHA；
2. 已适配同版本且 boot SHA 一致则结束，避免重复编译；
3. 发现新 OTA 后，从官方 GKI 目录寻找候选源码；锁定同一输入 SHA 与 commit，编译纯 GKI 候选；
4. 对新采集包里的厂商模块执行 vermagic 与导入符号 CRC/KMI 静态比对；
5. **只有所有已实现门禁通过时**才生成这次 OTA 专属的 `UNVERIFIED-FASTBOOT-BOOT-ONLY.img`；否则只保留诊断报告。

原来的独立工作流 `检查新固件 xm.zip（只读）` 已被此自动入口替代并移除。不再需要运行两套检查。

**不可误解为自动完成适配**：源码候选不等于 OEM 真实构建，静态 CRC 检查也不足以证明所有厂商驱动可用；待测包必须由你手动 `fastboot boot` 验证。禁止 `fastboot flash`、自动晋升 LKG 或跨系统版本复用旧 fixture。

---

# 八、把检查结果用于新固件适配

只读检查成功后，不要立刻运行旧的功能版 IMG 工作流。

新固件需要先判断：

1. `uname -r` 是否变化；
2. GKI 主版本 / KMI 是否变化；
3. 是否仍对应当前 R62；
4. stock boot header 是否变化；
5. OEM 模块是否需要重新审计；
6. 当前 BakaSU / SUSFS / NoMount pin 是否还能使用；
7. 是否要重新编译新的“无功能基线”。

因此新的标准顺序是：

```text
升级新固件
    ↓
正常开机 + 恢复 Root
    ↓
运行 collect-pandora-stock-input.cmd
    ↓
得到 *-xm.zip
    ↓
替换固定 Release 中旧 xm.zip
    ↓
OTA 主工作流自动识别和检查新固件 xm.zip
    ↓
根据报告做新固件适配
    ↓
编译新的无功能基线
    ↓
fastboot boot 真机验证新基线
    ↓
在 OTA 真机结果提交工作流填写 Run ID、SHA 和实际 uname
    ↓
GitHub 独立重打包验证并自动 PR 固化新版本 fixture
    ↓
开始新版本功能移植（旧 R62 LKG 不变）
    ↓
编译 BakaSU + SUSFS + NoMount
    ↓
生成新的 FASTBOOT-BOOT-ONLY.img
    ↓
再次 fastboot boot 真机验证
```

新的测试结果回报入口：[小米17 Pro OS4 / 提交 OTA 真机测试结果与固化基线](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml)。这是一个人工确认的单独 workflow，不会由 Release 更新自动认定为真机成功。

在 Run workflow（dev）里，按顺序填写 OTA 原工作流 Run ID、pass/fail、被测 IMG SHA256、实际系统 build 和 uname -r。pass 要勾选 Android 启动完成及 OEM 基础模块检查；fail 只保存 GitHub Issue。pass 还需通过同源 ZIP、Artifact、ABI 报告、重打包字节一致和 fixture 再现一致等门禁，才会自动创建并尝试合并仅含新版本 fixture 与验证记录的 PR。

通过后路径为 .github/config/ota-verified/<新 build>/fixture.json 和 verification.json。状态表示“已人工确认纯 GKI 基线启动，可进入新版本 BakaSU/SUSFS/NoMount 适配”，**不代表功能内核已经移植好，也不会更新 Gen 3 LKG 或自动刷入**。原 OS4 R62 自定义工作流仍是旧版本专用，需另行做新 OTA 功能适配。参见 [完整确认门禁](xiaomi-17-pro-os4-ota-auto-baseline.md)。

**不能把“上传了新 xm.zip”直接等价成“旧功能内核可以继续用”。**

---

# 九、只读检查之后怎么进入新版本适配

收尾后的仓库不再保留“一键导入 xm.zip 并固化 fixture”的旧实验工作流。

这是有意的：**新 OTA 的 stock boot、GKI 基线、ABI/KMI 和 boot-v4 布局必须先重新确认，不能让旧自动化直接把新固件推进到可启动/可刷阶段。**

只读检查完成后，按下面顺序处理：

1. 保存 `stock-intake` 报告；
2. 更新 `.github/config/pandora-os4-stock-input.env` 中的新 build 与 stock boot 身份；
3. 确认新的 GKI tag / commit / toolchain；
4. 先构建纯 baseline；
5. 只允许 `fastboot boot` 验证 baseline；
6. baseline 真机成功后，再用 `make-tested-boot-v4-fixture.py` 固化新版本 fixture；
7. 更新版本级 LKG 配置；
8. 才进入 Full Parity 功能恢复与 ABI/KMI 验证。

旧版本的 fixture、Image SHA、boot SHA 都不能直接复用。

---

# 十、当前 LKG 工作流只用于已验证版本

当前唯一正式 OS4 构建入口：

**小米17 Pro OS4 / Full Parity LKG 复现与打包**

地址：

**https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-lkg.yml**

它当前只针对：

```text
pandora
OS4.0.5.0.XBLCNXM
6.12.69 / android16-6 / R62
```

并使用固定的：

```text
.github/config/pandora-os4-full-parity-lkg.env
.github/config/pandora-os4-r62-tested-boot-v4-fixture.json
```

因此系统升级后，在这些版本级配置完成重新验证并更新之前，**不要运行它来给新系统生成内核包**。

当前版本下，该工作流会自行重建 baseline 和 Full Parity LKG，并用已验证 SHA 强校验，最终同时生成：

- `fastboot boot` 临时测试镜像；
- AnyKernel3 持久化包；
- Image / Module.symvers / final.config / 验证清单。

它不依赖历史 Actions Artifact，也不会自动刷写手机。

---
# 十一、常见问题

| 现象 | 含义 / 处理 |
|---|---|
| `adb.exe was not found` | 把脚本放进 platform-tools，或把 platform-tools 加入 PATH |
| `unauthorized` | 手机上重新允许 USB 调试授权 |
| `offline` | 重插 USB、重新启动 adb server |
| `su Root` 检查失败 | 新固件 Root 尚未恢复；先解决 Root |
| 输出目录已经存在 | 脚本故意不覆盖旧数据；确认后手工移动/删除旧目录 |
| 固定 Release 找到 0 个 xm.zip | 尚未上传 |
| 固定 Release 找到 2 个或更多 xm.zip | 删除旧资产，只留当前固件一个 |
| `xm.zip 中没有 boot*.img` | ZIP 不是本项目标准采集包或固件包结构异常 |
| stock boot SHA 不匹配 | 若是新固件，先更新版本适配配置；不要绕过 SHA |
| boot header 不是预期版本 | 新固件启动镜像格式可能变化，需要重新适配 |
| baseline boot SHA 不匹配 | 当前 baseline 不能证明与新固件等价，停止进入功能版 |
| 最终功能 IMG Action 失败 | 不要刷写；先排查 fixture / ABI / Image / cmdline 门禁 |

---

# 十二、当前 OS4.0.5.0 已完成到什么程度

当前 `OS4.0.5.0.XBLCNXM` 已完成一次完整 stock-input 闭环：

```text
xm.zip
  ↓
boot_OS4.0.5.0.XBLCNXM.img
  ↓
stock boot SHA256:
4f873abec68220c0028c11c8833e7ec8b9652f263e850f1ddb76d19913374653
  ↓
R62 #7 baseline Image
  ↓
真机成功 baseline temporary boot SHA256:
3faeffbb6a8fd4a56e81760e226da5e3822a4e282b5b65bcd168fcf77496c8e0
  ↓
版本化 fixture
  ↓
功能 #4 Image
  ↓
最终 FASTBOOT-BOOT-ONLY.img SHA256:
4cbb1b6f4087e3a275e266cc2776cd61637f4c6da3d7e46557e77d0df2d95660
```

因此当前这个 build **无需再次上传 xm.zip**。

---

## 最简记忆版

以后升级 OS4，只需要记住：

```text
1. 新固件正常开机
2. 恢复 Root
3. platform-tools 里运行 collect-pandora-stock-input.cmd
4. 得到新的 *-xm.zip
5. 固定 Release 删除旧 xm.zip，只上传新的一个
6. OTA 主工作流自动检查（Release 编辑事件 / 每日补查），必要时可手动重试同一工作流
7. 根据检查结果完成新版本适配和 baseline 真机测试
8. 再固化 fixture
9. 最后才生成新的功能版 FASTBOOT-BOOT-ONLY.img
10. 未验证前始终只 fastboot boot，不 fastboot flash
```

## 新 OTA 通过真机确认后自定义构建的默认版本

一旦新 OTA 的真机验证结果通过 GitHub 全部安全门禁并自动合并开发基线指针 .github/config/ota-development-current.json，现有「小米17 Pro OS4 / 自定义内核」默认切换到这个新固件的 GKI 源码和对应 fixture，而不是编译旧 R62。

只有上传了新 xm.zip 但还没提交成功的真机测试时，会阻止旧版内核回退；新 GKI 上功能补丁或 OEM ABI 比较失败时，也不会输出冒充新版本的文件。

新版本功能编译通过 ABI/KMI 等门禁后，**同一次构建同时输出 fastboot boot 待测 IMG 和实验性 UNVERIFIED AnyKernel3.zip**，无需再提交第二次测试结果才能拿到安装包。可先 fastboot boot 测试；请注意 AnyKernel3 会持久替换活动 boot 的内核，功能版未经真机验证前存在无法开机风险。以后仅正式晋升 LKG 才需你另外明确确认，Gen 3 LKG 和旧 fixture 一直独立保留。
