"""Actual Dong static symbol pointer datum emitter (CR3 + CR4): exact text, ELF64/COFF 64-bit relocations, native link."""
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

SOURCE=WORKS/'claude-works/src/bootstrap/nasm_symbol_pointer_data.dg'
DEPENDENCIES=[ROOT/'lang/bootstrap'/n for n in ('nasm_symbol.dg','decimal_integer.dg')]  # CR3, CR4
OK,INVALID,CAPACITY=0,1,2
U64=2**64-1
MIN,MAX=-2**63,2**63-1
PREFLIGHTS=23
NEIGHBOUR_BEFORE,NEIGHBOUR_AFTER=0x0bef0bef0bef0bef,0x0af70af70af70af7
WRAPPER='''module probe.pointer_export;
import bootstrap.nasm_symbol_pointer_data as p;
export("dong_pointer_emit") pub unsafe fn emit(a:*const u8,na:usize,b:*const u8,nb:usize,c:*const u8,nc:usize,d:*const u8,nd:usize,addend:i64,out:*u8,nout:usize,written:*usize)u64{unsafe{
 return p.emit(slice_from_raw_parts(a,na),slice_from_raw_parts(b,nb),slice_from_raw_parts(c,nc),slice_from_raw_parts(d,nd),addend,slice_from_raw_parts(out,nout),written);
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
extern uint64_t ABI dong_pointer_emit(const uint8_t*,uint64_t,const uint8_t*,uint64_t,const uint8_t*,uint64_t,const uint8_t*,uint64_t,int64_t,uint8_t*,uint64_t,uint64_t*);
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
/* Each preflight keeps every other field valid (names "a","b","c","d", addend -8) so only the target check can reject it. */
static unsigned invalid(void){
 static _Alignas(16) uint8_t arena[4096],saved[4096];const unsigned total=23;
 for(unsigned i=0;i<total;i++){
  memset(arena,0xa5,sizeof(arena));for(unsigned j=0;j<4;j++)arena[64*j]=(uint8_t)('a'+j);memcpy(saved,arena,sizeof(arena));
  const uint8_t*p[4]={arena,arena+64,arena+128,arena+192};uint64_t l[4]={1,1,1,1};
  uint8_t*o=arena+1024;uint64_t ol=1024;uint64_t*w=(uint64_t*)(arena+3584);
  if(i==0)w=NULL;                                                   /* written NULL */
  else if(i==1)w=(uint64_t*)(arena+3585);                           /* written odd */
  else if(i==2){w=(uint64_t*)(uintptr_t)(UINT64_MAX-7);o=NULL;ol=0;} /* written end overflow, legal empty out */
  else if(i==3)o=(uint8_t*)(uintptr_t)(UINT64_MAX-15);              /* out end overflow (length 1024) */
  else if(i==4)o=NULL;                                              /* NULL non-empty out */
  else if(i<9)p[i-5]=NULL;                                          /* each name: NULL non-empty */
  else if(i<13){p[i-9]=FAKE(UINT64_MAX-1);l[i-9]=4;}                /* each name: end overflow */
  else if(i<17)w=(uint64_t*)(uintptr_t)p[i-13];                     /* written on each name */
  else if(i<21){o=arena+64*(i-17);ol=8;}                            /* out over each name */
  else if(i==21)w=(uint64_t*)o;                                     /* written on out prefix */
  else w=(uint64_t*)(o+1016);                                       /* written in out's unused tail */
  uint64_t s=dong_pointer_emit(p[0],l[0],p[1],l[1],p[2],l[2],p[3],l[3],-8,o,ol,w);
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
  uint64_t h[12];read_exact(h,sizeof(h));uint64_t pool=h[0],cap=h[10],ro=h[11];int64_t addend=(int64_t)h[9];
  if(pool>1024||cap>8192)exit(94);
  uint8_t*in=malloc(pool+64),*copy=malloc(pool+1),*out=malloc(cap+64);uint64_t meta[3];
  if(!in||!copy||!out)exit(95);
  read_exact(in,pool);memcpy(copy,in,pool);const uint8_t*base=in;uint8_t*page=NULL;uint64_t pages=4096,protected_ok=1;
  for(unsigned j=0;j<4;j++)if(h[1+2*j]+h[2+2*j]>pool)exit(94);
  if(ro){page=ro_alloc(pages);if(!page)exit(95);memcpy(page,in,pool);protected_ok=ro_protect(page,pages);base=page;}
  memset(out,0xa5,cap+64);memset(meta,0xa5,sizeof(meta));
  uint64_t s=dong_pointer_emit(base+h[1],h[2],base+h[3],h[4],base+h[5],h[6],base+h[7],h[8],addend,cap?out+32:NULL,cap,meta+1);
  uint64_t w=s?0:meta[1];
  uint64_t valid=protected_ok&&filled(meta,8)&&filled(meta+2,8)&&!memcmp(copy,base,pool)&&filled(out,32)&&filled(out+32+cap,32);
  if(s)valid=valid&&filled(meta+1,8)&&filled(out+32,cap);else valid=valid&&w<=cap&&filled(out+32+w,cap-w);
  uint64_t response[3]={s,valid,w};write_exact(response,24);write_exact(out+32,w);
  if(page)ro_free(page,pages);
  free(in);free(copy);free(out);
 }return 0;
}
'''


def symbol(module,item):return '__dong_m'+module.hex()+'_n'+item.hex()


def expected_text(sm,si,tm,ti,addend):
    tail='' if addend==0 else (' + %d'%addend if addend>0 else ' - %d'%-addend)
    return ('%s:\ndq %s%s\n'%(symbol(sm,si),symbol(tm,ti),tail)).encode()


def pooled(names):
    """Separate names in one pool: (pool, [(offset, length)]*4)."""
    pool=b'';spans=[]
    for n in names:spans.append((len(pool),len(n)));pool+=n+b'\x00'*(8-len(n)%8)
    return pool,spans


L64=[bytes(range(64)),bytes(range(64,128)),bytes(range(128,192)),bytes([0xff-i for i in range(64)])]
TARGET=(b'mod',b'target');NEAR=(b'mod',b'array')
# (storage module, storage item, target module, target item, addend)
VECTORS=[(b'mod',b'p0',*TARGET,0),(b'mod',b'p1',*TARGET,1),(b'mod',b'pm1',*TARGET,-1),(b'mod',b'p8',*NEAR,8),(b'mod',b'pm8',*NEAR,-8),
         (b'mod',b'pmin',*TARGET,MIN),(b'mod',b'pmax',*TARGET,MAX),(L64[0],L64[1],L64[2],L64[3],MIN),
         (b'\x00',b'\xff\x80',b'\x00\x01',b'z',-123456789),(b'self',b'ptr',b'self',b'ptr',0),(b'self',b'ptr16',b'self',b'ptr16',16),
         (L64[3],L64[2],L64[3],L64[2],MAX),(L64[1],L64[0],*NEAR,8)]
DEREF={3:NEIGHBOUR_AFTER,4:NEIGHBOUR_BEFORE,12:NEIGHBOUR_AFTER}


def data_flags(nasm):
    """-Wall makes NASM 3 warn on every 64-bit absolute relocation, which is exactly what a dq pointer datum needs; only that warning is relaxed."""
    return nasm_flags(nasm)+['-w-reloc-abs-qword']


def elf_relocations(data):
    """Independent ELF64 parse: [(section, offset, type, symbol, addend)] for every RELA section."""
    shoff,=struct.unpack_from('<Q',data,0x28);shentsize,shnum,shstrndx=struct.unpack_from('<3H',data,0x3a)
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*shentsize)for i in range(shnum)]
    def name(table,offset):
        start=sections[table][4]+offset;return data[start:data.index(b'\x00',start)].decode('latin-1')
    result=[]
    for s in sections:
        if s[1]!=4:continue                                         # SHT_RELA
        symtab=sections[s[6]];target=name(shstrndx,sections[s[7]][0])
        for k in range(s[5]//24):
            offset,info,addend=struct.unpack_from('<QQq',data,s[4]+24*k)
            st_name,=struct.unpack_from('<I',data,symtab[4]+24*(info>>32))
            result.append((target,offset,info&0xffffffff,name(symtab[6],st_name),addend))
    return result


def coff_relocations(data):
    """Independent COFF parse: [(section, offset, type, symbol, implicit 64-bit addend)]."""
    _,nsec,_,symptr,nsym,optsize,_=struct.unpack_from('<HHIIIHH',data,0)
    strings=symptr+18*nsym
    def symname(index):
        raw=data[symptr+18*index:symptr+18*index+8]
        if raw[:4]==b'\x00\x00\x00\x00':
            start=strings+struct.unpack_from('<I',raw,4)[0];return data[start:data.index(b'\x00',start)].decode('latin-1')
        return raw.rstrip(b'\x00').decode('latin-1')
    result=[]
    for i in range(nsec):
        h=struct.unpack_from('<8sIIIIIIHHI',data,20+optsize+40*i);sec=h[0].rstrip(b'\x00').decode('latin-1')
        for k in range(h[7]):
            va,index,kind=struct.unpack_from('<IIH',data,h[5]+10*k)
            result.append((sec,va,kind,symname(index),struct.unpack_from('<q',data,h[4]+va)[0]))
    return result


class NasmSymbolPointerDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm,cls.cc=tool('nasm','NASM'),tool('gcc','CC')
        if not cls.nasm or not cls.cc:raise unittest.SkipTest('native NASM emitter requires NASM/GCC')
        cls.work=WORKS/'claude-works/build/C38'/('run-'+uuid.uuid4().hex[:12]);cls.work.mkdir(parents=True)
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
        """Stage only this component and the integrated CR3/CR4 modules, then build debug/release harnesses."""
        root=cls.work/name;(root/'bootstrap').mkdir(parents=True);(root/'probe').mkdir()
        (root/'bootstrap/nasm_symbol_pointer_data.dg').write_text(text,encoding='utf-8')
        for dep in DEPENDENCIES:shutil.copyfile(dep,root/'bootstrap'/dep.name)
        (root/'probe/pointer_export.dg').write_text(WRAPPER,encoding='utf-8')
        result={}
        for mode in ('debug','release'):
            tag=name+'-'+mode;compiled=compile_file(root/'probe/pointer_export.dg',roots=[root],mode=mode)
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
            records=cls.records,integrated=False,OS_VM_built=False,ELF64_executed=False),indent=2)+'\n')

    def run_cases(self,exe,cases,label):
        """cases: (pool, [(offset,len)]*4, addend, cap, readonly, status). Returns the emitted text (None on failure)."""
        payload=bytearray(struct.pack('<Q',len(cases)))
        for pool,spans,addend,cap,ro,_ in cases:
            payload.extend(struct.pack('<9Q',len(pool),*[x for s in spans for x in s]))
            payload.extend(struct.pack('<qQQ',addend,cap,ro));payload.extend(pool)
        (self.work/(label+'.input')).write_bytes(payload)
        run=subprocess.run([str(exe)],input=bytes(payload),capture_output=True,timeout=60)
        (self.work/(label+'.output')).write_bytes(run.stdout);(self.work/(label+'.stderr')).write_bytes(run.stderr)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(struct.unpack_from('<Q',run.stdout,0)[0],PREFLIGHTS)
        offset=8;results=[]
        for index,c in enumerate(cases):
            got,guard,written=struct.unpack_from('<3Q',run.stdout,offset);offset+=24
            text=run.stdout[offset:offset+written];offset+=written
            self.assertEqual(guard,1,(label,index,'guard/atomicity'))
            self.assertEqual(got,c[-1],(label,index,'status',c[2:4]))
            results.append(text if got==OK else None)
        self.assertEqual(offset,len(run.stdout))
        return results

    def texts(self,exe,vectors,label):
        return self.run_cases(exe,[(*pooled(v[:4]),v[4],1024,0,OK)for v in vectors],label)

    def objects(self,texts,vectors,label):
        """Each extern-target datum assembled alone after a guard qword: one 64-bit relocation at offset 8 with the addend."""
        for k,(text,v) in enumerate(zip(texts,vectors)):
            target=symbol(*v[2:4])
            if target==symbol(*v[:2]):continue                     # self pointer: checked by the native link instead
            source=self.work/('%s-%d.asm'%(label,k));source.write_bytes(('bits 64\nextern %s\nsection .data\ndq 0x1234\n'%target).encode()+text)
            for fmt in ('elf64','win64'):
                obj=self.work/('%s-%d.%s.o'%(label,k,fmt))
                self.command([self.nasm,'-f',fmt,*data_flags(self.nasm),'-o',obj,source],'%s-%d-%s'%(label,k,fmt))
                relocs=(elf_relocations if fmt=='elf64'else coff_relocations)(obj.read_bytes())
                want=('.data',8,1,target,v[4])                     # R_X86_64_64 / IMAGE_REL_AMD64_ADDR64, explicit / implicit addend
                self.assertEqual(relocs,[want],(label,k,fmt,'object 64-bit relocation'))

    def native_run(self,texts,vectors,label):
        """Link every datum into the data section with real targets; C reports each stored u64 and target address."""
        storages={symbol(*v[:2])for v in vectors}
        targets=sorted({symbol(*v[2:4])for v in vectors}-storages)
        data=['bits 64','section .data']
        for t in targets:data+=['align 8','global %s'%t,'dq 0x%x'%NEIGHBOUR_BEFORE,'%s:'%t,'dq 0x5157505157505157','dq 0x%x'%NEIGHBOUR_AFTER]
        (self.work/(label+'.targets.asm')).write_text('\n'.join(data)+'\n',encoding='ascii')
        lines=('bits 64\n'+''.join('extern %s\n'%t for t in targets)+'section .data\n').encode()
        for v,text in zip(vectors,texts):lines+=('align 8\nglobal %s\n'%symbol(*v[:2])).encode()+text
        (self.work/(label+'.data.asm')).write_bytes(lines)
        objects=[]
        for part in ('targets','data'):
            for fmt in ('elf64','win64'):
                obj=self.work/('%s.%s.%s.o'%(label,part,fmt))
                self.command([self.nasm,'-f',fmt,*data_flags(self.nasm),'-o',obj,self.work/('%s.%s.asm'%(label,part))],'%s-%s-%s'%(label,part,fmt))
            objects.append(self.work/('%s.%s.%s.o'%(label,part,self.native)))
        decls=['extern const uint64_t %s[];'%s for s in sorted(storages)]+['extern const uint64_t %s[];'%t for t in targets]
        rows=[]
        for k,v in enumerate(vectors):
            s,t=symbol(*v[:2]),symbol(*v[2:4])
            deref='*(const uint64_t*)(uintptr_t)%s[0]'%s if k in DEREF else '0'
            rows.append('{%s[0],(uint64_t)(uintptr_t)%s,%s}'%(s,t,deref))
        main='#include <stdint.h>\n#include <stdio.h>\n'+'\n'.join(decls)+'\nint main(void){\n const uint64_t rows[][3]={'+','.join(rows)+'};\n'
        main+=' for(unsigned i=0;i<sizeof(rows)/sizeof(rows[0]);i++)printf("%016llx %016llx %016llx\\n",(unsigned long long)rows[i][0],(unsigned long long)rows[i][1],(unsigned long long)rows[i][2]);\n return 0;\n}\n'
        (self.work/(label+'.native.c')).write_text(main,encoding='utf-8')
        exe=self.work/(label+'-native'+('.exe'if os.name=='nt'else''))
        self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Wno-format','-Werror',self.work/(label+'.native.c'),*objects,'-o',exe],label+'-native-link')
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
        (self.work/(label+'.native.output')).write_text(run.stdout,encoding='utf-8')
        self.assertEqual(run.returncode,0,(label,'native exit',run.stderr))
        rows=[[int(x,16)for x in line.split()]for line in run.stdout.split('\n')if line]
        self.assertEqual(len(rows),len(vectors))
        for k,(v,(stored,address,deref)) in enumerate(zip(vectors,rows)):
            self.assertEqual(stored,(address+v[4])&U64,(label,k,v[4],'native pointer value'))
            if k in DEREF:self.assertEqual(deref,DEREF[k],(label,k,'native neighbour through pointer'))

    def test_exact_text_capacity_and_invalid(self):
        cases=[]
        for k,v in enumerate(VECTORS):
            pool,spans=pooled(v[:4]);n=len(expected_text(*v))
            cases+=[(pool,spans,v[4],n,int(k%2==0),OK),(pool,spans,v[4],n+13,0,OK),(pool,spans,v[4],n-1,0,CAPACITY),(pool,spans,v[4],0,0,CAPACITY)]
        for addend in (MIN,MAX):
            pool,spans=pooled(L64);n=len(expected_text(*L64,addend));self.assertEqual(n,560)
            cases+=[(pool,spans,addend,560,1,OK),(pool,spans,addend,559,0,CAPACITY),(pool,spans,addend,0,1,CAPACITY)]
        # Overlapping read-only names: storage == target sharing bytes, item a suffix of module.
        shared=b'shared-module-name';spans=[(0,len(shared)),(7,6),(0,len(shared)),(7,6)]
        cases+=[(shared,spans,-8,4096,1,OK),(shared,[(0,18),(0,1),(17,1),(0,18)],8,4096,1,OK)]
        for position in range(4):
            for bad in (0,65):
                names=[b'a',b'b',b'c',b'd'];names[position]=bytes(range(65))[:bad];pool,sp=pooled(names)
                cases+=[(pool,sp,1,4096,position%2,INVALID),(pool,sp,1,0,0,INVALID)]
            names=[b'a',b'b',b'c',b'd'];names[position]=bytes(range(1,2))if position%2 else bytes(range(64));pool,sp=pooled(names)
            cases+=[(pool,sp,-1,4096,0,OK)]
        for mode,exe in self.executables.items():
            results=self.run_cases(exe,cases,'text-'+mode)
            for c,text in zip(cases,results):
                if c[-1]!=OK:continue
                names=[c[0][o:o+l]for o,l in c[1]];self.assertEqual(text,expected_text(*names,c[2]),(mode,c[2]))
        self.records.append(dict(test='exact-text-capacity-invalid',cases=len(cases),preflights_per_native=PREFLIGHTS,longest_bytes=560,modes=2,passed=True))

    def test_object_relocations_are_64_bit(self):
        for mode,exe in self.executables.items():
            self.objects(self.texts(exe,VECTORS,'obj-'+mode),VECTORS,'obj-'+mode)
        self.records.append(dict(test='object-relocations',formats=['elf64 R_X86_64_64 rela addend','win64 IMAGE_REL_AMD64_ADDR64 implicit addend'],
                                 vectors=sum(1 for v in VECTORS if v[:2]!=v[2:4]),modes=2,passed=True))

    def test_native_link_stores_target_plus_addend(self):
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,VECTORS,'vectors-'+mode),VECTORS,'native-'+mode)
        self.records.append(dict(test='native-link',vectors_per_mode=len(VECTORS),dereferenced=sorted(DEREF),modes=2,passed=True))

    def test_actual_compiled_wrong_sources_are_rejected(self):
        source=SOURCE.read_text(encoding='utf-8');vectors=[VECTORS[1],VECTORS[4],VECTORS[5]]
        for mode,exe in self.executables.items():
            self.native_run(self.texts(exe,vectors,'bad-good-'+mode),vectors,'bad-good-'+mode)
        for name,old,new in [('bad-addend-zero','if addend!=0{','if false{'),
                             ('bad-addend-sign','if !put(text,&at," - ")','if !put(text,&at," + ")')]:
            self.assertEqual(source.count(old),1,name)
            for mode,exe in self.build_all(name,source.replace(old,new,1)).items():
                texts=self.texts(exe,vectors,name+'-'+mode)
                with self.assertRaisesRegex(AssertionError,'native pointer value'):self.native_run(texts,vectors,name+'-'+mode)
            self.records.append(dict(test=name,compiled=True,linked=True,native_executed=True,modes=2,rejected_by='native pointer value'))
        old='if at>on{return CAPACITY;}\n var i:usize=0;while i<at{out[i]=buffer[i];i+=1;}'
        new='if at>on{*written=at;return CAPACITY;}\n var i:usize=0;while i<at{out[i]=buffer[i];i+=1;}'
        self.assertEqual(source.count(old),1);pool,spans=pooled(VECTORS[1][:4]);case=[(pool,spans,1,20,0,CAPACITY)]
        for mode,exe in self.executables.items():self.run_cases(exe,case,'bad-early-written-good-'+mode)
        for mode,exe in self.build_all('bad-early-written',source.replace(old,new,1)).items():
            with self.assertRaisesRegex(AssertionError,'guard/atomicity'):self.run_cases(exe,case,'bad-early-written-'+mode)
        self.records.append(dict(test='bad-early-written',compiled=True,native_executed=True,modes=2,rejected_by='guard/atomicity'))


if __name__=='__main__':unittest.main()
