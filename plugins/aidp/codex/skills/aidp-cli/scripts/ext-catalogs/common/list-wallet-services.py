#!/usr/bin/env python3
"""Print only service aliases from a wallet ZIP, never paths or contents."""
import argparse
import json
from catalog_inputs import guarded, wallet_services


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet", required=True, help="Non-secret wallet path supplied in chat; file contents stay private.")
    args = parser.parse_args()
    print(json.dumps({"ok": True, "services": wallet_services(args.wallet)}))


if __name__ == "__main__":
    raise SystemExit(guarded(main))
