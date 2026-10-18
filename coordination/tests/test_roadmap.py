"""Project-local progress map reads and HTTP isolation; no model invocations."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dongos_coordination import roadmap
from dongos_coordination.projects import Registry
from dongos_coordination.runner import Runner
from dongos_coordination.server import Console


def example(title='整体任务图'):
    return dict(version=1, title=title, updated_at='2026-10-18', scope='项目里程碑',
                summary='已完成启动闭环', focus='编译器自举', notes=['按验收证据标注'],
                tracks=[dict(id='system', title='系统线', stages=[dict(
                    id='P0', title='工具链', status='complete',
                    done=['构建通过'], remaining=[], evidence=['PLAN.md'])])])


class RoadmapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.registry = Registry(self.base / 'control')
        for name in ('alpha', 'beta'):
            source = self.base / name
            source.mkdir()
            self.registry.add(name, name, str(source))
        self.store = self.registry.store('alpha')
        self.server = Console(('127.0.0.1', 0), self.store, Runner(self.store, {}),
                              registry=self.registry)
        self.server.context('beta')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def save(self, value, project='alpha'):
        target = self.registry.store(project).works_root / 'roadmap.json'
        target.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def get(self, path, project='alpha'):
        request = Request(self.url + path, headers={'X-Coordination-Project': project})
        return urlopen(request, timeout=5)

    def read_json(self, path, project='alpha'):
        with self.get(path, project) as response:
            return json.load(response)

    def test_missing_map_is_null_without_using_source_directory(self):
        (self.store.root / 'roadmap.json').write_text(json.dumps(example()), encoding='utf-8')
        self.assertEqual(self.read_json('/api/roadmap'), {'roadmap': None, 'roadmap_error': None})
        state = self.server.snapshot(self.store, self.server.runner)
        self.assertIsNone(state['roadmap'])
        self.assertIsNone(state['roadmap_error'])
        self.assertEqual(state['tasks'], [])

    def test_selected_project_maps_and_snapshots_never_cross_projects(self):
        first, second = example('Alpha'), example('Beta')
        self.save(first)
        self.save(second, 'beta')
        for project, expected in (('alpha', first), ('beta', second), ('alpha', first)):
            with self.subTest(project=project):
                state = self.read_json('/api/roadmap', project)
                self.assertEqual(state, {'roadmap': expected, 'roadmap_error': None})
                self.assertEqual(self.read_json('/api/snapshot', project)['roadmap'], expected)

    def test_invalid_json_and_schema_do_not_interrupt_snapshot(self):
        source = self.store.works_root / 'roadmap.json'
        invalid = [b'{broken', b'\xff']
        for change in ({'version': True}, {'tracks': []}, {'notes': 'not a list'}):
            invalid.append(json.dumps(example() | change).encode('utf-8'))
        bad_stage = copy.deepcopy(example())
        bad_stage['tracks'][0]['stages'][0]['status'] = 'integrated'
        invalid.append(json.dumps(bad_stage).encode('utf-8'))
        for body in invalid:
            with self.subTest(body=body):
                source.write_bytes(body)
                state = self.read_json('/api/snapshot')
                self.assertIsNone(state['roadmap'])
                self.assertTrue(state['roadmap_error'])
                self.assertEqual(state['tasks'], [])
        self.save(example())
        self.assertIsNone(self.read_json('/api/snapshot')['roadmap_error'])

    def test_oversized_map_is_isolated_and_unreadable_map_is_reported(self):
        source = self.store.works_root / 'roadmap.json'
        source.write_bytes(b' ' * (roadmap.MAX_BYTES + 1))
        state = self.read_json('/api/snapshot')
        self.assertIsNone(state['roadmap'])
        self.assertIn('256 KiB', state['roadmap_error'])
        with patch.object(roadmap, '_read', side_effect=PermissionError('cannot read')):
            self.assertEqual(roadmap.snapshot(self.store),
                             {'roadmap': None, 'roadmap_error': 'cannot read'})

    def test_markdown_is_bounded_project_local_and_read_only(self):
        body = '# Alpha 整体任务图\n\n```mermaid\ngraph TD\nA-->B\n```\n'
        target = self.store.works_root / 'progress-map.md'
        target.write_text(body, encoding='utf-8')
        beta = self.registry.store('beta').works_root / 'progress-map.md'
        beta.write_text('# Beta\n', encoding='utf-8')
        before = target.read_bytes()
        with patch.object(self.server, 'scan') as scan, patch.object(self.store, 'export') as export:
            with self.get('/api/roadmap?format=markdown') as response:
                self.assertEqual(response.read(), before)
                self.assertEqual(response.headers['Content-Type'], 'text/markdown; charset=utf-8')
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
            self.read_json('/api/roadmap?format=json')
            scan.assert_not_called()
            export.assert_not_called()
        with self.get('/api/roadmap?format=markdown', 'beta') as response:
            self.assertEqual(response.read(), beta.read_bytes())
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.store.tasks(), [])
        self.assertEqual(self.store.jobs(), [])
        self.assertEqual(self.store.recent_events(), [])

    def test_markdown_missing_or_oversized_is_explicit_error(self):
        (self.store.root / 'progress-map.md').write_text('wrong directory', encoding='utf-8')
        with self.assertRaises(HTTPError) as error:
            self.get('/api/roadmap?format=markdown')
        self.assertEqual(error.exception.code, 404)
        (self.store.works_root / 'progress-map.md').write_bytes(b'a' * (roadmap.MAX_BYTES + 1))
        with self.assertRaises(HTTPError) as error:
            self.get('/api/roadmap?format=markdown')
        self.assertEqual(error.exception.code, 400)

    def test_unknown_formats_paths_or_duplicate_parameters_are_rejected(self):
        for query in ('format=html', 'format=', 'format=json&format=markdown',
                      'path=../beta_works/roadmap.json', 'format=markdown&path=other.md'):
            with self.subTest(query=query), self.assertRaises(HTTPError) as error:
                self.get('/api/roadmap?' + query)
            self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error:
            self.get('/api/roadmap', '../alpha')
        self.assertEqual(error.exception.code, 400)

    def test_no_post_write_route(self):
        request = Request(self.url + '/api/roadmap', data=b'{}', headers={
            'X-Coordination-Project': 'alpha', 'Origin': self.url,
            'Content-Type': 'application/json', 'X-Coordinator-CSRF': self.server.csrf})
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=5)
        self.assertEqual(error.exception.code, 404)
        self.assertFalse((self.store.works_root / 'roadmap.json').exists())
        self.assertFalse((self.store.works_root / 'progress-map.md').exists())

    def test_symlinks_cannot_read_other_project(self):
        other = self.registry.store('beta').works_root / 'roadmap.json'
        self.save(example('Beta'), 'beta')
        target = self.store.works_root / 'roadmap.json'
        try:
            target.symlink_to(other)
        except OSError:
            self.skipTest('File symlinks unavailable on this Windows host')
        value = self.read_json('/api/roadmap')
        self.assertIsNone(value['roadmap'])
        self.assertIn('不能越出', value['roadmap_error'])


if __name__ == '__main__':
    unittest.main()
