# mm.fixed_cache — 单缓冲区固定尺寸对象缓存

P2 定长对象缓存的单缓冲区核心：调用方提供已映射的虚拟内存与外部逐槽元数据，库管理固定槽的分配/释放。不自动向 buddy 取页或扩容。

## 接口

```text
module mm.fixed_cache;
pub struct Cache { /* 私有状态 */ }
pub struct SlotMeta { /* 私有逐槽元数据 */ }
pub const EMPTY_CACHE:Cache = ...;
pub const EMPTY_SLOT:SlotMeta = ...;

pub unsafe fn init(cache:*Cache,buffer:[]u8,object_size:usize,alignment:usize,metadata:[]SlotMeta)!void
pub unsafe fn alloc(cache:*Cache)!*u8
pub unsafe fn free(cache:*Cache,object:*u8)!void
pub unsafe fn free_count(cache:*const Cache)!usize
```

## 契约

- 首次调用前用 EMPTY 值整体初始化；重复 init 返回 AlreadyInitialized，未初始化返回 NotInitialized。
- `object_size` 1～4096；`alignment` 1～4096 的 2 次幂，`buffer` 起点对齐且非空。`stride = align_up(object_size, alignment)`；`capacity = buffer.len / stride` 至少 1。
- `metadata` 至少 `capacity` 项，否则 MetadataTooSmall；只用所需项，不动超额尾部。
- init 后全槽空闲；alloc 返回空闲槽精确起点（满足 alignment、与存活对象不重叠），无空闲槽返回 OutOfMemory，选择规则为自由链头（可复现）。alloc/free/count 均 O(1)。
- free 仅接受本实例当前已分配槽的精确起点；null/内部字节/槽间填充/尾部余量/越界/其他缓存/重复释放返回 InvalidFree。
- 不清零、不写 payload、padding 与末尾余量。free_count 精确；无全局可变状态，单线程或调用方持锁。

## 数据布局

`Cache` 存 `initialized/buffer/metadata/object_size/stride/capacity/free_head/free_total`；`SlotMeta`（每槽）存 `state`（Free/Allocated）与 `next`（自由链后继）。自由链放在 metadata 中，不挪用对象 payload。

## 已验证

宿主测试用独立 C 槽位模型交叉核对对齐、唯一性、容量、耗尽、释放复用与计数，覆盖奇数对象大小、1/4096 边界、各类 alignment、恰好一槽、尾部余量、metadata 超额、无效配置、null/内部/填充/越界/重复释放、OOM、未初始化、重复 init、元数据不足，及固定种子随机操作与两个独立缓存。debug/release 与 ELF64/COFF 组装均通过。
