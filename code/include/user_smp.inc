; Candidate unified kernel GS layout. Prefix is the existing 64B UserCpu,
; followed by a pointer to the unchanged 256B SmpContext. No production entry
; currently installs this layout; all SMP handlers must switch together.
%ifndef DONGOS_USER_SMP_INC
%define DONGOS_USER_SMP_INC
%include "user_context.inc"
%include "smp.inc"
USER_SMP_RESCHEDULE_VECTOR equ 0xf4
struc UserSmpCpu
 .prefix: resb UserCpu_size
 .smp: resq 1
 .domain: resq 1
 .logical_id: resq 1
 .contexts: resq 1
 .context_count: resq 1
 .pcid_enabled: resq 1
endstruc
%endif
