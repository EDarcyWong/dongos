"""Disaster recovery must preserve history and reject concurrent real work."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination import migrate
from dongos_coordination.state_recovery import restore
from dongos_coordination.store import Conflict, Store, StateRecoveryRequired, digest


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.works = self.base / 'control' / 'alpha_works'
        self.store = Store(self.root, self.works / '.local', self.works)
        records = []
        evidence = []
        for number, state in [('C90', 'accepted'), ('C91', 'integrated'),
                              ('C92', 'paused'), ('C93', 'rework'), ('C94', 'todo')]:
            source = f'claude-works/src/{number}.txt'
            book = f'claude-works/tasks/{number}-board.md'
            for path, text in [(source, 'content\n'), (book, f'# {number} — Example\n状态：待领取。')]:
                f = self.store.path(path)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding='utf-8')
            task = self.store.create(dict(id=number, owner='claude', title=number,
                write_paths=[source], document=book, legacy_hash=digest(self.store.path(book))), imported=True)
            task.update(status=state, rev=8, review_note='Original independent review')
            if state == 'integrated':
                task.update(verification=dict(passed=True, fingerprint={source: digest(self.store.path(source))}),
                            integration_note='Original integration record')
            if state == 'paused':
                task.update(archived=True, archive_note='Transferred and completed')
            records.append(task)
            file_record = dict(path=source, sha256=digest(self.store.path(source)))
            if state == 'integrated':
                file_record.update(historical_sha256=file_record['sha256'], comparison='raw')
            evidence.append(dict(id=task['id'], status=state, rev=8,
                documents=[dict(path=book, sha256=digest(self.store.path(book)))], files=[file_record]))
        self.snapshot = self.base / 'snapshot.json'
        self.snapshot.write_text(json.dumps(dict(schema_version=1, generated_at='2026-10-18T16:06:35+00:00',
            tasks=[t for t in records if not t.get('archived')],
            archived_tasks=[t for t in records if t.get('archived')])), encoding='utf-8')
        self.audit = self.base / 'audit.json'
        self.audit.write_text(json.dumps(dict(project='alpha', snapshot_sha256=digest(self.snapshot), tasks=evidence)), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def recover(self, **kwargs):
        return restore(self.store, 'alpha', self.snapshot, self.audit, **kwargs)

    def test_dry_run_does_not_change_tasks_or_export(self):
        before = self.store.tasks(include_archived=True)
        result = self.recover()
        self.assertFalse(result['applied'])
        self.assertEqual(result['archived'], 1)
        self.assertEqual(self.store.tasks(include_archived=True), before)
        self.assertFalse((self.works / 'index.json').exists())

    def test_restore_history_archive_revisions_backup_and_sync(self):
        result = self.recover(apply=True)
        self.assertTrue(result['applied'])
        self.assertEqual(self.store.get('claude:C90')['status'], 'accepted')
        self.assertEqual(self.store.get('claude:C91')['status'], 'integrated')
        self.assertEqual(self.store.get('claude:C91')['verification']['passed'], True)
        self.assertTrue(self.store.get('claude:C92')['archived'])
        self.assertEqual(len(self.store.tasks()), 4)
        self.assertEqual(self.store.get('claude:C93')['rev'], 9)
        self.assertFalse(self.store.get('claude:C93')['auto_dispatch'])
        with self.assertRaises(Conflict):
            self.store.change('claude:C94', 1, 'claim')
        with closing(sqlite3.connect(Path(result['backup']) / 'tasks.sqlite3')) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0], 5)
            self.assertEqual(c.execute("SELECT count(*) FROM events WHERE kind='state_restored'").fetchone()[0], 0)
        migrate.synchronize(self.store)
        self.assertEqual(self.store.get('claude:C90')['status'], 'accepted')
        self.assertEqual(self.store.get('claude:C91')['status'], 'integrated')
        self.assertTrue(self.store.get('claude:C92')['archived'])
        with self.assertRaises(Conflict):
            self.recover(apply=True)

    def test_rejects_project_mismatch_and_snapshot_tampering(self):
        with self.assertRaises(ValueError):
            restore(self.store, 'beta', self.snapshot, self.audit)
        self.snapshot.write_text(self.snapshot.read_text() + ' ', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.recover()

    def test_rejects_changed_evidence_and_files_without_partial_writes(self):
        before = self.store.tasks(include_archived=True)
        self.store.path('claude-works/src/C91.txt').write_text('changed', encoding='utf-8')
        with self.assertRaises(Conflict):
            self.recover(apply=True)
        self.assertEqual(self.store.tasks(include_archived=True), before)

    def test_rejects_real_work_after_import(self):
        self.store.change('claude:C94', 1, 'claim')
        with self.assertRaises(Conflict):
            self.recover(apply=True)
        self.assertEqual(self.store.get('claude:C94')['status'], 'in_progress')

    def test_missing_and_empty_database_fail_closed_without_overwriting_snapshot(self):
        self.recover(apply=True)
        index = self.works / 'index.json'
        original = index.read_bytes()
        self.store.db.unlink()
        with self.assertRaises(StateRecoveryRequired):
            Store(self.root, self.works / '.local', self.works)
        self.assertFalse(self.store.db.exists())
        self.assertEqual(index.read_bytes(), original)
        empty = Store(self.root, self.works / '.local', self.works, allow_state_recovery=True)
        with self.assertRaises(StateRecoveryRequired):
            Store(self.root, self.works / '.local', self.works)
        self.assertEqual(empty.tasks(), [])
        self.assertEqual(index.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
