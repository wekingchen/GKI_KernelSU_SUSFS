# 小米 17 Pro（pandora）OS4 固件升级后的 stock input 操作指南

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
9. 自动计算四张镜像的 SHA256；
10. 自动生成 `README.txt`；
11. 自动打成一个新的 `*-xm.zip`。

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
├─ README.txt
└─ SHA256SUMS.txt

pandora-stock-OS4.x.x.x.XBLCNXM-_a-xm.zip
```

**真正需要上传的是最后这个 `*-xm.zip`。**

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

# 七、上传完后先跑“只读检查”，不要直接生成内核

新固件上传后，第一步运行：

## 工作流

**小米17 Pro OS4 / 检查新固件 xm.zip（只读）**

地址：

**https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-stock-intake.yml**

操作：

1. 打开仓库 **Actions**；
2. 左侧选择：
   **小米17 Pro OS4 / 检查新固件 xm.zip（只读）**；
3. 点击 **Run workflow**；
4. 使用默认分支 `dev`；
5. 点击绿色 **Run workflow**。

这个工作流只会：

- 下载固定 Release 中唯一的 `*xm.zip`；
- 列出 ZIP 内容；
- 自动找到唯一的 `boot*.img`；
- 计算：
  - boot SHA256
  - 4KB header SHA256
  - kernel SHA256
  - kernel size
  - boot header version
  - header size
  - ramdisk size
  - signature size
- 尝试读取 ZIP 中的 `README.txt`：
  - device
  - build
  - uname
  - slot
- 输出检查报告 Artifact。

它**不会**：

- 修改仓库；
- 更新 fixture；
- 修改手机；
- 生成可刷镜像；
- 自动认为旧内核兼容新固件。

### 正常结果

工作流应该是：

```text
SUCCESS
```

并在 Summary 里看到新固件的 boot / kernel 信息。

如果只是新固件 SHA 与旧配置不同，这本身并不是故障；新固件本来就应该重新建立版本门禁。

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
运行“检查新固件 xm.zip（只读）”
    ↓
根据报告做新固件适配
    ↓
编译新的无功能基线
    ↓
fastboot boot 真机验证新基线
    ↓
更新 stock-input 版本配置
    ↓
固化新版本 fixture
    ↓
编译 BakaSU + SUSFS + NoMount
    ↓
生成新的 FASTBOOT-BOOT-ONLY.img
    ↓
再次 fastboot boot 真机验证
```

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
6. 先跑“检查新固件 xm.zip（只读）”
7. 根据检查结果完成新版本适配和 baseline 真机测试
8. 再固化 fixture
9. 最后才生成新的功能版 FASTBOOT-BOOT-ONLY.img
10. 未验证前始终只 fastboot boot，不 fastboot flash
```
