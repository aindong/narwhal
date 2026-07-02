"""Image weight/format checks and og:image validation.

Oversized or legacy-format images are a top LCP cause, missing width/height
attributes cause layout shift (CLS), and a broken/undersized ``og:image``
silently kills social and chat-app previews. This module checks all of that
within a strict budget: one HEAD per image (capped count, headers only) and a
single ranged GET (~64 KB) to probe the og:image's dimensions — never whole
files. All network goes through the SSRF-guarded helpers; the network functions
are injectable so the logic is fully offline-testable.
"""

from __future__ import annotations

import struct
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from . import http
from .links import UNDETERMINED

MAX_IMAGES = 10            # HEAD budget per page
HEAVY_KB = 200             # a page image above this is "heavy"
VERY_HEAVY_KB = 500        # above this the finding escalates
LEGACY_MIN_KB = 100        # only nag jpeg/png->AVIF/WebP when there's real weight
PROBE_BYTES = 65536        # ranged GET size for og:image dimensions
OG_MIN = 200               # below this (either side) previews break
OG_RECOMMENDED_W = 1200    # large-card recommendation (1200x630)

_IMG_TYPES = ("image/", )
_LEGACY_TYPES = ("image/jpeg", "image/png")


def probe_dimensions(data: bytes):
    """Width/height from the first bytes of a PNG/GIF/JPEG/WebP file, else None.

    Header-only parsing on a partial download — no imaging library needed."""
    if not data or len(data) < 24:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":                      # PNG: IHDR at 16
        w, h = struct.unpack(">II", data[16:24])
        return (w, h)
    if data[:6] in (b"GIF87a", b"GIF89a"):                     # GIF: LE at 6
        w, h = struct.unpack("<HH", data[6:10])
        return (w, h)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":          # WebP variants
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return (w, h)
        if chunk == b"VP8 " and len(data) >= 30:
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return (w, h)
        if chunk == b"VP8L" and len(data) >= 25:
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        return None
    if data[:2] == b"\xff\xd8":                                # JPEG: scan SOFn
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (w, h)
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg_len
        return None
    return None


def audit_images(doc, base_url: str, *, allow_private=False, timeout=8,
                 max_images=MAX_IMAGES, head_info=None, fetch_range=None) -> dict:
    """Collect image facts for a page (network-capped; helpers injectable)."""
    head_info = head_info or http.head_info
    fetch_range = fetch_range or http.fetch_range

    # --- pure facts from the markup -----------------------------------------
    srcs, missing_dims = [], 0
    seen = set()
    srcset_map = {}
    for img in doc.images:
        src = (img.get("src") or "").strip()
        if not (img.get("width") and img.get("height")):
            missing_dims += 1
        if not src or src.startswith("data:"):
            continue
        full = urljoin(base_url, src)
        if full.startswith("http") and full not in seen:
            seen.add(full)
            srcs.append(full)
            srcset_map[full] = bool(img.get("srcset"))

    # --- weight/format via HEAD (parallel, capped) --------------------------
    checked = []
    targets = srcs[:max_images]
    if targets:
        def one(u):
            status, headers, err = head_info(u, timeout=timeout,
                                             allow_private=allow_private)
            size = headers.get("content-length")
            return {"url": u, "status": status,
                    "type": (headers.get("content-type") or "").split(";")[0],
                    "kb": round(int(size) / 1024) if (size or "").isdigit() else None,
                    "srcset": srcset_map.get(u, False)}
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
            checked = list(ex.map(one, targets))

    heavy = sorted((c for c in checked if (c["kb"] or 0) >= HEAVY_KB),
                   key=lambda c: -c["kb"])
    legacy = [c for c in checked if c["type"] in _LEGACY_TYPES
              and (c["kb"] or 0) >= LEGACY_MIN_KB]

    # --- og:image validation -------------------------------------------------
    og = {"present": False}
    og_url = doc.meta_by_property("og:image")
    if og_url:
        og_full = urljoin(base_url, og_url.strip())
        og = {"present": True, "url": og_full, "status": 0, "is_image": False,
              "dimensions": None}
        status, headers, err = head_info(og_full, timeout=timeout,
                                         allow_private=allow_private)
        og["status"] = status
        ctype = (headers.get("content-type") or "").split(";")[0]
        og["is_image"] = status == 200 and ctype.startswith(_IMG_TYPES)
        if og["is_image"]:
            data, _ = fetch_range(og_full, PROBE_BYTES, timeout=timeout,
                                  allow_private=allow_private)
            og["dimensions"] = probe_dimensions(data or b"")

    return {"total_imgs": len(doc.images), "missing_dims": missing_dims,
            "checked": len(checked), "unchecked": max(0, len(srcs) - len(targets)),
            "heavy": heavy, "legacy": legacy, "og_image": og}


def findings(facts: dict, report) -> None:
    """Emit technical findings from :func:`audit_images` facts."""
    cat = "technical"

    heavy = facts["heavy"]
    if heavy:
        worst = heavy[0]
        all_srcset = all(h.get("srcset") for h in heavy)
        # Weight is measured on the raw `src` (no Accept header). With srcset,
        # real browsers usually download smaller/modern variants — the raw src
        # is the fallback scrapers and non-srcset clients get. Overstating that
        # as the user experience was a live-audit lesson; say what was measured.
        sev = "medium" if worst["kb"] >= VERY_HEAVY_KB or len(heavy) >= 3 else "low"
        if all_srcset:
            sev = "low"
        listing = ", ".join(f"{h['url'].rsplit('/', 1)[-1]} ({h['kb']} KB)"
                            for h in heavy[:4])
        report.add(cat, sev, f"Heavy images ({len(heavy)} over {HEAVY_KB} KB)",
                   f"Largest: {worst['kb']} KB. Checked {facts['checked']} of "
                   f"{facts['checked'] + facts['unchecked']} images (HEAD on the "
                   "raw src)."
                   + (" All carry srcset, so browsers likely fetch smaller "
                      "variants — this is the fallback weight." if all_srcset
                      else ""),
                   "Compress/resize and serve modern formats (AVIF/WebP); heavy "
                   "images are a top LCP cause."
                   + (" Also lighten the src fallback (it's what scrapers and "
                      "srcset-unaware clients download)." if all_srcset else ""),
                   evidence=listing)
    elif facts["checked"]:
        report.ok(cat, "No heavy images detected",
                  f"{facts['checked']} checked, all under {HEAVY_KB} KB")

    if facts["legacy"]:
        listing = ", ".join(f"{l['url'].rsplit('/', 1)[-1]} ({l['kb']} KB, "
                            f"{l['type'].split('/')[-1]})"
                            for l in facts["legacy"][:4])
        report.add(cat, "low",
                   f"Legacy image formats with real weight "
                   f"({len(facts['legacy'])})",
                   "JPEG/PNG files over 100 KB that AVIF/WebP would shrink "
                   "substantially.",
                   "Serve AVIF/WebP with <picture> or content negotiation.",
                   evidence=listing)

    total = facts["total_imgs"]
    if total >= 3 and facts["missing_dims"] / total > 0.3:
        report.add(cat, "low",
                   "Images without width/height attributes",
                   f"{facts['missing_dims']} of {total} <img> tags lack explicit "
                   "dimensions.",
                   "Add width/height (or CSS aspect-ratio) so the browser "
                   "reserves space — prevents layout shift (CLS).")

    og = facts["og_image"]
    if og.get("present"):
        if og["status"] in UNDETERMINED:
            # Rate-limited / bot-gated (429, 403…) is NOT broken — social
            # platforms fetching with their own agents usually get through.
            # (Found as a false positive on a rate-limiting CDN in tuning.)
            report.add(cat, "low", "og:image could not be verified",
                       f"HTTP {og['status']} (gated/rate-limited) at {og['url']}.",
                       "Likely fine — the host throttles bots. Confirm the "
                       "preview in a social-card debugger.")
        elif not og["is_image"]:
            report.add(cat, "high", "og:image is broken",
                       f"HTTP {og['status']} or non-image content at {og['url']}.",
                       "Point og:image at a reachable image — broken previews "
                       "suppress clicks everywhere links are shared.")
        elif og.get("dimensions"):
            w, h = og["dimensions"]
            if w < OG_MIN or h < OG_MIN:
                report.add(cat, "medium", "og:image is too small",
                           f"{w}x{h}px — below the {OG_MIN}px minimum many "
                           "platforms enforce.",
                           "Use a ~1200x630 image for large link cards.")
            elif w < OG_RECOMMENDED_W:
                report.add(cat, "low", "og:image below large-card size",
                           f"{w}x{h}px.",
                           f"Serve ~{OG_RECOMMENDED_W}x630 to get the large "
                           "preview card on social platforms.")
            else:
                report.ok(cat, "og:image looks healthy", f"{w}x{h}px, reachable")
        else:
            report.ok(cat, "og:image reachable",
                      "dimensions unreadable from a partial fetch — verify the "
                      "card in a preview debugger")