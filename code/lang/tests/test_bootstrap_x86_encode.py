"""Native debug/release machine-code encoder tests against an independent NASM oracle.

This assembles the actual Dong implementation and calls it from a guarded C ABI
harness. NASM supplies expected bytes, not the implementation's text backend.
"""
from pathlib import Path
import struct
import subprocess
import hashlib
import json
import uuid
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import tool

ROOT = Path(__file__).resolve().parents[2]
MASK = (1 << 64) - 1
FIELDS = 'op form width dst src base disp imm src_width cc reserved'.split()
REGS = {
    8: 'al cl dl bl spl bpl sil dil'.split() + [f'r{i}b' for i in range(8, 16)],
    16: 'ax cx dx bx sp bp si di'.split() + [f'r{i}w' for i in range(8, 16)],
    32: 'eax ecx edx ebx esp ebp esi edi'.split() + [f'r{i}d' for i in range(8, 16)],
    64: 'rax rcx rdx rbx rsp rbp rsi rdi'.split() + [f'r{i}' for i in range(8, 16)],
}
SIZE = {8: 'byte', 16: 'word', 32: 'dword', 64: 'qword'}
WRAPPER = '''module probe.x86_export;
import bootstrap.x86_encode as x;
export("dong_encode") pub unsafe fn encode(out:*u8,n:usize,ins:*const x.Instruction,written:*usize)u64{unsafe{
 return x.encode(slice_from_raw_parts(out,n),ins,written);
}}
'''
HARNESS = r'''
#define _GNU_SOURCE
#include <sys/mman.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define ABI __attribute__((sysv_abi))
typedef struct { uint64_t op,form,width,dst,src,base,disp,imm,src_width,cc,reserved; } Instruction;
_Static_assert(sizeof(Instruction)==88,"instruction ABI");
extern uint64_t ABI dong_encode(uint8_t*,uint64_t,const Instruction*,uint64_t*);
void ABI __attribute__((noreturn)) __dong_panic(uint32_t k,uint32_t l,const void*f,uint64_t n){
 fprintf(stderr,"panic %u %u %.*s\n",k,l,(int)n,(const char*)f);exit(87);
}
static void read_exact(void*p,size_t n){if(fread(p,1,n,stdin)!=n)exit(90);}
static void write_exact(const void*p,size_t n){if(fwrite(p,1,n,stdout)!=n)exit(91);}
static int filled(const void*p,size_t n){const uint8_t*s=p;while(n--)if(*s++!=0xa5)return 0;return 1;}
static void preflight(void){
 union {uint64_t align;uint8_t b[512];} a,s;
 for(unsigned i=0;i<12;i++){
  memset(a.b,0xa5,sizeof(a.b));Instruction*in=(Instruction*)(a.b+128);
  memset(in,0,sizeof(*in));in->op=29;uint64_t*w=(uint64_t*)(a.b+384);
  memcpy(s.b,a.b,sizeof(a.b));uint64_t status=0;
  switch(i){
   case 0:status=dong_encode(a.b+32,32,NULL,w);break;
   case 1:status=dong_encode(a.b+32,32,in,NULL);break;
   case 2:status=dong_encode(a.b+32,32,(Instruction*)(a.b+129),w);break;
   case 3:status=dong_encode(a.b+32,32,in,(uint64_t*)(a.b+385));break;
   case 4:status=dong_encode(a.b+32,32,in,(uint64_t*)(a.b+40));break;
   case 5:status=dong_encode(a.b+32,32,in,(uint64_t*)(a.b+128));break;
   case 6:status=dong_encode(a.b+120,32,in,w);break;
   case 7:status=dong_encode(NULL,32,in,w);break;
   case 8:status=dong_encode((uint8_t*)(uintptr_t)(UINT64_MAX-15),32,in,w);break;
   case 9:status=dong_encode(a.b+32,32,(Instruction*)(uintptr_t)(UINT64_MAX-7),w);break;
   case 10:status=dong_encode(a.b+32,32,in,(uint64_t*)(uintptr_t)(UINT64_MAX-7));break;
   case 11:status=dong_encode(a.b+360,32,in,w);break;
  }
  if(status!=1||memcmp(a.b,s.b,sizeof(a.b))){fprintf(stderr,"preflight %u status %llu\n",i,(unsigned long long)status);exit(92);}
 }
}
static void execute_smoke(void){
 uint8_t*code=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(code==MAP_FAILED)exit(94);
 Instruction seq[3]={{.op=1,.form=2,.width=64,.imm=0x123456789abcdef0ull},
                     {.op=2,.form=2,.width=64,.imm=7},{.op=29}};
 uint64_t pos=0;
 for(unsigned i=0;i<3;i++){uint64_t n=0;if(dong_encode(code+pos,4096-pos,seq+i,&n))exit(95);pos+=n;}
 if(mprotect(code,4096,PROT_READ|PROT_EXEC))exit(96);
 uint64_t (*fn)(void)=(uint64_t(*)(void))code;
 if(fn()!=0x123456789abcdef7ull)exit(97);
 if(munmap(code,4096))exit(98);
}
int main(void){
 execute_smoke();preflight();uint64_t count;read_exact(&count,8);
 while(count--){
  Instruction in,original;uint64_t cap;read_exact(&in,sizeof(in));original=in;read_exact(&cap,8);if(cap>32)exit(93);
  uint8_t out[96];uint64_t meta[3];memset(out,0xa5,sizeof(out));memset(meta,0xa5,sizeof(meta));
  uint64_t status=dong_encode(cap?out+32:NULL,cap,&in,meta+1);
  uint64_t guard=filled(out,32)&&filled(out+32+cap,64-cap)&&filled(meta,8)&&filled(meta+2,8)&&!memcmp(&in,&original,sizeof(in));
  if(status)guard=guard&&filled(out,sizeof(out))&&filled(meta,sizeof(meta));
  else guard=guard&&meta[1]<=cap&&filled(out+32+meta[1],64-meta[1]);
  uint64_t result[3]={status,guard,status?0:meta[1]};write_exact(result,sizeof(result));write_exact(out+32,32);
 }return 0;
}
'''


def ins(op, form=0, **values):
    d = dict.fromkeys(FIELDS, 0)
    d.update(op=op, form=form, **values)
    return tuple(d[k] & MASK for k in FIELDS)


class X86EncodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nasm = tool('nasm', 'NASM')
        if not cls.nasm and Path('/tmp/dongos-tools/usr/bin/nasm').exists():
            cls.nasm = '/tmp/dongos-tools/usr/bin/nasm'
        cls.cc = tool('gcc', 'CC')
        if not cls.nasm or not cls.cc:
            raise unittest.SkipTest('native encoder tests require NASM and GCC')
        cls.work = ROOT / 'build/test/bootstrap-components/x86-encode' / ('run-' + uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.records = []
        wrapper = cls.work / 'probe/x86_export.dg'
        wrapper.parent.mkdir()
        wrapper.write_text(WRAPPER)
        (cls.work / 'harness.c').write_text(HARNESS)
        cls.executables = {}
        for mode in ('debug', 'release'):
            asm = cls.work / (mode + '.asm')
            asm.write_text(compile_file(wrapper, roots=[ROOT / 'lang', cls.work], mode=mode).assembly)
            obj, exe = cls.work / (mode + '.o'), cls.work / mode
            cls.command([cls.nasm, '-f', 'elf64', '-o', obj, asm])
            cls.command([cls.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', cls.work / 'harness.c', obj, '-o', exe])
            cls.executables[mode] = exe

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'work'):
            inputs = [ROOT / 'lang/bootstrap/x86_encode.dg', Path(__file__)]
            summary = {'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}, 'records': cls.records, 'OS_VM_built': False, 'integrated': False}
            summary['artifact_sha256'] = {str(p.relative_to(cls.work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.work.rglob('*') if p.is_file()}
            (cls.work / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    @classmethod
    def command(cls, args):
        r = subprocess.run(list(map(str, args)), capture_output=True, timeout=120)
        with (cls.work / 'commands.log').open('ab') as log:
            log.write((' '.join(map(str,args)) + '\n').encode() + r.stdout + r.stderr)
        if r.returncode:
            raise AssertionError((args, r.returncode, r.stdout, r.stderr))
        return r.stdout

    def oracle(self, lines):
        # Fixed 16-byte slots retain instruction boundaries without disassembly.
        asm = self.work / 'oracle.asm'
        asm.write_text('bits 64\n' + ''.join(f'db e{i}-v{i}\nv{i}: {line}\ne{i}: times 16-($-v{i}) db 0xa5\n' for i, line in enumerate(lines)))
        out = self.work / 'oracle.bin'
        self.command([self.nasm, '-O0', '-f', 'bin', '-o', out, asm])
        data = out.read_bytes()
        self.assertEqual(len(data), 17 * len(lines))
        return [data[i+1:i+1+data[i]] for i in range(0, len(data), 17)]

    def verify(self, cases):
        payload = struct.pack('<Q', len(cases)) + b''.join(struct.pack('<12Q', *instruction, cap) for instruction, cap, status, expected in cases)
        for mode, exe in self.executables.items():
            r = subprocess.run([exe], input=payload, capture_output=True, timeout=120)
            self.assertEqual(r.returncode, 0, (mode, r.stderr))
            self.assertEqual(len(r.stdout), len(cases) * 56)
            for i, (instruction, cap, status, expected) in enumerate(cases):
                actual, guarded, length = struct.unpack_from('<3Q', r.stdout, i * 56)
                context = (mode, i, dict(zip(FIELDS, instruction)), cap)
                self.assertEqual(guarded, 1, context)
                self.assertEqual(actual, status, context)
                self.assertEqual(length, len(expected) if status == 0 else 0, context)
                self.assertEqual(r.stdout[i*56+24:i*56+56], expected + b'\xa5'*(32-len(expected)), context)
            self.records.append({'test': self.id(), 'mode': mode, 'cases': len(cases), 'execution_smoke': True, 'descriptor_preflights': 12})

    def check_assembly(self, pairs, capacity=True):
        expected = self.oracle([line for _, line in pairs])
        cases = []
        for (instruction, _), encoded in zip(pairs, expected):
            cases.append((instruction, 32, 0, encoded))
            if capacity:
                cases.append((instruction, len(encoded), 0, encoded))
                cases.append((instruction, len(encoded)-1, 2, b''))
        self.verify(cases)

    def test_all_register_pairs_and_widths(self):
        pairs = []
        for op, name in enumerate(('mov','add','sub','and','or','xor','cmp','test'), 1):
            for width in (8,16,32,64):
                for dst in range(16):
                    for src in range(16):
                        pairs.append((ins(op,1,width=width,dst=dst,src=src), f'{name} {REGS[width][dst]}, {REGS[width][src]}'))
        self.check_assembly(pairs, capacity=False)

    def test_immediates(self):
        pairs=[]
        for width in (8,16,32,64):
            for dst in range(16):
                for imm in (0,1,127,128,(1<<width)-1):
                    pairs.append((ins(1,2,width=width,dst=dst,imm=imm),f'mov {REGS[width][dst]}, strict {SIZE[width]} {imm}'))
            # NASM's accumulator special forms differ intentionally from our /digit policy.
            for op,name in ((2,'add'),(3,'sub'),(4,'and'),(5,'or'),(6,'xor'),(7,'cmp'),(8,'test')):
                for dst in range(1,16):
                    for imm in (0,1,127,128,-1):
                        encoded_imm = imm & ((1<<width)-1) if width!=64 else imm
                        pairs.append((ins(op,2,width=width,dst=dst,imm=encoded_imm),f'{name} {REGS[width][dst]}, strict {SIZE[width]} {imm}'))
        self.check_assembly(pairs)

    def test_memory_displacements(self):
        pairs=[]
        for width in (8,16,32,64):
            for reg in range(16):
                for base in range(16):
                    for disp in (0,-128,127,-129,128,-2147483648,2147483647):
                        mem=f'[dword {REGS[64][base]} + {disp}]'
                        pairs.append((ins(1,3,width=width,dst=reg,base=base,disp=disp),f'mov {REGS[width][reg]}, {mem}'))
                        pairs.append((ins(1,4,width=width,src=reg,base=base,disp=disp),f'mov {mem}, {REGS[width][reg]}'))
        self.check_assembly(pairs, capacity=False)

    def test_arithmetic_lea_and_extension_memory(self):
        pairs=[]
        for width in (8,16,32,64):
            for reg in (0,4,8,15):
                for base in range(16):
                    for disp in (0,-129,2147483647):
                        mem=f'[dword {REGS[64][base]} + {disp}]'
                        for op,name in ((2,'add'),(3,'sub'),(4,'and'),(5,'or'),(6,'xor'),(7,'cmp'),(8,'test')):
                            pairs.append((ins(op,4,width=width,src=reg,base=base,disp=disp),f'{name} {mem}, {REGS[width][reg]}'))
                            if op!=8:
                                pairs.append((ins(op,3,width=width,dst=reg,base=base,disp=disp),f'{name} {REGS[width][reg]}, {mem}'))
                        if width>8:
                            for op,name in ((9,'lea'),(18,'imul')):
                                pairs.append((ins(op,3,width=width,dst=reg,base=base,disp=disp),f'{name} {REGS[width][reg]}, {mem}'))
                            for source in (8,16,32):
                                if source>=width:continue
                                for op,name in (((12,'movsxd'),) if source==32 else ((10,'movzx'),(11,'movsx'))):
                                    pairs.append((ins(op,3,width=width,dst=reg,base=base,disp=disp,src_width=source),f'{name} {REGS[width][reg]}, {SIZE[source]} {mem}'))
        self.check_assembly(pairs,capacity=False)

    def test_extensions_unary_shift_and_control(self):
        pairs=[]
        for width in (16,32,64):
            for dst in range(16):
                for src in range(16):
                    pairs.append((ins(18,1,width=width,dst=dst,src=src),f'imul {REGS[width][dst]}, {REGS[width][src]}'))
        for op,name in ((10,'movzx'),(11,'movsx'),(12,'movsxd')):
            for source in ((32,) if op==12 else (8,16)):
                for width in (16,32,64):
                    if width<=source or (op==12 and width!=64):continue
                    for dst in range(16):
                        for src in range(16):
                            pairs.append((ins(op,1,width=width,dst=dst,src=src,src_width=source),f'{name} {REGS[width][dst]}, {REGS[source][src]}'))
        for op,name in ((13,'neg'),(14,'not'),(15,'mul'),(16,'div'),(17,'idiv'),(19,'shl'),(20,'shr'),(21,'sar')):
            for width in (8,16,32,64):
                for dst in range(16):
                    pairs.append((ins(op,6,width=width,dst=dst),f'{name} {REGS[width][dst]}' + (', cl' if op>=19 else '')))
        conditions='o no b ae e ne be a s ns p np l ge le g'.split()
        for cc,name in enumerate(conditions):
            for dst in range(16):pairs.append((ins(22,6,width=8,dst=dst,cc=cc),f'set{name} {REGS[8][dst]}'))
        for op,name in ((23,'push'),(24,'pop'),(25,'call'),(26,'jmp')):
            for dst in range(16):pairs.append((ins(op,6,width=64,dst=dst),f'{name} {REGS[64][dst]}'))
        for op,name in enumerate(('cqo','ret','ud2','cld','std','rep movsb','rep stosb','syscall'),28):pairs.append((ins(op),name))
        self.check_assembly(pairs)

    def test_relative_and_rip_fixed_vectors(self):
        cases=[]
        for disp in (0,1,-1,127,128,-128,-2147483648,2147483647):
            for op,opcode in ((25,b'\xe8'),(26,b'\xe9')):
                cases.append((ins(op,7,imm=disp),32,0,opcode+struct.pack('<i',disp)))
            for cc in range(16):cases.append((ins(27,7,imm=disp,cc=cc),32,0,bytes((15,128+cc))+struct.pack('<i',disp)))
            cases.append((ins(1,3,width=64,dst=9,base=16,disp=disp),32,0,b'\x4c\x8b\x0d'+struct.pack('<i',disp)))
        self.verify(cases)

    def test_accumulator_full_immediates_and_rip_lea(self):
        # Intel group-1 /digit and TEST /0 policy, intentionally not NASM's
        # accumulator-special opcodes. Immediate fields are little-endian.
        cases=[]
        groups={2:0,3:5,4:4,5:1,6:6,7:7,8:0}
        for width in (8,16,32,64):
            prefix={8:b'',16:b'\x66',32:b'',64:b'\x48'}[width]
            n=min(width,32)//8
            boundaries=(0,1,127,128,(1<<width)-1) if width<64 else (-2147483648,-1,0,2147483647)
            for op,group in groups.items():
                for imm in boundaries:
                    opcode=(0xf6 if width==8 else 0xf7) if op==8 else (0x80 if width==8 else 0x81)
                    encoded=prefix+bytes((opcode,0xc0+group*8))+(imm&((1<<(n*8))-1)).to_bytes(n,'little')
                    instruction=ins(op,2,width=width,imm=imm)
                    cases.extend(((instruction,32,0,encoded),(instruction,len(encoded)-1,2,b'')))
                bad=(1<<width,) if width<64 else (2147483648,-2147483649,0xffffffff)
                cases.extend((ins(op,2,width=width,imm=imm),32,1,b'') for imm in bad)
        for width in (16,32,64):
            for reg in range(16):
                for disp in (-2147483648,-1,0,2147483647):
                    prefix=b'\x66' if width==16 else b''
                    rex=(0x48 if width==64 else 0x40) | (4 if reg>=8 else 0)
                    if rex!=0x40:prefix+=bytes((rex,))
                    encoded=prefix+b'\x8d'+bytes((5+8*(reg&7),))+struct.pack('<i',disp)
                    cases.append((ins(9,3,width=width,dst=reg,base=16,disp=disp),32,0,encoded))
        self.verify(cases)

    def test_indexed_lea_nasm_vectors(self):
        pairs=[]
        for dst in (0,4,7,8,12,15):
            for base in range(16):
                for index in range(16):
                    if index==4:continue
                    for scale in (1,2,4,8):
                        for disp in (0,-128,127,-129,128,-2147483648,2147483647):
                            instruction=ins(9,8,width=64,dst=dst,src=index,base=base,disp=disp,imm=scale)
                            # NOSPLIT retains the selected base and scaled index even
                            # for scale 1/2; dword forces the promised disp32 form.
                            line=f'lea {REGS[64][dst]}, [nosplit dword {REGS[64][base]} + {REGS[64][index]}*{scale} + {disp}]'
                            pairs.append((instruction,line))
        self.check_assembly(pairs,capacity=False)
        small=[(ins(9,8,width=64,dst=15,src=12,base=4,disp=-2147483648,imm=8), 'lea r15, [nosplit dword rsp+r12*8-2147483648]')]
        self.check_assembly(small)

    def test_indexed_lea_invalid_descriptors(self):
        valid={'width':64,'dst':15,'src':12,'base':4,'disp':-1,'imm':8}
        invalid=[]
        for field,values in {'width':(0,8,16,32,128),'dst':(16,255),'src':(4,16,255),'base':(16,255),'disp':(2147483648,-2147483649),'imm':(0,3,5,7,16,MASK),'src_width':(8,32),'cc':(1,15),'reserved':(1,MASK)}.items():
            for value in values:
                record=dict(valid);record[field]=value
                invalid.append(ins(9,8,**record))
        for op in range(1,36):
            if op!=9:invalid.append(ins(op,8,**valid))
        self.verify([(instruction,32,1,b'') for instruction in invalid])

    def test_rejected_operation_form_cross_product(self):
        allowed={op:{1,2,3,4} for op in range(1,8)}
        allowed.update({8:{1,2,4},9:{3,8},10:{1,3},11:{1,3},12:{1,3},18:{1,3}})
        allowed.update({op:{6} for op in (13,14,15,16,17,19,20,21,22,23,24)})
        allowed.update({25:{6,7},26:{6,7},27:{7}})
        allowed.update({op:{0} for op in range(28,36)})
        invalid=[]
        for op in range(1,36):
            for form in range(9):
                if form in allowed[op]:continue
                width=0 if form==7 or op>=28 else (8 if op==22 else 64)
                extra={'src_width':32 if op==12 else 8} if op in (10,11,12) else {}
                invalid.append(ins(op,form,width=width,**extra))
        self.verify([(instruction,32,1,b'') for instruction in invalid])

    def test_invalid_and_unused_fields(self):
        invalid=[ins(0),ins(36),ins(1,99),ins(1,1,width=7),ins(1,1,width=64,dst=16),ins(1,1,width=64,src=16),ins(1,3,width=64,base=17),ins(22,6,width=8,cc=16),ins(12,1,width=32,src_width=32),ins(10,1,width=8,src_width=8),ins(23,6,width=32),ins(1,2,width=8,imm=256),ins(1,3,width=64,disp=2147483648),ins(25,7,imm=2147483648)]
        for field in FIELDS[1:]:
            values={field:1}
            if field=='form':invalid.append(ins(29,1))
            else:invalid.append(ins(29,**values))
        for field in ('base','disp','imm','src_width','cc','reserved'):
            invalid.append(ins(1,1,width=64,**{field:1}))
        self.verify([(i,32,1,b'') for i in invalid])


if __name__ == '__main__':
    unittest.main()
