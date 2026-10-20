# CX8 delivery

Added one-shot authorized file artifact store backed by production files.write
and files.sync, and the already integrated guest_artifact_commit state machine.
No path/rights/open/create/truncate/close/process/power actions. Full five-region
alias/range preflight precedes State initialization and any IPC. Limits 2 MiB
artifact and 61440-byte IPC chunks, exact short-write offsets, zero progress
bound, invalid counts rejected, one successful H_SYNC required for durable.
Full-width errors retained independently of generic negative callback marker.

Local permanent test: 1 test, 0 skips, 38.282 seconds, two modes, two formats,
15 structural preflights and ten protocol plans including max-sized source,
high-bit error, short write, flush error, oversized response, version error and
zero stall. Actual skip-H_SYNC and accept-oversize mutations rejected in both
modes. Inputs stable. Earlier compiler errors (reserved field name error and
safe callback signature) were corrected before the passing run; retained failed
runs are not counted as successful evidence. One command from the wrong cwd
failed module import and was rerun from code/.

Independent source/contract/test review and formal verification pending. Does
not truncate an existing destination suffix or grant a writable token; caller
must arrange the destination. No real guest FLUSH/reboot/L3 acceptance claim.


## AI交付 2026-10-20T08:19:33+00:00 · codex-mcp-d76b66689d824a70

真实files H_WRITE/H_SYNC适配+既有commit状态机，一次性借用授权token；2MiB限制/61440分块/full alias preflight/高位错误完整保留/短写与flush门禁。主线1test/0skip/38.282秒、双模式双格式与4坏体执行通过；独立review_io复审中。契约与交付已落盘，需正式复验；不声称真实客体磁盘或重启。
