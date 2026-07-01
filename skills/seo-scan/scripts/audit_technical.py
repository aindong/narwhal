"""Technical SEO auditor.

Checks the crawlability and indexability signals that determine whether a page
can rank at all: title/meta, headings, canonical, robots directives, viewport,
hreflang, images, links, and a few HTTP-header hygiene checks.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

try:
    from lib import htmlx
except ImportError:  # when imported as a package
    from .lib import htmlx  # type: ignore

CAT = "technical"


def audit(doc, resp, report, ctx=None) -> None:
    ctx = ctx or {}
    th = ctx.get("thresholds", {})
    _title(doc, report, th)
    _description(doc, report, th)
    _headings(doc, report)
    _canonical(doc, resp, report)
    _robots_directives(doc, report)
    _viewport_lang(doc, report)
    _hreflang(doc, report)
    _images(doc, report)
    _links(doc, resp, report)
    _http_hygiene(resp, report)
    _robots_txt(ctx, report)
    _sitemap(ctx, report)


def _title(doc, report, th=None):
    th = th or {}
    lo, hi = th.get("title_min", 15), th.get("title_max", 65)
    t = doc.title
    if not t:
        report.add(CAT, "critical", "Missing <title>",
                   "The page has no title element.",
                   "Add a unique, descriptive <title> of ~50–60 characters.")
        return
    n = len(t)
    if n < lo:
        report.add(CAT, "high", "Title is very short",
                   f"Title is {n} characters.",
                   "Expand to ~50–60 characters with the primary query and brand.",
                   evidence=t)
    elif n > hi:
        report.add(CAT, "medium", "Title may be truncated in SERPs",
                   f"Title is {n} characters (>{hi} often truncates).",
                   "Trim to ~50–60 characters, front-loading the key phrase.",
                   evidence=t)
    else:
        report.ok(CAT, "Title length is in range", f"{n} characters")


def _description(doc, report, th=None):
    th = th or {}
    lo, hi = th.get("meta_desc_min", 70), th.get("meta_desc_max", 165)
    d = doc.meta_by_name("description")
    if not d:
        report.add(CAT, "high", "Missing meta description",
                   "No <meta name=\"description\"> found.",
                   "Add a compelling 140–160 character summary with the target query.")
        return
    n = len(d)
    if n < lo:
        report.add(CAT, "low", "Meta description is short",
                   f"Description is {n} characters.",
                   "Aim for 140–160 characters to use the full SERP snippet.",
                   evidence=d)
    elif n > hi:
        report.add(CAT, "low", "Meta description may be truncated",
                   f"Description is {n} characters.",
                   "Trim to ~155 characters.", evidence=d)
    else:
        report.ok(CAT, "Meta description length is in range", f"{n} characters")


def _headings(doc, report):
    h1s = [t for lvl, t in doc.headings if lvl == 1]
    if not h1s:
        report.add(CAT, "high", "No H1 heading",
                   "The page has no <h1>.",
                   "Add a single H1 that states the page's main topic.")
    elif len(h1s) > 1:
        report.add(CAT, "medium", "Multiple H1 headings",
                   f"Found {len(h1s)} H1 elements.",
                   "Use one H1; demote the rest to H2/H3.",
                   evidence=" | ".join(h1s[:3]))
    else:
        report.ok(CAT, "Exactly one H1", h1s[0])

    # heading level jumps (e.g. H2 -> H4) hurt outline clarity
    levels = [lvl for lvl, _ in doc.headings]
    for a, b in zip(levels, levels[1:]):
        if b - a > 1:
            report.add(CAT, "low", "Heading levels skip a level",
                       f"An H{a} is followed by an H{b}.",
                       "Keep heading nesting sequential (no H2→H4 jumps).")
            break


def _canonical(doc, resp, report):
    can = doc.canonical()
    if not can:
        report.add(CAT, "medium", "No canonical URL",
                   "No <link rel=\"canonical\"> present.",
                   "Add a self-referencing canonical to consolidate signals.")
        return
    final = resp.final_url or resp.url
    if _norm(can) != _norm(final):
        report.add(CAT, "low", "Canonical points elsewhere",
                   f"Canonical is {can} but page URL is {final}.",
                   "Confirm this is intentional (cross-domain/variant canonical).",
                   evidence=can)
    else:
        report.ok(CAT, "Self-referencing canonical", can)


def _robots_directives(doc, report):
    robots = (doc.meta_by_name("robots") or "").lower()
    if "noindex" in robots:
        report.add(CAT, "critical", "Page is set to noindex",
                   "Meta robots contains 'noindex'.",
                   "Remove 'noindex' if this page should rank.",
                   evidence=robots)
    if "nofollow" in robots:
        report.add(CAT, "medium", "Page-level nofollow",
                   "Meta robots contains 'nofollow'.",
                   "Confirm you intend to drop all outbound link equity.",
                   evidence=robots)
    if "noindex" not in robots:
        report.ok(CAT, "Page is indexable", "no meta-robots noindex")


def _viewport_lang(doc, report):
    if not doc.meta_by_name("viewport"):
        report.add(CAT, "high", "No responsive viewport tag",
                   "Missing <meta name=\"viewport\">.",
                   "Add <meta name=\"viewport\" content=\"width=device-width, "
                   "initial-scale=1\"> for mobile-first indexing.")
    else:
        report.ok(CAT, "Responsive viewport declared")
    if not doc.lang:
        report.add(CAT, "low", "No lang attribute on <html>",
                   "The <html> element has no lang.",
                   "Set <html lang=\"…\"> to aid rendering and localization.")


def _hreflang(doc, report):
    alts = doc.links_by_rel("alternate")
    hreflangs = [l for l in alts if l.get("hreflang")]
    if not hreflangs:
        return
    seen = {}
    for l in hreflangs:
        code = l.get("hreflang").lower()
        seen[code] = seen.get(code, 0) + 1
    dupes = [c for c, n in seen.items() if n > 1]
    if dupes:
        report.add(CAT, "medium", "Duplicate hreflang entries",
                   f"Repeated hreflang codes: {', '.join(dupes)}.",
                   "Each hreflang value should map to exactly one URL.")
    if "x-default" not in seen:
        report.add(CAT, "low", "No x-default hreflang",
                   "hreflang cluster has no x-default.",
                   "Add rel=alternate hreflang=\"x-default\" for the fallback URL.")
    if not dupes:
        report.ok(CAT, "hreflang cluster present", f"{len(hreflangs)} locales")


def _images(doc, report):
    total = len(doc.images)
    if not total:
        return
    missing = [i for i in doc.images if not (i.get("alt") is not None)]
    if missing:
        report.add(CAT, "medium", "Images missing alt text",
                   f"{len(missing)} of {total} <img> tags have no alt attribute.",
                   "Add descriptive alt text (empty alt=\"\" only for decorative images).")
    else:
        report.ok(CAT, "All images have alt attributes", f"{total} images")
    if not any(i.get("loading") == "lazy" for i in doc.images) and total > 5:
        report.add(CAT, "low", "No lazy-loaded images",
                   f"{total} images and none use loading=\"lazy\".",
                   "Add loading=\"lazy\" to below-the-fold images to improve LCP.")


def _links(doc, resp, report):
    host = urlparse(resp.final_url or resp.url).netloc
    empty = 0
    generic = 0
    external = 0
    for a in doc.links:
        href = a.get("href") or ""
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        if not a.text:
            empty += 1
        elif a.text.lower() in ("click here", "read more", "here", "link", "more"):
            generic += 1
        if urlparse(urljoin(resp.final_url or resp.url, href)).netloc not in ("", host):
            external += 1
    if empty:
        report.add(CAT, "low", "Links with no anchor text",
                   f"{empty} <a> tags have empty visible text.",
                   "Give links descriptive anchor text for users and crawlers.")
    if generic:
        report.add(CAT, "low", "Generic anchor text",
                   f"{generic} links use phrases like 'click here'.",
                   "Use keyword-relevant anchor text describing the destination.")


def _http_hygiene(resp, report):
    if resp.redirects:
        chain = len(resp.redirects)
        if chain > 1:
            report.add(CAT, "low", "Redirect chain",
                       f"{chain} redirects before the final URL.",
                       "Collapse to a single 301 to preserve equity and speed.")
    scheme = urlparse(resp.final_url or resp.url).scheme
    if scheme != "https":
        report.add(CAT, "critical", "Page not served over HTTPS",
                   f"Final URL scheme is {scheme}.",
                   "Serve all pages over HTTPS with a valid certificate.")
    ct = (resp.headers.get("content-type") or "").lower()
    if ct and "text/html" not in ct:
        report.add(CAT, "low", "Unexpected content-type",
                   f"Content-Type is {ct}.", "Confirm the document is served as text/html.")
    if not resp.headers.get("content-encoding") and resp.headers:
        report.add(CAT, "low", "No compression header",
                   "Response has no Content-Encoding (gzip/br).",
                   "Enable gzip or Brotli compression to cut transfer size.")


def _robots_txt(ctx, report):
    robots = ctx.get("robots_txt")
    if robots is None:
        report.add(CAT, "medium", "No robots.txt found",
                   "Could not fetch /robots.txt.",
                   "Add a robots.txt; reference the XML sitemap in it.")
        return
    if "sitemap:" not in robots.lower():
        report.add(CAT, "low", "robots.txt has no Sitemap directive",
                   "No 'Sitemap:' line in robots.txt.",
                   "Add 'Sitemap: https://…/sitemap.xml' to robots.txt.")
    else:
        report.ok(CAT, "robots.txt references a sitemap")


def _sitemap(ctx, report):
    if ctx.get("sitemap_found"):
        report.ok(CAT, "XML sitemap reachable", ctx.get("sitemap_url", ""))
    else:
        report.add(CAT, "medium", "No XML sitemap found",
                   "No sitemap.xml at the common locations or in robots.txt.",
                   "Publish an XML sitemap and submit it in Search Console.")


def _norm(url: str) -> str:
    p = urlparse(url)
    return f"{p.netloc}{p.path}".rstrip("/").lower()
