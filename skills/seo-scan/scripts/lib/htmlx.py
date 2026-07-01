"""HTML parsing helpers with graceful fallback.

Uses ``lxml``/``BeautifulSoup`` when available (accurate), otherwise a stdlib
``html.parser`` shim that is good enough for the audits. All auditors consume the
normalized :class:`Doc` view so they never depend on which backend parsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin

WS = re.compile(r"\s+")


def collapse(text: str) -> str:
    return WS.sub(" ", text or "").strip()


@dataclass
class Tag:
    name: str
    attrs: dict = field(default_factory=dict)
    text: str = ""

    def get(self, key: str, default=None):
        return self.attrs.get(key.lower(), default)


@dataclass
class Doc:
    """Normalized, backend-agnostic view of a parsed HTML document."""

    base_url: str
    title: str = ""
    meta: list = field(default_factory=list)          # list[Tag]
    links: list = field(default_factory=list)          # list[Tag] (<a>)
    link_rels: list = field(default_factory=list)      # list[Tag] (<link>)
    headings: list = field(default_factory=list)       # list[(level:int, text:str)]
    images: list = field(default_factory=list)         # list[Tag]
    scripts_ld: list = field(default_factory=list)     # list[str] JSON-LD blobs
    lang: str = ""
    text: str = ""                                     # all visible text
    main_text: str = ""                                # main content only (if isolable)
    html: str = ""

    @property
    def body_text(self) -> str:
        """Main content when we could isolate it, else all visible text."""
        return self.main_text or self.text

    def meta_by_name(self, name: str) -> Optional[str]:
        name = name.lower()
        for m in self.meta:
            if (m.get("name") or "").lower() == name:
                return m.get("content")
        return None

    def meta_by_property(self, prop: str) -> Optional[str]:
        prop = prop.lower()
        for m in self.meta:
            if (m.get("property") or "").lower() == prop:
                return m.get("content")
        return None

    def links_by_rel(self, rel: str) -> list:
        rel = rel.lower()
        return [l for l in self.link_rels if rel in (l.get("rel") or "").lower().split()]

    def canonical(self) -> Optional[str]:
        links = self.links_by_rel("canonical")
        href = links[0].get("href") if links else None
        return urljoin(self.base_url, href) if href else None


def parse(html: str, base_url: str = "") -> Doc:
    try:
        doc = _parse_bs4(html, base_url)
    except ImportError:
        doc = _parse_stdlib(html, base_url)
    doc.main_text = _main_content(html)
    return doc


def _main_content(html: str) -> str:
    """Isolate the main article text with trafilatura when available.

    Returns "" when the library is absent or can't confidently extract, in which
    case callers fall back to all visible text via ``Doc.body_text``.
    """
    try:
        import trafilatura  # noqa: PLC0415
    except ImportError:
        return ""
    try:
        extracted = trafilatura.extract(html, include_comments=False,
                                        include_tables=False)
        return collapse(extracted) if extracted else ""
    except Exception:  # noqa: BLE001
        return ""


def _parse_bs4(html: str, base_url: str) -> Doc:
    from bs4 import BeautifulSoup  # noqa: PLC0415

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:  # noqa: BLE001 - lxml not installed
        soup = BeautifulSoup(html, "html.parser")

    doc = Doc(base_url=base_url, html=html)
    if soup.title and soup.title.string:
        doc.title = collapse(soup.title.string)
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        doc.lang = html_tag.get("lang")

    for m in soup.find_all("meta"):
        doc.meta.append(Tag("meta", {k.lower(): v for k, v in m.attrs.items()}))
    for l in soup.find_all("link"):
        attrs = {k.lower(): _join(l, k) for k in l.attrs}
        doc.link_rels.append(Tag("link", attrs))
    for a in soup.find_all("a"):
        doc.links.append(Tag("a", {k.lower(): v for k, v in a.attrs.items()}, collapse(a.get_text())))
    for lvl in range(1, 7):
        for h in soup.find_all(f"h{lvl}"):
            doc.headings.append((lvl, collapse(h.get_text())))
    for img in soup.find_all("img"):
        doc.images.append(Tag("img", {k.lower(): v for k, v in img.attrs.items()}))
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if s.string:
            doc.scripts_ld.append(s.string.strip())

    for bad in soup(["script", "style", "noscript", "template"]):
        bad.extract()
    doc.text = collapse(soup.get_text(" "))
    return doc


def _join(tag, key):  # normalize list-valued attrs from bs4
    v = tag.get(key)
    return " ".join(v) if isinstance(v, list) else (v or "")


class _StdlibParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.doc = Doc(base_url=base_url)
        self._stack = []
        self._capture = None       # (kind, buffer)
        self._ld_buf = None
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.doc.lang = a["lang"]
        elif tag == "meta":
            self.doc.meta.append(Tag("meta", a))
        elif tag == "link":
            self.doc.link_rels.append(Tag("link", a))
        elif tag == "img":
            self.doc.images.append(Tag("img", a))
        elif tag == "title":
            self._capture = ("title", [])
        elif tag == "a":
            self._capture = ("a", [], a)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._capture = (tag, [])
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._ld_buf = []
        elif tag in ("script", "style", "noscript", "template"):
            self._skip_depth += 1
        if tag not in ("meta", "link", "img", "br", "hr", "input"):
            self._stack.append(tag)

    def handle_endtag(self, tag):
        if self._capture and tag == self._capture[0]:
            text = collapse("".join(self._capture[1]))
            if tag == "title":
                self.doc.title = text
            elif tag == "a":
                self.doc.links.append(Tag("a", self._capture[2], text))
            else:
                self.doc.headings.append((int(tag[1]), text))
            self._capture = None
        elif tag == "script" and self._ld_buf is not None:
            self.doc.scripts_ld.append("".join(self._ld_buf).strip())
            self._ld_buf = None
        elif tag in ("script", "style", "noscript", "template") and self._skip_depth:
            self._skip_depth -= 1
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._ld_buf is not None:
            self._ld_buf.append(data)
        elif self._capture:
            self._capture[1].append(data)
        elif self._skip_depth == 0:
            self._text.append(data)

    _text: list = []


def _parse_stdlib(html: str, base_url: str) -> Doc:
    p = _StdlibParser(base_url)
    p._text = []
    p.feed(html)
    p.doc.html = html
    p.doc.text = collapse(" ".join(p._text))
    return p.doc
