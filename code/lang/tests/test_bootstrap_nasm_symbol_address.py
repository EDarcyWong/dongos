"""Actual Dong NASM RIP-relative symbol-address emitter: exact CR3 text, dual-format assembly, native address checks."""
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

ROOT=Path(__file__).resolve().parents[2]
WORKS=ROOT
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

SOURCE=ROOT/'lang/bootstrap/nasm_symbol_address.dg'
DEPENDENCY=ROOT/'lang/bootstrap/nasm_symbol.dg'      # integrated CR3, staged read-only
OK,INVALID,CAPACITY=0,1,2
NAMES=['rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi']+['r%d'%i for i in range(8,16)]
SAFE=[0,1,2,6,8,9,10,11]          # caller-saved registers the native stubs may load/clobber (rdi holds the state pointer)
ARITH_FLAGS=0x8d5
WRAPPER='''module probe.addr_export;
import bootstrap.nasm_symbol_address as a;
export("dong_addr_emit") pub unsafe fn emit(destination:u64,module_name:*const u8,nm:usize,item_name:*const u8,ni:usize,
 out:*u8,no:usize,written:*usize)u64{unsafe{
 return a.emit(destination,slice_from_raw_parts(module_name,nm),slice_from_raw_parts(item_name,ni),slice_from_raw_parts(out,no),written);
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
extern uint64_t ABI dong_addr_emit(uint64_t,const uint8_t*,uint64_t,const uint8_t*,uint64_t,uint8_t*,uint64_t,uint64_t*);
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
#define FAKE(x) ((const uint8_t*)(uintptr_t)(x))
/* Each preflight keeps every other field valid (names 1..64 bytes, aligned written) so only the target check can reject. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[2048],saved[2048];const unsigned total=22;
 uint8_t*m=arena+64,*it=arena+192,*o=arena+512;uint64_t*w=(uint64_t*)(arena+1536);
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));memcpy(saved,arena,sizeof(arena));uint64_t s=0;
  switch(i){
   case 0:s=dong_addr_emit(0,m,4,it,4,o,512,NULL);break;                                     /* written NULL */
   case 1:s=dong_addr_emit(0,m,4,it,4,o,512,(uint64_t*)(arena+1537));break;                  /* written odd */
   case 2:s=dong_addr_emit(0,m,4,it,4,NULL,0,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;    /* written end overflow, empty out */
   case 3:s=dong_addr_emit(0,m,4,it,4,(uint8_t*)(uintptr_t)(UINT64_MAX-15),16,w);break;      /* out end overflow */
   case 4:s=dong_addr_emit(0,m,4,it,4,NULL,512,w);break;                                     /* NULL non-empty out */
   case 5:s=dong_addr_emit(0,NULL,4,it,4,o,512,w);break;                                     /* NULL non-empty module */
   case 6:s=dong_addr_emit(0,m,4,NULL,4,o,512,w);break;                                      /* NULL non-empty item */
   case 7:s=dong_addr_emit(0,FAKE(UINT64_MAX-3),8,it,4,o,512,w);break;                       /* module end overflow */
   case 8:s=dong_addr_emit(0,m,4,FAKE(UINT64_MAX-1),4,o,512,w);break;                        /* item end overflow */
   case 9:s=dong_addr_emit(0,m,64,it,4,o,512,(uint64_t*)m);break;                            /* written on module's aligned prefix */
   case 10:s=dong_addr_emit(0,m,64,it,4,o,512,(uint64_t*)(m+56));break;                      /* written in module's declared tail */
   case 11:s=dong_addr_emit(0,m,4,it,64,o,512,(uint64_t*)it);break;                          /* written on item prefix */
   case 12:s=dong_addr_emit(0,m,4,it,64,o,512,(uint64_t*)(it+56));break;                     /* written in item's declared tail */
   case 13:s=dong_addr_emit(0,m,4,it,4,o,512,(uint64_t*)(o+504));break;                      /* written in out's unused tail */
   case 14:s=dong_addr_emit(0,m,64,it,4,m+60,32,w);break;                                    /* out overlaps module tail */
   case 15:s=dong_addr_emit(0,m,4,it,64,it+63,8,w);break;                                    /* out overlaps item tail */
   case 16:s=dong_addr_emit(0,m,0,it,4,NULL,0,w);break;                                      /* empty module, capacity 0 */
   case 17:s=dong_addr_emit(0,m,4,it,0,o,512,w);break;                                       /* empty item */
   case 18:s=dong_addr_emit(0,m,65,it,4,NULL,0,w);break;                                     /* 65-byte module, capacity 0 */
   case 19:s=dong_addr_emit(0,m,4,it,65,o,512,w);break;                                      /* 65-byte item */
   case 20:s=dong_addr_emit(16,m,4,it,4,NULL,0,w);break;                                     /* bad destination, capacity 0 */
   default:s=dong_addr_emit(UINT64_MAX,m,4,it,4,o,512,w);break;                              /* bad destination */
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
  uint64_t h[6];read_exact(h,sizeof(h));uint64_t dest=h[0],nm=h[1],ni=h[2],cap=h[3],share=h[4],ro=h[5];
  if(nm>200||ni>200||cap>4096)exit(94);
  uint8_t*in=malloc(nm+ni+96),*copy=malloc(nm+ni+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  memset(in,0xa5,nm+ni+96);read_exact(in+32,nm);read_exact(in+64+nm,ni);memcpy(copy,in+32,nm);memcpy(copy+nm,in+64+nm,ni);
  const uint8_t*m=in+32,*it=in+64+nm;uint8_t*page=NULL;uint64_t pages=4096*2,protected_ok=1;
  if(share){it=m+share-1;}
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,copy,nm+ni);protected_ok=ro_protect(page,pages);
   m=page;it=share?page+share-1:page+nm;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));uint64_t*written=meta+1;
  uint64_t s=dong_addr_emit(dest,nm?m:NULL,nm,ni?it:NULL,ni,cap?out+32:NULL,cap,written);
  uint64_t valid=protected_ok&&!memcmp(copy,m,nm)&&(share||!memcmp(copy+nm,it,ni))&&(ro||(filled(in,32)&&filled(in+32+nm,32)&&filled(in+64+nm+ni,32)))&&
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
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void ABI (*stub)(uint64_t*);
%DECLS%
static const stub table[]={%TABLE%};
static const uint64_t*const symbols[]={%SYMBOLS%};
static void read_exact(void*p,uint64_t n){if(n&&fread(p,1,n,stdin)!=n)exit(91);}
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 for(unsigned i=0;i<sizeof(table)/sizeof(table[0]);i++){
  /* [0..7] safe registers, [8] RFLAGS before, [9] RFLAGS after, [10] independent symbol address,
     [11..13] guard-before, data, guard-after read through the C address after the stub ran */
  uint64_t state[16];read_exact(state+1,64);state[9]=state[10]=0;state[0]=state[15]=0xa5a5a5a5a5a5a5a5ull;
  table[i](state+1);
  if(state[0]!=0xa5a5a5a5a5a5a5a5ull||state[15]!=0xa5a5a5a5a5a5a5a5ull)exit(96);
  const uint64_t*p=symbols[i];state[11]=(uint64_t)(uintptr_t)p;state[12]=p[-1];state[13]=p[0];state[14]=p[1];
  if(fwrite(state+1,8,14,stdout)!=14)exit(92);
 }return 0;
}
'''


def symbol(module,item):
    """Independent CR3 expectation: __dong_m<hex module>_n<hex item>, two lowercase digits per byte."""
    return '__dong_m'+module.hex()+'_n'+item.hex()


def expected_text(d,module,item):
    return ('lea %s, [rel %s]\n'%(NAMES[d],symbol(module,item))).encode()


PAIRS=[(b'm',b'f'),(b'core',b'main'),(b'a',b'bc'),(b'ab',b'c'),(b'\x00',b'\x00\x01'),(b'\xe4\xb8\xad\xe6\x96\x87',b'\xff\xfe'),
       (b'x'*64,b'y'*64),(b'pkg.sub',b'fn-name!'),(b'\n\r\t',b' "q"'),(bytes(range(1,65)),b'z'),(b'z',bytes(range(192,256)))]
GUARD_BEFORE,GUARD_AFTER=0x6b6b6b6b6b6b6b6b,0x7c7c7c7c7c7c7c7c


class NasmSymbolAddressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=ROOT/'build/test/bootstrap-components/C29'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        (root/'bootstrap/nasm_symbol_address.dg').write_text(text,encoding='utf-8')
        shutil.copyfile(DEPENDENCY,root/'bootstrap/nasm_symbol.dg')
        (root/'probe/addr_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/addr_export.dg',roots=[root],mode=mode)
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
        """cases: (dest,module,item,cap,share,readonly,expected_status). Guards are asserted per call before results are used."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for d,m,it,cap,share,ro,_ in cases:
            payload.extend(struct.pack('<6Q',d,len(m),len(it),cap,share,ro));payload.extend(m+it)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],22)
        offset=8;texts=[]
        for index,case in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,case[6],(label,index,'status'))
            texts.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return texts

    def native_run(self,texts,vectors,label):
        """Each symbol is independently defined as 8 bytes of read-only data between two guards; the destination register
        must hold exactly the symbol's address as taken by C, while other registers and the arithmetic flags stay unchanged."""
        stub=['bits 64','%ifidn __OUTPUT_FORMAT__, win64','section .rdata rdata align=8','%else','section .rodata align=8','%endif']
        for i,(d,(m,it)) in enumerate(vectors):
            stub+=['dq %d'%GUARD_BEFORE,'global %s'%symbol(m,it),'%s:'%symbol(m,it),'dq %d'%(0x5100000000000000+i),'dq %d'%GUARD_AFTER]
        stub.append('section .text')
        for i,text in enumerate(texts):
            stub+=['global v%d'%i,'v%d:'%i]+['mov %s, [rdi+%d]'%(NAMES[r],8*k)for k,r in enumerate(SAFE)]
            stub+=['pushfq','pop qword [rdi+64]',text.decode('ascii').rstrip('\n'),'pushfq','pop qword [rdi+72]']
            stub+=['mov [rdi+%d], %s'%(8*k,NAMES[r])for k,r in enumerate(SAFE)]+['ret']
        (self.work/(label+'.stubs.asm')).write_text('\n'.join(stub)+'\n',encoding='ascii')
        for fmt in ('elf64','win64'):
            self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/(label+'.stubs.'+fmt+'.o'),self.work/(label+'.stubs.asm')],label+'-stubs-'+fmt)
        decls=['extern void ABI v%d(uint64_t*);'%i for i in range(len(texts))]
        decls+=['extern const uint64_t %s[];'%symbol(m,it)for _,(m,it) in vectors]
        main=NATIVE_MAIN.replace('%DECLS%','\n'.join(decls)).replace('%TABLE%',','.join('v%d'%i for i in range(len(texts))))
        main=main.replace('%SYMBOLS%',','.join(symbol(m,it)for _,(m,it) in vectors))
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',self.work/(label+'.native.c'),self.work/(label+'.stubs.'+self.native+'.o'),'-o',exe],label+'-native-link')
        payload=bytearray();initial=[]
        for i,(d,_) in enumerate(vectors):
            state=[0x1111111111111111*(j+1)for j in range(8)];initial.append(state)
            payload.extend(struct.pack('<8Q',*state))
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.native.output')).write_bytes(run.stdout)
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        for i,(d,pair) in enumerate(vectors):
            got=list(struct.unpack_from('<14Q',run.stdout,112*i));address=got[10]
            self.assertEqual(got[11:14],[GUARD_BEFORE,0x5100000000000000+i,GUARD_AFTER],(label,i,'native data and guards'))
            self.assertEqual(got[8]&ARITH_FLAGS,got[9]&ARITH_FLAGS,(label,i,'native flags preserved'))
            want=list(initial[i]);want[SAFE.index(d)]=address
            self.assertEqual(got[SAFE.index(d)],address,(label,i,'native address',NAMES[d],pair))
            self.assertEqual(got[:8],want,(label,i,'native other registers'))

    def test_exact_text_capacity_and_read_only_inputs(self):
        cases=[]
        for k,(m,it) in enumerate(PAIRS):
            for d in (k%16,(k+5)%16,(k+11)%16):
                n=len(expected_text(d,m,it))
                cases+=[(d,m,it,n,0,k%3==0,OK),(d,m,it,n+9,0,0,OK),(d,m,it,n-1,0,0,CAPACITY)]
            cases.append((k%16,m,it,0,0,1,CAPACITY))
        cases+=[(3,b'abcd',b'cd',300,3,0,OK),(9,b'abcd',b'abcd',300,1,1,OK),(15,b'q'*64,b'q'*64,300,1,1,OK)]
        cases+=[(0,b'',b'f',300,0,0,INVALID),(0,b'm',b'',300,0,0,INVALID),(0,b'm'*65,b'f',300,0,1,INVALID),(0,b'm',b'f'*65,0,0,0,INVALID),
                (16,b'm',b'f',300,0,0,INVALID),(16,b'm',b'f',0,0,1,INVALID),(2**64-1,b'm',b'f',300,0,0,INVALID)]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'text-'+mode)
            for (d,m,it,cap,share,ro,status),text in zip(cases,texts):
                if status==OK:
                    item=m[share-1:share-1+len(it)]if share else it
                    self.assertEqual(text,expected_text(d,m,item),(mode,d,m,it))
        self.records.append(dict(test='exact-text-capacity-readonly',cases=len(cases),preflights_per_native=22,modes=2,passed=True))

    def test_all_sixteen_destinations_assemble_in_both_formats(self):
        cases=[(d,m,it,300,0,0,OK)for d in range(16)for m,it in PAIRS[d%len(PAIRS):d%len(PAIRS)+1]]
        for mode,exe in self.executables.items():
            texts=self.emit(exe,cases,'asm-'+mode)
            defs=sorted({symbol(m,it)for _,m,it,_,_,_,_ in cases})
            source=self.work/('all-registers-'+mode+'.asm')
            source.write_bytes(b'bits 64\nsection .text\n'+b''.join(texts)+b''.join(('%s:\ndq 0\n'%s).encode()for s in defs))
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',self.work/('all-registers-%s.%s.o'%(mode,fmt)),source],'all-registers-%s-%s'%(mode,fmt))
        self.records.append(dict(test='all-destinations-assemble',lines=len(cases),formats=['elf64','win64'],modes=2,passed=True))

    def vectors(self):
        return [(SAFE[i%len(SAFE)],pair)for i,pair in enumerate(PAIRS)]

    def test_native_lea_returns_the_independent_symbol_address(self):
        vectors=self.vectors()
        for mode,exe in self.executables.items():
            texts=self.emit(exe,[(d,m,it,300,0,0,OK)for d,(m,it) in vectors],'addr-'+mode)
            self.native_run(texts,vectors,'native-'+mode)
        self.records.append(dict(test='native-rip-address',vectors_per_mode=len(vectors),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8')
        # mov keeps a valid [rel symbol] operand but loads the 8 data bytes instead of the address.
        old='var at=copy(buffer,0,"lea ");';new='var at=copy(buffer,0,"mov ");';self.assertEqual(source.count(old),1)
        vectors=self.vectors()
        for mode,exe in self.executables.items():
            self.native_run(self.emit(exe,[(d,m,it,300,0,0,OK)for d,(m,it) in vectors],'bad-mov-good-'+mode),vectors,'bad-mov-good-'+mode)
        for mode,exe in self.build_all('bad-lea-as-mov',source.replace(old,new,1)).items():
            texts=self.emit(exe,[(d,m,it,300,0,0,OK)for d,(m,it) in vectors],'bad-mov-'+mode)
            with self.assertRaisesRegex(AssertionError,'native address'):self.native_run(texts,vectors,'bad-mov-'+mode)
        self.records.append(dict(test='bad-lea-as-mov',compiled=True,native_executed=True,modes=2,rejected_by='native address'))
        old='if at>on{return CAPACITY;}';self.assertEqual(source.count(old),1)
        new='if at>on{if on!=0{out[0]=108;}return CAPACITY;}'
        case=[(2,b'core',b'main',8,0,0,CAPACITY)]
        for mode,exe in self.executables.items():self.emit(exe,case,'bad-early-out-good-'+mode)
        for mode,exe in self.build_all('bad-early-out',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.emit(exe,case,'bad-early-out-'+mode)
        self.records.append(dict(test='bad-early-out',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
