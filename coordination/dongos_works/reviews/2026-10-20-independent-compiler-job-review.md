# CX13 pure compiler job 独立审查

独立审查者review_io。已通过coordination MCP读CX13原任务书，并审查compiler_job.dg、tools/compiler_job.py、永久测试及依赖graph_compact/compiler_driver/native_assembler。未修改生产、永久测试或交付，未自行验收集成，未运行OS/VM。

## 阻塞：桥附加在只允许结尾的GNU metadata之后

[P1] 当前compiler_job在driver文本末尾追加`section .text`和dong_compiler_entry桥，但driver正常输出末尾是：

```text
%ifidn __OUTPUT_FORMAT__,elf64
section .note.GNU-stack noalloc noexec nowrite progbits
%endif
```

native_assembler.dg:139的%endif只清conditional；第141行在metadata=true时拒绝任何后续非空section/指令。因而合法driver输出追加桥后必然在新section .text被SYNTAX拒绝，不能生成ELF。应在metadata尾块之前插入桥或另行有界组合，保持既有assembler元数据接受契约。已通知实现者，不代改。

独立原生实证：复用首轮run-247e8623ff5e/release/job.o及bridge.o，确认各自job.stdout/bridge.stdout存在（汇编已退出）后另行链接独立C。输入合法小程序 `module a;export("dong_compile_job") fn f()u64{return 37;}`，采用真实64KiB guarded stack及56MiB guarded arena调用真实Dong job：

```text
small rc=3 stage=3 code=3 detail=26 written=0
```

原始输出完整保留driver文本，metadata的%endif之后第26行即新增section .text。C夹具因预期合法输入生成ELF未满足而exit90 `FAIL small valid pipeline`；没有panic、崩溃或构建失败。该次夹具在达到合法小程序前，已实际通过63项多Source最后一段缺失的前置拒绝和3项完整catalog尾部别名拒绝。

命令：`python code/build/test/independent-io/probe_job.py code/build/test/compiler-job/run-247e8623ff5e release`。原始C/生成脚本位于code/build/test/independent-io/compiler-job/probe.c与上级probe_job.py；完整命令、对象SHA和stdout/stderr已固化到metadata-tail-defect.json，后续重放不覆盖这份缺陷证据。

## 其余初审（尚待最终结果）

预检：四个live区域使用完整声明容量（catalog固定64条而不是count），span/对齐/两两互斥先于首次写。blob先按count<=64、entry<count、root<=1、pn=1..4096、逐段剩余长度及最终exact-end校验一遍，再第二遍填catalog，路径/源码均借用只读blob，不复制进arena。没有发现framing算术溢出或错误前置写。

生命周期：frontend/compact结果记录放在stack，Source目录和blob在arena外；graph_compact把所有活跃graph池移到前部并收窄Graph.arena长度。driver只使用retained..47MiB工作区与47..56MiB文本；发射完成后Graph及lower工作区已死亡，assembler复用0..8MiB和8..10MiB输出，仍live的assembly在47..56MiB，无阶段间活跃别名。最终written受2MiB out cap约束。

桥ABI：run六个SysV寄存器参数分别为blob.ptr/blob.len/catalog/arena.ptr/arena.len/result，桥调用前只减rsp未改参数。kernel/user/memory.dg:394设置进程初始rsp=stack_top-8，桥sub rsp8后call令run入口rsp%16=8，退出mov rdi,rax/mov eax255符合现有ABI。host loader明确跳过桥里的guest syscall，仅调用解析出的direct target；因此现有host测试不能证明guest exit syscall已经实际执行。

guard测试：invoke_guarded先在host栈保存rbp/rbx/r12-r15，用callee-saved r12保存host rsp，再切换到单独64KiB两侧NOACCESS guarded stack，call前对齐16；调用结束恢复host栈。blob为只读页；arena两侧guard。host ELF loader检查标识、header/segment表范围、segments flags/range/order、RX/RW映射与entry direct-target范围，足以用于本测试自生产ELF；不替代真实kernel loader/权限验收。

待实现者修复桥插入顺序，重跑独立合法小程序/实际backend capacity负控及完整self-compiler固定点后形成最终意见。当前不能推荐验收CX13。

## 修复与追加独立复验

实现者已在compiler_job中完整比对driver终端metadata常量tail，在写入前确认er.written>=tail.len、er.written+bridge.len<=9MiB，然后把bridge放到insert=er.written-tail.len，并在其后重写literal tail。新增写范围都在既有47..56MiB文本区，复制源为literal而非被覆盖的旧arena尾部；原assembler接受契约没有修改。只读审核该修复正确。

复用修复后run-2359c6c1be85/debug/job.o（对象SHA256 `1ab89134e22f61cf3d590f4a487c303f37127d28556f191aab89b0558673fed5`），job.stdout及bridge.stdout已完成。合法小程序现返回 `small rc=0 stage=3 code=0 detail=0 written=8208`，旧metadata P1在真实生产路径已关闭。

追加发现host loader门槛off-by-one：[P2] tools/compiler_job.py要求text_end-entry>=25，但真实桥是24字节（sub7+call5+mov3+mov eax5+syscall2+ud2=24），位于.text尾部，因此将正确ELF误拒绝为`FAIL ELF entry`。已通知实现者，其计划改为24并校验完整桥。原始误拒绝命令/对象SHA/stdout/stderr固化于code/build/test/independent-io/compiler-job/host-entry-defect.json与同名.c，没有覆盖旧metadata-tail-defect证据。

本代理仅在独立host夹具把>=25修正>=24后继续同一未修改Dong对象。命令：

```text
python code/build/test/independent-io/probe_job.py code/build/test/compiler-job/run-2359c6c1be85 debug
```

结果exit0，stderr为空：

```text
small rc=0 stage=3 code=0 detail=0 written=8208
capacity rc=3 stage=2 code=2 written=0
66 independent late-frame/full-catalog rejects + generated return37 + backend capacity passed
```

66项前置拒绝包含count=2..64、前count-1条目录均完整但最后一条缺失（63项），以及Source全64条尾部与arena/Result/blob重叠（3项）。全部零publication，Source/Result全文及arena头尾canary不变。小程序在64KiB guarded栈、56MiB guarded arena生成真实ELF并执行返回37。另1101函数源码真实触发backend容量错误stage2/code2且written0，而不是只靠错误descriptor假装容量覆盖。生产SHA256为`c071546dcad196024fc9cfd4ac2b9843f9540bda5540c2dc74a39ee763fe0e84`。

原始probe.c/脚本/编译和执行命令/完整结果在code/build/test/independent-io/compiler-job/evidence-debug.json。已另启动该debug对象和对应完整sources.bin的独立guarded self-compiler固定点复验，输出目录full-debug；最终固定点和修正host门槛后的正式结果尚待完成。

### 独立完整闭包固定点完成

命令：`python code/build/test/independent-io/full_job.py code/build/test/compiler-job/run-2359c6c1be85 debug`。复用相同稳定debug对象及对应sources.bin（447948字节），独立重新链接host夹具，仅修正已发现的host>=25误拒绝为>=24，无生产替代实现。完整输入blob内compiler_job.dg摘要与当前生产c071546d...一致。

结果exit0，stderr为空：

```text
seed 0/3/0/0 bytes=1892632 frontend=57144296 retained=27228976 backend=20702968
native 0/3/0/0 bytes=1892632 frontend=57144296 retained=27228976 backend=20702968
PASS exact ELF fixed point; seed/native guarded 56MiB arena and 64KiB stack; 32 atomic preflights; native semantic rejection
```

stage1.elf/stage2.elf均1892632字节，SHA256均为`cf19cd58e244835e142f5abc40c1ced98da3666b3ba4855080623bc638b606bc`，逐字节相等且低于2MiB。两stage都在64KiB NOACCESS边界栈与56MiB NOACCESS边界arena执行，完整源码blob只读。原始stdout/stderr、C/EXE、输入blob、两份ELF及完整命令/SHA在code/build/test/independent-io/compiler-job/full-debug/evidence.json及同目录文件。

已读最终host门槛修复：tools/compiler_job.py:107改>=24，第119–121行同时核对完整prefix/suffix及原有rel32目标RX范围，关闭错误拒绝而没有接受错误桥字节。该host改动不影响生产job源码或以上固定点。当前尚待最终release及正式完整零skip/源稳定结果，未提前把正在运行的测试记通过。

### 最终release独立复验及kernel ELF验证完成

run-3383cd152203/release的job.stdout和bridge.stdout完成后复用稳定对象，SHA256 `100efe4600a0feefd0225d8db0266865e8e2e04fe7c3c555af926e268723b7be`。先重放独立66拒绝/合法机器码返回37/1101函数真实backend容量失败，exit0，结果与debug完全相同：code/build/test/independent-io/compiler-job/evidence-release.json。

再执行 `python code/build/test/independent-io/full_job.py code/build/test/compiler-job/run-3383cd152203 release`，使用最终host >=24及完整桥校验逻辑，生产字节不改。exit0、stderr为空，seed/native全部结果和上述debug一致：1892632字节，frontend57144296、retained27228976、backend20702968；32项前置原子性与native错误语义拒绝通过。stage1/stage2 ELF SHA256均cf19cd58...，且与debug的两份ELF四者全文一致。原始证据full-release/evidence.json、stdout.txt、stderr.txt及两个ELF均保留。

额外采用实际kernel ELF验证器而非仅依赖host自写loader：复用已退出且稳定的GUEST4原生对象内kernel_validate，核对其中snapshot/exec/elf.dg与当前code/kernel/exec/elf.dg SHA256均为`fccdc3ac4da2928388f65d2bca4614b0c1971b4deeb59e423e332876a6a31db5`。对独立debug/release的stage1/stage2四份真实job ELF逐一验证，全部 `production kernel ELF validation rc=0 bytes=1892632`、exit0。命令 `python code/build/test/independent-io/check_job_elf.py`，完整原生链接命令/来源对象SHA/ELF SHA/结果见compiler-job/kernel-elf/evidence.json。

最终代码独审意见：已发现的metadata尾桥P1和host entry字节数P2均已关闭，当前生产SHA c071546d...没有未关闭阻塞。两seed模式均有独立真实语义、实际容量失败、guarded闭包精确固定点和kernel ELF验证证据。推荐最终接口文档与此契约一致，并在正式完整定向测试零skip、源码稳定后验收CX13。此时接口文档尚待实现者落盘、正式测试尚在运行，本报告不将未完成项或取消轮次计为通过。没有验证客体启动/退出syscall、文件FLUSH或同盘重启，仍不等同完整L3完成。
