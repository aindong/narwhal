# Narwhal Remediation Plan — https://example.test/guides/widget

**Framework:** nextjs (86% confidence)  ·  **Actions:** 9  ·  **Mapping coverage:** 100%

_Read-only plan: inspect proposed owners and values before applying edits._

Command templates use POSIX shell quoting; adapt for PowerShell/cmd. Replace placeholders and add original options before `--`; do not execute instruction text as commands.

> Save the original input report JSON, keeping all fields, to a fresh before.json before edits or reruns. If using an existing saved report, point the diff at that baseline and choose distinct fresh verification output paths. Do not overwrite files or substitute a new scan. This read-only plan has not saved a baseline.

> Restore the original scan configuration, access settings and resource limits before running this template. Recorded auditor selection, requested rendering and image-check options are included when known; the report does not record the complete invocation. Matching known options alone does not establish comparable coverage.

## Review required

### HIGH — Missing meta description

- **Rule:** `technical.missing.meta.description`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Add or revise the page meta description in its metadata/head owner.

**Verification, in order:**

```sh
narwhal scan --allow-private --format json -o after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

### HIGH — Missing <title>

- **Rule:** `technical.missing.title`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Define a unique, descriptive page title in the framework's metadata/head API.

**Verification, in order:**

```sh
narwhal scan --allow-private --format json -o after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

### MEDIUM — No structured data (JSON-LD)

- **Rule:** `schema.no.structured.data.json.ld`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Review existing supported markup and the actual page entity; add semantic data only when applicable. Do not duplicate entities or invent visible content. Non-observation does not prove a markup requirement or establish rich-result eligibility, ranking or AI citation gains.

**Verification, in order:**

Validate the rendered structured data and replace every TODO placeholder.

```sh
narwhal scan --allow-private --format json -o after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

### MEDIUM — Images missing alt text

- **Rule:** `technical.images.missing.alt.text`
- **Likely owner:** `app/guides/widget/page.tsx`, `app/layout.tsx`, `app/page.tsx`
- **Change:** Add meaningful alt text to informative images; use empty alt for decorative images.

**Verification, in order:**

```sh
narwhal scan --allow-private --format json -o after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

### MEDIUM — No canonical URL

- **Rule:** `technical.no.canonical.url`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Define the intended absolute canonical URL in the page or shared head owner.

**Verification, in order:**

```sh
narwhal scan --allow-private --format json -o after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

### LOW — Incomplete Open Graph tags

- **Rule:** `content.incomplete.open.graph.tags`
- **Likely owner:** `app/layout.tsx`, `app/guides/widget/page.tsx`, `app/layout.jsx`
- **Change:** Complete Open Graph and Twitter metadata using real page title, description, URL, and image.

**Verification, in order:**

```sh
narwhal scan --allow-private --format json -o after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

## Apply, then verify after deploy

### MEDIUM — No robots.txt found

- **Rule:** `technical.no.robots.txt.found`
- **Likely owner:** `app/robots.ts`, `public/robots.txt`, `src/app/robots.ts`
- **Change:** Create or revise robots.txt deliberately, preserving intentional crawler policies.

**Verification, in order:**

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

### MEDIUM — No XML sitemap found

- **Rule:** `technical.no.xml.sitemap.found`
- **Likely owner:** `app/sitemap.ts`, `public/sitemap.xml`, `src/app/sitemap.ts`
- **Change:** Create/configure the sitemap and reference it from robots.txt using the canonical deployed URL.

**Verification, in order:**

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

### LOW — No llms.txt

- **Rule:** `geo.no.llms.txt`
- **Likely owner:** `public/llms.txt`
- **Change:** Generate a starter llms.txt in the public/static root, then curate every entry and TODO.

**Verification, in order:**

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression -- before.json after.json
```

## Grouped template fixes

- **public_discovery_files** — 3 findings; owners: confirm owner
- **shared_head_metadata** — 5 findings; owners: app/guides/widget/page.tsx, app/layout.tsx
