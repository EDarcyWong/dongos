"""Build actual independent Dong userspace PIE executables."""
from pathlib import Path
import argparse
import json
from tools.build import ROOT, assemble, execute, find_tool
from lang.dongc import compile_file


def build_service(source: Path, output: Path, *, mode='release') -> Path:
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    result = compile_file(Path(source), roots=[ROOT/'services',ROOT/'lang/std'],mode=mode)
    generated = output/'program.asm'
    generated.write_text(result.assembly,encoding='utf-8')
    obj = assemble(generated,output,fmt='elf64',test=False,stage='p1')
    bridge = assemble(ROOT/'services/lib/syscalls.asm',output,fmt='elf64',test=False,stage='p1')
    graphics = assemble(ROOT/'services/gfx/accelerated.asm',output,fmt='elf64',test=False,stage='p1')
    transform = assemble(ROOT/'services/gfx/transform.asm',output,fmt='elf64',test=False,stage='p1')
    elf = output/'program.elf'
    execute([find_tool('ld.lld','LD_LLD'),'-pie','--no-dynamic-linker',
        '-z','norelro','--build-id=none','-T',str(ROOT/'services/lib/service.ld'),
        '-o',str(elf),str(obj),str(bridge),str(graphics),str(transform)])
    (output/'build.json').write_text(json.dumps(dict(source=str(source),mode=mode,elf=str(elf),
        byte_length=elf.stat().st_size),indent=2)+'\n')
    return elf


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(build_service(args.source,args.output))


if __name__=='__main__':
    main()
