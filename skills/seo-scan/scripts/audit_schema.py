"""Structured-data (schema.org / JSON-LD, Microdata and bounded RDFa) auditor.

Parses every ``application/ld+json`` block, validates required properties for the
common rich-result types, flags types Google has deprecated, and notes when a
page that clearly should carry markup (article, product, org) has none.
"""

from __future__ import annotations

try:
    from lib import ecommerce, htmlx, structured_data
except ImportError:  # when imported as a package
    from .lib import ecommerce, htmlx, structured_data  # type: ignore

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
    "Organization": ["url", "logo"],
    "LocalBusiness": ["telephone", "openingHours", "geo"],
    "Recipe": ["image", "author", "aggregateRating"],
    "Event": ["endDate", "offers"],
    "VideoObject": ["description", "duration"],
}


def audit(doc, resp, report, ctx=None) -> None:
    blobs = doc.scripts_ld
    records, errors = structured_data.collect(doc)
    report.meta["structured_data"] = structured_data.provenance(doc, records)
    if doc.microdata_warnings:
        warning = "\n".join(doc.microdata_warnings)
        report.add(CAT, "low", "Microdata extraction needs verification",
                   warning, "Check item scopes, URLs and itemref targets; validate the rendered markup with the schema.org validator.",
                   evidence=warning, rule_id="schema.microdata.extraction")
    if doc.rdfa_warnings:
        warning = "\n".join(doc.rdfa_warnings)
        report.add(CAT, "low", "RDFa extraction needs verification",
                   warning, "Check RDFa subjects, vocabulary and coverage limits; validate the rendered markup with the schema.org validator.",
                   evidence=warning, rule_id="schema.rdfa.extraction")
    if not blobs and not any(structured_data.types(r["node"]) for r in records):
        # Hub/index pages have no single entity to mark up — absence there is a
        # note, not a real gap (articles/products/homepages keep medium).
        hub = htmlx.is_hub_page(doc)
        report.add(CAT, "low" if hub else "medium",
                   "No structured data",
                   "No JSON-LD, typed Microdata or supported schema.org RDFa was detected.",
                   "Add JSON-LD for the page's entity (Article, Product, "
                   "Organization…) to unlock rich results and clarify meaning for "
                   "AI search."
                   + (" (Least critical on listing/index pages.)" if hub else ""),
                   rule_id="schema.no.structured.data")
        report.meta["ecommerce"] = ecommerce.audit(doc, report)
        return

    found_types = []
    for block, error in errors:
        report.add(CAT, "high", "Invalid JSON-LD",
                   f"Block #{block} could not be parsed or processed as JSON-LD.",
                   "Fix the JSON syntax or excessive nesting; malformed blocks are ignored by search "
                   "engines.", evidence=error)
    # Validate shared unique objects, including nested Microdata/RDFa entities.
    # Distinct defective variants remain evidence, but score a given rule once.
    start = len(report.findings)
    for record in records:
        _validate_node(record["node"], found_types, report)
    kept, seen = report.findings[:start], {}
    for finding in report.findings[start:]:
        if finding.rule_id not in seen:
            kept.append(finding)
            seen[finding.rule_id] = finding
        elif finding.detail not in seen[finding.rule_id].detail:
            seen[finding.rule_id].detail += " Additional node: " + finding.detail
    report.findings = kept

    if found_types:
        report.ok(CAT, "Structured data present",
                  ", ".join(sorted(set(found_types))))
    _cross_checks(doc, found_types, report)
    report.meta["ecommerce"] = ecommerce.audit(doc, report)


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
