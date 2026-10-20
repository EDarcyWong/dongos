"""New synthetic workload routing plan; never a historical builder or OS build.

The plan binds existing source bytes, not fabricated ELF bytes. Executable ELF
and finite CPU tests are independently performed by test_user_smp_worker.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/current_user_smp'
ARGUMENTS = {7: 78117, 8: 88219, 9: 99323, 10: 104729, 11: 115249}
NAMES = {7: 'echo', 8: 'fault', 9: 'waiter', 10: 'ipc-peer', 11: 'fs-reader'}


def workload_plan(output, *, test, runtime_level, user_smp, user_case=None):
    if test is not True or runtime_level != 7 or user_smp is not True:
        raise ValueError('synthetic workload requires explicit test/runtime7/user_smp controls')
    if user_case not in (None, 'omit-xstate'):
        raise ValueError('unknown synthetic workload negative case')
    output = Path(output).resolve()
    source = FIXTURE / 'services/apps/user_smp_worker.dg'
    assembly = source.with_suffix('.asm')
    architecture = ROOT / 'kernel/sched/user_arch.asm'
    inputs = [source, assembly, architecture, Path(__file__)]
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    routes = [dict(configuration=cfg, name=NAMES[cfg], argument=argument,
                   source=str(source), roots=[str(FIXTURE/'services'), str(ROOT/'services'), str(ROOT/'lang/std')],
                   assembly=str(assembly), output=str(output/'services'/NAMES[cfg]/'program.elf'))
              for cfg, argument in ARGUMENTS.items()]
    # Ordinary GUI applications remain current production sources, not workload aliases.
    terminal = dict(configuration=14, name='terminal', source=str(ROOT/'services/apps/gui_terminal.dg'),
                    roots=[str(ROOT/'services'), str(ROOT/'lang/std')])
    for path in [source, assembly, architecture, Path(terminal['source'])]:
        if not path.is_file():
            raise ValueError('missing actual workload routing source: '+str(path))
    arch = dict(source=str(architecture), output=str(output/'user_arch.o'),
                defines=dict(P1_TEST=1, RUNTIME_LEVEL=7, P6_USER_SMP=1,
                             USER_SMP_TEST_NO_XSTATE=int(user_case=='omit-xstate')))
    plan = dict(contract='synthetic-current-user-smp-workload-plan-v1', synthetic_test_workload=True,
                historical_replay=False, built=False, os_link_executed=False, vm_executed=False,
                guest_argument_virtual=0x44000000,actual_cpl3_executed=False, user_case=user_case, source_sha256=hashes,
                workloads=routes, unchanged_terminal=terminal, architecture=arch)
    output.mkdir(parents=True, exist_ok=True)
    (output/'current-user-workload-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    return plan
