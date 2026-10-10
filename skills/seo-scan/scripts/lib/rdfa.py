"""Bounded, local-only schema.org RDFa extraction, not a full RDF processor.

Supports the RDFa Lite attributes plus about/content and plain scalar datatypes.
Relations, lists, property copying and markup literals are deliberately skipped
with coverage warnings. No vocabulary, context or referenced URL is fetched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from .microdata import INERT, _Limit, _Tree, _text, schema_name

MAX_ELEMENTS = 50_000
MAX_NODES = 1_000
MAX_PROPERTIES = 10_000
MAX_DEPTH = 64
SCOPE = "bounded schema.org RDFa (not a full RDFa processor)"
PREFIXES = {"schema": "http://schema.org/", "og": "http://ogp.me/ns#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfa": "http://www.w3.org/ns/rdfa#"}
URL_PROPERTIES = {"url", "image", "logo", "sameAs", "availability", "itemCondition",
                  "contentUrl", "thumbnailUrl", "embedUrl", "license"}
HTML_RELS = set("alternate author bookmark canonical dns-prefetch external help icon license manifest modulepreload next nofollow noopener noreferrer opener pingback preconnect prefetch preload prev search stylesheet tag".split())


@dataclass(frozen=True)
class _Ref:
    key: object


def extract(html, base_url=""):
    """Return shared-auditor objects and explicit partial-coverage warnings."""
    if not re.search(r"\b(?:typeof|property|vocab)\s*=", html or "", re.I):
        return [], []
    tree = _Tree(base_url, label="RDFa", element_limit=MAX_ELEMENTS)
    try:
        tree.feed(html)
        tree.close()
    except _Limit as exc:
        tree.warn(str(exc))
    graph, counter, property_count = {}, 0, 0

    def blank():
        nonlocal counter
        counter += 1
        return _Ref(("blank", counter))

    def absolute(value):
        try:
            return bool(urlsplit(value).scheme) and not re.search(r"[\s<>]", value)
        except ValueError:
            return False

    def expand(raw, prefixes, vocab, term=False):
        safe = raw.startswith("[") and raw.endswith("]")
        value = raw[1:-1] if safe else raw
        if ":" in value:
            prefix, tail = value.split(":", 1)
            if prefix.lower() in prefixes:
                return prefixes[prefix.lower()] + tail
            if prefix == "_" and not term:
                return value
            if not safe and absolute(value):
                return value
            tree.warn("RDFa unresolved CURIE skipped: " + raw)
            return None
        if safe:
            tree.warn("RDFa unresolved CURIE skipped: " + raw)
            return None
        if term:
            return vocab + value if vocab and value else None
        return tree.resolve(value)

    def names(raw, prefixes, vocab):
        values = []
        for token in raw.split():
            iri = expand(token, prefixes, vocab, term=True)
            name = schema_name(iri)
            if iri and name != iri and name not in values:
                values.append(name)
        return values

    def resource(attrs, keys, prefixes, vocab):
        for key in keys:
            if key in attrs:
                # href/src are IRIs, not CURIEs; resource/about may be either.
                iri = (tree.resolve(attrs[key]) if key in {"href", "src"}
                       else expand(attrs[key], prefixes, vocab))
                return _Ref(iri) if iri is not None else None
        return None

    def node(ref):
        if ref not in graph:
            if len(graph) >= MAX_NODES:
                raise _Limit("RDFa node limit reached; extraction is partial.")
            graph[ref] = {}
        return graph[ref]

    def add(ref, prop, value):
        nonlocal property_count
        if ref is None:
            return
        if property_count >= MAX_PROPERTIES:
            raise _Limit("RDFa property limit reached; extraction is partial.")
        property_count += 1
        values = node(ref).setdefault(prop, [])
        # RDF graphs contain unique triples, not repeated copies of a value.
        if value not in values:
            values.append(value)

    document = _Ref(tree.base_url)
    pending = [(child, document, PREFIXES, "") for child in reversed(tree.root.children)]
    try:
        while pending:
            element, parent, inherited_prefixes, vocab = pending.pop()
            if element.tag in INERT:
                continue
            attrs = element.attrs
            prefixes = dict(inherited_prefixes)
            for key, value in attrs.items():
                if key.startswith("xmlns:"):
                    prefixes[key[6:].lower()] = value if absolute(value) else ""
            if "prefix" in attrs:
                tokens = attrs["prefix"].split()
                if len(tokens) % 2:
                    tree.warn("RDFa malformed prefix declaration; extraction is partial.")
                    if tokens[-1].endswith(":"):
                        prefixes[tokens[-1][:-1].lower()] = ""
                for i in range(0, len(tokens) - 1, 2):
                    prefix, iri = tokens[i:i + 2]
                    if not re.fullmatch(r"[A-Za-z][\w.-]*:", prefix) or not absolute(iri):
                        tree.warn("RDFa malformed prefix declaration; extraction is partial.")
                        if prefix.endswith(":"):
                            prefixes[prefix[:-1].lower()] = ""
                        continue
                    prefixes[prefix[:-1].lower()] = iri
            if "vocab" in attrs:
                raw = attrs["vocab"]
                vocab = tree.resolve(raw) if raw else ""
                if vocab and not absolute(vocab):
                    tree.warn("RDFa invalid vocabulary; extraction is partial.")
                    vocab = ""
            types = names(attrs.get("typeof", ""), prefixes, vocab)
            properties = names(attrs.get("property", ""), prefixes, vocab)
            relations = [token for token in (attrs.get("rel", "") + " " + attrs.get("rev", "")).split()
                         if token.lower() not in HTML_RELS and (vocab or ":" in token)]
            special = [expand(t, prefixes, vocab, term=True) for t in
                       (attrs.get("property", "") + " " + attrs.get("typeof", "")).split()]
            datatype = expand(attrs.get("datatype", ""), prefixes, vocab, term=True)
            unsupported = (relations or ("inlist" in attrs and properties)
                           or "http://www.w3.org/ns/rdfa#copy" in special
                           or "http://www.w3.org/ns/rdfa#Pattern" in special
                           or (properties and datatype and not
                               (datatype.startswith(PREFIXES["xsd"]) or datatype == PREFIXES["rdf"] + "langString")))
            if unsupported:
                tree.warn("RDFa relations, lists, property copying or non-scalar literals skipped; extraction is partial.")
                # Do not attach descendant properties to the wrong parent.
                continue
            about = resource(attrs, ("about",), prefixes, vocab)
            target = resource(attrs, ("resource", "href", "src"), prefixes, vocab)
            literal = "content" in attrs or "datatype" in attrs
            if "property" in attrs and not literal:
                if element.tag == "html" and about is None:
                    about = document
                subject = about if about is not None else parent
                typed = (about if about is not None else target if target is not None else blank()) if "typeof" in attrs else None
                obj = typed if typed is not None and about is None else target
            else:
                subject = about if about is not None else target
                if subject is None:
                    subject = (parent if element.tag in {"html", "head", "body"}
                               else blank() if "typeof" in attrs else parent)
                typed = subject if "typeof" in attrs else None
                obj = None
            for typ in types:
                add(typed, "@type", typ)
            if properties:
                value = (attrs["content"] if "content" in attrs else
                         attrs["datetime"] if "datetime" in attrs else
                         _text(element) if literal or obj is None else obj)
                for prop in properties:
                    add(subject, prop, value)
            # A resource-valued property makes its object the children's subject.
            child_subject = obj if obj is not None else subject
            pending.extend((child, child_subject, prefixes, vocab) for child in reversed(element.children))
    except _Limit as exc:
        tree.warn(str(exc))

    cache, active = {}, set()

    def project(ref, depth=0):
        identity = {"@id": ref.key} if isinstance(ref.key, str) else {}
        if ref in active or depth >= MAX_DEPTH:
            tree.warn("RDFa cyclic or excessively nested resource reference truncated; extraction is partial.")
            return identity
        if ref in cache:
            return cache[ref]
        result = dict(identity)
        active.add(ref)
        for prop, values in graph[ref].items():
            out = []
            for value in values:
                if isinstance(value, _Ref):
                    # Keep typed ImageObject/logo entities, but ordinary URL
                    # properties remain IRIs even when their target is described.
                    nested = (prop not in URL_PROPERTIES or not isinstance(value.key, str)
                              or (prop in {"image", "logo"} and "ImageObject" in graph.get(value, {}).get("@type", [])))
                    value = (project(value, depth + 1) if value in graph and nested
                             else value.key if isinstance(value.key, str) else {})
                out.append(value)
            result[prop] = out[0] if len(out) == 1 else out
        active.remove(ref)
        cache[ref] = result
        return result

    return [project(ref) for ref in graph], tree.warnings
