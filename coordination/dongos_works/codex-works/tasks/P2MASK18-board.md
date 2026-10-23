# P2MASK18 — P2根forest按真实硬件上限审计异宽用户Space

负责人：codex。状态：待领取。

接P2LARGE16独立源码审查发现ROOT13已过同48位host但生产正常有异宽：boot.memory_startup使用真实CPUID physical_bits，user.memory私有Space固定48；runtime_roots目前要求所有address_mask相等会拒合法36/40/46/52bit环境。本项只修只读forest组件与独立C/DG测试/doc，不改生产root构建、编译器或旧owner权限。以可信canonical kernel Space.address_mask作为实际硬件物理上限，每个private Space另保留自身valid_mask并使用min(hardware_mask,space_mask)解析/检查所有table pool与present parent/leaf物理地址、reserved位、查询范围；不能只删除相等检查后接受超过硬件的PA。共享1..511仍精确canonical忽略A而非D，zero仍exact；private foreign/accounting/pending/失败原子/5056B Scratch/4KiB帧限制不变。增加真实kernel36/40/46/user48及kernel52/user48正向、超过hardware和超过private descriptor上限的pool/parent/leaf精确拒绝，C原始oracle独立重算，不制造host通过为VM。保留ROOT13 integrated15历史范围并说明新发现/新复验。实现者不运行test/compiler/OS/VM、改状态或commit/push；root独立三模块0skip/source stable后实际主线集成。

## 可修改文件

- `kernel/mm/runtime_roots.dg`
- `tests/runtime_roots_probe.dg`
- `tests/runtime_roots_probe.c`
- `tests/test_runtime_roots.py`
- `docs/runtime-roots.md`
- `codex-works/deliveries/P2MASK18.md`

## 定向验收

- `module:tests.test_runtime_roots`
- `module:tests.test_paging_view`
- `module:tests.test_paging`

交付：`codex-works/deliveries/P2MASK18.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
