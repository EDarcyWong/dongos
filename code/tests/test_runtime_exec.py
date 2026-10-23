"""Unwired EXEC component: actual DG/paging, explicit mocked hardware boundary."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def closure():
    result = {'runtime_exec_probe.dg': HERE / 'runtime_exec_probe.dg'}
    pending = list(result.values())
    while pending:
        source = pending.pop()
        for module in re.findall(r'(?m)^\s*import\s+([\w.]+)', source.read_text(encoding='utf-8')):
            relative = module.replace('.', '/') + '.dg'
            if relative in result:
                continue
            matches = [p / relative for p in (ROOT / 'kernel', ROOT / 'lang/std') if (p / relative).is_file()]
            if len(matches) != 1:
                raise AssertionError((module, matches))
            result[relative] = matches[0]
            pending.append(matches[0])
    return result


class RuntimeExecTests(unittest.TestCase):
    def test_real_component_and_three_wrong_sources_have_precise_raw_verdicts(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'required native tools; zero skip')
        graph = closure()
        reader = ROOT / 'kernel/sched/runtime_exec_reader.asm'
        sources = sorted(set(graph.values()) | {Path(__file__), HERE / 'runtime_exec_probe.c', reader,
            ROOT / 'include/user_smp.inc', ROOT / 'include/user_context.inc', ROOT / 'include/smp.inc',
            ROOT / 'docs/runtime-exec.md', ROOT / 'lang/tests/test_dongc.py', *list((ROOT / 'lang/dongc').rglob('*.py'))})
        fingerprint = lambda: {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}
        before = fingerprint()
        tools = {name: dict(path=str(Path(path).resolve()), sha256=sha(path))
                 for name, path in [('python', sys.executable), ('nasm', nasm), ('cc', cc)]}
        output = ROOT / 'build/test/runtime-exec' / ('run-' + uuid.uuid4().hex[:12])
        output.mkdir(parents=True)
        records, commands = [], []
        complete = False
        original = (ROOT / 'kernel/mm/runtime_exec.dg').read_text(encoding='utf-8')
        revoke = 'try pg.protect_live((*c).space,WRITE_ALIAS,0);'
        mutations = {
            'missing-revoke': (revoke, 'if false{' + revoke + '}', 'missing-revoke'),
            'incomplete-ack': ('try ud.barrier_wait(d,0,sequence,try limit(c));',
                               'if false{try ud.barrier_wait(d,0,sequence,try limit(c));}', 'incomplete-ack'),
            'early-exec-grant': (revoke, 'try pg.protect_live((*c).space,EXEC_ALIAS,pg.EXECUTE);' + revoke,
                                 'early-exec-grant'),
        }

        def write(path, value):
            path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

        def run(argv, directory, label, expected=0):
            argv = list(map(str, argv))
            entry = dict(argv=argv, cwd=str(ROOT), label=label)
            commands.append(entry)
            try:
                completed = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=120)
                stdout, stderr = completed.stdout, completed.stderr
                entry['returncode'] = completed.returncode
            except BaseException as exc:
                entry['error'] = type(exc).__name__ + ': ' + str(exc)
                stdout = getattr(exc, 'stdout', None) or b''
                stderr = getattr(exc, 'stderr', None) or b''
                raise
            finally:
                for name, raw in [('stdout', stdout), ('stderr', stderr)]:
                    path = directory / (label + '.' + name)
                    path.write_bytes(raw)
                    entry[name] = dict(path=path.relative_to(output).as_posix(), sha256=sha(path))
                write(directory / (label + '.json'), entry)
            text = stdout.decode(errors='replace') + stderr.decode(errors='replace')
            self.assertEqual(expected, completed.returncode, text)
            return stdout.decode(errors='replace'), stderr.decode(errors='replace')

        write(output / 'source-before.json', before)
        write(output / 'tools.json', tools)
        try:
            asm = reader.read_text(encoding='utf-8')
            self.assertNotRegex(asm, r'(?mi)^\s*(?:mov\s+cr[034]\s*,|invlpg\b|invpcid\b|lidt\b)')
            for fmt in ('elf64', 'win64'):
                run([nasm, '-f', fmt, *nasm_flags(nasm), '-I', str(ROOT / 'include') + os.sep, reader,
                     '-o', output / ('reader-' + fmt + '.o')], output, 'reader-' + fmt)
            for mode in ('debug', 'release'):
                for mutant in (None, *mutations):
                    with self.subTest(mode=mode, mutant=mutant):
                        directory = output / mode / (mutant or 'production')
                        stage = directory / 'source'
                        stage.mkdir(parents=True)
                        for relative, source in graph.items():
                            target = stage / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                        if mutant:
                            old, new, marker = mutations[mutant]
                            self.assertEqual(1, original.count(old))
                            path = stage / 'mm/runtime_exec.dg'
                            path.write_text(original.replace(old, new), encoding='utf-8')
                            write(directory / 'mutation.json', dict(source='mm/runtime_exec.dg', old=old, new=new,
                                source_sha256=sha(ROOT / 'kernel/mm/runtime_exec.dg'), mutant_sha256=sha(path)))
                        compiled = compile_file(stage / 'runtime_exec_probe.dg', roots=[stage], mode=mode)
                        layouts = {t['full_name']: t for t in compiled.layout_manifest['types']}
                        for name, size in {'mm.runtime_exec.Report': 200, 'mm.runtime_exec.ReaderReport': 456,
                                           'mm.runtime_exec.FaultTicket': 64, 'mm.runtime_exec.Fault': 72,
                                           'mm.runtime_exec.FaultBinding': 48, 'sched.user_domain.Domain': 120,
                                           'sched.user_domain.Cpu': 120}.items():
                            self.assertEqual(size, layouts[name]['size'], name)
                        self.assertEqual(64, layouts['mm.runtime_exec.Context']['alignment'])
                        self.assertLess(layouts['mm.runtime_exec.Context']['size'], 32 * 4096)
                        for name, names in {
                            'mm.runtime_exec.Environment': ['cpu', 'root', 'cr0', 'cr4', 'rflags'],
                            'mm.runtime_exec.Sample': ['cpu', 'root', 'cr0', 'cr4', 'rflags', 'value', 'fault'],
                            'mm.runtime_exec.FaultTicket': ['armed', 'consumed', 'cpu', 'sequence', 'root', 'virtual', 'rip', 'after'],
                            'mm.runtime_exec.Fault': ['cpu', 'sequence', 'root', 'rip', 'cr2', 'error_code', 'cs', 'rflags', 'vector'],
                        }.items():
                            self.assertEqual({value: index * 8 for index, value in enumerate(names)},
                                             {field['name']: field['offset'] for field in layouts[name]['fields']})
                        assembly = directory / 'probe.asm'
                        assembly.write_text(compiled.assembly, encoding='utf-8')
                        write(directory / 'layout.json', compiled.layout_manifest)
                        write(directory / 'compilation.json', dict(api='lang.dongc.compile_file', mode=mode,
                            staged_inputs={name: sha(stage / name) for name in sorted(graph)}, assembly_sha256=sha(assembly),
                            real_paging=True, hardware_mocked=True, handler_wired=False, actual_guest=False,
                            compiler_frame_limit=4096))
                        objects = {}
                        for fmt in ('elf64', 'win64'):
                            objects[fmt] = directory / (fmt + '.o')
                            run([nasm, '-f', fmt, *nasm_flags(nasm), assembly, '-o', objects[fmt]], directory, fmt)
                        executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                        run([cc, '-std=c11', '-O2', '-D__USE_MINGW_ANSI_STDIO=1', '-Wall', '-Wextra', '-Werror',
                             *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']), HERE / 'runtime_exec_probe.c',
                             objects['win64' if os.name == 'nt' else 'elf64'], '-o', executable], directory, 'link')
                        scenarios = ['all'] if mutant else ['all', 'fallback', 'identity', 'omitted-root', 'generation', 'kernel-tag', 'kernel-tag-fallback',
                            'pge', 'ap-kernel-tag', 'ap-kernel-tag-fallback', 'ap-pge',
                            'wrong-cpu', 'missing-ack', 'stale-write', 'hidden-user', 'hidden-kernel']
                        for scenario in scenarios:
                            stdout, stderr = run([executable, scenario], directory, 'execute-' + scenario, 1 if mutant else 0)
                            if mutant:
                                self.assertIn('RAW_EXEC_REJECT ' + marker + '; returned normally', stderr)
                                self.assertNotIn('unexpected Dong panic', stderr)
                            else:
                                self.assertIn('handler not wired; no guest executed', stdout)
                        records.append(dict(mode=mode, mutant=mutant, scenarios=scenarios, executable_sha256=sha(executable),
                            elf_sha256=sha(objects['elf64']), coff_sha256=sha(objects['win64'])))
                        self.assertEqual(before, fingerprint())
            self.assertEqual(8, len(records))
            complete = True
        finally:
            after = fingerprint()
            stable_tools = all(sha(v['path']) == v['sha256'] for v in tools.values())
            write(output / 'source-after.json', after)
            write(output / 'commands.json', commands)
            write(output / 'result.json', dict(passed=complete and before == after and stable_tools,
                cases=records, expected_cases=8, source_stable=before == after, tools_stable=stable_tools,
                hardware_mocked=True, handler_wired=False, actual_guest=False,
                scope='component host contract only; real ASM assembled, privileged body not host executed'))
        self.assertEqual(before, after)
        self.assertTrue(stable_tools)
        print('RUNTIME_EXEC_COMPONENT_EVIDENCE', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
