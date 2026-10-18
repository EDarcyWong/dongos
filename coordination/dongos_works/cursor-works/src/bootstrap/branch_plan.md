# bootstrap.branch_plan：确定性条件分支与落空边规划

根据比较谓词与 yes/no/fallthrough 块号，规划是否发出条件跳转与无条件跳转。不调整 CFG、不删除源比较副作用。模块不导出 C 符号。

```text
module bootstrap.branch_plan;
pub struct Plan {
  pub has_cond:u64, pub condition:u64, pub cond_target:u64,
  pub has_jump:u64, pub jump_target:u64
}  // 40 bytes, 8-byte aligned
pub unsafe fn plan(condition:u64, yes:u64, no:u64, fallthrough:u64, out:*Plan)u64
```

`condition` 枚举：0 EQ、1 NE、2 ULT、3 ULE、4 UGT、5 UGE、6 SLT、7 SLE、8 SGT、9 SGE。逆谓词 0↔1、2↔5、3↔4、6↔9、7↔8。`fallthrough==u64::MAX` 表示无落空块。`yes`/`no` 不得为 `u64::MAX`。

## 规则

- `yes==no`：无条件分支；若无落空或目标 ≠ fallthrough，则一次无条件跳转至 yes。
- `yes!=no` 且 `no==fallthrough`：原条件跳 yes，无额外跳转。
- `yes!=no` 且 `yes==fallthrough`：逆条件跳 no，无额外跳转。
- 其余：原条件跳 yes，再无条件跳 no。
- 未使用字段为 0；`has_cond`/`has_jump` 仅为 0 或 1。

## 检查

`out` 非空、8 对齐、完整 40 字节区间有效；枚举/目标非法 → `INVALID`，`out` 全文不变。无分配、无 OS。
