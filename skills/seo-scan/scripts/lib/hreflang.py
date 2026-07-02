"""Cross-page hreflang validation: reciprocity, self-reference, code syntax.

hreflang only works when it's **reciprocal**: if page A lists B as an alternate,
B must list A back, and each page must include itself in its own cluster.
Broken return tags silently disable international targeting — Google ignores
one-way pairs. The on-page auditor checks a single page's cluster syntax; this
module checks the *relationships* across a crawl.

Cap-aware honesty: a capped crawl usually can't see every alternate. Targets
outside the crawled sample are counted as **unverified**, never reported broken.
To make reciprocity actually checkable, the crawler can *probe* a handful of
same-host alternate URLs (fetch + parse their link tags only) — bounded by
``PROBE_CAP`` requests.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from . import htmlx
from .sitegraph import norm

# BCP-47-ish subset Google accepts: lang(2-3) [-Script(4)] [-REGION(2)|-(3digit)]
CODE = re.compile(r"^[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|\d{3}))?$", re.I)
PROBE_CAP = 5


def valid_code(code: str) -> bool:
    c = (code or "").strip().lower()
    return c == "x-default" or bool(CODE.match(c))


def extract(doc, base_url: str) -> list:
    """A page's hreflang cluster as ``[{lang, href}]`` (absolute URLs)."""
    out = []
    for l in doc.links_by_rel("alternate"):
        lang, href = l.get("hreflang"), l.get("href")
        if lang and href:
            out.append({"lang": lang.strip(), "href": urljoin(base_url, href.strip())})
    return out


def probe(pages_alts: dict, *, allow_private=False, timeout=8, cap=PROBE_CAP,
          fetch_text=None) -> dict:
    """Fetch up to ``cap`` same-host alternate URLs we didn't crawl and extract
    their clusters, so reciprocity can be verified instead of left unknown."""
    if fetch_text is None:
        from . import http
        fetch_text = lambda u: http.fetch_text(u, allow_private=allow_private,  # noqa: E731
                                               timeout=timeout)
    known = {norm(u) for u in pages_alts}
    targets, seen = [], set()
    for page, alts in pages_alts.items():
        host = urlparse(page).netloc.lower()
        for a in alts:
            tn = norm(a["href"])
            if tn in known or tn in seen:
                continue
            if urlparse(a["href"]).netloc.lower() != host:
                continue   # cross-host alternates are out of probe scope
            seen.add(tn)
            targets.append(a["href"])
            if len(targets) >= cap:
                break
        if len(targets) >= cap:
            break

    probed = {}
    for t in targets:
        body = fetch_text(t)
        if body:
            probed[t] = extract(htmlx.parse(body, base_url=t), t)
    return probed


def analyze(pages_alts: dict) -> dict:
    """Validate hreflang relationships across ``{page_url: [{lang, href}]}``.

    Every page present in the mapping counts as "seen" (crawled or probed);
    alternate targets outside it are unverified, not broken."""
    used = {p: alts for p, alts in pages_alts.items() if alts}
    seen = {norm(p): p for p in pages_alts}

    invalid, missing_self, missing_return = [], [], []
    unverified = 0
    langs_seen = set()

    for page, alts in used.items():
        pn = norm(page)
        cluster = {norm(a["href"]) for a in alts}
        for a in alts:
            langs_seen.add(a["lang"].lower())
            if not valid_code(a["lang"]):
                invalid.append({"page": page, "code": a["lang"]})
        if pn not in cluster:
            missing_self.append(page)
        for a in alts:
            tn = norm(a["href"])
            if tn == pn:
                continue
            if tn not in seen:
                unverified += 1
                continue
            target_cluster = {norm(x["href"]) for x in pages_alts.get(seen[tn], [])}
            if pn not in target_cluster:
                missing_return.append({"page": page, "target": a["href"],
                                       "lang": a["lang"]})

    return {
        "used": bool(used),
        "pages_with_hreflang": len(used),
        "invalid_codes": invalid,
        "missing_self": missing_self,
        "missing_return": missing_return,
        "unverified_targets": unverified,
        "has_x_default": "x-default" in langs_seen,
    }


def render_markdown(r: dict) -> list:
    """The 'Hreflang' report section (only rendered when hreflang is in use)."""
    lines = [f"## Hreflang / international ({r['pages_with_hreflang']} pages "
             "carry clusters)", ""]
    ok = True
    if r["missing_return"]:
        ok = False
        lines.append(f"- **Missing return tags ({len(r['missing_return'])})** — "
                     "one-way pairs are ignored by Google:")
        for m in r["missing_return"][:6]:
            lines.append(f"  - {m['page']} → {m['target']} (`{m['lang']}`) has "
                         "no link back")
    if r["missing_self"]:
        ok = False
        lines.append(f"- **Missing self-reference ({len(r['missing_self'])})** — "
                     "each page must list itself in its own cluster:")
        for p in r["missing_self"][:5]:
            lines.append(f"  - {p}")
    if r["invalid_codes"]:
        ok = False
        codes = ", ".join(f"`{i['code']}`" for i in r["invalid_codes"][:6])
        lines.append(f"- **Invalid language codes:** {codes} (use "
                     "ISO-639-1 lang + optional ISO-3166 region, e.g. `en-GB`).")
    if not r["has_x_default"]:
        lines.append("- **No x-default** anywhere in the sample — add a fallback "
                     "for unmatched locales.")
    if ok and r["has_x_default"]:
        lines.append("- Clusters verified within the sample are reciprocal and "
                     "self-referencing. 🟢")
    if r["unverified_targets"]:
        lines.append(f"- _{r['unverified_targets']} alternate target(s) point "
                     "outside the crawled/probed sample — **unverified**, not "
                     "broken. Raise `--max-pages` to verify more._")
    lines.append("")
    return lines
