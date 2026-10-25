"""Technical SEO auditor.

Checks the crawlability and indexability signals that determine whether a page
can rank at all: title/meta, headings, canonical, robots directives, viewport,
hreflang, images, links, and a few HTTP-header hygiene checks.
"""

from __future__ import annotations

import json
import unicodedata
from urllib.parse import urljoin, urlparse

try:
    from lib import htmlx
    from lib import jsdiff
    from lib import links
    from lib import sitemap as sm
    from lib import indexing
    from lib import canonical
    from lib import hreflang
except ImportError:  # when imported as a package
    from .lib import htmlx  # type: ignore
    from .lib import jsdiff  # type: ignore
    from .lib import links  # type: ignore
    from .lib import sitemap as sm  # type: ignore
    from .lib import indexing  # type: ignore
    from .lib import canonical  # type: ignore
    from .lib import hreflang  # type: ignore

CAT = "technical"
ANCHOR_WITNESSES = 5


def audit(doc, resp, report, ctx=None) -> None:
    ctx = ctx or {}
    th = ctx.get("thresholds", {})
    _title(doc, report, th)
    _description(doc, report, th)
    _headings(doc, report)
    _canonical(doc, resp, report)
    _robots_directives(doc, report)
    _http_robots(resp, report)
    _viewport_lang(doc, report)
    _hreflang(doc, report)
    _images(doc, report)
    _links(doc, resp, report)
    _http_hygiene(resp, report)
    _robots_txt(ctx, report)
    _sitemap(ctx, report)
    _noscript_only(doc, report)
    if ctx.get("jsdep"):   # only present when a --render scan measured it
        jsdiff.technical_findings(ctx["jsdep"], report)


def _noscript_only(doc, report):
    """JS-shell pages that serve their real content only inside <noscript>.

    Non-rendering crawlers (and most AI fetchers) do read the fallback, so it's
    not invisible — but it's a second-class, historically spam-adjacent signal,
    and rendering crawlers see a *different* document than non-rendering ones."""
    visible = len((doc.text or "").split())
    fallback = len((doc.noscript_text or "").split())
    if visible < 20 and fallback >= 50:
        report.add(CAT, "medium", "Content served only as a <noscript> fallback",
                   f"{visible} words of regular body text vs {fallback} words "
                   "inside <noscript>.",
                   "Server-render (SSR/SSG) the main content so JS and non-JS "
                   "crawlers see the same document; verify the rendered page "
                   "with --render matches the fallback.")


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
        # A homepage title that is just the brand name is normal practice, not a
        # ranking emergency — flagging it "high" was noise on most real sites.
        if htmlx.is_homepage(doc):
            report.add(CAT, "low", "Homepage title is just the brand",
                       f"Title is {n} characters.",
                       "Fine for a known brand; consider \"Brand — what you do\" "
                       "(~50–60 chars) to also rank for the value proposition.",
                       evidence=t)
        else:
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
    final = resp.final_url or resp.url
    receipt = canonical.observe(doc, final)
    report.meta['canonical_comparison'] = receipt
    can = doc.canonical()
    if receipt['status'] == 'missing':
        report.add(CAT, "medium", "No canonical URL",
                   "No <link rel=\"canonical\"> present.",
                   "Add a self-referencing canonical to consolidate signals.")
        return
    if receipt['status'] == 'unverified':
        report.add(CAT, 'low', 'Review unverified canonical comparison',
                   'A first HTML canonical declaration was observed, but a candidate/comparison URL '
                   'was empty, malformed or outside supported HTTP comparison. ' + canonical.LIMITS,
                   'Inspect the original declaration, HTML base and fetched URL before editing. '
                   'Repair only confirmed source defects; do not add a duplicate canonical or assume '
                   'the target is missing, reachable or selected by a search engine.', evidence=can or '',
                   rule_id='technical.canonical.comparison.unverified')
    elif receipt['status'] == 'differs':
        report.add(CAT, "low", "Canonical points elsewhere",
                   f"Canonical is {can} but fetched URL is {final}. Differing components: "
                   + ', '.join(receipt['differences']) + '. ' + canonical.LIMITS,
                   'Confirm this is intentional (cross-domain/variant canonical). Preserve valid '
                   'consolidation; edit only a verified wrong target. Search-engine selection is unmeasured.',
                   evidence=can)
    else:
        report.ok(CAT, 'Self-referencing canonical', str(can) + '. ' + canonical.LIMITS)


def _generic_meta_robots(doc):
    """Collect exact restriction names across active generic robots meta tags.

    Parameter names/values are not standalone rules (e.g. image-preview:none),
    but standalone names before a parameter remain observable.
    Keep one bounded positional witness per recognized name, scanning every tag.
    """
    observed = {}
    for position, meta in enumerate(doc.meta, 1):
        if (meta.get('name') or '').lower() != 'robots':
            continue
        for token in indexing.restriction_names(meta.get('content') or ''):
            observed.setdefault(token, position)
    rules = indexing.expand(observed)
    evidence = '; '.join(f'meta robots #{position}: {token}'
                         for token, position in sorted(observed.items()))
    return rules, evidence


def _robots_directives(doc, report):
    named = indexing.crawler_meta(doc.meta)
    if named:
        report.meta['crawler_meta_robots'] = named
    robots, evidence = _generic_meta_robots(doc)
    if 'noindex' in robots:
        report.add(CAT, "critical", "Page is set to noindex",
                   "Generic meta robots declares 'noindex' or its 'none' alias.",
                   "Remove the restricting directive only if this page should appear in search results.",
                   evidence=evidence)
    if 'nofollow' in robots:
        report.add(CAT, "medium", "Page-level nofollow",
                   "Generic meta robots declares 'nofollow' or its 'none' alias.",
                   "Review this directive if crawlers should follow page links; this check does not measure crawler behavior.",
                   evidence=evidence)
    if 'noindex' not in robots:
        report.add(CAT, 'good', 'No generic meta noindex detected',
                   'Generic meta robots observation only; it excludes HTTP headers and crawler-specific meta. '
                   'Absence is not proof of indexability.',
                   rule_id='technical.page.is.indexable')


def _http_robots(resp, report):
    """Score only observed unprefixed restrictions; named scopes are policy notes."""
    fields = getattr(resp, 'robots_header_fields', None)
    basis = getattr(resp, 'robots_header_basis', 'merged_or_unknown')
    if fields is None:
        value = next((value for key, value in resp.headers.items() if key.lower() == 'x-robots-tag'), '')
        fields = [value] if value else []
        basis = 'merged_or_unknown'
    if not fields:
        return
    receipt, witnesses = indexing.http_robots(fields, basis)
    report.meta['http_robots'] = receipt
    recommendation = ('Review the hosting/CDN/middleware response-header owner; remove the restriction only if unintended. '
                      'Changing HTML meta tags alone does not remove this header.')
    if 'noindex' in receipt['generic']:
        report.add(CAT, 'critical', 'HTTP X-Robots-Tag declares noindex',
                   'An unprefixed response-header rule declares noindex (including the none alias). '
                   'This observes a declaration, not live search inclusion.', recommendation,
                   evidence=witnesses['noindex'], rule_id='technical.http.robots.noindex')
    if 'nofollow' in receipt['generic']:
        report.add(CAT, 'medium', 'HTTP X-Robots-Tag declares nofollow',
                   'An unprefixed response-header rule declares nofollow (including the none alias). '
                   'This observes a declaration, not actual crawler behavior.', recommendation,
                   evidence=witnesses['nofollow'], rule_id='technical.http.robots.nofollow')


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
    hreflangs = [l for l in alts if l.get("hreflang") is not None]
    receipt = {}
    hreflang.extract(doc, report.final_url or report.url, diagnostics=receipt)
    report.meta['hreflang_policy_basis'] = hreflang.EXTRACTION_BASIS
    report.meta['hreflang_extraction'] = receipt
    if not hreflangs:
        return
    seen = {}
    for l in hreflangs:
        code = l.get("hreflang").strip().lower()
        seen[code] = seen.get(code, 0) + 1
    dupes = [c for c, n in seen.items() if n > 1]
    if dupes:
        report.add(CAT, "medium", "Duplicate hreflang entries",
                   f"Repeated hreflang codes: {', '.join(dupes)}.",
                   "Each hreflang value should map to exactly one URL.")
    if "x-default" not in seen:
        report.add(CAT, "low", "No x-default hreflang",
                   'No x-default declaration observed; an unmatched-locale fallback is optional, not a universal requirement.',
                   'Review whether an existing intended fallback should be declared as x-default. '
                   'Do not invent a page or add a fallback solely to clear this contextual review.')
    if hreflang.unverified(report.meta):
        report.add(CAT, 'low', 'HTML hreflang URL declarations need review', hreflang.note(report.meta),
                   'If these are intended language alternatives, confirm their fully-qualified HTTP(S) page URLs '
                   'and correct only the relevant declarations. Do not invent language pages or treat source '
                   'omissions as HTTP failures; re-scan before relationship or score claims.',
                   rule_id='technical.hreflang.urls.review')
    if not dupes and not hreflang.unverified(report.meta):
        report.add(CAT, 'good', 'hreflang declarations observed',
                  f"{len(hreflangs)} declarations with supported source URLs; not search acceptance or language equivalence.",
                  rule_id='technical.hreflang.cluster.present')


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


def _anchor_evidence(count, witnesses):
    """Omit credential-like hrefs; keep other witnesses as reversible literal JSON."""
    safe_witnesses = []
    for witness in witnesses:
        item = dict(witness)
        spelling = unicodedata.normalize('NFKC', item['href'])
        if '@' in spelling or '%40' in spelling:
            item['href'] = None
            item['href_omitted'] = 'credential_like_marker'
        safe_witnesses.append(item)
    return json.dumps({'scope': 'Source anchor observations; destinations not checked.',
                       'observed_count': count, 'witnesses': safe_witnesses},
                      indent=2, ensure_ascii=True).replace('`', '\\u0060')


def _links(doc, resp, report):
    empty = 0
    generic = 0
    invalid = 0
    empty_witnesses, generic_witnesses, invalid_witnesses = [], [], []
    base_url = resp.final_url or resp.url
    effective, receipt = links.document_base(doc, base_url, csp=resp.headers.get('content-security-policy', ''))
    report.meta['anchor_resolution_basis'] = links.RESOLUTION_BASIS
    if receipt is not None:
        report.meta['anchor_base'] = receipt
    for a in doc.links:
        href = a.get("href") or ""
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        try:
            links.resolve_anchor(href, base_url, effective)
        except ValueError:
            invalid += 1
            if len(invalid_witnesses) < ANCHOR_WITNESSES:
                invalid_witnesses.append({'href': href})
        # Google documents image alt text and an otherwise-empty anchor's title
        # as source fallbacks. Keep them separate from visible/page text.
        text = (htmlx.collapse(a.text) or htmlx.collapse(a.image_alt_text)
                or htmlx.collapse(a.get("title")))
        if not text:
            empty += 1
            if len(empty_witnesses) < ANCHOR_WITNESSES:
                empty_witnesses.append({'href': href, 'label': text})
        elif text.lower() in ("click here", "read more", "here", "link", "more"):
            generic += 1
            if len(generic_witnesses) < ANCHOR_WITNESSES:
                generic_witnesses.append({'href': href, 'label': text})
    if invalid:
        report.add(CAT, "low", "Malformed HTTP link URLs",
                   f"{invalid} <a> href value(s) have invalid HTTP URL syntax and are omitted "
                   "from HTTP link collection and crawl discovery. No network failure is inferred.",
                   "Correct the link host, IPv6 brackets or port, then re-scan. "
                   "Syntax rejection does not establish whether a destination is reachable.",
                   rule_id="technical.links.invalid.url",
                   evidence=_anchor_evidence(invalid, invalid_witnesses))
    if empty:
        report.add(CAT, "low", "Links with no anchor text",
                   f"{empty} <a> tags have no text, image alt text or title fallback.",
                   "Give links descriptive text or meaningful image alt text. "
                   "A title is only a fallback, not a full accessibility fix.",
                   evidence=_anchor_evidence(empty, empty_witnesses))
    if generic:
        report.add(CAT, "low", "Generic anchor text",
                   f"{generic} links use phrases like 'click here'.",
                   "Review link purpose and surrounding context; use descriptive labels where helpful. "
                   "Keep concise navigation and avoid keyword insertion solely to change this phrase count.",
                   evidence=_anchor_evidence(generic, generic_witnesses))


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
    rejected = {}
    references = sm.robots_sitemaps(robots, diagnostics=rejected)
    if rejected:
        report.add(CAT, "low", "Rejected sitemap URL references",
                   sm.reference_note(sm.reference_diagnostics(rejected)),
                   "Use absolute HTTP(S) sitemap URLs with valid hosts and ports in robots.txt. "
                   "Correct rejected references and re-scan; syntax checks do not prove reachability.",
                   rule_id="technical.sitemap.invalid.references", scope="site")
        return  # do not endorse invalid directives as a passing sitemap reference
    if not references:
        report.add(CAT, "low", "robots.txt has no Sitemap directive",
                   "No 'Sitemap:' line in robots.txt.",
                   "Add 'Sitemap: https://…/sitemap.xml' to robots.txt.")
    else:
        report.ok(CAT, "robots.txt references a sitemap")


def _sitemap(ctx, report):
    value = ctx.get('sitemap_discovery')
    receipt = sm.recorded_discovery(value)
    if value is not None:
        report.meta['sitemap_discovery'] = receipt or {'basis': 'unrecognized'}
    found = ctx.get('sitemap_found') if value is None else bool(receipt and receipt['verified_files'])
    if found:
        report.ok(CAT, "XML sitemap reachable", ctx.get("sitemap_url", ""))
    elif sm.discovery_note(value):
        return  # coverage note, not proof of absence or a source penalty
    else:
        report.add(CAT, "medium", "No XML sitemap found",
                   "No sitemap.xml at the common locations or in robots.txt.",
                   "Publish an XML sitemap and submit it in Search Console.")


def _norm(url: str):
    """Compatibility alias for the shared, local component-comparison key."""
    return canonical.key(url)
