"""Dependency-free client for local AI workers; refreshes stale CSRF once."""
import json
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler


class APIError(RuntimeError):
    def __init__(self,status,body):
        self.status,self.body=status,body
        super().__init__(body.get('error',str(status)))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class CoordinationClient:
    def __init__(self,base_url='http://127.0.0.1:8765',*,timeout=15):
        p=urlsplit(base_url)
        if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost') or p.path not in ('','/') or p.username or p.password or p.query or p.fragment:
            raise ValueError('只支持本机协调服务的http源地址')
        self.base_url=base_url.rstrip('/')
        self.timeout,self.csrf=timeout,None
        self.claims={}
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def _request(self,path,data=None,*,retry=True,project=None):
        headers={} if project is None else {'X-Coordination-Project':project}
        if data is not None:
            if not self.csrf:
                self.csrf=self._request('/api/session')['csrf']
            headers.update({'Origin':self.base_url,'X-Coordinator-CSRF':self.csrf,'Content-Type':'application/json'})
        request=Request(self.base_url+path, data=None if data is None else json.dumps(data,ensure_ascii=False).encode('utf-8'),headers=headers)
        try:
            with self.opener.open(request,timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            body=json.load(error)
            if error.code==403 and data is not None and retry:
                self.csrf=self._request('/api/session')['csrf']
                return self._request(path,data,retry=False,project=project)
            raise APIError(error.code,body) from error

    @staticmethod
    def _root(project):
        return '/api/v1/projects/'+quote(project,safe='')+'/tasks'

    def projects(self):
        return self._request('/api/v1/projects')['projects']

    def tasks(self,project,*,owner='',status='',q=''):
        return self._request(self._root(project)+'?'+urlencode(dict(owner=owner,status=status,q=q)))['tasks']

    def task(self,project,task_id):
        return self._request(self._root(project)+'/'+quote(task_id,safe=''))['task']

    def create_task(self,project,**fields):
        return self._request(self._root(project),fields)['task']

    def _action(self,project,task_id,action,rev,owner,agent_id,**extra):
        key=(project,task_id,agent_id)
        if action!='claim' and 'claim_token' not in extra and key in self.claims:
            extra['claim_token']=self.claims[key]
        result=self._request(self._root(project)+'/'+quote(task_id,safe='')+'/'+action,dict(rev=rev,owner=owner,agent_id=agent_id,**extra))['task']
        if action=='claim':self.claims[key]=result.get('claim_token')
        elif action in ('release','submit'):self.claims.pop(key,None)
        return result

    def claim_task(self,project,task_id,*,rev,owner,agent_id):
        return self._action(project,task_id,'claim',rev,owner,agent_id)

    def release_task(self,project,task_id,*,rev,owner,agent_id,claim_token=None):
        return self._action(project,task_id,'release',rev,owner,agent_id,**({} if claim_token is None else {'claim_token':claim_token}))

    def acknowledge_pause(self,project,task_id,*,rev,owner,agent_id,claim_token=None):
        return self._action(project,task_id,'acknowledge_pause',rev,owner,agent_id,**({} if claim_token is None else {'claim_token':claim_token}))

    def submit_task(self,project,task_id,*,rev,owner,agent_id,report=None,claim_token=None):
        return self._action(project,task_id,'submit',rev,owner,agent_id,**({} if report is None else {'report':report}),**({} if claim_token is None else {'claim_token':claim_token}))

    def document(self,project,task_id,*,kind='task'):
        return self._request(self._root(project)+'/'+quote(task_id,safe='')+'/document?'+urlencode({'kind':kind}))

    def manage_task(self,project,task_id,*,rev,action,note,options=None):
        return self._request('/api/action',dict(task=task_id,rev=rev,action=action,note=note,options=options),project=project)

    def queue_verification(self,project,task_id,*,rev):
        return self._request('/api/queue',dict(task=task_id,rev=rev,kind='verify'),project=project)

    def jobs(self,project):
        return self._request('/api/snapshot',project=project)['jobs']

    def job_log(self,project,job_id):
        return self._request('/api/log/'+quote(job_id,safe=''),project=project)
