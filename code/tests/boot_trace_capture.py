"""Read-only adapter for a root-owned, already-stopped QEMU guest.

No VM is created, started, stopped or resumed. The guest adapter provides real
qmp.request, kernel(va,n,role), verify_code(), symbols, esp and evidence. Existing
run_clock_calibration_qemu.Run implements this shape. Do not call capture during
an active build or on a running guest. The root runner owns boot/artifact binding.
"""
from pathlib import Path
import hashlib,json,struct,sys
from tests.boot_trace_oracle import decode
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.run_clock_calibration_qemu import SAMPLE_FIELDS,REFERENCE_FIELDS

def symbol(module,name):return '__dg_m'+module.encode().hex()+'_g'+name.encode().hex()
def capture(guest,out):
 status=guest.qmp.request('query-status');assert status.get('running') is False,'guest must already be stopped'
 verified=guest.verify_code();assert verified>0,'actual executable bytes must match linked ELF'
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 def global_data(module,name,n):
  va=guest.symbols[symbol(module,name)];assert guest.symbols['__kernel_bss_start']<=va<=guest.symbols['__kernel_bss_end']-n,'read escaped owned kernel BSS'
  raw=guest.kernel(va,n,module+'.'+name);assert len(raw)==n,'truncated retained kernel data';return raw
 raw=global_data('boot.trace_runtime','STORAGE',4096);assert global_data('boot.trace_runtime','ACTIVE',1)==b'\1','trace never adopted'
 assert struct.unpack('<Q',global_data('boot.trace_runtime','LAST_ERROR',8))[0]==0,'trace diagnostic error'
 stamp=struct.unpack('<3Q',global_data('boot.trace_runtime','ENTRY_SAMPLE',24));header=struct.unpack('<32Q',raw[:256]);assert stamp[0]>0 and stamp[1]==header[9] and stamp[2] in (0,1),'invalid actual entry sample'
 kernel_entry=next((struct.unpack('<6Q',raw[256+i*48:304+i*48]) for i in range(min(header[5],80)) if struct.unpack_from('<Q',raw,256+i*48+16)[0]==3),None)
 assert kernel_entry and kernel_entry[1]==stamp[0],'entry stamp differs from recorded handoff'
 proof=dict(invariant_sample_flags=stamp[2],invariant_provenance='actual boot_trace_sample CPUID80000007.EDX bit8 retained at kernel entry')
 if header[12]==1:proof['cpuid15']=list(struct.unpack('<3Q',global_data('boot.trace_runtime','RATIO_RAW',24)))
 else:
  assert global_data('irq.platform','CALIBRATION_READY',1)==b'\1' and struct.unpack('<Q',global_data('irq.platform','CALIBRATION_COUNT',8))[0]==7,'calibration not completely published'
  proof['reference']=dict(zip(REFERENCE_FIELDS,struct.unpack('<3Q',global_data('irq.platform','CALIBRATION_REFERENCE',24))))
  samples=global_data('irq.platform','CALIBRATION_SAMPLES',7*64);proof['samples']=[dict(zip(SAMPLE_FIELDS,struct.unpack('<8Q',samples[i*64:(i+1)*64]))) for i in range(7)]
 actual=guest.evidence.get('actual_qemu_executed') is True
 kvm=guest.qmp.request('query-kvm');assert all(isinstance(kvm.get(k),bool) for k in ('enabled','present')),'missing actual accelerator query'
 env=dict(host_os='linux' if sys.platform.startswith('linux') else sys.platform,actual_guest_boots=1 if actual else 0,query_kvm={k:kvm[k] for k in ('enabled','present')},artifact_bound=actual)
 result=decode(raw,proof,env);elf=Path(guest.esp).parent/'kernel.elf';metadata=dict(standalone_reader_only=True,vm_created_or_run_by_this_tool=False,actual_executable_bytes_compared=verified,kernel_elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),trace_sha256=hashlib.sha256(raw).hexdigest(),environment=env)
 (out/'trace.bin').write_bytes(raw)
 for name,value in [('clock-proof',proof),('environment',env),('decoded',result),('capture',metadata)]: (out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
 return result
