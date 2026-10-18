/* Execute the real bundled vscode-textmate + vscode-oniguruma/WASM engine.
 * JSON request on stdin, JSON token/scopes response on stdout. No network/UI.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const base = __dirname;

async function main() {
  const lock = JSON.parse(fs.readFileSync(path.join(base, 'engine-lock.json'), 'utf8'));
  for (const [relative, pinned] of Object.entries(lock.files)) {
    const file = path.resolve(base, relative);
    if (!file.startsWith(base + path.sep)) throw new Error('dependency path escaped test directory');
    const bytes = fs.readFileSync(file);
    const digest = crypto.createHash('sha256').update(bytes).digest('hex');
    if (bytes.length !== pinned.bytes || digest !== pinned.sha256) throw new Error('dependency hash mismatch: ' + relative);
  }
  for (const [name, version] of Object.entries(lock.packages)) {
    const installed = JSON.parse(fs.readFileSync(path.join(base, 'node_modules', name, 'package.json'), 'utf8'));
    if (installed.version !== version) throw new Error('dependency version mismatch: ' + name);
  }
  const tm = require(path.join(base, 'node_modules/vscode-textmate'));
  const onig = require(path.join(base, 'node_modules/vscode-oniguruma'));
  const wasm = fs.readFileSync(path.join(base, 'node_modules/vscode-oniguruma/release/onig.wasm'));
  await onig.loadWASM(wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength));
  const request = JSON.parse(fs.readFileSync(0, 'utf8'));
  const groups = {};
  for (const group of request.groups) {
    const registry = new tm.Registry({
      onigLib: Promise.resolve({
        createOnigScanner: patterns => new onig.OnigScanner(patterns),
        createOnigString: value => new onig.OnigString(value),
      }),
      loadGrammar: async scope => scope === group.grammar.scopeName ? group.grammar : null,
    });
    const grammar = await registry.loadGrammar(group.grammar.scopeName);
    if (!grammar) throw new Error('grammar failed to load');
    const values = [];
    for (const sample of group.samples) {
      const lines = sample.text.split('\n');
      let state = tm.INITIAL;
      let utf16Offset = 0;
      const tokens = [];
      const lineStates = [];
      for (let index = 0; index < lines.length; index++) {
        const line = lines[index];
        const previous = state;
        const result = grammar.tokenizeLine(line, state, 0);
        if (result.stoppedEarly) throw new Error('tokenization stopped early');
        state = result.ruleStack;
        lineStates.push({line: index + 1, depth: state.depth, root: state.depth === 1,
                         stateChanged: !state.equals(previous)});
        for (const token of result.tokens) {
          // vscode-textmate appends a virtual newline. Keep only real input.
          const end = Math.min(token.endIndex, line.length);
          if (token.startIndex < end) tokens.push({
            start: utf16Offset + token.startIndex, end: utf16Offset + end,
            line: index + 1, column: token.startIndex, scopes: token.scopes,
          });
        }
        utf16Offset += line.length + (index + 1 < lines.length ? 1 : 0);
      }
      values.push({id: sample.id, tokens, lineStates, finalDepth: state.depth, root: state.depth === 1});
    }
    groups[group.id] = values;
    registry.dispose();
  }
  process.stdout.write(JSON.stringify({
    engine: {textmate: lock.packages['vscode-textmate'], oniguruma: lock.packages['vscode-oniguruma'],
             wasm: true, node: process.version, dependencyHashesVerified: true},
    groups,
  }));
}
main().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
