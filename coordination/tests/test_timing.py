"""Lifecycle history and duration checks; isolated temporary coordination store."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination.store import Store
from dongos_coordination.timing import summarize


def at(minutes):
    return f'2026-10-19T00:{minutes:02d}:00+00:00'


def event(kind, minute, status=None):
    return dict(kind=kind, at=at(minute), data={'status': status})


class TimingTests(unittest.TestCase):
    def test_multiple_rounds_pause_wait_and_failed_verification(self):
        events = [event('created', 0), event('claim', 2), event('pause', 5),
                  event('resume', 8), event('submit', 12),
                  event('verified', 14, 'rework'), event('claim', 17),
                  event('submit', 22), event('verified', 24, 'submitted')]
        result = summarize({'status': 'submitted'}, events, at(25))
        first, repair = result['rounds']
        self.assertEqual(first['active_seconds'], 7 * 60)
        self.assertEqual(first['paused_seconds'], 3 * 60)
        self.assertEqual(first['waiting_seconds'], 2 * 60)
        self.assertEqual(repair['kind'], 'rework')
        self.assertEqual(repair['waiting_seconds'], 3 * 60)
        self.assertEqual(result['rework_active_seconds'], 5 * 60)
        self.assertEqual(result['total_active_seconds'], 12 * 60)
        self.assertEqual(result['last_verified_at'], at(24))

    def test_ongoing_pause_and_released_repair_do_not_count_wait(self):
        events = [event('rework', 1, 'rework'), event('claim', 2),
                  event('release', 4), event('claim', 9), event('pause', 10)]
        result = summarize({'status': 'paused'}, events, at(15))
        self.assertEqual([r['kind'] for r in result['rounds']], ['rework', 'rework'])
        self.assertEqual(result['total_active_seconds'], 3 * 60)
        self.assertEqual(result['rounds'][1]['paused_seconds'], 5 * 60)
        self.assertTrue(result['rounds'][1]['ongoing'])

    def test_imported_history_is_unknown_not_import_time(self):
        result = summarize({'status': 'integrated', 'created_at': at(0)},
                           [event('imported', 0)], at(10))
        self.assertIsNone(result['published_at'])
        self.assertIsNone(result['total_active_seconds'])
        self.assertTrue(result['history_incomplete'])

    def test_store_records_real_transitions_and_keeps_full_history_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'source', local=Path(directory) / 'local')
            with patch('dongos_coordination.store.now', return_value=at(0)):
                task = store.create(dict(id='CR1', owner='cursor', title='timing',
                    write_paths=['cursor-works/src/example.dg'], checks=[]))
            with patch('dongos_coordination.store.now', return_value=at(2)):
                task = store.change(task['id'], task['rev'], 'claim')
            delivery = store.path(task['delivery'])
            delivery.parent.mkdir(parents=True, exist_ok=True)
            delivery.write_text('actual delivery', encoding='utf-8')
            with patch('dongos_coordination.store.now', return_value=at(7)):
                task = store.change(task['id'], task['rev'], 'submit')
            with store.transaction() as c:
                for _ in range(65):
                    store.event(c, task['id'], 'document_changed', {})
            before = store.get(task['id'])
            result = store.timing(before)
            self.assertEqual(result['published_at'], at(0))
            self.assertEqual(result['last_submitted_at'], at(7))
            self.assertEqual(result['total_active_seconds'], 5 * 60)
            self.assertEqual(len(result['timeline']), 68)
            self.assertEqual(store.get(task['id']), before)
            self.assertNotIn('timing', before)

    def test_verification_start_and_end_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'source', local=Path(directory) / 'local')
            task = store.create(dict(id='CR1', owner='cursor', title='timing',
                write_paths=['cursor-works/src/example.dg'], checks=['module:tests.test_example']))
            delivery = store.path(task['delivery'])
            delivery.parent.mkdir(parents=True, exist_ok=True)
            delivery.write_text('actual delivery', encoding='utf-8')
            task = store.change(task['id'], task['rev'], 'submit')
            with patch('dongos_coordination.store.now', return_value=at(10)):
                store.queue(task['id'], task['rev'], 'verify')
            with patch('dongos_coordination.store.now', return_value=at(12)):
                job = store.take_job()
            with patch('dongos_coordination.store.now', return_value=at(14)):
                store.finish(job, {'passed': True, 'checks': [{'elapsed_seconds': 45}]})
            result = store.timing(store.get(task['id']))['verifications'][0]
            self.assertEqual(result['queued_at'], at(10))
            self.assertEqual(result['started_at'], at(12))
            self.assertEqual(result['finished_at'], at(14))
            self.assertEqual(result['elapsed_seconds'], 120)
            self.assertEqual(result['check_seconds'], 45)


if __name__ == '__main__':
    unittest.main()
