# mm.phys_buddy — 单 arena 物理页伙伴分配器

纯 Dong 实现的伙伴分配器，支持 4 KiB～4 MiB（order 0～10）。元数据由调用方提供，物理地址只作为 u64 数值处理，不访问实际物理内存。单线程或由调用方持锁；不内置锁、不清零页面、不解析 UEFI 内存图。

## 接口

```text
module mm.phys_buddy;
pub const PAGE_SIZE:usize = 4096;
pub const MAX_ORDER:usize = 10;
pub struct Allocator { /* 私有状态 */ }
pub struct PageMeta { /* 私有逐页元数据 */ }
pub const EMPTY_ALLOCATOR:Allocator = ...;
pub const EMPTY_META:PageMeta = ...;

pub unsafe fn init(state:*Allocator,base:u64,page_count:usize,metadata:[]PageMeta)!void
pub unsafe fn add_usable(state:*Allocator,start_page:usize,count:usize)!void
pub unsafe fn alloc(state:*Allocator,order:usize)!u64
pub unsafe fn free(state:*Allocator,address:u64,order:usize)!void
pub unsafe fn free_pages(state:*const Allocator)!usize
```

## 共享错误码（mm.errors）

| 错误 | 编号 | 含义 |
| --- | --- | --- |
| NotInitialized | 0x0200_0001 | 未初始化即调用其他接口 |
| AlreadyInitialized | 0x0200_0002 | 重复 init |
| InvalidArgument | 0x0200_0003 | page_count / base 不合法 |
| MetadataTooSmall | 0x0200_0004 | metadata 不足 page_count 项 |
| RangeUnavailable | 0x0200_0005 | 发布段与已发布/已分配重叠 |
| InvalidOrder | 0x0200_0006 | order 超过 MAX_ORDER |
| OutOfMemory | 0x0200_0007 | 无足够连续块 |
| InvalidFree | 0x0200_0008 | 释放的块不匹配（越界/非对齐/错阶/重复/保留） |

## 内部表示

- `Allocator`：`initialized`、`base`、`page_count`、`metadata`（指向调用方元数据）、每阶自由链头 `free_head[0..10]`、`free_total`。
- `PageMeta`（每页 16 字节）：`state`（0 Reserved / 1 Free 头 / 2 Allocated 头 / 3 块内尾页）、`order`（头页的块阶）、`next`（Free 头页的同阶自由链后继页号，空为 `LIST_END`）。
- 自由链按阶组织；只有块头页标记为 Free，块内尾页标记为 Tail，保证发布检查（要求 Reserved）不会误收块内页。

## 行为契约

- `init` 只接受 EMPTY 状态（`initialized==0`），重复返回 AlreadyInitialized。`page_count` 须为 `1..=2^20` 内 2 的次幂，`base` 按 `page_count*4096` 对齐，且 `base + page_count*4096` 不溢出 u64。`metadata.len >= page_count`。
- `add_usable` 先检查边界（InvalidArgument）再检查整段 Reserved（RangeUnavailable），随后用“最大对齐块”贪心发布并逐块向上合并。合法零长度成功且无修改。相邻发布可合并；未发布的 hole/保留页不参与合并。
- `alloc` 分配连续 `2^order` 页，地址按块大小对齐，仅来自已发布页。选择最小够用阶并按阶拆分；无够用块返回 OutOfMemory（含块大于 arena 的情况）。
- `free` 仅接受本实例尚未释放的完整分配块（起始地址与阶精确匹配）。越界/非对齐/内部页/错阶/保留页/重复释放返回 InvalidFree；相邻空闲伙伴合并到最多 order 10。
- `free_pages` 精确返回可分配页数。

所有失败保持 state 与 metadata 不变；debug/release 行为一致，检查先于可能溢出的算术/移位。物理地址 0 是合法数值；上层负责不发布零页、内核、启动资源与元数据所在页。

## 复杂度

alloc/free 为 O(MAX_ORDER) 次阶操作，每次合并从自由链中移除伙伴为 O(链表长度)（测试规模下很短）。`add_usable` 为 O(count)（每页至多标记一次）加 O(段数 × MAX_ORDER)。

## 已验证

宿主测试用独立 C 位图/占用模型交叉核对每个返回块的发布、无重叠、对齐与 `free_pages`；覆盖 0～10 全阶、耗尽、拆分、乱序释放、holes、多实例隔离、2^20 页 arena、4 GiB 以上基址、u64 末端溢出、非法配置与各类错误释放，以及 4000 轮固定种子随机 alloc/free。debug/release 与 ELF64/COFF 组装均通过。
