#!/usr/bin/env python3
"""Synchronize plugin manifests with the canonical Python release version.

Run ``python scripts/sync_version.py --check`` to reject drift without edits.
"""

import argparse
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = Path("skills/seo-scan/scripts/_version.py")
MANIFESTS = (
    (Path(".claude-plugin/plugin.json"), ("version",)),
    (Path(".claude-plugin/marketplace.json"), ("metadata", "version")),
)


def read_version(root=ROOT):
    """Read the literal version without importing the runtime package."""
    tree = ast.parse((root / VERSION_PATH).read_text(encoding="utf-8"))
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__"
                        for target in node.targets)]
    if len(versions) != 1 or not isinstance(versions[0], str) or not re.fullmatch(
            r"\d+\.\d+\.\d+", versions[0]):
        raise ValueError("Canonical version must be one literal X.Y.Z release version")
    return versions[0]


def synchronize(root=ROOT, *, check=False):
    """Return stale paths; update them only outside read-only check mode."""
    version = read_version(root)
    updates = []
    # Validate every input before writing any manifest.
    for relative, keys in MANIFESTS:
        data = json.loads((root / relative).read_text(encoding="utf-8"))
        owner = data
        for key in keys[:-1]:
            owner = owner[key]
        if owner[keys[-1]] != version:
            owner[keys[-1]] = version
            updates.append((relative, data))
    if not check:
        for relative, data in updates:
            with (root / relative).open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return [relative for relative, _ in updates]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on version drift without edits")
    args = parser.parse_args(argv)
    try:
        stale = synchronize(check=args.check)
        version = read_version()
    except (OSError, ValueError, KeyError, TypeError, SyntaxError) as exc:
        print(f"Version synchronization failed: {exc}", file=sys.stderr)
        return 1
    if stale and args.check:
        print("Version drift: " + ", ".join(map(str, stale)), file=sys.stderr)
        print("Run python scripts/sync_version.py", file=sys.stderr)
        return 1
    print(f"Version {version}: " + ("updated " + ", ".join(map(str, stale))
                                    if stale else "all manifests match"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
