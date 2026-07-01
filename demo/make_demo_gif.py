#!/usr/bin/env python3
"""Render a terminal-style demo GIF for the README (no external tools needed).

This is the quick, dependency-light path (just Pillow): it draws a scripted
Narwhal terminal session — typed commands + realistic output — into an animated
GIF. For a higher-fidelity screencast, use the VHS tape instead (see
`demo/demo.tape` and `demo/README.md`).

    python demo/make_demo_gif.py            # -> assets/demo.gif

The session shown is faithful to real `narwhal` output, curated for length.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

# ---- theme (GitHub-dark) --------------------------------------------------
W, H = 960, 600
PAD, TITLEBAR, LINEH, FONTSIZE = 22, 36, 27, 19
BG = (13, 17, 23)          # #0d1117
BAR = (22, 27, 34)
FG = (201, 209, 217)       # default text
MUTED = (125, 133, 144)
PROMPT = (63, 185, 190)    # teal
CMD = (240, 246, 252)
HEAD = (88, 166, 255)      # headings (blue)
SEV = {"crit": (248, 81, 73), "high": (219, 109, 40), "med": (210, 153, 34),
       "low": (56, 139, 253), "ok": (63, 185, 80)}
VISIBLE_LINES = (H - TITLEBAR - PAD * 2) // LINEH

FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/Library/Fonts/Menlo.ttc",
]


def _font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT = _font(FONTSIZE)
FONT_B = _font(FONTSIZE)

# ---- the scripted session -------------------------------------------------
# Each line: (style, text). Styles: head, muted, plain, or a severity key.
SESSION = [
    {"cmd": "narwhal scan https://example.com", "hold": 1400, "lines": [
        ("muted", ""),
        ("head", "SEO & GEO Audit — https://example.com"),
        ("muted", ""),
        ("plain", "Health score: 56/100 (needs work)  ·  status 200"),
        ("muted", ""),
        ("head", "Summary"),
        ("plain", "2 high, 1 medium issue(s) need attention, plus 2 quick wins."),
        ("muted", ""),
        ("plain", "Top priorities:"),
        ("high", "No meta description  (Technical SEO)"),
        ("high", "Thin content  (Content & E-E-A-T)"),
        ("med", "No structured data  (Structured data)"),
    ]},
    {"cmd": "narwhal audit example.com --vitals --format pdf -o audit.pdf", "hold": 1500,
     "lines": [
        ("muted", ""),
        ("ok", "Wrote PDF audit to audit.pdf  (overall 61/100)"),
        ("muted", "   homepage + crawl + sitemap + Core Web Vitals, one shareable report"),
     ]},
    {"cmd": "narwhal vitals example.com --lab", "hold": 2200, "lines": [
        ("muted", ""),
        ("head", "PageSpeed Insights (lab) — example.com  ·  mobile"),
        ("plain", "Performance score: 83/100 (needs-improvement)"),
        ("muted", ""),
        ("ok", "LCP   2.1 s    good"),
        ("ok", "TBT   120 ms   good"),
        ("ok", "CLS   0.05     good"),
        ("med", "TTI   4.2 s    needs-improvement"),
    ]},
]


def _bullet_style(style):
    return SEV.get(style)


def render_frame(buffer):
    """Draw the terminal window with the given list of (style, text) lines."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # title bar with traffic-light dots
    d.rectangle([0, 0, W, TITLEBAR], fill=BAR)
    for i, c in enumerate([(248, 81, 73), (210, 153, 34), (63, 185, 80)]):
        d.ellipse([PAD + i * 22, 13, PAD + i * 22 + 11, 24], fill=c)
    d.text((PAD + 78, 9), "narwhal — demo", font=FONT, fill=MUTED)

    y = TITLEBAR + PAD
    for style, text in buffer[-VISIBLE_LINES:]:
        x = PAD
        if style == "cmd":
            d.text((x, y), "$ ", font=FONT_B, fill=PROMPT)
            d.text((x + FONT.getlength("$ "), y), text, font=FONT_B, fill=CMD)
        elif _bullet_style(style):
            d.text((x, y), "●", font=FONT, fill=_bullet_style(style))
            d.text((x + FONT.getlength("●  "), y), text, font=FONT, fill=FG)
        elif style == "head":
            d.text((x, y), text, font=FONT_B, fill=HEAD)
        elif style == "muted":
            d.text((x, y), text, font=FONT, fill=MUTED)
        else:
            d.text((x, y), text, font=FONT, fill=FG)
        y += LINEH
    return img


def build():
    frames, durations = [], []
    buffer = []  # list of (style, text)

    def emit(ms):
        frames.append(render_frame(buffer))
        durations.append(ms)

    emit(700)  # opening beat
    for seg in SESSION:
        # "type" the command in a few chunks with a trailing cursor
        cmd = seg["cmd"]
        buffer.append(["cmd", ""])
        steps = max(3, len(cmd) // 8)
        for s in range(1, steps + 1):
            buffer[-1][1] = cmd[: int(len(cmd) * s / steps)] + "█"
            emit(55)
        buffer[-1][1] = cmd
        emit(350)
        # reveal output line by line
        for style, text in seg["lines"]:
            buffer.append((style, text))
            emit(130)
        emit(seg["hold"])
    emit(1600)  # final hold

    os.makedirs("assets", exist_ok=True)
    out = os.path.join("assets", "demo.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True, disposal=2)
    size_kb = os.path.getsize(out) // 1024
    print(f"wrote {out} — {len(frames)} frames, {size_kb} KB")


if __name__ == "__main__":
    build()
