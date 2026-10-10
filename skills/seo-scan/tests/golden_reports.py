"""Deterministic full-report fixture and snapshot helpers."""

from pathlib import Path
import sys
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import scan as scan_mod  # noqa: E402
from lib import htmlx, http  # noqa: E402

FIXTURE = HERE / "fixtures" / "reports" / "full-report.html"
SNAPSHOTS = HERE / "fixtures" / "reports" / "snapshots"
URL = "https://example.test/guides/answer-visibility"


def build_report():
    """Run the real scan pipeline with fixed I/O and the stdlib parser."""
    source = FIXTURE.read_text(encoding="utf-8")
    response = http.Response(
        url=URL,
        final_url=URL,
        status=200,
        headers={"content-type": "text/html", "content-language": "en"},
        text=source,
        elapsed_ms=17,
    )
    context = {
        "robots_txt": "User-agent: *\nDisallow:\nSitemap: https://example.test/sitemap.xml",
        "llms_txt": False,
        "sitemap_found": True,
    }
    parse_stdlib = lambda text, base_url="": htmlx._parse_stdlib(text, base_url)
    with mock.patch.object(scan_mod.http, "fetch", return_value=response), \
            mock.patch.object(scan_mod.htmlx, "parse", side_effect=parse_stdlib):
        return scan_mod.scan(URL, ctx=context, check_images=False)


def render_all():
    report = build_report()
    return {
        "full-report.md": report.to_markdown(),
        "full-report.json": report.to_json() + "\n",
        "full-report.html": report.to_html(),
    }


def write_snapshots():
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    rendered = render_all()
    for name, content in rendered.items():
        (SNAPSHOTS / name).write_text(content, encoding="utf-8")
    return [SNAPSHOTS / name for name in rendered]
