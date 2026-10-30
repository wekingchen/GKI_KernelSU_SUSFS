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
4. 分支选择当前 OS4 适配分支；
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

# 九、什么时候运行“导入 xm.zip 并固化 boot-v4 模板”

只有在新固件的基线内核已经确定、并完成必要适配之后，才运行：

**小米17 Pro OS4 / 导入 xm.zip 并固化 boot-v4 模板**

地址：

**https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-stock-input.yml**

在运行之前，仓库中的：

```text
.github/config/pandora-os4-stock-input.env
```

必须已经更新到**新固件**的：

- build；
- stock boot SHA256；
- 已确认 baseline Image SHA256；
- 已真机成功 baseline temporary boot SHA256。

如果还是旧版本参数，导入工作流应该失败。

这是故意的安全门禁，不应该通过删校验、放宽 SHA 或“先跑起来再说”绕过。

成功后会完成：

1. 新 `xm.zip` 的 stock boot 校验；
2. 用新 baseline Image 重建临时 boot；
3. 必须与新版本已经真机成功的 baseline boot 精确匹配；
4. 生成版本化 boot-v4 fixture；
5. 写入：
   - stock build
   - stock boot SHA
   - stock header SHA
   - stock kernel SHA
   - tested baseline boot SHA
   - baseline kernel SHA
   - `safe_to_flash=false`
6. 提交 fixture 到 OS4 适配分支。

---

# 十、之后才生成新的功能版 IMG

fixture 固化后，再进入：

**小米17 Pro OS4 / R62 功能内核临时启动镜像（直接下载）**

当前工作流：

**https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/workflows/xiaomi-sm8850-os4-feature-fastboot-image.yml**

它最终应该输出：

```text
FASTBOOT-BOOT-ONLY-pandora-OS4-...
```

下载并校验 SHA256 后，只允许：

```cmd
fastboot boot xxx-FASTBOOT-BOOT-ONLY.img
```

仍然禁止：

```cmd
fastboot flash boot ...
```

直到新功能内核经过真机验证并明确改变 `safe_to_flash` 状态。

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
