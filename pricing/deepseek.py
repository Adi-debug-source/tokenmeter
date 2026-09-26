"""DeepSeek's first-party API rates, in dollars per million tokens.

Read off https://api-docs.deepseek.com/quick_start/pricing on 26 September
2026, twice, independently. Only two models are sold.

**Published, not measured.** Nobody has yet compared these with a real
DeepSeek bill. Please do, and open an issue either way.

Rules taken from the page and modelled here:

  - Peak and off-peak. The table holds the peak rate, the standard one. "Off-
    peak rates are half of the peak rates. Peak hours are 01:00 - 04:00 and
    06:00 - 10:00 UTC, Monday through Friday", so a call outside those hours
    is priced at half. Every call has a timestamp, so this is exact, with one
    gap: Chinese public holidays are off-peak all day and are not modelled,
    which can only overstate.
  - Cache hits have their own rate. Building the cache is free: a miss is
    ordinary input.
  - No long-context tier, no web search.

The legacy names deepseek-v4-flash and deepseek-v4-flash-vision-exp are
billed at the Flash price, per the page's own footnote.
"""

import html
import re

PROVIDER = "deepseek"
NAME = "DeepSeek"
SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"
VERIFIED_ON = "2026-09-26"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 0.0
SNAPSHOT = r"(?!)"

# Hours are [start, end) in UTC; weekdays 0 to 4 are Monday to Friday.
_OFF_PEAK = {"mult": 0.5, "peak_utc_hours": [[1, 4], [6, 10]], "peak_weekdays": [0, 1, 2, 3, 4]}


def _row(peak_in, peak_out, peak_hit):
    return {"from": "", "in": peak_in, "out": peak_out, "cache_read_mult": peak_hit / peak_in,
            "fast": None, "off_peak": _OFF_PEAK}


PRICES = {
    "deepseek-flash":  [_row(0.30, 1.20, 0.006)],
    "deepseek-v4-pro": [_row(1.32, 3.96, 0.044)],
}

ALIASES = {"deepseek-v4-flash": "deepseek-flash", "deepseek-v4-flash-vision-exp": "deepseek-flash"}

FALLBACK_MODEL = "deepseek-v4-pro"


def page_rates(fetch, tables, want=None):
    """The peak and off-peak rates on the page, as {model id: {field: $/MTok}}.
    The table is transposed: one column per model, and each price row is
    followed by an unlabelled PEAK row."""
    text = fetch(SOURCE)
    body = re.search(r"<table[^>]*>(.*?)</table>", text, re.S).group(1)
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        rows.append([html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)])
    models = [re.sub(r"\(\d+\)$", "", c).strip() for c in rows[0][1:]]
    rates = {m: {} for m in models}
    field = None
    for r in rows:
        joined = " ".join(r).upper()
        if "CACHE HIT" in joined:
            field = "cached"
        elif "CACHE MISS" in joined:
            field = "in"
        elif "OUTPUT TOKENS" in joined:
            field = "out"
        if field and r and r[-len(models) - 1] == "PEAK":
            values = [float(v.strip("$")) for v in r[-len(models):]]
            for m, v in zip(models, values):
                rates[m][field] = v
    unknown = sorted(m for m in models if m not in PRICES)
    return rates, unknown
