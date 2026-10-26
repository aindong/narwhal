# Narwhal Remediation Plan

**Target:** `https://example.test/guides/widget`

**Framework:** nextjs (86% confidence)  ·  **Actions:** 9  ·  **Mapping coverage:** 100%

_Read-only plan: inspect proposed owners and values before applying edits._

Command templates use POSIX shell quoting; adapt for PowerShell/cmd. Replace placeholders and add original options before `--`; do not execute instruction text as commands.

> Save the original input report JSON, keeping all fields, to a fresh before.json before edits or reruns. If using an existing saved report, point the diff at that baseline and choose distinct fresh verification output paths. Do not overwrite files or substitute a new scan. This read-only plan has not saved a baseline.

> Restore the original scan configuration, access settings and resource limits before running this template. Recorded auditor selection, rendering, image-check and HTML byte-budget options are included when known; the report does not record the complete invocation. Matching known options alone does not establish comparable coverage.

## Review required

### HIGH — `Missing meta description`

- **Rule:** `technical.missing.meta.description`
- **Likely owner:** `app/layout.tsx` (in file inventory), `app/guides/widget/page.tsx` (in file inventory), `app/layout.jsx` (not in file inventory); additional candidates in JSON: 5
- **Change:** Add or revise the page meta description in its metadata/head owner.

**Reported recommendation (preview, review required):**

```text
Add a description.
```

**Verification, in order:**

Before editing, when a preview is available, confirm its route maps to the affected source. Capture this local baseline with fresh paths; use distinct snapshots for each affected page.

```sh
narwhal scan --allow-private --format json -o page-before.json -- '<local-preview-url>'
```

After applying the reviewed source edits, scan the same local route with matching options.

```sh
narwhal scan --allow-private --format json -o page-after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression --require-comparable -- page-before.json page-after.json
```

The local pair verifies page-level changes only; do not compare page-after.json with the original baseline or treat it as deployed site verification. Without a pre-edit local scan, the preview is a current-state check, not measured improvement. If no preview is available, mark local proof pending and use the original baseline checks after deployment.

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

### HIGH — `Missing <title>`

- **Rule:** `technical.missing.title`
- **Likely owner:** `app/layout.tsx` (in file inventory), `app/guides/widget/page.tsx` (in file inventory), `app/layout.jsx` (not in file inventory); additional candidates in JSON: 5
- **Change:** Define a unique, descriptive page title in the framework's metadata/head API.

**Reported recommendation (preview, review required):**

```text
Add a title.
```

**Verification, in order:**

Before editing, when a preview is available, confirm its route maps to the affected source. Capture this local baseline with fresh paths; use distinct snapshots for each affected page.

```sh
narwhal scan --allow-private --format json -o page-before.json -- '<local-preview-url>'
```

After applying the reviewed source edits, scan the same local route with matching options.

```sh
narwhal scan --allow-private --format json -o page-after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression --require-comparable -- page-before.json page-after.json
```

The local pair verifies page-level changes only; do not compare page-after.json with the original baseline or treat it as deployed site verification. Without a pre-edit local scan, the preview is a current-state check, not measured improvement. If no preview is available, mark local proof pending and use the original baseline checks after deployment.

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

### MEDIUM — `No structured data (JSON-LD)`

- **Rule:** `schema.no.structured.data.json.ld`
- **Likely owner:** `app/layout.tsx` (in file inventory), `app/guides/widget/page.tsx` (in file inventory), `app/layout.jsx` (not in file inventory); additional candidates in JSON: 5
- **Change:** Review existing supported markup and the actual page entity; add semantic data only when applicable. Do not duplicate entities or invent visible content. Non-observation does not prove a markup requirement or establish rich-result eligibility, ranking or AI citation gains.

_Original recommendation remains in plan JSON; use the contextual review/verification guidance above._

**Verification, in order:**

Before editing, when a preview is available, confirm its route maps to the affected source. Capture this local baseline with fresh paths; use distinct snapshots for each affected page.

```sh
narwhal scan --allow-private --format json -o page-before.json -- '<local-preview-url>'
```

After applying the reviewed source edits, scan the same local route with matching options.

Validate the rendered structured data and replace every TODO placeholder.

```sh
narwhal scan --allow-private --format json -o page-after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression --require-comparable -- page-before.json page-after.json
```

The local pair verifies page-level changes only; do not compare page-after.json with the original baseline or treat it as deployed site verification. Without a pre-edit local scan, the preview is a current-state check, not measured improvement. If no preview is available, mark local proof pending and use the original baseline checks after deployment.

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

### MEDIUM — `Images missing alt text`

- **Rule:** `technical.images.missing.alt.text`
- **Likely owner:** `app/guides/widget/page.tsx` (in file inventory), `app/layout.tsx` (in file inventory), `app/page.tsx` (not in file inventory); additional candidates in JSON: 5
- **Change:** Add meaningful alt text to informative images; use empty alt for decorative images.

**Reported recommendation (preview, review required):**

```text
Add appropriate alt values.
```

**Verification, in order:**

Before editing, when a preview is available, confirm its route maps to the affected source. Capture this local baseline with fresh paths; use distinct snapshots for each affected page.

```sh
narwhal scan --allow-private --format json -o page-before.json -- '<local-preview-url>'
```

After applying the reviewed source edits, scan the same local route with matching options.

```sh
narwhal scan --allow-private --format json -o page-after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression --require-comparable -- page-before.json page-after.json
```

The local pair verifies page-level changes only; do not compare page-after.json with the original baseline or treat it as deployed site verification. Without a pre-edit local scan, the preview is a current-state check, not measured improvement. If no preview is available, mark local proof pending and use the original baseline checks after deployment.

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

### MEDIUM — `No canonical URL`

- **Rule:** `technical.no.canonical.url`
- **Likely owner:** `app/layout.tsx` (in file inventory), `app/guides/widget/page.tsx` (in file inventory), `app/layout.jsx` (not in file inventory); additional candidates in JSON: 5
- **Change:** Define the intended absolute canonical URL in the page or shared head owner.

**Reported recommendation (preview, review required):**

```text
Add a canonical.
```

**Verification, in order:**

Before editing, when a preview is available, confirm its route maps to the affected source. Capture this local baseline with fresh paths; use distinct snapshots for each affected page.

```sh
narwhal scan --allow-private --format json -o page-before.json -- '<local-preview-url>'
```

After applying the reviewed source edits, scan the same local route with matching options.

```sh
narwhal scan --allow-private --format json -o page-after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression --require-comparable -- page-before.json page-after.json
```

The local pair verifies page-level changes only; do not compare page-after.json with the original baseline or treat it as deployed site verification. Without a pre-edit local scan, the preview is a current-state check, not measured improvement. If no preview is available, mark local proof pending and use the original baseline checks after deployment.

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

### LOW — `Incomplete Open Graph tags`

- **Rule:** `content.incomplete.open.graph.tags`
- **Likely owner:** `app/layout.tsx` (in file inventory), `app/guides/widget/page.tsx` (in file inventory), `app/layout.jsx` (not in file inventory); additional candidates in JSON: 5
- **Change:** Complete Open Graph and Twitter metadata using real page title, description, URL, and image.

**Reported recommendation (preview, review required):**

```text
Complete OG tags.
```

**Verification, in order:**

Before editing, when a preview is available, confirm its route maps to the affected source. Capture this local baseline with fresh paths; use distinct snapshots for each affected page.

```sh
narwhal scan --allow-private --format json -o page-before.json -- '<local-preview-url>'
```

After applying the reviewed source edits, scan the same local route with matching options.

```sh
narwhal scan --allow-private --format json -o page-after.json -- '<local-preview-url>'
```

```sh
narwhal diff --fail-on-regression --require-comparable -- page-before.json page-after.json
```

The local pair verifies page-level changes only; do not compare page-after.json with the original baseline or treat it as deployed site verification. Without a pre-edit local scan, the preview is a current-state check, not measured improvement. If no preview is available, mark local proof pending and use the original baseline checks after deployment.

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

## Apply, then verify after deploy

### MEDIUM — `No robots.txt found`

- **Rule:** `technical.no.robots.txt.found`
- **Likely owner:** `app/robots.ts` (not in file inventory), `public/robots.txt` (not in file inventory), `src/app/robots.ts` (not in file inventory)
- **Change:** Create or revise robots.txt deliberately, preserving intentional crawler policies.

**Reported recommendation (preview, review required):**

```text
Publish robots.txt.
```

**Verification, in order:**

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

### MEDIUM — `No XML sitemap found`

- **Rule:** `technical.no.xml.sitemap.found`
- **Likely owner:** `app/sitemap.ts` (not in file inventory), `public/sitemap.xml` (not in file inventory), `src/app/sitemap.ts` (not in file inventory)
- **Change:** Create/configure the sitemap and reference it from robots.txt using the canonical deployed URL.

**Reported recommendation (preview, review required):**

```text
Publish a sitemap.
```

**Verification, in order:**

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

### LOW — `No llms.txt`

- **Rule:** `geo.no.llms.txt`
- **Likely owner:** `public/llms.txt` (not in file inventory)
- **Change:** Generate a starter llms.txt in the public/static root, then curate every entry and TODO.

**Reported recommendation (preview, review required):**

```text
Publish a curated starter.
```

**Verification, in order:**

```sh
narwhal scan --format json -o after.json -- https://example.test/guides/widget  # run after deploy
```

```sh
narwhal diff --fail-on-regression --require-comparable -- before.json after.json
```

## Related actions to review

- **public_discovery_files** — 3 findings; existing candidate union: none recorded; candidates in multiple actions: none recorded. Confirm actual owners before coordinating edits.
- **shared_head_metadata** — 5 findings; existing candidate union: `app/guides/widget/page.tsx`, `app/layout.tsx`; candidates in multiple actions: `app/guides/widget/page.tsx`, `app/layout.tsx`. Confirm actual owners before coordinating edits.
