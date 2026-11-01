# 小米 17 系列 / SM8850：OS3 历史说明（已退役）

本项目当前只维护 pandora 的 OS4 路线。请从 [当前文档入口](pandora-os4-guide.md)进入，不要照旧 OS3 / 6.12.23 的菜单或工作流操作 OS4。

## 仍需保留的历史结论

- OS3 曾使用 Gold / 6.12.23 及 ACK-R51 实验路线；相关一次性工作流已退役。
- 用户实际遇到 ACK-R51 AnyKernel3 无法开机，回退 Gold #2 成功；这条路线没有被接受为当前稳定方案。旧稿早期“ACK 已可用”等阶段性文字不能覆盖后来的失败结论。
- Gold #3 原包已删除，不能仅凭同名附件或旧 Release 的 target_commitish 断言其与 Gold #2 的真实字节差异。历史同名资产混淆不应再次用于判断可刷性。
- 旧 Gold 恢复包仅属于原系统的历史恢复资料，不是 OS4 或下一次 OTA 的恢复镜像。
- Magic Mount 已不作为本项目当前方案；OS4 采用用户选择的 NoMount VFS 路线。

原有 500 多行历史菜单、缓存实验及退役工作流命令已从当前文档撤下，可在 Git 历史查看。保留此文件名是为了避免已有链接失效；不会为了修复旧链接而重新创建废弃工作流。

## 当前替代说明

- [OS4 OTA 与手机反馈](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)
- [OS4 当前 LKG 与动态组件](xiaomi-17-pro-os4-full-parity-lkg.md)
- [长期恢复与校验](xiaomi-17-pro-os4-lkg-release-archive.md)
