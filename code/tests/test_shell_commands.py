"""Execute unchanged shell command code with independent IPC/process models."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest
import uuid
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_input import command
from tests.test_fat32 import stack_bound
ROOT=Path(__file__).resolve().parents[1]


class ShellCommandTests(unittest.TestCase):
    def test_actual_commands_minimum_file_rights_close_and_terminal_process_snapshots(self):
        directory=ROOT/'build/test/shell-commands'/('run-'+uuid.uuid4().hex[:12]);directory.mkdir(parents=True)
        paths=[ROOT/p for p in ('services/shell/main.dg','services/shell/parser.dg','services/lib/files.dg',
            'services/lib/process.dg','services/lib/process_abi.dg','services/lib/sys.dg','services/lib/abi.dg','services/lib/boot_trace.dg',
            'services/fs/protocol.dg','services/fs/handles.dg','services/fs/path.dg',
            'tests/shell_commands_probe.dg.in','tests/shell_commands_probe.c','tests/test_shell_commands.py')]
        before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        staged=directory/'services';(staged/'shell').mkdir(parents=True)
        for p in paths:
            if p.is_relative_to(ROOT/'services'):
                target=staged/p.relative_to(ROOT/'services');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        original=(ROOT/'services/shell/main.dg').read_bytes();target=staged/'shell/main.dg'
        target.write_bytes(original+(ROOT/'tests/shell_commands_probe.dg.in').read_bytes())
        self.assertEqual(original,target.read_bytes()[:len(original)])
        bad_source=original.decode().replace('\r\n','\n').replace('module shell.main;','module shell.main;\nunsafe extern "sysv64" ("shc_negative_hit") fn native_negative_hit(kind:u64)void;',1)
        terminal='PROCESS_STATE.process==token||(token==LAST_PROCESS&&index==LAST_CONFIGURATION&&PROCESS_STATE.generation==LAST_GENERATION)'
        self.assertEqual(1,bad_source.count(terminal));bad_source=bad_source.replace(terminal,'PROCESS_STATE.process==token',1)
        wait_loop='    loop{\n        var flags=process_abi.NONBLOCK;if found'
        self.assertEqual(1,bad_source.count(wait_loop));bad_source=bad_source.replace(wait_loop,
            '    if !found{native_negative_hit(1);return 0x0511_0003;}\n'+wait_loop,1)
        bad_services=directory/'bad-terminal-services';shutil.copytree(staged,bad_services)
        (bad_services/'shell/main.dg').write_bytes(bad_source.encode()+(ROOT/'tests/shell_commands_probe.dg.in').read_bytes())
        limited=original.decode().replace('\r\n','\n').replace('module shell.main;','module shell.main;\nunsafe extern "sysv64" ("shc_negative_hit") fn native_negative_hit(kind:u64)void;',1)
        bound='(*BOOT).reserved1>process_abi.LIMIT as u64||index>=(*BOOT).reserved1{return 0x0511_0001;}'
        self.assertEqual(1,limited.count(bound))
        limited=limited.replace(bound,'(*BOOT).reserved1>16||index>=(*BOOT).reserved1{native_negative_hit(2);return 0x0511_0001;}',1)
        limited_services=directory/'bad-capacity-services';shutil.copytree(staged,limited_services)
        (limited_services/'shell/main.dg').write_bytes(limited.encode()+(ROOT/'tests/shell_commands_probe.dg.in').read_bytes())
        outcomes=[]
        for label,source_root in (('normal',staged),('bad-terminal',bad_services),('bad-capacity',limited_services)):
          for mode in ('debug','release'):
            out=directory/label/mode;out.mkdir(parents=True);compiled=compile_file(source_root/'shell/main.dg',roots=[source_root],mode=mode)
            bound=stack_bound(compiled.assembly);self.assertLessEqual(bound,8192)
            asm=out/'probe.asm';asm.write_text(compiled.assembly);nasm,cc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and cc)
            for fmt in ('elf64','win64'):command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',out/(fmt+'.o'),asm],out,'assemble-'+fmt)
            # Explicit SysV attributes on the bridge are sufficient. Disabling
            # SSE breaks current MinGW windows.h intrinsics before our code runs.
            executable=out/('probe.exe' if os.name=='nt' else 'probe');flags=[] if os.name=='nt' else ['-no-pie','-D_GNU_SOURCE']
            command([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,
                ROOT/'tests/shell_commands_probe.c',out/('win64.o' if os.name=='nt' else 'elf64.o'),'-o',executable],out,'link')
            result=command([executable],out,'native',success=False)
            if label=='normal':
                self.assertEqual(0,result.returncode,result.stdout+result.stderr)
                self.assertIn('Shell production command checks passed',result.stdout)
            else:
                self.assertEqual(1,result.returncode,result.stdout+result.stderr)
                self.assertIn('SHELL_COMMAND_NEGATIVE_HIT '+('2' if label=='bad-capacity' else '1'),result.stderr)
                self.assertIn('SHELL_COMMAND_ASSERT',result.stderr);self.assertNotIn('unexpected panic',result.stderr)
            outcomes.append(dict(label=label,mode=mode,stack=bound,stdout=result.stdout,stderr=result.stderr))
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        self.assertEqual(before,after)
        (directory/'validation-summary.json').write_text(json.dumps(dict(source_unchanged=True,
            source_sha256=after,results=outcomes,actual_shell_machine_code=True,
            actual_filesystem_kernel_and_process_lifecycle=False),indent=2)+'\n')
        print('SHELL_COMMANDS_EVIDENCE '+str(directory))


if __name__=='__main__':unittest.main(verbosity=2)
