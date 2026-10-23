"""Production cache owner + paging/forest/Domain, independent raw C oracle.

Only hardware callbacks are mocked. The ASM atomic gate runs as actual native
CPU instructions; its privileged reader is assembled but is never executed.
"""
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


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def closure():
    result = {'runtime_cache_probe.dg': HERE / 'runtime_cache_probe.dg'}
    pending = list(result.values())
    while pending:
        source = pending.pop()
        for module in re.findall(r'(?m)^\s*import\s+([\w.]+)', source.read_text(encoding='utf-8')):
            relative = module.replace('.', '/') + '.dg'
            if relative in result:
                continue
            matches = [base / relative for base in (ROOT / 'kernel', ROOT / 'lang/std', ROOT / 'lang/examples')
                       if (base / relative).is_file()]
            if len(matches) != 1:
                raise AssertionError((module, matches))
            result[relative] = matches[0]
            pending.append(matches[0])
    return result


class RuntimeCacheTests(unittest.TestCase):
    def test_full_gop_transaction_raw_order_and_five_real_bad_sources(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'native tools required; zero skips')
        graph = closure()
        inputs = sorted(set(graph.values()) | {
            Path(__file__), HERE / 'runtime_cache_probe.c', ROOT / 'kernel/sched/runtime_cache_reader.asm',
            ROOT / 'docs/runtime-cache.md', ROOT / 'lang/tests/test_dongc.py',
            *list((ROOT / 'lang/dongc').rglob('*.py')),
        })
        frozen = lambda: {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}
        before = frozen()
        tools = {role: dict(path=str(Path(path).resolve()), sha256=sha(path))
                 for role, path in [('python', sys.executable), ('nasm', nasm), ('cc', cc)]}
        state = ROOT / 'build/test/runtime-cache' / ('run-' + uuid.uuid4().hex[:12])
        state.mkdir(parents=True)
        write(state / 'source-before.json', before)
        write(state / 'tools.json', tools)
        original = (ROOT / 'kernel/mm/runtime_cache.dg').read_text(encoding='utf-8')
        mutants = {
            'omit-user-revoke': (
                'try pg.unmap_live((*p).space,(*p).virtual,&(*p).retired);',
                'if ((*p).flags&pg.USER)==0{try pg.unmap_live((*p).space,(*p).virtual,&(*p).retired);}',
                'all', 'USER-alias-not-revoked'),
            'reclaim-without-ack': (
                '(*c).report.first=try barrier(c);',
                '(*c).report.first=(*cfg.domain).completed;',
                'all', 'reclaim-without-first-ACK'),
            'omit-maintenance': (
                'try actions(c,MAINTAIN);', 'let omitted:u64=0;',
                'all', 'missing-per-CPU-cache-maintenance'),
            'accept-wrong-pat': (
                '||(((*r).pat>>32)&255)!=plan.WC', '||false',
                'bad-pat', 'wrong-PAT-readback'),
            'early-open': (
                'try closure(c,target,true);(*c).report.phase=6;',
                'try closure(c,target,true);(*c).report.phase=6;let opened=runtime_cache_gate_open(cfg.gate,(*c).report.gate_token);',
                'all', 'early-open-gate'),
        }
        expected = 2 * (1 + len(mutants))
        commands, cases = [], []

        def run(command, directory, label, expected_rc=0):
            command = list(map(str, command))
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
            receipt = dict(argv=command, cwd=str(ROOT), returncode=completed.returncode,
                           stdout=completed.stdout, stderr=completed.stderr)
            write(directory / (label + '.json'), receipt)
            commands.append(dict(directory=directory.relative_to(state).as_posix(), label=label, **receipt))
            self.assertEqual(expected_rc, completed.returncode, completed.stdout + completed.stderr)
            return completed

        try:
            for mode in ('debug', 'release'):
                for mutant in (None, *mutants):
                    with self.subTest(mode=mode, mutant=mutant):
                        directory = state / mode / (mutant or 'production')
                        stage = directory / 'src'
                        stage.mkdir(parents=True)
                        for relative, source in graph.items():
                            target = stage / relative
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                        source = original
                        if mutant:
                            old, new, scenario, diagnostic = mutants[mutant]
                            self.assertEqual(1, source.count(old), 'mutate one actual semantic boundary')
                            source = source.replace(old, new)
                            (stage / 'mm/runtime_cache.dg').write_text(source, encoding='utf-8')
                            write(directory / 'mutation.json', dict(path='mm/runtime_cache.dg', old=old, new=new,
                                source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                                actual_sha256=sha(stage / 'mm/runtime_cache.dg')))
                        compiled = compile_file(stage / 'runtime_cache_probe.dg', roots=[stage], mode=mode)
                        layouts = {item['full_name']: item for item in compiled.layout_manifest['types']}
                        self.assertEqual(456, layouts['mm.runtime_cache.Reading']['size'])
                        self.assertEqual(96, layouts['mm.runtime_cache.Page']['size'])
                        self.assertEqual(128, layouts['mm.runtime_cache.Config']['size'])
                        self.assertEqual(32, layouts['mm.runtime_cache.Gate']['size'])
                        self.assertEqual(5056, layouts['mm.runtime_roots.Scratch']['size'])
                        self.assertEqual(64, layouts['mm.runtime_cache.Context']['alignment'])
                        self.assertLess(layouts['mm.runtime_cache.Context']['size'], 8 * 4096)
                        write(directory / 'layout.json', compiled.layout_manifest)
                        write(directory / 'compilation.json', dict(api='lang.dongc.compile_file', mode=mode,
                            roots=[str(stage)], source=str(stage / 'runtime_cache_probe.dg'),
                            frozen_inputs=before, staged_inputs={n: sha(stage / n) for n in graph},
                            context=layouts['mm.runtime_cache.Context'], work=layouts['mm.runtime_cache.Work'],
                            compiler_frame_limit=4096, hardware_callbacks_mocked=True,
                            actual_guest_executed=False, actual_privileged_instructions_executed=False))
                        assembly = directory / 'probe.asm'
                        assembly.write_text(compiled.assembly, encoding='utf-8')
                        reader = directory / 'runtime_cache_reader.asm'
                        shutil.copy2(ROOT / 'kernel/sched/runtime_cache_reader.asm', reader)
                        self.assertNotRegex(reader.read_text(), r'(?mi)^\s*wrmsr\b')
                        objects = {}
                        for fmt in ('elf64', 'win64'):
                            obj = directory / (fmt + '.o')
                            hardware_obj = directory / ('reader-' + fmt + '.o')
                            run([nasm, '-f', fmt, *nasm_flags(nasm), assembly, '-o', obj], directory, fmt)
                            run([nasm, '-f', fmt, *nasm_flags(nasm), '-l', directory / ('reader-' + fmt + '.lst'),
                                 reader, '-o', hardware_obj], directory, 'reader-' + fmt)
                            objects[fmt] = (obj, hardware_obj)
                        executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                        run([cc, '-std=c11', '-O2', '-D__USE_MINGW_ANSI_STDIO=1', '-Wall', '-Wextra', '-Werror',
                             *(['-mno-sse'] if os.name == 'nt' else ['-no-pie']), HERE / 'runtime_cache_probe.c',
                             *objects['win64' if os.name == 'nt' else 'elf64'], '-o', executable], directory, 'link')
                        scenarios = [scenario] if mutant else ['gate', 'all', 'bad-pat', 'bad-ledger', 'omitted-user',
                            'omitted-alias', 'wrong-identity', 'PGE', 'tagged-kernel', 'capacity', 'source-overlap',
                            'memory-generation', 'domain-incarnation',
                            'returning', 'active-barrier',
                            'hidden-USER', 'non-WB-MTRR',
                            'missing-ack', 'bad-maintenance', 'mtrr-changed']
                        for scenario in scenarios:
                            result = run([executable, scenario], directory, 'execute-' + scenario, 1 if mutant else 0)
                            if mutant:
                                self.assertIn('runtime cache raw oracle line', result.stderr)
                                self.assertIn(diagnostic, result.stderr)
                                self.assertIn('returned normally', result.stderr)
                            elif scenario != 'gate':
                                self.assertIn('privileged instructions not executed', result.stdout)
                        cases.append(dict(mode=mode, mutant=mutant, scenarios=scenarios,
                            dong_objects={fmt: sha(pair[0]) for fmt, pair in objects.items()},
                            reader_objects={fmt: sha(pair[1]) for fmt, pair in objects.items()},
                            executable_sha256=sha(executable), normally_exited=True))
                        self.assertEqual(before, frozen())
        finally:
            after = frozen()
            stable_tools = all(sha(v['path']) == v['sha256'] for v in tools.values())
            write(state / 'source-after.json', after)
            write(state / 'commands.json', commands)
            write(state / 'result.json', dict(passed=len(cases) == expected and before == after and stable_tools,
                expected_cases=expected, cases=cases, source_stable=before == after,
                source_before=before, source_after=after, tools=tools, tools_stable=stable_tools,
                actual_dong_paging_forest_domain=any(c['label'] == 'execute-all' and c['returncode'] == 0 for c in commands),
                atomic_gate_native_executed=any(c['label'] == 'execute-gate' and c['returncode'] == 0 for c in commands),
                hardware_callbacks_mocked=True, actual_privileged_instructions_executed=False,
                actual_guest_executed=False))
        self.assertEqual(expected, len(cases))
        self.assertEqual(before, after)
        self.assertTrue(stable_tools)
        print('RUNTIME_CACHE_NATIVE_EVIDENCE', state)


if __name__ == '__main__':
    unittest.main(verbosity=2)
