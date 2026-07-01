#!/usr/bin/env python3
"""narwhal vitals — real Core Web Vitals field data from the Chrome UX Report.

This is the one **opt-in, network** feature: it calls Google's CrUX API to fetch
real-world (28-day, 75th-percentile) Core Web Vitals for a URL or origin. It is
NOT on the default scan path — you must pass an API key — because everything else
in Narwhal is local-only and honest about what it can measure. Lab tools (and our
local `technical` auditor) can flag performance *hygiene*, but only field data
tells you what real Chrome users actually experience.

As of 2026 the PageSpeed Insights API is dropping CrUX field data, so this talks
to the dedicated CrUX API directly. The Core Web Vitals are **LCP, INP, CLS**
(INP replaced FID in 2024).

Get a free key: https://developer.chrome.com/docs/crux/api  (enable the
"Chrome UX Report API"). Then:

    narwhal vitals https://example.com/page --crux-key YOUR_KEY
    CRUX_API_KEY=... narwhal vitals https://example.com --origin --form-factor phone

CrUX only has data for pages/origins with enough real traffic; low-traffic URLs
return "no data" (try --origin).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"

# metric key -> (label, unit, good_max, needs_improvement_max). Values at p75.
CORE = [
    ("largest_contentful_paint", "LCP", "ms", 2500, 4000),
    ("interaction_to_next_paint", "INP", "ms", 200, 500),
    ("cumulative_layout_shift", "CLS", "", 0.1, 0.25),
]
SECONDARY = [
    ("first_contentful_paint", "FCP", "ms", 1800, 3000),
    ("experimental_time_to_first_byte", "TTFB", "ms", 800, 1800),
]
_ALL = {m[0]: m for m in CORE + SECONDARY}
_RATING_ICON = {"good": "🟢", "needs-improvement": "🟡", "poor": "🔴"}
_FORM_FACTORS = {"phone": "PHONE", "desktop": "DESKTOP", "tablet": "TABLET"}


def rate(good_max, ni_max, value) -> str:
    if value <= good_max:
        return "good"
    if value <= ni_max:
        return "needs-improvement"
    return "poor"


def _query(target, api_key, *, origin, form_factor, timeout) -> tuple:
    """POST to the CrUX API. Returns (status_code, json_or_None, error_or_None).

    Only ever contacts Google's fixed CrUX host, so there is no SSRF surface —
    ``target`` is a *payload* value, not the host we connect to."""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    body = {"origin" if origin else "url": target}
    if form_factor:
        body["formFactor"] = _FORM_FACTORS[form_factor]
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{CRUX_ENDPOINT}?key={api_key}", data=data,
        headers={"Content-Type": "application/json", "User-Agent": "narwhal-crux"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, json.loads(fh.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        return exc.code, None, detail or exc.reason
    except Exception as exc:  # noqa: BLE001
        return 0, None, str(exc)


def _p75(metric: dict):
    """Extract and coerce the p75 value (CLS comes back as a string)."""
    raw = (metric or {}).get("percentiles", {}).get("p75")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_record(record: dict) -> dict:
    """Turn a CrUX ``record`` into our structured metrics (pure; offline-testable)."""
    metrics_in = record.get("metrics", {})
    rows = []
    for key, (mkey, label, unit, good, ni) in ((k, _ALL[k]) for k in _ALL if k in metrics_in):
        v = _p75(metrics_in[key])
        if v is None:
            continue
        rows.append({"metric": label, "key": key, "unit": unit,
                     "p75": v, "rating": rate(good, ni, v),
                     "core": mkey in {m[0] for m in CORE}})
    # Core Web Vitals assessment: all three core metrics present AND "good" at p75.
    core_ratings = {r["metric"]: r["rating"] for r in rows if r["core"]}
    have_all = all(m[1] in core_ratings for m in CORE)
    cwv_pass = (have_all and all(v == "good" for v in core_ratings.values())) if have_all else None

    period = ""
    cp = record.get("collectionPeriod", {})
    last = cp.get("lastDate")
    if isinstance(last, dict) and last:
        period = f"{last.get('year')}-{last.get('month'):02d}-{last.get('day'):02d}"
    return {"rows": rows, "cwv_pass": cwv_pass, "period": period}


def analyze(target, api_key, *, origin=False, form_factor=None, timeout=20) -> dict:
    status, payload, error = _query(
        target, api_key, origin=origin, form_factor=form_factor, timeout=timeout)
    key_label = ("origin " if origin else "") + target
    if status == 404:
        return {"found": False, "target": key_label, "form_factor": form_factor,
                "error": "CrUX has no data for this "
                         + ("origin" if origin else "URL")
                         + " (needs enough real-user traffic; try --origin)."}
    if payload is None:
        return {"found": False, "target": key_label, "form_factor": form_factor,
                "error": error or f"CrUX request failed (HTTP {status})."}
    parsed = parse_record(payload.get("record", {}))
    return {"found": True, "target": key_label, "form_factor": form_factor, **parsed}


def _fmt(row) -> str:
    v = row["p75"]
    return f"{v:.2f}" if row["unit"] == "" else f"{int(round(v))} {row['unit']}"


def render_markdown(r: dict) -> str:
    ff = f" · {r['form_factor']}" if r.get("form_factor") else ""
    lines = [f"# Core Web Vitals (field data) — {r['target']}{ff}", ""]
    if not r.get("found"):
        lines += [r.get("error", "No data."), "",
                  "_Source: Chrome UX Report (real Chrome users, 28-day)._"]
        return "\n".join(lines) + "\n"

    if r["cwv_pass"] is True:
        lines.append("**✅ Passes Core Web Vitals** — LCP, INP, and CLS are all good at p75.")
    elif r["cwv_pass"] is False:
        lines.append("**❌ Does not pass Core Web Vitals** — at least one of LCP/INP/CLS "
                     "is not good at p75.")
    else:
        lines.append("**⚠️ Incomplete Core Web Vitals** — not all of LCP/INP/CLS have "
                     "field data yet.")
    if r["period"]:
        lines.append(f"_Collection period ending {r['period']} · 75th percentile of real users._")
    lines += ["", "| Metric | p75 | Rating |", "|:--|--:|:--|"]
    for row in r["rows"]:
        tag = "" if row["core"] else " *(secondary)*"
        lines.append(f"| {row['metric']}{tag} | {_fmt(row)} | "
                     f"{_RATING_ICON[row['rating']]} {row['rating']} |")
    lines += ["", "_Source: Chrome UX Report API — real Chrome-user field data, not a "
              "lab estimate. Thresholds per web.dev._"]
    return "\n".join(lines).rstrip() + "\n"


def render_json(r: dict) -> str:
    return json.dumps(r, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Real Core Web Vitals field data from the Chrome UX Report (opt-in)")
    ap.add_argument("url", help="page URL (or origin, with --origin)")
    ap.add_argument("--crux-key", default=None,
                    help="CrUX API key. Or set CRUX_API_KEY (env var or a .env "
                         "file). Get one: https://developer.chrome.com/docs/crux/api")
    ap.add_argument("--origin", action="store_true",
                    help="query origin-level data (aggregate across the whole site)")
    ap.add_argument("--form-factor", choices=list(_FORM_FACTORS),
                    help="restrict to phone/desktop/tablet (default: all)")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("-o", "--output")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    # Resolve the key: --crux-key > CRUX_API_KEY env var > .env file.
    from lib import env as envlib  # noqa: PLC0415
    api_key = envlib.resolve("CRUX_API_KEY", args.crux_key)
    if not api_key:
        print("A CrUX API key is required (this is the only feature that calls an "
              "external API).\nProvide it any of these ways:\n"
              "  - pass --crux-key YOUR_KEY\n"
              "  - set the CRUX_API_KEY environment variable (e.g. in your shell profile)\n"
              "  - add CRUX_API_KEY=YOUR_KEY to a .env file (it's gitignored)\n"
              "Get a free key: https://developer.chrome.com/docs/crux/api",
              file=sys.stderr)
        return 2

    r = analyze(args.url, api_key, origin=args.origin,
                form_factor=args.form_factor, timeout=args.timeout)
    out = render_json(r) if args.format == "json" else render_markdown(r)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} vitals to {args.output}")
    else:
        print(out)
    # exit 1 when we have data and it fails CWV — usable as a soft gate
    return 1 if r.get("found") and r.get("cwv_pass") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
