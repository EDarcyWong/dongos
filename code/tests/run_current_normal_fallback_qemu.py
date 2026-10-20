#!/usr/bin/env python3
"""New current fallback identity/planning. CLI never starts a guest."""
from pathlib import Path
import argparse,json,struct,sys
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import run_process_lifecycle_qemu as life
from tests import user_smp_oracle as oracle
from tools.build_usb import verify_build
from tools.elf_symbols import read_elf_symbols
settings,storage=life.settings,life.storage
check=oracle.check

def topology_command(command,cpus):
 check(type(cpus)is int and cpus in(1,2),'explicit one/two CPU fallback required')
 check(command.count('-smp')==1 and not any(str(v).startswith('-smp=')for v in command),'exact owned -smp required')
 i=command.index('-smp');check(i+1<len(command)and str(command[i+1]).isdigit(),'missing topology argument')
 result=list(command);result[i+1]=str(cpus);return result

def decode_smp(raw,count):
 r=oracle.words(raw,28)
 check(count in(1,2)and r[:4]==[1,count,count,count-1]and r[4:7]==[count*2097152,count*1536,count*512]and r[7]==0 and 0<r[8]<r[9]and r[11]==r[12]==r[10]*(count-1)and r[15]==2 and r[16]==3 and r[17]==r[18]and r[19]==count-1 and r[24:26]==[0x1122334455667788,0x8877665544332211]and r[20]!=0 and r[26:]==[31,0],'actual fallback SMP report differs')
 return r

def fallback_state(report,contexts,legacy,current,processes,registers,domain,enabled,count):
 decode_smp(struct.pack('<28Q',*report),count)
 check(domain==enabled==0 and len(contexts)==len(registers)==count and len(legacy)==8 and legacy[6]==1 and len(processes)==16*1288 and type(current)is int and 0<=current<16,'fallback authority invalid')
 ready,root=struct.unpack_from('<2Q',processes,current*1288);check(ready==1 and root>0 and root%4096==0,'BSP process invalid')
 check(len({c[2]for c in contexts})==count,'duplicate actual APIC ownership')
 for cpu,(c,r)in enumerate(zip(contexts,registers)):
  check(len(c)==32 and c[0]==report[20]+cpu*256 and c[1]==cpu and c[3]==4 and c[25]==1,'legacy CPU context differs')
  check((r['GDT'],r['IDT'],r['TR_base'],r['TR'])==(c[13],c[15],c[14],24),'legacy descriptor ownership differs')
  if cpu==0:check(r['CS']==0x33 and r['SS']==0x2b and r['GS_base']==0 and r['CR3']&~4095==root and r['CR3']&4095==(current+1 if r['CR4']&(1<<17)else 0),'BSP CPL3/root differs')
  else:check(r['CS']==8 and r['SS']==16 and r['GS_base']==c[0]and r['CR3']==legacy[4]and not r['CR4']&(1<<17),'AP legacy ownership differs')
 return dict(online_count=count,online_mask=(1<<count)-1,user_domain_pointer=domain)

class FallbackGuest(life.ProcessGuest):
 def __init__(self,*args,cpus=2,**kwargs):
  self._constructing,self._early_captured=True,False;original=settings.builder.qemu_command
  def command(*a,**k):return topology_command(original(*a,**k),cpus)
  try:
   with mock.patch.object(settings.builder,'qemu_command',command):super().__init__(*args,**kwargs)
  except BaseException:
   if not self._early_captured:self.close()
   raise
  finally:self._constructing=False
 def hmp(self,cpu,command):
  check(type(cpu)is int and cpu in(0,1),'invalid fallback CPU')
  return self.qmp.request('human-monitor-command',{'command-line':command,'cpu-index':cpu})
 def close(self):
  if self._constructing and not self._early_captured:
   self._early_captured=True
   try:self.capture_failure()
   except Exception as e:
    try:storage.write_json(self.state/'failure-capture-error.json',{'error':str(e)})
    except Exception:pass
  super().close()

def elf_bytes(path,address,count):
 raw=Path(path).read_bytes();check(raw[:6]==b'\x7fELF\x02\x01'and len(raw)>=64,'ELF64 little-endian required')
 start=struct.unpack_from('<Q',raw,32)[0];stride,number=struct.unpack_from('<HH',raw,54)
 check(stride>=56 and start+stride*number<=len(raw),'invalid ELF headers')
 for i in range(number):
  kind,flags,offset,virtual,_,size,_,_=struct.unpack_from('<II6Q',raw,start+i*stride)
  if kind==1 and flags&1 and virtual<=address and address+count<=virtual+size:
   at=offset+address-virtual;check(at+count<=len(raw),'ELF truncated');return raw[at:at+count]
 raise ValueError('selector not in executable file-backed ELF segment')

def identity(esp):
 record=verify_build(esp);path=esp.parent/'kernel.elf';symbols=read_elf_symbols(path);begin=symbols['service_runtime_begin'];raw=elf_bytes(path,begin,384)
 calls={begin+i+5+struct.unpack_from('<i',raw,i+1)[0]for i in range(len(raw)-4)if raw[i]==0xe8}
 check(symbols['user_smp_normal_policy']in calls and symbols['user_smp_boot_begin']in calls,'actual normal selector/boot calls absent')
 return record

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reuse-esp',type=Path,required=True);p.add_argument('--cpus',type=int,choices=(1,2),default=2);a=p.parse_args()
 print(json.dumps(dict(mode='identity-only',guest_started=False,cpu_count=a.cpus,historical_acceptance=False,source_identity=identity(a.reuse_esp))))
 return 0
if __name__=='__main__':raise SystemExit(main())
