# LM8 — 最简单固定数据：8条NASM基址位移文本

负责人：lmstudio。状态：待领取。

只做最简单固定数据录入，写一个JSON及交付两个文件，不写实现或测试。文件lmstudio-works/fixtures/memory-operand-known-vectors.json。
顶层恰好version/cases，version为整数1；cases恰好如下顺序8项，每项恰好id/base/disp/text。base是JSON整数；disp和text均是给定字符串，原样复制，不自行计算。
id=rax_zero,base=0,disp="0",text="[rax]"
id=rbp_minus8,base=5,disp="-8",text="[rbp - 8]"
id=rsp_plus16,base=4,disp="16",text="[rsp + 16]"
id=r8_plus1,base=8,disp="1",text="[r8 + 1]"
id=r15_minus1,base=15,disp="-1",text="[r15 - 1]"
id=rax_min,base=0,disp="-2147483648",text="[rax - 2147483648]"
id=r10_max,base=10,disp="2147483647",text="[r10 + 2147483647]"
id=rcx_zero,base=1,disp="0",text="[rcx]"
UTF-8 JSON，不增删字段/项目，不把disp改成JSON数字。独立检查由Codex维护，不修改检查文件；不依赖Cursor任务，数据仅供后续可选补充。另写lmstudio-works/deliveries/LM8.md，说明固定数据录入，未运行测试明确未运行，禁止编造通过或自举完成。
通过自己的worker MCP查看最新rev、领取、实际落盘后提交；没有文件工具则说明并释放，不能以聊天正文冒充文件。LM Studio同时仅一项最简单任务。不改主线/他人/索引，不运行OS/VM、AI CLI、全回归、提交推送或自行验收。


## 可修改文件

- `lmstudio-works/fixtures/memory-operand-known-vectors.json`
- `lmstudio-works/deliveries/LM8.md`

## 定向验收

- `discover:lmstudio-works/tests:test_memory_operand_vectors.py`

交付：`lmstudio-works/deliveries/LM8.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
