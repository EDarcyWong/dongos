#!/usr/bin/env python3
"""Start with: python coordination/coordinate.py serve"""
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dongos_coordination.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
