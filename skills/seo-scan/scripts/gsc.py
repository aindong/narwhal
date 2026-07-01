#!/usr/bin/env python3
"""narwhal gsc — real search-query data from Google Search Console (opt-in).

Pulls Search Analytics rows (query, page, clicks, impressions, CTR, position)
for a property you own and turns them into prioritized opportunities:

  - **Striking distance** — queries at positions 8-20 with real impressions:
    the "push to page 1" list.
  - **CTR laggards** — top-10 positions whose CTR is far below the expected
    curve for that position: title/meta rewrite candidates.
  - **Decaying pages** — clicks down sharply vs the previous period.
  - **Cannibalization** — several of your pages splitting one query.

Like `vitals`, this is opt-in and calls an external API — everything else in
Narwhal stays local. GSC has **no API-key path**; auth is OAuth, resolved in
this order (env var or .env via lib/env.py, flags win):

  1. GSC_ACCESS_TOKEN                      — direct bearer (e.g. from
     `gcloud auth print-access-token`); expires after ~1 hour.
  2. GSC_CLIENT_ID + GSC_CLIENT_SECRET + GSC_REFRESH_TOKEN — durable; we mint
     an access token per run with one POST to Google's token endpoint.
  3. `narwhal gsc --auth`                  — one-time browser consent flow that
     obtains that refresh token (create a **Desktop** OAuth client first).

Only fixed Google hosts are contacted (googleapis.com / accounts.google.com);
your site URL is payload, never the connection target — no SSRF surface.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from urllib.parse import quote, urlencode, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
SITES_ENDPOINT = "https://www.googleapis.com/webmasters/v3/sites"
QUERY_ENDPOINT = ("https://www.googleapis.com/webmasters/v3/sites/"
                  "{prop}/searchAnalytics/query")

# Selection rules (documented in the report; deliberately few knobs).
POS_MIN, POS_MAX = 8.0, 20.0     # "striking distance" window
DECAY_PCT = 25                   # clicks drop % that counts as decaying
DECAY_CLICK_FLOOR = 10           # ignore pages with fewer prior-period clicks
CANN_SHARE = 0.20                # min impression share to count as competing
GSC_LAG_DAYS = 2                 # GSC data lags ~2 days behind today

# Rough organic CTR by position — a *heuristic* curve used only to rank
# rewrite candidates, never reported as a measurement.
_EXPECTED_CTR = {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05,
                 6: 0.04, 7: 0.032, 8: 0.027, 9: 0.023, 10: 0.02}


def expected_ctr(position: float) -> float:
    """Heuristic expected CTR for a SERP position (clamped to 1..10)."""
    return _EXPECTED_CTR[max(1, min(10, int(round(position))))]


# ---------------------------------------------------------------- analysis

def _by_page(rows: list) -> dict:
    """Aggregate query+page rows per page: clicks, impressions, weighted pos."""
    pages: dict = {}
    for r in rows:
        page = r["keys"][0]
        agg = pages.setdefault(page, {"clicks": 0, "impressions": 0, "_pw": 0.0})
        agg["clicks"] += r["clicks"]
        agg["impressions"] += r["impressions"]
        agg["_pw"] += r["position"] * r["impressions"]
    for agg in pages.values():
        agg["position"] = (agg.pop("_pw") / agg["impressions"]) if agg["impressions"] else 0.0
    return pages


def _totals(rows: list) -> dict:
    clicks = sum(r["clicks"] for r in rows)
    impressions = sum(r["impressions"] for r in rows)
    pw = sum(r["position"] * r["impressions"] for r in rows)
    return {"clicks": clicks, "impressions": impressions,
            "ctr": (clicks / impressions) if impressions else 0.0,
            "position": (pw / impressions) if impressions else 0.0}


def analyze(rows_now: list, rows_prev: list, *,
            min_impressions: int = 50, top: int = 15) -> dict:
    """Turn two periods of Search Analytics rows into opportunities.

    Rows carry ``keys=[page, query]`` plus clicks/impressions/ctr/position.
    Pure and offline-testable; every number comes from the rows."""
    now, prev = _totals(rows_now), _totals(rows_prev)
    summary = {**now, "clicks_prev": prev["clicks"],
               "impressions_prev": prev["impressions"],
               "ctr_prev": prev["ctr"], "position_prev": prev["position"]}

    striking = sorted(
        ({"page": r["keys"][0], "query": r["keys"][1], "clicks": r["clicks"],
          "impressions": r["impressions"], "position": round(r["position"], 1)}
         for r in rows_now
         if POS_MIN <= r["position"] <= POS_MAX
         and r["impressions"] >= min_impressions),
        key=lambda s: -s["impressions"])[:top]

    pages_now, pages_prev = _by_page(rows_now), _by_page(rows_prev)

    laggards = sorted(
        ({"page": page, "position": round(agg["position"], 1),
          "ctr": agg["clicks"] / agg["impressions"],
          "expected_ctr": expected_ctr(agg["position"]),
          "clicks": agg["clicks"], "impressions": agg["impressions"]}
         for page, agg in pages_now.items()
         if agg["impressions"] >= min_impressions and agg["position"] <= 10
         and agg["clicks"] / agg["impressions"] < expected_ctr(agg["position"]) / 2),
        key=lambda e: -e["impressions"])[:top]

    decaying = sorted(
        ({"page": page,
          "clicks_prev": prev_agg["clicks"],
          "clicks_now": pages_now.get(page, {}).get("clicks", 0),
          "drop_pct": round(100 * (1 - pages_now.get(page, {}).get("clicks", 0)
                                   / prev_agg["clicks"]))}
         for page, prev_agg in pages_prev.items()
         if prev_agg["clicks"] >= DECAY_CLICK_FLOOR
         and pages_now.get(page, {}).get("clicks", 0)
         <= prev_agg["clicks"] * (1 - DECAY_PCT / 100)),
        key=lambda e: e["clicks_now"] - e["clicks_prev"])[:top]

    by_query: dict = {}
    for r in rows_now:
        by_query.setdefault(r["keys"][1], []).append(r)
    cannibalization = []
    for query, qrows in by_query.items():
        q_impr = sum(r["impressions"] for r in qrows)
        if q_impr < min_impressions:
            continue
        competing = [
            {"page": r["keys"][0], "share": round(r["impressions"] / q_impr, 2),
             "clicks": r["clicks"], "impressions": r["impressions"],
             "position": round(r["position"], 1)}
            for r in qrows if r["impressions"] / q_impr >= CANN_SHARE]
        if len(competing) >= 2:
            cannibalization.append(
                {"query": query, "impressions": q_impr,
                 "pages": sorted(competing, key=lambda p: -p["impressions"])})
    cannibalization.sort(key=lambda c: -c["impressions"])

    return {"summary": summary, "striking": striking, "laggards": laggards,
            "decaying": decaying, "cannibalization": cannibalization[:top]}


def pick_property(sites: list, target: str) -> str | None:
    """Choose the GSC property that covers ``target``.

    Longest matching URL-prefix property wins; else a ``sc-domain:`` property
    whose registrable domain matches the target host (www-insensitive)."""
    target_norm = target if target.endswith("/") else target + "/"
    host = (urlparse(target).hostname or "").lower()
    prefixes = [s["siteUrl"] for s in sites
                if not s["siteUrl"].startswith("sc-domain:")
                and target_norm.startswith(s["siteUrl"])]
    if prefixes:
        return max(prefixes, key=len)
    for s in sites:
        if s["siteUrl"].startswith("sc-domain:"):
            domain = s["siteUrl"][len("sc-domain:"):].lower()
            if host == domain or host.endswith("." + domain):
                return s["siteUrl"]
    return None


# ---------------------------------------------------------------- network

def _http_json(url, *, token=None, body=None, form=None, timeout=30) -> tuple:
    """One JSON request to a fixed Google host. -> (status, json|None, err|None)"""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    headers = {"User-Agent": "narwhal-gsc"}
    data = None
    if form is not None:
        data = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, json.loads(fh.read().decode()), None
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode())
            detail = (payload.get("error", {}) or {}).get("message", "") \
                if isinstance(payload.get("error"), dict) \
                else payload.get("error_description", payload.get("error", ""))
        except Exception:  # noqa: BLE001
            pass
        return exc.code, None, detail or str(exc.reason)
    except Exception as exc:  # noqa: BLE001
        return 0, None, str(exc)


def resolve_token(access_token=None, *, timeout=30) -> tuple:
    """Auth ladder -> (bearer_token|None, error|None)."""
    from lib import env as envlib  # noqa: PLC0415

    token = envlib.resolve("GSC_ACCESS_TOKEN", access_token)
    if token:
        return token, None
    cid = envlib.resolve("GSC_CLIENT_ID")
    secret = envlib.resolve("GSC_CLIENT_SECRET")
    refresh = envlib.resolve("GSC_REFRESH_TOKEN")
    if cid and secret and refresh:
        status, payload, err = _http_json(TOKEN_ENDPOINT, form={
            "client_id": cid, "client_secret": secret,
            "refresh_token": refresh, "grant_type": "refresh_token"},
            timeout=timeout)
        if payload and payload.get("access_token"):
            return payload["access_token"], None
        return None, f"refresh-token exchange failed (HTTP {status}): {err}"
    return None, None   # no credentials at all


def fetch(target: str, token: str, *, days=28, timeout=30) -> dict:
    """Resolve the property and pull current + previous period rows."""
    status, payload, err = _http_json(SITES_ENDPOINT, token=token, timeout=timeout)
    if payload is None:
        return {"found": False,
                "error": f"could not list GSC properties (HTTP {status}): {err}"}
    sites = payload.get("siteEntry", [])
    prop = pick_property(sites, target)
    if not prop:
        have = ", ".join(s["siteUrl"] for s in sites) or "none"
        return {"found": False,
                "error": f"no GSC property matches {target}. "
                         f"This account can see: {have}."}

    end = _dt.date.today() - _dt.timedelta(days=GSC_LAG_DAYS)
    start = end - _dt.timedelta(days=days - 1)
    prev_end = start - _dt.timedelta(days=1)
    prev_start = prev_end - _dt.timedelta(days=days - 1)

    def rows(d1, d2):
        st, pl, e = _http_json(
            QUERY_ENDPOINT.format(prop=quote(prop, safe="")), token=token,
            body={"startDate": d1.isoformat(), "endDate": d2.isoformat(),
                  "dimensions": ["page", "query"], "rowLimit": 25000,
                  "type": "web"},
            timeout=timeout)
        if pl is None:
            raise RuntimeError(f"searchAnalytics query failed (HTTP {st}): {e}")
        return pl.get("rows", [])

    try:
        rows_now, rows_prev = rows(start, end), rows(prev_start, prev_end)
    except RuntimeError as exc:
        return {"found": False, "error": str(exc)}
    return {"found": True, "property": prop, "days": days,
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "rows_now": rows_now, "rows_prev": rows_prev}


def gather(target: str, *, days=28, timeout=30, min_impressions=50) -> dict:
    """Creds-gated one-call entry point for the audit (mirrors gather_vitals)."""
    token, err = resolve_token(timeout=timeout)
    if not token:
        return {"found": False, "error": err or (
            "No GSC credentials — set GSC_ACCESS_TOKEN, or the GSC_CLIENT_ID/"
            "GSC_CLIENT_SECRET/GSC_REFRESH_TOKEN trio (one-time: `narwhal gsc --auth`).")}
    r = fetch(target, token, days=days, timeout=timeout)
    if not r.get("found"):
        return r
    return {"found": True, "property": r["property"], "days": days,
            "window": r["window"],
            **analyze(r["rows_now"], r["rows_prev"],
                      min_impressions=min_impressions)}


# ---------------------------------------------------------------- one-time auth

def run_auth(client_id: str, client_secret: str, *, timeout=300,
             write_env=False) -> int:
    """One-time loopback OAuth consent flow -> prints (or stores) the refresh
    token. Listens only on 127.0.0.1; contacts only Google's fixed hosts."""
    import http.server  # noqa: PLC0415
    import webbrowser  # noqa: PLC0415

    captured: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            from urllib.parse import parse_qs, urlparse as up  # noqa: PLC0415
            captured.update({k: v[0] for k, v in
                             parse_qs(up(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Narwhal: authorization received."
                             b" You can close this tab.</h2>")

        def log_message(self, *a):  # silence request logging
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = timeout
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = AUTH_ENDPOINT + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect,
        "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent"})
    print("Open this URL to authorize read-only Search Console access:\n\n  "
          + url + "\n\nWaiting for the browser redirect …")
    webbrowser.open(url)
    server.handle_request()
    server.server_close()

    code = captured.get("code")
    if not code:
        print(f"Authorization failed: {captured.get('error', 'no code received')}",
              file=sys.stderr)
        return 2
    status, payload, err = _http_json(TOKEN_ENDPOINT, form={
        "client_id": client_id, "client_secret": client_secret, "code": code,
        "redirect_uri": redirect, "grant_type": "authorization_code"})
    refresh = (payload or {}).get("refresh_token")
    if not refresh:
        print(f"Token exchange failed (HTTP {status}): {err}", file=sys.stderr)
        return 2

    lines = [f"GSC_CLIENT_ID={client_id}", f"GSC_CLIENT_SECRET={client_secret}",
             f"GSC_REFRESH_TOKEN={refresh}"]
    if write_env:
        with open(".env", "a", encoding="utf-8") as fh:
            fh.write("\n# narwhal gsc (Search Console, read-only)\n"
                     + "\n".join(lines) + "\n")
        print("Stored GSC credentials in ./.env — you're set. "
              "Try: narwhal gsc <your-site>")
    else:
        print("Success. Add these to your .env (or re-run with --write-env):\n\n"
              + "\n".join(lines))
    return 0


# ---------------------------------------------------------------- rendering

def _pct(new: float, old: float) -> str:
    if not old:
        return ""
    d = round(100 * (new - old) / old)
    return f" ({'+' if d >= 0 else ''}{d}% vs prior)"


def render_markdown(r: dict, target: str) -> str:
    lines = [f"# Search performance (GSC) — {target}", ""]
    if not r.get("found"):
        lines += [r.get("error", "No data."), "",
                  "_Setup: create a Desktop OAuth client, then run "
                  "`narwhal gsc --auth` once (read-only scope)._"]
        return "\n".join(lines) + "\n"

    s = r["summary"]
    w = r.get("window", {})
    period = f"{w.get('start')} → {w.get('end')}" if w else f"last {r.get('days', '?')} days"
    lines += [
        f"**Property:** `{r.get('property', '?')}` · **Window:** {period}",
        "",
        f"**Clicks:** {s['clicks']}{_pct(s['clicks'], s['clicks_prev'])} · "
        f"**Impressions:** {s['impressions']}"
        f"{_pct(s['impressions'], s['impressions_prev'])} · "
        f"**CTR:** {s['ctr'] * 100:.1f}% · "
        f"**Avg position:** {s['position']:.1f}",
        "",
    ]

    def section(title, rows_, header, fmt, empty):
        lines.extend([f"## {title}", ""])
        if not rows_:
            lines.extend([empty, ""])
            return
        lines.extend(header)
        lines.extend(fmt(x) for x in rows_)
        lines.append("")

    section(
        f"Striking distance (positions {POS_MIN:.0f}–{POS_MAX:.0f})",
        r["striking"],
        ["| Query | Page | Pos | Impressions | Clicks |", "|:--|:--|--:|--:|--:|"],
        lambda x: f"| {x['query']} | {x['page']} | {x['position']} "
                  f"| {x['impressions']} | {x['clicks']} |",
        "Nothing in striking distance with meaningful impressions.")
    section(
        "CTR laggards — title/meta rewrite candidates",
        r["laggards"],
        ["| Page | Pos | CTR | Expected* | Impressions |", "|:--|--:|--:|--:|--:|"],
        lambda x: f"| {x['page']} | {x['position']} | {x['ctr'] * 100:.1f}% "
                  f"| ~{x['expected_ctr'] * 100:.0f}% | {x['impressions']} |",
        "No top-10 pages with unusually low CTR.")
    lines += ["*Expected CTR is a **heuristic** position curve, used only to "
              "rank rewrite candidates — not a measurement.", ""]
    section(
        f"Decaying pages (clicks down ≥{DECAY_PCT}% vs prior period)",
        r["decaying"],
        ["| Page | Clicks before | Clicks now | Drop |", "|:--|--:|--:|--:|"],
        lambda x: f"| {x['page']} | {x['clicks_prev']} | {x['clicks_now']} "
                  f"| -{x['drop_pct']}% |",
        "No pages decaying beyond the threshold.")
    section(
        "Possible keyword cannibalization",
        r["cannibalization"],
        ["| Query | Impressions | Competing pages |", "|:--|--:|:--|"],
        lambda x: f"| {x['query']} | {x['impressions']} | "
                  + " · ".join(f"{p['page']} (pos {p['position']}, "
                               f"{p['share'] * 100:.0f}%)" for p in x["pages"]) + " |",
        "No queries with several pages competing.")
    lines += ["_Cross-check cannibalization against the audit's near-duplicate "
              "clusters — consolidating or canonicalizing usually fixes both._",
              "",
              "_Source: Google Search Console Search Analytics API (real search "
              "data for your verified property)._"]
    return "\n".join(lines).rstrip() + "\n"


def render_json(r: dict) -> str:
    return json.dumps(r, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Search Console query data → prioritized SEO opportunities "
                    "(opt-in; needs OAuth — see --auth)")
    ap.add_argument("url", nargs="?", help="site or page URL (its GSC property "
                                           "is auto-resolved)")
    ap.add_argument("--auth", action="store_true",
                    help="one-time browser flow to obtain a refresh token "
                         "(needs GSC_CLIENT_ID/GSC_CLIENT_SECRET of a Desktop "
                         "OAuth client)")
    ap.add_argument("--write-env", action="store_true",
                    help="with --auth: append the credentials to ./.env")
    ap.add_argument("--access-token", default=None,
                    help="bearer token (or set GSC_ACCESS_TOKEN / the "
                         "GSC_REFRESH_TOKEN trio via env or .env)")
    ap.add_argument("--days", type=int, default=28,
                    help="window length; compared against the previous window "
                         "(default 28)")
    ap.add_argument("--min-impressions", type=int, default=50,
                    help="ignore queries/pages below this many impressions "
                         "(default 50)")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("-o", "--output")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    from lib import env as envlib  # noqa: PLC0415

    if args.auth:
        cid = envlib.resolve("GSC_CLIENT_ID")
        secret = envlib.resolve("GSC_CLIENT_SECRET")
        if not (cid and secret):
            print("--auth needs an OAuth client first (one-time, ~2 min):\n"
                  "  1. console.cloud.google.com → APIs & Services → enable "
                  "'Google Search Console API'\n"
                  "  2. Credentials → Create credentials → OAuth client ID → "
                  "type **Desktop app**\n"
                  "  3. put GSC_CLIENT_ID=… and GSC_CLIENT_SECRET=… in your "
                  ".env, then re-run `narwhal gsc --auth`", file=sys.stderr)
            return 2
        return run_auth(cid, secret, write_env=args.write_env)

    if not args.url:
        print("Usage: narwhal gsc <url>   (or: narwhal gsc --auth)", file=sys.stderr)
        return 2

    token, err = resolve_token(args.access_token, timeout=args.timeout)
    if not token:
        print(err or
              "Google Search Console needs OAuth credentials (no API-key path "
              "exists). Provide either:\n"
              "  - GSC_ACCESS_TOKEN — a bearer token, e.g. from "
              "`gcloud auth print-access-token` (expires ~1h), or\n"
              "  - GSC_CLIENT_ID + GSC_CLIENT_SECRET + GSC_REFRESH_TOKEN — "
              "durable; get the refresh token once with `narwhal gsc --auth`.\n"
              "All are read from the environment or a .env file (gitignored).",
              file=sys.stderr)
        return 2

    r = fetch(args.url, token, days=args.days, timeout=args.timeout)
    if r.get("found"):
        r = {"found": True, "property": r["property"], "days": r["days"],
             "window": r["window"],
             **analyze(r["rows_now"], r["rows_prev"],
                       min_impressions=args.min_impressions)}
    out = render_json(r) if args.format == "json" else render_markdown(r, args.url)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.format} GSC report to {args.output}")
    else:
        print(out)
    return 0 if r.get("found") else 1


if __name__ == "__main__":
    raise SystemExit(main())
