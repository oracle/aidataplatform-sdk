#!/usr/bin/env python3
# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
"""Prepare an unresolved credentials create/update body; never execute an API."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from protected_resource_templates import main

if __name__ == "__main__":
    raise SystemExit(main("credentials"))
