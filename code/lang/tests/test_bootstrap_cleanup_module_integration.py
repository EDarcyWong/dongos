"""Real CR40 cleanup functions call real exports from an unchanged C52 module.

Only the bridge supplies zero-argument adapters and observes machine state. Dong
emits the scope traversal, cleanup preservation, module symbols and arithmetic.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from lang.tests import test_bootstrap_nasm_pair_cleanup_function as cleanup
from lang.tests import test_bootstrap_nasm_u64_module as module

ROOT = Path(__file__).resolve().parents[2]
MAX = (1 << 64) - 1
TOP = 1 << 63
IDS = tuple(range(7)) + (MAX-1,)
ARGS = [(MAX-k*17, TOP+k*31) for k in range(8)]
NAMES = [(b"m", b"a"), (b"m", b"b"), (b"n", b"a"),
         (bytes(range(64)), b"f"*64), (b"\xff", b"\xfe"),
         (b"cleanup", b"five"), (b"cleanup", b"six"), (b"cleanup", b"seven")]
OPS = [module.ADD, module.SUB, module.XOR, module.IMUL] * 2
FUNCTIONS = [module.fn(m, i, 2, 4,
    [(OPS[k], 2, 0, 1, 0), (module.CONST, 3, 0, 0, 0x1234+k)], 2)
    for k, (m, i) in enumerate(NAMES)]
SHAPES = [
    ([(MAX, 0, 0)], [], 0),
    ([(MAX, 0, 1)], [0], 0),
    ([(MAX, 0, 2)], [0, 1], 0),
    ([(MAX, 0, 2), (0, 2, 2), (1, 4, 2)], [0, 1, 2, 3, 4, 5], 2),
    ([(MAX, 0, 1), (0, 1, 1), (0, 2, 2)], [0, 1, 6, MAX-1], 1),
    ([(MAX, 0, 3)], [2, 2, MAX-1], 0),
    ([(MAX, 0, 16)], list(IDS)*2, 0),
    ([(MAX if k == 0 else k-1, k, 1) for k in range(8)], list(IDS), 7),
    ([(MAX if k == 0 else k-1, k, 1) for k in range(8)], list(IDS), 0),
    ([(MAX, 0, 2), (0, 2, 0), (1, 2, 0)], [5, 6], 2),
    ([(MAX, 0, 2), (0, 1, 2)], [0, 1, 2], 1),
]
VECTORS = [dict(names=[b"composition", ("cleanup%d" % k).encode()], q=[],
                args=[MAX-k, TOP+k], scopes=scopes, ids=ids, **{"from": start})
           for k, (scopes, ids, start) in enumerate(SHAPES)]
ORACLE = r'''
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#define ABI __attribute__((sysv_abi))
%DECLARATIONS%
typedef struct { uint64_t parent, first, count; } Scope;
typedef struct { uint64_t low, high, start; Scope scopes[8]; uint64_t ids[16]; } Case;
static const Case cases[] = {%CASES%};
static void (ABI *const calls[])(uint64_t *) = {%CALLS%};
static const uint64_t ids[] = {%IDS%};
static const uint64_t args[][2] = {%ARGS%};
static const uint64_t preserved[] = {%PRESERVED%};
static uint64_t value(unsigned k) {
    uint64_t a = args[k][0], b = args[k][1];
    switch (k % 4) { case 0: return a+b; case 1: return a-b;
                    case 2: return a^b; default: return a*b; }
}
int main(void) {
    unsigned pair_failures=0, trace_failures=0, value_failures=0, abi_failures=0, total_calls=0;
    for (unsigned k=0; k<sizeof(cases)/sizeof(cases[0]); ++k) {
        const Case *c = &cases[k]; uint64_t want[16]={0}; unsigned n=0;
        for (uint64_t at=c->start; at!=UINT64_MAX; at=c->scopes[at].parent) {
            const Scope *s=&c->scopes[at];
            for (uint64_t j=s->count; j>0; --j) want[n++]=c->ids[s->first+j-1];
        }
        uint64_t guarded[338]={0}; guarded[0]=guarded[337]=%CANARY%;
        uint64_t *o=guarded+1; calls[k](o);
        int badabi=o[2]!=o[3] || o[4] || o[5]!=%CANARY% ||
                   guarded[0]!=%CANARY% || guarded[337]!=%CANARY%;
        int badtrace=o[12]!=n, badvalue=0;
        for (unsigned r=0; r<6; ++r) if(o[6+r]!=preserved[r]) badabi=1;
        for (unsigned j=0; j<16; ++j) {
            const uint64_t *g=o+16+20*j;
            if (j<o[12] && j<16) {
                if(j>=n || g[0]!=want[j]) badtrace=1;
                unsigned id=0; while(id<8 && ids[id]!=g[0]) ++id;
                if(id==8 || g[1]!=value(id)) badvalue=1;
                if(g[2]!=8 || g[3]!=g[4] || (g[3]&15) || g[5]!=%CANARY%) badabi=1;
                for(unsigned r=0;r<6;++r) if(g[6+r]!=g[12+r]) badabi=1;
            } else { for(unsigned r=0;r<20;++r) if(g[r]) badabi=1; }
        }
        pair_failures+=o[0]!=c->low || o[1]!=c->high;
        trace_failures+=badtrace; value_failures+=badvalue; abi_failures+=badabi; total_calls+=n;
    }
    printf("{\"cases\":%zu,\"cleanup_calls\":%u,\"pair_failures\":%u,"
           "\"trace_failures\":%u,\"value_failures\":%u,\"abi_failures\":%u}\n",
           sizeof(cases)/sizeof(cases[0]), total_calls, pair_failures,trace_failures,value_failures,abi_failures);
    return abi_failures ? 11 : pair_failures || trace_failures || value_failures ? 10 : 0;
}
'''


def cu(value):
    return "UINT64_C(0x%x)" % (value & MAX)


class CleanupModuleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures=[]
        cls.before=cls.digests()
        cls.addClassCleanup(cls.cleanup_fixtures)
        for base in (cleanup.FunctionTests, module.NasmU64ModuleTests):
            fixture=type("Composition"+base.__name__, (base,), {})
            cls.fixtures.append(fixture)
            fixture.setUpClass()
        cls.cleanup,cls.module=(fixture() for fixture in cls.fixtures)
        cls.work=ROOT/"build/test/bootstrap-cleanup-module"/("run-"+uuid.uuid4().hex[:12])
        cls.work.mkdir(parents=True)
        cls.records=[]

    @classmethod
    def cleanup_fixtures(cls):
        errors=[]
        for fixture in reversed(cls.fixtures):
            try: fixture.tearDownClass()
            except Exception as error: errors.append(error)
        if errors: raise errors[0]

    @staticmethod
    def digests():
        paths={cleanup.SOURCE,cleanup.DOC,module.SOURCE,module.DOC,
               Path(cleanup.__file__),Path(module.__file__),Path(__file__),
               *cleanup.DEPENDENCIES,*module.DEPENDENCIES,*(ROOT/"lang/dongc").glob("*.py")}
        return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls,"work"): return
        after=cls.digests()
        result=dict(inputs_before=cls.before,inputs_after=after,stable=cls.before==after,
                    records=cls.records,native_format=cls.cleanup.native,selfhost_complete=False,OS_VM_built=False,
                    artifacts={str(p.relative_to(cls.work)):hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in cls.work.rglob("*") if p.is_file()})
        (cls.work/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
        if cls.before!=after: raise AssertionError("source changed during verification")

    def bridge(self,vectors):
        lines=["bits 64","section .data","align 8","observation: dq 0","host_anchor: dq 0",
               "thunk_anchor: dq 0","slot_anchor: dq 0","section .text"]
        lines += ["extern "+module.symbol(*names) for names in NAMES]
        for k,v in enumerate(vectors):
            lines += ["global compose%d"%k,"compose%d:"%k]
            lines += ["push "+r for r in cleanup.CALLER]
            lines += ["sub rsp, 8","mov [rel observation], rdi","mov [rel host_anchor], rsp",
                      "mov r10, rdi","mov [r10+16], rsp","mov rax, rsp","and rax, 15",
                      "mov [r10+32], rax","mov rax, 0x%x"%cleanup.CANARY,"mov [rsp], rax"]
            lines += ["mov %s, 0x%x"%pair for pair in cleanup.CALLER.items()]
            lines += ["mov rdi, 0x%x"%v["args"][0],"mov rsi, 0x%x"%v["args"][1],
                      "call "+cleanup.symbol(*v["names"]),"mov r10, [rel observation]",
                      "mov [r10], rax","mov [r10+8], rdx","mov [r10+24], rsp"]
            lines += ["mov [r10+%d], %s"%(48+8*j,r) for j,r in enumerate(cleanup.CALLER)]
            lines += ["mov r11, [rel host_anchor]","mov r11, [r11]","mov [r10+40], r11",
                      "mov rsp, [rel host_anchor]","add rsp, 8"]
            lines += ["pop "+r for r in reversed(cleanup.CALLER)]+["ret"]
        for k,id_ in enumerate(IDS):
            lines += ["__dong_cleanup%d:"%id_,"mov r10, [rel observation]","mov r11, [r10+96]",
                      "inc qword [r10+96]","and r11, 15","imul r11, 160","lea r10, [r10+r11+128]",
                      "mov [rel slot_anchor], r10","mov r11, 0x%x"%id_,"mov [r10], r11",
                      "mov r11, rsp","and r11, 15","mov [r10+16], r11","sub rsp, 8",
                      "mov [rel thunk_anchor], rsp","mov [r10+24], rsp",
                      "mov r11, 0x%x"%cleanup.CANARY,"mov [rsp], r11"]
            lines += ["mov [r10+%d], %s"%(48+8*j,r) for j,r in enumerate(cleanup.CALLER)]
            lines += ["mov rdi, 0x%x"%ARGS[k][0],"mov rsi, 0x%x"%ARGS[k][1],
                      "call "+module.symbol(*NAMES[k]),"mov r10, [rel slot_anchor]",
                      "mov [r10+8], rax","mov [r10+32], rsp"]
            lines += ["mov [r10+%d], %s"%(96+8*j,r) for j,r in enumerate(cleanup.CALLER)]
            lines += ["mov r11, [rel thunk_anchor]","mov r11, [r11]","mov [r10+40], r11"]
            # Observe first; restore from independent anchors before returning to CR40.
            lines += ["mov %s, [r10+%d]"%(r,48+8*j) for j,r in enumerate(cleanup.CALLER)]
            lines += ["mov rsp, [rel thunk_anchor]","add rsp, 8"]
            lines += ["mov %s, %d"%(r,31+j) for j,r in enumerate(("rdi","rsi","rcx","rdx","r8","r9","r10","r11"))]
            lines += ["stc","ret"]
        return "\n".join(lines)+"\n"

    def oracle_source(self,vectors):
        entries=[]
        for v in vectors:
            scopes=",".join("{"+",".join(map(cu,s))+"}" for s in v["scopes"])
            ids=",".join(map(cu,v["ids"])) or "0"
            entries.append("{"+",".join(map(cu,[*v["args"],v["from"]]))+",{"+scopes+"},{"+ids+"}}")
        return (ORACLE.replace("%DECLARATIONS%","\n".join("extern void ABI compose%d(uint64_t *);"%k for k in range(len(vectors))))
                .replace("%CASES%",",\n".join(entries)).replace("%CALLS%",",".join("compose%d"%k for k in range(len(vectors))))
                .replace("%IDS%",",".join(map(cu,IDS))).replace("%ARGS%",",".join("{"+",".join(map(cu,a))+"}" for a in ARGS))
                .replace("%PRESERVED%",",".join(map(cu,cleanup.CALLER.values()))).replace("%CANARY%",cu(cleanup.CANARY)))

    def command(self,command,label):
        run=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=180)
        (self.work/(label+".log")).write_text(run.stdout+run.stderr)
        self.assertEqual(run.returncode,0,(label,run.stdout,run.stderr))

    def run_chain(self,mode,vectors,variant,cleanup_exe,module_exe,expected):
        label=mode+"-"+variant
        texts=self.cleanup.generate(cleanup_exe,vectors,label,exact=not variant.startswith("bad-cleanup"))
        result=self.module.emit_all(module_exe,[self.module.case(FUNCTIONS,out=len(module.module_text(FUNCTIONS))+512)],label)[0]
        self.assertEqual((result["status"],result["valid"]),(0,1))
        if not variant.startswith("bad-module") : self.assertEqual(result["text"],module.module_text(FUNCTIONS))
        # C52 output is assembled directly, as a separate object, without rewriting a byte.
        module_asm=self.work/(label+"-module.asm");module_asm.write_bytes(result["text"])
        bridge_asm=self.work/(label+"-bridge.asm");bridge_asm.write_text(self.bridge(vectors)+b"".join(texts).decode("ascii"))
        for fmt in ("elf64","win64"):
            for part,asm in (("module",module_asm),("bridge",bridge_asm)):
                self.command([self.cleanup.nasm,"-f",fmt,*cleanup.nasm_flags(self.cleanup.nasm),
                              "-o",self.work/(label+"-"+part+"."+fmt+".o"),asm],label+"-"+part+"-"+fmt)
        c=self.work/(label+".c");c.write_text(self.oracle_source(vectors))
        exe=self.work/(label+(".exe" if os.name=="nt" else ""))
        self.command([self.cleanup.cc,"-std=c11","-O2","-Wall","-Wextra","-Werror",c,
                      self.work/(label+"-module."+self.cleanup.native+".o"),
                      self.work/(label+"-bridge."+self.cleanup.native+".o"),"-o",exe],label+"-link")
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
        (self.work/(label+".stdout")).write_text(run.stdout);(self.work/(label+".stderr")).write_text(run.stderr)
        self.assertEqual(run.returncode,11 if expected["abi_failures"] else 0 if variant=="good" else 10,(label,run.stderr))
        record=json.loads(run.stdout);self.assertEqual(record,expected,label)
        self.records.append(dict(mode=mode,variant=variant,normal_exit=True,observations=record))

    def test_real_module_exports_cleanup_order_and_pair_preservation(self):
        self.assertEqual(len(VECTORS),11)
        source=cleanup.SOURCE.read_text()
        old='if !store_memory(buffer,&at,2,-32){return false;}'
        self.assertEqual(source.count(old),1)
        pair=self.cleanup.build_all("composition-bad-cleanup-rdx",source.replace(old,'if !put(buffer,&at,"mov rdx, 17\\n"){return false;}'+old))
        _,old,new,_,_=cleanup.mutations(source)[1]
        self.assertEqual(source.count(old),1)
        order=self.cleanup.build_all("composition-bad-cleanup-order",source.replace(old,new))
        source=module.SOURCE.read_text()
        old='functions[i].instructions,functions[i].return_slot,slice_from_raw_parts(&work[at],BODY),&n)'
        self.assertEqual(source.count(old),1)
        wrong_source=source.replace(old,'functions[i].instructions,chosen_return,slice_from_raw_parts(&work[at],BODY),&n)')
        # Keep the fixture harness startup/preflight probes unchanged. Only the
        # composition's four-slot, return-slot-2 functions have initialized slot 3.
        marker='  if f.emit('
        self.assertEqual(wrong_source.count(marker),1)
        wrong_source=wrong_source.replace(marker,'  var chosen_return=functions[i].return_slot;\n  if functions[i].slot_count==4&&chosen_return==2{chosen_return=3;}\n'+marker,1)
        wrong=self.module.build_all("composition-bad-module-return",wrong_source,module.C48.read_text())
        c48=module.C48.read_text()
        old='if ex.emit(U64_KIND,frame,0,8*(return_slot+1),0,slice_from_raw_parts(&buffer[0],CHUNK),&n)!=ex.OK{return false;}\n  at=n;'
        self.assertEqual(c48.count(old),1)
        clobber=c48.replace(old,old+'at-=4;put(buffer,&at,"add rbx, 8\\nret\\n");',1)
        rbx=self.module.build_all("composition-bad-module-rbx",source,clobber)
        zero=dict(pair_failures=0,trace_failures=0,value_failures=0,abi_failures=0)
        total=sum(len(cleanup.order(v)) for v in VECTORS)
        for mode in ("debug","release"):
            self.run_chain(mode,VECTORS,"good",self.cleanup.executables[mode],self.module.executables[mode],dict(zero,cases=11,cleanup_calls=total))
            self.run_chain(mode,VECTORS,"bad-cleanup-rdx",pair[mode],self.module.executables[mode],dict(zero,cases=11,cleanup_calls=total,pair_failures=11))
            self.run_chain(mode,[VECTORS[2]],"bad-cleanup-order",order[mode],self.module.executables[mode],dict(zero,cases=1,cleanup_calls=2,trace_failures=1))
            self.run_chain(mode,VECTORS,"bad-module-return",self.cleanup.executables[mode],wrong[mode],dict(zero,cases=11,cleanup_calls=total,value_failures=10))
            self.run_chain(mode,VECTORS,"bad-module-rbx",self.cleanup.executables[mode],rbx[mode],dict(zero,cases=11,cleanup_calls=total,abi_failures=10))


if __name__=="__main__":
    unittest.main()
