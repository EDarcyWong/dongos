"""Loopback-only HTTP console. Mutations require same-origin CSRF token + CAS."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import unquote, urlsplit, parse_qs

from . import migrate, providers, ai_api, roadmap
from .store import Conflict, LABELS, now, resolve

STATIC = Path(__file__).with_name('web')


def read_log_tail(source):
    if not source.is_file():
        return ''
    with source.open('rb') as f:
        f.seek(max(0, source.stat().st_size - 128000))
        body = f.read()
    # A tail seek can land in the middle of a Chinese UTF-8 codepoint.
    while body and body[0] & 0xC0 == 0x80:
        body = body[1:]
    return providers.redact(body.decode('utf-8', 'replace'))


class Console(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store, runner, config=None, registry=None):
        if address[0] != '127.0.0.1':
            raise ValueError('本服务仅绑定127.0.0.1')
        super().__init__(address, Handler)
        self.store, self.runner, self.config = store, runner, config or {}
        self.registry = registry
        self.contexts = {}
        self.context_lock = threading.RLock()
        self.driving = False
        self.provider_info = runner.providers if runner else {}
        if registry and store:
            for project in registry.list():
                if project['source_root'] == str(store.root):
                    self.contexts[project['id']] = (store, runner)
        self.csrf = secrets.token_urlsafe(32)
        self.origins = {'http://127.0.0.1:' + str(self.server_port), 'http://localhost:' + str(self.server_port)}
        self.scan_lock = threading.Lock()

    def context(self, ident):
        if not self.registry:
            return self.store, self.runner
        with self.context_lock:
            if ident not in self.contexts:
                from .runner import Runner
                store = self.registry.store(ident)
                store.backup()
                migrate.synchronize(store)
                store.export()
                runner = Runner(store, self.provider_info, timeout=self.config.get('job_timeout_seconds',1800), parallel=self.config.get('parallel_jobs',2))
                if self.driving:
                    runner.start()
                self.contexts[ident] = (store, runner)
            return self.contexts[ident]

    def snapshot(self, store=None, runner=None):
        store, runner = store or self.store, runner or self.runner
        if store.state:
            store.state.refresh()   # files that arrived through git while serving
        store.recover_orphan_pauses()
        probes = store.local / 'connection-probes.json'
        tasks = [t | {'timing': store.timing(t)} for t in store.tasks()]
        return dict(at=now(), tasks=tasks, jobs=store.jobs(),
                    events=store.recent_events(), issues=store.validate(),
                    providers=runner.providers, labels=LABELS,
                    project_root=str(store.root), works_root=str(store.works_root),
                    automation=store.setting('automation'),
                    connections=json.loads(probes.read_text(encoding='utf-8')) if probes.exists() else {},
                    **roadmap.snapshot(store))

    def scan(self, store=None):
        store = store or self.store
        with self.scan_lock:
            store.recover_orphan_pauses()
            result = migrate.synchronize(store)
            if result['added'] or result['changed']:
                store.export()
            return result


class Handler(BaseHTTPRequestHandler):
    server_version = 'DongOS-Coordination/1'

    def log_message(self, *_):
        pass

    def reply(self, data, code=200, mime='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8') if mime.startswith('application/json') else data
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized_host(self):
        return 'http://' + self.headers.get('Host', '') in self.server.origins

    # Some browsers omit the port from Origin for loopback pages. Host is still
    # required to be this service and the CSRF token remains the real gate.
    PORTLESS_LOOPBACK_ORIGINS = frozenset({'http://127.0.0.1', 'http://localhost'})

    def authorized_origin(self):
        origin = self.headers.get('Origin')
        return origin in self.server.origins or origin in self.PORTLESS_LOOPBACK_ORIGINS

    def context(self):
        ident = self.headers.get('X-Coordination-Project', '')
        if self.server.registry and not ident:
            projects = self.server.registry.list()
            ident = projects[0]['id'] if projects else ''
        self.store, self.runner = self.server.context(ident)

    def do_GET(self):
        if not self.authorized_host():
            return self.reply({'error': '无效Host'}, 403)
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        try:
            base='http://'+self.headers['Host']
            if path=='/api/ai':
                return self.reply(ai_api.discovery(base))
            if path=='/api/ai/guide':
                return self.reply(ai_api.GUIDE.read_bytes(),mime='text/markdown; charset=utf-8')
            if path=='/api/mcp/guide':
                return self.reply(ai_api.MCP_GUIDE.read_bytes(),mime='text/markdown; charset=utf-8')
            if path=='/api/ai/openapi.json':
                return self.reply(ai_api.openapi(base))
            if path.startswith('/api/v1/'):
                return self.reply(ai_api.get(self.server,path,parsed.query))
            if path == '/api/session':
                return self.reply({'csrf': self.server.csrf, 'poll_seconds': 2,
                                   'projects': self.server.registry.list() if self.server.registry else []})
            if path == '/api/projects':
                return self.reply(self.server.registry.list() if self.server.registry else [])
            if path.startswith('/api/'):
                self.context()
            if path == '/api/snapshot':
                self.server.scan(self.store)
                return self.reply(self.server.snapshot(self.store, self.runner))
            if path == '/api/roadmap':
                query = parse_qs(parsed.query, keep_blank_values=True)
                if set(query) - {'format'} or len(query.get('format', ['json'])) != 1:
                    raise ValueError('整体任务图只接受一个format参数')
                output = query.get('format', ['json'])[0]
                if output == 'json':
                    return self.reply(roadmap.snapshot(self.store))
                if output != 'markdown':
                    raise ValueError('整体任务图format只支持json或markdown')
                try:
                    body = roadmap.markdown(self.store)
                except FileNotFoundError:
                    return self.reply({'error': '整体任务图文档尚未保存'}, 404)
                return self.reply(body, mime='text/markdown; charset=utf-8')
            if path == '/api/export':
                return self.reply(self.store.export())
            if path == '/api/document':
                query = parse_qs(parsed.query)
                task = self.store.get(query.get('task', [''])[0])
                kind = query.get('kind', ['task'])[0]
                if kind not in ('task', 'delivery'):
                    raise ValueError('文档类别无效')
                root = self.store.candidate_root(task) if kind == 'delivery' else self.store.root
                source = self.store.path(task['document'] if kind == 'task' else task['delivery'], root)
                if source.suffix != '.md' or not source.is_file():
                    raise ValueError('文档尚未生成')
                return self.reply({'text': source.read_text(encoding='utf-8-sig')[:100000]})
            if path.startswith('/api/log/'):
                job_id = path.rsplit('/', 1)[-1]
                if not any(j['id'] == job_id for j in self.store.jobs()):
                    raise ValueError('作业不存在')
                source = self.store.local / 'runs' / job_id / 'output.log'
                return self.reply({'text': read_log_tail(source)})
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/theme-boot.js': ('theme-boot.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in files:
                name, mime = files[path]
                return self.reply((STATIC / name).read_bytes(), mime=mime)
            return self.reply({'error': '不存在'}, 404)
        except ai_api.NotFound as error:
            return self.reply({'error':str(error)},404)
        except (ValueError, OSError) as error:
            return self.reply({'error': str(error)}, 400)

    def do_POST(self):
        if not self.authorized_host():
            return self.reply({'error': '需要本机页面的同源操作令牌（Host 不是 ' + ' 或 '.join(sorted(self.server.origins)) + '）'}, 403)
        if not self.authorized_origin():
            return self.reply({'error': '需要本机页面的同源操作令牌（页面来源 ' + str(self.headers.get('Origin') or '缺失') + ' 不是本服务地址）'}, 403)
        if not secrets.compare_digest(self.headers.get('X-Coordinator-CSRF', ''), self.server.csrf):
            return self.reply({'error': '需要本机页面的同源操作令牌（令牌已失效，请刷新页面）'}, 403)
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.reply({'error': '需要application/json'}, 415)
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if not 0 < length <= 65536:
                return self.reply({'error': '请求过大或为空'}, 413)
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('需要JSON对象')
            path = urlsplit(self.path).path
            if path.startswith('/api/v1/'):
                result,code=ai_api.post(self.server,unquote(path),data)
                return self.reply(result,code)
            if path == '/api/projects':
                if not self.server.registry:
                    raise ValueError('未配置多项目注册表')
                result = self.server.registry.add(data.get('id'), data.get('name'), data.get('source_root'))
                self.server.context(result['id'])
                return self.reply(result)
            if path == '/api/shutdown':
                self.reply({'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self.context()
            store = self.store
            if path == '/api/tasks':
                result = store.create(data)
            elif path == '/api/action':
                result = store.change(data.get('task'), data.get('rev'), data.get('action'), data.get('note', ''), data.get('options'))
            elif path == '/api/queue':
                task = store.get(data.get('task'))
                provider = task['owner'] if data.get('kind') == 'implement' else data.get('provider', 'codex')
                if data.get('kind') != 'verify':
                    info = self.runner.providers.get(provider, {})
                    if not info.get('available'):
                        raise ValueError('该CLI尚未可用，可先手动领取任务')
                    if info.get('authenticated') is False:
                        raise ValueError('CLI已检测但尚未授权；可使用客户端的同一账号完成CLI官方授权，或先手动领取任务')
                    if data.get('kind') == 'implement' and 'implement' not in info.get('modes', []):
                        raise ValueError('该CLI尚未验证自动实现模式')
                result = store.queue(task['id'], data.get('rev'), data.get('kind'), provider)
            elif path == '/api/cancel':
                store.cancel(data.get('job'))
                result = {'ok': True}
            elif path == '/api/automation':
                store.set_automation(data.get('enabled'))
                result = {'enabled': data.get('enabled')}
            elif path == '/api/sync':
                result = self.server.scan(store)
            elif path == '/api/doctor':
                info = providers.discover(self.server.config.get('providers'))
                self.server.provider_info = info
                self.runner.providers = info
                for _, runner in self.server.contexts.values():
                    runner.providers = info
                (store.local / 'cli-probe.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
                result = info
            elif path == '/api/shutdown':
                self.reply({'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                return self.reply({'error': '不存在'}, 404)
            store.export()
            return self.reply(result)
        except ai_api.NotFound as error:
            return self.reply({'error':str(error)},404)
        except Conflict as error:
            return self.reply({'error': str(error)}, 409)
        except (ValueError, TypeError, KeyError, OSError) as error:
            return self.reply({'error': str(error)}, 400)
