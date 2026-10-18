"""Independently match actual taskbar pixels to captured window/focus state."""
from pathlib import Path
import argparse,hashlib,json,struct
from PIL import Image

def check(matrix_path:Path):
    matrix=json.loads(matrix_path.read_text());assert matrix['passed'] and matrix['runner_unchanged']
    checks=[]
    for run in matrix['runs']:
        path=Path(run['result']);r=json.loads(path.read_text());directory=path.parent
        assert r['passed'] and r['p7_60fps_accepted'] and r['source_unchanged']
        chunks=json.loads((directory/'physical-manifest.json').read_text());q=r['scale_percent']*256//100
        px=lambda n:(n*q+128)//256
        for label in ('before-controls','window-hidden','window-restored'):
            pieces=[(directory/c['file']).read_bytes() for c in chunks if c['role']=='actual compositor window state '+label]
            raw=b''.join(pieces)[-3128:];assert len(raw)==3128
            focus=struct.unpack_from('<Q',raw,2440)[0];focused=(focus&255)-1 if focus else -1
            picture=Image.open(directory/(label+'.png')).convert('RGB')
            for index in range(4):
                point=(px(195)+index*px(100)+px(5),picture.height-px(40))
                expected=(0x35,0x55,0x8c) if index==focused else (0x24,0x2b,0x3b)
                assert picture.getpixel(point)==expected,(run['scale'],label,index,point)
            checks.append(dict(scale=run['scale'],tablet=run['tablet'],image=label,focus=focused,exact_pixels=4))
    return dict(passed=True,checks=checks,total_exact_pixels=len(checks)*4,
                checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                matrix_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('matrix',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=check(a.matrix);a.output.write_text(json.dumps(result,indent=2)+'\n');print('Taskbar pixel verification PASS',result['total_exact_pixels'])
if __name__=='__main__':main()
