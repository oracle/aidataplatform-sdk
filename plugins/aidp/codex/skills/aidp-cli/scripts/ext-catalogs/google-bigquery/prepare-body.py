#!/usr/bin/env python3
"""Prepare an unresolved GOOGLE_BIGQUERY catalog create/test body."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from protected_catalog_templates import main

if __name__ == "__main__":
    raise SystemExit(main("GOOGLE_BIGQUERY"))
