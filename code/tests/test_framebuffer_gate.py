"""Native execution of the actual production GOP writers and cache Gate.

Only safe renderer/atomic fragments execute. Complete entry objects are also
assembled for every supported runtime level; privileged entry code never runs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
import uuid

from lang.dongc import compile_file
from lang.tests.test_dongc import tool
from tools.gen_offsets import generate

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'tests'
ENTRY = ROOT / 'kernel/entry.asm'
READER = ROOT / 'kernel/sched/runtime_cache_reader.asm'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def fragment(source, name):
    start, end = '; ' + name + '_BEGIN', '; ' + name + '_END'
    if source.count(start) != 1 or source.count(end) != 1:
        raise AssertionError('production fragment boundary: ' + name)
    return source.split(start, 1)[1].split(end, 1)[0]


def production_include(source):
    # These strings are slices, never a reimplementation of the instructions,
    # glyphs, panic field offsets, labels or geometry validation.
    rodata = source.split('\ntitle: db ', 1)
    if len(rodata) != 2:
        raise AssertionError('unique production drawing rodata boundary')
    rodata = 'title: db ' + rodata[1].split('\nsection .bss', 1)[0]
    return ('section .text\n' + fragment(source, 'FRAMEBUFFER_GATE_TEXT') +
            fragment(source, 'FRAMEBUFFER_RENDER_TEXT') + '\nsection .rodata\n' +
            rodata + '\nsection .bss\n' + fragment(source, 'FRAMEBUFFER_GATE_STORAGE'))


def change_scope(source, scope, old, new):
    body = fragment(source, scope)
    if body.count(old) != 1:
        raise AssertionError(('mutation must change one production boundary', scope, old))
    return source.replace(body, body.replace(old, new), 1)


def source_census(source):
    """The lone exempt pixel probe precedes Domain/AP/service publication."""
    calls = []
    for path in sorted((ROOT / 'kernel').rglob('*.asm')):
        for match in re.finditer(r'(?m)^\s*(?:call|jmp)\s+memory_active_probe\s*(?:;[^\n]*)?$',
                                 path.read_text(encoding='utf-8')):
            calls.append(path.relative_to(ROOT).as_posix())
    if calls != ['kernel/entry.asm']:
        raise AssertionError(('startup-only framebuffer probe callsites', calls))
    boot = source[:source.index('; FRAMEBUFFER_GATE_TEXT_BEGIN')]
    probe = boot.index('call memory_active_probe')
    for later in ('call screen_draw', 'call runtime_begin', 'call smp_runtime_begin',
                  'call user_runtime_begin', 'call dong_desktop_enable', 'call service_runtime_begin'):
        if boot.index(later) <= probe:
            raise AssertionError('startup GOP probe must precede ' + later)
    render = fragment(source, 'FRAMEBUFFER_RENDER_TEXT')
    if len(re.findall(r'(?m)^\s*call\s+framebuffer_gate_enter\s*$', render)) != 2:
        raise AssertionError('one outer writer for each production renderer')
    if len(re.findall(r'(?m)^\s*call\s+framebuffer_gate_leave\s*$', render)) != 2:
        raise AssertionError('one release for each acquired production renderer')
    nonrender = source.replace(render, '')
    if re.search(r'(?m)^\s*(?:call|jmp)\s+(?:text_draw|screen_hex_draw)\s*$', nonrender):
        raise AssertionError('glyph/hex renderer escaped its outer writer')
    gate = fragment(source, 'FRAMEBUFFER_GATE_TEXT')
    leave = gate.split('framebuffer_gate_leave:', 1)[1]
    if leave.index('sfence') >= leave.index('lock cmpxchg'):
        raise AssertionError('WC stores must be fenced before count release')
    panic = (ROOT / 'kernel/panic.asm').read_text(encoding='utf-8')
    reentry = panic.split('\npanic_reentered:', 1)[1].split('\npanic_select_range:', 1)[0]
    if re.search(r'(?m)^\s*(?:call|push|pop)\b', reentry):
        raise AssertionError('reentrant panic must retain its bounded serial-only path')
    return dict(startup_probe_calls=calls, before_domain_ap_service_publication=True,
                entry_writers=['screen_draw', 'kernel_panic_screen'],
                glyph_and_hex_only_under_outer_writer=True,
                user_compositor_drained=False, hardware_entry_executed=False)


class FramebufferGateTests(unittest.TestCase):
    def test_actual_renderers_guarded_pixels_cache_gate_and_real_bad_sources(self):
        nasm, cc = tool('nasm', 'NASM'), tool('gcc', 'CC')
        self.assertTrue(nasm and cc, 'native tools required; zero skips')
        inputs = sorted(set(
            p for tree in ('kernel', 'include', 'lang/examples', 'lang/std', 'lang/dongc')
            for p in (ROOT / tree).rglob('*') if p.is_file() and p.suffix in ('.dg', '.asm', '.inc', '.py')
        ) | {Path(__file__), HERE / 'framebuffer_gate_probe.c', HERE / 'framebuffer_gate_probe.asm',
             ROOT / 'tools/gen_offsets.py', ROOT / 'lang/tests/test_dongc.py', ROOT / 'docs/p2-framebuffer-gate.md'})
        frozen = lambda: {p.relative_to(ROOT).as_posix(): sha(p) for p in inputs}
        before = frozen()
        tools = {name: dict(path=str(Path(path).resolve()), sha256=sha(path))
                 for name, path in [('python', sys.executable), ('nasm', nasm), ('cc', cc)]}
        state = ROOT / 'build/test/framebuffer-gate' / ('run-' + uuid.uuid4().hex[:12])
        state.mkdir(parents=True)
        write(state / 'source-before.json', before)
        write(state / 'tools-before.json', tools)
        commands, cases, complete_objects = [], [], []
        original = ENTRY.read_text(encoding='utf-8')
        cache_source = READER.read_text(encoding='utf-8')
        cache_gate = cache_source.split('runtime_cache_gate_enter:', 1)
        self.assertEqual(2, len(cache_gate))
        cache_gate = ('section .text\nruntime_cache_gate_enter:' +
                      cache_gate[1].split('; Hardware(action, request, completed-alltag-sequence, Reading*).', 1)[0])
        self.assertNotIn('runtime_cache_hardware:', cache_gate)
        self.assertNotRegex(cache_gate, r'(?mi)^\s*(?:extern|wrmsr|rdmsr|wbinvd|cli|sti)\b')
        mutants = {
            'omit-screen-enter': ('FRAMEBUFFER_RENDER_TEXT',
                '    push r15\n    call framebuffer_gate_enter\n', '    push r15\n    mov eax,1\n'),
            'omit-panic-enter': ('FRAMEBUFFER_RENDER_TEXT',
                '    mov r13, rdi\n    call framebuffer_gate_enter\n', '    mov r13, rdi\n    mov eax,1\n'),
            'omit-screen-leave': ('FRAMEBUFFER_RENDER_TEXT',
                '    mov ebx,eax\n    call framebuffer_gate_leave\n', '    mov ebx,eax\n'),
            'omit-panic-leave': ('FRAMEBUFFER_RENDER_TEXT',
                '.done:\n    call framebuffer_gate_leave\n.restore:', '.done:\n.restore:'),
            'ignore-closed-closing': ('FRAMEBUFFER_GATE_TEXT',
                '    shr rdx,32\n    jnz .no\n    cmp eax,-1',
                '    shr rdx,32\n    ; wrong source ignores closed/closing/reserved bits\n    cmp eax,-1'),
            'getter-wrong-static-address': ('FRAMEBUFFER_GATE_TEXT',
                'kernel_framebuffer_gate_get:\n    lea rax,[rel framebuffer_gate]',
                'kernel_framebuffer_gate_get:\n    lea rax,[rel framebuffer_gate+8]'),
        }
        # The writer-address mutant changes the actual operands in both real
        # helpers while leaving the independent getter/storage oracle intact.
        writer_wrong = fragment(original, 'FRAMEBUFFER_GATE_TEXT')
        prefix, writers = writer_wrong.split('framebuffer_gate_enter:', 1)
        self.assertEqual(4, writers.count('[rel framebuffer_gate]'))
        wrong_writer_source = original.replace(writer_wrong,
            prefix + 'framebuffer_gate_enter:' + writers.replace('[rel framebuffer_gate]', '[rel framebuffer_gate+8]'), 1)
        expected = 2 * (2 + len(mutants))

        def run(command, directory, label, expected_rc=0):
            argv = list(map(str, command))
            try:
                completed = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired as error:
                receipt = dict(argv=argv, cwd=str(ROOT), timeout_seconds=120, timed_out=True,
                               stdout=str(error.stdout or ''), stderr=str(error.stderr or ''))
                write(directory / (label + '.json'), receipt)
                commands.append(dict(directory=directory.relative_to(state).as_posix(), label=label, **receipt))
                raise
            receipt = dict(argv=argv, cwd=str(ROOT), returncode=completed.returncode,
                           stdout=completed.stdout, stderr=completed.stderr)
            write(directory / (label + '.json'), receipt)
            commands.append(dict(directory=directory.relative_to(state).as_posix(), label=label, **receipt))
            self.assertEqual(expected_rc, completed.returncode, completed.stdout + completed.stderr)
            return completed

        try:
            write(state / 'writer-census.json', source_census(original))
            help_text = run([nasm, '-h'], state, 'nasm-help').stdout
            if re.search(r'(?m)^\s*-h\s+-\S+', help_text):
                help_text += '\n' + run([nasm, '-h', '-w'], state, 'nasm-warning-help').stdout
            flags = ['-Wall', '-Werror'] + ['-w-' + warning
                for warning in ('reloc-rel-dword', 'reloc-abs-qword')
                if re.search(r'(?m)^\s*' + re.escape(warning) + r'\s', help_text)]
            run([cc, '--version'], state, 'cc-version')
            # Fresh compiler-derived layouts only. This is not an OS build and
            # the emitted Dong program is neither assembled nor executed here.
            compiled = compile_file(ROOT / 'kernel/memory_probe.dg',
                roots=[ROOT / 'kernel', ROOT / 'lang/std', ROOT / 'lang/examples'], mode='debug')
            layout = compiled.layout_manifest
            write(state / 'layout.json', layout)
            write(state / 'layout-generation.json', dict(api='lang.dongc.compile_file',
                source='kernel/memory_probe.dg', mode='debug', roots=['kernel', 'lang/std', 'lang/examples'],
                emitted_dong_program_executed=False, actual_os_build=False))
            includes = state / 'includes'
            includes.mkdir()
            for filename, typename, alias in (
                ('bootinfo_layout.inc', 'boot.abi.BootInfo', None),
                ('memory_layout.inc', 'boot.memory_resources.Layout', 'MemoryLayout'),
                ('memory_report.inc', 'boot.memory_startup.Report', 'MemoryReport'),
                ('memory_resource.inc', 'boot.memory_resources.Resource', 'MemoryResource'),
                ('runtime_display.inc', 'boot.runtime_view.Display', 'RuntimeDisplay'),
                ('runtime_view.inc', 'boot.runtime_view.View', 'RuntimeView'),
                ('control_state.inc', 'boot.preflight.State', 'ControlState'),
                ('control_plan.inc', 'boot.preflight.Plan', 'ControlPlan'),
                ('activation_report.inc', 'boot.activation.Report', 'ActivationReport'),
                ('mutation_report.inc', 'boot.live_memory.Report', 'MutationReport'),
                ('hardening_report.inc', 'cpu.hardening.Report', 'HardeningReport'),
                ('object_memory_report.inc', 'boot.object_memory.Report', 'ObjectMemoryReport'),
                ('acpi_report.inc', 'boot.acpi_startup.Report', 'AcpiReport')):
                (includes / filename).write_text(generate(layout, typename, alias), encoding='ascii')
            write(state / 'generated-includes.json', {p.name: sha(p) for p in sorted(includes.glob('*.inc'))})
            display = next(t for t in layout['types'] if t['full_name'] == 'boot.runtime_view.Display')
            self.assertEqual(48, display['size'])
            self.assertEqual([0, 8, 16, 24, 32, 40], [f['offset'] for f in display['fields']])
            for level in (0, 3, 4, 5, 6, 7):
                for fmt in ('elf64', 'win64'):
                    obj = state / ('entry-runtime%d-%s.o' % (level, fmt))
                    run([nasm, '-f', fmt, *flags, '-I', str(ROOT / 'include') + os.sep,
                         '-I', str(includes) + os.sep, '-DRUNTIME_LEVEL=' + str(level),
                         '-l', obj.with_suffix('.lst'), ENTRY, '-o', obj], state, obj.stem)
                    complete_objects.append(dict(runtime=level, format=fmt, sha256=sha(obj)))
            sources = [('production', original), *[(name, change_scope(original, *spec))
                       for name, spec in mutants.items()], ('writer-wrong-static-address', wrong_writer_source)]
            for optimization in ('O0', 'O2'):
                for name, source in sources:
                    with self.subTest(optimization=optimization, source=name):
                        directory = state / optimization / name
                        directory.mkdir(parents=True)
                        stage_entry = directory / 'entry.asm'
                        stage_entry.write_text(source, encoding='utf-8')
                        if name in mutants:
                            scope, old, new = mutants[name]
                            write(directory / 'mutation.json', dict(scope=scope, old=old, new=new,
                                source_sha256=before['kernel/entry.asm'], actual_sha256=sha(stage_entry)))
                        elif name == 'writer-wrong-static-address':
                            write(directory / 'mutation.json', dict(scope='FRAMEBUFFER_GATE_TEXT helpers',
                                old='[rel framebuffer_gate]', new='[rel framebuffer_gate+8]', changed_operands=4,
                                source_sha256=before['kernel/entry.asm'], actual_sha256=sha(stage_entry)))
                        actual = production_include(source)
                        (directory / 'framebuffer-production.inc').write_text(actual, encoding='utf-8')
                        (directory / 'framebuffer-cache-gate.inc').write_text(cache_gate, encoding='utf-8')
                        write(directory / 'extraction.json', dict(source_sha256=sha(stage_entry),
                            production_source_sha256=before['kernel/entry.asm'],
                            production_fragment_sha256=sha(directory / 'framebuffer-production.inc'),
                            cache_source_sha256=before['kernel/sched/runtime_cache_reader.asm'],
                            cache_fragment_sha256=sha(directory / 'framebuffer-cache-gate.inc'),
                            source_is_mutant=name != 'production', fragments_are_verbatim_slices=True))
                        objects = {}
                        for fmt in ('elf64', 'win64'):
                            obj = directory / (fmt + '.o')
                            run([nasm, '-f', fmt, *flags, '-I', str(directory) + os.sep,
                                 '-I', str(includes) + os.sep, '-I', str(ROOT / 'include') + os.sep,
                                 '-l', directory / (fmt + '.lst'), HERE / 'framebuffer_gate_probe.asm',
                                 '-o', obj], directory, fmt)
                            objects[fmt] = obj
                        executable = directory / ('probe.exe' if os.name == 'nt' else 'probe')
                        run([cc, '-std=c11', '-' + optimization, '-D__USE_MINGW_ANSI_STDIO=1',
                             '-Wall', '-Wextra', '-Werror', *([] if os.name == 'nt' else ['-no-pie']),
                             HERE / 'framebuffer_gate_probe.c', objects['win64' if os.name == 'nt' else 'elf64'],
                             '-o', executable], directory, 'link')
                        executed = run([executable], directory, 'execute', 0 if name == 'production' else 1)
                        if name == 'production':
                            self.assertIn('framebuffer gate production renderers passed', executed.stdout)
                            self.assertIn('privileged entry and actual guest not executed', executed.stdout)
                        else:
                            self.assertIn('framebuffer gate oracle case=', executed.stderr)
                            self.assertIn('returned normally', executed.stderr)
                        cases.append(dict(optimization=optimization, source=name,
                            source_sha256=sha(stage_entry), objects={f: sha(o) for f, o in objects.items()},
                            executable_sha256=sha(executable), normal_exit=True,
                            expected_returncode=0 if name == 'production' else 1))
                        self.assertEqual(before, frozen())
        finally:
            after = frozen()
            tool_after = {name: dict(path=v['path'], sha256=sha(v['path'])) for name, v in tools.items()}
            write(state / 'source-after.json', after)
            write(state / 'tools-after.json', tool_after)
            write(state / 'commands.json', commands)
            write(state / 'result.json', dict(passed=len(cases) == expected and before == after and tools == tool_after,
                expected_cases=expected, cases=cases, complete_entry_objects=complete_objects,
                source_stable=before == after, tools_stable=tools == tool_after,
                production_renderers_native_executed=any(c['source'] == 'production' for c in cases),
                privileged_entry_executed=False, actual_guest_executed=False, actual_os_build=False,
                wc_hardware_ordering_or_nmi_guest_proven=False, user_compositor_drained=False))
        self.assertEqual(expected, len(cases))
        self.assertEqual(before, after)
        self.assertEqual(tools, tool_after)
        print('FRAMEBUFFER_GATE_NATIVE_EVIDENCE', state)


if __name__ == '__main__':
    unittest.main(verbosity=2)
