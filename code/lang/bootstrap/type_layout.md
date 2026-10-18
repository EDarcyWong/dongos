# bootstrap.type_layout：无分配的目标类型布局引擎

对已解析、已消除别名的类型描述符计算 x86-64 布局，规则与 `lang/dongc/typesys.py` 一致。不解析 AST、不查名字、不做常量求值。

```text
module bootstrap.type_layout;
pub struct Type { pub kind:u64, pub element:usize, pub count:usize,
 pub first:usize, pub length:usize, pub alignment:usize, pub is_packed:bool }   // 56 字节，is_packed 偏移 48
pub struct Field { pub typ:usize }                                              // 8 字节
pub struct Layout { pub size:usize, pub alignment:usize }                      // 16 字节
pub unsafe fn calculate(types:[]const Type, fields:[]const Field,
 layouts:[]Layout, offsets:[]usize, work:[]Layout, work_offsets:[]usize,
 states:[]u8, max_depth:usize)u64
```

**与任务书的唯一差异**：任务书中的字段名 `packed` 是 Dong 保留关键字，不能作字段名（`pub struct Type{pub packed:bool}` 报 `E0101 expected 'identifier', found 'packed'`），所以改名为 `is_packed`。类型、偏移（48）和整体布局（56/8）不变，C 侧二进制接口完全相同。

## 描述符

`kind`：1..4 = u8/u16/u32/u64，5 = bool，6 = pointer，7 = function pointer，8 = slice，9 = optional，10 = result，11 = array，12 = struct，13 = enum。`NONE` 为 usize 最大值。

| kind | element | count | first/length | alignment / is_packed |
| --- | --- | --- | --- | --- |
| 标量、bool、function | NONE | 0 | 0/0 | 0 / false |
| pointer、slice、optional | 有效类型索引 | 0 | 0/0 | 0 / false |
| result | 有效类型索引，或 NONE（`!void`） | 0 | 0/0 | 0 / false |
| array | 有效类型索引 | >0 | 0/0 | 0 / false |
| struct | NONE | 0 | 非空 Field 区间，各 `typ` 为有效索引 | 任意 / 0 或 1 |
| enum | NONE | 0 | 非空 Field 区间，`typ` 为有效索引或 NONE（无 payload） | 0 / false |

`is_packed` 按原始字节读取，只接受 0 或 1。每个 Field 最多属于一个 struct/enum（区间两两不相交）；不属于任何聚合的 Field 允许存在，其 offset 输出 0。

## 布局规则

- u8/u16/u32/u64 为 1/2/4/8 字节、同值对齐；bool 1/1；pointer、function 8/8；slice、optional、result 16/8。
- array：`count*element.size`，对齐继承元素；乘积超过 `MAX_SIZE=2^63-1` 为 `OVERFLOW`（先用除法判断，不会回绕）。
- struct 非 packed：字段按各自对齐依次向上取整；对齐取字段对齐最大值（至少 1）；末尾按对齐取整。packed：字段对齐视为 1，紧密排列，struct 对齐 1。
- 显式对齐：0 表示无。非零时必须是 1..4096 的 2 次幂，且不能与 packed 组合，否则 `ALIGNMENT`（在展开字段之前检查，与 typesys 相同）。与 typesys 相同，显式对齐小于自然对齐也是 `ALIGNMENT`；否则 struct 对齐取显式值。
- enum：没有任何 payload 为 8/8，有任一 payload 为 16/8。
- pointer/slice/optional/result/enum payload/function 是间接边：只检查目标索引，不跟随计算，所以允许经这些边自引用。array 元素和 struct 字段是直接值边，直接值环为 `CYCLE`。
- 任何偏移或大小超过 `MAX_SIZE` 为 `OVERFLOW`。enum 字段 offset 统一 0。

可存储类型限制（例如 optional/enum payload 只能是标量）由语义层负责，本模块只检查索引和固定布局。

## 状态与顺序

公开状态：`OK=0`、`INVALID=1`、`CAPACITY=2`、`CYCLE=3`、`OVERFLOW=4`、`ALIGNMENT=5`、`DEPTH=6`。

1. `INVALID`：`max_depth` 不在 1..256；任一区间 span 溢出、未自然对齐（types/fields/layouts/offsets/work/work_offsets 为 8 字节，states 为 1 字节）；五个写入区间（layouts、offsets、work、work_offsets、states）彼此重叠或与任一输入重叠（两个输入之间可以重叠）；任一描述符元数据非法或 Field 区间重叠。这一步不写任何存储，scratch 也不变。
2. `CAPACITY`：`layouts.len`、`work.len`、`states.len` 小于 `types.len`，或 `offsets.len`、`work_offsets.len` 小于 `fields.len`。也不写任何存储。
3. 初始化 states 和 work_offsets，然后按索引顺序对每个类型做深度优先计算，返回遇到的第一个 `CYCLE`、`OVERFLOW`、`ALIGNMENT`、`DEPTH`。深度沿当前值边链计算，起点为 1，超过 `max_depth` 为 `DEPTH`；深度检查先于缓存命中，所以同一类型在不同路径上可能结果不同，顺序固定为上述索引顺序。这些失败可能改变 scratch，但 layouts/offsets 全部不变。
4. 全部成功后才写 `layouts[0..types.len)` 和 `offsets[0..fields.len)`，两者尾部及所有区间外字节不变。

## 复杂度

states 记录 未访问 / 进行中 / 完成，每个类型只计算一次，计算部分为 O(types + fields)，递归深度不超过 `max_depth`。元数据检查里 Field 区间两两相交的判断不使用 scratch（INVALID 不得改变 scratch），为 O(A²)，A 为 struct/enum 的个数；其余检查为线性。

## 限制

- 不分配、无全局可变状态、无 OS 依赖。
- 有符号/无符号整数同布局，由调用方分类。函数指针签名、可存储性和名称解析不在本模块范围内。
- 模块本身不导出 C 符号；测试通过临时 wrapper 导出 `dong_type_layout`。
