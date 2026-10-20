# Offline real TextMate test runtime

`vendor/` is a tracked runtime-only allowlist containing the actual
`vscode-textmate` 9.3.2 JavaScript, `vscode-oniguruma` 1.7.0 JavaScript and
Oniguruma WASM, with their MIT licenses and notices. No npm installation or
package lifecycle scripts are required or were run. A clean Git checkout
includes all nine runtime files; no ignored `node_modules/` directory is needed.
`engine-lock.json` pins every file's size/SHA-256. The engine runner verifies
all pins before loading either module or WASM.

The package's Python test invokes `node test-deps/run_textmate.cjs` using a JSON
request over stdin. `Registry.loadGrammar` and `grammar.tokenizeLine` execute
the actual TextMate rules on the actual Oniguruma WASM engine; ruleStack is
carried between lines. The returned scopes use UTF-16 offsets, which the
independent Python lexer oracle converts back to Unicode code points.

Tests are fully offline. Requirements: Node.js 18 or newer and Python 3.12 or
newer. From the source `code/` directory:

```sh
python -m unittest tests.test_vscode_dong -v
python editors/vscode-dong/test-deps/test_extract_vscode_engine.py
```

## Provenance and exact recovery

The lock retains the original Microsoft VS Code 1.142.0 Windows installation
and original ASAR SHA-256 as historical provenance only. Tests never read that
installation. All nine original byte counts and SHA-256 values are unchanged;
only the tracked directory changed from `node_modules/` to `vendor/`.

Eight files were recovered byte-for-byte from the official VS Code 1.142.0 Linux
bundle, build `6d62b1d5dace93a33b3a6d3eca1317bd5e15bcb1`:

- https://update.code.visualstudio.com/1.142.0/linux-x64/stable
- Resolved archive: https://vscode.download.prss.microsoft.com/dbazure/download/stable/6d62b1d5dace93a33b3a6d3eca1317bd5e15bcb1/code-stable-x64-1792034917.tar.gz
- Its `resources/app/node_modules.asar` SHA-256 is
  `8e0d35ea43fc40272ad47c023f03891e11950a153b9608c6065e830728f5effd`.

The unpacked `vscode-oniguruma/release/onig.wasm` was recovered byte-for-byte
from the official npm package:

- https://registry.npmjs.org/vscode-oniguruma/-/vscode-oniguruma-1.7.0.tgz
- Tarball SHA-256: `830c8de8fd475455d8c161ca3c1f5f3c935fad8327ee548dec38c8985097657f`.
- WASM SHA-256: `fd885c2d12e5951e59d761ebd4a006e06254b1491fd6f530c92b69fb4d8d77d9`.

The npm TextMate 9.3.2 `release/main.js` is NOT interchangeable with the
VS Code bundle's patched file: npm has 61242 bytes and SHA-256
`9da91ca33178e8d68ac5b9ea5733258275fe2f1924db02930ef9cf7e0d850e0f`,
whereas the required bundled file has 61358 bytes and SHA-256
`b19a1d0b8ec9340100a0f793fbdf8d84749a8e36a44136323edfe31b7e515f1e`.
Do not replace it with npm's same-version file or regenerate the lock to pass.

## Restoring from an existing installation

If a tracked runtime file is missing, restore it from Git. Alternatively:

```sh
python editors/vscode-dong/test-deps/extract_vscode_engine.py --app "<VS Code>/resources/app"
```

Extraction rejects mismatched VS Code/package versions and file hashes before
writing any output. It writes only the vendored test dependencies and never
rewrites the lock, launches VS Code, installs extensions or touches settings.
The modules, runner and lock are test-only and excluded from VSIX.
