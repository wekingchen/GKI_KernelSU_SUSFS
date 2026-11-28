# OS4.0.8 EEXIST 临时启动基线（2026-11-28）

- 原厂输入 SHA256 `957ea67209374ce18465859bd5088bcb382b7518fd809cb30cfdfb3b636541a9`，stock boot SHA256 `1b73c648be2797548e9dcda88046be70bd8b023590c54f3dd15c1d6ec28ee82f`。
- 隔离构建 Run 46154744059，条件图 Run 46159502342（38,531 项有效导入，0 缺失/CRC/歧义；假设条件仍须真机验证）。
- 临时启动包 Run 46157442679 / Artifact 15268187296，Image SHA256 `3e4bab6b9ffaa4825908a8c02fdb4ffbbfc6273c8156f19d7a5904f6667a2397`，boot SHA256 `7b9570667715a2b6d0d2d1893486e1a6d55e8675f18c2ca09402ec371bf73044`。
- 用户按临时启动步骤提供的 ADB 回报：boot_completed=1；OS4.0.8.0.XBLCNXM；slot _a；uname 与原厂一致；activity/package 服务 found；sysfs 模块列表仅 node_cache/zram/zsmalloc；两项 Binder 参数 Permission denied；su inaccessible or not found。
- 这是用户回报而非服务器独立硬件证明。未直接读取 Binder active_impl、proc/modules、运行时 Note、完整 cmdline；不伪造运行时证据 ZIP 或把打包 Run 当作硬件核验 Run。
- 此版本开发指针仅允许全功能自定义内核 **fastboot boot** 测试。正式 OEM gate、AnyKernel3、持久安装及新 LKG 均保持阻断。历史 Gen7 LKG 不变。
