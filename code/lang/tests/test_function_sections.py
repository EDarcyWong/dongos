"""Real section/relocation/ABI execution; no kernel or VM is started."""
from pathlib import Path
import json,os,re,subprocess,sys,unittest,uuid
from lang.dongc import compile_source,compile_file
from lang.tests.test_dongc import tool,nasm_flags
from tools.build import find_tool
from tools.elf_symbols import read_elf_symbols
ROOT=Path(__file__).resolve().parents[2]
SOURCE='''module sections;
type Callback=fn(u64)u64;
var CALLBACK:Callback=pointer_only;
fn pointer_only(x:u64)u64{return x+7;}
fn direct(x:u64)u64{return x*3;}
export("dead_export") fn dead(x:u64)u64{return x+999;}
export("windows_bridge") extern "win64" fn windows(x:u64)u64{return x+5;}
export("entry") fn entry(x:u64)u64{unsafe{return direct(x)+CALLBACK(x)+windows(x);}}
'''

def command(args,directory,label):
    r=subprocess.run(list(map(str,args)),cwd=ROOT,capture_output=True,text=True,timeout=70)
    (directory/(label+'.json')).write_text(json.dumps(dict(command=list(map(str,args)),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n',encoding='utf-8')
    return r

class FunctionSectionsTests(unittest.TestCase):
    def directory(self):
        p=ROOT/'build/test/function-sections'/('run-'+uuid.uuid4().hex[:12]);p.mkdir(parents=True);return p
    def test_explicit_options_preserve_default_bodies_layout_and_manifest(self):
        for mode in ('debug','release'):
            a=compile_source(SOURCE,mode=mode);b=compile_source(SOURCE,mode=mode,function_sections=True)
            stripped=re.sub(r'%ifidn __OUTPUT_FORMAT__,elf64\nsection \.text\.dg_[0-9a-f]+ progbits alloc exec nowrite align=16\n%else\nsection \.text\.dg_[0-9a-f]+ code align=16\n%endif\n','',b.assembly)
            self.assertEqual(stripped,a.assembly)
            self.assertEqual(a.layout_manifest,b.layout_manifest)
            manifest=b.manifest();self.assertIs(manifest.pop('function_sections'),True);self.assertEqual(manifest,a.manifest())
            self.assertEqual(len(re.findall(r'^section \.text\.dg_',b.assembly,re.M)),10)
        for flag in (0,1,None,'yes'):
            with self.assertRaises(ValueError):compile_source(SOURCE,function_sections=flag)
        with self.assertRaises(ValueError):compile_source(SOURCE,function_sections=True,debug_info=True)
        d=self.directory();s=d/'input.dg';s.write_text(SOURCE,encoding='utf-8')
        self.assertTrue(compile_file(s,function_sections=True).function_sections)
        with self.assertRaises(ValueError):compile_file(s,function_sections=1)
        r=command([sys.executable,'-m','lang.dongc',s,'--function-sections','--emit-asm',d/'cli.asm','--emit-manifest',d/'cli-manifest.json'],d,'cli-command')
        self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(json.loads((d/'cli-manifest.json').read_text())['function_sections'])
        r=command([sys.executable,'-m','lang.dongc',s,'--function-sections','-g','--emit-asm',d/'invalid.asm'],d,'invalid-cli')
        self.assertNotEqual(r.returncode,0);self.assertFalse((d/'invalid.asm').exists())

    def test_actual_gc_keeps_direct_static_pointer_and_win64_bridge_and_executes(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc,'native tools required; no skip')
        linker=find_tool('ld.lld','LD_LLD')
        for mode in ('debug','release'):
            d=self.directory();c=compile_source(SOURCE,mode=mode,function_sections=True)
            a=d/'probe.asm';a.write_text(c.assembly,encoding='utf-8')
            obj=d/'probe.o';r=command([nasm,'-f','elf64',*nasm_flags(nasm),a,'-o',obj],d,'elf-assemble');self.assertEqual(r.returncode,0,r.stderr)
            stub=d/'stub.asm';stub.write_text('bits 64\nsection .text\nglobal __dong_panic\n__dong_panic: ud2\n',encoding='utf-8')
            so=d/'stub.o';r=command([nasm,'-f','elf64',stub,'-o',so],d,'stub');self.assertEqual(r.returncode,0,r.stderr)
            paths={}
            for gc in (False,True):
                elf=d/('gc.elf' if gc else 'all.elf');r=command([linker,'-nostdlib','-e','entry',*(['--gc-sections'] if gc else []),'-o',elf,obj,so],d,'link-'+str(gc));self.assertEqual(r.returncode,0,r.stderr);paths[gc]=read_elf_symbols(elf)
            self.assertIn('dead_export',paths[False]);self.assertNotIn('dead_export',paths[True])
            for symbol in ('entry','windows_bridge'):
                self.assertIn(symbol,paths[True])
            self.assertTrue(any('706f696e7465725f6f6e6c79' in n for n in paths[True]))
            self.assertTrue(any(n.startswith('__dg_bridge_') for n in paths[True]))
            fmt='win64' if os.name=='nt' else 'elf64';native=d/'native.o'
            r=command([nasm,'-f',fmt,*nasm_flags(nasm),a,'-o',native],d,'native-assemble');self.assertEqual(r.returncode,0,r.stderr)
            host=d/'host.c';host.write_text('''#include <stdint.h>
#include <stdio.h>
extern uint64_t __attribute__((sysv_abi)) entry(uint64_t);
void __attribute__((sysv_abi,noreturn)) __dong_panic(void){puts("panic");__builtin_trap();}
int main(void){for(uint64_t i=0;i<256;i++)if(entry(i)!=5*i+12)return 1;puts("256 exact ABI calls passed");return 0;}
''',encoding='utf-8')
            exe=d/('native.exe' if os.name=='nt' else 'native');r=command([cc,'-O2','-Wall','-Wextra','-Werror',*(['-mno-sse'] if os.name=='nt' else ['-no-pie']),'-Wl,--gc-sections',host,native,'-o',exe],d,'native-link');self.assertEqual(r.returncode,0,r.stderr)
            r=command([exe],d,'native-execute');self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('256 exact ABI calls passed',r.stdout)

if __name__=='__main__':unittest.main()
