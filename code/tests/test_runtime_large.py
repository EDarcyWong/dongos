"""Production DG/paging with independent raw C forest and per-CPU cache oracle."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def closure():
    result = {'runtime_large_probe.dg': HERE / 'runtime_large_probe.dg'}
    pending = list(result.values())
    while pending:
        source = pending.pop()
        for name in re.findall(r'(?m)^\s*import\s+([\w.]+)', source.read_text(encoding='utf-8')):
            relative = name.replace('.', '/') + '.dg'
            if relative in result:
                continue
            paths = [p / relative for p in (ROOT / 'kernel', ROOT / 'lang/std') if (p / relative).is_file()]
            if len(paths) != 1:
                raise AssertionError((name, paths))
            result[relative] = paths[0]
            pending.append(paths[0])
    return result


class RuntimeLargeTests(unittest.TestCase):
    def test_real_owner_raw_paging_and_three_wrong_dong_implementations(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'required native tools, zero skip')
        graph = closure()
        inputs = sorted(set(graph.values()) | {Path(__file__), HERE / 'runtime_large_probe.c',
            ROOT / 'kernel/sched/runtime_large_reader.asm', ROOT / 'include/user_smp.inc',
            ROOT / 'include/user_context.inc', ROOT / 'include/smp.inc', ROOT / 'docs/runtime-large.md',
            ROOT / 'lang/tests/test_dongc.py', *list((ROOT / 'lang/dongc').rglob('*.py'))})
        frozen = lambda: {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}
        before = frozen()
        tools = {name: dict(path=str(Path(path).resolve()), sha256=sha(path))
                 for name, path in [('nasm', nasm), ('cc', cc)]}
        out = ROOT / 'build/test/runtime-large' / ('run-' + uuid.uuid4().hex[:12])
        out.mkdir(parents=True)
        records, commands = [], []
        original = (ROOT / 'kernel/mm/runtime_large.dg').read_text(encoding='utf-8')
        mutants = {
            'ignore-trusted-enumeration': ('if (*c).check((*c).cookie)!=0', 'if false', 'authority'),
            'omit-replacement-post-flush': ('try barrier(c,true);', 'if kind!=3{try barrier(c,true);}', 'all'),
            'reclaim-before-ack': ('try barrier(c,true);',
                'var early:usize=0;while early<receipts{try pg.reclaim((*c).space,&(*c).receipts[early]);early+=1;}\n try barrier(c,true);', 'all'),
        }

        def write(path, value):
            path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

        def run(argv, directory, label, expected=0):
            argv = list(map(str, argv))
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
            receipt = dict(argv=argv, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
            write(directory / (label + '.json'), receipt)
            commands.append(dict(path=directory.relative_to(out).as_posix(), label=label, **receipt))
            self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
            return result

        write(out / 'source-before.json', before)
        write(out / 'tools.json', tools)
        try:
            # Real privileged reader assembly is assembled in both formats,
            # inspected and archived, and never executed by the host fixture.
            bridge = (ROOT / 'kernel/sched/runtime_large_reader.asm').read_text(encoding='utf-8')
            self.assertNotRegex(bridge, r'(?mi)^\s*(?:mov\s+cr[34]\s*,|invlpg\b|invpcid\b)')
            for fmt in ('elf64', 'win64'):
                run([nasm, '-f', fmt, *nasm_flags(nasm), '-I', str(ROOT / 'include') + os.sep,
                     ROOT / 'kernel/sched/runtime_large_reader.asm', '-o', out / ('reader-' + fmt + '.o')], out, 'reader-' + fmt)
            for mode in ('debug', 'release'):
                for mutant in (None, *mutants):
                    with self.subTest(mode=mode, mutant=mutant):
                        directory = out / mode / (mutant or 'production')
                        stage = directory / 'source'
                        stage.mkdir(parents=True)
                        for relative, source in graph.items():
                            target = stage / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                        scenario = 'all'
                        if mutant:
                            old, new, scenario = mutants[mutant]
                            self.assertEqual(1, original.count(old))
                            (stage / 'mm/runtime_large.dg').write_text(original.replace(old, new), encoding='utf-8')
                            write(directory / 'mutation.json', dict(source='mm/runtime_large.dg', old=old, new=new,
                                source_sha256=sha(ROOT / 'kernel/mm/runtime_large.dg'), mutant_sha256=sha(stage / 'mm/runtime_large.dg')))
                        compiled = compile_file(stage / 'runtime_large_probe.dg', roots=[stage], mode=mode)
                        layouts = {v['full_name']: v for v in compiled.layout_manifest['types']}
                        self.assertEqual(120, layouts['sched.user_domain.Domain']['size'])
                        self.assertEqual(120, layouts['sched.user_domain.Cpu']['size'])
                        self.assertEqual(232, layouts['mm.runtime_large.Report']['size'])
                        self.assertEqual(64, layouts['mm.runtime_large.Context']['alignment'])
                        self.assertEqual(5056, layouts['mm.runtime_roots.Scratch']['size'])
                        self.assertLess(layouts['mm.runtime_large.Context']['size'], 32 * 4096)
                        write(directory / 'layout.json', compiled.layout_manifest)
                        write(directory / 'compilation.json', dict(mode=mode, api='lang.dongc.compile_file',
                            production_inputs=before, staged_inputs={name: sha(stage / name) for name in sorted(graph)},
                            context=layouts['mm.runtime_large.Context'], actual_paging=True, hardware_callbacks_mocked=True,
                            actual_guest_executed=False, compiler_frame_bound=4096))
                        assembly = directory / 'probe.asm'
                        assembly.write_text(compiled.assembly, encoding='utf-8')
                        objects = {}
                        for fmt in ('elf64', 'win64'):
                            objects[fmt] = directory / (fmt + '.o')
                            run([nasm, '-f', fmt, *nasm_flags(nasm), assembly, '-o', objects[fmt]], directory, fmt)
                        executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                        run([cc, '-std=c11', '-O2', '-D__USE_MINGW_ANSI_STDIO=1', '-Wall', '-Wextra', '-Werror',
                             *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']), HERE / 'runtime_large_probe.c',
                             objects['win64' if os.name == 'nt' else 'elf64'], '-o', executable], directory, 'link')
                        scenarios = [scenario] if mutant else ['all', 'all-untagged', 'occupied-window', 'null-callbacks', 'authority', 'omitted-root', 'generation',
                            'shared-slot', 'wrong-cpu', 'kernel-tag', 'ap-kernel-tag', 'ap-pge', 'returning', 'missing-ack', 'old-window',
                            'new-third-party', 'new-hole', 'new-permission']
                        for scenario in scenarios:
                            result = run([executable, scenario], directory, 'execute-' + scenario, 1 if mutant else 0)
                            if mutant:
                                self.assertIn('runtime large raw oracle line', result.stderr)
                                self.assertIn('returned normally', result.stderr)
                            else:
                                self.assertIn('no privileged instructions executed', result.stdout)
                        records.append(dict(mode=mode, mutant=mutant, scenarios=scenarios,
                            elf_sha256=sha(objects['elf64']), coff_sha256=sha(objects['win64']), executable_sha256=sha(executable)))
                        self.assertEqual(before, frozen())
        finally:
            after = frozen()
            stable_tools = all(sha(v['path']) == v['sha256'] for v in tools.values())
            write(out / 'source-after.json', after)
            write(out / 'commands.json', commands)
            write(out / 'result.json', dict(passed=len(records) == 8 and before == after and stable_tools,
                expected_cases=8, cases=records, commands=len(commands), source_stable=before == after,
                source_before=before, source_after=after, tools_stable=stable_tools,
                real_dong_paging=True, hardware_callbacks_mocked=True, actual_guest_executed=False))
        self.assertEqual(8, len(records))
        self.assertEqual(before, after)
        self.assertTrue(stable_tools)
        print('RUNTIME_LARGE_NATIVE_EVIDENCE', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
