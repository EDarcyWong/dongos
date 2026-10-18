# C1 — 任意精度有符号除法和余数

负责人：Claude。状态：已验收（2026-10-18 Codex 独立组件验收，见[记录](../reviews/2026-10-18-C1-C2-acceptance.md)）。发布：2026-10-18。领取：2026-10-18。交付：2026-10-18，见 [deliveries/C1.md](../deliveries/C1.md)。

先读 [共同约定](../CONTRACT.md)。只新增 `lang/bootstrap/bigint_div.dg`、`lang/bootstrap/bigint_div.md`、`lang/tests/test_bootstrap_bigint_div.py`，必要时新增专用 `lang/tests/bootstrap_bigint_div_probe.c` / `.asm`，以及 `claude-works/deliveries/C1.md`。不改 C2 或 Codex 核心文件。

## 固定接口

```text
module bootstrap.bigint_div;
import bootstrap.bigint as big;
pub const DIV:u64=1;
pub const REM:u64=2;
pub const DIVZERO:u64=5;
pub unsafe fn calculate(operation:u64, negative_a:bool, a:[]const u32,
 negative_b:bool, b:[]const u32, out:[]u32, work:[]u32, result:*big.Result)u64
```

DIV 向零截断；REM 满足 `a = q*b + r`、`abs(r)<abs(b)`，非零余数符号随被除数。零除数返回 DIVZERO，不能触发 CPU 除零或 panic；零结果不带负号。与 `lang/dongc/model.py` 中 integer_div / constant_op 的整数数学一致，Python 负数 `//` 和 `%` 不能直接作为该语义参考。任意精度层不执行目标 i64 最小值/-1 的位宽溢出规则，目标类型范围检查留给 Codex。

可使用按位长除法或多 limb 算法，不按商值逐次减法。无损处理多 limb 除数、商的高零与余数规范化。公开函数仅此一项，其余私有。

## 本项验收

- [ ] 共同存储与失败原子性契约完整成立，两模式实际原生执行、两格式组装，真实 SysV 切片/栈参数及 Result 布局有效。
- [ ] 四种符号、0/±1、a<b、相等、整除/非整除、2 的幂与相邻值、32/64 位跨 limb、长零/全一 limb、至少一组 4096 位；固定种子至少 500 对数，同时核 DIV/REM 及独立期望。
- [ ] 零除数、负零/高零输入、非法 opcode、精确与差一 out/work、描述符拒绝；每次返回立即核共同约定中的完整内容/guard。不只验证 `q*b+r`，还要验证准确 q/r、范围和符号。
- [ ] 至少两类实际坏源码负控：商/余数符号或截断错误；失败提前发布 output 或 Result。两模式都实际命中并因指定断言拒绝。
- [ ] 文档给 workspace 上界、状态优先顺序、限制；交付登记完整并保持待复验。

命令：`python -m unittest lang.tests.test_bootstrap_bigint_div -v`。不要求本任务接入语义检查器或关闭 L3；集成由 Codex 完成。
