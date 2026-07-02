"""Structured-data (schema.org / JSON-LD) auditor.

Parses every ``application/ld+json`` block, validates required properties for the
common rich-result types, flags types Google has deprecated, and notes when a
page that clearly should carry markup (article, product, org) has none.
"""

from __future__ import annotations

import json

try:
    from lib import htmlx
except ImportError:  # when imported as a package
    from .lib import htmlx  # type: ignore

CAT = "schema"

# Types Google has retired as rich results (still valid schema.org, but no longer
# surface features — flag so authors don't invest in them).
DEPRECATED = {
    "HowTo": "HowTo rich results were retired in 2023.",
    "FAQPage": "FAQ rich results are limited to authoritative gov/health sites since 2023.",
    "SpecialAnnouncement": "COVID-era rich result, no longer surfaced.",
    "ClaimReview": "Fact-check rich results restricted to approved publishers.",
}

# Minimal required-property expectations per common type.
REQUIRED = {
    "Article": ["headline"],
    "NewsArticle": ["headline"],
    "BlogPosting": ["headline"],
    "Product": ["name"],
    "Organization": ["name"],
    "LocalBusiness": ["name", "address"],
    "Recipe": ["name", "recipeIngredient", "recipeInstructions"],
    "Event": ["name", "startDate", "location"],
    "JobPosting": ["title", "hiringOrganization", "datePosted"],
    "BreadcrumbList": ["itemListElement"],
    "VideoObject": ["name", "thumbnailUrl", "uploadDate"],
    "Review": ["reviewRating", "author"],
    "Course": ["name", "provider"],
}

RECOMMENDED = {
    "Article": ["author", "datePublished", "image"],
    "Product": ["offers", "image", "brand"],
    "Organization": ["url", "logo"],
    "LocalBusiness": ["telephone", "openingHours", "geo"],
    "Recipe": ["image", "author", "aggregateRating"],
    "Event": ["endDate", "offers"],
    "VideoObject": ["description", "duration"],
}


def audit(doc, resp, report, ctx=None) -> None:
    blobs = doc.scripts_ld
    if not blobs:
        report.add(CAT, "medium", "No structured data (JSON-LD)",
                   "The page has no application/ld+json markup.",
                   "Add JSON-LD for the page's entity (Article, Product, "
                   "Organization…) to unlock rich results and clarify meaning for "
                   "AI search.")
        return

    found_types = []
    for i, blob in enumerate(blobs):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError as exc:
            report.add(CAT, "high", "Invalid JSON-LD",
                       f"Block #{i + 1} does not parse as JSON.",
                       "Fix the JSON syntax; malformed blocks are ignored by search "
                       "engines.", evidence=str(exc))
            continue
        for node in _iter_nodes(data):
            _validate_node(node, found_types, report)

    if found_types:
        report.ok(CAT, "Structured data present",
                  ", ".join(sorted(set(found_types))))
    _cross_checks(doc, found_types, report)


def _iter_nodes(data):
    """Yield every schema object, unwrapping @graph and arrays."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_nodes(item)
    elif isinstance(data, dict):
        if "@graph" in data:
            yield from _iter_nodes(data["@graph"])
        else:
            yield data


def _types_of(node) -> list:
    t = node.get("@type")
    if isinstance(t, list):
        return [str(x) for x in t]
    return [str(t)] if t else []


def _validate_node(node, found_types, report):
    for typ in _types_of(node):
        found_types.append(typ)
        if typ in DEPRECATED:
            report.add(CAT, "low", f"Deprecated rich-result type: {typ}",
                       DEPRECATED[typ],
                       "Keep only if used for meaning; do not expect a rich result.")
        for req in REQUIRED.get(typ, []):
            if req not in node:
                report.add(CAT, "high", f"{typ} missing required '{req}'",
                           f"Schema {typ} lacks the required '{req}' property.",
                           f"Add '{req}' — without it the rich result is invalid.")
        missing_rec = [p for p in RECOMMENDED.get(typ, []) if p not in node]
        if missing_rec:
            report.add(CAT, "low", f"{typ} missing recommended properties",
                       f"Recommended fields absent: {', '.join(missing_rec)}.",
                       f"Add {', '.join(missing_rec)} to strengthen the {typ} entity.")


def _cross_checks(doc, found_types, report):
    has_article = any(t in found_types for t in ("Article", "NewsArticle", "BlogPosting"))
    # Shared page-type heuristic (og:type / published_time / single <article>) —
    # raw text length alone misread text-heavy homepages as articles.
    if htmlx.looks_article(doc) and not has_article:
        report.add(CAT, "low", "Article-like page without Article schema",
                   "Long-form content with no Article/BlogPosting markup.",
                   "Add Article JSON-LD (headline, author, datePublished) to aid "
                   "rich results and AI attribution.")
    if not any(t in found_types for t in ("Organization", "LocalBusiness", "WebSite")):
        report.add(CAT, "low", "No Organization/WebSite entity",
                   "No site-level Organization or WebSite markup detected.",
                   "Add Organization + WebSite JSON-LD (typically sitewide) to "
                   "establish the publishing entity.")
