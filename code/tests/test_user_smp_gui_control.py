"""Host controls for the actual shared GUI helper; no VM, compiler or guest writes."""
import copy
import hashlib
import unittest
from unittest import mock

from tests import run_current_user_smp_qemu as runner


def fixture(running=(14, 15, 16, 17)):
    """New host data, never a substitute for an actual guest observation."""
    c = dict(sequence=20, configs=[], snapshots=[], slots=[runner.life.NONE] * 32,
             incarnations=[0] * 16, configurations=[runner.life.NONE] * 16, events=[])
    for cfg in range(32):
        flags = 7 if cfg in (0, 1, 3, 6) else 5 if cfg < 7 else 4 if cfg == 13 else 9 if 14 <= cfg < 18 else 8
        c['configs'].append(dict(id=cfg if cfg < 18 else 0, flags=flags if cfg < 18 else 0,
                                 dependencies=runner.life.DEPS[cfg] if cfg < 18 else 0))
        c['snapshots'].append(dict(configuration=cfg, process=0, generation=0, state=0,
                                   status=0, sequence=0, argument=0))
    for cfg, slot, incarnation, generation in (
            *((cfg, cfg, 1, 1) for cfg in (*range(7), 13)),
            (14, 10, 3, 11), (15, 8, 5, 17), (16, 7, 7, 23), (17, 9, 9, 29)):
        if cfg >= 14 and cfg not in running:
            continue
        c['snapshots'][cfg].update(process=(incarnation << 8) | (slot + 1), generation=generation, state=2)
        c['slots'][cfg] = slot
        c['incarnations'][slot] = incarnation
        c['configurations'][slot] = cfg
    return c


def ps_body(c):
    return b''.join(('PROCESS ' + name + ' id=' + str(cfg) + ' token=' + str(c['snapshots'][cfg]['process'])
                     + ' generation=' + str(c['snapshots'][cfg]['generation'])
                     + ' state=' + str(c['snapshots'][cfg]['state'])
                     + ' status=' + str(c['snapshots'][cfg]['status']) + '\r\n').encode('ascii')
                    for cfg, name in enumerate(runner.NAMES))


class Guest:
    """Stateful host transport using the production fresh_response parser."""
    def __init__(self, c=None):
        self.c = copy.deepcopy(fixture() if c is None else c)
        self.raw = bytearray(b'old unrelated UART output\r\n> ')
        self.stopped = True
        self.commands = []
        self.evidence = {}
        self.reads = 0
        self.on_catalog = None
        self.before_command = None
        self.on_command = None
        self.body_change = None
        self.receipt_change = None

    def pause(self):
        self.stopped = True

    def catalog(self):
        if not self.stopped:
            raise AssertionError('unpaused Catalog read')
        self.reads += 1
        if self.on_catalog:
            self.on_catalog(self)
        return copy.deepcopy(self.c)

    def shell(self, command, expected=None, *, expect_error=False, exact=None):
        if not self.stopped and not getattr(self, 'historical_capture', False):
            raise AssertionError('command did not start from a pause')
        self.commands.append(command)
        self.stopped = False
        start = len(self.raw)
        if self.before_command:
            self.before_command(self, command)
        if command == 'ps':
            body = ps_body(self.c)
        else:
            if not command.startswith('kill '):
                raise AssertionError('unsupported helper command: ' + command)
            token = int(command[5:])
            targets = [cfg for cfg, s in enumerate(self.c['snapshots']) if s['process'] == token]
            if len(targets) != 1:
                body = b'ERROR 0x0000000005110003\r\n'
            else:
                cfg = targets[0]
                if cfg not in runner.GUI_CONFIGS:
                    raise AssertionError('helper attempted an essential or unrelated kill')
                slot = self.c['slots'][cfg]
                self.c['sequence'] += 1
                self.c['snapshots'][cfg].update(process=0, state=5, status=0, sequence=self.c['sequence'])
                self.c['slots'][cfg] = runner.life.NONE
                self.c['configurations'][slot] = runner.life.NONE
                body = ('KILL OK token=' + str(token) + ' generation=0 state=5 status=0\r\n').encode('ascii')
        if self.body_change:
            body = self.body_change(command, body)
        segment = command.encode('ascii') + b'\r\n' + body + b'> '
        self.raw.extend(segment)
        if self.on_command:
            self.on_command(self, command)
        response = runner.life.fat.fresh_response(segment, command, expected=expected,
                                                   expect_error=expect_error, exact=exact)
        if response is None:
            raise AssertionError('fixture failed to produce a complete response')
        self.pause()
        receipt = dict(command=command, command_utf8_sha256=hashlib.sha256(command.encode()).hexdigest(),
                       serial_offset=start, serial_segment_sha256=hashlib.sha256(segment).hexdigest(), **response)
        if self.receipt_change:
            self.receipt_change(command, receipt)
        return receipt


class CapturedCatalog:
    """Explicit synthetic decoding boundary, never an actual RAM or VM receipt."""
    def __init__(self, catalog, epoch, serial_offset, phase, events, chunks):
        self.epoch, self.serial_offset = epoch, serial_offset
        self._catalog, self._phase, self._events = copy.deepcopy(catalog), phase, events
        self.chunks = chunks
        self.boot_info_ref = dict(epoch=epoch, length=160, bulk_id='e%d:boot-info' % epoch,
                                  offset=0, physical=4096, file='synthetic-boot.bin',
                                  sha256=hashlib.sha256(bytes(160)).hexdigest())
        self._registers = [dict(epoch=epoch, cpu_index=cpu, file='synthetic-reg%d.txt' % cpu,
                                source_id='e%d:r%d' % (epoch, cpu)) for cpu in range(4)]
        self.ref_epoch = epoch

    def register_ref(self, cpu):
        return copy.deepcopy(self._registers[cpu])

    def catalog(self):
        if not self._phase['running']:
            raise AssertionError('heavy historical decode before actual synthetic cont')
        self._events.append(('catalog', self.epoch))
        self.chunks.append(dict(epoch=self.ref_epoch, file='synthetic-catalog-%d.bin' % self.epoch))
        return copy.deepcopy(self._catalog)


class HistoricalGuest(Guest):
    """Fresh synthetic epoch/transport owner, with no running Catalog fallback."""
    historical_capture = True

    def __init__(self):
        super().__init__()
        self._epoch = 1
        self.phase = dict(running=False)
        self.events, self.history_chunks = [], []
        self.image_change = None
        self.resume_error = None
        self.confirm_running = True

    @property
    def current_epoch(self):
        if not self.stopped:
            raise AssertionError('live epoch read while running')
        return self._epoch

    def pause(self):
        if not self.stopped:
            self._epoch += 1
        self.stopped = True
        self.phase['running'] = False

    def capture_image(self, label):
        if label != 'gui-catalog':
            raise AssertionError('wrong explicit observation label')
        self.pause()
        self.reads += 1
        if self.on_catalog:
            self.on_catalog(self)
        image = CapturedCatalog(self.c, self._epoch, len(self.raw), self.phase,
                                self.events, self.history_chunks)
        self.events.append(('capture', self._epoch))
        if self.image_change:
            self.image_change(self, image)
        return image

    def resume(self):
        self.events.append(('resume', self._epoch))
        if self.resume_error is not None:
            raise self.resume_error
        if self.confirm_running:
            self.stopped = False
            self.phase['running'] = True

    def catalog(self):
        raise AssertionError('historical profile used live Guest.catalog')

    def shell(self, command, **kwargs):
        self.events.append(('shell', command))
        return super().shell(command, **kwargs)


class Tests(unittest.TestCase):
    def test_all_running_follow_current_configuration_tokens_not_physical_ids(self):
        g = Guest()
        initial = copy.deepcopy(g.c)
        with mock.patch('subprocess.Popen', side_effect=AssertionError('host control started a VM')):
            report = runner.close_gui(g)
        self.assertEqual(['ps'] + ['kill ' + str(initial['snapshots'][cfg]['process'])
                                  for cfg in runner.GUI_CONFIGS], g.commands)
        self.assertEqual(['killed'] * 4, [r['action'] for r in report['clients']])
        self.assertTrue(report['essential_identities_preserved'])
        self.assertIs(report, g.evidence['gui_controls'][0])
        self.assertTrue(report['completed'])
        for cfg in (*range(7), 13):
            self.assertEqual(runner._gui_owner(initial, cfg), runner._gui_owner(g.c, cfg))
        for record in report['clients']:
            self.assertEqual(5, record['after']['state'])
            self.assertEqual(record['before']['generation'], record['after']['generation'])
            self.assertEqual(0, record['after']['process'])
            receipt = record['command']
            at, size = receipt['serial_offset'], receipt['verified_serial_length']
            self.assertEqual(receipt['verified_serial_sha256'], hashlib.sha256(g.raw[at:at + size]).hexdigest())
        self.assertTrue(g.stopped)

    def test_partial_and_all_nonrunning_use_real_states_without_kill(self):
        c = fixture((15, 17))
        c['snapshots'][14].update(generation=2, state=3, status=99)
        c['snapshots'][16].update(generation=4, state=4, status=6)
        g = Guest(c)
        result = runner.close_gui(g)
        self.assertEqual(['already-stopped', 'killed', 'already-stopped', 'killed'],
                         [r['action'] for r in result['clients']])
        self.assertEqual(3, len(g.commands))
        c = fixture(())
        for cfg, state in zip(runner.GUI_CONFIGS, (0, 3, 4, 5)):
            c['snapshots'][cfg].update(state=state, generation=int(state != 0), status=state)
        g = Guest(c)
        self.assertEqual(['already-stopped'] * 4, [r['action'] for r in runner.close_gui(g)['clients']])
        self.assertEqual(['ps'], g.commands)

    def test_bad_ps_is_rejected_before_any_kill(self):
        changes = (
            lambda b: b.replace(b'PROCESS terminal id=14', b'PROCESS shell id=14'),
            lambda b: b.replace(b'id=14', b'id=15'),
            lambda b: b.replace(b'generation=11', b'generation=12'),
            lambda b: b.replace(b'token=779', b'token=257'),
            lambda b: b + b.splitlines()[0] + b'\r\n',
            lambda b: b + b'ignored junk\r\n',
            lambda b: b.rsplit(b'PROCESS settings', 1)[0],
            lambda b: b'unknown command\r\n',
        )
        for change in changes:
            g = Guest()
            g.body_change = lambda command, body: change(body) if command == 'ps' else body
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.close_gui(g)
            self.assertEqual(['ps'], g.commands)

    def test_bad_kill_cannot_be_success_or_a_skip(self):
        changes = (
            lambda b: b.replace(b'token=779', b'token=257'),
            lambda b: b.replace(b'generation=0', b'generation=11'),
            lambda b: b.replace(b'state=5', b'state=4'),
            lambda b: b.replace(b'status=0', b'status=1'),
            lambda b: b + b,
            lambda b: b'',
            lambda b: b'ERROR 0x0000000005110003\r\n',
            lambda b: b'unknown command\r\n',
        )
        for change in changes:
            g = Guest()
            g.body_change = lambda command, body: change(body) if command.startswith('kill ') else body
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner.close_gui(g)
            self.assertEqual(['ps', 'kill 779'], g.commands)
            self.assertFalse(g.evidence['gui_controls'][0]['completed'])

    def test_old_or_forged_receipts_do_not_replace_fresh_uart(self):
        for command in ('ps', 'kill 779'):
            for key, value in (('serial_offset', 0), ('command', 'kill 257'),
                               ('command_utf8_sha256', '0' * 64), ('response_hex', ''),
                               ('complete_echo_and_new_prompt_verified', False), ('error_code', 1)):
                g = Guest()
                g.receipt_change = lambda actual, receipt: receipt.update({key: value}) if actual == command else None
                with self.subTest(command=command, key=key), self.assertRaises(ValueError):
                    runner.close_gui(g)

    def test_catalog_alias_role_and_stale_identity_fail_before_commands(self):
        def mutate(kind):
            c = fixture()
            if kind == 'essential-token': c['snapshots'][14]['process'] = c['snapshots'][0]['process']
            if kind == 'incarnation': c['incarnations'][10] += 1
            if kind == 'slot': c['slots'][14] = 0
            if kind == 'inverse': c['configurations'][10] = 0
            if kind == 'reserved-slot': c['slots'][14] = 13
            if kind == 'essential-flag': c['configs'][14]['flags'] |= 4
            if kind == 'restart-flag': c['configs'][14]['flags'] |= 2
            if kind == 'wrong-config': c['configs'][14]['id'] = 0
            if kind == 'wrong-dependency': c['configs'][14]['dependencies'] = 2
            if kind == 'fake-stopped': c['snapshots'][14]['state'] = 5
            if kind == 'dead-shell':
                c['snapshots'][0].update(process=0, state=3)
                c['slots'][0] = c['configurations'][0] = runner.life.NONE
            return c
        for kind in ('essential-token', 'incarnation', 'slot', 'inverse', 'reserved-slot', 'essential-flag',
                     'restart-flag', 'wrong-config', 'wrong-dependency', 'fake-stopped', 'dead-shell'):
            g = Guest(mutate(kind))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runner.close_gui(g)
            self.assertEqual([], g.commands)

    def test_changed_generation_after_ps_does_not_kill_replacement(self):
        g = Guest()
        def change(guest, command):
            if command == 'ps': guest.c['snapshots'][14]['generation'] += 1
        g.on_command = change
        with self.assertRaisesRegex(ValueError, 'generation changed'):
            runner.close_gui(g)
        self.assertEqual(['ps'], g.commands)

    def test_post_kill_requires_killed_generation_and_released_slot(self):
        for kind in ('exit', 'status', 'generation', 'retained-slot', 'reuse', 'essential'):
            g = Guest()
            def change(guest, command):
                if command != 'kill 779': return
                c = guest.c
                if kind == 'exit': c['snapshots'][14]['state'] = 3
                if kind == 'status': c['snapshots'][14]['status'] = 1
                if kind == 'generation': c['snapshots'][14]['generation'] += 1
                if kind == 'retained-slot': c['configurations'][10] = 14
                if kind == 'reuse': c['incarnations'][10] += 1
                if kind == 'essential': c['snapshots'][0]['generation'] += 1
            g.on_command = change
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runner.close_gui(g)
            self.assertEqual(['ps', 'kill 779'], g.commands)

    def test_token_race_is_a_real_kill_error_and_never_retargets(self):
        g = Guest()
        def replace(guest, command):
            if command != 'kill 779': return
            guest.c['incarnations'][10] += 1
            guest.c['snapshots'][14].update(process=(guest.c['incarnations'][10] << 8) | 11, generation=12)
        g.before_command = replace
        with self.assertRaisesRegex(ValueError, 'fresh UART command failed'):
            runner.close_gui(g)
        self.assertEqual(['ps', 'kill 779'], g.commands)
        self.assertEqual(12, g.c['snapshots'][14]['generation'])

    def test_restart_between_clients_is_not_a_successful_close(self):
        g = Guest()
        def restart(guest, command):
            if command != 'kill 1289': return
            c = guest.c
            c['incarnations'][10] += 1
            c['configurations'][10] = 14
            c['slots'][14] = 10
            c['snapshots'][14].update(process=(c['incarnations'][10] << 8) | 11, state=2, generation=12)
        g.on_command = restart
        with self.assertRaisesRegex(ValueError, 'generation changed'):
            runner.close_gui(g)
        self.assertEqual(['ps', 'kill 779', 'kill 1289'], g.commands)

    def test_shell_failure_propagates_without_fallback_or_more_kills(self):
        for error in (ValueError('fresh UART command failed'), TimeoutError('UART timeout')):
            g = Guest()
            actual = g.shell
            def fail(command, **kwargs):
                if command.startswith('kill '): raise error
                return actual(command, **kwargs)
            with mock.patch.object(g, 'shell', side_effect=fail):
                with self.subTest(error=error), self.assertRaises(type(error)):
                    runner.close_gui(g)
            self.assertEqual(['ps'], g.commands)
            self.assertFalse(g.evidence['gui_controls'][0]['completed'])


class HistoricalTests(unittest.TestCase):
    def test_historical_observations_resume_before_decode_and_keep_fresh_epochs(self):
        g = HistoricalGuest()
        initial = copy.deepcopy(g.c)
        with mock.patch('subprocess.Popen', side_effect=AssertionError('host control started a VM')):
            report = runner.close_gui(g)
        self.assertTrue(report['completed'])
        self.assertFalse(g.stopped)
        self.assertEqual(['ps'] + ['kill ' + str(initial['snapshots'][cfg]['process'])
                                  for cfg in runner.GUI_CONFIGS], g.commands)
        history = g.evidence['gui_catalog_captures']
        self.assertEqual(11, len(history))
        self.assertEqual(sorted({r['epoch'] for r in history}), [r['epoch'] for r in history])
        for record in history:
            epoch = record['epoch']
            self.assertTrue(record['historical'])
            self.assertEqual(epoch, record['boot_info_ref']['epoch'])
            self.assertEqual([0, 1, 2, 3], [r['cpu_index'] for r in record['registers']])
            self.assertTrue(all(r['epoch'] == epoch for r in record['catalog_refs']))
            capture, resume, decode = [g.events.index((name, epoch)) for name in ('capture', 'resume', 'catalog')]
            self.assertLess(capture, resume)
            self.assertLess(resume, decode)
        self.assertEqual(history[-1], report['final_catalog']['_historical_capture'])
        self.assertGreaterEqual(history[-1]['serial_offset'], g.evidence['gui_last_fresh_command_end'])

    def test_historical_source_or_uart_boundary_replay_cannot_select_a_kill(self):
        for kind in ('old-epoch', 'boot-epoch', 'register-epoch', 'register-cpu', 'derived-epoch',
                     'reused-epoch', 'before-fresh-ps'):
            g = HistoricalGuest()
            def change(owner, image):
                if kind == 'old-epoch': image.epoch -= 1
                elif kind == 'boot-epoch': image.boot_info_ref['epoch'] += 1
                elif kind == 'register-epoch': image._registers[0]['epoch'] += 1
                elif kind == 'register-cpu': image._registers[1]['cpu_index'] = 0
                elif kind == 'derived-epoch': image.ref_epoch += 1
                elif kind == 'reused-epoch' and owner.reads > 1:
                    image.epoch = owner._epoch = owner.evidence['gui_catalog_captures'][-1]['epoch']
                elif kind == 'before-fresh-ps' and owner.commands:
                    image.serial_offset = 0
            g.image_change = change
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runner.close_gui(g)
            self.assertEqual(['ps'] if kind in ('reused-epoch', 'before-fresh-ps') else [], g.commands)
            self.assertFalse(g.evidence['gui_controls'][0]['completed'])

    def test_historical_mode_preserves_raw_uart_and_replacement_identity_checks(self):
        for kind in ('bad-ps', 'changed-generation', 'token-race'):
            g = HistoricalGuest()
            if kind == 'bad-ps':
                g.body_change = lambda command, body: body + b'junk\r\n' if command == 'ps' else body
            elif kind == 'changed-generation':
                def changed(owner, command):
                    if command == 'ps': owner.c['snapshots'][14]['generation'] += 1
                g.on_command = changed
            else:
                def replace(owner, command):
                    if command == 'kill 779':
                        owner.c['incarnations'][10] += 1
                        owner.c['snapshots'][14].update(process=(owner.c['incarnations'][10] << 8) | 11,
                                                        generation=12)
                g.before_command = replace
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                runner.close_gui(g)
            self.assertEqual(['ps', 'kill 779'] if kind == 'token-race' else ['ps'], g.commands)

    def test_failed_or_unconfirmed_resume_never_enters_historical_decode(self):
        for confirmed in (True, False):
            g = HistoricalGuest()
            error = OSError('synthetic actual cont failed')
            g.resume_error = error if confirmed else None
            g.confirm_running = confirmed
            with self.subTest(confirmed=confirmed), self.assertRaises(OSError if confirmed else ValueError) as caught:
                runner.close_gui(g)
            if confirmed: self.assertIs(error, caught.exception)
            self.assertFalse(any(kind == 'catalog' for kind, _ in g.events))
            self.assertEqual([], g.commands)
            self.assertEqual([], g.evidence['gui_catalog_captures'])


if __name__ == '__main__':
    unittest.main()
