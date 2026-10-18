"""Small local-only text adapter. The model has no filesystem or command tools."""
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener, Request

MAX_FILES = 3  # Includes delivery. Tests are authored and run independently.


def endpoint(value):
    url = urlsplit(value)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or
            url.username or url.password or url.query or url.fragment or url.path.rstrip('/') != '/v1'):
        raise ValueError('LM Studio 仅支持本机 http://127.0.0.1:端口/v1')
    return value.rstrip('/')


def request(base, route, payload=None, timeout=8):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
    url = endpoint(base)
    if route.startswith('/api/'):
        url = url.removesuffix('/v1')
    req = Request(url + route, data=data, headers={'Content-Type': 'application/json'})
    # Ignore system proxies: prompts must stay on the loopback endpoint. Never follow redirects.
    from urllib.request import HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as response:
        body = response.read(128001)
        if len(body) > 128000:
            raise ValueError('本地模型响应过长')
        return json.loads(body)


def discover(config=None):
    config = config or {}
    base = endpoint(config.get('base_url', 'http://127.0.0.1:1234/v1'))
    model = config.get('model', 'qwen/qwen3.8-27b')
    info = dict(name='lmstudio', available=False, base_url=base, model=model,
                version=model, modes=['implement'], auth='本机API', simple_only=True,
                wire_api='native', reasoning='off',
                hint='仅简单任务：最多3个明确文件、含交付；无工具调用，无自动验收。')
    try:
        models = request(base, '/models')
        info['models'] = [m['id'] for m in models.get('data', [])]
        info['available'] = model in info['models']
    except (OSError, ValueError, KeyError) as error:
        info['error'] = type(error).__name__
    return info


def complete(info, messages, *, schema=None, tokens=1024, timeout=180):
    if info.get('wire_api') == 'native':
        system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
        if schema:
            system += '\n只返回一个JSON对象，不加Markdown围栏或解释。JSON必须符合此schema：' + json.dumps(schema,ensure_ascii=False)
        prompt = '\n'.join(m['content'] for m in messages if m['role'] != 'system')
        value = request(info['base_url'], '/api/v1/chat', dict(model=info['model'],input=prompt,
            system_prompt=system, reasoning='off', integrations=[], store=False,
            temperature=0,max_output_tokens=tokens), timeout)
        output = value.get('output',[])
        if (any(o.get('type') not in ('message','reasoning') for o in output) or
                value.get('stats',{}).get('total_output_tokens',tokens) >= tokens):
            raise ValueError('本地模型输出截断或包含工具请求，不能作为交付')
        messages = [o['content'] for o in output if o.get('type') == 'message']
        if not messages:
            raise ValueError('本地模型没有返回正文')
        return '\n'.join(messages)
    data = dict(model=info['model'], messages=messages, temperature=0, max_tokens=tokens, stream=False)
    if schema:
        data['response_format'] = dict(type='json_schema', json_schema=dict(name='simple_delivery', strict=True, schema=schema))
    result = request(info['base_url'], '/chat/completions', data, timeout)
    choice = result['choices'][0]
    if choice.get('finish_reason') != 'stop' or choice['message'].get('tool_calls'):
        raise ValueError('本地模型输出被截断或试图调用工具，不能作为交付')
    return choice['message']['content']


def simple_scope(paths, description):
    from .store import relative
    if not 1 <= len(paths) <= MAX_FILES or len(description) > 3000:
        raise ValueError('LM Studio 只接简单任务：含交付最多3个文件、说明最多3000字符')
    for path in paths:
        relative(path)
        if (not path.startswith(('lmstudio-works/src/', 'lmstudio-works/docs/', 'lmstudio-works/fixtures/', 'lmstudio-works/deliveries/')) or
                Path(path).suffix not in ('.py', '.md', '.json', '.txt')):
            raise ValueError('本地模型只写专属src/docs/fixtures/deliveries内的明确文本文件，不修改测试或主线')


def apply_files(root, allowed, value):
    from .store import resolve
    simple_scope(allowed, '')
    files = value.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('交付文件数量无效')
    seen, total, writes = set(), 0, []
    for item in files:
        path, content = item.get('path'), item.get('content')
        if path not in allowed or path in seen or not isinstance(content, str):
            raise ValueError('交付包含越权、重复路径或非法正文')
        seen.add(path)
        total += len(content.encode('utf-8'))
        if total > 24000:
            raise ValueError('交付超过24KiB，请拆分任务')
        writes.append((resolve(root, path), content))
    # Validate the entire response before writing any file.
    for path, content in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')


SCHEMA = dict(type='object', additionalProperties=False, required=['files'], properties={
    'files': dict(type='array', minItems=1, maxItems=MAX_FILES, items=dict(type='object',
        additionalProperties=False, required=['path', 'content'], properties={
            'path': dict(type='string'), 'content': dict(type='string')}))})
