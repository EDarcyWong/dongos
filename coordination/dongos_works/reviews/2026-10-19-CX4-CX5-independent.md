# CX4 / CX5 追加独立审查与主线复验

所属阶段：L3本机语义程序产物支撑；CX4关联P7进程/文件EXEC容量，CX5为宿主Dong编译器BSS对象发射兼容性。均不等同于客体生命周期或完整L3通过。

## CX5

已审查emitter.py静态对象发射差异、任务契约、交付和永久测试。仅将BSS的NASM alignb宏替换为`resb (alignment-($-$$)%alignment)%alignment`，并设置BSS节基址为所有BSS对象要求的最大对齐（下限4）。对象前缀偏移对齐与节基址对齐分别保证，零填充/对象内容/其它节保持原语义；未关闭警告。新测试独立解析ELF64/COFF节表的实际发布对齐，并在显式SysV本机执行中检查64字节对齐、全对象零值、真实写后读取及邻接对象保持；原globals和alignment测试继续执行。

正式作业84bc452304474cd7b8d5a9b0fe914ef2：1+3+2=6项0skip，1.857+2.269+1.850秒，来源稳定。不是虚构NASM兼容性成功：已实际组装两种格式，且测试保留Wall/Werror。

## CX4

已审查共享process_abi.MAX_EXEC_IMAGE=2MiB及shell/kernel三处实际使用，任务/交付和8个声明文件差异。shell从共享常量确定BSS和读取上限，超限在读取之前返回并关闭文件；成功仍分段最多61440字节读取、逐段验证真实长度、结束关闭后才EXEC。kernel保留权限分支、bytes非零/上界、check_range、copy_in及launch原路径，仅统一上界并按(上限+4095)/4096分配512页；service_memory.allocate通过reserve后逐页映射清零，失败不提前发布EXECUTABLE。未取消这些检查。

独立C IPC/filesystem模型比较实际传给EXEC的每个字节，新增262145/1048577/exact2MiB输入，cap+1要求读量/EXEC次数不变且close次数增加1；既有终态token/扩容等实际坏Dong负控保留。lifecycle测试仅运行宿主解析/夹具控制，不启动VM；独立fixture中2MiB常量属于oracle，不替代生产共享常量。

正式作业b7b3757bd49b420bb8fafd498af4b9ab：shell1项+生命周期宿主控制11项=12项0skip，35.753+2.076秒，来源稳定。交付说明另有kernel服务leaf生成6134955字节汇编，默认NASM组装120秒超时、O0重试待定；本审查者未把生成文本或宿主mock冒充内核/客体实际EXEC成功。本任务书将leaf组装限定为可行时追加，客体生命周期门禁明确另行，故该限制保留，不宣称客体已过。

## 审查者独立主线检查

在code内运行`python -m unittest -v lang.tests.test_bss_compatibility lang.tests.test_globals_native lang.tests.test_alignment_native tests.test_shell_commands tests.test_process_lifecycle_qemu`：18项全部通过、0skip、40.940秒。shell证据code/build/test/shell-commands/run-d7991f2902d7。生产修改已实际落在主线code中，验收/集成前另比对各声明文件与正式指纹，未从旧副本覆盖主线文件。协调器accepted/integrated分别登记，不以本说明替代状态关卡。
