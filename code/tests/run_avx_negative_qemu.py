#!/usr/bin/env python3
"""Actually omit YMM_Hi128 save while enabling AVX, and require CPL3 failure."""
from pathlib import Path
import argparse,hashlib,re,subprocess,sys,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tools.make_fat32_disk import create
from tests.run_services_qemu import write_json
ROOT=builder.ROOT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-esp',type=Path);a=p.parse_args()
    state=ROOT/'build/test/p7-desktop/drop-ymm'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    result=dict(passed=False,build_succeeded=False,actual_qemu_executed=False)
    paths=[ROOT/x for x in ('kernel/sched/context.asm','services/lib/syscalls.asm','services/drivers/input_service.dg','services/desktop/service.dg')]
    hashes=lambda:{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before=hashes()
    try:
        esp=a.reuse_esp.resolve() if a.reuse_esp else builder.build(test=True,runtime_level=7,graphics_case='drop-ymm',output=state/'build')
        result['build_succeeded']=True
        metadata=__import__('json').loads((esp.parent/'build-inputs.json').read_text())
        if metadata['graphics_case']!='drop-ymm' or not metadata['test'] or not metadata['source_unchanged']:
            raise ValueError('negative build identity/integrity differs')
        disk=state/'disk.img';create(disk,64)
        command=builder.qemu_command(esp,state/'guest',test=True)+['-cpu','max,+smep,+smap,+umip',
            '-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk.resolve().as_posix()}',
            '-device','virtio-blk-pci,drive=data,disable-legacy=on']
        result.update(actual_qemu_executed=True,command=command)
        actual=subprocess.run(command,capture_output=True,timeout=45)
        (state/'stderr.log').write_bytes(actual.stderr)
        serial=(state/'guest/serial.log').read_bytes()
        fields={n.decode():int(v,16) for n,v in re.findall(rb'^services_([a-z_]+)=0x([0-9a-f]{16})\r?$',serial,re.MULTILINE)}
        expected=dict(process_count=5,errors=1,last_error=0x07320001,last_pid=4,last_syscall=254,completed=0)
        if actual.returncode!=35 or any(fields.get(n)!=v for n,v in expected.items()):
            raise ValueError('actual missing YMM save did not fail through the compositor')
        if serial.count(b'DONGOS_P7_AVX_FAILED')!=1 or b'DONGOS_INPUT_PS2_READY' not in serial:
            raise ValueError('real independent input clobber and vector comparison not reached')
        if any(s in serial for s in (b'DONGOS_P7_AVX_CONTEXT_READY',b'DONGOS_P7_DESKTOP_READY',b'DONGOS_P1_PASS')):
            raise ValueError('bad vector context falsely reached success')
        if hashes()!=before:raise ValueError('negative guest modified original sources')
        result.update(passed=True,returncode=actual.returncode,actual_fields=fields,source_unchanged=True,
            fault='XCR0=7 with actual XSAVE/XRSTOR mask=3; another CPL3 process destroys YMM15 before yield.')
    except Exception as exc:result['error']=f'{type(exc).__name__}: {exc}'
    write_json(state/'result.json',result)
    print('P7 actual missing YMM','PASS' if result['passed'] else 'FAIL',state,result.get('error',''))
    return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
