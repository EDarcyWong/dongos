# Offline real TextMate test runtime

`node_modules/` contains an explicit runtime-only allowlist copied read-only
from the local Microsoft VS Code 1.142.0 bundle. It includes the actual
`vscode-textmate` 9.3.2 JavaScript, `vscode-oniguruma` 1.7.0 JavaScript and
Oniguruma WASM, with their MIT licenses and notices. No npm installation or
package lifecycle scripts were run. `engine-lock.json` pins every copied file's
size/SHA-256 and records source archive SHA-256, original location and upstream
repositories. Original installation paths are provenance only; tests never
read them. The engine runner verifies the local pins before loading either
module or WASM.

The package's Python test invokes `node test-deps/run_textmate.cjs` using a JSON
request over stdin. `Registry.loadGrammar` and `grammar.tokenizeLine` execute
the actual TextMate rules on the actual Oniguruma WASM engine; ruleStack is
carried between lines. The returned scopes use UTF-16 offsets, which the
independent Python lexer oracle converts back to Unicode code points.

Tests are fully offline once these files are present. Requirements: Node.js
18 or newer and Python 3.12 or newer. From the language-package directory:

```powershell
python ../../tests/test_vscode_dong.py
```

For a source checkout without these vendored test dependencies, extract the
same pinned versions from an existing VS Code installation using:

```powershell
python test-deps/extract_vscode_engine.py --app "<VS Code>/resources/app"
```

Extraction rejects mismatched versions. It writes only this test dependency
directory and does not launch VS Code, install extensions or touch user
settings. The modules, runner and lock are test-only and excluded from VSIX.
