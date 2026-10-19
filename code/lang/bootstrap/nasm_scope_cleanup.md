# bootstrap.nasm_scope_cleanup

按 scope 规划发射零参数清理调用序列（C36）。只处理零参数、正常返回的 SysV 清理函数，不涉及捕获、some/ok/err 或完整 defer 语义。

## 依赖（只读、已集成）

- C12 `bootstrap.cleanup_plan`：直接复用 `Scope{parent,first,count}`（24 字节）与 `ROOT_PARENT = u64::MAX`；在局部 `usize[16]` 上实际调用 `plan` 得到清理顺序，树、父链、区间、环和 target 规则全部原样由 C12 判断。
- CR4 `bootstrap.decimal_integer`：清理 ID 的无符号十进制。

## 接口

```
import bootstrap.cleanup_plan as clean;
pub unsafe fn emit(scopes:[]const clean.Scope,cleanup_ids:[]const usize,
 from_scope:usize,target_scope:usize,out:[]u8,written:*usize)u64
```

状态 `OK=0`、`INVALID=1`、`CAPACITY=2`。

### 校验顺序（全部先于 CAPACITY）

1. `written` 非空、8 对齐、8 字节端点不回绕。
2. scopes（24n 字节）与 cleanup_ids（8n 字节）的乘法、端点、非空时非 NULL 与 8 对齐；out 端点不回绕，非空非 NULL（空可 NULL）。
3. 两个输入之间可以重叠；out 与 written 不能与任何输入重叠，二者之间也不能重叠（包括 out 未使用的尾部）。
4. `scopes.len` 在 1..8 之间，`cleanup_ids.len <= 16`。
5. 所有 scope 的 count 之和 ≤ 16（不仅是当前退出路径；先比较再相加，不会溢出）。
6. 每个 cleanup ID 都小于 u64::MAX，包括当前路径没用到的项。
7. C12 `plan` 必须返回 OK（全图验证、不可达父环、target 必须是自身、祖先或 ROOT_PARENT）。局部 16 槽总够用：树无环，所以路径上每个 scope 至多一次，调用数 ≤ count 总和 ≤ 16。

失败时 out 与 `*written` 全文不变，输入不变；成功只写精确前缀，尾部不变。

### 输出

空计划输出空文本，`written = 0`，out 不变。非空计划严格为：

```
sub rsp, 16
mov qword [rsp], rax
mov qword [rsp + 8], rdx
call __dong_cleanup<ID>      （每个 ID 一行，按 C12 顺序，重复 ID 重复调用）
mov rax, qword [rsp]
mov rdx, qword [rsp + 8]
add rsp, 16
```

`__dong_cleanup<ID>` 与 `__dong_b` 名称空间不同；callee 的定义与链接由上游负责。

## 运行时约定

- 入口 `rsp % 16 == 0`、DF=0；每次 call 前 rsp 仍 16 对齐，callee 入口 rsp ≡ 8 (mod 16)。
- callee 必须是零参数 void、正常返回、遵守 SysV callee-saved 与 DF=0 的函数；禁止 noreturn 或改变约定的函数。文本不验证运行时函数地址。
- 非空序列结束后 RAX/RDX 位模式与 RSP 精确恢复；其它 caller-saved 寄存器和 flags 可能改变。保存只用调用栈，可重入。

## 长度证明

- 固定六行：12 + 21 + 25 + 21 + 25 + 12 = 116。
- 每条 call：`call `(5) + `__dong_cleanup`(14) + 至多 20 位 ID（ID ≤ u64::MAX−1）+ `\n`(1) = 40。
- 至多 16 条 call，总长 ≤ 116 + 16×40 = 756 ≤ 局部文本缓冲 1024；每次追加仍检查边界。测试用 16 个 20 位 ID 覆盖恰好 756 字节的精确/少 1/0 容量。
