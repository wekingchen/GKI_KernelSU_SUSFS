# 小米 17 Pro / HyperOS 4 — 手机 OTA 采集助手

> Android APK 0.7.1-dev（原生 UI 2.0）｜代码整合进 `dev` 后长期维护｜不刷机、不自动晋升 LKG。
> **已在 pandora OS4 真机验证 Root、采集、GitHub 上传和服务端身份审计；**同版本自定义 Boot 被安全拦截。新 OTA 成功切换仍待实物。

## 操作流程

1. 下载 `STABLE-SIGNED` 长期签名 APK，直接覆盖安装。首次打开在「设置」填入 GitHub 仓库/PAT；然后在 Root 管理器中为本应用手动授予超级用户权限。
2. 「设置」中 GitHub 接收仓库填入 `wekingchen/GKI_KernelSU_SUSFS` 与 fine-grained PAT（**仅该仓库**、Contents: Read and write），可按 GitHub 提供的期限长期有效；AES-GCM/Android Keystore 加密存储，可主动清除。
3. 回到「工作台」，点击「检查 Root 权限」，随后「采集并生成 ZIP」：强制读取设备代码、OS build、uname、活动 slot、OEM 内核模块以及 `boot/init_boot/vendor_boot/dtbo`，所有读取均只读。**当前分区不等于可信厂商原版**，Root/LKM/自定义内核也可能改变内容。
4. 上传：APK 将包送到仅管理员可见的 **Draft Release**，显示写入进度、大小、速度和时间。只有 GitHub 返回 **HTTP 201 且附件大小一致** 才记成功并留有回执。
5. **只要 ZIP 打包完成，手机立即清理分区镜像、OEM TAR 等所有中间采集物和 staging 目录，只留下最终 ZIP。采集或压缩出错则同时删除残缺 ZIP 并尝试清理 staging；上次意外终止遗留的 staging 在下次采集时自动回收（保留 30 分钟宽限以避开正在执行的采集）。**
6. 到「记录」查看本地 ZIP 和 GitHub 回执：只要 GitHub **已确认上传并仍保留完整附件**，就可以手动删除本地 ZIP，即便 OTA 身份审计返回 REJECTED；删除前重新在线验证 Draft Release、附件 ID/大小/远端 SHA-256，再核验本地 SHA-256。多个历史 ZIP 可切换，上传失败和安全拒收绝不自动删除；远端附件不得因本地清理被删除。
7. 上传并不等于接收成功：发送 `repository_dispatch` 后可在 APP 中查询后端接收结果；服务端以 Asset ID 与 SHA-256 绑定的 Draft Release 回执区分 ACCEPTED / ALREADY_CURRENT / REJECTED / PENDING。仅在接收已确认后开放最终 ZIP 手动清理。
8. 通知请求失败可直接核对远端附件并重新发送，不重复上传整个 ZIP。

上传阶段请保持 App 前台及网络稳定，目前**不支持断点续传**，也不提供后台 Foreground Service。单个采集文件须小于 950 MiB。

## 服务端与现有 OTA 流程的兼容性

- APP 上传的 `pandora-ota-capture-v1` 包含活动 slot 的分区快照、`oem-modules.tar` 及身份清单。
- `normalize_mobile_capture.py` 严格校验清单、slot、uname、目录、大小和内核模块数量，转换成当前 Windows `collect-pandora-stock-input.cmd` 的同款 **八文件 `*xm.zip`**。
- `mobile-intake.sh` 仅接受对应 Draft Release 的特定 Asset ID、实际文件长度与 SHA-256 一致的输入；转换后还执行原 `inspect-ota-stock-input.py` 身份审计。旧固定 Release 不会因为无效上传被覆盖。
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

## 界面 UI 2.0（0.7.1-dev）

- 原生 Android Activity 顶部信息区、固定状态条与底部三目的地导航：**工作台 / 记录 / 设置**。不采用 WebView 或 HTML。
- 工作台只保留设备身份、Root 检测、只读采集、GitHub 上传与真实传输进度。
- 记录页集中管理本地 ZIP 列表、历史回执、接收状态查询、通知重试和安全删除。
- 设置页保管 GitHub 仓库与加密 PAT；升级保持相同包名与固定签名，不清除应用数据。
- 触控按钮具有 Android Ripple、短缩放与触控震动；长操作在顶部显示即时任务状态，上传使用实际字节进度，不伪造采集百分比。
- UI 重构不改动 RootCollector、GitHubUploader 接收协议、ZIP 内容、SHA-256、原厂 Boot 比对或 LKG 门禁。

## 已验证 / 待新 OTA 验证

- ✅ OS4.0.5.0 真机设备识别、Root `uid=0`、四个活动启动分区 + OEM 模块采集；本地 ZIP 85.43 MiB。
- ✅ GitHub Draft Release #430401431、附件 #697520792 上传成功；Run #41280701707 第三次重跑通过 ZIP SHA-256、OEM 模块格式转换及原 OTA 身份审计。
- ✅ 同版本自定义内核 `6.12.69-android16-6-os4r62-custom-4k` 与固定 Boot 不一致，被 `SAME_BUILD_BOOT_DRIFT_REVIEW` 安全拒收，固定 `xm.zip` 和 LKG 保持不变。
- ✅ 修复的 OEM TAR 链接处理、Draft 重试机制在 Python/CI 回归中通过。
- ✅ 原生 UI 2.0 Android 15 模拟器 14 项测试、正式固定签名 APK 构建通过；视觉和触感仍需要用户真机确认。
- ⏳ **真正新 OTA** 的自动成功入库、候选 GKI 构建与 OEM ABI/KMI 全链路尚需实际新固件验证。
- ⏳ 后端 ACCEPTED 后的手动删除功能尚未完成真实设备验证。
- ⚠️ Root 设备抓取的 boot 属于活动快照，不保证厂商原始完整性。

## 真机 Root 联调诊断（0.6.1-dev）

- 应用 02 区显示 `Build.DEVICE` 与 `Build.PRODUCT`，Root 检测按钮始终可用；**分区采集按钮依然严格要求 pandora**。
- Root 命令 `su -c id` 最多等待 45 秒，成功、拒绝、超时均在检测按钮下面即时显示；不再只在页面底部输出结果。
- `adb shell su -c id` 的授权主体是 ADB shell，**不等于**本应用被授予 Root；请在 ReSukiSU/BakaSU 的「超级用户」中独立核对 `com.wekingchen.pandoraota`。
- 如果出现「等待 Root 授权超时」，先检查管理器对本应用的授权，不要删除数据重装，否则加密存储的 PAT 可能丢失。

## 0.7.1-dev 本地空间清理安全修复

- OTA 安全拒收（如同版本自定义 Boot 漂移）**不等于 GitHub 上传失败**，也不应阻止用户手动清理自己的本地 ZIP。
- 「记录」页只有存在 GitHub 上传回执且有已保存 PAT 时开放清理。先明确提示删除本地副本无法恢复；后台再次读取对应 Draft Release 并核验附件 ID、名称、字节大小、上传状态、SHA-256，再次核验本地文件 SHA-256 后才执行删除。
- 远端不存在、被修改、网络错误或 SHA 不符时，**禁止删除**；不会删除远端 Draft Release，也不会修改原有 OTA 固定输入或 LKG。
- 校验采用独立 HTTP GET，不会改变已验证的采集/上传/后端门禁。
