# bootstrap.nasm_byte_truth_load — 字节装入 + 双零比较的非零真值规范化

```text
module bootstrap.nasm_byte_truth_load;
import bootstrap.nasm_integer_memory_load as loadm;   // 已集成 CR12
import bootstrap.nasm_integer_unary as unarym;        // 已集成 CR16
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(base:u64, displacement:i64, out:[]u8, written:*usize)u64
```

运行时有效地址由上游保证；组件读一个字节，RAX 结果为 `byte != 0` 的
0/1（非零真值转换，非严格 bool 表示校验）。实现严格实际复用
`CR12.emit(destination=0, base, displacement, width=8, signed=false)`
后接**两次** `CR16.emit(operation=2, register=0)`。双零比较才是非零
判定：byte≠0 → 第一次比较得 0 → 第二次比较得 1；byte=0 → 第一次得 1
→ 第二次得 0。只调用一次会把语义取反，因此两次调用都强制存在。
`base=RAX` 合法：load 为单指令，地址在写 RAX 之前求值。
除 RAX 与 flags 外其它 GPR 及全部内存保持。

## 输出文本

`signed=false`、`width=8`、`destination=0`（操作数经 CR8）：

```text
movzx rax, byte [<base>]
test rax, rax
sete al
movzx rax, al
test rax, rax
sete al
movzx rax, al
```

操作数：`displacement==0` 时为 `[<base>]`；否则 `[<base> + <N>]` 或
`[<base> - <N>]`，`N` 为绝对值的 CR4 十进制（≤10 位）。

## 边界证明

- load 段最大 35 字节：`movzx ` 6 + `rax` 3 + `, ` 2 + `byte ` 5 +
  操作数 ≤18（`[r15 - 2147483648]`：括号 2 + `r15` 3 + ` - ` 3 + 10 位）
  + LF 1。局部 load 缓冲 128 字节覆盖之。
- 一段零比较恰 36 字节（register=0）：`test rax, rax\n` 14 +
  `sete al\n` 8 + `movzx rax, al\n` 14。局部 unary 缓冲 64 字节覆盖之。
- 组合文本上界 35 + 36×2 = 107 字节 ≤ 256。三段各自局部组装完成、
  容量判定通过后才一次性拷入用户 out 并写 written；任何 INVALID/
  CAPACITY 下完整 out 与 written 不变。

## 预检顺序（INVALID 优先 CAPACITY）

1. written 非 NULL、8 对齐、完整 8 字节端点不回绕；
2. out 完整声明区间端点不回绕（空可 NULL）；
3. written 与完整 out（含成功未用尾部）不重叠；
4. `base>15` 或 `base==rsp(4)` 或 `base==rbp(5)` → INVALID；
5. 位移超出 i32 范围 → INVALID；
6. 依赖调用返回非 OK 或子段超局部上界 → INVALID；
7. `llen+ulen+ulen` 回绕 → INVALID；`total>out.len` → CAPACITY。

## 范围与限制

- 有效地址可访问性由上游保证；本组件不构造、不验证地址映射。
- 不声称已接活动 IR 或完整 L3；无分配、无全局可变状态、无 OS 调用、
  不导出 C 符号（临时测试 wrapper 可导出）。
- 依赖闭包只读：CR12（及其 CR8、CR4 传递依赖）与 CR16。


## R1永久验证修复（用户授权Codex直接处理）

探针先捕获全部15个非RSP GPR（含R11），再使用scratch并写marker，独立比较片段前后RSP，最后恢复宿主callee-saved。16KiB源映射填充并快照后设置PAGE_READONLY/PROT_READ，检查保护与释放调用成功，并比较完整源映射。新增真实坏Dong追加mov r11,61453，两模式同输入先跑正式好侧，坏体正常返回后按R11保持数值拒绝。16个主要原生向量与真值/容量/预检保持；生产.dg逻辑未改。
