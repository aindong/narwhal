"""Zero-dependency secret resolution for optional API keys (e.g. CRUX_API_KEY).

An API key is a secret, so it must never live in ``narwhal.toml`` (which people
commit). Instead we resolve keys, highest precedence first, from:

  1. an explicit value (a CLI flag like ``--crux-key``),
  2. a real environment variable (best for CI and shell profiles),
  3. a ``.env`` file in the working directory or a parent (best for local dev —
     it's in ``.gitignore`` so it never gets committed).

This is a tiny stdlib parser, not python-dotenv — the toolkit stays dependency-free.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_dotenv(start: str | None = None) -> Path | None:
    """Return the nearest ``.env`` file, searching cwd then each parent."""
    base = Path(start or os.getcwd()).resolve()
    for d in (base, *base.parents):
        candidate = d / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_dotenv(path: str | None = None, *, override: bool = False) -> dict:
    """Parse ``KEY=VALUE`` lines from a ``.env`` into ``os.environ``.

    Ignores blanks and ``#`` comments, tolerates a leading ``export`` and
    surrounding quotes. Existing environment variables win unless ``override``.
    Returns the keys it set (handy for tests/logging)."""
    p = path or find_dotenv()
    if not p:
        return {}
    p = Path(p)
    if not p.is_file():
        return {}
    loaded: dict = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key and (override or key not in os.environ):
            os.environ[key] = val
            loaded[key] = val
    return loaded


def resolve(name: str, cli_value: str | None = None) -> str | None:
    """Resolve a secret ``name``: explicit CLI value > env var > ``.env`` file.

    ``.env`` is only read (once, lazily) when neither of the first two provide a
    value, so unrelated commands never touch the filesystem for secrets."""
    if cli_value:
        return cli_value
    if os.environ.get(name):
        return os.environ[name]
    load_dotenv()
    return os.environ.get(name)
