# P2GOP29：永久 GOP writer Gate

本项把 `kernel/entry.asm` 的真实绘图入口接到永久静态 Gate。它是后续
P2CACHE20 正常迁移接线的前置组件；没有接入 C/D 服务、修改 IDT、启动 VM，
也没有证明用户 compositor 已停止写 GOP。

## 固定 ABI 与生命周期

`kernel_framebuffer_gate_get()` 是无参数 SysV 函数，RAX 始终返回同一个
`framebuffer_gate` 地址。该对象在内核 `.bss` 内，64 字节对齐，恰好 32 字节：

| 字段 | 偏移 | writer 的访问 |
| --- | ---: | --- |
| word | 0 | 原子计数增减 |
| epoch | 8 | 不修改 |
| drained | 16 | 不修改 |
| opened | 24 | 不修改 |

这与 `mm.runtime_cache.Gate` 和真实 `runtime_cache_gate_close/drain/open`
使用的字段布局相同。word 的低 32 位是 writer 数，bit62 是尚未发布完成的
closing，bit63 是 closed；其余高位非法。初始四个字段均为零。生产
`tools/elf_image.py:materialize` 以零填充完整 PT_LOAD 内存范围，包含 BSS；
没有任何后续 Gate 重置或晚发布指针。

局部 `framebuffer_gate_enter` 只尝试一次 CAS：高位非零或低位计数为
`0xffffffff` 时拒绝，CAS 竞争时也立即拒绝。它不等 BKL、CPU 状态或另一个
writer。返回 1 才拥有一次 writer。竞争可能略过一次重绘，调用者可以安全
放弃绘图。

`framebuffer_gate_leave` 在减计数前执行 SFENCE，随后用 CAS 保留关闭位、
只减低位计数；已进入的 writer 在 close/closing 后仍可退出。它不修改迁移
token。SFENCE 用于将先前 WC 像素存储排在计数释放前；参见
[Intel 指令手册的 SFENCE 定义](https://cdrdv2-public.intel.com/789581/325383-sdm-vol-2abcd.pdf)。
宿主 RAM 测试不证明实际 GOP 的 WC 硬件时序。

两个局部 helper 仅破坏 RAX、RDX 和标志，没有 GS、SIMD、MSR、端口或可选
CACHE reader 外部依赖。getter 及存储在全部 runtime 级别存在，不会给
runtime0..6 增加尚未链接的 CACHE 符号。

## 写入覆盖与异常行为

`screen_draw` 和 `kernel_panic_screen` 各在最外圈取得一次 writer。任何显示
几何、framebuffer 地址或像素访问前先检查 Gate；拒绝后恢复原保存寄存器并
返回。正常绘图、无效几何及空 framebuffer 的所有 acquired 出口都会 leave。
普通绘图仍返回原来的 0/1，leave 的返回值不会覆盖绘图结果。

`text_draw` 和 `screen_hex_draw` 保持内部实现，由外层 writer 覆盖背景、
文字、字段和调用栈绘制，不嵌套获取第二个 writer。原有 SysV 保存寄存器、
CALL 前的 16 字节栈对齐以及图形内容不变。

`kernel/panic.asm` 未修改：首个 panic 完成串口输出后调用受 Gate 保护的
`kernel_panic_screen`，之后进入原 fatal 停机流程；`panic_reentered` 仍是
不调用、不压栈的有限 UART 路径。关闭期间的 panic 可略过图形，不等锁或
drain。若 NMI 打断已持 writer 的绘图并最终停机，旧 writer 可能无法归还；
迁移必须在旧映射仍存在时超时并保持失败，不能强制清零或重开 Gate。

还有一条只在启动期发生的 GOP 写入：`memory_runtime.asm:memory_active_probe`
读取一个像素、写测试值并恢复。静态调用点只有 `entry.asm` 的一个直接 CALL，
位于 `screen_draw`、`runtime_begin`、`smp_runtime_begin`、`user_runtime_begin`、
`dong_desktop_enable`、`service_runtime_begin` 之前。测试会枚举全部 kernel
ASM 的 CALL/JMP，保留这个仅启动期的边界；本项不修改该探针。未来新增运行期
调用会使此前置证明失效，必须重新接 Gate。

用户 compositor 在 CPL3 经现有 present 路径写 GOP，不能直接调用这个内核
Gate。后续 D 必须先 close/drain 内核 writer，再完成全 Domain CPU capture
及 all-tag 协议，才可移除用户和内核 GOP 映射。Gate 本身不代表用户写入已排空。

## 独立 host 验证

协调器运行 `python -m unittest tests.test_framebuffer_gate -v`。
本交付阶段未运行该命令，也未编译、汇编或执行任何探针。

测试新建 `build/test/framebuffer-gate/run-*` 证据目录。它从实际 entry 源码的
标记区间原样抽取 getter、helpers、四个 renderer、32 字节存储，以及真实
title 至 glyphs 的 rodata；没有重写 Gate 模型或绘图函数。独立抽取真实
`runtime_cache_reader.asm` 的五个 Gate 函数，排除特权 hardware reader。
RuntimeDisplay include 来自本次 `kernel/memory_probe.dg` 的 fresh compiler
layout，与 C 独立声明的 48 字节 Display 和 184 字节 ExceptionContext 对照。
生成 Dong layout 不等于 OS build，生成的 Dong 程序不汇编或执行。

生产完整 `entry.asm` 会在 runtime 0、3、4、5、6、7 下分别实际汇编 ELF64 和
COFF。它们只作为对象保存；任何特权启动或异常入口都不在宿主运行。安全抽取
片段的 ELF64/COFF 也实际汇编，宿主格式与 C oracle 在 O0/O2 下链接执行。
MinGW 命令显式含 `-D__USE_MINGW_ANSI_STDIO=1`。

C oracle 使用自有 RAM framebuffer、两端 sentinel、逐行 padding、独立字形/
十六进制期望值和独立 Gate 存储地址，检查：

- RGB/BGR 正常背景、真实文字和 panic hex/trace，保留 active count=1 的嵌套情形。
- closed、closing、非法高位、count overflow 的无副作用拒绝。
- 无效格式、尺寸、stride、短缓冲区和空地址的返回值及 writer 释放。
- 真正 `PROT_NONE` / `PAGE_NOACCESS` framebuffer 和 Display 均不被拒绝路径读取。
- 真实 close 在有 writer 时不能 drain/open，writer leave 后才可 drain/open，
  错误 token 不可重开，重开后可继续渲染。
- SysV 非易失 GPR、wrapper 栈平衡、CALL 前对齐和栈 sentinel。

七个坏体都直接修改本次 staging 的生产源码：分别删除普通/panic enter、删除
普通/panic leave、忽略 closed/closing 高位、getter 错地址、两 writer helpers
都指向错误的静态地址。每个坏体必须先成功汇编/链接，再由独立 C oracle
正常返回 1，并输出 `framebuffer gate oracle case=...; returned normally`。
所有坏体敏感的 RAM 检查排在 NOACCESS 前；异常退出、崩溃或超时都不能冒充
有效拒绝。总计 2 个正常执行和 14 个坏体执行，零 skip。

证据包含 `source-before/after.json`、`tools-before/after.json`、实际 NASM/CC
帮助及版本命令、每条命令的 argv/cwd/returncode/stdout/stderr、全量
`commands.json`、生成 include 的 SHA、抽取来源 SHA、实际 mutation、对象/
EXE SHA 和 `result.json`。源码和 Python/NASM/CC 工具前后哈希必须稳定。
真实 NMI、中断竞争、硬件 WC、全内核链接后的 2MiB 预算、AP/capture 和 guest
结果仍属于后续独立验证，不能由这组 host 结果推出。

## 后续 C/D 接线的只读设计边界

以下是接口审查结论，没有在本项实现。D 的 `Config.gate` 必须绑定本 getter
的实际地址；可信 adapter 在每次 recheck 同时核对这个固定地址和真正的
ledger epoch 指针，不能只信调用者复制的 Config 或指纹。

`memory.dg` 当前只发布 GOP physical/bytes，没有独立的 per-root alias ledger。
后续 ledger 应由真实 `publish_framebuffer`、`map_framebuffer/map_device_kind`、
destroy/rollback 生产点维护：内核 HHDM 记录来自原始 BootInfo 全 GOP 范围；
私有记录来自真实 Space/root、slot、memory generation、VA、PA、实际映射字节、
原 WC flags 和 4KiB leaf。desktop 私有映射可以短于完整 GOP，不能把原始 GOP
大小当作每个用户 alias 的实际长度。

逐页 map 可能中途失败，必须先登记 pending 并记录真实已提交范围；失败时保留
failed/held 状态阻止迁移，不能仅登记全成功调用而漏掉残留 PTE。destroy 应在
detach/flush/reclaim 完成后退役记录，不能仅凭 Catalog 状态消失。RootSnapshot
需包含所有存活或 pinned/preload root，不能只选 READY。独立 producer registry
与完整 forest audit 相互核验，禁止从 forest 扫描结果再构造同一个“独立”ledger。

ledger 使用确定顺序、仅合并连续且 flags/leaf 相同的段。真实 epoch 初始非零，
生产拓扑变更递增并拒绝溢出；它与 Gate epoch、Catalog incarnation/config
generation、Domain queue generation、memory generation 分别绑定。D 中间
WC→空→UC→空→WC 阶段 ledger 保留原 intended WC 形态，由组件的 phase closure
核实际页表，adapter 不可在每个中间阶段错误地要求所有 PTE 仍是 WC。
工作区按真实页数分配，保留 alias<=64、root<=16、linear page<=65536 限制，
不增加巨型 BSS 或局部数组。

`user_domain.register_poll` 是一次注册；当前 `services.enable_smp` 注册 B 的
`large_poll`。后续应在首次注册时使用可信 B/C/D mux，尚未 bind 的 Context
跳过，完成 bind/entry registration 后才发布指针。mux 按组件返回值传播失败，
不递归调用 Domain.poll、不代替组件 ACK、不改变原 legacy/all-tag 顺序。每次
事务使用 fresh RootSnapshot 和独立 ticket，不能复用 B 的历史 frozen arrays。

C 的生产 bind 还需真实 buddy lease、新 Context/roots/headers 的完整生命周期、
`runtime_exec_entry.bind` 的真实 snapshot 及一次注册，不能使用 host bind_snapshot。
现有 `tools/build.py` 尚未将 EXEC/CACHE readers 接到正常服务路径；后续必须在
与实际 DG import 图一致的 runtime 分支各链接一次，并 fresh build 验证，避免
再次重复声明共享 ASM extern。P2GOP29 的局部 helpers 正是为了让这些未来工作
不成为当前 runtime0..6 的未链接依赖。
