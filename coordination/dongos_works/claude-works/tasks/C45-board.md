# C45 — [L3] 接续CR33：生成可由内核验证的静态ELF64代码与数据镜像

负责人：claude。状态：待领取。

所属阶段：L3：Dong自举后端 → 目标产物：静态ELF64镜像。

转交来源：cursor:CR33（用户2026-10-19明确授权转交Claude），原发布时间2026-10-19T07:39:21+00:00，转交前todo rev1，无领取/提交/复验及实现产物。原任务书cursor-works/tasks/CR33-board.md，SHA256=198998b046290f10e84afa4ea92f4c67a54e2fe0f313c79c92e0878ba92d452e，由协调器保留全部原历史；本任务created/claim/submit/verify时间及每轮耗时另按协调器事件记录，不把原发布时间伪装为本次发布时间。原Cursor任务暂停后归档，不恢复或重复执行。仅写本任务列出的claude-works四文件，完整继承原接口/验收/只读依赖，交付编号改为C45。本人客户端通过worker MCP读取最新rev、claim成功后手动执行；不自动启动任何AI CLI。

L3目标产物缺口：bootstrap.elf64_image。现有NASM发射组件不等于客体可发布ELF，本项真正生成有界ELF64 ET_EXEC二进制容器，尚不组装指令/链接符号，不冒充完整后端。只四文件，不修改内核解析器或活动编译器。

pub unsafe fn emit(code:[]const u8,data:[]const u8,bss_bytes:usize,entry_offset:usize,out:[]u8,written:*usize)u64

固定BASE=0x400000，PAGE=4096，TEXT_OFFSET=4096。code非空，entry_offset<code.len；code/data各<=16MiB，bss<=16MiB，最终文件<=16MiB，所有加法和align_up先检查。code_end=4096+code.len；若data.len+bss_bytes>0，data_offset=align_up(code_end,4096)，file_size=data_offset+data.len；否则file_size=code_end。无数据/BSS只有一个PT_LOAD；否则两个。code_end、data_offset、BASE加虚拟范围和映射页数均须有证明上界，满足kernel/exec/elf.dg当前USER_LIMIT/MAX_PAGES。

严格ELF64 little-endian SystemV：ident为7fELF/CLASS64/DATA_LSB/version1/OSABI0，其余ident0；e_type2/e_machine62/e_version1，entry=BASE+4096+entry_offset，phoff64、shoff0、flags0、ehsize64、phentsize56、phnum1或2、其余section字段0。PT_LOAD text：type1/flags5(RX)/offset0/vaddr=paddr=BASE/filesz=memsz=code_end/align4096。第二PT_LOAD data：type1/flags6(RW)/offset=data_offset/vaddr=paddr=BASE+data_offset/filesz=data.len/memsz=data.len+bss_bytes/align4096。无动态链接、符号、节表或重定位；code中的地址/位移由上游按固定布局预先解析。BSS不写入文件，bss-only时第二p_offset等于file_size。headers和所有padding为0后逐字段设置，code/data原始字节精确保留，out未用尾部保持。

接口OK0/INVALID1/CAPACITY2。written非NULL/8对齐/8字节区间不回绕；完整输入/out描述符端点、NULL、alias预检在任何输入读取或输出写入之前。输入只读且彼此可重叠；written/out与两完整输入均不可重叠，out/written不可重叠。全部非法数据/尺寸/entry优先CAPACITY。先求布局和预检全部字段，最后发布；不能复制code后再发现data容量不足，失败完整out/written/输入不变。无需把16MiB输出暂存栈中：布局确定、所有失败条件检查完成后直接最终写出，之后不得再返回失败。无分配/OS调用/全局可变状态，不导出生产C符号。

实际debug/release董产出，独立Python struct解析全部字段并对照布局/字节，参考源kernel/exec/elf.dg只读，临时桥实际调用其validate(image,0,plan)检查image以及entry/segments/pagecount（只暂存该内核模块及其真实依赖，不改它，不以其自身输出作唯一期望）。需覆盖无data、仅data、仅BSS、data+BSS、4095/4096/4097代码边界、entry首/末、0/max/超限、exact/少1/0容量；非法描述符/端点/完整尾部别名有效可达，真实只读页检查系统调用成功，输入输出双端guard。主要有限案例合计<=24每模式，预检/文本格式除外，避免性能或全笛卡尔积。

真实坏董至少两类：entry落在RX末端外或text flags改RWX，输出仍是成功二进制，独立字段模型和实际kernel.validate必须拒绝（按指定错误，不以崩溃/超时/构建失败代替）；完整容量不足提前写written/out按原子性拒绝。好侧同输入实际董输出先通过。可安全宿主映射仅位置无关小code并显式SysV执行返回数值作为补充，但不要执行任意输入或声称VM/客体已通过。生产/说明/测试/只读解析器前后SHA稳定、0skip，交付真实命令/计数/产物及限制。只本任务检查，不OS/VM/全回归、AI CLI、提交推送、自行验收集成。


## 可修改文件

- `claude-works/src/bootstrap/elf64_image.dg`
- `claude-works/src/bootstrap/elf64_image.md`
- `claude-works/tests/test_elf64_image.py`
- `claude-works/deliveries/C45.md`

## 定向验收

- `discover:claude-works/tests:test_elf64_image.py`

交付：`claude-works/deliveries/C45.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
