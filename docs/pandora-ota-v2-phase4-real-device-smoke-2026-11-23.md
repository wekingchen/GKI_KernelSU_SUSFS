# Pandora OTA V2 第四阶段 · 真机基础回归记录（2026-11-23）

## 对象与变更身份

- 设备：Xiaomi 17 Pro，代号 `pandora`。
- 应用：Pandora OTA 助手 `0.14.1-dev`（源码 `versionCode 30`）。
- 对应修复：[#130](https://github.com/wekingchen/GKI_KernelSU_SUSFS/pull/130)，合并到 `dev` 的提交为 `e0a8d8d908c3921dcd67545046830fd0a7b6c97f`。
- 固定签名 APK CI：[构建 #218](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45132013788)，`success`。
- Android 15 仪器/模拟器：[回归 #147](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45132013745)，`success`。
- 上述 CI 验证的是构建和模拟器回归；当前记录里的设备表现来自用户本人实机反馈，不替代设备侧 APK 文件 SHA/签名二次提取证据。

## 用户反馈：实际完成的验证

用户在 2026-11-23 安装并检查新版本后报告：

| 检查项 | 结果 | 判定 |
| --- | --- | --- |
| 原工作台页面 | 正常 | 真机基础回归通过 |
| 原记录页面 | 正常 | 真机基础回归通过 |
| 原设置页面 | 正常 | 真机基础回归通过 |
| Root 状态 | 正确 | 真机基础回归通过 |
| GitHub 连接状态 | 正确 | 真机基础回归通过 |
| 「兼容性补采」入口 | 未出现 | 当前无需新增 ABI 补采时符合预期；不能代替真实 ABI 阻断分支的测试 |
| 旧采集记录是否保留 | 用户此前已主动删除采集记录 | 无数据可验，明确记作 **NOT_TESTED**，不可标记为迁移通过 |

用户此次没有重新采集/上传 OTA，也没有为测试而制造 ABI 阻断。

## 验收边界：尚未完成

1. 新 OTA 真实发生 `ABI_BLOCKED` 时，可信任务出现、设备端仅按白名单补采、预览/确认、GitHub Draft 上传与只读审核返回 `REVIEW_REQUIRED` 的**真机端到端**验收尚未发生。当前仅有生产契约测试及 Android 模拟器覆盖。
2. 新增的 SHA 绑定 Draft 中断恢复、附件身份/摘要冲突拒绝，已由 Android 仪器模拟测试通过；尚无真机网络中断故障注入结果。
3. 历史采集记录保留/迁移因用户主动清空记录无法验证，不能从「记录页面正常」推论「历史记录未丢失」。
4. 该回归不构成任何新内核 ABI/KMI 放行、可刷机授权或 LKG 晋升证明。

## 决策与后续

- 第四阶段**真机基础功能回归通过**，无需反复重采现有 OTA，也不应刻意制造 ABI 错误。
- 正常新 OTA 继续按原先工作台采集 → 可信候选和 ABI 门禁 → 待测引导 → 人工真机验证与 LKG 晋升流程。
- 若未来真实出现可诊断的 ABI 阻断，再按当前 OTA Build、stock SHA、来源 Run 执行补采与审核；禁止复用 OS4.0.6 的旧观察替代新 OTA 证据。
- OS4.0.6 Gen7 LKG 归档/晋升是独立事项。晋升工作流 [#7](https://github.com/wekingchen/GKI_KernelSU_SUSFS/actions/runs/45128727756) 因 `dev changed during build` 在指针更新前停止，归档草稿保留；未成功晋升前，当前可证实的稳定 LKG 仍为 Gen6。
