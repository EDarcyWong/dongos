"""Real Dong Bridge/Domain errors; host hardware boundaries are synthetic.

Only the coordinator executes this gate. It never builds or starts an OS/VM.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool
from tests.test_service_ipc_cancellation import block

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests'


def graph():
    result = {'user_smp_failure_probe': HERE / 'user_smp_failure_probe.dg'}
    pending = list(result.values())
    while pending:
        path = pending.pop()
        for name in re.findall(r'\bimport\s+([\w.]+)\s+as\s+', path.read_text(encoding='utf-8')):
            if name in result:
                continue
            relative = name.replace('.', '/') + '.dg'
            candidates = [root / relative for root in (HERE, ROOT / 'kernel') if (root / relative).is_file()]
            if len(candidates) != 1:
                raise AssertionError((name, candidates))
            result[name] = candidates[0]
            pending.append(candidates[0])
    return result


class FailureDiagnosticsTests(unittest.TestCase):
    def test_actual_first_errors_and_fail_held_semantic_controls(self):
        sources = graph()
        watched = set(sources.values()) | {Path(__file__), HERE / 'user_current_entry_probe.c',
            HERE / 'user_smp_failure_probe.c', ROOT / 'kernel/sched/user_entry.asm',
            ROOT / 'kernel/sched/user_legacy.asm', HERE / 'test_service_ipc_cancellation.py',
            ROOT / 'lang/tests/test_dongc.py', ROOT / 'docs/p2-smp-failure-diagnostics.md'}
        watched |= set((ROOT / 'include').glob('*.inc')) | set((ROOT / 'lang/dongc').glob('*.py'))
        hashes = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(watched)}
        before = hashes()
        output = ROOT / 'build/test/user-smp-failure' / ('run-' + uuid.uuid4().hex[:12])
        output.mkdir(parents=True)
        evidence, commands = [], []
        passed, failure = False, None
        # Keep a conservative receipt even if tool discovery or fixture
        # preparation fails before the compiler loop starts.
        (output / 'validation-summary.json').write_text(json.dumps(dict(passed=False, phase='preparation',
            source_before=before, skipped=[], actual_qemu_executed=False, actual_ap_cpl3_executed=False), indent=2) + '\n')
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'actual NASM and C compiler required; no skip')
        paths = {name: Path(path).resolve() for name, path in dict(python=sys.executable, nasm=nasm, cc=cc).items()}
        nasm, cc = str(paths['nasm']), str(paths['cc'])
        def tool_hashes():
            return {name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
                    for name, path in paths.items()}
        tools_before = tool_hashes()
        self.assertTrue(all(item['sha256'] for item in tools_before.values()), 'actual tool files required')
        common = (HERE / 'user_current_entry_probe.c').read_text(encoding='utf-8')
        common = common[:common.index('int main(void)')]
        old = 'U ABI user_domain_legacy_poll(void){return 0;}'
        self.assertEqual(1, common.count(old))
        common = common.replace(old, 'extern U diagnostic_legacy;\nU ABI user_domain_legacy_poll(void){return diagnostic_legacy;}')
        old = 'U ABI user_bridge_clock(void){return clock_tick++;}'
        self.assertEqual(1, common.count(old))
        common = common.replace(old, 'void diagnostic_observe(void);\nU ABI user_bridge_clock(void){diagnostic_observe();return clock_tick++;}')
        old = block(common, 'U ABI user_bridge_project(void)')
        common = common.replace(old, 'extern U diagnostic_project,diagnostic_nested;\nextern U ABI dong_user_smp_barrier(void);\n' + old.replace(
            '{C(cpu==0', '{if(diagnostic_nested){diagnostic_nested=0;U nested=dong_user_smp_barrier();if(nested)return nested;}if(diagnostic_project)return diagnostic_project;C(cpu==0', 1))
        common += '\nU ABI user_bridge_service_policy(U slot,U event,U frame){(void)slot;(void)event;(void)frame;return 0;}\n'
        c_source = common + (HERE / 'user_smp_failure_probe.c').read_text(encoding='utf-8')
        controls = {
            'overwrite-first-error': ('if atomic_compare_exchange(&(*f).published,0,2)!=0{return;}', 'atomic_store(&(*f).published,2);', 'timeout'),
            'foreign-cpu-slot': ('let actual=user_bridge_cpu();if actual>=16{return;}', 'let actual=cpu as u64;if actual>=16{return;}', 'checked-foreign'),
            'lost-error-code': ('(*f).error_code=code;', '(*f).error_code=0;', 'timeout'),
            'lost-stage': ('(*f).stage=PROGRESS[id].stage;', '(*f).stage=CHECKED;', 'timeout'),
            'published-before-fields': ('atomic_compare_exchange(&(*f).published,0,2)', 'atomic_compare_exchange(&(*f).published,0,1)', 'timeout'),
            'failure-reported-idle': ('}}return 0xffff_ffff_ffff_ffff;', '}}return 0;', 'timeout'),
            'nested-context-lost': ('PROGRESS[0]=previous;', 'PROGRESS[0].stage=SHARED;', 'nested-project'),
            'lost-wait-deadline': ('PROGRESS[cpu].deadline=limit;', 'PROGRESS[cpu].deadline=0;', 'timeout'),
            'lost-acquired-clock': ('PROGRESS[cpu].acquired=user_bridge_clock();', 'PROGRESS[cpu].acquired=0;', 'project'),
            'rewritten-deadline-evidence': ('PROGRESS[cpu].deadline=limit;', 'PROGRESS[cpu].deadline=PROGRESS[cpu].wait_started+1;', 'expired-before-acquire'),
        }

        def run(args, directory, label):
            args = list(map(str, args))
            try:
                result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
            except subprocess.TimeoutExpired as exc:
                record = dict(argv=args, timed_out=True, stdout=str(exc.stdout), stderr=str(exc.stderr))
                (directory / (label + '.json')).write_text(json.dumps(record, indent=2) + '\n')
                commands.append(record)
                raise
            record = dict(argv=args, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
            (directory / (label + '.json')).write_text(json.dumps(record, indent=2) + '\n')
            commands.append(record)
            return result

        try:
            for mode in ('debug', 'release'):
                for variant in ('normal', *controls):
                    directory = output / (mode + '-' + variant)
                    stage = directory / 'source'
                    for name, path in sources.items():
                        text = path.read_text(encoding='utf-8')
                        if name == 'sched.user_bridge' and variant != 'normal':
                            old, new, _ = controls[variant]
                            self.assertEqual(1, text.count(old), variant)
                            text = text.replace(old, new)
                        target = stage / (name.replace('.', '/') + '.dg')
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(text, encoding='utf-8')
                    (directory / 'probe.c').write_text(c_source, encoding='utf-8')
                    compiled = compile_file(stage / 'user_smp_failure_probe.dg', roots=[stage], mode=mode)
                    layouts = {t['full_name']: t for t in compiled.layout_manifest['types']}
                    expected = {'sched.user_bridge.Failure': 224, 'sched.user_bridge.Progress': 48,
                                'sched.user_bridge.Bridge': 64, 'sched.user_domain.Domain': 120,
                                'sched.user_domain.Cpu': 120, 'sched.user_entry_plan.Cpu': 256}
                    for name, size in expected.items():
                        self.assertEqual(size, layouts[name]['size'], name)
                    self.assertEqual(list(range(0, 224, 8)), [f['offset'] for f in layouts['sched.user_bridge.Failure']['fields']])
                    self.assertEqual(list(range(0, 48, 8)), [f['offset'] for f in layouts['sched.user_bridge.Progress']['fields']])
                    (directory / 'layout.json').write_text(json.dumps(compiled.layout_manifest, indent=2) + '\n')
                    assembly = directory / 'probe.asm'
                    assembly.write_text(compiled.assembly, encoding='utf-8')
                    objects = []
                    for name, path in (('dong', assembly), ('entry', ROOT / 'kernel/sched/user_entry.asm'), ('legacy', ROOT / 'kernel/sched/user_legacy.asm')):
                        obj = directory / (name + '.o')
                        result = run([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm),
                                      '-I', str(ROOT / 'include') + os.sep, path, '-o', obj], directory, 'assemble-' + name)
                        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                        objects.append(obj)
                    executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                    result = run([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                                  *([] if os.name == 'nt' else ['-no-pie']), directory / 'probe.c', *objects, '-o', executable], directory, 'link')
                    self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                    scenarios = ('no-active', 'timeout', 'expired-before-acquire', 'hardware', 'checked-foreign', 'invalid-argument',
                                 'invalid-cpu', 'pointer-guard', 'commit', 'project', 'nested-project', 'acquired', 'capture-acquired') if variant == 'normal' else (controls[variant][2],)
                    for scenario in scenarios:
                        result = run([executable, scenario], directory, 'native-' + scenario)
                        self.assertEqual(0 if variant == 'normal' else 1, result.returncode, result.stdout + result.stderr)
                        if variant == 'normal':
                            self.assertIn('USER_SMP_FAILURE_NATIVE_PASS synthetic_hardware=true actual_ap_cpl3_executed=false', result.stdout)
                        else:
                            self.assertIn('user CPL3 current-source oracle line', result.stderr)
                            self.assertNotIn('USER_SMP_FAILURE_NATIVE_PASS', result.stdout)
                        evidence.append(dict(mode=mode, variant=variant, scenario=scenario,
                                             executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                                             object_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in objects},
                                             returncode=result.returncode))
            self.assertEqual(before, hashes())
            self.assertEqual(tools_before, tool_hashes(), 'actual compiler/tool bytes changed')
            passed = True
        except BaseException as exc:
            failure = dict(type=type(exc).__name__, message=str(exc))
            raise
        finally:
            after = hashes()
            tools_after = tool_hashes()
            artifacts = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(output.rglob('*')) if p.is_file() and p != output / 'validation-summary.json'}
            (output / 'validation-summary.json').write_text(json.dumps(dict(passed=passed and before == after and tools_before == tools_after,
                failure=failure, source_before=before, source_after=after, sources_unchanged=before == after,
                tools_before=tools_before, tools_after=tools_after, tools_unchanged=tools_before == tools_after, artifact_sha256=artifacts,
                commands=commands, evidence=evidence, skipped=[], actual_dong_bridge_domain_queue=True,
                synthetic_hardware_boundaries=True, actual_ap_cpl3_executed=False, actual_qemu_executed=False,
                os_build_executed=False, raw_root_available=False, normalized_root_available=False), indent=2) + '\n')
            print('USER_SMP_FAILURE_EVIDENCE', output)
        self.assertTrue(passed and before == after and tools_before == tools_after,
                        'late source/tool instability must fail the unittest as well as its receipt')


if __name__ == '__main__':
    unittest.main(verbosity=2)
