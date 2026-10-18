# Dong language support

This private language package associates `.dg` files with Dong and supplies
syntax highlighting, comment toggles, brackets and quote pairing. It contains
no executable VS Code extension, formatter, language server or dependencies.

The grammar follows the current `lang/dongc/frontend.py`,
`lang/dongc/model.py` and `lang/spec.md` lexer contract. Block comments stop
at the **first** `*/`; `/*` inside a comment does not create another level.
Strings accept `\n`, `\r`, `\t`, `\0`, `\\`, `\"` and exactly two
hexadecimal digits after `\x`. Decimal, lowercase `0x` hexadecimal and
lowercase `0b` binary integers allow underscores only between digits.
Malformed numbers and escapes receive `invalid.illegal` scopes.

Unicode XID start/continue ranges and numeric continuation ranges are static
literal ranges generated with the same Python Unicode tables as the compiler.
The grammar records the Unicode version and source hashes. These are not
ASCII `\b` approximations and do not normalize identifier spelling.
After changing the compiler contract, open this package directory and
regenerate with `python generate_grammar.py`.

Build offline using Python 3.12 or newer:

```powershell
python package.py --output dist/dong-language-0.1.0.vsix
```

The script uses an explicit four-file allowlist, sorted ZIP entries, fixed
timestamps, fixed permissions and stored bytes. The same input files produce
the same VSIX bytes, without npm, `vsce`, downloads or plugin installation.
The resulting file can be installed manually through VS Code's **Extensions:
Install from VSIX** command when desired; building never installs it.

From this package directory, validation runs with
`python ../../tests/test_vscode_dong.py`; after promotion it can also run as
`python -m unittest tests.test_vscode_dong -v` from the repository root.
It runs the actual pinned VS Code TextMate and Oniguruma WASM engines from
`test-deps/`, compares real Dong samples and Unicode boundaries against the
independent production lexer, checks multiline state, escape captures,
UTF-16 offsets and string/comment masking, rejects three deliberately broken
grammars through the actual engine, and inspects two byte-identical VSIX files.
A separate Python regex subset consumer provides additional independent
coverage. No VS Code UI is launched. The test-only runtime is fully offline;
see `test-deps/README.md` for versions, provenance, hashes and extraction.
Highlighting does not replace compiler diagnostics, semantic checking or a
language server. An unterminated block comment remains comment-colored to
EOF, as in a normal TextMate grammar.
