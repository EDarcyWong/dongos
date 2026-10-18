# core.mem — 原始字节内存原语

面向裸指针与显式长度的字节级内存操作。所有函数把内存当作无类型字节；没有分配器、libc 或 SIMD 依赖。

## 接口

```text
pub unsafe fn copy(dst:*u8, src:*const u8, count:usize) void
pub unsafe fn move(dst:*u8, src:*const u8, count:usize) void
pub unsafe fn zero(dst:*u8, count:usize) void
pub unsafe fn compare(a:*const u8, b:*const u8, count:usize) i32
```

## 语义与契约

- `copy`：把 `count` 字节从 `src` 复制到 `dst`。**源与目标区间必须互不重叠**；重叠交给 `move`。
- `move`：允许前向/后向重叠以及相同地址（自移为无操作）。按地址关系选择复制方向。
- `zero`：精确清零 `count` 字节。
- `compare`：按无符号字节做字典序比较，仅返回 `-1`、`0`、`1`。

所有函数在 `count == 0` 时不做任何内存访问，允许空指针。非零长度的地址范围、权限、映射和有效期由调用方保证；这些函数不检查，也不做 volatile 或原子访问。

## 用法示例

```text
import core.mem as mem;
var buffer: [64]u8 = [0; 64];
unsafe {
    mem.zero(&buffer[0], buffer.len);
    mem.copy(&buffer[0], source, source_len);
}
```

## 已验证

宿主测试使用独立 C 程序经 SysV 接口调用，覆盖零长度（空指针）、非对齐偏移、相邻哨兵字节、相等/不同内容、多个长度、两个方向的重叠以及完全自移；`debug` 与 `release` 两种模式均通过。
