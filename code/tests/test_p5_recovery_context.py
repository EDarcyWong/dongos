"""Run exact services 0x63/retire_one and host retirement against a C oracle.

Hardware, scheduler and memory boundaries are explicit stubs. This proves the
kernel wiring and immutable receipts, not guest execution or DMA drain.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
import uuid

HERE = Path(__file__).resolve().parent
ROOT = next((p / 'code' if (p / 'code/lang/dongc').is_dir() else p
             for p in HERE.parents if (p / 'code/lang/dongc').is_dir() or (p / 'lang/dongc').is_dir()), None)
if ROOT is None:
    raise RuntimeError('Cannot find DongOS compiler root')
sys.path.insert(0, str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags, tool


def block(source, needle):
    start = source.index(needle)
    opening = source.index('{', start)
    level, end = 1, opening + 1
    while level:
        if source[end] == '{': level += 1
        elif source[end] == '}': level -= 1
        end += 1
    return source[start:end]


CANDIDATE = HERE.parent / 'src/p5/user'
PRODUCTION = CANDIDATE if (CANDIDATE / 'services.dg').is_file() else ROOT / 'kernel/user'
SOURCES = [PRODUCTION / 'services.dg', PRODUCTION / 'device_host.dg', ROOT / 'kernel/user/memory.dg',
           ROOT / 'kernel/user/device_manager.dg', ROOT / 'services/drivers/device_policy.dg',
           ROOT / 'kernel/user/abi.dg', ROOT / 'services/lib/device_abi.dg',
           HERE / 'p5_recovery_context_fixture.dg', HERE / 'p5_recovery_context_probe.c', Path(__file__).resolve()]


def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}


class P5RecoveryContextTests(unittest.TestCase):
    def command(self, args, directory, label):
        args = list(map(str, args))
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=90)
        (directory / (label + '.json')).write_text(json.dumps(dict(
            args=args, cwd=str(ROOT), returncode=result.returncode,
            stdout=result.stdout, stderr=result.stderr), indent=2) + '\n')
        return result

    def prepare(self, mode, mutation):
        directory = ROOT / 'build/test/p5-recovery-context' / ('run-' + uuid.uuid4().hex[:12])
        directory.mkdir(parents=True)
        before = hashes()
        (directory / 'source-before.json').write_text(json.dumps(before, indent=2) + '\n')
        services, host = SOURCES[0].read_text(), SOURCES[1].read_text()
        if mutation == 'lost-error-snapshot':
            old = 'err(e)=>{if dma_tracked{device_host.dma_finish(CURRENT,dma_owner,dma_root,dma_generation,e);}try device_host.dma_result(acquired);}'
            self.assertEqual(services.count(old), 1)
            services = services.replace(old, 'err(e)=>{try device_host.dma_result(acquired);}')
        elif mutation == 'replace-old-owner-root':
            old = 'if DMA_CONTEXTS[slot].present!=0{return error.abi.Busy;}'
            self.assertEqual(host.count(old), 1)
            host = host.replace(old, 'if DMA_CONTEXTS[slot].present!=0{DMA_CONTEXTS[slot]=EMPTY_DMA_CONTEXT;}')
            old = 'match memory.dma_snapshot(slot,&previous){ok=>{return error.abi.Busy;},err(e)=>{},}'
            self.assertEqual(host.count(old), 1)
            host = host.replace(old, 'match memory.dma_snapshot(slot,&previous){ok=>{},err(e)=>{},}')
        (directory / 'production-services.dg').write_text(services)
        (directory / 'production-device_host.dg').write_text(host)
        template = (HERE / 'p5_recovery_context_fixture.dg').read_text()
        replacements = {
            '// PRODUCTION_HARDWARE': block(host, 'unsafe fn hardware('),
            '// PRODUCTION_CONTEXT': host.split('// P5_CONTEXT_BEGIN', 1)[1].split('// P5_CONTEXT_END', 1)[0],
            '// PRODUCTION_HOST_REVOKE': block(host, 'pub unsafe fn revoke_owner('),
            '// PRODUCTION_HOST_MANAGER': block(host, 'pub unsafe fn revoke('),
            '// PRODUCTION_SYSCALL': block(services, 'if code==0x63 {'),
            '// PRODUCTION_RETIRE': block(services, 'unsafe fn retire_one('),
        }
        for marker, value in replacements.items():
            self.assertEqual(template.count(marker), 1)
            template = template.replace(marker, value)
        # Exact pure-ledger identity/authentication routines keep the stub from
        # accidentally accepting malformed binding/index fields.
        ledger = (ROOT / 'kernel/user/device_manager.dg').read_text()
        policy = (ROOT / 'services/drivers/device_policy.dg').read_text()
        template = template.replace(block(template, 'pub unsafe fn same_identity('), block(policy, 'pub unsafe fn same_identity('))
        template = template.replace(block(template, 'pub unsafe fn binding('), '\n'.join(
            block(ledger, name) for name in ('unsafe fn require(', 'unsafe fn index(', 'pub unsafe fn binding(')))
        sections = re.split(r'(?m)^// FILE (.+)\n', template)
        for i in range(1, len(sections), 2):
            path = directory / sections[i].strip()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(sections[i + 1])
        for source, target in ((ROOT / 'kernel/user/abi.dg', 'user/abi.dg'),
                               (ROOT / 'services/lib/device_abi.dg', 'lib/device_abi.dg')):
            path = directory / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read_bytes())
        stdout, stderr = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                compiled = compile_file(directory / 'p5_recovery_context_fixture.dg', roots=[directory], mode=mode)
            returncode = 0
        except Exception as error:
            returncode = 1
            stderr.write(repr(error))
            raise
        finally:
            (directory / 'compile.json').write_text(json.dumps(dict(
                args=['compile_file', str(directory / 'p5_recovery_context_fixture.dg'), '--mode', mode, '--roots', str(directory)],
                returncode=returncode, stdout=stdout.getvalue(), stderr=stderr.getvalue()), indent=2) + '\n')
            after = hashes()
            (directory / 'source-after.json').write_text(json.dumps(after, indent=2) + '\n')
            self.assertEqual(before, after)
        layout = {x['full_name']: x for x in compiled.layout_manifest['types']}
        self.assertEqual(424, layout['user.device_host.DmaContext']['size'])
        asm = directory / 'probe.asm'
        asm.write_text(compiled.assembly)
        (directory / 'binding.json').write_text(json.dumps(dict(mode=mode, mutation=mutation,
            candidate=str(PRODUCTION), fragments={k: hashlib.sha256(v.encode()).hexdigest() for k,v in replacements.items()},
            production_sha256={n:hashlib.sha256(v.encode()).hexdigest() for n,v in [('services',services),('device_host',host)]}), indent=2) + '\n')
        return directory, asm

    def test_debug_release_production_paths_and_real_mutants(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'NASM and GCC are required; native checks must not skip')
        for mode in ('debug', 'release'):
            for mutation in (None, 'lost-error-snapshot', 'replace-old-owner-root'):
                with self.subTest(mode=mode, mutation=mutation):
                    directory, asm = self.prepare(mode, mutation)
                    obj = directory / 'probe.o'
                    exe = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                    result = self.command([nasm, '-f', 'win64' if os.name == 'nt' else 'elf64', *nasm_flags(nasm), asm, '-o', obj], directory, 'assemble')
                    self.assertEqual(result.returncode, 0, result.stderr[:6000])
                    result = self.command([cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        *([] if os.name == 'nt' else ['-no-pie']), HERE / 'p5_recovery_context_probe.c', obj, '-o', exe], directory, 'link')
                    self.assertEqual(result.returncode, 0, result.stderr[:6000])
                    result = self.command([exe], directory, 'execute')
                    after_execute = hashes()
                    (directory / 'source-after-execute.json').write_text(json.dumps(after_execute, indent=2) + '\n')
                    if mutation:
                        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                        self.assertIn('P5 context check failed', result.stderr)
                        expected = 'snapshot_status==2' if mutation == 'lost-error-snapshot' else 'p5_call(131072,4096)==BUSY'
                        self.assertIn(expected, result.stderr)
                    else:
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertIn('P5 context native checks passed', result.stdout)
                    self.assertEqual(json.loads((directory / 'source-before.json').read_text()), after_execute)
                    print('P5 native evidence:', directory, mode, mutation or 'production')


if __name__ == '__main__':
    unittest.main()
