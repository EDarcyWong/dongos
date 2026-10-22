# G5ALIGN1 delivery

Candidate extends the G5EXEC1 snapshot with FRAME_ALIGNMENT, dynamically aligned
R12 frames and a combined 4096-byte stack budget. Public IR descriptor sizes
remain unchanged. Tests cover 64/1024-byte local alignment, typed copy, stacked
incoming parameters, nested outgoing calls, a Win64 wrapper, oversized frame
rejection and an actual bad Dong local address emitter.

Initial cold run passed alignment/Win64/real-address negative execution but the
oversized-frame test expected rejection during emission: lowering correctly
rejected its 4096-byte allocation first. The assertion now accepts the precise
FRAME status from either real backend stage and still requires unchanged output.

Final cold development: **4 tests, 0 skips, 607.494 s**, passed. Evidence
`code/build/test/g5-alignment/run-6e8a68bab57d/`; 47 frozen candidate/closure
inputs stable, 6 differential execution records including 2 negative records.
The bad Dong emitter shifts local addresses by eight bytes, compiles/links and
normally returns, then the independent C alignment oracle rejects it with exit
17. Both same-input good and seed pass. The G5TAG1 known-match flow correction
is incorporated.

Formal independent verification, acceptance and real mainline integration
remain required. Overall G5 is not marked complete.


## AI交付 2026-10-22T07:23:40+00:00 · codex-mcp-a56c25d7f28e4bc4

最终冷开发4tests/0skip/607.494s，run-6e8a68bab57d，47初始冻结依赖稳定，6真实差分记录含2正常执行错地址负控；64/1024对齐、局部复制、incoming栈参数和outgoing调用、Win64组合帧、超大FRAME失败原子输出通过。公开IR尺寸不变，R12保存恢复，G5TAG known-match修复已同步。未验收/集成，等待独立复验。
