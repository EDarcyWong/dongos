# mm.memory_map — UEFI 内存图规范化与保留区差集

把原始 UEFI 内存图加显式保留区，转换成 `mm.phys_buddy` 可接受的相对页段。只计算结果，不发布到活动分配器或修改页表。

## 接口

```text
module mm.memory_map;
pub struct ReservedRange { pub base:u64, pub length:u64 }
pub struct PageRange { pub start_page:usize, pub page_count:usize }

pub unsafe fn normalize(
    raw:[]const u8,descriptor_size:usize,descriptor_version:u64,
    arena_base:u64,arena_pages:usize,
    reserved:[]const ReservedRange,
    scratch:[]u8,output:[]PageRange
)!usize
```

返回实际写入的最大连续可用段数；输出按页号递增、不重叠、无零长度段，邻接段合并。

## 输入与保留策略

- arena 沿用 D8：4096 字节页，`arena_pages` 为 `1..=2^20` 的 2 次幂，`arena_base` 按整个 arena 大小对齐且结尾不溢出 u64。
- `descriptor_version` 必须为 1；`descriptor_size >= 40` 且为 8 的倍数，`raw` 最多 64 KiB 且长度为 stride 整倍数，允许空图。按实际 stride 用非对齐访问解析 Type@0(u32)/PhysicalStart@8(u64)/NumberOfPages@24(u64)/Attribute@32(u64)，忽略 VirtualStart 与扩展尾部。
- 描述符可无序；非页对齐 PhysicalStart、零页数、端点溢出、任意两范围重叠均返回 `InvalidArgument`（即使范围在 arena 外也先验证）。
- 仅 ConventionalMemory(type 7) 且未置 EFI_MEMORY_RUNTIME(bit 63) 的范围可用；其他类型/未知类型/未描述区域保留。
- 显式 reserved 可无序、可重叠、任意字节边界；非零长度端点溢出报 `InvalidArgument`，零长度忽略；裁剪后任何与保留字节相交的整页均排除（用 floor 取整，不漏保留）。

## 缓冲与错误

`scratch` 至少 `arena_pages` 字节（否则 `MetadataTooSmall`），内容可被改写；输出容量在写第一项前确认（不足返回 `core.errors.BufferTooSmall`）。所有失败保持整个 output 不变。复用 `mm.errors.InvalidArgument/MetadataTooSmall` 与 `core.errors.BufferTooSmall`。

## 复杂度

描述符校验 O(n²)（重叠检查，n 为描述符数，raw ≤ 64 KiB）；标记与扫描 O(arena_pages + 描述符 × 每描述符裁剪页数)。

## 已验证

宿主测试用独立 C 逐页参考模型交叉核对，覆盖 stride 40/48/56、非对齐 raw、空图、unknown/RUNTIME 类型、holes、跨 arena 裁剪、保留区部分页/重复/跨界、高于 4 GiB 基址、各类非法输入、容量/scratch 边界，及固定种子随机无序合法图。debug/release 与 ELF64/COFF 组装均通过。
