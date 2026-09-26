"""Z.ai's GLM API rates, international, in dollars per million tokens.

Read off https://docs.z.ai/guides/overview/pricing on 26 September 2026,
twice, independently. The page is plain markdown, so --check-prices reads it
exactly.

**Published, not measured.** Nobody has yet compared these with a real Z.ai
bill. Please do, and open an issue either way.

Rules taken from the page and modelled here:

  - Cached input has its own published rate per model, from the pricing
    table. (Z.ai's caching guide says hits are "usually 50%"; the table's
    per-model figures are lower, and the table is what bills.)
  - No cache write charge. Cache storage is "Limited-time Free" and is not
    modelled either way.
  - GLM-4.7-Flash and GLM-4.5-Flash are free.
  - No long-context tier.
"""

import re

PROVIDER = "zai"
NAME = "Z.ai"
SOURCE = "https://docs.z.ai/guides/overview/pricing"
SOURCE_MD = "https://docs.z.ai/guides/overview/pricing.md"
VERIFIED_ON = "2026-09-26"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 0.0
SNAPSHOT = r"(?!)"


def _row(inp, out, cached=None):
    mult = (cached / inp) if (cached is not None and inp) else (0.0 if not inp else 1.0)
    return [{"from": "", "in": inp, "out": out, "cache_read_mult": mult, "fast": None}]


PRICES = {
    "glm-5.3":             _row(1.40, 4.40, 0.26),
    "glm-5.3-flash":       _row(0.15, 0.50, 0.03),
    "glm-5.3-flashx":      _row(0.37, 1.25, 0.075),
    "glm-5.2":             _row(1.40, 4.40, 0.26),
    "glm-5.1":             _row(1.40, 4.40, 0.26),
    "glm-5":               _row(1.00, 3.20, 0.20),
    "glm-4.7":             _row(0.60, 2.20, 0.11),
    "glm-4.7-flashx":      _row(0.07, 0.40, 0.01),
    "glm-4.7-flash":       _row(0.0, 0.0),
    "glm-4.6":             _row(0.60, 2.20, 0.11),
    "glm-4.5":             _row(0.60, 2.20, 0.11),
    "glm-4.5-x":           _row(2.20, 8.90, 0.45),
    "glm-4.5-air":         _row(0.20, 1.10, 0.03),
    "glm-4.5-airx":        _row(1.10, 4.50, 0.22),
    "glm-4.5-flash":       _row(0.0, 0.0),
    "glm-4-32b-0414-128k": _row(0.10, 0.10),
}

FALLBACK_MODEL = "glm-5.3"


def _money(cell):
    if cell.strip().lower() == "free":
        return 0.0
    m = re.search(r"\$([\d.]+)", cell)
    return float(m.group(1)) if m else None


def page_rates(fetch, tables, want=None):
    rates, seen = {}, []
    for title, header, rows in tables(fetch(SOURCE_MD)):
        if not title.lower().startswith(("latest models", "text models")):
            continue
        h = [c.strip().lower() for c in header]
        if h[:3] != ["model", "input", "cached input"]:
            continue
        for r in rows:
            mid = r[0].strip().lower()
            seen.append(mid)
            inp, cached, out = _money(r[1]), _money(r[2]), _money(r[4])
            rates[mid] = {"in": inp, "out": out, "cached": inp if cached is None else cached}
    return rates, sorted(m for m in set(seen) if m not in PRICES)
