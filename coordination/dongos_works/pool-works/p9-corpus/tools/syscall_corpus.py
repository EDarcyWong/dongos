"""Deterministic syscall/IPC fuzz corpus and strict replay format.

Pure-Python (3.8+) generator/verifier/minimizer for the DongOS userspace
syscall and IPC boundary. It never executes host commands, real syscalls,
devices or a VM; it only builds and strictly validates versioned JSONL text.

The ABI facts are frozen in DISPATCH below with the exact source locations in
`code/`. The test suite re-derives the numeric constants from those sources so
a drifted kernel/ABI reference fails instead of silently producing stale cases.

Determinism: SplitMix64 over integer state only. No floats, no `random`, no
hash iteration order, no locale, no timestamps. `generate(seed, count)` is a
pure function; `generate(seed, n)` is always a prefix of `generate(seed, m)`
for n < m and output is ASCII-only JSON with a fixed key order and "\n" ends.

CLI::

    python syscall_corpus.py generate --seed 0x2a --count 64 --out corpus.jsonl
    python syscall_corpus.py verify corpus.jsonl
    python syscall_corpus.py minimize corpus.jsonl --index 3 --limit 8 --out min.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

FORMAT = "dongos-syscall-corpus"
VERSION = 1
MAX_LINE = 2048
MAX_COUNT = 100000
MAX_MINIMIZE = 16
MAX_DEPTH = 64
MASK64 = (1 << 64) - 1
CORPUS_MAX_BYTES = (MAX_COUNT + 1) * (MAX_LINE + 1) + MAX_LINE

# kernel/exec/elf.dg:14-15 (USER_MIN / USER_LIMIT), duplicated in
# kernel/user/abi.dg:4-5. check_range in kernel/user/memory.dg:704-707 accepts
# only USER_MIN <= address < USER_LIMIT and length <= USER_LIMIT - address.
USER_MIN = 0x1_0000
USER_LIMIT = 0x0000_0080_0000_0000
# kernel/ipc/core.dg:16 (Message.bytes[64]) and services/lib/abi.dg:4
# (Message.words[8]): the user-visible IPC payload is exactly 64 bytes.
MESSAGE_BYTES = 64
# kernel/user/services.dg:1058 rejects log lengths above 4096.
LOG_MAX = 4096
# kernel/ipc/handles.dg:22: generations never wrap and live entries stay below
# MAX_GENERATION; install only reuses generations in 0 < generation < MAX.
MAX_GENERATION = 0x00ff_ffff_ffff_ffff

# kernel/user/services.dg:37-39
CODE_INVALID_CALL = 0x050b0001
CODE_PROTOCOL = 0x050b0002
# kernel/user/memory.dg:31
CODE_INVALID_ADDRESS = 0x04060003
# kernel/ipc/handles.dg:24
CODE_INVALID_HANDLE = 0x04010002

REGISTERS = ("rax", "rdi", "rsi", "rdx", "r10", "r8", "r9")


class Syscall(NamedTuple):
    number: int
    name: str
    args: str
    message_bytes: int
    source: str
    token: str


def _abi(number: int, name: str, args: str, message_bytes: int, source: str,
         token: str) -> Syscall:
    return Syscall(number, name, args, message_bytes, source, token)


# syscall numbers dispatched by kernel/user/services.dg (production service
# dispatcher). `token` is the literal dispatch test in that file, used by the
# tests to detect source drift. kernel/user/runtime.dg is a distinct, smaller
# legacy dispatcher; its extra numbers live in LEGACY below.
DISPATCH: Dict[int, Syscall] = {entry.number: entry for entry in (
    _abi(0x01, "identify", "rdi=magic:0x33", 0, "kernel/user/services.dg:871", "code==1"),
    _abi(0x02, "boot", "none", 0, "kernel/user/services.dg:872", "code==2"),
    _abi(0x03, "yield", "none", 0, "kernel/user/services.dg:873", "code==3"),
    _abi(0x10, "close", "rdi=handle", 0, "kernel/user/services.dg:874-878", "code==0x10"),
    _abi(0x11, "duplicate", "rdi=handle rsi=rights", 0, "kernel/user/services.dg:879", "code==0x11"),
    _abi(0x22, "call", "rdi=endpoint rsi=request:64 rdx=response:64", 64,
         "kernel/user/services.dg:880-898; kernel/ipc/core.dg:16", "code==0x22"),
    _abi(0x23, "receive", "rdi=endpoint rsi=message:64", 64,
         "kernel/user/services.dg:899-907; kernel/ipc/core.dg:16", "code==0x23"),
    _abi(0x25, "take_call", "rdi=endpoint rsi=message:64 rdx=ticket:8", 64,
         "kernel/user/services.dg:908-921", "code==0x25"),
    _abi(0x24, "reply", "rdi=endpoint rsi=ticket rdx=response:64", 64,
         "kernel/user/services.dg:922-945", "code==0x24"),
    _abi(0x26, "reply_wait", "rdi=endpoint rsi=ticket rdx=response:64 r10=next:64", 64,
         "kernel/user/services.dg:922-945", "code==0x26"),
    _abi(0x29, "peer", "rdi=endpoint rsi=ticket", 0, "kernel/user/services.dg:983-997", "code==0x29"),
    _abi(0x2a, "peer_generation", "rdi=endpoint rsi=ticket", 0,
         "kernel/user/services.dg:983-997", "code==0x2a"),
    _abi(0x2b, "peer_rights", "rdi=endpoint rsi=ticket", 0,
         "kernel/user/services.dg:983-997", "code==0x2b"),
    _abi(0x2c, "departed", "rdi=manager", 0, "kernel/user/services.dg:946-952", "code==0x2c"),
    _abi(0x2d, "gui_role", "rdi=endpoint rsi=ticket", 0, "kernel/user/services.dg:953-959", "code==0x2d"),
    _abi(0x2e, "usb_departed", "rdi=manager", 0, "kernel/user/services.dg:960-971", "code==0x2e"),
    _abi(0x2f, "usb_ready", "rdi=manager", 0, "kernel/user/services.dg:972-982", "code==0x2f"),
    _abi(0x60, "configuration_read", "rdi=configuration rsi=offset rdx=out:4", 0,
         "kernel/user/services.dg:998-1004", "code==0x60"),
    _abi(0x61, "configuration_grant", "rdi=configuration rsi=role rdx=out:6*Bar", 0,
         "kernel/user/services.dg:1005-1012", "code==0x61"),
    _abi(0x62, "device_map", "rdi=device", 0, "kernel/user/services.dg:1013", "code==0x62"),
    _abi(0x63, "dma_acquire", "rdi=dma rsi=? rdx=? r10=out:Lease", 0,
         "kernel/user/services.dg:1014-1037", "code==0x63"),
    _abi(0x64, "dma_close", "none (always Busy)", 0, "kernel/user/services.dg:1040", "code==0x64"),
    _abi(0x65, "ahci_enable", "rdi=configuration rsi=?", 0,
         "kernel/user/services.dg:1041-1044", "code==0x65"),
    _abi(0x66, "nvme_enable", "rdi=configuration", 0,
         "kernel/user/services.dg:1045-1049", "code==0x66"),
    _abi(0x67, "xhci_enable", "rdi=configuration", 0,
         "kernel/user/services.dg:1050-1056", "code==0x67"),
    _abi(0x70, "log", "rdi=buffer rsi=length:<=4096", 0,
         "kernel/user/services.dg:1057-1062", "code==0x70"),
    _abi(0x71, "character", "rdi=console", 0, "kernel/user/services.dg:1063-1070", "code==0x71"),
    _abi(0x73, "ticks", "none", 0, "kernel/user/services.dg:1071", "code==0x73"),
    _abi(0x74, "present", "rdi=display", 0, "kernel/user/services.dg:1084-1087", "code==0x74"),
    _abi(0x75, "i8042_read", "rdi=console", 0, "kernel/user/services.dg:1096-1101", "code==0x75"),
    _abi(0x76, "i8042_write", "rdi=console rsi=port rdx=value", 0,
         "kernel/user/services.dg:1096-1101", "code==0x76"),
    _abi(0x77, "font_select", "rdi=display rsi=scale", 0,
         "kernel/user/services.dg:1088-1095", "code==0x77"),
    _abi(0x78, "power", "rdi=power rsi=action", 0, "kernel/user/services.dg:1072-1083", "code==0x78"),
    _abi(0x80, "process_config", "rdi=manager rsi=config rdx=out:Config r10=out:Snapshot?",
         0, "kernel/user/services.dg:568-577", "code==proc.CONFIG"),
    _abi(0x81, "process_spawn", "rdi=manager rsi=config rdx=argument r10=? r8=out:Snapshot",
         0, "kernel/user/services.dg:578-593", "code==proc.SPAWN"),
    _abi(0x82, "process_wait", "rdi=manager rsi=after rdx=out:Event r10=block r8=deadline",
         0, "kernel/user/services.dg:594-605", "code==proc.WAIT"),
    _abi(0x83, "process_kill", "rdi=manager rsi=token rdx=exit", 0,
         "kernel/user/services.dg:606-616", "code==proc.KILL"),
    _abi(0x84, "process_mark_ready", "rdi=endpoint rsi=status", 0,
         "kernel/user/services.dg:561-567", "code==proc.MARK_READY"),
    _abi(0x85, "process_exec", "rdi=manager rsi=image rdx=bytes r10=argument r8=out:Snapshot",
         0, "kernel/user/services.dg:578-593", "code==proc.EXEC"),
    _abi(0x86, "process_incarnation", "rdi=endpoint", 0,
         "kernel/user/services.dg:556-560", "code==0x86"),
    _abi(0x87, "process_runtime", "rdi=manager rsi=out:Runtime", 0,
         "kernel/user/services.dg:524-534", "code==proc.RUNTIME"),
    _abi(0x88, "process_restart", "rdi=manager rsi=config rdx=generation", 0,
         "kernel/user/services.dg:535-542", "code==proc.RESTART_SERVICE"),
    _abi(0x89, "trace_mark", "rdi=mark", 0, "kernel/user/services.dg:543-555", "code==0x89"),
    _abi(0x8a, "compiler_start", "rdi=image", 0,
         "kernel/user/services.dg:857-864", "code==0x8a"),
    _abi(0x90, "device_enumerate", "rdi=manager rsi=cursor rdx=out:Device", 0,
         "kernel/user/services.dg:683-690", "code==dev.ENUMERATE"),
    _abi(0x91, "device_bind", "rdi=manager rsi=token rdx=? r10=out:Binding", 0,
         "kernel/user/services.dg:683-694", "code==dev.BIND"),
    _abi(0x92, "irq_bind", "rdi=console rsi=? rdx=incarnation r10=out:Irq", 0,
         "kernel/user/services.dg:718-727", "code==dev.IRQ_BIND"),
    _abi(0x93, "irq_wait", "rdi=irq rsi=after rdx=out:Irq r10=nonblock r8=deadline", 0,
         "kernel/user/services.dg:728-747", "code==dev.IRQ_WAIT"),
    _abi(0x94, "irq_ack", "rdi=irq rsi=sequence", 0,
         "kernel/user/services.dg:748-752", "code==dev.IRQ_ACK"),
    _abi(0x95, "device_revoke", "rdi=manager rsi=token rdx=?", 0,
         "kernel/user/services.dg:683-701", "code==dev.REVOKE"),
    _abi(0x96, "pci_irq_bind", "rdi=configuration rsi=incarnation rdx=out:Irq", 0,
         "kernel/user/services.dg:704-717", "code==dev.PCI_IRQ_BIND"),
    _abi(0x97, "pci_inventory", "rdi=configuration rsi=cursor rdx=out:Entry", 0,
         "kernel/user/services.dg:1179-1187", "code==pci_inventory_abi.ENUMERATE"),
    _abi(0xa0, "window_allocate", "rdi=endpoint rsi=ticket rdx=? r10=w<<32|h r8=? r9=out:Lease",
         0, "kernel/user/services.dg:665-671", "code==window.ALLOCATE"),
    _abi(0xa1, "window_revoke", "rdi=endpoint rdx=lease", 0,
         "kernel/user/services.dg:644-647", "code==window.REVOKE"),
    _abi(0xa2, "window_font", "rdi=endpoint rsi=ticket rdx=? r10=out:Font", 0,
         "kernel/user/services.dg:672-679", "code==window.FONT"),
    _abi(0xa3, "window_peer", "rdi=endpoint rsi=ticket? rdx=out:Peer", 0,
         "kernel/user/services.dg:648-662", "code==window.PEER"),
    _abi(0xb0, "cap_create", "rdi=out:token rsi=rights", 0,
         "kernel/user/services.dg:791-797", "code==capabi.CREATE"),
    _abi(0xb1, "cap_signal", "rdi=token rsi=bits", 0,
         "kernel/user/services.dg:798-802", "code==capabi.SIGNAL"),
    _abi(0xb2, "cap_take", "rdi=token rsi=mask rdx=out:bits", 0,
         "kernel/user/services.dg:803-809", "code==capabi.TAKE"),
    _abi(0xb3, "cap_call", "rdi=endpoint rsi=out:response rdx=? r10=offer:32", 64,
         "kernel/user/services.dg:820-835", "code==capabi.CALL_CAP"),
    _abi(0xb4, "cap_claim", "rdi=endpoint rsi=ticket rdx=out:Received", 0,
         "kernel/user/services.dg:836-847", "code==capabi.CLAIM"),
    _abi(0xb5, "cap_export", "rdi=endpoint rsi=out:token rdx=rights", 0,
         "kernel/user/services.dg:810-819", "code==capabi.EXPORT_ENDPOINT"),
    _abi(0xb6, "shared_create", "rdi=rights rsi=? rdx=out:token", 0,
         "kernel/user/services.dg:1192-1196", "code==shared_abi.CREATE"),
    _abi(0xb7, "shared_map", "rdi=token rsi=? rdx=out:Mapping", 0,
         "kernel/user/services.dg:1196-1199", "code==shared_abi.MAP"),
    _abi(0xb8, "shared_unmap", "rdi=token", 0,
         "kernel/user/services.dg:1200-1201", "code==shared_abi.UNMAP"),
    _abi(0xb9, "shared_info", "rdi=token rsi=out:Info", 0,
         "kernel/user/services.dg:1202-1206", "code==shared_abi.INFO"),
    _abi(0xfe, "fault", "rdi=status", 0, "kernel/user/services.dg:1111", "code==0xfe"),
    _abi(0xff, "exit", "rdi=status", 0, "kernel/user/services.dg:1102-1110", "code==0xff"),
)}

# kernel/user/runtime.dg:120-196 (legacy two-process runtime dispatcher).
# Kept only to keep "unknown syscall" probes unambiguous across dispatchers.
LEGACY = frozenset({0x01, 0x10, 0x11, 0x22, 0x23, 0x24, 0x26, 0x30, 0x31, 0x40, 0xfe, 0xff})

UNKNOWN_FIXED: Tuple[int, ...] = (
    0x00, 0x04, 0x05, 0x0F, 0x12, 0x13, 0x1F, 0x20, 0x21, 0x27, 0x28, 0x32,
    0x3F, 0x41, 0x42, 0x50, 0x68, 0x69, 0x6A, 0x6F, 0x72, 0x79, 0x7A, 0x7B,
    0x7C, 0x7D, 0x7E, 0x7F, 0x8B, 0x8C, 0x8F, 0x98, 0x99, 0x9F, 0xA4, 0xA5,
    0xAF, 0xBA, 0xBB, 0xBF, 0xC0, 0x100, 0x3FF, 0x408, 0xFFFF, 0x1_0000,
    0x1_0000_0000, 0x7FFF_FFFF_FFFF_FFFF, MASK64,
)

OPERATIONS: Dict[str, Optional[int]] = {
    "syscall.unknown": None,
    "syscall.log": 0x70,
    "syscall.close": 0x10,
    "syscall.duplicate": 0x11,
    "syscall.call": 0x22,
    "syscall.receive": 0x23,
    "syscall.reply": 0x24,
    "syscall.take_call": 0x25,
    "syscall.reply_wait": 0x26,
}

HANDLE_OPERATIONS = (
    "syscall.close", "syscall.duplicate", "syscall.call", "syscall.receive",
    "syscall.reply", "syscall.take_call", "syscall.reply_wait",
)

# Preconditions are explicit, because the dispatcher's shape checks only decide
# a result once the relevant state is declared:
#   none                  - argument shape alone (unknown number, LOG, dead handle)
#   absent_handle_entry   - structurally valid handle with no live entry
#   live_endpoint         - handle holds CALL and names a live endpoint owned by
#                           another managed process (endpoint()/PeerGone pass)
#   live_endpoint_write   - + response 64-byte span mapped user-writable
#   live_endpoint_rw      - + request span mapped user-readable
REQUIRES = ("none", "absent_handle_entry", "live_endpoint",
            "live_endpoint_write", "live_endpoint_rw")

ORACLE_CLASSES = frozenset({
    "invalid_call", "protocol", "invalid_address", "invalid_handle",
    "accepted_shape", "ok",
})

# Handles that can never name a live entry: slot 0, slot > 32, generation 0,
# or generation == MAX_GENERATION (install only reuses 0 < g < MAX, and close
# stops at MAX). kernel/ipc/handles.dg:22,56-82.
HANDLE_STATIC_INVALID: Tuple[int, ...] = (
    0x00, 0x01, 0x21, 0x0100, 0x2000, 0x2021, 0xFFFF,
    0xFFFF_FFFF_FFFF_FF00, 0xFFFF_FFFF_FFFF_FF21,
    0xFFFF_FFFF_FFFF_FF01, 0xFFFF_FFFF_FFFF_FF20,
)

# Structurally valid handles (slot 1..32, generation 1..MAX-1) that are not
# installed by the corpus fixture; replaying them requires an absent entry.
HANDLE_ABSENT: Tuple[int, ...] = (
    0x0101, 0x0102, 0x0103, 0x0A01, 0x2A01, 0x1_0101, 0xFFFF_FFFF_FFFF_FE01,
)

MESSAGE_ADDRESSES: Tuple[int, ...] = (
    USER_MIN, USER_MIN + 0x1000, USER_MIN + 0x10000, 0x10_0000,
    0x1000_0000, 0x7F00_0000, USER_LIMIT - MESSAGE_BYTES,
)

# Request/response pointer probes for CALL. USER_LIMIT - 64 + 64 lands exactly
# on USER_LIMIT (accepted); one byte further overflows check_range. The last
# two values are non-canonical 48-bit forms; check_range only compares against
# USER_MIN/USER_LIMIT, so both are rejected as out-of-range.
CALL_POINTERS: Tuple[int, ...] = (
    0, USER_MIN - 1, USER_MIN, USER_MIN + 1, USER_LIMIT - MESSAGE_BYTES,
    USER_LIMIT - MESSAGE_BYTES + 1, USER_LIMIT, 0x0000_8000_0000_0000,
    0xFFFF_8000_0000_0000, MASK64,
)

LOG_MATRIX: Tuple[Tuple[int, int], ...] = (
    (0, 0), (0, 1), (USER_MIN - 1, 0), (USER_MIN - 1, 1),
    (USER_MIN, 0), (USER_MIN, LOG_MAX + 1), (USER_LIMIT - 1, 0),
    (USER_LIMIT - 1, 2), (USER_LIMIT, 0), (USER_LIMIT, 1),
    (0x0000_8000_0000_0000, 0), (0xFFFF_0000_0000_0000, 0),
    (0x7FFF_FFFF_FFFF_FFFF, 0), (0, LOG_MAX + 1), (MASK64, 0),
)

MESSAGE_MATRIX: Tuple[Tuple[int, ...], ...] = (
    (0,) * 8,
    (1, 0, 0, 0, 0, 0, 0, 0),
    (MASK64,) * 8,
    (0x400, 1, 2, 3, 4, 5, 6, 7),
    (0x0742_0002, 0, 0, 0, 0, 0, 0, 0),
    (0x8000_0000_0000_0000, 0, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 0, 0, 0, 0, MASK64),
    (0x0000_0001_0000_0000, 0xFFFF_FFFF_FFFF_FFFF, 0, 0, 0, 0, 0, 0),
)

FAMILIES: Tuple[Tuple[str, int], ...] = (
    ("unknown", 12),
    ("log", 20),
    ("handle", 22),
    ("stale", 12),
    ("message", 18),
    ("call-pointer", 16),
)

_CASE_KEYS = frozenset({
    "kind", "format", "version", "seed", "index", "operation", "syscall",
    "registers", "message", "oracle", "requires", "abi",
})
_HEADER_KEYS = frozenset({"kind", "format", "version", "seed", "count", "origin"})
_MINIMIZED_HEADER_KEYS = _HEADER_KEYS | {"minimized_from"}

_U64_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
_CODE_RE = re.compile(r"^0x[0-9a-f]{8}$")


class CorpusError(ValueError):
    """Rejected corpus text or arguments; `line` is 1-based (0 = whole input)."""

    def __init__(self, line: int, reason: str) -> None:
        super().__init__(reason)
        self.line = line
        self.reason = reason

    def __str__(self) -> str:
        if self.line:
            return "line %d: %s" % (self.line, self.reason)
        return self.reason


class _Duplicate(Exception):
    pass


def _hook(pairs: Sequence[Tuple[str, object]]) -> Dict[str, object]:
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise _Duplicate(key)
        seen.add(key)
    return dict(pairs)


def _reject_constant(value: str) -> object:
    raise ValueError("non-finite number %r" % value)


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _number_recognised(number: int) -> bool:
    return number in DISPATCH or number in LEGACY


def _handle_invalid(handle: int) -> bool:
    slot = handle & 0xFF
    generation = handle >> 8
    return (slot == 0 or slot > 32 or generation == 0
            or generation >= MAX_GENERATION)


def _regs_dict(values: Sequence[int]) -> Dict[str, int]:
    return {name: int(value) for name, value in zip(REGISTERS, values)}


def _regs_text(registers: Dict[str, int]) -> Dict[str, str]:
    return {name: str(registers[name]) for name in REGISTERS}


def abi_summary(operation: str, number: int) -> Dict[str, object]:
    """Frozen per-record ABI description; the verifier rejects drift."""
    entry = DISPATCH.get(number)
    if operation == "syscall.unknown":
        return {
            "name": "unknown",
            "args": "none",
            "message_bytes": "0",
            "source": "kernel/user/services.dg:849-1114",
        }
    if entry is None:
        raise ValueError("syscall 0x%x has no ABI entry" % number)
    return {
        "name": entry.name,
        "args": entry.args,
        "message_bytes": str(entry.message_bytes),
        "source": entry.source,
    }


def _span_in_range(address: int) -> bool:
    # kernel/user/memory.dg:704-707 range half of check_range (PTE/USER/WRITE
    # checks and copy_alias follow in 709-716 and are preconditions, not shape).
    return (USER_MIN <= address < USER_LIMIT
            and MESSAGE_BYTES <= USER_LIMIT - address)


def classify(operation: str, registers: Dict[str, int],
             message: Optional[Sequence[int]], requires: str) -> Tuple[str, Optional[int]]:
    """Model the dispatcher's documented argument-shape checks.

    Returns (class, error_code). Only results decided by argument shape plus
    the explicitly declared preconditions are produced. `accepted_shape` means
    every shape check passes but the real syscall outcome (mappings, PTE
    permissions, IPC state, scheduling) is deliberately NOT asserted. A case
    whose result needs a precondition that is not declared raises ValueError.
    """
    number = int(registers["rax"])
    if operation == "syscall.unknown":
        if _number_recognised(number):
            raise ValueError("unknown-syscall probe uses a recognised number")
        return "invalid_call", CODE_INVALID_CALL
    if operation == "syscall.log":
        if number != 0x70:
            raise ValueError("log operation must use syscall 0x70")
        address = int(registers["rdi"])
        length = int(registers["rsi"])
        if length > LOG_MAX:  # kernel/user/services.dg:1058
            return "protocol", CODE_PROTOCOL
        # kernel/user/memory.dg:704-707
        if (address < USER_MIN or address >= USER_LIMIT
                or length > USER_LIMIT - address):
            return "invalid_address", CODE_INVALID_ADDRESS
        if length == 0:
            # copy_in is a no-op and services_write_bytes(ptr, 0) returns 0
            # (kernel/services_run.asm:59-84): this is a certain success, not
            # merely a shape pass.
            return "ok", None
        raise ValueError("in-range non-empty log copy depends on live mappings")
    if operation in HANDLE_OPERATIONS:
        if number != OPERATIONS[operation]:
            raise ValueError("operation/syscall number mismatch")
        handle = int(registers["rdi"])
        if _handle_invalid(handle):
            if requires != "none":
                raise ValueError("requires must be none for a dead handle")
            return "invalid_handle", CODE_INVALID_HANDLE
        if requires == "absent_handle_entry":
            return "invalid_handle", CODE_INVALID_HANDLE
        if requires not in ("live_endpoint", "live_endpoint_write",
                           "live_endpoint_rw"):
            raise ValueError("case result is not decided by argument shape alone")
        if operation != "syscall.call":
            raise ValueError("live_endpoint* is only modelled for CALL")
        response = int(registers["rdx"])
        request = int(registers["rsi"])
        # kernel/user/services.dg:880-891: endpoint() and the PeerGone checks
        # precede check_range(rdx, 64, write=True), which precedes copy_in(rsi).
        if not _span_in_range(response):
            if requires in ("live_endpoint_write", "live_endpoint_rw"):
                raise ValueError("declared response mapping is impossible out of range")
            return "invalid_address", CODE_INVALID_ADDRESS
        # The response span is numerically in range. Whether check_range(rdx)
        # actually passes (PTE present, USER, WRITE, copy_alias) is a
        # precondition that `live_endpoint` does not declare.
        if requires == "live_endpoint":
            raise ValueError("response mapping precondition is not declared")
        if not _span_in_range(request):
            if requires == "live_endpoint_rw":
                raise ValueError("declared request mapping is impossible out of range")
            return "invalid_address", CODE_INVALID_ADDRESS
        # The response is declared writable and the request span is in range;
        # deciding the request copy or the IPC state needs `live_endpoint_rw`.
        if requires == "live_endpoint_write":
            raise ValueError("request mapping precondition is not declared")
        return "accepted_shape", None
    raise ValueError("unknown operation %r" % (operation,))


class Stream:
    """SplitMix64 over a single u64 state; pure integer arithmetic."""

    def __init__(self, seed: int) -> None:
        self.state = seed & MASK64

    def u64(self) -> int:
        self.state = (self.state + 0x9E37_79B9_7F4A_7C15) & MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58_476D_1CE4_E5B9) & MASK64
        value = ((value ^ (value >> 27)) * 0x94D0_49BB_1331_11EB) & MASK64
        return value ^ (value >> 31)

    def below(self, bound: int) -> int:
        return self.u64() % bound

    def pick(self, values: Sequence[object]) -> object:
        return values[self.below(len(values))]


def _weighted(stream: Stream, choices: Sequence[Tuple[str, int]]) -> str:
    total = sum(weight for _, weight in choices)
    roll = stream.below(total)
    for name, weight in choices:
        if roll < weight:
            return name
        roll -= weight
    raise AssertionError("weighted choice fell through")


def _noise(stream: Stream) -> int:
    if stream.below(2) == 0:
        return 0
    return int(stream.pick((1, USER_MIN, USER_LIMIT, MASK64, stream.u64())))


def _message(stream: Stream) -> List[int]:
    if stream.below(2) == 0:
        return list(stream.pick(MESSAGE_MATRIX))
    return [stream.u64() for _ in range(8)]


def _case(seed: int, index: int, operation: str, number: int,
          registers: Dict[str, int], message: Optional[List[int]],
          requires: str) -> Dict[str, object]:
    oracle_class, code = classify(operation, registers, message, requires)
    return {
        "kind": "case",
        "format": FORMAT,
        "version": VERSION,
        "seed": str(seed),
        "index": str(index),
        "operation": operation,
        "syscall": str(number),
        "registers": _regs_text(registers),
        "message": None if message is None else [str(word) for word in message],
        "oracle": {
            "class": oracle_class,
            "code": None if code is None else "0x%08x" % code,
        },
        "requires": requires,
        "abi": abi_summary(operation, number),
    }


def _build_case(stream: Stream, seed: int, index: int) -> Dict[str, object]:
    family = _weighted(stream, FAMILIES)
    if family == "unknown":
        if stream.below(2) == 0:
            number = int(stream.pick(UNKNOWN_FIXED))
            values = [number, 0, 0, 0, 0, 0, 0]
        else:
            number = stream.u64()
            guard = 0
            while _number_recognised(number) and guard < 8:
                number = stream.u64()
                guard += 1
            if _number_recognised(number):
                number = int(stream.pick(UNKNOWN_FIXED))
            values = [number] + [stream.u64() for _ in range(6)]
        return _case(seed, index, "syscall.unknown", number,
                     _regs_dict(values), None, "none")
    if family == "log":
        if stream.below(2) == 0:
            address, length = stream.pick(LOG_MATRIX)
        else:
            address = int(stream.pick((
                stream.u64(), USER_MIN - 1, USER_MIN, USER_LIMIT - 1,
                USER_LIMIT, USER_LIMIT + 1, MASK64,
            )))
            length = int(stream.pick((0, 1, 63, 64, LOG_MAX, LOG_MAX + 1,
                                      MASK64, stream.u64())))
            if (USER_MIN <= address < USER_LIMIT and length
                    and length <= USER_LIMIT - address):
                length = 0
        values = [0x70, address, length, 0, 0, 0, 0]
        return _case(seed, index, "syscall.log", 0x70,
                     _regs_dict(values), None, "none")
    if family == "handle":
        operation = str(stream.pick(HANDLE_OPERATIONS))
        number = OPERATIONS[operation]
        handle = int(stream.pick(HANDLE_STATIC_INVALID))
        values = [int(number), handle] + [_noise(stream) for _ in range(5)]
        return _case(seed, index, operation, int(number),
                     _regs_dict(values), None, "none")
    if family == "stale":
        operation = str(stream.pick(HANDLE_OPERATIONS))
        number = OPERATIONS[operation]
        handle = int(stream.pick(HANDLE_ABSENT))
        values = [int(number), handle] + [_noise(stream) for _ in range(5)]
        return _case(seed, index, operation, int(number),
                     _regs_dict(values), None, "absent_handle_entry")
    if family == "message":
        handle = int(stream.pick(HANDLE_ABSENT))
        request = int(stream.pick(MESSAGE_ADDRESSES))
        response = int(stream.pick(MESSAGE_ADDRESSES))
        values = [0x22, handle, request, response, 0, 0, 0]
        return _case(seed, index, "syscall.call", 0x22,
                     _regs_dict(values), _message(stream), "live_endpoint_rw")
    # call-pointer: pick the response first because services.dg:885 validates it
    # before the request copy, then declare exactly the preconditions needed.
    handle = int(stream.pick(HANDLE_ABSENT))
    response = int(stream.pick(CALL_POINTERS))
    request = int(stream.pick(CALL_POINTERS))
    if not _span_in_range(response):
        requires = "live_endpoint"
    elif not _span_in_range(request):
        requires = "live_endpoint_write"
    else:
        requires = "live_endpoint_rw"
    values = [0x22, handle, request, response, 0, 0, 0]
    return _case(seed, index, "syscall.call", 0x22,
                 _regs_dict(values), None, requires)


def _header(seed: int, count: int, origin: str,
            source_index: Optional[int] = None) -> Dict[str, object]:
    header: Dict[str, object] = {
        "kind": "header",
        "format": FORMAT,
        "version": VERSION,
        "seed": str(seed),
        "count": str(count),
        "origin": origin,
    }
    if origin == "minimized":
        header["minimized_from"] = str(0 if source_index is None else source_index)
    return header


def generate(seed: int, count: int) -> bytes:
    """Return the canonical corpus bytes for (seed, count)."""
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= MASK64:
        raise CorpusError(0, "seed must be an integer in 0..2^64-1")
    if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= MAX_COUNT:
        raise CorpusError(0, "count must be an integer in 0..%d" % MAX_COUNT)
    stream = Stream(seed)
    lines = [_dumps(_header(seed, count, "generated"))]
    for index in range(count):
        lines.append(_dumps(_build_case(stream, seed, index)))
    return ("\n".join(lines) + "\n").encode("ascii")


def _u64_field(value: object, what: str, line: int) -> int:
    if not isinstance(value, str) or not _U64_RE.match(value):
        raise CorpusError(line, "%s must be a canonical decimal u64 string" % what)
    number = int(value)
    if number > MASK64:
        raise CorpusError(line, "%s exceeds 2^64-1" % what)
    return number


def _code_field(value: object, line: int) -> str:
    if not isinstance(value, str) or not _CODE_RE.match(value):
        raise CorpusError(line, "oracle code must be null or 0x%08x form")
    return value


def _version_field(value: object, line: int, what: str) -> None:
    # bool is an int subclass and 1.0 compares equal to 1; both must be rejected.
    if type(value) is not int or value != VERSION:
        raise CorpusError(line, "%s version must be the integer %d" % (what, VERSION))


def _exact_keys(obj: Dict[str, object], keys: frozenset, line: int, what: str) -> None:
    missing = sorted(keys - set(obj))
    extra = sorted(set(obj) - keys)
    if missing or extra:
        raise CorpusError(line, "%s fields mismatch (missing=%s extra=%s)"
                          % (what, missing, extra))


def _check_nesting(text: str, line: int) -> None:
    """Lexically cap JSON nesting before any recursive parser sees the line."""
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise CorpusError(line, "JSON nesting depth exceeds %d" % MAX_DEPTH)
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise CorpusError(line, "unbalanced JSON nesting")
    if in_string:
        raise CorpusError(line, "unterminated JSON string")
    if depth != 0:
        raise CorpusError(line, "unterminated JSON nesting")


def _parse_line(text: str, line: int) -> Dict[str, object]:
    if len(text) > MAX_LINE:
        raise CorpusError(line, "line exceeds %d characters" % MAX_LINE)
    if not text or text != text.strip() or text != text.strip("\t"):
        raise CorpusError(line, "line has leading/trailing whitespace")
    _check_nesting(text, line)
    try:
        value = json.loads(text, object_pairs_hook=_hook,
                           parse_constant=_reject_constant)
    except _Duplicate as duplicate:
        raise CorpusError(line, "duplicate field %r" % duplicate.args[0])
    except RecursionError:
        raise CorpusError(line, "JSON nesting exceeds the supported depth")
    except MemoryError:
        raise CorpusError(line, "JSON line exceeds available parsing resources")
    except ValueError as error:
        raise CorpusError(line, "invalid JSON: %s" % error)
    if not isinstance(value, dict):
        raise CorpusError(line, "record is not a JSON object")
    return value


def _validate_header(obj: Dict[str, object], line: int) -> Tuple[int, int, str]:
    if obj.get("kind") != "header":
        raise CorpusError(line, "first record must be the header")
    origin = obj.get("origin")
    if origin not in ("generated", "minimized"):
        raise CorpusError(line, "header origin must be generated or minimized")
    expected = _MINIMIZED_HEADER_KEYS if origin == "minimized" else _HEADER_KEYS
    _exact_keys(obj, expected, line, "header")
    if obj["format"] != FORMAT:
        raise CorpusError(line, "header format must be %r" % FORMAT)
    _version_field(obj["version"], line, "header")
    seed = _u64_field(obj["seed"], "header seed", line)
    count = _u64_field(obj["count"], "header count", line)
    if count > MAX_COUNT:
        raise CorpusError(line, "header count exceeds %d" % MAX_COUNT)
    if origin == "minimized":
        _u64_field(obj["minimized_from"], "minimized_from", line)
    return seed, count, origin


def _validate_case(obj: Dict[str, object], line: int, seed: int,
                   index: int) -> None:
    if obj.get("kind") != "case":
        raise CorpusError(line, "record is not a case")
    _exact_keys(obj, _CASE_KEYS, line, "case")
    if obj["format"] != FORMAT:
        raise CorpusError(line, "case format must be %r" % FORMAT)
    _version_field(obj["version"], line, "case")
    if _u64_field(obj["seed"], "case seed", line) != seed:
        raise CorpusError(line, "case seed does not match the header")
    if _u64_field(obj["index"], "case index", line) != index:
        raise CorpusError(line, "case index must be %d" % index)
    operation = obj["operation"]
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise CorpusError(line, "unknown operation %r" % (operation,))
    number = _u64_field(obj["syscall"], "syscall", line)
    expected_number = OPERATIONS[operation]
    if expected_number is None:
        if _number_recognised(number):
            raise CorpusError(line, "unknown-syscall probe uses a recognised number")
    elif number != expected_number:
        raise CorpusError(line, "syscall does not match operation")
    registers = obj["registers"]
    if not isinstance(registers, dict) or set(registers) != set(REGISTERS):
        raise CorpusError(line, "registers must be exactly %s" % (REGISTERS,))
    values = _regs_dict([_u64_field(registers[name], "register " + name, line)
                         for name in REGISTERS])
    if values["rax"] != number:
        raise CorpusError(line, "registers.rax must equal the syscall number")
    message = obj["message"]
    if message is None:
        message_values = None
    else:
        if not isinstance(message, list) or len(message) != 8:
            raise CorpusError(line, "message must be null or 8 u64 words")
        message_values = [_u64_field(word, "message word", line) for word in message]
        if operation != "syscall.call":
            raise CorpusError(line, "message words are only valid for CALL")
    requires = obj["requires"]
    if not isinstance(requires, str) or requires not in REQUIRES:
        raise CorpusError(line, "unknown requires value %r" % (requires,))
    allowed = {"none"}
    if operation in HANDLE_OPERATIONS:
        allowed.add("absent_handle_entry")
    if operation == "syscall.call":
        allowed.update(("live_endpoint", "live_endpoint_write",
                        "live_endpoint_rw"))
    if requires not in allowed:
        raise CorpusError(line, "requires %r is not valid for %s" % (requires, operation))
    oracle = obj["oracle"]
    if not isinstance(oracle, dict) or set(oracle) != {"class", "code"}:
        raise CorpusError(line, "oracle must contain exactly class and code")
    if not isinstance(oracle["class"], str) or oracle["class"] not in ORACLE_CLASSES:
        raise CorpusError(line, "unknown oracle class %r" % (oracle["class"],))
    try:
        expected_class, expected_code = classify(operation, values, message_values,
                                                 requires)
    except ValueError as error:
        raise CorpusError(line, "case is not decidable from argument shape: %s"
                          % error)
    expected_text = None if expected_code is None else "0x%08x" % expected_code
    if oracle["class"] != expected_class:
        raise CorpusError(line, "oracle class %r != %r"
                          % (oracle["class"], expected_class))
    if oracle["code"] is None:
        if expected_text is not None:
            raise CorpusError(line, "oracle code missing")
    else:
        if _code_field(oracle["code"], line) != expected_text:
            raise CorpusError(line, "oracle code %r != %r"
                              % (oracle["code"], expected_text))
    abi = obj["abi"]
    if not isinstance(abi, dict) or set(abi) != {"name", "args", "message_bytes", "source"}:
        raise CorpusError(line, "abi summary has unexpected fields")
    if not all(isinstance(abi[key], str) for key in ("name", "args", "message_bytes", "source")):
        raise CorpusError(line, "abi summary values must be strings")
    if _u64_field(abi["message_bytes"], "abi message_bytes", line) > MESSAGE_BYTES:
        raise CorpusError(line, "abi message_bytes exceeds %d" % MESSAGE_BYTES)
    expected_abi = abi_summary(operation, number)
    if abi != expected_abi:
        raise CorpusError(line, "abi summary drift: %r" % (abi,))


def verify_bytes(data: bytes) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    """Strictly validate corpus bytes; raise CorpusError on the first defect."""
    if not isinstance(data, (bytes, bytearray)):
        raise CorpusError(0, "corpus must be bytes")
    if len(data) > CORPUS_MAX_BYTES:
        raise CorpusError(0, "corpus file exceeds the bounded size (%d bytes)"
                          % CORPUS_MAX_BYTES)
    if data.startswith(b"\xef\xbb\xbf"):
        raise CorpusError(0, "corpus must not start with a UTF-8 BOM")
    if b"\r" in data:
        raise CorpusError(0, "corpus must use LF line endings")
    if not data:
        raise CorpusError(0, "corpus is empty")
    if not data.endswith(b"\n"):
        raise CorpusError(0, "corpus must end with a newline")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CorpusError(0, "corpus is not valid UTF-8: %s" % error)
    lines = text.split("\n")[:-1]
    if not lines:
        raise CorpusError(0, "corpus is empty")
    for offset, line in enumerate(lines):
        if line == "":
            raise CorpusError(offset + 1, "blank line")
    if any(len(line) > MAX_LINE for line in lines):
        raise CorpusError(0, "a line exceeds %d characters" % MAX_LINE)
    header = _parse_line(lines[0], 1)
    seed, count, origin = _validate_header(header, 1)
    if len(lines) - 1 != count:
        raise CorpusError(0, "header declares %d cases but the file has %d"
                          % (count, len(lines) - 1))
    records: List[Dict[str, object]] = []
    for index in range(count):
        record = _parse_line(lines[index + 1], index + 2)
        _validate_case(record, index + 2, seed, index)
        records.append(record)
    return header, records


def read_bounded(path: Path, limit: int = CORPUS_MAX_BYTES) -> bytes:
    """Read at most limit+1 bytes so an oversized file is never fully buffered."""
    if limit < 0:
        raise CorpusError(0, "read limit must be non-negative")
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise CorpusError(0, "corpus file exceeds the bounded size (%d bytes)"
                          % limit)
    return data


def verify_file(path: Path) -> Tuple[Dict[str, object], List[Dict[str, object]]]:
    return verify_bytes(read_bounded(Path(path)))


def _requires_after(operation: str, registers: Dict[str, int], requires: str) -> str:
    if operation in ("syscall.unknown", "syscall.log"):
        return "none"
    if _handle_invalid(int(registers["rdi"])):
        return "none"
    if operation == "syscall.call" and requires in (
            "live_endpoint", "live_endpoint_write", "live_endpoint_rw"):
        if not _span_in_range(int(registers["rdx"])):
            return "live_endpoint"
        if not _span_in_range(int(registers["rsi"])):
            return "live_endpoint_write"
        return "live_endpoint_rw"
    return requires


def minimize(record: Dict[str, object], limit: int = 8) -> bytes:
    """Return a corpus of bounded same-operation replay candidates.

    Candidates only zero individual registers (and optionally the message
    payload); they are NOT claimed to preserve any failure signal.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_MINIMIZE:
        raise CorpusError(0, "limit must be an integer in 1..%d" % MAX_MINIMIZE)
    if not isinstance(record, dict) or set(record) != _CASE_KEYS:
        raise CorpusError(0, "minimize input must be one validated case record")
    if record.get("kind") != "case":
        raise CorpusError(0, "minimize input is not a case")
    operation = record["operation"]
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise CorpusError(0, "minimize input has an unknown operation")
    number = _u64_field(record["syscall"], "syscall", 0)
    requires = record["requires"]
    if not isinstance(requires, str) or requires not in REQUIRES:
        raise CorpusError(0, "minimize input has an unknown requires value")
    registers = record["registers"]
    if not isinstance(registers, dict) or set(registers) != set(REGISTERS):
        raise CorpusError(0, "minimize input registers are malformed")
    values = _regs_dict([_u64_field(registers[name], name, 0) for name in REGISTERS])
    if values["rax"] != number:
        raise CorpusError(0, "minimize input registers.rax does not match syscall")
    raw_message = record["message"]
    message: Optional[List[int]]
    if raw_message is None:
        message = None
    elif isinstance(raw_message, list) and len(raw_message) == 8:
        message = [_u64_field(word, "message word", 0) for word in raw_message]
    else:
        raise CorpusError(0, "minimize input message is malformed")
    seed = _u64_field(record["seed"], "seed", 0)
    source_index = _u64_field(record["index"], "index", 0)
    try:
        expected_class, expected_code = classify(operation, dict(values), message,
                                                 requires)
    except ValueError as error:
        raise CorpusError(0, "minimize input is not decidable by argument shape: %s"
                          % error)
    expected_text = None if expected_code is None else "0x%08x" % expected_code
    oracle = record["oracle"]
    if not isinstance(oracle, dict) or oracle.get("class") != expected_class \
            or oracle.get("code") != expected_text:
        raise CorpusError(0, "minimize input oracle does not match the ABI model")

    candidates: List[Tuple[Dict[str, int], Optional[List[int]]]] = []
    seen = set()

    def add(new_values: Dict[str, int], new_message: Optional[List[int]]) -> None:
        if len(candidates) >= limit:
            return
        new_requires = _requires_after(operation, new_values, requires)
        try:
            classify(operation, new_values, new_message, new_requires)
        except ValueError:
            return
        key = (tuple(new_values[name] for name in REGISTERS),
               None if new_message is None else tuple(new_message))
        if key in seen:
            return
        seen.add(key)
        candidates.append((new_values, new_message))

    for name in REGISTERS[1:]:
        if len(candidates) >= limit:
            break
        if values[name] == 0:
            continue
        reduced = dict(values)
        reduced[name] = 0
        add(reduced, message)
    if message is not None and len(candidates) < limit and any(message):
        add(dict(values), [0] * 8)

    cases = [_case(seed, index, operation, number, new_values, new_message,
                   _requires_after(operation, new_values, requires))
             for index, (new_values, new_message) in enumerate(candidates)]
    header = _header(seed, len(cases), "minimized", source_index)
    payload = "\n".join([_dumps(header)] + [_dumps(case) for case in cases]) + "\n"
    data = payload.encode("ascii")
    verify_bytes(data)
    return data


def parse_u64_argument(text: str, what: str) -> int:
    if not isinstance(text, str):
        raise CorpusError(0, "%s must be text" % what)
    if re.fullmatch(r"0x[0-9a-fA-F]+", text):
        value = int(text, 16)
    elif re.fullmatch(r"[0-9]+", text):
        value = int(text, 10)
    else:
        raise CorpusError(0, "%s must be decimal digits or 0x-prefixed hex" % what)
    if value > MASK64:
        raise CorpusError(0, "%s exceeds 2^64-1" % what)
    return value


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="syscall_corpus.py",
        description="DongOS deterministic syscall/IPC corpus " + FORMAT + " v%d" % VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="generate a deterministic corpus")
    gen.add_argument("--seed", required=True, help="u64 seed (decimal or 0x hex)")
    gen.add_argument("--count", required=True, help="case count 0..%d" % MAX_COUNT)
    gen.add_argument("--out", required=True, help="output JSONL path")
    ver = sub.add_parser("verify", help="strictly validate a corpus file")
    ver.add_argument("path")
    mini = sub.add_parser("minimize", help="bounded same-operation replay candidates")
    mini.add_argument("path")
    mini.add_argument("--index", default="0", help="source case index")
    mini.add_argument("--limit", default="8", help="candidate limit 1..%d" % MAX_MINIMIZE)
    mini.add_argument("--out", required=True, help="output JSONL path")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            seed = parse_u64_argument(args.seed, "seed")
            if not re.fullmatch(r"[0-9]+", args.count):
                raise CorpusError(0, "count must be decimal digits")
            count = int(args.count, 10)
            data = generate(seed, count)
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_bytes(data)
            print("generated cases=%d bytes=%d sha256=%s"
                  % (count, len(data), hashlib.sha256(data).hexdigest()))
            return 0
        if args.command == "verify":
            data = read_bounded(Path(args.path))
            header, records = verify_bytes(data)
            print("verified cases=%d seed=%s origin=%s sha256=%s"
                  % (len(records), header["seed"], header["origin"],
                     hashlib.sha256(data).hexdigest()))
            return 0
        data = read_bounded(Path(args.path))
        header, records = verify_bytes(data)
        index = parse_u64_argument(args.index, "index")
        if index >= len(records):
            raise CorpusError(0, "index %d is outside 0..%d" % (index, len(records) - 1))
        limit = int(args.limit, 10) if re.fullmatch(r"[0-9]+", args.limit) else -1
        candidates = minimize(records[index], limit)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(candidates)
        _, produced = verify_bytes(candidates)
        print("candidates=%d source_index=%d bytes=%d sha256=%s"
              % (len(produced), index, len(candidates),
                 hashlib.sha256(candidates).hexdigest()))
        return 0
    except CorpusError as error:
        print("error: %s" % error, file=sys.stderr)
        return 3
    except OSError as error:
        print("error: %s" % error, file=sys.stderr)
        return 3
    except (RecursionError, MemoryError) as error:
        print("error: input exceeds parser resources (%s)"
              % type(error).__name__, file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
