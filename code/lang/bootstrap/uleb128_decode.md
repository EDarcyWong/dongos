# bootstrap.uleb128_decode：有界最短 ULEB128 u64 解码

```text
module bootstrap.uleb128_decode;
pub const OK:u64=0; pub const INVALID:u64=1; pub const TRUNCATED:u64=2;
pub const OVERFLOW:u64=3; pub const NONCANONICAL:u64=4;
pub unsafe fn decode(input:[]const u8, value:*u64, consumed:*usize)u64
```

只解码最短 ULEB128 u64（无符号），不负责 SLEB128、文件或调试节。编码由主线 `bootstrap.leb128` 负责，本模块不重复。

## 编码格式

每个字节的低 7 位是载荷，bit7 是继续位。最多扫描 10 字节：前 9 字节任意，第 10 字节只贡献 bit 63，因此其载荷只能为 0 或 1 且必须终止。

## 状态与优先级

1. `INVALID`（描述符）：任一输出为空/未 8 对齐/8 字节端点溢出；完整 input 声明区间端点溢出（空 input 可为 NULL）；完整 input（不只已解码前缀）与两个输出两两分离。描述符不合法不读取任何输入字节。
2. 扫描（每次读一个字节，最多 10 次）：
   - 到第 10 字节（下标 9）：该字节继续位=1 或载荷>1 → `OVERFLOW`（优先于终止/规范检查）；否则载荷为 0 → `NONCANONICAL`，载荷为 1 → 成功。
   - 其它字节：继续位=1 → 累加载荷、移位 +7 继续；继续位=0（终止）→ 若非首字节且载荷=0 → `NONCANONICAL`，否则成功。
   - 未遇终止且 input 耗尽（不足 10 字节，含空 input）→ `TRUNCATED`。
3. 成功：`*value` 为无符号组合，`*consumed` 为 1..10，忽略剩余 input。

禁止移位 >= 64 或先移位后查溢出；移位为 7*i（i=0..8），第 10 字节用常量 bit63，不会达到 64。

## 原子性

非 OK 时两个输出全文不变，input 只读；成功只写两个输出字段，无 CAPACITY 码。先预检再写，值在局部暂存中累加，全部通过后才写 `*value`/`*consumed`。循环最多 10 次，无分配、无全局可变状态、无 OS 调用。模块不导出 C 符号，测试经临时 wrapper 导出 `dong_uleb128_decode`。

示例：00→0/1；80 01→128/2；80 00→NONCANONICAL；FF×9 01→u64 最大/10；80×9 02、80×10→OVERFLOW；80×9→TRUNCATED。
