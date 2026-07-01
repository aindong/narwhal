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

CONTEXT = "https://schema.org"

# type -> (required, recommended). Kept in sync with audit_schema.py.
TEMPLATES = {
    "Article": (["headline"], ["author", "datePublished", "dateModified", "image", "publisher"]),
    "BlogPosting": (["headline"], ["author", "datePublished", "image"]),
    "NewsArticle": (["headline"], ["author", "datePublished", "image", "publisher"]),
    "Product": (["name"], ["image", "description", "brand", "offers", "aggregateRating", "sku"]),
    "Organization": (["name"], ["url", "logo", "sameAs", "contactPoint"]),
    "LocalBusiness": (["name", "address"], ["telephone", "openingHours", "geo", "priceRange", "url"]),
    "WebSite": (["name", "url"], ["potentialAction"]),
    "BreadcrumbList": (["itemListElement"], []),
    "FAQPage": (["mainEntity"], []),
    "Recipe": (["name", "recipeIngredient", "recipeInstructions"], ["image", "author", "aggregateRating", "cookTime"]),
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
    "offers": {"@type": "Offer", "price": "TODO", "priceCurrency": "USD", "availability": "https://schema.org/InStock"},
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
    return node


def _coerce(value: str):
    v = value.strip()
    if v.startswith(("{", "[")):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return value
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
                    help="print bare JSON without the <script> wrapper")
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
    node = build(args.type, fields, include_recommended=not args.no_recommended)
    blob = json.dumps(node, indent=2, ensure_ascii=False)
    if args.raw:
        print(blob)
    else:
        print('<script type="application/ld+json">')
        print(blob)
        print("</script>")
    if "TODO" in blob:
        print("\n# NOTE: replace all TODO placeholders before publishing.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
