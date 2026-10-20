"""Compact/legacy encodings against NASM bytes; real assembled ELF execution."""
import hashlib,json,os,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
ROOT=Path(__file__).resolve().parents[2]
WRAPPER='''module probe;
import bootstrap.x86_encode as x;
import bootstrap.native_assembler as a;
export("enc") unsafe fn enc(o:*u8,n:usize,i:*const x.Instruction,w:*usize,short:bool)u64{unsafe{
 if short{return x.encode_compact(slice_from_raw_parts(o,n),i,w);}return x.encode(slice_from_raw_parts(o,n),i,w);
}}
export("assemble") unsafe fn assemble(p:*const u8,n:usize,w:*const a.Workspace,o:*u8,on:usize,r:*a.Result)u64{unsafe{
 return a.assemble(slice_from_raw_parts(p,n),"f",w,slice_from_raw_parts(o,on),r);
}}
'''
HARNESS=r'''
#define _GNU_SOURCE
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
typedef uint64_t U;
typedef struct{U v[11];}Ins;
typedef struct{void*p;U n;}S;
typedef struct{U start,length,section,offset;}Label;
typedef struct{S labels,table,text,data;}Workspace;
typedef struct{U status,line,detail,text,data,labels,written;}Result;
extern U ABI enc(void*,U,const Ins*,U*,U),assemble(const void*,U,const Workspace*,void*,U,Result*);
static void check(int good,const char*s){if(!good){fprintf(stderr,"FAIL %s\n",s);exit(90);}}
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*p,U n){(void)k;(void)l;(void)p;(void)n;check(0,"panic");abort();}
static void read_exact(void*p,U n){check(fread(p,1,n,stdin)==n,"input");}
static int fill(const unsigned char*p,U n){while(n--)if(*p++!=0xa5)return 0;return 1;}
static void preflight(void){
 for(U mode=0;mode<2;mode++)for(U k=0;k<10;k++){
  union{U a[64];unsigned char b[512];}raw,saved;memset(&raw,0xa5,sizeof raw);Ins*i=(Ins*)(raw.b+128);memset(i,0,sizeof *i);i->v[0]=29;
  U*w=(U*)(raw.b+400);void*out=raw.b+32;U n=15;Ins*ip=i;U*wp=w;
  switch(k){case 0:ip=NULL;break;case 1:wp=NULL;break;case 2:ip=(Ins*)(raw.b+129);break;case 3:wp=(U*)(raw.b+401);break;
   case 4:out=raw.b+120;break;case 5:wp=(U*)(raw.b+40);break;case 6:wp=(U*)(raw.b+128);break;
   case 7:out=NULL;break;case 8:i->v[10]=1;break;case 9:out=(void*)(uintptr_t)(UINT64_MAX-3);break;}
  saved=raw;check(enc(out,n,ip,wp,mode)==1&&!memcmp(&raw,&saved,sizeof raw),"invalid atomicity");
 }
}
static void execution(void){
 const char*source="bits 64\ndefault rel\nsection .text\nf:\npush rbp\nmov rbp, rsp\nsub rsp, 16\nmov rax, qword [rel datum]\nmov qword [rbp-8], rax\nmov rax, qword [rbp-8]\nadd rsp, 16\npop rbp\nret\nsection .rodata\ndatum: dq 37\n";
 Label labels[256];U table[1024];unsigned char text[65536],data[4096],image[131072];
 Workspace w={ {labels,256},{table,1024},{text,sizeof text},{data,sizeof data} };Result r={0};
 check(assemble(source,strlen(source),&w,image,sizeof image,&r)==0&&r.status==0&&r.written>4096,"native assembler");
 check(r.text<55,"compact assembled stack operands");
 U ph=*(U*)(image+32),count=*(uint16_t*)(image+56),extent=0;
 for(U i=0;i<count;i++){U*q=(U*)(image+ph+56*i);U end=q[2]+q[5]-0x400000;if(end>extent)extent=end;}
 extent=(extent+4095)&~4095ULL;
#ifdef _WIN32
 void*m=VirtualAlloc((void*)0x400000,extent,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);check(m!=NULL,"map image");
#else
 void*m=mmap((void*)0x400000,extent,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);check(m!=MAP_FAILED,"map image");
#endif
 for(U i=0;i<count;i++){U*q=(U*)(image+ph+56*i);memcpy((void*)(uintptr_t)q[2],image+q[1],q[4]);
#ifdef _WIN32
  DWORD old;check(VirtualProtect((void*)(uintptr_t)q[2],q[5],(q[0]>>32)&1?PAGE_EXECUTE_READ:PAGE_READWRITE,&old),"protect image");
#else
  check(!mprotect((void*)(uintptr_t)q[2],(q[5]+4095)&~4095ULL,PROT_READ|((q[0]>>32)&1?PROT_EXEC:PROT_WRITE)),"protect image");
#endif
 }
#ifdef _WIN32
 FlushInstructionCache(GetCurrentProcess(),m,extent);
#endif
 U(ABI*fn)(void)=(U(ABI*)(void))(uintptr_t)*(U*)(image+24);check(fn()==37,"RIP data and stack memory execution");
}
int main(void){
#ifdef _WIN32
 check(_setmode(_fileno(stdin),_O_BINARY)!=-1,"binary input");
#endif
 preflight();U count;read_exact(&count,8);
 for(U k=0;k<count;k++){Ins in,old;unsigned char expected[2][16];read_exact(&in,sizeof in);old=in;read_exact(expected,sizeof expected);
  for(U mode=0;mode<2;mode++){
   unsigned char out[64];memset(out,0xa5,sizeof out);U written=123;
   U n=expected[mode][0];check(n>0&&n<=15,"oracle length");
   check(enc(out+16,15,&in,&written,mode)==0&&written==n&&!memcmp(out+16,expected[mode]+1,n),"encoding oracle");
   check(fill(out,16)&&fill(out+16+n,48-n)&&!memcmp(&in,&old,sizeof in),"success canaries/input");
   memset(out,0xa5,sizeof out);written=123;
   check(enc(out+16,n-1,&in,&written,mode)==2&&written==123&&fill(out,sizeof out)&&!memcmp(&in,&old,sizeof in),"capacity atomicity");
  }
 }
 execution();printf("%llu oracle vectors; legacy+compact, capacity/preflight, real ELF PASS\n",(unsigned long long)count);return 0;
}
'''
def vectors():
 rows=[];regs='rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15'.split()
 def add(ins,short,long):rows.append((ins,short,long))
 def memory(base,disp,force=False):return '['+('dword ' if force else '')+regs[base]+('+' if disp>=0 else '')+str(disp)+']'
 for base in range(16):
  for d in (0,127,128,-128,-129):
   ins=[1,3,64,0,0,base,d&((1<<64)-1),0,0,0,0]
   add(ins,'mov rax,qword '+memory(base,d),'mov rax,qword '+memory(base,d,True))
  for width,src,name in ((8,4,'spl'),(16,9,'r9w'),(32,9,'r9d'),(64,9,'r9')):
   ins=[1,4,width,0,src,base,0,0,0,0,0];size={8:'byte',16:'word',32:'dword',64:'qword'}[width]
   add(ins,'mov '+size+' '+memory(base,0)+','+name,'mov '+size+' '+memory(base,0,True)+','+name)
  for d in (0,-128,127,128,-129):
   index=12 if base%2 else 2;scale=(2,4,8)[base%3];addr=f'{regs[base]}+{regs[index]}*{scale}'+('+' if d>=0 else '')+str(d)
   add([9,8,64,9,index,base,d&((1<<64)-1),scale,0,0,0],f'lea r9,[{addr}]',f'lea r9,[dword {addr}]')
 add([1,3,64,0,0,16,0,0,0,0,0],'mov rax,[rel $+7]','mov rax,[rel $+7]')
 return rows
class Tests(unittest.TestCase):
 def test_oracle_both_apis_native_elf_and_real_bad_encoders(self):
  out=ROOT/'build/test/x86-compact'/('run-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
  names=['lang/bootstrap/x86_encode.dg','lang/bootstrap/native_assembler.dg','lang/bootstrap/elf64_image.dg','lang/tests/test_bootstrap_x86_compact.py']
  before={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names};snapshot=out/'source';(snapshot/'bootstrap').mkdir(parents=True)
  for n in names[:3]:(snapshot/'bootstrap'/Path(n).name).write_bytes((ROOT/n).read_bytes())
  wrapper=out/'probe.dg';wrapper.write_text(WRAPPER);harness=out/'probe.c';harness.write_text(HARNESS)
  nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc);records=[]
  def command(args,label,data=None,expected=0):
   r=subprocess.run(list(map(str,args)),input=data,capture_output=True,timeout=120)
   (out/(label+'.stdout')).write_bytes(r.stdout);(out/(label+'.stderr')).write_bytes(r.stderr)
   self.assertEqual(r.returncode,expected,r.stderr.decode(errors='replace'));records.append(dict(command=list(map(str,args)),returncode=r.returncode,expected=expected));return r
  rows=vectors();oracle=out/'oracle.asm'
  oracle.write_text('bits 64\n'+''.join(f'block_{i}_{mode}:\ndb end_{i}_{mode}-start_{i}_{mode}\nstart_{i}_{mode}:\n{row[2 if mode==0 else 1]}\nend_{i}_{mode}:\ntimes 15-($-start_{i}_{mode}) db 0\n' for i,row in enumerate(rows) for mode in range(2)))
  binary=out/'oracle.bin';command([nasm,'-f','bin',oracle,'-o',binary],'oracle');expected=binary.read_bytes();self.assertEqual(len(expected),len(rows)*32)
  payload=bytearray(struct.pack('<Q',len(rows)))
  for i,row in enumerate(rows):payload+=struct.pack('<11Q',*row[0])+expected[i*32:(i+1)*32]
  production=(snapshot/'bootstrap/x86_encode.dg').read_text()
  for mode in ('debug','release'):
   for variant in ('normal','bad-zero-rbp','bad-negative-byte'):
    source=production
    if variant=='bad-zero-rbp':source=source.replace('disp==0&&(m&7)!=5','disp==0')
    if variant=='bad-negative-byte':source=source.replace('disp>=0xffff_ffff_ffff_ff80','disp>=0xffff_ffff_ffff_ff7f')
    (snapshot/'bootstrap/x86_encode.dg').write_text(source)
    compiled=compile_file(wrapper,roots=[snapshot,out],mode=mode);name=mode+'-'+variant
    asm=out/(name+'.asm');asm.write_text(compiled.assembly);obj=out/(name+'.o');exe=out/(name+('.exe' if os.name=='nt' else ''))
    for fmt in ('elf64','win64'):
     target=obj if fmt==('win64' if os.name=='nt' else 'elf64') else out/(name+'.'+fmt+'.o')
     command([nasm,'-O0','-f',fmt,*nasm_flags(nasm),'-o',target,asm],name+'-'+fmt)
    command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',harness,obj,'-o',exe],name+'-link')
    run=command([exe],name+'-run',bytes(payload),0 if variant=='normal' else 90)
    if variant!='normal':self.assertIn(b'FAIL encoding oracle',run.stderr)
  self.assertEqual(before,{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names})
  (out/'summary.json').write_text(json.dumps(dict(inputs=before,source_stable=True,vectors=len(rows),records=records,guest_executed=False),indent=2)+'\n')
if __name__=='__main__':unittest.main()
