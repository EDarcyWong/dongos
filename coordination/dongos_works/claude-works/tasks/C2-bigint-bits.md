# C2 — 任意精度位运算和移位

负责人：Claude。状态：已验收（2026-10-18 Codex 独立组件验收，见[记录](../reviews/2026-10-18-C1-C2-acceptance.md)）。发布：2026-10-18。领取：2026-10-18。交付：2026-10-18，见 [deliveries/C2.md](../deliveries/C2.md)。

先读 [共同约定](../CONTRACT.md)。只新增 `lang/bootstrap/bigint_bits.dg`、`lang/bootstrap/bigint_bits.md`、`lang/tests/test_bootstrap_bigint_bits.py`，必要时专用 `lang/tests/bootstrap_bigint_bits_probe.c` / `.asm`，以及 `claude-works/deliveries/C2.md`。不改 C1 或 Codex 核心文件。

## 固定接口

```text
module bootstrap.bigint_bits;
import bootstrap.bigint as big;
pub const AND:u64=1;
pub const OR:u64=2;
pub const XOR:u64=3;
pub unsafe fn bitwise(operation:u64, negative_a:bool, a:[]const u32,
 negative_b:bool, b:[]const u32, out:[]u32, work:[]u32, result:*big.Result)u64
pub unsafe fn invert(negative:bool, a:[]const u32,
 out:[]u32, work:[]u32, result:*big.Result)u64
pub unsafe fn shift(left:bool, negative:bool, a:[]const u32, amount:usize,
 out:[]u32, work:[]u32, result:*big.Result)u64
```

bitwise/invert 与 Python 无限符号扩展的补码整数 `& | ^ ~` 一致，输入输出仍为规范符号/幅值；`~0=-1`、`~-1=0`，不能直接对幅值逐 limb 取反作为有符号结果。临时补码宽度应包含足够符号扩展位，成功转换回规范幅值。invert/shift 的共同区间检查按单输入应用。

shift 的 left=true 为精确数学左移，false 为算术右移（负数向负无穷取整）。amount 是非负 usize，至少正确处理 0/1/31/32/33/63/64/65、超过有效位数和 usize 最大值。大右移非负值归零、负值归 -1；零左移任意 amount 仍零。非零巨大左移不能先计算 `amount+bits` 溢出或尝试无界循环；用可证明的工作区上界安全返回 WORKSPACE。具体目标位宽和移位次数诊断由 Codex 在语义层负责，组件不把精度固定成 64 位。

## 本项验收

- [ ] 共同存储与失败原子性契约、两模式原生、双格式组装、SysV ABI 与 Result 布局通过。
- [ ] 0/±1、正负不等宽、32/64 位交界、2 的幂及相邻值、全一/长零、至少 4096 位；固定种子至少 500 对，三种二元运算、invert、左右移与独立 Python 期望逐值比较。
- [ ] 所列移位边界及极大 amount、负数被丢弃位全零/非零（例如 -4>>1 与 -3>>1），非法 opcode/规范表示、精确/差一 out/work，以及共同描述符拒绝。每次返回立即核全部内容/guard，不用双重取反或左右移互逆替代独立期望。
- [ ] 至少两类实际坏源码负控：遗漏负数符号扩展/算术右移舍入；失败提前修改 output/Result。两模式实际命中且指定断言拒绝。
- [ ] 文档给各操作 workspace 上界、状态顺序与极大移位处理；交付登记完整，保持待复验。

命令：`python -m unittest lang.tests.test_bootstrap_bigint_bits -v`。不要求接入词法器/语义器或自举流水线，Codex 后续集成。
