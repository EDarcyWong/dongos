"""Strict serial/physical-report decoding for the staged actual AP gate."""
import re,struct
FIELDS=('version phase error_code cpus domain probes count tsc_hz quantum_ns started initial_done migrated_done idle_start idle_end '
        'wake_start wake_end completed restart_token restart_bottom restart_top restart_xstate restart_frame').split()
ARRAYS16='rates timer_events ipi_events initial_ticks initial_switches idle_ticks idle_end_ticks wake_ticks wake_end_ticks'.split()
ARRAYS32='initial_masks migrated_masks iterations errors stack_bottom stack_top xstate final_frame retired_token'.split()
BYTES=(len(FIELDS)+len(ARRAYS16)*16+len(ARRAYS32)*32)*8
START=b'DONGOS_P6_PARALLEL_START\r\n';READY=b'DONGOS_P6_PARALLEL_READY\r\n'
def parse(serial):
 if serial.count(START)!=1 or serial.count(READY)!=1 or b'DONGOS_P6_PARALLEL_ERROR='in serial:raise ValueError('missing/duplicate/failed actual parallel gate')
 a=serial.index(START);b=serial.index(READY,a)+len(READY)
 pairs=re.findall(rb'^parallel_([a-z_]+)=0x([0-9a-f]{16})\r$',serial[a:b],re.MULTILINE)
 if [n.decode()for n,_ in pairs]!=FIELDS:raise ValueError('parallel serial shape/order differs')
 return {n.decode():int(v,16)for n,v in pairs},serial[:a]+serial[b:]
def decode(raw):
 if len(raw)!=BYTES:raise ValueError('parallel physical Report size differs')
 values=iter(struct.unpack('<'+str(BYTES//8)+'Q',raw));data={n:next(values)for n in FIELDS}
 for names,count in ((ARRAYS16,16),(ARRAYS32,32)):
  for name in names:data[name]=[next(values)for _ in range(count)]
 return data
def validate(data,count=4):
 d=data
 if (d['version'],d['phase'],d['error_code'],d['cpus'],d['count'],d['quantum_ns'])!=(1,6,0,count,(count-1)*2,1000000):raise ValueError('parallel actual gate incomplete')
 if not d['domain']or d['domain']%64 or not d['probes']or d['probes']%64:raise ValueError('parallel owned metadata pointer absent')
 if not 1000000<=d['tsc_hz']<=16000000000:raise ValueError('parallel TSC reference differs')
 timeline=[d[n]for n in 'started initial_done migrated_done idle_start idle_end wake_start wake_end completed'.split()]
 if not all(a<b for a,b in zip(timeline,timeline[1:])):raise ValueError('parallel phases have no real elapsed interval')
 if d['idle_end']-d['idle_start']<d['tsc_hz']//20 or d['wake_end']-d['wake_start']<d['tsc_hz']//100:raise ValueError('idle/single-thread tickless interval too short')
 mask=(1<<count)-2;workers=(count-1)*2
 for cpu in range(1,count):
  if not 1000<=d['rates'][cpu]<=16000000000 or d['timer_events'][cpu]<3 or d['ipi_events'][cpu]<1 or d['initial_ticks'][cpu]<3 or d['initial_switches'][cpu]<3:raise ValueError('actual AP calibration/timer switches absent')
  if d['idle_ticks'][cpu]!=d['idle_end_ticks'][cpu]or d['wake_ticks'][cpu]!=d['wake_end_ticks'][cpu]:raise ValueError('unneeded local timer/IPI still wakes idle/uncontended CPU')
 if d['wake_ticks'][1]<=d['idle_end_ticks'][1]:raise ValueError('empty domain was not awakened through a real IPI')
 for i in range(workers):
  if d['initial_masks'][i]!=(1<<(i//2+1))or not d['migrated_masks'][i]or d['migrated_masks'][i]&~mask or d['iterations'][i]<8192 or d['errors'][i]!=0:raise ValueError('actual private worker seed/progress/affinity failed')
  if d['stack_top'][i]-d['stack_bottom'][i]!=16384 or d['stack_bottom'][i]%4096 or not d['stack_bottom'][i]<=d['final_frame'][i]<=d['stack_top'][i]-184 or d['xstate'][i]%64 or not d['retired_token'][i]:raise ValueError('retired actual frame/stack/xstate receipt missing')
 if not any(m&(1<<(count-1))and m&(m-1)for m in d['migrated_masks'][:workers-2]):raise ValueError('no actual cross-CPU worker migration to emptied AP')
 if d['restart_token']==d['retired_token'][0]or d['restart_top']-d['restart_bottom']!=16384 or d['restart_bottom']%4096 or not d['restart_bottom']<=d['restart_frame']<=d['restart_top']-184 or d['restart_xstate']%64:raise ValueError('empty-domain wake did not create a fresh owned frame')
 if d['restart_xstate']!=d['xstate'][0]:raise ValueError('restart xstate did not preserve the owned slot allocation')
 ranges=[(d['stack_bottom'][i],d['stack_top'][i])for i in range(workers)]+[(d['restart_bottom'],d['restart_top'])]
 if any(a<e and c<b for i,(a,b)in enumerate(ranges)for c,e in ranges[i+1:]):raise ValueError('actual thread stacks overlap')
 return dict(cpus=count,ordinary_threads=workers,actual_timer_preemptions=True,cross_cpu_migration=True,idle_and_uncontended_tickless=True,ipi_restart_new_generation=True)
def supervisor_leaf(root, virtual, read_page):
    """Verify effective arena access; intermediate U/S bits alone grant none."""
    from tests.run_fat_paths_qemu import effective_mapping
    result = effective_mapping(root, virtual, read_page, (root, 128), 128)
    if not result['present']:
        return result['path'][-1]['entry']
    if (result['leaf_bytes'] != 4096 or result['effective_user']
            or not result['effective_writable'] or not result['effective_nx']
            or result['leaf_entry'] & 0x800000000000019f != 0x8000000000000003):
        raise ValueError('arena mapping is not effective supervisor WB/RW/NX 4KiB RAM')
    return result['leaf_entry']

