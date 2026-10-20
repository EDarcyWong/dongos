"""Source-contract guard against restoring the superseded unproven DMA release API.

Native ownership/failure tests live in test_dma_lease; these source checks are
not evidence that a real device can be stopped, unmapped, or safely reclaimed.
"""
from pathlib import Path
import unittest
from tests.test_service_ipc_cancellation import block

ROOT = Path(__file__).resolve().parents[1]


class DmaHoldContractTests(unittest.TestCase):
    def test_no_unproven_release_export_or_legacy_range(self):
        source = (ROOT / 'kernel/user/memory.dg').read_text()
        for legacy in ('release_dma', 'PINNED_BASE', 'PINNED_PAGES'):
            self.assertNotIn(legacy, source)
        self.assertIn('pub unsafe fn dma_snapshot(', source)

    def test_destroy_and_unshare_keep_valid_rejection_guards(self):
        source = (ROOT / 'kernel/user/memory.dg').read_text()
        for name in ('destroy', 'unshare_range'):
            with self.subTest(name=name):
                body = block(source, 'pub unsafe fn ' + name + '(')
                guard = body[:body.index('return error.InvalidState;')]
                for condition in ('id>=LIMIT', 'PROCESSES[id].ready!=1',
                                  'PINNED[id]', 'user_current_root()==PROCESSES[id].root'):
                    self.assertIn(condition, guard)
                self.assertNotIn('PINNED[id]=false', body)

    def test_compiler_stack_profiles_survive_integration(self):
        source = (ROOT / 'kernel/user/memory.dg').read_text()
        for api in ('stage_compiler', 'stage_compiler_random'):
            self.assertIn('pub unsafe fn ' + api + '(', source)
        self.assertIn('compiler_stack.pages(compiler)', source)
        self.assertIn('stack_top - (stack_pages+1) * 4096', source)
        self.assertIn('plan.page_count + stack_pages >', source)


if __name__ == '__main__':
    unittest.main()
