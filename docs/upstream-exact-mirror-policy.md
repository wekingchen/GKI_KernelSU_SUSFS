# 上游原件完整同步与本仓补丁隔离

## 规则

上游 zzh20188/GKI_KernelSU_SUSFS 的 dev 分支为不可修改的来源。
本仓 dev 中，上游已存在文件的相对路径和内容必须一致。不得自行删改任何上游文件，包括原始 GitHub Actions 工作流。
自定义功能只能加在新路径里；修改内核功能须在 Runner 下载源码之后应用补丁。

## 现有独立入口

- 小米 17 Pro OS4：独立的 xiaomi-sm8850-os4-*.yml 和 scripts/xiaomi-os4/**，不会因上游同步自动修改 LKG。
- 红米 K50 Pro：kernel-custom-fork.yml 使用 build-fork-custom.yml 和 get-manager-fork.yml；后者由 sync_fork_manager.py 在上游原件基础上重放私有补丁。
- SUSFS 历史兼容：susfs-compat-overlay.sh 仅修改 Runner 的临时源码树，不改写上游 scripts/susfs_fixes/apply.sh。

## 自动同步机制

每天北京时间约 10:37，upstream-exact-auto-sync.yml 检查最新上游。若有新增提交，采用正常 Git merge 生成独立候选 PR。
共享路径有本地改写、上游合并冲突、来源提交发生变化时，立即失败关闭，保留当前稳定 dev。
候选通过 GitHub pull_request 事件的真实隔离 CI 后才会自动合并；若上游新增高权限 Actions 工作流则保留 PR 等待人工审阅。
不会自动刷机、生成新的真机已验证结论，也不会晋升 OS4 LKG。

## 必需令牌（尚待运行环境验收）

2026-11-16 的 K50 Pro 自动同步失败，是因为原 GITHUB_TOKEN 没有修改 .github/workflows 工作流文件的权限。
仓库需要一个 Actions Secret：UPSTREAM_SYNC_PAT。令牌应仅授权本仓，Contents: Read and write、Workflows: Read and write、Pull requests: Read and write、Actions: Read。
在 GitHub 仓库 Settings → Secrets and variables → Actions 中设置，不要将令牌贴到聊天、日志或仓库源码里。
缺少凭据时，新的上游自动同步和原 K50 Pro 自动构建更新都应明确失败，不得声称已自动完成。

结构、隔离门禁和静态回归经过 CI 验证后可判定完成；无人值守合入需实测 GitHub PAT 权限及下一次真实上游提交。
