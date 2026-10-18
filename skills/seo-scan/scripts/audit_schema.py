"""Structured-data (schema.org / JSON-LD, Microdata and bounded RDFa) auditor.

Parses every ``application/ld+json`` block, validates required properties for the
common rich-result types, flags types Google has deprecated, and notes when a
page that clearly should carry markup (article, product, org) has none.
"""

from __future__ import annotations

try:
    from lib import ecommerce, htmlx, microdata, structured_data, schema_appearance, schema_coverage
except ImportError:  # when imported as a package
    from .lib import ecommerce, htmlx, microdata, structured_data, schema_appearance, schema_coverage  # type: ignore

CAT = "schema"

# Preserve existing module names while sharing one dated, offline snapshot.
FEATURE_STATUS_CHECKED = schema_appearance.FEATURE_STATUS_CHECKED
DEPRECATED = schema_appearance.DEPRECATED
DEPRECATED_SOURCES = schema_appearance.DEPRECATED_SOURCES
DEPRECATED_ADDITIONAL_SOURCES = schema_appearance.DEPRECATED_ADDITIONAL_SOURCES

# Minimal required-property expectations per common type.
REQUIRED = {
    "Organization": ["name"],
    "LocalBusiness": ["name", "address"],
    "Recipe": ["name", "image"],
    "Event": ["name", "startDate", "location"],
    "JobPosting": ["title", "hiringOrganization", "datePosted"],
    "BreadcrumbList": ["itemListElement"],
    "VideoObject": ["name", "thumbnailUrl", "uploadDate"],
    "Review": ["reviewRating", "author"],
    "Course": ["name", "provider"],
}

ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting"}
ARTICLE_SOURCE = "https://developers.google.com/search/docs/appearance/structured-data/article"
ARTICLE_STATUS_CHECKED = "2026-10-12"
ARTICLE_FIELDS = ["headline", "author", "datePublished", "image"]
RECIPE_SOURCE = "https://developers.google.com/search/docs/appearance/structured-data/recipe"
RECIPE_STATUS_CHECKED = "2026-10-12"
RECIPE_FIELDS = ["recipeIngredient", "recipeInstructions", "author", "aggregateRating"]

RECOMMENDED = {
    **{typ: list(ARTICLE_FIELDS) for typ in sorted(ARTICLE_TYPES)},
    "Organization": ["url", "logo"],
    "LocalBusiness": ["telephone", "openingHours", "geo"],
    "Recipe": list(RECIPE_FIELDS),
    "Event": ["endDate", "offers"],
    "VideoObject": ["description", "duration"],
}


def _field_value_present(value, depth=0):
    """Absence/blank evidence only, not datatype or reference validation."""
    if depth >= 16:
        return True  # unknown deeply nested shape, not proven absent
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_field_value_present(child, depth + 1) for child in value)
    if isinstance(value, dict):
        if not value:
            return False
        if "@value" in value and set(value) <= {"@value", "@language", "@type", "@direction", "@index"}:
            return _field_value_present(value["@value"], depth + 1)
    return True  # preserve non-empty references/unknown shapes, not validity


def _article_policy(typ, report):
    policy = report.meta.setdefault("structured_data", {}).setdefault("article_field_policy", {
        "scope": "Google Article-family field recommendations, not full eligibility or schema.org validity",
        "required_properties": [], "checked_recommendations": list(ARTICLE_FIELDS),
        "checked_on": ARTICLE_STATUS_CHECKED, "source": ARTICLE_SOURCE, "observed_types": [],
    })
    if typ not in policy["observed_types"]:
        policy["observed_types"].append(typ)
        policy["observed_types"].sort()


def _recipe_policy(report):
    """Record offline base-field expectations without claiming full eligibility."""
    report.meta.setdefault("structured_data", {}).setdefault("recipe_field_policy", {
        "scope": "Google Recipe base-field presence, not full eligibility or schema.org validity",
        "required_properties": list(REQUIRED["Recipe"]),
        "checked_recommendations": list(RECIPE_FIELDS),
        "checked_on": RECIPE_STATUS_CHECKED, "source": RECIPE_SOURCE,
        "not_checked": ["conditional nutrition/yield and time relationships", "nested steps/sections",
                        "image crawlability and dish/content suitability", "datatype/language/reference validation"],
    })


def audit(doc, resp, report, ctx=None) -> None:
    blobs = doc.scripts_ld
    records, errors = structured_data.collect(doc)
    report.meta["structured_data"] = structured_data.provenance(doc, records)
    report.meta['structured_data']['extraction_coverage'] = schema_coverage.observe(doc, errors)
    if doc.microdata_warnings:
        warning = "\n".join(doc.microdata_warnings)
        report.add(CAT, "low", "Microdata extraction needs verification",
                   warning, ("Check item scopes, URLs and itemref targets; validate the rendered markup with the schema.org validator. "
                             + microdata.warning_summary(doc.microdata_warnings)).strip(),
                   evidence=warning, rule_id="schema.microdata.extraction")
    if doc.rdfa_warnings:
        warning = "\n".join(doc.rdfa_warnings)
        report.add(CAT, "low", "RDFa extraction needs verification",
                   warning, ("Check RDFa subjects, vocabulary and coverage limits; validate the rendered markup with the schema.org validator. "
                             + microdata.warning_summary(doc.rdfa_warnings)).strip(),
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


def _feature_notice(typ, report):
    source = DEPRECATED_SOURCES[typ]
    additional = DEPRECATED_ADDITIONAL_SOURCES.get(typ, [])
    notices = report.meta.setdefault("structured_data", {}).setdefault("google_rich_result_notices", [])
    if not any(notice["type"] == typ for notice in notices):
        notices.append(schema_appearance.notice(typ))
    # Config ignores use title substrings, not rule IDs. Honor the old title
    # as well as the new presentation; factual provenance remains available.
    if report.ignore and report.ignore(CAT, f"Deprecated rich-result type: {typ}"):
        return
    sources = "; ".join([source] + additional)
    other_use = "ClaimReview remains supported by Fact Check Explorer. " if typ == "ClaimReview" else ""
    report.add(CAT, "low", f"Retired Google rich-result feature: {typ}",
               DEPRECATED[typ],
               "Retain accurate markup if useful for semantic meaning or other consumers; do not expect this Google Search rich-result feature. "
               "Retirement alone does not invalidate schema.org markup or establish a ranking penalty. "
               + other_use + f"Google sources (checked {FEATURE_STATUS_CHECKED}): {sources}",
               # Keep the historical identity despite clearer wording.
               rule_id=f"schema.deprecated.rich.result.type.{typ.lower()}")


def _validate_node(node, found_types, report):
    for typ in _types_of(node):
        found_types.append(typ)
        if typ in DEPRECATED:
            _feature_notice(typ, report)
        if typ in ARTICLE_TYPES:
            _article_policy(typ, report)
        if typ == "Recipe":
            _recipe_policy(report)
        for req in REQUIRED.get(typ, []):
            absent = not _field_value_present(node.get(req)) if typ == "Recipe" else req not in node
            if absent:
                recipe = typ == "Recipe"
                report.add(CAT, "high", f"{typ} missing required '{req}'",
                           f"Recipe '{req}' is absent or blank; Google requires it for Recipe rich results."
                           if recipe else f"Schema {typ} lacks the required '{req}' property.",
                           (f"Add an accurate {'completed-dish image' if req == 'image' else 'dish name'} matching the page. "
                            f"This is a base-field check, not full eligibility or schema.org validity; verify conditional, nested and image requirements separately. Source: {RECIPE_SOURCE}")
                           if recipe else f"Add '{req}' — without it the rich result is invalid.")
        if typ in ARTICLE_TYPES or typ == "Recipe":
            missing_rec = [p for p in RECOMMENDED[typ] if not _field_value_present(node.get(p))]
        else:
            missing_rec = [p for p in RECOMMENDED.get(typ, []) if p not in node]
        if typ in ARTICLE_TYPES and "headline" in missing_rec and report.ignore and report.ignore(CAT, f"{typ} missing required 'headline'"):
            missing_rec.remove("headline")  # preserve the old headline-only opt-out
        if typ == "Recipe" and report.ignore:
            missing_rec = [p for p in missing_rec if p not in ("recipeIngredient", "recipeInstructions")
                           or not report.ignore(CAT, f"Recipe missing required '{p}'")]
        if missing_rec:
            article = typ in ARTICLE_TYPES
            recipe = typ == "Recipe"
            if article:
                recommendation = (f"Consider applicable, known {', '.join(missing_rec)} values; do not invent authors or dates. "
                                  f"Google Article markup has no required properties, and this is not an invalidity or eligibility verdict. Source: {ARTICLE_SOURCE}")
            elif recipe:
                recommendation = (f"Add applicable, real {', '.join(missing_rec)} values matching the recipe; do not invent authors or ratings. "
                                  f"Google requires Recipe name and image; ingredients and instructions are recommended. "
                                  f"This is not full eligibility or schema.org validity; verify conditional, nested and image requirements separately. Source: {RECIPE_SOURCE}")
            else:
                recommendation = f"Add {', '.join(missing_rec)} to strengthen the {typ} entity."
            report.add(CAT, "low", f"{typ} missing recommended properties",
                       f"Recommended fields absent{' or blank' if article or recipe else ''}: {', '.join(missing_rec)}.",
                       recommendation)


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
