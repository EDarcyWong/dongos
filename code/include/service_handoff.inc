; Independent boot extension; BootInfo v1 is unchanged. All addresses are PA.
%ifndef DONGOS_SERVICE_HANDOFF_INC
%define DONGOS_SERVICE_HANDOFF_INC
SERVICE_HANDOFF_MAGIC equ 0x31444e4148565344 ; "DSVHAND1"
SERVICE_HANDOFF_VERSION equ 1
SERVICE_HANDOFF_LOADED equ 1             ; loaded bytes, not an authentication claim
SERVICE_BUNDLE_MAX_BYTES equ 64 * 1024 * 1024
SERVICE_ARENA_BYTES equ 128 * 1024 * 1024
SERVICE_ARENA_PAGES equ SERVICE_ARENA_BYTES / 4096
struc ServiceHandoff
    .magic:             resq 1
    .version:           resq 1
    .size:              resq 1
    .flags:             resq 1
    .bundle_physical:   resq 1
    .bundle_bytes:      resq 1
    .bundle_pages:      resq 1
    .arena_physical:    resq 1
    .arena_bytes:       resq 1
    .arena_pages:       resq 1
    .self_physical:     resq 1
    .checksum:          resq 1 ; sum of all12 u64 fields modulo2^64 is0
endstruc
%if ServiceHandoff_size != 96
%error ServiceHandoff ABI must be96 bytes
%endif
%endif
