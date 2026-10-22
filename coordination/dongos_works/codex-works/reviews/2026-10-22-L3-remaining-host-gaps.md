# L3/L3A 后续宿主缺口复核

本记录为主线方法增量冻结时的只读审计，不是完整语言通过报告。使用正式作业 `058669dd13d2447c888d7e9c5f2d2f20` 的 good 编译器，先逐一核对47模块 staged/source SHA一致，再对16份 seed 接受的源码运行32次原生编译（debug/release）。无 seed fallback、目标 IR 构造或输出改写。失败32次均保留原输出，具有原始源码位置与 frontend/lower 精确状态。

审计源码：`codex-works/reviews/L3-host-gap-audit.py`。完整指纹、来源及状态：`codex-works/build/L3-host-gap-audit/run-fa765f868ad1/summary.json`。源码使用模块 `probe`，每项单独落盘并保存SHA；此审计只比较源码接受/拒绝，不将 seed 编译或原生仅编译成功计为真实执行通过。

| 语法/能力 | 当前冻结主线观测 |
| --- | --- |
| range / array / slice 的 for | lower UNSUPPORTED，detail70 |
| bool match | lower UNSUPPORTED，detail73 |
| 函数值和函数指针调用 | lower UNSUPPORTED，detail51 |
| volatile、unaligned、atomic、compiler_fence | lower UNSUPPORTED，detail60 |
| 白名单 asm pause | lower UNSUPPORTED，detail77 |
| optional/orelse | lower UNSUPPORTED，detail9 |
| enum 构造/match | frontend UNSUPPORTED，stage4/code8/detail4 |
| error 声明/返回 | frontend UNSUPPORTED，stage4/code8/detail5 |
| result/try | lower UNSUPPORTED，detail81 |
| defer | lower UNSUPPORTED，detail72；L3DEFER1独立候选另行复验 |
| Win64 | lower UNSUPPORTED，detail81 |

此处16项是确定的剩余失败样例，不是完整枚举。仍须按活动 Python seed 的语言、ABI、诊断及运行期检查合同建立完整证据；少数G5探针转绿不能关闭整个G5。原子/asm等已验收文本组件也尚不等于整程序降级或原生汇编器接线。本轮不抹去已有G4/G6的历史源码及runtime5/compiler_job profile结论，也不把其覆盖外推到新源码和完整语言。

## 合并源码复查（L3FLOWINT1）

在新的冻结作业f48ec24178864741a9a0b2d09290f546之good编译器上重跑同16项：重新核对47模块staged与当前生产源相等，lower SHA为2eb36a91291ce4293e89654a9f2b91e1edf9742e8b87c73624a701dc2e10241e。for-range、for-array、for-slice、bool-match、defer五项×两模式已由明确失败变为原生编译成功；此审计未执行目标，状态严格标为compile-only-needs-execution，真实行为由正式永久25项/独立C/原生ELF门禁另行检查。

其余11项×两模式仍精确失败且原输出保留：function-pointer、volatile、unaligned、atomic、fence、asm、optional、enum、error、try、Win64。完整新记录位于codex-works/build/L3-host-gap-audit/run-da0643ee50ed/summary.json，旧run-fa记录保留。矩阵仍不是完整枚举，也不因五个样例转绿关闭完整G5；更广defer、完整ABI和诊断等仍需覆盖。
