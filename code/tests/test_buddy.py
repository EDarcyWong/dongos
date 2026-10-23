"""Real native allocated-block audit, including canonical tails and atomicity."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import tool, nasm_flags

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = '''module probe;
import mm.phys_buddy as b;
export("bs") fn size(which:u64)u64{if which==0{return sizeof(b.Allocator) as u64;}return sizeof(b.PageMeta) as u64;}
export("bi") fn init(a:*b.Allocator,m:*b.PageMeta)u64{unsafe{*a=b.EMPTY_ALLOCATOR;
 match b.init(a,0x10000000,1024,slice_from_raw_parts(m,1024)){ok=>{},err(e)=>{return e;},}
 match b.add_usable(a,0,1024){ok=>{return 0;},err(e)=>{return e;},}}}
export("ba") fn alloc(a:*b.Allocator,out:*u64)u64{unsafe{match b.alloc(a,9){ok(p)=>{*out=p;return 0;},err(e)=>{return e;},}}}
export("bf") fn free(a:*b.Allocator,p:u64)u64{unsafe{match b.free(a,p,9){ok=>{return 0;},err(e)=>{return e;},}}}
export("bc") fn check(a:*const b.Allocator,p:u64,o:usize)u64{unsafe{match b.allocated_block(a,p,o){ok=>{return 0;},err(e)=>{return e;},}}}
'''
ORACLE = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DG __attribute__((sysv_abi))
typedef uint64_t U;
extern U DG bs(U),bi(void*,void*),ba(void*,U*),bf(void*,U),bc(void*,U,U);
void DG __attribute__((noreturn)) __dong_panic(unsigned k,unsigned l,const char*f,U n){fprintf(stderr,"panic %u %u %.*s",k,l,(int)n,f);exit(99);}
#define C(x) do{if(!(x)){fprintf(stderr,"allocated buddy oracle %d\n",__LINE__);return 1;}}while(0)
int main(void){U an=bs(0),mn=bs(1),p=0;C(mn==16);unsigned char*a=calloc(an+128,1),*m=calloc(mn*1024+128,1),*old=malloc(an+mn*1024);C(a&&m&&old);memset(a,0xa5,64);memset(a+64+an,0xa5,64);memset(m,0xa5,64);memset(m+64+mn*1024,0xa5,64);void*s=a+64;unsigned char*t=m+64;
 C(!bi(s,t));C(bc(s,0x10000000,9));C(!ba(s,&p)&&p==0x10000000);C(!bc(s,p,9));
 memcpy(old,s,an);memcpy(old+an,t,mn*1024);
 C(bc(s,p+4096,9)&&bc(s,p,8)&&bc(s,p,10)&&bc(s,p,11)&&bc(s,UINT64_MAX,9)&&bc(s,0,9));
 C(!memcmp(old,s,an)&&!memcmp(old+an,t,mn*1024));
 for(U i=1;i<512;i++){for(unsigned field=0;field<3;field++){U at=i*mn+(field==2?8:field);unsigned char saved=t[at];t[at]^=1;memcpy(old+an,t,mn*1024);C(bc(s,p,9));C(!memcmp(old,s,an)&&!memcmp(old+an,t,mn*1024));t[at]=saved;}}
 for(unsigned field=0;field<3;field++){U at=field==2?8:field;unsigned char saved=t[at];t[at]^=1;memcpy(old+an,t,mn*1024);C(bc(s,p,9));C(!memcmp(old,s,an)&&!memcmp(old+an,t,mn*1024));t[at]=saved;}
 C(!bc(s,p,9));C(!bf(s,p));C(bc(s,p,9));for(unsigned i=0;i<64;i++){C(a[i]==0xa5&&a[64+an+i]==0xa5&&m[i]==0xa5&&m[64+mn*1024+i]==0xa5);}
 puts("allocated buddy head/tails 1536 corruptions rejected; real DG, no VM");free(a);free(m);free(old);return 0;}
'''


class BuddyAllocationAuditTests(unittest.TestCase):
    def test_actual_allocated_head_and_every_tail_both_modes(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'native tools required, no skip')
        paths = [Path(__file__), ROOT / 'kernel/mm/phys_buddy.dg', ROOT / 'kernel/mm/errors.dg',
                 ROOT / 'lang/tests/test_dongc.py', *list((ROOT / 'lang/dongc').rglob('*.py'))]
        hashes = lambda: {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        before = hashes()
        tools = {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in [nasm, cc]}
        out = ROOT / 'build/test/buddy-allocation' / ('run-' + uuid.uuid4().hex[:12])
        out.mkdir(parents=True)
        (out / 'probe.dg').write_text(WRAPPER)
        (out / 'oracle.c').write_text(ORACLE)
        evidence = []
        for mode in ['debug', 'release']:
            compiled = compile_file(out / 'probe.dg', roots=[out, ROOT / 'kernel', ROOT / 'lang/std'], mode=mode)
            (out / (mode + '-layout.json')).write_text(json.dumps(compiled.layout_manifest, indent=2))
            asm = out / (mode + '.asm'); asm.write_text(compiled.assembly)
            commands = []
            for fmt in ['elf64', 'win64']:
                commands.append([nasm, '-f', fmt, *nasm_flags(nasm), asm, '-o', out / (mode + '-' + fmt + '.o')])
            exe = out / (mode + ('.exe' if os.name == 'nt' else ''))
            commands += [[cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', *([] if os.name == 'nt' else ['-no-pie']),
                          out / 'oracle.c', out / (mode + ('-win64.o' if os.name == 'nt' else '-elf64.o')), '-o', exe], [exe]]
            for index, command in enumerate(commands):
                command = list(map(str, command))
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=90)
                evidence.append(dict(mode=mode, index=index, argv=command, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
                (out / 'commands.json').write_text(json.dumps(evidence, indent=2))
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn('1536 corruptions rejected', result.stdout)
        after = hashes(); self.assertEqual(before, after)
        self.assertEqual(tools, {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in tools})
        (out / 'result.json').write_text(json.dumps(dict(passed=True, source_before=before, source_after=after,
            source_stable=before == after, tools_sha256=tools, actual_dong_allocator=True, guest_executed=False), indent=2))
        print('BUDDY_ALLOCATION_EVIDENCE', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
