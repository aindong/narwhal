# Narwhal terminal demo — VHS tape (the high-fidelity path).
#
# VHS renders this into a clean, reproducible GIF/MP4. Install it from
# https://github.com/charmbracelet/vhs (needs ffmpeg + ttyd), then run:
#
#     vhs demo/demo.tape        # -> assets/demo.gif
#
# Run from the repo root. Prefer a quick, no-tools GIF? See demo/make_demo_gif.py.

Output assets/demo.gif

Set Shell bash
Set FontSize 19
Set Width 960
Set Height 600
Set Padding 22
Set Theme "Dracula"
Set TypingSpeed 45ms

# Hidden setup: alias `narwhal` so it runs from a clone without installing.
Hide
Type "alias narwhal='python skills/seo-scan/scripts/cli.py' && clear"
Enter
Show

Type "narwhal scan https://example.com"
Sleep 500ms
Enter
Sleep 5s

Type "narwhal audit https://example.com --format html -o audit.html"
Sleep 500ms
Enter
Sleep 5s

Type "narwhal schema Article --field headline='How GEO works' --field author='Jane Doe'"
Sleep 500ms
Enter
Sleep 5s

# Tip: add `narwhal vitals example.com --lab` for real Core Web Vitals
# (set CRUX_API_KEY / PAGESPEED_API_KEY first).
