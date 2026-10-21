# P5CTX1 交付：真实 DMA 持有上下文

用户明确要求由 Codex 接手原 Cursor 待领取任务；协调器已转派为 codex 并领取，保留 cursor:P5CTX1 编号与原文件范围。

已实现真实 0x63 申请前可信身份封存、成功/err 两分支实际快照、重复/重入/slot 复用拒绝、真实 retire_one/owner revoke/manager revoke 结果追加。上下文不授权回收；drain 始终 UNKNOWN。未改 memory/devices/device_manager、Process/Frame 布局、公共 syscall；未运行 OS/VM、未提交或推送。

## 验证

- 完整候选 services/device_host/memory 闭包 debug/release 各 86 模块编译通过，所有依赖逐模块来自主线并保存来源 SHA；输入未变。命令：在 code 内运行 `python build/p5ctx1_candidate_check.py`，exit 0。证据 `code/build/test/p5ctx1-candidate/20261020-234858/evidence.json`。
- 实现测试：在工作区根运行 `python -m unittest discover -s coordination/dongos_works/cursor-works/tests -p test_p5_recovery_context.py -v`，exit 0，1 unittest、0 skip。debug/release 正常体各 1081 断言、73 场景；真实错误源码删除 err 快照、覆盖旧 owner/root 两类均编译/汇编/链接成功后按指定数值断言 exit 1。
- 独立审查代理重新执行同一命令，exit 0，1 test/0 skip，8.275 秒；6 个 run 证据为 `run-f5c1a09654dc`、`run-4604424b07d8`、`run-410e60676fd2`、`run-2a9cef16cec1`、`run-73218ab46f56`、`run-113f6b2a7440`，位于 `code/build/test/p5-recovery-context/`。每组含真实源码/坏源、片段绑定 SHA、compile/assemble/link/execute 命令/退出码/stdout/stderr、source-before/after/after-execute。
- 独立静态审查已核对真实控制流、可信 Catalog/host/memory 身份、完整租约/舍入尾部、失败 sticky、上下文错误不短路隔离、合法设备代际跃迁、SMP stop ACK 原时点、manager revoke 无 reset。正式协调器独立隔离复验待排队；主线相关回归和真实文件集成待协调者处理。

宿主 fixture 明确 stub 硬件、内存、调度和 Catalog 边界，真实 pure ledger 身份/binding/index 函数被抽取执行。不将这些结果视为 guest、撤映射后全核 TLB 退休或 DMA drain 的证明；P5 未完成。

## 文件 SHA256

- `cursor-works/src/p5/user/device_host.dg`：`823fc27763560ff880dd26b9e4da236a92cf55174d3e4a86bf0b234592ba95ce`
- `cursor-works/src/p5/user/services.dg`：`548c6dafa0f2e515bcefeba51ae28c754e68273c979275862c32b60b6a76fa65`
- `cursor-works/src/p5/recovery-context.md`：`c664037393f5b40b4e8c3b93b7186b1eedf0c49af96315272903b2bf5944e4bb`
- `cursor-works/tests/p5_recovery_context_fixture.dg`：`caf529fef8b79aca3487baf23c0e6e20859cc6f60ec1c354b775bc53723f23eb`
- `cursor-works/tests/p5_recovery_context_probe.c`：`99f99218f7764ae98e5d5f8a3eaa94ae5bcbe03bfca6774bd25154e4b55487fe`
- `cursor-works/tests/test_p5_recovery_context.py`：`832e27b61707a27673cc1aa1b239e212cc32a6e328a5be5e5a35b0ed5cd0ba45`

## 基线与完整源码差异

基线 HEAD `244b18c737495fc1acc4a39520a69a5b77fa5f67`。device_host 基线 SHA `4a5b7766d2de334f725b4d2966eb663be62c851614048a27bf949f88e4a067da`；services 基线 SHA `2c6dacb8267e2727aef1fd960271b9789afb856f707628268e781c672260a1e7`。以下 diff 保留两份完整生产模块，未剪掉旧控制流。

```diff
diff --git "a/D:\\projects\\2026\\dongos\\code\\kernel\\user\\device_host.dg" "b/D:\\projects\\2026\\dongos\\coordination\\dongos_works\\cursor-works\\src\\p5\\user\\device_host.dg"
index 97f87fc..52ea29e 100644
--- "a/D:\\projects\\2026\\dongos\\code\\kernel\\user\\device_host.dg"
+++ "b/D:\\projects\\2026\\dongos\\coordination\\dongos_works\\cursor-works\\src\\p5\\user\\device_host.dg"
@@ -9,6 +9,7 @@ import boot.service_memory as resources;
 import irq.platform as platform;
 import lib.device_abi as abi;
 import drivers.pci_msi as msi;
+import user.memory as memory;
 pub var TABLE:*ledger.Table=null;
 pub var VIEW:abi.Device=abi.EMPTY_DEVICE;
 pub var BINDING:abi.Binding=abi.EMPTY_BINDING;
@@ -23,6 +24,120 @@ pub var BLOCK_RESET_TOKEN:u64=0;
 pub var MSI:msi.State=msi.EMPTY;
 pub var PCI_FAILED:bool=false;
 var MSI_OPS:msi.Ops=msi.Ops{read:msi_read,write:msi_write};
+// P5_CONTEXT_BEGIN
+// Kernel-private first-request receipt. No field authorizes DMA reclamation.
+// snapshot_status: 0 not sampled, 1 no allocator receipt, 2 real receipt.
+// reset: 0 unknown, 1 no supported reset, 2 RESET_CONFIRMED, 3 uncertain.
+// drain remains UNKNOWN (0), even after a confirmed modern VirtIO reset.
+pub struct DmaContext {
+ pub present:u64,pub slot:u64,pub configuration:u64,pub owner:u64,pub incarnation:u64,
+ pub device_token:u64,pub device_generation:u64,pub identity:abi.Device,
+ pub root:u64,pub memory_generation:u64,pub request_bytes:u64,pub request_alignment:u64,
+ pub snapshot_status:u64,pub snapshot_error:u64,pub lease:memory.DmaLease,
+ pub acquire_done:u64,pub acquire_error:u64,pub context_error:u64,
+ pub stop_state:u64,pub stop_error:u64,pub smp_retire:u64,
+ pub route_state:u64,pub route_error:u64,pub isolation:u64,pub isolation_error:u64,
+ pub reset:u64,pub reset_error:u64,pub generation_after:u64,pub revoke_error:u64,
+ pub held:u64,pub drain:u64,
+}
+pub const EMPTY_DMA_CONTEXT:DmaContext=DmaContext{present:0,slot:0,configuration:0,owner:0,incarnation:0,
+ device_token:0,device_generation:0,identity:abi.EMPTY_DEVICE,root:0,memory_generation:0,request_bytes:0,request_alignment:0,
+ snapshot_status:0,snapshot_error:0,lease:memory.EMPTY_DMA,acquire_done:0,acquire_error:0,context_error:0,
+ stop_state:0,stop_error:0,smp_retire:0,route_state:0,route_error:0,isolation:0,isolation_error:0,
+ reset:0,reset_error:0,generation_after:0,revoke_error:0,held:0,drain:0};
+var DMA_CONTEXTS:[16]DmaContext=[EMPTY_DMA_CONTEXT;16];
+// Forward a materialized error union without calling its operation twice.
+pub fn dma_result(result:!void)!void{return result;}
+pub unsafe fn dma_context(slot:usize,out:*DmaContext)!void{unsafe{
+ if slot>=16||out==null{return error.abi.Invalid;}
+ if DMA_CONTEXTS[slot].present!=1{return error.abi.WouldBlock;}*out=DMA_CONTEXTS[slot];
+}return;}
+// Only services supplies Catalog/current Process values. Hardware and the
+// original role attachment are authenticated here before the allocator call.
+// A first trusted request is sticky, including a rejected/no-snapshot request;
+// later requests cannot adopt its owner/root or an old allocator receipt.
+pub unsafe fn dma_begin(slot:usize,configuration:u64,owner:u64,incarnation:u64,root:u64,memory_generation:u64,bytes:u64,alignment:u64)!bool{unsafe{
+ if slot>=16{return error.abi.Invalid;}
+ if DMA_CONTEXTS[slot].present!=0{return error.abi.Busy;}
+ if TABLE==null||(slot!=2&&slot!=4&&slot!=devices.ADMITTED_XHCI){return false;}
+ var role:u64=abi.BLOCK;var attached:u64=PCI_OWNERS[0];var token:u64=PCI_TOKENS[0];
+ if slot==4{role=abi.TABLET;attached=PCI_OWNERS[1];token=PCI_TOKENS[1];}
+ if slot==devices.ADMITTED_XHCI{role=abi.XHCI;attached=XHCI_OWNER;token=(*TABLE).bindings[3].device_token;}
+ // No prior trusted attachment means the old device path retains its policy.
+ if attached==0{return false;}
+ if configuration!=slot as u64||owner==0||incarnation==0||incarnation>0x0fff_ffff
+  ||owner!=(((slot as u64+1)<<32)|incarnation)||attached!=owner||root==0||memory_generation==0{return error.abi.Denied;}
+ let p=memory.processes()+slot;
+ if (*p).ready!=1||(*p).root!=root||memory.generation(slot)!=memory_generation{return error.abi.Stale;}
+ var binding=abi.EMPTY_BINDING;try ledger.binding(TABLE,role,&binding);
+ if token==0||binding.device_token!=token||binding.role!=role||binding.configuration_id!=configuration
+  ||binding.generation==0||binding.generation!=(token>>8)||(binding.flags&abi.REVOKED)!=0{return error.abi.Stale;}
+ let index=token&255;if index==0||index>(*TABLE).count as u64{return error.abi.Stale;}
+ let d=(*TABLE).devices[(index-1) as usize];var raw=abi.EMPTY_DEVICE;
+ if d.token!=token||d.generation!=binding.generation||(d.flags&abi.REVOKED)!=0||d.kind!=abi.PCI
+  ||!(try hardware(d.ecam,&raw))||!ledger.same_identity(&d,&raw){return error.abi.Removed;}
+ // Never bind an existing memory lease to a newly created context.
+ var previous=memory.EMPTY_DMA;match memory.dma_snapshot(slot,&previous){ok=>{return error.abi.Busy;},err(e)=>{},}
+ var c=EMPTY_DMA_CONTEXT;c.present=1;c.slot=slot as u64;c.configuration=configuration;c.owner=owner;c.incarnation=incarnation;
+ c.device_token=token;c.device_generation=binding.generation;c.identity=d;c.root=root;c.memory_generation=memory_generation;
+ c.request_bytes=bytes;c.request_alignment=alignment;c.held=1;DMA_CONTEXTS[slot]=c;return true;
+}}
+// Called on BOTH actual dma_acquire branches, before any copy_out. A valid
+// physical=0 HELD receipt is retained verbatim; an absent receipt is distinct.
+pub unsafe fn dma_finish(slot:usize,owner:u64,root:u64,memory_generation:u64,acquire_error:u64)void{unsafe{
+ if slot>=16{return;}let c=&DMA_CONTEXTS[slot];
+ if (*c).present!=1||(*c).owner!=owner||(*c).root!=root||(*c).memory_generation!=memory_generation||(*c).acquire_done!=0{return;}
+ (*c).acquire_done=1;(*c).acquire_error=acquire_error;var lease=memory.EMPTY_DMA;
+ match memory.dma_snapshot(slot,&lease){
+  ok=>{(*c).snapshot_status=2;(*c).lease=lease;
+   if lease.root!=root||lease.generation!=memory_generation||lease.pages==0
+    ||(lease.state!=memory.DMA_HELD&&lease.state!=memory.DMA_COMPLETE){(*c).context_error=0x0512_0004;}
+  },err(e)=>{(*c).snapshot_status=1;(*c).snapshot_error=e;},}
+}return;}
+// Stop/detach ACK is recorded at its real point, before mapping withdrawal.
+// It is never a post-unmap TLB acknowledgement. All hooks are non-throwing:
+// a damaged context must never bypass the existing isolation/revoke path.
+pub unsafe fn dma_stop(slot:usize,configuration:u64,owner:u64,incarnation:u64,root:u64,memory_generation:u64,smp_retire:u64,stop_error:u64)void{unsafe{
+ if slot>=16{return;}let c=&DMA_CONTEXTS[slot];if (*c).present!=1{return;}
+ if (*c).slot!=slot as u64||(*c).configuration!=configuration||(*c).owner!=owner||(*c).incarnation!=incarnation
+  ||(*c).root!=root||(*c).memory_generation!=memory_generation{if (*c).context_error==0{(*c).context_error=0x0512_0004;}return;}
+ if smp_retire==1{(*c).smp_retire=1;(*c).stop_state=1;}
+ else if smp_retire==2&&(*c).smp_retire==0{(*c).smp_retire=2;}
+ if stop_error!=0{if (*c).stop_error==0{(*c).stop_error=stop_error;}}
+ else if smp_retire!=2{(*c).stop_state=1;}
+}return;}
+unsafe fn dma_target(slot:usize,owner:u64,token:u64)bool{unsafe{
+ if slot>=16||TABLE==null{return false;}let c=&DMA_CONTEXTS[slot];
+ if (*c).present!=1||(*c).slot!=slot as u64||(*c).owner!=owner||(*c).device_token!=token{return false;}
+ let index=token&255;if index==0||index>(*TABLE).count as u64{return false;}
+ let d=(*TABLE).devices[(index-1) as usize];
+ let original=d.generation==(*c).device_generation&&(d.flags&abi.REVOKED)==0;
+ let revoked=d.generation==(*c).device_generation+1&&(d.flags&abi.REVOKED)!=0;
+ if d.token!=token||!ledger.same_identity(&(*c).identity,&d)||(!original&&!revoked){if (*c).context_error==0{(*c).context_error=0x0512_0004;}return false;}
+ return true;
+}}
+unsafe fn dma_route(owner:u64,result:u64)void{unsafe{
+ var slot:usize=0;while slot<16{let c=&DMA_CONTEXTS[slot];if (*c).present==1&&(*c).owner==owner{
+  if (*c).route_state==0{(*c).route_state=1;}if result!=0{(*c).route_state=2;if (*c).route_error==0{(*c).route_error=result;}}
+ }slot+=1;}
+}return;}
+unsafe fn dma_isolation(slot:usize,owner:u64,token:u64,result:u64)void{unsafe{
+ if !dma_target(slot,owner,token){return;}let c=&DMA_CONTEXTS[slot];
+ if (*c).isolation==0{(*c).isolation=1;}if result!=0{(*c).isolation=2;if (*c).isolation_error==0{(*c).isolation_error=result;}}
+}return;}
+unsafe fn dma_reset(slot:usize,owner:u64,token:u64,result:u64,code:u64)void{unsafe{
+ if !dma_target(slot,owner,token){return;}let c=&DMA_CONTEXTS[slot];if (*c).reset!=0{return;}
+ (*c).reset=result;(*c).reset_error=code;
+}return;}
+unsafe fn dma_revoked(token:u64,result:u64)void{unsafe{
+ var slot:usize=0;while slot<16{let c=&DMA_CONTEXTS[slot];
+  if (*c).present==1&&(*c).device_token==token&&dma_target(slot,(*c).owner,token){
+   if result!=0{if (*c).revoke_error==0{(*c).revoke_error=result;}}
+   else if (*c).generation_after==0{(*c).generation_after=(*TABLE).devices[((token&255)-1) as usize].generation;}
+  }slot+=1;
+ }
+}return;}
+// P5_CONTEXT_END
 unsafe fn hardware(ecam:u64,out:*abi.Device)!bool{unsafe{
     let identity=try devices.configuration_read(ecam);
     if (identity&65535)==0||(identity&65535)==65535{return false;}
@@ -125,20 +240,26 @@ pub unsafe fn interrupt(vector:u64)!u64{unsafe{
 pub unsafe fn revoke_owner(owner:u64)!void{unsafe{
     if TABLE==null{return;}
     // Retire the message route and verified BME before closing driver caps.
-    let stopped=msi.retire(&MSI,&MSI_OPS,owner);match stopped{ok=>{},err(e)=>{PCI_FAILED=true;return stopped;},}
+    let stopped=msi.retire(&MSI,&MSI_OPS,owner);match stopped{ok=>{dma_route(owner,0);},err(e)=>{dma_route(owner,e);PCI_FAILED=true;return stopped;},}
     var pci:usize=0;while pci<2{if PCI_OWNERS[pci]==owner&&owner!=0{
         var slot:usize=2;if pci==1{slot=4;}
-        let isolated=devices.quarantine(slot);match isolated{ok=>{},err(e)=>{PCI_FAILED=true;return isolated;},}
-        let token=PCI_TOKENS[pci];let index=(token&255)-1;
-        if slot==2{if try devices.quiesce_stopped_block(){BLOCK_RESET_OWNER=owner;BLOCK_RESET_TOKEN=token;}}
+        let token=PCI_TOKENS[pci];
+        let isolated=devices.quarantine(slot);match isolated{ok=>{dma_isolation(slot,owner,token,0);},err(e)=>{dma_isolation(slot,owner,token,e);PCI_FAILED=true;return isolated;},}
+        let index=(token&255)-1;
+        if slot==2{let quiesced=devices.quiesce_stopped_block();match quiesced{
+            ok(confirmed)=>{if confirmed{dma_reset(slot,owner,token,2,0);BLOCK_RESET_OWNER=owner;BLOCK_RESET_TOKEN=token;}
+                else{dma_reset(slot,owner,token,1,0);}},
+            err(e)=>{dma_reset(slot,owner,token,3,e);let ignored=try quiesced;},
+        }}
         if token!=0&&((*TABLE).devices[index as usize].flags&abi.REVOKED)==0{
-            try ledger.revoke(TABLE,token,token>>8);
+            let revoked=ledger.revoke(TABLE,token,token>>8);match revoked{ok=>{dma_revoked(token,0);},err(e)=>{dma_revoked(token,e);return revoked;},}
         }
     }pci+=1;}
     if XHCI_OWNER!=0&&owner==XHCI_OWNER{
-        try devices.quarantine(devices.ADMITTED_XHCI);
+        let token=(*TABLE).bindings[3].device_token;
+        let isolated=devices.quarantine(devices.ADMITTED_XHCI);match isolated{ok=>{dma_isolation(devices.ADMITTED_XHCI,owner,token,0);},err(e)=>{dma_isolation(devices.ADMITTED_XHCI,owner,token,e);return isolated;},}
         let binding=(*TABLE).bindings[3];if binding.device_token!=0&&(binding.flags&abi.REVOKED)==0{
-            try ledger.revoke(TABLE,binding.device_token,binding.generation);
+            let revoked=ledger.revoke(TABLE,binding.device_token,binding.generation);match revoked{ok=>{dma_revoked(binding.device_token,0);},err(e)=>{dma_revoked(binding.device_token,e);return revoked;},}
         }
     }
     var i:usize=0;while i<2{let irq=(*TABLE).interrupts[i];
@@ -151,14 +272,14 @@ pub unsafe fn revoke(token:u64,generation:u64)!u64{unsafe{
     var config:u64=0xffff_ffff_ffff_ffff;var i:usize=0;
     while i<4{let binding=(*TABLE).bindings[i];if binding.device_token==token{
         if binding.generation!=generation{return error.abi.Stale;}config=binding.configuration_id;
-        if binding.role==abi.BLOCK{try devices.quarantine(2);}
-        if binding.role==abi.TABLET{try devices.quarantine(4);}
-        if binding.role==abi.XHCI{try devices.quarantine(devices.ADMITTED_XHCI);}
+        if binding.role==abi.BLOCK{let isolated=devices.quarantine(2);match isolated{ok=>{dma_isolation(2,PCI_OWNERS[0],token,0);},err(e)=>{dma_isolation(2,PCI_OWNERS[0],token,e);try dma_result(isolated);},}}
+        if binding.role==abi.TABLET{let isolated=devices.quarantine(4);match isolated{ok=>{dma_isolation(4,PCI_OWNERS[1],token,0);},err(e)=>{dma_isolation(4,PCI_OWNERS[1],token,e);try dma_result(isolated);},}}
+        if binding.role==abi.XHCI{let isolated=devices.quarantine(devices.ADMITTED_XHCI);match isolated{ok=>{dma_isolation(devices.ADMITTED_XHCI,XHCI_OWNER,token,0);},err(e)=>{dma_isolation(devices.ADMITTED_XHCI,XHCI_OWNER,token,e);try dma_result(isolated);},}}
         if binding.role==abi.PS2{var n:usize=0;while n<2{
             if (*TABLE).interrupts[n].live==1{try platform.mask_isa((*TABLE).interrupts[n].view.irq,true);}n+=1;
         }}
     }i+=1;}
-    try ledger.revoke(TABLE,token,generation);return config;
+    let revoked=ledger.revoke(TABLE,token,generation);match revoked{ok=>{dma_revoked(token,0);},err(e)=>{dma_revoked(token,e);try dma_result(revoked);},}return config;
 }}
 // Read-only completed boot inventory: no rediscovery, hardware read or grant.
 pub unsafe fn read_pci_inventory(cursor:u64,out:*pci_inventory_abi.Entry)!void{unsafe{
```

```diff
diff --git "a/D:\\projects\\2026\\dongos\\code\\kernel\\user\\services.dg" "b/D:\\projects\\2026\\dongos\\coordination\\dongos_works\\cursor-works\\src\\p5\\user\\services.dg"
index 73ce59e..e53bd2f 100644
--- "a/D:\\projects\\2026\\dongos\\code\\kernel\\user\\services.dg"
+++ "b/D:\\projects\\2026\\dongos\\coordination\\dongos_works\\cursor-works\\src\\p5\\user\\services.dg"
@@ -398,7 +398,12 @@ unsafe fn retire_one(id:usize,state:u64,status:u64)!void{unsafe{
     let incarnation=(*CATALOG).incarnation[id];
     let cfg=procs.current(CATALOG,id);
     // Quiesce/detach all running and RETURNING references before aliases/root.
-    if SMP_ENABLED{try smp_bridge.retire(id);SMP_TEST_SLOTS&=~(1<<id as u64);}
+    var dma_smp:u64=0;let dma_owner=((id as u64+1)<<32)|incarnation;
+    let dma_root=(*process(id)).root;let dma_memory_generation=memory.generation(id);
+    if SMP_ENABLED{let stopped=smp_bridge.retire(id);match stopped{
+        ok=>{dma_smp=1;device_host.dma_stop(id,cfg,dma_owner,incarnation,dma_root,dma_memory_generation,1,0);},
+        err(e)=>{device_host.dma_stop(id,cfg,dma_owner,incarnation,dma_root,dma_memory_generation,2,e);return stopped;},
+    }SMP_TEST_SLOTS&=~(1<<id as u64);}
     // Withdraw every shared alias while both roots still exist. A failed
     // withdrawal permanently stops scheduling before either root is freed.
     if id==3&&windows.EPOCH!=0{try windows.compositor_gone(windows.EPOCH);}
@@ -406,7 +411,10 @@ unsafe fn retire_one(id:usize,state:u64,status:u64)!void{unsafe{
         try windows.owner_gone(((id as u64+1)<<32)|incarnation);
         if incarnation>GUI_DEPARTED[id]{GUI_DEPARTED[id]=incarnation;}
     }
-    try procs.terminate(CATALOG,id,state,status);
+    let terminated=procs.terminate(CATALOG,id,state,status);match terminated{
+        ok=>{device_host.dma_stop(id,cfg,dma_owner,incarnation,dma_root,dma_memory_generation,dma_smp,0);},
+        err(e)=>{device_host.dma_stop(id,cfg,dma_owner,incarnation,dma_root,dma_memory_generation,dma_smp,e);return terminated;},
+    }
     boot_trace.event(trace.SERVICE_STOP,cfg,(*CATALOG).states[cfg as usize].generation,0);
     if id==13&&cfg==13&&incarnation>USB_DEPARTED{USB_DEPARTED=incarnation;}
     try revoke_loaded(id,incarnation);
@@ -1006,7 +1014,24 @@ unsafe fn perform(frame:*abi.Frame)!usize {
         if code==0x63 {
             if (try authority((*frame).rdi,handles.DMA,handles.MAP|handles.WRITE))!=devices.DMA_OBJECT { return error.Protocol; }
             try memory.check_range(CURRENT,(*frame).r10,sizeof(blk.Lease),true);
-            try devices.dma_acquire(CURRENT,(*frame).rsi,(*frame).rdx);
+            var dma_tracked=false;var dma_owner:u64=0;var dma_root:u64=0;var dma_generation:u64=0;
+            if CATALOG!=null{
+                if !managed(CURRENT)||(*CATALOG).ready!=1||CURRENT>=procs.SLOTS{return error.Protocol;}
+                let dma_configuration=procs.current(CATALOG,CURRENT);let dma_incarnation=(*CATALOG).incarnation[CURRENT];
+                if dma_configuration>=(*CATALOG).count as u64||dma_configuration>=procs.CONFIGS as u64
+                    ||dma_incarnation==0||dma_incarnation>0x0fff_ffff{return error.Protocol;}
+                let dma_state=(*CATALOG).states[dma_configuration as usize];
+                if (*CATALOG).slot[dma_configuration as usize]!=CURRENT as u64||dma_state.configuration!=dma_configuration
+                    ||dma_state.process!=((dma_incarnation<<8)|(CURRENT as u64+1))
+                    ||(dma_state.state!=proc.STARTING&&dma_state.state!=proc.READY){return error.Protocol;}
+                dma_owner=owner_key(CURRENT);dma_root=(*process(CURRENT)).root;dma_generation=memory.generation(CURRENT);
+                dma_tracked=try device_host.dma_begin(CURRENT,dma_configuration,dma_owner,
+                    dma_incarnation,dma_root,dma_generation,(*frame).rsi,(*frame).rdx);
+            }
+            let acquired=devices.dma_acquire(CURRENT,(*frame).rsi,(*frame).rdx);match acquired{
+                ok=>{if dma_tracked{device_host.dma_finish(CURRENT,dma_owner,dma_root,dma_generation,0);}},
+                err(e)=>{if dma_tracked{device_host.dma_finish(CURRENT,dma_owner,dma_root,dma_generation,e);}try device_host.dma_result(acquired);},
+            }
             try memory.copy_out(CURRENT,(*frame).r10,slice_from_raw_parts(devices.dma_lease(CURRENT) as *const u8,sizeof(blk.Lease)));
             (*frame).rax=0; return CURRENT;
         }
```


## AI交付 2026-10-20T15:53:22+00:00 · codex-mcp-398fa2ecee7645ff

Codex按用户要求接手，已在原7文件范围完成真实DMA上下文实现与交付。候选完整86模块debug/release编译通过；实现测试及独立代理复验均1test/0skip，双mode各1081断言73场景，两个真实坏源正常构建运行后指定断言拒绝。交付含基线SHA、完整diff、证据位置与宿主stub/未获guest证明边界。请进入正式隔离独立复验；主线集成和既有回归尚未执行。
