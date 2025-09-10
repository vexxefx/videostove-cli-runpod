# videostove_cli/render.py
# Thin wrapper kept for backward imports; delegates to CLI entrypoint.
from __future__ import annotations
import sys
from videostove_cli.cli import main as _main

if __name__ == "__main__":
    sys.exit(_main())