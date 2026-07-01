# Brand assets

| File | Use |
|---|---|
| `logo.png` | Primary logo, 2048×2048 (full resolution) — badge/emblem with the "NARWHAL" wordmark |
| `logo-512.png` | Downscaled 512×512 version for README / web embeds |
| `logo-alt.png` | Alternate mark (dynamic leaping-narwhal pose) — swap in by renaming to `logo.png` |

**Concept:** a narwhal breaching from ocean waves, its spiral tusk rising into a
growth arrow over a bar/line chart — search & AI-answer visibility trending up.
Palette: deep ocean navy → teal/aqua.

To make the alternate the primary logo:
```
mv logo.png logo-primary.png && mv logo-alt.png logo.png
```
(then regenerate `logo-512.png` from the new `logo.png`).
