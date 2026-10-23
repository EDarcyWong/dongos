"""Real DG adapter + production ASM gate, independent C data oracle.

The host never enters the IRQ, hardware snapshot, SWAPGS or IRET paths.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import traceback
import unittest
import uuid

from lang.dongc import CompileError, compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def closure():
    found = {'runtime_exec_entry_probe.dg': HERE / 'runtime_exec_entry_probe.dg'}
    pending = list(found.values())
    while pending:
        source = pending.pop()
        for name in re.findall(r'(?m)^\s*import\s+([\w.]+)', source.read_text(encoding='utf-8')):
            relative = name.replace('.', '/') + '.dg'
            if relative in found:
                continue
            matches = [base / relative for base in (ROOT / 'kernel', ROOT / 'lang/std')
                       if (base / relative).is_file()]
            if len(matches) != 1:
                raise AssertionError((name, matches))
            found[relative] = matches[0]
            pending.append(matches[0])
    return found


RAW = 'cr2 r15 r14 r13 r12 r11 r10 r9 r8 rdi rsi rbp rdx rcx rbx rax vector error rip cs rflags rsp ss'.split()
HEADER = ('kernel_stack user_stack continuation root_frame original_cr3 syscalls busy result smp domain '
          'logical_id contexts context_count pcid_enabled gdt tss idt stack_bottom df_top nmi_top '
          'exception_top kernel_xstate capture returned return_xstate ready last_error event raw_frame '
          'deadline_ticks tsc_hz timer_hz').split()
TRACE = ('version commit cpu payload header root generation frame stack_bottom stack_top context domain reader '
         'request acknowledged action_sequence command virtual expected after').split()


class RuntimeExecEntryTests(unittest.TestCase):
    def test_exact_registered_adapter_and_real_wrong_sources(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'required native tools, zero skips')
        graph = closure()
        include_names = ['user_entry.inc', 'user_smp.inc', 'user_context.inc', 'smp.inc', 'cpu.inc']
        tracked = sorted(set(graph.values()) | {
            Path(__file__), HERE / 'runtime_exec_entry_probe.c', ROOT / 'kernel/sched/user_entry.asm',
            ROOT / 'docs/runtime-exec-entry.md',
            *(ROOT / 'include' / name for name in include_names),
            *list((ROOT / 'lang/dongc').rglob('*.py')), ROOT / 'lang/tests/test_dongc.py',
        })
        fingerprint = lambda: {p.relative_to(ROOT).as_posix(): sha(p) for p in tracked}
        before = fingerprint()
        tools = {name: dict(path=str(Path(path).resolve()), sha256=sha(path))
                 for name, path in [('python', sys.executable), ('nasm', nasm), ('cc', cc)]}
        output = ROOT / 'build/test/runtime-exec-entry' / ('run-' + uuid.uuid4().hex[:12])
        output.mkdir(parents=True)
        write(output / 'source-before.json', before)
        write(output / 'tools.json', tools)
        commands, cases, bad_abi = [], [], []
        completed_all = False

        def run(argv, directory, label, expected=0):
            argv = list(map(str, argv))
            record = dict(argv=argv, cwd=str(ROOT), label=label)
            commands.append(record)
            stdout, stderr = b'', b''
            try:
                result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=120)
                stdout, stderr = result.stdout, result.stderr
                record['returncode'] = result.returncode
            except BaseException as exc:
                record['error'] = type(exc).__name__ + ': ' + str(exc)
                stdout, stderr = getattr(exc, 'stdout', None) or b'', getattr(exc, 'stderr', None) or b''
                raise
            finally:
                for kind, raw in [('stdout', stdout), ('stderr', stderr)]:
                    path = directory / (label + '.' + kind)
                    path.write_bytes(raw)
                    record[kind] = dict(path=path.relative_to(output).as_posix(), sha256=sha(path))
                write(directory / (label + '.json'), record)
            self.assertEqual(expected, result.returncode, stdout.decode(errors='replace') + stderr.decode(errors='replace'))
            return stdout.decode(errors='replace'), stderr.decode(errors='replace')

        # A third, independently assembled layout view. This binary is data only.
        asm_header = ['UserCpu.' + name for name in HEADER[:8]]
        asm_header += ['UserSmpCpu.' + name for name in HEADER[8:14]]
        asm_header += ['UserEntryCpu.' + name for name in HEADER[14:]]
        layout_source = output / 'layout.asm'
        layout_source.write_text('bits 64\n%include "user_entry.inc"\n' +
            'dq ExceptionContext_size,UserEntryCpu_size\n' +
            'dq ' + ','.join('ExceptionContext.' + name for name in RAW) + '\n' +
            'dq ' + ','.join(asm_header) + '\n', encoding='utf-8')
        try:
            run([nasm, '-f', 'bin', *nasm_flags(nasm), '-I', str(ROOT / 'include') + os.sep,
                 layout_source, '-o', output / 'layout.bin'], output, 'layout')
            expected_layout = [184, 256, *(i * 8 for i in range(23)), *(i * 8 for i in range(32))]
            actual_layout = list(struct.unpack('<' + 'Q' * len(expected_layout), (output / 'layout.bin').read_bytes()))
            self.assertEqual(expected_layout, actual_layout)
            write(output / 'layout-oracle.json', dict(expected=expected_layout, actual=actual_layout,
                source_sha256=sha(layout_source), binary_sha256=sha(output / 'layout.bin')))
            original_asm = (ROOT / 'kernel/sched/user_entry.asm').read_text(encoding='utf-8')
            original_dg = (ROOT / 'kernel/sched/runtime_exec_entry.dg').read_text(encoding='utf-8')
            trace_commit = original_dg.split('unsafe fn trace_commit(', 1)[1].split('pub unsafe fn dispatch(', 1)[0]
            self.assertRegex(trace_commit,
                r'compiler_fence\(\);atomic_store\(&\(\*record\)\.commit,TRACE_COMMITTED\);\s*\}return;\}\s*$')
            recovery = original_asm.split('.exec_fault:', 1)[1].split('user_smp_captured:', 1)[0]
            self.assertEqual(RAW[1:16], re.findall(r'(?m)^\s*pop (r\w+)\s*$', recovery))
            self.assertLess(recovery.index('call user_smp_exec_claim'), recovery.index('mov rsp,rax'))
            self.assertIn('add rax,16', recovery)
            self.assertIn('add rsp,8', recovery)
            self.assertIn('add rsp,16', recovery)
            self.assertIn('iretq', recovery)
            self.assertNotRegex(recovery, r'(?m)^\s*(?:swapgs|sti|invlpg|invpcid)\b')
            pure_gate = original_asm.split('user_smp_exec_claim:', 1)[1].split('align 16\nuser_smp_entry_stubs:', 1)[0]
            self.assertNotRegex(pure_gate, r'(?mi)^\s*(?:iretq|rdmsr|wrmsr|swapgs|cli|sti|invlpg|invpcid|xsave\w*|xrstor\w*)\b')
            mutations = {
                'missing-root-generation': ('sched/runtime_exec_entry.dg',
                    'a.space!=b.space||a.identity!=b.identity||a.generation!=b.generation',
                    'a.space!=b.space||a.identity!=b.identity', 'all'),
                'extra-frame-write': ('user_entry.asm',
                    'mov [r14+ExceptionContext.rip],r13 ; the only saved-frame write',
                    'mov [r14+ExceptionContext.rip],r13\n    mov qword [r14+ExceptionContext.rax],0', 'all'),
                'missing-fixed-after': ('user_entry.asm',
                    'cmp r13,[rel user_exec_after]\n    jne .bad',
                    'cmp r13,r13\n    jne .bad', 'after-gate'),
                'trace-overwrite-nonempty': ('sched/runtime_exec_entry.dg',
                    'record=TRACE_RECORDS+slot;if !trace_empty(record){return 0;}',
                    'record=TRACE_RECORDS+slot;', 'trace'),
                'trace-lost-raw': ('sched/runtime_exec_entry.dg',
                    '*((&(*record).raw as *u64)+i)=*((raw as *const u64)+i)',
                    '*((&(*record).raw as *u64)+i)=0', 'trace'),
                'trace-wrong-consumed-ticket': ('sched/runtime_exec_entry.dg',
                    '*((&(*record).ticket_after as *u64)+i)=*((&(*reader).ticket as *const u64)+i)',
                    '*((&(*record).ticket_after as *u64)+i)=*((before as *const u64)+i)', 'trace'),
            }
            for mode in ('debug', 'release'):
                for variant in ('production', *mutations):
                    with self.subTest(mode=mode, variant=variant):
                        directory = output / mode / variant
                        stage = directory / 'source'
                        stage.mkdir(parents=True)
                        for relative, source in graph.items():
                            target = stage / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                        architecture = directory / 'user_entry.asm'
                        architecture.write_text(original_asm, encoding='utf-8')
                        if variant != 'production':
                            relative, old, new, scenario = mutations[variant]
                            target = architecture if relative == 'user_entry.asm' else stage / relative
                            content = original_asm if relative == 'user_entry.asm' else original_dg
                            self.assertEqual(1, content.count(old), (variant, old))
                            target.write_text(content.replace(old, new), encoding='utf-8')
                            write(directory / 'mutation.json', dict(source=relative, old=old, new=new,
                                mutant_sha256=sha(target)))
                        compilation = compile_file(stage / 'runtime_exec_entry_probe.dg', roots=[stage], mode=mode)
                        assembly = directory / 'probe.asm'
                        assembly.write_text(compilation.assembly, encoding='utf-8')
                        write(directory / 'layout.json', compilation.layout_manifest)
                        layouts = {v['full_name']: v for v in compilation.layout_manifest['types']}
                        dong_raw = ['error_code' if name == 'error' else name for name in RAW]
                        for name, fields, size in [('Raw', dong_raw, 184), ('Header', HEADER, 256),
                                                  ('Snapshot', 'cpu root cr0 cr4 rflags header'.split(), 48)]:
                            actual = layouts['sched.runtime_exec_entry.' + name]
                            self.assertEqual(size, actual['size'])
                            self.assertEqual({name: i * 8 for i, name in enumerate(fields)},
                                             {v['name']: v['offset'] for v in actual['fields']})
                        trace = layouts['sched.runtime_exec_entry.RawTrace']
                        self.assertEqual(512, trace['size'])
                        self.assertEqual(64, trace['alignment'])
                        self.assertEqual({**{name: i * 8 for i, name in enumerate(TRACE)},
                                          'raw': 160, 'ticket_before': 344, 'ticket_after': 408, 'reserved': 472},
                                         {v['name']: v['offset'] for v in trace['fields']})
                        self.assertNotRegex(compilation.assembly.lower(),
                            r'\b(?:xmm\d+|ymm\d+|zmm\d+|mm[0-7]|fld\w*|fst\w*|fns\w*|xsave\w*|xrstor\w*|rdmsr|wrmsr|invpcid)\b')
                        # The handler closure is entirely integer/REP code. Summing
                        # every helper frame is a conservative bound, even though
                        # siblings do not coexist on the actual call stack.
                        frame_sizes, call_graph = {}, {}
                        helper_groups = [('sched.runtime_exec_entry', ['dispatch', 'identity', 'fixed', 'object', 'overlap',
                                                                       'trace_empty', 'trace_commit']),
                                         ('mm.runtime_exec', ['handle_fault', 'consume_fault', 'object', 'overlap'])]
                        symbols = {'__dg_m' + module.encode().hex() + '_f' + name.encode().hex(): module + '.' + name
                                   for module, names in helper_groups for name in names}
                        permitted = set(symbols) | {'user_smp_exec_registration', 'user_smp_exec_callback_bits', '__dong_panic'}
                        for module, names in helper_groups:
                            for name in names:
                                symbol = '__dg_m' + module.encode().hex() + '_f' + name.encode().hex()
                                match = re.search(r'(?m)^\$' + re.escape(symbol) + r':\n', compilation.assembly)
                                self.assertIsNotNone(match, (module, name))
                                tail = compilation.assembly[match.end():]
                                end = re.search(r'(?m)^\$__dg_m[0-9a-f]+_f[0-9a-f]+:', tail)
                                body = tail[:end.start()] if end else tail
                                self.assertNotIn('and rsp,', body)
                                self.assertNotRegex(body, r'(?m)^\s*call (?:r\w+|\[)')
                                calls = set(re.findall(r'(?m)^\s*call \$?([A-Za-z_][A-Za-z_0-9]*)\s*$', body))
                                self.assertLessEqual(calls, permitted, (module, name, calls - permitted))
                                call_graph[symbol] = calls & set(symbols)
                                adjustments = list(map(int, re.findall(r'(?m)^\s*sub rsp, ([0-9]+)\s*$', body)))
                                self.assertLessEqual(len(adjustments), 1, (module, name, adjustments))
                                frame_sizes[module + '.' + name] = (adjustments[0] if adjustments else 0) + 16
                        self.assertTrue(all(size <= 4096 for size in frame_sizes.values()), frame_sizes)
                        def acyclic(symbol, active):
                            self.assertNotIn(symbol, active, 'handler helper recursion invalidates stack sum')
                            for target in call_graph[symbol]:
                                acyclic(target, active | {symbol})
                        for symbol in call_graph:
                            acyclic(symbol, set())
                        conservative_stack = sum(frame_sizes.values()) + 64
                        self.assertLess(conservative_stack, 16384)
                        write(directory / 'compilation.json', dict(mode=mode, api='lang.dongc.compile_file',
                            staged_inputs={n: sha(stage / n) for n in sorted(graph)}, assembly_sha256=sha(assembly),
                            architecture_sha256=sha(architecture),
                            frame_sizes=frame_sizes, callback_stack_bound=conservative_stack,
                            callback_call_graph={symbols[k]: [symbols[v] for v in sorted(values)] for k, values in call_graph.items()},
                            hardware_snapshot_mocked=True, real_irq_executed=False, actual_guest=False,
                            trace_layout_bytes=512, trace_slots=32, trace_is_pre_asm=True,
                            native_trace_stack='host-selected guarded 16KiB exception arena; no hardware entry/IRET'))
                        objects = {}
                        for fmt in ('elf64', 'win64'):
                            dong_object, entry_object = directory / (fmt + '.o'), directory / ('entry-' + fmt + '.o')
                            run([nasm, '-f', fmt, *nasm_flags(nasm), assembly, '-o', dong_object], directory, fmt)
                            run([nasm, '-f', fmt, *nasm_flags(nasm), '-I', str(ROOT / 'include') + os.sep,
                                 architecture, '-o', entry_object], directory, 'entry-' + fmt)
                            objects[fmt] = (dong_object, entry_object)
                        executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                        run([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-D__USE_MINGW_ANSI_STDIO=1',
                             *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']), HERE / 'runtime_exec_entry_probe.c',
                             *objects['win64' if os.name == 'nt' else 'elf64'], '-o', executable], directory, 'link')
                        scenarios = (['missing', 'all', 'nested', 'after-gate', 'trace', 'trace-offline', 'trace-binds',
                                      *['trace-entry-' + kind for kind in ('context', 'header', 'kernel', 'df', 'nmi', 'exception', 'late')]]
                                     if variant == 'production' else [mutations[variant][3]])
                        for scenario in scenarios:
                            stdout, stderr = run([executable, scenario], directory, 'execute-' + scenario,
                                                 0 if variant == 'production' else 1)
                            if variant == 'production':
                                self.assertIn('no guest executed', stdout)
                            else:
                                self.assertIn('runtime EXEC entry oracle', stderr)
                                self.assertNotIn('unexpected Dong panic', stderr)
                        cases.append(dict(mode=mode, variant=variant, scenarios=scenarios,
                            executable_sha256=sha(executable), objects={fmt: [sha(p) for p in pair] for fmt, pair in objects.items()}))
                        self.assertEqual(before, fingerprint())
                # Exercise the real compiler's ABI rejection instead of guessing
                # that every non-null machine address has the correct fn type.
                bad_stage = output / mode / 'bad-abi'
                shutil.copytree(output / mode / 'production/source', bad_stage)
                invalid = bad_stage / 'callback_bad.dg'
                invalid.write_text('module callback_bad;\nimport sched.runtime_exec_entry as e;\n'
                    'unsafe extern "win64" fn wrong(h:*e.Header,r:u64,p:*const e.Raw,g:u64)u64;\n'
                    'pub fn reject()void{let callback:e.Callback=wrong;}\n', encoding='utf-8')
                try:
                    compile_file(invalid, roots=[bad_stage], mode=mode)
                except CompileError as exc:
                    self.assertEqual('E0301', exc.code)
                    receipt = dict(mode=mode, code=exc.code, message=exc.message, source_sha256=sha(invalid))
                    write(bad_stage / 'rejection.json', receipt)
                    bad_abi.append(receipt)
                else:
                    self.fail('wrong ABI callback unexpectedly compiled')
            self.assertEqual(2 * (1 + len(mutations)), len(cases))
            self.assertEqual(2, len(bad_abi))
            completed_all = True
        except BaseException:
            (output / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
            raise
        finally:
            after = fingerprint()
            stable_tools = all(sha(item['path']) == item['sha256'] for item in tools.values())
            write(output / 'source-after.json', after)
            write(output / 'commands.json', commands)
            write(output / 'result.json', dict(passed=completed_all and before == after and stable_tools,
                expected_cases=2 * (1 + len(mutations)), cases=cases, wrong_abi=bad_abi, source_stable=before == after,
                tools_stable=stable_tools, zero_skip_required=True, actual_irq_executed=False, actual_guest=False,
                scope='registered adapter and pre-ASM RawTrace; host apply never executes privileged entry or proves IRET'))
        self.assertEqual(before, after)
        self.assertTrue(stable_tools)
        print('RUNTIME_EXEC_ENTRY_EVIDENCE', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
