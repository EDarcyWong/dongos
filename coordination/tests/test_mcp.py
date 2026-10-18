"""Actual MCP subprocess <-> real HTTP API; isolated two-project fixtures."""
import json
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination.client import CoordinationClient
from dongos_coordination.mcp_config import configuration, default_path, install
from dongos_coordination.mcp_server import MAX_MESSAGE
from dongos_coordination.projects import Registry
from dongos_coordination.runner import Runner
from dongos_coordination.server import Console

ENTRY = Path(__file__).resolve().parents[1]/'coordinate.py'


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='coordination mcp ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = Registry(self.root/'console')
        for project in ('alpha', 'beta'):
            source = self.root/project;source.mkdir()
            self.registry.add(project, project, str(source))
        self.store = self.registry.store('alpha')
        self.server = Console(('127.0.0.1', 0), self.store, Runner(self.store, {}), registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.addCleanup(self.close_server)
        self.url = 'http://127.0.0.1:'+str(self.server.server_port)
        self.client = CoordinationClient(self.url)
        self.seq = 0

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)

    def start(self, owner='claude', agent='test-worker', url=None, version='2025-06-18', role='worker'):
        process = subprocess.Popen([sys.executable, '-u', str(ENTRY), 'mcp', '--owner', owner,
                                    '--url', url or self.url, '--agent-id', agent, '--role',role],
                                   cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        messages = queue.Queue()
        def read():
            for line in iter(process.stdout.readline, b''):
                messages.put(line)
        reader = threading.Thread(target=read, daemon=True);reader.start()
        def close():
            if process.poll() is None:
                process.stdin.close()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            reader.join(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
        self.addCleanup(close)
        handle = (process, messages)
        init = self.rpc(handle, 'initialize', dict(protocolVersion=version, capabilities={}, clientInfo=dict(name='real-test', version='1')))
        self.assertEqual(init['result']['protocolVersion'], version)
        self.assertIn('Cursor', init['result']['instructions'])
        self.notify(handle, 'notifications/initialized')
        return handle

    def rpc(self, handle, method, params=None):
        self.seq += 1
        self.notify(handle, method, params, self.seq)
        response = self.receive(handle)
        self.assertEqual(response['id'], self.seq)
        return response

    def notify(self, handle, method, params=None, ident=None):
        message = dict(jsonrpc='2.0', method=method)
        if params is not None:message['params'] = params
        if ident is not None:message['id'] = ident
        handle[0].stdin.write((json.dumps(message, ensure_ascii=False)+'\n').encode());handle[0].stdin.flush()

    def receive(self, handle):
        try:line = handle[1].get(timeout=8)
        except queue.Empty:self.fail('MCP没有及时返回JSON-RPC；进程状态='+str(handle[0].poll()))
        self.assertTrue(line.endswith(b'\n'))
        return json.loads(line.decode('utf-8'))

    def call(self, handle, name, **arguments):
        response = self.rpc(handle, 'tools/call', dict(name=name, arguments=arguments))
        self.assertNotIn('error', response, response)
        result = response['result']
        value = json.loads(result['content'][0]['text'])
        if 'structuredContent' in result:self.assertEqual(result['structuredContent'], value)
        return result['isError'], value

    def create(self, owner='claude', number='C1', project='alpha', **extra):
        return self.client.create_task(project, id=number, owner=owner, title='真实中文任务',
                                       description='只修改授权文件，等待独立复验。',
                                       write_paths=[owner+'-works/docs/'+number+'.md'], **extra)

    def test_all_five_owners_real_list_claim_submit_and_unicode_history(self):
        for owner, number in [('claude', 'C1'), ('cursor', 'CR1'), ('lmstudio', 'LM1'), ('deepseek', 'D1'), ('codex','CX1')]:
            with self.subTest(owner=owner):
                t = self.create(owner, number);h = self.start(owner, owner+'-test')
                error, projects = self.call(h, 'list_projects');self.assertFalse(error)
                self.assertEqual([p['id'] for p in projects['projects']], ['alpha', 'beta'])
                error, tasks = self.call(h, 'list_tasks', project='alpha');self.assertFalse(error)
                self.assertEqual([x['id'] for x in tasks['tasks']], [t['id']])
                error, doc = self.call(h, 'read_document', project='alpha', task_id=t['id'])
                self.assertFalse(error);self.assertIn('授权文件', doc['text'])
                error, task = self.call(h, 'get_task', project='alpha', task_id=t['id']);self.assertEqual(task['task']['rev'], t['rev'])
                error, task = self.call(h, 'claim_task', project='alpha', task_id=t['id'], rev=t['rev'])
                self.assertFalse(error);t = task['task'];self.assertEqual(t['claimed_by'], owner+'-test')
                path = self.store.path(t['delivery']);path.parent.mkdir(parents=True, exist_ok=True);path.write_text('原始交付\n', encoding='utf-8')
                error, result = self.call(h, 'submit_task', project='alpha', task_id=t['id'], rev=t['rev'], report='已写说明；测试未运行。等待独立复验。')
                self.assertFalse(error);self.assertEqual(result['task']['status'], 'submitted');self.assertIsNone(result['task']['verification'])
                self.assertTrue(path.read_text(encoding='utf-8').startswith('原始交付\n'))
                error, doc = self.call(h, 'read_document', project='alpha', task_id=t['id'], kind='delivery')
                self.assertIn('测试未运行', doc['text']);self.assertEqual(len(doc['sha256']), 64)
                self.assertEqual(self.store.jobs(), [])

    def test_conflicting_workers_stale_rev_and_cross_owner_cannot_mutate(self):
        t = self.create();a = self.start(agent='a');b = self.start(agent='b');cursor = self.start('cursor')
        error, claimed = self.call(a, 'claim_task', project='alpha', task_id=t['id'], rev=t['rev']);self.assertFalse(error)
        for h, name, rev in [(b, 'claim_task', t['rev']), (b, 'submit_task', claimed['task']['rev']), (cursor, 'release_task', claimed['task']['rev'])]:
            error, result = self.call(h, name, project='alpha', task_id=t['id'], rev=rev)
            self.assertTrue(error);self.assertEqual(result['status'], 409)
        self.assertFalse(self.store.path(t['delivery']).exists())
        error, released = self.call(a, 'release_task', project='alpha', task_id=t['id'], rev=claimed['task']['rev'])
        self.assertFalse(error);self.assertEqual(released['task']['status'], 'todo')
        error, _ = self.call(b, 'claim_task', project='alpha', task_id=t['id'], rev=released['task']['rev']);self.assertFalse(error)

    def test_codex_coordinator_real_review_verify_accept_and_integration(self):
        manager=self.start('codex',role='coordinator');worker=self.start('claude')
        error,r=self.call(manager,'create_task',project='alpha',id='C20',owner='claude',title='bounded review',
                          write_paths=['claude-works/docs/C20.md'],checks=['discover:claude-works/tests:test_manager.py'])
        self.assertFalse(error);t=r['task'];self.assertFalse(t['auto_dispatch'])
        path=self.store.path('claude-works/docs/C20.md');path.parent.mkdir(parents=True,exist_ok=True);path.write_text('ready',encoding='utf-8')
        tests=self.store.path('claude-works/tests');tests.mkdir(parents=True)
        (tests/'test_manager.py').write_text("import unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n def test_real_file(self):self.assertEqual(Path('claude-works/docs/C20.md').read_text(),'ready')\n",encoding='utf-8')
        error,r=self.call(worker,'claim_task',project='alpha',task_id=t['id'],rev=t['rev']);self.assertFalse(error);t=r['task']
        error,r=self.call(worker,'submit_task',project='alpha',task_id=t['id'],rev=t['rev'],report='implementation ready; tests not run by owner')
        self.assertFalse(error);t=r['task']
        error,r=self.call(manager,'change_task',project='alpha',task_id=t['id'],rev=t['rev'],action='accept',note='cannot accept before independent check')
        self.assertTrue(error);self.assertEqual(r['status'],409)
        error,r=self.call(manager,'queue_verification',project='alpha',task_id=t['id'],rev=t['rev']);self.assertFalse(error)
        job=self.store.take_job();self.assertEqual(job['id'],r['job']['id']);self.assertEqual(job['provider'],'python')
        result=self.server.runner.execute(job);self.assertTrue(result['passed'],result);self.store.finish(job,result)
        error,jobs=self.call(manager,'list_jobs',project='alpha',task_id=t['id']);self.assertFalse(error)
        self.assertEqual(jobs['jobs'][0]['status'],'completed')
        error,log=self.call(manager,'read_job_log',project='alpha',job_id=job['id']);self.assertFalse(error);self.assertIn('test_real_file',log['text'])
        t=self.client.task('alpha',t['id']);path.write_text('changed',encoding='utf-8')
        error,r=self.call(manager,'change_task',project='alpha',task_id=t['id'],rev=t['rev'],action='accept',note='changed source must be refused')
        self.assertTrue(error);self.assertEqual(r['status'],409)
        path.write_text('ready',encoding='utf-8')
        error,r=self.call(manager,'change_task',project='alpha',task_id=t['id'],rev=t['rev'],action='accept',note='independent file assertion passed; reviewed implementation and test')
        self.assertFalse(error);self.assertEqual(r['task']['status'],'accepted');t=r['task']
        error,r=self.call(manager,'change_task',project='alpha',task_id=t['id'],rev=t['rev'],action='integrate',note='reviewed live files match the verified fingerprint')
        self.assertFalse(error);self.assertEqual(r['task']['status'],'integrated')
        self.assertEqual(len(self.store.jobs()),1)

    def test_manager_project_isolation_token_refresh_and_workers_cannot_manage(self):
        a=self.create();b=self.create(project='beta');self.create('cursor','CR1')
        h=self.start('codex',role='coordinator');worker=self.start('deepseek')
        error,r=self.call(h,'list_tasks',project='alpha');self.assertFalse(error);self.assertEqual(r['total'],2)
        self.assertEqual(len(self.rpc(h,'tools/list')['result']['tools']),13)
        error,r=self.call(h,'change_task',project='alpha',task_id=a['id'],rev=a['rev'],action='pause',note='pause bounded task')
        self.assertFalse(error);self.assertEqual(self.client.task('beta',b['id'])['status'],'todo')
        self.server.csrf='new-manager-token'
        error,r=self.call(h,'change_task',project='beta',task_id=b['id'],rev=b['rev'],action='pause',note='refresh must retain beta header')
        self.assertFalse(error);self.assertEqual(self.client.task('beta',b['id'])['status'],'paused')
        error,r=self.call(h,'change_task',project='beta',task_id=b['id'],rev=r['task']['rev'],action='resume',note='resume beta')
        self.assertFalse(error);self.assertEqual(r['task']['status'],'todo')
        forbidden=self.rpc(worker,'tools/call',dict(name='change_task',arguments=dict(project='alpha',task_id=a['id'],rev=a['rev'],action='resume',note='wrong role')))
        self.assertEqual(forbidden['error']['code'],-32602)
        from dongos_coordination.mcp_server import TaskMCP
        with self.assertRaises(ValueError):TaskMCP(self.client,'claude',role='coordinator')

    def test_manager_respects_scope_limits_and_rework_history(self):
        h=self.start('codex',role='coordinator');t=self.create();w=self.start()
        error,r=self.call(w,'claim_task',project='alpha',task_id=t['id'],rev=t['rev']);self.assertFalse(error)
        error,r=self.call(w,'submit_task',project='alpha',task_id=t['id'],rev=r['task']['rev'],report='original report');self.assertFalse(error)
        error,r=self.call(h,'change_task',project='alpha',task_id=t['id'],rev=r['task']['rev'],action='rework',note='specific missing branch')
        self.assertFalse(error);self.assertEqual(r['task']['status'],'rework');self.assertIn('missing',r['task']['review_note'])
        self.assertIn('original report',self.store.path(t['delivery']).read_text(encoding='utf-8'))
        error,r=self.call(h,'create_task',project='alpha',id='LM20',owner='lmstudio',title='bad scope',write_paths=['lmstudio-works/tests/test_forbidden.py'])
        self.assertTrue(error);self.assertEqual(r['status'],400)
        response=self.rpc(h,'tools/call',dict(name='create_task',arguments=dict(project='alpha',id='C21',owner='claude',title='bad',write_paths=[True])))
        self.assertEqual(response['error']['code'],-32602)
        self.assertEqual(self.store.jobs(),[])

    def test_archive_hides_handoff_preserves_history_and_can_be_restored(self):
        from dongos_coordination import migrate
        from dongos_coordination.store import Conflict
        h = self.start('codex', role='coordinator')
        worker = self.start()
        t = self.create(number='C16')
        beta = self.create(number='C16', project='beta')
        book = self.store.path(t['document'])
        delivery = self.store.path(t['delivery'])
        delivery.parent.mkdir(parents=True, exist_ok=True)
        delivery.write_text('原交付保留\n', encoding='utf-8')
        original = (book.read_bytes(), delivery.read_bytes())
        error, r = self.call(h, 'change_task', project='alpha', task_id=t['id'],
                             rev=t['rev'], action='archive', note='cannot archive active todo')
        self.assertTrue(error)
        error, r = self.call(h, 'change_task', project='alpha', task_id=t['id'],
                             rev=t['rev'], action='pause', note='handed off')
        self.assertFalse(error); t = r['task']
        error, r = self.call(h, 'change_task', project='alpha', task_id=t['id'],
                             rev=t['rev'], action='archive', note='replacement integrated')
        self.assertFalse(error); archived = r['task']
        self.assertTrue(archived['archived']); self.assertEqual(archived['status'], 'paused')
        self.assertEqual(self.call(h, 'list_tasks', project='alpha')[1]['total'], 0)
        self.assertEqual(self.server.snapshot()['tasks'], [])
        self.assertEqual(self.client.tasks('alpha'), [])
        self.assertEqual(self.client.task('beta', beta['id'])['status'], 'todo')
        error, r = self.call(h, 'get_task', project='alpha', task_id=t['id'])
        self.assertFalse(error); self.assertEqual(r['task']['archive_note'], 'replacement integrated')
        error, r = self.call(h, 'read_document', project='alpha', task_id=t['id'], kind='delivery')
        self.assertFalse(error); self.assertEqual(r['text'], '原交付保留\n')
        self.assertEqual((book.read_bytes(), delivery.read_bytes()), original)
        migrate.synchronize(self.store)
        self.assertEqual(self.store.get(t['id'])['rev'], archived['rev'])
        exported = self.store.export()
        self.assertEqual(exported['tasks'], [])
        self.assertEqual([x['id'] for x in exported['archived_tasks']], [t['id']])
        for action in ('resume', 'pause'):
            error, _ = self.call(h, 'change_task', project='alpha', task_id=t['id'],
                                 rev=archived['rev'], action=action, note='must restore first')
            self.assertTrue(error)
        with self.assertRaises(Conflict):
            self.store.queue(t['id'], archived['rev'], 'verify')
        denied = self.rpc(worker, 'tools/call', dict(name='change_task', arguments=dict(
            project='alpha', task_id=t['id'], rev=archived['rev'], action='unarchive', note='wrong role')))
        self.assertEqual(denied['error']['code'], -32602)
        error, _ = self.call(h, 'change_task', project='alpha', task_id=t['id'],
                             rev=t['rev'], action='unarchive', note='stale revision')
        self.assertTrue(error)
        error, r = self.call(h, 'change_task', project='alpha', task_id=t['id'],
                             rev=archived['rev'], action='unarchive', note='restore history to list')
        self.assertFalse(error); self.assertFalse(r['task']['archived'])
        self.assertEqual(r['task']['status'], 'paused')
        self.assertEqual(len(self.client.tasks('alpha')), 1)
        self.assertEqual(self.store.jobs(), [])
        kinds = [e['kind'] for e in self.store.recent_events()]
        self.assertIn('archive', kinds); self.assertIn('unarchive', kinds)

    def test_deepseek_handoff_can_be_submitted_and_independently_verified(self):
        manager=self.start('codex',role='coordinator');worker=self.start('deepseek')
        error,r=self.call(manager,'create_task',project='alpha',id='D14',owner='deepseek',title='handoff fixture',
                          write_paths=['deepseek-works/docs/D14.md'],checks=['discover:deepseek-works/tests:test_handoff.py'])
        self.assertFalse(error);t=r['task'];self.assertEqual(t['status'],'todo')
        source=self.store.path('deepseek-works/docs/D14.md');source.parent.mkdir(parents=True,exist_ok=True);source.write_text('ready',encoding='utf-8')
        tests=self.store.path('deepseek-works/tests');tests.mkdir(parents=True)
        (tests/'test_handoff.py').write_text("import unittest\nfrom pathlib import Path\nclass T(unittest.TestCase):\n def test_handoff(self):self.assertEqual(Path('deepseek-works/docs/D14.md').read_text(),'ready')\n",encoding='utf-8')
        error,r=self.call(worker,'claim_task',project='alpha',task_id=t['id'],rev=t['rev']);self.assertFalse(error)
        error,r=self.call(worker,'submit_task',project='alpha',task_id=t['id'],rev=r['task']['rev'],report='handoff implemented; owner tests not run');self.assertFalse(error)
        error,r=self.call(manager,'queue_verification',project='alpha',task_id=t['id'],rev=r['task']['rev']);self.assertFalse(error)
        job=self.store.take_job();self.assertEqual(job['id'],r['job']['id']);result=self.server.runner.execute(job)
        self.assertTrue(result['passed'],result);self.store.finish(job,result)
        self.assertEqual(self.client.task('alpha',t['id'])['status'],'submitted')
        self.assertEqual(self.client.task('alpha',t['id'])['verification']['checks'][0]['tests'],1)

    def test_project_pagination_dependencies_and_active_job_lock(self):
        dep = self.create(number='C1');blocked = self.create(number='C2', depends_on=[dep['id']]);queued = self.create(number='C3')
        self.store.queue(queued['id'], queued['rev'], 'implement')
        h = self.start()
        error, result = self.call(h, 'list_tasks', project='alpha', limit=1)
        self.assertEqual(result['total'], 3);self.assertEqual(result['next_offset'], 1)
        error, result = self.call(h, 'list_tasks', project='alpha', limit=1, offset=1)
        self.assertEqual(result['tasks'][0]['id'], blocked['id'])
        error, result = self.call(h, 'list_tasks', project='beta');self.assertEqual(result['tasks'], [])
        for t in (blocked, queued):
            error, result = self.call(h, 'claim_task', project='alpha', task_id=t['id'], rev=t['rev'])
            self.assertTrue(error);self.assertEqual(result['status'], 409)
        error, result = self.call(h, 'get_task', project='beta', task_id=dep['id'])
        self.assertTrue(error);self.assertEqual(result['status'], 404)

    def test_no_mutating_notification_or_unknown_tools_and_strict_arguments(self):
        t = self.create();h = self.start()
        self.notify(h, 'tools/call', dict(name='claim_task', arguments=dict(project='alpha', task_id=t['id'], rev=t['rev'])))
        self.assertEqual(self.rpc(h, 'ping')['result'], {})
        self.assertEqual(self.client.task('alpha', t['id'])['status'], 'todo')
        names = [t['name'] for t in self.rpc(h, 'tools/list')['result']['tools']]
        self.assertEqual(len(names), 8);self.assertNotIn('accept_task', names);self.assertNotIn('queue', names)
        metadata=self.rpc(h,'tools/list',dict(cursor=None,_meta=dict(progressToken='codex-discovery')))
        self.assertEqual(len(metadata['result']['tools']),8)
        for name, args in [('accept_task', {}), ('claim_task', dict(project='alpha', task_id=t['id'], rev=True)),
                           ('claim_task', dict(project='alpha', task_id=t['id'], rev=t['rev'], owner='cursor')),
                           ('get_task', dict(project='../beta', task_id=t['id']))]:
            result = self.rpc(h, 'tools/call', dict(name=name, arguments=args))
            self.assertEqual(result['error']['code'], -32602)
        self.assertEqual(self.client.task('alpha', t['id'])['status'], 'todo')

    def test_csrf_refresh_and_disconnected_service_report_tool_error(self):
        a = self.create(number='C1');b = self.create(number='C2');h = self.start()
        self.assertFalse(self.call(h, 'claim_task', project='alpha', task_id=a['id'], rev=a['rev'])[0])
        self.server.csrf = 'rotated-test-token'
        self.assertFalse(self.call(h, 'claim_task', project='alpha', task_id=b['id'], rev=b['rev'])[0])
        # A real local listener that is closed produces a deterministic connection refusal.
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0));url = 'http://127.0.0.1:'+str(sock.getsockname()[1])
        offline = self.start(url=url)
        error, result = self.call(offline, 'list_projects');self.assertTrue(error);self.assertIsNone(result['status'])
        self.assertEqual(self.rpc(offline, 'ping')['result'], {})

    def test_utf8_framing_oversize_parse_errors_recovery_and_legacy_version(self):
        h = self.start(version='2024-11-05')
        for payload in (b'{\n', b'\xff\n', b'[]\n', b'x'*(MAX_MESSAGE+1)+b'\n'):
            h[0].stdin.write(payload);h[0].stdin.flush()
            result = self.receive(h);self.assertIn(result['error']['code'], (-32700, -32600))
        error, result = self.call(h, 'get_workflow');self.assertFalse(error);self.assertEqual(result['owner'], 'claude')
        response = self.rpc(h, 'tools/call', dict(name='get_workflow'))
        self.assertNotIn('structuredContent', response['result'])


class MCPConfigTests(unittest.TestCase):
    def test_codex_toml_preserves_existing_config_and_approval_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            p=default_path('codex',temp);p.parent.mkdir(parents=True)
            original='# user comment\nmodel = "original-model"\n[mcp_servers.other]\ncommand = "existing"\n'
            p.write_text(original,encoding='utf-8');r=install('codex',home=temp)
            after=p.read_text(encoding='utf-8');self.assertTrue(after.startswith(original))
            d=tomllib.loads(after);self.assertEqual(d['model'],'original-model');self.assertEqual(d['mcp_servers']['other']['command'],'existing')
            e=d['mcp_servers']['coordination-tasks'];self.assertEqual(e['args'][-2:],['--role','coordinator'])
            self.assertEqual(Path(r['backup']).read_text(encoding='utf-8'),original)
            self.assertFalse(install('codex',home=temp)['changed'])
            after=after.replace('# END coordination-tasks MCP (Codex coordinator)','default_tools_approval_mode = "prompt"\nenv = { KEEP_VALUE = "sample" }\n# END coordination-tasks MCP (Codex coordinator)')
            p.write_text(after,encoding='utf-8');install('codex',home=temp)
            e=tomllib.loads(p.read_text(encoding='utf-8'))['mcp_servers']['coordination-tasks']
            self.assertEqual(e['default_tools_approval_mode'],'prompt');self.assertEqual(e['env'],{'KEEP_VALUE':'sample'})

    def test_codex_unowned_collision_invalid_toml_and_managed_other_keys_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config.toml'
            for old in ('[mcp_servers.coordination-tasks]\ncommand="other"\n','invalid = ['):
                p.write_text(old,encoding='utf-8')
                with self.assertRaises(ValueError):install('codex',target=p)
                self.assertEqual(p.read_text(encoding='utf-8'),old)
            p.unlink();install('codex',target=p)
            old=p.read_text(encoding='utf-8').replace('# END coordination-tasks MCP (Codex coordinator)','[unrelated]\nkeep=true\n# END coordination-tasks MCP (Codex coordinator)')
            p.write_text(old,encoding='utf-8')
            with self.assertRaises(ValueError):install('codex',target=p)
            self.assertEqual(p.read_text(encoding='utf-8'),old)

    def test_deepseek_profile_insert_keeps_original_yaml_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            path = default_path('deepseek', temp);path.parent.mkdir(parents=True)
            original = '# existing comment\n- id: existing\n  name: package\n  config:\n    value: !!js process.env.VALUE\n'
            path.write_text(original, encoding='utf-8')
            result = install('deepseek', home=temp)
            after = path.read_text(encoding='utf-8');self.assertTrue(after.startswith(original))
            self.assertEqual(Path(result['backup']).read_text(encoding='utf-8'), original)
            row = json.loads(next(line[2:] for line in after.splitlines() if line.startswith('- {')))
            entry, = row['insert'];self.assertEqual(entry['name'], '@deepseek-ai/dsh-mcp-client')
            self.assertEqual(entry['config']['transport'], 'stdio');self.assertIn('deepseek', entry['config']['args'])
            self.assertFalse(install('deepseek', home=temp)['changed'])
            self.assertFalse((path.parent/'package.json.lock').exists())

    def test_deepseek_empty_root_collision_and_manifest_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'cordis.patch.yml'
            path.write_text('# empty\n[]\n', encoding='utf-8');install('deepseek', target=path)
            self.assertNotIn('[]', path.read_text(encoding='utf-8'))
            for old in ('- id: coordination-tasks\n  name: other\n', '{not: a-list}\n'):
                path.write_text(old, encoding='utf-8')
                with self.assertRaises(ValueError):install('deepseek', target=path)
                self.assertEqual(path.read_text(encoding='utf-8'), old)
            path.write_text('[]\n', encoding='utf-8')
            lock=path.parent/'package.json.lock';lock.write_text('12345\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'正在更新'):install('deepseek', target=path)
            self.assertEqual(path.read_text(encoding='utf-8'),'[]\n');self.assertEqual(lock.read_text(),'12345\n')

    def test_configuration_merges_preserves_other_settings_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory(prefix='mcp settings ') as temp:
            home = Path(temp)
            for client in ('claude', 'cursor', 'lmstudio'):
                path = default_path(client, home);path.parent.mkdir(parents=True, exist_ok=True)
                original = dict(setting='保留', mcpServers=dict(other=dict(command='existing')))
                path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
                result = install(client, home=home)
                saved = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(saved['setting'], original['setting']);self.assertEqual(saved['mcpServers']['other'], original['mcpServers']['other'])
                self.assertEqual(json.loads(Path(result['backup']).read_text(encoding='utf-8')), original)
                entry = saved['mcpServers']['coordination-tasks']
                self.assertTrue(Path(entry['command']).is_absolute());self.assertTrue(Path(entry['args'][1]).is_absolute())
                self.assertIn(client, entry['args']);self.assertNotIn('shell', entry)
                self.assertFalse(install(client, home=home)['changed'])

    def test_invalid_existing_or_colliding_config_and_remote_url_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'mcp.json'
            for original in ('{"mcpServers":[]}', '{bad', '{"mcpServers":{"coordination-tasks":{"command":"other"}}}',
                             '{"mcpServers":{"coordination-tasks":{"command":"other","args":["other_coordinate.py"]}}}'):
                path.write_text(original, encoding='utf-8')
                with self.assertRaises(ValueError):install('cursor', target=path)
                self.assertEqual(path.read_text(encoding='utf-8'), original)
            for url in ('https://example.com', 'http://127.0.0.1:8765/path', 'http://u:p@127.0.0.1'):
                with self.assertRaises(ValueError):configuration('claude', url)


if __name__ == '__main__':
    unittest.main()
