# CR2 交付：复用 CR1 的受限 NASM 只读数据声明

状态：**交付待复验**（2026-10-18，Cursor；含 R1 补交）。未经 Codex 复验，不代表验收。

## 文件与 SHA256

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/nasm_rodata.dg` | `915a57fb4e89fd5aae3ba4868f33bcba066f4e9335a983c4af530ae8547d7c5a` |
| `cursor-works/src/bootstrap/nasm_rodata.md` | `c1fce3d3592739b845c97ca40105059eb1bfdb46525b4988f6d6d6d3ba256606` |
| `cursor-works/tests/test_nasm_rodata.py` | `a655e89e3d16193b61371339a4802e9d50ab1f2ab7ceb7e61c903d3c8e2fa2cb` |

只读依赖已集成的 `lang/bootstrap/nasm_bytes.dg`（CR1，hash `1b3466b9520d1d8ba63088d7cb474e33bbe2e65d040ec145878f232c788f036f`）。未修改 `lang/`、CR1 工作区副本、Claude/DeepSeek/协调器。模块不导出 C 符号。

## 实现要点

- `emit(label,data,out,written)`：成功输出 `label` 原字节 + `0x3A` + `0x0A` + `nasm_bytes.encode(data)`。
- `label` 长度 8..128，必须以 `__dong_` 开头且后缀非空，后缀仅 `A-Z`/`a-z`/`0-9`/`_`。
- 全部描述符/别名/标签规则/需要长度预检后才写；先 `encode` 到标签后尾部，成功后再写标签行，避免半成品。
- `label`/`data` 可互叠；`out`/`written` 与二者及彼此分离。`INVALID` 先于 `CAPACITY`。

## 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_nasm_rodata.py -v
```

在 `coordination/dongos_works/` 下执行。编译根为暂存的仅含 `nasm_rodata` 的 src + 主线 `lang`（避免与 cursor-works 内历史 CR1 副本撞模块）。**3 项全部通过，0 skip，约 9.3 秒。**

证据：`cursor-works/build/CR2/run-9758a3870ad2/`。

| 测试 | 说明 |
| --- | --- |
| labels-data-capacity-readonly | 合法/非法 label 边界、容量精确/少一/多余、100 组随机、只读页；每 exe 20 项原生预检（含对齐 out 尾部别名、高位长度溢出） |
| dong-nasm-bin-roundtrip | ≥120 组董实际输出（含空 data 标签行）全部真实 `nasm -f bin`，还原原 data |
| 负控 | bad-colon / bad-early-written / bad-skip-label-check；debug/release 实际编译链接执行后被拒绝 |

## 坏源码负控

| 名称 | 改动 | 拒绝 |
| --- | --- | --- |
| bad-colon | 冒号改为 `;` | output |
| bad-early-written | CAPACITY 前写 `*written` | guard/atomicity |
| bad-skip-label-check | 跳过 label 规则 | status |

## 限制

- 只跑本项定向测试；未跑 OS/VM/全回归。
- 未提交、未推送。保持待 Codex 复验。

## R1 补交（2026-10-18）

针对 [CR2 R1 复验](../reviews/2026-10-18-CR2-R1.md)：**正式 Dong 源码未改**（`nasm_rodata.dg` / `.md` SHA256 同上）。仅修测试观察器原 case5。

### 修复

原 case5 使用 `label=out+80`、`len=8`，但该处曾是 `0xA5` 填充，非法标签先被 `label_ok` 拒绝，遮住完整 out/label 声明区间别名检查。现于 `memcpy(saved,arena,...)` **之前**增加：

```c
if(i==5)memcpy(o+80,oklab,8);
```

使 label 其余条件通过，仅因完整 out 尾部别名而 `INVALID`。仍为 20 项预检，不扩展输入矩阵，原三类负控不变。

### 命令与结果

```
python -m unittest discover -s cursor-works/tests -p test_nasm_rodata.py -v
```

3 项全部通过，0 skip，约 9.1 秒。

| 文件 | SHA256 |
| --- | --- |
| `cursor-works/src/bootstrap/nasm_rodata.dg` | `915a57fb4e89fd5aae3ba4868f33bcba066f4e9335a983c4af530ae8547d7c5a`（未变） |
| `cursor-works/src/bootstrap/nasm_rodata.md` | `c1fce3d3592739b845c97ca40105059eb1bfdb46525b4988f6d6d6d3ba256606`（未变） |
| `cursor-works/tests/test_nasm_rodata.py` | `a655e89e3d16193b61371339a4802e9d50ab1f2ab7ceb7e61c903d3c8e2fa2cb` |

证据：`cursor-works/build/CR2/run-fe1197400f08/`。保持待 Codex 复验。
