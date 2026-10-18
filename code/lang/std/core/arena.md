# core.arena — 调用方缓冲区线性 arena

模块 `core.arena`。线性 arena 只记录 `base/capacity/used`，在调用者提供的缓冲区上按对齐切分字节；不做分配、扩容、清零、析构、加锁或 OS 调用，也没有全局状态。

## 结构

```text
pub struct Arena { pub base:*u8, pub capacity:usize, pub used:usize }
```

x86-64 下大小 24 字节、对齐 8，字段偏移 0/8/16。

## 接口

```text
pub unsafe fn init(arena:*Arena, storage:[]u8)bool
pub unsafe fn allocate(arena:*Arena, size:usize, alignment:usize, out:*usize)bool
pub unsafe fn rewind(arena:*Arena, mark:usize)bool
```

`out` 是分配区首地址的整数表示；调用者按目标类型转换指针。

## 契约

- `arena` 与 `out` 必须是调用者提供的有效、自然对齐、已初始化、可写且互不重叠的独立对象，且不在 storage 中；这是 unsafe 前提，不探测任意非法宿主地址。
- `init` 接受调用者拥有的可写 storage。非空时指针必须非空，且 `base+capacity` 不溢出；非法区间返回 false 并保持 Arena 全部字节不变。成功设置 base/capacity 并令 used=0。任何操作都不改写 storage 的字节。
- `allocate` 先核对 `used <= capacity`、base/capacity 区间合法（空 NULL 仅当 capacity 为 0）、`alignment` 为非零 2 次幂；随后先检查对齐舍入、padding、size 与剩余容量，再计算，debug/release 都不会先溢出或 panic。成功时 `p=align_up(base+used, alignment)` 且 `p+size<=base+capacity`，只写 `*out=p` 与 `used=(p-base)+size`，保留 base/capacity；失败保持整个 Arena、out 与 storage 不变。
- `size=0` 也走同一公式，可能消耗对齐 padding，允许返回恰好等于 end 的地址，但该地址不可解引用或访问。空 NULL arena 仅 `size=0` 且无需 padding 的分配可成功（返回 0）。零大小结果不能用于存储。
- `rewind` 要求 `mark <= used <= capacity` 且区间合法；成功只把 used 设为 mark，否则 false 并保持不变。mark 是字节偏移而非代次保护句柄，回退后旧对象不得再用；没有并发或自动生命周期保证。

## 验证

永久测试 `lang/tests/test_std_arena.py`：

- `test_module_compiles_and_assembles`：模块编译后以 elf64 / win64 组装。
- `test_native_arena`：独立 C 模型计算地址/padding/成功失败/新 used，debug/release 原生调用，核对 24 字节布局与偏移；覆盖空/非空/溢出 init，真实非对齐 base，连续混合 size/alignment，精确/差一容量，非法 0 与非 2 次幂 alignment，零大小，NULL 空区间，rewind 前后复用，极值虚拟 base 与 used>capacity 的数值拒绝，以及固定种子 300 + 1200 步序列；每次调用后立即核对 Arena 全字节、out、storage 全内容与前后 guard。
- `test_negative_controls`：两类临时坏 Dong 实现（按偏移对齐；在检查前提前写 out）在 debug/release 均成功编译链接、实际命中后被原生断言拒绝。

运行命令：`python -m unittest lang.tests.test_std_arena -v`。详见 `deepseek-works/deliveries/D12.md`。

本模块未接入编译器或活动内核；L3 接入由 Codex 负责。
