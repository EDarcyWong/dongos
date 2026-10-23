# G5HOST1 Windows宿主映射修复

正式闭包c9682daca7bd417ba6bf615f9bdebb4c在自编译前真实失败`FAIL ELF map`。
已解析debug/release宿主probe.exe，两个PE64 ImageBase均为0x400000，
与不能移动的被测ELF地址冲突。tools.compiler_job.host_link_flags为Windows
宿主选择0x10000000；Linux保留原no-pie/text-segment策略，被测ELF不改动。
新增实际GCC链接/PE头解析/运行VirtualAlloc固定地址写读释放的门禁，另实际
链接强制冲突的坏宿主并要求返回17。未运行OS/VM，未改变编译器预算或ELF。
本轮测试尚未运行，提交协调器独立复验；闭包需随后重新完整冷构建，不以
映射修复代替固定点成功。

首轮dcf06e7db8c34cb2b7ac60fac2e76949为1test/0skip实际失败：新增C探针
漏旧MinGW所需__USE_MINGW_ANSI_STDIO宏，printf格式在-Werror下拒绝；
未产生通过证据。已补宏并重新提交独立复验，宿主基址修复保持不变。

第二轮aead6faca4874e5b9757c12976bc604e真实失败：PE已移至10000000，
但旧MinGW初始主线程栈仍占400000–600000；VirtualQuery为MEM_PRIVATE，
栈上地址5ffcc8。现Windows在完成CRT初始化后用_beginthreadex创建worker，
静态context保存参数及DuplicateHandle得到的原线程句柄，main仅ExitThread，
worker等WAIT_OBJECT_0并关闭句柄后执行原harness，完成后fflush/ExitProcess。
上下文不依赖被退休栈，编译器仍用其原64KiB双guard调用栈。
开发探针已真实分配完整2MiB 400000–600000并写读首尾/释放；不宣称最大
8MiB ELF范围始终空闲，实际完整ELF含BSS extent仍须由闭包真实映射验收。
现重新提交正式独立复验，两个小门禁失败完整保留。

第三轮e33ce8eaa77e477d859bc37dc9799458正向PE/完整2MiB映射已实际通过，
坏宿主构建因旧ld不支持--disable-dynamicbase失败，未算负控通过。现读取
真实ld帮助按能力使用该选项，并解析坏PE要求RELOCS_STRIPPED或DYNAMIC_BASE
关闭；仍必须实际在400000装载并返回17，不以构建失败替代运行负控。


## AI交付 2026-10-22T15:15:56+00:00 · codex-mcp-daece153b59c4bd5

真实失败已解析为本机TDM-GCC默认PE基址0x400000冲突，显式将宿主探针放到0x10000000；被测ELF原始地址/内容和编译预算不变。新增真实PE头/VirtualAlloc固定地址与冲突坏宿主运行门禁。当前未跑本轮测试，提交独立复验。


## AI交付 2026-10-22T15:17:06+00:00 · codex-mcp-daece153b59c4bd5

首轮探针因旧MinGW printf格式宏缺失在构建期失败，已补与现有工具一致的__USE_MINGW_ANSI_STDIO。宿主基址修复不变，重新独立复验；旧失败保留未计通过。


## AI交付 2026-10-22T15:24:58+00:00 · codex-mcp-daece153b59c4bd5

已实际诊断PE移开后旧MinGW初始线程2MiB栈占固定窗口；Windows宿主用CRT初始化后的_beginthreadex和静态ctx/真实线程HANDLE等待旧线程退休，再执行原harness。开发完整2MiB固定映射首尾写读释放成功，官方重验待结果；最大8MiB范围未作保证，实际compiler ELF extent仍须closure真正load验收。固定ELF、56MiB arena/64KiB guarded compiler stack/2MiB ELF不变。


## AI交付 2026-10-22T15:26:25+00:00 · codex-mcp-daece153b59c4bd5

正向完整2MiB映射已实际通过；坏宿主旧ld不支持disable-dynamicbase已改按实际ld帮助能力使用，并核坏PE确实固定装载，必须真实运行返回17。旧失败保留；重验待结果。
