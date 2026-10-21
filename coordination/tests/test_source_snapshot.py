"""Real build configuration source modules must survive isolated snapshots."""
from pathlib import Path
import hashlib,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dongos_coordination.runner import inventory,snapshot

class SourceSnapshotTests(unittest.TestCase):
    def test_legitimate_kernel_build_module_is_copied_and_fingerprinted(self):
        with tempfile.TemporaryDirectory()as directory:
            base=Path(directory);source=base/'source';module=source/'kernel/build/storage_profile.dg';module.parent.mkdir(parents=True);module.write_bytes(b'module build.storage_profile;\r\npub const STATIC_USER_POOLS:usize=3;\r\n')
            for rel in ('build/output.bin','services/build/output.bin','tests/build/output.bin','kernel/.local/output.bin'):
                p=source/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'generated')
            before=inventory(source,source_filter=True);self.assertEqual(set(before),{'kernel/build/storage_profile.dg'})
            self.assertEqual(before['kernel/build/storage_profile.dg'],hashlib.sha256(module.read_bytes()).hexdigest())
            target=base/'workspace';self.assertEqual(snapshot(source,target),before)
            self.assertEqual((target/'kernel/build/storage_profile.dg').read_bytes(),module.read_bytes());self.assertEqual(inventory(target),before)
            (target/'kernel/build/storage_profile.dg').write_bytes(b'changed')
            self.assertNotEqual(inventory(target),before);self.assertEqual(inventory(source,source_filter=True),before)
    def test_works_build_outputs_remain_excluded(self):
        with tempfile.TemporaryDirectory()as directory:
            base=Path(directory);source=base/'source';source.mkdir();works=base/'works';p=works/'codex-works/build/output.bin';p.parent.mkdir(parents=True);p.write_bytes(b'generated')
            p=works/'codex-works/src/x.dg';p.parent.mkdir(parents=True);p.write_bytes(b'source')
            target=base/'snapshot';before=snapshot(source,target,works)
            self.assertEqual(set(before),{'codex-works/src/x.dg'});self.assertEqual(inventory(target),before)
if __name__=='__main__':unittest.main()
