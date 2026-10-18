# Project status & handoff

_Last updated: 2026-10-19 · latest release **1.30.19**_

A snapshot of where Narwhal stands and how to continue it. For the item-by-item
plan see [ROADMAP.md](ROADMAP.md); for release history see
[../CHANGELOG.md](../CHANGELOG.md).

## What Narwhal is
A local-first SEO + GEO/LLMO scanning toolkit shipped as a Claude Code plugin
(also runnable via `uvx` / cloned repo / any agent via `AGENTS.md`). Two layers:

- **Deterministic scripts** (`skills/seo-scan/scripts/`) — bounded measurements
  and heuristic findings, with zero required dependencies. Regression tests
  support repeatability and implementation correctness, not independent SEO
  accuracy or proof of ranking/citation outcomes.
- **Multi-agent orchestration** (`agents/` + `commands/narwhal.md`) — specialist
  subagents that run the scripts as tools and add **reasoning** on top; `/narwhal
  audit` fans them out in parallel and synthesizes one report.

Design principles (keep these): local-first, zero required deps, SSRF-safe,
fix-first & honest output. See [../CONTRIBUTING.md](../CONTRIBUTING.md).

## Unreleased improvements
- **Scoped page text-length cues:** historical ASCII matches no longer become
  a high "thin content" verdict or a content-depth certificate. Literal count/
  extraction/language receipts explain conservative uninterpreted coverage for
  non-English declarations or non-ASCII letters/marks. Applicable length reviews
  are low; current/legacy plans preserve useful concise text. Counts/defaults/IDs
  remain, while titles/priorities/scores can change. No multilingual segmentation,
  ranking/citation validation or comparison/brief length correction is claimed.
- **Inspectable quick wins:** low-priority page findings show safe reported-field
  previews rather than only titles/advice. Detail and evidence each have a
  400-character normalized preview with explicit truncation; full JSON is intact.
  Native HTML/PDF input and Markdown retain literal markup/backticks and readable
  mobile/print wrapping. No new measurements, verification, scores or advice.
  Markdown-rendered report H1 URLs wrap rather than overflow narrow screens.
- **Evidence-scoped tuning guidance:** the README and tuning workflow distinguish
  rule/prompt development from model training, tests from accuracy, and tool-score
  corrections from website improvements. Detection and priority revisions can
  raise or lower scores; familiar sites and agent agreement are not ground truth.
  Historical score tables remain unchanged with missing-input/review limits.
  This is documentation correction, not completed independent validation.
- **Document-order headings:** optional BeautifulSoup parsing no longer groups
  heading levels before technical checks or brief subtopic extraction. The
  selected parser's document order preserves actual skip-pair evidence and
  sibling-section order. Text/counts, IDs and severity stay unchanged, while
  order-sensitive findings/scores can change. Development-only frozen replays
  inform this parser correction, not independent SEO validation; reserved
  findings stay uninspected and cross-parser malformed-HTML parity is not claimed.
- **Prospective acquisition cohort:** 50 candidate URLs are registered before
  scans, split into 30 development and 20 reserved cases across 25 declared site
  families. Conservative preflight/delay/deadline rules preserve failures rather
  than replace them. The first private run retained 46 pending-review bundles
  (44 HTTP 200, two HTTP 403) and four unverified-preflight skips. These are
  acquisition counts, not 44 healthy pages or measured accuracy. Raw captures
  stay in ignored owner-only local storage; independent adjudication remains open.
- **Opt-in review acquisition:** a maintainer-only capture command preserves the
  same scan's decoded primary/paired source, available response fields and context
  in a new local bundle, without an evidence re-fetch or ordinary-scan retention.
  Completion manifests are last-written, output sizes bounded and data sensitive;
  no automatic publication/redaction/review labels. Missing network inputs remain
  explicit. This enables new frozen cases, not completed independent validation.
- **Mobile score-table containment:** native page HTML score breakdowns use a
  labelled keyboard-focusable scroll region, readable area labels and named
  severity headers instead of widening narrow phones/spilling outside cards.
  Print/PDF removes scroll clipping/focus outlines. Scores, counts, JSON and
  Markdown stay unchanged; browser CI covers narrow/desktop/keyboard/print cases.
- **Bounded attribution candidates:** scan and comparison share nonempty author
  metadata, author-link and short leading byline-like witnesses independent of
  main-text extraction. Bare prose words/blank metadata no longer pass; source,
  value, depth and candidate limits are explicit. JSON and literal page-report
  evidence do not verify writers, visibility or expertise. Missing article cues
  prompt low contextual review; legacy/current plans never demand invented people.
  Stable IDs remain; score corrections do not demonstrate improved pages.
- **Findings-first page headlines:** native page HTML/PDF heroes describe the
  highest reported priority or "No flagged findings", not a blanket grade.
  The secondary numeric band is explicitly not page quality. Critical/high and
  unmeasured precedence, scores, JSON, Markdown and other report types stay intact.
- **Literal GEO text cues:** four editorial checks expose bounded pattern counts
  and explicit limits instead of declaring answer quality, source absence or
  engine citability. Advisories stay low priority and plans keep edits conditional;
  new/legacy IDs remain compatible. Priority corrections are not page improvements.
  This does not validate language understanding or AI-answer/ranking outcomes.
- **Contextual phrase review:** common wording produces low-priority editorial
  advice with actual examples and explicit limits, not an AI-authorship or ranking
  risk verdict. Low-match passes also avoid quality/authorship certification.
  Plans keep edits conditional. Stable IDs and phrase counters remain; four-plus-
  distinct-phrase priority changes from medium to low, not proof of improved pages.
  Review title filters.
- **Review-pack foundation:** an offline maintainer utility binds reported
  findings to local snapshots and tracks observation, priority and advice review
  separately. The historical 15-case corpus remains pending/report-only, without
  invented accuracy, recall or independent-review claims. The 50–100-page held-out
  validation milestone still requires new evidence and human adjudication.
- **Terminal error identity:** stdlib HTML/text fetches carry their guarded
  terminal URL and observed redirect hops into HTTP-error responses. Failed-page
  reports and root llms receipts no longer substitute the starting URL; origin
  URL claims do not override fetch identity. Status codes, body budgets and
  network guards are preserved; this does not claim transfer completeness.
- **Cold-start crawl resilience:** HTML helpers initialize the local RDFa module
  before parallel workers access independent documents. This prevents observed
  Python 3.9 startup import failures; extraction remains lazy, cached per Doc and
  local-only. This is not a shared-Doc thread-safety guarantee.
- **Non-backtracking robots matching:** ordered literal-piece searches replace
  combinatorial wildcard regex matching. Repeated-star nonmatches complete
  without changing rule specificity, Allow ties, URL normalization or fetch
  behavior; exhaustive small-input and adversarial subprocess tests cover this
  scoped computation, not total crawl CPU or full robots conformance.
- **Initial robots marker:** a single optional file-start UTF-8 BOM no longer
  hides the first rule group or Sitemap directive. Blocked leaves remain filtered
  and GEO no longer invents root allowance from a missed group; path literals,
  reference guards and the explicit crawl-base override stay unchanged.
- **Root llms.txt evidence:** typed root-response receipts distinguish candidate
  text, observed 404/410 and uncertainty. HTML fallbacks/gates/partial bodies no
  longer produce false publication/absence claims. Crawl/audit notes, GEO-score
  comparison guards and verification-only plans preserve uncertainty without
  inventing file-generation work, full-site coverage or engine/ranking benefits.
- **Repeatable graph rankings:** inbound-link and deep-page lists keep numeric
  priority, then sort tied ranks by URL before display caps. Cross-process hash
  seeds no longer change tied most-linked selection for the same fixed sample;
  graph measurements, scoring and sample-aware coverage are unchanged.
- **Literal crawl table data:** weakest-page and broken-link tables encode
  dynamic URL/error cells instead of interpreting them as Markdown, including
  GFM tildes; internal whitespace is preserved apart from CR/LF breaks. Table-local
  opt-in preserves legacy rendering elsewhere, full JSON and scores; browser CI
  checks desktop/mobile/print columns, literal text and table markup boundaries.
- **Leaf-page indexing evidence:** crawl JSON retains HTTP/named-meta receipts
  per successfully scanned page; crawl/audit reports show bounded non-scoring
  observations with literal page/receipt text. Display caps preserve full JSON,
  scores/issue counts are unchanged, and no unscanned-page or live-indexing
  coverage is implied.
- **Named meta visibility:** documented Googlebot/Googlebot-News meta restrictions
  have a distinct non-scoring section and bounded positional JSON witnesses.
  Generic findings/scores stay unchanged. Other named agents, preview/date
  rules, effective cross-source policy and live indexing remain unverified;
  intentional restrictions require manual policy review, not automatic removal.
- **HTTP indexing declarations:** final HTML-response robots headers now produce
  generic noindex/nofollow findings with hosting-owner remediation. Raw field
  boundaries survive repeated headers; named scopes remain non-scoring report
  notes. JSON provenance documents browser/legacy boundary limits; date/preview
  semantics and actual indexing/crawler behavior are not inferred.
  Rendered post-load document replacement fails explicitly to prevent header/DOM
  misattribution; HTTP redirects and same-document history changes still work.
- **Evidence-scoped robots meta:** all active generic robots tags contribute
  exact restriction names; `none` expands to noindex/nofollow. Substrings and
  parameter values do not create false restrictions. Bounded positional
  witnesses retain late matches; the passing legacy rule ID stays stable, with
  wording limited to generic meta (not HTTP headers, named bots or indexability).
- **Column-aligned reports:** Markdown table separator markers now control
  header/body alignment, so comparison scores honor their right-aligned columns.
  Static classes preserve cell data and header scopes; missing/invalid markers
  keep default left alignment. Browser CI covers mixed alignment and print.
- **Readable branded tables:** dedicated Markdown styles add padding, row guides
  and aligned semantic headers. Wide tables scroll locally via mouse/keyboard;
  print uses compact wrapping cells without focused-region outlines. Score tables
  retain their separate styling. A dedicated browser regression is included in CI.
- **Stable report-table cells:** escaped pipes stay inside their cells, including
  code examples; one optional outer delimiter no longer consumes empty edge
  cells. Odd/even backslash runs distinguish escaped pipes from separators.
  Non-table/fenced text and existing inline escaping remain unchanged.
- **Literal report-link destinations:** inline rendering isolates HTTP(S)
  destinations from emphasis processing while formatting labels and surrounding
  text. Query characters/entities are escaped once and round-trip as data;
  literal code, scheme restrictions and collision-safe protection remain.
- **Literal inline-code reports:** equal-length backtick runs protect escaped
  contents from link/emphasis processing while retaining surrounding formatting.
  Unmatched runs stay text; token lookalikes cannot replace user data, and code
  cannot be inserted into link attributes. Single-line spans preserve inner
  spaces/tabs; this does not add full CommonMark parsing or new dependencies.
- **Literal fenced-code reports:** shared root-fence rules preserve escaped code
  and exclude code comments from report-title extraction. Whitespace survives
  documented indentation/newline normalization; long lines scroll on screen and
  wrap for print/PDF input. No highlighting dependency or full Markdown claim.
- **In-memory verification prerequisite:** diff-producing plans ask callers to
  preserve the original input report, with all fields, before edits/reruns. The
  planner remains read-only; Markdown does not turn that instruction into shell
  code. File-backed and manual measurement checks keep their existing
  responsibilities; manual hosting fixes retain requested deployed verification.
- **Fragment-free sitemap-file accounting:** literal `#fragment` aliases share
  file attempts and child/traversal slots, including failed/cyclic references.
  Valid siblings remain reachable within existing limits; pending-file counts
  do not multiply aliases. Queries, encoded delimiters and page references are
  unchanged. This is not general URI canonicalization or a wider fetch policy.
- **Baseline-preserving verification names:** scan/audit output templates choose
  distinct names when the input basename collides with `after.json` or local
  `page-after.json`. JSON and Markdown share that choice; filesystem aliases are
  not inferred, and fresh output paths remain the caller's responsibility.
- **Kind-matched planner verification:** audit plans separate local page checks
  from the final deployed audit/diff. Templates require the original settings and
  limits rather than inventing a replay; matching kinds alone does not establish
  comparable coverage. Scan plans and manual sitemap gap tasks are unchanged.
  Verification templates quote paths/URLs as POSIX-shell literals and separate
  data from options; they are not universal shell syntax or automatically run.
- **HTTP compression evidence:** raw sitemap fetches acquire bounded wire bytes
  for gzip/deflate and require complete compression streams before decoding.
  Short wire lengths, missing/corrupt trailers and response decode overflow
  contribute no XML prefix, on both transports. Unsupported HTTP encodings stay
  fetch gaps; unencoded `.gz` files keep the separate sitemap decoder.
- **Shared XML discovery:** scan context, crawl and validator fallback discovery
  recognize supported namespace prefixes/gzip and XML escaping from complete
  bounded inputs, not marker/comment guesses. Discovery caps and unknown formats
  remain explicit scoped notes; unknown availability cannot imply missing source
  or silently resolve a technical-score comparison. Valid siblings and anchor
  fallback remain usable. Receipts describe candidate samples, not a site census.
- **Evidence-aware sitemap planning:** recorded fetch/cap gaps and uncertain
  sampled probes are manual verification actions, not sitemap creation/removal.
  Unknown legacy notes remain unclassified; consistent current counters add scope,
  not authenticated provenance. No source owner is guessed for uncertainty.
  Actual source validation findings remain separate with targeted repair advice.
- **Raw sitemap fetch evidence:** failed/non-success HTTP bodies and oversized
  response prefixes cannot certify XML extraction, even if a prefix looks
  complete. Both transports retain actual exact-limit success and bounded fetch
  notes; known incomplete transfers withhold data. Response/error/redirect
  handles close, private-host/redirect guards remain active, and processing bugs
  propagate. Raw fetch failures stay distinct from fetched-file XML coverage;
  explicit failure counts label mixed URL totals incomplete.
  Failed file attempts consume the traversal cap; remaining-file counts exclude
  duplicate/already-visited references. This is not a whole-network request cap.
- **Decoded sitemap budget:** sized gzip reads enforce 52,428,800 decoded bytes
  per file before UTF-8 conversion/XML parsing, across concatenated members.
  Budget exhaustion and failed integrity checks withhold all file entries and
  samples, preserving valid siblings and explicit manual verification notes.
  This bounds decoded input, not total Python heap, CPU or transport work.
- **Crawl measurement evidence:** link outcomes count successful 2xx, broken and
  unverified responses separately; zero checks cannot produce a green pass.
  No-response request failures remain unverified, while existing unreachable
  entries remain available separately from observed broken HTTP responses.
  Duplicate results count actual eligible fingerprints (excluding known failed/
  partial pages); fewer than two means insufficient data, not no duplicates.
  Unknown legacy coverage remains unrecorded. Audit headlines distinguish not
  run from scoped observed counts; scores and actual broken-link findings remain.
- **Sitemap extraction evidence:** validator/audit URL totals include only files
  fully extracted within the supported XML scope. Malformed/unsupported XML,
  DTDs or parser limits produce explicit fetched-file coverage notes, withholding
  partial entries while retaining verified siblings. Planner advice is manual
  verification, not source rewriting. Samples require successful 2xx responses
  for positive reachability; gated/other responses are unverified, not invented
  dead links. This is not complete sitemap/XSD or whole-site validation.
- **Sitemap reference resilience:** rejected robots/index/page URL references
  no longer abort otherwise usable discovery or validation. Counts are scoped
  per examined source component, not network-dead statuses or whole-site totals;
  valid entries and actual-fetch guards remain. Fetch errors, rejected references
  or a reached sitemap-file cap prevent the validator's healthy conclusion.
- **Malformed anchor resilience:** parser-known host/port errors no longer abort
  page checks, link collection or anchor discovery. Source findings and bounded
  omission counts remain visible without fabricating dead-link statuses; valid
  links and fetch guards are retained. Counts describe scanned href occurrences,
  not complete URI validation or site-wide failure totals.
- **Source anchor-text fallbacks:** image-only alternatives and empty-anchor
  titles no longer create false empty-link advice. Both parsers keep image alt
  data out of page text/headings, and blank/generic labels remain flagged.
  This is not browser accessibility-name or CSS visibility validation.
- **Finding reference navigation:** page priority fixes and quick wins link to
  project-guide sections, also exposed as additive `reference_url` JSON metadata.
  Known rule IDs choose precise sections; unmapped rules get general built-in
  category context. No runtime guide fetches or scoring/identity changes; a
  guide is context, not validation of heuristic findings.
- **Robots path parameters:** full-URL checks retain semicolon path suffixes,
  preventing both missed exclusions and lost specific allowances. Query and
  fragment boundaries and encoded reserved distinctions remain unchanged.
- **Robots URI comparison:** equivalent unreserved escapes and UTF-8 spellings
  now match before crawl filtering. Reserved delimiters and literal encoded
  operators remain distinct, with case sensitivity and normalized Allow ties
  preserved. This changes comparison, not checked-path scope or explicit overrides.
- **Role-aware crawler policies:** documented search/retrieval restrictions
  remain high findings; training/data-use, nonbinding user-fetch and unverified
  directives are non-scoring notes. Page metadata records dated sources and
  checked-root scope, without live/WAF/indexing/citation claims. Deliberate
  opt-outs and the high rule's ignore/planner compatibility are preserved.
- **Invalid response charset resilience:** unknown/non-text declared encodings
  return bounded failed-fetch diagnostics instead of crashing the optional HTTP
  path. Undecoded bodies are not measured or silently assigned a fallback
  charset; supported encodings and existing byte replacement remain unchanged.
- **Comparison/brief byte budgets:** CLI, Python and MCP callers can select the
  per-snapshot HTML limit (5MB default, 64KB–20MB bounds) and retry large-page
  coverage failures without bypassing eligibility checks. One limit covers all
  pages and paired inputs; default private-host protections remain unchanged.
- **Optional HTTP transport resilience:** expected `requests` acquisition and
  stream failures produce explicit failed-fetch reports, matching stdlib
  degradation rather than crashing. Interrupted prefixes are not page evidence;
  acquired responses close on success and failure. Unexpected errors still
  propagate, and URL/redirect guards stay in force.
- **Comparison snapshot provenance:** compare/brief facts preserve actual
  rendering mode and display the HTML source per page, including mixed modes.
  Legacy missing flags remain unknown; requested rendering is not substituted
  for measured mode. Scores and synthesis are unchanged.
- **Paired JS-comparison coverage:** rendered and served snapshots share the
  selected byte budget; invalid baseline inputs do not produce numeric JS-only
  measurements. Explicit unverified receipts surface in reports and protect
  relevant diffs and comparison/brief scores, including crawled contributions.
  Non-JS focused scores and legacy unknown receipts are not reclassified.
- **Rendered HTML byte budgets:** serialized DOM snapshots obey the primary UTF-8
  byte limit and record partial coverage; incomplete DOMs are not JS-dependence
  measurements. This bounds retained analysis input, not browser memory or network
  traffic. Complete snapshots and existing fetch/browser safety checks are unchanged.
- **Comparison/brief HTML coverage:** explicitly truncated page reports are
  excluded from gap/score benchmarks. Partial targets error, partial rivals are
  skipped with reasons, and topic briefs require a usable page. Standalone scans
  still report partial findings with warnings; absent legacy flags are not proof
  of complete coverage.
- **Evidence-grounded brief wording:** rendered headings, CLI help and plugin
  guidance call supplied pages comparisons, not verified ranking winners. Own-page
  Search Console evidence does not prove competitors' rankings; measured facts,
  scores and JSON are unchanged.
- **Brief rule consistency:** own-page and topic-mode briefs capture built-in
  weights, thresholds and suppression once before page I/O. Caller changes no
  longer switch rules for later competitors; future briefs still pick them up.
  Custom policies remain live, and remote content/context is not frozen.
- **Comparison target identity:** the first requested URL must supply the user's
  page. Failed targets return diagnostics rather than relabeling a rival as "You"
  or producing gap/lead verdicts. Failed competitors remain skippable; successful
  target redirects retain their role.
- **Comparison rule consistency:** one competitor comparison captures built-in
  weights, thresholds and suppression before its first scan, so caller changes
  cannot switch the rules for later competitors. Future runs pick up updates;
  custom policies remain live. Remote content and per-site context are not frozen.
- **Priority-first site rollups:** crawl/audit output ranks recurring issue types
  by severity, then frequency, with stable ties and explicit capped-list omissions.
  Rare urgent findings remain visible; full JSON counts and scoring are unchanged.
- **Site-wide rule consistency:** crawls/audits capture one built-in policy at
  entry; later pages retain the same weights, thresholds and suppression under
  caller mutation. Gathered crawl overrides are owned before discovery and audit
  sitemap sample budgets are resolved before component I/O. This does not freeze
  external page content or promise identical samples between runs.
- **Per-scan rule ownership:** built-in weights, thresholds and suppression are
  captured before page I/O, with supplied/gathered threshold overrides owned at
  their receipt boundary. Caller changes no longer leak into later auditors or
  completed reports. Custom policies/shapes stay compatible and unverified;
  snapshot capture is not a multi-field atomic transaction.
- **Diff input coverage:** explicit requested/actual rendering and effective
  image-check settings prevent skipped subchecks from appearing resolved.
  Opaque rule fingerprints cover weights, effective thresholds and ignore rules,
  so changed scoring or suppression cannot become page-fix evidence.
  Audit comparisons also check recorded settings for common crawled URLs, without
  guessing legacy or outside-sample modes. Other configuration, rule versions
  and site-wide sampling still need to be controlled separately.
- **Severity-first presentation:** high/critical findings lead the
  HTML/PDF hero and report summary; score bands are explicitly labelled instead
  of being an unqualified urgency verdict. Scores, JSON finding data, unknown/
  focused scope caveats and unmeasured failures are preserved. Heuristic
  findings still require verification, not automatic source edits.

Verified improvements accumulate on main after review and merge, not automatically released.
Keep version/manifests at the latest release until an explicit release request.

## Current state (released)
- **v1.30.19 zero-price evidence:** native numeric zero remains present, rather
  than being mistaken for a missing amount or replaced by a positive fallback.
  Merchant nonpositive-price validity and exact unit-gated comparisons stay
  active. Missing/positive prices and boolean handling remain unchanged.
- **v1.30.18 JSON-LD literal boundaries:** value objects and opaque JSON
  examples are not entities or merchant evidence. Datatypes are not entity
  coverage types. Normalization and deduplication preserve literal content,
  while real graph/list nodes and independent merchant signals remain active.
  Context definitions do not classify a page as Product. No full context
  expansion, remote fetch or general datatype/value validation is claimed.
- **v1.30.17 exact point-price comparisons:** scientific notation and long
  decimals retain their true amounts, including multi-Offer consensus, without
  Decimal context rounding. Matching explicit units and supported displayed
  amounts are required; unsupported Text receives verification notes, not an
  invented numeric comparison or schema.org invalidity verdict. JSON records
  exact evidence; existing localized display parsing and other checks remain.
- **v1.30.16 diff execution-scope guard:** omitted auditor groups cannot become
  resolved fixes. Known mismatched/incomplete scopes, truncated responses and
  page/audit score-kind differences yield incomparable diagnostics and gate
  exit 2, with null unmeasured deltas/verdicts. Matching scopes retain normal
  diff behavior; unknown legacy scope warns without inventing coverage.
  This checks execution provenance, not full configuration/sample equality.
- **v1.30.15 expected URL rejection diagnostics:** five CLI boundaries return
  bounded single-line errors and exit 2 for expected input/host-policy failures,
  without creating reports or hiding programming errors. API exceptions and
  explicit private opt-in remain. Initial sitemap target validation rejects
  direct XML inputs instead of returning an error report with exit 0;
  crawl/llms context receives normalized entry URLs.
- **v1.30.14 honest scan scope:** JSON execution provenance and visible
  requested/completed/unselected group labels distinguish focused scores from
  overall health. Failed responses are not measured and do not fabricate area
  grades; partial HTML and unknown legacy scope remain explicit. Duplicate
  selections run once; normal scoring, threshold values and findings remain.
- **v1.30.13 Recipe base-field expectations:** name/image required, with absent
  and blank values detected; ingredients/instructions remain recommended.
  Source/date and unverified conditional/nested/image validation scope are
  explicit, not a full eligibility verdict. Generators and field-scoped legacy
  ignores align across all three formats without inventing authors or ratings.
- **v1.30.12 Article-family expectations:** missing applicable fields are low
  recommendations, not mandatory headline errors. Dated Google policy/source
  metadata is explicit. Blank values are handled without author/date invention;
  generator labels, all three formats and legacy headline opt-outs align.
  This does not claim full datatype/reference or eligibility validation.
- **v1.30.11 source-backed Google feature notices:** current retirement status
  for existing four notices, dated primary-source metadata and visible guidance.
  Appearance retirement is not schema.org invalidity or ranking proof. Stable
  rule IDs, low severity, title ignores, FAQ generation and semantic uses remain.
  Course Info retirement is not applied to all Course markup. No runtime fetch.
- **v1.30.10 Product name ownership:** H1/name comparisons use the selected
  Product, not a seller/sale Offer label. Genuine Product-name disagreements and
  missing names remain visible. Variant selection and non-name comparisons are
  unchanged; names are preserved on both entity types across all three formats.
- **v1.30.9 inert templates:** one cached stdlib source projection excludes
  template fragments from normalized page facts and all lazy markup consumers.
  Original HTML is preserved. Hidden active data blocks remain readable;
  Chromium smoke coverage checks inert examples versus JS-activated schema.
  Source projection does not claim a complete browser DOM/shadow-root model.
- **v1.30.8 AggregateOffer ranges:** one aggregate uses inclusive numeric bounds
  with matching explicit currencies, not an exact lower-bound comparison.
  JSON distinguishes range compatibility from selected-Offer existence.
  Unknown evidence is explicitly skipped; outside-range amounts and known
  negative/inverted bounds remain high findings. Other Offer checks stay active.
- **v1.30.7 Offer comparison scope:** multiple Offers require per-field consensus
  for price/currency/stock, with compatible currency evidence for numeric price.
  Ambiguous fields are explicitly skipped; agreed fields, Product identity and
  all-offer validity/completeness remain checked. Single-Offer behavior is intact.
- **v1.30.6 bounded source warnings:** shared Microdata/RDFa/merchant-source
  warning budgets retain up to 64 details plus an omission notice, with visible
  512-character truncation. Extraction continues; duplicate-at-cap behavior and
  parser parity are tested. Noisy reports remain bounded and honest.
- **v1.30.5 Offer-value resilience:** non-string references and non-object
  price-specification members cannot abort reports. Unsupported shapes have
  verification notes; valid mixed-array object members, null semantics and
  local string references are preserved. Real price defects still surface.
- **v1.30.4 variant identity:** multi-Product comparisons require a unique
  visible identity rather than source order. Ambiguous comparisons are explicitly
  skipped with a verification note; all-node schema checks still run. Identifier
  punctuation and Unicode are preserved; real selected-variant mismatches remain.
- **v1.30.3 URL resilience:** malformed Product/Offer URLs produce scoped
  findings without aborting reports; local host/port/character syntax checks
  preserve valid IPv6, Unicode hosts and encoded paths. No reachability claim.
- **v1.30.2 source-evidence accuracy:** cached stdlib extraction excludes inert
  and explicitly hidden markup from commerce facts, labels and controls. Active
  itemprop values and OpenGraph preference order remain intact; partial coverage
  and warning limits are visible. Verified against real mismatch controls.
- **v1.30.1 merchant-scope correction:** requires Product plus selling evidence,
  excludes SKU-only editorial reviews, tightens prose-label matching, and rejects
  inconsistent merchant flags in crawl summaries. Dogfooded on schema.org docs.
- **v1.30.0 RDFa support:** bounded schema.org extraction with scoped
  vocabularies/prefixes, nested entities, local references, shared schema/merchant
  checks, comparison facts, and three-format deduplication. Coverage warnings are
  explicit; this is not a full RDFa processor.
- **v1.29.0 Microdata support:** bounded stdlib extraction, shared schema /
  merchant checks, source-format provenance, comparison facts, and equal-node
  deduplication. Valid Microdata no longer receives missing-JSON-LD penalties;
  extraction warnings are explicit. Bounded RDFa support shipped in v1.30.0 above.
- **v1.28.0 e-commerce checks:** deterministic Product/store detection,
  Product/Offer/AggregateOffer and variant validation, evidence-gated visible
  merchant mismatches, crawl scope metadata, planner ownership, and a conditional
  e-commerce specialist shipped for #27.
- **v1.27.0 remediation planner:** `narwhal plan REPORT.json --repo .` emits
  a versioned, read-only action contract with six framework adapters, stable
  finding linkage, safety/deploy classifications, grouped fixes, conflicts,
  coverage/provenance, CLI + bounded MCP surfaces, and golden fixtures.
- **All P0 + P1 roadmap items** shipped (#1–#12, closed).
- **Beyond the roadmap:** `/narwhal <action> <site>` command, plugin renamed to
  `narwhal`, audit-style report, comprehensive `audit`, **multi-agent deep audit**
  (10 specialists), filler/AI-writing content scorer, link-check perf fix,
  **`/narwhal fix`** (v1.17.0) — closes the audit → fix loop: maps findings to
  source edits in the workspace, re-scans, and diffs to prove the delta,
  **Search Console integration** (v1.18.0, `gsc.py`) — real query data
  (striking distance, CTR laggards, decay, cannibalization) via stdlib-only
  OAuth; standalone `narwhal gsc` + `audit --gsc` fold-in.
- **#13 shipped:** **HTML + PDF report export** — self-contained styled HTML
  (`--format html`: score gauge, per-area breakdown, severity cards) on `scan` and
  `audit`; PDF via WeasyPrint with graceful HTML fallback (`--format pdf`). Sample
  in `docs/samples/`.
- **#14 shipped:** **Scan diffing / regression tracking** — `narwhal diff
  old.json new.json` (score delta + new/resolved/worsened/improved findings,
  `--fail-on-regression` CI gate). Database-free by design: diffs the JSON we
  already emit (`diff_scan.py`).
- **#17 shipped:** **MCP server** — `narwhal mcp` exposes all auditors as MCP
  tools over stdio (`mcp_server.py`, FastMCP; optional `mcp` extra). Verified
  against the current MCP Python SDK release.
- **#16 shipped:** **Hardened `--render`** — actionable missing-browser message,
  capped networkidle settle, guaranteed browser cleanup, honest failures; new CI
  `render-smoke` job executes JS end to end (verified vs Playwright 1.61).
- **#15 shipped:** **Real Core Web Vitals** — `narwhal vitals` (`crux.py`) fetches
  LCP/INP/CLS field data from the CrUX API. Opt-in (API key), never on the default
  path; honest when no key / no data. Verified vs the live CrUX API contract.
  **`--lab` (v1.12.0, `psi.py`)** adds PageSpeed Insights Lighthouse *lab* data for
  any URL (fills CrUX's low-traffic gap); labeled synthetic, key optional.
- **#18 shipped:** **Dark-mode logo** — `assets/logo-dark.png`; README auto-swaps
  via `<picture>`. Derived deterministically from the light logo
  (`assets/make-dark-logo.py`).
- **P2 backlog (#13–#18) fully cleared.**
- **Real-world tuning round (v1.19.0, closes #19 + #20):** scanned 8 diverse live
  sites + graded 3 live specialist-agent runs. Fixed the stdlib parser (nested
  `<h1><a>` lost headings; anchor text missing from visible text), stopworded
  month tokens, added **page-type-aware checks** (`htmlx.is_hub_page/looks_article/
  is_homepage`): homepage brand titles, hub thin-content, article-only byline,
  article-scoped GEO severities. All 10 agent prompts gained **Judgment rules**
  (classify page type, sample an inner page, respect owner opt-outs, report
  *Discounted script findings*), and the orchestrator honors the discounts.
  Depth findings state their extraction basis (trafilatura vs visible text).
  `${CLAUDE_PLUGIN_ROOT}` confirmed resolving for subagents. Scores on well-run
  sites corrected: jvns 62→79, HN 52→66, pydocs 75→86, Verge 71→80.
- **Next wave P1 tier fully shipped (v1.20–v1.24, one release per feature):**
  **#21** `narwhal compare` (competitor gap analysis, `compare.py`, MCP
  `compare_pages`) · **#22** site-graph analysis (`lib/sitegraph.py`: click
  depth, orphan candidates, link equity — always-on in crawl/audit) · **#23**
  JS-dependence (`lib/jsdiff.py`: `--render` diffs served HTML vs rendered DOM)
  · **#24** image checks (`lib/images.py`: HEAD-budgeted weights, formats,
  og:image dimension probe) · **#25** hreflang reciprocity (`lib/hreflang.py`:
  exact missing return pairs + capped alternate probe).
- **Tuning Round 2 (v1.25.0) + corpus addition (v1.25.1):** corpus 8 → 15 pages
  (product/article/recipe/French/hreflang/dead-URL page types +
  openskyelabs.xyz, a `<noscript>`-shell site that exposed a parser gap). Six
  fixes at source: hard-fail score 0 for unfetchable pages, og:image gated ≠
  broken, non-English skips English-calibrated checks, article-scoped
  readability, hub-aware no-JSON-LD, srcset-aware heavy images; plus
  noscript-fallback measurement + architecture finding. Two graded agent runs
  (schema, performance — the perf agent caught the srcset caveat in our own
  check). Full evidence in `docs/tuning/2026-07-round-2/`.
- **#26 shipped (v1.26.0): `narwhal brief` — data-driven content briefs.**
  GSC striking-distance queries for the page (+ laggard/decay/cannibalization
  status) + compare gaps + missing subtopics (competitor H2/H3 vs your text,
  inflection-tolerant) + questions to answer + schema/structure targets.
  `--topic` mode for pages that don't exist yet (`--gsc-site` grounds it in
  real adjacent queries). Honest degradation: structure-only brief without GSC
  creds — queries omitted, never invented. Wired as `narwhal brief`,
  agent-orchestrated `/narwhal brief` (editorial outline + branded HTML), and
  MCP `content_brief`. Also fixed a live-found `compare` bug: vacuous depth
  "lead" when all rivals are hub pages.
- **Tests:** 279 locally, split into focused area modules, with CI covering
  Python 3.8–3.12 + Windows (+ render-smoke job); complete Markdown, JSON, and
  HTML report shapes plus planner output are protected by committed goldens.
- **v1.28.0 version consistency:** one `_version.py` constant supplies
  package metadata, CLI, and report provenance; plugin manifests are synchronized
  with a stdlib command. CI verifies manifest consistency and installed versions.
- **CrUX key convenience (v1.10.0):** `narwhal vitals` resolves the key from
  `--crux-key` > `CRUX_API_KEY` env > `.env` file (`lib/env.py`, zero-dep).
- **Plugin-native `vitals`/`diff` (v1.11.0):** both wired into `/narwhal <action>`
  and the skill.
- **Vitals in the audit report (v1.13.0):** `audit.py --vitals` runs CrUX field
  (or PSI lab fallback) and adds a Core Web Vitals section to **all** formats
  (md/html/pdf/json); `/narwhal audit` passes `--vitals`. md_to_html now does
  `_italic_`.
- **Branded report file from `/narwhal audit` (v1.15.0):** the command writes
  `narwhal-audit-report.md` then renders a branded HTML (offers PDF) via the new
  `narwhal render` (`render_report.py`) — Markdown → branded HTML/PDF, reusing the
  report shell. md_to_html now renders `[links]`.
- **Two PDF engines (v1.16.0):** `report.pdf_from_html` tries WeasyPrint then
  headless Chromium (Playwright `page.pdf`, pixel-perfect, verified). `/narwhal
  audit` delivers **HTML by default** (v1.16.1 — needs no tools); PDF is opt-in
  (`--format pdf`).
- **Released:** v1.0.0 → v1.30.19 (54 releases). Plugin installs as `narwhal@narwhal`.

## Layout
```
narwhal/
├── .claude-plugin/        plugin.json + marketplace.json (name: narwhal)
├── commands/narwhal.md    /narwhal <action> <site> (dispatch + audit orchestration)
├── agents/                10 specialist subagents (narwhal-*.md)
├── skills/seo-scan/
│   ├── SKILL.md           auto-triggering skill
│   ├── scripts/           scan, plan, compare, brief, crawl_site, validate_sitemap,
│   │                      generate_schema, generate_llms, audit, diff_scan,
│   │                      render_report, crux, psi, gsc, mcp_server, cli
│   │                      + lib/ (http, htmlx, report, robots, links, sitemap,
│   │                      simhash, text, content_quality, config, env, brand,
│   │                      sitegraph, jsdiff, images, hreflang)
│   ├── references/        deep-dive guidance per auditor
│   └── tests/             offline unittest suite (no network, no deps)
├── docs/                  ROADMAP, CONFIG, STATUS (this), index, samples/,
│                          tuning/ (published tuning rounds + raw snapshots)
├── narwhal.example.toml   config template
└── pyproject.toml         uvx/pip packaging (narwhal-seo)
```

## What's next (open issues)
The original roadmap (#1–#20) is **complete**. The **next wave (v2.x)** came out
of the 2026-07 project self-review — relative + strategic answers, still
local-first (see ROADMAP "Next wave" for detail):
- ~~#21~~ `narwhal compare` — **shipped v1.20.0** (compare.py, /narwhal compare, MCP compare_pages)
- ~~#22~~ Site-graph analysis — **shipped v1.21.0** (lib/sitegraph.py, always-on in crawl/audit)
- ~~#23~~ JS-dependence check — **shipped v1.22.0** (lib/jsdiff.py, --render diffs raw vs rendered)
- ~~#24~~ Image weight/format + og:image — **shipped v1.23.0** (lib/images.py, HEAD-budgeted + dimension probe)
- ~~#25~~ Hreflang reciprocity — **shipped v1.24.0** (lib/hreflang.py, probe + exact pairs) — P1 tier complete
- ~~#26~~ Content-brief flow — **shipped v1.26.0** (brief.py, /narwhal brief, MCP content_brief)
- ~~#27~~ E-commerce checks + conditional store specialist (P2) — **shipped v1.28.0**
- ~~#28~~ Test-suite health: split monolith + golden-file tests (P3) — **shipped v1.28.0**

### Ongoing quality practice
Specialist tuning (#19) is a loop, not a one-shot: each real `/narwhal audit` run
is tuning material. When a specialist misses, over-flags, or parrots the script,
encode the correction in its `agents/narwhal-*.md` **Judgment rules** and, where
the root cause is measurable, fix the deterministic check + add a regression test
(see the v1.19.0 round for the pattern).

## Dev workflow
```bash
python -m unittest discover -s skills/seo-scan/tests -v   # run tests (no deps)
python skills/seo-scan/scripts/scan.py https://example.com  # try a scan
claude plugin validate .                                  # validate plugin manifests
```
CI runs on every push/PR (`.github/workflows/ci.yml`). Two hard-won practices:
- **Verify parser/auditor changes in a bs4 venv too** (`pip install requests
  beautifulsoup4 lxml trafilatura` then re-run the suite) — the backends
  disagreeing has failed CI's `with-extras` job before while local stdlib runs
  were green.
- **No AI co-author trailers in commits/PRs** — repository owner's preference.

## Release process
Development and publishing are separate workflows. Work → verify/dogfood → fix
→ PR → green CI/review → merge, then accumulate related changes under Unreleased.
Do not bump versions, create tags or publish a release for each improvement.
Only begin the steps below when the owner explicitly requests a release.

1. Bump the canonical version in `skills/seo-scan/scripts/_version.py`, then run
   `python scripts/sync_version.py` to synchronize the plugin manifests.
   Package metadata, CLI, and report provenance all read the same constant.
   CI runs `python scripts/sync_version.py --check` to reject manifest drift.
2. Update [CHANGELOG.md](../CHANGELOG.md) and this file's version line.
   Regenerate the report snapshots with
   `python skills/seo-scan/tests/update_golden_reports.py` after the version bump.
3. Commit, push, confirm CI green.
4. After merging and verifying CI for the exact main commit, publish with
   `gh release create vX.Y.Z --target <verified-commit-sha> --title … --notes …`.
   Verify the tag points to that commit. Publishing is not implied by green CI.
5. Users update: `/plugin marketplace update narwhal` → `/plugin update narwhal@narwhal` (restart).

Versioning is additive-minor / patch-fix; the plugin rename in 1.2.0 only changed
the *install string* (`narwhal@narwhal`), not behavior.
