# Structured data (schema.org / JSON-LD, Microdata and bounded RDFa) reference

Structured data tells search engines and AI systems *what* a page is about in a
machine-readable way. It powers rich results (stars, FAQs, prices, breadcrumbs)
and helps AI answer engines identify and attribute entities.

## Format
- Use **JSON-LD** in a `<script type="application/ld+json">` block. Google
  recommends it over Microdata/RDFa; it's easier to generate and maintain.
- One `@graph` per page can hold multiple linked entities (WebSite +
  Organization + Article + Breadcrumb), connected via `@id` references.
- Valid **Microdata** is also audited, not penalized for lacking JSON-LD. The
  stdlib extractor follows nested `itemscope` / `itemtype` / `itemprop`, repeated
  and multi-name properties, `itemid`, and local `itemref` targets. `meta.content`,
  URL element attributes, `data`/`meter.value`, `time.datetime`, and text values
  follow the [HTML Microdata model](https://html.spec.whatwg.org/multipage/microdata.html).
  URL attributes resolve against the page URL (or the first HTML `base` URL).
- **Schema.org RDFa** is also audited within a bounded subset. Scoped `vocab`,
  `prefix` (including the initial `schema:` prefix), legacy `xmlns:` mappings,
  `typeof`, `property`, `resource`, and `about` establish subjects and nested
  entities. Local statements for the same subject are combined within RDFa;
  forward references resolve only against nodes in the document. Resource,
  `href` and `src` values resolve against the page / HTML `base` URL. Text,
  `content` and `datetime` supply scalar values; scalar XSD datatypes retain
  lexical strings, not RDF datatype/language semantics. See
  [RDFa Core subject/property rules](https://www.w3.org/TR/rdfa-core/#sequence)
  and [HTML+RDFa host rules](https://www.w3.org/TR/html-rdfa/).
- JSON-LD, Microdata and supported RDFa feed the same schema and merchant checks.
  `meta.structured_data` reports source formats, types per format, unique typed
  node count, and extraction warnings. Equal normalized objects are audited
  once; different variants or conflicting copies are retained, not merged by ID.
  This is not a complete cross-format conflict validator.
- `rdfa_supported` means bounded support, not full RDFa conformance: read
  `rdfa_scope` and `rdfa_warnings`. RDFa relations (`rel`/`rev`), ordered lists,
  property copying, markup literals and non-scalar datatypes are not processed.
  Unsupported subtrees are skipped with a verification finding to avoid leaking
  their properties into the wrong entity. Foreign vocabularies are not audited;
  vocabulary expansion and referenced resources are never fetched. Language
  tags are not modeled. Validate those cases externally.
- Extraction is capped at 50,000 HTML elements, 1,000 item scopes, 256 HTML
  nesting levels, and 64 nested item references. Partial coverage and invalid
  references produce a verification finding, not a claim of complete validation.
  The source-tree parser is not a full HTML5 browser DOM: malformed HTML may
  need external validation. Inert templates and SVG/MathML are excluded.
- RDFa uses the same element/HTML-depth caps, with 1,000 graph nodes, 10,000
  property statements and 64 nested resource references. Cycles are truncated
  to references with explicit partial-coverage warnings.
- Each source extraction retains at most 64 warning details plus one explicit
  omission notice. Details are capped at 512 characters with a visible
  truncation marker; repeated retained details do not consume additional budget.
  This bounds warning output, not supported data extraction: later valid
  properties are still inspected. Warning arrays are representative details,
  not a total count of errors or a claim that omitted cases are valid.
  Omission/truncation summaries are also included in recommendations so HTML
  quick-win summaries cannot hide them.
- Google supports all three formats; JSON-LD is a maintenance recommendation,
  not a requirement.
  See [Google's supported formats](https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data#structured-data-format).

## The rule that matters most
Structured data must **match visible content**. Marking up a price, rating, or
review that a user can't see on the page is a spam violation and can trigger a
manual action. Never generate schema for content that isn't actually present.

## Common types and their required properties
The auditor and `generate_schema.py` validate these:

| Type | Required | Key recommended |
|---|---|---|
| Article / BlogPosting / NewsArticle | `headline` | `author`, `datePublished`, `image`, `publisher` |
| Product snippet | `name` + one of `review`, `aggregateRating`, `offers` | `image`, `description`, `brand`, SKU/GTIN/MPN |
| Merchant Product + Offer | Product identity + active `price` and `priceCurrency` | `availability`, `url`, `itemCondition`, `seller`, valid identifiers |
| Organization | `name` | `url`, `logo`, `sameAs` |
| LocalBusiness | `name`, `address` | `telephone`, `openingHours`, `geo` |
| Recipe | `name`, `recipeIngredient`, `recipeInstructions` | `image`, `author`, `aggregateRating` |
| Event | `name`, `startDate`, `location` | `endDate`, `offers` |
| JobPosting | `title`, `hiringOrganization`, `datePosted` | `jobLocation`, `baseSalary` |
| VideoObject | `name`, `thumbnailUrl`, `uploadDate` | `description`, `duration` |
| BreadcrumbList | `itemListElement` | — |

## Deprecated / restricted rich results
Still valid schema.org, but no longer produce rich results — don't invest in them
expecting a SERP feature:
- **HowTo** — rich result retired (2023).
- **FAQPage** — rich result limited to authoritative government/health sites.
- **SpecialAnnouncement** — COVID-era, no longer surfaced.
- **ClaimReview** — restricted to approved fact-checkers.

`sameAs` on Organization/Person (linking to Wikipedia, LinkedIn, official
socials) is *not* deprecated and is increasingly useful for entity/AI grounding.

## Product and merchant-listing checks

All normalized document consumers use a cached stdlib source projection that
excludes literal HTML [`template`](https://html.spec.whatwg.org/multipage/scripting.html#the-template-element)
fragments. Inert examples cannot supply page JSON-LD, metadata/canonical links,
headings, links, images or language, including before active declarations.
Main-content extraction and lazy Microdata/RDFa/merchant extraction share the
projected view. `Doc.html` keeps the original source; `Doc.document_html` is the
cached non-template source view. Active JSON-LD in head, hidden elements or
CSS-hidden containers is **not** suppressed: data-block eligibility is not a
visibility test. An unescaped script in `pre` remains HTML, not automatically an
example. Chromium smoke coverage checks inert versus JS-cloned active schema.
This streaming source projection handles nested/unclosed templates and the
non-void template slash syntax, but is not a complete HTML5, foreign-element
integration, declarative-shadow-root or browser-DOM model. Rendered active
document markup is scanned normally; no shadow-root traversal is claimed.

Narwhal classifies a parsed Product JSON-LD, Microdata or supported RDFa node as product evidence.
Without Product structured data it requires stronger corroboration—
`og:type=product` plus an explicit merchant fact—so an article that merely
mentions a price is not treated as a store page.

Merchant scope additionally requires that Product classification plus an Offer,
explicit price/currency/availability evidence, or a visible purchase action.
Purchase-action fallback requires an enabled button/input or same-origin purchase
link; ordinary prose, inert/explicitly hidden controls and external affiliate
links are not purchase evidence. This is source markup, not a checkout or CSS
visibility test. SKU alone is identity evidence, not evidence that an editorial publisher sells
the product. Prose-label fallback requires `:` or `#` after the label; vocabulary
definitions such as "SKU Text ..." are not observed product values. Crawl
rollups also reject contradictory non-product/merchant flags, so documentation
cannot enable the conditional store specialist.

For purchasable products, the scanner checks Product identity (`name`, `image`,
`description`, `brand`, URL, and SKU/GTIN/MPN) and validates nested `Offer` or
`AggregateOffer` data. `Offer.price` and `priceCurrency` may live under a
`priceSpecification`; AggregateOffer requires `lowPrice` and `priceCurrency`.
Do not use AggregateOffer as shorthand for product variants. ProductGroup /
`hasVariant` pages are inspected per Product node, and visible SKU/name evidence
selects the matching variant for price and availability comparisons.

Visible/schema mismatch findings are evidence-gated. Narwhal compares only
explicit product metadata, itemprop values, labelled facts, and the visible H1;
it does not guess merchant facts from arbitrary prose. Expired
`priceValidUntil`, invalid currency/availability values, and stale visible-vs-
schema price or stock are called out separately.

Commerce observations come from a shared, cached source tree, not regex matches
inside inert markup. Comments, templates, escaped examples, SVG/MathML and
explicitly hidden subtrees cannot supply merchant facts. Itemprop observations
follow element-specific content/text/value/URL rules, support multi-name
properties and exact schema.org property URLs, and retain linked brands' visible
names. Inactive OpenGraph examples are ignored; first active type wins.
`meta.ecommerce.source_warnings` and `schema.ecommerce.source.extraction` expose
partial coverage (50,000 elements / 256 nesting levels) and the shared warning
count/detail budgets. This is source evidence, not computed CSS visibility or a
complete multi-product identity/conflict validator.

Product and Offer URL checks validate local syntax only: absolute HTTP(S), a
nonempty hostname, a valid port when present, and no embedded whitespace,
control characters or backslashes. Malformed bracket/IPv6 authorities become
invalid-URL findings instead of aborting reports. Valid IPv6, Unicode hosts,
encoded paths and non-default ports remain allowed; no DNS or reachability
test of these structured-data URLs is performed.
Bracketed IPvFuture literals follow [RFC 3986 §3.2.2](https://www.rfc-editor.org/rfc/rfc3986#section-3.2.2).

For multiple Product nodes, page-versus-schema comparisons require a unique
visible identifier, exact name or unique containment-name match. A single
Product remains comparison-eligible, including when its SKU disagrees with the
page. Identifier matching preserves punctuation and Unicode. Duplicate matching
identifiers, nonunique names or no matching identity do not fall back to schema
source order or infer identity from a coincidentally matching price.
`meta.ecommerce.comparison_status` is `ready` or `skipped_ambiguous`, with
`selection_method` explaining the selection; `selected_product` is null when
ambiguous. `schema.ecommerce.comparison.ambiguous` is a low-severity verification
note, not proof of a price defect. Completeness and validity checks still cover
every Product/Offer. This does not prove that unrelated page observations belong
to the selected variant.

For multiple Offers on the selected Product, price/currency/availability
comparisons use per-field consensus instead of the first Offer. A price
consensus also requires all declared currencies to agree with an explicit page
currency; amounts in different or unknown units are not compared. Non-unique,
incomplete evidence gets
`schema.ecommerce.offer.comparison.ambiguous`, a low verification note.
When Offer price evidence is used, the presence of any AggregateOffer also
blocks multi-Offer price comparisons, including homogeneous AggregateOffer sets.
`meta.ecommerce.offer_comparison_status` maps observed Offer fields to `ready`
(eligible, not necessarily valid/present) or `skipped_ambiguous`. The parent
`comparison_status` covers Product identity eligibility, not every Offer field.
Agreed fields, Product identity checks and all-offer completeness/validity remain
active. Ordinary single-Offer behavior is unchanged. No particular seller/Offer
is selected from a coincidentally matching amount; this is not a full seller,
price-component or observation-ownership resolver.

A single selected [`AggregateOffer`](https://schema.org/AggregateOffer) uses
inclusive [`lowPrice`](https://schema.org/lowPrice) and
[`highPrice`](https://schema.org/highPrice) compatibility instead of treating
the lower bound as an exact price. Both bounds must be finite scalar decimal
numbers/text (scientific notation is supported), non-negative and ordered.
Bound parsing is limited to 512 characters and does not strip units or separators;
unsupported Text/shapes cause a verification note, not a full schema validity
verdict. Existing singleton-array normalization is preserved. Explicit page and
Offer currencies must agree as three-letter codes. No conversion or currency
inference is performed. Observed decimal amounts can use existing comma-decimal
or grouping conventions and a currency label/symbol, but ambiguous prose/ranges
are not guessed. Decimal comparison does not round quoted amounts.

`meta.ecommerce.aggregate_price_comparison` records `method: inclusive_range`,
string bounds, currency and `within_range`. Eligibility is still represented by
`offer_comparison_status.price`; unknown/incomplete evidence is skipped with the
existing low verification note. Inside-range amounts are compatible, **not**
proof that an Offer exists at every interior amount or that a specific seller is
selected. Outside-range amounts retain `schema.ecommerce.price.mismatch` at high
severity. Known negative/inverted numeric bounds get
`schema.ecommerce.offer.invalid.range` even without a page comparison. Other
completeness/validity checks remain active, and multiple AggregateOffers still
cannot establish price consensus. Missing bounds are not replaced by `price`
or Product fallback values.

Offer references are resolved only for string `@id` values against nodes already
present in the document. Non-string IDs produce
`schema.ecommerce.offer.invalid.reference` instead of crashing a lookup.
Price/currency fallback reads only inline object members of
[`priceSpecification`](https://schema.org/priceSpecification); unsupported
non-object values get `schema.ecommerce.offer.price_specification.extraction`,
a low-severity coverage note, not a full JSON-LD validity verdict. Supported
members in mixed arrays are still inspected, and null values are ignored.
No referenced resource or context is fetched; context-coerced references and
other unsupported forms require manual verification.

Google distinguishes non-purchasable product snippets from merchant listings:
an editorial Product with an authentic review does not need an Offer, while a
merchant listing needs an active positive price and currency. See Google's
[Product structured data introduction](https://developers.google.com/search/docs/appearance/structured-data/product),
[product snippet](https://developers.google.com/search/docs/appearance/structured-data/product-snippet),
and [merchant listing](https://developers.google.com/search/docs/appearance/structured-data/merchant-listing)
documentation for the current authoritative eligibility rules.

## Generating markup
```
python scripts/generate_schema.py Product \
  --field name="Acme Widget" --field brand="Acme" \
  --field offers='{"@type":"Offer","price":"19.99","priceCurrency":"USD"}'
```
- `--field` values can be plain strings or inline JSON (for nested objects).
- Required fields you omit become clearly-marked `TODO` placeholders — replace
  them before publishing (the tool warns on stderr when TODOs remain).

## Validation
- The auditor checks presence of required/recommended properties and JSON
  validity across supported formats. For the authoritative check, use Google's **Rich Results Test** and
  the **schema.org validator** — recommend these for anything you'll ship.
