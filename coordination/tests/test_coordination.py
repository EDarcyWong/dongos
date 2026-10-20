"""Isolated state machine, real subprocess and HTTP boundary checks; no model calls."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dongos_coordination import migrate, providers
from dongos_coordination.runner import Runner, inventory, snapshot
from dongos_coordination.server import Console
from dongos_coordination.store import Conflict, Store, checks, fingerprint, relative


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.store = Store(self.root)
        self.source = self.root / 'cursor-works/src/widget.py'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('original', encoding='utf-8')
        tests = self.root / 'tests'
        tests.mkdir()
        (tests / '__init__.py').write_text('', encoding='utf-8')
        (tests / 'test_sample.py').write_text("import unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n def test_value(self):self.assertEqual(Path('cursor-works/src/widget.py').read_text(), 'original')\n", encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def task(self, number='CR9', **extra):
        return self.store.create(dict(id=number, owner='cursor', title='Test component',
                                     description='A bounded task', write_paths=['cursor-works/src/widget.py'],
                                     checks=['module:tests.test_sample'], **extra))

    def delivery(self, task):
        path = self.root / task['delivery']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('actual delivery', encoding='utf-8')

    def submit(self, task):
        self.delivery(task)
        return self.store.change(task['id'], task['rev'], 'submit')


class StateTests(Fixture):
    def test_create_preserves_books_and_uses_revision(self):
        task = self.task()
        book = self.root / task['document']
        before = book.read_bytes()
        task = self.store.change(task['id'], task['rev'], 'claim')
        with self.assertRaises(Conflict):self.store.change(task['id'], 1, 'release')
        self.assertEqual(book.read_bytes(), before)
        with self.assertRaises(Conflict):self.store.change(task['id'], task['rev'], 'release')
        task = self.store.change(task['id'], task['rev'], 'pause')
        task = self.store.change(task['id'], task['rev'], 'confirm_pause', note='isolated fixture stopped', options={'stopped_confirmed': True})
        task = self.store.change(task['id'], task['rev'], 'release')
        self.assertEqual(task['status'], 'todo')
        with self.assertRaises(Conflict):self.task()

    def test_path_escape_hidden_and_symlink_are_rejected(self):
        for value in ['../x', 'C:/x', '/tmp/x', 'a/../b', '.git/config', 'x/.env', 'a//b']:
            with self.subTest(value=value),self.assertRaises(ValueError):relative(value)
        with self.assertRaises(ValueError):self.store.create(dict(id='X1',owner='cursor',title='bad',write_paths=['lang/bootstrap/x.dg']))

    def test_conflicting_paths_and_dependencies(self):
        task = self.task()
        with self.assertRaises(Conflict):self.task('CR10')
        other = self.store.create(dict(id='C9',owner='claude',title='Dependent',write_paths=['claude-works/src/dep.dg'],depends_on=[task['id']]))
        with self.assertRaises(Conflict):self.store.change(other['id'],other['rev'],'claim')
        with self.assertRaises(ValueError):self.store.create(dict(id='C8',owner='claude',title='Missing',write_paths=['claude-works/src/z.dg'],depends_on=['claude:C999']))

    def test_submit_requires_real_delivery_and_accept_requires_fresh_pass(self):
        task = self.task()
        with self.assertRaises(ValueError):self.store.change(task['id'],task['rev'],'submit')
        task = self.submit(task)
        with self.assertRaises(ValueError):self.store.change(task['id'],task['rev'],'accept','read source')
        identity = fingerprint(self.root,task['write_paths'])
        with self.store.transaction() as c:
            task['verification']={'passed':True,'fingerprint':identity}
            self.store.save(c,task,'test_receipt')
        self.source.write_text('changed',encoding='utf-8')
        with self.assertRaises(Conflict):self.store.change(task['id'],task['rev'],'accept','source reviewed')
        self.source.write_text('original',encoding='utf-8')
        task=self.store.change(task['id'],task['rev'],'accept','source/contract reviewed')
        self.assertEqual(task['status'],'accepted')
        task=self.store.change(task['id'],task['rev'],'integrate','main files matched')
        self.assertEqual(task['status'],'integrated')

    def test_glob_identity_includes_new_and_deleted_files(self):
        before=fingerprint(self.root,['cursor-works/src/**'])
        self.assertIn('cursor-works/src/widget.py',before)
        self.source.with_name('new.py').write_text('new')
        self.assertNotEqual(before,fingerprint(self.root,['cursor-works/src/**']))
        self.source.unlink()
        self.assertNotIn('cursor-works/src/widget.py',fingerprint(self.root,['cursor-works/src/**']))

    def test_pause_resume_and_automation_does_not_reopen_closed_tasks(self):
        task=self.task()
        task=self.store.change(task['id'],task['rev'],'pause')
        task=self.store.change(task['id'],task['rev'],'resume')
        self.assertEqual(task['status'],'todo')
        task=self.store.change(task['id'],task['rev'],'automation',options={'auto_dispatch':True,'auto_verify':True})
        self.assertTrue(task['auto_dispatch'])
        self.assertFalse(self.store.setting('automation'))
        self.store.set_automation(True)
        self.assertTrue(self.store.setting('automation'))

    def test_test_commands_are_structured_not_shell(self):
        for spec in ['python -c evil', 'module:os', 'module:lang.tests.test_a;calc', 'discover:../../:test_a.py', 'discover:tests:*.py']:
            with self.subTest(spec=spec),self.assertRaises(ValueError):checks([spec])
        self.assertEqual(checks(['discover:cursor-works/tests:test_bytes.py']),['discover:cursor-works/tests:test_bytes.py'])
        self.assertEqual(checks(['discover:deepseek-works/tests:test_handoff.py']),['discover:deepseek-works/tests:test_handoff.py'])
        with self.assertRaises(ValueError):checks(['discover:deepseek-works/build:test_handoff.py'])

    def test_queue_duplicate_cancel_and_restart_no_replay(self):
        task=self.task()
        job=self.store.queue(task['id'],task['rev'],'implement')
        with self.assertRaises(Conflict):self.store.queue(task['id'],task['rev'],'implement')
        self.store.cancel(job['id'])
        job=self.store.queue(task['id'],task['rev'],'implement')
        self.store.take_job()
        self.store.recover()
        self.assertEqual(self.store.get(task['id'])['status'],'rework')
        self.assertEqual(self.store.jobs()[0]['status'],'interrupted')
        self.assertIsNone(self.store.take_job())

    def test_concurrent_claims_have_one_winner(self):
        task=self.task();results=[]
        def claim():
            try:self.store.change(task['id'],task['rev'],'claim');results.append('won')
            except Conflict:results.append('conflict')
        threads=[threading.Thread(target=claim) for _ in range(4)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(results.count('won'),1)
        self.assertEqual(results.count('conflict'),3)

    def test_migration_idempotent_and_new_self_acceptance_not_trusted(self):
        book=self.root/'claude-works/tasks/C6-source-position.md'
        book.parent.mkdir(parents=True)
        book.write_text('# C6 — Position\n\n负责人：Claude。状态：进行中。',encoding='utf-8')
        migrate.synchronize(self.store)
        self.assertEqual(self.store.get('claude:C6')['status'],'in_progress')
        book.write_text('# C6 — Position\n\n负责人：Claude。状态：已验收。',encoding='utf-8')
        migrate.synchronize(self.store)
        self.assertEqual(self.store.get('claude:C6')['status'],'in_progress')
        self.assertEqual(migrate.synchronize(self.store)['added'],[])

    def test_validate_detects_dependency_cycles(self):
        task=self.task()
        with self.store.transaction() as c:
            task['depends_on']=[task['id']]
            self.store.save(c,task,'bad_fixture')
        self.assertIn('依赖环',self.store.validate()[0]['message'])

    def test_verification_is_serialized_across_tasks(self):
        one=self.submit(self.task())
        two=self.store.create(dict(id='C9',owner='claude',title='Other',write_paths=['claude-works/src/x.dg'],checks=['module:tests.test_sample']))
        two=self.submit(two)
        self.store.queue(one['id'],one['rev'],'verify')
        self.store.queue(two['id'],two['rev'],'verify')
        self.assertIsNotNone(self.store.take_job())
        self.assertIsNone(self.store.take_job())


class RunnerTests(Fixture):
    def make_job(self,kind='verify'):
        task=self.task()
        if kind=='verify' or kind=='review':task=self.submit(task)
        self.store.queue(task['id'],task['rev'],kind,'codex')
        return self.store.take_job()

    def runner(self):return Runner(self.store,{},timeout=5,parallel=1)

    def test_native_verification_pass_keeps_task_submitted_and_main_unchanged(self):
        job=self.make_job();before=inventory(self.root,source_filter=True)
        result=self.runner().execute(job);self.store.finish(job,result)
        self.assertTrue(result['passed'],result)
        self.assertEqual(result['checks'][0]['tests'],1)
        self.assertEqual(self.store.get(job['task_id'])['status'],'submitted')
        self.assertEqual(before,inventory(self.root,source_filter=True))

    def test_skipped_and_zero_test_runs_are_not_passes(self):
        job=self.make_job()
        (self.root/'tests/test_sample.py').write_text('import unittest\nclass T(unittest.TestCase):\n @unittest.skip("missing tool")\n def test_skip(self):pass\n')
        result=self.runner().execute(job)
        self.assertFalse(result['passed'])
        self.assertEqual(result['checks'][0]['skips'],1)

    def test_test_source_mutation_rejected_even_if_unittest_returns_zero(self):
        job=self.make_job()
        (self.root/'tests/test_sample.py').write_text("import unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n def test_mutate(self):Path('cursor-works/src/widget.py').write_text('wrong')\n")
        result=self.runner().execute(job)
        self.assertFalse(result['passed'])
        self.assertFalse(result['source_stable'])
        self.assertEqual(self.source.read_text(),'original')

    def fake(self,text):
        script=Path(self.temp.name)/'fake_cli.py';script.write_text(text,encoding='utf-8')
        return patch('dongos_coordination.providers.command',return_value=[sys.executable,str(script)])

    def test_implementation_real_process_collects_isolated_delivery(self):
        job=self.make_job('implement')
        with self.fake("import sys\nfrom pathlib import Path\nsys.stdin.read()\np=Path('cursor-works/deliveries/CR9.md');p.parent.mkdir(parents=True,exist_ok=True);p.write_text('done')\nprint('{\"result\":\"delivered\"}')\n"):
            result=self.runner().execute(job)
        self.store.finish(job,result)
        self.assertTrue(result['passed'],result)
        task=self.store.get(job['task_id']);self.assertEqual(task['status'],'submitted')
        self.assertEqual(task['candidate'],job['id'])
        self.assertFalse((self.root/task['delivery']).exists())

    def test_exit_zero_without_delivery_is_failure(self):
        job=self.make_job('implement')
        with self.fake("import sys\nsys.stdin.read()\nprint('done')"):
            result=self.runner().execute(job)
        self.assertFalse(result['passed'])

    def test_chinese_output_and_multibyte_split_are_lossless_utf8(self):
        job=self.make_job('implement')
        script=("import sys,os,time\nprint('中文日志：任务已完成',flush=True)\n"
                "value='跨块汉字🙂'.encode('utf-8')\n"
                "for b in value:\n os.write(sys.stdout.fileno(),bytes([b]));time.sleep(.002)\n")
        with self.fake(script):
            result=self.runner().execute(job)
        work=self.store.local/'runs'/job['id']
        text=(work/'output.log').read_text(encoding='utf-8')
        self.assertEqual(text,'中文日志：任务已完成\n跨块汉字🙂')
        self.assertNotIn('\ufffd',text)

    def test_log_tail_does_not_split_a_chinese_character(self):
        from dongos_coordination.server import read_log_tail
        source=Path(self.temp.name)/'long-output.log'
        source.write_text('中文🙂'*30000,encoding='utf-8')
        text=read_log_tail(source)
        self.assertNotIn('\ufffd',text)
        self.assertTrue(text.endswith('中文🙂'))

    def test_forbidden_new_root_file_cannot_be_hidden_by_inventory(self):
        job=self.make_job('implement')
        with self.fake("from pathlib import Path\nPath('unauthorized.txt').write_text('bad')"):
            result=self.runner().execute(job)
        self.assertFalse(result['passed'])
        self.assertIn('unauthorized.txt',result['forbidden_paths'])
        self.assertFalse((self.root/'unauthorized.txt').exists())

    def test_readonly_review_rejects_workspace_writes(self):
        job=self.make_job('review')
        with self.fake("from pathlib import Path\nPath('cursor-works/src/widget.py').write_text('bad')"):
            result=self.runner().execute(job)
        self.assertFalse(result['passed'])

    def test_cancellation_and_timeout_kill_owned_process(self):
        job=self.make_job('implement');runner=self.runner();runner.timeout=.3
        with self.fake('import time\ntime.sleep(30)'):
            result=runner.execute(job)
        self.assertFalse(result['passed']);self.assertTrue(result['timed_out'])

    def test_provider_commands_never_enable_permission_bypass(self):
        for name in ('codex','claude'):
            info=dict(available=True,name=name,path='fake',features={'--permission-mode':True,'--tools':True})
            args=providers.command(info,'implement',Path('report'))
            self.assertNotIn('--dangerously-skip-permissions',args)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',args)
            if name=='claude':self.assertNotIn('Bash',args[-1])
        self.assertEqual(providers.redact('Bearer abcdefghijk sk-test123456789012345'),'Bearer [REDACTED] [REDACTED]')


class HTTPTests(Fixture):
    def setUp(self):
        super().setUp()
        self.runner=Runner(self.store,{})
        self.server=Console(('127.0.0.1',0),self.store,self.runner)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.token=self.request('/api/session')['csrf']

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def request(self,path,data=None,headers=None):
        h={'Origin':self.url,'Content-Type':'application/json','X-Coordinator-CSRF':getattr(self,'token','')}
        h.update(headers or {})
        req=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
        with urlopen(req,timeout=5) as r:
            return json.load(r)

    def test_snapshot_and_create_task_have_live_cas_state(self):
        data=dict(owner='cursor',id='CR11',title='<script>test</script>',write_paths=['cursor-works/src/new.py'])
        task=self.request('/api/tasks',data)
        self.assertEqual(self.request('/api/snapshot')['tasks'][0]['title'],data['title'])
        updated=self.request('/api/action',dict(task=task['id'],rev=task['rev'],action='claim'))
        self.assertEqual(updated['status'],'in_progress')
        with self.assertRaises(HTTPError) as error:self.request('/api/action',dict(task=task['id'],rev=task['rev'],action='release'))
        self.assertEqual(error.exception.code,409)

    def test_cross_origin_missing_token_and_rebinding_rejected(self):
        for headers in [{'Origin':'https://evil.example'}, {'X-Coordinator-CSRF':'bad'}, {'Host':'evil.example'}]:
            with self.subTest(headers=headers),self.assertRaises(HTTPError) as error:self.request('/api/sync',{},headers)
            self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:self.request('/api/snapshot',headers={'Host':'evil.example'})
        self.assertEqual(error.exception.code,403)

    def test_portless_loopback_origin_still_requires_host_and_token(self):
        for origin in ['http://127.0.0.1','http://localhost']:
            with self.subTest(origin=origin):
                self.request('/api/sync',{},{'Origin':origin})
                for headers in [{'X-Coordinator-CSRF':'bad'},{'Host':'evil.example'}]:
                    with self.assertRaises(HTTPError) as error:self.request('/api/sync',{},{'Origin':origin,**headers})
                    self.assertEqual(error.exception.code,403)
        for origin in ['http://127.0.0.1:1','https://127.0.0.1','http://127.0.0.1.evil.example','http://[::1]','null']:
            with self.subTest(origin=origin),self.assertRaises(HTTPError) as error:self.request('/api/sync',{},{'Origin':origin})
            self.assertEqual(error.exception.code,403)

    def test_arbitrary_file_and_command_routes_absent(self):
        for path in ['/../coordination/.local/tasks.sqlite3','/api/document?task=../x','/api/log/../../x']:
            with self.subTest(path=path),self.assertRaises(HTTPError):self.request(path)
        with self.assertRaises(HTTPError):self.request('/api/exec',{'command':'calc.exe'})

    def test_cli_unavailable_is_not_queued_and_static_csp_present(self):
        task=self.task()
        with self.assertRaises(HTTPError):self.request('/api/queue',dict(task=task['id'],rev=task['rev'],kind='implement'))
        self.assertEqual(self.store.jobs(),[])
        with urlopen(self.url,timeout=5) as response:
            self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
            self.assertIn('协作工作台',response.read().decode())


if __name__=='__main__':unittest.main()
