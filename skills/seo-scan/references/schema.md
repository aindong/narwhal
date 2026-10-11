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
partial coverage (50,000 elements / 256 nesting levels) and a 64-warning cap plus
one omission notice. This is source evidence, not computed CSS visibility or a
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
every Product/Offer. This does not resolve multiple offers on one Product or
prove that unrelated page observations belong to the selected variant.

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
