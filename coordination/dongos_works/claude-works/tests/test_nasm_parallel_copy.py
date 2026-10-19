"""Actual Dong 8-slot parallel-copy emitter (C9 schedule + CR14 MOV lines): exact text, assembly, native execution."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
import uuid

WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS
if not (ROOT/'lang').is_dir() and (WORKS/'project.json').is_file():
    source=Path(json.loads((WORKS/'project.json').read_text(encoding='utf-8'))['source_root'])
    ROOT=(WORKS/source).resolve() if not source.is_absolute() else source
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_parallel_copy.dg'
DEPENDENCIES=[ROOT/'lang/bootstrap/parallel_moves.dg',ROOT/'lang/bootstrap/nasm_integer_cast.dg']   # integrated C9, CR14
OK,INVALID,CAPACITY=0,1,2
SLOT_REGS=['rax','rcx','rdx','rsi','rdi','r8','r9','r10']
TEMP='r11'
CALLEE=['rbp','r12','r13','r14','r15']
ARITH_FLAGS=0x8d5
WRAPPER='''module probe.pcopy_export;
import bootstrap.parallel_moves as pm;
import bootstrap.nasm_parallel_copy as c;
export("dong_pcopy_emit") pub unsafe fn emit(moves:*const pm.Move,nm:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return c.emit(slice_from_raw_parts(moves,nm),slice_from_raw_parts(out,no),written);
}}
export("dong_c9_schedule") pub unsafe fn schedule(moves:*const pm.Move,nm:usize,out:*pm.Move,no:usize,work:*u8,nw:usize,used:*usize)u64{unsafe{
 return pm.schedule(slice_from_raw_parts(moves,nm),8,slice_from_raw_parts(out,no),slice_from_raw_parts(work,nw),used);
}}
'''
HARNESS=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#include <io.h>
#include <fcntl.h>
#else
#include <sys/mman.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef struct {uint64_t dst,src;} Move;
_Static_assert(sizeof(Move)==16,"Move layout");
extern uint64_t ABI dong_pcopy_emit(const Move*,uint64_t,uint8_t*,uint64_t,uint64_t*);
extern uint64_t ABI dong_c9_schedule(const Move*,uint64_t,Move*,uint64_t,uint8_t*,uint64_t,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n)
{fprintf(stderr,"unexpected panic %u/%u %.*s\n",k,l,(int)n,(const char*)f);exit(87);}
static int filled(const void*p,uint64_t n){const uint8_t*s=p;for(uint64_t i=0;i<n;i++)if(s[i]!=0xa5)return 0;return 1;}
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
static void write_exact(const void*p,uint64_t n){if(n&&fwrite(p,1,n,stdout)!=n)exit(92);}
static uint8_t*ro_alloc(uint64_t n){
#ifdef _WIN32
 return VirtualAlloc(NULL,n,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
#else
 void*p=mmap(NULL,n,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return p==MAP_FAILED?NULL:p;
#endif
}
static int ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;return VirtualProtect(p,n,PAGE_READONLY,&old)!=0;
#else
 return mprotect(p,n,PROT_READ)==0;
#endif
}
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
/* Each preflight keeps every other field valid so only the target check can reject it: all 8 moves are
   legal (swap 0<->1, then self moves 2..7) before the snapshot, so a declared-tail alias of a len=8 input
   cannot be masked by C9 rejecting an illegal slot. Every failing preflight is reported, then exit 93. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[1024],saved[1024];const unsigned total=14;unsigned failed=0;
 Move*m=(Move*)arena;uint8_t*o=arena+256;uint64_t*w=(uint64_t*)(arena+768);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));m[0].dst=0;m[0].src=1;m[1].dst=1;m[1].src=0;
  for(unsigned k=2;k<8;k++){m[k].dst=k;m[k].src=k;}
  memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_pcopy_emit(m,2,o,256,NULL);break;                                     /* written NULL */
   case 1:s=dong_pcopy_emit(m,2,o,256,(uint64_t*)(arena+769));break;                   /* written odd */
   case 2:s=dong_pcopy_emit(m,2,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;    /* written end overflow, empty out */
   case 3:s=dong_pcopy_emit(m,2,(uint8_t*)(uintptr_t)(UINT64_MAX-15),16,w);break;      /* out end overflow */
   case 4:s=dong_pcopy_emit(m,2,NULL,256,w);break;                                     /* NULL non-empty out */
   case 5:s=dong_pcopy_emit(NULL,2,o,256,w);break;                                     /* NULL non-empty moves */
   case 6:s=dong_pcopy_emit((Move*)(arena+4),2,o,256,w);break;                         /* misaligned moves */
   case 7:s=dong_pcopy_emit(m,UINT64_MAX/16+1,o,256,w);break;                          /* moves length overflow */
   case 8:s=dong_pcopy_emit((Move*)(uintptr_t)(UINT64_MAX-31),2,o,256,w);break;        /* moves end overflow */
   case 9:s=dong_pcopy_emit(m,2,o,256,(uint64_t*)m);break;                             /* written on moves prefix */
   case 10:s=dong_pcopy_emit(m,8,o,256,(uint64_t*)(arena+120));break;                  /* written in moves' declared tail */
   case 11:s=dong_pcopy_emit(m,8,arena+112,64,w);break;                                /* out overlaps moves tail */
   case 12:s=dong_pcopy_emit(m,2,o,256,(uint64_t*)o);break;                            /* written on out prefix */
   default:s=dong_pcopy_emit(m,2,o,256,(uint64_t*)(o+248));break;                      /* written in out's unused tail */
  }
  int same=!memcmp(saved,arena,sizeof(arena));
  if(s!=1||!same){fprintf(stderr,"invalid preflight %u status %u unchanged %d\n",i,(unsigned)s,same);failed++;}
 }
 if(failed)exit(93);
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[3];read_exact(h,sizeof(h));uint64_t nm=h[0],cap=h[1],ro=h[2];
  if(nm>64||cap>4096)exit(94);
  uint64_t mb=nm*16;uint8_t*in=malloc(mb+64),*copy=malloc(mb+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,mb+64);read_exact(in+32,mb);memcpy(copy,in+32,mb);
  const Move*m=nm?(const Move*)(in+32):NULL;uint8_t*page=NULL;uint64_t pages=4096*2,protected_ok=1;
  if(ro&&nm){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,mb);protected_ok=ro_protect(page,pages);m=(const Move*)page;}
  /* independent C9 schedule for the expected order (slot_count 8) */
  Move steps[16];uint8_t work[8];uint64_t used=0;
  uint64_t c9=nm<=8?dong_c9_schedule(m,nm,steps,16,work,8,&used):1;
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_pcopy_emit(m,nm,cap?out+32:NULL,cap,written);
  uint64_t valid=protected_ok&&(!mb||!memcmp(copy,m,mb))&&(ro||(filled(in,32)&&filled(in+32+mb,32)))&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[5]={s,valid,s?0:*written,c9,c9?0:used};write_exact(response,40);
  write_exact(steps,c9?0:used*16);write_exact(out+32,s?0:*written);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''
NATIVE_MAIN=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  /* [0..7] slots, [8] flags before, [9] flags after, [10..15] rbp r12..r15 rsp before, [16..21] after */
  uint64_t state[24];memset(state,0,sizeof(state));read_exact(state+1,64);state[0]=state[23]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[23]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(state+1,8,22,stdout)!=22)exit(92);
 }return 0;
}
'''


def mov_line(d,s):
    regs=SLOT_REGS+[TEMP]
    return ('mov %s, %s\n'%(regs[d],regs[s])).encode()


def parallel(moves,initial):
    """Independent parallel-assignment semantics on the 8 slots using an old-value snapshot."""
    result=list(initial)
    for d,s in moves:result[d]=initial[s]
    return result


SEEDS=[0x1111111100000000+0x1000001*k+0x0123456700000000*(k+1)for k in range(8)]
VECTORS=[[],[(1,0),(2,1),(3,2)],[(0,1),(1,0)],[(0,1),(1,2),(2,0)],[(0,1),(1,0),(5,6),(6,5)],
         [(1,0),(2,0),(3,0),(4,0)],[(0,0),(3,3),(7,7)],[(k,(k+1)%8)for k in range(8)],
         [(7,6),(6,7)],[(7,0),(0,7),(3,4),(4,5),(5,3)],[(2,5),(5,2),(0,0),(4,1)],[(k,7-k)for k in range(8)]]


class NasmParallelCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C33'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,*DEPENDENCIES,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and the integrated C9/CR14 modules, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_parallel_copy.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/pcopy_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/pcopy_export.dg',roots=[root],mode=mode)
            asm=cls.work/(tag+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
            obj=cls.work/(tag+'.o');exe=cls.work/(tag+('.exe'if os.name=='nt'else''))
            for fmt in ('elf64','win64'):
                output=obj if fmt==cls.native else cls.work/(tag+'.'+fmt+'.o')
                cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],tag+'-'+fmt)
            cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],tag+'-link')
            result[mode]=exe
        return result

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def emit(self,exe,cases,label):
        """cases: (moves,cap,readonly,expected_status). Returns (text, c9 steps); guards asserted per call."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for moves,cap,ro,_ in cases:
            payload.extend(struct.pack('<3Q',len(moves),cap,ro))
            for d,s in moves:payload.extend(struct.pack('<2Q',d,s))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],14)
        offset=8;results=[]
        for index,(moves,cap,ro,status) in enumerate(cases):
            got,guard,written,c9,used=struct.unpack_from('<5Q',run.stdout,offset);offset+=40
            flat=struct.unpack_from('<%dQ'%(2*used),run.stdout,offset);offset+=16*used
            steps=[(flat[2*k],flat[2*k+1])for k in range(used)]
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,status,(label,index,'status',moves))
            results.append((text if got==OK else None,steps if c9==OK else None))
        self.assertEqual(offset,len(run.stdout))
        return results

    def native_run(self,texts,vectors,label):
        """rbx (saved/restored) holds the state pointer, so no slot or R11 is used as an observation temporary."""
        stub=['bits 64','section .text']
        for k,text in enumerate(texts):
            stub+=['global v%d'%k,'v%d:'%k,'push rbx','mov rbx, rdi']
            stub+=['mov [rbx+%d], %s'%(80+8*j,r)for j,r in enumerate(CALLEE)]+['mov [rbx+120], rsp']
            stub+=['mov %s, [rbx+%d]'%(r,8*j)for j,r in enumerate(SLOT_REGS)]
            stub+=['pushfq','pop qword [rbx+64]']+text.decode('ascii').rstrip('\n').split('\n')*(1 if text else 0)
            stub+=['pushfq','pop qword [rbx+72]']+['mov [rbx+%d], %s'%(8*j,r)for j,r in enumerate(SLOT_REGS)]
            stub+=['mov [rbx+%d], %s'%(128+8*j,r)for j,r in enumerate(CALLEE)]+['mov [rbx+168], rsp','pop rbx','ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%k for k in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%k for k in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=b''.join(struct.pack('<8Q',*SEEDS)for _ in vectors)
        run=subprocess.run([str(exe)],input=payload,capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for k,moves in enumerate(vectors):
            got=list(struct.unpack_from('<22Q',run.stdout,176*k))
            self.assertEqual(got[:8],parallel(moves,SEEDS),(label,k,'native slots',moves))
            self.assertEqual(got[8]&ARITH_FLAGS,got[9]&ARITH_FLAGS,(label,k,'native flags preserved'))
            self.assertEqual(got[10:16],got[16:22],(label,k,'native callee-saved and rsp preserved'))

    def test_exact_text_follows_c9_schedule(self):
        cases=[]
        for k,moves in enumerate(VECTORS):
            cases+=[(moves,256,int(k%3==0),OK),(moves,300,0,OK)]
        longest=[(k,(k+1)%8)for k in range(4)]+[(4+k,4+(k+1)%4)for k in range(4)]   # two 4-cycles
        cases+=[(longest,256,1,OK),([(0,1),(1,0),(2,3),(3,2),(4,5),(5,4),(6,7),(7,6)],256,1,OK)]   # four swaps: 12 steps
        for mode,exe in self.executables.items():
            results=self.emit(exe,cases,'text-'+mode)
            for (moves,cap,ro,status),(text,steps) in zip(cases,results):
                self.assertEqual(text,b''.join(mov_line(d,s)for d,s in steps),(mode,moves,'C9 order'))
        swaps=self.emit(self.executables['release'],[cases[-1]],'longest')[0]
        self.assertEqual(len(swaps[1]),12);self.assertLessEqual(len(swaps[0]),12*13)        # 12 steps, each line at most 13 bytes
        self.records.append(dict(test='exact-text-c9-order',cases=len(cases),max_steps_observed=12,modes=2,passed=True))

    def test_capacity_and_invalid_moves(self):
        cases=[]
        for moves in VECTORS[1:5]+[VECTORS[7]]:
            n=len(self.emit(self.executables['release'],[(moves,256,0,OK)],'size')[0][0])
            cases+=[(moves,n,0,OK),(moves,n-1,0,CAPACITY),(moves,0,0,CAPACITY)]
        cases+=[([],0,0,OK),([(0,0),(5,5)],0,0,OK),([],256,1,OK)]
        cases+=[([(k,(k+1)%9)for k in range(9)],256,0,INVALID),([(0,1)]*9,0,0,INVALID),([(0,8)],256,0,INVALID),([(8,0)],0,0,INVALID),
                ([(0,1),(0,2)],256,0,INVALID),([(3,3),(3,3)],256,1,INVALID),([(0,2**64-1)],256,0,INVALID),
                ([(0,1),(0,2)],0,0,INVALID),([(3,3),(3,3)],0,1,INVALID)]   # legal count/slots, duplicate dst, cap 0: INVALID before CAPACITY
        for mode,exe in self.executables.items():
            results=self.emit(exe,cases,'bounds-'+mode)
            for (moves,cap,ro,status),(text,_) in zip(cases,results):
                if status==OK and not any(d!=s for d,s in moves):self.assertEqual(text,b'',(mode,moves))
        self.records.append(dict(test='capacity-invalid',cases=len(cases),preflights_per_native=14,modes=2,passed=True))

    def test_native_parallel_semantics(self):
        self.assertEqual(len(set(SEEDS)),8);self.assertTrue(all(s>>32 for s in SEEDS))
        for mode,exe in self.executables.items():
            texts=[t for t,_ in self.emit(exe,[(m,256,0,OK)for m in VECTORS],'vectors-'+mode)]
            self.native_run(texts,VECTORS,'native-'+mode)
        self.records.append(dict(test='native-parallel-copy',vectors_per_mode=len(VECTORS),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        old='if slot==7{return 10;}return 11;';new='if slot==7{return 10;}return 10;';self.assertEqual(source.count(old),1)
        vectors=[VECTORS[8],VECTORS[9]]                                          # swaps/cycles involving slot 7 (r10)
        for mode,exe in self.executables.items():
            self.native_run([t for t,_ in self.emit(exe,[(m,256,0,OK)for m in vectors],'bad-temp-good-'+mode)],vectors,'bad-temp-good-'+mode)
        for mode,exe in self.build_all('bad-temp-r10',source.replace(old,new,1)).items():
            texts=[t for t,_ in self.emit(exe,[(m,256,0,OK)for m in vectors],'bad-temp-'+mode)]
            with self.assertRaisesRegex(AssertionError,'native slots'):self.native_run(texts,vectors,'bad-temp-'+mode)
        self.records.append(dict(test='bad-temp-r10',compiled=True,native_executed=True,modes=2,rejected_by='native slots'))
        old='if at>out.len{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='var j:usize=0;while j<at&&j<out.len{out[j]=text[j];j+=1;}if at>out.len{return CAPACITY;}'
        case=[(VECTORS[3],10,0,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))

    def test_prefix_only_input_alias_is_rejected(self):
        """Preflight sensitivity: a real Dong that checks only the first two moves (32 bytes) for input aliasing."""
        source=SOURCE.read_text(encoding='utf-8')
        old='overlap(mp,mn,op,out.len)||overlap(mp,mn,wp,8)';self.assertEqual(source.count(old),1)
        for mode,exe in self.executables.items():self.emit(exe,[],'prefix-good-'+mode)      # same harness passes all 14
        for mode,exe in self.build_all('bad-prefix-alias',source.replace(old,'overlap(mp,32,op,out.len)||overlap(mp,32,wp,8)',1)).items():
            run=subprocess.run([str(exe)],input=struct.pack('<Q',0),capture_output=True,timeout=60)
            err=run.stderr.decode('ascii','replace');(self.work/('bad-prefix-'+mode+'.stderr')).write_text(err,encoding='ascii')
            self.assertEqual(run.returncode,93,(mode,err))                                   # normal exit from the preflight check
            failed=sorted(int(line.split()[2])for line in err.splitlines()if line.startswith('invalid preflight '))
            self.assertEqual(failed,[10,11],(mode,err))                                      # exactly the two declared-tail cases
            self.assertNotIn('status 1 unchanged 1',err)
        self.records.append(dict(test='bad-prefix-alias',compiled=True,native_executed=True,modes=2,rejected_by='preflight 10/11'))


if __name__=='__main__':unittest.main()
