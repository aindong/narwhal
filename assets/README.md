# Brand assets

| File | Use |
|---|---|
| `logo.png` | Primary logo, **transparent** background, 2048×2048 — badge/emblem with the "NARWHAL" wordmark |
| `logo-512.png` | Downscaled 512×512 transparent version for README / web embeds |
| `logo-white.png` | Same primary logo on a solid **white** background (for photos, print, or where a fill is needed) |
| `logo-alt.png` | Alternate mark (dynamic leaping-narwhal pose), transparent — swap in by renaming to `logo.png` |

All transparent PNGs are keyed from a flat white background (distance-to-white
alpha), so edges are anti-aliased and the badge interior is see-through.

**Dark backgrounds:** the mark uses deep-navy elements, so it reads best on light
or medium backgrounds. For dark-mode / dark marketing surfaces, use a light or
inverted variant (not yet generated — ask to add one).

**Concept:** a narwhal breaching from ocean waves, its spiral tusk rising into a
growth arrow over a bar/line chart — search & AI-answer visibility trending up.
Palette: deep ocean navy → teal/aqua.

To make the alternate the primary logo:
```
mv logo.png logo-primary.png && mv logo-alt.png logo.png
```
(then regenerate `logo-512.png` from the new `logo.png`).
