# Pandora OTA 适配自动化 V2 · 第一阶段：真实 ABI 证据回放

## 为什么有这一阶段

OS4.0.6.0.XBLCNXM 的初始 GKI 构建成功，但真实 OEM ABI 门禁 BLOCKED：
从完整 stock vendor/system + vendor_boot 解析到 38,998 次导入，
剩余 71 个原厂 Rust Binder 导入未解析、27 处模块提供者歧义。
这一阻断是正确的安全结果，不能因 Action 的 conclusion=success 而视为可刷机。

后续 exact #37 通过了受真机与具体 Image SHA 约束的 runtime-selected
OEM gate，**不是对初始静态 ABI 失败的通用豁免**。
本阶段的目标是重放初始 **BLOCKED** 状态，并把失败原因自动转换成可操作的诊断。

## 新增内容

- scripts/xiaomi-os4/ota-v2-abi-diagnostics.py：只读解释现有 OEM checker
  的 JSON；输出机器可读状态、阻断分类、下一步所需证据和中文 Markdown。
- scripts/xiaomi-os4/ota-v2-references/pandora-os4-406-raw-oem-abi.json：
  已知的原始 OS4.0.6 静态图参考记录，锁定 stock SHA、GKI commit、
  模块数量、导入和 ABI 阻断统计。
- scripts/xiaomi-os4/test_ota_v2_diagnostics.py：正常/篡改/误放行/证据缺失测试。
- .github/workflows/pandora-os4-ota-v2-evidence-replay.yml：只读从两个已有
  Release 读取真实 stock-input 和 GKI 候选，核对来源及文件校验和，
  调用 **现有生产 OEM checker** 全图重新分析，比较历史参考，
  上传原始 ABI JSON、V2 诊断 JSON 和 Markdown。只做回放，不编译内核。

## 成功判定

1. 文件可证明来自当前归档的 exact OS4.0.6 输入和 r74 GKI 候选；
2. 原 checker 确实重新解析真实 OEM ZIP / vendor_boot，而不是人工拼接通过结果；
3. 原 checker 继续报告 BLOCKED，并匹配历史 71 / 27 / 0 与完整模块图；
4. V2 诊断结果为 ABI_BLOCKED_DIAGNOSABLE，并给出
   Rust Binder ABI 调查和 vendor/system 模块来源调查方向；
5. Action 的成功仅代表**成功复现被阻断的历史状态**。这不能解锁 fastboot boot、
   AnyKernel3、persistent、LKG，更不能替代真机测试。

如果数据被替换、参考统计不再一致、checker 意外放行或证据不完整，回放
**必须失败**，不得静默修正预期值。

## 第二阶段：接入已有 OTA 自动候选的 OEM ABI job

正式入口仍然是 .github/workflows/xiaomi-sm8850-os4-ota-auto-candidate.yml，
没有另建一条并行的 OTA 构建流水线。原有 OEM checker 不变，始终独立
决策 eligible_for_fastboot_boot；新增的诊断步骤调用
scripts/xiaomi-os4/run-ota-v2-diagnostics.sh，对同一份原始
ota-abi-report.json 生成 ota-v2-diagnostic.json 和 ota-v2-diagnostic.md。

- ABI_BLOCKED_DIAGNOSABLE：已识别出具体的模块或 ABI 阻断，按原因给出
  只读补证建议，不打包 boot。
- AUDIT_OR_INPUT_BLOCKED_REQUIRES_MANUAL_REVIEW：来源、文件校验、解析或
  前置审计无法形成有效模块图，明确要求人工审核，不把缺失结果当成零错误。
- STATIC_ABI_PASS_REQUIRES_REAL_DEVICE_TEST：**仅**静态门禁通过，可进入
  旧有的 fastboot-boot-only 未验证候选流程；不开放持久刷机与 LKG。

新增桥接器强制交叉比对原始 gate / eligible 与 V2 输出：若诊断器失败、报告
矛盾或产生意外的持久安装授权，CI 失败并阻止后续待测 boot 打包。其他产物
（手机反馈元数据和 boot）仍由原始 ABI 结果与 V2 完整性共同限制。
原始 ABI JSON、V2 JSON、V2 Markdown 同放入原来的 ABI Artifact；
运行摘要直接展示中文诊断与建议，无须另外找一次性 Workflow。

这次在历史回放 Workflow 中复用同一个生产桥接器，对**真实 OS4.0.6
完整 stock/GKI 归档**执行并与历史固定参考比对。
回放成功仅意味着重现旧的 BLOCKED，不代表为任意新 OTA 建立兼容证书。

## 第三阶段：来源绑定的可选只读手机诊断补采

当正式 OEM checker 报告可定位的 ABI 阻断时，OTA 候选工作流追加生成 `ota-v2-diagnostic-task.json`，绑定 stock SHA、Build、原始 Run/head、GKI commit 和已知问题类型；任务中 `commands=[]`，不能下发远程执行指令。App 仅在可信阶段为 `ABI_BLOCKED` 时，在原有工作台的状态卡上显示一次性「查看补采建议」入口。原三页导航与日常 Root/OTA 采集不变。

二级页沿用原生蓝白卡片与三步流程：看懂原因、读取白名单信息、预览并明确同意上传。采集结果按部分/完整区分，不发送原始 cmdline、模块地址、ELF 或内核日志。单独的 GitHub 诊断 Draft 接入 `pandora-os4-ota-diagnostic-intake.yml`，审核源 Run、当前 stock SHA、附件原始字节/哈希及 schema 后只生成 **REVIEW_REQUIRED** 的证据，绝不更新 OEM Gate 或 LKG。模拟器/真实归档回放只是对代码路径验证；真正新 OTA 的诊断仍需当次真机采集并审核。

## 尚未实现的能力

本阶段没有自动发明 EEXIST 补丁、自动推断完整模块加载顺序、自动认定
某个模块可以从运行图排除，也不会自动写手机或自动升级 LKG。
后续应为已识别的阻断类型生成安全的**可选**只读采集模板，并将
诊断状态显示在 OTA 助手工作台（需额外 API/客户端契约验证）。
每次新 OTA/新 Image 的 runtime-selected 放行都必须重新绑定真机证据；
OS4.0.6 的 runtime-selected gate / Gen 6 LKG 保持原样。

## 上游隔离边界

只新增 pandora 专属 scripts/xiaomi-os4/、.github/workflows/ 和本文；
不修改 zzh20188 上游共用文件、不改 Gen 6 指针与发布、不操作手机、不上传手机私有日志。
