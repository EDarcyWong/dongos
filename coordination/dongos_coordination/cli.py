import argparse
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

from . import migrate, providers, probe
from .runner import Runner
from .server import Console
from .store import Store
from .projects import Registry, DEFAULT_HOME


def main(argv=None):
    parser = argparse.ArgumentParser(description='本地多项目协作控制台')
    parser.add_argument('--home', type=Path, default=DEFAULT_HOME, help='独立协调数据/配置目录')
    parser.add_argument('--project', default='dongos', help='项目编号')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('init', 'sync', 'validate', 'status', 'doctor', 'export', 'stop', 'projects', 'backup', 'state-sync'):
        commands.add_parser(command)
    timing = commands.add_parser('timing', help='只读查询完整任务时间线及每轮办理/返修时长')
    timing.add_argument('task_id', help='完整任务编号，如claude:C43')
    identity = commands.add_parser('resolve-identity', help='按绑定原文/事件SHA的审查清单分离同号异义历史，不删除事件或授予验收')
    identity.add_argument('task_id')
    identity.add_argument('--rev', required=True, type=int)
    identity.add_argument('--manifest', required=True)
    identity.add_argument('--sha256', required=True)
    identity.add_argument('--note', required=True)
    for name, help_text in (
            ('recover-state', '按逐项审查证据恢复空库历史状态，默认仅预览'),
            ('reconcile-state', '按逐项审查证据协调落后状态库并保留历史，默认仅预览')):
        recovery = commands.add_parser(name, help=help_text)
        recovery.add_argument('--snapshot', required=True, type=Path)
        recovery.add_argument('--audit', required=True, type=Path)
        recovery.add_argument('--apply', action='store_true')
    add = commands.add_parser('add-project')
    add.add_argument('id')
    add.add_argument('--name', required=True)
    add.add_argument('--source', required=True)
    connect = commands.add_parser('probe')
    connect.add_argument('provider', choices=('codex', 'claude', 'cursor', 'lmstudio'))
    serve = commands.add_parser('serve')
    serve.add_argument('--port', type=int)
    mcp = commands.add_parser('mcp', help='供客户端启动的本地stdio MCP任务服务')
    mcp.add_argument('--owner', required=True, choices=('claude', 'cursor', 'lmstudio', 'deepseek', 'codex'))
    mcp.add_argument('--role', choices=('worker','coordinator'), default='worker')
    mcp.add_argument('--url', default='http://127.0.0.1:8765')
    mcp.add_argument('--agent-id')
    mcp_config = commands.add_parser('mcp-config', help='生成/合并客户端MCP配置，不运行模型')
    mcp_config.add_argument('--client', required=True, choices=('claude', 'cursor', 'lmstudio', 'deepseek', 'codex'))
    mcp_config.add_argument('--url', default='http://127.0.0.1:8765')
    mcp_config.add_argument('--install', action='store_true')
    mcp_config.add_argument('--target', type=Path)
    args = parser.parse_args(argv)
    if args.command == 'mcp':
        from .mcp_server import serve as serve_mcp
        return serve_mcp(args.owner, args.url, args.agent_id, role=args.role)
    if args.command == 'mcp-config':
        from .mcp_config import configuration, install, codex_toml
        if args.target and not args.install:
            parser.error('--target需要--install')
        result = install(args.client, args.url, target=args.target) if args.install else configuration(args.client, args.url)
        if args.client=='codex' and not args.install:
            print(codex_toml(result['mcp_servers']['coordination-tasks']),end='')
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    registry = Registry(args.home)
    if args.command == 'projects':
        print(json.dumps(registry.list(), ensure_ascii=False, indent=2))
        return 0
    if args.command == 'add-project':
        print(json.dumps(registry.add(args.id, args.name, args.source), ensure_ascii=False, indent=2))
        return 0
    config_file = registry.home / 'config.json'
    config = json.loads(config_file.read_text(encoding='utf-8')) if config_file.exists() else {}
    if args.command in ('recover-state', 'reconcile-state'):
        from .state_recovery import reconcile, restore
        if args.command == 'reconcile-state' and not any(
                arg == '--project' or arg.startswith('--project=') for arg in (sys.argv[1:] if argv is None else argv)):
            parser.error('reconcile-state 需要显式 --project，防止协调错误项目')
        store = registry.store(args.project, allow_state_recovery=True)
        operation = reconcile if args.command == 'reconcile-state' else restore
        result = operation(store, args.project, args.snapshot, args.audit, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    store = registry.store(args.project) if args.command not in ('serve', 'stop') else None
    if args.command == 'resolve-identity':
        if not any(arg == '--project' or arg.startswith('--project=') for arg in (sys.argv[1:] if argv is None else argv)):
            parser.error('resolve-identity需要显式--project')
        result = store.change(args.task_id, args.rev, 'resolve_identity', args.note,
                              dict(project=args.project, manifest=args.manifest, sha256=args.sha256))
        store.export()
    elif args.command == 'timing':
        task = store.get(args.task_id)
        result = dict(project=args.project, task_id=task['id'], rev=task['rev'],
                      status=task['status'], timing=store.timing(task))
    elif args.command == 'doctor':
        result = providers.discover(config.get('providers'))
        (store.local / 'cli-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    elif args.command == 'probe':
        info = providers.discover(config.get('providers'))
        result = probe.connection(store, info[args.provider])
    elif args.command in ('init', 'sync'):
        store.backup()
        result = migrate.synchronize(store)
        store.export()
    elif args.command == 'backup':
        result = dict(backup=str(store.backup()))
    elif args.command == 'state-sync':
        result = store.state.sync()          # merge state/ into the database, then write every change back
    elif args.command == 'validate':
        result = store.validate()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result else 0
    elif args.command == 'status':
        result = dict(tasks=store.tasks(), issues=store.validate())
    elif args.command == 'export':
        result = store.export()
    elif args.command == 'stop':
        runtime = json.loads((registry.home / '.local/server.json').read_text(encoding='utf-8'))
        url = runtime['url']
        with urlopen(url + '/api/session', timeout=5) as response:
            token = json.load(response)['csrf']
        req = Request(url + '/api/shutdown', data=b'{}', headers={'Content-Type': 'application/json', 'Origin': url, 'X-Coordinator-CSRF': token})
        with urlopen(req, timeout=5) as response:
            result = json.load(response)
    else:
        cli_infos = providers.discover(config.get('providers'))
        items = registry.list()
        if items:
            ident = args.project if any(p['id'] == args.project for p in items) else items[0]['id']
            store = registry.store(ident)
            store.backup()
            migrate.synchronize(store)
            store.export()
        runner = Runner(store, cli_infos, timeout=config.get('job_timeout_seconds', 1800), parallel=config.get('parallel_jobs', 2)) if store else None
        port = args.port if args.port is not None else config.get('port', 8765)
        server = Console(('127.0.0.1', port), store, runner, config, registry)
        server.provider_info = cli_infos
        url = 'http://127.0.0.1:' + str(server.server_port)
        try:
            for item in items:
                server.context(item['id'])[1].start()
            server.driving = True
            runtime_dir = registry.home / '.local'
            runtime_dir.mkdir(exist_ok=True)
            (runtime_dir / 'server.json').write_text(json.dumps({'url': url}), encoding='utf-8')
            print(url, flush=True)
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            for _, active_runner in server.contexts.values():
                active_runner.close()
            server.server_close()
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
