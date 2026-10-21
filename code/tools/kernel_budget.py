"""Explicit existing backend selection for the bounded service kernel image."""

def kernel_flags(runtime_level):
    # SSA retains ordered memory and falls back per whole unsupported body.
    # Other images keep their original debug/backend policy and default ABI.
    return ["--function-sections", "-O1"] if runtime_level >= 5 else []
