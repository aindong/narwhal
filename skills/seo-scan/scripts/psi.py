#!/usr/bin/env python3
"""PageSpeed Insights (Lighthouse) lab data — the companion to CrUX field data.

CrUX (`crux.py`) reports what *real users* experienced, but only for pages with
enough traffic. When CrUX has no data (most pages), PageSpeed Insights runs a
**Lighthouse lab test** — a synthetic single run in a controlled environment — for
**any** URL. This module fetches and formats that.

Lab vs field, kept honest: lab data is an *estimate* from one controlled run, not
real-user experience. It's great for catching regressions and comparing changes,
but it isn't the same thing as CrUX. Lab has no INP (a field-only metric); its
proxy is **Total Blocking Time (TBT)**.

Used via ``narwhal vitals <url> --lab``. The PSI API key is *optional* (it runs
keyless at a low quota); a key raises the quota. One Google Cloud key can serve
both CrUX and PSI if you enable both APIs on it.
"""

from __future__ import annotations

import json
import sys
from urllib.parse import urlencode

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Lighthouse audit id -> (label, unit, good_max, needs_improvement_max).
# Thresholds per web.dev / Lighthouse scoring (mobile). numericValue is ms for
# timings, unitless for CLS.
LAB_METRICS = [
    ("largest-contentful-paint", "LCP", "ms", 2500, 4000),
    ("total-blocking-time", "TBT", "ms", 200, 600),   # lab proxy for INP
    ("cumulative-layout-shift", "CLS", "", 0.1, 0.25),
    ("first-contentful-paint", "FCP", "ms", 1800, 3000),
    ("speed-index", "SI", "ms", 3400, 5800),
    ("interactive", "TTI", "ms", 3800, 7300),
]
_CORE = {"largest-contentful-paint", "total-blocking-time", "cumulative-layout-shift"}
_RATING_ICON = {"good": "🟢", "needs-improvement": "🟡", "poor": "🔴"}
_STRATEGIES = ("mobile", "desktop")


def rate(good_max, ni_max, value) -> str:
    if value <= good_max:
        return "good"
    if value <= ni_max:
        return "needs-improvement"
    return "poor"


def rate_score(score100) -> str:
    # Lighthouse colour bands: >=90 green, 50-89 orange, <50 red.
    if score100 >= 90:
        return "good"
    if score100 >= 50:
        return "needs-improvement"
    return "poor"


def _query(url, api_key, *, strategy, timeout) -> tuple:
    """GET the PSI API. Returns (status, json_or_None, error_or_None). Only ever
    contacts Google's fixed PSI host, so there's no SSRF surface."""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    params = {"url": url, "strategy": strategy, "category": "performance"}
    if api_key:
        params["key"] = api_key
    req = urllib.request.Request(
        f"{PSI_ENDPOINT}?{urlencode(params)}",
        headers={"User-Agent": "narwhal-psi"})
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


def parse_lighthouse(lhr: dict) -> dict:
    """Extract the perf score + lab metrics from a lighthouseResult (pure)."""
    audits = lhr.get("audits", {})
    score_raw = lhr.get("categories", {}).get("performance", {}).get("score")
    perf = round(score_raw * 100) if isinstance(score_raw, (int, float)) else None
    rows = []
    for aid, label, unit, good, ni in LAB_METRICS:
        a = audits.get(aid)
        if not a or a.get("numericValue") is None:
            continue
        val = float(a["numericValue"])
        rows.append({"metric": label, "id": aid, "unit": unit, "value": val,
                     "display": a.get("displayValue") or _fmt(val, unit),
                     "rating": rate(good, ni, val),
                     "core": aid in _CORE})
    return {"perf_score": perf,
            "perf_rating": rate_score(perf) if perf is not None else None,
            "rows": rows,
            "lighthouse_version": lhr.get("lighthouseVersion", "")}


def analyze(url, api_key=None, *, strategy="mobile", timeout=60) -> dict:
    status, payload, error = _query(url, api_key, strategy=strategy, timeout=timeout)
    if payload is None:
        return {"found": False, "url": url, "strategy": strategy,
                "error": error or f"PageSpeed Insights request failed (HTTP {status})."}
    lhr = payload.get("lighthouseResult", {})
    if not lhr:
        return {"found": False, "url": url, "strategy": strategy,
                "error": "PageSpeed Insights returned no Lighthouse result."}
    return {"found": True, "url": url, "strategy": strategy, **parse_lighthouse(lhr)}


def _fmt(value, unit) -> str:
    if unit == "":
        return f"{value:.2f}"
    if value >= 1000:
        return f"{value / 1000:.1f} s"
    return f"{int(round(value))} ms"


def render_markdown(r: dict) -> str:
    lines = [f"# PageSpeed Insights (lab) — {r['url']}  ·  {r['strategy']}", ""]
    if not r.get("found"):
        err = r.get("error", "No data.")
        lines.append(err)
        if "quota" in err.lower() or "key" in err.lower():
            lines += ["",
                      "The keyless PSI quota is shared and often exhausted. Add your "
                      "own key: set `PAGESPEED_API_KEY` (or reuse `CRUX_API_KEY` with "
                      "the *PageSpeed Insights API* enabled on that Google Cloud "
                      "project). Get one: https://developers.google.com/speed/docs/insights/v5/get-started"]
        lines += ["", "_Lab data comes from a synthetic Lighthouse run._"]
        return "\n".join(lines) + "\n"

    if r["perf_score"] is not None:
        lines.append(f"**Performance score: {r['perf_score']}/100 "
                     f"({_RATING_ICON[r['perf_rating']]} {r['perf_rating']})** — "
                     f"Lighthouse lab, {r['strategy']}")
    lines += ["", "| Metric | Value | Rating |", "|:--|--:|:--|"]
    for row in r["rows"]:
        tag = "" if row["core"] else " *(secondary)*"
        lines.append(f"| {row['metric']}{tag} | {row['display']} | "
                     f"{_RATING_ICON[row['rating']]} {row['rating']} |")
    lines += ["", "_Lab data: a synthetic single run in a controlled environment — an "
              "estimate for catching regressions, **not** real-user field data. Lab "
              "has no INP (TBT is its proxy). For real-user Core Web Vitals use "
              "`narwhal vitals` (CrUX) when the page has enough traffic._"]
    return "\n".join(lines).rstrip() + "\n"


def render_json(r: dict) -> str:
    return json.dumps(r, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    # Thin CLI so `python psi.py <url>` works standalone; `narwhal vitals --lab`
    # is the main entry point.
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(description="PageSpeed Insights (Lighthouse) lab data")
    ap.add_argument("url")
    ap.add_argument("--psi-key", default=None)
    ap.add_argument("--strategy", choices=_STRATEGIES, default="mobile")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("-o", "--output")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    r = analyze(args.url, args.psi_key, strategy=args.strategy, timeout=args.timeout)
    out = render_json(r) if args.format == "json" else render_markdown(r)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} PSI report to {args.output}")
    else:
        print(out)
    return 1 if r.get("found") and (r.get("perf_rating") == "poor") else 0


if __name__ == "__main__":
    raise SystemExit(main())
