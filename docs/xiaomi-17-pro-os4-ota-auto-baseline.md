# 小米 17 Pro OS4：OTA 自动化、手机反馈与开发基线

核对日期：2026-11-02。当前入口见 [功能与文档索引](pandora-os4-guide.md)，实际操作见 [OTA 指南](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)。

## 手机接收与候选构建是两条接力

| 阶段 | 工作流 | 触发与结果 |
| --- | --- | --- |
| 手机上传接收 | [手机安全接收入库](../.github/workflows/pandora-os4-ota-mobile-intake.yml) | App 把活动快照上传到专用 Draft，发送 `pandora_ota_upload_v1`；服务器绑定附件 ID、大小和 SHA-256 审计 |
| GKI / OEM ABI 候选 | [OTA 自动候选](../.github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml) | 接收器更新固定输入后通知；也响应指定 Release published/edited、北京时间 04:41 每日补查及手动运行 |
| 真机测试反馈 | [原真机反馈与固化工作流](../.github/workflows/xiaomi-sm8850-os4-ota-test-feedback.yml) | 首选在 App 填表，执行该 workflow 的 `workflow_dispatch`，固定 `ref=dev`；网页入口兼容保留 |
| 功能版构建 | [OS4 自定义内核](../.github/workflows/xiaomi-sm8850-os4-custom.yml) | 读取已验证开发基线，按用户菜单和当次上游快照构建 |

仅替换 Release 附件不保证立即发出 edited 事件，定时补查/手动入口用于补救。正常手机流程不需要用户自己删除固定 Release 的旧输入。

## 输入与安全替换

手机先保留同版本原始 `init_boot.img`，修补 Root 后再只读采集四个活动启动分区及 OEM 模块。手机 ZIP 由 `normalize_mobile_capture.py` 转为包含 README、SHA256SUMS、四张镜像、OEM ZIP 和模块数量清单的八文件 `xm.zip`。

这些是活动快照；Root 后 init_boot 明确为诊断材料，不能冒充 OEM 原版。boot 与 OEM .ko 是内核/ABI 主输入，但仅修补 init_boot 并不能自动证明 boot 未被换过。

接收器先校验来源、附件和归档结构，再与当前固定输入实际 build、渠道、boot 身份比较；旧 OTA、同版本 boot 漂移等应拒收。新输入先暂存、从 GitHub 下载回检后才替换固定唯一 `*xm.zip`；不采用“先删旧文件再验证新文件”的顺序。

App 接收状态绑定 Asset ID 与源 SHA：

| 状态 | 含义及下一步 |
| --- | --- |
| PENDING | 尚无最终回执，保留本地 ZIP，前台继续查询 |
| ACCEPTED | 新输入已接收，候选阶段仍需继续执行；不是 ABI 或真机通过 |
| ALREADY_CURRENT | 与固定输入一致，不必重复分析 |
| REJECTED | 身份或内容门禁未通过；远端原始附件仍保留，查看原因 |

## 候选构建与可测试条件

1. `inspect` 核对设备、build、slot、boot v4、kernel marker 与 KMI。
2. `baseline` 在现有支持范围 `6.12.x / android16-6`、Clang r536225 内解析官方 GKI tag/commit，生成 Image、Module.symvers、final.config 和来源记录。它是适配候选，不宣称找到了 Xiaomi 全部私有源码。
3. `archive` 对候选 prerelease 资产独立下载、校验来源与 SHA 后发布；候选公开不等于允许刷写。
4. OEM ABI 阶段逐项检查同 OTA 模块 vermagic 和导入 `vmlinux` 符号 CRC；只有 `eligible_for_fastboot_boot=true` 才生成 `UNVERIFIED-FASTBOOT-BOOT-ONLY.img`。
5. 同时上传独立小型 `pandora-OTA-MOBILE-FEEDBACK-<build>-<run>` Artifact，保存 Run、commit、build、预期 uname、IMG SHA 和文件名；App 不必下载整个 boot 才能预填表单。没有该文件的旧候选仍需手填实际 IMG SHA。

静态检查不覆盖全部驱动运行时。没有待测 IMG 的报告不能当作可启动包。App 尚不提供候选构建、ABI 和所有后续任务的统一实时进度面板。

## 电脑临时启动，手机提交原表单

电脑校验实际 IMG 的 SHA-256 并执行 `fastboot boot`。手机测试 Wi-Fi、移动数据、通话、蓝牙、相机及关键模块后，打开工作台「真机测试反馈」：

- 选择候选或输入来源 Run ID；新元数据核对来源后预填校验值，用户仍须确认电脑实际用了这张镜像。
- 自动读取 `ro.product.device`、`ro.mi.os.version.incremental`、`sys.boot_completed`、`uname -r` 和 `/proc/modules`；模块读取受限时做只读 Root 回退，失败明确显示未取得。
- build/uname 预填，用户手动选择 pass/fail、确认桌面及模块/功能并补充备注；自动采证不代替人工确认。
- 无法进入待测系统、恢复后再填表时，选恢复后失败模式；待测 build/uname 留空，确认项为 false，恢复环境不算待测成功。
- 本地先保存唯一反馈编号，原工作流通过 `client_request_id` / 运行标题关联；响应未知先查原运行，两分钟仍未建立可手动重发同一请求。服务器在任何 Issue 或基线变更前阻止重复编号。
- 前台自动跟踪等待、运行、成功/失败；后台暂停查询，重新打开继续；历史最多 20 条。模块全文保留在本地草稿，不宣称原工作流接收了完整模块附件。

反馈功能需要目标仓库 Contents 读写与 Actions 读写；原手机采集只需 Contents 读写。

## 服务端仍然独立核验

通过只接受 dev 上已成功的正式 OTA 来源及唯一、未过期且版本匹配的候选附件；再次核对固定 stock-input 的 asset ID / SHA、GKI 来源、配置、Image/symvers、ABI 与实际测试 IMG SHA。用同 OTA stock boot + 对应 Image 重新打包，必须字节一致，再从 schema 2 fixture 复现。

通过时 PR 仅固化以下三份记录： `.github/config/ota-verified/<build>/fixture.json`、`verification.json` 和 `.github/config/ota-development-current.json`。这叫 `HUMAN_ATTESTED_BASELINE_BOOTED`，是用户报告加 CI 来源核验，不是远程硬件证明。失败只保存故障 Issue，不创建已验证开发指针。

后续仍从同一自定义入口拿到同次 Image 的待测 IMG 与 `OTA_CUSTOM_UNVERIFIED` AnyKernel3，不需要再回报一次测试结果才能取得 ZIP。真正稳定使用后，另由用户在[唯一 LKG 晋升入口](xiaomi-17-pro-os4-cross-ota-lkg.md)确认；App 的测试通过不会自动晋升 LKG。

当前真实稳定基线为 R62 Gen 4；真正不同 OTA 的采集→候选→真机→功能版→LKG 全链路仍待实际固件验证。
