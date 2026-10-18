# bootstrap.sleb128_decode：有界最短 SLEB128 i64 解码

```text
module bootstrap.sleb128_decode;
pub const OK:u64=0; pub const INVALID:u64=1; pub const TRUNCATED:u64=2;
pub const OVERFLOW:u64=3; pub const NONCANONICAL:u64=4;
pub unsafe fn decode(input:[]const u8, value:*i64, consumed:*usize)u64
```

只解码最短 SLEB128 i64（有符号），是主线 `bootstrap.leb128` 编码器与 `bootstrap.uleb128_decode` 无符号解码器的有符号补全；不负责文件/DWARF/CLI/后端。

## 编码格式

每字节低 7 位为载荷、bit7 为继续位。最多扫描 10 字节；前 9 字节低位在前累积载荷，终止字节的载荷 bit6 是符号位。第 10 字节只决定 64 位结果的 bit63，因此其继续位必须为 0 且载荷必须为 0（正）或 127（负）。

## 状态与优先级

1. `INVALID`（描述符）：任一输出为空/未 8 对齐/8 字节端点溢出；完整 input 端点溢出（空可 NULL）；完整 input 与两输出、两输出之间两两分离。描述符不合法不读输入。
2. 扫描（每次一字节，最多 10 次）：
   - 到第 10 字节（下标 9）：继续位=1 或载荷不是 0/127 → `OVERFLOW`（优先于最短性判定）。
   - 其它字节：继续位=1 → 累加载荷、移位 +7；继续位=0（终止）→ 按符号位做二进制补码解释。
   - 未遇终止且 input 耗尽（不足 10 字节，含空）→ `TRUNCATED`。
3. 最短性：终止长度 >1 时，末载荷为 0 且前一字节 bit6=0，或末载荷为 127 且前一字节 bit6=1 → `NONCANONICAL`（适用于第 2..10 字节；单字节 00/7F 分别是规范 0/-1）。
4. 成功：`*value` 为精确 i64 值，`*consumed` 为 1..10，忽略终止字节之后的 input。

禁止移位 >=64 或溢出移位后才检查：前 9 字节移位为 7*i（i=0..8），符号扩展用 `MAX<<(shift+7)`（shift+7 最大 63），第 10 字节用常量 bit63。

## 原子性

非 OK 不修改 input 或两个输出的任何字节；成功只写两个输出字段。值在局部暂存中累积，完全验证后再写回。无分配/全局可变状态/OS 调用，模块不导出 C 符号，测试经临时 wrapper 导出 `dong_sleb128_decode`。
