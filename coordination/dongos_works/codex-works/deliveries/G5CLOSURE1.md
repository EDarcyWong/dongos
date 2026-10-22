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
