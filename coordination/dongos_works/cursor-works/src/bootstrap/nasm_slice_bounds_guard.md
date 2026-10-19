# bootstrap.nasm_slice_bounds_guard：允许空端点的切片 lo/hi/len 联合门禁

```text
module bootstrap.nasm_slice_bounds_guard;
import bootstrap.decimal_integer as dec;   // 已集成 CR4，块号十进制
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const NONE:u64=0xffff_ffff_ffff_ffff;
pub unsafe fn emit(trap_block:u64, out:[]u8, written:*usize)u64
```

固定寄存器：`RDI=lo`、`RSI=hi`、`RDX=len`，全部为完整 64 位 usize 无符号比较。成功时 out 前缀恰好四行 ASCII：

```text
cmp rsi, rdx
ja __dong_b<N>
cmp rdi, rsi
ja __dong_b<N>
```

- 仅当 `lo <= hi <= len` 落空；允许 `lo==hi==len` 与全 0（空切片端点）。区别于 CR20 的 `index < len`。
- 两次 unsigned 比较之间不改写参与寄存器；只改变 flags，全部 GPR 保持。
- 不计算元素地址、len 差、指针乘法；不代替存储有效性/权限验证。trap 由上游定义为 bounds kind1。
- 块号经 CR4；`trap_block` 允许 `0..usize最大−1`，`NONE` 非法。无需依赖 CR20。

## 求长与上界

局部 **128** 字节。最长（20 位块号两次）：

- `cmp rsi, rdx\n` = 13
- `ja __dong_b` + 20 + `\n` = 32
- `cmp rdi, rsi\n` = 13
- `ja __dong_b` + 20 + `\n` = 32

合计 **90** 字节。先以两次块号精确求长，再发布。

## 检查顺序与内存

1. `INVALID`：written 为 NULL、未 8 字节对齐或 8 字节区间回绕；out 区间回绕（空 out 可为 NULL）；written 与完整声明 out 重叠。
2. `INVALID`：`trap_block == NONE`（容量为 0 时也先报 INVALID）。
3. `CAPACITY`：文本长度大于 out.len。

失败不改 out 和 written；成功只写精确前缀，尾部不变。无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试经临时 wrapper 导出 `dong_slice_bounds_guard_emit`。
