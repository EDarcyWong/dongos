"""Native C14 -> C15 -> C13 -> CR1 data handoffs from the integrated modules."""
import hashlib,json,os,subprocess,unittest,uuid
from pathlib import Path
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags
from lang.tests.test_bootstrap_backend_components import HARNESS

ROOT=Path(__file__).resolve().parents[2]
WRAPPER='''module probe;
import bootstrap.linear_intervals as live;
import bootstrap.register_slots as regs;
import bootstrap.leb128 as leb;
import bootstrap.nasm_bytes as text;
export("backend_components_probe") pub unsafe fn run(out:*u8,cap:usize,written:*usize)u64{unsafe{
 var events:[6]live.Event=[live.Event{value:1,position:7},live.Event{value:0,position:0},
  live.Event{value:2,position:10},live.Event{value:0,position:5},live.Event{value:1,position:5},live.Event{value:2,position:9}];
 var spans:[3]live.Interval=[live.Interval{first:0,last:0};3];var count:usize=0;
 if live.build(slice_from_raw_parts(&events[0],6),3,slice_from_raw_parts(&spans[0],3),&count)!=0{return 101;}
 if count!=3||spans[0].first!=0||spans[0].last!=5||spans[1].first!=5||spans[1].last!=7||spans[2].first!=9||spans[2].last!=10{return 102;}
 var intervals:[3]regs.Interval=[regs.Interval{start:0,end:0};3];var i:usize=0;
 while i<3{intervals[i]=regs.Interval{start:spans[i].first,end:spans[i].last};i+=1;}
 var places:[3]regs.Location=[regs.Location{kind:0,index:0};3];var result=regs.Result{used:0,spill_slots:0};
 if regs.assign(slice_from_raw_parts(&intervals[0],3),1,slice_from_raw_parts(&places[0],3),&result)!=0{return 103;}
 if result.used!=3||result.spill_slots!=1||places[0].kind!=0||places[1].kind!=1||places[1].index!=0||places[2].kind!=0{return 104;}
 var payload:[4]u8=[0;4];var a:usize=0;var b:usize=0;
 if leb.unsigned(result.spill_slots*128+result.used,slice_from_raw_parts(&payload[0],2),&a)!=0{return 105;}
 if leb.signed(-((spans[0].last as i64)+60),slice_from_raw_parts(&payload[2],2),&b)!=0{return 106;}
 if a!=2||b!=2{return 107;}
 return text.encode(slice_from_raw_parts(&payload[0],4),slice_from_raw_parts(out,cap),written);
}}
'''


class IntervalEncodingIntegrationTests(unittest.TestCase):
    def test_native_interval_register_leb_and_nasm_handoffs(self):
        nasm,cc=tool('nasm','NASM'),tool('gcc','CC')
        if not nasm or not cc:self.skipTest('native interval integration requires NASM/GCC')
        work=ROOT/'build/test/bootstrap-components/interval-encoding'/('run-'+uuid.uuid4().hex[:12]);work.mkdir(parents=True)
        (work/'probe.dg').write_text(WRAPPER,encoding='utf-8');(work/'probe.c').write_text(HARNESS,encoding='utf-8')
        names=('linear_intervals','register_slots','leb128','nasm_bytes')
        hashes={n:hashlib.sha256((ROOT/f'lang/bootstrap/{n}.dg').read_bytes()).hexdigest() for n in names}
        records=[]
        def run(argv,label):
            r=subprocess.run(list(map(str,argv)),capture_output=True,timeout=120)
            (work/(label+'.log')).write_bytes(r.stdout+r.stderr)
            self.assertEqual(r.returncode,0,(label,r.stdout,r.stderr));return r.stdout
        for mode in ('debug','release'):
            asm=work/(mode+'.asm');asm.write_text(compile_file(work/'probe.dg',roots=[ROOT/'lang',work],mode=mode).assembly,encoding='utf-8')
            native='win64' if os.name=='nt' else 'elf64'
            for fmt in ('elf64','win64'):run([nasm,'-f',fmt,*nasm_flags(nasm),'-o',work/(mode+'.'+fmt+'.o'),asm],mode+'-'+fmt)
            exe=work/(mode+('.exe' if os.name=='nt' else ''))
            run([cc,'-std=c11','-O2','-Wall','-Wextra','-Werror',work/'probe.c',work/(mode+'.'+native+'.o'),'-o',exe],mode+'-link')
            output=run([exe],mode+'-native');self.assertEqual(output,b'db 0x83,0x01,0xBF,0x7F\n')
            source=work/(mode+'-data.asm');source.write_bytes(output);binary=work/(mode+'-data.bin')
            run([nasm,'-f','bin','-o',binary,source],mode+'-roundtrip');self.assertEqual(binary.read_bytes(),bytes([0x83,1,0xbf,0x7f]))
            records.append(dict(mode=mode,passed=True,native=True,formats=['elf64','win64'],nasm_roundtrip=True))
        self.assertEqual(hashes,{n:hashlib.sha256((ROOT/f'lang/bootstrap/{n}.dg').read_bytes()).hexdigest() for n in names})
        (work/'summary.json').write_text(json.dumps(dict(passed=True,source_sha256=hashes,records=records,L3_selfhost_complete=False),indent=2),encoding='utf-8')


if __name__=='__main__':unittest.main()
