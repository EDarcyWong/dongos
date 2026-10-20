"""Copy only the pinned TextMate/Oniguruma runtime from a local VS Code bundle.

Reads the ASAR header with Python's stdlib; does not execute VS Code, install
extensions, modify the source installation, or access the network.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct


HERE = Path(__file__).resolve().parent
PINNED = {'vscode-textmate': '9.3.2', 'vscode-oniguruma': '1.7.0'}
ALLOWLIST = {
    'vscode-textmate': ('LICENSE.md', 'package.json', 'release/main.js'),
    'vscode-oniguruma': ('LICENSE.txt', 'NOTICES.txt', 'SECURITY.md', 'package.json', 'release/main.js', 'release/onig.wasm'),
}


def extract(app):
    app = Path(app).resolve()
    archive = app / 'node_modules.asar'
    vscode = json.loads((app / 'package.json').read_text(encoding='utf-8'))
    lock = json.loads((HERE / 'engine-lock.json').read_text(encoding='utf-8'))
    if vscode['version'] != lock['vscode_version']:
        raise ValueError('VS Code version does not match engine-lock.json')
    extracted = {}
    with archive.open('rb') as stream:
        first, header_size, _, json_size = struct.unpack('<4I', stream.read(16))
        if first != 4 or json_size > 16 * 1024 * 1024:
            raise ValueError('unsupported ASAR header')
        tree = json.loads(stream.read(json_size))
        data_offset = 8 + header_size

        def contents(module, relative):
            entry = tree['files'][module]
            for name in relative.split('/'):
                entry = entry['files'][name]
            if entry.get('unpacked'):
                data = (app / 'node_modules.asar.unpacked' / module / relative).read_bytes()
            else:
                stream.seek(data_offset + int(entry['offset']))
                data = stream.read(entry['size'])
            if len(data) != entry['size']:
                raise ValueError('truncated ASAR entry')
            return data

        for module, version in PINNED.items():
            metadata = json.loads(contents(module, 'package.json'))
            if metadata['name'] != module or metadata['version'] != version:
                raise ValueError(f'{module}: expected pinned {version}, found {metadata.get("version")}')
            for relative in ALLOWLIST[module]:
                data = contents(module, relative)
                path = f'vendor/{module}/{relative}'
                actual = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                if lock['files'].get(path) != actual:
                    raise ValueError(f'dependency hash mismatch: {path}')
                extracted[path] = data
    if set(extracted) != set(lock['files']):
        raise ValueError('dependency allowlist does not match engine-lock.json')
    # Validate every input before writing anything; never regenerate trusted pins.
    for relative, data in extracted.items():
        output = HERE / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
    return lock


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True, help='Existing VS Code resources/app directory')
    args = parser.parse_args()
    print(json.dumps(extract(args.app), indent=2))
