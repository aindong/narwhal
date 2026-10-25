"""SSRF-safe HTTP fetching with graceful dependency degradation.

Prefers ``requests`` when installed; falls back to ``urllib`` from the stdlib so
the scanner runs on a bare Python install. Optionally renders JavaScript-heavy
pages with Playwright when it is available and the caller asks for it.
"""

from __future__ import annotations

import ipaddress
import gzip
import io
import socket
import time
import zlib
from dataclasses import dataclass, field, replace
from typing import Optional
from urllib.parse import urlparse, urlunparse
from urllib.parse import urljoin

from .budgets import nonnegative_integer, positive_integer

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; seo-scan/1.0; +local-audit) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 20
MAX_REDIRECTS = 10
SERVER_RANGE_BASIS = 'http_206_or_content_range_v1'
PARTIAL_RESOURCE_ERROR = 'Partial/ranged HTTP response; complete resource bytes are unverified.'


def _range_evidence(status, headers):
    """Shared membership rule for normalized and transport-native headers."""
    return status == 206 or 'content-range' in headers


def has_range_evidence(response):
    """Recognize range evidence, not validate its syntax or complete coverage.

    A full byte range or a malformed Content-Range still needs verification;
    neither is silently promoted to a complete standalone representation.
    """
    return _range_evidence(response.status, response.headers)


def _origin_headers(headers):
    """Normalize origin headers without trusting our internal coverage marker."""
    return {key.lower(): value for key, value in headers.items()
            if key.lower() != "x-narwhal-truncated"}


def _robots_header_fields(headers):
    """Capture just robots fields through a duplicate-preserving header API."""
    for name in ('getlist', 'get_all'):
        getter = getattr(headers, name, None)
        if callable(getter):
            values = getter('X-Robots-Tag')
            if values is None:
                return []
            if isinstance(values, (list, tuple)) and all(isinstance(value, str) for value in values):
                return list(values)
    return None


class _ResponseDecodeError(ValueError):
    """A remote charset is unknown or is not a text encoding."""


def _decode_html(raw, encoding):
    """Decode a declared charset without guessing; bound invalid-name diagnostics."""
    try:
        return raw.decode(encoding, "replace")
    except LookupError as exc:
        label = ascii(encoding[:80])
        clipped = len(encoding) > 80 or len(label) > 100
        label = label[:100] + ("…" if clipped else "")
        raise _ResponseDecodeError(
            "Unsupported HTTP charset " + label
            + "; set a supported text encoding in Content-Type.") from exc


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
    robots_header_fields: Optional[list] = None
    robots_header_basis: str = 'merged_or_unknown'

    @property
    def ok(self) -> bool:
        """Transport success, not complete HTML, indexability or page-health proof.

        Redirects are followed by the transports. A terminal 3xx (including a
        304 without a cached representation) is not a successful resource body.
        Partial/empty 2xx coverage still needs each consumer's evidence checks.
        """
        return self.error is None and 200 <= self.status < 300


class URLInputError(ValueError):
    """Expected URL syntax or host-policy rejection, not a programming failure."""


class SSRFError(URLInputError):
    """Raised when a URL resolves to a blocked (private/loopback) address."""


def normalize_url(url: str) -> str:
    if "://" not in url:
        url = "https://" + url
    try:
        parts = urlparse(url)
    except ValueError as exc:
        # Parser errors can echo the entire authority, including credentials.
        raise URLInputError("Invalid URL syntax (check host and IPv6 brackets).") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise URLInputError(f"Unsupported URL scheme: {scheme!r}")
    try:
        host = parts.hostname
        parts.port  # validate lazy port parsing before selecting a transport
    except ValueError as exc:
        raise URLInputError("Invalid URL host or port (port must be numeric and 0–65535).") from exc
    if not host:
        raise SSRFError("URL has no host")
    netloc = parts.netloc or parts.path
    path = parts.path if parts.netloc else ""
    return urlunparse((scheme, netloc, path or "/", parts.params, parts.query, ""))


def _is_blocked_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    # is_private misses shared IPv4 space and deprecated IPv6 site-local ranges.
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
        or not addr.is_global
        or (addr.version == 6 and addr.is_site_local)
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
    except UnicodeError as exc:
        raise URLInputError(f"Invalid host encoding: {exc}") from exc
    if not infos:
        raise SSRFError(f"Cannot resolve host {host!r}: no addresses returned")
    for info in infos:
        ip = info[4][0]
        if _is_blocked_ip(ip):
            raise SSRFError(f"Host {host!r} resolves to blocked address {ip}")


def _redirect_target(current_url: str, location: str, *, allow_private=False) -> str:
    """Resolve and validate one redirect hop before any request is made to it."""
    target = normalize_url(urljoin(current_url, location))
    assert_public_host(target, allow_private=allow_private)
    return target


def _declared_length_exceeds(value, size):
    """Compare an ASCII Content-Length without unbounded integer conversion."""
    value = str(value or '').strip()
    if not value or any(char < '0' or char > '9' for char in value):
        return False
    value = value.lstrip('0') or '0'
    actual = str(size)
    return (len(value), value) > (len(actual), actual)


def _limited_content(response, max_bytes: int) -> tuple:
    """Read at most ``max_bytes`` from a streaming requests response."""
    chunks, size, truncated = [], 0, False
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        remaining = max_bytes - size
        if remaining <= 0:
            truncated = True
            break
        chunks.append(chunk[:remaining])
        size += min(len(chunk), remaining)
        if len(chunk) > remaining:
            truncated = True
            break
        if size >= max_bytes:
            length = response.headers.get("content-length")
            if _declared_length_exceeds(length, max_bytes):
                truncated = True
                break
            # With no trustworthy length, consume at most the next yielded chunk
            # to distinguish an exactly-max-sized body from a larger one.
            continue
    return b"".join(chunks), truncated


def _requests_safe(requests, method: str, url: str, *, timeout: int,
                   headers: dict, allow_private: bool, stream=False):
    """Make a requests call while validating every redirect target."""
    current, redirects = url, []
    for _ in range(MAX_REDIRECTS + 1):
        response = requests.request(method, current, headers=headers, timeout=timeout,
                                    allow_redirects=False, stream=stream)
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            response.close()
            if not location:
                return response, current, redirects
            if len(redirects) >= MAX_REDIRECTS:
                raise requests.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")
            current = _redirect_target(current, location, allow_private=allow_private)
            redirects.append(current)
            continue
        return response, current, redirects
    raise requests.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")


def _urllib_safe_open(url: str, *, timeout: int, headers: dict,
                      allow_private: bool, method="GET"):
    """Open with urllib while validating each redirect before following it."""
    import urllib.error
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    current, redirects = url, []
    while True:
        req = urllib.request.Request(current, headers=headers, method=method)
        try:
            return opener.open(req, timeout=timeout), current, redirects
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308) or not exc.headers.get("Location"):
                # Keep only the guarded request identity, not Content-Location
                # or another origin-supplied claim about where this was fetched.
                exc._narwhal_final_url = current
                exc._narwhal_redirects = tuple(redirects)
                raise
            try:
                if len(redirects) >= MAX_REDIRECTS:
                    raise SSRFError(f"Too many redirects (>{MAX_REDIRECTS})")
                current = _redirect_target(current, exc.headers["Location"],
                                           allow_private=allow_private)
                redirects.append(current)
            finally:
                exc.close()


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
    Invalid budgets raise before I/O. Zero retains no HTML, not zero network use.
    """
    nonnegative_integer(max_bytes, 'Response byte budget')
    url = normalize_url(url)
    assert_public_host(url, allow_private=allow_private)

    if render:
        rendered = _try_render(url, timeout=timeout, user_agent=user_agent,
                               allow_private=allow_private)
        if rendered is not None:
            # Bound the retained UTF-8 DOM snapshot, not Chromium's in-memory
            # DOM or network traffic. Drop an incomplete final code point.
            encoded = rendered.text.encode("utf-8", "replace")
            if len(encoded) > max_bytes:
                headers = {**rendered.headers, "x-narwhal-truncated": "true"}
                rendered = replace(rendered, headers=headers,
                                   text=encoded[:max(0, max_bytes)].decode("utf-8", "ignore"))
            return rendered

    start = time.time()
    try:
        resp = _fetch_requests(url, timeout, user_agent, max_bytes,
                               allow_private=allow_private)
    except ImportError:
        resp = _fetch_urllib(url, timeout, user_agent, max_bytes,
                            allow_private=allow_private)
    resp.elapsed_ms = int((time.time() - start) * 1000)
    return resp


def _fetch_requests(url, timeout, user_agent, max_bytes, allow_private=False) -> Response:
    import requests  # noqa: PLC0415

    try:
        r, current, redirects = _requests_safe(
            requests, "GET", url, timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "text/html,*/*"},
            allow_private=allow_private, stream=True)
    except (requests.RequestException, SSRFError, ValueError) as exc:
        return Response(url, url, 0, {}, "", 0, error=str(exc))
    try:
        raw, truncated = _limited_content(r, max_bytes)
        encoding = r.encoding or "utf-8"
        text = _decode_html(raw, encoding)
        headers = _origin_headers(r.headers)
        robots_fields = _robots_header_fields(getattr(getattr(r, 'raw', None), 'headers', None))
        if truncated:
            headers["x-narwhal-truncated"] = "true"
        return Response(
            url=url,
            final_url=current,
            status=r.status_code,
            headers=headers,
            text=text,
            elapsed_ms=0,
            redirects=redirects,
            robots_header_fields=robots_fields,
            robots_header_basis='response_header_fields' if robots_fields is not None else 'merged_or_unknown',
        )
    except (requests.RequestException, _ResponseDecodeError) as exc:
        # A partial or undecodable body is not usable page evidence.
        return Response(url, current, 0, {}, "", 0, redirects=redirects, error=str(exc))
    finally:
        r.close()


def _fetch_urllib(url, timeout, user_agent, max_bytes, allow_private=False) -> Response:
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    try:
        fh, current, redirects = _urllib_safe_open(
            url, timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "text/html,*/*"},
            allow_private=allow_private)
        with fh:
            raw = fh.read(max_bytes + 1)
            truncated = len(raw) > max_bytes
            raw = raw[:max_bytes]
            headers = _origin_headers(fh.headers)
            robots_fields = _robots_header_fields(fh.headers)
            charset = fh.headers.get_content_charset() or "utf-8"
            status = fh.status
            if truncated:
                headers["x-narwhal-truncated"] = "true"
        return Response(url=url, final_url=current, status=status, headers=headers,
                        text=_decode_html(raw, charset), elapsed_ms=0,
                        redirects=redirects, robots_header_fields=robots_fields,
                        robots_header_basis='response_header_fields' if robots_fields is not None else 'merged_or_unknown')
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(max_bytes + 1) if exc.fp else b""
            headers = _origin_headers(exc.headers or {})
            if len(raw) > max_bytes:
                headers['x-narwhal-truncated'] = 'true'
            return Response(
                url=url,
                final_url=getattr(exc, '_narwhal_final_url', url),
                status=exc.code,
                headers=headers,
                text=raw[:max_bytes].decode("utf-8", "replace"),
                elapsed_ms=0,
                redirects=list(getattr(exc, '_narwhal_redirects', ())),
            )
        finally:
            exc.close()
    except Exception as exc:  # noqa: BLE001
        return Response(url, url, 0, {}, "", 0, error=str(exc))


def _browser_launch_hint(exc) -> str:
    """Turn a Playwright launch/render error into an actionable message.

    The most common failure is Playwright being installed while its Chromium
    binary isn't — the fix is one command, so we say so plainly instead of
    surfacing the raw stack message."""
    msg = str(exc)
    if "Executable doesn't exist" in msg or "playwright install" in msg:
        return ("Playwright is installed but its Chromium browser isn't. "
                "Run: python -m playwright install chromium")
    return f"Playwright render failed: {msg}"


def _try_render(url, timeout, user_agent, allow_private=False) -> Optional[Response]:
    """Render ``url`` with headless Chromium and return the post-JS DOM.

    Returns ``None`` only when Playwright isn't installed at all, so the caller
    transparently falls back to a plain fetch. Every other problem (missing
    browser binary, navigation timeout, page error) comes back as a Response
    with a clear, actionable ``error`` — a ``--render`` request never silently
    degrades to raw HTML, which would misrepresent what was measured."""
    try:
        from playwright.sync_api import (  # noqa: PLC0415
            Error as PWError,
            TimeoutError as PWTimeout,
            sync_playwright,
        )
    except ImportError:
        return None  # Playwright absent -> caller uses a normal HTTP fetch.

    start = time.time()
    nav_ms = max(1, timeout) * 1000
    try:
        with sync_playwright() as p:
            try:
                # --disable-dev-shm-usage avoids /dev/shm exhaustion in containers/CI;
                # the sandbox stays ON since we render untrusted pages.
                browser = p.chromium.launch(
                    headless=True, args=["--disable-dev-shm-usage"])
            except PWError as exc:
                return Response(url, url, 0, {}, "", 0, rendered=True,
                                error=_browser_launch_hint(exc))
            try:
                page = browser.new_page(user_agent=user_agent)
                page.set_default_timeout(nav_ms)
                latest_document_request = [None]

                def observe_document_request(request):
                    # Keep one bounded witness, including navigations still in
                    # flight. Same-document history changes have no request.
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        latest_document_request[0] = request

                page.on('request', observe_document_request)
                if not allow_private:
                    def guard_request(route):
                        try:
                            assert_public_host(route.request.url)
                        except (ValueError, SSRFError):
                            route.abort("blockedbyclient")
                            return
                        route.continue_()
                    page.route("**/*", guard_request)
                resp = page.goto(url, wait_until="domcontentloaded", timeout=nav_ms)
                # Best-effort settle for late XHR/hydration. networkidle can hang on
                # sites with long-polling/analytics, so cap it and proceed with
                # whatever rendered rather than failing the whole scan.
                try:
                    page.wait_for_load_state("networkidle", timeout=min(nav_ms, 5000))
                except PWTimeout:
                    pass
                html = page.content()
                status = resp.status if resp else 0
                headers = _origin_headers(resp.headers if resp else {})
                try:
                    robots_fields = resp.header_values('x-robots-tag') if resp else []
                    if not isinstance(robots_fields, list) or not all(isinstance(v, str) for v in robots_fields):
                        robots_fields = None
                except Exception:  # optional metadata must not discard an otherwise valid DOM
                    robots_fields = None
                final_url = page.url
                assert_public_host(final_url, allow_private=allow_private)
                if resp and latest_document_request[0] != resp.request:
                    raise ValueError(
                        'Rendered page started another document navigation after the initial load; '
                        'response headers and DOM cannot be safely paired. Scan the final destination directly.')
            finally:
                browser.close()
        return Response(
            url=url,
            final_url=final_url,
            status=status,
            headers=headers,
            text=html,
            elapsed_ms=int((time.time() - start) * 1000),
            rendered=True,
            robots_header_fields=robots_fields,
            robots_header_basis='browser_reported_fields' if robots_fields is not None else 'merged_or_unknown',
        )
    except PWTimeout as exc:
        return Response(url, url, 0, {}, "", 0, rendered=True,
                        error=f"Render timed out after {timeout}s "
                              f"(try a higher --timeout): {exc}")
    except PWError as exc:
        return Response(url, url, 0, {}, "", 0, rendered=True,
                        error=_browser_launch_hint(exc))
    except Exception as exc:  # noqa: BLE001
        return Response(url, url, 0, {}, "", 0, rendered=True, error=str(exc))


def fetch_text(url: str, **kwargs) -> Optional[str]:
    """Fetch a plain-text resource (robots.txt, llms.txt, sitemap) or None."""
    resp = fetch(url, **kwargs)
    return resp.text if resp.ok else None


def _decode_http_content(raw, encoding, max_bytes):
    """Bound HTTP gzip/deflate decoding and require a complete encoded stream."""
    if encoding == 'identity':
        return raw, None
    if encoding not in ('gzip', 'x-gzip', 'deflate'):
        return None, 'Unsupported HTTP content encoding; body unverified.'
    try:
        if encoding in ('gzip', 'x-gzip'):
            if not raw.startswith(b'\x1f\x8b'):
                return None, 'Incomplete or invalid HTTP encoded body; body unverified.'
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                decoded = stream.read(max_bytes + 1)
        else:
            decoder = zlib.decompressobj()
            try:
                decoded = decoder.decompress(raw, max_bytes + 1)
            except zlib.error:  # HTTP servers also use unwrapped DEFLATE
                decoder = zlib.decompressobj(-zlib.MAX_WBITS)
                decoded = decoder.decompress(raw, max_bytes + 1)
            if len(decoded) <= max_bytes and (not decoder.eof or decoder.unused_data):
                return None, 'Incomplete or invalid HTTP encoded body; body unverified.'
        if len(decoded) > max_bytes:
            return None, f'Response exceeded decoded byte limit ({max_bytes} bytes); body unverified.'
        return decoded, None
    except (EOFError, OSError, zlib.error):
        return None, 'Incomplete or invalid HTTP encoded body; body unverified.'


def fetch_bytes(url: str, *, timeout: int = DEFAULT_TIMEOUT,
                user_agent: str = DEFAULT_UA, allow_private: bool = False,
                max_bytes: int = 20_000_000):
    """Return complete successful raw bytes, or (None, bounded failure note).

    Prefixes from oversized, failed or known-incomplete responses are withheld.
    HTTP gzip/deflate is decoded only after bounded wire acquisition; a raw .gz
    file without Content-Encoding remains raw. The byte budget applies to both
    wire and HTTP-decoded bodies, not all network/process work.
    """
    positive_integer(max_bytes, 'Raw response byte budget')
    limit_note = f'Response exceeded raw byte limit ({max_bytes} bytes); body unverified.'
    try:
        url = normalize_url(url)
        assert_public_host(url, allow_private=allow_private)
    except (ValueError, SSRFError) as exc:
        return None, str(exc)
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        requests = None
    if requests is not None:
        try:
            r, _, _ = _requests_safe(
                requests, "GET", url, timeout=timeout,
                headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate, identity"},
                allow_private=allow_private,
                stream=True)
        except (requests.RequestException, SSRFError, ValueError) as exc:
            return None, type(exc).__name__
        try:
            if not 200 <= r.status_code < 300:
                return None, f'HTTP {r.status_code}'
            if _range_evidence(r.status_code, r.headers):
                return None, PARTIAL_RESOURCE_ERROR
            encoding = (r.headers.get('content-encoding') or 'identity').strip().lower()
            if encoding != 'identity':
                # iter_content auto-decodes and older urllib3 can accept a short
                # wire body or missing gzip trailer if its XML prefix is complete.
                try:
                    raw = r.raw.read(max_bytes + 1, decode_content=False)
                except requests.packages.urllib3.exceptions.HTTPError as exc:
                    return None, type(exc).__name__
                truncated = len(raw) > max_bytes
            else:
                raw, truncated = _limited_content(r, max_bytes)
            if truncated:
                return None, limit_note
            if (not r.headers.get('transfer-encoding')
                    and _declared_length_exceeds(r.headers.get('content-length'), len(raw))):
                return None, 'Incomplete response body (Content-Length not satisfied).'
            return _decode_http_content(raw, encoding, max_bytes)
        except requests.RequestException as exc:
            return None, type(exc).__name__
        finally:
            r.close()
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    import http.client as http_client  # noqa: PLC0415
    try:
        fh, _, _ = _urllib_safe_open(
            url, timeout=timeout, headers={"User-Agent": user_agent},
            allow_private=allow_private)
    except urllib.error.HTTPError as exc:
        exc.close()
        return None, f"HTTP {exc.code}"
    except (OSError, http_client.HTTPException, ValueError) as exc:
        return None, type(exc).__name__
    try:
        with fh:
            if not 200 <= fh.status < 300:
                return None, f'HTTP {fh.status}'
            if _range_evidence(fh.status, fh.headers):
                return None, PARTIAL_RESOURCE_ERROR
            raw = fh.read(max_bytes + 1)
            if len(raw) > max_bytes:
                return None, limit_note
            length = fh.headers.get('content-length')
            if (not fh.headers.get('transfer-encoding')
                    and _declared_length_exceeds(length, len(raw))):
                return None, 'Incomplete response body (Content-Length not satisfied).'
            encoding = (fh.headers.get('content-encoding') or 'identity').strip().lower()
            return _decode_http_content(raw, encoding, max_bytes)
    except (OSError, http_client.HTTPException) as exc:
        return None, type(exc).__name__


def head_info(url: str, *, timeout: int = DEFAULT_TIMEOUT,
              user_agent: str = DEFAULT_UA, allow_private: bool = False):
    """HEAD a URL and return ``(status, headers, error)`` with lowercase header
    names. Used by the image checks (content-length / content-type) — like
    :func:`head` but keeps the response headers. Never raises."""
    try:
        url = normalize_url(url)
        assert_public_host(url, allow_private=allow_private)
    except (ValueError, SSRFError) as exc:
        return 0, {}, str(exc)
    try:
        import requests  # noqa: PLC0415
        try:
            r, _, _ = _requests_safe(
                requests, "HEAD", url, timeout=timeout,
                headers={"User-Agent": user_agent}, allow_private=allow_private)
            return r.status_code, {k.lower(): v for k, v in r.headers.items()}, None
        except (requests.RequestException, SSRFError, ValueError) as exc:
            return 0, {}, type(exc).__name__
    except ImportError:
        pass
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    try:
        fh, _, _ = _urllib_safe_open(
            url, timeout=timeout, headers={"User-Agent": user_agent},
            allow_private=allow_private, method="HEAD")
        with fh:
            return fh.status, {k.lower(): v for k, v in fh.headers.items()}, None
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, None
    except Exception as exc:  # noqa: BLE001
        return 0, {}, type(exc).__name__


def fetch_range(url: str, n: int, *, timeout: int = DEFAULT_TIMEOUT,
                user_agent: str = DEFAULT_UA, allow_private: bool = False):
    """Fetch at most the first ``n`` bytes of a URL (Range request; the read is
    capped even when the server ignores Range). Returns ``(bytes, error)`` —
    used to probe image dimensions without downloading whole files.
    Invalid/nonpositive counts raise ValueError before I/O."""
    positive_integer(n, 'Range byte budget')
    try:
        url = normalize_url(url)
        assert_public_host(url, allow_private=allow_private)
    except (ValueError, SSRFError) as exc:
        return None, str(exc)
    headers = {"User-Agent": user_agent, "Range": f"bytes=0-{n - 1}"}
    try:
        import requests  # noqa: PLC0415
        try:
            r, _, _ = _requests_safe(
                requests, "GET", url, timeout=timeout, headers=headers,
                allow_private=allow_private, stream=True)
            try:
                buf = b""
                for chunk in r.iter_content(chunk_size=8192):
                    buf += chunk
                    if len(buf) >= n:
                        break
                return buf[:n], None if r.status_code < 400 else f"HTTP {r.status_code}"
            finally:
                r.close()
        except (requests.RequestException, SSRFError, ValueError) as exc:
            return None, type(exc).__name__
    except ImportError:
        pass
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    try:
        fh, _, _ = _urllib_safe_open(
            url, timeout=timeout, headers=headers, allow_private=allow_private)
        with fh:
            return fh.read(n), None
    except urllib.error.HTTPError as exc:
        exc.close()
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, type(exc).__name__


def head(url: str, *, timeout: int = DEFAULT_TIMEOUT, user_agent: str = DEFAULT_UA,
         allow_private: bool = False):
    """Check a URL's reachability cheaply. Returns ``(status, error)``.

    Uses HEAD (falling back to GET when a server rejects it) and follows
    redirects. When GET is attempted, its outcome replaces the HEAD rejection.
    ``status == 0`` means unreachable (DNS/timeout/SSRF-blocked); the
    error string carries the reason. Never raises — safe for bulk link checking.
    """
    try:
        url = normalize_url(url)
    except ValueError as exc:
        return 0, str(exc)
    try:
        assert_public_host(url, allow_private=allow_private)
    except URLInputError as exc:
        return 0, str(exc)
    try:
        return _head_requests(url, timeout, user_agent,
                              allow_private=allow_private)
    except ImportError:
        return _head_urllib(url, timeout, user_agent,
                            allow_private=allow_private)


def _head_requests(url, timeout, user_agent, allow_private=False):
    import requests  # noqa: PLC0415

    headers = {"User-Agent": user_agent}
    try:
        r, _, _ = _requests_safe(requests, "HEAD", url, timeout=timeout,
                                  headers=headers, allow_private=allow_private)
        r.close()
        if r.status_code in (403, 405, 501):  # some servers refuse HEAD
            r, _, _ = _requests_safe(requests, "GET", url, timeout=timeout,
                                      headers=headers, allow_private=allow_private,
                                      stream=True)
            r.close()
        return r.status_code, None
    except (requests.RequestException, SSRFError, ValueError) as exc:
        return 0, type(exc).__name__


def _head_urllib(url, timeout, user_agent, allow_private=False):
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    def _try(method):
        try:
            fh, _, _ = _urllib_safe_open(
                url, timeout=timeout, headers={"User-Agent": user_agent},
                allow_private=allow_private, method=method)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise
        with fh:
            return fh.status, None

    try:
        return _try("HEAD")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            try:
                return _try("GET")
            except urllib.error.HTTPError as fallback:
                return fallback.code, None
            except Exception as fallback:  # noqa: BLE001
                return 0, type(fallback).__name__
        return exc.code, None
    except Exception as exc:  # noqa: BLE001
        return 0, type(exc).__name__
