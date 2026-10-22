# `bootstrap.guest_source_reader` — 调用者读回调的有界源码装载器

本模块把“已由调用者授权并校验过的单个文件标识”变成内存中的源码字节：它只通过调用者
提供的 `read_at` 回调按顺序读取，先把数据放进独立的暂存区（scratch），确认 EOF 和最终
大小后，才一次性发布到最终输出缓冲区（out）。它不解析根目录、不打开宿主文件、不分配
内存、不保存全局状态、不授予任何 I/O 权限。

## 接口

```dong
import bootstrap.guest_source_reader as reader;

const OK:u64=0;const INVALID:u64=1;const CAPACITY:u64=2;const IO:u64=3;const PROTOCOL:u64=4;
const PHASE_NONE:u64=0;const PHASE_DESCRIPTOR:u64=1;const PHASE_READ:u64=2;const PHASE_PROBE:u64=3;
const MAX_SOURCE:usize=131072;

struct Result { status:u64, size:usize, phase:u64, code:u64 }
type ReadAt = unsafe fn(context:u64, offset:u64, destination:*u8,
                        capacity:usize, moved:*usize) u64;

pub unsafe fn load(context:u64, read_at:ReadAt, scratch:[]u8, out:[]u8,
                   result:*Result) u64;
```

`max(OUT) = MAX_SOURCE = 128 KiB`：当前主线最大 bootstrap 源码为 82,667 字节，128 KiB
留出余量同时保持有界。`scratch` 必须严格大于 `out`（`scratch.len >= out.len + 1`），因为
缓冲区恰好填满时还需要 1 字节的额外探测来区分“正好 EOF”和“文件更长”。

## 回调 ABI 与语义

回调是**函数指针**（默认 SysV 约定），不是整数句柄，因此类型系统已排除空指针；跨 FFI
传入空函数指针属于调用方未定义行为。回调必须遵守：

| 情况 | 定义 |
| --- | --- |
| 成功 | 返回 0，并把 `*moved` 设为实际写入 `destination` 的字节数 |
| 满块 | `moved == capacity`，继续在 `offset + moved` 读取 |
| 短读 | `0 < moved < capacity`，正常现象，继续读取，不视为 EOF |
| EOF | 成功且 `moved == 0`；这是唯一的 EOF 表示，也是合法的零进展终止 |
| 错误 | 返回非 0 错误码；此时 `moved` 被忽略，错误码原样写入 `Result.code` |
| 越界返回 | `moved > capacity` 属于协议违规，报告 `PROTOCOL`，不发布任何字节 |

其他约束：`capacity` 恒大于 0；回调不得写入 `destination` 的 `capacity` 字节之外；
`offset` 只增不减；EOF 之后不再调用；只有恰好填满输出缓冲时，才会在 `offset == out.len`
处发起一次 `capacity == 1` 的探测调用。读取器不要求回调支持回退或重复读取同一范围。

进度有界：每次循环要么前进至少 1 字节、要么 EOF、要么终止，循环次数最多
`out.len + 1 <= MAX_SOURCE + 1`；零进展（EOF）不会造成死循环。

## 结果与原子性

`Result.size` 是终止时已确认的暂存前缀长度：

- `OK`：`size == 文件长度`，`out[0..size]` 为原文逐字节内容；
- `CAPACITY`：`size == out.len`，文件至少有这么多字节（实际更长），`out` 不变；
- `IO` / `PROTOCOL`：`size` 为故障前已暂存的字节数，`out` 不变；
- 描述符/别名错误：返回 `INVALID`，连 `Result` 也不写，调用者只看返回值。

因此**所有失败都不修改 out 及其尾部**（scratch 可以保留部分数据）。只有确认 EOF 后
才执行唯一一次发布拷贝。`phase` 区分故障阶段（`PHASE_READ` / `PHASE_PROBE`），
`code` 保留回调原始错误码或越界返回的 `moved` 值。

## 描述符预检

以下情况在调用回调之前返回 `INVALID`，不写任何内存（包括 `Result`）：

- `result` 为空、8 字节不对齐，或其 32 字节范围环绕；
- `out.len > MAX_SOURCE`，或 `scratch.len > MAX_SOURCE + 1`，或 `scratch.len <= out.len`；
- scratch/out 的声明范围环绕；
- scratch 与 out 重叠，或 `Result` 与 scratch/out 重叠。

## 明确不负责的部分

本模块**不**校验路径（那是 `bootstrap.guest_source_path` 的职责）、**不**解析根、
**不**打开文件、**不**检查文件类型或符号链接、**不**缓存、**不**判断“读到的内容是否
是合法源码”。回调本身代表调用者已经完成授权与真实打开；把 `read_at` 指向未授权对象
或忽略 `CAPACITY` 都是调用方缺陷。

## 验证

`pool-works/tests/test_guest_source_reader.py` 用 debug/release 两模式的真实 Dong 产物
（ELF64/Win64 汇编，本机执行 Win64）驱动 C 夹具，覆盖：空文件、短文件、精确容量、
容量 +1、远超容量、逐字节短读、短读精确/超容量、分块轨迹、途中/立即/探测阶段 I/O
失败、越界读取与越界探测、起始 EOF、零容量输出、128 KiB 边界、错误码与阶段保持、
重复确定性，以及 4 个实际编译的坏实现负控（逐块提前发布、零容量探测、忽略回调错误、
探测错误阶段错误）。每个用例校验状态、`size/phase/code`、回调调用次数、输出逐字节
与三处 canary；测试还校验 14 个结构性预检不调用回调且整块夹具不变。输入源码 SHA 在
测试前后保持一致，结果写入 `build/GUEST2/run-*/summary.json`。
