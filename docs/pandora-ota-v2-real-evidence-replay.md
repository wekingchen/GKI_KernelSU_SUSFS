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

## 当前与后续阶段

本阶段仅证明可重复诊断和阻断分类。它**没有**自动发现 EEXIST 兼容补丁、
自动选择运行时模块或自动建立新的 OEM gate 放行记录。
OS4.0.6 的 runtime-selected gate / Gen 6 LKG 继续独立保留、原样生效。

下一阶段才考虑把 V2 的诊断结果挂到现有
xiaomi-sm8850-os4-ota-auto-candidate.yml（不另起一套完整 OTA 流程），
为 ABI_BLOCKED_DIAGNOSABLE 输出可安全执行的补采模板，同时明确
INPUT_OR_PROVENANCE_BLOCKED、NONFLASH_RESEARCH_ONLY 等状态。
所有修复与放行仍需严格基于新 OTA、新 Image 的独立证明。

## 上游隔离边界

只新增 pandora 专属 scripts/xiaomi-os4/、.github/workflows/ 和本文；
不修改 zzh20188 上游共用文件、不改 Gen 6 指针与发布、不操作手机、不上传手机私有日志。
