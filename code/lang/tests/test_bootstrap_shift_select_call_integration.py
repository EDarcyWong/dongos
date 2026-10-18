"""Execute actual Dong-produced CL shift, symbol addresses, cmov and indirect call."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
import uuid

from lang.tests import test_bootstrap_nasm_variable_shift as shift
from lang.tests import test_bootstrap_nasm_conditional_move as select
from lang.tests import test_bootstrap_nasm_indirect_call as call
from lang.tests import test_bootstrap_nasm_symbol_address as address
from lang.tests.test_dongc import nasm_flags

ROOT = Path(__file__).resolve().parents[2]
MASK = (1 << 64)-1
TOP = 1 << 63
FALSE_MARK, TRUE_MARK = 0x123456789ABCDEF0, 0xFEDCBA9876543210
# (shift, predicate, value, RCX count, comparison threshold)
VECTORS = [(0, 6, TOP, 0, 0), (0, 2, TOP, 0, 0), (1, 6, TOP, 1, 1 << 62),
           (2, 6, TOP, 1, 0), (0, 2, MASK, 1, MASK), (1, 2, MASK, 63, 1),
           (2, 6, MASK, 64, 0), (0, 6, 3, 65, 5), (1, 2, TOP, 65, TOP),
           (2, 6, TOP, MASK, 0), (0, 2, 1, 63, TOP), (2, 6, 0, MASK, 1)]
HELPERS = ((shift, 'NasmVariableShiftTests'), (select, 'NasmConditionalMoveTests'),
           (call, 'NasmIndirectCallTests'), (address, 'NasmSymbolAddressTests'))
MAIN = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif
#define ABI __attribute__((sysv_abi))
typedef void (ABI *probe)(uint64_t,uint64_t,uint64_t,uint64_t*);
%DECLS%
int main(void){
#ifdef _WIN32
 _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
 probe functions[]={%FUNCTIONS%};
 for(unsigned i=0;i<sizeof(functions)/sizeof(functions[0]);i++){
  uint64_t args[3],result[5];memset(result,0xA5,sizeof(result));
  if(fread(args,1,sizeof(args),stdin)!=sizeof(args))return 91;
  functions[i](args[0],args[1],args[2],result+1);
  if(result[0]!=UINT64_C(0xA5A5A5A5A5A5A5A5)||result[4]!=result[0])return 96;
  if(fwrite(result+1,1,24,stdout)!=24)return 92;
 }return 0;
}
'''


class ShiftSelectCallIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = ROOT/'build/test/bootstrap-shift-select-call-integration'/('run-'+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.helpers, cls.records = [], []
        cls.sources = [ROOT/'lang/bootstrap'/(n+ext)
                       for n in ('nasm_variable_shift','nasm_conditional_move','nasm_indirect_call','nasm_symbol_address')
                       for ext in ('.dg','.md')]
        cls.sources += [ROOT/'lang/bootstrap'/(n+'.dg') for n in ('branch_plan','nasm_symbol')]
        cls.sources += [Path(__file__)]
        cls.sources += [Path(m.__file__) for m, _ in HELPERS]
        cls.inputs = cls.identities()
        try:
            for module, name in HELPERS:
                helper = getattr(module, name)
                cls.helpers.append(helper)
                helper.setUpClass()
            cls.nasm, cls.cc = cls.helpers[0].nasm, cls.helpers[0].cc
        except BaseException:
            for helper in reversed(cls.helpers):
                helper.tearDownClass()
            cls.helpers = []
            raise

    @classmethod
    def identities(cls):
        return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in cls.sources}

    @classmethod
    def tearDownClass(cls):
        for helper in reversed(cls.helpers):
            helper.tearDownClass()
        (cls.work/'summary.json').write_text(json.dumps(dict(source_sha256=cls.inputs,
            source_stable=cls.identities() == cls.inputs, records=cls.records,
            helper_artifacts=[str(h.work) for h in cls.helpers],
            OS_VM_built=False, L3_selfhost_complete=False), indent=2)+'\n', encoding='utf-8')

    def command(self, args, label):
        run = subprocess.run(list(map(str,args)), capture_output=True, text=True, timeout=120)
        (self.work/(label+'.log')).write_text(run.stdout+run.stderr, encoding='utf-8')
        self.assertEqual(run.returncode, 0, (label,run.stderr))

    def test_Dong_shift_selects_and_calls_an_actual_callee(self):
        sh, cm, ca, ad = (h() for h in self.helpers)
        native = 'win64' if os.name == 'nt' else 'elf64'
        for mode in ('debug','release'):
            emitted_shifts = sh.emit(sh.executables[mode],
                [(op,0,32,0) for op,_,_,_,_ in VECTORS], 'pipeline-shift-'+mode)
            emitted_moves = cm.emit(cm.executables[mode],
                [(predicate,10,11,32,0) for _,predicate,_,_,_ in VECTORS], 'pipeline-select-'+mode)
            indirect_call = ca.emit(ca.executables[mode], [(10,32,0)], 'pipeline-call-'+mode)[0]
            callee_addresses = ad.emit(ad.executables[mode],
                [(10,b'pipeline',b'false_callee',300,0,1,0),
                 (11,b'pipeline',b'true_callee',300,0,1,0)], 'pipeline-addresses-'+mode)
            body = b'bits 64\nsection .text\n'
            for i, (sh_text, cm_text) in enumerate(zip(emitted_shifts, emitted_moves)):
                body += f'global pipeline_{i}\npipeline_{i}:\n'.encode()
                # SysV: value=RDI, count=RSI, threshold=RDX, result*=RCX.
                # Save the result pointer before RCX becomes the hardware count.
                body += b'push rbx\nmov rbx, rcx\nmov rax, rdi\nmov rcx, rsi\n'+sh_text
                body += b'mov [rbx], rax\n'+b''.join(callee_addresses)
                body += b'cmp rax, rdx\n'+cm_text+b'mov rdi, rax\n'+indirect_call
                body += b'mov [rbx+8], rax\nmov [rbx+16], rdx\npop rbx\nret\n'
            for label, marker in (('false_callee',FALSE_MARK), ('true_callee',TRUE_MARK)):
                symbol = '__dong_m'+b'pipeline'.hex()+'_n'+label.encode('ascii').hex()
                body += (f'{symbol}:\nmov rax, rdi\nmov rdx, 0x{marker:x}\nxor rax, rdx\n'
                         'mov rdx, rsp\nand edx, 15\nret\n').encode()
            asm = self.work/(mode+'.asm')
            asm.write_bytes(body)
            for fmt in ('elf64','win64'):
                self.command([self.nasm,'-f',fmt,*nasm_flags(self.nasm),'-o',
                              self.work/(mode+'.'+fmt+'.o'),asm], mode+'-'+fmt)
            c = self.work/(mode+'.c')
            declarations = '\n'.join(f'extern void ABI pipeline_{i}(uint64_t,uint64_t,uint64_t,uint64_t*);'
                                     for i in range(len(VECTORS)))
            functions = ','.join(f'pipeline_{i}' for i in range(len(VECTORS)))
            c.write_text(MAIN.replace('%DECLS%',declarations).replace('%FUNCTIONS%',functions), encoding='utf-8')
            exe = self.work/(mode+('.exe' if os.name == 'nt' else ''))
            self.command([self.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',c,
                          self.work/(mode+'.'+native+'.o'),'-o',exe], mode+'-link')
            payload = b''.join(struct.pack('<3Q',v,count,threshold) for _,_,v,count,threshold in VECTORS)
            run = subprocess.run([str(exe)], input=payload, capture_output=True, timeout=60)
            (self.work/(mode+'.input')).write_bytes(payload)
            (self.work/(mode+'.output')).write_bytes(run.stdout)
            (self.work/(mode+'.stderr')).write_bytes(run.stderr)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(len(run.stdout), 24*len(VECTORS))
            truths = []
            for i, (op,predicate,value,count,threshold) in enumerate(VECTORS):
                k = count & 63
                if op == 0:
                    shifted = (value << k) & MASK
                elif op == 1:
                    shifted = value >> k
                else:
                    shifted = ((value-(1 << 64) if value & TOP else value) >> k) & MASK
                if predicate == 2:
                    selected = shifted < threshold
                else:
                    signed_value = shifted-(1 << 64) if shifted & TOP else shifted
                    signed_threshold = threshold-(1 << 64) if threshold & TOP else threshold
                    selected = signed_value < signed_threshold
                truths.append(selected)
                marker = TRUE_MARK if selected else FALSE_MARK
                self.assertEqual(struct.unpack_from('<3Q',run.stdout,24*i),
                                 (shifted,shifted ^ marker,8), (mode,i))
            self.assertEqual(set(truths), {False,True})
            self.records.append(dict(mode=mode,vectors=len(VECTORS),true=sum(truths),
                false=len(truths)-sum(truths),formats=['elf64','win64'],
                pipeline='Dong CL shift -> Dong RIP symbol addresses -> cmp -> Dong cmov -> Dong indirect call',passed=True))
        self.assertEqual(self.identities(), self.inputs, 'source identity changed')


if __name__ == '__main__':
    unittest.main()
