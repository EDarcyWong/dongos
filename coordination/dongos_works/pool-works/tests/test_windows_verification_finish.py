"""WINVERIFY1: a verification that really finished must be recorded, and only a
proven stop may count as stopped.

The official coordinator stays read-only. Each run copies the official
``dongos_coordination`` package into a temporary directory under a different
package name, overlays the candidate files from ``pool-works/win-verify`` and
imports that copy, so the official package, database and service are never
touched. Every scenario uses real child processes; nothing is mocked except
the explicit "job object unavailable" fallback.
"""
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

WORKS = Path(__file__).resolve().parents[2]
COORDINATION = next(root for root in WORKS.parents
                    if (root / 'coordinate.py').is_file() and (root / 'dongos_coordination').is_dir())
OFFICIAL = COORDINATION / 'dongos_coordination'
OFFICIAL_HASHES = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in OFFICIAL.rglob('*.py') if '__pycache__' not in p.parts}
CANDIDATE = WORKS / 'pool-works/win-verify/dongos_coordination'
PACKAGE = 'winverify_candidate'
WINDOWS = os.name == 'nt'


def load_candidate():
    root = Path(tempfile.mkdtemp(prefix='winverify-'))
    target = root / PACKAGE
    shutil.copytree(OFFICIAL, target, ignore=shutil.ignore_patterns('__pycache__', 'web', 'docs'))
    overlaid = []
    for name in ('runner.py', 'store.py'):
        if (CANDIDATE / name).is_file():
            shutil.copyfile(CANDIDATE / name, target / name)
            overlaid.append(name)
    sys.path.insert(0, str(root))
    runner = importlib.import_module(PACKAGE + '.runner')
    store = importlib.import_module(PACKAGE + '.store')
    return root, overlaid, runner, store


def alive(pid):
    """True while the process exists (independent of the code under test)."""
    if WINDOWS:
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)   # SYNCHRONIZE|QUERY_LIMITED
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 0x102   # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        state = Path(f'/proc/{pid}/stat').read_text()
        return state[state.rfind(')') + 2] not in 'ZX'
    except OSError:
        return True


def wait_dead(pid, seconds=10):
    deadline = time.monotonic() + seconds
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not alive(pid)


def setUpModule():
    global TEMP_ROOT, OVERLAID, runner_module, store_module
    TEMP_ROOT, OVERLAID, runner_module, store_module = load_candidate()


def tearDownModule():
    assert OFFICIAL_HASHES == {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in OFFICIAL.rglob('*.py') if '__pycache__' not in p.parts}, 'read-only coordinator dependencies changed'
    sys.path.remove(str(TEMP_ROOT))
    for name in [m for m in sys.modules if m == PACKAGE or m.startswith(PACKAGE + '.')]:
        del sys.modules[name]
    shutil.rmtree(TEMP_ROOT, ignore_errors=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.store = store_module.Store(self.root)
        self.source = self.root / 'cursor-works/src/widget.py'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('original', encoding='utf-8')
        (self.root / 'tests').mkdir()
        (self.root / 'tests/__init__.py').write_text('', encoding='utf-8')
        self.pidfile = Path(self.temp.name) / 'child.pid'
        self.children = []

    def tearDown(self):
        for pid in self.children:
            if alive(pid):
                if WINDOWS:
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)
                else:
                    os.kill(pid, 9)
        self.temp.cleanup()

    def check(self, body):
        """The verification check: one unittest module with the given body."""
        text = 'import os, subprocess, sys, time, unittest\nclass T(unittest.TestCase):\n' + body
        (self.root / 'tests/test_sample.py').write_text(text, encoding='utf-8')

    def child_pid(self):
        pid = int(self.pidfile.read_text())
        self.children.append(pid)
        return pid

    def verify_job(self):
        task = self.store.create(dict(id='CR9', owner='cursor', title='Windows finish', description='bounded',
                                      write_paths=['cursor-works/src/widget.py'], checks=['module:tests.test_sample']))
        (self.root / task['delivery']).parent.mkdir(parents=True, exist_ok=True)
        (self.root / task['delivery']).write_text('actual delivery', encoding='utf-8')
        task = self.store.change(task['id'], task['rev'], 'submit')
        self.store.queue(task['id'], task['rev'], 'verify', 'codex')
        return self.store.take_job()

    def runner(self, timeout=60):
        return runner_module.Runner(self.store, {}, timeout=timeout, parallel=1)

    def job_row(self, job_id):
        return next(j for j in self.store.jobs() if j['id'] == job_id)

    def spawn_child(self, seconds):
        """unittest body line that starts a detached-from-wait child and records its pid."""
        return (f"   c=subprocess.Popen([sys.executable,'-c','import time;time.sleep({seconds})'])\n"
                f"   open(r'{self.pidfile}','w').write(str(c.pid))\n")


class FinishTests(Fixture):
    def test_candidate_overlay_is_complete_and_official_untouched(self):
        self.assertIn('runner.py', OVERLAID)
        # The candidate may already be integrated in OFFICIAL. Verify the
        # isolated module is the requested candidate, independent of that state.
        self.assertEqual(Path(runner_module.__file__).read_bytes(), (CANDIDATE / 'runner.py').read_bytes())
        self.assertEqual(runner_module.__name__, PACKAGE + '.runner')
        self.assertTrue(str(Path(runner_module.__file__).resolve()).startswith(str(TEMP_ROOT.resolve())))

    def test_normal_parent_and_child_exit_records_verification(self):
        # Parent unittest process starts a real child that exits before it.
        self.check("  def test_child(self):\n"
                   "   r=subprocess.run([sys.executable,'-c','print(42)'],capture_output=True,text=True)\n"
                   "   self.assertEqual(r.stdout.strip(),'42')\n")
        job = self.verify_job()
        result = self.runner().execute(job)
        self.assertTrue(result['passed'], result)
        self.assertIs(result['process_stopped'], True)
        self.assertIs(result['checks'][0]['process_stopped'], True)
        self.assertTrue(result['execution_exited'])
        self.store.finish(job, result)
        task = self.store.get(job['task_id'])
        self.assertEqual(task['status'], 'submitted')
        self.assertTrue(task['verification']['passed'])
        self.assertEqual(task['verification']['job'], job['id'])
        self.assertNotIn('pause_requested_at', task)
        self.assertNotIn('stop_unconfirmed', task)
        self.assertEqual(self.job_row(job['id'])['status'], 'completed')

    def test_residual_child_is_never_reported_stopped_while_alive(self):
        # The leader exits normally but leaves a running grandchild behind.
        self.check("  def test_leave_child(self):\n" + self.spawn_child(120))
        job = self.verify_job()
        result = self.runner().execute(job)
        pid = self.child_pid()
        check = result['checks'][0]
        # Not a normal completion: the tree was ended and the stop proven.
        self.assertTrue(check['cancelled'], check)
        self.assertFalse(result['passed'])
        self.assertIs(check['process_stopped'], True)
        self.assertTrue(wait_dead(pid, 1), 'reported stopped while the child still runs')
        self.store.finish(job, result)
        task = self.store.get(job['task_id'])
        self.assertFalse(task['verification']['passed'])

    @unittest.skipUnless(WINDOWS, 'Windows job object accounting')
    def test_job_counts_residual_member_until_it_is_ended(self):
        argv = [sys.executable, '-c',
                "import subprocess,sys;c=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
                f"open(r'{self.pidfile}','w').write(str(c.pid))"]
        container = runner_module.WindowsJob()
        process = subprocess.Popen(argv, creationflags=subprocess.CREATE_NO_WINDOW | runner_module.WindowsJob.CREATE_SUSPENDED)
        self.assertTrue(container.adopt(process))
        process.coordination_job = container
        process.wait(timeout=30)
        pid = self.child_pid()
        self.assertTrue(alive(pid))
        self.assertGreaterEqual(container.active(), 1)
        self.assertFalse(runner_module.Runner.tree_stopped(process))   # leader exit is not proof
        runner_module.Runner.terminate(process)
        self.assertTrue(process.coordination_tree_terminated)
        self.assertEqual(container.active(), 0)
        self.assertTrue(runner_module.Runner.tree_stopped(process))
        self.assertTrue(wait_dead(pid, 5))
        container.close()

    @unittest.skipUnless(WINDOWS, 'Windows job breakaway')
    def test_child_cannot_break_away_from_job(self):
        script = ("import subprocess,sys\n"
                  "try:\n subprocess.Popen([sys.executable,'-c','pass'],creationflags=0x01000000).wait()\n"
                  " print('escaped')\nexcept OSError as e:\n print('refused',e.winerror)\n")
        container = runner_module.WindowsJob()
        process = subprocess.Popen([sys.executable, '-c', script], stdout=subprocess.PIPE, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW | runner_module.WindowsJob.CREATE_SUSPENDED)
        self.assertTrue(container.adopt(process))
        out, _ = process.communicate(timeout=30)
        self.assertTrue(out.startswith('refused'), out)
        self.assertTrue(container.wait_empty(5))
        container.close()

    def test_cancel_waits_for_the_whole_tree(self):
        self.check("  def test_hang(self):\n" + self.spawn_child(120) + "   time.sleep(120)\n")
        job = self.verify_job()
        outcome = {}
        worker = threading.Thread(target=lambda: outcome.update(result=self.runner(timeout=300).execute(job)))
        worker.start()
        deadline = time.monotonic() + 60
        while not (self.pidfile.exists() and self.pidfile.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(0.1)
        pid = self.child_pid()
        self.store.cancel(job['id'])
        worker.join(90)
        self.assertFalse(worker.is_alive())
        check = outcome['result']['checks'][0]
        self.assertTrue(check['cancelled'])
        self.assertIs(check['process_stopped'], True)
        self.assertTrue(wait_dead(pid, 1))
        self.assertFalse(outcome['result']['passed'])

    def test_pause_during_verification_confirms_only_after_stop(self):
        self.check("  def test_hang(self):\n" + self.spawn_child(120) + "   time.sleep(120)\n")
        job = self.verify_job()
        outcome = {}
        worker = threading.Thread(target=lambda: outcome.update(result=self.runner(timeout=300).execute(job)))
        worker.start()
        deadline = time.monotonic() + 60
        while not (self.pidfile.exists() and self.pidfile.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(0.1)
        pid = self.child_pid()
        task = self.store.get(job['task_id'])
        task = self.store.change(task['id'], task['rev'], 'pause', 'pause while verifying')
        self.assertTrue(task.get('pause_requested_at'))
        self.assertEqual(task['status'], 'submitted')   # not paused until the stop is proven
        worker.join(90)
        self.assertTrue(wait_dead(pid, 1))
        self.store.finish(job, outcome['result'])
        task = self.store.get(job['task_id'])
        self.assertEqual(task['status'], 'paused')
        self.assertEqual(task['pause_control'], 'confirmed')
        self.assertNotIn('stop_unconfirmed', task)

    def test_late_result_with_old_token_cannot_overwrite(self):
        self.check("  def test_ok(self):\n   self.assertTrue(True)\n")
        job = self.verify_job()
        result = self.runner().execute(job)
        self.assertTrue(result['passed'], result)
        # The task moved on while the job ran: its job record carries an old token.
        with self.store.transaction() as c:
            data = json.loads(c.execute('SELECT data FROM jobs WHERE id=?', (job['id'],)).fetchone()['data'])
            c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data | {'claim_token': 'old-token'}), job['id']))
        self.store.finish(job, result)
        task = self.store.get(job['task_id'])
        self.assertIsNone(task.get('verification'))
        kinds = [e['kind'] for e in self.store.timing(task)['timeline']]
        self.assertIn('stale_result_ignored', kinds)

    def test_service_restart_still_requires_external_confirmation(self):
        job = self.verify_job()   # left running: the service "restarts" now
        self.store.recover()
        task = self.store.get(job['task_id'])
        self.assertEqual(self.job_row(job['id'])['status'], 'interrupted')
        self.assertEqual(task['pause_control'], 'external')
        self.assertIsNone(task.get('verification'))

    @unittest.skipUnless(WINDOWS, 'Windows fallback without a job object')
    def test_without_job_object_completion_stays_unproven(self):
        self.check("  def test_ok(self):\n   self.assertTrue(True)\n")
        job = self.verify_job()
        with patch.object(runner_module, 'WindowsJob', side_effect=OSError('no job')):
            result = self.runner().execute(job)
        self.assertIsNone(result['checks'][0]['process_stopped'])
        self.store.finish(job, result)
        task = self.store.get(job['task_id'])
        self.assertTrue(task.get('stop_unconfirmed'))
        self.assertIsNone(task.get('verification'))

    def test_job_object_is_only_used_on_windows(self):
        tree = ast.parse((CANDIDATE / 'runner.py').read_text(encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'WindowsJob']
        self.assertEqual(len(calls), 1)
        guarded = [n for n in ast.walk(tree) if isinstance(n, ast.If) and "os.name == 'nt'" in ast.unparse(n.test)
                   and any(c in ast.walk(n) for c in calls)]
        self.assertEqual(len(guarded), 1)
        # Importing the module never touches Win32 APIs on any platform.
        self.assertTrue(hasattr(runner_module, 'WindowsJob'))


if __name__ == '__main__':
    unittest.main()
