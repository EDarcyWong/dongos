# Bounded native diagnostic output

`emit(sources, frontend_result, scratch, context, write, result)` invokes the
existing `frontend_diagnostics.render` and then sends its exact written prefix
to an already authorized callback. No diagnostic code/message/position
mapping is duplicated. Successful frontend results need no diagnostic: OK,
length=sent=0, no callback. All descriptors/aliases are still preflighted.

Write ABI: unsafe SysV fn(context:u64, bytes:*const u8, length:usize,
moved:*usize)u64. Zero return confirms moved bytes; nonzero is the original
transport code (moved is ignored). Short writes continue at the next byte.
Zero progress terminates immediately; oversized moved is a protocol error.
There are at most rendered length calls, no implicit retries, and no calls
after failure. Callback code must not mutate the borrowed inputs/scratch.

Result is five u64 words: status/stage/code/length/sent. Status is OK=0,
INVALID=1, RENDER=2, IO=3, PROTOCOL=4, NO_PROGRESS=5. Stages are 0 no diagnostic,
1 render, 2 send. RENDER preserves the renderer status and calls no sink.
IO preserves the original code; PROTOCOL records the oversized count. sent
counts only confirmed bytes and can be smaller than length. External output
cannot be rolled back; partial output is never reported complete.

Full scratch/Result ranges must not overlap each other or any sources,
frontend Result, path or source bytes. Numeric ranges must not wrap, records
must be aligned, and storage must remain accessible through return (unsafe
caller responsibility). INVALID changes nothing and calls no sink. Other
paths publish Result; scratch can contain a rendered diagnostic. Sources and
frontend Result remain unchanged. Callbacks must be nonnull per Dong ABI.
The adapter grants no file/log/process permissions and performs no syscalls.
Host transport tests do not establish guest execution or L3 completion.
