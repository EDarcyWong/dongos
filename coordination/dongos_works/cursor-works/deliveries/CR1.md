# CR1 交付：原生 NASM 字节常量编码器

状态：**交付待复验**（2026-10-18，Cursor；含 R1 补交）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/nasm_bytes.dg` | `1b3466b9520d1d8ba63088d7cb474e33bbe2e65d040ec145878f232c788f036f` |
| `cursor-works/src/bootstrap/nasm_bytes.md` | `17fd383eba45e684406cd2478afa6f3818c39b83676b44be334b2ef4ffd91f76` |
| `cursor-works/tests/test_nasm_bytes.py` | `318ffbdd9187ad985f461349733fb61a374dac9e75f8035a881714681f848526` |

模块无 import，只公开 `OK`/`INVALID`/`CAPACITY` 与 `encode`，不导出 C 符号。C 探针与导出 wrapper 写入唯一临时目录。未修改 `lang/`、Claude/DeepSeek 工作区或主线测试/构建脚本。

## 实现要点

1. `written` 非空、8 字节对齐且区间不回绕。
2. `source`/`out` 区间不回绕（空切片可为 NULL）。
3. 整个 `source`、`out` 描述区间与 `written` 8 字节彼此不重叠。
4. 需要长度 `5*N + 3*ceil(N/16)`（N=0 为 0）逐步溢出检查；失败为 `INVALID` 且不读输入。
5. `out.len` 不足 → `CAPACITY`。`INVALID` 总先于 `CAPACITY`。
6. 成功按行写出 `db 0xHH,...\n`（每行最多 16 字节，十六进制 A～F 大写），`*written` 为精确长度；失败不改 `out`/`written`/输入。

## 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_nasm_bytes.py -v
```

Windows 11，Python 3.12.6，NASM 3.02，GCC tdm64 9.2.0。**4 项全部通过，0 skip，约 11.2 秒。** 证据目录：`build/test/cursor-cr1/run-c46dcb3ef9ce/`。

| 测试 | 数量 | 说明 |
| --- | --- | --- |
| seeded-exact-short-extra | 3100 用例 × debug/release | 固定种子 `0x0C81B17E` 的 1000 条随机二进制（长度 0～2048）+ 20 组边界/特殊输入；每条测精确、多余、少一容量；覆盖 256 全字节、NUL/引号/反斜杠/换行/非 UTF-8、0/1/15/16/17/31/32/33、全 0/全 FF、多行；含只读输入页 |
| line-boundaries-empty-priority | 32 用例 × 2 模式 | 行边界与空输入；`INVALID` 先于 `CAPACITY`；每可执行文件另跑 18 项原生描述符预检 |
| dong-nasm-bin-roundtrip | 120 输入 × 2 模式 = 240 次 | 用**董实际输出**经已装 NASM `-f bin` 还原；空输出汇编结果为空；不拿 Python 期望代替董输出 |
| 负控（见下） | 4 类 × debug/release | 私有坏董副本实际编译链接原生执行后被指定断言拒绝 |

期望由独立 Python（每 16 字节分组 + `%02X`）生成。每次调用后 C 驱动立即检查输入全文与双端 guard、`out`/`written` 双端；失败时整段不变；成功时只允许有效前缀变化。debug/release 均原生执行；elf64 与 win64 均组装，宿主链接 win64。

原生预检（每 exe 18 项）：NULL/奇地址/重叠 `written`；NULL 非空切片；区间端点与需要长度溢出；伪造极端地址仅走预检拒绝路径；整个 4 KiB arena 在 `INVALID` 后逐字节不变。

## 坏源码负控（私有临时根，两模式均实际编译、链接、执行）

| 名称 | 改动 | 命中用例 | 拒绝断言 |
| --- | --- | --- | --- |
| bad-hex-case | 十六进制字母改为小写（`55+v`→`87+v`） | `[0xAB,0xCD,0xEF]` | output |
| bad-line-split | 每行宽度 16→15 | 16 字节、`cap=200` | written\|output |
| bad-early-written | 容量不足前先写 `*written` | `[0,10,255]`、`cap=5` | guard/atomicity |
| bad-early-out | 容量不足前先写 `out[0]` | 同上 | guard/atomicity |

每个负控先用正式实现跑同一用例并通过，再确认坏构建被拒绝。构建失败/崩溃/超时不算通过。

## 限制

- 只跑本项定向测试；未运行完整回归、系统构建、QEMU/VMware 或基准。
- 不做 UTF-8 校验或替换；不生成标签/节/完整汇编文件。
- 源码暂留 `cursor-works/`；主线集成由 Codex 验收后决定。
- 未提交、未推送。

## Codex 独立验收

待 Codex 写入 `reviews/`。不得自行标记已验收。

## R1 补交（2026-10-18）

针对 [CR1 R1 复验](../reviews/2026-10-18-CR1-R1.md)：**正式 Dong 源码未改**（SHA256 仍为 `1b3466b9520d1d8ba63088d7cb474e33bbe2e65d040ec145878f232c788f036f`）。仅修测试观察器与说明，复用原有限 18 项预检案例，不扩展输入矩阵。

### 修复点

1. **out 尾部别名**：原 case5 `written=out+60` 未 8 字节对齐，被对齐检查遮住。改为自然对齐的 `out+56`。另用 case4：`source` 仅落在未使用 out 尾部（3 字节 need=18，source 起于 `out+40`），仍因完整 out 声明区间别名而 INVALID。
2. **空输出真实 NASM**：roundtrip 对董实际空输出也写空 `.asm` 并实际执行 `nasm -f bin`；本轮 `nasm_bin_calls=240`，其中 `empty_nasm_bin_calls=24`，证据目录内 240 个 `.asm`/`.bin` 成对，空 asm/bin 各 24。
3. **需要长度溢出夹具**：低地址 + 巨大 `source.len` 会先覆盖栈上真实 out/written 而走别名拒绝。改为高位伪基址 `(1<<63)|0x1/2/3000`，span 合法且与真实对象分离；case11 为 `n>MAX/5`，case12 为 `n=MAX/5` 的 body/overhead 溢出，default 在 `out.len=0` 上仍优先 INVALID。

### 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_nasm_bytes.py -v
```

在 `coordination/dongos_works/` 下执行。4 项全部通过，0 skip，约 11.5 秒。

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/nasm_bytes.dg` | `1b3466b9520d1d8ba63088d7cb474e33bbe2e65d040ec145878f232c788f036f`（未变） |
| `cursor-works/src/bootstrap/nasm_bytes.md` | `17fd383eba45e684406cd2478afa6f3818c39b83676b44be334b2ef4ffd91f76`（未变） |
| `cursor-works/tests/test_nasm_bytes.py` | `318ffbdd9187ad985f461349733fb61a374dac9e75f8035a881714681f848526` |

证据：`cursor-works/build/test/cursor-cr1/run-089b29913338/`（含 `summary.json` 与 `nasm-bin/`）。四类既有坏董负控仍两模式拒绝。保持待 Codex 复验；未提交/推送，未跑 OS/VM/全回归。
