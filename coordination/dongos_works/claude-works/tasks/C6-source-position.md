# C6 — 原生 UTF-8 源码位置定位器

负责人：Claude。状态：已验收（2026-10-18 Codex独立复验，见 [验收](../reviews/2026-10-18-C6-acceptance.md)）。发布：2026-10-18。C1～C5均已验收，保持关闭。

只新增 `lang/bootstrap/source_position.dg`、同名 `.md`、`lang/tests/test_bootstrap_source_position.py` 及专用 `bootstrap_source_position_probe.*`，交付 `claude-works/deliveries/C6.md`，证据 `build/test/claude-c6/<唯一目录>/`。可更新本任务状态及README的C6行。现有实现/测试、Codex的 `semantic_types.dg` 运行时类型/流程、AST/绑定/模块、后端/规格/系统均只读。不运行完整回归、基准或VM，不提交/推送。可只读调用已验收 `core.utf8`；编译根显式包含 `lang` 和 `lang/std`，不修改D13。

目的：给C5提供源位置及当前行字节范围。独立组件不输出文字、不做I/O、不选错误码、不修改词法器；不接手Codex当前语义工作。

```text
module bootstrap.source_position;
pub const OK:u64=0; pub const INVALID:u64=1;
pub const UTF8:u64=2; pub const BOUNDARY:u64=3;
pub struct Position {
 pub line:usize, pub column:usize,
 pub line_start:usize, pub line_end:usize
}
pub unsafe fn locate(source:[]const u8,byte_offset:usize,out:*Position)u64
```

固定契约：

1. Position大小32、对齐8、偏移0/8/16/24。source为借用只读字节，空切片允许NULL。out是有效、自然对齐、独立可写对象，与整个source不重叠。检查非空/span/对齐/别名和 `byte_offset<=source.len` 后才能读输入；unsafe调用者保证合法区间真实可访问。
2. 严格验证**整个source**的UTF-8，包含目标偏移之后的尾部；非法编码返回UTF8。合法源上，偏移必须位于标量起点或EOF，处于多字节标量内部返回BOUNDARY。描述符/越界偏移INVALID优先于内容检查；UTF8优先于BOUNDARY。不接受替换解码。
3. line/column均从1开始，column数Unicode标量，不数UTF-8字节；TAB、CR及其它标量均计1列，只有LF换行并重置列为1，与现有原生lexer一致。CRLF由CR计一列、随后LF换行。NUL合法且计一列。不展开TAB、不按显示宽度计列、不做正规化。
4. BOM不特殊处理，U+FEFF计一个标量；调用方要与模块lexer对应时传入其已剥离BOM的unit_source，不能在这里再自动跳过。
5. line_start为当前逻辑行首字节偏移，line_end为该行LF字节位置或source.len，范围不包含LF但保留CR。偏移指向LF时仍属于前一行，column为该LF之前下一列；偏移在LF之后属于新行。EOF允许定位；尾部LF之后EOF为新空行。空source在offset0返回1/1/0/0。
6. 所有非OK返回保持out全部32字节不变，所有输入不变。成功一次发布。无分配/全局可变状态/OS调用；按源长度有界，先检查数值再相加，debug/release不得溢出panic。

有限验收：

- [x] Python严格UTF-8解码与bytes切分作独立参考。至少1000个固定种子Unicode源（中文、emoji、组合符、BOM、TAB、CR、CRLF、LF、NUL、空源/空行/EOF），每个长度不超过64字节的源覆盖所有字节偏移，包括continuation拒绝；另测长行/多行。
- [x] 非法UTF-8（过长、代理项、超界、孤立continuation、各级截断），特别是目标之前/之后的坏尾；越界offset、NULL/不对齐/溢出/别名描述符。伪造地址只用于保证预检拒绝的情形。
- [x] debug/release实际C/SysV调用，ELF64/COFF组装，结构布局核对；至少一组真实只读页。每次调用立即核输入全文和实际双端、out32字节及实际双端；失败全对象不变、成功四字段与独立期望一致，下一调用前完成观察。
- [x] 两类实际坏董实现：按UTF-8字节计列或LF位置错误；失败提前改out。两模式成功构建/链接/命中后由明确值/不变性断言拒绝；构建失败、超时或未命中不计通过。
- [x] 说明列出接口、检查顺序、BOM/CRLF/EOF和unsafe限制，交付附hash、实际命令/数量/skip、证据路径及负控拒绝位置，保持“交付待复验”。

命令 `python -m unittest lang.tests.test_bootstrap_source_position -v`。不要顺带修改C5或维护主线的回归/语料排除列表；Codex负责集成与验收。
