"""Deterministic Product/Offer evidence extraction and merchant checks.

The module consumes only the normalized document plus its original HTML, so the
results do not depend on BeautifulSoup/lxml being installed. Visible/schema
comparisons are emitted only for explicit metadata, itemprop values, or labelled
page facts; an incidental number or currency word is not treated as a product.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from html import unescape
from urllib.parse import urlparse

from . import htmlx, structured_data

CAT = "schema"
IDENTIFIERS = ("sku", "gtin", "gtin8", "gtin12", "gtin13", "gtin14", "mpn")
AVAILABILITY = {
    "instock": "in_stock", "in stock": "in_stock",
    "outofstock": "out_of_stock", "out of stock": "out_of_stock", "sold out": "out_of_stock",
    "preorder": "preorder", "pre-order": "preorder",
    "backorder": "backorder", "back-order": "backorder",
    "discontinued": "discontinued", "limitedavailability": "limited",
    "instoreonly": "in_store_only", "onlineonly": "online_only",
    "presale": "presale", "soldout": "out_of_stock",
}
ITEM_CONDITIONS = {"newcondition", "usedcondition", "refurbishedcondition", "damagedcondition"}


def _types(node):
    typ = node.get("@type") if isinstance(node, dict) else None
    return [str(x).lower() for x in typ] if isinstance(typ, list) else ([str(typ).lower()] if typ else [])


def schema_nodes(doc):
    """Return unique structured-data nodes; syntax failures belong to audit_schema."""
    records, _ = structured_data.collect(doc)
    return [record["node"] for record in records]


def _clean(value):
    if isinstance(value, dict):
        value = value.get("name") or value.get("@id") or value.get("value")
    if isinstance(value, list):
        value = next((x for x in value if x not in (None, "")), "")
        return _clean(value)
    return htmlx.collapse(str(value or ""))


def _meta(doc, keys):
    for key in keys:
        value = doc.meta_by_property(key) or doc.meta_by_name(key)
        if value:
            return _clean(value), f"meta[{key}]"
    return "", ""


def _attr_value(html, itemprop):
    # Constrain matching to one tag; accept content/value/href or its text.
    tag_re = re.compile(r"<([a-z0-9]+)\b([^>]*\bitemprop\s*=\s*([\"'])" +
                        re.escape(itemprop) + r"\3[^>]*)>(.*?)</\1\s*>", re.I | re.S)
    bare_re = re.compile(r"<[^>]*\bitemprop\s*=\s*([\"'])" + re.escape(itemprop) +
                         r"\1[^>]*>", re.I | re.S)
    match = tag_re.search(html or "")
    raw = (match.group(2) if match else "")
    text = re.sub(r"<[^>]+>", " ", match.group(4)) if match else ""
    if not match:
        bare = bare_re.search(html or "")
        raw = bare.group(0) if bare else ""
    attr = re.search(r"\b(?:content|value|href)\s*=\s*([\"'])(.*?)\1", raw, re.I | re.S)
    value = unescape(attr.group(2) if attr else text)
    return (htmlx.collapse(value), f"itemprop={itemprop}") if value else ("", "")


def _label(text, label):
    match = re.search(r"\b" + label + r"\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9 ._/-]{0,60})", text or "", re.I)
    if not match:
        return "", ""
    value = match.group(1).strip()
    # Stop before common next-label boundaries in collapsed page text.
    value = re.split(r"\s+(?:price|availability|brand|sku|mpn|gtin)\s*[:#]", value, 1, flags=re.I)[0]
    return value.strip(), f"visible label {label}"


def visible_facts(doc):
    facts = {}
    mappings = {
        "price": (("product:price:amount", "og:price:amount"), "price"),
        "currency": (("product:price:currency", "og:price:currency"), "priceCurrency"),
        "availability": (("product:availability", "og:availability"), "availability"),
        "brand": (("product:brand",), "brand"),
        "sku": (("product:retailer_item_id",), "sku"),
    }
    for key, (meta_keys, itemprop) in mappings.items():
        value, source = _meta(doc, meta_keys)
        if not value:
            value, source = _attr_value(doc.html, itemprop)
        if value:
            facts[key] = {"value": value, "source": source, "confidence": 1.0}
    for key, label in (("brand", "brand"), ("sku", "sku"), ("availability", "availability")):
        if key not in facts:
            value, source = _label(doc.body_text, label)
            if value:
                facts[key] = {"value": value, "source": source, "confidence": 0.9}
    if doc.headings:
        h1 = next((text for level, text in doc.headings if level == 1 and text), "")
        if h1:
            facts["name"] = {"value": h1, "source": "visible H1", "confidence": 0.85}
    return facts


def detect(doc, nodes=None):
    nodes = nodes if nodes is not None else schema_nodes(doc)
    product_nodes = [n for n in nodes if "product" in _types(n)]
    evidence = []
    if product_nodes:
        records, _ = structured_data.collect(doc)
        formats = {source for record in records if "product" in _types(record["node"])
                   for source in record["formats"]}
        if "jsonld" in formats:
            evidence.append("Product JSON-LD")
        if "microdata" in formats:
            evidence.append("Product microdata")
        if "rdfa" in formats:
            evidence.append("Product RDFa")
    if (doc.meta_by_property("og:type") or "").lower() == "product":
        evidence.append("og:type=product")
    visible = visible_facts(doc)
    merchant = sorted(set(visible) & {"price", "currency", "availability", "sku"})
    if merchant:
        evidence.append("explicit merchant facts: " + ", ".join(merchant))
    is_product = bool(product_nodes) or htmlx.looks_product(doc)
    has_offer = any(n.get("offers") for n in product_nodes)
    is_merchant = bool(has_offer or merchant)
    confidence = 1.0 if product_nodes else (0.9 if "Product microdata" in evidence else (0.8 if is_product else 0.0))
    return {"is_product": is_product, "is_merchant": is_merchant,
            "confidence": confidence, "evidence": evidence,
            "product_nodes": product_nodes, "visible": visible}


def _norm_text(value):
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _norm_price(value):
    value = re.sub(r"[^0-9.,-]", "", _clean(value))
    if "," in value and "." not in value and re.search(r",\d{1,2}$", value):
        value = value.replace(",", ".")
    else:
        value = value.replace(",", "")
    try:
        return Decimal(value).normalize()
    except (InvalidOperation, ValueError):
        return None


def _norm_availability(value):
    value = _clean(value).split("/")[-1].replace("_", " ").replace("-", " ").lower().strip()
    compact = value.replace(" ", "")
    return AVAILABILITY.get(value) or AVAILABILITY.get(compact) or compact


def _valid_url(value):
    parsed = urlparse(_clean(value))
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _valid_gtin(value, length=None):
    digits = re.sub(r"\D", "", _clean(value))
    if len(digits) not in ((length,) if length else (8, 12, 13, 14)):
        return False
    total = sum(int(n) * (3 if (len(digits) - i) % 2 == 0 else 1)
                for i, n in enumerate(digits[:-1]))
    return (10 - total % 10) % 10 == int(digits[-1])


def _coalesce_ecommerce_findings(report, start):
    """One scored finding per rule, even across a large variant catalogue."""
    before, new = report.findings[:start], report.findings[start:]
    kept, counts = [], {}
    for finding in new:
        if finding.severity == "good" or finding.rule_id not in counts:
            counts[finding.rule_id] = len(kept)
            kept.append(finding)
            continue
        first = kept[counts[finding.rule_id]]
        marker = " Repeated on additional Product/Offer nodes."
        if marker.strip() not in first.detail:
            first.detail = first.detail.rstrip() + marker
    report.findings = before + kept


def _add_missing(report, field, severity, owner="Product"):
    field_id = re.sub(r"[^a-z0-9]+", ".", field.lower()).strip(".")
    report.add(CAT, severity, f"{owner} missing merchant property '{field}'",
               f"The {owner} markup has no usable {field} value.",
               f"Add {field} from the product page's real, current data.",
               rule_id=f"schema.ecommerce.{owner.lower()}.missing.{field_id}")


def _add_variant_missing(report, field, severity, products):
    labels = [_clean(p.get("sku")) or _clean(p.get("name")) or "unnamed variant" for p in products]
    field_id = re.sub(r"[^a-z0-9]+", ".", field.lower()).strip(".")
    report.add(CAT, severity, f"Product variant(s) missing merchant property '{field}'",
               f"Missing on {len(products)} Product node(s): {', '.join(labels[:8])}.",
               f"Populate {field} for each affected variant from its real product record.",
               evidence=", ".join(labels[:8]),
               rule_id=f"schema.ecommerce.product.missing.{field_id}")


def _offers(product, by_id):
    raw = product.get("offers")
    values = raw if isinstance(raw, list) else ([raw] if raw else [])
    out = []
    for value in values:
        if isinstance(value, dict) and set(value) == {"@id"}:
            value = by_id.get(value["@id"], value)
        if isinstance(value, dict):
            out.append(value)
    return out


def _select_product(products, visible):
    """Choose the schema variant supported by explicit visible identity."""
    visible_sku = _norm_text(visible.get("sku", {}).get("value"))
    if visible_sku:
        for product in products:
            if any(_norm_text(product.get(key)) == visible_sku for key in IDENTIFIERS):
                return product
    visible_name = _norm_text(visible.get("name", {}).get("value"))
    if visible_name:
        for product in products:
            name = _norm_text(product.get("name"))
            if name and (name in visible_name or visible_name in name):
                return product
    return products[0]


def _schema_fact(product, offers, field):
    if field == "price":
        keys = ("price", "lowPrice", "highPrice")
    elif field == "currency":
        keys = ("priceCurrency",)
    else:
        keys = (field,)
    for node in offers + [product]:
        for key in keys:
            value = node.get(key)
            if value in (None, "", []) and key in ("price", "priceCurrency"):
                spec = node.get("priceSpecification")
                specs = spec if isinstance(spec, list) else ([spec] if isinstance(spec, dict) else [])
                value = next((s.get(key) for s in specs if s.get(key) not in (None, "", [])), None)
            if value not in (None, "", []):
                return _clean(value), f"{_clean(node.get('@type')) or 'schema'}.{key}"
    return "", ""


def audit(doc, report, *, today=None):
    """Add product-scoped merchant findings and return serializable evidence."""
    finding_start = len(report.findings)
    nodes = schema_nodes(doc)
    detected = detect(doc, nodes)
    meta = {"is_product": detected["is_product"], "is_merchant": detected["is_merchant"],
            "confidence": detected["confidence"],
            "evidence": detected["evidence"], "visible_facts": detected["visible"]}
    if not detected["is_product"]:
        return meta
    products = detected["product_nodes"]
    if not products:
        report.add(CAT, "high", "Product page has no Product structured data",
                   "Strong product-page signals were found, but no Product JSON-LD, Microdata or supported RDFa was detected.",
                   "Add Product JSON-LD using only visible, current merchant facts.",
                   evidence="; ".join(detected["evidence"]),
                   rule_id="schema.ecommerce.product.missing")
        return meta

    by_id = {n.get("@id"): n for n in nodes if isinstance(n.get("@id"), str)}
    product = _select_product(products, detected["visible"])
    offers = _offers(product, by_id)
    all_product_offers = [(p, offer) for p in products for offer in _offers(p, by_id)]
    merchant = detected["is_merchant"]
    meta["is_merchant"] = merchant
    meta["product_nodes_count"] = len(products)
    meta["selected_product"] = _clean(product.get("sku")) or _clean(product.get("name"))
    meta["schema_offer_types"] = sorted({t for _, offer in all_product_offers for t in _types(offer)})

    required = (("name", "high"), ("image", "medium"), ("description", "low"),
                ("brand", "medium"), ("url", "low"))
    for field, severity in required:
        missing = [p for p in products if not _clean(p.get(field))]
        if missing:
            _add_variant_missing(report, field, severity, missing)
    missing_ids = [p for p in products if not any(_clean(p.get(key)) for key in IDENTIFIERS)]
    if missing_ids:
        _add_variant_missing(report, "sku/gtin/mpn", "low", missing_ids)
    missing_offers = [p for p in products if merchant and not _offers(p, by_id)]
    if missing_offers:
        _add_variant_missing(report, "offers", "high", missing_offers)
    invalid_product_urls = [p for p in products if p.get("url") and not _valid_url(p["url"])]
    if invalid_product_urls:
        report.add(CAT, "medium", "Product has invalid URL",
                   "One or more Product URLs are not absolute HTTP(S) URLs.",
                   "Use each variant's canonical absolute product URL.",
                   evidence=", ".join(_clean(p.get("url")) for p in invalid_product_urls[:8]),
                   rule_id="schema.ecommerce.product.invalid.url")
    for product_node in products:
        for key in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14"):
            value = product_node.get(key)
            expected = int(key[4:]) if key[4:].isdigit() else None
            if value and not _valid_gtin(value, expected):
                report.add(CAT, "medium", "Product has invalid GTIN",
                           f"{key}={_clean(value)!r} fails the expected length/check digit.",
                           "Correct the GTIN from the product system; never invent an identifier.",
                           evidence=f"{key}={_clean(value)}",
                           rule_id="schema.ecommerce.product.invalid.gtin")

    for offer_product, offer in all_product_offers:
        types = _types(offer)
        aggregate = "aggregateoffer" in types
        owner = "AggregateOffer" if aggregate else "Offer"
        if not any(t in ("offer", "aggregateoffer") for t in types):
            _add_missing(report, "@type", "medium", "Offer")
        if aggregate:
            for field, severity in (("lowPrice", "high"), ("highPrice", "medium"),
                                    ("priceCurrency", "high"), ("offerCount", "low")):
                if not _clean(offer.get(field)):
                    _add_missing(report, field, severity, owner)
        else:
            spec = offer.get("priceSpecification")
            specs = spec if isinstance(spec, list) else ([spec] if isinstance(spec, dict) else [])
            for field, severity in (("price", "high"), ("priceCurrency", "high")):
                if not _clean(offer.get(field)) and not any(_clean(s.get(field)) for s in specs):
                    _add_missing(report, field, severity, owner)
        for field in ("availability", "url", "itemCondition", "seller"):
            if not _clean(offer.get(field)):
                _add_missing(report, field, "low" if field != "availability" else "medium", owner)
        if offer.get("url") and not _valid_url(offer["url"]):
            report.add(CAT, "medium", f"{owner} has invalid URL",
                       f"Offer URL is not an absolute HTTP(S) URL: {_clean(offer['url'])}",
                       "Use the canonical absolute product/offer URL.",
                       evidence=_clean(offer["url"]), rule_id="schema.ecommerce.offer.invalid.url")
        valid_until = _clean(offer.get("priceValidUntil"))
        if valid_until:
            try:
                expired = date.fromisoformat(valid_until[:10]) < (today or date.today())
            except ValueError:
                expired = False
            if expired:
                report.add(CAT, "high", "Offer price validity date has expired",
                           f"priceValidUntil is {valid_until}.",
                           "Update the offer price and validity date, or remove a stale validity date.",
                           evidence=valid_until, rule_id="schema.ecommerce.offer.price.expired")
        price, _ = _schema_fact(offer_product, [offer], "price")
        if price and (_norm_price(price) is None or (merchant and _norm_price(price) <= 0)):
            report.add(CAT, "high", f"{owner} has invalid price",
                       f"The active price is {price!r}.",
                       "Provide a non-negative numeric price; merchant listings require a price greater than zero.",
                       evidence=price, rule_id="schema.ecommerce.offer.invalid.price")
        currency, _ = _schema_fact(offer_product, [offer], "currency")
        if currency and not re.fullmatch(r"[A-Za-z]{3}", currency):
            report.add(CAT, "high", f"{owner} has invalid price currency",
                       f"priceCurrency is {currency!r}.",
                       "Use the correct three-letter ISO 4217 currency code.",
                       evidence=currency, rule_id="schema.ecommerce.offer.invalid.currency")
        availability = _clean(offer.get("availability"))
        if availability and _norm_availability(availability) not in set(AVAILABILITY.values()):
            report.add(CAT, "medium", f"{owner} has invalid availability",
                       f"availability is {availability!r}.",
                       "Use the closest supported schema.org ItemAvailability value.",
                       evidence=availability, rule_id="schema.ecommerce.offer.invalid.availability")
        condition = _clean(offer.get("itemCondition"))
        if condition and condition.split("/")[-1].lower() not in ITEM_CONDITIONS:
            report.add(CAT, "medium", f"{owner} has invalid item condition",
                       f"itemCondition is {condition!r}.",
                       "Use the accurate schema.org OfferItemCondition value.",
                       evidence=condition, rule_id="schema.ecommerce.offer.invalid.condition")

    schema_offers = offers
    visible = detected["visible"]
    for field in ("price", "currency", "availability", "sku", "brand", "name"):
        if field not in visible:
            continue
        schema_value, schema_source = _schema_fact(product, schema_offers, field)
        observed = visible[field]
        if not schema_value:
            severity = "high" if field in ("price", "currency") else ("medium" if field in ("availability", "sku") else "low")
            report.add(CAT, severity, f"Visible product {field} missing from schema",
                       f"{observed['source']} exposes {observed['value']!r}, but Product/Offer markup does not.",
                       f"Add the same current {field} value to Product/Offer structured data.",
                       evidence=f"visible={observed['value']}",
                       rule_id=f"schema.ecommerce.visible.{field}.missing")
            continue
        if field == "price":
            mismatch = _norm_price(observed["value"]) is not None and _norm_price(schema_value) is not None and _norm_price(observed["value"]) != _norm_price(schema_value)
        elif field == "availability":
            mismatch = _norm_availability(observed["value"]) != _norm_availability(schema_value)
        elif field == "name":
            left, right = _norm_text(observed["value"]), _norm_text(schema_value)
            mismatch = bool(left and right and left not in right and right not in left)
        else:
            mismatch = _norm_text(observed["value"]) != _norm_text(schema_value)
        if mismatch:
            severity = "high" if field in ("price", "currency", "availability") else "medium"
            report.add(CAT, severity, f"Visible and schema {field} do not match",
                       f"{observed['source']} says {observed['value']!r}; {schema_source} says {schema_value!r}.",
                       "Make the rendered page and structured data use the same current product data source.",
                       evidence=f"visible={observed['value']}; schema={schema_value}",
                       rule_id=f"schema.ecommerce.{field}.mismatch")
    report.ok(CAT, "Product page merchant signals inspected",
              f"{len(products)} Product node(s), {len(all_product_offers)} offer object(s); visible comparisons were evidence-gated.")
    _coalesce_ecommerce_findings(report, finding_start)
    return meta
