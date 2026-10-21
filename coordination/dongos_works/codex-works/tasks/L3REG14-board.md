# L3REG14 — [发布门禁] 修复旧native compiler无参数容量负例下溢

负责人：codex。状态：待领取。

实际Linux用原DRIVER/同Dong对象执行新GLOBAL无参正例返回96/contract line52；旧容量循环无条件exact_args-1，在0参数时变UINT64_MAX，底层正确INVALID1却被harness误要求CAPACITY2。不能给正例塞无关参数绕过。仅修旧harness边界：零参数没有合法的更小容量，改明确测试UINT64_MAX描述符先拒INVALID且保持Result/完整workspace；非零args原short capacity2负控保留，全部其它bad buffers/guards/源码/ABI/真实语义坏体保持。worker候选先隔离，L3HOST13正式与Linux冻源退出前不修改其读取的主线旧test文件。新增便携独立真实旧Driver→当前Dong前端/lower/backend→debug/release零参数GLOBAL→ELF64/COFF/SysV实际返回1，cold真实引导、0skip/source稳定；Linux再实际旧原测试方法通过。原96失败和修复来源保留，不改生产DG，不以字串断言替代执行。源码审查、正式独立零skip、实际主目录指纹分别accept/integrate。

## 可修改文件

- `codex-works/l3reg14/test_bootstrap_native_compiler.py`
- `lang/tests/test_bootstrap_native_compiler.py`
- `lang/tests/test_native_zero_args.py`
- `docs/native-zero-argument-capacity.md`
- `codex-works/deliveries/L3REG14.md`

## 定向验收

- `module:lang.tests.test_native_zero_args`

交付：`codex-works/deliveries/L3REG14.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
