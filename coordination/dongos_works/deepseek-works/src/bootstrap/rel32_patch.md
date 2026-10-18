# bootstrap.rel32_patch：同一缓冲区内的 rel32 补丁

```text
module bootstrap.rel32_patch;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub struct Patch { pub at:usize, pub target:usize }   // 16 字节、对齐 8；均为 code 内偏移
pub unsafe fn apply(code:[]u8, patches:[]const Patch, applied:*usize)u64
```

每项把 `code[at..at+4)` 写成 `target-(at+4)` 的有符号 i32 小端补码。target 可为 `0..=code.len`（含末端标签）。只做补丁：不生成指令、不读文件、不做真实地址重定位。成功时 `*applied = patches.len`，补丁区以外的字节不变。

## 检查顺序

全部为 `INVALID`，任何一项失败 code 全文与 applied 都不变：

1. 描述符：`applied` 非空、8 字节对齐；patches 非空时 8 字节对齐；`patches.len*16` 与 code/patches/applied 各区间端点不溢出；空切片可为 NULL。code 与 applied 都可写，二者彼此不重叠，也不与只读 patches 的整个声明区间重叠。
2. 每一项单独：`code.len >= 4 且 at <= code.len-4`（因此 `at+4` 不会回绕）；`target <= code.len`；位移在 `[-2^31, 2^31-1]`。位移以无符号运算求出：`target >= at+4` 时差值 ≤ `0x7fffffff`，否则 `at+4-target` ≤ `0x80000000`，负值写为 `2^32-差值`。
3. 所有项两两比较（与输入顺序无关）：`a < b+4 且 b < a+4` 即四字节区间共享字节，含重复 at，均 INVALID。

以上全部通过后才原位写四字节。本接口没有输出容量概念，`CAPACITY` 仅为公共状态常量，不会返回。

## 复杂度与限制

时间 O(patches.len²)，与 code.len 无关；不扫描 code、无工作区、无分配、无全局可变状态、无 OS 调用。unsafe 调用方须保证通过数值预检后实际访问的 `code[at..at+4)` 与 patches 内存可访问。模块本身不导出 C 符号，测试经临时 wrapper 导出 `dong_rel32_apply`。
