# bootstrap.nasm_branch_emit：由分支规划生成可执行 NASM 条件跳转

在已集成的 `bootstrap.branch_plan`（CR6）之上发射 NASM 跳转文本；块号标签数字由 `bootstrap.decimal_integer`（CR4）编码。不重写逆谓词或落空规划。模块不导出 C 符号。

```text
module bootstrap.nasm_branch_emit;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn emit(condition:u64, yes:u64, no:u64, fallthrough:u64, out:[]u8, written:*usize)u64
```

## 行为

1. 先调用 `branch_plan.plan(...)`；失败 → `INVALID`（不写 `out`）。
2. 使用 **Plan 内** 的 `condition`（可能已相对输入求逆）、`cond_target`、`jump_target`。
3. `has_cond=1` 时输出一行：`<mnemonic> __dong_b<十进制>\n`
4. `has_jump=1` 时再输出：`jmp __dong_b<十进制>\n`
5. 未启用的行完全省略。两行皆无时成功 `*written=0` 且 `out` 全文不变。

助记符按 `Plan.condition`：`je,jne,jb,jbe,ja,jae,jl,jle,jg,jge`（0..9）。换行为真实 `0x0A`。

## 检查顺序

`written` / `out` 描述符与别名 → `plan` → 数字编码与总长溢出 → `CAPACITY`。`INVALID` 先于 `CAPACITY`。子结果先入栈暂存，再一次写入用户缓冲。
