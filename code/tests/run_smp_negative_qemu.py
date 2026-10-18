#!/usr/bin/env python3
"""Execute a missing-INVLPG guest and inspect the retained failed TLB domain."""
from pathlib import Path
import argparse,hashlib,re,struct,subprocess,sys,time,uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import build as builder
from tests import run_acpi_qemu as acpi
from tests import run_runtime_qemu as runtime
from tests import run_services_qemu as services
ROOT=builder.ROOT

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reuse-esp',type=Path);args=parser.parse_args()
    state=ROOT/'build/test/p6-smp/no-invalidate'/('run-'+uuid.uuid4().hex[:12]);state.mkdir(parents=True)
    result=dict(passed=False,actual_qemu_executed=False,build_succeeded=False)
    source=ROOT/'kernel/smp/bootstrap.asm';before=hashlib.sha256(source.read_bytes()).hexdigest()
    process=None;qmp=None
    try:
        esp=args.reuse_esp.resolve() if args.reuse_esp else builder.build(test=True,runtime_level=6,smp_case='no-invalidate',output=state/'build')
        result['build_succeeded']=True
        guest=state/'guest';port=services.free_port()
        command=builder.qemu_command(esp,guest,test=True)
        i=command.index('isa-debug-exit,iobase=0xf4,iosize=0x04');del command[i-1:i+1]
        command+=['-cpu','max,+smep,+smap,+umip','-S','-qmp',f'tcp:127.0.0.1:{port},server=on,wait=off']
        result['command']=command
        with (state/'stderr.log').open('wb') as stderr:
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=stderr)
            result['actual_qemu_executed']=True;qmp=acpi.QMP(port,process);qmp.request('cont')
            started=time.monotonic();serial=b''
            while time.monotonic()-started<35:
                serial=(guest/'serial.log').read_bytes() if (guest/'serial.log').exists() else b''
                if b'DONGOS_P1_KERNEL_FAIL' in serial or b'DONGOS_P1_FAIL' in serial or b'smp_error_code=0x0000000006030006' in serial:break
                if b'DONGOS_P6_SMP_READY' in serial or process.poll() is not None:break
                time.sleep(.02)
            qmp.request('stop');time.sleep(.02)
            serial=(guest/'serial.log').read_bytes()
            fields={k.decode():int(v,16) for k,v in re.findall(rb'^smp_([a-z_]+)=0x([0-9a-f]{16})\r?$',serial,re.MULTILINE)}
            if fields.get('error_code')!=0x06030006 or fields.get('steps')!=7 or fields.get('reclaimed')!=0:
                raise ValueError('actual missing INVLPG did not fail before retirement')
            if b'DONGOS_P6_SMP_READY' in serial or b'DONGOS_P5_SERVICES_START' in serial or b'DONGOS_P1_PASS' in serial:
                raise ValueError('bad guest reached success or continued into user services')
            symbols=acpi.validation_symbols(esp.parent/'kernel.elf')
            memory={k.decode():int(v,16) for k,v in re.findall(rb'^memory_([a-z_]+)=0x([0-9a-f]{16})\r?$',serial,re.MULTILINE)}
            reads=[]
            def physical(pa,n,role):
                path=state/f'physical-{len(reads):02d}.bin'
                qmp.request('pmemsave',dict(val=pa,size=n,filename=str(path.resolve())))
                raw=path.read_bytes()
                if len(raw)!=n:raise ValueError('incomplete failed-domain dump')
                reads.append(dict(physical=pa,length=n,file=path.name,role=role))
                return raw
            boot=struct.unpack('<20Q',physical(memory['runtime_boot_info']-acpi.HHDM,160,'BootInfo'))
            def kernel(va,n,role):return physical(boot[15]+va-services.KERNEL,n,role)
            domain=struct.unpack('<14Q',kernel(fields['domain_pointer'],112,'retained pending domain'))
            if domain[0:2]!=(1,1) or domain[13]!=1 or domain[12]!=1 or domain[6]!=domain[7]+1:
                raise ValueError('failed TLB domain not retained pending')
            boxes=kernel(fields['mailbox_pointer'],1024,'actual skipped invalidations and stale probes')
            actual=[]
            for i in (1,2,3):
                box=struct.unpack_from('<8Q',boxes,i*64)
                if box[0]!=domain[6] or box[3]!=domain[6] or box[2]!=2 or box[4]!=fields['marker_b'] or box[5]!=fields['marker_a'] or box[6]!=0 or box[7]!=domain[10] or box[7]<2:
                    raise ValueError('missing actual skipped-INVLPG hit or warmed stale translation')
                actual.append(list(box))
            registers=qmp.request('human-monitor-command',{'command-line':'info registers -a'})
            (state/'registers.txt').write_text(registers)
            if 'HLT=1' not in registers or 'CPL=0' not in registers:raise ValueError('failure did not retain hardware in kernel')
            result.update(passed=True,actual_fields=fields,domain=list(domain),mailboxes=actual,physical_reads=reads,
                actual_mutation_hits=sum(b[7] for b in actual),stale_translations_verified=3,reclaimed_tables=0,source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==before)
    except Exception as exc:result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        if qmp:
            try:qmp.request('quit')
            except Exception:pass
            qmp.close()
        if process:
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        services.write_json(state/'result.json',result)
    print('P6 actual missing INVLPG','PASS' if result['passed'] else 'FAIL',state,result.get('error',''))
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
