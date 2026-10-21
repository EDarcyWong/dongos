# CX6：NASM 分组帮助兼容修复

原任务 `codex:CX6`，实施基于协调器 `in_progress rev2`，由 root 领取并授权本协作者修改三个声明文件。未自行提交任务、验收或登记集成。

## 变更

`lang/tests/test_dongc.py:nasm_flags` 保留先执行 `nasm -h` 的实际能力探测。只有该帮助明确公布 `-h -opt` 一类分组帮助语法时，才继续读取 `nasm -h -w`；旧平铺帮助不接收其可能不支持的额外参数。合并两份真实帮助后，仍按行首完整警告名分别识别 `reloc-rel-dword` 与 `reloc-abs-qword`，保持 `-Wall`、`-Werror` 和其它警告。没有按版本号猜测、无条件抑制未知警告或捕获探测失败；两次实际探测均 `check=True`，真实错误向调用者传播。

`lang/tests/test_nasm_compatibility.py` 保留原能力检测测试，增加新分组格式、旧版拒绝多余参数时只调用一次、完整名与前后缀误匹配、两个警告独立检测、第二次探测失败传播测试。真实本机 NASM 小汇编在 ELF64/COFF 两种格式分别验证跨 section RIP 相对重定位及绝对 64 位指针：原 `-Wall -Werror` 控制侧确实报告指定警告，探测生成的选项成功组装有效对象。另一小汇编 `db 256` 在相同选项下仍按 `number-overflow` 以非零码拒绝。

## 本地定向验证

- 工作目录：`D:\projects\2026\dongos\code`
- 命令：`python -m unittest lang.tests.test_nasm_compatibility -v`
- 结果：**10 tests，0 skips，returncode 0**；unittest 0.343 秒，外层进程 0.485 秒。
- 本机工具：`code/.tools/nasm/nasm-3.02/nasm.exe`；真实 ELF64/COFF 组装均执行，不以 mock 代替原生组装。
- 完整日志：`code/build/test/CX6-local-15abbf5df64b/unittest.log`
- 机器回执及前后指纹：`code/build/test/CX6-local-15abbf5df64b/result.json`

本地测试前后源码 SHA256 完全一致：

| 文件 | SHA256 |
|---|---|
| `lang/tests/test_dongc.py` | `8a38a0b223e7b5eb4035b00558ddfe4d70cb9963cb51877fbe33b876eae75bb1` |
| `lang/tests/test_nasm_compatibility.py` | `e51d2e3f1e5d825ab64b68b035ec31e23416b71e994b17c4a4727c8295f85e4d` |

旧 NASM 格式和不支持分组参数的行为通过有明确调用次数约束的 mock 验证，未声称本机安装并运行了旧 NASM。这里只运行本任务定向兼容测试；未运行 OS/VM、全回归、AI CLI、提交或推送。等待 root 的正式独立复验；后续授权的整函数主线测试另行记录，不算作本任务已经完成的独立验收。


## AI交付 2026-10-20T12:56:13+00:00 · codex-mcp-6d5798b7b4b74b61

已落实NASM分组帮助兼容修复，仅授权三文件。保留旧-h平铺能力探测，仅帮助明示-h -opt分组语法时追加-h -w；check=True保留真实失败，完整名检测，-Wall/-Werror及其它警告不变。代理局部10tests/0skip0.343s，root独立实际重跑同10项全过，含真实NASM3.02 ELF64/COFF两种合法重定位正反对照及number-overflow仍拒绝。源码SHA前后稳定，详见交付/CX6.md与code/build/test/CX6-local-15abbf5df64b/result.json。当前控制台Windows正常复验结算将process_stopped=None记为停止待确认（已由C52正式作业实证）；本项先submitted，未据本地通过伪造协调器verification，不自行验收。未运行OS/VM/全回归。
