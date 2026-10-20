# bootstrap.frontend_diagnostics: native single-line diagnostics

Connects frontend stage failures to the existing C6 source-position locator and C5 formatter. No I/O, allocation, host formatting, source execution, or locale-dependent conversion.

```text
unsafe render(sources:[]const modules.Source, result:*const frontend.Result,
              output:[]u8, written:*usize)u64
export dong_frontend_diagnostic(sources:*const modules.Source,count:usize,
              result:*const frontend.Result,output:*u8,capacity:usize,written:*usize)u64
```

Returns OK0, INVALID1, CAPACITY2. INVALID/CAPACITY preserve the entire output and written; success modifies only the exact output prefix and written. Input/source/result bytes remain unchanged. Full span/alignment/alias checks include the entire source catalog and every path/source byte range, not just the selected diagnostic source. A success Result is not a diagnostic and returns INVALID.

Output is C5's native single-line mode:

```text
path:line:column: E####: message\n
```

This deliberately documents the accepted formatter's existing shape. It does not yet provide the specified full CLI `error[E####]`, source excerpt, caret or related-declaration note. Do not claim full diagnostic-format parity with the Python CLI.

Code mapping follows the specification's categories: lexical E0001, syntax E0101, names E0201, modules E0202, types E0301, constants/layout E0302, uninitialized E0401, mutability/return E0402, match E0403, unsafe/control E0501, unsupported/depth/capacity E0601. Internal contract failures use E0901. Raw stage status/detail remain in frontend.Result for tooling. Public pure functions `error_code(stage,code,detail)` and `message(stage,code,detail)` use static borrowed text.

BOM handling exactly matches modules.load: remove only the first three UTF-8 BOM bytes, then use the recorded relative offset. Unicode columns count scalars, not bytes or display width. For a lexical BAD_UTF8 result, only the known-valid prefix before the first bad scalar is passed to C6, so its strict whole-input validation does not hide the original diagnostic. Invalid offsets or non-boundaries reject formatting rather than inventing coordinates.

Source paths preserve valid UTF-8 bytes. Empty paths, malformed UTF-8 paths or ASCII control bytes (C0/DEL, including ESC/NUL/CR/LF) use the deterministic display label `<input>` to avoid forged diagnostic lines or terminal escapes; the original catalog index remains in the Result. A source-less internal result uses that label at 1:1. Workspace and import-depth failures (module DEPTH with detail=0) may precede lexing that source and use the conventional location 1:1 without decoding it. Syntax-depth failures retain their actual parser token position.

Integrated validation lives in `lang/tests/test_bootstrap_frontend.py`, including cross-module routing, Unicode/BOM/CRLF, malformed UTF-8, output capacity, read-only inputs and exact failure atomicity.

