# P2VIEW6 — [P2EXEC/WC] 实际Space只读池视图及隐藏别名扫描前置

负责人：codex。状态：待领取。

用户明确要求Codex接手P2EXEC1/P2WC1修改。两项原契约要求完整真实根池扫描但paging.Space字段私有且现有公开API只返回root/mask/used，无法安全核对调用方伪造池descriptor确实等于Space正在使用的pool。此项只增加只读PoolView/inspect公开API，返回实际Space内部pool/metadata/count/root/mask/used/NX，不构造Space、不修改私有状态、不改变既有Context/Stats ABI，不放宽页表或W^X规则。unsafe readable initializedSpace前提明确；输出与Space/完整pool/metadata完整端点、对齐/数量乘法/指针溢出先验，失败完全不写输出和源。实际pool/meta descriptor来自Space本身，供EXEC/WC在自己候选内只读全树扫描，不引入新算法组件替代它们。只4文件，tests/test_paging_view.py内嵌真实Dong wrapper/C独立布局oracle，debug/release+ELF64/COFF+SysV原生call，实际descriptor精确对应及源/完整out guards不变，null/未init/未对齐/完整尾部重叠/极端端点失败，测试缺工具fail0skip；既有paging测试回归。只在完成独立正式复验和源码审查后accept并核对真实文件integrate分开登记。协调者接续原EXEC任务，不提前关闭EXEC/WC。本项不运行OS/VM，无commit/push/PR/AI CLI。

## 可修改文件

- `kernel/mm/paging.dg`
- `tests/test_paging_view.py`
- `docs/paging-pool-view.md`
- `codex-works/deliveries/P2VIEW6.md`

## 定向验收

- `module:tests.test_paging_view`
- `module:tests.test_paging`

交付：`codex-works/deliveries/P2VIEW6.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
