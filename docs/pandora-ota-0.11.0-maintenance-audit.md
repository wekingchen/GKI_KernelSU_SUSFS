# Pandora OTA 0.11.0 清理与交付审计

清理日期：2026-11-02（北京时间）。开发基线：`dev@34db6b2a0c5a504c05dc85c8764bdacedcbc3511`。

## 已执行历史清理

独立审计运行：[41328789065](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/41328789065)，成功。删除 11 个指定分支、213 条归属于这些分支且不在保留清单内的已完成运行。不是按年龄或 success/failure 批量删除。

- dev-ota-help-guide-20261102
- dev-ota-current-release-guard-20261101
- dev-ota-function-audit-20261101
- dev-ota-ui-micro-polish-20261101
- dev-ota-ui-realdevice-polish-20261101
- dev-ota-ui-detail-polish-20261101
- dev-ota-ui-commercial-20261101
- dev-ota-ui-minimal-20261101
- dev-ota-ui-polish-20261101
- pandora-os4-rooted-initboot-provenance
- pandora-ota-draft-release-link-fix

临时维护分支在完成后自行删除；维护 workflow 未合入 dev。删除明细 ID 记录在审计运行 summary 与 job 日志中。

## 关键保留证据

| Run | 证据 |
| --- | --- |
| 41280701707 | 真机上传与接收门禁；failure 是同版本自定义 Boot 被拒收的有效证据 |
| 41265596768 | LKG 来源 |
| 41266571030 | LKG 晋升 |
| 41325059131 | 0.10.5 固定签名 APK |
| 41325059217 | 0.10.5 模拟器验证 |
| 41322534432 | OTA 契约回归 |

清理后再次读取全部六条证据成功。保留 dev、19 个上游对应分支、LKG 配置/历史、正式 Release、固定 xm.zip 与真实采集 Draft；不删除备份或真机附件。

## 仓库扫描结果

- dev 现有 25 个 workflow 均有真实源码文件，未发现需要废弃的正式工作流。
- 全库本地 `.github/workflows/*.yml` 引用完整；唯一不存在的 `unknown.yml` 是 `test_native_upstream_policy.py` 的故意负向夹具，保留。
- APK 和模拟器 workflow 去除已不存在的 `pandora-os4-ota-companion` 分支触发引用，继续由 dev push / PR 和手动入口运行。
- APK 工作流去除“独立实验”名称，签名缺失直接失败；不再允许只有 Debug 产物却整体校验成功。
- 未复用废弃帮助分支的未完成预检代码；0.11.0 从干净 dev 重新实现。
- 修正采集规范化脚本计算 SHA-256 时未关闭输入文件的问题，已有格式/字节契约保持一致。

## 验证范围

本地基线回归：OTA Python 契约 26 项、OS4 Python 108 项通过。0.11.0 另有 Android 仪器测试，覆盖实际目录空间读取、1/2 GiB 边界、build/fingerprint 与提醒持久化、实时 HTTP 写权限探针、过期/只读/断网/草稿清理失败，以及轮询所有终态、前后台恢复、网络重试和切换采集包丢弃迟到回执。

最终 APK、固定签名指纹、模拟器与接收契约结果见 0.11.0 PR 的检查记录；所有必要检查完成前不合入 dev。新增功能的模拟器验证不替代新 OTA 实物的全链路真机验证。
