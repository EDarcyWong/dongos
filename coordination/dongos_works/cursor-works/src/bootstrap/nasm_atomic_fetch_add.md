# bootstrap.nasm_atomic_fetch_add：原子 fetch-add 返回旧值与模加法

```text
module bootstrap.nasm_atomic_fetch_add;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(width:u64, out:[]u8, written:*usize)u64
```

`width` 仅 `32` 或 `64`，其它 `INVALID`（优先于 `CAPACITY`）。固定运行时 `RDI`=目标地址、`RSI`=delta。

width32 精确两行：

```text
mov eax, esi
lock xadd dword [rdi], eax
```

width64 精确两行：

```text
mov rax, rsi
lock xadd qword [rdi], rax
```

- 必须带 `LOCK` 前缀的 `XADD`。
- 目标变为 `(old + delta) mod 2^width`；`RAX` 返回 `old`（32 位经 `mov eax, esi` 零扩展）。
- 只 `RAX`/flags 可变；`RDI`/`RSI` 与其余 GPR、非目标内存保持；32 位只改低 4 字节。
- 调用方保证普通可缓存、自然对齐、可写内存与原子使用契约；本发射器不校验地址，不用于 MMIO。
- 本任务不改 IR 接线，不以仅指令库宣称完整原子语义集成。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与完整声明的 out 重叠。
2. `INVALID`：`width` 不是 32/64（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 64 字节局部缓冲区组装（最长 40 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_atomic_fetch_add_emit`。依赖 `[]`。

## 原生/并发观察契约（R1）

目标与元数据分离；断言 RDI=原目标、双端 guard。并发用正式 Dong 实际产出；窗口内无普通读共享单元；双端 guard join 后检查。向量合计 ≤24。负控好坏两侧实际 Dong 同输入。
