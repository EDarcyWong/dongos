"""Build/run the persistent 1080p DongOS desktop with its real VirtIO disk."""
from pathlib import Path
import argparse,subprocess
from tools.build import ROOT,build,qemu_command
from tools.make_fat32_disk import create

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--esp',type=Path,help='reuse a completed runtime7 ESP')
    p.add_argument('--disk',type=Path,default=ROOT/'build/desktop/user-disk.img')
    p.add_argument('--scale',type=int,choices=(100,125,150,175,200),default=100,help='boot UI scale in percent')
    p.add_argument('--ps2',action='store_true',help='use the PS/2 pointer fallback')
    p.add_argument('--headless',action='store_true');a=p.parse_args()
    esp=a.esp.resolve() if a.esp else build(runtime_level=7,desktop_scale=a.scale,output=ROOT/f'build/desktop/scale-{a.scale}')
    if not (esp/'SERVICES.BIN').is_file():raise ValueError('runtime7 service bundle required')
    disk=a.disk.resolve();disk.parent.mkdir(parents=True,exist_ok=True)
    if not disk.exists():create(disk,64)
    command=qemu_command(esp,ROOT/'build/desktop/run',headless=a.headless)
    disk_option=disk.as_posix().replace(',',',,')
    command+=['-cpu','max,+smep,+smap,+umip','-drive',f'if=none,id=data,format=raw,cache=writeback,file={disk_option}',
        '-device','virtio-blk-pci,drive=data,disable-legacy=on']
    if not a.ps2:command+=['-device','virtio-tablet-pci']
    print('Persistent disk:',disk,flush=True)
    return subprocess.run(command,cwd=ROOT).returncode
if __name__=='__main__':raise SystemExit(main())
