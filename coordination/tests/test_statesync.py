"""The committed task-state snapshot: any machine that pulls the repository and starts the service sees the same task list."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dongos_coordination.store import Store, StateRecoveryRequired


def spec(number, owner='claude', **extra):
    return dict(id=number, owner=owner, title='任务' + number, description='说明' + number,
                write_paths=[owner + '-works/src/' + number.lower() + '.dg'], checks=[], **extra)


class StateSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name)
        self.addCleanup(self.directory.cleanup)
        self.a = self.machine('a')

    def machine(self, name, source=None):
        """One development machine: its own project tree and its own (never committed) .local database."""
        root = self.base / name
        if source is not None:
            shutil.copytree(source, root, ignore=shutil.ignore_patterns('.local'))
        root.mkdir(parents=True, exist_ok=True)
        return root

    def store(self, root):
        return Store(root, root / '.local', root)

    def ledger(self, store):
        return {t['id']: (t['rev'], t['status']) for t in store.tasks(include_archived=True)}

    def event_keys(self, store):
        with store.connect() as c:
            return sorted((r['task_id'], r['at'], r['kind']) for r in c.execute('SELECT * FROM events WHERE task_id IS NOT NULL'))

    def test_snapshot_is_written_stably_and_rebuilds_a_missing_database(self):
        store = self.store(self.a)
        for number in ('C2', 'C1', 'D9'):
            store.create(spec(number, 'deepseek' if number == 'D9' else 'claude'))
        store.change('claude:C1', 1, 'claim')
        files = sorted(p.relative_to(self.a).as_posix() for p in (self.a / 'state').rglob('*') if p.is_file())
        self.assertEqual(files, ['state/.gitattributes', 'state/.gitignore', 'state/README.md', 'state/events/claude/C1.jsonl',
                                 'state/events/claude/C2.jsonl', 'state/events/deepseek/D9.jsonl', 'state/tasks/claude/C1.json',
                                 'state/tasks/claude/C2.json', 'state/tasks/deepseek/D9.json'])
        body = (self.a / 'state/tasks/claude/C1.json').read_bytes()
        self.assertTrue(body.endswith(b'}\n') and b'\r' not in body)
        task = json.loads(body)
        self.assertEqual(list(task), sorted(task), 'keys are sorted so diffs stay small')
        self.assertEqual((task['rev'], task['status']), (2, 'in_progress'))
        lines = (self.a / 'state/events/claude/C1.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual([json.loads(x)['kind'] for x in lines], ['created', 'claim'])
        before = self.ledger(store), self.event_keys(store)
        stamp = {p: p.stat().st_mtime_ns for p in (self.a / 'state').rglob('*') if p.is_file()}
        self.assertEqual(store.state.sync()['written'], [], 'a second sync must not touch any file')
        self.assertEqual(stamp, {p: p.stat().st_mtime_ns for p in (self.a / 'state').rglob('*') if p.is_file()})
        # A brand-new machine only has the committed files (no .local): it must load them, not re-import task books.
        fresh = self.machine('fresh', self.a)
        self.assertFalse((fresh / '.local').exists())
        loaded = self.store(fresh)
        self.assertEqual((self.ledger(loaded), self.event_keys(loaded)), before)
        # ...and a deleted database on the original machine is rebuilt from state/ as well.
        store.db.unlink()
        rebuilt = self.store(self.a)
        self.assertEqual((self.ledger(rebuilt), self.event_keys(rebuilt)), before)

    def test_two_machines_converge_after_a_git_style_merge(self):
        store_a = self.store(self.a)
        store_a.create(spec('C1'))
        store_a.create(spec('C2'))
        b = self.machine('b', self.a)
        store_b = self.store(b)
        store_a.change('claude:C1', 1, 'claim')                       # machine A advances C1
        store_b.create(spec('C3'))                                    # machine B adds C3 and works on C2
        store_b.change('claude:C2', 1, 'claim')
        # git merge: different tasks never conflict; event logs merge by union.
        for source, target in ((self.a, b), (b, self.a)):
            for path in (source / 'state').rglob('*'):
                if not path.is_file():
                    continue
                destination = target / path.relative_to(source)
                if not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
                elif path.suffix == '.jsonl':
                    merged = sorted(set(path.read_text(encoding='utf-8').splitlines()) |
                                    set(destination.read_text(encoding='utf-8').splitlines()))
                    destination.write_text('\n'.join(merged) + '\n', encoding='utf-8', newline='\n')
                elif path.suffix == '.json' and json.loads(path.read_text(encoding='utf-8'))['rev'] > \
                        json.loads(destination.read_text(encoding='utf-8'))['rev']:
                    shutil.copyfile(path, destination)
        # Restart both services (they re-open the stores) and compare.
        restarted_a, restarted_b = self.store(self.a), self.store(b)
        self.assertEqual(self.ledger(restarted_a), self.ledger(restarted_b))
        self.assertEqual(self.ledger(restarted_a), {'claude:C1': (2, 'in_progress'), 'claude:C2': (2, 'in_progress'),
                                                    'claude:C3': (1, 'todo')})
        self.assertEqual(self.event_keys(restarted_a), self.event_keys(restarted_b))

    def test_files_that_arrive_while_serving_are_loaded_and_never_overwritten(self):
        store = self.store(self.a)
        store.create(spec('C1'))
        store.create(spec('C2'))
        path = self.a / 'state/tasks/claude/C1.json'
        newer = json.loads(path.read_text(encoding='utf-8'))
        newer.update(rev=7, status='accepted', review_note='另一台机器验收', updated_at='2099-01-01T00:00:00+00:00')
        path.write_text(json.dumps(newer, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')
        # An unrelated change on this machine writes back its own tasks but must not roll C1's file back.
        store.change('claude:C2', 1, 'claim')
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['rev'], 7)
        self.assertEqual(store.get('claude:C1')['status'], 'accepted')
        self.assertEqual(store.get('claude:C1')['rev'], 7)
        self.assertEqual(store.get('claude:C2')['status'], 'in_progress')

    def test_equal_revision_divergence_prefers_the_later_update_and_is_reported(self):
        store = self.store(self.a)
        store.create(spec('C1'))
        path = self.a / 'state/tasks/claude/C1.json'
        other = json.loads(path.read_text(encoding='utf-8'))
        other.update(status='paused', updated_at='2099-01-01T00:00:00+00:00')
        path.write_text(json.dumps(other, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')
        report = store.state.pull(force=True)
        self.assertEqual(report['diverged'], ['claude:C1'])
        self.assertEqual(store.get('claude:C1')['status'], 'paused')

    def test_conflict_markers_and_invalid_files_are_skipped_reported_and_kept(self):
        store = self.store(self.a)
        store.create(spec('C1'))
        store.create(spec('C2'))
        c1 = self.a / 'state/tasks/claude/C1.json'
        good = c1.read_text(encoding='utf-8')
        c1.write_text('<<<<<<< HEAD\n' + good + '=======\n' + good + '>>>>>>> other\n', encoding='utf-8', newline='\n')
        c2 = self.a / 'state/tasks/claude/C2.json'
        wrong = json.loads(c2.read_text(encoding='utf-8'))
        wrong['id'] = 'claude:C9'
        c2.write_text(json.dumps(wrong, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')
        keep = c1.read_bytes()
        restarted = self.store(self.a)                                   # starting is never blocked by a bad file
        issues = restarted.validate()
        messages = {i['task']: i['message'] for i in issues}
        self.assertIn('state/tasks/claude/C1.json', messages)
        self.assertIn('合并冲突', messages['state/tasks/claude/C1.json'])
        self.assertIn('state/tasks/claude/C2.json', messages)
        self.assertEqual({t['id'] for t in restarted.tasks()}, {'claude:C1', 'claude:C2'})   # the database copy is kept
        restarted.change('claude:C1', 1, 'claim')                        # a later change must not overwrite the conflicted file
        self.assertEqual(c1.read_bytes(), keep)
        c1.write_text(good, encoding='utf-8', newline='\n')              # the human resolves it; the problem disappears
        restarted.state.pull(force=True)
        self.assertNotIn('state/tasks/claude/C1.json', {i['task'] for i in restarted.validate()})

    def test_legacy_index_json_alone_still_blocks_a_silent_reimport(self):
        store = self.store(self.a)
        store.create(spec('C1'))
        store.export()
        store.db.unlink()
        shutil.rmtree(self.a / 'state')
        with self.assertRaises(StateRecoveryRequired):
            self.store(self.a)
        # an unreadable (merge-conflicted) index.json must not crash a start that has state/
        self.assertFalse((self.a / 'state').exists())

    def test_unreadable_index_json_does_not_stop_a_start_that_has_state(self):
        store = self.store(self.a)
        store.create(spec('C1'))
        (self.a / 'index.json').write_text('<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> other\n', encoding='utf-8')
        store.db.unlink()
        self.assertEqual(self.ledger(self.store(self.a)), {'claude:C1': (1, 'todo')})


if __name__ == '__main__':
    unittest.main()
