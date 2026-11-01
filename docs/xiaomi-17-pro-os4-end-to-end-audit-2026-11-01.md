# 小米 17 Pro OS4：2026-11-01 审计历史快照

> 这是历史记录，已由 [当前功能与文档入口](pandora-os4-guide.md)接替。旧稿把 Windows/网页列为主路径、把 Gen 3 写成当前 LKG，并重复列出了同一晋升工作流；这些表述已撤下，不能继续当作操作指令。

## 当时建立并继续保留的检查边界

- 设备活动快照不自动等于 OEM 原厂镜像；Root 后 init_boot 只作诊断。
- `NEW_OTA_CANDIDATE` 不表示已启动；OEM CRC/vermagic 通过不表示所有厂商运行时兼容。
- `HUMAN_ATTESTED_BASELINE_BOOTED` 是用户报告、来源核验及同 OTA IMG/fixture 字节复现，不是 CI 远程证明手机已开机。
- 自定义 `OTA_CUSTOM_UNVERIFIED` AnyKernel3 与已晋升 LKG 是不同身份；取得安装包不需要第二次反馈，但稳定晋升必须明确确认真实使用结果。
- 新 OTA 不得静默回退 R62，不得跨版本复用旧 fixture；公开稳定归档前必须下载核验资产，失败不能移动旧指针。

## 后续状态变化

1. 当前 R62 LKG 已晋升为 Gen 4：来源 41265596768、晋升 41266571030，后续复现/归档已成功。Gen 3 仅为历史恢复点。
2. App 已成为首选采集入口，具备空间/真实 GitHub 写权限预检、新 build 原始 init_boot 提醒、上传后前台状态跟踪和本地安全清理。
3. 真机结果首选直接在 App 填表：五项本机读取、人工功能确认、原工作流提交与状态跟踪；电脑只负责临时启动。Windows/网页入口作为备用保留。
4. 新 OTA 版本化 LKG 已使用与 R62 相同的唯一晋升入口，不再让用户选择两个重复工作流。
5. 新功能的模拟器与合成门禁不能代替真正不同固件上的端到端真机验收。

## 当前说明

- [手机优先 OTA 操作](xiaomi-17-pro-os4-firmware-upgrade-stock-input-guide.md)
- [服务端接收、候选与反馈](xiaomi-17-pro-os4-ota-auto-baseline.md)
- [当前 LKG 与组件策略](xiaomi-17-pro-os4-full-parity-lkg.md)
- [长期恢复](xiaomi-17-pro-os4-lkg-release-archive.md)
- [版本化 LKG 晋升](xiaomi-17-pro-os4-cross-ota-lkg.md)

历史大段操作说明仍可从 Git 历史查阅；本页不继续复制会随版本漂移的菜单、指针或工作流清单。
