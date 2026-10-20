# PR10 / PR8 接续处理

## 最终GitHub门禁（2026-10-20 22:51）

PR10已合入main d7468a1；PR8候选50ab7cf已完成阻塞修复、独审和完整CI，已转为可评审，尚未合入main。
[最新门禁快照](2026-10-20-pr10-pr8-integration-checkpoint.json)。本地主线已包含PR7/10；PR8源码与异机状态的本地同步仍是合入后的独立工作。

## Linux固定点实物复核

准确候选为 `50ab7cf9cde101691774a8480bdb7fcc07c766be`。language-0 job
118675046435已成功；准确head完整CI20个job全部成功，P5/输入专项也全部通过；PR8已转为ready，尚未合入main。

从GitHub下载artifact12272786821并独立校验ZIP摘要与CRC；两份receipt的49模块
源码指纹及输入blob均匹配该提交。debug/release两seed路径的四份ELF逐字节一致：

- 大小：1,892,648字节。
- SHA256：`e7f2424dc2010cf5b66e32c14faafec87f1f0f76051c04bd4e9eee050d34c9f2`。
- 输入blob SHA256：`1d97c57e1f6cbd5cfd795bce687f854e6ad00c59d86751871644c35099b33e48`。
- ZIP SHA256：`b666cccba586fee8dfedcd62aed9f0d2f240cf45aa97beab9b5fc164869464a3`。

两模式全部构建/执行命令rc0，实际native-generated startup bridge检查通过；
56MiB arena、64KiB guard栈及既有32预检、语义/容量负控全部保留。
下载产物只做数据核对，未在本机执行。此处为宿主固定点与桥检查，G6客体双启仍未验收。

[固定点核验记录](2026-10-20-pr8-fixedpoint-proof.json)；
[准确head完整CI](https://github.com/EDarcyWong/dongos/actions/runs/39436523413)。

本轮按用户要求先核对 PR10，再处理 PR8 阻塞。PR10 已正常合并，merge
`d7468a17481a6c55c9add7035aff5e67c577de51`。PR8 接续基线是
`15eb695c2bab44b8e20a4018ef46cd5bea1672a1`，已包含该主线；不重复合并 PR10。

## 修复范围

- `bootstrap/compiler_job.dg` 的入口桥在调用前恢复 `RCX <- R10`，长度24→27字节。
  内核已设置 R10；不修改全局 SYSRET 或权限实现。
- 宿主 ELF 解码器同步 rel32、目标和尾部偏移。完整固定点仍调用纯编译核心；
  每次加载的真实原生生成桥另执行前缀与 call，用独立观察器检查六参和栈对齐。
- 快速机器测试抽取生产桥文本，RCX置毒值、R10给正确第四参；移除恢复指令的
  NOP坏桥正常到达观察器后仅因第四参不符被拒绝，不以崩溃或构建错误代替负控。
- 移植已开发的 NASM 分组帮助探测与永久测试，保留旧平铺帮助及严格警告失败。
- CI增加完整固定点的源码绑定回执和stage1/stage2 ELF产物留存；不改变测试条件。

## 已完成的独立审查与定向验证

- P5 独审：`device_host`、`devices`、`virtio_quiesce`、`device_manager` 与
  main完全一致；完整DMA租约、`contiguous/dma_reserved/share_at/dma_snapshot/destroy`
  及退休/hold顺序保留。compiler栈/P2增量独立，无生产 `release_dma` 回退。
- 入口桥独审：27字节布局、rel32@11、目标/尾部@15正确；宿主观察器在客体退出
  syscall前返回。好坏机器桥组装和链接均成功；好桥exit0，坏桥exit90并精确报告
  `FAIL startup argument 4 differs`。新快测1项、0skip、0.935秒。
- NASM兼容：10项、0skip、0.469秒，前后源码SHA稳定。
- 原生产启动门禁/生命周期：3项、0skip、18.116秒。
- 协调控制台：149项、0skip、95.401秒，包含真实Windows进程结算测试。
- 完整宿主固定点以新head的Linux CI为准，不能把上述局部通过写成完整固定点通过。
  本机Windows两次运行318.560/321.430秒均失败于固定ELF地址映射，尚未进入seed执行，
  不计成功。诊断确认旧TDM PE及主线程栈占位；仅调整PE基址仍不足，临时尝试已撤回。
  保留全部失败实物，不放宽ELF固定地址、RX/RW或段/入口验证。最终源码机器桥快测
  在本机独立再次通过（1项、0skip），完整ELF证据由Linux CI及新增产物回执提供。

准确head的完整CI和P5/输入专项已全部成功，原53文件在本地主线快进后仍逐字节匹配保全清单。此前15eb695的权限job
118659084287已实际通过12个权限客体场景；旧 `lld-link --version` 探针超时不是
权限生产缺陷，也不需要通过修改权限断言解决。

## 本机文件与阶段边界

保全时主工作区HEAD为 `345570f`；最终reflog核对22:12已快进至 `d7468a1`，当前本地与远端主线一致并已包含PR7/10。PR8修复在干净隔离worktree处理。53个脏文件已做
ZIP与逐文件SHA保全，官方数据库备份SHA已核验；本轮修复未checkout/reset主目录，
没有覆盖本地五个UI/测试文件、任务图、DB、index或任务状态。

异机161条历史任务与本机137条记录（121活动、16归档）并非同一份状态：本机
CX6/CR43与异机同号不同义，C52/CR40也有独立后续记录，不能按较高rev直接覆盖。
本轮不运行state-sync或伪造验收/集成。现有局部任务状态保持原样。

PR8是已有开发及本轮修复的集成检查点。新桥宿主验证不会关闭G6：仍需新的不可变
内核快照、编译器fixture、真实同盘双启、逐字节ELF固定点、物理隔离和持久输出。
历史 `source-64ec14668c` / `run-3383cd152203` 与cf19 ELF指纹不作为新桥证据。

## 任务图与本机保全复核

整体图同步为3条轨道、22个环节：PR10 complete，PR8 partial待合，P5 partial、
L3B complete、L3C partial。9项任务图回归全部通过，0skip，9.949秒。
JSON schema、显式 `X-Coordination-Project: dongos` 的HTTP读取与磁盘一致、
Markdown相对链接及diff空白检查均通过。

原53文件中仅3个授权任务图文件更新；其余50个文件仍逐字节匹配保全清单，
包括本地UI、测试、派生索引及任务状态。当前本地主线d7468a1已包含PR7/10；
PR8仍在候选分支，本轮未将其历史state导入当前协调库。
