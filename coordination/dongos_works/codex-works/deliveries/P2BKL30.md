# P2BKL30 交付

按 `dongos/codex:P2BKL30` rev2 完整任务书实施，仅六个声明文件：新增
`kernel/sched/user_bkl.dg`、`tests/user_bkl_probe.dg`、`tests/user_bkl_probe.c`、
`tests/test_user_bkl.py`、`docs/p2-fair-bkl.md` 和本交付。未修改 Bridge、Domain、
bootstrap 或汇编；未来生产接线另项处理。

新 sidecar 一次永久绑定实际 Domain，bind 不读取旧 GS 下的硬件。公开 const
192B State 供后续原始采集，CAS 发票/claim、防 MAX 回卷。等待始终执行实际
Domain poll/pause 和同一 absolute deadline，前驱释放不会抹掉已观察到的排队；
到头仍保留真实 Domain acquire 与实际 kernel root 检查。原头票 bootstrap
等待超时仍为 0x06090005，FIFO 等待超时独立为 0x06230004。错误保留票且不
交接，未来调用者必须进入原 Bridge held。实际 unlock 成功后先清旧 wait/owner、
最后发布 serving，支持 LOCKED 和真实 select 得到的 RETURNING，失败不清票。

新门禁真编译实际 Dong FIFO/Domain/queue，C 使用 TLS CPU/root/IF0、原子
硬件锁/clock 和真实 Windows/POSIX 线程。强制票 0/1/2 后旧主重入票 3，独立
核取得顺序与唯一 owner；票 0 的真实 barrier 等待票 1/2 实际 poll 写 ACK。
每模式 19 正常/拒绝场景、11 真坏 DG 源；预期 24 次编译、60 原生执行、零 skip。
拒绝场景包括原 head Timeout、queued Timeout、已过期限的空闲 head、重复 CPU、
foreign/IF0/root、unlock failed 和 overflow。坏体必须编译链接成功再 rc1，
不能拿编译失败或 subprocess timeout 替代真实原生拒绝。
独立只读复审发现最初 MAX 坏体可能先触发 debug 算术 panic，现已改为错误放行
MAX-1 的 guard 并运行该边界，两个加法均不溢出，要求实际 C 状态/返回码断言
拒绝。意外 Dong panic 使用独立前缀及 rc97，Python 显式排除 panic、信号与
进程崩溃；19 场景、11 坏体数量保持不变。该修正首次提交时未运行编译或测试；
后续正式作业的真实局部结果及新返修见下文。

每次 run 保留失败 summary、完整 source/tool 前后 SHA、实际模式/layout/源图、
原始命令输出、对象/EXE hashes、2232B 真实宿主原始 State/Domain/Cpu 快照与独立
u64 解包。回执明确 synthetic hardware、实际原生线程，Bridge 未接入，AP CPL3、
QEMU 和 OS 构建均未执行。FIFO 只防止插队，不把 R9/R10/R11 未定首因归责为
不公平锁，也不宣称期限内进展或实际 AP/PCID 已证明。

待协调器独立定向检查：`module:tests.test_user_bkl` 和
`module:tests.test_user_domain`。实施者未编译、测试、运行 OS/VM、提交/推送或
变更任务状态；本交付不登记通过/验收。静态检查和最终 SHA 另由冻结消息提供。


## AI交付 2026-10-22T22:03:30+00:00 · codex-mcp-daece153b59c4bd5

已在主工作树完成授权6文件独立FIFO BKL组件及真实DG/Domain/native线程测试，Bridge/Domain生产入口尚未接线。根审查和独立只读审查已读源码/原绝对deadline/fail-held/ACK/atomic发布顺序。修复负控误用运行时panic：overflow mutant仅放行MAX−1不触发算术overflow；__dong_panic独立前缀和exit97，Python拒panic/崩溃/异常退出作为oracle拒绝。19正常+11真实坏源×debug/release，24编译/60native计划。未执行编译、测试或VM，等待协调器独立复验；不宣称修复WHPX超时或AP验收。详见P2BKL30交付。

## rev5 返修与真实失败记录

协调器正式作业 `3be554a207994b029e7a60feffdce896` 整轮失败：首模块
1 test/0 skip、17.578 秒，source/tool stable；后续 Domain 模块未执行。
只读核对 immutable `workspace/build/test/user-bkl/run-899f355da7a8` 的 summary、
原始命令 stdout/stderr：debug normal 真编译/汇编/链接，19 场景全部 rc0，
包含真实 TLS 线程 0/1/2/3 票序、实际 poll/ACK、RETURNING 与 MAX；前七个坏体
也真编译/链接后由 C 预言正常 rc1 拒绝，无 panic。总计八个已生成对象/EXE、
26 个原生进程；release 和余下四个坏体未验证，不把局部结果登记为通过。
summary SHA256 为 `8e97ba72f7e60892f1f46657ed654ff4d77562a78d31e064a2e53eb650e9241d`；
fair 原始 2232B 快照 SHA256 为
`0f41c5724a27daf1fe981f935a1123b76e6c0f5ca14d82c1ec88a8209705d4b6`。

失败是第九次 debug 编译的 `clear-ticket-after-acquire-failure` 坏体把 u64
err(e) 直接 return 到 !void。现仅把坏体返回改为转发原 !void result，仍实际
清错票、仍由 C 的原错误码及票保留断言拒绝；不改编译器、正常 sidecar、probe、
Domain 或 C 预言。逐项静态复核其余十个坏体仍保持原错误行为，panic/crash
继续明确拒收。19 正常场景及 11 坏体不变；返修未编译、测试或运行 VM，旧
失败回执及产物未改，等待协调器新的完整独立复验。


## AI交付 2026-10-22T22:12:22+00:00 · codex-mcp-daece153b59c4bd5

R2修正首轮独立3be554a207994b029e7a60feffdce896发现的坏源编译错误：clear-ticket-after-acquire-failure将err(e)直接u64 return改为原!void result转发，与已有runtime_large/runtime_exec相同合法模式。核心/两probe保持不变；其余坏体逐项静态审阅。首轮整体failed，实读原始归档为debug19 normal rc0及7坏体正常oracle rc1，8次真实编译/assemble/link成功，第9编译失败；release与后续Domain未执行，source/tool稳定，文档如实保留历史。未自行再编译测试/VM，等待新独立复验。
