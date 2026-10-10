"""One normalized, format-aware node view for schema and commerce consumers."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from .microdata import schema_name

NUMERIC_PROPERTIES = {"price", "lowPrice", "highPrice", "offerCount", "ratingValue", "reviewCount", "ratingCount"}


def _normalize(value, memo=None):
    memo = {} if memo is None else memo
    if isinstance(value, (dict, list)) and id(value) in memo:
        return memo[id(value)]
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            if key == "@context":
                continue
            if key == "@type":
                normalized = ([schema_name(t) if isinstance(t, str) else t for t in child]
                              if isinstance(child, list) else schema_name(child) if isinstance(child, str) else child)
                if isinstance(normalized, list) and all(isinstance(t, str) for t in normalized):
                    normalized = sorted(set(normalized))
                out[key] = (normalized[0] if isinstance(normalized, list) and len(normalized) == 1
                            else normalized)
            else:
                out[key] = _normalize(child, memo)
        memo[id(value)] = out
        return out
    if isinstance(value, list):
        normalized = [_normalize(child, memo) for child in value]
        out = normalized[0] if len(normalized) == 1 else normalized
        memo[id(value)] = out
        return out
    return value


def _walk(data, seen=None):
    seen = set() if seen is None else seen
    if isinstance(data, (dict, list)):
        if id(data) in seen:
            return
        seen.add(id(data))
    if isinstance(data, list):
        for child in data:
            yield from _walk(child, seen)
    elif isinstance(data, dict):
        yield data
        for child in data.values():
            if isinstance(child, (dict, list)):
                yield from _walk(child, seen)


def _fingerprint(value, memo, prop=""):
    """Hash shared itemref subtrees once, avoiding exponential JSON expansion."""
    if not isinstance(value, (dict, list)):
        if prop in NUMERIC_PROPERTIES and isinstance(value, (str, int, float)) and not isinstance(value, bool):
            try:
                number = Decimal(str(value))
                if number.is_finite():
                    sign, digits, exponent = number.as_tuple()
                    digits = list(digits)
                    while len(digits) > 1 and digits[-1] == 0:
                        digits.pop()
                        exponent += 1
                    if not any(digits):
                        sign, exponent = 0, 0
                    # Exact coefficient/exponent equality, without Decimal's
                    # context rounding accidentally folding conflicting prices.
                    number_key = json.dumps([sign, digits, exponent])
                    return sha256(("number:" + number_key).encode("utf-8")).digest()
            except InvalidOperation:
                pass
        if prop in {"availability", "itemCondition"} and isinstance(value, str):
            value = schema_name(value)
        return sha256(json.dumps(value, ensure_ascii=False).encode("utf-8")).digest()
    if id(value) in memo:
        return memo[id(value)]
    digest = sha256(b"dict" if isinstance(value, dict) else b"list")
    if isinstance(value, dict):
        for key in sorted(value):
            digest.update(sha256(key.encode("utf-8")).digest())
            digest.update(_fingerprint(value[key], memo, key))
    else:
        for child in value:
            digest.update(_fingerprint(child, memo))
    memo[id(value)] = digest.digest()
    return memo[id(value)]


def collect(doc):
    """Return unique node records with source formats, plus JSON syntax errors.

    Only equal normalized objects are folded. Conflicting copies and different
    variants remain observable; a matching @id alone never overwrites evidence.
    """
    records, by_value, errors = [], {}, []

    def add(data, source):
        fingerprints = {}
        for node in _walk(_normalize(data)):
            key = _fingerprint(node, fingerprints)
            if key in by_value:
                record = by_value[key]
                if source not in record["formats"]:
                    record["formats"].append(source)
            else:
                record = {"node": node, "formats": [source]}
                by_value[key] = record
                records.append(record)

    for i, blob in enumerate(doc.scripts_ld):
        try:
            add(json.loads(blob), "jsonld")
        except (ValueError, TypeError, RecursionError) as exc:
            errors.append((i + 1, str(exc)))
    add(doc.microdata, "microdata")
    return records, errors


def types(node):
    raw = node.get("@type")
    return [t for t in (raw if isinstance(raw, list) else [raw]) if isinstance(t, str)]


def provenance(doc, records):
    """Small serializable coverage summary; raw markup is never copied here."""
    by_format = {}
    for record in records:
        node_types = types(record["node"])
        if node_types:
            for source in record["formats"]:
                by_format.setdefault(source, set()).update(node_types)
    return {"formats": sorted(by_format),
            "types_by_format": {source: sorted(found) for source, found in sorted(by_format.items())},
            "nodes_count": sum(bool(types(r["node"])) for r in records),
            "microdata_warnings": doc.microdata_warnings,
            "rdfa_supported": False}
