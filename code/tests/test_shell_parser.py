"""Actual Dong UTF-8 shell parser with independently generated token vectors."""
from __future__ import annotations
import hashlib,json,os,random,re,shutil,struct,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import nasm_flags,tool
from tests.test_fat32 import stack_bound
ROOT=Path(__file__).resolve().parents[1]
FILES=[ROOT/p for p in ('services/shell/parser.dg','tests/shell_parser_probe.dg','tests/shell_parser_probe.c','tests/test_shell_parser.py')]
SYNTAX=0x050d0001;LONG=0x050d0002;UTF8=0x050d0003

def quote(s):
    return '"'+s.replace('\\','\\\\').replace('"','\\"')+'"'

def vectors():
    rows=[]
    def add(line,tokens=(),error=0):
        if isinstance(line,str):line=line.encode()
        parts=[t.encode() if isinstance(t,str) else t for t in tokens]
        rows.append((line,error,parts))
    add('');add('  \t ');add('help',('help',));add('pwd ',('pwd',));add('cat README.TXT',('cat','README.TXT'))
    add('write "文档 😀/报告.txt" hello  世界\\nnext',('write','文档 😀/报告.txt','hello  世界\\nnext'))
    add("cat single'quote",('cat',"single'quote"))
    add('write path ""',('write','path','""'));add('touch ""',('touch',''))
    add('cat before\\space',('cat','before\\space'));add('cat a" b"c',('cat','a bc'))
    add('  write\t"a"\t x   ',('write','a','x   '))
    add('cat \\n',('cat','\\n'));add('write n \\t\\r\\n',('write','n','\\t\\r\\n'))
    add('write path "unclosed body',('write','path','"unclosed body'))
    for line in ('cat "unfinished','cat "trailing\\','cat "bad\\n"','"quotedverb" x','12345678901234567'):
        add(line,error=SYNTAX)
    for line in (b'cat \xc0\xaf',b'cat \xed\xa0\x80',b'cat \xf4\x90\x80\x80',b'cat \x80',b'cat \xe2\x82',b'cat \xff'):
        add(line,error=UTF8)
    for line in (b'cat \x00',b'cat \x1b',b'cat \x7f',b'cat \n'):
        add(line,error=SYNTAX)
    add('write p '+'x'*(8192-8),('write','p','x'*(8192-8)))
    add('x'*8193,error=LONG)
    rng=random.Random(0x5348454c4c)
    chars='abcXYZ09 /_-.中界报告😀λé~\'"\\'
    for n in range(3000):
        verb=rng.choice(('write','append','cat','touch','mkdir','rm','cd','truncate'))
        name=''.join(rng.choice(chars) for _ in range(rng.randrange(1,90)))
        if verb in ('write','append'):
            body=''.join(rng.choice(chars) for _ in range(rng.randrange(1,180)))
            if body[0] in ' \t':body='x'+body
            add(verb+' '+quote(name)+' '+body,(verb,name,body))
        else:add(verb+' '+quote(name),(verb,name))
    return rows

class ShellParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'build/test/shell-parser'/('run-'+uuid.uuid4().hex[:12]);cls.out.mkdir(parents=True)
        cls.before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES};cls.results=[]
        cls.data=cls.out/'vectors.bin'
        with cls.data.open('wb') as f:
            cls.count=0
            for line,error,parts in vectors():
                lengths=[len(v) for v in parts]+[0]*3
                f.write(struct.pack('<6Q',len(line),error,len(parts),*lengths[:3]));f.write(line);f.write(b''.join(parts));cls.count+=1
    @classmethod
    def tearDownClass(cls):
        after={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES}
        (cls.out/'validation-summary.json').write_text(json.dumps(dict(before=cls.before,after=after,source_unchanged=after==cls.before,vectors=cls.count,results=cls.results,actual_guest=False),indent=2)+'\n')
        if after!=cls.before:raise AssertionError('parser changed while testing')
    def command(self,args,d,label):
        r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=60)
        (d/(label+'.json')).write_text(json.dumps(dict(args=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n');return r
    def run_mode(self,mode,bad=False):
        d=self.out/(mode+('-bad-utf8' if bad else ''));d.mkdir();services=ROOT/'services'
        if bad:
            services=d/'services';(services/'shell').mkdir(parents=True)
            p=services/'shell/parser.dg';s=(ROOT/'services/shell/parser.dg').read_text(encoding='utf-8');needle='try utf8(line);';self.assertEqual(1,s.count(needle));p.write_text(s.replace(needle,'if false{try utf8(line);}'),encoding='utf-8')
        c=compile_file(ROOT/'tests/shell_parser_probe.dg',roots=[ROOT/'tests',services],mode=mode)
        frame=max(map(int,re.findall(r'sub rsp, ([0-9]+)',c.assembly)));bound=stack_bound(c.assembly)
        self.assertLessEqual(bound,4096);self.assertLessEqual(frame,2048)
        asm=d/'parser.asm';asm.write_text(c.assembly);nasm,gcc=tool('nasm','NASM'),tool('gcc','CC');self.assertTrue(nasm and gcc)
        for fmt in ('elf64','win64'):
            r=self.command([nasm,'-f',fmt,*nasm_flags(nasm),'-o',str(d/(fmt+'.o')),str(asm)],d,'assemble-'+fmt);self.assertEqual(0,r.returncode,r.stderr)
        exe=d/('probe.exe' if os.name=='nt' else 'probe');flags=[] if os.name=='nt' else ['-no-pie']
        r=self.command([gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-D__USE_MINGW_ANSI_STDIO=1',*flags,str(ROOT/'tests/shell_parser_probe.c'),str(d/(('win64' if os.name=='nt' else 'elf64')+'.o')),'-o',str(exe)],d,'link');self.assertEqual(0,r.returncode,r.stderr)
        r=self.command([str(exe),str(self.data)],d,'native');self.assertEqual(1 if bad else 0,r.returncode,r.stdout+r.stderr)
        self.assertIn('shell parser check failed' if bad else 'shell parser checks passed',r.stderr if bad else r.stdout)
        self.results.append(dict(mode=mode,bad_utf8=bad,max_frame=frame,direct_stack=bound,returncode=r.returncode))
    def test_actual_vectors_both_modes_and_formats(self):
        for mode in ('debug','release'):self.run_mode(mode)
    def test_actual_bad_utf8_validator_is_caught(self):
        for mode in ('debug','release'):self.run_mode(mode,True)
