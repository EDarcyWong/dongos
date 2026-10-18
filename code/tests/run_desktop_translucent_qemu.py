#!/usr/bin/env python3
"""Actual preference-policy and translucent-divider occlusion regression.

The current preferences contract rejects translucent surfaces. Two correctly
checksummed fixtures must therefore fall back to defaults; the opaque-surface,
half-border fixture must really load. No policy is weakened to make a fixture
load. Stable scenes run without armed breakpoints; DPI middle scenes reuse the
existing immutable-code Z1 publication capture. No build or guest-memory writes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import tempfile
import unittest
import uuid
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests import desktop_preferences_oracle as disk_oracle
from tests import run_services_qemu as storage
from tests.run_desktop_settings_qemu import ROOT,DARK,check,rect,sha,theme_bytes
from tests.run_desktop_transition_qemu import TransitionGuest,full_rect,source_point,over
from tests.run_desktop_transition_perf_qemu import pin_build
from tests.run_desktop_qemu import validate_font_aperture
from tools.make_fat32_disk import create

HALF_SURFACE=0x80252b3b
HALF_BORDER=0x80602010
SEQUENCE=17
CASES=(('half-surface-opaque-border',HALF_SURFACE,DARK[5],False),
       ('opaque-surface-half-border',DARK[1],HALF_BORDER,True),
       ('half-surface-half-border',HALF_SURFACE,HALF_BORDER,False))


def colors_for(surface,border):
    colors=list(DARK);colors[1]=surface;colors[5]=border
    return tuple(colors)


def manual_checksum(raw):
    check(len(raw)==128,'record must be 128 bytes')
    data=bytearray(raw);data[104:112]=bytes(8)
    def adler(values):
        a,b=1,0
        for value in values:
            a=(a+value)%65521;b=(b+a)%65521
        return b<<16|a
    return adler(reversed(data))<<32|adler(data)


def preference_record(colors,sequence=SEQUENCE,scale=256):
    check(len(colors)==9 and 0<sequence<1<<64,'invalid fixture values')
    data=bytearray(128)
    struct.pack_into('<8sIIQQ',data,0,b'DONGPREF',1,128,sequence,0)
    data[32:104]=theme_bytes(colors,scale)
    checksum=(zlib.adler32(data[::-1])&0xffffffff)<<32|(zlib.adler32(data)&0xffffffff)
    struct.pack_into('<Q',data,104,checksum)
    check(manual_checksum(data)==checksum,'independent checksum algorithms disagree')
    return bytes(data)


def record_contract(raw):
    """Distinguish byte/checksum validity from the existing surface policy."""
    check(len(raw)==128 and raw[:8]==b'DONGPREF','fixture envelope invalid')
    check(struct.unpack_from('<II',raw,8)==(1,128),'fixture version/length invalid')
    check(struct.unpack_from('<Q',raw,16)[0]>0 and raw[24:32]==bytes(8)
          and raw[68:72]==bytes(4) and raw[112:]==bytes(16),'fixture canonical fields invalid')
    check(struct.unpack_from('<Q',raw,104)[0]==manual_checksum(raw),'fixture checksum invalid')
    colors=struct.unpack_from('<9I',raw,32)
    check(all(all((color>>shift&255)<=color>>24 for shift in (0,8,16)) for color in colors),
          'fixture color is not premultiplied')
    radius,shadow,scale,duration=struct.unpack_from('<4Q',raw,72)
    check(radius<=32 and shadow<=32 and scale in (256,320,384,448,512) and duration<=1000,
          'fixture theme metric invalid')
    check(colors[0]>>24==255,'fixture background must be opaque')
    accepted=colors[1]>>24==255
    return dict(envelope_and_checksum_valid=True,premultiplied_colors=True,
                accepted_by_current_preferences_policy=accepted,
                rejection_reason=None if accepted else 'surface alpha must equal 255',
                sequence=struct.unpack_from('<Q',raw,16)[0],record_hex=raw.hex(),
                record_sha256=hashlib.sha256(raw).hexdigest())


def seed_new_image(path,record):
    """Only seed the freshly created ordinary test image; no existing disks."""
    path=Path(path)
    check(len(record)==128,'fixture record must have exact128-byte length')
    check(not path.exists() and not path.is_symlink(),'fixture image already exists')
    create(path,64)
    with disk_oracle.Fat32Image(path) as image:
        check(image.root_chain==[2] and image.directory[32:64]==bytes(32),
              'unexpected fresh-image directory layout')
        check(struct.unpack_from('<I',image.fat,16)[0]==0,'fixture cluster4 already allocated')
        g=dict(image.geometry);fat_bytes=len(image.fat)
        root_offset=image.cluster_offset(2);data_offset=image.cluster_offset(4)
        cluster_bytes=image.cluster_bytes
    entry=bytearray(32);entry[:11]=b'DESK0   CFG';entry[11]=0x20
    for offset in (16,18,24):struct.pack_into('<H',entry,offset,0x21)
    struct.pack_into('<H',entry,26,4);struct.pack_into('<I',entry,28,128)
    with path.open('r+b') as stream:
        for mirror in range(2):
            stream.seek(g['reserved_sectors']*512+mirror*fat_bytes+4*4)
            stream.write(struct.pack('<I',0x0fffffff))
        stream.seek(root_offset+32);stream.write(entry)
        stream.seek(data_offset);stream.write(record+bytes(cluster_bytes-len(record)))
        stream.flush()
    with disk_oracle.Fat32Image(path) as image:
        actual,metadata=image.file(b'DESK0   CFG')
        check(actual==record and image.entry(b'DESK1   CFG') is None,'raw seeded preference differs')
        result=dict(record=record_contract(actual),file=metadata,geometry=image.geometry,
                    fat_mirrors_equal=True,clean=image.clean,image_sha256=sha(path))
    return result


def pixel(raw,stride,x,y):
    return struct.unpack_from('<I',raw,(y*stride+x)*4)[0]


def cursor_covers(pointer,scale,x,y):
    dx,dy=x-pointer[0],y-pointer[1]
    return 0<=dy<(17*scale+128)//256 and 0<=dx<=dy//2


def scene_pixel(x,y,background,textures,stride,targets,full,alphas,order,margin,pointer,scale,text_color,
                unsafe_first=None):
    """Exact independent cache source-over; optional OLD unsafe base copy."""
    color=pixel(background,stride,x,y)
    used=[]
    for n,handle in enumerate(order):
        if unsafe_first is not None and n<unsafe_first:continue
        i=(handle&255)-1
        if not alphas[i]:continue
        sw=targets[i][2]-targets[i][0]+2*margin;sh=targets[i][3]-targets[i][1]+2*margin
        uv=source_point(x,y,full[i],sw,sh)
        if uv is None:continue
        source=struct.unpack_from('<I',textures,i*0x200000+(uv[1]*sw+uv[0])*4)[0]
        color=source if unsafe_first==n else over(source,color,alphas[i])
        used.append(dict(window=i,source=list(uv),argb=source,alpha=alphas[i],order=n))
    if cursor_covers(pointer,scale,x,y):color=text_color
    return color,used


def legacy_first(x,y,targets,bodies,alphas,order,inset):
    """Old stable opaque selection for a clip inside one pixel/cursor cell."""
    chosen=None
    for n,handle in enumerate(order):
        i=(handle&255)-1;l,t,r,b=targets[i]
        if alphas[i]==256 and tuple(bodies[i])==tuple(targets[i]) \
                and l+inset<=x<r-inset and t+inset<=y<b-inset:
            chosen=n
    return chosen


class TranslucentGuest(TransitionGuest):
    def __init__(self,*args,**kwargs):
        self.scene_buffers={};self.cursor_damage_witness=None
        super().__init__(*args,**kwargs)

    def ram(self,address,size,role):
        data=super().ram(address,size,role)
        keys={'actual final background cache':'background','actual final four window textures':'textures',
              'actual completed WB back buffer':'back'}
        if role in keys:self.scene_buffers[keys[role]]=data
        return data

    def physical(self,address,size,role):
        data=super().physical(address,size,role)
        if role=='actual completed GOP pixels':self.scene_buffers['gop']=data
        return data

    def verify_scene(self,name,value=None):
        self.scene_buffers={}
        item=super().verify_scene(name,value)
        d=self.descriptor();scale=d[14];margin=(12*scale+128)//256
        win=self.windows();order=list(struct.unpack_from('<16Q',win,2304)[:4])
        pointer=struct.unpack_from('<2q',win,2464);style=self.field('STYLE',72)
        text_color=struct.unpack_from('<I',style,8)[0]
        targets=item['target_rects'];full=item['source_full_rects'];alphas=item['presented_alpha']
        buffers=self.scene_buffers;points=set();sources=[]
        px=lambda value:(value*scale+128)//256
        for i,target in enumerate(targets):
            sw=target[2]-target[0]+2*margin;sh=target[3]-target[1]+2*margin
            sy=margin+px(32);source_height=px(33)-px(32)
            sx=sw//2
            color=struct.unpack_from('<I',buffers['textures'],i*0x200000+(sy*sw+sx)*4)[0]
            sources.append(dict(window=i,width=sw,height=sh,source_x=sx,source_y=sy,
                                alpha=color>>24,argb=color,inside_old_opaque_interior=True))
            l,t,r,b=full[i];tw,th=r-l,b-t
            low=t+(sy*th+sh-1)//sh;high=t+((sy+source_height)*th+sh-1)//sh
            xlow=l+((margin+px(10))*tw+sw-1)//sw
            xhigh=l+((sw-margin-px(10))*tw+sw-1)//sw
            if high>low:
                xs=range(max(0,xlow),min(d[1],xhigh),max(1,(xhigh-xlow)//32))
                points.update((x,y) for y in range(max(0,low),min(d[2],high)) for x in xs)
        if self.cursor_damage_witness:
            points.add(tuple(self.cursor_damage_witness['point']))
        comparisons=[];controls=[]
        for x,y in sorted(points,key=lambda point:(point[1],point[0])):
            arguments=(x,y,buffers['background'],buffers['textures'],d[3],targets,full,alphas,order,
                       margin,pointer,scale,text_color)
            expected,used=scene_pixel(*arguments)
            actual=pixel(buffers['back'],d[3],x,y)
            check(actual==expected,f'{name}: targeted divider WB mismatch at {(x,y)} {actual:08x}!={expected:08x}')
            expected_gop=expected&0xffffff
            if d[4]==0:expected_gop=(expected_gop&255)<<16|(expected_gop&0xff00)|(expected_gop>>16)
            actual_gop=pixel(buffers['gop'],d[3],x,y)&0xffffff
            check(actual_gop==expected_gop,f'{name}: targeted divider GOP mismatch at {(x,y)}')
            comparisons.append(dict(x=x,y=y,actual_back=actual,expected_back=expected,
                                    actual_gop=actual_gop,sources=used))
            first=legacy_first(x,y,targets,item['visual_rects'],alphas,order,px(8))
            if first is not None and not cursor_covers(pointer,scale,x,y):
                wrong,_=scene_pixel(*arguments,unsafe_first=first)
                if (wrong&0xffffff)!=(expected&0xffffff):
                    controls.append(dict(x=x,y=y,legacy_first_order=first,
                        expected_source_over=expected,old_unsafe_skipcenter=wrong,
                        mismatch_rgb=(wrong^expected)&0xffffff,actual_back=actual,
                        independent_counterfactual=True,bad_guest_executed=False))
        item.update(targeted_divider_pixels=len(comparisons),divider_comparisons=comparisons,
            source_divider_pixels=sources,nonopaque_source_dividers=sum(source['alpha']<255 for source in sources),
            old_unsafe_skipcenter_counterexamples=controls,hardware_breakpoints_armed=sorted(self.armed))
        if self.cursor_damage_witness:
            witness=self.cursor_damage_witness
            x,y=witness['point'];left,top,right,bottom=witness['old_cursor_clip']
            check(left<=x<right and top<=y<bottom and not cursor_covers(pointer,scale,x,y),
                  'targeted regression point is not exposed old-cursor damage')
            item['actual_old_cursor_damage_witness']=witness
            check(any(control['x']==x and control['y']==y for control in controls),
                  'old unsafe skipcenter did not differ at the actual divider damage witness')
        storage.write_json(self.state/(name+'.json'),item)
        return item

    def verify_assets(self,name,colors,scale,frames,metadata):
        check(self.stopped,'asset verification requires paused guest')
        d=self.descriptor();style=self.field('STYLE',72)
        check(d[0]==3 and d[14:]==(scale,scale//16) and style==theme_bytes(colors,scale),
              'actual loaded whole Theme/DPI differs')
        atlas=struct.unpack('<9Q',self.field('FONT',72))
        check(atlas[0]==d[8] and atlas[1]==d[9] and atlas[3]==scale//16,'actual selected Atlas differs')
        aperture=validate_font_aperture(self.roots[3],d[8],d[9],self.pte)
        payload=self.physical(self.pte(self.roots[3],d[8])&storage.MASK,d[9],'actual selected translucent-test atlas')
        check(hashlib.sha256(payload).hexdigest()==sha(ROOT/f'assets/fonts/dong-cjk-sc-{scale//16}.dgfont'),
              'actual atlas payload differs')
        for pid in (0,1,2,4):
            for offset in (0,0x400000,0x7ff000):
                check(self.pte(self.roots[pid],d[8]+offset)==0,'font aperture leaked')
        check(self.pte(self.roots[3],0x70001000)&0x800000000000001f==0x8000000000000005,
              'descriptor lost RO/NX/WB')
        check(self.pte(self.roots[4],0x70001000)&~0x60==self.pte(self.roots[3],0x70001000)&~0x60,
              'input descriptor mapping differs')
        check(self.kval('user.memory','FRAME_COUNT')==frames,'DPI/scene allocated user RAM')
        check(self.kernel(self.ksym('user.memory','META'),5*32,'private metadata '+name)==metadata,
              'DPI/scene changed private table META')
        report=dict(name=name,scale_q8=scale,theme_hex=style.hex(),font_aperture=aperture,
                    font_sha256=hashlib.sha256(payload).hexdigest(),held_frames=frames,
                    metadata_sha256=hashlib.sha256(metadata).hexdigest())
        self.evidence.setdefault('translucent_assets',[]).append(report)
        return report


def run(args):
    esp=args.reuse_esp.resolve()
    output=ROOT/'build/test/p7-translucent/qemu'/('run-'+uuid.uuid4().hex[:12]);output.mkdir(parents=True)
    result=dict(passed=False,actual_qemu_boots=0,actual_qemu_start_attempts=0,cases=[],p7_60fps_accepted=False,
        guest_memory_writes=False,stable_scenes_without_armed_breakpoints=True,
        middle_capture='existing Z1 immutable-code publication capture; no timing acceptance',
        surface_preferences_contract='opaque-only, unchanged')
    guest=None;pinned={}
    def unchanged():return bool(pinned) and all(sha(path)==value for path,value in pinned.items())
    try:
        pinned=pin_build(esp)
        for relative in ('tests/run_desktop_translucent_qemu.py','tests/run_desktop_transition_qemu.py',
                         'tests/desktop_preferences_oracle.py','tests/run_desktop_qemu.py'):
            path=ROOT/relative;pinned[str(path)]=sha(path)
        result['pinned_files']=pinned
        description=json.loads((esp.parent/'build-inputs.json').read_text())
        check(description['desktop_scale']==100,'fallback tests require a normal default100 build')
        for name,surface,border,accepted in CASES:
            case_dir=output/name;case_dir.mkdir()
            colors=colors_for(surface,border);record=preference_record(colors)
            disk=case_dir/'new-fixture.img';fixture=seed_new_image(disk,record)
            case=dict(name=name,expected_record_policy_accepted=accepted,fixture=fixture,scenes=[])
            result['cases'].append(case);storage.write_json(case_dir/'fixture.json',fixture)
            check(fixture['record']['accepted_by_current_preferences_policy']==accepted,'fixture policy expectation differs')
            before_disk=sha(disk)
            result['actual_qemu_start_attempts']+=1
            guest=TranslucentGuest(esp,disk,case_dir/'guest',True)
            result['actual_qemu_boots']+=1
            expected_colors=colors if accepted else DARK
            sequence=SEQUENCE if accepted else 0
            check(guest.field('STYLE',72)==theme_bytes(expected_colors,256),'loaded/fallback theme differs')
            check(guest.value('PREF_SEQUENCE','desktop.apps')==sequence,'selected preference sequence differs')
            marker=b'DONGOS_P7_SETTINGS_LOADED' if accepted else b'DONGOS_P7_SETTINGS_DEFAULT'
            check(marker in guest.raw,'expected preference load/fallback marker absent')
            frames=guest.kval('user.memory','FRAME_COUNT')
            meta=guest.kernel(guest.ksym('user.memory','META'),5*32,'initial translucent test META')
            case['loaded_sequence']=sequence;case['loaded_actual_theme_hex']=guest.field('STYLE',72).hex()
            check(not guest.armed,'stable startup has an armed breakpoint')
            initial=guest.verify_scene('initial-stable');case['scenes'].append(initial)
            guest.verify_assets('initial-assets',expected_colors,256,frames,meta)
            if accepted:
                check(initial['nonopaque_source_dividers']==4,'half-border fixture did not create four nonopaque source dividers')
                guest.focus(3);r=rect(guest.windows(),3)
                divider=r[1]+32;guest.move(r[0]+80,divider-5)
                old=struct.unpack_from('<2q',guest.windows(),2464)
                point=(old[0]+1,divider)
                guest.move(r[0]+180,divider-5)
                guest.cursor_damage_witness=dict(window=3,point=list(point),
                    old_cursor_clip=[old[0],old[1],old[0]+10,old[1]+18],
                    reason='actual pointer moved off the title divider; old footprint must be repainted',
                    old_clip_wholly_inside_claimed_opaque_center=(r[0]+8<=old[0]
                        and old[0]+10<=r[2]-8 and r[1]+8<=old[1] and old[1]+18<=r[3]-8))
                check(guest.cursor_damage_witness['old_clip_wholly_inside_claimed_opaque_center'],
                      'old cursor damage clip not inside legacy opaque center')
                case['scenes'].append(guest.verify_scene('stable-actual-divider-damage'))
                guest.cursor_damage_witness=None
            guest.focus(3)
            revision=guest.value('STYLE_REVISION');guest.key_async('equal')
            middle=guest.capture_middle('dpi125-middle',3,revision=revision+1)
            check(middle['actual_scaled_texture_pixels']>=8,'middle scene did not exercise actual nearest sampling')
            case['scenes'].append(middle)
            guest.verify_assets('middle-assets',expected_colors,320,frames,meta)
            guest.settle_motion();check(not guest.armed,'stable endpoint has an armed breakpoint')
            case['scenes'].append(guest.verify_scene('dpi125-endpoint'))
            guest.verify_assets('endpoint-assets',expected_colors,320,frames,meta)
            if accepted:
                check(all(scene['nonopaque_source_dividers']==4 for scene in case['scenes']),
                      'loaded fixture lost the actual nonopaque interior divider')
            guest.verify_elf()
            case['guest_evidence']=guest.evidence
            guest.close();guest=None
            check(sha(disk)==before_disk,'read-only fixture disk changed')
            with disk_oracle.Fat32Image(disk) as image:
                after_record,_=image.file(b'DESK0   CFG');check(after_record==record,'preference fixture bytes changed')
            case.update(passed=True,disk_unchanged=True,actual_five_elf_rx_and_ten_guards_verified=True,
                        font_aperture_and_private_meta_verified=True,
                        expected_surface_policy_rejection_verified=not accepted)
            storage.write_json(case_dir/'result.json',case)
        result.update(passed=True,all_three_preference_policy_cases_verified=True,
            actual_loaded_translucent_border_verified=True,half_surface_cases_correctly_rejected=True,
            default_surface_policy_not_weakened=True)
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        if guest:
            result['incomplete_guest_evidence']=guest.evidence
            try:guest.close()
            except Exception as exc:result['cleanup_error']=f'{type(exc).__name__}: {exc}'
        # A constructor failure may still have launched and reaped a real VM.
        # Its own persistent report, not successful construction, counts it.
        boot_reports=[]
        for case in result['cases']:
            report=output/case['name']/'guest/guest.json'
            if report.exists():
                evidence=json.loads(report.read_text(encoding='utf-8'))
                boot_reports.append(dict(case=case['name'],report=str(report),
                    actual_qemu_executed=bool(evidence.get('actual_qemu_executed'))))
        result['actual_boot_reports']=boot_reports
        result['actual_qemu_boots']=sum(report['actual_qemu_executed'] for report in boot_reports)
        result['source_and_artifacts_unchanged']=unchanged()
        if not result['source_and_artifacts_unchanged']:
            result.update(passed=False,identity_error='pinned source/artifact changed or metadata unavailable')
        storage.write_json(output/'result.json',result)
    print(output/'result.json',flush=True)
    return 0 if result['passed'] else 1


class ModelTests(unittest.TestCase):
    def test_fixtures_have_real_valid_checksums_but_preserve_surface_policy(self):
        for _,surface,border,accepted in CASES:
            raw=preference_record(colors_for(surface,border));contract=record_contract(raw)
            self.assertTrue(contract['envelope_and_checksum_valid'])
            self.assertEqual(accepted,contract['accepted_by_current_preferences_policy'])
            if accepted:self.assertEqual(SEQUENCE,disk_oracle.decode_record(raw)['sequence'])
            else:
                with self.assertRaisesRegex(disk_oracle.RecordError,'surface'):disk_oracle.decode_record(raw)
        bad=bytearray(raw);bad[40]^=1
        with self.assertRaisesRegex(ValueError,'checksum'):record_contract(bad)

    def test_new_disk_seeding_is_raw_exact_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'new.img';raw=preference_record(colors_for(DARK[1],HALF_BORDER))
            result=seed_new_image(path,raw)
            self.assertTrue(result['fat_mirrors_equal'])
            self.assertEqual([4],result['file']['clusters'])
            digest=sha(path)
            with self.assertRaises(ValueError):seed_new_image(path,raw)
            self.assertEqual(digest,sha(path))

    def test_actual_nonopaque_divider_defeats_legacy_skipcenter_copy(self):
        background=struct.pack('<I',0xff254b6a)*64
        textures=bytearray(0x200000);struct.pack_into('<I',textures,(3*8+3)*4,HALF_BORDER)
        arguments=(3,3,background,textures,8,[(0,0,8,8)],[(0,0,8,8)],[256],[257],0,(99,99),256,0xffffffff)
        expected,used=scene_pixel(*arguments)
        wrong,_=scene_pixel(*arguments,unsafe_first=0)
        self.assertEqual(0,legacy_first(3,3,[(0,0,8,8)],[(0,0,8,8)],[256],[257],1))
        self.assertEqual(HALF_BORDER,used[0]['argb'])
        self.assertNotEqual(expected&0xffffff,wrong&0xffffff)
        self.assertEqual(HALF_BORDER,wrong)
        self.assertEqual(255,expected>>24)
        self.assertIsNone(legacy_first(3,3,[(0,0,8,8)],[(0,0,8,8)],[128],[257],1))

    def test_exact_divider_inverse_can_disappear_when_downscaled(self):
        # For a 1-row source stripe, ceil bounds are the exact inverse of floor.
        for sh in (8,17,260,308):
            for th in (1,7,sh-1,sh,sh+1,sh*2):
                for sy in (1,sh//2,sh-1):
                    low=(sy*th+sh-1)//sh;high=((sy+1)*th+sh-1)//sh
                    self.assertEqual(list(range(low,high)),[y for y in range(th) if y*sh//th==sy])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-esp',type=Path)
    parser.add_argument('--selftest',action='store_true')
    args=parser.parse_args()
    if args.selftest:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(ModelTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.reuse_esp is None:parser.error('--reuse-esp required; this runner never builds')
    return run(args)


if __name__=='__main__':raise SystemExit(main())
