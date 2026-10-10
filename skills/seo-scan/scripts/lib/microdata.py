"""Bounded, stdlib-only schema.org Microdata extraction.

Both HTML backends use this same original-source extractor. It implements item
scopes, property values and itemref, not a full browser DOM or RDFa processor.
Inert templates and foreign SVG/MathML subtrees are deliberately excluded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

VOID = set("area base br col embed hr img input link meta param source track wbr".split())
INERT = {"script", "style", "template", "svg", "math"}
MAX_ELEMENTS = 50_000
MAX_ITEMS = 1_000
MAX_DEPTH = 64
P_BLOCKS = set("address article aside blockquote div dl fieldset footer form h1 h2 h3 h4 h5 h6 header hgroup hr main nav ol p pre section table ul".split())


def schema_name(value):
    """Shorten schema.org vocabulary URLs only, never lookalike namespaces."""
    match = re.fullmatch(r"https?://(?:www\.)?schema\.org/([A-Za-z][A-Za-z0-9]*)/?", value or "")
    return match.group(1) if match else value


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict
    order: int
    children: list = field(default_factory=list)
    content: list = field(default_factory=list)


class _Tree(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.root = Element("", {}, -1)
        self.stack = [self.root]
        self.elements = []
        self.ids = {}
        self.base_url = base_url
        self.base_seen = False
        self.warnings = []

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def resolve(self, raw):
        try:
            return urljoin(self.base_url, raw)
        except ValueError:
            self.warn("Microdata URL could not be resolved: " + raw)
            return ""

    def close_optional(self, targets, boundaries=()):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag in targets:
                del self.stack[i:]
                return
            if self.stack[i].tag in boundaries:
                return

    def handle_starttag(self, tag, attrs):
        # Common valid omitted end tags must not leak properties into siblings.
        # This is intentionally not a full HTML5 tree-construction algorithm.
        if not any(parent.tag in INERT for parent in self.stack):
            if tag in P_BLOCKS:
                self.close_optional({"p"})
            if tag == "li":
                self.close_optional({"li"}, {"ul", "ol"})
            elif tag in {"dt", "dd"}:
                self.close_optional({"dt", "dd"}, {"dl"})
            elif tag in {"td", "th"}:
                self.close_optional({"td", "th"}, {"tr", "table"})
            elif tag == "tr":
                self.close_optional({"tr"}, {"table", "tbody", "thead", "tfoot"})
            elif tag == "option":
                self.close_optional({"option"}, {"select", "datalist"})
        if len(self.elements) >= MAX_ELEMENTS:
            raise _Limit("Microdata element limit reached; extraction is partial.")
        if len(self.stack) >= 256:
            raise _Limit("Microdata HTML nesting limit reached; extraction is partial.")
        attrs = dict(attrs)
        node = Element(tag, {k: v or "" for k, v in attrs.items()}, len(self.elements))
        self.elements.append(node)
        self.stack[-1].children.append(node)
        self.stack[-1].content.append(node)
        inert = any(parent.tag in INERT for parent in self.stack) or tag in INERT
        if inert:
            node.attrs.clear()
        else:
            if "id" in node.attrs:
                self.ids.setdefault(node.attrs["id"], node)
            if tag == "base" and "href" in node.attrs and not self.base_seen:
                self.base_url = self.resolve(node.attrs["href"])
                self.base_seen = True
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if not any(node.tag in INERT for node in self.stack):
            self.stack[-1].content.append(data)


class _Limit(Exception):
    pass


def _text(node):
    # Iterative traversal avoids recursion on untrusted, deeply nested HTML.
    pending, out = list(reversed(node.content)), []
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            out.append(value)
        elif value.tag not in INERT:
            pending.extend(reversed(value.content))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def extract(html, base_url=""):
    """Return normalized item objects and explicit extraction-coverage warnings."""
    if "itemscope" not in (html or "").lower():
        return [], []
    tree = _Tree(base_url)
    try:
        tree.feed(html)
        tree.close()
    except _Limit as exc:
        tree.warn(str(exc))
    scopes = [node for node in tree.elements if "itemscope" in node.attrs]
    if len(scopes) > MAX_ITEMS:
        tree.warn("Microdata item limit reached; extraction is partial.")
        scopes = scopes[:MAX_ITEMS]
    allowed = set(scopes)
    cache, active = {}, set()

    def value(node, depth):
        if "itemscope" in node.attrs:
            return item(node, depth + 1)
        if node.tag == "meta":
            return node.attrs.get("content", "")
        url_attr = ("src" if node.tag in {"audio", "embed", "iframe", "img", "source", "track", "video"}
                    else "href" if node.tag in {"a", "area", "link"}
                    else "data" if node.tag == "object" else "")
        if url_attr:
            raw = node.attrs.get(url_attr, "")
            return tree.resolve(raw) if raw else ""
        if node.tag in {"data", "meter"}:
            return node.attrs.get("value", "")
        if node.tag == "time" and "datetime" in node.attrs:
            return node.attrs["datetime"]
        return _text(node)

    def item(root, depth=0):
        if root in active or depth >= MAX_DEPTH:
            tree.warn("Microdata cyclic or excessively nested item reference skipped; extraction is partial.")
            return {}
        if root not in allowed:
            tree.warn("Microdata item limit reached; extraction is partial.")
            return {}
        if root in cache:
            return cache[root]
        active.add(root)
        types = []
        for typ in root.attrs.get("itemtype", "").split():
            try:
                valid = bool(urlsplit(typ).scheme)
            except ValueError:
                valid = False
            if valid:
                types.append(schema_name(typ))
            else:
                tree.warn("Microdata itemtype must be an absolute vocabulary URL: " + typ)
        result = {"@type": types[0] if len(types) == 1 else types} if types else {}
        if root.attrs.get("itemid"):
            result["@id"] = tree.resolve(root.attrs["itemid"])
        pending, seen, properties = list(root.children), {root}, []
        for ref in root.attrs.get("itemref", "").split():
            if ref in tree.ids:
                pending.append(tree.ids[ref])
            else:
                tree.warn("Microdata itemref target not found: " + ref)
        while pending:
            node = pending.pop()
            if node in seen:
                tree.warn("Microdata overlapping or cyclic itemref skipped.")
                continue
            seen.add(node)
            if node.tag in INERT:
                continue
            if "itemprop" in node.attrs:
                properties.append(node)
            if "itemscope" not in node.attrs:
                pending.extend(node.children)
        collected = {}
        for node in sorted(properties, key=lambda n: n.order):
            names = dict.fromkeys(schema_name(p) for p in node.attrs["itemprop"].split())
            prop_value = value(node, depth)
            for name in names:
                # JSON-LD keywords cannot be supplied as Microdata properties.
                if not name.startswith("@"):
                    collected.setdefault(name, []).append(prop_value)
        for name, values in collected.items():
            result[name] = values[0] if len(values) == 1 else values
        active.remove(root)
        cache[root] = result
        return result

    # Extract every scope, including independent nested items and itemref-only
    # items. Consumers deduplicate normalized nested objects, not their values.
    return [item(root) for root in scopes], tree.warnings
