"""Same-number history repair keeps raw evidence and never changes acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination.identity import contract_identity, event_identity
from dongos_coordination.projects import Registry
from dongos_coordination.store import Conflict, digest


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        (base / 'source').mkdir()
        registry = Registry(base / 'control')
        registry.add('alpha', 'Test', str(base / 'source'))
        self.store = registry.store('alpha')
        with patch('dongos_coordination.store.now', return_value='2026-10-20T00:00:00+00:00'):
            task = self.store.create(dict(id='T1', owner='codex', title='Reader',
                                         write_paths=['reader.dg'], checks=[]))
        with patch('dongos_coordination.store.now', return_value='2026-10-20T00:01:00+00:00'):
            task = self.store.change(task['id'], task['rev'], 'claim')
        delivery = self.store.path(task['delivery'])
        delivery.parent.mkdir(parents=True, exist_ok=True)
        delivery.write_text('Reader delivery', encoding='utf-8')
        with patch('dongos_coordination.store.now', return_value='2026-10-20T00:02:00+00:00'):
            task = self.store.change(task['id'], task['rev'], 'submit')
        task = self.store.change(task['id'], task['rev'], 'pause', 'fixture pause')
        with self.store.transaction() as connection:
            for minute, kind in ((0, 'created'), (1, 'claim'), (2, 'submit')):
                with patch('dongos_coordination.store.now', return_value=f'2026-10-20T10:0{minute}:00+00:00'):
                    self.store.event(connection, task['id'], kind, {'identity': 'other task'})
        self.task = self.store.get(task['id'])
        self.foreign = [e for e in self.events() if e['data'].get('identity') == 'other task']
        self.archive = self.store.works_root / 'reviews/foreign.md'
        self.archive.parent.mkdir()
        self.archive.write_text('Original other contract', encoding='utf-8')
        self.plan = dict(version=1, project='alpha', task_id=task['id'], rev=task['rev'],
                         identity_label='Other task, archived', contract_sha256=contract_identity(task),
                         document=dict(path=task['document'], sha256=digest(self.store.path(task['document']))),
                         evidence=[dict(path=task['document'], sha256=digest(self.store.path(task['document']))),
                                   dict(path='reviews/foreign.md', sha256=digest(self.archive))],
                         exclude_events=[event_identity(e) for e in self.foreign])
        self.manifest = self.store.works_root / 'reviews/identity.json'

    def events(self):
        with self.store.connect() as connection:
            return [dict(row) | {'data': json.loads(row['data'])} for row in connection.execute('SELECT * FROM events ORDER BY seq')]

    def options(self, plan=None):
        self.manifest.write_text(json.dumps(plan or self.plan, ensure_ascii=False), encoding='utf-8')
        return dict(project='alpha', manifest='reviews/identity.json', sha256=digest(self.manifest))

    def apply(self, plan=None, options=None, rev=None):
        return self.store.change(self.task['id'], self.task['rev'] if rev is None else rev,
                                 'resolve_identity', 'Original evidence distinguishes two contracts.',
                                 options or self.options(plan))

    def test_separation_preserves_raw_events_state_and_original_delivery(self):
        before = self.events()
        delivery = self.store.path(self.task['delivery']).read_bytes()
        updated = self.apply()
        self.assertEqual(updated['status'], self.task['status'])
        self.assertEqual(updated.get('verification'), self.task.get('verification'))
        self.assertEqual(self.events()[:-1], before)
        self.assertEqual(self.store.path(self.task['delivery']).read_bytes(), delivery)
        result = self.store.timing(updated)
        self.assertEqual(len(result['rounds']), 1)
        self.assertEqual(result['published_at'], '2026-10-20T00:00:00+00:00')
        self.assertEqual(result['total_active_seconds'], 60)
        self.assertEqual(len(result['identity_resolution']['separated_events']), 3)
        reloaded = Registry(self.store.works_root.parent).store('alpha')
        self.assertEqual(len(reloaded.timing(reloaded.get(updated['id']))['rounds']), 1)

    def test_stale_revision_or_changed_contract_refuses_without_writing(self):
        before = self.events()
        with self.assertRaises(Conflict):
            self.apply(rev=self.task['rev'] - 1)
        plan = copy.deepcopy(self.plan)
        plan['contract_sha256'] = '0' * 64
        with self.assertRaises(Conflict):
            self.apply(plan)
        self.assertEqual(self.events(), before)

    def test_unknown_duplicate_or_all_events_cannot_be_excluded(self):
        before = self.events()
        for values in (['0' * 64], self.plan['exclude_events'] * 2,
                       [event_identity(e) for e in before]):
            plan = copy.deepcopy(self.plan)
            plan['exclude_events'] = values
            with self.assertRaises((ValueError, Conflict)):
                self.apply(plan)
        self.assertEqual(self.events(), before)

    def test_changed_manifest_document_and_original_evidence_are_rejected(self):
        options = self.options()
        self.manifest.write_text('{}', encoding='utf-8')
        with self.assertRaises(Conflict):
            self.apply(options=options)
        self.archive.write_text('tampered original', encoding='utf-8')
        with self.assertRaises(Conflict):
            self.apply()
        self.archive.write_text('Original other contract', encoding='utf-8')
        self.store.path(self.task['document']).write_text('wrong contract', encoding='utf-8')
        with self.assertRaises(Conflict):
            self.apply()
        self.assertNotIn('identity_resolution', self.store.get(self.task['id']))

    def test_cross_project_and_escaping_evidence_paths_are_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan['project'] = 'beta'
        with self.assertRaises(Conflict):
            self.apply(plan)
        plan = copy.deepcopy(self.plan)
        plan['evidence'][1]['path'] = '../outside.md'
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertNotIn('identity_resolution', self.store.get(self.task['id']))

    def test_tasks_without_resolution_keep_the_original_timeline(self):
        result = self.store.timing(self.task)
        self.assertEqual(len(result['rounds']), 2)
        self.assertNotIn('identity_resolution', result)


if __name__ == '__main__':
    unittest.main()
