# Brand assets

| File | Use |
|---|---|
| `logo.png` | Primary logo, **transparent** background, 2048×2048 — badge/emblem with the "NARWHAL" wordmark |
| `logo-512.png` | Downscaled 512×512 transparent version for README / web embeds |
| `logo-white.png` | Same primary logo on a solid **white** background (for photos, print, or where a fill is needed) |
| `logo-alt.png` | Alternate mark (dynamic leaping-narwhal pose), transparent — swap in by renaming to `logo.png` |
| `logo-dark.png` | **Dark-mode** variant, transparent, 2048×2048 — recolored so the navy structure/wordmark reads as light icy-blue on dark backgrounds |
| `logo-dark-512.png` | Downscaled 512×512 dark-mode version for README / web embeds |

All transparent PNGs are keyed from a flat white background (distance-to-white
alpha), so edges are anti-aliased and the badge interior is see-through.

**Dark backgrounds:** the primary mark uses deep-navy elements that fade on dark
surfaces, so use **`logo-dark.png`** there. The README auto-swaps to it via a
`<picture>` element with `prefers-color-scheme: dark`. The dark variant is derived
deterministically from `logo.png` (luminance fold: darks lighten, the teal/aqua
stays vivid) — regenerate it with:

```
python assets/make-dark-logo.py assets/logo.png assets/logo-dark.png
# then downscale to assets/logo-dark-512.png
```

**Concept:** a narwhal breaching from ocean waves, its spiral tusk rising into a
growth arrow over a bar/line chart — search & AI-answer visibility trending up.
Palette: deep ocean navy → teal/aqua.

To make the alternate the primary logo:
```
mv logo.png logo-primary.png && mv logo-alt.png logo.png
```
(then regenerate `logo-512.png` from the new `logo.png`).
