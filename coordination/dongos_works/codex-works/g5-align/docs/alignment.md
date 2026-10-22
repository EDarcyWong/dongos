# G5 dynamic aligned frames candidate

FRAME_ALIGNMENT records the maximum required local-object alignment without
changing any public IR descriptor size. Slot allocation uses actual type layout
alignment. The emitter keeps RBP as the incoming-stack anchor and, for alignment
above 16, saves R12, aligns RSP, uses R12 for local slots, and restores R12/RSP at
each return. All IR consumers use the same frame base, including tagged payload
loads, atomic desired values, indirect targets and aggregate addresses.

The budget includes body storage, outgoing calls, saved frame state, worst-case
alignment loss and any outer Win64 wrapper. Failure publishes no target output.
Tests compare actual object addresses/copies and stack arguments against seed
and C, execute a Win64 entry with an aligned body, reject an oversized frame,
and run a wrong-address compiler variant against the same independent oracle.
Development/independent/integration results belong in the task delivery.
