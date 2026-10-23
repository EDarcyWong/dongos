# G5CLOSURE1 开发记录

实现位于 g5-closure/src/bootstrap/compiler_job.dg；当前任务 rev2，尚未提交。
真实初始回归为 code/build/test/g5-closure/run-7403d0762d5e：
seed 3/0/2/6，frontend=57144296，原节点池不足。
独立原生 frontend 探针得到 49 模块、177359 tokens、115973 nodes、842 types。
只重分配原56MiB内的调用者容量，未增加预算。

第二次实际运行 run-ac7fea62b5e4：seed 3/2/2/4，frontend=57745296、
retained=29876008、backend=11336256，后端NASM文本池分区不足。
候选现以48MiB/8MiB重分区，后端文本池8MiB，保留2MiB ELF及64KiB栈。
无体extern panic由真实目标退出runtime在需要时提供；G5FULL1的native assembler
只允许同一汇编内已定义的extern，未解析仍原子拒绝。

永久测试 test_g5_closure_native.py 同时冷构建debug/release并运行既有真实
pure job固定点、32原子预检、语义/容量拒绝、启动桥ABI和源稳定性检查。
旧并行run-f9aa99452119使用已证实不足的旧分区，在确认自有进程树后停止，
不计成功。当前run-cf86f8579747仍在执行；结果待填写。

run-cf86f8579747完整结束，真实失败为seed 3/2/3/80，前端及内存分区通过，
lowering拒绝全局常量。独立原生frontend/lower C探针精确定位：
bootstrap/unicode.dg:6，type197=ARRAY(element u64,count667)。现有IR.words把
大于4080字节的静态类型也当作不支持。修复由G5FULL1声明路径program_ir.dg
实现：word数为类型大小，局部slot仍独立检查4KiB帧预算；新增真实大静态
数组执行测试。当前冷闭包run-845053bfe02f正在执行，结果待填写。

未启动OS/VM/AI CLI，未提交或推送，尚未改主线、验收或登记集成。

## 2026-10-22 本机迁移后接续

用户授权继续本任务并在独立复验通过后集成。已通过协调器暂停旧领取、
记录本机无外部构建进程及无活动作业的停止依据、重新领取；保留旧失败历史。
当前实现实际使用47.25MiB/8.75MiB分区，后端640函数/126000指令/
14000实参/9150000文本字节。大静态对象修复位于G5FULL1候选。
迁移前run编号对应的ignored产物不在本机，旧“正在执行”不代表本机进程。
本轮尚未运行测试，现提交现有候选至协调器重新冷构建独立复验；结果待填。

首轮排队job344a3691271f4082885f30b0447188cf已随G5FULL独立审查返修取消，
未执行亦不计通过。闭包将同步使用修复后的最终6模块；自身固定预算实现
未放宽。重新提交协调器独立冷构建，结果待填。

本机jobc9682daca7bd417ba6bf615f9bdebb4c实际失败：1test/0skip/291.063s，
两模式均在small ELF映射前`FAIL ELF map`。解析两份probe.exe确认PE基址
0x400000占用被测ELF固定地址；尚未到完整自编译，不能称固定点失败或通过。
宿主修复通过独立任务G5HOST1处理，ELF地址/字节及56MiB/64KiB/2MiB不变。
G5FULL1已通过51项正式独立复验并accepted rev15，闭包将在宿主修复复验后重跑。

宿主修复G5HOST1正式job4d1c4e4057a142f2aa9af0c87050d60c已1test/0skip/
1.609s/source_stable通过：PE放10000000，原主线程栈真实退休后由CRT worker
执行原harness，完整2MiB固定地址写读释放通过，强制冲突坏PE真实运行返回17。
此证据仅限宿主修复；现重新冷构建完整闭包，保留此前失败，不借开发缓存。

第三轮c464866d6f9b4fb2beeac4c23d9974fc实际仍在初始ELF map失败：释放旧栈后
宿主guarded小块可重占固定窗口。G5HOST2已补临时reserve/真实load前释放/
small卸载重持有，并经独立job0e522b2b18b54676a48a417e00e21cc0的1test/
0skip/2.219s复验和另一代理源码/产物复算后integrated rev6。
仅删除初始hold的正常构建坏宿主实际rc17，证明旧失败机制。

开发诊断仅复用c464轮冻结release job.o/bridge.o、同源sources.bin并重链接新
宿主harness，实际seed/native均0/3/0/0，完整stage1/stage2各2046376字节一致，
32原子预检、语义/后端容量拒绝及启动桥真实检查通过；该缓存轮只用于定位，
不计正式闭包验收。下一轮从全新协调副本冷构建debug/release，两模式与两代
必须共同满足实际固定预算和字节一致，结果待正式填证。


## AI交付 2026-10-22T14:47:42+00:00 · codex-mcp-daece153b59c4bd5

迁移后本会话接续。原候选与失败历史保留，已核对当前源码/测试/预算并更新交付说明；尚未在本机运行测试，提交到协调器独立副本重新冷构建复验。未运行OS/VM，未修改主线，未提交或推送；通过后须独立源码审查及真实主线集成。


## AI交付 2026-10-22T14:53:29+00:00 · codex-mcp-daece153b59c4bd5

独立审查返修已完成；G5FULL修复跨模块静态枚举、tagged payload const转换、known-error try终止，并补4项回归（合计51/27组），局部大布局早拒保留对象上限。首轮冷构建中断/排队取消不计成功。本轮完整测试尚未执行，提交冻结候选至协调器正式独立复验；未改主线、未运行OS/VM、未提交推送。


## AI交付 2026-10-22T15:27:19+00:00 · codex-mcp-daece153b59c4bd5

宿主映射冲突已由G5HOST1正式1test/0skip独立复验通过，工具仅改变宿主PE基址/原线程退休启动，不改ELF/预算。现重新冷构建debug/release完整两阶段ELF固定点；未借缓存、未宣告闭包通过。G5FULL6模块仍与accepted rev15指纹一致。


## AI交付 2026-10-22T15:39:14+00:00 · codex-mcp-daece153b59c4bd5

宿主窗口持有由G5HOST2正式1test/0skip独审后integrated6。开发复用冻结release对象重链新C宿主已真实得到seed/native同2046376B完整ELF与所有预算/原子/桥检查通过，仅诊断不计验收。现提交冻结候选重新独立冷构建debug/release，要求两模式两代完整ELF一致。G5FULL六模块仍accepted15原指纹，无OS/VM/commit/push。
