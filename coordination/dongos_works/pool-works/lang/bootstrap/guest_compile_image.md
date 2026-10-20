# guest_compile_image — Graph → NASM text → static ELF64

`bootstrap.guest_compile_image` is a thin guest adapter. It takes a live successful
`frontend.Graph`, calls production `compiler_driver.compile`, then
`native_assembler.assemble`. It does not rebuild IR, lower, or encode instructions
in Python/C, and it does not modify those modules.

## API

```dong
pub unsafe fn compile_image(
  g:*const front.Graph,
  limits:*const driver.Limits,
  mode:u64,
  storage:[]u8,
  text:[]u8,
  entry:[]const u8,
  w:*const nasm.Workspace,
  out:[]u8,
  r:*Result)u64
```

`Result` (72 bytes, 8-aligned): `status`, `stage`, `code`, `unit`, `node`,
`detail`, `used`, `text`, `written`.

| Field | Meaning |
| --- | --- |
| `status` / `code` | Original stage outcome. Emit failures keep driver values; assemble failures keep assembler status in both `status` and `code`. |
| `stage` | `WORKSPACE=0`, `LOWER=1`, `EMIT=2`, or `ASSEMBLE=3`. |
| `used` | Bytes reserved in the emit arena (`compiler_driver`). |
| `text` | Assembly byte count after a successful emit; `0` if emit failed. |
| `written` | Exact ELF length on full success; otherwise `0`. |

Mode `0` is debug, `1` is release. `entry` must name a defined `.text` label in the
emitted dialect (CR3 `__dong_m<hex module>_n<hex item>`). That label is a callable
SysV function, not a DongOS process startup stub; this module never synthesizes a
fake `_start`.

Assembler status numbers (`SYNTAX=3`, `SYMBOL=4`, `RANGE=5`) intentionally overlap
emit codes (`UNSUPPORTED`/`FRAME`/`INTERNAL`); distinguish them with `stage`.

## Publication rules

1. Full descriptor, span, multiplication and alias preflight first. On `INVALID`,
   every caller region (including `Result` and the entire ELF capacity) is unchanged.
2. Driver `compile` runs into caller-owned `text`. On any non-OK driver status
   (including `LOWER`/`EMIT` failures such as module-level `UNSUPPORTED`) the
   assembler is not called; `Result` publishes the driver fields with `text=0` and
   `written=0`; ELF `out` is untouched. `UNSUPPORTED` is never treated as success.
3. Only after emit `OK` does the adapter call `assemble` on `text[0..er.written]`.
4. On assemble failure, `written=0`, ELF `out` unchanged, `text` retains the emit
   length, and `stage=ASSEMBLE`.
5. On success, ELF bytes `out[0..written)` are published exactly once; the unused
   ELF tail is unchanged.

Caller-owned `storage`, full `text` capacity, assembler workspace slices, ELF `out`
and `Result` are mutually exclusive. Graph / limits / entry / workspace descriptors
may share only as read-only inputs and must not overlap mutables. No hidden heap,
global cache, or OS I/O.

The borrowed Graph includes its entire declared arena (including unused tails),
the complete Source array, and every source path/byte slice. R1 validates these
extents and rejects overlap with any mutable before invoking the driver. The
assembler cannot make that check on the adapter's behalf because it receives
only assembly text. Graph Source counts are checked before multiplication and
Source records must be aligned. Even a driver failure must leave Graph/source
storage unchanged. The permanent native probe covers eleven backing/source
aliases, a valid unsupported-source control, a valid ELF control, and a compiled
regression mutant that removes only these backing/source checks.

Labels/table pointer alignment is checked even when their length is zero,
matching native_assembler.valid. A late INVALID from the assembler after the
driver has modified storage/text would otherwise break the adapter's INVALID
atomicity contract. Two native empty-slice alignment regressions check early
rejection with unchanged storage/text/Result.

## Host probing

Independent tests build a live Graph with production `frontend.check`, call
`compile_image`, then validate the image with the kernel `exec.elf.validate`
planner. On supported hosts the probe maps the static ELF at its planned base and
invokes the entry as a SysV function; it never treats that entry as an OS process
`_start` or launches the image with `CreateProcess`/`exec`.

## Limits

A passing image does not prove the guest can host the compiler, enlarge memory or
stack, or complete L3 self-host. Independent acceptance and integration remain with
Codex.
