"""SSRF-safe HTTP fetching with graceful dependency degradation.

Prefers ``requests`` when installed; falls back to ``urllib`` from the stdlib so
the scanner runs on a bare Python install. Optionally renders JavaScript-heavy
pages with Playwright when it is available and the caller asks for it.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urlunparse

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; seo-scan/1.0; +local-audit) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 20


@dataclass
class Response:
    url: str
    final_url: str
    status: int
    headers: dict
    text: str
    elapsed_ms: int
    rendered: bool = False
    redirects: list = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 400


class SSRFError(ValueError):
    """Raised when a URL resolves to a blocked (private/loopback) address."""


def normalize_url(url: str) -> str:
    if "://" not in url:
        url = "https://" + url
    parts = urlparse(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {scheme!r}")
    netloc = parts.netloc or parts.path
    path = parts.path if parts.netloc else ""
    return urlunparse((scheme, netloc, path or "/", parts.params, parts.query, ""))


def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_public_host(url: str, allow_private: bool = False) -> None:
    """Guard against SSRF by resolving the host and rejecting private ranges."""
    if allow_private:
        return
    host = urlparse(url).hostname
    if not host:
        raise SSRFError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFError(f"Cannot resolve host {host!r}: {exc}") from exc
    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            raise SSRFError(f"Host {host!r} resolves to blocked address {ip}")


def fetch(
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_UA,
    render: bool = False,
    allow_private: bool = False,
    max_bytes: int = 5_000_000,
) -> Response:
    """Fetch ``url`` and return a :class:`Response`.

    Set ``render=True`` to run the page through Playwright (if installed) so
    client-rendered DOMs are captured. Errors are returned on the Response
    rather than raised, so a single failing page never aborts a scan.
    """
    url = normalize_url(url)
    assert_public_host(url, allow_private=allow_private)

    if render:
        rendered = _try_render(url, timeout=timeout, user_agent=user_agent)
        if rendered is not None:
            return rendered

    start = time.time()
    try:
        resp = _fetch_requests(url, timeout, user_agent, max_bytes)
    except ImportError:
        resp = _fetch_urllib(url, timeout, user_agent, max_bytes)
    resp.elapsed_ms = int((time.time() - start) * 1000)
    return resp


def _fetch_requests(url, timeout, user_agent, max_bytes) -> Response:
    import requests  # noqa: PLC0415

    r = requests.get(
        url,
        headers={"User-Agent": user_agent, "Accept": "text/html,*/*"},
        timeout=timeout,
        allow_redirects=True,
    )
    text = r.text
    if len(r.content) > max_bytes:
        text = r.content[:max_bytes].decode(r.encoding or "utf-8", "replace")
    redirects = [h.url for h in r.history]
    return Response(
        url=url,
        final_url=r.url,
        status=r.status_code,
        headers={k.lower(): v for k, v in r.headers.items()},
        text=text,
        elapsed_ms=0,
        redirects=redirects,
    )


def _fetch_urllib(url, timeout, user_agent, max_bytes) -> Response:
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            raw = fh.read(max_bytes)
            charset = fh.headers.get_content_charset() or "utf-8"
            return Response(
                url=url,
                final_url=fh.geturl(),
                status=fh.status,
                headers={k.lower(): v for k, v in fh.headers.items()},
                text=raw.decode(charset, "replace"),
                elapsed_ms=0,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(max_bytes).decode("utf-8", "replace") if exc.fp else ""
        return Response(
            url=url,
            final_url=url,
            status=exc.code,
            headers={k.lower(): v for k, v in (exc.headers or {}).items()},
            text=body,
            elapsed_ms=0,
        )
    except Exception as exc:  # noqa: BLE001
        return Response(url, url, 0, {}, "", 0, error=str(exc))


def _try_render(url, timeout, user_agent) -> Optional[Response]:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        return None
    start = time.time()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=user_agent)
            resp = page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            html = page.content()
            status = resp.status if resp else 0
            headers = {k.lower(): v for k, v in (resp.headers if resp else {}).items()}
            final_url = page.url
            browser.close()
        return Response(
            url=url,
            final_url=final_url,
            status=status,
            headers=headers,
            text=html,
            elapsed_ms=int((time.time() - start) * 1000),
            rendered=True,
        )
    except Exception as exc:  # noqa: BLE001
        return Response(url, url, 0, {}, "", 0, rendered=True, error=str(exc))


def fetch_text(url: str, **kwargs) -> Optional[str]:
    """Fetch a plain-text resource (robots.txt, llms.txt, sitemap) or None."""
    resp = fetch(url, **kwargs)
    return resp.text if resp.ok else None


def head(url: str, *, timeout: int = DEFAULT_TIMEOUT, user_agent: str = DEFAULT_UA,
         allow_private: bool = False):
    """Check a URL's reachability cheaply. Returns ``(status, error)``.

    Uses HEAD (falling back to GET when a server rejects it) and follows
    redirects. ``status == 0`` means unreachable (DNS/timeout/SSRF-blocked); the
    error string carries the reason. Never raises — safe for bulk link checking.
    """
    try:
        url = normalize_url(url)
    except ValueError as exc:
        return 0, str(exc)
    try:
        assert_public_host(url, allow_private=allow_private)
    except SSRFError as exc:
        return 0, str(exc)
    try:
        return _head_requests(url, timeout, user_agent)
    except ImportError:
        return _head_urllib(url, timeout, user_agent)


def _head_requests(url, timeout, user_agent):
    import requests  # noqa: PLC0415

    headers = {"User-Agent": user_agent}
    try:
        r = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code in (403, 405, 501):  # some servers refuse HEAD
            r = requests.get(url, headers=headers, timeout=timeout,
                             allow_redirects=True, stream=True)
            r.close()
        return r.status_code, None
    except requests.RequestException as exc:
        return 0, type(exc).__name__


def _head_urllib(url, timeout, user_agent):
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    def _try(method):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent},
                                     method=method)
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return fh.status, None

    try:
        return _try("HEAD")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            try:
                return _try("GET")
            except Exception:  # noqa: BLE001
                return exc.code, None
        return exc.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, type(exc).__name__
