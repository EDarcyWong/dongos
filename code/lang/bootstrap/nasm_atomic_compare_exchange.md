# bootstrap.nasm_atomic_compare_exchange：顺序一致性 32/64 位原子比较交换

```text
module bootstrap.nasm_atomic_compare_exchange;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(width:u64, out:[]u8, written:*usize)u64
```

`width` 仅 `32` 或 `64`，其它 `INVALID`（优先于 `CAPACITY`）。固定运行时 `RDI`=目标地址、`RSI`=expected、`RDX`=desired；只比较并写入低 `width` 位。

width32 精确三行：

```text
mov eax, esi
mov r10d, edx
lock cmpxchg dword [rdi], r10d
```

width64 精确三行：

```text
mov rax, rsi
mov r10, rdx
lock cmpxchg qword [rdi], r10
```

- 必须带 `LOCK` 前缀；强比较无伪失败。
- 若旧内存低 `width` 位等于 expected 低位，则写入 desired 低位；否则不写。
- `RAX` 始终为旧值；32 位路径必须先 `mov eax, esi` 零扩展清高 32（成功时 CMPXCHG 不重写累加器，不能用 `mov rax, rsi`）。
- `ZF=1` 当且仅当交换成功；其余算术 flags 允许被改变。
- 只 `RAX`/`R10`/flags 可变；`RDI`/`RSI`/`RDX` 与其余 GPR、非目标内存保持。
- 调用方保证普通可缓存、自然对齐、可写内存与原子使用契约；本发射器不校验地址，不用于 MMIO。
- 本任务不改 IR 接线，不以仅指令库宣称完整原子语义集成。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与完整声明的 out 重叠。
2. `INVALID`：`width` 不是 32/64（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 64 字节局部缓冲区组装（最长 58 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_atomic_cmpxchg_emit`。依赖 `[]`。

## 原生/并发观察契约（R1）

目标与元数据分离；断言 `RDI` 等于原目标、双端 guard、32 位高 4 字节 guard。两宽度主要向量合计 ≤24。并发使用正式 Dong 实际产出；窗口内不对共享单元做普通 C 读，以 CAS 返回 `RAX` 驱动重试并记录成功旧值；join 后检查终值与双端 guard。负控好坏两侧均为实际 Dong 产出与相同输入。
