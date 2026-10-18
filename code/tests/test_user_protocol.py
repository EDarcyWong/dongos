"""Independent adversarial checks of the actual CPL3 serial contract."""
import unittest
from tests.run_user_qemu import FIELDS, project_user


class UserProtocolTests(unittest.TestCase):
    def setUp(self):
        self.rounds = 1000000
        fields = dict.fromkeys(FIELDS, 0)
        fields.update(version=1, process_count=2, expected=self.rounds, roundtrips=self.rounds,
            syscalls=2000015,calls=self.rounds,replies=self.rounds,rejections=5,handles_created=7,
            shared_value=self.rounds,shared_physical=0x500000,start_tsc=100,end_tsc=10100,
            elapsed_tsc=10000,tsc_hz=1000000,elapsed_ns=10000000,
            client_bias=0x10000000,server_bias=0x30010000,client_root=0x100000,server_root=0x200000,
            client_entry=0x10001000,server_entry=0x30011000,notification_bits=4,
            completed=1,steps=31,last_syscall=255)
        self.fields = fields
        self.lines = [b'DONGOS_P3_THREADS_READY',b'DONGOS_P4_USER_START']
        self.lines += [f'user_progress=0x{i:016x}'.encode() for i in range(100000,1000001,100000)]
        self.lines += [f'user_{name}=0x{fields[name]:016x}'.encode() for name in FIELDS]
        self.lines += [b'DONGOS_P4_IPC_READY',b'DONGOS_P1_PASS']

    def encoded(self, lines=None):
        return b'\r\n'.join(self.lines if lines is None else lines) + b'\r\n'

    def test_complete(self):
        projected, fields = project_user(self.encoded(), self.rounds)
        self.assertEqual(self.fields, fields)
        self.assertEqual(b'DONGOS_P3_THREADS_READY\r\nDONGOS_P1_PASS\r\n', projected)

    def test_actual_counters_and_integrity(self):
        for name in ('roundtrips','syscalls','calls','replies','rejections','shared_value','completed',
                     'error_code','user_errors','notification_bits','elapsed_tsc','elapsed_ns','client_entry'):
            with self.subTest(field=name):
                bad = self.encoded().replace(f'user_{name}=0x{self.fields[name]:016x}'.encode(),
                    f'user_{name}=0x{self.fields[name]+1:016x}'.encode())
                with self.assertRaises(ValueError):
                    project_user(bad,self.rounds)

    def test_reordered_duplicate_truncated_or_false_pass(self):
        variants = [self.encoded()[:-1], self.encoded() + b'DONGOS_P1_PASS\r\n',
                    self.encoded().replace(b'DONGOS_P4_IPC_READY',b'DONGOS_P4_IPC_READY\r\nuser_completed=0x0000000000000001'),
                    self.encoded().replace(self.lines[2],self.lines[3]),
                    self.encoded().replace(b'DONGOS_P3_THREADS_READY',b'DONGOS_P1_PASS')]
        for bad in variants:
            with self.assertRaises(ValueError):
                project_user(bad,self.rounds)
