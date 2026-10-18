# C7–C12、CR1、LM2 集成验收

2026-10-18：八项已验收任务完成集成，协调器通过新鲜测试及文件身份门禁登记 integrated。保留原交付/验收文件，无提交或推送。

- 七个Dong模块及接口文档按原验收字节加入code/lang/bootstrap；模块hash完全相同。
- 七个定向测试适配为code/lang/tests/test_bootstrap_*.py，只改变主线根目录、模块位置及构建输出位置；既有观察器/独立期望/负控保持。原works测试不修改、不删除。测试实际编译主线lang中的源码。
- 新增test_bootstrap_backend_components.py：在同一真实董图中，将CFG可达性传给INTEGER参数规划，参数栈大小传给栈帧规划，寄存器位置送入并行复制，分支排序标签选择统计数据，清理次序生成payload，再由CR1编码实际NASM输出。debug/release各原生运行、ELF64/COFF组装，NASM -f bin恢复字节06 05 20 03；容量失败观察out/written不变。
- LM2的两个已验收文件从候选副本逐字节回写lmstudio-works/docs及deliveries，结构测试在真实项目路径再跑1项通过。未把主线compiler替换成完整Dong后端，L3自举继续未完成。

## 验证

主线组件及模块图/语法/声明类型/运行时语义相关回归 **38项通过、0skip**。首次批量驱动的600秒上限过短，在34项完成后、运行时类准备阶段中断；timeout.json明确保存失败的批量运行，不作为整组通过。仅续跑剩余4项运行时测试并通过，未重跑已通过的34项。回执：`code/build/test/bootstrap-components/mainline-1d495b26962d/result.json`，首批和续跑日志分别保留。

续跑期间受测lang/bootstrap、lang/dongc、lang/tests文件前后hash一致；全部集成文件另与最初复制回执的hash一致。组合原生测试另1项通过；LM2真实路径结构检查另1项通过。总计40项不同测试。

组合回执：`code/build/test/bootstrap-components/integration/run-a0b91bcedc78/summary.json`。首轮组合夹具的数组类型语法错误、Windows stdout换行转换失败均保留在构建目录；修正夹具后两模式成功，没有用失败结果冒充通过。正式七个模块未因此修改。

集成总回执：[batch3-integration-result.json](../.local/reviews/batch3-integration-result.json)。未运行OS/VM、性能基准或全语言回归；不将这一组定向回归标成完整L3阶段验收。

## 目标文件与身份

| 原任务 | 集成目标（源码相对code，works相对本项目任务目录） | SHA256 |
| --- | --- | --- |
| claude:C7 | `lang/bootstrap/cfg_reachability.dg` | `efe2caddefd9b6634d0d3b1633b4caa992b077debc674a942d47920ae4bbc5a3` |
| claude:C7 | `lang/bootstrap/cfg_reachability.md` | `9d3dd6e9f2baa997e77018f4db5764da982e0fcd261bfb553200c01dd8df027d` |
| claude:C7 | `lang/tests/test_bootstrap_cfg_reachability.py` | `cdd84e45d3a722afa2d42465e827473343df5250980df22d714d510f763bb170` |
| claude:C8 | `lang/bootstrap/sysv_integer_args.dg` | `75c4ab5fd07d586684eb753958654e6e6658ff90e4d77f2a1ea96cb110573204` |
| claude:C8 | `lang/bootstrap/sysv_integer_args.md` | `e019998826a2007980a2b4e843b1e01cc546492c6a9fd0226de71a9a77ecf700` |
| claude:C8 | `lang/tests/test_bootstrap_sysv_integer_args.py` | `456029c0d9dc290f27dd1e7a062e5d0168e73d97b756792125f67d14f423fcff` |
| claude:C9 | `lang/bootstrap/parallel_moves.dg` | `f6e6563e9a7994f788f0ef00eb5cf47f194d05961067b4ce20e5fd3663a6c8eb` |
| claude:C9 | `lang/bootstrap/parallel_moves.md` | `821319fca07c84beda9011b800ee7c29d5b0dbcf28914a9e0ef69a4c714a3302` |
| claude:C9 | `lang/tests/test_bootstrap_parallel_moves.py` | `514865571594f5d6ca6f174aaae77483317afa3dd903a20588cc0c481e4bc677` |
| claude:C10 | `lang/bootstrap/stack_slots.dg` | `eb6d21cf8e1099725d86048926efee272845404be3361dc809bf0121f4918312` |
| claude:C10 | `lang/bootstrap/stack_slots.md` | `3ffea4a2e737ef00661f80ca05678f3a8fd1c12875728e90189cab8f93cc83fd` |
| claude:C10 | `lang/tests/test_bootstrap_stack_slots.py` | `98d1068c156205b76a9cb6757545df552ccc2a65c3552bf275d217bb338a5ba9` |
| claude:C11 | `lang/bootstrap/switch_cases.dg` | `b7c37bc138c0eb1903167cb0df5a9e8b416e98bfa8de4ee22e8ff3234a738887` |
| claude:C11 | `lang/bootstrap/switch_cases.md` | `0a3533a0b2e31aafb0c2bb5ea9042976821dfba1f573da3ad246c6cbdb49e99f` |
| claude:C11 | `lang/tests/test_bootstrap_switch_cases.py` | `4db7dc2ac4013a7be91138d39c00db4b52a3941cdb807455001c229247bfbdec` |
| claude:C12 | `lang/bootstrap/cleanup_plan.dg` | `655b2a50fbfd68b5af3593eb97d0e9c50e6efad09f9f8a0798a857df61b8f8d9` |
| claude:C12 | `lang/bootstrap/cleanup_plan.md` | `cf26ddca3b148666eb39472fbe63d93ca7ae5ebcf9b8d634ff732b7d5cb02147` |
| claude:C12 | `lang/tests/test_bootstrap_cleanup_plan.py` | `710ffdf1901eaa36db212f4eb0df0823c9c1b2b7ab648f559096f2853b5b3ffc` |
| cursor:CR1 | `lang/bootstrap/nasm_bytes.dg` | `1b3466b9520d1d8ba63088d7cb474e33bbe2e65d040ec145878f232c788f036f` |
| cursor:CR1 | `lang/bootstrap/nasm_bytes.md` | `17fd383eba45e684406cd2478afa6f3818c39b83676b44be334b2ef4ffd91f76` |
| cursor:CR1 | `lang/tests/test_bootstrap_nasm_bytes.py` | `7f1cd7bf38f2f612b78e4161db56e949f0b43a033e3acb79b50bb013084c2941` |
| lmstudio:LM2 | `lmstudio-works/docs/handoff-checklist.zh-CN.json` | `b2008db56854c986375ce62e7289fa531d91a9ebc4125e8378fccf1e035fc9b1` |
| lmstudio:LM2 | `lmstudio-works/deliveries/LM2.md` | `46f0c20818863a468c5c704d101889214921cdf8a2d21920793a4e98320bbffa` |
