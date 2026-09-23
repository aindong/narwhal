#!/usr/bin/env python3
"""Regenerate the committed full-report snapshots."""

from golden_reports import write_snapshots


if __name__ == "__main__":
    for path in write_snapshots():
        print(f"updated {path}")
