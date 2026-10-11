"""Bounded original-source merchant evidence, shared by both HTML backends.

This is not a browser visibility or checkout test. Inert and explicitly hidden
subtrees cannot corroborate a price, identifier, label or purchase action.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from .microdata import INERT, _Limit, _Tree, schema_name

MAX_ELEMENTS = 50_000
MAX_WARNINGS = 64
PROPERTIES = {name.lower(): name for name in ("price", "priceCurrency", "availability", "brand", "sku")}


def meta_property(markup, name):
    """First active declaration wins, matching OpenGraph preference order."""
    for meta in markup["meta"]:
        if (meta.get("property") or "").lower() == name.lower():
            return meta.get("content") or ""
    return ""


def _hidden(node):
    attrs = node.attrs
    return (node.tag in INERT or "hidden" in attrs
            or attrs.get("aria-hidden", "").lower() == "true"
            or bool(re.search(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)\b", attrs.get("style", ""), re.I)))


def _text(node):
    pending, out = list(reversed(node.content)), []
    while pending:
        child = pending.pop()
        if isinstance(child, str):
            out.append(child)
        elif not _hidden(child):
            pending.extend(reversed(child.content))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _value(node, tree, name):
    attrs = node.attrs
    if node.tag == "meta":
        return attrs.get("content", "")
    if node.tag in {"data", "meter"}:
        return attrs.get("value", "")
    if node.tag == "time" and "datetime" in attrs:
        return attrs["datetime"]
    if node.tag in {"a", "area", "link"}:
        # A linked brand's label is name evidence, not its resource URL.
        if name == "brand":
            return _text(node)
        return tree.resolve(attrs["href"]) if attrs.get("href") else ""
    return _text(node)


def _control(node, base_url, page_url):
    attrs = node.attrs
    if (node.tag not in {"button", "input", "a"} or "disabled" in attrs
            or attrs.get("aria-disabled", "").lower() == "true"):
        return False
    text = attrs.get("value", "") if node.tag == "input" else _text(node)
    if not re.match(r"(?:add to (?:cart|bag)|buy now)\b", text, re.I):
        return False
    if node.tag == "input":
        return attrs.get("type", "text").lower() in {"button", "submit"}
    if node.tag != "a":
        return True
    try:
        target, source = urlparse(urljoin(base_url, attrs.get("href", ""))), urlparse(page_url)
        def origin(parsed):
            port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
            return parsed.scheme, parsed.hostname, port
        return "href" in attrs and target.scheme in {"http", "https"} and origin(target) == origin(source)
    except ValueError:
        return False


def extract(html, base_url=""):
    """Return active metadata, itemprop observations, labels and controls once."""
    tree = _Tree(base_url, label="Merchant evidence", element_limit=MAX_ELEMENTS, warning_limit=MAX_WARNINGS)
    try:
        tree.feed(html or "")
        tree.close()
    except _Limit as exc:
        tree.warn(str(exc))
    result = {"meta": [], "itemprops": {}, "text": "", "h1": "",
              "purchase_action": False, "warnings": tree.warnings}
    pending, texts = [(tree.root, True, False)], []
    while pending:
        node, visible, blocked = pending.pop()
        if isinstance(node, str):
            texts.append(node)
            continue
        if _hidden(node):
            continue
        visible = visible and node.tag not in {"head", "title"}
        blocked = blocked or (node.tag == "fieldset" and "disabled" in node.attrs)
        if node.tag == "meta":
            result["meta"].append(dict(node.attrs))
        if node.tag == "h1" and visible and not result["h1"]:
            result["h1"] = _text(node)
        if visible and not blocked and _control(node, tree.base_url, base_url):
            result["purchase_action"] = True
        for token in node.attrs.get("itemprop", "").split():
            name = PROPERTIES.get(schema_name(token).lower())
            if name and name not in result["itemprops"]:
                value = re.sub(r"\s+", " ", _value(node, tree, name)).strip()
                if value:
                    result["itemprops"][name] = value
        # Walk content, not just elements, to keep prose-label order intact.
        for child in reversed(node.content):
            if isinstance(child, str):
                if visible:
                    # A text marker preserves its place in the iterative walk.
                    pending.append((child, visible, blocked))
            else:
                pending.append((child, visible, blocked))
    result["text"] = re.sub(r"\s+", " ", " ".join(texts)).strip()
    return result
