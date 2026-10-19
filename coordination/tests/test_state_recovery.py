"""Disaster recovery must preserve history and reject concurrent real work."""
import json
import shutil
import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination import migrate
from dongos_coordination.state_recovery import reconcile, restore
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

    def bind_current(self):
        audit = json.loads(self.audit.read_text(encoding='utf-8'))
        with self.store.connect() as c:
            audit['current_tasks'] = [dict(id=row['id'], rev=row['rev'],
                data_sha256=hashlib.sha256(row['data'].encode('utf-8')).hexdigest())
                for row in c.execute('SELECT id,rev,data FROM tasks ORDER BY id')]
        self.audit.write_text(json.dumps(audit), encoding='utf-8')

    def reconcile(self, **kwargs):
        return reconcile(self.store, 'alpha', self.snapshot, self.audit, **kwargs)

    def historical_work(self):
        with self.store.transaction() as c:
            c.execute('INSERT INTO events(at,task_id,kind,data) VALUES(?,?,?,?)',
                ('2026-10-18T00:00:00+00:00', 'claude:C94', 'claim', '{}'))
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', ('original-job', 'claude:C94',
                'verify', 'python', 'completed', '2026-10-18T00:00:00+00:00',
                '2026-10-18T00:01:00+00:00', '{"passed":true}'))

    def test_reconcile_preview_and_success_preserve_history_and_back_up_every_table(self):
        self.historical_work()
        # A later document import is explicitly permitted, but still revision-bound.
        with self.store.transaction() as c:
            task = self.store.get('claude:C94', c)
            task.update(auto_dispatch=True, auto_verify=True)
            self.store.save(c, task, 'document_changed')
            c.execute('INSERT INTO settings VALUES(?,?)', ('automation', 'true'))
        self.bind_current()
        before_tasks = self.store.tasks(include_archived=True)
        with self.store.connect() as c:
            before_events = [tuple(row) for row in c.execute('SELECT * FROM events ORDER BY seq')]
            before_jobs = [tuple(row) for row in c.execute('SELECT * FROM jobs ORDER BY id')]
        preview = self.reconcile()
        self.assertFalse(preview['applied'])
        self.assertEqual(preview['preserved_jobs'], 1)
        self.assertEqual(self.store.tasks(include_archived=True), before_tasks)
        self.assertFalse((self.works / 'index.json').exists())
        result = self.reconcile(apply=True)
        self.assertTrue(result['applied'])
        with self.store.connect() as c:
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM events WHERE seq<=? ORDER BY seq',
                (before_events[-1][0],))], before_events)
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM jobs ORDER BY id')], before_jobs)
            self.assertEqual(c.execute("SELECT count(*) FROM events WHERE kind='state_reconciled'").fetchone()[0], 5)
        with closing(sqlite3.connect(Path(result['backup']) / 'tasks.sqlite3')) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0], len(before_events))
            self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT value FROM settings WHERE key='automation'").fetchone()[0], 'true')
        task = self.store.get('claude:C91')
        self.assertEqual(task['rev'], 9)
        self.assertEqual(task['status'], 'integrated')
        self.assertFalse(task['state_reconciliation']['verification_reexecuted'])
        self.assertEqual(task['verification'], json.loads(self.snapshot.read_text())['tasks'][1]['verification'])
        self.assertFalse(self.store.setting('automation'))
        self.assertFalse(self.store.get('claude:C94')['auto_verify'])
        self.assertTrue(self.store.get('claude:C92')['archived'])
        self.assertTrue((self.works / 'index.json').exists())
        with self.assertRaises(Conflict):
            self.reconcile(apply=True)

    def test_reconcile_rejects_new_real_operation_and_active_job(self):
        self.bind_current()
        self.store.change('claude:C94', 1, 'claim')
        self.bind_current()
        with self.assertRaisesRegex(Conflict, '真实操作'):
            self.reconcile(apply=True)
        self.assertEqual(self.store.get('claude:C94')['status'], 'in_progress')

    def test_reconcile_rejects_active_historical_job(self):
        self.historical_work()
        with self.store.transaction() as c:
            c.execute("UPDATE jobs SET status='running'")
        self.bind_current()
        with self.assertRaisesRegex(Conflict, '活动'):
            self.reconcile()

    def test_reconcile_binds_raw_data_even_if_revision_is_unchanged(self):
        self.bind_current()
        with self.store.transaction() as c:
            row = c.execute("SELECT data FROM tasks WHERE id='claude:C94'").fetchone()
            c.execute("UPDATE tasks SET data=? WHERE id='claude:C94'", (row['data'] + ' ',))
        with self.assertRaisesRegex(Conflict, 'rev/data_sha256'):
            self.reconcile(apply=True)

    def test_reconcile_rechecks_files_under_write_lock(self):
        self.bind_current()
        before = self.store.tasks(include_archived=True)
        original_backup = self.store.backup
        def raced_backup():
            result = original_backup()
            self.store.path('claude-works/src/C91.txt').write_text('concurrent edit', encoding='utf-8')
            return result
        with patch.object(self.store, 'backup', side_effect=raced_backup):
            with self.assertRaisesRegex(Conflict, '恢复实物'):
                self.reconcile(apply=True)
        self.assertEqual(self.store.tasks(include_archived=True), before)

    def test_reconcile_rolls_back_tasks_and_events_if_file_changes_during_saves(self):
        self.historical_work()
        self.bind_current()
        before_tasks = self.store.tasks(include_archived=True)
        with self.store.connect() as c:
            before_events = [tuple(row) for row in c.execute('SELECT * FROM events ORDER BY seq')]
            before_jobs = [tuple(row) for row in c.execute('SELECT * FROM jobs ORDER BY id')]
        original_save = self.store.save
        saved = []
        def raced_save(c, task, kind):
            original_save(c, task, kind)
            saved.append(task['id'])
            if len(saved) == 1:
                self.store.path('claude-works/src/C91.txt').write_bytes(b'edit during saves\n')
        with patch.object(self.store, 'save', side_effect=raced_save):
            with self.assertRaisesRegex(Conflict, '恢复实物'):
                self.reconcile(apply=True)
        self.assertEqual(len(saved), 5)
        self.assertEqual(self.store.tasks(include_archived=True), before_tasks)
        with self.store.connect() as c:
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM events ORDER BY seq')], before_events)
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM jobs ORDER BY id')], before_jobs)
            self.assertIsNone(c.execute("SELECT value FROM settings WHERE key='automation'").fetchone())
        backups = list((self.store.local / 'backups').glob('*/tasks.sqlite3'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0], len(before_events))
        self.assertFalse((self.works / 'index.json').exists())

    def test_reconcile_rechecks_events_and_jobs_under_write_lock(self):
        self.bind_current()
        before = self.store.tasks(include_archived=True)
        original_backup = self.store.backup
        def raced_backup():
            result = original_backup()
            with self.store.transaction() as c:
                self.store.event(c, 'claude:C94', 'document_changed', {'concurrent': True})
            return result
        with patch.object(self.store, 'backup', side_effect=raced_backup):
            with self.assertRaisesRegex(Conflict, '已变化'):
                self.reconcile(apply=True)
        self.assertEqual(self.store.tasks(include_archived=True), before)

    def test_reconcile_rejects_missing_current_task_and_ownership_changes(self):
        self.bind_current()
        data = json.loads(self.snapshot.read_text())
        data['tasks'][-1]['write_paths'].append('claude-works/extra.txt')
        self.snapshot.write_text(json.dumps(data), encoding='utf-8')
        audit = json.loads(self.audit.read_text())
        audit['snapshot_sha256'] = digest(self.snapshot)
        self.audit.write_text(json.dumps(audit), encoding='utf-8')
        with self.assertRaisesRegex(Conflict, '路径归属'):
            self.reconcile()
        data['tasks'].pop()
        self.snapshot.write_text(json.dumps(data), encoding='utf-8')
        audit['snapshot_sha256'] = digest(self.snapshot)
        audit['tasks'] = [item for item in audit['tasks'] if item['id'] != 'claude:C94']
        self.audit.write_text(json.dumps(audit), encoding='utf-8')
        with self.assertRaisesRegex(Conflict, '缺少当前任务'):
            self.reconcile()

    def test_reconcile_checks_crlf_historical_hash_without_changing_files(self):
        snapshot = json.loads(self.snapshot.read_text())
        audit = json.loads(self.audit.read_text())
        source = 'claude-works/src/C91.txt'
        self.store.path(source).write_bytes(b'content\n')
        historical = hashlib.sha256(b'content\r\n').hexdigest()
        task = next(task for task in snapshot['tasks'] if task['id'] == 'claude:C91')
        task['verification']['fingerprint'][source] = historical
        item = next(item for item in audit['tasks'] if item['id'] == task['id'])
        item['files'][0].update(sha256=digest(self.store.path(source)),
                              historical_sha256=historical, comparison='crlf')
        self.snapshot.write_text(json.dumps(snapshot), encoding='utf-8')
        audit['snapshot_sha256'] = digest(self.snapshot)
        self.audit.write_text(json.dumps(audit), encoding='utf-8')
        self.bind_current()
        self.assertFalse(self.reconcile()['applied'])
        self.assertEqual(self.store.path(source).read_bytes(), b'content\n')
        item['files'][0]['historical_sha256'] = hashlib.sha256(b'different\r\n').hexdigest()
        self.audit.write_text(json.dumps(audit), encoding='utf-8')
        self.bind_current()
        with self.assertRaisesRegex(Conflict, '历史文件指纹'):
            self.reconcile()

    def test_reconcile_supersession_requires_later_stable_integrated_successor(self):
        snapshot = json.loads(self.snapshot.read_text())
        audit = json.loads(self.audit.read_text())
        source = 'claude-works/src/C91.txt'
        self.store.path(source).write_bytes(b'successor\n')
        successor_hash = digest(self.store.path(source))
        original = next(task for task in snapshot['tasks'] if task['id'] == 'claude:C91')
        successor = next(task for task in snapshot['tasks'] if task['id'] == 'claude:C94')
        original['verification']['finished_at'] = '2026-10-18T01:00:00+00:00'
        successor.update(status='integrated', integration_note='Independent later integration',
            verification=dict(passed=True, source_stable=True,
                finished_at='2026-10-18T02:00:00+00:00', fingerprint={source: successor_hash}))
        original_item = next(item for item in audit['tasks'] if item['id'] == original['id'])
        original_item['files'][0].update(sha256=successor_hash, comparison='superseded',
            superseded_by=successor['id'], successor_sha256=successor_hash, successor_comparison='exact')
        successor_item = next(item for item in audit['tasks'] if item['id'] == successor['id'])
        successor_item.update(status='integrated')
        successor_item['files'].append(dict(path=source, sha256=successor_hash,
            historical_sha256=successor_hash, comparison='raw'))
        self.snapshot.write_text(json.dumps(snapshot), encoding='utf-8')
        audit['snapshot_sha256'] = digest(self.snapshot)
        self.audit.write_text(json.dumps(audit), encoding='utf-8')
        self.bind_current()
        self.assertFalse(self.reconcile()['applied'])
        with self.assertRaisesRegex(ValueError, '后继集成证据'):
            self.recover()
        for field, value in [('source_stable', False), ('passed', False),
                             ('finished_at', '2026-10-18T00:59:59+00:00')]:
            with self.subTest(field=field):
                original_value = successor['verification'][field]
                successor['verification'][field] = value
                self.snapshot.write_text(json.dumps(snapshot), encoding='utf-8')
                audit['snapshot_sha256'] = digest(self.snapshot)
                self.audit.write_text(json.dumps(audit), encoding='utf-8')
                self.bind_current()
                with self.assertRaisesRegex(ValueError, '后继集成证据'):
                    self.reconcile()
                successor['verification'][field] = original_value

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
        shutil.rmtree(self.works / 'state')      # only the legacy index.json snapshot remains (no committed state/ files)
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
