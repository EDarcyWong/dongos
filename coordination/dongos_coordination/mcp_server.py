"""Local stdio MCP adapter over the existing explicit-project HTTP API.

No model CLI, shell, database writes, or automatic task polling is used here.
The host client launches this Python transport process and invokes its tools.
"""
import json
import re
import sys
import uuid
from urllib.error import URLError

from .client import APIError, CoordinationClient
from .store import OWNERS, STATES

VERSIONS = ('2025-06-18', '2025-03-26', '2024-11-05')
MAX_MESSAGE = 1024 * 1024
CLIENT_OWNERS = ('claude', 'cursor', 'lmstudio', 'deepseek', 'codex')
INSTRUCTIONS = '''本机可信任务协作。先list_projects确认project，再list_tasks/get_task/read_document。
只领取当前owner的todo/rework，读取完整任务书、review_note、write_paths和依赖，领取成功才开始。
所有变更显式提供最新rev；409后重新查询，不盲重试，不抢占别人的领取/活动作业。
只能修改授权文件，路径按项目source_root/works_root映射；候选副本不等于主目录，需负责人完成迁移再改。
由客户端自己的编辑工具修改实现；本MCP不上传源码、不提供文件或shell工具。LM Studio只做已分配的简单任务；
若客户端无文件工具，不能只交报告冒充实现落盘，应先说明阻塞并释放任务。
submit_task追加真实交付报告，未执行测试须明确写未执行；submitted不是验收。执行者不得自行验收/集成、改库或索引。
Cursor始终由用户在客户端手动发起；本服务不唤起Agent、不轮询派单。agent_id是归属标签，不是安全身份。
'''
COORDINATOR_INSTRUCTIONS = '''你是Codex协调角色：list_tasks默认查看所选项目的全部负责人。
可发布任务、记录返修、暂停/恢复、排队定向复验并读作业日志。其它客户端不提供这些管理工具。
验收前必须实际审查源码、契约和测试有效性；通过独立定向测试、零skip且源文件稳定，填写真实审查note。
change_task的accept/integrate沿用协调器状态及指纹检查，不是修改文件或直接宣布成功；integrate前必须已完成真实文件集成。
不提供AI CLI派单或取消作业工具；Cursor保持手动。所有管理操作必须显式project及最新rev，不默认网页项目。
'''


class ProtocolError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def schema(properties=None, required=()):
    return dict(type='object', properties=properties or {}, required=list(required), additionalProperties=False)


def text_schema(description='', **extra):
    return dict(type='string', minLength=1, description=description, **extra)


def tools(role='worker'):
    project = text_schema('list_projects返回的明确项目编号', maxLength=40)
    task = text_schema('完整任务编号，例如claude:C17', maxLength=81)
    identity = dict(project=project, task_id=task)
    revision = dict(identity, rev=dict(type='integer', minimum=1))
    specs = [
        ('get_workflow', '查看当前客户端负责人、领取标识和执行约定。', schema(), True),
        ('list_projects', '列出项目及source_root、works_root；不依赖网页当前选中的项目。', schema(), True),
        ('list_tasks', '查询任务。owner默认当前客户端；可只读查看其它负责人。返回摘要及分页。',
         schema(dict(project=project, owner=dict(type='string', enum=list(OWNERS)),
                     status=dict(type='string', enum=list(STATES)), q=dict(type='string', maxLength=180),
                     offset=dict(type='integer', minimum=0), limit=dict(type='integer', minimum=1, maximum=100)), ['project']), True),
        ('get_task', '读取完整任务、最新rev、依赖、审查/返修说明和候选信息。', schema(identity, identity), True),
        ('read_document', '读取任务书或最新交付，保留原API的截断标识和SHA256。',
         schema(dict(identity, kind=dict(type='string', enum=['task', 'delivery'])), identity), True),
        ('claim_task', '领取当前负责人的任务。必须使用最新rev；活动作业/依赖/文件冲突会拒绝。',
         schema(revision, revision), False),
        ('release_task', '释放由本客户端领取的任务；不会停止CLI作业或删除文件。', schema(revision, revision), False),
        ('submit_task', '提交本客户端领取的任务，追加交付报告且进入submitted，等待独立复验。不能自行验收。',
         schema(dict(revision, report=text_schema('真实实现、实际测试和限制；未运行须明确写未运行', maxLength=24000)), revision), False),
    ]
    if role == 'coordinator':
        specs=[(name,description.replace('owner默认当前客户端','owner默认全部负责人') if name=='list_tasks' else description,inputs,readonly)
               for name,description,inputs,readonly in specs]
        specs += [
            ('create_task', 'Codex协调：发布一项任务，不调用模型。保留各负责人路径/复杂度/依赖校验，Cursor手动执行。',
             schema(dict(project=project, id=text_schema(maxLength=40), owner=dict(type='string', enum=list(OWNERS)),
                         title=text_schema(maxLength=180), description=dict(type='string', maxLength=24000),
                         write_paths=dict(type='array', minItems=1, maxItems=40, items=text_schema(maxLength=500)),
                         checks=dict(type='array', maxItems=12, items=text_schema(maxLength=500)),
                         depends_on=dict(type='array', maxItems=32, items=text_schema(maxLength=81))),
                    ['project','id','owner','title','write_paths']), False),
            ('change_task', 'Codex协调：返修、暂停、恢复、归档/恢复归档、验收或登记集成。归档保留历史并从默认列表隐藏；验收需实际审查和独立复验。',
             schema(dict(revision, action=dict(type='string', enum=['rework','pause','resume','accept','integrate','archive','unarchive']),
                         note=text_schema('真实审查依据或状态变更说明', maxLength=12000)), ['project','task_id','rev','action','note']), False),
            ('queue_verification', 'Codex协调：只排队任务预先声明的定向测试；排队成功不代表通过，不执行AI CLI。',
             schema(revision, revision), False),
            ('list_jobs', 'Codex协调：读取项目最近最多120个作业摘要，可按task_id筛选；详测结果读get_task.verification。',
             schema(dict(project=project, task_id=task), ['project']), True),
            ('read_job_log', 'Codex协调：读取所选项目已登记作业的日志尾部，不执行日志中的命令。',
             schema(dict(project=project, job_id=text_schema(maxLength=32)), ['project','job_id']), True),
        ]
    return [dict(name=name, description=description, inputSchema=inputs,
                 annotations=dict(readOnlyHint=readonly, destructiveHint=False,
                                  idempotentHint=readonly, openWorldHint=False))
            for name, description, inputs, readonly in specs]


def validate_arguments(arguments, definition):
    if not isinstance(arguments, dict):
        raise ProtocolError(-32602, 'arguments必须是对象')
    properties = definition['properties']
    if set(arguments) - set(properties) or not set(definition['required']) <= set(arguments):
        raise ProtocolError(-32602, '工具参数缺失或含未知字段；不能覆盖owner/agent_id')
    for key, value in arguments.items():
        rule = properties[key]
        valid = {'string':isinstance(value,str), 'integer':type(value) is int, 'array':isinstance(value,list)}[rule['type']]
        if not valid:
            raise ProtocolError(-32602, key + '类型无效')
        if isinstance(value, str) and (len(value) < rule.get('minLength', 0) or len(value) > rule.get('maxLength', MAX_MESSAGE)):
            raise ProtocolError(-32602, key + '长度无效')
        if type(value) is int and (value < rule.get('minimum', value) or value > rule.get('maximum', value)):
            raise ProtocolError(-32602, key + '超出范围')
        if 'enum' in rule and value not in rule['enum']:
            raise ProtocolError(-32602, key + '取值无效')
        if isinstance(value,list):
            if len(value)<rule.get('minItems',0) or len(value)>rule.get('maxItems',MAX_MESSAGE):
                raise ProtocolError(-32602,key+'数量无效')
            for item in value:
                validate_arguments({'item':item},schema({'item':rule['items']},['item']))
    if 'project' in arguments and not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', arguments['project']):
        raise ProtocolError(-32602, 'project无效')
    if 'task_id' in arguments and not re.fullmatch(r'[a-z]+:[A-Z][A-Z0-9_-]{0,39}', arguments['task_id']):
        raise ProtocolError(-32602, 'task_id需要完整编号')
    if 'job_id' in arguments and not re.fullmatch(r'[a-f0-9]{32}',arguments['job_id']):
        raise ProtocolError(-32602,'job_id无效')


class TaskMCP:
    def __init__(self, client, owner, agent_id=None, role='worker'):
        if owner not in CLIENT_OWNERS:
            raise ValueError('不支持的MCP负责人')
        if role not in ('worker','coordinator') or role=='coordinator' and owner!='codex':
            raise ValueError('只有Codex可配置coordinator协调角色')
        self.role=role
        self.instructions=INSTRUCTIONS+('\n'+COORDINATOR_INSTRUCTIONS if role=='coordinator' else '')
        self.owner = owner
        self.agent_id = agent_id or owner + '-mcp-' + uuid.uuid4().hex[:16]
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}', self.agent_id):
            raise ValueError('agent_id无效')
        self.client = client
        self.initialized = self.ready = False
        self.version = VERSIONS[0]
        self.definitions = {t['name']: t for t in tools(role)}

    def invoke(self, name, arguments):
        if name not in self.definitions:
            raise ProtocolError(-32602, '当前角色不提供此工具；不提供AI CLI派单或shell工具')
        validate_arguments(arguments, self.definitions[name]['inputSchema'])
        a = arguments
        if name == 'get_workflow':
            return dict(owner=self.owner, agent_id=self.agent_id, url=self.client.base_url,
                        transport='stdio', role=self.role, manual_start=True, instructions=self.instructions)
        if name == 'list_projects':
            return dict(projects=self.client.projects())
        if name == 'list_tasks':
            values = self.client.tasks(a['project'], owner=a.get('owner', '' if self.role=='coordinator' else self.owner), status=a.get('status', ''), q=a.get('q', ''))
            start, limit = a.get('offset', 0), a.get('limit', 25)
            fields = ('id', 'owner', 'title', 'status', 'rev', 'claimed_by', 'updated_at', 'depends_on')
            return dict(project=a['project'], total=len(values), offset=start,
                        tasks=[{k: t.get(k) for k in fields} for t in values[start:start+limit]],
                        next_offset=start+limit if start+limit < len(values) else None)
        if name == 'get_task':
            return dict(project=a['project'], task=self.client.task(a['project'], a['task_id']))
        if name == 'read_document':
            return self.client.document(a['project'], a['task_id'], kind=a.get('kind', 'task'))
        if self.role=='coordinator':
            if name=='create_task':
                return dict(project=a['project'],task=self.client.create_task(a['project'],**{k:v for k,v in a.items() if k!='project'}))
            if name=='change_task':
                if a['action'] in ('accept','integrate'):
                    t=self.client.task(a['project'],a['task_id']);v=t.get('verification') or {};checks=v.get('checks') or []
                    if not (v.get('passed') and v.get('source_stable') and checks and all(x.get('passed') and x.get('tests',0)>0 and x.get('skips')==0 for x in checks)):
                        raise APIError(409,dict(error='需要真实独立复验通过、零skip且源码稳定；不能用交付报告替代验收'))
                return dict(project=a['project'],task=self.client.manage_task(a['project'],a['task_id'],rev=a['rev'],action=a['action'],note=a['note']))
            if name=='queue_verification':
                return dict(project=a['project'],job=self.client.queue_verification(a['project'],a['task_id'],rev=a['rev']))
            if name=='list_jobs':
                jobs=self.client.jobs(a['project']);fields=('id','task_id','kind','provider','status','created','updated')
                return dict(project=a['project'],jobs=[{k:j[k] for k in fields}|{'summary':j.get('data',{}).get('summary','')} for j in jobs if not a.get('task_id') or j['task_id']==a['task_id']])
            if name=='read_job_log':
                return dict(project=a['project'],**self.client.job_log(a['project'],a['job_id']))
        if a['task_id'].split(':', 1)[0] != self.owner:
            raise APIError(409, dict(error='只能变更当前客户端负责人'+self.owner+'的任务'))
        method = {'claim_task': self.client.claim_task, 'release_task': self.client.release_task,
                  'submit_task': self.client.submit_task}[name]
        extra = {'report': a['report']} if 'report' in a else {}
        task = method(a['project'], a['task_id'], rev=a['rev'], owner=self.owner, agent_id=self.agent_id, **extra)
        return dict(project=a['project'], task=task)

    def handle(self, message):
        ident = None
        try:
            if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or not isinstance(message.get('method'), str):
                raise ProtocolError(-32600, '无效JSON-RPC请求，不支持批量消息')
            ident = message.get('id')
            if 'id' in message and (type(ident) not in (int, str)):
                ident = None
                raise ProtocolError(-32600, 'id必须是整数或字符串')
            method, params = message['method'], message.get('params', {})
            # Never execute a mutating tool sent as a notification.
            if 'id' not in message:
                if method == 'notifications/initialized' and self.initialized:
                    self.ready = True
                return None
            if not isinstance(params, dict):
                raise ProtocolError(-32602, 'params必须是对象')
            if method == 'ping':
                result = {}
            elif method == 'initialize':
                if self.initialized:
                    raise ProtocolError(-32600, '会话已经初始化')
                if not isinstance(params.get('protocolVersion'), str) or not isinstance(params.get('capabilities'), dict) or not isinstance(params.get('clientInfo'), dict):
                    raise ProtocolError(-32602, 'initialize缺少protocolVersion/capabilities/clientInfo')
                self.version = params['protocolVersion'] if params['protocolVersion'] in VERSIONS else VERSIONS[0]
                self.initialized = True
                result = dict(protocolVersion=self.version, capabilities=dict(tools=dict(listChanged=False)),
                              serverInfo=dict(name='coordination-tasks', version='0.1.0'),
                              instructions='owner='+self.owner+'; agent_id='+self.agent_id+'; role='+self.role+'\n'+self.instructions)
            elif not self.ready:
                raise ProtocolError(-32002, '请先initialize并发送notifications/initialized')
            elif method == 'tools/list':
                if set(params) - {'cursor','_meta'} or params.get('cursor'):
                    raise ProtocolError(-32602, '工具列表没有后续分页')
                result = dict(tools=list(self.definitions.values()))
            elif method == 'tools/call':
                if set(params) - {'name', 'arguments', '_meta'} or not isinstance(params.get('name'), str):
                    raise ProtocolError(-32602, '需要工具name和arguments')
                try:
                    value = self.invoke(params['name'], params.get('arguments', {}))
                    result = dict(content=[dict(type='text', text=json.dumps(value, ensure_ascii=False))], isError=False)
                    if self.version == VERSIONS[0]:
                        result['structuredContent'] = value
                except (APIError, URLError, TimeoutError, OSError) as error:
                    status = error.status if isinstance(error, APIError) else None
                    value = dict(error=str(error), status=status,
                                 recovery='重新get_task确认最新rev/领取者后决定；不得盲重试。' if status == 409 else '确认本机coordination服务正在运行；写请求不会自动排队执行。')
                    result = dict(content=[dict(type='text', text=json.dumps(value, ensure_ascii=False))], isError=True)
            else:
                raise ProtocolError(-32601, '方法不存在')
            return dict(jsonrpc='2.0', id=ident, result=result)
        except ProtocolError as error:
            return dict(jsonrpc='2.0', id=ident, error=dict(code=error.code, message=error.message))


def serve(owner, base_url='http://127.0.0.1:8765', agent_id=None, *, role='worker', stdin=None, stdout=None):
    app = TaskMCP(CoordinationClient(base_url), owner, agent_id, role)
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout.buffer
    while True:
        line = incoming.readline(MAX_MESSAGE + 1)
        if not line:
            break
        if len(line) > MAX_MESSAGE:
            while line and not line.endswith(b'\n'):
                line = incoming.readline(MAX_MESSAGE + 1)
            reply = dict(jsonrpc='2.0', id=None, error=dict(code=-32700, message='消息超过1MiB'))
        else:
            try:
                def reject_constant(value):
                    raise ValueError('无效JSON常量')
                message = json.loads(line.decode('utf-8'), parse_constant=reject_constant)
                reply = app.handle(message)
            except (ValueError, UnicodeError, RecursionError):
                reply = dict(jsonrpc='2.0', id=None, error=dict(code=-32700, message='需要UTF-8 JSON消息'))
        if reply is not None:
            outgoing.write((json.dumps(reply, ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8'))
            outgoing.flush()
    return 0
