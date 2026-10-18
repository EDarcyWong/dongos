# Runtime 地址视图

`kernel/boot/runtime_view.dg` 只把经范围校验的 PA 数值转换成运行时 VA，不解引用 PA、不访问页表或 CPU、不分配资源、不修改 BootInfo。调用者分别证明 BootInfo VA 对应 `info_physical`，验证完整 UEFI map 内容、资源归属和各视图的实际 PTE；本模块不重复这些工作。传入的 BootInfo 可以是宿主地址或 HHDM 地址。当前启动已在新根下实际验证这些视图，见 [paging-activation.md](paging-activation.md)。

`display(info, out)` 检查 v1 头（magic/version/160字节/退出固件标志）与 GOP：非零低4GiB范围、宽高1～8192、宽不大于stride且stride不大于16384、pixel_format为0或1，以及完整stride×height×4容量。返回的6个u64依次为framebuffer_base、framebuffer_size、width、height、stride、pixel_format；大小48、对齐8，framebuffer_base为HHDM别名。显示视图不要求有效的raw map、RSDP或页表池。

`make(info, info_physical, rsdp_size, pool, stack, out)` 再检查raw大小1～65536、descriptor_size至少40且整除raw大小、descriptor_version=1、RSDP大小36～4096。pool与stack参数都是PA，分别要求256KiB与64KiB对齐、保留64页与16页。BootInfo160字节、raw、RSDP、GOP、pool、stack这6个实际字节范围都必须非空、不越4GiB且两两不交叠；相邻端点允许，页包络冲突交给PTE检查。

`View` 大小160、对齐8：首字段为偏移0的Display；其后14个u64依次为boot_info、raw_map、raw_size、descriptor_size、rsdp、rsdp_size、pool、pool_physical、pool_pages、stack_bottom、stack_top、stack_probe_bottom、stack_probe_top、root_physical。boot_info/raw_map/rsdp/pool均为`0xffff800000000000 + PA`；pool_physical与root_physical保留pool PA，pool_pages固定64。普通栈目标为`[0xffff900000001000, 0xffff900000011000)`，干跑栈为`[HHDM+stack, HHDM+stack+65536)`。

两接口的unsafe契约要求调用者提供对齐、存活且可读/可写的完整对象。模块拒绝null、数值跨度回绕、输入输出对象重叠，统一返回`boot.runtime_errors.InvalidView=0x02070001`。所有校验在发布结果前完成；失败时完整输出及输入不变，成功时只改完整结果对象。原BootInfo及其中PA字段保持原值。EMPTY_DISPLAY与EMPTY_VIEW供显式静态初始化。

`python -m unittest tests.test_runtime_view -v` 检查debug/release固定字段布局、ELF64/COFF组装及native C O0/O2。宿主探针的每次display/make调用均使用同一完整输入/输出快照与双端哨兵；成功比对全部字段及输出尾部，失败比对完整输出。覆盖六范围全部15对相交/端点相邻、各范围4GiB边界、头/几何/raw/RSDP/对齐拒绝，以及1000轮固定种子的有效视图及对应坏输入。此验证不代表新树已激活，也不验证NX/WP或硬件guard fault。
