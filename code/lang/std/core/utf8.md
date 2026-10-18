# core.utf8 — 严格 UTF-8 编解码与验证

模块 `core.utf8`。只接受最短编码的 U+0000..U+10FFFF 标量；拒绝代理项 U+D800..U+DFFF、过长编码、C0/C1、F5..FF、错误/孤立 continuation 与截断。不做替换字符容错、不跳过 BOM、无分配、无全局状态、无宿主调用。

## 结构

```text
pub struct Decode { pub scalar:u32, pub width:usize }
```

x86-64 下大小 16 字节、对齐 8，字段偏移 0/8；中间 4 字节 padding 从不被改写。

## 接口

```text
pub unsafe fn decode(bytes:[]const u8, start:usize, out:*Decode)bool
pub unsafe fn encode(scalar:u32, output:[]u8, written:*usize)bool
pub fn validate(bytes:[]const u8)bool
```

`out` / `written` 是调用者提供的有效、自然对齐、已初始化、可写且与输入/输出字节区间不重叠的对象；切片是有效可访问视图，零长度允许 NULL。不探测任意伪造切片或不可访问宿主指针。

## 契约

- `decode` 只解析 `start` 处一个标量：成功时 `scalar` 为 Unicode 标量、`width` 为 1..4，不扫描前缀，也不要求后缀合法。`start >= len`（含 usize 最大值）、起始字节为 continuation、非法/截断编码均返回 false，整个 `Decode`（含 padding）不变，输入字节不变。边界判断用 `bytes.len - start`，不会先算 `start+width` 溢出。
- 仅接受最短编码：`EF BB BF` 解为普通 U+FEFF，嵌入 NUL 是普通 U+0000；未分配字符与非字符仍是合法标量。
- `encode` 对合法标量输出唯一最短 UTF-8。容量足够时只写 `width` 个字节并写 `*written=width`，其余 output 字节不变；非法标量或容量不足返回 false，整个 output 与 `written` 不变。所有检查（标量范围、代理项、容量）完成后才发布字节或计数。
- `validate` 对整条切片逐标量解码：空切片 true，其余仅当所有字节组成完整严格 UTF-8 时 true。所有输入只读。

## 验证

永久测试 `lang/tests/test_std_utf8.py`：

- `test_module_compiles_and_assembles`：模块编译后以 elf64 / win64 组装。
- `test_native_utf8`：期望数据由**独立 Python 严格 UTF-8** 编解码生成（不复制实现算法）：遍历全部 1112064 个合法标量的 encode→bytes/width 与 decode 反向；全部 65536 个双字节组合的 decode-at-0 与整串 validate；三/四字节边界、过长、代理项、>10FFFF、错误 continuation、每级截断、BOM/NUL/非字符；decode 起点 len/len+1/USIZE_MAX/continuation；encode 精确/少一/空容量与非法标量原子性；失败时 Decode 全 16 字节、output 全内容与前后 guard 立即检查，成功核预期前缀与未写尾部。debug/release 实际原生执行，核对 16 字节布局。
- `test_negative_controls`：两类临时坏 Dong 实现（放行代理项；encode 容量失败前先写 `*written`）在 debug/release 均成功编译链接、实际命中后被原生断言拒绝。

运行命令：`python -m unittest lang.tests.test_std_utf8 -v`。详见 `deepseek-works/deliveries/D13.md`。

本模块不替换 `bootstrap.lexer` 或 Unicode 分类表，未接入编译器或内核。
