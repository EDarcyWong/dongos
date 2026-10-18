# BSP interrupt platform

`irq.platform` owns one BSP xAPIC controller, initially masked IOAPICs, the
8259 interrupt masks, and a rearmed timer. It does not own interrupt entry,
scheduling, page tables, CPU feature setup, or a general IRQ allocator.

## Preconditions and lifetime

`initialize(Inventory*, Views*const, Report*)` consumes the persistent validated
ACPI inventory and `boot.device_policy.Views` (88 bytes). The caller supplies
permanent supervisor RW/NX UC mappings at the fixed device-window slots. The
inventory and mappings must remain valid for the controller's lifetime. Calls
require CPL0 on the BSP with IF, DF, VM, and AC clear. The present profile
requires enabled xAPIC mode, TSC/MSR/APIC capabilities, and at least one IOAPIC;
it rejects pre-enabled x2APIC rather than changing APIC mode.

Initialization checks the actual APIC base, BSP APIC ID and enabled ACPI CPU,
IOAPIC IDs, pin counts and nonoverlapping GSI intervals. It masks both legacy
PICs and every discovered IOAPIC redirection entry, then masks local sources,
sets TPR zero, enables the local APIC, and prepares the timer. It publishes
the output only on success. Initialization is a one-attempt boot operation:
after hardware mutation begins, any error requires a terminal boot path;
neither hardware rollback nor reinitialization is promised.

This version leaves external device IRQs masked. It does not yet expose ISA
routing, AP startup, IPI delivery, NMI routing, SMP clock synchronization, or
hotplug.

## Timer and entry agreement

`arm(ns)` accepts 1 through 1,000,000,000 nanoseconds, while `stop()` masks and
disarms the timer. `describe(Report*)` returns the current 192-byte report.
Rate multiplication, absolute deadlines and counter ranges are checked.

The clock uses a complete CPUID.15H ratio where available. Otherwise HPET or
the ACPI PM timer measures TSC rate over approximately 10 ms. The PM reader
handles 24- and 32-bit wrap. Reference waits have a finite polling bound;
stopped clocks and implausible readings fail. LAPIC divide-16 count rate is
measured against the same reference when one-shot fallback is needed.

CPUID.1 ECX bit24 selects TSC deadline mode. Its xAPIC LVT MMIO write is followed
by MFENCE before writing IA32_TSC_DEADLINE. Without that capability, no deadline
MSR is accessed and each IRQ reloads a calibrated one-shot count. Mode changes
and stop paths explicitly disarm the relevant source.

Vector `0x40` uses a scheduler-owned returning interrupt entry with IST0. After
saving GPR/xstate and dispatching, that entry calls `platform_timer_rearm()` and
requires its zero result, calls `apic_eoi()` exactly once, then restores and
IRETQs. The spurious vector is `0xff` and must return without EOI. These integer
SysV helpers preserve nonvolatile GPRs and do not use SIMD. The scheduler and
CPU-feature initialization must be ready before enabling IF.

## Evidence

Run `python -m unittest tests.test_irq_platform -v`. Three tests cover debug
and release compilation, ELF64/COFF assembly of both generated and hardware
code, report/view layouts, and an independent C register/clock model. Its eight
scenarios cover the deadline/CPUID ratio branch, HPET, both PM widths with wrap,
memory PM, invalid controls, unexpected x2APIC, and a stopped reference clock.
Existing clock cases also exercise max-LVT values 3 through 6 and reject
accesses to absent local registers. Success cases independently observe PIC,
all IOAPIC masks, timer arming/rearming/stopping, and API rejection behavior.

A temporary controller copy removes only the arm-path MFENCE. Both native
build modes compile and link, reach the injected path exactly once, and fail
the independent model's ordering assertion. A build failure is not counted as
a rejected mutation. Every command, output and elapsed time is preserved under
`build/test/p3-irq/host/`; tracked input hashes must remain stable across a run.
This model covers the otherwise unavailable deadline branch; it does not claim
that TCG has delivered a real deadline interrupt. Root-owned QEMU validation
checks actual mapped hardware and returning timer IRQs separately.

## Architecture references

- [Intel SDM official index](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html),
  Vol.3A rev093 chapter13: xAPIC UC/32-bit access, §13.4.8 and §13.5.1 local
  register availability, §13.5.4 timer, §13.5.4.1 deadline ordering, and §13.9
  spurious interrupt behavior. The original rev093 PDF was read locally.
- [Intel official CPUID documentation changes](https://cdrdv2-public.intel.com/825745/252046-sdm-change-document.pdf),
  CPUID leaf15 crystal frequency and ratio fields.
- [Intel HPET 1.0a](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/software-developers-hpet-spec-1-0a.pdf),
  §2.3 capabilities, period, configuration and main counter.
- [Intel 82093AA original datasheet mirror](https://tvsat.com.pl/PDF/8/82093AA_int.pdf),
  selector/window access, pin count and redirection mask.
