# CR1 — 原生 NASM 字节常量编码器

负责人：Cursor。状态：交付待复验（R1 已补交）。发布：2026-10-18。

目标：为 L3 后端提供无歧义的二进制字节常量文本。只负责把借用字节编码为 NASM `db` 行，不生成标签、重定位、节、字符串结束符或完整汇编文件；不接手 Codex 的语义/后端主线。

## 文件归属

仅新增：

- `cursor-works/src/bootstrap/nasm_bytes.dg` 和同目录 `nasm_bytes.md`。
- `cursor-works/tests/test_nasm_bytes.py`；如需独立 C/NASM 探针，放在该 tests 目录且使用 `nasm_bytes_probe` 前缀。
- `cursor-works/deliveries/CR1.md`，本任务状态和 README 的 CR1 行。

生成 wrapper、坏董副本、可执行文件、日志和回执放 `build/test/cursor-cr1/<唯一运行目录>/`。编译根明确指定 `cursor-works/src` 与临时 wrapper 根。既有源码只读，不把文件先放到 `lang/bootstrap/` 或 `lang/tests/`；主线集成由 Codex 验收后进行。不要改主线语料排除列表或完整回归脚本。

## 固定接口与契约

```text
module bootstrap.nasm_bytes;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub unsafe fn encode(source:[]const u8, out:[]u8, written:*usize)u64
```

1. source 是任意字节，不做 UTF-8 验证或替换。每行最多16字节，精确格式 `db 0xHH,0xHH\n`：`db ` 小写，`0x` 小写，十六进制 A～F 大写，逗号后无空格，LF结束；每字节恰好两位。最后一行也有LF。不加BOM、NUL、引号、标签或注释。空输入输出长度0，不写out。
2. 例：字节 `[0,10,255]` 输出 ASCII `db 0x00,0x0A,0xFF` 后跟一个LF。16字节恰好一行；17字节两行，第二行只有最后一个字节。
3. 需要长度为 `5*N + 3*ceil(N/16)`，N=0时为0。所有乘法、加法及端点先检查溢出；不能用 `(N+15)/16` 的未检查加法。需要长度不可表示为usize时返回INVALID，且不能读取输入。
4. source/out 非空时指针非NULL且区间端点不溢出，空切片允许NULL。written 是有效、自然8字节对齐且完整可写的独立usize对象。整个 source、整个 out 描述区间及 written8字节必须彼此不重叠，即使 out 的剩余容量不会使用也不允许重叠。完成所有描述符/span/对齐/别名及长度预检后才能读输入或写任何对象；INVALID优先于CAPACITY。
5. out.len 小于需要长度返回CAPACITY。所有非OK返回保持整个 out、written 和输入全文不变。成功只写 out 的精确有效前缀，written为长度；out剩余部分不变。输入始终不变。空输入也必须做完整描述符检查，成功写written=0。
6. 不分配、不依赖全局可变状态、不做OS/文件I/O；O(N)，debug/release无溢出panic。unsafe调用方保证通过预检的区间真实可访问，不能以span检查替代地址有效性保证。公开接口不导出C符号；测试通过临时wrapper调用。

## 有限验收

- [x] Python 独立按每16字节分组和十六进制格式生成期望。至少1000个固定种子二进制输入，长度0～2048；覆盖全部256字节、NUL/引号/反斜杠/换行/非UTF-8，以及0/1/15/16/17/31/32/33、全0/全FF和多行。分别测精确、少一及多余容量；所有返回点立即检查内容和实际双端，不能只检查written。
- [x] NULL/奇地址written、NULL非空切片、区间端点/需要长度溢出、各类别名、空输入、不足容量。伪造地址仅用于确保预检拒绝的路径，不能实际读写。失败保持整个out/written不变，输入只读；至少一组真实只读输入页。检查优先级。
- [x] debug/release真实Dong→C/SysV原生运行，两种ELF64/COFF均组装。额外从不少于100个代表性输入取**董实际输出**，用已装NASM `-f bin` 汇编成原始二进制，逐字节还原source；空输出汇编结果也应为空。不能拿Python期望代替董输出去做往返。
- [x] 两类真实董坏实现：错误十六进制/16字节分行；容量失败提前写out或written。每类至少一个确定用例，debug/release成功编译链接执行，正式实现先通过同用例，坏实现命中后由对应内容或原子性断言拒绝。保留命中证据；构建失败/崩溃/超时不算通过。
- [x] 说明接口、字节格式、长度公式、检查顺序、失败原子性和unsafe限制；交付附hash、命令、真实数量/skip及证据，保持“交付待复验”。

建议命令：`python -m unittest discover -s cursor-works/tests -p test_nasm_bytes.py -v`。只跑本项，不修改已验收组件，不运行OS/VM或完整回归，不提交/推送。


## R1：Codex独立复验返修

2026-10-18，原4项测试通过，但独立坏董实证输出尾部别名漏检；空输出24个案例未实际调用NASM；需要长度溢出夹具被更早别名检查遮住。按[独立复验](../reviews/2026-10-18-CR1-R1.md)修复这三个原契约缺口，仅复用原有限案例，不扩展矩阵或修改正式算法。保留原交付，在deliveries/CR1.md追加R1及真实命令/数量/hash/证据，保持待Codex复验。
