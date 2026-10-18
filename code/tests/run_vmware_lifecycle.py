#!/usr/bin/env python3
"""Actual VMware PCID/process gate, retaining two-boot independent FAT evidence.

Default only prepares the private dual-SATA profile. --execute uses the
existing bounded UART tee and own-VM cleanup. No builds, guest memory reads,
Tools installation, physical disks or fallback-PCID acceptance occur here.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import sys
import time
sys.path.insert(0,str(Path(__file__).absolute().parents[1]))
from tests import run_vmware_storage as storage

check=storage.check
HERE=Path(__file__).absolute().parent
MAX=(1<<64)-1
NAMES=('shell','fs','block','compositor','input','init','devmgr','echo','fault','waiter','ipc-peer','fs-reader','file-app','xhci','terminal','files','editor','settings')
PROMPT=b'\r\n> '


def frame(raw,start,command):
    """Return output only after one fresh complete line of command echo."""
    check(0<=start<=len(raw),'UART cursor escaped captured bytes')
    segment=raw[start:];echo=command+b'\r\n'
    echoes=list(re.finditer(rb'(?:\A|(?<=\n))'+re.escape(echo),segment))
    if not echoes:return None
    first=echoes[0];end=segment.find(PROMPT,first.end())
    if end<0:return None
    check(len([item for item in echoes if item.start()<end])==1,'duplicate fresh command echo')
    check(PROMPT not in segment[:first.start()],'prompt preceded the new complete command echo')
    return segment[first.end():end],start+end+len(PROMPT)


def exchange(session,command,delay,*,clock=time.monotonic,sleep=time.sleep):
    check(re.fullmatch(rb'[\x20-\x7e]{1,240}',command) is not None,'command is not bounded printable ASCII')
    start=len(session.snapshot());session.send(command+b'\r',delay)
    raw=storage.wait_for(session,lambda value:frame(value,start,command) is not None,clock=clock,sleep=sleep)
    body,end=frame(raw,start,command);segment=raw[start:end]
    return body,dict(command=command.decode('ascii'),rx_start=start,rx_end=end,
      rx_sha256=hashlib.sha256(segment).hexdigest(),response_hex=body.hex(),
      response_sha256=hashlib.sha256(body).hexdigest(),fresh_complete_echo_and_prompt=True)


def fields(body,pattern,label):
    matches=re.findall(rb'^'+pattern+rb'\r?$',body,re.M)
    check(len(matches)==1,'one fresh literal '+label+' response is required')
    values=tuple(map(int,matches[0]));check(all(0<=value<=MAX for value in values),label+' field exceeds u64')
    return values


def process_record(body,label,name=None):
    prefix=re.escape((label+(' '+name if name else '')).encode('ascii'))
    token,generation,state,status=fields(body,prefix+rb' token=([0-9]+) generation=([0-9]+) state=([0-9]+) status=([0-9]+)',label)
    check(1<=token&255<=16 and 0<token>>8<=0xfffffff and state<=5,'process token/state violates the admitted ABI')
    return dict(token=token,generation=generation,state=state,status=status)


def processes(body):
    rows=re.findall(rb'^PROCESS ([a-z-]+) id=([0-9]+) token=([0-9]+) generation=([0-9]+) state=([0-9]+) status=([0-9]+)\r?$',body,re.M)
    check(len(rows)==len(NAMES),'ps requires all eighteen admitted configurations')
    result=[]
    for index,(name,identifier,token,generation,state,status) in enumerate(rows):
        check(name.decode('ascii')==NAMES[index] and int(identifier)==index,'ps configuration ordering differs')
        values=tuple(map(int,(token,generation,state,status)))
        check(all(value<=MAX for value in values) and values[2]<=5,'ps field exceeds its ABI')
        if values[0]:
            check(1<=values[0]&255<=16 and 0<values[0]>>8<=0xfffffff and values[1]>0
                  and values[2] in (1,2),'ps live token is invalid or has a terminal state')
        else:check(values[2] in (0,3,4,5),'ps READY/STARTING row has no live token')
        result.append(dict(name=NAMES[index],id=index,token=values[0],generation=values[1],state=values[2],status=values[3]))
    live=[row['token'] for row in result if row['token']]
    check(len({token&255 for token in live})==len(live),'ps aliases multiple processes to one physical slot')
    check(all(row['state']==2 and row['status']==0 and row['token'] and row['generation'] for row in result[:7]),
          'all seven essential services must remain READY')
    return result


def pcid(body):
    enabled,switches,retained,cr4,root,incarnation=fields(body,
      rb'PCID enabled=([0-9]+) switches=([0-9]+) retained=([0-9]+) cr4=([0-9]+) root=([0-9]+) incarnation=([0-9]+)','PCID')
    check(enabled==1 and cr4&(1<<17) and not cr4&(1<<7),'VMware requires actual CR4.PCIDE=1 and CR4.PGE=0; fallback is not a pass')
    check(0<root<1<<32 and root&4095==0 and incarnation>0 and retained<=switches,'PCID counters/root/incarnation are invalid')
    return dict(enabled=enabled,switches=switches,retained=retained,cr4=cr4,root=root,incarnation=incarnation)


def lifecycle(session,record,delay,*,clock=time.monotonic,sleep=time.sleep):
    evidence=dict(passed=False,physical_pte_inspected=False,commands=[])
    record['lifecycle']=evidence
    def call(command):
        evidence['phase_command']=command
        body,item=exchange(session,command.encode('ascii'),delay,clock=clock,sleep=sleep)
        evidence['commands'].append(item);return body
    def ps():return processes(call('ps'))
    def launched(name,argument=None):
        value=process_record(call('run '+name+(' '+str(argument) if argument is not None else '')),'RUN OK',name)
        check(value['generation']>0 and value['state'] in (1,2) and value['status']==0,'spawn did not return a live admitted generation')
        return value
    def ended(value,state,status):
        outcome=process_record(call('wait '+str(value['token'])),'WAIT OK')
        check(outcome==dict(value,state=state,status=status),'wait did not report this exact process generation and terminal outcome')
        return outcome
    def ready(value):
        for attempt in range(64):
            rows=ps();row=rows[9]
            check(row['token']==value['token'] and row['generation']==value['generation'] and row['status']==0
                  and row['state'] in (1,2),'waiter failed its fixed-VA/BSS checks, disappeared, or changed identity')
            if row['state']==2:return rows
        raise TimeoutError('waiter did not publish READY within 64 complete ps commands')
    def held(value):
        row=ps()[9]
        check((row['token'],row['generation'],row['state'],row['status'])==
              (value['token'],value['generation'],2,0),'waiter failed or stopped while yielding with its fixed-VA probe')
    def killed(value):
        outcome=process_record(call('kill '+str(value['token'])),'KILL OK')
        check(outcome==dict(token=value['token'],generation=0,state=5,status=0),'kill did not acknowledge this exact token')
        return ended(value,5,0)
    before=pcid(call('pcid'));initial=ps()
    check(all(row['token']==0 for row in initial[7:13]),'controlled ordinary programs were already running before the isolated gate')
    gui=initial[14:18]
    gui_running=any(row['token'] for row in gui)
    if record.get('required_gui_clients_ready_observed') or gui_running:
        check(all(row['token'] and row['state']==2 and row['status']==0 for row in gui),
              'four independent GUI processes must be READY before the lifecycle gate')
    background=initial[13:18]
    echo=launched('echo',17);evidence['nonzero_exit']=ended(echo,3,17)
    first=launched('waiter',781624);ready(first);held(first)
    warm_first=pcid(call('pcid'));held(first);evidence['first_waiter']=dict(first,argument=781624,terminal=killed(first))
    second=launched('waiter',991833)
    check(second['generation']==first['generation']+1 and second['token']&255==first['token']&255
          and second['token']>>8==(first['token']>>8)+1,'waiter reuse did not change generation/incarnation in the same physical slot')
    ready(second);held(second);warm_second=pcid(call('pcid'));held(second)
    evidence['second_waiter']=dict(second,argument=991833,terminal=killed(second))
    fault=launched('fault');evidence['isolated_cpu_fault']=ended(fault,4,6)
    rights_start=len(session.snapshot());reader=launched('fs-reader');evidence['file_rights']=ended(reader,3,0)
    check(session.snapshot()[rights_start:].count(b'DONGOS_APP_FS_RIGHTS_PASS\r\n')==1,
          'fresh successful user file-rights marker was not observed')
    final=ps();after=pcid(call('pcid'))
    check(final[:7]==initial[:7],'ordinary exit/fault/reuse changed an essential service generation')
    check(final[13:18]==background,'ordinary exit/fault/reuse disturbed an independent GUI or USB process')
    for identifier,value,state,status in ((7,echo,3,17),(8,fault,4,6),(9,second,5,0),(11,reader,3,0)):
        row=final[identifier]
        check((row['token'],row['generation'],row['state'],row['status'])==(0,value['generation'],state,status),
              'terminal ps snapshot differs from the independently waited generation')
    observations=[before,warm_first,warm_second,after]
    for earlier,later in zip(observations,observations[1:]):
        check(later['root']==before['root'] and later['incarnation']==before['incarnation'],'shell address-space identity changed')
        check(later['switches']>earlier['switches'] and later['retained']>earlier['retained'],
              'actual PCID switches and retained-tag switches did not both increase')
    evidence.update(passed=True,pcid=observations,initial_processes=initial,final_processes=final,
      waiter_fixed_va_self_check_survived_dispatch_and_reuse=True,actual_cr4_pcide_observed=True,
      background_gui_and_usb_processes_unchanged=True,
      physical_pte_evidence='Not read by VMware UART runner; QEMU lifecycle gate provides independent physical-PTE evidence.')


def probe(args):
    def lifecycle_boot(state,owner,commands,index,payload,timeout,delay,result):
        result['process_lifecycle_gate_requested']=True
        result['process_lifecycle_and_pcid_observed']=False
        observed=storage.boot(state,owner,commands,index,payload,timeout,delay,result,
                              after_commands=lambda session,record:lifecycle(session,record,delay))
        result['process_lifecycle_and_pcid_observed']=len(result['boots'])==2 and all(item.get('lifecycle',{}).get('passed') for item in result['boots'])
        return observed
    return storage.probe(args,boot_runner=lifecycle_boot,extra_inputs=(Path(__file__),
      HERE/'test_vmware_lifecycle.py',storage.ROOT/'services/apps/waiter.dg',storage.ROOT/'services/apps/echo.dg',
      storage.ROOT/'services/apps/fault.dg',storage.ROOT/'services/apps/fs_reader.dg'))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path);parser.add_argument('--reuse-esp','--esp',dest='reuse_esp',type=Path)
    parser.add_argument('--vmrun',type=Path,default=storage.base.DEFAULT_VMRUN)
    parser.add_argument('--timeout',type=float,default=120);parser.add_argument('--char-delay',type=float,default=.003)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--live',action='store_true')
    parser.add_argument('--require-client-ready',action='store_true',help='wait for four independent GUI first presentations before UART input')
    parser.add_argument('--selftest',action='store_true');args=parser.parse_args(argv)
    if args.selftest:
        check(not args.execute,'selftest cannot execute VMs')
        from tests import test_vmware_lifecycle
        return test_vmware_lifecycle.run()
    if args.image is None or args.reuse_esp is None:parser.error('--image and --reuse-esp are required; no auto-build exists')
    if not 5<=args.timeout<=300 or not .001<=args.char_delay<=.05:parser.error('timeout/char-delay out of bounded range')
    return probe(args)


if __name__=='__main__':raise SystemExit(main())
