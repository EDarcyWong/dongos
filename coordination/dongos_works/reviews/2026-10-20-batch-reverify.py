import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

WORKS=Path(__file__).resolve().parents[1]
OUT=WORKS/'reviews/2026-10-20-batch-reverify'
OUT.mkdir(exist_ok=True)
SPECS={
 'GUEST1':('pool-works',['test_guest_source_path.py'],['lang/bootstrap/guest_source_path.dg','lang/bootstrap/guest_source_path.md']),
 'GUEST2':('pool-works',['test_guest_source_reader.py'],['lang/bootstrap/guest_source_reader.dg','lang/bootstrap/guest_source_reader.md']),
 'GUEST3':('pool-works',['test_guest_compile_memory.py'],['lang/bootstrap/guest_compile_memory.dg','lang/bootstrap/guest_compile_memory.md']),
 'MCPPOOL1':('pool-works',['test_mcp_pool.py','test_mcp_pool_config.py'],['mcp-pool/dongos_coordination/mcp_server.py','mcp-pool/dongos_coordination/mcp_config.py','mcp-pool/dongos_coordination/docs/MCP.md','mcp-pool/README.md']),
 'CR40':('cursor-works',['test_nasm_pair_cleanup_function.py'],['src/bootstrap/nasm_pair_cleanup_function.dg','src/bootstrap/nasm_pair_cleanup_function.md'])}

def digest(paths):
 return {str(p.relative_to(WORKS)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def verify(number):
 owner,patterns,files=SPECS[number]
 paths=[WORKS/owner/f for f in files]+[WORKS/owner/'tests'/f for f in patterns]+[WORKS/owner/'deliveries'/(number+'.md')]
 before=digest(paths);checks=[]
 for pattern in patterns:
  argv=[sys.executable,'-m','unittest','discover','-s',owner+'/tests','-p',pattern,'-v']
  start=time.monotonic()
  with (OUT/(number+'-'+pattern+'.log')).open('w',encoding='utf-8') as log:
   run=subprocess.run(argv,cwd=WORKS,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
  text=(OUT/(number+'-'+pattern+'.log')).read_text(encoding='utf-8')
  counts=re.findall(r'Ran (\d+) tests?',text);skips=re.findall(r'skipped=(\d+)',text)
  checks.append(dict(command=argv,returncode=run.returncode,tests=int(counts[-1]) if counts else 0,skips=sum(map(int,skips)),elapsed_seconds=round(time.monotonic()-start,3)))
 after=digest(paths)
 result=dict(task=number,checks=checks,before=before,after=after,source_stable=before==after,passed=before==after and all(c['returncode']==0 and c['tests']>0 and c['skips']==0 for c in checks),formal_registration=False)
 (OUT/(number+'.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:result[k] for k in ('task','checks','source_stable','passed')}),flush=True)
 return result

if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  futures={pool.submit(verify,n):n for n in SPECS}
  for future in concurrent.futures.as_completed(futures):
   try:future.result()
   except Exception as error:print(json.dumps(dict(task=futures[future],error=str(error))),flush=True)
