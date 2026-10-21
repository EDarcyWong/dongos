"""Independent ELF load-segment/retention oracle using the real kernel script."""
from pathlib import Path
import struct,unittest
from lang.dongc import compile_source
from lang.tests.test_dongc import tool,nasm_flags
from lang.tests import test_function_sections as sections
from lang.tests.test_function_sections import command,SOURCE,ROOT
from tools.build import find_tool
from tools.elf_symbols import read_elf_symbols
from tools.elf_image import materialize

class KernelGCChecks(unittest.TestCase):
    def test_kernel_entry_and_relocations_survive_gc_with_original_wx_and_image_bounds(self):
        d=sections.FunctionSectionsTests().directory();nasm=tool('nasm','NASM');self.assertTrue(nasm,'requires real NASM')
        linker=find_tool('ld.lld','LD_LLD')
        # Distinct unused functions make collection observable in final load size.
        extra=''.join('fn unused'+str(i)+'(x:u64)u64{var a=x;'+('a=a*3+1;'*12)+'return a;}' for i in range(20))
        c=compile_source(SOURCE+extra,mode='release',function_sections=True)
        asm=d/'kernel.dg.asm';asm.write_text(c.assembly,encoding='utf-8');obj=d/'dong.o'
        r=command([nasm,'-f','elf64',*nasm_flags(nasm),asm,'-o',obj],d,'kernel-dong');self.assertEqual(r.returncode,0,r.stderr)
        entry=d/'entry.asm';entry.write_text('bits 64\nsection .text.entry\nglobal kernel_entry,__dong_panic\nextern entry\nkernel_entry: mov edi,5\ncall entry\n.halt: hlt\njmp .halt\n__dong_panic: ud2\n',encoding='utf-8')
        eo=d/'entry.o';r=command([nasm,'-f','elf64',entry,'-o',eo],d,'kernel-entry');self.assertEqual(r.returncode,0,r.stderr)
        sizes={}
        for gc in (False,True):
            elf=d/('kernel-gc.elf' if gc else 'kernel-all.elf')
            r=command([linker,'-nostdlib',*(['--gc-sections'] if gc else []),'-z','max-page-size=0x1000','-T',ROOT/'kernel/linker.ld','-o',elf,eo,obj],d,'kernel-link-'+str(gc));self.assertEqual(r.returncode,0,r.stderr)
            symbols=read_elf_symbols(elf);raw=materialize(elf.read_bytes());sizes[gc]=len(raw)
            for n in ('__kernel_text_start','__kernel_text_end','__kernel_rodata_end','__kernel_data_end','__kernel_bss_end'):
                self.assertEqual(symbols[n]%4096,0,n)
            data=elf.read_bytes();offset=struct.unpack_from('<Q',data,32)[0];stride,count=struct.unpack_from('<HH',data,54)
            loads=[struct.unpack_from('<IIQQQQQQ',data,offset+i*stride) for i in range(count)]
            self.assertTrue(any(p[0]==1 for p in loads))
            for p in loads:
                if p[0]==1:self.assertNotEqual(p[1]&3,3,'PT_LOAD cannot be writable executable')
            self.assertLessEqual(len(raw),0x200000)
            self.assertEqual('dead_export' in symbols,not gc)
            self.assertIn('windows_bridge',symbols);self.assertIn('entry',symbols)
        self.assertLess(sizes[True],sizes[False])

if __name__=='__main__':unittest.main()
