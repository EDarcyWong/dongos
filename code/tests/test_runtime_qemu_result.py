import unittest
from tests import run_runtime_qemu as gate


class RuntimeProtocolTests(unittest.TestCase):
    def fixture(self):
        names = ['platform_' + name for name in gate.PLATFORM] + ['sched_' + name for name in gate.SCHED]
        names += ['runtime_device_plan', 'runtime_spurious_count']
        lines = [b'DONGOS_P2_MEMORY_READY', b'DONGOS_P3_RUNTIME_START', b'DONGOS_P3_IRQ_READY']
        lines += [name.encode() + b'=0x0000000000000000' for name in names]
        lines += [b'DONGOS_P3_THREADS_READY', b'DONGOS_P1_PASS']
        return lines

    def test_projection_retains_actual_completion_and_exact_prior_bytes(self):
        lines = self.fixture()
        projected, values = gate.project_runtime(b'\r\n'.join(lines) + b'\r\n')
        self.assertEqual(b'DONGOS_P2_MEMORY_READY\r\nDONGOS_P1_PASS\r\n', projected)
        self.assertEqual(56, len(values))

    def test_missing_duplicate_reordered_truncated_and_misplaced_proofs_reject(self):
        lines = self.fixture()
        variants = [lines[:4] + lines[5:], lines[:4] + [lines[4]] + lines[4:],
                    lines[:4] + [lines[5], lines[4]] + lines[6:], lines[:-1],
                    [b'DONGOS_P3_RUNTIME_START'] + lines, lines[:1] + [b'unexpected'] + lines[1:]]
        for variant in variants:
            with self.subTest(variant=variant[:5]), self.assertRaises(ValueError):
                gate.project_runtime(b'\r\n'.join(variant) + b'\r\n')
        with self.assertRaises(ValueError):
            gate.project_runtime(b'\r\n'.join(lines))

    def test_success_requires_actual_worker_execution_and_exact_interrupt_ownership(self):
        values = {'platform_' + name: 0 for name in gate.PLATFORM}
        values.update({'sched_' + name: 0 for name in gate.SCHED})
        values.update(runtime_device_plan=0xffffffff80000000, runtime_spurious_count=0)
        p = dict(lapic_pa=0xfee00000, lapic_va=gate.BASE, lapic_id=0, ioapic_count=1,
                 redirection_count=24, pic_master=255, pic_slave=255, timer_vector=0x40,
                 spurious_vector=255, interval_ns=10000000, arm_count=130, stop_count=1,
                 steps=127, tsc_hz=3000000000, timer_mode=2, lapic_hz=62500000,
                 last_tsc=1000000000, last_deadline=1030000000, reference_source=2)
        s = dict(version=1, vector=0x40, ticks=129, switches=65, worker0_ticks=64, worker1_ticks=64,
                 worker0_count=10, worker1_count=20, gpr_checks=30, restore_checks=129,
                 guard_count=2, steps=7, xstate_mode=2, xstate_bytes=576, xcr0=3,
                 worker0_stack_bottom=0xffffffff80010000, worker0_stack_top=0xffffffff80014000,
                 worker0_rsp=0xffffffff80013ff8, worker1_stack_bottom=0xffffffff80016000,
                 worker1_stack_top=0xffffffff8001a000, worker1_rsp=0xffffffff80019ff8)
        values.update({'platform_' + k: v for k, v in p.items()})
        values.update({'sched_' + k: v for k, v in s.items()})
        gate.validate_fields(values, 'normal')
        for key, value in [('sched_ticks', 128), ('sched_switches', 64), ('sched_worker1_count', 0),
                           ('sched_worker0_fail', 1), ('sched_restore_checks', 128),
                           ('platform_arm_count', 129), ('platform_pic_master', 0),
                           ('sched_xstate_mode', 1), ('sched_worker0_rsp', 0x40000000)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.validate_fields({**values, key: value}, 'normal')
