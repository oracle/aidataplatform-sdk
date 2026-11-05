#!/usr/bin/env python3
"""Prepare an unresolved agents create/update body; never execute an API."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from protected_resource_templates import main

if __name__ == "__main__":
    raise SystemExit(main("agents"))
