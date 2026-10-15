# Changelog

All notable changes to Narwhal are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

- Compare and content briefs retain each page's actual rendering flag in JSON
  and label served HTML versus JavaScript-rendered DOM in their reports. Missing
  legacy flags remain unknown; generic grounding text no longer calls rendered
  snapshots served HTML. Scores and gap/brief calculations are unchanged.

### Improved
- Final HTML-response `X-Robots-Tag` restrictions are audited with separate
  header findings and manual hosting remediation. Repeated raw fields retain
  scope boundaries; named-crawler policies remain non-scoring notes with
  additive `meta.http_robots` provenance. Browser/legacy boundary limits,
  unsupported preview/date rules and unverified actual indexing are explicit.
  Post-load cross-document browser navigation now fails explicitly instead of
  pairing an earlier response's headers with a replacement DOM. Ordinary HTTP
  redirects and same-document History API changes remain supported.
- Branded Markdown tables have scoped cell/header styling, semantic column
  headers and labelled keyboard-focusable scroll regions. Screen columns retain
  readable minimum widths; print/PDF input uses compact wrapping styles without
  scroll clipping or focus rings. Native scan score-table styling is unchanged.
  A Chromium regression now runs in CI for desktop/mobile/keyboard/print behavior.
- Non-passing page findings link to reference-guide sections in Markdown/HTML
  and PDF input, with additive `reference_url` JSON metadata. Unmapped rules use
  general category context; unknown categories and passing checks get no link.
  Destinations are static, never fetched by scans, and do not validate findings
  or change scores, severity, identities, suppression or diff classifications.
- Compare and brief CLI, Python and MCP interfaces accept a bounded per-snapshot
  `max_bytes` option, allowing deliberate retries of large-page coverage failures.
  The default remains 5MB; 64KB–20MB bounds apply uniformly to all compared pages
  and paired served/rendered inputs. Incomplete-input and private-host guards
  remain active; this is not a total network/browser memory budget.
- Reports lead with high/critical findings rather than an unqualified numeric
  grade. HTML/PDF heroes distinguish urgency from the explicitly labelled score
  band, and Markdown/HTML summaries put findings needing attention first.
- Numeric scoring, JSON finding data, execution-scope caveats and unavailable
  scores are unchanged. A high score does not hide a high-priority finding;
  heuristic findings still need source verification.

### Fixed
- Generic robots-meta checks combine all active tags, recognize `none` as
  `noindex,nofollow`, and match exact names instead of substrings/parameter
  values. Standalone restrictions before a parameter are retained; later tags
  are no longer hidden by an earlier allowing tag.
  Passing wording now says only that no generic meta noindex was detected, not
  that the page is indexable. Existing rule IDs remain; affected restriction
  findings/scores are corrected. This generic-meta observation excludes headers
  and crawler-specific meta; response headers are handled by the separate check above.
- Markdown tables honor left/center/right separator markers on both headers
  and body cells, including comparison score columns. Only static alignment
  classes are emitted; unmarked/missing/invalid markers retain default left
  alignment, and cell values, column counts and native score tables are unchanged.
- Markdown report tables honor escaped pipes in headers/body, including inline
  code, and retain empty first/last cells. Only the backslash escaping a pipe is
  removed; other backslashes and non-table content retain existing behavior.
- Markdown link destinations remain literal escaped data: underscores and
  asterisks in paths, queries and fragments no longer become emphasis tags in
  `href` values. Labels and surrounding text keep their supported formatting;
  existing HTTP(S)-only link recognition and literal-code guards remain.
- Inline code retains literal Markdown, links and escaped HTML rather than
  formatting its contents. Equal-length backtick runs allow embedded shorter
  runs; surrounding formatting still works. Code cannot become an href value,
  and internal span protection cannot collide with user text. Single-line spans
  retain inner whitespace; this remains a limited report Markdown subset.
- Branded Markdown rendering preserves root fenced code as escaped literal
  content, including whitespace, comments and Markdown-looking examples. Shared
  fence rules keep code headings out of title extraction; screen blocks scroll
  and print/PDF input wraps long lines. Existing non-code rendering and scan
  scoring are unchanged; this is a limited subset, not a full Markdown engine.
- In-memory/Python and parsed-object MCP plans explicitly require preserving the
  original report before verification diffs; read-only planning never saves it.
  Markdown keeps that prerequisite outside shell blocks. File-backed, measurement-
  check-only and empty plans do not receive invented save/diff tasks; actual manual
  hosting fixes retain their requested deployed verification. Coverage is unchanged.
- Sitemap-file discovery/traversal deduplicates literal fragment aliases before
  counting attempts, child slots and remaining files. Repeated `file.xml#…`
  references no longer crowd valid siblings out of bounded samples or multiply
  fetched-file URL entries. Query strings, encoded delimiters and page-location
  source values remain distinct/unchanged; fetch policies and limits remain.
- Planner verification templates avoid known baseline basename collisions for
  both scan and audit workflows, including local page checks. Alternate output
  names stay aligned with diff targets and Markdown, preserving an `after.json`
  or `page-after.json` baseline instead of creating a self-comparison. File aliases
  still require caller checks; the read-only planner does not inspect them.
- Audit-based remediation plans no longer suggest diffing a page scan against
  an audit overall score. Local page checks use a separate artifact; final
  verification reruns an audit after deployment and asks callers to restore the
  original settings and limits. Scan workflow semantics and diff eligibility guards remain.
- Planner verification commands use literal POSIX-shell quoting and an explicit
  option separator for report paths/URLs. Pasted dollar signs, substitutions and
  apostrophes remain data; leading dashes cannot become CLI options. Templates
  are labelled POSIX-specific and never executed by the read-only planner.
- Raw sitemap fetches verify bounded HTTP gzip/deflate wire bodies before
  decoding, including on older optional transports. Short Content-Length and
  incomplete/corrupt compression trailers cannot expose a complete-looking XML
  prefix. Both wire and HTTP-decoded bytes obey the response budget; raw `.gz`
  files retain the separate sitemap decode path. Unsupported HTTP encodings
  remain explicit fetch gaps, and network guards are unchanged.
- Sitemap discovery across scan context, crawl and site validation uses complete
  bounded namespace-aware XML instead of marker/loc regex guesses. Prefixed and
  gzip roots and XML-escaped URLs work consistently; unverified files cannot
  contribute crawl candidates. Candidate scopes/limits are explicit, uncertain
  availability is a non-scoring note/manual check rather than a missing-source
  verdict, and affected technical-score comparisons stay unverified.
- Remediation plans separate sitemap fetch/traversal/sample coverage gaps from
  recorded source defects. Uncertain and legacy-unclassified notes receive manual
  verification without guessed source owners or sitemap-creation instructions;
  consistent current counters add scoped fetch/cap context. Actual invalid URL/
  lastmod and failing sampled HTTP findings retain targeted repair advice.
- Raw sitemap fetches withhold failed HTTP bodies, oversized prefixes and known
  incomplete transfers consistently across requests/urllib. Exact-limit bodies
  remain valid; fetch failures are separate from XML extraction notes and cannot
  contribute URL totals or samples. Explicit failed-file counts label mixed totals
  incomplete. Responses and urllib redirect/error handles
  close on handled paths; unrelated processing errors propagate. Numeric header
  comparisons avoid unbounded integer conversion. Failed file attempts consume
  the sitemap traversal cap, and remaining counts deduplicate visited references.
  Network guards are unchanged.
- Short, unencoded requests streams below the raw byte limit are explicitly
  checked against Content-Length, including older supported optional dependency
  combinations. Encoded/transfer-decoded body sizes are not mistaken for wire
  lengths; complete and encoded controls remain usable.
- Sitemap gzip decoding uses sized streaming reads and a shared per-file
  decoded-byte ceiling of 52,428,800 bytes, including concatenated members.
  Oversized or corrupt/truncated gzip files contribute no XML prefix, URL entries
  or HTTP samples; fixed extraction notes distinguish budget/integrity gaps and
  retain verified siblings. The legacy decode helper is also bounded. This is
  not a total process-memory, CPU or transport budget.
- Crawl and combined audit reports distinguish zero link checks, gated/unknown
  HTTP responses and insufficient duplicate-comparison inputs from clean results.
  Additive coverage counts retain successful, broken and unverified checks;
  no-response request failures stay unverified while legacy unreachable entries
  remain available, distinct from observed broken HTTP responses;
  duplicate scope counts eligible fingerprints, excluding known failed/partial
  pages. Missing legacy receipts stay unrecorded. Headlines label observed/sample
  results rather than presenting disabled checks as zero. Scoring is unchanged.
- Sitemap validation and combined audits record bounded XML extraction coverage
  instead of treating markers, malformed prefixes or unsupported roots as measured
  URL lists. Namespace-aware extraction decodes XML escaping; incomplete files
  contribute no entries, while verified siblings remain usable. Coverage gaps
  get manual verification advice, not instructions to rewrite unsupported formats.
  Sample success requires a successful 2xx response; gated/other responses no
  longer count as OK, and skipped samples explicitly leave reachability unverified.
- Malformed/non-absolute discovered sitemap references no longer abort site
  context, anchor-independent crawl discovery or sitemap validation. Robots
  directives, index children and page locations are syntax-checked before use;
  valid siblings/fallbacks remain available. Bounded source counts distinguish
  rejected references from HTTP failures, preserve raw entry/problem totals,
  and do not echo invalid URLs. Sitemap health is not declared after rejections,
  fetch errors or a reached file cap. User-input errors and fetch guards are unchanged.
- Malformed anchor hrefs no longer crash technical checks, link collection or
  anchor-based crawl discovery. Valid later links remain usable. A low source
  finding and conditional page/crawl omission counts distinguish parser-known
  URL syntax issues from network-dead links, without retaining raw hrefs or
  exception messages. Direct user URL errors and actual-fetch host/redirect
  protections remain unchanged; this is not complete URI or sitemap validation.
- Image-only links with descriptive image alternatives, and otherwise-empty
  links with title fallbacks, no longer receive the empty-anchor-text heuristic.
  Both parser backends retain image alternatives separately from visible text;
  blank/generic fallbacks and independent missing-alt checks remain active.
  This is documented source fallback handling, not a full accessibility-name or
  visibility computation. Existing finding identities and severities remain.
- Robots full-URL matching retains semicolon path parameters, so path-specific
  exclusions and more-specific allowances agree with direct path checks.
  Queries, fragment exclusion and encoded reserved-delimiter distinctions remain.
- Robots matching treats equivalent unreserved ASCII escapes and UTF-8 URI
  spellings consistently, preventing encoded candidates from evading crawl
  exclusions. Encoded reserved delimiters remain distinct, literal encoded
  wildcard/end characters stay literal, and normalized equivalent rules retain
  Allow-on-tie precedence. Path case, explicit robots overrides and existing
  checked-path scopes are unchanged; no complete conformance claim is added.
- AI-crawler scoring distinguishes documented search/retrieval agents from
  training/data-use choices, nonbinding user-fetch directives and unverified
  roles. The latter stay visible as non-scoring policy notes, not blanket
  visibility penalties or instructions to enable training. Page JSON includes
  dated primary-source roles and robots-only `/` scope; current retrieval agents
  are covered without claiming live access, indexing or citations. The existing
  high finding identity/title ignores and planner ownership remain compatible.
- Unknown and non-text HTTP charset names produce bounded failed-fetch
  diagnostics rather than crashing optional `requests` scans or guessing an
  encoding. Supported decoding and malformed-byte replacement are unchanged;
  unrelated processing errors still propagate on the requests path.
- Optional `requests` connection/TLS/timeout and interrupted-body failures now
  return failed-fetch responses instead of aborting scans. Failed streams do
  not expose a received prefix as usable HTML; acquired responses close even
  when decoding or unexpected processing errors propagate. Successful fetches,
  HTTP error status/body diagnostics, and SSRF checks are unchanged.
- Served-HTML baselines use the same selected byte budget as rendered snapshots.
  JS-dependence metrics require two eligible HTML inputs; unavailable, partial or
  explicitly non-HTML baselines yield a visible unverified receipt, not invented
  percentages or cached results. Known missing JS measurements block relevant
  score/finding diffs, including crawl contributions, and compare/brief score
  benchmarks; focused non-JS scores remain comparable. Primary coverage is kept
  distinct from auxiliary baseline coverage. Legacy receipts are not inferred.
- Rendered HTML snapshots now obey the primary HTML byte budget in UTF-8, with
  explicit truncation metadata and no broken final code point. Partial rendered
  snapshots do not produce JS-dependence measurements. Smaller complete snapshots,
  errors, SSRF checks and browser cleanup retain their behavior. This caps retained
  analysis input, not Chromium DOM memory or subresource downloads.
- Origin response headers cannot forge Narwhal's internal truncation marker;
  raw and rendered coverage reflects the client's byte-count calculation.
- Comparisons and content briefs exclude reports explicitly marked as truncated,
  rather than turning unseen HTML into missing-feature gaps or full-page scores.
  Partial targets return errors; partial rivals are skipped with diagnostics.
  Brief requests without any usable page are errors, not page-grounded briefs.
  Standalone partial scans remain available with their coverage warnings; missing
  or malformed legacy flags are not inferred to prove truncation/completeness.
- Content-brief headings, recommendations, CLI help and plugin guidance describe
  supplied comparison pages rather than unverified ranking "winners." Own-page
  Search Console data does not establish competitor rankings. Facts, scoring,
  JSON data and recommendation generation remain unchanged.
- Content briefs retain one supported built-in rule policy across own-page and
  competitor scans, including topic mode and failed competitors. Mid-run caller
  updates no longer switch later pages' scoring/suppression; future briefs still
  see updates. Custom policies stay live; remote content/context is not frozen.
- A failed first URL in competitor comparisons cannot promote a rival to "You"
  or produce a successful target/competitor verdict. HTTP failures, host-policy
  rejection and non-HTML targets yield error diagnostics and CLI exit 2; failed
  competitors remain skippable when the requested target and another rival load.
- Competitor comparisons retain one supported built-in rule policy across page
  scans, including when a failed competitor fetch mutates caller configuration.
  Future comparisons still see caller updates; custom callbacks stay compatible
  and unverified. Remote content and per-site context are not frozen.
- Site-wide human-readable rollups prioritize severity before frequency, so a
  rare critical/high finding is not hidden by more common lower-priority types.
  Ties are deterministic and capped lists disclose omitted types. JSON retains
  its full frequency-ordered counts; scoring and finding generation are unchanged.
- Crawls and audits retain one built-in rule policy across their component/page
  scans instead of mixing configurations after mid-run caller updates. Gathered
  crawl threshold overrides are owned before discovery/worker I/O; audit sitemap
  sampling is resolved at entry. Future operations still see caller changes;
  custom policies stay compatible and unverified.
- Built-in rule inputs and context threshold overrides are owned per scan, so
  caller mutations during page/render I/O or between auditors cannot invalidate
  recorded rule provenance or silently change suppression. Completed reports keep
  their ignore policy; future scans see updated inputs. Custom policies/shapes
  preserve their behavior and remain unverified without invoking copy hooks.
- Diffs no longer count skipped image checks or changed raw/rendered page modes
  as verified fixes when those settings are recorded. Scans serialize requested
  and actual rendering plus effective image-check selection; audits preserve
  crawl-page settings and compare shared exact URLs. Known differences block
  score/finding verdicts and return gate exit 2. Missing legacy settings are not
  inferred, and matching flags do not prove identical configuration or samples.
  Visible scope notes identify disabled images and served/rendered HTML, including
  render requests that produced no measured rendered DOM.
- Recorded fingerprints of scoring weights, effective thresholds and normalized
  ignore rules block fake fixes caused by suppressing findings or changing their
  penalties. Fingerprints expose no raw configuration values or paths; unknown
  custom/unserializable shapes remain unverified. Ignore ordering/case/duplicates
  and equivalent integral numeric weights do not cause spurious mismatches.
  Reports retain their scoring-weight snapshot, so later Config mutations cannot
  silently change a saved report's score while leaving its provenance unchanged.

## [1.30.19] — 2026-10-12

### Fixed
- Native numeric zero is present merchant evidence, not a missing price. Zero
  Offer prices retain the high nonpositive-price finding and can be compared
  against explicit matching-currency page amounts; they are not replaced by
  a positive priceSpecification fallback. Missing/positive prices and boolean
  handling retain their existing behavior.

## [1.30.18] — 2026-10-12

### Fixed
- JSON-LD value objects and their opaque JSON literal payloads are not entity
  nodes. Tutorial examples no longer create Product/Offer merchant evidence, and
  value datatypes no longer appear in the entity-type coverage summary.
- Literal payloads preserve arrays, datatype IRIs, context data and exact JSON
  content through normalization and deduplication. Real graph/list entities and
  independent merchant cues remain active. This is not full JSON-LD expansion
  or datatype/value validation; scalar value interpretation remains bounded.
- Product classification also excludes context definitions and value objects.
  Literal-valued offers are not counted as purchase/Offer evidence.

## [1.30.17] — 2026-10-12

### Fixed
- Point Offer prices and multi-Offer consensus use exact bounded decimal parsing:
  scientific notation is not digit-stripped, and long unequal prices are not
  rounded equal by the caller's Decimal context.
  JSON decimal number tokens retain their lexemes rather than rounding through
  binary floats before comparison.
- Point-price comparisons, like ranges, require explicit matching currency units
  and parseable observed amounts. Supported localized display forms remain;
  prose, malformed separators and conflicting units are not guessed. Other
  currency/stock/identity and completeness checks remain active.
- Unsupported declared price text produces a low extraction/verification note,
  not a schema.org invalidity verdict. Known nonpositive merchant prices retain
  their high finding. JSON exposes exact point-comparison evidence and limits.

## [1.30.16] — 2026-10-12

### Fixed
- Diffs no longer classify omitted auditor groups as resolved fixes. Known
  mismatched or incomplete execution, truncated HTML and page/audit score-kind
  mismatches produce an explicit incomparable diagnostic with no change verdict.
- `--fail-on-regression` exits 2 for known incomparable coverage. JSON records
  comparison status/reasons and null score delta/regression for unmeasured
  comparisons; matching completed full/focused scopes retain normal diff gates.
- Legacy/malformed execution scope remains unknown, not inferred from findings.
  Compatible legacy comparisons now warn visibly; matching auditor scope alone
  does not prove identical configuration, rendering, rules or site-wide samples.

## [1.30.15] — 2026-10-12

### Fixed
- Scan, audit, crawl, llms and sitemap CLI boundaries report expected URL syntax,
  DNS/host-policy rejections as bounded single-line diagnostics with exit 2,
  rather than tracebacks or successful-looking scan reports. Programming errors,
  interrupts and argparse behavior remain visible; core APIs still raise.
- URL normalization validates lazy host/port syntax and classifies expected
  failures without weakening SSRF checks. Explicit private previews remain
  opt-in; no output is written or overwritten on rejection. Syntax diagnostics
  do not echo parser errors containing URL credentials or query values.
- Initial sitemap targets are validated before discovery/walking, so a blocked
  direct XML target does not emit an error report with exit 0. Crawl/llms entry
  URLs normalize before parsing site context; supported bare hosts and valid
  ports remain usable.

## [1.30.14] — 2026-10-12

### Fixed
- Focused scans identify requested, completed and unselected auditor groups in
  JSON, Markdown and HTML/PDF. Selected-check scores are no longer presented as
  overall page health; full selections remain page-level, not exhaustive audits.
- Failed/non-HTML responses record no completed auditors and show a fail-safe
  zero as not measured, without fabricated area grades. Truncated response
  coverage stays explicit; legacy reports do not infer scope from finding counts.
- Duplicate auditor selections run only once. Custom report titles remain;
  accessible gauges and threshold failures use the correct scope label. Normal
  unique-selection score weights and findings are unchanged.

## [1.30.13] — 2026-10-12

### Fixed
- Recipe base-field checks now follow Google's name/image requirements.
  Ingredients and instructions are recommended, not mandatory; absent/blank
  required name/image values are high findings instead of passing as complete.
- Recipe reports expose dated primary-source policy and unverified conditional,
  nested, image and datatype/reference scope. Recommendations never ask for
  invented authors or ratings, and are not full rich-result eligibility verdicts.
- Recipe generators align required/recommended fields while preserving useful
  scaffolds and explicit fields. Legacy ingredient/instruction-only ignores stay
  field-scoped; other schema types and existing name/recommendation IDs remain.

## [1.30.12] — 2026-10-12

### Fixed
- Article, NewsArticle and BlogPosting no longer treat headline as a mandatory
  rich-result property. Missing applicable headline/author/datePublished/image
  values are grouped low recommendations, with Google's no-required-properties
  scope and dated source metadata, not invalidity or eligibility verdicts.
- Absent/blank Article values are detected without inventing authors/dates or
  claiming full datatype/reference validation. Other types retain their existing
  checks; legacy headline-only ignores do not suppress unrelated recommendations.
- Article-family generators label headline recommended, not required; the
  no-recommended mode does not inject mandatory placeholders. Explicit fields
  and useful default scaffolds remain. Reference and specialist guidance align.

## [1.30.11] — 2026-10-12

### Fixed
- Google rich-result retirement notices now use source-checked current status:
  FAQ appearances ended in May 2026; ClaimReview and SpecialAnnouncement support
  ended in 2025. ClaimReview's Fact Check Explorer use is explicitly preserved.
- Notices distinguish Google visual appearances from schema.org validity or
  ranking, with dated primary-source provenance in JSON and recommendations.
  Historical finding IDs, low severity and legacy title-substring ignores remain
  stable. Sources are not fetched during scans; valid FAQ generation remains.
- Schema reference and specialist guidance no longer describe retired FAQ and
  ClaimReview appearances as merely restricted. Feature-specific Course Info
  retirement is not generalized to all Course markup or Course list support.

## [1.30.10] — 2026-10-12

### Fixed
- Product H1/name comparisons now use the selected Product name, never an
  Offer's sale/seller label. Offer names cannot create false Product mismatches,
  mask genuine name disagreements or fill a missing Product name.
- Existing variant selection, range/price/currency/stock comparisons and
  non-name field source precedence are unchanged. Local references and all
  supported structured-data formats retain their original node names.

## [1.30.9] — 2026-10-12

### Fixed
- Inert source templates no longer supply JSON-LD, metadata, canonical links,
  headings, links, images or language to the normalized page view. A cached
  stdlib projection is shared by HTML backends, main-content extraction and lazy
  Microdata/RDFa/merchant consumers; original HTML remains available as evidence.
- Nested/unclosed templates and non-void template slash syntax are consistent
  across backends. Script/style text and textarea/title literals cannot open or
  close templates; comments and entities are preserved. Ordinary hidden JSON-LD
  remains readable. Malformed marked declarations do not abort projection.
- Chromium smoke coverage checks inert Product examples are ignored and
  JavaScript-cloned active Product schema is detected exactly once. This source
  projection is not a complete HTML5, foreign-integration or shadow-root parser.

## [1.30.8] — 2026-10-12

### Fixed
- A single AggregateOffer compares the displayed amount against its inclusive
  lowPrice/highPrice range, not the lower bound as an exact seller price. Valid
  numeric bounds and matching explicit currencies are required; outside-range
  amounts remain high mismatches. JSON records range-compatibility evidence,
  not proof of a selected seller or an Offer at every interior amount.
- Missing, unsupported or incomparable range evidence gets a verification note
  while completeness/currency findings remain. Known negative or inverted
  numeric bounds get a high range finding. Decimal comparisons do not round
  quoted amounts; ordinary Offer and multi-Offer consensus behavior is preserved.

## [1.30.7] — 2026-10-12

### Fixed
- Multiple Offers no longer select the first price/currency/stock value for page
  comparisons. Non-unique or incomplete fields get a low verification note;
  agreed fields and Product identity checks remain active.
- Numeric price consensus requires matching declared and observed currencies;
  any AggregateOffer in a multi-Offer comparison blocks Offer-based price
  consensus, including homogeneous sets. Per-field
  `offer_comparison_status` is explicit in JSON. All-offer validity/completeness
  checks and existing single-Offer behavior are preserved.

## [1.30.6] — 2026-10-12

### Fixed
- Microdata, RDFa and merchant-source warning output is bounded: 64 retained
  details per extraction plus one explicit omission notice, with 512-character
  detail limits and visible truncation markers. Valid extraction continues.
- Warning deduplication is bounded and constant-time; repeating a retained
  warning at the cap does not incorrectly claim additional details were omitted.
- Omission/truncation summaries remain visible in HTML quick-win recommendations.

## [1.30.5] — 2026-10-12

### Fixed
- Non-string Offer references and non-object price-specification members no
  longer crash merchant scans. Malformed IDs are field-specific findings;
  unsupported price-specification shapes produce a bounded-coverage note.
- Supported object members survive mixed arrays; null members remain ignored.
  Local string Offer references, completeness checks and real price mismatches
  remain intact. No remote reference or JSON-LD context is fetched.

## [1.30.4] — 2026-10-12

### Fixed
- Multi-Product page comparisons no longer choose the first schema variant.
  A unique visible identifier, exact name or unambiguous name match is required;
  ambiguous identity produces a low-severity verification note instead of a
  guessed mismatch. All Product/Offer completeness and validity checks remain.
- Comparison status and selection method are explicit in JSON; no selected
  Product is reported when identity is ambiguous. SKU punctuation and Unicode
  characters remain significant in selection and mismatch checks.

## [1.30.3] — 2026-10-12

### Fixed
- Malformed Product and Offer URLs produce field-specific findings instead of
  crashing scans. Missing hosts, invalid ports, embedded whitespace/control
  characters and backslashes are rejected by local syntax validation.
- Valid IPv6, Unicode hosts, encoded paths and non-default ports remain accepted.
  Validation does not resolve DNS, fetch offer URLs or claim reachability.

## [1.30.2] — 2026-10-12

### Fixed
- Merchant evidence now uses one cached, bounded source parse instead of regex
  matches over HTML. Templates, comments, escaped examples and explicitly hidden
  subtrees cannot supply price, identity, labels or purchase controls.
- Inactive OpenGraph examples cannot classify articles as Product pages; the
  first active type declaration retains preference order.
- Active itemprop values support multi-name properties, exact schema.org URLs
  and element-specific values. Linked brand names use their visible label.
- Partial merchant-source coverage and invalid URL warning limits are explicit
  in JSON and a stable verification finding. No browser visibility is claimed.
- RDFa tests support both root and skill-directory test discovery.

## [1.30.1] — 2026-10-12

### Fixed
- Merchant classification now requires Product evidence and a selling signal;
  documentation and SKU-only editorial reviews no longer enable store checks.
- Prose-label fallback requires an explicit separator rather than interpreting
  schema vocabulary definitions as brand, SKU or availability facts.
- Crawl merchant rollups reject contradictory legacy non-product flags.
- Purchase-action fallback requires an enabled control or same-origin purchase
  link; prose, inert/hidden controls and external affiliate links are excluded.

## [1.30.0] — 2026-10-11

### Added
- Bounded, stdlib-only schema.org RDFa extraction: scoped vocabularies/prefixes,
  nested entities, local subject references, resource URLs and scalar literals.
  Unsupported relations/lists/copying/markup literals and resource limits are
  explicit partial-coverage warnings; no referenced resources are fetched.
- Shared JSON-LD/Microdata/RDFa schema and merchant checks, three-format
  deduplication, RDFa provenance and coverage metadata, and comparison facts.

### Fixed
- Valid supported RDFa no longer receives missing-structured-data penalties.
  Inert examples, foreign namespaces and vocabulary rebinding do not create
  product false positives. Remediation guidance preserves valid RDFa.

## [1.29.0] — 2026-10-11

### Added
- Stdlib-only schema.org Microdata extraction: nested scopes, repeated and
  multi-name properties, typed values, relative URLs, item IDs, and bounded local
  `itemref` resolution. Extraction limits and invalid references remain visible.
- Shared JSON-LD/Microdata schema and merchant validation, format provenance in
  scan JSON, equivalent-node deduplication, and Microdata-aware comparison facts.

### Fixed
- Product/Offer Microdata no longer receives missing-JSON-LD penalties. Inert
  templates, escaped examples, and lookalike namespaces do not classify articles
  as product pages. Remediation guidance preserves existing valid markup.

## [1.28.0] — 2026-10-11

### Added
- Full Markdown, JSON, and self-contained HTML report golden snapshots from a
  fixed offline fixture, plus a one-command regeneration script.
- Evidence-gated e-commerce checks within the schema auditor: Product and
  ProductGroup detection, per-variant identity completeness, Offer and
  AggregateOffer merchant properties, nested `priceSpecification`, expired
  price validity, and explicit visible-vs-schema price, currency, availability,
  SKU, brand, and name comparisons. Crawl/audit JSON exposes sampled merchant
  pages for conditional orchestration.
- Conditional `narwhal-ecommerce` deep-audit specialist plus dedicated
  remediation-planner ownership and guidance for `schema.ecommerce.*` rules.
- Product, non-product, malformed, AggregateOffer, variant, stale, missing, and
  mismatch fixtures with parser-backend parity coverage.

### Changed
- Package metadata, CLI, and report provenance now share one canonical release
  version. A stdlib synchronization command updates plugin manifests, and CI
  rejects drift instead of relying on manual edits across six files.
- Split the 2,095-line smoke-test monolith into focused parser, auditor,
  report, tool, and integration modules while preserving zero-config discovery.
- Product schema generation now emits explicit TODOs for merchant currency,
  availability, URL, condition, and seller instead of assuming USD/InStock.

## [1.27.0] — 2026-08-10

### Added
- **`narwhal plan REPORT.json --repo PATH`** — a deterministic, read-only
  remediation planner for scan and comprehensive-audit JSON. It detects plain
  HTML, Next.js, Astro, Nuxt, Hugo, and Jekyll; maps stable finding IDs to likely
  route/layout/static owners; classifies automation safety and deploy-only
  verification; groups shared-template work; and reports conflicts, coverage,
  warnings, and provenance in Markdown or a versioned JSON contract.
- MCP tool **`plan_remediation`**, bounded to relative repository descendants of
  the server working directory and accepting report objects rather than file
  paths.
- MCP Python SDK 2.x compatibility (while retaining 1.x support) and a two-major
  CI contract matrix; this prevents `mcp>=1.12` from resolving to an SDK whose
  renamed high-level server cannot start.
- Formal remediation-plan JSON Schema, six representative framework fixtures,
  and golden Markdown coverage.

## [1.26.0] — 2026-07-03

### Added
- **`narwhal brief` — data-driven content briefs** (closes
  [#26](https://github.com/aindong/narwhal/issues/26)). Turns "what should we
  write?" into a plan grounded in data Narwhal already has — no keyword APIs,
  no fabricated search volumes:
  - **Target queries** from the page's own GSC **striking-distance** rows
    (positions 8–20), plus its CTR-laggard / decay / cannibalization status —
    real Search Console data only. Without credentials the brief degrades to a
    clearly labeled **structure-only** brief (queries omitted, never invented).
  - **Competitor gaps** via the `compare` engine (schema types, meta strategy,
    OG/social packaging), deduplicated against the structure section.
  - **Missing subtopics** — competitor H2/H3 sections whose topic words don't
    appear in your page text (inflection-tolerant matching; nav/footer
    boilerplate and one-word column labels filtered out).
  - **Questions to answer** — competitors' question-shaped headings you don't
    cover + your own question-shaped striking queries.
  - **Schema suggestions** (`narwhal schema <Type>` for each) and **structure
    targets** (depth/evidence benchmarks vs the compared pages; hub pages
    excluded as benchmarks).
  - **`--topic` mode** plans a page that doesn't exist yet from competitor
    pages; `--gsc-site` folds in real adjacent queries site-wide.
  - Wired everywhere: `narwhal brief` CLI, **`/narwhal brief`**
    (agent-orchestrated editorial synthesis: outline, metadata drafts, branded
    HTML via `narwhal render`), and MCP tool **`content_brief`**.

### Fixed
- **`compare`: false "Content depth" lead when every rival is a hub page**
  (found live while building the brief). The lead check's `all()` over non-hub
  rivals was vacuously true, so a 138-word page "led" a 521-word competitor.
  Depth gap/lead now compares only non-hub rivals, with a regression test.

12 new tests (191 total), green stdlib-only and with bs4/lxml/trafilatura.

## [1.25.1] — 2026-07-02

### Fixed
- **`<noscript>`-fallback content is now measured** (corpus addition:
  openskyelabs.xyz). JS-shell sites that serve their entire content inside
  `<body><noscript>…</noscript>` scanned as **"~0 words"** with empty
  headings/links — while non-rendering crawlers and AI fetchers read that
  fallback just fine. Both parser backends now capture noscript into a separate
  channel: `body_text` falls back to it when the page has no regular body text
  (labeled `measured on noscript fallback`), headings/links inside noscript keep
  their text, and tiny noscript blocks (font loaders) change nothing.

### Added
- New technical finding: **"Content served only as a `<noscript>` fallback"**
  (medium) — rendering and non-rendering crawlers see different documents;
  SSR/SSG recommended. 3 new tests (179 total), green with and without extras
  (with trafilatura installed the same content is isolated by trafilatura —
  covered by the tests).

## [1.25.0] — 2026-07-02

Tuning Round 2 (documented with raw snapshots in `docs/tuning/2026-07-round-2/`):
corpus grown 8 → 14 pages by adding page *types* — product URL, real articles, a
Recipe-schema page, a French site, an international hreflang site, and a
deliberately dead URL. Two live specialist runs graded (schema: validated the
full Recipe graph beyond the script; performance: measured real wire sizes and
caught a caveat in our own image check).

### Fixed
- **Unfetchable pages now score 0** — a 404 used to score 88/100 (one critical
  finding = −12), which read as "healthy". New `Report.hard_fail`.
- **og:image behind a rate-limiting CDN is no longer "broken"** — gated codes
  (429/403/…) now report "could not be verified" (low), reusing the broken-link
  checker's UNDETERMINED semantics.
- **Non-English pages skip English-calibrated checks** (Flesch readability,
  filler/AI-writing patterns) — and claim nothing, instead of mislabeling
  French prose "very hard to read".

### Changed
- **Readability severity is article-scoped** — terse marketing homepages get
  low, not medium.
- **"No structured data" is low on hub/index pages** (no single entity to mark
  up); articles/products/homepages keep medium.
- **Heavy-image findings are srcset-aware** — when every heavy image carries
  srcset, the finding is framed as *fallback weight* (what scrapers and
  srcset-unaware clients download) and capped at low. Lesson credited to the
  graded performance-agent run; also encoded in the agent's prompt.

6 new regression tests (176 total), green with and without parser extras.

## [1.24.0] — 2026-07-02

### Added
- **Cross-page hreflang validation** (closes #25 — the last P1 of the next
  wave; `lib/hreflang.py`). When a crawled site uses hreflang, the crawl now
  verifies the *relationships*, not just per-page syntax:
  - **Missing return tags** reported as exact `A → B (lang)` pairs — one-way
    hreflang is ignored by Google, so this is the killer check.
  - **Missing self-references** (each page must list itself) and **invalid
    language codes** (BCP-47 subset: lang / optional script / optional region).
  - **Sample-wide x-default** presence check.
  - **Capped alternate probe**: up to 5 same-host alternates the crawl didn't
    reach are fetched (link tags only) so reciprocity is actually verifiable.
  - **Cap-aware honesty**: targets outside the crawled/probed sample are
    counted *unverified* — never reported broken.
  - Verified live on a 137-locale international site: probe verified 5
    alternates reciprocal, correctly flagged the missing x-default, and labeled
    786 outside-sample targets unverified. 7 new tests (170 total), green with
    and without parser extras.

## [1.23.0] — 2026-07-02

### Added
- **Image weight/format checks + og:image validation** (closes #24,
  `lib/images.py`). Single-page scans now check, within a strict budget (up to
  10 HEAD requests — headers only — plus one ~64 KB ranged GET):
  - **Heavy images**: >200 KB flagged with real sizes as evidence (≥500 KB or
    3+ heavy escalates to medium) — a top LCP cause.
  - **Legacy formats worth converting**: JPEG/PNG over 100 KB → AVIF/WebP
    candidates.
  - **Missing width/height** on >30% of images → CLS risk (pure, no network).
  - **og:image validation**: reachability (broken → high) and **real
    dimensions** parsed from partial bytes — a stdlib PNG/GIF/JPEG/WebP header
    prober (`probe_dimensions`), no imaging library. Under 200px → medium;
    under 1200px wide → low; healthy gets a passing note with the dimensions.
  - `--no-image-checks` to skip; crawls skip automatically (per-page HEADs
    would multiply). New SSRF-guarded `http.head_info` and `http.fetch_range`.
  - Verified live: real og:images probed correctly (1200×630 and 2048×1024) and
    genuine heavy/legacy findings on two major sites. 4 new tests (163 total),
    green with and without parser extras.

## [1.22.0] — 2026-07-02

### Added
- **JS-dependence check** (closes #23, `lib/jsdiff.py`): scans run with
  `--render` now diff the **served HTML against the rendered DOM** and report —
  the **JS-only share of the content** ("1 word served vs 407 after JavaScript —
  100% JS-only", tiered: ≥30% high / ≥10% medium), **headings that only exist
  post-JS** (as evidence), and **client-injected head metadata**
  (title/description/canonical high; JSON-LD medium). A GEO finding fires on
  heavy dependence — most AI answer-engine fetchers don't execute JavaScript.
  - Honest by design: without Playwright there is no rendered DOM, so the check
    is silent — it never guesses. Server-rendered pages get a passing note.
  - Verified end to end with real Chromium: a local CSR fixture (100% JS-only
    detected) and a real SSR site (0% + a genuine client-injected JSON-LD
    finding). 5 new tests (159 total), green with and without parser extras.

## [1.21.0] — 2026-07-02

### Added
- **Site-structure analysis in every crawl** (closes #22, `lib/sitegraph.py`):
  the crawler now builds the internal-link graph from pages it already parsed
  (zero extra requests) and reports — **click depth** from the start URL (buried
  pages flagged past 3 clicks), pages **unreachable** from the start within the
  sample, **zero-inbound** pages (weak link equity), **most-linked** pages, and
  sitemap **orphan candidates** (sitemap URLs no crawled page links to; crawled
  pages are excluded — they're covered by zero-inbound with more certainty).
  - **Sample-aware honesty**: every claim carries the crawl-sample size; orphan
    detection only runs when a sitemap was actually found.
  - In `crawl` and `audit` Markdown/JSON automatically (`graph` block); the
    `narwhal-links` specialist is pointed at it.
  - Link collection is now always on during crawls (pure parsing, no extra
    network), so the graph needs no flag.
  - Verified live on a real 12-page crawl (correctly surfaced unlinked taxonomy
    pages and an unlinked content section as orphan candidates). 5 new tests
    (154 total), green with and without the optional parser extras.

## [1.20.0] — 2026-07-02

### Added
- **`narwhal compare <you> <rival…>` — side-by-side competitor comparison**
  (closes #21). Runs the same auditors on your page and 1–3 competitor pages,
  extracts comparable facts (per-area scores, schema types, title/meta strategy,
  depth, structure, question headings, evidence, social packaging), and reports:
  a **scoreboard**, a **side-by-side fact table**, **"Gaps to close"** (what they
  have that you don't, each with the action), and **"Where you lead"**.
  - **Local-first by design**: it only fetches the pages you name — no rank or
    keyword APIs — and the report says explicitly that a gap is an on-page
    difference, *not proof of why anyone ranks*.
  - Resilient: a dead/unresolvable competitor URL is skipped with a note instead
    of sinking the run (found via live testing).
  - Plugin-native (`/narwhal compare`), MCP tool (`compare_pages`), documented in
    SKILL/AGENTS/README; Markdown/JSON output; schema-type gaps grouped into one
    actionable entry.
  - Verified live: vercel.com vs stripe.com and jvns.ca vs blog.cloudflare.com
    (the latter independently re-found the OG/Twitter gap our content specialist
    had reported). 6 new tests (149 total).

## [1.19.0] — 2026-07-02

Real-world tuning round (#19, #20): scans of 8 diverse live sites (SaaS,
e-commerce, news, docs, blog, wiki, link-hub) + 3 live specialist-agent runs,
then every false positive fixed at the source. Average score change on well-run
sites: jvns.ca 62→79, HN 52→66, docs.python.org 75→86, The Verge 71→80 — all
from removing *wrong* findings, not loosening checks.

### Fixed
- **Stdlib parser lost headings that wrap links** (`<h1><a>…</a></h1>` recorded no
  H1 — false "No H1" on most real blogs) and **dropped all anchor text from the
  visible text** (link-heavy pages looked falsely thin). Captures are now a stack
  and captured text flows into the page text; `<title>` stays out of body copy.
- **Month names counted as "dominant topics"** on date-heavy archive pages
  (`dec (78), jan (74)…`) — now stopworded.

### Changed — page-type-aware checks
New shared helpers (`htmlx.is_hub_page` / `looks_article` / `is_homepage` /
`link_text_share`) scope checks to the page's role:
- Brand-only **homepage titles** are a low note, not "Title very short (high)".
- **Link-hub/index pages** get "hub with little prose (low)" instead of "Thin
  content (high)"; readability isn't judged on nav fragments.
- **Byline/author** is only expected on article pages.
- GEO **question-headings** and **evidence-density** are medium on articles, low
  elsewhere (they used to fire on ~90% of real sites).
- The schema auditor's "article-like page" now uses the shared heuristic instead
  of raw text length (no more Article-schema nags on text-heavy homepages).
- Depth findings state their **extraction basis** (trafilatura main-content vs
  visible text), and the trade-off is documented (#20).

### Changed — specialist agents (tuned from graded live runs)
All 10 `agents/narwhal-*` prompts gain **Judgment rules**: classify the page type
first and discount type-mismatched script findings; sample a representative inner
page when auditing a domain root; respect deliberate owner choices (e.g.
intentional AI-crawler opt-outs — split advice by intent, never "fix" an opt-out).
GEO adds the training-vs-answer-engine distinction (GPTBot ≠ AI-answer
visibility); technical verifies surprising negatives in raw HTML. Specialists now
return a **Discounted script findings** section, and the audit orchestrator
honors it (discounts are never re-added to the action plan).
`${CLAUDE_PLUGIN_ROOT}` confirmed to resolve for subagents in the field.

## [1.18.0] — 2026-07-02

### Added
- **Google Search Console integration (`narwhal gsc <site>`)** — opt-in, real
  query data for your verified property: **striking-distance** queries
  (positions 8–20 with impressions), **CTR laggards** (top-10 rankings far below
  the expected-CTR curve — title/meta rewrite candidates; the curve is a labeled
  heuristic), **decaying pages** (clicks down ≥25% vs the prior window), and
  **keyword cannibalization** (several pages splitting one query). Markdown/JSON
  output; `--days`, `--min-impressions`.
- **Stdlib-only OAuth** (GSC has no API-key path): `GSC_ACCESS_TOKEN`
  passthrough, or the durable `GSC_CLIENT_ID`/`GSC_CLIENT_SECRET`/
  `GSC_REFRESH_TOKEN` trio — obtained once with **`narwhal gsc --auth`**
  (loopback browser consent; `--write-env` stores the credentials in `.env`).
  Read-only scope; only fixed Google hosts are contacted. Service-account auth
  deliberately deferred (would need a crypto dependency).
- **`narwhal audit --gsc`** folds the same data into the audit (new
  "Search performance (GSC)" section in Markdown/HTML, `gsc` block in JSON, and
  a clicks headline in the metrics strip), mirroring `--vitals`; degrades to a
  one-line note without credentials. `/narwhal audit` now prioritizes the action
  plan by real queries when the block is present, and `/narwhal fix` fixes pages
  with actual search opportunity first.

### Changed
- The audit's conditional report sections (Core Web Vitals, Search performance)
  are now numbered dynamically instead of hardcoding "4."

## [1.17.0] — 2026-07-02

### Added
- **`/narwhal fix <site>` — close the audit → fix loop.** When the site's source
  is in the current workspace, the agent maps each scan/audit finding to the file
  that owns it (title/meta, canonical, OG/Twitter, JSON-LD via
  `generate_schema.py`, alt text, robots.txt, `llms.txt` via `generate_llms.py`),
  applies minimal framework-idiomatic edits, then **re-scans and runs
  `diff_scan.py`** to prove what resolved and the score delta. Honest by design:
  localhost re-scans verify page-level fixes only (site-level signals are labeled
  *verify after deploy*), "applied, pending deploy" when there's no local preview,
  no edits + a per-finding fix plan when the source isn't in the workspace, and a
  "needs manual action" list for findings unreachable from the repo. Fix-loop
  guidance also added to `SKILL.md` and `AGENTS.md` for non-Claude agents.

## [1.16.1] — 2026-07-02

### Changed
- **`/narwhal audit` delivers HTML by default again** (needs no extra tools). PDF is
  now opt-in — the Chromium/WeasyPrint engines and `--format pdf` remain available
  for anyone who wants a PDF, and the self-contained HTML can be Printed → Saved as
  PDF from any browser.

## [1.16.0] — 2026-07-02

### Added
- **Second PDF engine: headless Chromium (Playwright).** `pdf_from_html` now tries
  WeasyPrint, then Chromium print-to-PDF — which renders our exact CSS (pixel-perfect
  branded PDF) and installs cleanly cross-platform (it also powers `--render`).
  Verified end to end (real branded PDF generated via Chromium).

### Changed
- **`/narwhal audit` delivers a PDF by default.** Step 4 now renders
  `narwhal-audit-report.pdf`; with no PDF engine it falls back to a self-contained
  HTML (and the message lists both install options + the "Print to PDF from your
  browser" escape hatch).

## [1.15.0] — 2026-07-02

### Added
- **`/narwhal audit` now delivers a branded report file** — not just chat output. It
  writes `narwhal-audit-report.md`, then renders a self-contained, branded **HTML**
  report (`narwhal-audit-report.html`) of the synthesis and offers a **PDF**.
- **`narwhal render <file.md>`** (`render_report.py`) — turns any Markdown report
  into a branded HTML/PDF (inline CSS + logo, same look as scan/audit reports).
  Reuses the report renderer; `--format html|pdf`, first `# heading` becomes the
  title, reads stdin with `-`.
- The Markdown→HTML converter now renders `[text](https://…)` **links**.

## [1.14.0] — 2026-07-01

### Added
- **Branded HTML/PDF reports** — the Narwhal logo now appears in the report header
  (next to the title) and footer. It's embedded **inline as a base64 data URI**
  (`lib/brand.py`), so reports stay fully self-contained (no external request,
  works offline and in the pip/uvx package where `assets/` isn't shipped).
  Regenerate with `assets/make-brand-logo.py`. Applies to `scan` and `audit`
  HTML/PDF output.

## [1.13.0] — 2026-07-01

### Added
- **Core Web Vitals in the audit report** — `narwhal audit <site> --vitals` now runs
  CrUX **field** data (origin-level, when `CRUX_API_KEY` is set) and falls back to
  PageSpeed Insights **lab** data for low-traffic sites, then includes a **Core Web
  Vitals** section in **every** output format: Markdown, **HTML, PDF**, and JSON
  (plus a headline in the report's metrics strip). Field vs lab is clearly labeled.
  ```bash
  narwhal audit https://example.com --vitals --format pdf -o audit.pdf
  ```
- The `/narwhal audit` command passes `--vitals` in its baseline step, folds the
  verdict into the report, and offers a shareable HTML/PDF that includes it.

### Fixed
- The Markdown→HTML converter now renders `_italic_` (so the honest field/lab notes
  in HTML/PDF reports no longer show literal underscores); word-boundary-guarded so
  `snake_case` and paths are untouched.

## [1.12.0] — 2026-07-01

### Added
- **PageSpeed Insights (Lighthouse) lab data** via `narwhal vitals <url> --lab`
  (`psi.py`) — the companion to CrUX field data. Works for **any URL regardless of
  traffic**, so it fills the gap when CrUX has no field data (most pages). Returns
  an overall performance score plus LCP, **TBT** (the lab proxy for INP), CLS, FCP,
  Speed Index, and TTI, each rated.
  - Clearly labeled **lab/synthetic** (an estimate for catching regressions), never
    conflated with real-user field data. Lab has no INP.
  - PSI key optional (keyless runs at a shared, easily-exhausted quota, so a key is
    recommended): `PAGESPEED_API_KEY`, or reuse the CrUX key with the PageSpeed
    Insights API also enabled. `--strategy mobile|desktop`.
  - The CrUX "no data" message now points to `--lab`; verified against the live
    PSI v5 API contract.

## [1.11.0] — 2026-07-01

### Added
- **`vitals` and `diff` are now plugin-native** — wired into the `/narwhal <action>
  <site>` command and documented in the skill, not just the CLI. `/narwhal vitals
  example.com` runs the real CrUX Core Web Vitals lookup (resolving the key from the
  env or a `.env`, which Claude Code inherits), and `/narwhal diff old.json new.json`
  compares two saved reports.
- **The multi-agent `audit` now folds in real Core Web Vitals** when a `CRUX_API_KEY`
  is available (runs `crux.py --origin` and merges the field verdict into the
  performance section); otherwise it stays honest and points at `/narwhal vitals`.

## [1.10.0] — 2026-07-01

### Added
- **`.env` support for the CrUX key** so you don't have to pass `--crux-key` every
  time. `narwhal vitals` now resolves the key as **`--crux-key` > `CRUX_API_KEY`
  env var > `.env` file** (auto-loaded from the working directory or a parent).
  Zero-dependency loader (`lib/env.py`); `.env` is gitignored, so secrets never get
  committed. Added [`.env.example`](.env.example); the "key required" message now
  lists all three options. (Never put the key in `narwhal.toml` — that's committed.)

## [1.9.0] — 2026-07-01

### Added
- **Dark-mode logo** (`assets/logo-dark.png` + `-512`): the navy structure and
  "NARWHAL" wordmark are recolored to light icy-blue so the mark reads on dark
  backgrounds, while the teal/aqua stays vivid. The README auto-swaps to it via a
  `<picture>` element (`prefers-color-scheme: dark`). Derived deterministically
  from the light logo (`assets/make-dark-logo.py`, luminance fold) — same artwork,
  regenerable in one command.

This release also marks the **P2 roadmap backlog (#13–#18) fully cleared.**

## [1.8.0] — 2026-07-01

### Added
- **Real Core Web Vitals** (`narwhal vitals <url>`): opt-in field data from Google's
  Chrome UX Report (CrUX) API — **LCP, INP, CLS** at the 75th percentile, each rated
  good/needs-improvement/poor, with a pass/fail verdict, plus FCP/TTFB as secondary.
  Origin- or URL-level, per form factor. Verified against the current CrUX API.
  - The only feature that calls an external service — **opt-in**, gated behind an API
    key (`--crux-key` / `CRUX_API_KEY`); never on the default scan path.
  - Honest: no key → clear message; low-traffic URL with no CrUX data → says so
    (suggests `--origin`); never fabricates field metrics.
  - Built against the CrUX API directly, since PageSpeed Insights is dropping CrUX
    field data in 2026 (and INP replaced FID in 2024).
- The `narwhal-performance` agent now points at `narwhal vitals` for real field data.

## [1.7.0] — 2026-07-01

### Changed
- **Hardened the `--render` (Playwright) path.** Verified against Playwright 1.61:
  - Missing Chromium binary now yields an actionable one-line fix
    (`python -m playwright install chromium`) instead of a raw error.
  - Navigation waits on `domcontentloaded` then a **capped** `networkidle` settle
    (5s max) — `networkidle` alone could hang on analytics/long-polling sites.
  - Browser is always closed via `try/finally` (no leak on error); container-safe
    launch (`--disable-dev-shm-usage`, sandbox kept on for untrusted pages).
  - A render that can't run reports an honest error rather than silently degrading
    to raw HTML.
- `pdf_from_html` now also handles WeasyPrint being installed without its native
  libraries (`OSError`), falling back to HTML instead of crashing.

### Added
- CI **`render-smoke`** job: installs Playwright + Chromium and asserts the
  `--render` path executes JavaScript end to end (serves a JS page, checks the
  post-JS DOM). Bumped `actions/checkout` to v5.

## [1.6.0] — 2026-07-01

### Added
- **MCP server** (`narwhal mcp`): exposes the auditors as Model Context Protocol
  tools over stdio — `scan_page`, `crawl_site`, `audit_site`, `validate_sitemap`,
  `generate_llms`, `generate_schema`, `diff_reports`. A thin, typed adapter over the
  existing scripts (results match the CLI). Built on the MCP Python SDK's `FastMCP`;
  verified against the current release. Optional `mcp` extra
  (`pip install "narwhal-seo[mcp]"`) + `narwhal-mcp` console script; the core
  toolkit stays zero-dependency and prints a friendly hint when `mcp` is absent.

## [1.5.0] — 2026-07-01

### Added
- **Scan diffing / regression tracking** (`narwhal diff old.json new.json`): compare
  two saved JSON reports — score delta plus **new / resolved / worsened / improved**
  findings. Deliberately database-free (diff the JSON we already emit): human-readable,
  git-friendly, and directly readable by the agent.
  - Dynamic finding titles (e.g. `Thin content (210 words)`) are normalized so the
    same issue matches run-to-run.
  - `--fail-on-regression` exit code for CI gating (score dropped, or a new
    critical/high finding appeared).
  - Accepts both `scan` and `audit --format json` output; Markdown + JSON output.

## [1.4.0] — 2026-07-01

### Added
- **HTML report export** (`--format html`): a self-contained, styled report —
  inline CSS, an SVG score gauge, a per-area breakdown with score bars, and
  severity-coloured finding cards. No external resources, so it renders offline
  and is easy to share. Available on both `scan.py` and the flagship `audit.py`.
- **PDF export** (`--format pdf`): renders the HTML to PDF via WeasyPrint when it's
  installed, and gracefully falls back to writing HTML (with a clear note) when it
  isn't — no crash, no hard dependency.
- Sample HTML report in [`docs/samples/`](docs/samples/sample-report.html); new
  optional `pdf` extra (`pip install narwhal-seo[pdf]`).

### Changed
- Report output writing is unified through `report.deliver()`, shared by `scan.py`
  and `audit.py`, so all four formats behave consistently.

## [1.3.0] — 2026-07-01

### Added
- **Filler / AI-writing content-quality scorer** (`lib/content_quality.py`, stdlib):
  detects padding/filler phrases, telltale AI-writing patterns, and low lexical
  diversity — surfaced as hard-data findings (with example matches) in the content
  auditor and the `narwhal-content` specialist.

## [1.2.1] — 2026-07-01

### Fixed
- Multi-agent `/narwhal audit` synthesis now uses plain GitHub-flavored Markdown
  (pipe tables + lists) instead of Unicode box-drawing tables, which corrupted in
  terminals.

## [1.2.0] — 2026-07-01

### Added
- **Multi-agent deep audit**: `/narwhal audit` runs the deterministic baseline, then
  fans out ~10 specialist subagents in parallel (`agents/`: technical, content,
  schema, geo, performance, links, duplication, sitemap, sxo, + conditional local)
  and synthesizes an SEO Health Score + prioritized action plan.
- **`/narwhal <action> <site>` command** dispatching audit/scan/crawl/sitemap/llms/schema.
- **Comprehensive `audit` action** combining homepage + site crawl + sitemap.
- **Audit-style report**: executive summary, per-area subscores, quick wins.

### Changed
- Plugin renamed `seo-scan` → **`narwhal`** (install: `narwhal@narwhal`).
- Link checking uses a shorter HEAD timeout + more workers; audit uses lighter
  sub-limits — link-heavy sites went from hanging to ~25s.

## [1.1.0] — 2026-07-01

### Added
- GitHub Actions **CI** (Python 3.8–3.12 + Windows, with/without extras).
- **`--fail-under N`** CI quality gate on `scan` and `crawl`.
- Unified **`narwhal` CLI** + **`uvx`** (git-based, no install, no PyPI).
- **Polite crawler** (robots.txt-aware, `--concurrency`, `--delay`, cached signals).
- **RFC 9309 robots.txt matcher** (`lib/robots.py`).
- **Broken-link checker** (`crawl --check-links`).
- **Sitemap validation** (`narwhal sitemap`): indexes, lastmod, 404 sampling, gzip.
- **`narwhal.toml` config** (weights, thresholds, CLI defaults, ignore rules).
- **`llms.txt` generator** (`narwhal llms`).
- **Readability** (Flesch) + keyword/entity extraction + topical-focus check.
- **Near-duplicate detection** (SimHash) with canonical checks.

## [1.0.0] — 2026-07-01

### Added
- Initial release: four auditors (technical, content/E-E-A-T, schema, GEO/LLMO),
  `scan` / `crawl` / `schema` tools, SSRF-safe fetching, Markdown/JSON reports,
  Claude Code plugin install, and the offline test suite.

[1.3.0]: https://github.com/aindong/narwhal/releases/tag/v1.3.0
[1.2.1]: https://github.com/aindong/narwhal/releases/tag/v1.2.1
[1.2.0]: https://github.com/aindong/narwhal/releases/tag/v1.2.0
[1.1.0]: https://github.com/aindong/narwhal/releases/tag/v1.1.0
[1.0.0]: https://github.com/aindong/narwhal/releases/tag/v1.0.0
