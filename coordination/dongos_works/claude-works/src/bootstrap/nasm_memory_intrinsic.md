# bootstrap.nasm_memory_intrinsic：固定寄存器字节复制与清零发射

```text
module bootstrap.nasm_memory_intrinsic;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const COPY:u64=0; pub const ZERO:u64=1;
pub unsafe fn emit(operation:u64, out:[]u8, written:*usize)u64
```

| operation | 文本 | 运行时输入 | 执行后 |
| --- | --- | --- | --- |
| COPY (0) | `rep movsb\n` | RDI=目的，RSI=源，RCX=字节数 | RCX=0，RDI/RSI 各前移原 count；RAX、其它寄存器和 flags 不变 |
| ZERO (1) | `xor eax, eax\nrep stosb\n` | RDI=目的，RCX=字节数 | RCX=0，RDI 前移 count，RAX=0；RSI 和其它寄存器不变，算术 flags 按 xor 改变 |

调用方负责 DF=0、区间真实可访问、COPY 源与目的不重叠（不是 memmove），以及对象边界、生命周期和语言层检查。count=0 时不访问内存（COPY 指针不变，ZERO 仍会先清 RAX）。这是内存内建的后端发射，不改写已验收的 D1 标准库，也不修改当前编译器的内建 lowering。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与**完整声明的** out 重叠（含未使用尾部）。
2. `INVALID`：operation > 1（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

文本在 32 字节局部缓冲区组装（最长 23 字节），全部通过后一次复制到 out 并写 `*written`。失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_mem_emit`。
