# bootstrap.nasm_sysv_function_entry：组合零保存寄存器序言与入口参数捕获（C44，接续 CR32）

SysV 函数入口片段：先用 CR11 的序言（固定 `saved_mask = 0`）建立 rbp 帧，再用 C37 把传入的 INTEGER 实参保存到固定帧槽 `[rbp - offset]`。两个组件都实际调用，本模块不重写它们的算法。不含尾声和 `ret`；不代表活动 IR 或完整 L3 已经完成。

```text
module bootstrap.nasm_sysv_function_entry;
import bootstrap.nasm_function_frame as ff;          // CR11（内部依赖 CR4 decimal_integer）
import bootstrap.nasm_sysv_incoming_args as inc;     // C37（内部依赖 C8 sysv_integer_args、CR8、CR4）
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const MAX_FRAME:usize=4080;
pub unsafe fn emit(kinds:[]const u8, destination_offsets:[]const usize, frame_bytes:usize,
                   out:[]u8, written:*usize)u64
```

没有 mask 参数：保存寄存器集合固定为空。

## 输出

```text
push rbp
mov rbp, rsp
sub rsp, <frame_bytes>        ; 仅当 frame_bytes 非 0（CR11 prologue(frame_bytes, 0) 原样输出）
<C37 捕获：先按字序存寄存器字，再经 RAX 搬栈字，栈字从 [rbp + 16] 起>
```

运行时前提：在真正的 SysV 函数入口执行（入口 `rsp % 16 == 8`）。序言之后 rbp 是帧基准，局部槽 `[rbp-offset, rbp-offset+8)` 完全在 `sub rsp` 分配的区域内，与 `[rbp+16]` 起的传入栈实参不重叠。捕获只改 RAX（有栈字时），6 个参数寄存器和其它 GPR 都保持；序言的 `sub rsp` 会改 flags。上游负责在函数出口配上 CR11 `epilogue(frame_bytes, 0)`。

## 参数校验（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕。
2. `destination_offsets.len*8` 不溢出；`kinds`、`destination_offsets`、`out` 的端点都不回绕，非空时指针不能为 NULL；`destination_offsets` 非空时必须 8 对齐。
3. 别名：`written` 与完整 `out` 不重叠；`written` 和 `out` 都不能和任何一个完整输入重叠（按声明长度，包括尾部）。两个输入之间允许互相重叠。
4. `frame_bytes` 在 0..4080 之间，且是 16 的倍数（CR11 本身接受 4096，C37 不接受，所以这里取 4080）。
5. 其余规则完整沿用 C37，由实际调用 C37 校验：kind 只能是 0/1、最多 16 个字、offset 数量等于字数、每个槽 8 对齐且 `8 <= offset <= frame_bytes`、槽互不相同。

第 5 步和 CR11 的调用都在局部 scratch 中完成，任何非 OK 都按 INVALID 返回，此时用户 `out` 还没被碰过。序言绝不会先于捕获单独发布：只有两段都组装完成、容量也够，才一次性发布精确前缀和 `*written`。任何失败都不改 `out`、`*written` 和输入。

## 局部 scratch 的上界证明

两段依次紧接着写进同一个 1536 字节的局部缓冲：

| 段 | 给组件的切片 | 组件自身的上界 | 写完后 `at` 的上界 |
| --- | --- | --- | --- |
| CR11 prologue | 64 | `push rbp\nmov rbp, rsp\n`（22）+ `sub rsp, 4080\n`（14）= 36 | 64 |
| C37 捕获 | 1024 | 16 字 × 55 = 880 | 1088 |

1088 ≤ 1536，每个组件最多只写到给它的切片末尾，所以不会越界；合法输入一定放得下。实际最长输出是 36 + 880 = 916 字节以内（由测试精确计算并覆盖）。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_entry_emit`（另外导出 CR11 `epilogue`，给原生测试的被调用函数生成真实的出口）。
