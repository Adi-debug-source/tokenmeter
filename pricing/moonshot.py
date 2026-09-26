"""Moonshot AI's Kimi API rates, international, in dollars per million tokens.

Read off https://platform.kimi.ai/docs/pricing/chat.md (where
platform.moonshot.ai now redirects) on 26 September 2026, twice,
independently.

**Published, not measured.** Nobody has yet compared these with a real Kimi
bill. Please do, and open an issue either way.

Rules taken from the page and modelled here:

  - Kimi K3 bills cache writes by lifetime: the 5-minute tier at the input
    rate and the 1-hour tier at twice it. A cache hit bills only at the
    cached rate.
  - The K2 models bill no cache write; a miss is ordinary input.
  - No long-context tier.
"""

import re

PROVIDER = "moonshot"
NAME = "Moonshot"
SOURCE = "https://platform.kimi.ai/docs/pricing/chat"
SOURCE_MD = "https://platform.kimi.ai/docs/pricing/chat.md"
VERIFIED_ON = "2026-09-26"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 0.0
SNAPSHOT = r"(?!)"

PRICES = {
    "kimi-k3": [{"from": "", "in": 3.00, "out": 15.00, "cache_read_mult": 0.1, "fast": None,
                 "write_mult": 1.0, "write_1h_mult": 2.0}],
    "kimi-k2.7-code":           [{"from": "", "in": 0.95, "out": 4.00, "cache_read_mult": 0.19 / 0.95, "fast": None}],
    "kimi-k2.7-code-highspeed": [{"from": "", "in": 1.90, "out": 8.00, "cache_read_mult": 0.38 / 1.90, "fast": None}],
    "kimi-k2.6":                [{"from": "", "in": 0.95, "out": 4.00, "cache_read_mult": 0.16 / 0.95, "fast": None}],
}

FALLBACK_MODEL = "kimi-k3"


def page_rates(fetch, tables, want=None):
    """Rates from the page's table rows, which are written as JavaScript
    arrays. K3 rows list five prices (5-minute write, 1-hour write, cached,
    input, output); K2 rows list three (cached, input, output)."""
    rates, seen = {}, []
    for mid, rest in re.findall(r'\["(kimi-[a-z0-9.\-]+)",\s*"1M tokens",(.*?)\]', fetch(SOURCE_MD)):
        v = [float(x) for x in re.findall(r'\{"\$"\}([\d.]+)', rest)]
        seen.append(mid)
        if len(v) == 5:
            rates[mid] = {"write_5m": v[0], "write_1h": v[1], "cached": v[2], "in": v[3], "out": v[4]}
        elif len(v) == 3:
            rates[mid] = {"cached": v[0], "in": v[1], "out": v[2]}
    return rates, sorted(m for m in set(seen) if m not in PRICES)
