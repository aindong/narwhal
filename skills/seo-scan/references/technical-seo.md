# Technical SEO reference

The technical auditor checks whether a page *can* rank at all — crawlability,
indexability, and rendering. Below is the reasoning and thresholds behind each
check, plus what to do when the automated check isn't enough.

## Final HTTP response status

Transport success means a final 2xx response without a recorded fetch error.
The existing bounded transports follow usable redirects before this check; a
terminal 3xx is not a successfully obtained resource representation. In
particular, 304 alone does not supply a cached representation to this local
scanner. Such responses use the existing unavailable-page path: no page
auditors complete, the zero score is a fail-safe rather than measured health,
and text-resource wrappers do not promote a redirect body into robots/sitemap/
llms content. Reports retain observed HTTP status for inspection.

Normal followed redirects ending in 2xx still work. Partial/empty 2xx responses
still require each consumer's coverage checks; successful transport alone is
not full HTML, indexing, crawler access, search acceptance or page quality.
Request/redirect/DNS/SSRF budgets, default CLI output/exit behavior and score
weights are unchanged. Corrected acquisition/scoring is not a website fix or
measured SEO gain; CI diffs retain the existing incomplete-execution guard.

## Title & meta description
- **Title:** ~50–60 characters. Front-load the primary query; include the brand
  at the end. One title per page, unique across the site. Titles over ~65 chars
  truncate in most SERPs; under ~15 usually means it's a placeholder.
- **Meta description:** 140–160 characters. It doesn't directly affect ranking
  but drives click-through and is often the snippet AI chat previews show. Write
  it as ad copy, not a keyword list.

## Headings
- Exactly one `<h1>` stating the page topic. Multiple H1s dilute the signal.
- Keep nesting sequential (no `H2 → H4` jumps) — the outline is how both crawlers
  and screen readers understand structure.

## Canonicalization
- Every indexable page should have a self-referencing `rel=canonical`.
- A canonical pointing elsewhere is a deliberate signal ("this is a duplicate of
  X"). Flag unexpected cross-URL canonicals — a wrong one can deindex a page.

Narwhal compares the **first parsed HTML declaration** against the final fetched
URL. Relative references use the first non-template href-bearing HTML base, or
the fetched document URL. Comparison is local: no canonical target request, DNS
lookup or new fetch permission is made.

- Scheme/host case, default HTTP(S) ports, empty root paths, percent-encoded
  unreserved characters/hex case and complete dot segments normalize. Other
  path/query case, non-root trailing/repeated separators, query order, reserved
  escapes and explicit query/fragment delimiters remain distinct.
- Literal non-ASCII path/query/fragment text maps to UTF-8 percent bytes before
  comparison, avoiding false differences against transport-encoded URLs.
  Non-ASCII hosts (including percent-encoded high bytes) remain unverified;
  this does not implement IDNA or Unicode-form normalization.
- A match is a **component observation**, not validated target content/access,
  redirect equivalence, canonical conflicts or Google's selected canonical.
  HTTP canonical headers, full URI/IRI conformance and IDNA/alternate numeric
  host aliases are outside this comparison. Fragment equality is not a claim
  that a search engine supports fragment canonicals.
- Missing declarations retain the existing rule. Observed but empty, malformed
  or unsupported candidates get manual-only verification, not duplicate markup
  generation or a false passing/absence result. Known uncertainty qualifies
  page/site scores and prevents diff fix claims/CI gates and comparative verdicts.
  Missing legacy receipts are unrecorded, not certified.
- Near-duplicate clusters share the same component key. The historical JSON
  `canonical_ok` means all observed candidates have one supported key; it does
  not prove consolidation. Review real duplication and intended variants before
  editing, and preserve useful distinct pages. Detector corrections can raise or
  lower tool scores without changing a website or measuring SEO improvement.

Sources: [RFC 3986 comparison/normalization](https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2),
[HTTP(S) URI normalization](https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2.3)
[literal Unicode to URI byte mapping](https://www.rfc-editor.org/rfc/rfc3987.html#section-3.1)
and [Google's canonical guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
(checked 2026-10-19). The latter treats declarations as signals and discourages
fragment canonicals; a local match does not verify Google's choice.

## Observed crawl address identity

Crawl deduplication, graph nodes/orphan candidates and hreflang matching use a
separate **observed-address key**, not the canonical comparator above. Literal
fragments and scheme/host case group; empty roots use `/`. Non-root trailing/
repeated separators, semicolon path data, path/query case, query order and
explicit empty query delimiters remain distinct. Userinfo case is preserved.
This does not implement full URI equivalence, canonical/redirect alias inference
or proof of equal server content. Per-URL fetch/SSRF guards remain separate.

Graph JSON records `url_identity_basis`; unrecorded legacy policy is not inferred.
Distinct variants can now consume their own slots within the existing page/probe
caps, changing graph counts or the sampled site average without a site change.
Audit diffs with known current versus missing/different policy withhold fix claims
and fail CI comparability gates. Matching policy alone is not an identical-sample
guarantee. The graph is non-scoring; per-page audit rules remain unchanged.

Orphan candidates deduplicate fragment aliases and exclude already crawled/start
URL identities and observed link targets. Zero additional candidates therefore
does **not** prove every sitemap URL has inbound links; use the separate sampled
zero-inbound observations and inspect wider coverage before edits.

Graph `depth_coverage` records `breadth_first_over_supplied_graph_edges_v1`,
whether the start identity occurs in the supplied nodes, and counts of reachable
and unreachable nodes. Depth is the shortest input-edge path from that start,
only among reachable nodes. An absent start means no assessed start depth;
the historical numeric `max_depth=0` then remains a placeholder, not a site pass.
Missing/unsupported or inconsistent receipts are not inferred from tool version.
This local computation does not verify fetch success, crawler access, link equity
or ranking. Zero inter-page edges retain known URL lists, orphan-check status
and sample caveats. It does not prove the whole site lacks links; inspect captured
links, extraction and sampling before source edits or a larger authorized crawl.
Existing five-item depth/unreachable/zero-inbound and eight-item orphan displays
keep full JSON lists and expose omitted counts. No scoring or fetch policy changes.

Relative anchor-path merging preserves empty path segments (`guide//chapter`
is not `guide/chapter`), including repeated separators in the base path and
semicolon data. Literal `.`/`..` resolution shares the existing canonical path
helper without changing canonical comparison. Collection, fallback discovery
and link-check targets use this resolver; scheme/authority/query handling
outside the relative path merge remains as before. Per-fetch SSRF/redirect
checks and configured caps remain mandatory and unchanged. Corrected observed
targets may change a bounded sample, graph counts or its average without a site edit.

Crawl JSON records `link_resolution_basis=relative_path_merge_preserve_separators_v1`.
Known current versus missing/different policy makes audit diffs incomparable;
matching policy is not proof of equal samples, server aliases or a measured fix.
This v1 receipt is not full WHATWG URL conformance: encoded-dot decoding, HTML base
elements and empty-query transport remain outside its scope. Bounded supported path
fixtures are checked against Chromium, not all browser repair behavior.
See [RFC 3986 reference merging](https://www.rfc-editor.org/rfc/rfc3986.html#section-5.2.3)
and [dot-segment removal](https://www.rfc-editor.org/rfc/rfc3986.html#section-5.2.4)
(checked 2026-10-24).

### Declared anchor bases

The current anchor policy is `first_declared_base_relative_path_merge_v2`.
It uses the first non-template href-bearing base, including an explicit empty
first href; a target-only base does not prevent a later href-bearing one.
The shared base reader ignores script/style/raw-text/RCDATA lookalikes (also
used by canonical resolution), not a full HTML5 tree construction algorithm.
Bogus marked declarations share the existing source projection's comment
handling across base, fallback HTML, markup-tree and attribution readers,
instead of aborting the complete scan.
Internal/external classification and fallback discovery compare targets with
the fetched document host, **not** the declared base host. Base parsing never
resolves DNS, fetches a target or overrides per-request SSRF/redirect controls.
Existing crawl/link/probe budgets remain unchanged.

Page `anchor_resolution_basis` and crawl `link_resolution_basis` record policy.
When a base is declared, `anchor_base` records `basis` and `status` without source
URL values or exception text. Status is `declared_http`, `document_url` (empty or
fragment-only), `ignored_scheme` (data/javascript), `non_http`, or `unverified`.
Known unsupported syntax, authority-ambiguous slash/backslash/control/credential
references, and a detected enforced-header/meta CSP `base-uri` directive withhold
base-dependent targets. CSP allowlists/enforcement are not guessed. Unrelated or
report-only CSP does not trigger that gap. Absolute HTTP(S) references remain
independently assessable; separate unassessed-base occurrence counts are not
malformed-anchor or failed-request counts.
Shared markup-tree resolution warnings omit raw source values/credentials.
Bounded extraction-local reference IDs retain deduplication and warning caps;
they are not URL fingerprints, network results or stable cross-report IDs.

Unscored page/site report notes expose known gaps outside capped page lists;
URL details remain bounded and full observations stay in JSON. Diff gates with
known current versus missing/different policy, or known unassessed base coverage,
exit 2 rather than claim a site fix. The previous v1-versus-unrecorded guard is
retained. Compare/brief acquisition withholds known unassessed page-score
verdicts, and facts retain recorded scope. Matching policy alone cannot prove
equal samples, accuracy or SEO improvement. Rule weights/IDs stay unchanged;
corrected target selection can change graph counts, failures and sampled scores.

This is local declaration resolution, not browser execution, CSP evaluation,
scripting/noscript/shadow-DOM certification, server-resource equivalence or full
WHATWG URL repair. Other resource/hreflang consumers, encoded-dot decoding and
empty-query transport are not certified by this anchor receipt. Conditional or
malformed HTML still needs browser inspection before source edits.
See [HTML base elements](https://html.spec.whatwg.org/multipage/semantics.html#the-base-element)
and [CSP base-uri](https://www.w3.org/TR/CSP3/#directive-base-uri) (checked 2026-10-24).

This preserves distinctions described in [RFC 3986 path/query components](https://www.rfc-editor.org/rfc/rfc3986.html#section-3.3).
In particular, [protocol-based slash equivalence](https://www.rfc-editor.org/rfc/rfc3986.html#section-6.2.4)
needs observed evidence rather than automatic removal (checked 2026-10-19).

## Robots directives (two layers)
1. `<meta name="robots">` / `X-Robots-Tag` header — page-level. `noindex` here is
   the single most common cause of "my page vanished."
2. `robots.txt` — site-level crawl control. It blocks *crawling*, not indexing;
   a URL blocked in robots.txt can still be indexed without a snippet. Always
   reference the XML sitemap from robots.txt.

Both robots readers ignore one optional initial UTF-8 byte-order mark before
reading fields, consistent with [Google's file-format guidance](https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec#file-format)
(checked 2026-10-15). A marker inside a path or on a later line is not stripped.
This prevents a lost first user-agent group or Sitemap declaration; it does not
change fetch/error policy, URI matching, reference guards or the explicit
crawl-base override, and is not proof of live crawler behavior.

The current deterministic page-meta check combines all active generic
`name="robots"` tags, matches exact restriction names and expands `none` to
`noindex,nofollow`. It does not interpret parameter values as standalone rules.
Crawler-specific meta is outside this check; a passing generic-meta observation
is not proof of indexability or actual inclusion.

A separate non-scoring observation recognizes the documented `googlebot` and
`googlebot-news` HTML meta names (case-insensitive), exact `noindex`/`nofollow`
and the `none` alias. Repeated active tags accumulate declared restrictions;
later allowing tags do not erase earlier declarations. Additive
`meta.crawler_meta_robots` records the checked agents, dated primary source and
bounded active-metadata positions. Inert templates are not document policy.
Other names, preview/date directives and effective policy across generic meta,
named meta and HTTP headers are outside this observation. Review intended
restrictions manually; they are not automatically scored or removed.

A separate final HTML-response header check recognizes unprefixed `noindex`,
`nofollow` and `none` in `X-Robots-Tag`. New header fields reset named-agent scope;
named-crawler restrictions are displayed as non-scoring policy observations.
`meta.http_robots` records transport provenance. Raw transports preserve repeated
fields; browsers may combine them before exposing them, so named scope may need
raw confirmation. Date/preview rules and live crawler/indexing behavior remain
unverified. Fix header findings at the hosting/CDN/middleware owner, not merely
by changing an HTML robots meta tag.
Rendered scans reject post-load main-document navigation rather than attributing
the initial response's headers to a replacement DOM; scan the final URL directly.
Ordinary HTTP redirects and same-document History API changes remain supported.
See [Google's primary specification](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag)
for aliases, multiple tags, named agents and header rules. Engine behavior can
differ; verify live indexing through the relevant external source when needed.

The shared robots matcher normalizes valid percent-encoded unreserved ASCII and
UTF-8 spellings before comparison, following the URI-comparison guidance in
[RFC 9309 §2.2.2](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.2.2).
Encoded reserved delimiters stay distinct (`%2F` is not a path separator), and
encoded literal `%2A` / `%24` do not become wildcard/end operators. Matching
remains case-sensitive outside escape hex digits; equivalent normalized rules
retain Allow-on-tie precedence. Query matching and full-URL fragment exclusion
remain. Full URLs retain semicolon path parameters rather than silently dropping
them. This does not claim complete URL/robots conformance or change which
paths a caller checks; the GEO policy receipt still explicitly checks `/` only.

Discovered sitemap references have a separate bounded syntax check. Robots.txt
`Sitemap:` values, sitemap-index child locations and sitemap page locations must
be supported absolute HTTP(S) URLs with parser-valid hosts/ports before they are
used for fetching, discovery or sampling. Relative values are rejected, not
silently resolved against the site. This follows the absolute-location requirement
in the [Sitemaps protocol](https://www.sitemaps.org/protocol.html) (checked
2026-10-15), not complete URI/XML/protocol validation. Existing cross-host page
checks and actual-fetch host/redirect protections remain; syntax acceptance is
not authorization or proof of reachability.

Known context rejections appear in page `meta.sitemap_references`; crawl and
sitemap-validator JSON expose their own `sitemap_references` receipts. The
`basis: absolute_http_url_syntax` receipt contains only positive scalar counts
under `rejected`: `robots_directives`, `index_locations`, `page_locations` when
observed. These count examined reference occurrences per component, not unique
destinations or whole-site failures; shared robots context is not multiplied by
crawled page count. Invalid page locations remain in the validator's raw entry
total/problem counts but are never HTTP-sampled. Invalid index references do not
consume the crawler's five usable-child fetch budget. Valid siblings and common
path / homepage-link fallbacks remain available.

Rejected references are visible as source issues/notes, not synthetic dead-link
statuses. Raw rejected URLs and parser exception text are not retained in the
receipts. The validator does not issue its healthy conclusion after rejections,
fetch errors or a reached sitemap-file cap. A basic page scan still checks only its
site context, not every nested sitemap. Missing/legacy receipts are unverified,
not complete validation. Direct user URL errors and unexpected implementation
errors still propagate through their existing boundaries.

## Mobile / rendering
- `<meta name="viewport" content="width=device-width, initial-scale=1">` is
  mandatory under mobile-first indexing.
- Set `<html lang>` for correct rendering and localization.
- For SPAs, re-run with `--render` — if content only appears after JS, the raw
  fetch understates the page and so will some crawlers.

## hreflang (international)
- Each `rel=alternate hreflang` value maps to exactly one URL; entries must be
  bidirectional (A points to B *and* B points to A).
- Consider `x-default` if an intended unmatched-locale fallback exists; it is
  not a universal requirement or a reason to invent a page.
- Use ISO 639-1 language + optional ISO 3166-1 region: `en`, `en-GB`, `es-MX`.

## Images
- Meaningful images need descriptive `alt`; decorative ones use `alt=""`.
- Lazy-load below-the-fold images (`loading="lazy"`) to protect LCP, but never
  lazy-load the LCP/hero image itself.

## Links
- Descriptive anchor text (not "click here") helps users and passes clearer
  relevance signals.
- The empty/generic anchor-text heuristics use text content first, descendant
  image `alt` text when that is empty, then an anchor `title` fallback. Google
  documents the image-alt and title fallbacks in its
  [link best practices](https://developers.google.com/search/docs/crawling-indexing/links-crawlable#anchor-text-placement)
  (checked 2026-10-15). Image alternatives stay separate from visible page text,
  headings and word counts; blank/generic alternatives remain actionable.
- A linked image's alternative should describe the destination/action, not just
  its appearance; see [W3C functional images](https://www.w3.org/WAI/tutorials/images/functional/).
  A title fallback is not a full accessibility fix. This source check does not
  compute browser accessible names, CSS visibility, ARIA naming or the combined
  name of mixed text/image content. Image-alt attribute checks stay independent.
- Parser-recognized malformed HTTP anchor hrefs (such as invalid host brackets or
  ports) produce a low source-syntax finding rather than aborting the page. They
  are omitted from HTTP link collection and anchor-based crawl discovery; later
  valid links remain available. Non-HTTP/fragment references are not mislabeled
  as malformed HTTP URLs. This is not a complete URI validator or reachability
  test: no DNS/HTTP request is made to validate syntax, and actual fetches retain
  the existing host/redirect guards.
- When links are collected, affected page JSON records `meta.link_extraction`
  with `invalid_url_occurrences` and `basis: url_syntax_only`. Crawl JSON includes
  per-page receipts and a sample rollup with `affected_pages`; visible crawl/audit
  output explains the omissions even when link checks are off. Counts are href
  occurrences in scanned pages, not unique targets or whole-site error counts.
  Invalid source URLs are **not network-dead links** and are never assigned a
  fabricated HTTP failure status. Only scalar counts are retained, not raw URLs
  or potentially sensitive parser messages. Unaffected/legacy missing receipts
  are not a promise of complete URL validation. Sitemap/XML and other URL-bearing
  markup are outside this anchor-href check.
- Audit for broken internal links and long redirect chains; collapse chains to a
  single 301 to preserve equity and speed.

## HTTP hygiene
- HTTPS everywhere with a valid cert.
- Enable gzip/Brotli compression.
- One redirect max to the canonical URL; avoid `http → https → www` daisy-chains.

## Beyond the automated checks
- **Core Web Vitals field data** (LCP, INP, CLS) needs CrUX or real-user
  monitoring — the scan only flags likely hygiene issues (no lazy-load, heavy
  DOM). Recommend PageSpeed Insights / CrUX for real numbers.
- **Crawl budget & log analysis** for large sites needs server logs.
- **JavaScript indexing edge cases** may need Search Console's URL Inspection.

## JS dependence (raw vs rendered)
When a scan runs with `--render`, Narwhal diffs the **served HTML** against the
**rendered DOM**. This is a paired-snapshot observation, not measured JavaScript
causation, server-rendering completeness or crawler/indexing/citation behavior.
The two requests can differ in timing/page state, and each parser selects text
independently. Inspect both original snapshots and intended behavior before
changing delivery; preserve useful client interaction and valid metadata/markup.

`meta.js_dependence.text_comparison` version 1, basis
`selected_extracted_text_pair`, records each extraction basis, whitespace-token
counts, signed `net_token_delta`, `positive_net_increase_percent` and exact
`selected_text_equal` for the selected extracted strings. Metadata contains
counts/scopes, not copied source text. Equality is limited to those extracted
strings, not all page content or CSS visibility. An empty pair establishes only
that neither extraction selected text; it does not establish that the page lacks
other content. Empty pairs produce low verification-only
`technical.rendered.text.unobserved`, not a
passing severity or the legacy server-rendering ID. Plans assign no source owner
or content/SSR rewrite to this observation.
Equal or shorter counts can accompany a complete replacement, so those cases
never receive a server-rendering pass when the selected strings differ.

Compatibility fields `words_raw` / `words_rendered` retain whitespace-token
counts; `js_only_pct` retains `round(100 * max(rendered - served, 0) / rendered)`
(zero if rendered count is zero). It is **not** a share of unique/JS-only content.
Historical 30%/10% positive-increase bands retain their rule IDs for filters,
but now prompt low-priority review, not high/medium content-availability verdicts.
The GEO-side large-count review likewise does not assert AI-access failure.
These priority/score changes are calibration corrections, not SEO improvements.

Heading nonmatch/count aliases remain compatible, not proof that sections are
missing from served content. Head-metadata presence differences are snapshot
observations, not authenticated injection events. A higher JSON-LD block count
does not mean all markup was absent in served HTML or establish semantic changes,
validity or eligibility. Corresponding findings are low contextual reviews.

Current and known legacy render-difference plans are manual verification tasks:
no source owner, SSR/JSON-LD generation, deploy requirement or grouped-template
edit. Old counts/labels without a supported coherent receipt are not backfilled
as text equality or server-rendering proof. Typed count consistency is not
evidence authentication. Unknown/malformed/stale receipts stay unverified.

Without a rendered DOM no pair is measured. Existing completeness and private-host
guards remain: partial/missing/non-HTML paired snapshots produce no text-comparison
receipt, and known comparison coverage failures retain incomparable diff gates.

## Image weight, formats, and og:image
Single-page scans HEAD-check up to 10 page images (headers only — never full
downloads): >200 KB is heavy (top LCP cause; >=500 KB or 3+ heavy escalates),
JPEG/PNG over 100 KB are flagged as AVIF/WebP candidates, and >30% of <img> tags
missing width/height is a CLS risk. The og:image is validated with one ranged
GET (~64 KB) that parses PNG/GIF/JPEG/WebP headers for dimensions: unreachable →
high, under 200px → medium (previews break), under 1200px wide → low (no large
card). Skip with `--no-image-checks`; crawls skip these automatically (they
would multiply requests per page).

## Hreflang reciprocity (cross-page)
Google requires fully-qualified HTTP(S) alternate URLs, including the scheme;
relative/scheme-relative declarations must not be turned into accepted absolute
annotations by resolving against a page/base. Narwhal's bounded source classifier
omits missing, non-qualified, non-HTTP, parser-rejected or unsupported references
(including credentials/control/backslash cases). It does not certify complete
URI/IRI, locale/IANA, head-placement, language/translation or search eligibility.
Ordinary anchor links and canonical declarations keep their separate policies.

Successful parsed pages record `hreflang_policy_basis` and `hreflang_extraction`
(`basis=html_hreflang_absolute_http_source_v1`, `declared`, `accepted`, and reason
counts in `omitted`). Counts are parsed annotation occurrences, not unique URLs
or measured HTTP failures. Rejected URL values/exceptions are not serialized.
Receipts are self-consistency checked, not authenticated; legacy/malformed or
unknown bases remain unrecorded rather than inferred from a version.

Crawls retain source receipts even when every declaration is rejected. Sampled
relationship analysis distinguishes recorded missing references in supported
snapshots from unassessed pairs/self-checks under omitted/partial sources, and
targets outside the sampled/probed map. Unsupported source-address keys and
imported targets are counted without echoing rejected values. `checked_pairs`
counts directed retained declaration checks, not unique graph edges or verified
language versions. No green cluster certificate is issued; legacy coverage is
explicitly unrecorded. Full JSON facts remain; displays keep five self/six return/
code items with omission counts and 400-character URL/80-character code previews.

Optional production probes keep the existing five-target, same-host scope,
timeouts, redirect and SSRF controls. Zero budget means no requests; sampled
pages (including empty annotation sets) are not re-fetched. Only complete,
successful HTML/XHTML with explicitly recorded matching final URL identity
enters relationship analysis. Unavailable, truncated, non-HTML or redirected
identity snapshots remain unassessed, never inferred absent or dead. The optional
supplied-body callback is a computation/test hook, not HTTP identity verification.
Matching URL identity is not canonical/server equivalence or Google acceptance.
`probe_observations` records bounded selected-target outcomes (source observed,
unavailable, empty, partial, non-HTML, or changed identity), acquisition kind and
HTTP status when available, without raw exception/final-URL claims. `probed`
counts usable snapshot entries, not all attempts or redirect/network hops.
Reports display at most five probe observations with explicit omissions.

Already crawled pages use the same response classifier before relationship
analysis. `hreflang_source_observation` records the explicit
`html_hreflang_response_snapshot_v1` basis, bounded status, HTTP status and
guarded-HTTP versus rendered-snapshot acquisition kind. Unknown/malformed
receipts stay unassessed, not inferred complete. `source_observed` means a
nonempty, untruncated 2xx HTML/XHTML response without 206/Content-Range evidence,
with matching requested/final URL
identity under Narwhal's literal URL policy, not canonical/server equivalence
or search acceptance. A complete HTML document without alternates can establish
an observed missing return; an empty byte body cannot.

A scan can still audit the final page after a redirect. Its source counts,
findings and score remain final-page facts. For requested-URL relationships,
unqualified source tags are withheld from the map and cannot seed additional
probes. Sampled entries remain known/unassessed and are not re-fetched. Crawl
`sampled_source_observations` retains the acquisition receipts, including early
hard failures; the report shows the qualified/total counts and up to five
unassessed literals with explicit omissions. Rendered snapshot counts are
disclosed separately, not treated as original served HTML or crawler behavior.
The crawl `hreflang_acquisition_basis` distinguishes current/legacy relationship
measurement; changed policy is not evidence of a repaired site. These response
receipts add no scoring deduction, request, retry or new network permission.

Page/site notes expose known gaps and counts. Known current versus missing/
different policy, or known omissions relevant to selected technical scoring,
withhold diff/compare/brief improvement verdicts (CI diff gates exit 2).
Content-only scores are not invalidated by unselected technical checks. A new
low `technical.hreflang.urls.review` replaces unsupported clean-presence verdicts
and stays manual-only in plans: no guessed locale pages, owner files, schema
generation or source rewrite. The supported-presence rule ID is retained with an
observational label. Review title-based filters. Rule weights stay unchanged;
corrected findings/scores are tool calibration, not measured SEO/site gains.
`x-default` remains a conditional review of an intended fallback, not a universal
page requirement. Header/sitemap hreflang discovery is outside this HTML scope.

See [Google's localized-version guidelines](https://developers.google.com/search/docs/specialty/international/localized-versions)
for absolute URLs, return links and optional fallbacks (checked 2026-10-24).
