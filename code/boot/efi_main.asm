; P1 OS loader. Firmware calls use Microsoft x64; kernel entry uses SysV rdi.
; Layout references: UEFI 2.10 chapters 4, 7, 9, 12 and 13; EDK II MdePkg
; Uefi/UefiSpec.h, Protocol/{LoadedImage,SimpleFileSystem,GraphicsOutput}.h.
        bits 64
        default rel
%include "uefi.inc"
%include "bootinfo.inc"
%include "image_manifest.inc"
%include "boot_trace.inc"

%ifndef P1_TEST
%define P1_TEST 0
%endif
%ifndef SERVICE_BUNDLE
%define SERVICE_BUNDLE 0
%endif
%if SERVICE_BUNDLE != 0 && SERVICE_BUNDLE != 1
%error SERVICE_BUNDLE must be0 or1
%endif

MAP_CAPACITY equ 65536
STACK_BYTES equ 65536
PAGE_TABLE_BYTES equ 8 * 4096
KERNEL_ALLOCATION_PAGES equ 1024  ; 4 MiB: retains a whole aligned 2 MiB region.
UART_POLL_LIMIT equ 0x100000

        section .text
        global efi_main
        extern image_verify, image_unpack
%ifdef DESKTOP_MODE
        extern desktop_graphics_mode
%endif
%if SERVICE_BUNDLE
        extern service_bundle_load
        extern boot_trace_sample,loader_trace_initialize,loader_trace_ebs
%endif

; Input: rcx image handle, rdx EFI_SYSTEM_TABLE. Does not return.
; No firmware service is called after ExitBootServices succeeds. All reserved
; storage is EfiLoaderCode/Data and remains reserved in the delivered map.
efi_main:
        endbr64
        sub     rsp, 56                  ; shadow + two stack args; call-aligned
        cld
        mov     [image_handle], rcx
        mov     [system_table], rdx
%if SERVICE_BUNDLE
        ; First owned timestamp, before UART/firmware I/O. EFI args saved.
        lea     rdi,[trace_loader_entry]
        call    boot_trace_sample
        mov     rdx,[system_table]       ; SysV sampler clobbers RDX/RCX.
%endif
        mov     r12, [rdx + EFI_SYSTEM_TABLE.BootServices]
        call    serial_init
        lea     rcx, [msg_start]
        call    serial_write

        ; A self-map limited to 4 GiB must also cover the loader itself.
        mov     rcx, [image_handle]
        lea     rdx, [loaded_image_guid]
        lea     r8, [loaded_image]
        call    [r12 + EFI_BOOT_SERVICES.HandleProtocol]
        test    rax, rax
        jnz     fail_loaded
        mov     rbx, [loaded_image]
        mov     rax, [rbx + EFI_LOADED_IMAGE_PROTOCOL.ImageBase]
        add     rax, [rbx + EFI_LOADED_IMAGE_PROTOCOL.ImageSize]
        jc      fail_loaded
        dec     rax
        shr     rax, 32
        jnz     fail_loaded

        xor     ecx, ecx
        xor     edx, edx
        xor     r8d, r8d
        xor     r9d, r9d
        call    [r12 + EFI_BOOT_SERVICES.SetWatchdogTimer]
        test    rax, rax
        jnz     fail_watchdog

        ; Open the filesystem on this EFI image's own device handle.
        mov     rcx, [rbx + EFI_LOADED_IMAGE_PROTOCOL.DeviceHandle]
        lea     rdx, [filesystem_guid]
        lea     r8, [filesystem]
        call    [r12 + EFI_BOOT_SERVICES.HandleProtocol]
        test    rax, rax
        jnz     fail_filesystem
        mov     rcx, [filesystem]
        lea     rdx, [root_file]
        call    [rcx + EFI_SIMPLE_FILE_SYSTEM_PROTOCOL.OpenVolume]
        test    rax, rax
        jnz     fail_filesystem
        mov     rcx, [root_file]
        lea     rdx, [image_file]
        lea     r8, [image_path]
        mov     r9d, EFI_FILE_MODE_READ
        mov     qword [rsp + 32], 0
        call    [rcx + EFI_FILE_PROTOCOL.Open]
        test    rax, rax
        jnz     fail_open

        mov     qword [file_info_size], 512
        mov     rcx, [image_file]
        lea     rdx, [file_info_guid]
        lea     r8, [file_info_size]
        lea     r9, [file_info]
        call    [rcx + EFI_FILE_PROTOCOL.GetInfo]
        test    rax, rax
        jnz     fail_file_size
        cmp     qword [file_info_size], EFI_FILE_INFO_size
        jb      fail_file_size
        cmp     qword [file_info + EFI_FILE_INFO.FileSize], IMAGE_FILE_SIZE
        jne     fail_file_size
        test    qword [file_info + EFI_FILE_INFO.Attribute], EFI_FILE_DIRECTORY
        jnz     fail_file_size

        mov     ecx, (IMAGE_FILE_SIZE + 4095) / 4096
        mov     edx, EfiLoaderData
        call    allocate_low
        test    rax, rax
        jz      fail_allocate
        mov     [image_buffer], rax
        mov     qword [read_size], IMAGE_FILE_SIZE
        mov     rcx, [image_file]
        lea     rdx, [read_size]
        mov     r8, rax
        call    [rcx + EFI_FILE_PROTOCOL.Read]
        test    rax, rax
        jnz     fail_read
        cmp     qword [read_size], IMAGE_FILE_SIZE
        jne     fail_read
        mov     rcx, [image_file]
        call    [rcx + EFI_FILE_PROTOCOL.Close]
        test    rax, rax
        jnz     fail_read
%if SERVICE_BUNDLE
        ; Independent service resources are allocated before the final map/EBS.
        mov     rcx, r12
        mov     rdx, [root_file]
        lea     r8, [service_handoff_pointer]
        call    service_bundle_load
        test    rax, rax
        jnz     fail_service_bundle
%endif
        mov     rcx, [root_file]
        call    [rcx + EFI_FILE_PROTOCOL.Close]
        test    rax, rax
        jnz     fail_read

        mov     rcx, [image_buffer]
        mov     edx, IMAGE_FILE_SIZE
        call    image_verify
        test    eax, eax
        jnz     fail_hash

        mov     ecx, KERNEL_ALLOCATION_PAGES
        mov     edx, EfiLoaderCode
        call    allocate_low
        test    rax, rax
        jz      fail_allocate
        add     rax, 0x1fffff
        and     rax, -0x200000
        mov     [kernel_physical], rax
        mov     rdi, rax
        xor     eax, eax
        mov     ecx, 0x200000 / 8
        rep     stosq
        mov     rcx, [image_buffer]
        mov     edx, IMAGE_FILE_SIZE
        mov     r8, [kernel_physical]
        mov     r9d, 0x200000
        call    image_unpack
        test    eax, eax
        jnz     fail_unpack
        lea     rcx, [msg_image]
        call    serial_write

        mov     ecx, 1
        mov     edx, EfiLoaderData
        call    allocate_low
        test    rax, rax
        jz      fail_allocate
        mov     r13, rax                 ; BootInfo kept in a nonvolatile register.
        mov     rdi, rax
        xor     eax, eax
        mov     ecx, 4096 / 8
        rep     stosq
        mov     rax, BOOTINFO_MAGIC
        mov     [r13 + BootInfo.magic], rax
        mov     qword [r13 + BootInfo.version], BOOTINFO_VERSION
        mov     qword [r13 + BootInfo.size], BootInfo_size
        mov     rax, [kernel_physical]
        mov     [r13 + BootInfo.kernel_physical], rax
        mov     qword [r13 + BootInfo.kernel_size], IMAGE_RAW_SIZE

        mov     ecx, MAP_CAPACITY / 4096
        mov     edx, EfiLoaderData
        call    allocate_low
        test    rax, rax
        jz      fail_allocate
        mov     [r13 + BootInfo.memory_map], rax
        mov     ecx, STACK_BYTES / 4096
        mov     edx, EfiLoaderData
        call    allocate_low
        test    rax, rax
        jz      fail_allocate
        mov     [r13 + BootInfo.stack_physical], rax
        mov     qword [r13 + BootInfo.stack_size], STACK_BYTES
        mov     ecx, PAGE_TABLE_BYTES / 4096
        mov     edx, EfiLoaderData
        call    allocate_low
        test    rax, rax
        jz      fail_allocate
        mov     [r13 + BootInfo.pml4_physical], rax

        call    collect_graphics
        test    eax, eax
        jnz     fail_gop
        call    draw_boot_logo
        call    collect_rsdp
        test    eax, eax
        jnz     fail_acpi
        call    prepare_page_tables
        lea     rcx, [msg_ready]
        call    serial_write

%if SERVICE_BUNDLE
        ; Independent EfiLoaderData page enters the final UEFI map. Never
        ; allocate inside EBS retries and never reuse BootInfo reserved bytes.
        mov     ecx,1
        mov     edx,EfiLoaderData
        call    allocate_low
        mov     [trace_loader_page],rax
        test    rax,rax
        jz      .trace_allocated
        mov     rdi,rax
        xor     eax,eax
        mov     ecx,512
        rep     stosq
        mov     rdi,[trace_loader_page]
        lea     rsi,[trace_loader_entry]
        call    loader_trace_initialize
        test    rax,rax
        jz      .trace_allocated
        mov     qword [trace_loader_page],0
.trace_allocated:
%endif
        ; From here on the only firmware calls are GetMemoryMap and EBS.
        ; A failed EBS may partially shut down services: retry with a new key
        ; using the already allocated map, never allocate or call protocols.
        mov     ebx, 8
.map_retry:
        mov     qword [r13 + BootInfo.memory_map_size], MAP_CAPACITY
        lea     rcx, [r13 + BootInfo.memory_map_size]
        mov     rdx, [r13 + BootInfo.memory_map]
        lea     r8, [map_key]
        lea     r9, [r13 + BootInfo.descriptor_size]
        lea     rax, [r13 + BootInfo.descriptor_version]
        mov     [rsp + 32], rax
        call    [r12 + EFI_BOOT_SERVICES.GetMemoryMap]
        test    rax, rax
        jnz     fail_map
        cmp     qword [r13 + BootInfo.descriptor_size], EFI_MEMORY_DESCRIPTOR_size
        jb      fail_map
        mov     rcx, [image_handle]
        mov     rdx, [map_key]
%if P1_TEST
        ; Exercise the real stale-key path once without changing the memory map.
        cmp     ebx, 8
        jne     .use_fresh_key
        not     rdx
.use_fresh_key:
%endif
        call    [r12 + EFI_BOOT_SERVICES.ExitBootServices]
        test    rax, rax
        jz      .firmware_exited
        mov     rdx, EFI_INVALID_PARAMETER
        cmp     rax, rdx
        jne     fail_exit
        lea     rcx, [msg_retry]
        call    serial_write            ; Direct UART only; no firmware call.
        dec     ebx
        jnz     .map_retry
        jmp     fail_exit
.firmware_exited:
        cli
%if SERVICE_BUNDLE
        cmp     qword [trace_loader_page],0
        je      .trace_exited
        lea     rdi,[trace_loader_exit]
        call    boot_trace_sample
        mov     rdi,[trace_loader_page]
        lea     rsi,[trace_loader_exit]
        call    loader_trace_ebs
.trace_exited:
%endif
        mov     qword [r13 + BootInfo.flags], 1
        lea     rcx, [msg_ebs]
        call    serial_write
        ; Own GDT and an empty IDT remove dependencies on firmware storage.
        lgdt    [gdt_pointer]
        lidt    [empty_idt]
        mov     ax, 0x10
        mov     ds, ax
        mov     es, ax
        mov     ss, ax
        xor     eax, eax
        mov     fs, ax
        mov     gs, ax
        mov     rsp, [r13 + BootInfo.stack_physical]
        add     rsp, STACK_BYTES
        ; Flush inherited global translations as well as ordinary TLB entries.
        mov     rdx, cr4
        and     rdx, ~0x80               ; CR4.PGE cleared; P2 may enable it again.
        mov     cr4, rdx
        mov     rax, [r13 + BootInfo.pml4_physical]
        mov     cr3, rax
        ; Reload CS via a far return while still on the identity mapping.
        push    qword 0x08
        lea     rax, [.own_cs]
        push    rax
        retfq
.own_cs:
        xor     ebp, ebp
        cld
        mov     rdi, r13
%if SERVICE_BUNDLE
        ; SysV second argument. Kernel must save RSI to owned BSS before calls.
        mov     rsi, [service_handoff_pointer]
%endif
        mov     rax, KERNEL_BASE + IMAGE_ENTRY_OFFSET
        ; SysV function entry alignment, plus a defined fatal return address.
        lea     rdx, [kernel_returned]
        push    rdx
%if SERVICE_BUNDLE
        ; Explicit new entry ABI: RDX PA / RCX signature. RDI160 and RSI96
        ; retain their original contracts. Absent trace cannot pass timing.
        mov     rdx,[trace_loader_page]
        xor     ecx,ecx
        test    rdx,rdx
        jz      .trace_handed_off
        mov     rcx,BOOT_TRACE_MAGIC
.trace_handed_off:
%endif
        jmp     rax

; rcx pages, edx UEFI memory type -> rax physical base or zero.
; Preserves nonvolatile registers. Always reserves pages below 4 GiB.
allocate_low:
        sub     rsp, 40
        mov     r8, rcx
        mov     ecx, AllocateMaxAddress
        mov     dword [rsp + 32], 0xffffffff
        mov     dword [rsp + 36], 0
        lea     r9, [rsp + 32]
        call    [r12 + EFI_BOOT_SERVICES.AllocatePages]
        test    rax, rax
        jnz     .failed
        mov     rax, [rsp + 32]
        add     rsp, 40
        ret
.failed:
        xor     eax, eax
        add     rsp, 40
        ret

; -> eax zero on a validated 32-bit RGB/BGR framebuffer below 4 GiB.
; Preserves nonvolatile registers except r13 BootInfo is written.
collect_graphics:
        sub     rsp, 40
        lea     rcx, [graphics_guid]
        xor     edx, edx
        lea     r8, [graphics]
        call    [r12 + EFI_BOOT_SERVICES.LocateProtocol]
        test    rax, rax
        jnz     .failed
%ifdef DESKTOP_MODE
        mov     rcx, [graphics]
        mov     rdx, r12
        call    desktop_graphics_mode
        test    eax,eax
        jnz     .failed
%endif
        mov     rax, [graphics]
        mov     rax, [rax + EFI_GRAPHICS_OUTPUT_PROTOCOL.Mode]
        test    rax, rax
        jz      .failed
        cmp     qword [rax + EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE.SizeOfInfo], EFI_GRAPHICS_OUTPUT_MODE_INFORMATION_size
        jb      .failed
        mov     rdx, [rax + EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE.Info]
        test    rdx, rdx
        jz      .failed
        cmp     dword [rdx + EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.Version], 0
        jne     .failed
        mov     ecx, [rdx + EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.PixelFormat]
        cmp     ecx, 1                   ; 0=RGB, 1=BGR; no BLT-only or bitmask.
        ja      .failed
        mov     [r13 + BootInfo.pixel_format], rcx
        mov     ecx, [rdx + EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.HorizontalResolution]
        test    ecx, ecx
        jz      .failed
        cmp     ecx, 8192
        ja      .failed
        mov     [r13 + BootInfo.width], rcx
        mov     r8d, [rdx + EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.PixelsPerScanLine]
        cmp     r8, rcx
        jb      .failed
        cmp     r8, 16384
        ja      .failed
        mov     [r13 + BootInfo.stride], r8
        mov     ecx, [rdx + EFI_GRAPHICS_OUTPUT_MODE_INFORMATION.VerticalResolution]
        test    ecx, ecx
        jz      .failed
        cmp     ecx, 8192
        ja      .failed
        mov     [r13 + BootInfo.height], rcx
        imul    r8, rcx
        jo      .failed
        mov     r10, 0x3fffffffffffffff
        cmp     r8, r10
        ja      .failed
        shl     r8, 2
        mov     rcx, [rax + EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE.FrameBufferSize]
        cmp     rcx, r8
        jb      .failed
        mov     [r13 + BootInfo.framebuffer_size], rcx
        mov     rdx, [rax + EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE.FrameBufferBase]
        test    rdx, rdx
        jz      .failed
        mov     [r13 + BootInfo.framebuffer_base], rdx
        add     rcx, rdx
        jc      .failed
        dec     rcx
        shr     rcx, 32
        jnz     .failed                  ; Explicit P1 limit, never truncates MMIO.
        xor     eax, eax
        add     rsp, 40
        ret
.failed:
        mov     eax, 1
        add     rsp, 40
        ret

; Draw the original DongOS D mark directly into the validated GOP buffer.
; Input: r13 BootInfo. Output: 80x80 blue tile at (24,24), white D at (32,32).
; Preserves nonvolatile registers; destroys rax/rcx/rdx/r8-r11 and flags.
; Loader-only, no firmware calls or locks; small screens omit the tile safely.
draw_boot_logo:
        cmp     qword [r13 + BootInfo.width], 104
        jb      .small
        cmp     qword [r13 + BootInfo.height], 104
        jb      .small
        push    rbx
        push    rsi
        push    rdi
        mov     r8, [r13 + BootInfo.stride]
        shl     r8, 2
        mov     rsi, [r13 + BootInfo.framebuffer_base]
        imul    rax, r8, 24
        lea     rsi, [rsi + rax + 24 * 4]
        mov     edx, 0x003768d6          ; RGB bytes adjusted for the GOP format.
        cmp     qword [r13 + BootInfo.pixel_format], 1
        je      .color_ready
        mov     edx, 0x00d66837
.color_ready:
        mov     r9d, 80
.tile_row:
        mov     rdi, rsi
        mov     eax, edx
        mov     ecx, 80
        rep     stosd
        add     rsi, r8
        dec     r9d
        jnz     .tile_row
        mov     rsi, [r13 + BootInfo.framebuffer_base]
        imul    rax, r8, 32
        lea     rsi, [rsi + rax + 32 * 4]
        xor     r9d, r9d
        lea     r10, [logo_bits]
.glyph_row:
        mov     eax, r9d
        shr     eax, 3
        movzx   ebx, byte [r10 + rax]
        mov     rdi, rsi
        xor     r11d, r11d
.glyph_pixel:
        mov     ecx, r11d
        shr     ecx, 3
        mov     edx, 7
        sub     edx, ecx
        bt      ebx, edx
        jnc     .transparent
        mov     dword [rdi], 0x00ffffff
.transparent:
        add     rdi, 4
        inc     r11d
        cmp     r11d, 64
        jb      .glyph_pixel
        add     rsi, r8
        inc     r9d
        cmp     r9d, 64
        jb      .glyph_row
        pop     rdi
        pop     rsi
        pop     rbx
.small:
        ret

; Find ACPI 2.0 configuration table; validate both RSDP checksums and bounds.
; -> eax zero success. Leaf; only volatile registers are destroyed.
collect_rsdp:
        mov     rax, [system_table]
        mov     rcx, [rax + EFI_SYSTEM_TABLE.NumberOfTableEntries]
        mov     rdx, [rax + EFI_SYSTEM_TABLE.ConfigurationTable]
        mov     r8, [acpi2_guid]
        mov     r9, [acpi2_guid + 8]
.next:
        test    rcx, rcx
        jz      .failed
        cmp     [rdx + EFI_CONFIGURATION_TABLE.VendorGuid], r8
        jne     .advance
        cmp     [rdx + EFI_CONFIGURATION_TABLE.VendorGuid + 8], r9
        je      .found
.advance:
        add     rdx, EFI_CONFIGURATION_TABLE_size
        dec     rcx
        jmp     .next
.found:
        mov     rdx, [rdx + EFI_CONFIGURATION_TABLE.VendorTable]
        test    rdx, rdx
        jz      .failed
        mov     rax, rdx
        add     rax, 35
        jc      .failed
        shr     rax, 32
        jnz     .failed
        mov     rax, 0x2052545020445352 ; "RSD PTR " little endian
        cmp     [rdx], rax
        jne     .failed
        cmp     byte [rdx + 15], 2
        jb      .failed
        mov     r9d, [rdx + 20]
        cmp     r9d, 36
        jb      .failed
        cmp     r9d, 4096
        ja      .failed
        lea     rax, [rdx + r9 - 1]
        shr     rax, 32
        jnz     .failed
        xor     eax, eax
        xor     ecx, ecx
.checksum20:
        add     al, [rdx + rcx]
        inc     ecx
        cmp     ecx, 20
        jb      .checksum20
        test    al, al
        jnz     .failed
        xor     eax, eax
        xor     ecx, ecx
.checksum_all:
        add     al, [rdx + rcx]
        inc     ecx
        cmp     ecx, r9d
        jb      .checksum_all
        test    al, al
        jnz     .failed
        mov     [r13 + BootInfo.rsdp], rdx
        xor     eax, eax
        ret
.failed:
        mov     eax, 1
        ret

; Build 4-level tables: 0..4 GiB identity + HHDM alias, and 2 MiB kernel.
; Temporary P1 mappings are supervisor RWX; P2 installs section permissions.
; Input r13 BootInfo; destroys rax, rcx, rdx, r8-r11, rdi (loader-only helper).
prepare_page_tables:
        mov     rdi, [r13 + BootInfo.pml4_physical]
        mov     r11, rdi
        xor     eax, eax
        mov     ecx, PAGE_TABLE_BYTES / 8
        rep     stosq
        lea     rax, [r11 + 4096]
        or      rax, 3
        mov     [r11], rax
        mov     [r11 + 256 * 8], rax
        lea     rax, [r11 + 6 * 4096]
        or      rax, 3
        mov     [r11 + 511 * 8], rax
        lea     rax, [r11 + 7 * 4096]
        or      rax, 3
        mov     [r11 + 6 * 4096 + 510 * 8], rax
        mov     rax, [r13 + BootInfo.kernel_physical]
        or      rax, 0x83
        mov     [r11 + 7 * 4096], rax
        xor     ecx, ecx
.pdpt:
        mov     rax, rcx
        shl     rax, 12
        lea     rax, [r11 + rax + 2 * 4096]
        or      rax, 3
        mov     [r11 + 4096 + rcx * 8], rax
        inc     ecx
        cmp     ecx, 4
        jb      .pdpt
        xor     ecx, ecx
.large_pages:
        mov     rax, rcx
        shl     rax, 21
        or      rax, 0x83
        mov     [r11 + 2 * 4096 + rcx * 8], rax
        inc     ecx
        cmp     ecx, 2048
        jb      .large_pages
        ; MMIO framebuffer pages use PCD/PWT (default PAT UC), including aliases.
        mov     r8, [r13 + BootInfo.framebuffer_base]
        mov     r9, r8
        add     r9, [r13 + BootInfo.framebuffer_size]
        dec     r9
        shr     r8, 21
        shr     r9, 21
.uncached:
        or      qword [r11 + 2 * 4096 + r8 * 8], 0x18
        inc     r8
        cmp     r8, r9
        jbe     .uncached
        lea     rax, [gdt]
        mov     [gdt_pointer + 2], rax
        ret

%macro FAILURE 2
%1:
        lea     rcx, [%2]
        jmp     fatal
%endmacro
FAILURE fail_loaded, msg_fail_loaded
FAILURE fail_watchdog, msg_fail_watchdog
FAILURE fail_filesystem, msg_fail_fs
FAILURE fail_open, msg_fail_open
FAILURE fail_file_size, msg_fail_size
FAILURE fail_allocate, msg_fail_alloc
FAILURE fail_read, msg_fail_read
FAILURE fail_hash, msg_fail_hash
FAILURE fail_unpack, msg_fail_unpack
FAILURE fail_gop, msg_fail_gop
FAILURE fail_acpi, msg_fail_acpi
FAILURE fail_map, msg_fail_map
FAILURE fail_exit, msg_fail_exit
FAILURE kernel_returned, msg_fail_return
%if SERVICE_BUNDLE
FAILURE fail_service_bundle, msg_fail_service_bundle
%endif

; rcx diagnostic string; callable before/after EBS, uses direct I/O only.
fatal:
        call    serial_write
%if P1_TEST
        mov     eax, 0x11
        out     0xf4, eax
%endif
.halt:
        cli
        hlt
        jmp     .halt

; Direct 16550 COM1 setup. Only volatile rax/rdx destroyed.
serial_init:
        mov     dx, 0x3fb
        mov     al, 3
        out     dx, al
        mov     dx, 0x3f9
        xor     eax, eax
        out     dx, al
        mov     dx, 0x3fb
        mov     al, 0x80
        out     dx, al
        mov     dx, 0x3f8
        mov     al, 1
        out     dx, al
        mov     dx, 0x3f9
        xor     eax, eax
        out     dx, al
        mov     dx, 0x3fb
        mov     al, 3
        out     dx, al
        mov     dx, 0x3fa
        mov     al, 0xc7
        out     dx, al
        mov     dx, 0x3fc
        mov     al, 0x0b
        out     dx, al
        ret

; rcx ASCII NUL string; direct COM1 output with bounded waits and final drain.
; Preserves all nonvolatile registers; destroys rax/rcx/rdx/r8/r9.
serial_write:
.next:
        mov     r9b, [rcx]
        test    r9b, r9b
        jz      .drain
        mov     r8d, UART_POLL_LIMIT
        mov     dx, 0x3fd
.wait:
        in      al, dx
        test    al, 0x20
        jnz     .send
        pause
        dec     r8d
        jnz     .wait
        ret
.send:
        mov     dx, 0x3f8
        mov     al, r9b
        out     dx, al
        inc     rcx
        jmp     .next
.drain:
        mov     r8d, UART_POLL_LIMIT
        mov     dx, 0x3fd
.wait_empty:
        in      al, dx
        test    al, 0x40
        jnz     .done
        pause
        dec     r8d
        jnz     .wait_empty
.done:
        ret

        section .rdata
loaded_image_guid: dd 0x5b1b31a1
                   dw 0x9562, 0x11d2
                   db 0x8e,0x3f,0x00,0xa0,0xc9,0x69,0x72,0x3b
filesystem_guid:   dd 0x964e5b22
                   dw 0x6459, 0x11d2
                   db 0x8e,0x39,0x00,0xa0,0xc9,0x69,0x72,0x3b
file_info_guid:    dd 0x09576e92
                   dw 0x6d3f, 0x11d2
                   db 0x8e,0x39,0x00,0xa0,0xc9,0x69,0x72,0x3b
graphics_guid:     dd 0x9042a9de
                   dw 0x23dc, 0x4a38
                   db 0x96,0xfb,0x7a,0xde,0xd0,0x80,0x51,0x6a
acpi2_guid:        dd 0x8868e871
                   dw 0xe4f1, 0x11d3
                   db 0xbc,0x22,0x00,0x80,0xc7,0x3c,0x88,0x81
image_path:        dw __utf16__("\DONGOS.IMG"), 0
logo_bits:         db 0x00,0x7c,0x66,0x63,0x63,0x66,0x7c,0x00
msg_start:         db "DONGOS_P1_START",13,10,0
msg_image:         db "DONGOS_P1_IMAGE_OK",13,10,0
msg_ready:         db "DONGOS_P1_READY",13,10,0
msg_ebs:           db "DONGOS_P1_EBS_OK",13,10,0
msg_retry:         db "DONGOS_P1_EBS_RETRY",13,10,0
msg_fail_loaded:   db "DONGOS_P1_FAIL:E01_LOADED_IMAGE_RANGE",13,10,0
msg_fail_watchdog: db "DONGOS_P1_FAIL:E02_WATCHDOG",13,10,0
msg_fail_fs:       db "DONGOS_P1_FAIL:E03_FILESYSTEM",13,10,0
msg_fail_open:     db "DONGOS_P1_FAIL:E04_IMAGE_OPEN",13,10,0
msg_fail_size:     db "DONGOS_P1_FAIL:E05_IMAGE_SIZE",13,10,0
msg_fail_alloc:    db "DONGOS_P1_FAIL:E06_ALLOCATE_LOW",13,10,0
msg_fail_read:     db "DONGOS_P1_FAIL:E07_IMAGE_READ",13,10,0
msg_fail_hash:     db "DONGOS_P1_FAIL:E08_IMAGE_HASH",13,10,0
msg_fail_unpack:   db "DONGOS_P1_FAIL:E09_IMAGE_UNPACK",13,10,0
msg_fail_gop:      db "DONGOS_P1_FAIL:E10_GOP_MODE_OR_RANGE",13,10,0
msg_fail_acpi:     db "DONGOS_P1_FAIL:E11_ACPI2_RSDP",13,10,0
msg_fail_map:      db "DONGOS_P1_FAIL:E12_MEMORY_MAP_CAPACITY_OR_LAYOUT",13,10,0
msg_fail_exit:     db "DONGOS_P1_FAIL:E13_EXIT_BOOT_SERVICES",13,10,0
msg_fail_return:   db "DONGOS_P1_FAIL:E14_KERNEL_RETURNED",13,10,0
%if SERVICE_BUNDLE
msg_fail_service_bundle: db "DONGOS_P1_FAIL:E15_SERVICE_BUNDLE",13,10,0
%endif

        section .data
        align 8
image_handle:      dq 0
system_table:      dq 0
loaded_image:      dq 0
filesystem:        dq 0
root_file:         dq 0
image_file:        dq 0
image_buffer:      dq 0
kernel_physical:   dq 0
%if SERVICE_BUNDLE
service_handoff_pointer: dq 0
trace_loader_page: dq 0
trace_loader_entry: times 3 dq 0
trace_loader_exit: times 3 dq 0
%endif
graphics:          dq 0
file_info_size:    dq 0
read_size:         dq 0
map_key:           dq 0
        align 8
gdt:               dq 0, 0x00af9a000000ffff, 0x00cf92000000ffff
gdt_end:
gdt_pointer:       dw gdt_end - gdt - 1
                   dq 0
empty_idt:         dw 0
                   dq 0
        align 8
file_info:         times 512 db 0
