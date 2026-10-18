# core.int — usize 检查算术与 2 次幂对齐

无符号 `usize` 的溢出检查算术与对齐辅助。检查本身先于可能溢出的运算执行，因此不会先触发 debug 溢出或除零 panic。

## 接口

```text
pub fn is_power_of_two(value:usize) bool
pub unsafe fn add_checked(a:usize, b:usize, out:*usize) bool
pub unsafe fn sub_checked(a:usize, b:usize, out:*usize) bool
pub unsafe fn mul_checked(a:usize, b:usize, out:*usize) bool
pub unsafe fn align_up(value:usize, alignment:usize, out:*usize) bool
pub unsafe fn align_down(value:usize, alignment:usize, out:*usize) bool
```

## 语义与契约

- 检查算术：成功返回 `true` 并写入 `*out`；失败（溢出）返回 `false` 且**保持 `*out` 不变**。调用方提供有效、可写、已初始化的输出对象。
- `is_power_of_two`：`0` 返回 `false`。
- 对齐只接受非零的 2 次幂；非法 `alignment` 返回 `false`。`align_up` 在结果溢出 `usize` 时失败，`align_down` 向下取整且不会溢出。
- 对齐不使用浮点或除法实现，也不把整数对齐限制到结构体的 4096 上限。

## 用法示例

```text
import core.int as int;
var out: usize = 0;
if int.align_up(size, 4096, &out) { /* out 为向上对齐的页数 */ }
```

## 已验证

宿主测试用独立 C 参考计算核对边界值（0、1、`usize` 最大值、相邻值）、各 2 次幂、非法 alignment、溢出与失败时输出不变，并以确定种子随机输入交叉验证；两种模式均通过。
