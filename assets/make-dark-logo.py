"""Derive a dark-mode logo from the light logo by folding luminance.

L' = max(L, 1-L): pixels darker than mid get mirrored up to a light value while
already-bright pixels (the teal/aqua chart, tusk, highlights) are left untouched
— so nothing gets darker, the navy structure/wordmark becomes light, and the
brand's teal stays vivid. Lifted darks are desaturated toward icy white so the
wordmark reads crisply on a dark background. Alpha is preserved exactly.

Usage:
    python assets/make-dark-logo.py assets/logo.png assets/logo-dark.png

Also writes a 512x512 sibling (<out>-512.png) next to OUT. Needs Pillow + numpy.
"""

import sys
import numpy as np
from PIL import Image

SRC, OUT = sys.argv[1], sys.argv[2]

im = np.asarray(Image.open(SRC).convert("RGBA")).astype(np.float64)
rgb = im[..., :3] / 255.0
alpha = im[..., 3:4]

r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
mx = rgb.max(-1)
mn = rgb.min(-1)
l = (mx + mn) / 2.0
diff = mx - mn

# saturation
s = np.zeros_like(l)
nz = diff > 1e-9
s[nz & (l < 0.5)] = (diff / (mx + mn + 1e-12))[nz & (l < 0.5)]
s[nz & (l >= 0.5)] = (diff / (2.0 - mx - mn + 1e-12))[nz & (l >= 0.5)]

# hue (0..1)
h = np.zeros_like(l)
rc = np.where(nz, (mx - r) / (diff + 1e-12), 0)
gc = np.where(nz, (mx - g) / (diff + 1e-12), 0)
bc = np.where(nz, (mx - b) / (diff + 1e-12), 0)
h = np.where(mx == r, bc - gc, h)
h = np.where(mx == g, 2.0 + rc - bc, h)
h = np.where(mx == b, 4.0 + gc - rc, h)
h = (h / 6.0) % 1.0

# --- the transform ---
l2 = np.maximum(l, 1.0 - l)                     # fold: lighten darks, keep brights
lift = np.clip((l2 - l) / 0.8, 0.0, 1.0)        # 0 for bright px, ~1 for deep navy
s2 = s * (1.0 - 0.55 * lift)                     # desaturate the lifted darks -> icy

# hsl -> rgb (vectorized)
def _hue(p, q, t):
    t = t % 1.0
    out = p.copy()
    m = t < 1/6;  out[m] = (p + (q - p) * 6.0 * t)[m]
    m = (t >= 1/6) & (t < 1/2); out[m] = q[m]
    m = (t >= 1/2) & (t < 2/3); out[m] = (p + (q - p) * (2/3 - t) * 6.0)[m]
    return out

q = np.where(l2 < 0.5, l2 * (1 + s2), l2 + s2 - l2 * s2)
p = 2.0 * l2 - q
r2 = _hue(p, q, h + 1/3)
g2 = _hue(p, q, h)
b2 = _hue(p, q, h - 1/3)
gray = s2 < 1e-9
r2 = np.where(gray, l2, r2)
g2 = np.where(gray, l2, g2)
b2 = np.where(gray, l2, b2)

out = np.stack([r2, g2, b2], -1)
out = np.clip(out * 255.0, 0, 255)
result = np.concatenate([out, alpha], -1).astype(np.uint8)
img = Image.fromarray(result, "RGBA")
img.save(OUT)
print(f"wrote {OUT} {result.shape}")

# 512x512 sibling for README / web embeds
small = OUT.rsplit(".", 1)
small = f"{small[0]}-512.{small[1]}" if len(small) == 2 else OUT + "-512.png"
img.resize((512, 512), Image.LANCZOS).save(small)
print(f"wrote {small} (512x512)")
