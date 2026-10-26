#!/usr/bin/env python3
"""Generate valid schema.org JSON-LD for the common rich-result types.

Emits a ready-to-paste ``<script type="application/ld+json">`` block with the
required and recommended properties for a type, filled from ``--field key=value``
pairs. Unknown required fields are left as clearly-marked TODO placeholders so
nothing silently ships incomplete.

Usage:
    python generate_schema.py Article --field headline="How GEO works" \
        --field author="Jane Doe" --field datePublished=2026-01-15
    python generate_schema.py --list
    python generate_schema.py LocalBusiness --field name="Acme" --pretty
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from .lib.json_input import DuplicateKeyError, unique_object
except ImportError:  # standalone script
    from lib.json_input import DuplicateKeyError, unique_object

CONTEXT = "https://schema.org"

# type -> (required, recommended). Kept in sync with audit_schema.py.
TEMPLATES = {
    "Article": ([], ["headline", "author", "datePublished", "dateModified", "image", "publisher"]),
    "BlogPosting": ([], ["headline", "author", "datePublished", "image"]),
    "NewsArticle": ([], ["headline", "author", "datePublished", "image", "publisher"]),
    "Product": (["name"], ["image", "description", "brand", "url", "offers", "aggregateRating", "sku"]),
    "Organization": (["name"], ["url", "logo", "sameAs", "contactPoint"]),
    "LocalBusiness": (["name", "address"], ["telephone", "openingHours", "geo", "priceRange", "url"]),
    "WebSite": (["name", "url"], ["potentialAction"]),
    "BreadcrumbList": (["itemListElement"], []),
    "FAQPage": (["mainEntity"], []),
    "Recipe": (["name", "image"], ["recipeIngredient", "recipeInstructions", "author", "aggregateRating", "cookTime"]),
    "Event": (["name", "startDate", "location"], ["endDate", "offers", "description", "image"]),
    "JobPosting": (["title", "hiringOrganization", "datePosted"], ["employmentType", "jobLocation", "baseSalary"]),
    "VideoObject": (["name", "thumbnailUrl", "uploadDate"], ["description", "duration", "contentUrl"]),
    "Person": (["name"], ["url", "jobTitle", "sameAs", "image"]),
    "Course": (["name", "provider"], ["description", "offers"]),
}

# Sensible structured placeholders for non-scalar required fields.
STRUCT_PLACEHOLDER = {
    "address": {"@type": "PostalAddress", "streetAddress": "TODO", "addressLocality": "TODO",
                "addressRegion": "TODO", "postalCode": "TODO", "addressCountry": "TODO"},
    "author": {"@type": "Person", "name": "TODO author name"},
    "publisher": {"@type": "Organization", "name": "TODO", "logo": {"@type": "ImageObject", "url": "TODO"}},
    "location": {"@type": "Place", "name": "TODO", "address": "TODO"},
    "hiringOrganization": {"@type": "Organization", "name": "TODO"},
    "provider": {"@type": "Organization", "name": "TODO"},
    "offers": {"@type": "Offer", "price": "TODO current price",
               "priceCurrency": "TODO ISO 4217 currency",
               "availability": "TODO schema.org ItemAvailability",
               "url": "TODO canonical offer URL",
               "itemCondition": "TODO schema.org item condition",
               "seller": {"@type": "Organization", "name": "TODO seller name"}},
    "geo": {"@type": "GeoCoordinates", "latitude": "TODO", "longitude": "TODO"},
    "itemListElement": [{"@type": "ListItem", "position": 1, "name": "TODO", "item": "TODO-url"}],
    "recipeInstructions": ["TODO step 1", "TODO step 2"],
    "recipeIngredient": ["TODO ingredient"],
    "mainEntity": [{"@type": "Question", "name": "TODO question?",
                    "acceptedAnswer": {"@type": "Answer", "text": "TODO answer."}}],
}


def build(type_name: str, fields: dict, include_recommended: bool = True) -> dict:
    if type_name not in TEMPLATES:
        raise SystemExit(f"Unknown type {type_name!r}. Use --list to see supported types.")
    required, recommended = TEMPLATES[type_name]
    node = {"@context": CONTEXT, "@type": type_name}
    keys = list(required) + (recommended if include_recommended else [])
    for key in keys:
        if key in fields:
            node[key] = _coerce(fields[key])
        elif key in required:
            node[key] = STRUCT_PLACEHOLDER.get(key, f"TODO: {key} (required)")
        elif key in STRUCT_PLACEHOLDER:
            node[key] = STRUCT_PLACEHOLDER[key]
        else:
            node[key] = f"TODO: {key} (recommended)"
    # allow arbitrary extra fields the caller passed
    for k, v in fields.items():
        if k not in node:
            node[k] = _coerce(v)
    try:
        # Detach caller fields and shared placeholders, enforcing JSON value types.
        return json.loads(json.dumps(node, allow_nan=False, ensure_ascii=False).encode('utf-8'),
                          object_pairs_hook=unique_object)
    except DuplicateKeyError:
        raise ValueError('Schema fields contain colliding JSON object keys; supply unique string keys.') from None
    except (TypeError, ValueError, RecursionError):
        raise ValueError('Schema fields must be finite UTF-8 JSON-compatible values within supported serialization limits.') from None


def _coerce(value):
    if not isinstance(value, str):
        return value
    v = value.strip()
    if v.startswith(("{", "[")):
        duplicate = False

        def admit_object(pairs):
            nonlocal duplicate
            try:
                return unique_object(pairs)
            except DuplicateKeyError:
                duplicate = True
                return {}

        try:
            decoded = json.loads(v, object_pairs_hook=admit_object)
        except json.JSONDecodeError:
            return value
        except (ValueError, RecursionError):
            raise ValueError('JSON field cannot be decoded within supported parser limits.') from None
        # Defer rejection so malformed JSON keeps its literal-string fallback.
        if duplicate:
            raise ValueError('JSON field contains duplicate object keys; supply unique keys.') from None
        return decoded
    return value


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate schema.org JSON-LD")
    ap.add_argument("type", nargs="?", help="schema type, e.g. Article, Product")
    ap.add_argument("--field", action="append", default=[], metavar="KEY=VALUE",
                    help="set a property (repeatable); value may be JSON")
    ap.add_argument("--list", action="store_true", help="list supported types")
    ap.add_argument("--no-recommended", action="store_true",
                    help="emit only required properties")
    ap.add_argument("--raw", action="store_true",
                    help="print bare JSON without the <script> wrapper (not HTML-escaped)")
    ap.add_argument("--pretty", action="store_true", help="alias for default pretty output")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    if args.list or not args.type:
        print("Supported types:\n  " + "\n  ".join(sorted(TEMPLATES)))
        return 0

    fields = {}
    for item in args.field:
        if "=" not in item:
            raise SystemExit(f"--field must be KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        fields[k.strip()] = v
    try:
        node = build(args.type, fields, include_recommended=not args.no_recommended)
    except ValueError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    blob = json.dumps(node, indent=2, ensure_ascii=False)
    if args.raw:
        print(blob)
    else:
        # JSON quoting alone does not prevent HTML's script-closing delimiter.
        blob = blob.replace('<', '\\u003c')
        print('<script type="application/ld+json">')
        print(blob)
        print("</script>")
    if "TODO" in blob:
        print("\n# NOTE: replace all TODO placeholders before publishing.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
