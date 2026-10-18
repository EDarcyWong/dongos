"""Independent SysV function values and Microsoft callback bridge probes."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from lang.tests.test_globals_native import static_relocation_types


DEFINITIONS = '''module function_defs;
pub type Unary=fn(value:u64)u64;
pub type Pair=fn(a:u64,b:u64)u64;
pub type SysvNarrow=unsafe extern "sysv64" fn(a:i8,b:u16,c:i16,d:u32,e:i8,f:u16,g:i32,h:u64)i64;
pub type WinNarrow=unsafe extern "win64" fn(a:i8,b:u16,c:i16,d:u32,e:i8,f:u16,g:i32,h:u64)i64;
pub type SliceCall=unsafe extern "sysv64" fn(a:u64,b:u64,c:u64,d:u64,e:u64,s:[]u64,z:u64)u64;
pub type SliceReturn=unsafe extern "sysv64" fn(a:u64,b:u64,c:u64,d:u64,e:u64,s:[]u64,z:u64)[]u64;
pub fn increment(value:u64)u64{return value+1;}
pub fn double(value:u64)u64{return value*2;}
pub struct Dispatch{pub call:Unary}
pub var dispatch:Dispatch=Dispatch{call:increment};
pub const callbacks:[2]Unary=[increment,double];
pub const imported:Unary=increment;
pub var selected:Unary=increment;
pub var events:u64=0;
pub fn initial(value:u64)u64{events=events*10+3;return value+100;}
pub fn replacement(value:u64)u64{events=events*10+4;return value+200;}
pub fn select()Unary{events=events*10+1;return selected;}
pub fn argument()u64{events=events*10+2;selected=replacement;return 7;}
pub var pair:Pair=pair_initial;
pub fn pair_initial(a:u64,b:u64)u64{events=events*10+4;return 100+a*10+b;}
pub fn pair_replacement(a:u64,b:u64)u64{events=events*10+5;return 200+a*10+b;}
pub fn pair_factory()Pair{events=events*10+1;return pair;}
pub fn first_argument()u64{events=events*10+2;pair=pair_replacement;return 7;}
pub fn second_argument()u64{events=events*10+3;return 8;}
pub unsafe fn local_slice(a:u64,b:u64,c:u64,d:u64,e:u64,s:[]u64,z:u64)u64{
    return a+b*2+c*3+d*4+e*5+s.len*100+s[0]+z*1000;
}
pub unsafe fn local_tail(a:u64,b:u64,c:u64,d:u64,e:u64,s:[]u64,z:u64)[]u64{return s[1..];}
'''


SOURCE = '''module function_probe;
import function_defs as d;
const IMPORTED:d.Unary=d.increment;
type Callback=extern "win64" fn(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64;
align(64) struct Block{value:u64}
extern "sysv64" fn function_clobber(p:*const Block,expected:u64)u64;
export("function_fields") fn fields(value:u64)u64{unsafe{return d.dispatch.call(value)+d.callbacks[1](value)+d.imported(value)+IMPORTED(value);}}
export("function_get_imported") fn get_imported()d.Unary{return IMPORTED;}
export("function_get_selected") fn get_selected()d.Unary{return d.selected;}
export("function_factory_snapshot") fn factory_snapshot()u64{
    d.selected=d.initial;d.events=0;
    unsafe{let result=d.select()(d.argument());return result*1000+d.events;}
}
export("function_global_snapshot") fn global_snapshot()u64{
    d.selected=d.initial;d.events=0;
    unsafe{let result=d.selected(d.argument());return result*1000+d.events;}
}
export("function_argument_order") fn argument_order()u64{
    d.pair=d.pair_initial;d.events=0;
    unsafe{let result=d.pair_factory()(d.first_argument(),d.second_argument());return result*10000+d.events;}
}
export("function_sysv8") fn call_sysv(p:d.SysvNarrow)i64{
    unsafe{return p(-7,50000,-1234,3000000000,-3,60000,-2000000,9);}
}
export("function_win8") fn call_win(p:d.WinNarrow)i64{
    unsafe{return p(-7,50000,-1234,3000000000,-3,60000,-2000000,9);}
}
export("function_slice") fn call_slice(p:d.SliceCall,s:[]u64)u64{
    unsafe{return p(1,2,3,4,5,s,9);}
}
export("function_local_slice") fn call_local_slice(s:[]u64)u64{
    let p:d.SliceCall=d.local_slice;
    unsafe{return p(1,2,3,4,5,s,9);}
}
export("function_slice_return") fn call_slice_return(p:d.SliceReturn,s:[]u64)[]u64{
    unsafe{return p(1,2,3,4,5,s,9);}
}
export("function_local_tail") fn call_local_tail(s:[]u64)[]u64{
    let p:d.SliceReturn=d.local_tail;
    unsafe{return p(1,2,3,4,5,s,9);}
}
export("function_callback") extern "win64" fn callback(a:u64,b:u64,c:u64,d:u64,e:u64,f:u64,g:u64,h:u64)u64{
    let aligned=Block{value:a+b*2+c*3+d*4+e*5+f*6+g*7+h*8};
    unsafe{return function_clobber(&aligned,204);}
}
export("function_callback_narrow") extern "win64" fn callback_narrow(a:i8,b:u16,c:i16,d:u32,e:i8,f:u16,g:i32,h:u64)i64{
    return a as i64+(b as i64)*2+(c as i64)*3+(d as i64)*4+(e as i64)*5+(f as i64)*6+(g as i64)*7+(h as i64)*8;
}
const CALLBACK:Callback=callback;
export("function_get_callback") fn get_callback()Callback{return CALLBACK;}
'''


HARNESS = r'''
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define DG __attribute__((sysv_abi))
#define WIN __attribute__((ms_abi))
struct Slice{uint64_t *ptr;uint64_t len;};
typedef uint64_t (DG *Unary)(uint64_t);
typedef int64_t (DG *SysvNarrow)(int8_t,uint16_t,int16_t,uint32_t,int8_t,uint16_t,int32_t,uint64_t);
typedef int64_t (WIN *WinNarrow)(int8_t,uint16_t,int16_t,uint32_t,int8_t,uint16_t,int32_t,uint64_t);
typedef uint64_t (DG *SliceCall)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,struct Slice,uint64_t);
typedef struct Slice (DG *SliceReturn)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,struct Slice,uint64_t);
typedef uint64_t (WIN *Callback)(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
extern uint64_t DG function_fields(uint64_t),function_factory_snapshot(void),function_global_snapshot(void),function_argument_order(void),function_bridge_probe(void);
extern Unary DG function_get_imported(void),function_get_selected(void);
extern int64_t DG function_sysv8(SysvNarrow),function_win8(WinNarrow);
extern uint64_t DG function_slice(SliceCall,struct Slice),function_local_slice(struct Slice);
extern struct Slice DG function_slice_return(SliceReturn,struct Slice),function_local_tail(struct Slice);
extern Callback DG function_get_callback(void);
extern uint64_t WIN function_callback(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
extern int64_t WIN function_callback_narrow(int8_t,uint16_t,int16_t,uint32_t,int8_t,uint16_t,int32_t,uint64_t);
extern int64_t DG function_asm_sysv8(int8_t,uint16_t,int16_t,uint32_t,int8_t,uint16_t,int32_t,uint64_t);
extern int64_t WIN function_asm_win8(int8_t,uint16_t,int16_t,uint32_t,int8_t,uint16_t,int32_t,uint64_t);
extern uint64_t DG function_asm_slice(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,struct Slice,uint64_t);
extern struct Slice DG function_asm_slice_return(uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,struct Slice,uint64_t);
int64_t DG function_c_sysv8(int8_t a,uint16_t b,int16_t c,uint32_t d,int8_t e,uint16_t f,int32_t g,uint64_t h){
    return (int64_t)a+(int64_t)b*2+(int64_t)c*3+(int64_t)d*4+(int64_t)e*5+(int64_t)f*6+(int64_t)g*7+(int64_t)h*8;
}
int64_t WIN function_c_win8(int8_t a,uint16_t b,int16_t c,uint32_t d,int8_t e,uint16_t f,int32_t g,uint64_t h){
    return (int64_t)a+(int64_t)b*2+(int64_t)c*3+(int64_t)d*4+(int64_t)e*5+(int64_t)f*6+(int64_t)g*7+(int64_t)h*8;
}
uint64_t DG function_c_slice(uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,struct Slice s,uint64_t z){
    return a+b*2+c*3+d*4+e*5+s.len*100+s.ptr[0]+z*1000;
}
struct Slice DG function_c_slice_return(uint64_t a,uint64_t b,uint64_t c,uint64_t d,uint64_t e,struct Slice s,uint64_t z){
    if(a!=1 || b!=2 || c!=3 || d!=4 || e!=5 || z!=9){struct Slice empty={NULL,0};return empty;}
    struct Slice tail={s.ptr+1,s.len-1};return tail;
}
void DG __attribute__((noreturn)) function_panic_record(uint32_t kind,uint32_t line,const uint8_t *file,uint64_t length){
    fprintf(stderr,"unexpected function panic kind=%u line=%u file=%.*s\n",kind,line,(int)length,(const char *)file);exit(99);
}
#define CHECK(X) do{if(!(X)){fprintf(stderr,"function check failed at %d: %s\n",__LINE__,#X);return 1;}}while(0)
int main(void){
    CHECK(function_fields(7)==5*7+3);
    Unary imported=function_get_imported();CHECK(imported!=NULL && imported(41)==42);
    CHECK(function_factory_snapshot()==107123);
    CHECK(function_global_snapshot()==107023);
    CHECK(function_argument_order()==1781234);
    Unary selected=function_get_selected();CHECK(selected!=NULL && selected(7)==207);
    const int64_t expected=-INT64_C(7)+50000*2-1234*3+INT64_C(3000000000)*4-3*5+60000*6-2000000*7+9*8;
    CHECK(expected==INT64_C(11986456348));
    CHECK(function_sysv8(function_asm_sysv8)==expected && function_sysv8(function_c_sysv8)==expected);
    CHECK(function_win8(function_asm_win8)==expected && function_win8(function_c_win8)==expected);
    uint64_t values[]={11,22,33};struct Slice slice={values,3};
    CHECK(function_slice(function_asm_slice,slice)==9366 && function_slice(function_c_slice,slice)==9366);
    CHECK(function_local_slice(slice)==9366);
    struct Slice tail=function_slice_return(function_c_slice_return,slice);CHECK(tail.ptr==values+1 && tail.len==2);
    tail=function_slice_return(function_asm_slice_return,slice);CHECK(tail.ptr==values+1 && tail.len==2);
    tail=function_local_tail(slice);CHECK(tail.ptr==values+1 && tail.len==2);
    CHECK(function_callback(1,2,3,4,5,6,7,8)==204);
    Callback callback=function_get_callback();CHECK(callback!=NULL && callback(1,2,3,4,5,6,7,8)==204);
    CHECK(function_callback_narrow(-7,50000,-1234,UINT32_C(3000000000),-3,60000,-2000000,9)==expected);
    CHECK(function_bridge_probe()==1);
    puts("native function values, indirect ABI calls and Win64 callback preservation passed");return 0;
}
'''


def observer_source():
    lines = [r'''
bits 64
default rel
section .text
global __dong_panic
global function_clobber
global function_asm_sysv8
global function_asm_win8
global function_asm_slice
global function_asm_slice_return
global function_bridge_probe
extern function_panic_record
extern function_callback
extern function_callback_narrow
__dong_panic:
    jmp function_panic_record
function_clobber:
    mov rax,rsp
    and eax,15
    cmp eax,8
    jne .failed
    test rdi,63
    jnz .failed
    cmp qword [rdi],204
    jne .failed
    cmp rsi,204
    jne .failed
    mov eax,204
    jmp .clobber
.failed:
    xor eax,eax
.clobber:
    mov rdi,0xdeadbeefdeadbeef
    mov rsi,0xfedcba9876543210
''']
    for register in range(6, 16):
        lines.append(f"    pxor xmm{register},xmm{register}")
    lines.append(r'''
    ret
function_asm_sysv8:
    mov r10,rsp
    and r10d,15
    cmp r10d,8
    jne .failed
    movsx rax,dil
    movzx r10,si
    imul r10,r10,2
    add rax,r10
    movsx r10,dx
    imul r10,r10,3
    add rax,r10
    mov r10d,ecx
    imul r10,r10,4
    add rax,r10
    movsx r10,r8b
    imul r10,r10,5
    add rax,r10
    movzx r10,r9w
    imul r10,r10,6
    add rax,r10
    movsxd r10,dword [rsp+8]
    imul r10,r10,7
    add rax,r10
    mov r10,qword [rsp+16]
    imul r10,r10,8
    add rax,r10
    ret
.failed:
    mov rax,0x8000000000000000
    ret
function_asm_win8:
    mov r10,rsp
    and r10d,15
    cmp r10d,8
    jne .failed
    mov qword [rsp+8],0x11111111
    mov qword [rsp+16],0x22222222
    mov qword [rsp+24],0x33333333
    mov qword [rsp+32],0x44444444
    movsx rax,cl
    movzx r10,dx
    imul r10,r10,2
    add rax,r10
    movsx r10,r8w
    imul r10,r10,3
    add rax,r10
    mov r10d,r9d
    imul r10,r10,4
    add rax,r10
    movsx r10,byte [rsp+40]
    imul r10,r10,5
    add rax,r10
    movzx r10,word [rsp+48]
    imul r10,r10,6
    add rax,r10
    movsxd r10,dword [rsp+56]
    imul r10,r10,7
    add rax,r10
    mov r10,qword [rsp+64]
    imul r10,r10,8
    add rax,r10
    ret
.failed:
    mov rax,0x8000000000000000
    ret
function_asm_slice:
    mov r10,rsp
    and r10d,15
    cmp r10d,8
    jne .failed
    cmp rdi,1
    jne .failed
    cmp rsi,2
    jne .failed
    cmp rdx,3
    jne .failed
    cmp rcx,4
    jne .failed
    cmp r8,5
    jne .failed
    cmp r9,9
    jne .failed
    mov r10,qword [rsp+8]
    cmp qword [r10],11
    jne .failed
    cmp qword [rsp+16],3
    jne .failed
    mov eax,9366
    ret
.failed:
    xor eax,eax
    ret
function_asm_slice_return:
    mov r10,rsp
    and r10d,15
    cmp r10d,8
    jne .failed
    cmp rdi,1
    jne .failed
    cmp rsi,2
    jne .failed
    cmp rdx,3
    jne .failed
    cmp rcx,4
    jne .failed
    cmp r8,5
    jne .failed
    cmp r9,9
    jne .failed
    mov rax,qword [rsp+8]
    cmp qword [rax],11
    jne .failed
    cmp qword [rsp+16],3
    jne .failed
    add rax,8
    mov edx,2
    ret
.failed:
    xor eax,eax
    xor edx,edx
    ret
function_bridge_probe:
    push rbp
    mov rbp,rsp
    push rbx
    push r12
    push r13
    push r14
    push r15
    sub rsp,72
    mov qword [rsp+64],rbp
''')
    sentinels = {"rbx": 0x1122334455667788, "rdi": 0x2233445566778899, "rsi": 0x33445566778899aa,
                 "r12": 0x445566778899aabb, "r13": 0x5566778899aabbcc, "r14": 0x66778899aabbccdd,
                 "r15": 0x778899aabbccddee}
    for register, value in sentinels.items():
        lines.append(f"    mov {register},0x{value:016x}")
    for register in range(6, 16):
        lines.append(f"    movdqu xmm{register},oword [rel function_sentinel{register}]")
    lines.append(r'''
    mov ecx,1
    mov edx,2
    mov r8d,3
    mov r9d,4
    mov qword [rsp+32],5
    mov qword [rsp+40],6
    mov qword [rsp+48],7
    mov qword [rsp+56],8
    call function_callback
    cmp rax,204
    jne .failed
    mov rcx,0x11112222333344f9
    mov rdx,0x444455556666c350
    mov r8,0x777788889999fb2e
    mov r9,0xaaaabbbbb2d05e00
    mov rax,0x11112222333344fd
    mov qword [rsp+32],rax
    mov rax,0x444455556666ea60
    mov qword [rsp+40],rax
    mov rax,0x77778888ffe17b80
    mov qword [rsp+48],rax
    mov qword [rsp+56],9
    call function_callback_narrow
    mov r10,11986456348
    cmp rax,r10
    jne .failed
    cmp rbp,qword [rsp+64]
    jne .failed
    lea r10,[rbp-112]
    cmp rsp,r10
    jne .failed
''')
    for register, value in sentinels.items():
        lines += [f"    mov r10,0x{value:016x}", f"    cmp {register},r10", "    jne .failed"]
    for register in range(6, 16):
        lines += [f"    pcmpeqb xmm{register},oword [rel function_sentinel{register}]",
                  f"    pmovmskb r10d,xmm{register}", "    cmp r10d,65535", "    jne .failed"]
    lines.append(r'''
    mov eax,1
    jmp .done
.failed:
    xor eax,eax
.done:
    lea rsp,[rbp-40]
    pop r15
    pop r14
    pop r13
    pop r12
    pop rbx
    pop rbp
    ret
section .rodata
''')
    for register in range(6, 16):
        lines.append(f"function_sentinel{register}: dq 0x{0x1020304050607000 + register:016x},0x{0xfedcba9876543200 + register:016x}")
    lines.append("%ifidn __OUTPUT_FORMAT__,elf64\nsection .note.GNU-stack noalloc noexec nowrite progbits\n%endif\n")
    return "\n".join(lines)


class FunctionRuntimeTests(unittest.TestCase):
    def prepare(self, directory):
        (directory / "function_defs.dg").write_text(DEFINITIONS, encoding="utf-8")
        entry = directory / "function_probe.dg"
        entry.write_text(SOURCE, encoding="utf-8")
        return entry

    def assemble(self, nasm, source, output, object_format):
        result = subprocess.run([nasm, "-f", object_format, *nasm_flags(nasm), "-o", str(output), str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_function_value_relocations_are_absolute_64_bit_in_both_formats(self):
        nasm = tool("nasm", "NASM")
        if not nasm:
            self.skipTest("function-value relocation inspection requires NASM")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            entry = self.prepare(directory)
            source = directory / "functions.asm"
            source.write_text(compile_file(entry, roots=[directory]).assembly, encoding="utf-8")
            for object_format in ("elf64", "win64"):
                with self.subTest(format=object_format):
                    output = directory / (object_format + ".o")
                    self.assemble(nasm, source, output, object_format)
                    relocations = static_relocation_types(output, object_format)
                    self.assertGreaterEqual(sum(map(len, relocations.values())), 6)
                    self.assertIn(".data", relocations)
                    self.assertIn(".rodata", relocations)
                    for types in relocations.values():
                        self.assertEqual(set(types), {1})

    def test_native_indirect_calls_and_win64_bridge_preservation(self):
        nasm, cc = tool("nasm", "NASM"), tool("gcc", "CC")
        if not nasm or not cc:
            self.skipTest("native function probes require NASM and a SysV-capable GCC host compiler")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            entry = self.prepare(directory)
            c, observer = directory / "probe.c", directory / "observer.asm"
            c.write_text(HARNESS, encoding="utf-8")
            observer.write_text(observer_source(), encoding="utf-8")
            object_format = "win64" if os.name == "nt" else "elf64"
            for mode in ("debug", "release"):
                with self.subTest(mode=mode):
                    source, obj, abi = directory / (mode + ".asm"), directory / (mode + ".o"), directory / "observer.o"
                    executable = directory / (mode + (".exe" if os.name == "nt" else ""))
                    source.write_text(compile_file(entry, roots=[directory], mode=mode).assembly, encoding="utf-8")
                    self.assemble(nasm, source, obj, object_format)
                    self.assemble(nasm, observer, abi, object_format)
                    command = [cc, "-std=c11", "-O0", "-fno-omit-frame-pointer", "-Wall", "-Wextra", "-Werror"]
                    if os.name != "nt":
                        command.append("-no-pie")
                    result = subprocess.run(command + [str(c), str(obj), str(abi), "-o", str(executable)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("native function values, indirect ABI calls and Win64 callback preservation passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
