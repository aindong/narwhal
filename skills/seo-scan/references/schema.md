# Structured data (schema.org / JSON-LD) reference

Structured data tells search engines and AI systems *what* a page is about in a
machine-readable way. It powers rich results (stars, FAQs, prices, breadcrumbs)
and helps AI answer engines identify and attribute entities.

## Format
- Use **JSON-LD** in a `<script type="application/ld+json">` block. Google
  recommends it over Microdata/RDFa; it's easier to generate and maintain.
- One `@graph` per page can hold multiple linked entities (WebSite +
  Organization + Article + Breadcrumb), connected via `@id` references.

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

Narwhal classifies a Product JSON-LD node as product evidence. Without Product
JSON-LD it requires stronger corroboration—Product microdata, or
`og:type=product` plus an explicit merchant fact—so an article that merely
mentions a price is not treated as a store page.

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
  validity. For the authoritative check, use Google's **Rich Results Test** and
  the **schema.org validator** — recommend these for anything you'll ship.
