# 小米 17 Pro OS4 OTA 采集助手（Android）

状态：独立开发分支中的 **实验性 APK**，尚未通过真实设备/上传链路验证。不能取代现有 LKG 或 OTA 安全门禁。

## 首版范围

- 在 pandora 手机上申请 KernelSU/Root，**只读**采集系统版本、内核、OEM 模块及可选的当前 boot 分区。
- 打包本地 ZIP，计算 SHA-256，不自动删除本地备份。
- 在应用内配置接收仓库与有到期日的 GitHub fine-grained PAT；使用 Android Keystore AES-GCM 保存，不写入 APK、Git 历史或日志。
- 上传为 **Draft Release** 附件，再发送 repository_dispatch: pandora_ota_upload_v1。服务器收到事件 **不等于已完成自动适配**，须由默认分支中的已审核工作流接入。
- 本地包每个必须严格小于 GitHub Release 的 2 GiB 单文件限制；完整系统 OTA ZIP 的分片上传/断点续传属于后续开发。

## 安全约束

1. 仅支持设备代号 pandora；遇到不匹配设备拒绝采集。
2. 仅对分区做只读 dd、对目录做 tar；永不写 boot、调用 fastboot 或替换内核。
3. **当前 boot 不等于原厂 boot**。采集文件必须标明 ACTIVE_DEVICE_SNAPSHOT_NOT_VERIFIED_STOCK；OEM ABI/KMI 比对、GKI 临时包与 LKG 晋升继续由服务端安全门禁决定。
4. 不采集 IMEI、序列号、账户、照片、应用数据、整个 getprop 或完整 kallsyms 地址。
5. 建议专用的**私有接收仓库**或保持 Release 为 Draft；勿将模块与分区镜像发布为公开附件。
6. 仅给**单一接收仓库**开 Contents: Read and write 的 fine-grained PAT、设置短有效期。令牌在 Root 设备上也并非绝对安全，推荐后续接入 GitHub App 短期令牌。
7. GitHub 上传失败后保留本地 ZIP；当前版本是整文件重试，不宣称支持断点续传。
8. 此项目所有文件放在独立目录，除独立 APK 构建工作流外不修改上游共享配置。

## 开发构建

使用 JDK 17 + Gradle 8.11.1 + Android SDK 35，在该目录运行：

    gradle :app:assembleDebug

独立 Action：.github/workflows/pandora-os4-ota-companion-apk.yml

## 后续集成

需要将 pandora_ota_upload_v1 与原有 OTA 工件读取入口衔接，并按现有 xm.zip 契约转换/校验。这一步尚未完成，暂不宣称上传后会自动构建候选 GKI。完整 OTA ZIP 分片协议必须先确认已有入口的消费规则，不能直接猜测格式。
