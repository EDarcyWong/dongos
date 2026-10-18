"""Initial reproducible L2 native benchmarks against hand-written NASM.

This fixed corpus does not assert that all planned critical benchmarks exist.
No OS/VM build, downloads, priority changes or result selection are performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT)not in sys.path:sys.path.insert(0,str(ROOT))
from lang.dongc import compile_file
from lang.tests.test_dongc import tool,nasm_flags

THRESHOLD=1.20
NAMES=("sum","lcg","mix","array_sum","array_copy")
SYMBOLS={name:"dong_"+name for name in NAMES}

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations",type=int,default=2000000)
    parser.add_argument("--memory-words",type=int,default=65536)
    parser.add_argument("--repeats",type=int,default=32)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--measurement-context",choices=("diagnostic","quiescent"),default="diagnostic",help="quiescent requires the operator to stop concurrent builds/tests first")
    parser.add_argument("--check",action="store_true",help="exit nonzero if any fixed benchmark exceeds 1.20")
    args=parser.parse_args(argv)
    if not 1<=args.iterations<=100000000 or not 1<=args.memory_words<=1048576 or not 1<=args.repeats<=1024:parser.error("workload outside explicit bounded limits")
    output=(args.output or ROOT/"build/benchmarks"/("run-"+uuid.uuid4().hex[:12])).resolve()
    if output.exists():parser.error("output must be a fresh directory; prior evidence is never replaced")
    output.mkdir(parents=True)
    sources=sorted((ROOT/"lang/dongc").glob("*.py"))+[ROOT/"lang/benchmarks"/name for name in ("kernels.dg","reference.asm","harness.c")]+[Path(__file__).resolve()]
    before={str(path.relative_to(ROOT)).replace("\\","/"):digest(path)for path in sources}
    for path in sources:
        archived=output/"sources"/path.relative_to(ROOT)
        archived.parent.mkdir(parents=True,exist_ok=True)
        archived.write_bytes(path.read_bytes())
        if digest(archived)!=before[str(path.relative_to(ROOT)).replace("\\","/")]:raise RuntimeError("source changed during snapshot: "+str(path))
    nasm,cc=tool("nasm","NASM"),tool("gcc","CC")
    report={"kind":"initial-L2-native-benchmarks","passed":False,"threshold":THRESHOLD,"metric":"median Dong nanoseconds / median reference nanoseconds (all nine paired samples)","measurement_context":args.measurement_context,"quiescence_operator_asserted":args.measurement_context=="quiescent","samples":9,"warmups":2,"iterations":args.iterations,"memory_words":args.memory_words,"repeats":args.repeats,"seed":"0x18d46c3b950a27fe","source_sha256":before,"host":{"system":platform.platform(),"machine":platform.machine(),"processor":platform.processor()},"all_planned_critical_benchmarks_complete":False,"OS_VM_built":False}
    def command(command,label):
        result=subprocess.run([str(item)for item in command],capture_output=True,text=True,timeout=180)
        (output/(label+".stdout")).write_text(result.stdout,encoding="utf-8")
        (output/(label+".stderr")).write_text(result.stderr,encoding="utf-8")
        with(output/"commands.jsonl").open("a",encoding="utf-8")as stream:stream.write(json.dumps({"command":[str(item)for item in command],"returncode":result.returncode})+"\n")
        if result.returncode:raise RuntimeError(label+" returned "+str(result.returncode)+": "+result.stderr[-2000:])
        return result.stdout
    try:
        if not nasm or not cc:raise RuntimeError("NASM and GCC are required for actual native benchmarking")
        report["tools"]={"nasm":nasm,"gcc":cc,"nasm_version":command([nasm,"-v"],"nasm-version").strip(),"gcc_version":command([cc,"--version"],"gcc-version").strip()}
        compiled=compile_file(ROOT/"lang/benchmarks/kernels.dg",roots=[ROOT/"lang/benchmarks"],mode="release",optimize=1)
        (output/"kernels.asm").write_text(compiled.assembly,encoding="utf-8")
        (output/"compiler-manifest.json").write_text(json.dumps(compiled.manifest(),indent=2)+"\n",encoding="utf-8")
        (output/"optimization.json").write_text(json.dumps(compiled.optimization,indent=2)+"\n",encoding="utf-8")
        report["backend"]={record["symbol"]:{"backend":record["backend"],"reason":record.get("reason")}for record in compiled.optimization["functions"]}
        native_format="win64"if os.name=="nt"else"elf64"
        objects=[]
        for fmt in ("elf64","win64"):
            for name,assembly in (("kernels",output/"kernels.asm"),("reference",ROOT/"lang/benchmarks/reference.asm")):
                obj=output/(name+"-"+fmt+".o")
                command([nasm,"-f",fmt,*nasm_flags(nasm),str(assembly),"-o",obj],name+"-"+fmt)
                if fmt==native_format:objects.append(obj)
        executable=output/("benchmark.exe"if os.name=="nt"else"benchmark")
        command([cc,"-std=c11","-O2","-Wall","-Wextra","-Werror",*([]if os.name=="nt"else["-no-pie"]),ROOT/"lang/benchmarks/harness.c",*objects,"-o",executable],"native-link")
        raw=command([executable,str(args.iterations),str(args.memory_words),str(args.repeats)],"native")
        samples={name:{"dong":[],"reference":[]}for name in NAMES};correct={};frequency=None
        for line in raw.splitlines():
            fields=line.split("\t")
            if fields[0]=="clock_frequency":frequency=int(fields[1],16)
            elif fields[0]=="correct":correct.setdefault(fields[1],[]).append(int(fields[2],16))
            elif fields[0]=="sample":
                _,sample,name,backend,order,ticks,ns,checksum=fields
                samples[name][backend].append({"sample":int(sample),"order":int(order),"ticks":int(ticks,16),"nanoseconds":int(ns,16),"checksum":int(checksum,16)})
            else:raise RuntimeError("unrecognized native output: "+line)
        if not frequency or set(correct)!=set(NAMES)or any(len(values)!=2 or values[0]!=values[1]for values in correct.values()):raise RuntimeError("missing independent correctness checks or clock")
        results={}
        for name,values in samples.items():
            if any([item["sample"]for item in values[backend]]!=list(range(9))for backend in("dong","reference")):raise RuntimeError("missing/duplicate sample: "+name)
            if any(values["dong"][i]["checksum"]!=values["reference"][i]["checksum"]or values["dong"][i]["order"]==values["reference"][i]["order"]for i in range(9)):raise RuntimeError("work/checksum/pair order differs")
            if any(item["ticks"]<=0 or item["nanoseconds"]<=0 for backend in("dong","reference")for item in values[backend]):raise RuntimeError("clock resolution too low; every measured sample must have positive duration")
            dong=statistics.median(item["nanoseconds"]for item in values["dong"]);reference=statistics.median(item["nanoseconds"]for item in values["reference"])
            if not dong or not reference:raise RuntimeError("clock resolution too low; no zero-duration sample may pass")
            ratio=dong/reference
            results[name]={"backend":report["backend"][SYMBOLS[name]],"correct_value":correct[name][0],"samples":values,"dong_median_ns":dong,"reference_median_ns":reference,"dong_mad_ns":statistics.median(abs(item["nanoseconds"]-dong)for item in values["dong"]),"reference_mad_ns":statistics.median(abs(item["nanoseconds"]-reference)for item in values["reference"]),"ratio":ratio,"passed":ratio<=THRESHOLD,"paired_ratios":[values["dong"][i]["nanoseconds"]/values["reference"][i]["nanoseconds"]for i in range(9)]}
        after={str(path.relative_to(ROOT)).replace("\\","/"):digest(path)for path in sources}
        if after!=before:raise RuntimeError("compiler or benchmark sources changed during run; preserve and repeat")
        report.update({"clock_frequency":frequency,"correctness_passed":True,"results":results,"passed":all(item["passed"]for item in results.values())})
    except Exception as error:
        report["error"]=str(error)
    finally:
        report["artifact_sha256"]={str(path.relative_to(output)).replace("\\","/"):digest(path)for path in output.rglob("*")if path.is_file()and path.name!="result.json"}
        (output/"result.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(str(output/"result.json"))
    for name,result in report.get("results",{}).items():print(f"{name}: {result['ratio']:.3f}x ({result['backend']['backend']}), {'PASS' if result['passed'] else 'OVER 1.20'}")
    if"error"in report:print(report["error"],file=sys.stderr);return 2
    return 1 if args.check and not report["passed"]else 0

if __name__=="__main__":raise SystemExit(main())
