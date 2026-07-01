#!/usr/bin/env python3
"""Regenerate the inline report logo (skills/seo-scan/scripts/lib/brand.py).

The HTML/PDF reports are self-contained (no external resources, and assets/ isn't
shipped in the pip/uvx package), so the header/footer logo is baked into the code
as a base64 PNG data URI. Run this when the logo changes:

    python assets/make-brand-logo.py            # uses assets/logo-512.png, 128px
    python assets/make-brand-logo.py assets/logo.png 160

Needs Pillow.
"""

import base64
import io
import os
import sys

from PIL import Image

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), "logo-512.png")
PX = int(sys.argv[2]) if len(sys.argv) > 2 else 128
OUT = os.path.join(os.path.dirname(__file__), "..", "skills", "seo-scan",
                   "scripts", "lib", "brand.py")

im = Image.open(SRC).convert("RGBA").resize((PX, PX), Image.LANCZOS)
buf = io.BytesIO()
im.save(buf, "PNG", optimize=True)
b64 = base64.b64encode(buf.getvalue()).decode("ascii")

lines = [
    '"""Inline Narwhal brand mark for self-contained reports.',
    "",
    "The HTML/PDF reports must render with no external resources (offline, and the",
    "`assets/` folder is not shipped in the pip/uvx package). So the logo is baked in",
    f"here as a base64 PNG data URI — a small {PX}px mark used in report headers.",
    "Regenerate with `assets/make-brand-logo.py` if the logo changes.",
    '"""',
    "",
    "LOGO_DATA_URI = (",
    '    "data:image/png;base64,"',
]
lines += [f'    "{b64[i:i + 76]}"' for i in range(0, len(b64), 76)]
lines += [
    ")",
    "",
    "",
    'def logo_img(height=48, alt="Narwhal"):',
    '    """An <img> tag for the inline logo at the given pixel height."""',
    "    return (f'<img class=\"brand-logo\" src=\"{LOGO_DATA_URI}\" '",
    "            f'alt=\"{alt}\" height=\"{height}\">')",
]
with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"wrote {OUT} ({PX}px, base64 {len(b64) // 1024} KB)")
