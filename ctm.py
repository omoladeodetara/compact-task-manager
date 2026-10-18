#!/usr/bin/env python3
"""Shared command entry point. Diagnostics require only the Python standard library."""
import sys
sys.dont_write_bytecode = True
from portable.cli import main

if __name__ == "__main__":
    sys.exit(main())
