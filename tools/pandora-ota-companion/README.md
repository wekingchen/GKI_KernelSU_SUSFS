# 小米 17 Pro / HyperOS 4 — 手机 OTA 采集助手

> Android APK 0.12.0-dev（真机测试反馈表单）｜代码整合进 `dev` 后长期维护｜不刷机、不自动晋升 LKG。
> **已在 pandora OS4 真机验证 Root、采集、GitHub 上传和服务端身份审计；**同版本自定义 Boot 被安全拦截。新 OTA 成功切换仍待实物。

## 0.12.0 真机测试反馈

工作台「真机测试反馈 → 填写测试结果」直接填写原「提交 OTA 真机测试结果与固化基线」工作流，无需网页填表，也无需测试前登记任务。电脑负责 `fastboot boot`，在手机手动测试功能后打开 App 提交；App 没有 fastboot、flash、重启或分区写入能力。

1. 在设置为目标仓库 PAT 增加 **Actions: Read and write**（原 Contents 读写保留）。原采集/上传功能仅需 Contents 读写，不因新增反馈功能被强制升级权限。
2. 选择实际测试的候选，或输入来源 Run ID 后「读取候选信息」。新候选额外生成独立小型 `pandora-OTA-MOBILE-FEEDBACK-*` 附件，App 核对 Run、commit、build 和文件身份后预填 SHA-256；不下载完整 boot。旧候选没有该附件时必须手动填写电脑实际测试 IMG 的 SHA-256。
3. 打开反馈页会自动读取五项本机信息，也可点击重新读取：`getprop ro.product.device`、`getprop ro.mi.os.version.incremental`、`getprop sys.boot_completed`、`uname -r`、`/proc/modules`。前四项不依赖 Root；模块列表普通权限受限时仅尝试 `su -c cat /proc/modules`，失败显示未取得。不会把读取失败当成模块正常。
4. 选择通过/失败，确认实际测试镜像一致；人工确认已进桌面、关键模块和基础功能正常，填写备注，再核对摘要并提交。自动读数不自动勾选人工项。模块完整文本和采证时间保存在手机表单草稿，用于展开核对；原工作流仍按既有字段接收模块/功能确认，不宣称模块全文已上传。
5. 若待测无法开机、恢复后才进入 App，选择「待测启动失败，未能进入系统；现已恢复」。只允许失败反馈，build/uname 留空，启动/模块确认强制 false；当前读数标为恢复后环境，避免混淆。
6. App 对原工作流执行 `workflow_dispatch`，固定 `ref=dev`。新增可选 `client_request_id` 和运行标题仅用于精确定位本次反馈；网页手动入口保持兼容，服务端原来源/IMG/ABI/同 OTA 复现/人工确认门禁不削弱。成功仍只固化开发基线，不修改 LKG。
7. 本地先保存反馈编号再发请求。恢复页面不重发请求；网络响应未确认时先查询是否已受理，避免因超时自动重复触发。两分钟仍未建立运行记录时可手动重发同一编号及内容；服务端在任何 Issue/基线变更前阻止重复编号，App 跟踪最早的原始运行。前台自动显示等待、执行、完成或失败；后台暂停查询，返回继续。每次终态保留历史，最多 20 条。

`build + uname + boot_completed=1` 不构成指定 IMG 已启动的硬件证明，仍需用户确认电脑实际使用的镜像；绝不以磁盘 boot 分区 SHA-256 冒充 `fastboot boot` 的临时镜像 SHA-256。新功能经模拟器和合成契约验证，不替代新 OTA 实物真机测试。

## 0.11.0 新增功能

- **真实采集目录空间**：按 `captures` 所在文件系统的可用字节预检；小于 1 GiB 禁止采集，1 GiB 至不足 2 GiB 提醒后可继续，达到 2 GiB 正常继续。真正读取分区前再次检查，空间变化不会绕过硬门禁。
- **GitHub 实时权限**：设置页可单独验证；每次采集和上传前也重新验证。先读取目标仓库，再创建独有的空 Draft、读回核验并删除它，最后发送无人订阅的 `pandora_ota_preflight_v1` 通知探针。该探针不含采集数据、不执行 OTA 接收；不能以公开仓库可读或 `permissions.push=true` 代替 PAT 的实际写权限。清理失败会阻止继续并显示草稿 ID，供人工清理。
- **新系统身份提醒**：首次使用及 OS build / fingerprint 变化时提醒离线保存同版本原始 `init_boot.img`；「已了解」只记录读过说明，不宣称文件已经备份。「稍后提醒」在下次打开时再次提醒。
- **前台自动接收跟踪**：针对当前上传回执持续查询 `PENDING → ACCEPTED / ALREADY_CURRENT / REJECTED`；间隔从 5 秒退避到最多 60 秒。退出前台暂停、返回或重开恢复；网络失败保留回执和本地 ZIP，自动重试。切换仓库/采集包后丢弃旧查询结果，终态停止。通知失败时先重新通知，无需重传文件。
- **固定签名为必过项**：APK 工作流缺少签名 Secrets 时直接失败，不再以只有 Debug APK 的结果冒充完整发布验证。

既有真机验证属于 0.10.x 基线；0.11.0 新增逻辑须以对应 APK、固定签名和模拟器/契约运行记录为准，新 OTA 实物的完整接收链仍待实际 OTA。

## 操作流程

1. 下载 `STABLE-SIGNED` 长期签名 APK，直接覆盖安装。首次打开在「设置」填入 GitHub 仓库/PAT；然后在 Root 管理器中为本应用手动授予超级用户权限。
2. 「设置」中 GitHub 接收仓库填入 `wekingchen/GKI_KernelSU_SUSFS` 与 fine-grained PAT（**仅该仓库**、Contents: Read and write），可按 GitHub 提供的期限长期有效；AES-GCM/Android Keystore 加密存储，可主动清除。
3. 回到「工作台」，点击「检查 Root 权限」，随后「开始采集」：强制读取设备代码、OS build、uname、活动 slot、OEM 内核模块以及 `boot/init_boot/vendor_boot/dtbo`，所有读取均只读。**当前分区不等于可信厂商原版**，Root/LKM/自定义内核也可能改变内容。
4. 上传：APK 将包送到仅管理员可见的 **Draft Release**，显示写入进度、大小、速度和时间。只有 GitHub 返回 **HTTP 201 且附件大小一致** 才记成功并留有回执。
5. **只要 ZIP 打包完成，手机立即清理分区镜像、OEM TAR 等所有中间采集物和 staging 目录，只留下最终 ZIP。采集或压缩出错则同时删除残缺 ZIP 并尝试清理 staging；上次意外终止遗留的 staging 在下次采集时自动回收（保留 30 分钟宽限以避开正在执行的采集）。**
6. 到「记录」查看本地 ZIP 和 GitHub 回执：本地清理必须等到 **GitHub 已确认上传、工作流通知已成功发送，且后端状态进入 ACCEPTED / ALREADY_CURRENT / REJECTED 之一**；REJECTED 仍允许清理，但 PENDING 或通知失败时必须先保留 ZIP，以便重试和继续查询。删除前重新在线验证 Draft Release、附件 ID/大小/远端 SHA-256，再核验本地 SHA-256。多个历史 ZIP 可切换，上传失败和安全拒收绝不自动删除；远端附件不得因本地清理被删除。
7. 上传并不等于接收成功：发送 `repository_dispatch` 后在 App 前台自动轮询后端接收结果，也可手动查询；服务端以 Asset ID 与 SHA-256 绑定的 Draft Release 回执区分 ACCEPTED / ALREADY_CURRENT / REJECTED / PENDING。**无论是否通过 OTA 身份审计，只要远端完整附件得到再次确认，就允许用户主动手动清理本地 ZIP**。
8. 通知请求失败可直接核对远端附件并重新发送，不重复上传整个 ZIP。

上传阶段请保持 App 前台及网络稳定，目前**不支持断点续传**，也不提供后台 Foreground Service。单个采集文件须小于 950 MiB。

## 全链功能审计结论（0.10.4-dev）

当前主链已经闭环到：**新 OTA → 同版本 init_boot 获取 Root → App 只读采集 → 本地 ZIP → GitHub Draft → 手机接收入库 → 固定 stock-input → GKI 候选 → OEM ABI/KMI → 条件生成 fastboot boot → 人工真机验证 → verified fixture → 自定义功能适配 → 人工晋升 LKG → 长期归档**。

本轮已补齐两项采集前身份可见性：工作台直接显示当前 HyperOS 完整 build；设置页「采集设置」直接显示当前活动 slot A/B。历史采集包也显示自身 build/slot，上传前必须与当前手机一致。

本轮审计额外发现并修复了一个安全缺口：旧逻辑只要 `build != pinned` 就可能进入 `NEW_OTA_CANDIDATE`。现在客户端先阻止旧 build/旧 slot ZIP；服务端先做静态 legacy 基线审计，再以 GitHub **当前固定 stock-input Release** 的实际 build 作为最终单调向前门禁。比当前固定输入更旧的历史 OTA、同版本不同规范化字节、或固件渠道变化都不能自动替换。

仍待后续补强、但不阻断现有主链的能力：

- **后端进度可见性**：App 当前只显示手机 intake 的 PENDING / ACCEPTED / ALREADY_CURRENT / REJECTED，还不能继续显示 GKI 候选构建、ABI/KMI、待测 fastboot boot、真机验证状态。
- **远端 Draft 生命周期**：本地 ZIP 只有在通知成功且 intake 已到终态后才允许严格安全删除；远端采集 Draft 为保留证据暂不自动删，后续可在候选/验证证据已归档后提供人工清理。

明确属于安全边界、**不是缺失功能**：App 不刷机、不切 slot、不自动晋升 LKG、不把 Root 后 init_boot 冒充 OEM 原版、不因后端 ACCEPTED/REJECTED 自动删除本地证据，也不承诺后台断点续传。

## OTA 后恢复 Root 的固定操作顺序（用户真机操作决策）

1. 新 HyperOS OTA 升级成功，核对 **pandora / OS build / 内核 / 当前 slot**。
2. **先保存此次新 OTA 未修补的原始 `init_boot.img`**（离线保留来源、版本及 SHA-256），再用对应版本的 `init_boot` 修补 Root；绝不使用上一版修补镜像，或以 Root 后的活动分区备份冒充 OEM 原版。
3. 手机正常启动并确认 `uid=0`；在 Root 管理器**手动授予本 App**超级用户权限（曾实测未授权时会报 `su: error=13, Permission denied`）。
4. 由 OTA 助手只读采集活动分区镜像和 OEM 模块，上传 GitHub Draft Release，触发身份审计与不可刷候选；先验证，再决定是否晋升 LKG。
5. 本机留存的**原始 `init_boot.img` 不需要放进 App 上传的 ZIP**，也不需要为了采集先撤销 Root。

**重要分区区分：** `boot.img` 与 OEM `.ko` 是 GKI 内核/KMI/ABI 分析主输入，前提是 `boot` 未被另外刷成自定义内核（仅修补 `init_boot` 并不足以证明 `boot` 原厂）。App 采集的 `init_boot.img` 是**Root 后活动快照，可能已经修补，只用于诊断，不能当 OEM 原厂镜像或恢复文件**；`vendor_boot` / `dtbo` 同样是活动快照。现有八文件 ZIP 契约暂时保留这张快照，但会在清单、README 和 CI 审计中强制标注非原版身份。

完整、以手机 App 为首选的 OTA 操作步骤和回退原则参见 [小米 17 Pro OS4 OTA 升级指南](../../docs/xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)。

## 服务端与现有 OTA 流程的兼容性

- APP 上传的 `pandora-ota-capture-v1` 包含活动 slot 的分区快照、`oem-modules.tar` 及身份清单。
- `normalize_mobile_capture.py` 严格校验清单、slot、uname、目录、大小和内核模块数量，转换成当前 Windows `collect-pandora-stock-input.cmd` 的同款 **八文件 `*xm.zip`**，并加上 `boot_oem_original_verified=NO`、`init_boot_oem_original_verified=NO` 和 `init_boot_role=DIAGNOSTIC_ONLY_NOT_FACTORY_IMAGE` 等明确来源标签；不会因内核版本标记匹配便认定镜像出厂原版。
- `mobile-intake.sh` 仅接受对应 Draft Release 的特定 Asset ID、实际文件长度与 SHA-256 一致的输入；转换后还执行原 `inspect-ota-stock-input.py` 身份审计。旧固定 Release 不会因为无效上传被覆盖。
- App 上传前会重新读取本地采集包 manifest，并强制其 OS build / 活动 slot 与当前手机一致；服务端最终以 GitHub 当前固定 stock-input Release 内的 build 为版本基准，仅允许同渠道严格向前替换。静态 `pandora-os4-stock-input.env` 只承担最初 legacy OS4 基线身份，不再被误当成永久“当前版本”。
- 验证通过的新 OTA 先上传到固定 Release 的非 `*xm.zip` 暂存名并从 GitHub 下载回检，再更名、替换旧单一 `xm.zip`，最后触发原 `xiaomi-sm8850-os4-ota-auto-candidate.yml`。
- **`repository_dispatch` 从仓库默认分支执行。** 目前接收工作流及转换脚本已在默认 `dev` 上部署；真机采集包已成功触发并执行审计，但因同版本自定义 Boot 与固定基线不同而安全拒收。
- 原 GKI/KMI/OEM ABI 门禁、临时 `fastboot boot` 真机确认、LKG 人工晋升不变。不直接产生可刷内核或跳过风控。

## 编译、测试与签名

APK 自用工程目录：`tools/pandora-ota-companion/`，JDK 17 / Android SDK 35 / Gradle 8.11.1。

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
bash -n mobile-intake.sh
gradle --no-daemon :app:assembleDebug
```

独立 Action：`.github/workflows/pandora-os4-ota-companion-apk.yml`。

实验 APK：`pandora-os4-ota-companion-UNVERIFIED` Artifact。GitHub Runner 的 Debug 签名不能保证每轮相同，**不保证直接覆盖安装并保留旧数据**。

**独立长期签名已生成**：PKCS#12 签名证书有效期 100 年（至 2126-10-08），公钥证书 SHA-256 指纹 `6A:46:5B:38:EA:AD:AC:A9:0F:91:86:63:4F:41:6A:16:C0:3E:EE:F6:05:68:13:E5:AE:90:6C:0A:EC:AB:73:2F`。私钥不可提交到公开仓库。已有独立私密备份包，其中可包含一键配置脚本。

长期稳定升级需要在仓库配置 4 个 GitHub Actions Repository secrets（也可在 Windows 安装 GitHub CLI、`gh auth login` 后，解压私密签名备份并执行 `setup-long-term-signing.ps1` 一键配置）：

| Secret 名称 | 值 |
| --- | --- |
| `PANDORA_OTA_SIGNING_KEYSTORE_B64` | 私密 `p12` 签名密钥文件的 Base64 文本 |
| `PANDORA_OTA_STORE_PASSWORD` | 签名密钥库密码 |
| `PANDORA_OTA_KEY_ALIAS` | 密钥别名 |
| `PANDORA_OTA_KEY_PASSWORD` | 密钥密码 |

设置后分支工作流自动额外输出 `pandora-os4-ota-companion-STABLE-SIGNED` 的正式签名 Release APK。**私钥/密码不要上传仓库、日志、Release、Artifact。** 预先保管签名私钥和密码的离线备份；签名不同的 Debug APK 不能直接覆盖稳定版。

## 当前原生 UI 与功能状态（0.10.4-dev）

- 原生 Android Activity 顶部信息区、固定状态条与底部三目的地导航：**工作台 / 记录 / 设置**。不采用 WebView 或 HTML。
- 工作台显示当前 HyperOS 完整版本号，并保留设备身份、Root 检测、只读采集、GitHub 上传与真实传输进度。
- 记录页集中管理本地 ZIP 列表、历史回执、接收状态查询、通知重试和安全删除。
- 设置页保管 GitHub 仓库与加密 PAT；「采集设置」直接显示当前活动 slot A/B；升级保持相同包名与固定签名，不清除应用数据。
- 设置 → 关于新增原生「使用指南」：以当前 OS/slot 为起点，用 5 步时间线说明新 OTA 准备、只读采集、GitHub Draft 审计、GKI/OEM ABI/KMI 候选、fastboot boot 真机确认与 LKG 晋升；同时明确原始 init_boot 离线保留、Draft 不发布、待测 boot 不 flash。
- 触控按钮具有 Android Ripple、短缩放与触控震动；长操作在顶部显示即时任务状态，上传使用实际字节进度，不伪造采集百分比。
- UI 重构不改动 RootCollector、GitHubUploader 接收协议、ZIP 内容、SHA-256、原厂 Boot 比对或 LKG 门禁。

## 已验证 / 待新 OTA 验证

- ✅ OS4.0.5.0 真机设备识别、Root `uid=0`、四个活动启动分区 + OEM 模块采集；本地 ZIP 85.43 MiB。
- ✅ GitHub Draft Release #430401431、附件 #697520792 上传成功；Run #41280701707 第三次重跑通过 ZIP SHA-256、OEM 模块格式转换及原 OTA 身份审计。
- ✅ 同版本自定义内核 `6.12.69-android16-6-os4r62-custom-4k` 与固定 Boot 不一致，被 `SAME_BUILD_BOOT_DRIFT_REVIEW` 安全拒收，固定 `xm.zip` 和 LKG 保持不变。
- ✅ 修复的 OEM TAR 链接处理、Draft 重试机制在 Python/CI 回归中通过。
- ✅ 原生三页 UI 已在 Xiaomi 17 Pro 真机完成定版；Android 15 模拟器设备端回归、正式固定签名 APK 与签名指纹校验持续作为 PR/`dev` 门禁。
- ⏳ **真正新 OTA** 的自动成功入库、候选 GKI 构建与 OEM ABI/KMI 全链路尚需实际新固件验证。
- ✅ **本地 ZIP 手动安全删除、GitHub 草稿附件查看**均已由用户真机确认；通过远端 ID/大小/SHA-256 和本地 SHA-256 校验后删除本地文件，不影响云端附件。
- ⚠️ Root 设备抓取的 boot 属于活动快照，不保证厂商原始完整性；Root 后 `init_boot` 明确标记非原厂可信输入。

## 真机 Root 联调诊断（0.6.1-dev）

- 应用 02 区显示 `Build.DEVICE` 与 `Build.PRODUCT`，Root 检测按钮始终可用；**分区采集按钮依然严格要求 pandora**。
- Root 命令 `su -c id` 最多等待 45 秒，成功、拒绝、超时均在检测按钮下面即时显示；不再只在页面底部输出结果。
- `adb shell su -c id` 的授权主体是 ADB shell，**不等于**本应用被授予 Root；请在 ReSukiSU/BakaSU 的「超级用户」中独立核对 `com.wekingchen.pandoraota`。
- 如果出现「等待 Root 授权超时」，先检查管理器对本应用的授权，不要删除数据重装，否则加密存储的 PAT 可能丢失。

## 0.7.2-dev 本地空间清理安全修复

- OTA 安全拒收（如同版本自定义 Boot 漂移）**不等于 GitHub 上传失败**，也不应阻止用户手动清理自己的本地 ZIP。
- 「记录」页只有存在 GitHub 上传回执且有已保存 PAT 时开放清理。先明确提示删除本地副本无法恢复；后台再次读取对应 Draft Release 并核验附件 ID、名称、字节大小、上传状态、SHA-256，再次核验本地文件 SHA-256 后才执行删除。
- 远端不存在、被修改、网络错误或 SHA 不符时，**禁止删除**；不会删除远端 Draft Release，也不会修改原有 OTA 固定输入或 LKG。
- 校验采用独立 HTTP GET，不会改变已验证的采集/上传/后端门禁。

## GitHub Actions 直接下载 APK（无需解压 ZIP）

- 正式签名版本在 `OTA 采集助手 APK` 工作流的 **Artifacts** 中以 `pandora-ota-companion-STABLE-SIGNED.apk` 单文件原样发布，手机上点击该项即可下载 APK；采用 `actions/upload-artifact@v7` 与 `archive: false`。
- 仅在 **Release APK 编译成功、固定 SHA-256 签名指纹及 APK v2 签名验证通过** 后上传。没有配置四项长期签名 Secrets 时不产生正式签名 APK。
- `UNVERIFIED` Debug 仍为传统 ZIP，仅用于开发验证，不建议真机长期安装。
- 旧的 GitHub Actions 历史 Artifacts 仍然是 ZIP；请使用更新工作流后的新一次运行。
- 下载的正式 APK 仍是既有包名与长期签名，可以直接覆盖安装，保留已加密 PAT 与历史采集回执。Artifacts 按工作流保留策略自动过期，若需要永久分发应再单独设计 Release 渠道。

## v0.7.2-dev：GitHub 草稿采集附件 404 修复

- 对于安全原因始终不公开发布的手机采集 Draft Release，GitHub API 返回的 `html_url` 形如 `/releases/tag/untagged-*`，直接打开会 404；它**不表示附件已丢失**。
- 记录页「在 GitHub 查看草稿附件」点击时用本机保存的加密 PAT 向 GitHub **只读 GET** 最新 Release，核验 Release ID、草稿状态、专用名称、附件 ID、文件名、大小和 SHA-256，然后将其 GitHub 草稿 URL 转为 `/releases/edit/<draft-tag>` 打开。旧上传回执可直接使用，无需重新上传。
- 浏览器需登录具有目标仓库写权限的 GitHub 账号。草稿只能查看和管理，**严禁直接 Publish release**，否则可能公开未经验证的 Boot 和 OEM 文件。
- 不使用 PAT 作为浏览器 URL 参数、不更改 OTA 接收协议、LKG、ZIP、Root 权限和任何 GitHub Release 数据。错误或远端已删除时不打开伪造/失效页面。
