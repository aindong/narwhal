"""Deterministic Product/Offer evidence extraction and merchant checks.

The module consumes only the normalized document plus its original HTML, so the
results do not depend on BeautifulSoup/lxml being installed. Visible/schema
comparisons are emitted only for explicit metadata, itemprop values, or labelled
page facts; an incidental number or currency word is not treated as a product.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from . import htmlx, merchant_source, microdata, structured_data, schema_coverage

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
    if isinstance(node, dict) and "@value" in node:
        return []
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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return htmlx.collapse(str(value))
    return htmlx.collapse(str(value or ""))


def _meta(doc, keys):
    for key in keys:
        for attr in ("property", "name"):
            for meta in doc.merchant_markup["meta"]:
                if (meta.get(attr) or "").lower() == key.lower() and meta.get("content"):
                    return _clean(meta["content"]), f"meta[{key}]"
    return "", ""


def _attr_value(doc, itemprop):
    value = doc.merchant_markup["itemprops"].get(itemprop, "")
    return (value, f"itemprop={itemprop}") if value else ("", "")


def _label(text, label):
    # A vocabulary definition ("SKU Text ...") is not a labelled page fact.
    # Prefer under-reporting unmarked prose to inventing identity/stock values.
    match = re.search(r"\b" + label + r"\s*[:#]\s*([A-Za-z0-9][A-Za-z0-9 ._/-]{0,60})", text or "", re.I)
    if not match:
        return "", ""
    value = match.group(1).strip()
    # Stop before common next-label boundaries in collapsed page text.
    value = re.split(r"\s+(?:price|availability|brand|sku|mpn|gtin)\s*[:#]", value, maxsplit=1, flags=re.I)[0]
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
            value, source = _attr_value(doc, itemprop)
        if value:
            facts[key] = {"value": value, "source": source, "confidence": 1.0}
    for key, label in (("brand", "brand"), ("sku", "sku"), ("availability", "availability")):
        if key not in facts:
            value, source = _label(doc.merchant_markup["text"], label)
            if value:
                facts[key] = {"value": value, "source": source, "confidence": 0.9}
    h1 = doc.merchant_markup["h1"]
    if h1:
        facts["name"] = {"value": h1, "source": "visible H1", "confidence": 0.85}
    return facts


def _purchase_action(doc):
    """A real, enabled purchase control, not a phrase in review prose.

    Explicit hidden/inert subtrees and external affiliate links are excluded.
    This is source evidence, not a computed CSS visibility or checkout test.
    """
    return bool(doc.merchant_markup["purchase_action"] and not doc.merchant_markup["warnings"])


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
    if merchant_source.meta_property(doc.merchant_markup, "og:type").strip().lower() == "product":
        evidence.append("og:type=product")
    visible = visible_facts(doc)
    observed = sorted(set(visible) & {"price", "currency", "availability", "sku"})
    # Identifiers describe a product, not whether this publisher sells it.
    merchant = sorted(set(observed) - {"sku"})
    if merchant:
        evidence.append("explicit merchant facts: " + ", ".join(observed))
    elif "sku" in observed:
        evidence.append("explicit product identity: sku")
    is_product = bool(product_nodes) or htmlx.looks_product(doc)
    has_offer = any(value and not (isinstance(value, dict) and "@value" in value)
                    for n in product_nodes for value in _offer_values(n))
    purchase_action = is_product and not (has_offer or merchant) and _purchase_action(doc)
    is_merchant = bool(is_product and (has_offer or merchant or purchase_action))
    if is_merchant and purchase_action and not (has_offer or merchant):
        evidence.append("visible purchase action")
    confidence = 1.0 if product_nodes else (0.9 if "Product microdata" in evidence else (0.8 if is_product else 0.0))
    return {"is_product": is_product, "is_merchant": is_merchant,
            "confidence": confidence, "evidence": evidence,
            "product_nodes": product_nodes, "visible": visible}


def _norm_text(value):
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _norm_identifier(value):
    # Identity punctuation and non-ASCII characters are significant.
    return _clean(value).casefold()


def _norm_price(value):
    # Schema amounts are not localized display strings. Keep exact decimals;
    # normalize() rounds to the caller's Decimal context before removing zeros.
    return _range_number(_clean(value))


def _norm_availability(value):
    value = _clean(value).split("/")[-1].replace("_", " ").replace("-", " ").lower().strip()
    compact = value.replace(" ", "")
    return AVAILABILITY.get(value) or AVAILABILITY.get(compact) or compact


def _valid_url(value):
    # This is local syntax validation, never DNS/reachability validation.
    value = _clean(value)
    if re.search(r"[\s\x00-\x1f\x7f\\]", value):
        return False
    try:
        parsed = urlparse(value)
        # Accessing port also validates numeric syntax and the 0..65535 range.
        parsed.port
        host = parsed.hostname
        authority = parsed.netloc.rsplit("@", 1)[-1]
        if "[" in authority or "]" in authority:
            if not re.fullmatch(r"\[[^\[\]]+\](?::[0-9]*)?", authority) or not host:
                return False
            # Older supported Python versions do not validate bracketed hosts.
            # Preserve RFC 3986 IPvFuture syntax; otherwise require
            # IPv6 (not bracketed IPv4), allowing a nonempty zone identifier.
            if host.startswith("v"):
                if not re.fullmatch(r"v[a-f0-9]+\.[a-z0-9._~!$&'()*+,;=:-]+", host, re.I):
                    return False
            else:
                address, separator, zone = host.partition("%")
                if separator and not zone:
                    return False
                ipaddress.IPv6Address(address)
        return parsed.scheme in ("http", "https") and bool(host)
    except ValueError:
        # Malformed brackets/IPv6, invalid ports and unsafe netloc normalization
        # must become an invalid-URL finding, not terminate the entire scan.
        return False


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


def _offer_values(product):
    raw = product.get("offers")
    return raw if isinstance(raw, list) else ([raw] if raw else [])


def _offers(product, by_id):
    values = _offer_values(product)
    out = []
    for value in values:
        if isinstance(value, dict) and set(value) == {"@id"} and isinstance(value["@id"], str):
            value = by_id.get(value["@id"], value)
        if isinstance(value, dict) and "@value" not in value:
            out.append(value)
    return out


def _select_product(products, visible):
    """Choose only a uniquely identified variant, never the first of many."""
    if len(products) == 1:
        return products[0], "single_product"
    visible_sku = _norm_identifier(visible.get("sku", {}).get("value"))
    if visible_sku:
        matches = [p for p in products if any(_norm_identifier(p.get(key)) == visible_sku for key in IDENTIFIERS)]
        if len(matches) == 1:
            return matches[0], "visible_identifier"
        if matches:
            return None, "ambiguous_identifier"
    visible_name = _norm_text(visible.get("name", {}).get("value"))
    if visible_name:
        exact = [p for p in products if _norm_text(p.get("name")) == visible_name]
        if len(exact) == 1:
            return exact[0], "visible_name_exact"
        if exact:
            return None, "ambiguous_name"
        matches = [p for p in products if _norm_text(p.get("name")) and
                   (_norm_text(p.get("name")) in visible_name or visible_name in _norm_text(p.get("name")))]
        if len(matches) == 1:
            return matches[0], "visible_name_unique"
        if matches:
            return None, "ambiguous_name"
    return None, "unmatched_identity"


def _price_specs(node):
    value = node.get("priceSpecification")
    return [s for s in (value if isinstance(value, list) else [value]) if isinstance(s, dict)]


def _schema_fact(product, offers, field):
    if field == "price":
        keys = ("price", "lowPrice", "highPrice")
    elif field == "currency":
        keys = ("priceCurrency",)
    else:
        keys = (field,)
    # The page H1 names the selected Product, not a sale/seller Offer label.
    # Do not let Offer.name mask a missing or conflicting Product.name.
    owners = [product] if field == "name" else offers + [product]
    for node in owners:
        for key in keys:
            value = node.get(key)
            if value in (None, "", []) and key in ("price", "priceCurrency"):
                specs = _price_specs(node)
                value = next((s.get(key) for s in specs if s.get(key) not in (None, "", [])), None)
            if value not in (None, "", []):
                return _clean(value), f"{_clean(node.get('@type')) or 'schema'}.{key}"
    return "", ""


def _range_number(value):
    """Read a scalar decimal bound without stripping units or rounding it.

    schema.org permits Text as well as Number. Unsupported text is not a
    numeric proof; callers report partial comparison coverage rather than
    claiming all such text is invalid schema.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    text = str(value).strip()
    if len(text) > 512 or not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
        return None
    try:
        number = Decimal(text)
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _range_observed_price(value, currency):
    text = _clean(value)
    if len(text) > 512:
        return None
    match = re.fullmatch(r"([A-Za-z]{3}|[$€£¥])?\s*([+-]?[0-9][0-9.,]*)\s*([A-Za-z]{3}|[$€£¥])?", text)
    if not match:
        return None
    # A written unit must not contradict explicit currency metadata. Symbols
    # shared by several currencies remain compatible, not unit inference.
    symbols = {"$": {"USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN", "ARS", "CLP", "COP", "BBD", "BMD", "BND", "BSD", "BZD", "FJD", "GYD", "JMD", "KYD", "LRD", "NAD", "SBD", "SRD", "TTD", "TWD", "XCD"},
               "€": {"EUR"}, "£": {"GBP", "GIP", "FKP", "SHP"}, "¥": {"JPY", "CNY"}}
    for unit in (match.group(1), match.group(3)):
        if unit and currency.upper() not in symbols.get(unit, {unit.upper()}):
            return None
    text = match.group(2)
    if "," in text and "." not in text and re.search(r",\d{1,2}$", text):
        if not re.fullmatch(r"[+-]?[0-9]+,[0-9]{1,2}", text):
            return None
        text = text.replace(",", ".")
    elif "," in text:
        if not re.fullmatch(r"[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?", text):
            return None
        text = text.replace(",", "")
    return _range_number(text)


def _aggregate_range(offer, visible):
    low, high = (_range_number(offer.get(key)) for key in ("lowPrice", "highPrice"))
    raw_currency = offer.get("priceCurrency")
    currency = raw_currency.strip() if isinstance(raw_currency, str) else ""
    observed_currency = _clean(visible.get("currency", {}).get("value"))
    observed = _range_observed_price(visible.get("price", {}).get("value"), currency)
    if (low is None or high is None or low < 0 or high < low or observed is None
            or not re.fullmatch(r"[A-Za-z]{3}", currency)
            or currency.casefold() != observed_currency.casefold()):
        return None
    return low, high, observed, currency


def _comparison_fact(product, offers, field, visible):
    """Offer order is not evidence for selecting a seller's price or stock."""
    if field not in {"price", "currency", "availability"} or len(offers) <= 1:
        value, source = _schema_fact(product, offers, field)
        return value, source, "ready"
    values = [_schema_fact({}, [offer], field) for offer in offers]
    if not any(value for value, _ in values):
        value, source = _schema_fact(product, [], field)
        return value, source, "ready"
    if not all(value for value, _ in values):
        return "", "", "skipped_ambiguous"
    if field == "price":
        # Equal numbers are not a monetary consensus across different/unknown
        # currencies. Nor is an AggregateOffer's lower bound a selected price.
        currencies = [_schema_fact({}, [offer], "currency")[0] for offer in offers]
        observed_currency = _clean(visible.get("currency", {}).get("value"))
        if (not all(currencies) or len({_clean(c).casefold() for c in currencies}) != 1
                or not observed_currency or observed_currency.casefold() != _clean(currencies[0]).casefold()
                or any("aggregateoffer" in _types(offer) for offer in offers)):
            return "", "", "skipped_ambiguous"
        normalized = {_norm_price(value) for value, _ in values}
    elif field == "availability":
        normalized = {_norm_availability(value) for value, _ in values}
    else:
        normalized = {_clean(value).casefold() for value, _ in values}
    if None in normalized or len(normalized) != 1:
        return "", "", "skipped_ambiguous"
    return values[0][0], f"{values[0][1]} consensus ({len(offers)} Offer objects)", "ready"


def audit(doc, report, *, today=None):
    """Add product-scoped merchant findings and return serializable evidence."""
    finding_start = len(report.findings)
    records, errors = structured_data.collect(doc)
    nodes = [record['node'] for record in records]
    detected = detect(doc, nodes)
    meta = {"is_product": detected["is_product"], "is_merchant": detected["is_merchant"],
            "confidence": detected["confidence"],
            "evidence": detected["evidence"], "visible_facts": detected["visible"],
            "source_warnings": doc.merchant_markup["warnings"]}
    if meta["source_warnings"]:
        report.add(CAT, "low", "Merchant source evidence needs verification",
                   "\n".join(meta["source_warnings"]),
                   ("Verify the rendered page; source evidence is bounded and may be partial. "
                    + microdata.warning_summary(meta["source_warnings"])).strip(),
                   rule_id="schema.ecommerce.source.extraction")
    if not detected["is_product"]:
        return meta
    products = detected["product_nodes"]
    if not products:
        if schema_coverage.state(schema_coverage.observe(doc, errors)) == 'no_known_problem' and not meta['source_warnings']:
            report.add(CAT, "high", "Product page has no Product structured data",
                       "Product-page signals were found, but no Product type was observed in the supported subset; "
                       "this is not exhaustive absence or Google merchant eligibility.",
                       "Review existing markup before adding an applicable Product entity using real visible, current facts. "
                       "Preserve valid JSON-LD, Microdata or RDFa; do not duplicate entities or promise rich results.",
                       evidence="; ".join(detected["evidence"]),
                       rule_id="schema.ecommerce.product.missing")
        return meta

    by_id = {n.get("@id"): n for n in nodes if isinstance(n.get("@id"), str)}
    product, selection = _select_product(products, detected["visible"])
    offers = _offers(product, by_id) if product is not None else []
    all_product_offers = [(p, offer) for p in products for offer in _offers(p, by_id)]
    merchant = detected["is_merchant"]
    meta["is_merchant"] = merchant
    meta["product_nodes_count"] = len(products)
    meta["selected_product"] = (_clean(product.get("sku")) or _clean(product.get("name"))) if product is not None else None
    meta["comparison_status"] = "ready" if product is not None else "skipped_ambiguous"
    meta["selection_method"] = selection
    meta["schema_offer_types"] = sorted({t for _, offer in all_product_offers for t in _types(offer)})
    if product is None:
        report.add(CAT, "low", "Product comparison identity needs verification",
                   f"No unique Product matches the visible identity among {len(products)} nodes ({selection}). "
                   "Completeness and validity checks still cover all nodes; page-versus-schema comparisons are skipped.",
                   "Expose the selected variant's stable identifier or unambiguous name. Verify which Product/Offer supplies page facts before editing prices.",
                   rule_id="schema.ecommerce.comparison.ambiguous")

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
        if offer.get("@id") is not None and not isinstance(offer["@id"], str):
            report.add(CAT, "medium", "Offer has invalid local reference",
                       "The Offer @id is not a string; it cannot identify or resolve a local Offer node.",
                       "Use a string node identifier and include the referenced Offer data in the page. No remote reference is fetched.",
                       rule_id="schema.ecommerce.offer.invalid.reference")
        spec = offer.get("priceSpecification")
        if ((spec is not None and not isinstance(spec, (dict, list)))
                or (isinstance(spec, list) and any(s is not None and not isinstance(s, dict) for s in spec))):
            report.add(CAT, "low", "Price specification evidence needs verification",
                       "priceSpecification contains a non-object value; this bounded parser reads only inline object members as price/currency evidence.",
                       "Verify the PriceSpecification shape and JSON-LD context. Unsupported values are skipped; supported object members are still inspected.",
                       rule_id="schema.ecommerce.offer.price_specification.extraction")
        aggregate = "aggregateoffer" in types
        owner = "AggregateOffer" if aggregate else "Offer"
        if not any(t in ("offer", "aggregateoffer") for t in types):
            _add_missing(report, "@type", "medium", "Offer")
        if aggregate:
            for field, severity in (("lowPrice", "high"), ("highPrice", "medium"),
                                    ("priceCurrency", "high"), ("offerCount", "low")):
                if not _clean(offer.get(field)):
                    _add_missing(report, field, severity, owner)
            low, high = (_range_number(offer.get(key)) for key in ("lowPrice", "highPrice"))
            if ((low is not None and low < 0) or (high is not None and high < 0)
                    or (low is not None and high is not None and high < low)):
                report.add(CAT, "high", "AggregateOffer has contradictory price bounds",
                           f"lowPrice={offer.get('lowPrice')!r}; highPrice={offer.get('highPrice')!r}.",
                           "Use non-negative bounds with lowPrice no greater than highPrice, from the current offers.",
                           rule_id="schema.ecommerce.offer.invalid.range")
        else:
            specs = _price_specs(offer)
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
        number = _norm_price(price) if price else None
        if price and number is None:
            report.add(CAT, "low", f"{owner} price evidence needs verification",
                       f"The active price {price!r} is outside the bounded numeric parser; no amount is inferred by stripping text or separators.",
                       "Verify the current numeric Offer price and priceCurrency at source. Unsupported Text or shapes are not a full schema.org invalidity verdict; numeric comparison is skipped.",
                       evidence=price, rule_id="schema.ecommerce.offer.price.extraction")
        elif price and (number < 0 or (merchant and number <= 0)):
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

    visible = detected["visible"]
    skipped_offer_fields = []
    meta["offer_comparison_status"] = {}
    comparison_fields = ("price", "currency", "availability", "sku", "brand", "name") if product is not None else ()
    for field in comparison_fields:
        if field not in visible:
            continue
        if field == "price" and len(offers) == 1 and "aggregateoffer" in _types(offers[0]):
            price_range = _aggregate_range(offers[0], visible)
            meta["offer_comparison_status"][field] = "ready" if price_range else "skipped_ambiguous"
            if price_range is None:
                skipped_offer_fields.append(field)
                continue
            low, high, observed_price, currency = price_range
            meta["aggregate_price_comparison"] = {
                "method": "inclusive_range", "lowPrice": str(low), "highPrice": str(high),
                "currency": currency, "within_range": low <= observed_price <= high,
                "scope": "range compatibility, not selected seller or exact Offer existence",
            }
            if not low <= observed_price <= high:
                observed = visible[field]
                report.add(CAT, "high", "Visible price is outside the schema offer range",
                           f"{observed['source']} says {observed['value']!r}; AggregateOffer declares {low}–{high} {currency}.",
                           "Verify the current offers and displayed price; update the range or page from the same current product data source.",
                           evidence=f"visible={observed['value']}; lowPrice={low}; highPrice={high}; currency={currency}",
                           rule_id="schema.ecommerce.price.mismatch")
            continue
        schema_value, schema_source, comparison = _comparison_fact(product, offers, field, visible)
        if field in {"price", "currency", "availability"}:
            meta["offer_comparison_status"][field] = comparison
        if comparison == "skipped_ambiguous":
            skipped_offer_fields.append(field)
            continue
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
            schema_currency = _schema_fact(product, offers, "currency")[0]
            observed_currency = _clean(visible.get("currency", {}).get("value"))
            declared_price = _norm_price(schema_value)
            observed_price = _range_observed_price(observed["value"], schema_currency)
            if (declared_price is None or observed_price is None
                    or not re.fullmatch(r"[A-Za-z]{3}", schema_currency)
                    or schema_currency.casefold() != observed_currency.casefold()):
                meta["offer_comparison_status"][field] = "skipped_ambiguous"
                skipped_offer_fields.append(field)
                continue
            meta["point_price_comparison"] = {
                "method": "exact_decimal", "schema_price": str(declared_price),
                "observed_price": str(observed_price), "currency": schema_currency,
                "scope": "amount comparison, not selected seller or full price-component validation",
            }
            mismatch = observed_price != declared_price
        elif field == "availability":
            mismatch = _norm_availability(observed["value"]) != _norm_availability(schema_value)
        elif field == "name":
            left, right = _norm_text(observed["value"]), _norm_text(schema_value)
            mismatch = bool(left and right and left not in right and right not in left)
        elif field == "sku":
            mismatch = _norm_identifier(observed["value"]) != _norm_identifier(schema_value)
        else:
            mismatch = _norm_text(observed["value"]) != _norm_text(schema_value)
        if mismatch:
            severity = "high" if field in ("price", "currency", "availability") else "medium"
            report.add(CAT, severity, f"Visible and schema {field} do not match",
                       f"{observed['source']} says {observed['value']!r}; {schema_source} says {schema_value!r}.",
                       "Make the rendered page and structured data use the same current product data source.",
                       evidence=f"visible={observed['value']}; schema={schema_value}",
                       rule_id=f"schema.ecommerce.{field}.mismatch")
    if skipped_offer_fields:
        fields = ", ".join(skipped_offer_fields)
        report.add(CAT, "low", "Offer comparison scope needs verification",
                   f"{len(offers)} Offer objects do not establish comparable {fields} evidence (non-unique, incomplete, unsupported numeric text, range or unmatched currency units). No source-order Offer is selected for these comparisons.",
                   f"Verify the source Offer for {fields}; these comparisons were skipped. Other agreed Offer values and Product identity are still checked.",
                   rule_id="schema.ecommerce.offer.comparison.ambiguous")
    comparison_note = "visible comparisons were evidence-gated." if product is not None else "visible comparisons were skipped because Product identity is ambiguous."
    if skipped_offer_fields:
        comparison_note += " Ambiguous Offer fields skipped: " + ", ".join(skipped_offer_fields) + "."
    report.ok(CAT, "Product page merchant signals inspected",
              f"{len(products)} Product node(s), {len(all_product_offers)} offer object(s); {comparison_note}")
    _coalesce_ecommerce_findings(report, finding_start)
    return meta
