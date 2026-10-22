# G5 tagged values candidate

This candidate extends the checked source-to-native path. It does not construct
target Graph or IR in Python. The seed builds the candidate compiler and is a
separate differential reference for the same target sources.

Optional/result values and payload enums have two words: tag followed by a
zero-initialized scalar payload slot. Absent optional has tag 0, present has 1;
successful result has 0, failure has the declared nonzero u32 error number.
Payload enum tags follow declaration order; enums with no payload use one word.
Narrow signed payloads occupy their low bytes and leave the rest zero, matching
the language's memory representation. Extraction sign-extends by payload type.

`Info.flags` bit 64 identifies implicit payload wrapping; bits 32..63 hold the
original scalar type plus one. Bit 256 records its folded scalar evidence after
wrapping cleared the public scalar flag. Bit 512 identifies error wrapping.
These bits let lowering retain the checked original expression type without
mutating the Graph, reparsing literals, or guessing a call's return type.
Existing TAG and NEVER facts retain their public meaning.

`TAGGED` IR builds a one/two-word value from either an immediate tag or an
evaluated tag slot and an optional scalar payload. Its validator checks every
input and complete output slot before emission. Failed `try` constructs a new
result of the enclosing return type, clears its payload, freezes it across
cleanup calls and returns. `orelse` evaluates its fallback only on absence;
fallback return/break/continue traverses the relevant cleanup chain.

Match evaluates the subject once and holds its snapshot across arms. Pattern
bindings have persistent local slots; error bindings read the tag word, other
payload bindings read the payload word. Frontend exhaustiveness and duplicate
checks apply to nominal enum identity and optional/result/bool patterns.

Validation is in `codex-works/tests/test_g5_tagged_native.py`. Development runs,
independent verification and integration must be recorded separately in the
delivery; this design document is not evidence of a passing test or completed
G5 gate.
