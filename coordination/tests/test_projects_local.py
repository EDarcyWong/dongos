"""Project isolation and bounded local model integration. No real model requests."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination import cli, local_model, migrate, providers
from dongos_coordination.projects import Registry
from dongos_coordination.runner import Runner, inventory, snapshot
from dongos_coordination.server import Console
from dongos_coordination.store import Conflict


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.registry = Registry(self.base/'control')
        for name in ('alpha','beta'):
            source = self.base/name
            source.mkdir()
            (source/'main.py').write_text('original\n', encoding='utf-8')
            self.registry.add(name,name,str(source))

    def tearDown(self):
        self.temp.cleanup()

    def task(self, project='alpha'):
        return self.registry.store(project).create(dict(id='LM1',owner='lmstudio',title='Simple helper',
             description='One pure function',write_paths=['lmstudio-works/src/helper.py']))

    def test_same_task_id_isolated_state_books_and_index(self):
        first,second = self.task('alpha'),self.task('beta')
        a,b = self.registry.store('alpha'),self.registry.store('beta')
        a.change(first['id'],first['rev'],'claim')
        self.assertEqual(b.get(second['id'])['status'],'todo')
        for store in (a,b):
            self.assertTrue(store.path(first['document']).is_relative_to(store.works_root))
            self.assertFalse((store.root/first['document']).exists())
            store.export()
            self.assertTrue((store.works_root/'index.json').is_file())
            self.assertEqual(store.validate(),[])

    def test_duplicate_or_coordinator_source_registration_rejected(self):
        with self.assertRaises(Conflict):self.registry.add('alpha','Other',str(self.base/'beta'))
        with self.assertRaises(Conflict):self.registry.add('other','Other',str(self.base/'alpha'))
        for ident in ('../escape','Upper',''):
            with self.assertRaises(ValueError):self.registry.add(ident,'Bad',str(self.base/'alpha'))
        with self.assertRaises(ValueError):self.registry.add('control','Control',str(self.base))

    def test_mounted_snapshot_and_fingerprint_track_physical_works(self):
        task = self.task()
        store = self.registry.store('alpha')
        source = store.path('lmstudio-works/src/helper.py')
        source.parent.mkdir(parents=True)
        source.write_text('v1',encoding='utf-8')
        before = store.identity(store.root,task['write_paths'])
        target = self.base/'isolated'
        identities = snapshot(store.root,target,store.works_root)
        self.assertEqual(identities,inventory(target))
        self.assertEqual((target/'main.py').read_text(),'original\n')
        self.assertEqual((target/'lmstudio-works/src/helper.py').read_text(),'v1')
        source.write_text('v2',encoding='utf-8')
        self.assertNotEqual(before,store.identity(store.root,task['write_paths']))
        self.assertEqual(store.identity(target,task['write_paths']),before)

    def test_fresh_import_does_not_trust_self_declared_acceptance(self):
        store = self.registry.store('alpha')
        book=store.path('claude-works/tasks/C99-new.md');book.parent.mkdir(parents=True)
        book.write_text('# C99 — Unreviewed\n状态：已验收。',encoding='utf-8')
        migrate.synchronize(store)
        self.assertEqual(store.get('claude:C99')['status'],'todo')

    def test_historical_variants_require_independent_baseline(self):
        for status in ('R3验收通过','原R2正式验收','已验收'):
            self.assertEqual(migrate.document_status('状态：'+status+'。'),'accepted')
        store=self.registry.store('alpha')
        book=store.path('deepseek-works/tasks/D8-buddy.md');book.parent.mkdir(parents=True)
        book.write_text('# D8 — Buddy\n状态：R3验收通过。',encoding='utf-8')
        migrate.synchronize(store)
        self.assertEqual(store.get('deepseek:D8')['status'],'todo')
        readme=store.path('deepseek-works/README.md');readme.write_text('D1～D13 均已验收',encoding='utf-8')
        proof=store.path('deepseek-works/reviews/2026-10-18-D12-acceptance.md');proof.parent.mkdir();proof.write_text('independent evidence',encoding='utf-8')
        migrate.synchronize(store)
        task=store.get('deepseek:D8')
        self.assertIn('kernel/mm/phys_buddy.dg',task['write_paths'])
        # An already imported todo is never silently promoted after a new evidence file appears.
        self.assertEqual(task['status'],'todo')

    def test_cli_uses_standalone_home_and_probe_module_not_shadowed(self):
        with patch.object(cli.providers,'discover',return_value={'lmstudio':{'available':True}}), patch.object(cli.probe,'connection',return_value={'passed':True}) as connect, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['--home',str(self.registry.home),'--project','alpha','probe','lmstudio']),0)
            connect.assert_called_once()

    def test_http_project_switch_never_exposes_other_tasks_or_documents(self):
        task = self.task('alpha')
        store=self.registry.store('alpha')
        runner=Runner(store,{})
        server=Console(('127.0.0.1',0),store,runner,registry=self.registry)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        def get(path,project):
            with urlopen(Request(url+path,headers={'X-Coordination-Project':project}),timeout=5) as response:return json.load(response)
        try:
            self.assertEqual(len(get('/api/projects','')),2)
            self.assertEqual(len(get('/api/snapshot','alpha')['tasks']),1)
            self.assertEqual(get('/api/snapshot','beta')['tasks'],[])
            with self.assertRaises(HTTPError):get('/api/document?task=lmstudio:LM1&kind=task','beta')
            with self.assertRaises(HTTPError):get('/api/snapshot','../alpha')
        finally:
            server.shutdown();server.server_close();thread.join()


class LocalModelTests(unittest.TestCase):
    def test_local_endpoint_rejects_remote_proxy_redirect_targets_and_credentials(self):
        self.assertEqual(local_model.endpoint('http://127.0.0.1:1234/v1/'),'http://127.0.0.1:1234/v1')
        for value in ('https://example.com/v1','http://127.0.0.1.evil/v1','http://user:pw@localhost/v1','http://localhost/v1?x=y','http://localhost/path'):
            with self.subTest(value=value),self.assertRaises(ValueError):local_model.endpoint(value)

    def test_simple_scope_enforces_exact_files_no_tests_or_mainline(self):
        local_model.simple_scope(['lmstudio-works/src/helper.py','lmstudio-works/deliveries/LM1.md'],'one function')
        for paths in (['lmstudio-works/src/**'],['kernel/main.py'],['lmstudio-works/tests/test_helper.py'],['lmstudio-works/src/a.sh'],['lmstudio-works/src/a.py']*4):
            with self.subTest(paths=paths),self.assertRaises(ValueError):local_model.simple_scope(paths,'test')

    def test_response_entirely_validated_before_any_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);allowed=['lmstudio-works/src/helper.py']
            value={'files':[dict(path=allowed[0],content='safe'),dict(path='../escape.py',content='bad')]}
            with self.assertRaises(ValueError):local_model.apply_files(root,allowed,value)
            self.assertFalse((root/allowed[0]).exists())
            local_model.apply_files(root,allowed,{'files':[dict(path=allowed[0],content='valid')]})
            self.assertEqual((root/allowed[0]).read_text(),'valid')

    def test_truncated_or_tool_output_is_never_delivery(self):
        for reason,message in [('length',dict(content='{}')),('stop',dict(content='{}',tool_calls=[{}]))]:
            with patch.object(local_model,'request',return_value={'choices':[dict(finish_reason=reason,message=message)]}),self.assertRaises(ValueError):
                local_model.complete({'base_url':'http://localhost:1234/v1','model':'local'},[])

    def test_schema_request_has_no_execution_tools(self):
        with patch.object(local_model,'request',return_value={'choices':[dict(finish_reason='stop',message=dict(content='{}'))]}) as post:
            local_model.complete({'base_url':'http://localhost:1234/v1','model':'local'},[],schema=local_model.SCHEMA)
            payload=post.call_args.args[2]
            self.assertNotIn('tools',payload)
            self.assertEqual(payload['response_format']['type'],'json_schema')

    def test_native_request_turns_off_thinking_and_has_no_integrations(self):
        reply={'output':[dict(type='message',content='{"files":[]}')],'stats':{'total_output_tokens':8}}
        with patch.object(local_model,'request',return_value=reply) as post:
            value=local_model.complete(dict(base_url='http://localhost:1234/v1',model='local',wire_api='native'),[dict(role='user',content='small task')],schema=local_model.SCHEMA)
            self.assertEqual(json.loads(value),{'files':[]})
            payload=post.call_args.args[2]
            self.assertEqual(payload['reasoning'],'off')
            self.assertEqual(payload['integrations'],[])
            self.assertFalse(payload['store'])


class ProviderDiscoveryTests(unittest.TestCase):
    def test_windows_cursor_node_entry_is_detected_without_shell_launchers(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            version=base/'cursor-agent/versions/2026.10.16-e3cb207'
            version.mkdir(parents=True)
            (version/'node.exe').write_bytes(b'fixture')
            (version/'index.js').write_text('// fixture',encoding='utf-8')
            def run(argv,**kwargs):
                text='Not logged in' if argv[-1]=='status' else '{"loggedIn":true,"authMethod":"claude.ai"}' if 'auth' in argv else '--print --mode --output-format --tools --permission-mode --json'
                return SimpleNamespace(returncode=0,stdout=text.encode(),stderr=b'')
            with patch.dict(os.environ,{'LOCALAPPDATA':str(base)}),patch.object(providers.shutil,'which',return_value=None),patch.object(providers.subprocess,'run',side_effect=run),patch.object(local_model,'discover',return_value={'available':False}):
                cursor=providers.discover()['cursor']
            self.assertTrue(cursor['available'])
            self.assertFalse(cursor['authenticated'])
            self.assertEqual(Path(cursor['path']),version/'node.exe')
            self.assertEqual(cursor['prefix_args'],[str(version/'index.js')])

    def test_cursor_review_uses_ask_mode_without_force_or_shell(self):
        info=dict(name='cursor',path='node.exe',prefix_args=['C:/Program Files/Cursor/index.js'],available=True,features={'--mode':True})
        argv=providers.command(info,'review',Path('unused.md'))
        self.assertEqual(argv[:2],['node.exe','C:/Program Files/Cursor/index.js'])
        self.assertEqual(argv[-2:],['--mode','ask'])
        for flag in ('--force','--yolo','--approve-mcps'):
            self.assertNotIn(flag,argv)
        with self.assertRaises(ValueError):providers.command(info,'implement',Path('unused.md'))


if __name__=='__main__':unittest.main()
