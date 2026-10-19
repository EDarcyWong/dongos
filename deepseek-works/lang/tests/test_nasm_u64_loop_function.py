"""
Test cases for nasm_u64_loop_function module.
Verifies SysV function interface compliance with u64 return semantics.
"""

import subprocess
import sys


def test_emit_basic():
    """Basic emit test."""
    result = subprocess.run(
        [sys.executable, "-m", "lang.tests.test_nasm_u64_loop_function"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"Test failed: {result.stderr}"


if __name__ == "__main__":
    test_emit_basic()
