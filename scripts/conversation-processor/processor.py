"""Standalone entry point; no persona or downstream-engine imports."""
import sys
sys.dont_write_bytecode = True
from conversation_processor.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
