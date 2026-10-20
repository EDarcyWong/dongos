"""Current-source native staging and production build routing inspection.

This is new test infrastructure, not a recovered P6 candidate builder. It never
links an OS or starts a VM. Build routing executes the real production builder
with tool boundaries mocked and stops before its kernel linker can execute.
"""
from pathlib import Path
import hashlib
import json
import shutil
from unittest import mock
from tools import build as production

ROOT = Path(__file__).resolve().parents[1]
TREES = ('kernel', 'services', 'include', 'lang/dongc', 'lang/std', 'lang/examples', 'tools', 'boot')
SUFFIXES = ('.dg', '.asm', '.inc', '.ld', '.py')

def source_inputs():
    paths = [p for tree in TREES for p in sorted((ROOT / tree).rglob('*'))
             if p.is_file() and p.suffix in SUFFIXES]
    paths.append(Path(__file__))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def prepare(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    stage = output / 'source'
    if stage.exists():
        raise ValueError('fresh staging directory required')
    before = source_inputs()
    for name in before:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    def hashes():
        return {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in before}
    if hashes() != before or source_inputs() != before:
        raise ValueError('source changed during native staging')
    manifest = dict(schema=1, contract='current-smp-native-v1', historical_replay=False,
                    built=False, source_root=str(ROOT), source_sha256=before,
                    staged_sha256=hashes(), os_link_executed=False, vm_executed=False)
    (output / 'current-smp-native-source.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return stage / 'kernel', manifest, hashes

class _PlanComplete(Exception):
    pass

def production_plan(output, *, runtime_level=7, test=False):
    """Observe actual production decisions, never simulate a successful build."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    commands, assemblies, services = [], [], []
    from tools import user_services, service_bundle, gen_offsets
    def execute(command):
        values = list(map(str, command)); commands.append(values)
        if 'lang.dongc' in values:
            path = Path(values[values.index('--emit-layout')+1])
            path.write_text(json.dumps(dict(types=[])))
            Path(values[values.index('--emit-asm')+1]).write_text('; HOST-PLAN-ONLY: compiler not executed\n')
        elif '-nostdlib' in values:
            raise _PlanComplete()
        else:
            raise AssertionError('unexpected external command during plan: '+repr(values))
    def assemble(source, destination, **kwargs):
        source = Path(source)
        if not source.is_file(): raise ValueError('missing assembly source '+str(source))
        target = Path(destination) / (source.stem+'.o')
        assemblies.append(dict(source=str(source), output=str(target), **kwargs))
        return target
    def service(source, destination, **kwargs):
        source = Path(source)
        if not source.is_file(): raise ValueError('missing service source '+str(source))
        services.append(str(source)); target = Path(destination)/'program.elf'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'HOST-PLAN-ONLY-NOT-ELF')
        return target
    with mock.patch.object(production,'execute',execute), mock.patch.object(production,'assemble',assemble), \
         mock.patch.object(production,'find_tool',side_effect=lambda name,*args:name), \
         mock.patch.object(user_services,'build_service',service), \
         mock.patch.object(service_bundle,'pack',return_value=b'HOST-PLAN-ONLY'), \
         mock.patch.object(gen_offsets,'generate',return_value='; host routing plan only\n'):
        try:
            production.build(output=output, runtime_level=runtime_level, test=test)
        except _PlanComplete:
            pass
        else:
            raise AssertionError('production routing never reached kernel link boundary')
    return dict(contract='current-production-routing-v1', built=False, historical_replay=False,
                commands=commands, assemblies=assemblies, services=services,
                os_link_executed=False, vm_executed=False)
