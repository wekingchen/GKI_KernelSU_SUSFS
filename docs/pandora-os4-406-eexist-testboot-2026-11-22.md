# pandora OS4.0.6.0：Rust Binder EEXIST 临时启动实验

本页只记录 **FASTBOOT BOOT ONLY** 的实验路线。正式 OEM ABI gate 始终保持
`BLOCKED`；不允许 `fastboot flash`、AnyKernel3、持久安装或 LKG 晋升。

## 已确认的真机前提

两份 OS4.0.6.0 真机只读证据已经确认：

- 当前 Binder `impl=c`；stock 内核没有 `active_impl` 节点；
- `rust_binder.ko` 由 system_dlkm `modules.load` 明确请求加载，
  模块可见为 Live，但当前运行事实强证据指向 C Binder 主实现；
- 当前实际 `zsmalloc/zram/node_cache` 来源均为 vendor；
- OEM system `rust_binder.ko` 对锁定 r74 GKI 仍有 71 个 Rust mangled
  kernel imports 无法解析；
- 该 71 项因此属于 **system_dlkm 模块装载兼容性阻断**，不是当前
  Binder 主链必须依赖 Rust 的证据。

正式 ABI 图仍保留 71 unresolved 与 27 provider ambiguities，不删除、不伪造。

## 为什么不用 built-in Rust Binder

锁定 r74 commit：

`b1d12d482d767c50cb792d988e4479d3f75c342a`

已做独立源码语义探针。Rust `module!` 宏本身有 built-in initcall 支持，
但 Linux 动态模块的同名 EEXIST 检查针对动态 `modules` list。
把某实现编进 Image 并不能可靠保证后续 OEM `rust_binder.ko` 在旧 Rust
符号解析之前自动得到 EEXIST，因此不能把 built-in 当作解决 71 imports
的安全依据。

## 精确 EEXIST shim

实验只对 exact r74 的 `kernel/module/main.c` 增加一个默认关闭的
core parameter：

`pandora_rust_binder_eexist=1`

启用后，模块加载流程仍先执行正常 `module_blacklist` 策略；随后仅当
解析出的模块名精确等于 `rust_binder` 时，在 rewrite/modversion/symbol
resolution 之前返回 `-EEXIST`。

其它模块不受影响；没有 `module_blacklist=rust_binder`。

Android 16 `libmodprobe` 对 `finit_module()` 返回 EEXIST 视为
“module already loaded”并按成功处理。因此实验要验证的是：

1. Xiaomi 后续 system_dlkm loader 是否采用兼容该语义的加载路径；
2. C Binder 是否继续正常工作；
3. OEM rust_binder 是否不再真正进入模块命名空间；
4. vendor zsmalloc/zram/node_cache 运行时来源是否保持不变。

这只能由临时真机启动验证，不能由静态检查升级为正式 ABI PASS。

## stock boot 的双层 AVB

锁定 stock `boot.img` 是 96 MiB 分区镜像：

- SHA256：
  `a75b2dd5596f75474fad2da8e8e64bb0a6398864d4b7f593d1f0dd1c9328979b`
- boot v4，ramdisk=0，boot header signature_size=0；
- stock kernel size：41511424；
- aligned kernel end：41517056；
- aligned kernel 后存在精确 16384-byte `AVB0` GKI boot signature；
- inner GKI AVB SHA256：
  `824bf63be36ecd15c0f049d73c4a925efc6fda85dd6901e0f38c9a91ed740d77`
- outer AVB footer 再签整个 stock boot logical image。

avbtool 已确认 inner AVB Hash descriptor 的 partition 为 `boot`，并绑定
stock kernel 的 Image Size / KERNEL_RELEASE，因此替换 Image 后不能保留
这份旧签名；outer AVB 同样不能复用。

实验 packager 对 exact stock 才允许：

- 验证 stock ZIP / boot SHA；
- 验证 outer AVB footer；
- 验证 inner 16K GKI signature 长度、magic 与 SHA；
- 明确剥离 inner + outer 两层旧 AVB；
- 输出只有 boot-v4 header + patched r74 Image + 4K 对齐；
- 新逻辑 boot 只要求小于已知 96 MiB boot partition envelope；
- 输出强制无 `AVBf`；
- 标记 `FLASHABLE=NO`。

任意未知非零 tail、AVB offset/version 异常或 stock identity drift 都失败关闭。

## 实验影子门禁

只有以下精确合同同时成立才允许生成临时待测镜像：

- 正式 OEM gate 仍为 `BLOCKED`；
- failed modules = 0；
- CRC mismatches = 0；
- unresolved kernel imports = 71，且身份 hash 与锁定报告一致；
- 71 项全部属于 stock system rust_binder 的 Rust mangled imports；
- ambiguous providers = 27，身份 hash 与锁定报告一致；
- 真机 runtime selection 证据仍为 Binder C + vendor memory stack；
- exact r74 source、stock input、kernel release 不漂移；
- shim 不改变 `Module.symvers`。

该影子 gate **只允许一次人工 fastboot boot 实验**，不会改变任何正式发布状态。

## 真机验收

实验成功启动后使用
`collect-pandora-406-eexist-testboot.cmd` 只读采集，无需 Root。

期望核心状态：

```text
pandora_rust_binder_eexist=1
binder impl=c
binder active_impl=c          # r74 若直接暴露该节点
rust_binder module=ABSENT
zsmalloc/zram/node_cache=loaded
service check activity=found
service check package=found
```

vendor 三模块 GNU Note 如果 shell 可读，还应继续唯一匹配锁定的 vendor
原厂 Note。kernel log 中 shim warning 只作为辅助证据，因为 shell 读取
kernel log 可能受权限限制。

`review-pandora-406-eexist-testboot.py` 对采集包做失败关闭判卷。即使实验
真机通过，也只能先证明该 **boot-only EEXIST 兼容策略** 在这一 OTA 上可用；
正式 OEM gate、持久刷机与 LKG 是否升级必须另行审计和明确决策。
