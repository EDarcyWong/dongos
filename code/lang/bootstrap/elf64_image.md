# bootstrap.elf64_image：可由内核验证的静态 ELF64 代码与数据镜像（C45，接续 CR33）

把已经按固定布局解析好地址的机器码和数据，包装成一个有界的 ELF64 `ET_EXEC` 二进制容器，可以直接交给内核 `exec.elf.validate` 规划装载。它只是容器，不汇编指令、不链接符号，也不代表完整后端已经完成。

```text
module bootstrap.elf64_image;
pub const OK:u64=0; pub const INVALID:u64=1; pub const CAPACITY:u64=2;
pub const BASE:u64=0x40_0000; pub const PAGE:usize=4096; pub const TEXT_OFFSET:usize=4096;
pub const LIMIT:usize=0x100_0000;   // 16 MiB
pub unsafe fn emit(code:[]const u8, data:[]const u8, bss_bytes:usize, entry_offset:usize,
                   out:[]u8, written:*usize)u64
```

## 布局

- `code_end = 4096 + code.len`
- 有数据或 BSS（`data.len + bss_bytes > 0`）时：`data_offset = align_up(code_end, 4096)`，`file_size = data_offset + data.len`；否则 `file_size = code_end`。

| 文件区间 | 内容 |
| --- | --- |
| `[0, 64)` | ELF 头 |
| `[64, 64+56·phnum)` | 程序头（1 或 2 个） |
| 头页其余部分，到 4096 | 0 |
| `[4096, code_end)` | code 原样复制 |
| `[code_end, data_offset)` | 0（仅在有数据/BSS 时） |
| `[data_offset, file_size)` | data 原样复制 |

BSS 不写进文件；只有 BSS 时，第二个段的 `p_offset` 等于 `file_size`。`out` 中 `file_size` 之后的部分保持不变。

## 字段

- ELF 头：ident = `7f 45 4c 46`、CLASS64、DATA_LSB、version 1、OSABI 0，其余 ident 为 0；`e_type=2`（ET_EXEC）、`e_machine=62`（x86-64）、`e_version=1`、`e_entry = BASE + 4096 + entry_offset`、`e_phoff=64`、`e_shoff=0`、`e_flags=0`、`e_ehsize=64`、`e_phentsize=56`、`e_phnum` 为 1 或 2；`e_shentsize`、`e_shnum`、`e_shstrndx` 都是 0。
- 文本段 `PT_LOAD`：`flags=5`（R+X）、`offset=0`、`vaddr=paddr=BASE`、`filesz=memsz=code_end`、`align=4096`。头页也映射在这个只读可执行段里。
- 数据段 `PT_LOAD`（仅在有数据或 BSS 时）：`flags=6`（R+W）、`offset=data_offset`、`vaddr=paddr=BASE+data_offset`、`filesz=data.len`、`memsz=data.len+bss_bytes`、`align=4096`。

没有 W+X 段，没有动态链接、符号、节表或重定位。

## 参数校验（全部 INVALID，且都先于 CAPACITY）

1. `written` 非 NULL、8 对齐、8 字节端点不回绕。
2. `code`、`data`、`out` 的端点都不回绕，非空时指针不能为 NULL。
3. 别名：`written` 与完整 `out` 不重叠；`written` 和 `out` 都不能和完整的 `code`、`data` 重叠（按声明长度，包括尾部）。code 和 data 之间允许重叠（都是只读）。
4. `code` 非空，且 `entry_offset < code.len`（入口一定落在 RX 段的文件内容里）。
5. `code.len`、`data.len`、`bss_bytes` 各自 ≤ 16 MiB；`code_end ≤ 16 MiB`；`data_offset ≤ 16 MiB` 且 `file_size ≤ 16 MiB`。

## 上界证明

- 每一项都 ≤ 16 MiB + 4096，所以 `code_end`、`align_up`、`file_size`、`data.len + bss_bytes` 都不会溢出；比较时用 `dn > LIMIT - data_offset` 的形式，不先做加法。
- 映射页数：文本段最多 `16 MiB / 4096 = 4096` 页；数据段加 BSS 最多 `(16 MiB + 16 MiB) / 4096 + 1 = 8193` 页；合计 ≤ 12289，小于内核的 `MAX_PAGES = 16384`。
- 最高虚拟地址不超过 `BASE + 16 MiB + 32 MiB + 4096`，远小于内核的 `USER_LIMIT = 2^39`；`BASE = 0x400000` 也不小于 `USER_MIN`。
- 文件大小 ≤ 16 MiB = 内核的 `MAX_IMAGE`。

## 发布方式

所有失败条件（包括容量）在写 `out` 之前全部检查完。输出可能有 16 MiB，所以不在栈上暂存整份镜像。容量确认后直接按"头页清零 → 填字段 → 复制 code → 清零填充 → 复制 data"的顺序写出，这之后不会再失败；最后写 `*written = file_size`。任何失败都不改 `out`、`*written` 和输入。

无分配、无全局可变状态、无 OS 调用；模块不导出 C 符号，测试通过临时 wrapper 导出 `dong_elf_emit`（另外桥接只读的内核 `exec.elf.validate`）。
