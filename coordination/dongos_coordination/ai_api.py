"""Versioned, explicit-project API for local AI task collaboration."""
from pathlib import Path
from urllib.parse import parse_qs

from .store import OWNERS, STATES, digest

GUIDE = Path(__file__).with_name('docs')/'AI_API.md'
MCP_GUIDE = Path(__file__).with_name('docs')/'MCP.md'


class NotFound(ValueError):
    pass


def discovery(base):
    return dict(name='Coordination AI Task API',version='1',base_url=base,
        guide=base+'/api/ai/guide',openapi=base+'/api/ai/openapi.json',
        session=base+'/api/session',projects=base+'/api/v1/projects',
        mcp=dict(transport='stdio', guide=base+'/api/mcp/guide', clients=['claude','cursor','lmstudio','deepseek','codex'],
                 automatic_client_execution=False),
        authentication=dict(kind='local_same_origin_csrf',bootstrap='GET /api/session',
            write_headers={'Origin':base,'X-Coordinator-CSRF':'<csrf from session>','Content-Type':'application/json'}),
        operations=['list_projects','list_tasks','get_task','create_task','claim_task','release_task','submit_delivery','read_document'],
        rules=['所有任务请求必须在URL中指定项目','领取/释放/提交必须使用最新rev及owner、agent_id',
               '409后先重新查询，不盲目重试','提交交付只进入submitted，不自动验收','agent_id仅用于协作归属记录，不是独立身份认证'])


def projects(server):
    if server.registry:
        return server.registry.list()
    return [dict(id='default',name=server.store.project_name,source_root=str(server.store.root),works_root=str(server.store.works_root))]


def route(server,path):
    parts=path.strip('/').split('/')
    if len(parts)<4 or parts[:3]!=['api','v1','projects']:
        raise NotFound('API不存在')
    project=parts[3]
    if not any(p['id']==project for p in projects(server)):
        raise NotFound('项目不存在')
    store,_=server.context(project)
    if len(parts)<5 or parts[4]!='tasks':
        raise NotFound('API不存在')
    return project,store,parts[5:]


def task_or_404(store,key):
    try:
        return store.get(key)
    except ValueError as error:
        raise NotFound('任务不存在') from error


def get(server,path,query):
    if path=='/api/v1/projects':
        return dict(projects=projects(server))
    project,store,tail=route(server,path)
    server.scan(store)
    if not tail:
        filters=parse_qs(query)
        if set(filters)-{'owner','status','q'} or any(len(v)!=1 for v in filters.values()):
            raise ValueError('只支持单值owner/status/q查询参数')
        owner,status,search=(filters.get(k,[''])[0] for k in ('owner','status','q'))
        if owner and owner not in OWNERS or status and status not in STATES:
            raise ValueError('owner或status无效')
        tasks=[t for t in store.tasks() if (not owner or t['owner']==owner) and
               (not status or t['status']==status) and (not search or search.casefold() in (t['id']+' '+t['title']).casefold())]
        return dict(project=project,total=len(tasks),tasks=tasks)
    task=task_or_404(store,tail[0])
    if len(tail)==1:
        return dict(project=project,task=task)
    if len(tail)==2 and tail[1]=='document':
        kind=parse_qs(query).get('kind',['task'])[0]
        if kind not in ('task','delivery'):
            raise ValueError('kind只支持task或delivery')
        name=task['document'] if kind=='task' else task['delivery']
        root=store.root if kind=='task' else store.candidate_root(task)
        source=store.path(name,root)
        if not source.is_file():
            raise NotFound('文档尚未生成')
        text=source.read_text(encoding='utf-8-sig')
        return dict(project=project,path=name,text=text[:100000],truncated=len(text)>100000,sha256=digest(source))
    raise NotFound('API不存在')


def post(server,path,data):
    project,store,tail=route(server,path)
    if not tail:
        if set(data)-{'id','owner','title','description','write_paths','checks','depends_on'}:
            raise ValueError('创建任务包含未知字段；不能设置status、rev或验收结果')
        task=store.create(data)
        code=201
    elif len(tail)==2 and tail[1] in ('claim','release','submit'):
        task_or_404(store,tail[0])
        allowed={'rev','owner','agent_id'}|({'report'} if tail[1]=='submit' else set())
        if set(data)-allowed or not {'rev','owner','agent_id'}<=set(data):
            raise ValueError('需要rev、owner、agent_id；只有submit还可带report')
        options=dict(ai_request=True,owner=data['owner'],agent_id=data['agent_id'])
        if 'report' in data:
            options['report']=data['report']
        task=store.change(tail[0],data['rev'],tail[1],options=options)
        code=200
    else:
        raise NotFound('API不存在；AI任务接口不提供自行验收/集成或执行shell的操作')
    store.export()
    return dict(project=project,task=task),code


def openapi(base):
    string={'type':'string'}
    task_create=dict(type='object',additionalProperties=False,required=['id','owner','title','write_paths'],properties={
        'id':dict(type='string',pattern='^[A-Z][A-Z0-9_-]{0,39}$'),
        'owner':dict(type='string',enum=list(OWNERS)), 'title':dict(type='string',minLength=1,maxLength=180),
        'description':dict(type='string',maxLength=24000),
        'write_paths':dict(type='array',minItems=1,maxItems=40,items=string),
        'checks':dict(type='array',maxItems=12,items=string),'depends_on':dict(type='array',maxItems=32,items=string)})
    claim=dict(type='object',additionalProperties=False,required=['rev','owner','agent_id'],properties={
        'rev':dict(type='integer',minimum=1),'owner':dict(type='string',enum=list(OWNERS)),
        'agent_id':dict(type='string',pattern='^[A-Za-z0-9_.:-]{1,80}$')})
    submit=claim|{'properties':claim['properties']|{'report':dict(type='string',minLength=1,maxLength=24000)}}
    paths={}
    def op(method,path,ident,summary,body=None,parameters=None):
        params=list(parameters or [])
        for key in ('project','task_id'):
            if '{'+key+'}' in path:
                params.append(dict(name=key,**{'in':'path'},required=True,schema=string))
        responses={str(201 if ident=='createTask' else 200):dict(description='成功，返回JSON'),
                   '400':dict(description='请求、文件范围、依赖或报告无效'),
                   '403':dict(description='Host/Origin/操作令牌不匹配，最多刷新令牌重试一次'),
                   '404':dict(description='项目/任务/文档/接口不存在'),
                   '409':dict(description='版本、状态、领取人或文件归属冲突；重新查询后决定'),
                   '413':dict(description='请求体超过64KiB'),'415':dict(description='需要application/json')}
        item=dict(operationId=ident,summary=summary,parameters=params,responses=responses)
        if body:
            params.append(dict(name='Origin',**{'in':'header'},required=True,schema=string,example=base))
            item.update(security=[{'CoordinatorCSRF':[]}],requestBody=dict(required=True,content={'application/json':{'schema':body}}))
        paths.setdefault(path,{})[method]=item
    root='/api/v1/projects/{project}/tasks'
    op('get','/api/ai','discoverAIAPI','发现文档、契约和调用约定')
    op('get','/api/session','getSession','获取本地同源操作令牌')
    op('get','/api/v1/projects','listProjects','查看可用项目')
    op('get',root,'listTasks','按项目、负责人、状态或关键词查看任务',parameters=[dict(name=k,**{'in':'query'},schema=string) for k in ('owner','status','q')])
    op('post',root,'createTask','提交/发布一项新任务',task_create)
    op('get',root+'/{task_id}','getTask','查看任务及最新rev')
    op('get',root+'/{task_id}/document','getTaskDocument','读取任务书或交付',parameters=[dict(name='kind',**{'in':'query'},schema=dict(type='string',enum=['task','delivery']))])
    for action,body in [('claim',claim),('release',claim),('submit',submit)]:
        op('post',root+'/{task_id}/'+action,action+'Task',{'claim':'领取任务','release':'释放已领取任务','submit':'提交交付，等待独立复验'}[action],body)
    return dict(openapi='3.1.0',info=dict(title='Coordination AI Task API',version='1.0.0',description='本地可信协作接口，agent_id用于归属记录，不代表独立安全身份。'),
        servers=[{'url':base}],paths=paths,components=dict(securitySchemes={'CoordinatorCSRF':dict(type='apiKey',**{'in':'header'},name='X-Coordinator-CSRF')}))
