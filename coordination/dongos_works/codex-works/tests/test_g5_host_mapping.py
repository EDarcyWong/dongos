"""Execute a real host observer beside the unchanged 0x400000 ELF address."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import unittest
import uuid
WORKS=Path(__file__).resolve().parents[2]
ROOT=WORKS if (WORKS/'lang').is_dir() else WORKS.parents[1]/'code'
sys.path.insert(0,str(ROOT))
from tools.compiler_job import host_link_flags,host_harness
from lang.tests.test_dongc import tool

SOURCE=r'''
#define _GNU_SOURCE
#define __USE_MINGW_ANSI_STDIO 1
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <sys/mman.h>
#endif
int main(int argc,char**argv){
 (void)argc;(void)argv;
 void*target=(void*)(uintptr_t)0x400000;size_t extent=2*1024*1024;
#ifdef _WIN32
 printf("IMAGE %llx\n",(unsigned long long)(uintptr_t)GetModuleHandleW(NULL));
 void*scratch=VirtualAlloc(NULL,12288,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 if(!scratch)return 20;
#endif
 unsigned char*saved=malloc(extent);if(!saved)return 20;
 for(int round=0;round<2;round++){
#ifdef _WIN32
 g5_host_release_elf_window();
 void*p=VirtualAlloc(target,extent,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
 if(p!=target){MEMORY_BASIC_INFORMATION m;DWORD error=GetLastError();
  VirtualQuery(target,&m,sizeof(m));
  printf("MAPFAIL error=%lu p=%p base=%p allocation=%p state=%lx type=%lx bytes=%llu\n",
   (unsigned long)error,p,m.BaseAddress,m.AllocationBase,(unsigned long)m.State,(unsigned long)m.Type,(unsigned long long)m.RegionSize);
  if(m.Type==MEM_IMAGE){char name[MAX_PATH];if(GetModuleFileNameA((HMODULE)m.AllocationBase,name,MAX_PATH))puts(name);}
  return 17;
 }
#else
 void*p=mmap(target,extent,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
 if(p!=target)return 17;
#endif
 volatile unsigned char*q=p;q[0]=0x5a;q[extent-1]=0xa5;
 if(q[0]!=0x5a||q[extent-1]!=0xa5)return 18;
#ifdef _WIN32
 if(!VirtualFree(p,0,MEM_RELEASE))return 19;
 g5_host_reserve_elf_window();
#else
 if(munmap(p,extent))return 19;
#endif
 saved[round]=(unsigned char)round;
 }
 free(saved);
#ifdef _WIN32
 if(!VirtualFree(scratch,0,MEM_RELEASE))return 19;
 g5_host_release_elf_window();
#endif
 puts("MAPPED 400000 bytes 2097152 rounds 2 guarded-allocation canaries 5a a5 released");return 0;
}
'''
class HostMappingTests(unittest.TestCase):
    def test_actual_host_layout_and_fixed_address_allocation(self):
        cc=tool('gcc','CC');self.assertIsNotNone(cc,'GCC required')
        work=ROOT/'build/test/G5-host'/('run-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
        source=work/'probe.c';source.write_text(host_harness(SOURCE))
        records=[]
        def run(args):
            p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=60)
            records.append(dict(command=list(map(str,args)),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
            return p
        try:
            exe=work/('good.exe' if os.name=='nt' else 'good')
            p=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*host_link_flags(),source,'-o',exe])
            self.assertEqual(p.returncode,0,p.stderr)
            raw=exe.read_bytes()
            if os.name=='nt':
                pe=struct.unpack_from('<I',raw,60)[0];self.assertEqual(raw[pe:pe+4],b'PE\0\0')
                self.assertEqual(struct.unpack_from('<H',raw,pe+24)[0],0x20b)
                image=struct.unpack_from('<Q',raw,pe+48)[0]
                extent=struct.unpack_from('<I',raw,pe+80)[0]
                self.assertTrue(image+extent<=0x400000 or image>=0xc00000)
            p=run([exe]);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertIn('MAPPED 400000 bytes 2097152 rounds 2 guarded-allocation canaries 5a a5 released',p.stdout)
            if os.name=='nt':
                actual=int(re.search(r'IMAGE ([0-9a-f]+)',p.stdout)[1],16)
                self.assertTrue(actual+extent<=0x400000 or actual>=0xc00000)
                bad=work/'bad.exe'
                linker=run([cc,'-print-prog-name=ld']);self.assertEqual(linker.returncode,0,linker.stderr)
                help_result=run([linker.stdout.strip(),'--help']);self.assertEqual(help_result.returncode,0,help_result.stderr)
                fixed=['-Wl,--image-base,0x400000']
                if '--disable-dynamicbase' in help_result.stdout:fixed.append('-Wl,--disable-dynamicbase')
                p=run([cc,'-std=c11','-O2',*fixed,source,'-o',bad])
                self.assertEqual(p.returncode,0,p.stderr)
                bad_raw=bad.read_bytes();bad_pe=struct.unpack_from('<I',bad_raw,60)[0]
                file_flags=struct.unpack_from('<H',bad_raw,bad_pe+22)[0]
                dll_flags=struct.unpack_from('<H',bad_raw,bad_pe+94)[0]
                self.assertTrue(file_flags&1 or not dll_flags&0x40,'bad host must be fixed, not ASLR relocated')
                p=run([bad]);self.assertEqual(p.returncode,17,p.stdout+p.stderr)
                self.assertIn('IMAGE 400000',p.stdout)
                # Same source/PE base, with only the initial window hold removed.
                # Real small allocations must then expose the ownership bug.
                original=source.read_text();needle=' g5_host_reserve_elf_window();\n int result='
                self.assertEqual(original.count(needle),1)
                missing=work/'missing-hold.c';missing.write_text(original.replace(needle,' int result=',1))
                missing_exe=work/'missing-hold.exe'
                p=run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',*host_link_flags(),missing,'-o',missing_exe])
                self.assertEqual(p.returncode,0,p.stderr)
                p=run([missing_exe]);self.assertEqual(p.returncode,17,p.stdout+p.stderr)
                self.assertIn('IMAGE 10000000',p.stdout)
                self.assertIn('MAPFAIL',p.stdout)
                (work/'missing-hold.sha256').write_text(hashlib.sha256(missing.read_bytes()).hexdigest()+'\n')
            (work/'source.sha256').write_text(hashlib.sha256(source.read_bytes()).hexdigest()+'\n')
        finally:
            (work/'processes.json').write_text(json.dumps(records,indent=2)+'\n')
if __name__=='__main__':unittest.main()
