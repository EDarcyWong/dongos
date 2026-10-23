# P2DISCOVERY22 交付

状态：源码与契约已落盘，待 root 提交并独立复验；本交付不声明通过或集成。沿用 root 已领取的 rev2，执行者未修改任务状态。

修改范围：

- `kernel/user/device_host.dg`：新增内核 unsafe `preflight_discovery()`，要求 TABLE 已初始化，调用生产 `discover()` 并原样传播失败。原总线/slot/multifunction 扫描、完成标志及后续逐条硬件身份复验保持。
- `kernel/sched/user_boot.dg`：在新 INFO 前预先核验全部 Context 身份/ONLINE 与 AP current/timer drained 条件，并保留原逐 CPU 构造前的 Context 核验；在这些检查成功后、新 INFO/Domain/Bridge/Header 分配或 AP 用户 publish 之前调用 preflight。
- `docs/p2-device-preflight.md`：记录实际调用顺序、失败持有语义、fallback、权限边界、R6/R7 失败证据与首因推断的区别，以及尚待正式复验的范围。

未修改任何 timeout、acquire deadline、PCID、timer、ACK、Domain、legacy bridge、B18 路径或旧 owner 政策。预检不授予用户设备角色、路由 IRQ 或分配 DMA。后续 enumerate/bind/revoke 继续使用原实际硬件验证。

静态审查确认 `dong_services_prepare` 先完成设备窗口与内核 ledger 初始化，用户入口构造随后才被 runtime7 的 3..16 CPU 策略选择；1/2 CPU 与其它 runtime 级别仍走原路径。独立只读 reviewer 未发现生命周期、错误传播或现有 native fixture 新 stub 阻断。

验证：仅进行了源码/契约静态审查及限定路径 `git diff --check`。未执行编译、测试、OS 构建、VM、提交或推送。R6/R7 是已有真实失败诊断；R7 的 214 份原始物理读取已按长度与 SHA 独立复核，输入稳定且所属 QEMU 已退出，不是本修改的通过证据。正式检查仍为任务指定的 normal activation、device manager 原生回归，随后由 root 冷构建并执行实际四核 WHPX。

冻结文件 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `kernel/user/device_host.dg` | `3c57c8101c89284a8d082f894d2255ba12322767dd2d8add46cb95dd80a4a4e4` |
| `kernel/sched/user_boot.dg` | `98bf0251448ee7c131cc9db5e74ac4490041c8827dfe42ff6b1c0c4322614bd1` |
| `docs/p2-device-preflight.md` | `70a316aa8f84643e5d52c9fba4ecd10d8a9a089c5db4a96e837d74ae11f6c904` |

交付文件自身 SHA 在最终冻结时单独回报 root，不自包含哈希。


## AI交付 2026-10-22T20:42:50+00:00 · codex-mcp-daece153b59c4bd5

实现及交付已落入声明路径并冻结；将完整 ECAM inventory discovery 移到 user_boot 新 Domain/Bridge/Header 发布之前，保持原 deadline、ACK、错误与 1/2 CPU fallback 契约。root 已实际只读审查调用顺序、全 bus/function 枚举、缓存/权限/DMA 保持和 fail-held 行为，未发现确定阻断。执行者未运行编译/测试/VM。本次待独立定向复验；此前 R7 仅提供超时根因推断，不宣称修复已通过实际 guest。
