"""Diagnostic userspace derivative; formal acceptance requires a fresh build."""
from pathlib import Path
import argparse,hashlib,json,shutil
from tools.build import ROOT
from tools.user_services import build_service
from tools.service_bundle import pack,ELF,DATA

def refresh(base:Path,out:Path)->Path:
    base=base.resolve();out=out.resolve()
    if out.exists() or not base.is_dir() or base==out or base in out.parents:raise ValueError('fresh independent output directory required')
    for name in ('kernel.elf','kernel.bin','esp/SERVICES.BIN','services/compositor/program.elf','services/input/program.elf'):
        if not (base/name).is_file():raise ValueError('complete desktop base build required')
    shutil.copytree(base,out)
    before=hashlib.sha256((base/'kernel.bin').read_bytes()).hexdigest()
    for name,path in (('compositor','services/desktop/service.dg'),('input','services/drivers/input_service.dg')):
        build_service(ROOT/path,out/'services'/name)
    items=[(name,ELF,(out/'services'/name/'program.elf').read_bytes()) for name in ('shell','fs','block','compositor','input')]
    items.append(('font16',DATA,(ROOT/'assets/fonts/dong-cjk-sc-16.dgfont').read_bytes()))
    (out/'esp/SERVICES.BIN').write_bytes(pack(items))
    inherited=out/'build-inputs.json'
    if inherited.exists():
        # The inherited manifest names the original bundle and build inputs.
        # Preserve it as provenance, but never pass it off as this derivative.
        raw=inherited.read_text();(out/'base-build-inputs.json').write_text(raw)
        metadata=json.loads(raw);metadata.update(derived=True,source_unchanged=False,
            explanation='Kernel retained; userspace rebuilt for diagnosis. Run a complete build for formal acceptance.')
        metadata['artifacts']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (out/'kernel.bin',out/'kernel.elf',out/'esp/DONGOS.IMG',out/'esp/EFI/BOOT/BOOTX64.EFI',out/'esp/SERVICES.BIN')}
        inherited.write_text(json.dumps(metadata,indent=2)+'\n')
    (out/'refresh.json').write_text(json.dumps(dict(base=str(base),kernel_sha256=before,
        kernel_unchanged=before==hashlib.sha256((out/'kernel.bin').read_bytes()).hexdigest(),
        userspace_sources={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'services').rglob('*')) if p.suffix in ('.dg','.asm','.ld')}),indent=2)+'\n')
    return out/'esp'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);p.add_argument('output',type=Path);a=p.parse_args();print(refresh(a.base,a.output))
if __name__=='__main__':main()
