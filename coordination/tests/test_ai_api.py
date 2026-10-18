"""Real HTTP/client tests, isolated projects, no model invocations."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dongos_coordination.client import CoordinationClient,APIError
from dongos_coordination.projects import Registry
from dongos_coordination.runner import Runner
from dongos_coordination.server import Console


class AIAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.registry=Registry(self.root/'control')
        for project in ('alpha','beta'):
            source=self.root/project;source.mkdir()
            self.registry.add(project,project,str(source))
        self.store=self.registry.store('alpha')
        self.server=Console(('127.0.0.1',0),self.store,Runner(self.store,{}),registry=self.registry)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.client=CoordinationClient(self.url)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.temp.cleanup()

    def create(self,number='C20',project='alpha',**extra):
        return self.client.create_task(project,id=number,owner='claude',title='独立文档任务',description='只写授权文件。',
             write_paths=[f'claude-works/docs/{number}.md'],**extra)

    def claim(self,task,agent='claude-worker-1'):
        return self.client.claim_task('alpha',task['id'],rev=task['rev'],owner='claude',agent_id=agent)

    def test_discovery_document_and_openapi_are_served_with_no_project_context(self):
        with urlopen(self.url+'/api/ai') as response:value=json.load(response)
        self.assertEqual(value['version'],'1')
        with urlopen(value['guide']) as response:
            self.assertIn('text/markdown',response.headers['Content-Type'])
            self.assertIn('领取',response.read().decode('utf-8'))
        with urlopen(value['openapi']) as response:spec=json.load(response)
        self.assertEqual(spec['openapi'],'3.1.0')
        self.assertIn('/api/v1/projects/{project}/tasks/{task_id}/claim',spec['paths'])
        self.assertEqual(value['mcp']['transport'],'stdio')
        self.assertFalse(value['mcp']['automatic_client_execution'])
        with urlopen(value['mcp']['guide']) as response:
            self.assertIn('text/markdown',response.headers['Content-Type'])
            self.assertIn('Cursor 保持手动执行',response.read().decode('utf-8'))

    def test_client_publish_list_claim_submit_and_read_delivery(self):
        task=self.create()
        self.assertEqual(task['status'],'todo')
        self.assertEqual(self.client.tasks('alpha',owner='claude',status='todo',q='文档')[0]['id'],task['id'])
        self.assertEqual(len(self.client.projects()),2)
        self.assertIn('授权文件',self.client.document('alpha',task['id'])['text'])
        task=self.claim(task)
        self.assertEqual(task['claimed_by'],'claude-worker-1')
        self.assertEqual(task['status'],'in_progress')
        task=self.client.submit_task('alpha',task['id'],rev=task['rev'],owner='claude',agent_id='claude-worker-1',report='真实交付：未执行测试，仍需独立复验。')
        self.assertEqual(task['status'],'submitted')
        self.assertIsNone(task['verification'])
        self.assertIn('未执行测试',self.client.document('alpha',task['id'],kind='delivery')['text'])
        self.assertTrue(self.store.path(task['delivery']).is_relative_to(self.store.works_root))
        self.assertFalse((self.store.root/task['delivery']).exists())

    def test_explicit_url_project_isolation_and_not_found(self):
        task=self.create()
        self.assertEqual(self.client.tasks('beta'),[])
        for project,key in [('beta',task['id']),('missing',task['id'])]:
            with self.subTest(project=project),self.assertRaises(APIError) as error:self.client.task(project,key)
            self.assertEqual(error.exception.status,404)
        request=Request(self.url+'/api/v1/projects/alpha/tasks',headers={'X-Coordination-Project':'beta'})
        with urlopen(request) as response:self.assertEqual(json.load(response)['total'],1)

    def test_two_concurrent_workers_have_only_one_claim_winner(self):
        task=self.create()
        def attempt(agent):
            client=CoordinationClient(self.url)
            try:return client.claim_task('alpha',task['id'],rev=task['rev'],owner='claude',agent_id=agent)['claimed_by']
            except APIError as error:return error.status
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['worker-a','worker-b']))
        self.assertEqual(results.count(409),1)
        self.assertEqual(self.client.task('alpha',task['id'])['status'],'in_progress')

    def test_wrong_owner_or_worker_cannot_take_over_release_or_submit(self):
        task=self.create()
        with self.assertRaises(APIError) as error:self.client.claim_task('alpha',task['id'],rev=task['rev'],owner='cursor',agent_id='a')
        self.assertEqual(error.exception.status,409)
        task=self.claim(task)
        for action in (self.client.release_task,self.client.submit_task):
            with self.assertRaises(APIError) as error:action('alpha',task['id'],rev=task['rev'],owner='claude',agent_id='other')
            self.assertEqual(error.exception.status,409)
        task=self.client.release_task('alpha',task['id'],rev=task['rev'],owner='claude',agent_id='claude-worker-1')
        self.assertEqual(task['status'],'todo')
        self.assertIsNone(task['claimed_by'])

    def test_report_requires_claim_and_validation_before_writing(self):
        task=self.create()
        with self.assertRaises(APIError):self.client.submit_task('alpha',task['id'],rev=task['rev'],owner='claude',agent_id='worker',report='not claimed')
        task=self.claim(task)
        with self.assertRaises(APIError) as error:self.client.submit_task('alpha',task['id'],rev=task['rev'],owner='claude',agent_id='claude-worker-1',report=' ')
        self.assertEqual(error.exception.status,400)
        self.assertFalse(self.store.path(task['delivery']).exists())

    def test_resubmission_preserves_report_history_and_cas_blocks_replay(self):
        task=self.claim(self.create())
        path=self.store.path(task['delivery']);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('历史原文\n',encoding='utf-8')
        rev=task['rev']
        task=self.client.submit_task('alpha',task['id'],rev=rev,owner='claude',agent_id='claude-worker-1',report='最新交付')
        text=path.read_text(encoding='utf-8')
        self.assertTrue(text.startswith('历史原文\n'))
        self.assertIn('最新交付',text)
        with self.assertRaises(APIError) as error:self.client.submit_task('alpha',task['id'],rev=rev,owner='claude',agent_id='claude-worker-1',report='重复')
        self.assertEqual(error.exception.status,409)
        self.assertEqual(path.read_text(encoding='utf-8'),text)

    def test_stale_session_refreshes_once_and_no_self_accept_route(self):
        task=self.create()
        self.server.csrf='new-test-session'
        self.assertEqual(self.claim(task)['status'],'in_progress')
        with self.assertRaises(APIError) as error:self.client._request('/api/v1/projects/alpha/tasks/claude%3AC20/accept',{'rev':2})
        self.assertEqual(error.exception.status,404)

    def test_unsafe_fields_paths_unknown_filters_and_forged_requests_rejected(self):
        with self.assertRaises(APIError):self.create(status='accepted')
        with self.assertRaises(APIError):self.client.create_task('alpha',id='C21',owner='claude',title='bad',write_paths=['../escape'])
        with self.assertRaises(APIError):self.client.tasks('alpha',status='invented')
        request=Request(self.url+'/api/v1/projects/alpha/tasks',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://evil.example','X-Coordinator-CSRF':self.server.csrf})
        with self.assertRaises(HTTPError) as error:urlopen(request)
        self.assertEqual(error.exception.code,403)
        self.assertEqual(self.store.tasks(),[])


if __name__=='__main__':unittest.main()
