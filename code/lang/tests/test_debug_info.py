"""Real source debugging of generated Dong code with the installed native GDB.

Run ``python -m unittest lang.tests.test_debug_info -v``.  Host-only: one small
native executable, no operating-system image, QEMU, download or guest mutation.
The actual GDB transcript and exact inputs are retained in build/test/l2-debug.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import unittest
from unittest import mock

from lang.dongc import compile_source, compile_file
from lang.dongc.debug_info import uleb, sleb, logical_path, adapt_coff_debug
from lang.dongc import debug_info as debug_module
from tools.build import find_tool


ROOT = Path(__file__).resolve().parents[2]
SOURCE = '''module debug_probe;
align(64) struct Aligned { value: u64 }
fn leaf(a: u64, b: u64) u64 {
    var sum: u64 = a + b;
    sum += 1;
    return sum;
}
fn nested(seed: u64) u64 {
    let outer: u64 = seed + 2;
    let result: u64 = leaf(outer, 3);
    return result;
}
export("dbg_entry") fn entry(seed: u64) u64 {
    return nested(seed);
}
export("dbg_shadow") fn shadow(seed: u64) u64 {
    let value: u64 = seed;
    { let value: u64 = 77;
      unsafe { asm { pause } }
    }
    return value;
}
export("dbg_aligned") fn aligned(seed: u64) u64 {
    let record: Aligned = Aligned { value: seed + 9 };
    let marker: u64 = leaf(record.value, 1);
    return marker + record.value;
}
export("dbg_uninitialised") fn uninitialised(flag: bool) u64 {
    var missing: u64;
    if flag { missing = 99; }
    return 4;
}
extern "win64" export("dbg_windows") fn windows(seed: u64) u64 {
    let winlocal: u64 = seed + 6;
    return leaf(winlocal, 2);
}
var COUNTER: u64 = 321;
fn stack_arguments(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64 {
    return a+h;
}
export("dbg_extras") fn extras()u64 {
    let values:[3]u64=[7,8,9];
    let view:[]const u64=values[..];
    var total:u64=0;
    for index in 0..3 {
        total+=view[index];
    }
    let optional:?u64=42;
    match optional {
        some(payload)=>{ total+=payload; },
        null=>{ total+=100; },
    }
    let tail=stack_arguments(1,2,3,4,5,6,7,8);
    return total+tail+COUNTER;
}
export("dbg_missing_shadow") fn missing_shadow(seed:u64)u64 {
    let value:u64=seed+45;
    {
        unsafe { asm { pause } } // BEFORE_UNINITIALISED_SHADOW
        var value:u64;
        var hidden:u64;
        unsafe { asm { pause } } // UNINITIALISED_SHADOW
    }
    return value;
}
'''


def invoke(args, cwd, name, timeout=40):
    result = subprocess.run([str(arg) for arg in args],cwd=cwd,capture_output=True,text=True,
        encoding="utf-8",errors="replace",timeout=timeout)
    (cwd/(name+".stdout.txt")).write_text(result.stdout,encoding="utf-8")
    (cwd/(name+".stderr.txt")).write_text(result.stderr,encoding="utf-8")
    if result.returncode:
        raise AssertionError(f"{name} failed {result.returncode}: {result.stdout[-2500:]} {result.stderr[-2500:]}")
    return result.stdout+result.stderr


class DebugInfoUnitTests(unittest.TestCase):
    def test_only_windows_wrapper_claims_nonvolatile_argument_saves(self):
        instances=[]
        class Capture(debug_module.DebugInfo):
            def __init__(self,*args):
                super().__init__(*args)
                instances.append(self)
        with mock.patch.object(debug_module,"DebugInfo",Capture):
            compile_source(SOURCE,path="debug_probe.dg",debug_info=True)
        debug=instances[0]
        bodies={record["start"] for record in debug.functions}
        saved_frames=[]
        for frame in debug.frames:
            saved=any(cfi[:1] in {b"\x84",b"\x85"} for _,cfi in frame.cfi)
            if saved: saved_frames.append(frame.start)
            if frame.start in bodies: self.assertFalse(saved,"SysV parameter home misreported as saved caller register")
        self.assertEqual(len(saved_frames),1)

    def test_explicit_only_and_identical_machine_instructions(self):
        plain = compile_source(SOURCE,path="debug_probe.dg")
        explicit_false = compile_source(SOURCE,path="debug_probe.dg",debug_info=False)
        detailed = compile_source(SOURCE,path="debug_probe.dg",debug_info=True)
        self.assertEqual(plain.assembly,explicit_false.assembly)
        self.assertNotIn(".debug_info",plain.assembly)
        def instructions(text):
            return [line.strip() for line in text.split("section .debug_info",1)[0].splitlines()
                    if line.startswith("    ") and not line.lstrip().startswith(";")]
        # Conditional section directives are outside instructions and follow code.
        self.assertEqual(instructions(plain.assembly),instructions(detailed.assembly))

    def test_reproducible_logical_paths(self):
        self.assertEqual(logical_path(r"C:\\private\\source\\probe.dg"),"probe.dg")
        self.assertEqual(logical_path("/private/source/probe.dg"),"probe.dg")
        self.assertEqual(logical_path("one/two.dg"),"one/two.dg")

    def test_reproducible_debug_unit_under_different_absolute_roots(self):
        one=compile_source(SOURCE,path="C:/build-one/debug_probe.dg",debug_info=True)
        two=compile_source(SOURCE,path="D:/different/build/debug_probe.dg",debug_info=True)
        # Runtime panic's file-name payload deliberately retains its old contract.
        # The new debug contribution itself contains no absolute build directory.
        debug=lambda result:result.assembly[result.assembly.index("section .debug_info"):]
        self.assertEqual(debug(one),debug(two))

    def test_multimodule_root_relocation_is_byte_reproducible(self):
        outputs=[]
        for name in ("repo-one","repo-two"):
            root=ROOT/"build/test/l2-debug"/name
            root.mkdir(parents=True,exist_ok=True)
            (root/"entry.dg").write_text('module entry; import helper; export("call_debug") fn call(value:u64)u64{return helper.twice(value);}',encoding="utf-8")
            (root/"helper.dg").write_text('module helper; pub fn twice(value:u64)u64{return value*2;}',encoding="utf-8")
            outputs.append(compile_file(root/"entry.dg",roots=[root],debug_info=True).assembly)
        self.assertEqual(*outputs)

    def test_leb_encodings(self):
        self.assertEqual(uleb(624485),bytes.fromhex("e58e26"))
        self.assertEqual(sleb(-624485),bytes.fromhex("9bf159"))
        with self.assertRaises(ValueError): uleb(-1)

    def test_coff_adapter_rejects_invalid_objects(self):
        for blob in (b"",b"x"*50,b"\x64\x86"+b"\0"*18):
            with self.assertRaises(ValueError): adapt_coff_debug(blob)


class GdbSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gdb_exe=shutil.which("gdb")
        cls.gcc=shutil.which("gcc")
        if not cls.gdb_exe or not cls.gcc:
            raise unittest.SkipTest("native GDB/GCC unavailable; source-debug acceptance not claimed")
        cls.work=ROOT/"build/test/l2-debug"
        cls.work.mkdir(parents=True,exist_ok=True)
        cls.source=cls.work/"debug_probe.dg"
        cls.source.write_text(SOURCE,encoding="utf-8",newline="\n")
        cls.compilation=compile_file(cls.source,mode="debug",debug_info=True)
        cls.asm=cls.work/"debug_probe.asm"
        cls.asm.write_text(cls.compilation.assembly,encoding="utf-8")
        cls.nasm=find_tool("nasm","NASM")
        cls.windows=os.name=="nt"
        cls.obj=cls.work/("debug_probe.obj" if cls.windows else "debug_probe.o")
        cls.exe=cls.work/("debug_probe.exe" if cls.windows else "debug_probe")
        cls.import_root=cls.work/"imports"
        cls.import_root.mkdir(exist_ok=True)
        (cls.import_root/"import_probe.dg").write_text('''module import_probe;
import helper;
export("dbg_import") fn invoke(value:u64)u64 {
    let local=helper.twice(value);
    return local+1;
}
''',encoding="utf-8")
        (cls.import_root/"helper.dg").write_text('''module helper;
pub fn twice(value:u64)u64 {
    let doubled=value*2;
    return doubled;
}
''',encoding="utf-8")
        imported=compile_file(cls.import_root/"import_probe.dg",roots=[cls.import_root],debug_info=True)
        cls.import_asm=cls.work/"imported.asm"
        cls.import_asm.write_text(imported.assembly,encoding="utf-8")
        cls.import_obj=cls.work/("imported.obj" if cls.windows else "imported.o")
        invoke([cls.nasm,"-f","win64" if cls.windows else "elf64","-o",cls.import_obj,cls.import_asm],cls.work,"assemble-imports")
        if cls.windows: cls.import_obj.write_bytes(adapt_coff_debug(cls.import_obj.read_bytes()))
        cls.c=cls.work/"host.c"
        cls.c.write_text('''#include <stdint.h>
#include <stdlib.h>
#ifdef _WIN32
#define SYSV __attribute__((sysv_abi))
#else
#define SYSV
#endif
extern uint64_t SYSV dbg_entry(uint64_t);
extern uint64_t SYSV dbg_shadow(uint64_t);
extern uint64_t SYSV dbg_aligned(uint64_t);
extern uint64_t SYSV dbg_uninitialised(uint8_t);
extern uint64_t SYSV dbg_extras(void);
extern uint64_t SYSV dbg_import(uint64_t);
extern uint64_t SYSV dbg_missing_shadow(uint64_t);
#ifdef _WIN32
extern uint64_t dbg_windows(uint64_t);
#else
extern uint64_t __attribute__((ms_abi)) dbg_windows(uint64_t);
#endif
void SYSV __dong_panic(uint64_t a,uint64_t b,void*c,uint64_t d){abort();}
int main(int argc,char**argv){
  uint64_t mode=argc>1?strtoull(argv[1],0,10):0, value=0;
  if(mode==1)value=dbg_shadow(10);
  else if(mode==2)value=dbg_aligned(10);
  else if(mode==3)value=dbg_uninitialised(0);
  else if(mode==4)value=dbg_windows(10);
  else if(mode==5)value=dbg_extras();
  else if(mode==6)value=dbg_import(10);
  else if(mode==7)value=dbg_missing_shadow(10);
  else value=dbg_entry(10);
  return value==(mode==1?10:mode==2?40:mode==3?4:mode==4?19:mode==5?396:mode==6?21:mode==7?55:16)?0:1;
}
''',encoding="utf-8")
        invoke([cls.nasm,"-f","win64" if cls.windows else "elf64","-o",cls.obj,cls.asm],cls.work,"nasm")
        if cls.windows:
            raw=cls.obj.read_bytes()
            (cls.work/"debug_probe.nasm.obj").write_bytes(raw)
            cls.obj.write_bytes(adapt_coff_debug(raw))
        invoke([cls.gcc,"-g","-O0","-fno-omit-frame-pointer","-o",cls.exe,cls.c,cls.obj,cls.import_obj],cls.work,"link")
        for mode in range(8):
            invoke([cls.exe,str(mode)],cls.work,"native-mode-"+str(mode))
        cls.evidence={"source_sha256":hashlib.sha256(cls.source.read_bytes()).hexdigest(),
            "assembly_sha256":hashlib.sha256(cls.asm.read_bytes()).hexdigest(),
            "executable_sha256":hashlib.sha256(cls.exe.read_bytes()).hexdigest(),"gdb":cls.gdb_exe,
            "gcc":cls.gcc,"nasm":cls.nasm,"tests":[]}
        cls.evidence["module_sha256"]=hashlib.sha256(Path(debug_module.__file__).read_bytes()).hexdigest()
        cls.elf_obj=cls.work/"debug_probe.elf.o"
        invoke([cls.nasm,"-f","elf64","-o",cls.elf_obj,cls.asm],cls.work,"assemble-elf")
        panic=cls.work/"panic.asm"
        panic.write_text("bits 64\nsection .text\nglobal __dong_panic\n__dong_panic: ud2\nsection .note.GNU-stack noalloc noexec nowrite progbits\n",encoding="utf-8")
        panic_obj=cls.work/"panic.elf.o"
        invoke([cls.nasm,"-f","elf64","-o",panic_obj,panic],cls.work,"assemble-elf-panic")
        cls.elf=cls.work/"debug_probe.elf"
        invoke([find_tool("ld.lld","LD_LLD"),"-Ttext=0x401000","-e","dbg_entry","-o",cls.elf,cls.elf_obj,panic_obj],cls.work,"link-elf")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"evidence"):
            (cls.work/"evidence.json").write_text(json.dumps(cls.evidence,indent=2)+"\n",encoding="utf-8")

    def gdb(self,name,commands,mode=0,exe=None):
        script=self.work/(name+".gdb")
        prelude=["set pagination off","set confirm off","set print pretty off","set language c",
            "set width 0", "directory "+self.work.as_posix(),"directory "+self.import_root.as_posix(),
            "file "+(exe or self.exe).as_posix(),"set args "+str(mode)]
        script.write_text("\n".join(prelude+commands+["quit"])+"\n",encoding="utf-8")
        output=invoke([self.gdb_exe,"-nx","-batch","-x",script],self.work,name)
        self.evidence["tests"].append({"name":name,"output_sha256":hashlib.sha256(output.encode()).hexdigest()})
        return output

    def test_source_break_step_parameters_locals_and_backtrace(self):
        output=self.gdb("source-step",["break debug_probe.dg:10","run","print outer","step","next","next","next",
            'printf "DG_VALUES=%llu,%llu,%llu\\n", a,b,sum',"backtrace","info line"])
        self.assertIn("DG_VALUES=12,3,16",output)
        self.assertRegex(output,r"#0\s+.*leaf")
        self.assertRegex(output,r"#1\s+.*nested")
        self.assertRegex(output,r"#2\s+.*entry")
        self.assertIn("debug_probe.dg:6",output)
        self.assertIn("$1 = 12",output)

    def test_shadow_scope(self):
        output=self.gdb("shadow",["break debug_probe.dg:19","run","print value","next","print value"],1)
        self.assertIn("$1 = 77",output)
        self.assertIn("$2 = 10",output)

    def test_realigned_locals_and_unwind(self):
        output=self.gdb("realigned",["break debug_probe.dg:6","run","backtrace","up","print record.value","print seed"],2)
        self.assertRegex(output,r"#1\s+.*aligned")
        self.assertIn("$1 = 19",output)
        self.assertIn("$2 = 10",output)

    def test_uninitialised_location_is_unavailable(self):
        output=self.gdb("uninitialised",["break debug_probe.dg:31","run","info locals"],3)
        self.assertRegex(output,r"missing = <(optimized out|unavailable)>")

    def test_uninitialised_shadow_hides_outer_live_value(self):
        line=self.line("UNINITIALISED_SHADOW")
        before=self.line("BEFORE_UNINITIALISED_SHADOW")
        # The marker for the inner statement must not accidentally choose the
        # BEFORE_ marker when matching the substring.
        line=next(i for i,text in enumerate(SOURCE.splitlines(),1) if "// UNINITIALISED_SHADOW" in text)
        output=self.gdb("uninitialised-shadow",[f"break debug_probe.dg:{before}","run","print value","next","print value","next","print value",
            'printf "DG_OUTSIDE_SCOPE\\n"',"info locals"],7)
        self.assertIn("$1 = 55",output)
        self.assertRegex(output,r"\$2 = <(optimized out|unavailable)>")
        self.assertIn("$3 = 55",output)
        outside=output.split("DG_OUTSIDE_SCOPE\n",1)[-1]
        self.assertNotRegex(outside,r"\bhidden\b")

    def test_windows_bridge_unwind_and_local(self):
        output=self.gdb("windows-bridge",["break debug_probe.dg:6","run","backtrace","up","print winlocal"],4)
        self.assertRegex(output,r"#1\s+.*windows")
        self.assertIn("$1 = 16",output)

    def test_imported_source_breakpoint_and_cross_module_backtrace(self):
        output=self.gdb("imported-source",["break helper.dg:4","run","print doubled","print value","backtrace"],6)
        self.assertIn("$1 = 20",output)
        self.assertIn("$2 = 10",output)
        self.assertRegex(output,r"#0\s+.*twice.*helper.dg:4")
        self.assertRegex(output,r"#1\s+.*invoke.*import_probe.dg:4")

    @staticmethod
    def elf_sections(path):
        blob=path.read_bytes()
        if blob[:5]!=b"\x7fELF\x02": raise AssertionError("not ELF64")
        offset=struct.unpack_from("<Q",blob,40)[0]
        size,count,names=struct.unpack_from("<HHH",blob,58)
        headers=[struct.unpack_from("<IIQQQQIIQQ",blob,offset+size*i) for i in range(count)]
        strings=blob[headers[names][4]:headers[names][4]+headers[names][5]]
        result={}
        for header in headers:
            end=strings.find(b"\0",header[0])
            name=strings[header[0]:end].decode()
            result[name]=(header,blob[header[4]:header[4]+header[5]])
        return result

    def test_elf_dwarf_readback_and_identical_text(self):
        sections=self.elf_sections(self.elf)
        for name in (".debug_info",".debug_abbrev",".debug_line",".debug_loc",".debug_frame"):
            self.assertIn(name,sections)
            self.assertFalse(sections[name][0][2]&2,name+" unexpectedly ALLOC")
        readelf=shutil.which("readelf")
        if readelf:
            output=invoke([readelf,"--debug-dump=info,decodedline,frames",self.elf],self.work,"readelf-dwarf")
            for expected in ("DW_TAG_formal_parameter","DW_TAG_lexical_block","DW_TAG_array_type","DW_CFA_def_cfa_register","debug_probe.dg"):
                self.assertIn(expected,output)
            self.assertNotIn("Warning:",output)
            self.assertNotIn("Error:",output)
        plain=compile_file(self.source,mode="debug",debug_info=False)
        asm=self.work/"plain.asm"
        obj=self.work/"plain.elf.o"
        asm.write_text(plain.assembly,encoding="utf-8")
        invoke([self.nasm,"-f","elf64","-o",obj,asm],self.work,"assemble-plain")
        self.assertEqual(self.elf_sections(obj)[".text"][1],self.elf_sections(self.elf_obj)[".text"][1])
        self.evidence["elf_sha256"]=hashlib.sha256(self.elf.read_bytes()).hexdigest()

    def test_release_debug_information_executes_and_debugs(self):
        result=compile_file(self.source,mode="release",debug_info=True)
        asm=self.work/"release.asm"
        obj=self.work/("release.obj" if self.windows else "release.o")
        exe=self.work/("release.exe" if self.windows else "release")
        asm.write_text(result.assembly,encoding="utf-8")
        invoke([self.nasm,"-f","win64" if self.windows else "elf64","-o",obj,asm],self.work,"release-assemble")
        if self.windows: obj.write_bytes(adapt_coff_debug(obj.read_bytes()))
        invoke([self.gcc,"-g","-O0","-fno-omit-frame-pointer","-o",exe,self.c,obj,self.import_obj],self.work,"release-link")
        for mode in range(8): invoke([exe,str(mode)],self.work,"release-native-"+str(mode))
        output=self.gdb("release-gdb",["break debug_probe.dg:6","run",'printf "RELEASE=%llu,%llu,%llu\\n",a,b,sum',"backtrace"],exe=exe)
        self.assertIn("RELEASE=12,3,16",output)
        self.assertRegex(output,r"#2\s+.*entry")

    @staticmethod
    def line(containing):
        return next(index for index,line in enumerate(SOURCE.splitlines(),1) if containing in line)

    def test_arrays_slices_globals_stack_arguments_and_implicit_bindings(self):
        body=self.line("total+=view[index]")
        match=self.line("some(payload)")
        stack=self.line("return a+h")
        output=self.gdb("aggregates",[f"break debug_probe.dg:{body}","run","print index",
            "print values[1]","print view.len","print COUNTER","disable 1",
            f"break debug_probe.dg:{match}","continue","print payload","disable 2",
            f"break debug_probe.dg:{stack}","continue","print a","print h","backtrace"],5)
        for expected in ("$1 = 0","$2 = 8","$3 = 3","$4 = 321","$5 = 42","$6 = 1","$7 = 8"):
            self.assertIn(expected,output)
        self.assertRegex(output,r"#1\s+.*extras")

    def test_real_bad_debug_sources_are_rejected(self):
        original=Path(debug_module.__file__).read_text(encoding="utf-8")
        controls={
            "bad-location":("sleb(-offset)","sleb(-offset + 8)"),
            "bad-line":("sleb(line_no-previous_line)","sleb(line_no+1-previous_line)"),
            "bad-cfa":("cfi = bytes([0x0d, 6])","cfi = bytes([0x0d, 7])"),
        }
        rows=[]
        for name,(old,new) in controls.items():
            self.assertEqual(original.count(old),1)
            directory=self.work/name
            directory.mkdir(exist_ok=True)
            source=directory/"debug_info.py"
            source.write_text(original.replace(old,new),encoding="utf-8")
            module_name="lang.dongc._"+name.replace("-","_")
            spec=importlib.util.spec_from_file_location(module_name,source)
            changed=importlib.util.module_from_spec(spec)
            sys.modules[module_name]=changed
            spec.loader.exec_module(changed)
            with mock.patch.object(debug_module,"DebugInfo",changed.DebugInfo):
                result=compile_file(self.source,mode="debug",debug_info=True)
            asm=directory/"program.asm"
            asm.write_text(result.assembly,encoding="utf-8")
            obj=directory/("program.obj" if self.windows else "program.o")
            exe=directory/("program.exe" if self.windows else "program")
            invoke([self.nasm,"-f","win64" if self.windows else "elf64","-o",obj,asm],directory,"assemble")
            if self.windows: obj.write_bytes(adapt_coff_debug(obj.read_bytes()))
            invoke([self.gcc,"-g","-O0","-fno-omit-frame-pointer","-o",exe,self.c,obj,self.import_obj],directory,"link")
            invoke([exe],directory,"native-normal-execution")
            script=directory/"reject.gdb"
            script.write_text("\n".join(["set pagination off","set confirm off","set language c","directory "+self.work.as_posix(),
                "file "+exe.as_posix(),"break debug_probe.dg:6","run",
                'printf "DG_VALUES=%llu,%llu,%llu\\n", a,b,sum',"backtrace","info line","quit"])+"\n",encoding="utf-8")
            process=subprocess.run([self.gdb_exe,"-nx","-batch","-x",str(script)],cwd=directory,
                capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30)
            output=process.stdout+process.stderr
            (directory/"gdb.txt").write_text(output,encoding="utf-8")
            # A missing debugger, bad executable, failed breakpoint, or generic
            # environment error is a test FAILURE, never a successful negative.
            self.assertRegex(output,r"hit Breakpoint 1, leaf ",name)
            self.assertIn("DG_VALUES=",output,name)
            if name == "bad-line":
                self.assertIn("value has been optimized out",output)
            else:
                self.assertEqual(process.returncode,0,output)
            if name == "bad-cfa":
                self.assertIn("DG_VALUES=12,3,16",output)
                self.assertIn("#1",output)
                self.assertNotRegex(output,r"#1\s+.*nested")
            if name == "bad-location":
                self.assertRegex(output,r"#1\s+.*nested")
                self.assertNotIn("DG_VALUES=12,3,16",output)
            accepted=(process.returncode==0 and "DG_VALUES=12,3,16" in output and
                re.search(r"#0\s+.*leaf",output) and re.search(r"#1\s+.*nested",output) and
                re.search(r"#2\s+.*entry",output) and 'Line 6 of "debug_probe.dg"' in output)
            self.assertFalse(accepted,name+" wrong DWARF passed the real source-debug oracle")
            rows.append({"name":name,"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
                "assembly_sha256":hashlib.sha256(asm.read_bytes()).hexdigest(),"returncode":process.returncode,"rejected":True})
        self.evidence["bad_source_controls"]=rows


if __name__=="__main__": unittest.main()
