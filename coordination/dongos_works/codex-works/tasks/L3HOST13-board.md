# L3HOST13 — [发布门禁] 修复L3A测试桥的Linux/Windows宿主对象选择

负责人：codex。状态：待领取。

GitHub ci.yml真实全量language测试运行Ubuntu，新增L3A globals/native两桥虽然组装ELF64和COFF，却总把COFF送CC，本机Windows通过但Linux必然链接失败。只修测试桥按真实宿主选择链接/返回对象，仍两格式真实组装、显式SysV，不改已验收生产DG/ABI/语义或skip平台。候选先放codex-works/l3host内，不能在活跃L3冷复验期间修改其读取的主线桥；L3稳定退出后才真实复制主线。Windows正式兼容3项/零skip并保持原Windows分支，独立Linux容器实际完整L3A+兼容13项/零skip、源码与候选前后SHA、确切命令/工具/进程。缺Linux工具直接配置已有隔离测试容器，不把skip算通过。原L3A/L3REG11验收历史保留，本项明确后继修改。源码契约审查+独立正式+真实文件集成后分别accept/integrate。全部本轮任务闭合再提交GitHub main核对关机，仍无PR。

## 可修改文件

- `codex-works/l3host/test_l3a_globals.py`
- `codex-works/l3host/test_l3a_native_regression.py`
- `codex-works/tests/test_l3_host_portability.py`
- `lang/tests/test_l3a_globals.py`
- `lang/tests/test_l3a_native_regression.py`
- `docs/l3-host-portability.md`
- `codex-works/deliveries/L3HOST13.md`

## 定向验收

- `discover:codex-works/tests:test_l3_host_portability.py`

交付：`codex-works/deliveries/L3HOST13.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
