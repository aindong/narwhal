# Narwhal Remediation Plan — https://example.test/guides/widget

**Framework:** nextjs (86% confidence)  ·  **Actions:** 9  ·  **Mapping coverage:** 100%

_Read-only plan: inspect proposed owners and values before applying edits._

## Review required

### HIGH — Missing meta description

- **Rule:** `technical.missing.meta.description`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Add or revise the page meta description in its metadata/head owner.
- **Verify:** `narwhal diff before.json after.json`

### HIGH — Missing <title>

- **Rule:** `technical.missing.title`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Define a unique, descriptive page title in the framework's metadata/head API.
- **Verify:** `narwhal diff before.json after.json`

### MEDIUM — No structured data (JSON-LD)

- **Rule:** `schema.no.structured.data.json.ld`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Add or repair JSON-LD for the page's real entity; validate all values before publishing.
- **Verify:** `narwhal diff before.json after.json`

### MEDIUM — Images missing alt text

- **Rule:** `technical.images.missing.alt.text`
- **Likely owner:** `app/guides/widget/page.tsx`, `app/layout.tsx`, `app/page.tsx`
- **Change:** Add meaningful alt text to informative images; use empty alt for decorative images.
- **Verify:** `narwhal diff before.json after.json`

### MEDIUM — No canonical URL

- **Rule:** `technical.no.canonical.url`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Define the intended absolute canonical URL in the page or shared head owner.
- **Verify:** `narwhal diff before.json after.json`

### LOW — Incomplete Open Graph tags

- **Rule:** `content.incomplete.open.graph.tags`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Complete Open Graph and Twitter metadata using real page title, description, URL, and image.
- **Verify:** `narwhal diff before.json after.json`

## Apply, then verify after deploy

### MEDIUM — No robots.txt found

- **Rule:** `technical.no.robots.txt.found`
- **Likely owner:** `app/robots.ts`, `public/robots.txt`, `src/app/robots.ts`
- **Change:** Create or revise robots.txt deliberately, preserving intentional crawler policies.
- **Verify:** `narwhal diff before.json after.json`

### MEDIUM — No XML sitemap found

- **Rule:** `technical.no.xml.sitemap.found`
- **Likely owner:** `app/sitemap.ts`, `public/sitemap.xml`, `src/app/sitemap.ts`
- **Change:** Create/configure the sitemap and reference it from robots.txt using the canonical deployed URL.
- **Verify:** `narwhal diff before.json after.json`

### LOW — No llms.txt

- **Rule:** `geo.no.llms.txt`
- **Likely owner:** `public/llms.txt`
- **Change:** Generate a starter llms.txt in the public/static root, then curate every entry and TODO.
- **Verify:** `narwhal diff before.json after.json`

## Grouped template fixes

- **public_discovery_files** — 3 findings; owners: confirm owner
- **shared_head_metadata** — 5 findings; owners: app/guides/widget/page.tsx, app/layout.tsx
