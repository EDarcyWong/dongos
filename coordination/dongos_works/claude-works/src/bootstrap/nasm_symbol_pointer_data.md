# bootstrap.nasm_symbol_pointer_data

带完整 64 位重定位的静态符号指针声明（C38）：输出一个存储标签和一个 `dq <目标符号> ± addend`，让汇编器产生 64 位绝对重定位，不会被静默截成 32 位。C29 的 RIP 相对 LEA 只能在运行时算地址，表达不了全局指针、函数指针或聚合里的地址常量，这正是本模块补上的部分。不新增对象文件或链接器实现。

## 依赖（只读、已集成）

- CR3 `bootstrap.nasm_symbol.encode`：storage 与 target 符号都是它对（模块名, 条目名）原始字节的编码 `__dong_m<hex>_n<hex>`，不散列、不截断。
- CR4 `bootstrap.decimal_integer.encode`：addend 幅度的无符号十进制。

## 接口

```
pub unsafe fn emit(storage_module:[]const u8,storage_item:[]const u8,
 target_module:[]const u8,target_item:[]const u8,addend:i64,
 out:[]u8,written:*usize)u64
```

状态 `OK=0`、`INVALID=1`、`CAPACITY=2`。

### 校验顺序（全部先于 CAPACITY）

1. `written` 非空、8 对齐、8 字节端点不回绕。
2. 四个名字与 out 的端点不回绕，非空时非 NULL（空 out 可 NULL）。
3. 四个名字之间可以重叠（storage 与 target 也可以完全相同）；out、written 与每个名字都不重叠，二者之间也不重叠（包括 out 未使用尾部）。
4. 每个名字长度 1..64（原始字节，允许 NUL 与非 ASCII）。
5. 两次 CR3 编码都必须 OK。

失败时 out 与 `*written` 全文不变，名字不变；成功只写精确前缀，尾部不变。

### 输出

```
<storage_symbol>:
dq <target_symbol>
```

- addend 为 0 时第二行就是上面这样。
- 正数：`dq <target_symbol> + <addend>`。
- 负数：`dq <target_symbol> - <幅度>`，幅度用 `wrapping_sub(0, addend as u64)` 求得，i64::MIN 不会在 debug 下做有符号求负。
- 存储的位模式是 `(address(target) + addend) mod 2^64`，文本显式使用 64 位 `dq`。

不输出 section、global、extern 或 align，这些由上游决定；target 必须由上游定义并链接。本组件只发射上游已经验证过的符号重定位，不新增语言层地址转整数或一般编译期指针算术的权限，也不宣称加载器或完整镜像模型已经完成。

## 长度证明

- 两个 64 字节名字的 CR3 符号是 10 + 2×(64+64) = 266 字节（两个局部符号缓冲各 266）。
- 标签行：266 + `:\n` = 268。
- 数据行：`dq `(3) + 266 + ` - `(3) + 19 位（i64::MIN 的幅度 9223372036854775808）+ `\n` = 292；正数最大 i64::MAX 也是 19 位。
- 总长 ≤ 560 ≤ 局部文本缓冲 576；数字暂存 20 ≥ 19。每次追加仍检查边界。测试用四个 64 字节名字配 addend=MIN 与 MAX（都恰好 560 字节）覆盖精确/少 1/0 容量。

## 汇编注意

NASM 3 的 `-Wall` 会对每个 64 位绝对重定位给出 `reloc-abs-qword` 警告；这恰是 `dq` 指针数据需要的重定位，测试夹具只放宽这一项警告，其余仍按 `-Wall -Werror`。
