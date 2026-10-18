"""Independent raw ABI checks for the explicit CPL3 SMP hardware gate.

No expected state is written into the guest. The live runner supplies actual
hardware register dumps and read-only arena/PTE/application observations.
"""
import re,struct
NONE=(1<<64)-1
MAGIC=0x55534552534d5036
def check(ok,why):
 if not ok:raise ValueError(why)
def words(raw,count):
 check(len(raw)==count*8,'incomplete raw ABI record');return list(struct.unpack('<'+'Q'*count,raw))
def registers(text):
 result={name:int(value,16)for name,value in re.findall(r'\b(CR[034]|RIP|RSP)=([0-9a-fA-F]+)\b',text)}
 for name in ('CS','SS','GS'):
  matches=re.findall(r'\b'+name+r'\s*=([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
  check(len(matches)==1,'missing or duplicate hardware segment '+name)
  result[name]=int(matches[0][0],16);result[name+'_base']=int(matches[0][1],16)
 check(all(name in result for name in ('CR0','CR3','CR4','RIP','RSP')),'missing actual CPU control/general register')
 for name in ('GDT','IDT'):
  match=re.search(r'\b'+name+r'=\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
  check(match,'missing actual hardware '+name);result[name]=int(match[1],16);result[name+'_limit']=int(match[2],16)
 match=re.search(r'\bTR\s*=([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',text)
 check(match,'missing actual hardware TR');result['TR']=int(match[1],16);result['TR_base']=int(match[2],16)
 return result
def header(cpu,h,m,report,context,entry):
 check(len(h)==32 and len(m)==24,'private Header/Metrics ABI differs')
 check(h[2]==entry['address'] and h[7]==MAGIC and h[8]==report[7]+cpu*256
       and h[9]==report[5] and h[10]==cpu and h[11]==report[7] and h[12]==report[3]
       and h[4]==report[8] and h[25]==2 and h[26]==0,'private Header identity/readiness/root differs')
 check(context[0]==h[8] and context[1]==cpu and context[3]==4,'legacy Context pointer/CPU/online differs')
 check(h[14]==entry['address']+256 and h[15]==entry['address']+320 and h[16]==entry['address']+512
       and h[21]==entry['address']+4608 and h[0]-h[17]==16384,'private table/xstate/kernel-stack layout differs')
 check(m[5]==0 and m[6]==entry['address'] and m[7]==m[8]==0 and m[9]&1
       and m[10]==0x0020000800000000 and m[11]==entry['syscall_entry']
       and m[12]==entry['fmask'],'actual MSR readback differs')
 check((m[13],m[14],m[15],m[16],m[17],m[20])==(h[14],55,h[16],4095,24,h[0]),
       'actual GDTR/IDTR/TR/TSS-RSP0 readback differs')
 check(h[13]in(0,1) and bool(m[18]&(1<<17))==bool(h[13]) and not m[18]&((1<<7)|(1<<16)),
       'actual CR4 PCIDE/PGE/FSGSBASE policy differs')
 check(not any(m[21:]) and h[29]>0 and h[30]>0 and h[31]>0,'reserved metrics/rate invalid')
 if not h[13]:check(m[1]==0,'fallback reported a retained PCID switch')
def cpu_ownership(cpu,c,p,t,h,reg):
 check(c[0]in range(1,7) and c[6]in(0,1) and c[8]<=c[7],'CPU ownership/publication ABI invalid')
 check((reg['GDT'],reg['GDT_limit'],reg['IDT'],reg['IDT_limit'],reg['TR'],reg['TR_base'])==(h[14],55,h[16],4095,24,h[15]),
       'current hardware descriptor tables differ from private CPU ownership')
 if c[1]:
  check(c[3]<16 and p[c[3]][0]==c[1] and p[c[3]][1]==c[2], 'CPU token/incarnation not owned by live process')
  check(t[c[3]][0]==2 and t[c[3]][3]==cpu,'actual queue RUNNING ownership differs')
 else:check(c[3]==16,'detached CPU retains an owned slot')
 if reg['CS']&3==3:
  check(c[0]==2 and c[1]!=0,'actual CPL3 has no authoritative USER owner')
  process=p[c[3]]
  check(reg['CS']==0x33 and reg['SS']==0x2b and reg['GS_base']==0,
        'actual CPL3 selectors/user GS invalid')
  check(reg['CR3']&~4095==process[2] and reg['CR3']&4095==(c[3]+1 if h[13]else 0),
        'actual CPL3 CR3/root/tag binding differs')
  check(bool(reg['CR4']&(1<<17))==bool(h[13])and not reg['CR4']&(1<<7),'running CR4 disagrees with PCID gate')
  return True
 check(reg['CS']==8 and reg['GS_base']==h[2] and reg['CR3']&~4095==h[4],
       'actual kernel CPU is outside trusted private GS/kernel root')
 return False
def worker(v,argument,pid,cfg,incarnation,apics):
 check(len(v)==24 and v[0]==1 and(v[1],v[2],v[5],v[19],v[20],v[21])==(argument,pid,0,argument,cfg,incarnation),
       'actual busy app identity/fixed-VA/error differs')
 check(v[3]>=4096 and v[7]in(0,1)and v[17]>=v[16]>0,'actual busy loop did not progress')
 check(33<=v[22]<=4096 and v[23]==0x534d5046494c4553,'actual file IPC blocked/read/resumed proof absent')
 check(0<=v[6]<=255 and len(apics)==len(set(apics))and all(0<=apic<=255 for apic in apics),
       'actual APIC identifier exceeds the bounded 256-bit hardware bitmap')
 mask=sum(v[8+i]<<(64*i)for i in range(4));allowed=sum(1<<apic for apic in apics)
 check(mask!=0 and mask&~allowed==0 and mask&(1<<v[6]),'CPU-loaded APIC bitmap is not actual admitted hardware')
 return [cpu for cpu,apic in enumerate(apics)if mask&(1<<apic)]
def xstate(raw,argument,pid,avx):
 check(len(raw)==1024,'incomplete actual private XSAVE buffer')
 a=0x1122334455667788^argument;b=0x8877665544332211^pid;c=0xcafebabedeadbeef^argument^pid
 check(struct.unpack_from('<Q',raw,160)[0]==a and struct.unpack_from('<Q',raw,400)[0]==b,
       'actual saved XMM0/XMM15 corrupted')
 if avx:check(struct.unpack_from('<Q',raw,816)[0]==c,'actual saved upper YMM15 corrupted')
def warm_reuse(first,second,old_word):
 check(first['slot']==second['slot']and second['incarnation']>first['incarnation']
       and first['token']!=second['token']and first['physical']!=second['physical']
       and first['argument']!=second['argument']and old_word==first['argument'],
       'warm slot reuse failed generation/physical/fixed-VA isolation')
def negative(marker,states,timers,essential):
 check(marker and any(s['state']==4 and s['status']==6 for s in states)
       and sum(timers[1:])>0 and all(s['state']==2 for s in essential),
       'negative must be a busy-app SIMD assertion and actual CPL3 #UD after AP preemption')
def idle_lapic(text):
 pairs=re.findall(r'\bLVTT\s+0x([0-9a-fA-F]+).*?initial_count\s*=\s*([0-9]+).*?current_count\s*=\s*([0-9]+)',text,re.S)
 if not pairs:
  lvt=re.search(r'LVTT\s+0x([0-9a-fA-F]+)',text);initial=re.search(r'initial_count\s*[:=]\s*([0-9]+)',text);current=re.search(r'current_count\s*[:=]\s*([0-9]+)',text)
  check(lvt and initial and current,'actual per-CPU LAPIC dump incomplete');pairs=[(lvt[1],initial[1],current[1])]
 value,initial,current=pairs[0];value=int(value,16)
 check(value&0x10000 and not value&0x60000 and int(initial)==int(current)==0,
       'idle CPU local timer is armed/periodic/deadline or nonzero')
 return dict(lvtt=value,initial_count=int(initial),current_count=int(current))
