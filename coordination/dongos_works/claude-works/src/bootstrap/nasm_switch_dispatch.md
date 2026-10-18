# bootstrap.nasm_switch_dispatch

有界线性 i64 switch 分发链（C35）：把 RDI 里的运行时 selector 路由到 `__dong_b<label>` 块。

## 依赖（只读、已集成）

- C11 `bootstrap.switch_cases.order`：在局部 `Case[16]` 输出与 `Case[16]` work 上实际调用，按 signed i64 升序排序并拒绝重复 value。本模块不重写排序或查重。
- CR9 `bootstrap.nasm_integer_load.emit(0, value as u64, 64, true, local, &n)`：生成 `mov rax, <有符号十进制>`，MIN、负数和高位位模式都完整装入，不依赖无法编码的 `cmp r64, imm64`。
- CR4 `bootstrap.decimal_integer.encode`：label 与 default 的无符号十进制（无前导零）。

## 接口

```
import bootstrap.switch_cases as cases;
pub unsafe fn emit(input:[]const cases.Case,default_target:u64,out:[]u8,written:*usize)u64
```

`Case` 就是 C11 的 `{value:i64,label:usize}`（16 字节、8 对齐）。状态 `OK=0`、`INVALID=1`、`CAPACITY=2`。

### 校验顺序（全部先于 CAPACITY）

1. `written` 非空、8 对齐、8 字节端点不回绕。
2. `input.len <= MAX/16`；input 字节区间端点不回绕，非空时非 NULL 且 8 对齐；out 端点不回绕，非空非 NULL（空可 NULL）。
3. `written` 与完整 out 不重叠（包括未使用尾部），input 与 out、input 与 written 都不重叠。
4. `input.len <= 16`；`default_target` 与每个 label 都不能等于 u64::MAX（空输入也校验 default）。
5. C11 `order` 返回 OK 且 `used == input.len`；重复 value（不论 label 是否相同）返回 INVALID。局部容量总是足够，所以依赖查重一定发生在任何用户 CAPACITY 之前。

失败时 out 与 `*written` 全文不变，输入不变；成功只写精确前缀，尾部保持。

### 输出

按 signed i64 升序，每个 case 三行：

```
mov rax, <value>
cmp rdi, rax
je __dong_b<label>
```

最后一行 `jmp __dong_b<default>`。允许多个 case 或 default 指向同一个块。不输出块定义、跳表、fallthrough 或任何策略优化。运行时只有 RAX 和 flags 改变，RDI 及其它寄存器保持。

## 长度证明

- `mov rax, -9223372036854775808\n` = 4+3+2+20+1 = 30（CR9 单行临时缓冲 40）。
- `cmp rdi, rax\n` = 13。
- `je __dong_b18446744073709551614\n` = 11+20+1 = 32（最大合法 label 是 u64::MAX−1，20 位）。
- 每个 case 至多 75；末尾 `jmp __dong_b<20 位>\n` = 33。
- 总长至多 16×75+33 = 1233 ≤ 局部文本缓冲 1280；每次追加仍检查边界。测试用 16 个 20 字符 value 加 20 位 label（恰好 1233 字节）覆盖精确/少 1/0 容量。
