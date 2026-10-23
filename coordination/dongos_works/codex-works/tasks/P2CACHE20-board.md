# P2CACHE20 — P2调度后GOP全别名WC迁移与绘屏隔离组件

负责人：codex。状态：待领取。

用户先P2后P5。平行实现D核心组件，仅新增文件；正常memory framebuffer ledger、services poll multiplexer、panic/entry绘屏gate接线和真实VM另在B完成后统一声明并实际验收，本组件host通过不算运行期/物理WC通过。不修改旧cache_alias_owner PCIDE拒绝或永久seal，不伪造支持PGE。本最小迁移不写PAT，要求所有online CPU当前实际PAT4=WC/PAT3=UC及完整PAT/MTRR一致且全程不变，执行完整WC→UC→WC，最终USER恢复仍WC。
新runtime_cache以可信kernel hardware Space+全用户roots+独立身份recheck callback、真实BootInfo raw GOP base/bytes及完整发布ledger为前提，forest按rounded物理整页枚举kernel HHDM与compositor USER等所有alias，不准caller子集冒完整列表；预检允许的ledger必须逐项与实际forest根/VA/PA/bytes/权限/代际对应，隐藏USER/额外别名/非WB兼容/PGE/过期身份/错误PAT/MTRR均拒。保留每alias USER与WRITE/NX，禁止EXEC；每次全forest闭包复核。证明HHDM kernel表池永久非GOP锚使撤尽GOP不detach共享PML4[256]，否则拒绝。每个私有slot0按自己Space真实操作，共享canonical树只改一次，不能用不安全外来table PA放宽旧walker。容量/receipt线性总页数事先全验，caller arena动态storage，不增大BSS/帧/2MiB预算。
真实CPU0/IF0/rawkernelCR3/tag0/BKL/active healthy Domain/PGE0准入。先原子close framebuffer绘屏gate并排空active writers（NMI/panic必须可try-enter失败立即串口降级，不等BKL）；捕获全部用户，撤销全部GOPalias，第一全online alltag ACK后才回收Retired并做逐CPU SFENCE/WBINVD真实cache维护/硬件PAT/MTRR读回，按原VA/PA/USER恢复目标UC，第二全ACK并完整森林复审；再相同闭合事务恢复WC，最后成功才open gate/ledger commit。发布后任一步错误poison Domain failed，gate永久closed、lease/receipts held，不fallback/rollback或提前remap/reclaim/用户返回。booleans/flush次数不能代替perCPU action实际request-seq/root/cr0/cr4/PAT/MTRR readback。
新增runtime_cache_reader.asm含未来真实特权动作、当前可native实测的atomic gate enter/leave/close/drain/open helper；不改IDT/NMI handler或把未接线说完成。Gate拒underflow/overflow/重放/错误open，close之后原active需drain才允许撤映射，失败close不因返回路径自动open。真实privileged动作只组装两格式不宿主执行。
永久tests真实DG/paging/forest+独立C raw ledger/Retired/order oracle，debug/release/native guards及前置失败原子，硬件边界明确mock；至少真实坏源码遗漏USER别名撤销、漏ACK提前reclaim、未执行逐CPU维护/错误PAT读回、提前open gate各准确正常rc1拒绝，实际atomic gate并发或确定性interleaving检查closed期间不进入、原writers排空、失败保持closed。回执全commands/source/tool/artifacts/0skip。实现者不运行test/compiler/OS/VM/AI CLI/commit/push、不改任务状态；root独立审查正式复验和真实文件集成，物理显示性能仍另需真机。

## 可修改文件

- `kernel/mm/runtime_cache.dg`
- `kernel/sched/runtime_cache_reader.asm`
- `tests/runtime_cache_probe.dg`
- `tests/runtime_cache_probe.c`
- `tests/test_runtime_cache.py`
- `docs/runtime-cache.md`
- `codex-works/deliveries/P2CACHE20.md`

## 定向验收

- `module:tests.test_runtime_cache`
- `module:tests.test_paging`

交付：`codex-works/deliveries/P2CACHE20.md`。独立工作副本中执行；不提交、推送、运行OS/VM或修改归属外文件。完成后提交交付，等待独立复验。
