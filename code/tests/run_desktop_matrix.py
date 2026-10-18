"""Serial actual guests for every DPI resource configuration and PS/2 fallback."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys,uuid
from tests.desktop_resource_variant import variant
from tools.build import ROOT

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True);a=p.parse_args()
    out=ROOT/'build/test/p7-extensions'/('matrix-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
    own={str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'tests/desktop_resource_variant.py':hashlib.sha256((ROOT/'tests/desktop_resource_variant.py').read_bytes()).hexdigest()}
    summary=dict(passed=False,base=str(a.base.resolve()),runs=[],runner_inputs=own)
    try:
        for scale,tablet in ((100,True),(200,True),(150,True),(125,True),(175,True),(100,False)):
            label=str(scale)+('-tablet' if tablet else '-ps2')
            esp=variant(a.base,out/label,scale)
            command=[sys.executable,'-m','tests.run_desktop_qemu','--controls','--scale',str(scale),'--reuse-esp',str(esp)]
            if tablet:command+=['--tablet']
            with (out/(label+'.log')).open('w') as stream:
                actual=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
            log=(out/(label+'.log')).read_text();print(label,actual.returncode,log.strip(),flush=True)
            match=re.search(r'P7 actual desktop (?:PASS|FAIL) (.*?run-[a-z0-9]+)',log)
            result_path=Path(match[1])/'result.json' if match else None
            result=json.loads(result_path.read_text()) if result_path else {}
            item=dict(scale=scale,tablet=tablet,returncode=actual.returncode,esp=str(esp),result=str(result_path),
                passed=actual.returncode==0 and result.get('passed') and result.get('p7_60fps_accepted'),
                fps=result.get('drag_performance',{}).get('actual_fps'),maximum_frame_seconds=result.get('drag_performance',{}).get('maximum_frame_seconds'))
            summary['runs'].append(item);(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            if not item['passed']:raise RuntimeError('DPI/transport matrix failed: '+label)
        summary['passed']=True
    except Exception as exc:summary['error']=str(exc)
    finally:
        summary['runner_unchanged']=all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in own.items())
        if not summary['runner_unchanged']:summary['passed']=False
        (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('Desktop matrix',out,flush=True);return 0 if summary['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
