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
| Product | `name` | `image`, `offers`, `brand`, `aggregateRating` |
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
