"""Build a desktop and package a new, ordinary GPT/ESP disk image."""
from pathlib import Path
import argparse
import hashlib
import json
import uuid
from tools.build import ROOT, build
from tools.make_usb_image import create, _reject_special, _no_links


def verify_build(esp: Path) -> dict:
    metadata = json.loads((esp.parent / 'build-inputs.json').read_text(encoding='utf-8'))
    if (metadata['runtime_level'] != 7 or metadata['test'] or metadata['graphics_case'] is not None
            or not metadata['source_unchanged']):
        raise ValueError('a completed normal runtime7 build is required')
    for name, expected in metadata['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('source changed since the completed build: ' + name)
    for name, expected in metadata['artifacts'].items():
        path = Path(name) if Path(name).is_absolute() else esp.parent / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('completed build artifact changed: ' + str(path))
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--esp', type=Path, help='reuse a completed normal desktop ESP')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/usb/dongos.img')
    parser.add_argument('--size-mib', type=int, choices=(64, 128, 256, 512), default=128)
    args = parser.parse_args()
    output = _reject_special(args.output)
    if output.suffix.lower() != '.img':
        raise ValueError('output must be a new ordinary .img file')
    ancestor = output.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    _no_links(ancestor, directory=True)
    if output.exists() or output.is_symlink() or output.with_name(output.name + '.json').exists():
        raise FileExistsError('output already exists; choose a new --output filename')
    output.parent.mkdir(parents=True, exist_ok=True)
    esp = args.esp.resolve() if args.esp else build(runtime_level=7,
        output=ROOT / 'build/usb' / ('source-' + uuid.uuid4().hex[:12]))
    verify_build(esp)
    result = create(esp, output, args.size_mib)
    verify_build(esp)
    print('Boot image:', result['image'])
    print('Manifest:', str(output) + '.json')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit('ERROR: ' + str(error))
