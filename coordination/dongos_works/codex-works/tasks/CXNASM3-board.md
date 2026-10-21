# CXNASM3 — [P0/L3] NASM分组帮助能力探测维护（异机编号隔离）

负责人：codex。状态：待领取。

所属阶段P0工具链维护，关联L3主线复验。本机NASM3.02的-h帮助将warning放在-h -w；只读-h漏掉reloc-rel-dword及reloc-abs-qword，使主线C52初始化0tests失败。此维护曾临时占用CX6；发现另一电脑原CX6是已完成的源码读取接线后，临时记录已通过协调器暂停归档并备份，现用全refs未占用的CXNASM3保留独立身份，不覆盖原CX6。
仅授权3文件：共享helper保留旧-h能力探测，只在帮助明示-h -opt分组语法时再用-h -w；完整警告名匹配、check=True保留真实失败，不按版本硬猜、不无条件关闭未知warning，保留-Wall/-Werror及其它警告。永久兼容测试包含旧平铺/新分组、拒绝额外参数的旧版、假前缀、两warning独立、分组探测失败传播、本机真实ELF64/COFF两类合法重定位的失败/成功对照和number-overflow仍拒绝。实现已完成、局部及root独立10项全过0skip；原正式协调结算Windowsprocess_stopped=None缺口未关闭，不能据本地测试自授验收。本项只维护测试工具，不重做或声称完成P2/P5/P6/L3开发。未运行OS/VM/AI CLI。

## 可修改文件

- `lang/tests/test_dongc.py`
- `lang/tests/test_nasm_compatibility.py`
- `codex-works/deliveries/CXNASM3.md`

## 定向验收

- `module:lang.tests.test_nasm_compatibility`

交付：`codex-works/deliveries/CXNASM3.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
