# DongOS compiler source input

`lib.compiler_source.load(session, token, scratch, out, result)` connects the
native bounded source loader to the existing `lib.files` H_READ client. Build
with `services`, `lang` and `lang/std` module roots. `result` is a
`bootstrap.guest_source_reader.Result`; its status and publication rules apply.

The caller supplies an initialized session and an already authorized readable
file token. It exclusively borrows the session and its entire 64 KiB channel
until return. All five declared storage regions (session, channel, scratch,
out and result) must be disjoint, including unused tails. Invalid descriptors
return INVALID with no IPC and no changes. Mapped, accessible caller storage
remains the unsafe caller's responsibility.

Reads request at most 61,440 bytes, preserve short reads, and confirm EOF,
including the one-byte exact-capacity probe. Returned lengths exceeding the
requested chunk produce reader.IO with code `PROTOCOL=0x05130001` before any
channel bytes are copied. Transport/server errors retain their code and the
reader's read/probe phase. On failure, scratch may contain partial input; out
is unchanged. The session request/response and channel can change after IPC.

No path is opened here. Root confinement and token authorization belong to
the existing file server and caller; the lexical path gate alone is not
authorization. The adapter never acquires rights, creates or closes grants,
writes, flushes, launches a process, or changes memory/stack limits.

Native debug/release tests use the real files client with a syscall transport
stub to observe H_READ messages and outputs. They do not establish guest
execution, persistence or L3 completion.
