"""Actual Dong stack-slot layout, against unbounded Python integer arithmetic."""
import hashlib
import json
import os
from pathlib import Path
import random
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

SOURCE=WORKS/'claude-works/src/bootstrap/stack_slots.dg'
OK,INVALID,CAPACITY=0,1,2
MAX=2**64-1
WRAPPER='''module probe.slots_export;
import bootstrap.stack_slots as s;
export("dong_stack_slots") pub unsafe fn plan(slots:*const s.Slot,ns:usize,offsets:*usize,no:usize,frame_bytes:*usize)u64{unsafe{
 return s.plan(slice_from_raw_parts(slots,ns),slice_from_raw_parts(offsets,no),frame_bytes);
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
typedef struct {uint64_t size,alignment;} Slot;
_Static_assert(sizeof(Slot)==16&&__builtin_offsetof(Slot,alignment)==8,"Slot layout");
extern uint64_t ABI dong_stack_slots(const Slot*,uint64_t,uint64_t*,uint64_t,uint64_t*);
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
static void ro_protect(void*p,uint64_t n){
#ifdef _WIN32
 DWORD old;if(!VirtualProtect(p,n,PAGE_READONLY,&old))exit(98);
#else
 if(mprotect(p,n,PROT_READ))exit(98);
#endif
}
static void ro_free(void*p,uint64_t n){
#ifdef _WIN32
 (void)n;VirtualFree(p,0,MEM_RELEASE);
#else
 munmap(p,n);
#endif
}
/* Bad descriptors: INVALID with every arena byte unchanged. */
static unsigned invalid(void){
 static uint8_t arena[2048],saved[2048];const unsigned total=12;
 Slot*s=(Slot*)arena;uint64_t*o=(uint64_t*)(arena+512);uint64_t*f=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));s[0].size=4;s[0].alignment=4;s[1].size=8;s[1].alignment=8;memcpy(saved,arena,sizeof(arena));uint64_t r=0;
  switch(i){
   case 0:r=dong_stack_slots(s,2,o,8,NULL);break;
   case 1:r=dong_stack_slots(s,2,o,8,(uint64_t*)(arena+1540));break;
   case 2:r=dong_stack_slots(s,2,o,8,(uint64_t*)s);break;
   case 3:r=dong_stack_slots(s,2,(uint64_t*)s+1,8,f);break;
   case 4:r=dong_stack_slots(s,2,o,8,o+5);break;
   case 5:r=dong_stack_slots((Slot*)(arena+4),2,o,8,f);break;
   case 6:r=dong_stack_slots(s,2,(uint64_t*)(arena+516),8,f);break;
   case 7:r=dong_stack_slots(NULL,2,o,8,f);break;
   case 8:r=dong_stack_slots(s,2,NULL,8,f);break;
   case 9:r=dong_stack_slots(s,UINT64_MAX/16+1,o,8,f);break;
   case 10:r=dong_stack_slots((Slot*)(uintptr_t)(UINT64_MAX-15),2,o,8,f);break;
   default:r=dong_stack_slots(s,2,o,UINT64_MAX/8+1,f);break;
  }
  if(r!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)r);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[3];read_exact(h,sizeof(h));uint64_t ns=h[0],no=h[1],ro=h[2];
  if(ns>200000||no>200000)exit(94);
  uint64_t sb=ns*16;uint8_t*in=malloc(sb+64),*copy=malloc(sb+1);uint64_t*off=malloc((no+8)*8);uint64_t meta[3];
  if(!in||!copy||!off)exit(95);
  memset(in,0xa5,sb+64);read_exact(in+32,sb);memcpy(copy,in+32,sb);
  const Slot*s=ns?(const Slot*)(in+32):NULL;uint8_t*page=NULL;uint64_t pages=0;
  if(ro&&ns){pages=(sb/4096+2)*4096;page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,sb);ro_protect(page,pages);s=(const Slot*)page;}
  memset(off,0xa5,(no+8)*8);memset(meta,0xa5,sizeof(meta));uint64_t*frame=meta+1;
  uint64_t r=dong_stack_slots(s,ns,no?off+4:NULL,no,frame);
  uint64_t valid=(!sb||!memcmp(copy,s,sb))&&(ro||(filled(in,32)&&filled(in+32+sb,32)))&&filled(off,32)&&filled(off+4+no,32)&&
    filled(meta,8)&&filled(meta+2,8);
  if(r)valid=valid&&filled(off+4,no*8)&&filled(frame,8);
  else valid=valid&&no>=ns&&filled(off+4+ns,(no-ns)*8);
  uint64_t response[3]={r,valid,r?0:*frame};write_exact(response,24);write_exact(off+4,r?0:ns*8);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(off);
 }return 0;
}
'''


def reference(slots,no):
    """Unbounded integers; any intermediate above MAX is INVALID. Returns (status, offsets, frame)."""
    up=lambda x,a:-(-x//a)*a
    cursor,offsets=0,[]
    for size,alignment in slots:
        if alignment not in(1,2,4,8,16):return INVALID,None,None
        if cursor+size>MAX:return INVALID,None,None
        end=up(cursor+size,alignment)
        if end>MAX:return INVALID,None,None
        offsets.append(end);cursor=end
    frame=up(cursor,16)
    if frame>MAX:return INVALID,None,None
    if no<len(slots):return CAPACITY,None,None
    return OK,offsets,frame


def case(slots,no=None,readonly=0,status=None):
    no=len(slots)if no is None else no
    expected=reference(slots,no)
    if status is not None:assert expected[0]==status,(status,expected,slots)
    return dict(slots=slots,no=no,readonly=readonly,expected=expected)


class StackSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native stack slots require NASM/GCC')
        cls.work=WORKS/'claude-works/build/C10'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.executables={};cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,Path(__file__)]}
        wrapper=cls.work/'wrapper';(wrapper/'probe').mkdir(parents=True)
        (wrapper/'probe/slots_export.dg').write_text(WRAPPER,encoding='utf-8')
        for mode in ('debug','release'):
            cls.executables[mode]=cls.build([WORKS/'claude-works/src',wrapper],wrapper,mode,mode)

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build(cls,roots,wrapper,mode,name):
        compiled=compile_file(wrapper/'probe/slots_export.dg',roots=roots,mode=mode)
        asm=cls.work/(name+'.asm');asm.write_text(compiled.assembly,encoding='utf-8')
        native='win64'if os.name=='nt'else'elf64'
        obj=cls.work/(name+'.o');exe=cls.work/(name+('.exe'if os.name=='nt'else''))
        for fmt in ('elf64','win64'):
            output=obj if fmt==native else cls.work/(name+'.'+fmt+'.o')
            cls.command([cls.nasm,'-f',fmt,*nasm_flags(cls.nasm),'-o',output,asm],name+'-'+fmt)
        cls.command([cls.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',cls.work/'probe.c',obj,'-o',exe],name+'-link')
        return exe

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,'work'):return
        files={p.relative_to(cls.work).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in cls.work.rglob('*')if p.is_file()}
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,artifact_sha256=files,
            records=cls.records,integrated=False,OS_VM_built=False),indent=2)+'\n')

    def properties(self,slots,offsets,frame,label):
        """Frame-relative facts, independent of the exact formula: alignment, disjointness, 16-byte frame."""
        self.assertEqual(frame%16,0,(label,'frame alignment'))
        spans=[]
        for (size,alignment),offset in zip(slots,offsets):
            self.assertEqual(offset%alignment,0,(label,'slot alignment'))   # base is 16-aligned, so base-offset is aligned
            self.assertGreaterEqual(offset,size,(label,'slot below base'));self.assertLessEqual(offset,frame,(label,'slot inside frame'))
            if size:spans.append((offset-size,offset))
        spans.sort()
        for (a0,a1),(b0,b1) in zip(spans,spans[1:]):self.assertLessEqual(a1,b0,(label,'overlap'))

    def run_cases(self,exe,cases,label):
        payload=bytearray(struct.pack('<Q',len(cases)))
        for c in cases:
            payload.extend(struct.pack('<3Q',len(c['slots']),c['no'],c['readonly']))
            for size,alignment in c['slots']:payload.extend(struct.pack('<2Q',size,alignment))
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=120)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        preflights,=struct.unpack_from('<Q',run.stdout,0);self.assertEqual(preflights,12)
        offset=8
        for index,c in enumerate(cases):
            status,guard,frame=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            # Each call's storage verdict is checked before the next call's result is looked at.
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(status,c['expected'][0],(label,index,'status'))
            if not status:
                n=len(c['slots']);offsets=list(struct.unpack_from('<%dQ'%n,run.stdout,offset));offset+=8*n
                self.assertEqual(offsets,c['expected'][1],(label,index,'offsets'))
                self.assertEqual(frame,c['expected'][2],(label,index,'frame'))
                self.properties(c['slots'],offsets,frame,(label,index))
        self.assertEqual(offset,len(run.stdout))

    def run_both(self,cases,label):
        for mode,exe in self.executables.items():self.run_cases(exe,cases,label+'-'+mode)

    def test_random_layouts_against_unbounded_reference(self):
        rng=random.Random(0xC10A);cases=[]
        for i in range(400):
            slots=[(rng.choice([0,1,2,3,4,5,7,8,12,16,24,33,100,4096]),rng.choice([1,2,4,8,16]))for _ in range(rng.randint(0,24))]
            cases+=[case(slots,readonly=int(i%40==0)),case(slots,no=len(slots)+5)]
        cases.append(case([(rng.randrange(64),rng.choice([1,2,4,8,16]))for _ in range(50000)],readonly=1))
        self.run_both(cases,'random')
        self.records.append(dict(test='random-layouts',cases=len(cases),seed='0xC10A',modes=2,passed=True))

    def test_zero_sizes_overflow_invalid_alignment_and_capacity(self):
        cases=[case([],status=OK),case([],no=0,status=OK),case([(0,1)],status=OK),case([(0,16)],status=OK),case([(1,1),(0,16)],status=OK),
               case([(1,1)],status=OK),case([(1,1),(8,8)],status=OK),case([(3,2),(1,16)],status=OK),case([(16,16)]*3,status=OK),
               case([(1,1),(2,2),(4,4),(8,8),(16,16)],status=OK),case([(0,8),(0,8),(5,1)],status=OK)]
        self.assertEqual(reference([(1,1),(8,8)],2),(OK,[1,16],16))                 # end=align_up(1+8,8)=16
        for alignment in (0,3,5,6,12,32,64,4096,MAX):
            cases+=[case([(8,alignment)],status=INVALID),case([(0,alignment)],status=INVALID),case([(4,4),(8,alignment)],no=0,status=INVALID)]
        top=MAX-15                                                                    # largest multiple of 16
        cases+=[case([(top,16)],status=OK),case([(top+1,1)],status=INVALID),case([(top,1)],status=OK),case([(top-1,2)],status=OK),
                case([(MAX,1)],status=INVALID),case([(MAX-1,2)],status=INVALID),case([(top,16),(1,1)],status=INVALID),
                case([(top,16),(0,16)],status=OK),case([(2**63,8),(2**63,8)],status=INVALID),case([(2**62,16)]*3,status=OK),
                case([(2**62,16)]*4,status=INVALID),case([(1,1),(MAX-1,1)],status=INVALID),case([(top-16,16),(16,16)],status=OK),
                case([(top-16,16),(17,16)],status=INVALID),case([(top-2,1),(5,4)],status=INVALID)]
        for slots in ([(1,1)],[(8,8),(4,4)],[(1,16)]*7):
            n=len(slots);cases+=[case(slots,no=n-1,status=CAPACITY),case(slots,no=0,status=CAPACITY),case(slots,no=n+9,status=OK)]
        cases.append(case([(8,3),(1,1)],no=0,status=INVALID))
        self.run_both(cases,'bounds')
        self.records.append(dict(test='zero-overflow-invalid-capacity',cases=len(cases),invalid_preflights_per_native=12,modes=2,passed=True))

    def bad_build(self,name,old,new):
        source=SOURCE.read_text(encoding='utf-8');self.assertEqual(source.count(old),1,name)
        root=self.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/stack_slots.dg').write_text(source.replace(old,new,1),encoding='utf-8')
        (root/'probe/slots_export.dg').write_text(WRAPPER,encoding='utf-8')
        return {mode:self.build([root],root,mode,name+'-'+mode)for mode in ('debug','release')}

    def test_actual_compiled_wrong_sources_are_rejected(self):
        controls=[
            # align_up(cursor) then add size: the slot's address (base-offset) is no longer aligned.
            ('bad-align-then-add','let s=slots[i];var end:usize=0;up(cursor+s.size,s.alignment,&end);offsets[i]=end;cursor=end;i+=1;',
             'let s=slots[i];var end:usize=0;up(cursor,s.alignment,&end);end+=s.size;offsets[i]=end;cursor=end;i+=1;',
             [case([(1,1),(4,8)])],'offsets'),
            ('bad-frame-alignment','var frame:usize=0;if !up(cursor,16,&frame){return INVALID;}','var frame:usize=cursor;',
             [case([(1,1),(4,4)])],'frame'),
            # Writes each offset during the dry run, before a later overflow is detected.
            ('bad-early-write','var end:usize=0;if !up(cursor+s.size,s.alignment,&end){return INVALID;}cursor=end;i+=1;',
             'var end:usize=0;if !up(cursor+s.size,s.alignment,&end){return INVALID;}if i<offsets.len{offsets[i]=end;}cursor=end;i+=1;',
             [case([(8,8),(MAX,1)],no=2,status=INVALID)],'guard/atomicity'),
        ]
        for name,old,new,cases,reason in controls:
            # The real source passes the exact control case first.
            self.run_both(cases,name+'-good')
            for mode,exe in self.bad_build(name,old,new).items():
                with self.assertRaisesRegex(AssertionError,reason):self.run_cases(exe,cases,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,native_executed=True,modes=2,rejected_by=reason))


if __name__=='__main__':unittest.main()
