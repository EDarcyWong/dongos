"""Repackage only DPI DATA assets from a verified, unchanged full desktop build.

No code is recompiled: every ELF and firmware/kernel byte must match the full
build and its original embedded payload. Results explicitly record this fact.
"""
from pathlib import Path
import hashlib,json,shutil
from tools.service_bundle import inspect,pack,DATA,ELF
from tools.build import ROOT

def variant(base:Path,output:Path,scale:int)->Path:
    base=base.resolve();output=output.resolve()
    if scale not in (100,125,150,175,200) or output.exists():raise ValueError('fresh variant directory and supported scale required')
    manifest=json.loads((base/'build-inputs.json').read_text())
    if manifest['runtime_level']!=7 or manifest['test'] or manifest['graphics_case'] is not None or not manifest['source_unchanged']:
        raise ValueError('normal full production desktop build required')
    for path,digest in manifest['source_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('source changed since complete compilation: '+path)
    for path,digest in manifest['artifacts'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('base artifact changed: '+path)
    raw=(base/'esp/SERVICES.BIN').read_bytes();original=inspect(raw);items=[]
    for item in original['entries']:
        data=raw[item['offset']:item['offset']+item['length']]
        if item['kind']==ELF:
            elf=base/'services'/item['name']/'program.elf'
            if elf.read_bytes()!=data:raise ValueError('service ELF differs from actual embedded original')
        if item['name']=='desktop-config':data=(scale*256//100).to_bytes(8,'little')
        items.append((item['name'],item['kind'],data))
    output.mkdir(parents=True)
    shutil.copytree(base/'esp',output/'esp')
    for name in ('kernel.bin','kernel.elf','dong_layout.json'):shutil.copyfile(base/name,output/name)
    for name in ('shell','fs','block','input','compositor'):
        target=output/'services'/name;target.mkdir(parents=True)
        shutil.copyfile(base/'services'/name/'program.elf',target/'program.elf')
    (output/'esp/SERVICES.BIN').write_bytes(pack(items))
    manifest['desktop_scale']=scale
    manifest['resource_variant']=dict(base=str(base),base_build_inputs_sha256=hashlib.sha256((base/'build-inputs.json').read_bytes()).hexdigest(),
        unchanged_code=True,changed_resources=['desktop-config'],original_bundle_sha256=original['sha256'])
    manifest['artifacts']={str(path.resolve()):hashlib.sha256(path.read_bytes()).hexdigest() for path in
        (output/'kernel.bin',output/'kernel.elf',output/'esp/DONGOS.IMG',output/'esp/EFI/BOOT/BOOTX64.EFI',output/'esp/SERVICES.BIN')}
    for path,digest in manifest['source_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('source changed during resource packaging')
    (output/'build-inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return output/'esp'
