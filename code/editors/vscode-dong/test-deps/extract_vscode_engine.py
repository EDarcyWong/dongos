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
                output = HERE / 'node_modules' / module / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
                path = output.relative_to(HERE).as_posix()
                extracted[path] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    lock = {
        'source': 'Read-only extraction from an existing Microsoft VS Code installation; no npm install.',
        'source_app': str(app), 'vscode_version': vscode['version'],
        'source_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
        'packages': PINNED,
        'repositories': {
            'vscode-textmate': 'https://github.com/microsoft/vscode-textmate',
            'vscode-oniguruma': 'https://github.com/microsoft/vscode-oniguruma',
        },
        'files': extracted,
    }
    (HERE / 'engine-lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
    return lock


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True, help='Existing VS Code resources/app directory')
    args = parser.parse_args()
    print(json.dumps(extract(args.app), indent=2))
