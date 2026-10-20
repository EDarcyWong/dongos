"""Actual Dong generators; isolated dependency closure; numerical and atomicity controls."""
import hashlib,json,os,re,shutil,struct,subprocess,sys,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags as _nasm_flags
def nasm_flags(nasm):return [*_nasm_flags(nasm),'-w-reloc-rel-dword']
PREFLIGHTS=23
TASK='CR42';MODULE='nasm_slice_view_function';NT=2
SOURCE=ROOT/'lang/bootstrap'/ (MODULE+'.dg')
DOC=SOURCE.with_suffix('.md')
MAX=(1<<64)-1

def head(v,n,frame):
    s=[symbol(*v['names'][:2])+':','push rbp','mov rbp, rsp',f'sub rsp, {frame}']
    s += [f'mov qword [rbp - {8*(i+1)}], {r}' for i,r in enumerate(('rdi','rsi','rdx','rcx')[:n])]
    return s
def load(r,d):return f'mov {r}, qword [rbp - {d}]'
def store(r,d):return f'mov qword [rbp - {d}], {r}'
def end(frame,lo,hi=0):
    return ([load('rax',lo),load('rdx',hi)] if hi else [f'movzx rax, byte [rbp - {lo}]'])+[f'add rsp, {frame}','pop rbp','ret']
def text(lines):return ('\n'.join(lines)+'\n').encode()
def logger(name,id,value):
    return [name+':','mov r11, [rel log_count]','inc qword [rel log_count]','and r11, 15','lea r10, [rel log_ids]',f'mov rax, {id}','mov [r10+r11*8], rax','lea r10, [rel log_align]','mov rax, rsp','and rax, 15','mov [r10+r11*8], rax']+[f'mov {r}, {n}' for r,n in [('rdi',31),('rsi',32),('rcx',33),('rdx',34),('r8',35),('r9',36),('r10',37),('r11',38)]]+['stc',f'mov rax, {value}','ret']
def make(k,q,args):return dict(names=[b'm',('f%d'%k).encode()],q=q,args=args)
def clone(v,**updates):return dict(v,**updates)

data=[(1,0x1000,8,0,8),(2,0x1000,8,2,5),(4,0x1000,8,3,3),(8,0x1000,8,8,8),(1,0,0,0,0),(8,0,0,0,0),(1,0x1000,8,0,9),(1,0x1000,8,5,4),(1,0,1,0,1),(8,0x1000,1<<61,0,0),(2,0x1000,1<<63,0,0),(4,0x1000,1<<62,0,0),(1,MAX-3,4,0,0),(1,MAX-3,3,3,3),(8,MAX-15,2,0,0),(8,MAX-16,2,2,2),(1,1,(1<<63)+1,0,1<<63),(1,1,1<<63,0,(1<<63)+1),(4,0x1000,0,0,0),(2,0x1000,8,0,8),(4,0x1000,8,0,8),(8,0x1000,8,0,8)]
VECTORS=[make(k,[sz,MAX-1 if k==21 else 100+k],[b,n,l,h]) for k,(sz,b,n,l,h) in enumerate(data)]
VECTORS[-1]['names']=[bytes(range(64)),b'f'*64]
RBX_CASES=[0,6]
def oracle(v):
    sz,_=v['q'];b,n,l,h=v['args']
    if l>h or h>n or (b==0 and n!=0) or n*sz>MAX or b+n*sz>MAX:return (0,MAX),[]
    return (b+l*sz,h-l),[]
def targets(vs):return []
def expected_text(v):
    sz,err=v['q'];k=sz.bit_length()-1
    ls=head(v,4,48)+[load('rdi',24),load('rsi',32),load('rdx',16),'cmp rsi, rdx',f'ja __dong_b{err}','cmp rdi, rsi',f'ja __dong_b{err}',load('rax',8),'mov rcx, 0','cmp rax, rcx','setne al','movzx rax, al',store('rax',40),load('rax',16),'mov rcx, 0','cmp rax, rcx','sete al','movzx rax, al',load('rcx',40),'or rax, rcx','mov rcx, 0','cmp rcx, rax',f'jae __dong_b{err}']
    if k:ls += [load('rax',16),f'mov rcx, {1<<(64-k)}','cmp rax, rcx',f'jae __dong_b{err}']
    ls+=[load('rcx',16)]+([f'shl rcx, {k}'] if k else [])+[load('rax',8),'add rax, rcx',f'jc __dong_b{err}',load('rcx',24)]+([f'shl rcx, {k}'] if k else [])+[load('rax',8),'add rax, rcx',f'jc __dong_b{err}',store('rax',40),load('rax',32),load('rcx',24),'sub rax, rcx',store('rax',48)]+end(48,40,48)+[f'__dong_b{err}:','mov rax, 0',store('rax',40),f'mov rax, {MAX}',store('rax',48)]+end(48,40,48)
    return text(ls)
def invalid_cases():
    return [(clone(VECTORS[0],q=q),cap,1) for q in ([0,100],[3,100],[16,100],[1,MAX]) for cap in (0,8192)]
def mutations(source):
    a='if bounds.emit((*c).error_block,buffer,&n)!=0{return false;}at=n;'
    line=next(l for l in source.splitlines() if 'index==8{' in l)
    add='if addsub.emit(0,false,0,1,(*c).error_block,slice_from_raw_parts(&buffer[at],64),&n)!=0{return false;}at+=n;'
    # Delete only full-view endpoint carry. The sub-view addition remains checked.
    return [('bad-bounds',a,'at=0;',[6,7],'native value/status'),('bad-source-endpoint',line,line.replace(add,''),[12,14],'native value/status')]


def symbol(m,i):return '__dong_m'+m.hex()+'_n'+i.hex()
def closure():
    found={}
    def visit(p):
        if p.name in found:return
        found[p.name]=p
        for mod in re.findall(r'^import ([\w.]+) as ',p.read_text(encoding='utf-8'),re.M):
            visit(ROOT/'lang'/Path(*mod.split('.')).with_suffix('.dg'))
    visit(SOURCE)
    return [p for p in found.values() if p!=SOURCE]
DEPENDENCIES=closure()
WRAPPER='''module probe.exporter;
import bootstrap.nasm_slice_view_function as f;

pub struct Name{pub ptr:*const u8,pub len:usize}
export("dong_emit") pub unsafe fn emit(names:*const Name,q:*const u64,scopes:*const u64,sn:usize,ids:*const usize,inn:usize,from:usize,out:*u8,no:usize,w:*usize)u64{unsafe{
 return f.emit(slice_from_raw_parts(names[0].ptr,names[0].len),slice_from_raw_parts(names[1].ptr,names[1].len),q[0],q[1],slice_from_raw_parts(out,no),w);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
#define NT 2
typedef struct{const uint8_t*p;uint64_t n;}Name;
typedef struct{uint64_t parent,first,count;}Scope;
extern uint64_t ABI dong_emit(const Name*,const uint64_t*,const Scope*,uint64_t,const uint64_t*,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){fprintf(stderr,"panic %u/%u %.*s",k,l,(int)n,(const char*)f);exit(87);}
static void rd(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void wr(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static uint8_t*alloc_ro(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static int protect_ro(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;return VirtualProtect(p,n,PAGE_READONLY,&old)!=0;
#else
 return mprotect(p,n,PROT_READ)==0;
#endif
}
static int free_ro(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;return VirtualFree(p,0,MEM_RELEASE)!=0;
#else
 return munmap(p,n)==0;
#endif
}
static uint64_t invalid(void){
 static _Alignas(16) uint8_t a[32768],saved[32768];
 unsigned tests=0;
 for(unsigned k=0;k<23;k++){
  memset(a,0xa5,sizeof(a));Name names[6];
  for(unsigned j=0;j<6;j++){names[j].p=a+64+j*128;names[j].n=1;*(uint8_t*)names[j].p=(uint8_t)('a'+j);}
  uint64_t q[8]={1,100,0,0,0,0,0,0};Scope*s=(Scope*)(a+20480);uint64_t*ids=(uint64_t*)(a+22528);
  s[0]=(Scope){UINT64_MAX,0,0};ids[0]=10;uint64_t sn=1,inn=0,from=0,cap=8192;
  uint8_t*out=a+1024;uint64_t*w=(uint64_t*)(a+24576);
  switch(k){
   case 0:w=NULL;break;
case 1:w=(uint64_t*)(a+24577);break;
case 2:w=(uint64_t*)(uintptr_t)(UINT64_MAX-7);out=NULL;cap=0;break;
case 3:out=NULL;break;
case 4:out=(uint8_t*)(uintptr_t)(UINT64_MAX-4095);break;
case 5:w=(uint64_t*)out;break;
case 6:w=(uint64_t*)(out+8184);break;
case 7:names[0].p=NULL;break;
case 8:names[0].p=(uint8_t*)(uintptr_t)(UINT64_MAX-3);names[0].n=8;break;
case 9:names[0].n=0;break;
case 10:names[0].n=65;break;
case 11:names[0].n=64;w=(uint64_t*)(names[0].p+56);break;
case 12:names[0].n=64;out=(uint8_t*)names[0].p+63;cap=8;break;
case 13:names[0].p=out+8176;names[0].n=16;break;
case 14:names[1].p=NULL;break;
case 15:names[1].p=(uint8_t*)(uintptr_t)(UINT64_MAX-3);names[1].n=8;break;
case 16:names[1].n=0;break;
case 17:names[1].n=65;break;
case 18:names[1].n=64;w=(uint64_t*)(names[1].p+56);break;
case 19:names[1].n=64;out=(uint8_t*)names[1].p+63;cap=8;break;
case 20:names[1].p=out+8176;names[1].n=16;break;
case 21:q[0]=3;cap=0;break;
case 22:q[1]=UINT64_MAX;cap=0;break;
  }
  memcpy(saved,a,sizeof(a));
  uint64_t st=dong_emit(names,q,s,sn,ids,inn,from,out,cap,w);
  if(st!=1||memcmp(saved,a,sizeof(a))){fprintf(stderr,"preflight %u st=%u unchanged=%d\n",k,(unsigned)st,!memcmp(saved,a,sizeof(a)));exit(93);}
  tests++;
 }
 return tests;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t pre=invalid(),count;rd(&count,8);wr(&pre,8);
 while(count--){
  uint64_t h[28];rd(h,sizeof(h));uint64_t pool=h[0],cap=h[26];if(pool>8192||cap>8192)exit(94);
  uint8_t*page=alloc_ro(16384),*snapshot=malloc(16384),*out=malloc(cap+64);if(!page||!snapshot||!out)exit(95);
  memset(page,0xa5,16384);rd(page,pool);memcpy(snapshot,page,16384);
  Name names[6];for(unsigned j=0;j<6;j++){if(h[1+2*j]>pool||h[2+2*j]>pool-h[1+2*j])exit(94);names[j]=(Name){page+h[1+2*j],h[2+2*j]};}
  uint64_t q[8];memcpy(q,h+13,64);if(!protect_ro(page,16384))exit(97);
  static _Alignas(8) uint64_t meta[3];memset(meta,0xa5,sizeof(meta));memset(out,0xa5,cap+64);
  uint64_t st=dong_emit(names,q,(Scope*)(page+h[24]),h[21],(uint64_t*)(page+h[25]),h[22],h[23],cap?out+32:NULL,cap,meta+1);
  uint64_t valid=!memcmp(snapshot,page,16384)&&filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(st)valid=valid&&filled(out+32,cap)&&filled(meta+1,8);
  else valid=valid&&meta[1]<=cap&&filled(out+32+meta[1],cap-meta[1]);
  uint64_t response[3]={st,valid,st?0:meta[1]};wr(response,24);wr(out+32,response[2]);
  if(!free_ro(page,16384)){exit(98);}free(snapshot);free(out);
 }return 0;
}
'''
CALLER={'rbx':0x0bbb0bbb0bbb0bbb,'rbp':0x0b0b0b0b0b0b0b0b,'r12':0x1212121212121212,'r13':0x1313131313131313,'r14':0x1414141414141414,'r15':0x1515151515151515}
CANARY=0x5ca1ab1e0ddba11c;STATE=46
NATIVE_MAIN=r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#endif
#include <stdlib.h>
static uint8_t*alloc_ro(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static int protect_ro(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;return VirtualProtect(p,n,PAGE_READONLY,&old)!=0;
#else
 return mprotect(p,n,PROT_READ)==0;
#endif
}
static int free_ro(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;return VirtualFree(p,0,MEM_RELEASE)!=0;
#else
 return munmap(p,n)==0;
#endif
}
typedef void ABI(*stub)(uint64_t*,const uint8_t*);
%DECLS%
static const stub table[]={%TABLE%};
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint8_t*source=alloc_ro(16384);if(!source)return 97;memset(source,0xa5,16384);if(!protect_ro(source,16384))return 97;
 uint64_t io[48];for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
 memset(io,0,sizeof(io));io[0]=io[47]=0xa5a5a5a5a5a5a5a5ull;table[i](io+1,source);for(unsigned j=0;j<16384;j++)if(source[j]!=0xa5)return 98;
 if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[47]!=0xa5a5a5a5a5a5a5a5ull)return 96;
 if(fwrite(io+1,8,46,stdout)!=46)return 92;
 }if(!free_ro(source,16384))return 98;return 0;
}
'''

class FunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise RuntimeError('native NASM/GCC required; no skip')
        cls.inputs=cls.digests();cls.work=ROOT/'build/test/bootstrap-nasm-slice-view-function'/('codex-'+uuid.uuid4().hex)
        cls.work.mkdir(parents=True);cls.records=[];cls.native='win64' if os.name=='nt' else 'elf64'
        (cls.work/'probe.c').write_text(HARNESS)
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))
    @staticmethod
    def digests():return {str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE,DOC,Path(__file__),*DEPENDENCIES,*sorted((ROOT/'lang/dongc').glob('*.py'))]}
    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=180)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr)
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout[-2000:],r.stderr[-2000:]))
    @classmethod
    def build_all(cls,name,text):
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap'/(MODULE+'.dg')).write_text(text)
        for p in DEPENDENCIES:shutil.copyfile(p,root/'bootstrap'/p.name)
        wrapper=root/'probe/exporter.dg';wrapper.write_text(WRAPPER);exes={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;asm=cls.work/(tag+'.asm');obj=cls.work/(tag+'.o')
            asm.write_text(compile_file(wrapper,roots=[root],mode=mode).assembly)
            for fmt in ('elf64','win64'):
                target=obj if fmt==cls.native else cls.work/(tag+'.'+fmt+'.o')
                cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',target,asm],tag+'-'+fmt)
            exe=cls.work/(tag+('.exe' if os.name=='nt' else ''))
            cls.command([cls.cc,'-std=c11','-D_GNU_SOURCE','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],tag+'-link')
            exes[mode]=exe
        return exes
    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        after=cls.digests()
        (cls.work/'summary.json').write_text(json.dumps(dict(task=TASK,source_sha256=cls.inputs,source_sha256_after=after,stable=after==cls.inputs,records=cls.records,primary_vectors_per_mode=len(VECTORS),formats=['elf64','win64'],OS_VM=False),indent=2))
        if after!=cls.inputs:raise AssertionError('input SHA changed')
    def emit(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for v,cap,status in cases:
            pool=bytearray();h=[0]*28
            for j,n in enumerate(v['names']):h[1+2*j]=len(pool);h[2+2*j]=len(n);pool+=n+b'\xa5'*16
            pool+=b'\xa5'*(-len(pool)%8);h[24]=len(pool)
            for s in v.get('scopes',[(MAX,0,0)]):pool+=struct.pack('<3Q',*s)
            h[25]=len(pool)
            for i in v.get('ids',[]):pool+=struct.pack('<Q',i)
            h[0]=len(pool);h[13:21]=v['q']+[0]*(8-len(v['q']));h[21]=len(v.get('scopes',[(MAX,0,0)]));h[22]=len(v.get('ids',[]));h[23]=v.get('from',0);h[26]=cap
            payload+=struct.pack('<28Q',*h)+pool
        (self.work/(label+'.input')).write_bytes(payload)
        r=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(r.stdout);(self.work/(label+'.stderr')).write_bytes(r.stderr)
        self.assertEqual(r.returncode,0,(label,r.stderr));self.assertEqual(struct.unpack_from('<Q',r.stdout)[0],PREFLIGHTS)
        at=8;texts=[]
        for k,(_,_,status) in enumerate(cases):
            st,valid,n=struct.unpack_from('<3Q',r.stdout,at);at+=24;text=r.stdout[at:at+n];at+=n
            self.assertEqual(valid,1,(label,k,'guard/atomicity'));self.assertEqual(st,status,(label,k,'emit status'))
            texts.append(text if st==0 else None)
        self.assertEqual(at,len(r.stdout));return texts
    def generate(self,exe,vs,label,exact=True):
        texts=self.emit(exe,[(v,8192,0) for v in vs],label)
        if exact:
            for v,t in zip(vs,texts):self.assertEqual(t,expected_text(v),(label,'exact text'))
        return texts
    def native_run(self,texts,vs,label):
        asm=['bits 64','section .data','align 8','observation: dq 0','host_anchor: dq 0','parked_rax: dq 0','parked_rdx: dq 0','source_base: dq 0','log_count: dq 0','log_ids: times 16 dq 0','log_align: times 16 dq 0','section .text']
        for k,v in enumerate(vs):
            asm+=['global v%d'%k,'v%d:'%k,'push rbx','push rbp','push r12','push r13','push r14','push r15','sub rsp, 8','mov [rel observation], rdi','mov [rel source_base], rsi','mov [rel host_anchor], rsp','mov r11, rdi','mov qword [rel log_count], 0','mov rax, 0x%x'%CANARY,'mov [rsp], rax','mov [r11+16], rsp','mov rax, rsp','and rax, 15','mov [r11+96], rax','mov rax, 0x%x'%CALLER['rbx'],'mov [r11+32], rax']
            asm+=['mov %s, 0x%x'%(r,n) for r,n in CALLER.items()]
            asm+=['mov %s, 0x%x'%(r,n) for r,n in zip(('rdi','rsi','rdx','rcx'),v['args'])]
            if v['args'][0]==0x1000:asm+=['mov rdi, [rel source_base]']
            asm+=['call '+symbol(*v['names'][:2]),'mov [rel parked_rax], rax','mov [rel parked_rdx], rdx','mov rax, [rel observation]','mov [rax+24], rsp','mov [rax+40], rbx','mov [rax+48], rbp']
            asm+=['mov [rax+%d], r%d'%(8*(7+j),12+j) for j in range(4)]
            asm+=['mov rcx, [rel parked_rax]','mov [rax], rcx','mov rcx, [rel parked_rdx]','mov [rax+8], rcx','mov rcx, [rel host_anchor]','mov rcx, [rcx]','mov [rax+88], rcx','mov rcx, [rel log_count]','mov [rax+104], rcx']
            for j in range(16):asm+=['mov rcx, [rel log_ids+%d]'%(j*8),'mov [rax+%d], rcx'%((14+j)*8),'mov rcx, [rel log_align+%d]'%(j*8),'mov [rax+%d], rcx'%((30+j)*8)]
            if v['args'][0]==0x1000:asm+=['mov rcx, [rel source_base]','mov [rax+112], rcx']
            asm+=['mov rsp, [rel host_anchor]','add rsp, 8','pop r15','pop r14','pop r13','pop r12','pop rbp','pop rbx','ret']
        asm+=targets(vs)
        asm+=[t.decode('ascii') for t in texts]
        f=self.work/(label+'.native.asm');f.write_text('\n'.join(asm)+'\n')
        for fmt in ('elf64','win64'):self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.'+fmt+'.o'),f],label+'-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*,const uint8_t*);'%k for k in range(len(vs)))).replace('%TABLE%',','.join('v%d'%k for k in range(len(vs))))
        c=self.work/(label+'.c');c.write_text(main);exe=self.work/(label+('.exe' if os.name=='nt' else ''))
        self.command([self.cc,'-std=c11','-D_GNU_SOURCE','-O2','-Wall','-Wextra','-Werror',c,self.work/(label+'.'+self.native+'.o'),'-o',exe],label+'-link')
        r=subprocess.run([str(exe)],capture_output=True,timeout=60);(self.work/(label+'.native.output')).write_bytes(r.stdout)
        self.assertEqual(r.returncode,0,(label,'normal native exit',r.stderr));self.assertEqual(len(r.stdout),len(vs)*STATE*8)
        obs=[struct.unpack_from('<46Q',r.stdout,k*STATE*8) for k in range(len(vs))]
        self.records.append(dict(native=label,normal_exit=True,observations=obs,expected=[oracle(v) for v in vs]))
        for k,(v,g) in enumerate(zip(vs,obs)):
            self.assertEqual(g[12],0,(label,k,'caller alignment'));self.assertEqual(g[2],g[3],(label,k,'balanced rsp'))
            self.assertEqual(g[4],CALLER['rbx']);self.assertEqual(g[5],CALLER['rbx'],(label,k,'callee-saved rbx'))
            self.assertEqual(g[6:11],tuple(n for r,n in CALLER.items() if r!='rbx'),(label,k,'saved registers'))
            self.assertEqual(g[11],CANARY,(label,k,'stack guard'))
            pair,order=oracle(v)
            if v['args'][0]==0x1000 and pair[1]!=MAX:pair=(g[14]+v['args'][2]*v['q'][0],pair[1])
            self.assertEqual(g[13],len(order),(label,k,'call trace'))
            self.assertEqual(list(g[14:14+len(order)]),order,(label,k,'call trace'))
            self.assertEqual(list(g[30:30+len(order)]),[8]*len(order),(label,k,'callee alignment'))
            self.assertEqual(g[0] if NT==6 else g[:2],pair,(label,k,'native value/status'))
        return obs
    def test_contract(self):
        self.assertLessEqual(len(VECTORS),24)
        for mode,exe in self.executables.items():
            cases=[]
            for v in VECTORS:
                n=len(expected_text(v));cases += [(v,n,0),(v,n+17,0),(v,n-1,2),(v,0,2)]
            cases+=invalid_cases()
            texts=self.emit(exe,cases,'contract-'+mode)
            for (v,_,status),t in zip(cases,texts):
                if status==0:
                    self.assertEqual(t,expected_text(v));self.assertNotIn(b'\n\n',t)
                    self.assertTrue(all(b==10 or 32<=b<127 for b in t))
    def test_native(self):
        for mode,exe in self.executables.items():self.native_run(self.generate(exe,VECTORS,'good-'+mode),VECTORS,'native-'+mode)
    def test_real_bad_dong(self):
        source=SOURCE.read_text(encoding='utf-8')
        for label,old,new,indices,key in mutations(source):
            self.assertIn(old,source,label);bad=source.replace(old,new)
            vs=[VECTORS[i] for i in indices]
            for mode,exe in self.executables.items():self.native_run(self.generate(exe,vs,label+'-good-'+mode),vs,label+'-good-'+mode)
            for mode,exe in self.build_all(label,bad).items():
                with self.assertRaisesRegex(AssertionError,key):self.native_run(self.generate(exe,vs,label+'-'+mode,False),vs,label+'-'+mode)
            self.records.append(dict(mutant=label,compiled=True,normal_exit=True,rejected_by=key))
        old='if total>out.len{return CAPACITY;}'
        new='if total>out.len{if out.len!=0{out[0]=95;}return CAPACITY;}'
        self.assertEqual(source.count(old),1);v=VECTORS[0];short=[(v,len(expected_text(v))-1,2)]
        for mode,exe in self.executables.items():self.emit(exe,short,'capacity-good-'+mode)
        for mode,exe in self.build_all('bad-capacity',source.replace(old,new)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,short,'capacity-bad-'+mode)
        self.records.append(dict(mutant='bad-capacity',compiled=True,normal_exit=True,rejected_by='guard/atomicity'))
    def test_real_rbx_control(self):
        source=SOURCE.read_text(encoding='utf-8')
        bad=re.sub(r'(if ex\.emit\([^\n]*?buffer,&n\)!=0\{return false;\})at=n;',r'\1at=n-4;if !put(buffer,&at,"add rbx, 8\\nret\\n"){return false;}',source)
        self.assertNotEqual(source,bad)
        vs=[VECTORS[i] for i in RBX_CASES]
        for mode,exe in self.executables.items():self.native_run(self.generate(exe,vs,'rbx-good-'+mode),vs,'rbx-good-'+mode)
        for mode,exe in self.build_all('bad-rbx',bad).items():
            # Each exit is checked separately so the first rejection cannot hide the second exit.
            for j,v in enumerate(vs):
                with self.assertRaisesRegex(AssertionError,'callee-saved rbx'):self.native_run(self.generate(exe,[v],'rbx-bad-%s-%d'%(mode,j),False),[v],'rbx-bad-%s-%d'%(mode,j))
        self.records.append(dict(mutant='bad-rbx',compiled=True,normal_exit=True,exits=len(vs),rejected_by='callee-saved rbx'))

if __name__=='__main__':unittest.main()
