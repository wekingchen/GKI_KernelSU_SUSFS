# 小米 17 Pro / HyperOS 4 — 手机 OTA 采集助手

> Android APK 0.4.0-dev｜独立分支 `pandora-os4-ota-companion`｜不刷机、不自动晋升 LKG。
> 已通过 APK Debug 编译与 6 项模拟采集包格式测试；**未在真实 pandora 上验证 Root/上传**。

## 操作流程

1. 安装由 Actions 构建的 APK，Root 管理器首次授予本应用 Root。
2. GitHub 设置填入 `wekingchen/GKI_KernelSU_SUSFS` 与 fine-grained PAT（**仅该仓库**、Contents: Read and write），可按 GitHub 提供的期限长期有效；AES-GCM/Android Keystore 加密存储，可主动清除。
3. 点击“检查 Root”，随后“一键采集”：强制读取设备代码、OS build、uname、活动 slot、OEM 内核模块以及 `boot/init_boot/vendor_boot/dtbo`，所有读取均只读。**当前分区不等于可信厂商原版**，Root/LKM/自定义内核也可能改变内容。
4. 上传：APK 将包送到仅管理员可见的 **Draft Release**，显示写入进度、大小、速度和时间。只有 GitHub 返回 **HTTP 201 且附件大小一致** 才记成功并留有回执。
5. **只要 ZIP 打包完成，手机立即清理分区镜像、OEM TAR 等所有中间采集物和 staging 目录，只留下最终 ZIP。采集或压缩出错则同时删除残缺 ZIP 并尝试清理 staging；上次意外终止遗留的 staging 在下次采集时自动回收（保留 30 分钟宽限以避开正在执行的采集）。**
6. 在有回执后，可人工确认并删除对应最终 ZIP；删除前会复验 SHA-256。多个历史 ZIP 可切换，上传失败永不自动删除。

上传阶段请保持 App 前台及网络稳定，目前**不支持断点续传**，也不提供后台 Foreground Service。单文件必须小于 2 GiB，实际 OTA 输入处理限额更严格（950 MiB）。

## 服务端与现有 OTA 流程的兼容性

- APP 上传的 `pandora-ota-capture-v1` 包含活动 slot 的分区快照、`oem-modules.tar` 及身份清单。
- `normalize_mobile_capture.py` 严格校验清单、slot、uname、目录、大小和内核模块数量，转换成当前 Windows `collect-pandora-stock-input.cmd` 的同款 **八文件 `*xm.zip`**。
- `mobile-intake.sh` 仅接受对应 Draft Release 的特定 Asset ID、实际文件长度与 SHA-256 一致的输入；转换后还执行原 `inspect-ota-stock-input.py` 身份审计。旧固定 Release 不会因为无效上传被覆盖。
- 验证通过的新 OTA 先上传到固定 Release 的非 `*xm.zip` 暂存名并从 GitHub 下载回检，再更名、替换旧单一 `xm.zip`，最后触发原 `xiaomi-sm8850-os4-ota-auto-candidate.yml`。
- **重要：`repository_dispatch` 仅从仓库默认分支执行。** 只有当 `.github/workflows/pandora-os4-ota-mobile-intake.yml` 与配套脚本合入默认 `dev` 后才真正自动接收。仅在实验分支构建 APK 不构成端到端部署。
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

## 已验证 / 未验证

- ✅ Action Runner 固定 Ubuntu 24.04；SDK 初始化和 Debug APK 首轮编译成功（Run 41269296891）。
- ✅ 合成手机包转换：正常 / 缺分区 / 错设备 / 错 slot / tar 链接 / 禁止覆盖 6 项测试通过（Run 41269661858）。
- ⏳ 真机 Root 采集、手机网络上行、GitHub Draft 上传、固定 Release 安全切换、原 OTA GKI 候选联动：尚未有真实 OTA 实物验证。
- ⏳ 签名稳定版需要仓库 Secrets；未配置时 CI 只能提供实验 Debug APK。
- ⚠️ 任何从 Root 手机读出的 boot 都必须当作未验证活动快照，不能声称与 OTA 厂商原始镜像相同。
