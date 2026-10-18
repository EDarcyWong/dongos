"""Actual Dong NASM direct-call emitter: exact CR3 symbol text, dual-format assembly, and native SysV calls."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_direct_call.dg'
DEPENDENCY=ROOT/'lang/bootstrap/nasm_symbol.dg'      # integrated CR3, staged read-only
OK,INVALID,CAPACITY=0,1,2
WRAPPER='''module probe.call_export;
import bootstrap.nasm_direct_call as c;
export("dong_call_emit") pub unsafe fn emit(module_name:*const u8,nm:usize,item_name:*const u8,ni:usize,out:*u8,no:usize,written:*usize)u64{unsafe{
 return c.emit(slice_from_raw_parts(module_name,nm),slice_from_raw_parts(item_name,ni),slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_call_emit(const uint8_t*,uint64_t,const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
#define FAKE(x) ((const uint8_t*)(uintptr_t)(x))
/* Each preflight keeps every other field valid (names 1..64 bytes, aligned written) so only the target check can reject. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[2048],saved[2048];const unsigned total=21;
 uint8_t*m=arena+64,*it=arena+192,*o=arena+512;uint64_t*w=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_call_emit(m,4,it,4,o,512,NULL);break;                                     /* written NULL */
   case 1:s=dong_call_emit(m,4,it,4,o,512,(uint64_t*)(arena+1537));break;                  /* written odd */
   case 2:s=dong_call_emit(m,4,it,4,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;    /* written end overflow, empty out */
   case 3:s=dong_call_emit(m,4,it,4,(uint8_t*)(uintptr_t)(UINT64_MAX-15),16,w);break;      /* out end overflow */
   case 4:s=dong_call_emit(m,4,it,4,NULL,512,w);break;                                     /* NULL non-empty out */
   case 5:s=dong_call_emit(NULL,4,it,4,o,512,w);break;                                     /* NULL non-empty module */
   case 6:s=dong_call_emit(m,4,NULL,4,o,512,w);break;                                      /* NULL non-empty item */
   case 7:s=dong_call_emit(FAKE(UINT64_MAX-3),8,it,4,o,512,w);break;                       /* module end overflow */
   case 8:s=dong_call_emit(m,4,FAKE(UINT64_MAX-1),4,o,512,w);break;                        /* item end overflow */
   case 9:s=dong_call_emit(m,64,it,4,o,512,(uint64_t*)m);break;                            /* written on module's aligned prefix */
   case 10:s=dong_call_emit(m,64,it,4,o,512,(uint64_t*)(m+56));break;                      /* written in module's declared tail */
   case 11:s=dong_call_emit(m,4,it,64,o,512,(uint64_t*)it);break;                          /* written on item prefix */
   case 12:s=dong_call_emit(m,4,it,64,o,512,(uint64_t*)(it+56));break;                     /* written in item's declared tail */
   case 13:s=dong_call_emit(m,4,it,4,o,512,(uint64_t*)(o+504));break;                      /* written in out's unused tail */
   case 14:s=dong_call_emit(m,64,it,4,m+60,32,w);break;                                    /* out overlaps module tail */
   case 15:s=dong_call_emit(m,4,it,64,it+63,8,w);break;                                    /* out overlaps item tail */
   case 16:s=dong_call_emit(m,0,it,4,NULL,0,w);break;                                      /* empty module, capacity 0 */
   case 17:s=dong_call_emit(m,4,it,0,o,512,w);break;                                       /* empty item */
   case 18:s=dong_call_emit(m,65,it,4,NULL,0,w);break;                                     /* 65-byte module, capacity 0 */
   case 19:s=dong_call_emit(m,4,it,65,o,512,w);break;                                      /* 65-byte item */
   default:s=dong_call_emit(m,4,it,4,o,512,(uint64_t*)(o+8));break;                        /* written on out prefix */
  }
  if(s!=1||memcmp(saved,arena,sizeof(arena))){fprintf(stderr,"invalid preflight %u status %u\n",i,(unsigned)s);exit(93);}
 }
 return total;
}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 uint64_t preflights=invalid(),count;read_exact(&count,8);write_exact(&preflights,8);
 while(count--){
  uint64_t h[5];read_exact(h,sizeof(h));uint64_t nm=h[0],ni=h[1],cap=h[2],share=h[3],ro=h[4];
  if(nm>200||ni>200||cap>4096)exit(94);
  uint8_t*in=malloc(nm+ni+96),*copy=malloc(nm+ni+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,nm+ni+96);read_exact(in+32,nm);read_exact(in+64+nm,ni);memcpy(copy,in+32,nm);memcpy(copy+nm,in+64+nm,ni);
  const uint8_t*m=in+32,*it=in+64+nm;uint8_t*page=NULL;uint64_t pages=4096*2;
  if(share){it=m+share-1;}                   /* item shares the module bytes (overlapping read-only inputs) */
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,nm+ni);ro_protect(page,pages);
   m=page;it=share?page+share-1:page+nm;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_call_emit(nm?m:NULL,nm,ni?it:NULL,ni,cap?out+32:NULL,cap,written);
  uint64_t valid=!memcmp(copy,m,nm)&&(share||!memcmp(copy+nm,it,ni))&&(ro||(filled(in,32)&&filled(in+32+nm,32)&&filled(in+64+nm+ni,32)))&&
    filled(out,32)&&filled(out+32+cap,32)&&filled(meta,8)&&filled(meta+2,8);
  if(s)valid=valid&&filled(out+32,cap)&&filled(written,8);
  else valid=valid&&*written<=cap&&filled(out+32+*written,cap-*written);
  uint64_t response[3]={s,valid,s?0:*written};write_exact(response,24);write_exact(out+32,s?0:*written);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''
NATIVE_MAIN=r'''
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  uint64_t io[5]={0xa5a5a5a5a5a5a5a5ull,0x0123456789abc000ull+i,0,0,0xa5a5a5a5a5a5a5a5ull};
  table[i](io+1);
  if(io[0]!=0xa5a5a5a5a5a5a5a5ull||io[4]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  if(fwrite(io+1,8,3,stdout)!=3)exit(92);
 }return 0;
}
'''


def symbol(module,item):
    """Independent CR3 expectation: __dong_m<hex module>_n<hex item>, two lowercase digits per byte."""
    return '__dong_m'+module.hex()+'_n'+item.hex()


def expected_text(module,item):
    return ('call '+symbol(module,item)+'\n').encode()


NAMES=[(b'm',b'f'),(b'core',b'main'),(b'a',b'bc'),(b'ab',b'c'),(b'\x00',b'\x00\x01'),(b'\xe4\xb8\xad\xe6\x96\x87',b'\xff\xfe'),
       (b'x'*64,b'y'*64),(b'pkg.sub',b'fn-name!'),(b'\n\r\t',b' "q"'),(bytes(range(1,65)),b'z'),(b'z',bytes(range(192,256)))]


class NasmDirectCallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C25'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
        (cls.work/'probe.c').write_text(HARNESS,encoding='utf-8');cls.records=[]
        cls.inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE,DEPENDENCY,Path(__file__)]}
        cls.native='win64'if os.name=='nt'else'elf64'
        cls.executables=cls.build_all('good',SOURCE.read_text(encoding='utf-8'))

    @classmethod
    def command(cls,cmd,name):
        r=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120)
        (cls.work/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
        if r.returncode:raise AssertionError((name,r.returncode,r.stdout,r.stderr))

    @classmethod
    def build_all(cls,name,text):
        """Stage only this component and the integrated CR3 module, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_direct_call.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(DEPENDENCY,root/'bootstrap/nasm_symbol.dg')
        (root/'probe/call_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/call_export.dg',roots=[root],mode=mode)
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
        """cases: (module,item,cap,share,readonly,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for m,it,cap,share,ro,_ in cases:
            payload.extend(struct.pack('<5Q',len(m),len(it),cap,share,ro));payload.extend(m+it)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],21)
        offset=8;texts=[]
        for index,case in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,case[5],(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,texts,pairs,label):
        """Call through each emitted line from an aligned SysV probe into independently defined callees."""
        stub=['bits 64','section .text'];defined=set()
        def callee(name,marker):
            if name in defined:return []
            defined.add(name)
            # Returns rdi+marker in rax and the callee-entry rsp&15 in rdx (8 when the call site was 16-aligned).
            return [name+':','mov rax, %d'%marker,'add rax, rdi','mov rdx, rsp','and rdx, 15','ret']
        for i,(text,(m,it)) in enumerate(zip(texts,pairs)):
            stub+=['global v%d'%i,'v%d:'%i,'push rbx','mov rbx, rdi','mov rdi, [rbx]',
                   text.decode('ascii').rstrip('\n'),'mov [rbx+8], rax','mov [rbx+16], rdx','pop rbx','ret']
            stub+=callee(symbol(m,it),0x1000+i)
            stub+=callee(symbol(it,m),0x7000+i)          # a different, defined decoy target (swapped names)
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            target=self.work/(label+'.stubs.'+fmt+'.o')
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',target,self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join('extern void ABI v%d(uint64_t*);'%i for i in range(len(texts))))
        main=main.replace('%TABLE%',','.join('v%d'%i for i in range(len(texts))))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for i in range(len(texts)):
            param,ret,alignment=struct.unpack_from('<3Q',run.stdout,24*i)
            self.assertEqual(param,0x0123456789abc000+i,(label,i,'native parameter slot'))
            self.assertEqual(ret,param+0x1000+i,(label,i,'native callee return',pairs[i]))
            self.assertEqual(alignment,8,(label,i,'native stack alignment'))

    def test_exact_text_capacity_and_read_only_inputs(self):
        cases=[]
        for k,(m,it) in enumerate(NAMES):
            n=len(expected_text(m,it))
            cases+=[(m,it,n,0,k%3==0,OK),(m,it,n+9,0,0,OK),(m,it,n-1,0,0,CAPACITY),(m,it,0,0,1,CAPACITY)]
        cases+=[(b'abcd',b'cd',64,3,0,OK),(b'abcd',b'abcd',64,1,1,OK),(b'q'*64,b'q'*64,300,1,1,OK)]   # inputs sharing bytes
        cases+=[(b'',b'f',64,0,0,INVALID),(b'm',b'',64,0,0,INVALID),(b'm'*65,b'f',64,0,1,INVALID),(b'm',b'f'*65,0,0,0,INVALID),
                (b'',b'',0,0,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (m,it,cap,share,ro,status),text in zip(cases,texts):
                if status==OK:
                    item=m[share-1:share-1+len(it)]if share else it
                    self.assertEqual(text,expected_text(m,item),(mode,m,it))
        self.records.append(dict(test='exact-text-capacity-readonly',cases=len(cases),preflights_per_native=21,modes=2,passed=True))

    def test_native_calls_reach_the_encoded_callee(self):
        for mode,exe in self.executables.items():
            texts=self.emit(exe,[(m,it,300,0,0,OK)for m,it in NAMES],'calls-'+mode)
            self.native_run(texts,NAMES,'native-'+mode)
        self.records.append(dict(test='native-direct-calls',calls_per_mode=len(NAMES),formats_assembled=['elf64','win64'],modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        # Encodes the names swapped: a valid, defined decoy symbol that returns a different marker.
        old='let status=sym.encode(module_name,item_name,';new='let status=sym.encode(item_name,module_name,'
        self.assertEqual(source.count(old),1)
        pairs=[p for p in NAMES if p[0]!=p[1]]
        for mode,exe in self.executables.items():
            self.native_run(self.emit(exe,[(m,it,300,0,0,OK)for m,it in pairs],'bad-target-good-'+mode),pairs,'bad-target-good-'+mode)
        for mode,exe in self.build_all('bad-target',source.replace(old,new,1)).items():
            texts=self.emit(exe,[(m,it,300,0,0,OK)for m,it in pairs],'bad-target-'+mode)
            with self.assertRaisesRegex(AssertionError,'native callee return'):self.native_run(texts,pairs,'bad-target-'+mode)
        self.records.append(dict(test='bad-target',compiled=True,native_executed=True,modes=2,rejected_by='native callee return'))
        old='if total>on{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='if total>on{if on!=0{out[0]=99;}return CAPACITY;}'
        case=[(b'core',b'main',8,0,0,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
