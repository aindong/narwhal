# Demo

The animated terminal demo in the main README ([`assets/demo.gif`](../assets/demo.gif))
is generated — not hand-recorded — so it's reproducible. Two ways to (re)make it:

## Quick (no external tools) — Pillow

```bash
pip install pillow
python demo/make_demo_gif.py        # -> assets/demo.gif
```

Draws a scripted Narwhal session (typed commands + realistic output) straight to a
GIF. The session is curated for length but faithful to real `narwhal` output. Edit
the `SESSION` list in [`make_demo_gif.py`](make_demo_gif.py) to change what's shown.

## High-fidelity — VHS

[VHS](https://github.com/charmbracelet/vhs) (by Charm) records a **real** terminal
running the actual commands, and renders a GIF **or MP4/WebM** video. It needs
`ffmpeg` + `ttyd`.

```bash
# macOS: brew install vhs   ·   see the VHS repo for Linux/Windows
vhs demo/demo.tape                  # -> assets/demo.gif
```

The recipe is [`demo.tape`](demo.tape). To produce a real video instead of a GIF,
change the `Output` line to `demo/demo.mp4` (or `.webm`).

## Other options

- **[asciinema](https://asciinema.org)** — records a lightweight, shareable
  terminal *cast* you can embed or replay: `asciinema rec`. Convert to GIF with
  [`agg`](https://github.com/asciinema/agg).
- **Screen capture** (OBS, QuickTime, ScreenToGif) — for a true screencast/video
  when you want to show the whole flow, including opening the generated HTML/PDF
  report in a browser.

Whichever you use, keep the demo short (a few commands) and lead with `scan` —
it's the fastest "wow".
