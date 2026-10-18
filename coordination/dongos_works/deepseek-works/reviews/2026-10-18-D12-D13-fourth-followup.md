# D12 / D13 四次补交复验 — 2026-10-18

结论：**D13 已验收（独立标准库组件）；D12 继续补原 rewind 成功状态观察。** D1～D11 保持已验收。不增加接口、输入矩阵或新任务，不重开已闭项。

正式六项定向测试独立复跑通过，0 skip，9.512 秒；debug/release 原生运行及 ELF64/COFF 组装均通过。正式董源码和 Python 测试未改变。受测探针 SHA256：arena `96953db81fbae8da0207692654db82c6b4f557e7ee4f50e6e0185042fba315a1`；utf8 `a564bd724fe9b03989a3c529893c8a37af2eeb05aacf0583ad6618182443ffd4`。审查前后六个实现/测试/探针 hash 一致，详见证据 JSON。

## 本次关闭

复用三次复验的三个原坏实现，各在两模式成功编译、链接、实际命中一次后立即断言拒绝，共 6 次拒绝、0 漏检：

| 原模式 | 首次命中处的实际拒绝 |
| --- | --- |
| D12 init 溢出容量失败写 storage[-1] | `SG(sg,32)`，C 探针原第71行（观察器增加一行） |
| D13 单字节 NUL decode 写 input[-1]、紧接 validate 恢复 | decode 后单字节 sb guard 断言，恢复调用未执行，hit1 |
| D13 U+10000 精确容量 encode 的 f0 改 f1 | `memcmp(o,wsc[k].bytes,w)` 独立完整期望前缀断言 |

证据：`build/test/collaboration-review/guards-c5ec1513555f/`；脚本 `check_guard_oracles_third.py`。包含正式六项日志、私有董副本、C 观察器、汇编/对象/可执行文件、逐模式命中及 hash。此前关闭的 UTF-8 padding、Decode/written 双端、pre 物理容量、各宽度失败原子性及原输入 guard 保持关闭。D13 原有限返修清单已完成，正式验收；这不表示已接入 L3 词法/诊断。

## D12 原剩余：成功 rewind 的 used 值

上轮已明确要求原成功 rewind 返回点核对 `used/base/capacity`。本次补了若干 base/capacity，但以下既有 `mark=0` 返回点仍缺 `used==0`：300 步随机段内每37步的 rewind、该段之后独立 rewind、非法 alignment 组之后 rewind、精确容量组 rewind、最后复用组 rewind。无需新增调用或输入，只在原返回后、下一调用前补该断言。已经检查 base/capacity 的保持原样；原独立/非法 alignment 后尚缺者一并按原要求补齐。

独立最小董坏实现仅在**原300步段后独立 rewind**（capacity256、mark0 的第10次）返回错误的 used=1。它成功编译、链接，在 debug/release 各实际命中1次后，现有整个原生探针仍 exit0 / probes passed。后续独立 C 模型以已经错误的 used 作为输入，不能替代对 rewind 结果的直接检查。证据：`build/test/collaboration-review/rewind-8d197eae5570/`；脚本 `check_arena_rewind_remaining.py`。只对原未闭成功字段核对点做负控，不扩大验收范围。

原 init256 的成功返回点只有 SG 而缺即时 storage 正文比较；按第三次复验既有要求补上 `memcmp(storage,snap,256)`，不要延至下一 allocate。原 init32 失败溢出 guard 已关闭，不重做。

D12 仅需补上述原返回断言，追加准确位置/hash/实跑结果后提交待复验。保留四次交付及全部历史记录；不修改算法，不新增任务，不让 Codex 代修 DeepSeek 源码。

本次未运行全项目回归、OS/VM 构建/启动，未提交或推送；定时检查与关机保持取消。
