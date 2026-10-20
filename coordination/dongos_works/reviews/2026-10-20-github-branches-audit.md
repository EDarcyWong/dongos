# GitHub 全部分支与合并需求核对

核对时间：2026-10-20 21:25（Asia/Shanghai）。GitHub分支API、全部PR、精确head的Actions及失败job日志均实际读取；git ls-remote与fetch再次确认11个远端分支。主线固定345570f。

结论：**还有3组代码值得在门禁关闭后合入；P6实验验证暂缓。其余6个非主线分支已完整包含在main，无需重复合并。**

本轮只读审查和离线merge-tree预演，没有切分支、修改实现/任务状态、合并、推送、重跑CI或启动OS/VM。

## 全部11个分支

| 远端分支 | head | 相对main | 建议 |
| --- | --- | --- | --- |
| main | 345570f | 当前主线 | 基准 |
| codex/p5-recovery-dma-journal | b4c8236 | 已为main祖先 | PR5已合并，无需重复 |
| codex/p6-input-irq-fix | 18543a2 | 已为main祖先 | PR4已合并，无需重复 |
| docs/p5-p6-engineering-handoff | ea65932 | 已为main祖先 | PR6已合并，无需重复 |
| docs/p5-p6-merged-checkpoint | e854461 | 已为main祖先 | PR9已合并，无需重复 |
| dot/verified-components-console-20261020 | 9033b51 | 已为main祖先 | PR1已合并，备份无遗漏 |
| dot/l3-host-checkpoint-20261020 | a6be507 | 已为main祖先 | PR2已合并，备份无遗漏 |
| codex/p5-virtio-reset-hold | 3a5c773 | 独有4提交，13文件差集 | PR7先等完整CI，再合 |
| codex/p5-dma-alias-refusal | 1c00a6f | 独有6提交，含reset继承；对main18文件 | PR10在PR7之后对齐main再合 |
| tasks/2026-10-20-c0-c2-integration | 2a1a286 | 独有6提交，414文件（code83、coordination330及根检查点） | PR8需要集成，但有CI失败和本地重叠待处理 |
| codex/p6-input-irq-kvm-validation | 288d65c | 独有8提交；9文件中3个输入文件已与main相同 | PR3保留候选，验证门禁未过 |

来源：[全部分支API](https://api.github.com/repos/EDarcyWong/dongos/branches?per_page=100)、[PR1](https://github.com/EDarcyWong/dongos/pull/1)、[PR2](https://github.com/EDarcyWong/dongos/pull/2)、[PR4](https://github.com/EDarcyWong/dongos/pull/4)、[PR5](https://github.com/EDarcyWong/dongos/pull/5)、[PR6](https://github.com/EDarcyWong/dongos/pull/6)、[PR9](https://github.com/EDarcyWong/dongos/pull/9)。完整API快照见[JSON](2026-10-20-github-branches-audit.json)。

## PR7：停止后VirtIO复位与DMA持有

[PR7](https://github.com/EDarcyWong/dongos/pull/7)，head3a5c773，draft，GitHub mergeable=true，但检查未全部完成。

- [P5专项39422980556](https://github.com/EDarcyWong/dongos/actions/runs/39422980556)两job成功，包含实际virtio-reset-guest；输入专项也成功。
- [完整39422980582](https://github.com/EDarcyWong/dongos/actions/runs/39422980582)当前18个job成功，language-tests(1)仍运行，最终汇总尚未生成。
- 实际调用链为永久owner退休后revoke_owner→quiesce_stopped_block→可信VirtIO reset，MSE/BME/INTx与身份重查、1024次有限读回、sticky HELD；不回收DMA。
- 新xhci fixture修复复用真实PCI/VirtIO依赖，没有放宽断言。与本机当前未提交路径无重叠。

源码审查未发现阻止该受限功能集成的生产缺陷。建议完整精确head CI结束后先合，不据此关闭整个P5。

## PR10：普通USER映射拒绝DMA整块别名

[PR10](https://github.com/EDarcyWong/dongos/pull/10)，head1c00a6f，draft；目标分支仍是codex/p5-virtio-reset-hold（API基点e2ae56b），不是main。

- [P5专项39423326913](https://github.com/EDarcyWong/dongos/actions/runs/39423326913)两job成功，包含实际guest；[完整39423326930](https://github.com/EDarcyWong/dongos/actions/runs/39423326930)18成功、language-tests(1)仍运行。
- 实际memory相对main净差仅14行新增：dma_reserved扫描全部owner及完整向上取整块，share_at拒绝RO/RW普通别名，包含未映射尾部；安全减法避免端点溢出。
- 历史上传截断已由592c813修复；最终memory无其它净删除或算法倒退。缺__dong_panic的旧链接失败已修，不当作原生通过。
- 与PR7共享reset核心；两分支各自xhci fixture修正内容相同，虽然不是严格祖先关系，不能据独有提交数误判重复功能。

建议PR7合入后，把PR10正确对齐main并核对剩余差集/检查，再合。不得将PR10只合进一个已结束的旧base后误认为main已经得到防护。

## PR8：P2/L3及协调器检查点

[PR8](https://github.com/EDarcyWong/dongos/pull/8)，head2a1a286，draft，414个文件，值得集成已完成组件与历史记录。

- 最新提交仅改14个测试/夹具，适配Retired布局、scratch页数、COMPILER fixture与PIE链接；没有修生产启动桥。
- [完整39428786301](https://github.com/EDarcyWong/dongos/actions/runs/39428786301)仍运行，已有[permission job118648057647](https://github.com/EDarcyWong/dongos/actions/runs/39428786301/job/118648057647)失败：工具检查时lld-link --version超时10秒，尚未执行权限客体用例。这是失败事实，不直接认定为权限代码错误；应重跑确认并取得成功结果。
- 已知客体缺陷仍在：kernel已把arena传R10，compiler_job的24字节桥未mov rcx,r10；宿主测试跳过桥直接调用target，不能覆盖SYSRET覆写RCX。L3-RESUME明确CX14仍在途、原CX16需27字节桥和新快照双启。
- 分支保留PR5的DmaLease/snapshot/contiguous/destroy和DMA hold，没有偷偷恢复release_dma；不依赖尚未合并PR7/10，但后续需要合并各自独立功能。
- 分支中WINVERIFY1、MCP池、P2扩展、L3读取/写入/栈/固定点等完成代码应恢复，不重开发；其中部分任务图文字落后于该分支自身完成记录，应保留本轮核对更新。

提交层面main与PR8的merge-base为208029b，主线后来只修改交接文档，普通三方merge可以保留最新文档；离线预演无冲突。

**本机工作区另外有实际重叠**：13个tracked和7个untracked路径，含控制台UI、任务图、ALLOCATION、C52/CR40状态和CX6/CR43同号记录。不能把提交层面的clean误作工作区可以直接覆盖。应先保存当前改动，协调同号身份及状态，再正常三方集成；不整文件选取远端index/state/roadmap覆盖本轮成果。

若以未完成开发检查点合入，必须保留显式编译profile限制和CX14未完成结论；若要求合入即可使用客体自举，则先修桥并取得真实双启证据。

## PR3：P6验证工具暂缓

[PR3](https://github.com/EDarcyWong/dongos/pull/3)，head288d65c，draft。输入生产及两份测试与main逐字相同；剩余是6个新增验证文件。

[focused39425166102](https://github.com/EDarcyWong/dongos/actions/runs/39425166102)失败：

- [KVM job118635780078](https://github.com/EDarcyWong/dongos/actions/runs/39425166102/job/118635780078)：sudo要求密码，前置失败，未运行KVM计时；证据目录未产生，上传也失败。
- [DAG job118635780287](https://github.com/EDarcyWong/dongos/actions/runs/39425166102/job/118635780287)：实际TCG运行失败，initial AP/STARTING window missed; late readiness is not proof，失败artifact已保存。
- [完整39425166059](https://github.com/EDarcyWong/dongos/actions/runs/39425166059)其余已完成job成功，language-tests(1)仍运行；不能覆盖focused失败。

最新AP预筛只减少捕获成本，未放宽首代身份/STARTING/epoch ACK/同次停止判据。工具可保留，但当前不作为P6验收通过合并。应修复捕获/环境问题或另拆清晰的工具范围，保留失败门禁，不用豁免替代成功证据。

## 合并顺序与本轮边界

建议：**PR7 → PR10对齐main → PR8；PR3暂缓。** PR7/10各等精确head完整CI；PR8先关闭已失败CI并处理本机重叠。合并后重新验证共有memory、compiler栈、P2布局与DMA别名守卫，不能拿任一分支整文件覆盖另一方。

4个开放分支对已提交main的merge-tree均exit0，没有内容冲突；这只说明Git三方结构可合，不替代功能/契约/测试审查，也不包含当前未提交工作。

本报告是21:25快照。没有删除分支、调整PR/权限或触发CI，也没有承诺L3客体/P5安全回收/P6性能门槛完成。
