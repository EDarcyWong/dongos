# bootstrap.nasm_atomic_store：顺序一致性 32/64 位原子存储发射

```text
module bootstrap.nasm_atomic_store;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(width:u64, out:[]u8, written:*usize)u64
```

`width` 仅 `32` 或 `64`，其它 `INVALID`（优先于 `CAPACITY`）。固定运行时 `RDI`=目标地址、`RSI`=新值，写入 RSI 低 `width` 位。

width32 精确两行：

```text
mov eax, esi
xchg dword [rdi], eax
```

width64 精确两行：

```text
mov rax, rsi
xchg qword [rdi], rax
```

- 内存操作数上的 `XCHG` 隐式锁定，不额外加 `LOCK` 前缀。
- `RAX` 被改为旧值（32 位路径零扩展）；这是 scratch，语言层 `atomic_store` 无返回值。
- `RDI`/`RSI` 与其余 GPR、flags 均保持；只目标 `width` 字节改变。
- 调用方保证普通可缓存、自然对齐、可写内存与原子使用契约；本发射器不校验地址，不用于 MMIO。
- 本任务不改 IR 接线，不以仅指令库宣称完整原子语义集成。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与完整声明的 out 重叠。
2. `INVALID`：`width` 不是 32/64（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 64 字节局部缓冲区组装（最长 35 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_atomic_store_emit`。依赖 `[]`。

## 原生观察契约（R1）

目标对象与观测元数据分离：目标两侧各有独立 qword guard；片段后立即断言 `RDI` 等于原目标地址、完整目标、双端 guard，以及 32 位单元格高 4 字节 guard。flags 种子含 `CF=1`（`0x203`）。两宽度主要原生向量合计 ≤16。负控好坏两侧均用正式/坏 Dong 实际产出与完全相同输入。
