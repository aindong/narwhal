"""Optional project configuration via ``narwhal.toml``.

Lets a repo tune the scanner without repeating CLI flags. Precedence is always
**CLI flag > narwhal.toml > built-in default**. Parsing uses stdlib ``tomllib``
(Python 3.11+), falling back to ``tomli`` if installed; when neither is available
the file is ignored (config is a convenience, never required).

Config sections:
  [weights]      severity -> score penalty (critical/high/medium/low)
  [thresholds]   tunable check thresholds (title length, thin content, …)
  [defaults]     default values for CLI flags (fail_under, concurrency, …)
  [ignore]       suppress findings (by category and/or title substring)

A top-level ``[narwhal]`` table is also accepted (so the file can live in a
shared pyproject-style config); its contents are treated as the root.
"""

from __future__ import annotations

import os
import json
from copy import deepcopy
from hashlib import sha256

DEFAULT_WEIGHTS = {"critical": 12, "high": 6, "medium": 3, "low": 1, "good": 0}

DEFAULT_THRESHOLDS = {
    "title_min": 15, "title_max": 65,
    "meta_desc_min": 70, "meta_desc_max": 165,
    "thin_content": 300, "short_content": 600,
    "passage_min": 40, "passage_max": 120,
}

DEFAULT_DEFAULTS = {
    "timeout": 20, "fail_under": None,
    "concurrency": 4, "max_pages": 15, "max_links": 200, "delay": 0.0,
    "sample": 10, "max_sitemaps": 50, "dup_threshold": 90.0,
}


class Config:
    # The source is importable as both lib.config and narwhal.lib.config.
    # A locally declared protocol marker recognizes either built-in class;
    # subclasses do not implicitly declare this layout.
    _comparison_protocol = "narwhal-rule-config-v1"

    def __init__(self, data: dict = None):
        data = data or {}
        self.weights = {**DEFAULT_WEIGHTS, **(data.get("weights") or {})}
        self.thresholds = {**DEFAULT_THRESHOLDS, **(data.get("thresholds") or {})}
        self.defaults = {**DEFAULT_DEFAULTS, **(data.get("defaults") or {})}
        ignore = data.get("ignore") or {}
        self._ignore_categories = {c.lower() for c in ignore.get("categories", [])}
        self._ignore_titles = [t.lower() for t in ignore.get("titles", [])]

    def is_ignored(self, category: str, title: str) -> bool:
        if category.lower() in self._ignore_categories:
            return True
        low = (title or "").lower()
        return any(pat in low for pat in self._ignore_titles)

    def default(self, name, fallback=None):
        val = self.defaults.get(name, fallback)
        return fallback if val is None else val


def _builtin_policy(config):
    """Recognize the built-in policy across source/package import aliases."""
    if type(config).__dict__.get("_comparison_protocol") != Config._comparison_protocol:
        return False
    if "is_ignored" in config.__dict__:
        return False
    method = type(config).__dict__.get("is_ignored")
    return getattr(method, "__code__", None) == Config.is_ignored.__code__


def owned_value(value):
    """Detach plain rule containers without invoking arbitrary copy callbacks.

    Unsupported/deep shapes keep their original behavior and remain unverified.
    The bound is a snapshot limit, not a limit on what an auditor may accept.
    """
    seen = set()

    def plain(item, depth=0):
        if type(item) in (str, int, float, bool, type(None)):
            return True
        if depth > 64 or type(item) not in (dict, list, tuple, set, frozenset):
            return False
        if id(item) in seen:
            return True
        seen.add(id(item))
        children = list(item.keys()) + list(item.values()) if type(item) is dict else item
        return all(plain(child, depth + 1) for child in children)

    if not plain(value):
        return value, False
    try:
        return deepcopy(value), True
    except RecursionError:
        return value, False


def snapshot_rules(config):
    """Own built-in rule inputs for one scan; do not rewrite custom policies."""
    if not _builtin_policy(config):
        return config, False
    data, owned = owned_value({"weights": config.weights, "thresholds": config.thresholds,
                               "categories": config._ignore_categories, "titles": config._ignore_titles})
    if not owned:
        return config, False
    snapshot = Config()
    snapshot.weights, snapshot.thresholds = data["weights"], data["thresholds"]
    snapshot._ignore_categories, snapshot._ignore_titles = data["categories"], data["titles"]
    # Scan budgets/defaults are resolved by the caller, not part of the rules.
    snapshot.defaults = config.defaults
    return snapshot, True


def comparison_fingerprint(config, thresholds, *, weights=None):
    """Opaque provenance for scoring/check rules, not secrets or source paths.

    Unknown custom configuration shapes remain unverified instead of breaking
    a scan. CLI defaults are excluded: resolved rendering/image inputs have
    their own provenance, and crawl/time budgets are not rule definitions.
    """
    if not _builtin_policy(config):
        return None

    def canonical(value):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, dict):
            return {key: canonical(child) for key, child in value.items()}
        if isinstance(value, list):
            return [canonical(child) for child in value]
        return value

    data = {"version": 1, "weights": config.weights if weights is None else weights, "thresholds": thresholds,
            "ignore_categories": sorted(config._ignore_categories),
            "ignore_titles": sorted(set(config._ignore_titles))}
    try:
        encoded = json.dumps(canonical(data), sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        return None
    return sha256(encoded).hexdigest()


def find_config(path: str = None, start: str = None):
    """Locate narwhal.toml: explicit path, else walk up from ``start``/cwd."""
    if path:
        return path if os.path.isfile(path) else None
    directory = os.path.abspath(start or os.getcwd())
    while True:
        candidate = os.path.join(directory, "narwhal.toml")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _read_toml(path: str) -> dict:
    try:
        import tomllib  # noqa: PLC0415  (Python 3.11+)
    except ImportError:
        try:
            import tomli as tomllib  # noqa: PLC0415
        except ImportError:
            return {}
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def load(path: str = None, start: str = None):
    """Return ``(Config, path_or_None)``. Missing/unparseable config -> defaults."""
    found = find_config(path, start)
    data = {}
    if found:
        raw = _read_toml(found)
        data = raw.get("narwhal", raw) if isinstance(raw, dict) else {}
    return Config(data), found


# ---- CLI plumbing shared by scan.py / crawl_site.py / validate_sitemap.py ----
def config_arg_parser():
    """A parent parser exposing --config / --no-config for the tools to inherit."""
    import argparse
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--config", metavar="PATH",
                   help="path to narwhal.toml (default: auto-discover from cwd)")
    p.add_argument("--no-config", action="store_true",
                   help="ignore any narwhal.toml")
    return p


def load_from_args(argv):
    """Pre-parse --config/--no-config and return the resolved Config."""
    known, _ = config_arg_parser().parse_known_args(argv)
    if known.no_config:
        return Config()
    cfg, _found = load(known.config)
    return cfg
