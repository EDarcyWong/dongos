# C18 交付：稳定去重的 NUL 结尾字符串表构建

状态：**交付待复验**（2026-10-18，claude-worker-1，在本机直接执行）。未经 Codex 复验，不代表验收。

说明：本任务原在协调器队列中由 CLI 自动执行（作业 6917a6d0…，排在 C17 之后尚未开始）。按用户要求，先通过协调器 `/api/cancel` 取消了该排队作业，再用 AI 接口领取后在本机完成；未运行队列副本，未手改状态库。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `claude-works/src/bootstrap/string_table.dg` | `fd0fdfb95707b1f6fb46bec81c24e91ec843a7d00e5ab87a785941d9c628725a` |
| `claude-works/src/bootstrap/string_table.md` | `2e639362a9ba1827f9354ce5e75845221fc6b5bf78985621e65127e5114be6f0` |
| `claude-works/tests/test_string_table.py` | `5cf62313645645a66317245587450ce442fd196c68964b0df7930fb2a34ef7ab` |

模块无 import、不导出 C 符号；只修改了本任务列出的文件。

## 命令与结果（实际执行）

在 `coordination/dongos_works` 下：`python -m unittest discover -s claude-works/tests -p test_string_table.py -v`

3 项通过，0 skip，约 6 秒（Windows 11，Python 3.12.6，NASM 3.02，GCC tdm64 9.2.0）。证据 `claude-works/build/C18/run-7d1e42b22bf2/`。

| 测试 | 用例数（每模式） | 说明 |
| --- | --- | --- |
| random-dict | 501 | 固定种子 `0xC18D` 的 400 组（字节池含重复短串、非 ASCII/0xFF、1..255 全部非零字节，约 30% 名字重复先前描述符，大量共享原始子串），每 4 组再测富余容量；外加 3000 个名字、700 个不同内容（只读页）；每 40 组一个只读页 |
| sharing-bytes-invalid-capacity | 34 | 空输入（含 offsets/table 恰为 1 字节、bytes 非空）、不同描述符相同内容共享、同长度不同内容、前缀不合并、非 ASCII/0x01 原样保存、5 个相同名字、整段；空名字、含 NUL（首项/末项）、越界、first/count 为 usize 最大、bytes 为空；INVALID 先于 CAPACITY；table−1、offsets−1、两者为 0、空输入 table=0 → CAPACITY；含 NUL 的 bytes 中合法名字（只读页） |
| 原生描述符预检 | 18/每可执行文件 | NULL/未对齐 result，result 与 names、bytes、table、offsets 重叠，offsets 与 names、table 与 bytes、table 与 offsets 重叠，names/offsets 未对齐，三个 NULL 非空切片，names/offsets 长度溢出，bytes/table 极端地址；状态 1 且区域逐字节不变 |

期望值由独立的 Python `dict` 构建（键为名字字节）。每次调用后立即检查 names/bytes 全内容与前后 guard（只读页例子在 PAGE_READONLY 页）、table/offsets 前后 32 字节 guard、result 前后 16 字节 guard；失败时三个输出全不变；成功时 table/offsets 尾部不变，再比对 used、完整表字节与全部偏移。debug、release 均原生执行，elf64、win64 均组装，结构布局由 C 静态断言。

## 坏源码负控（两模式均实际编译、链接、执行）

| 名称 | 改动 | 命中用例 | 拒绝断言 |
| --- | --- | --- | --- |
| bad-length-dedup | 只按长度判断相同 | "abc" 与 "abd" | table bytes / offsets |
| bad-duplicate-copy | 重复名字写入新副本 | 同一名字两次 | table bytes / offsets |
| bad-early-prefix | 验证前先写 table[0] | 末项含 NUL | guard/atomicity |

## 限制

去重为 O(n² × 比较字节数)；表长度溢出分支在实际内存中不可达。只跑本任务定向测试，ELF64 只组装，未提交、未推送、未集成。
