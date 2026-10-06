"""Google's Gemini Developer API rates, in dollars per million tokens.

Read off https://ai.google.dev/gemini-api/docs/pricing on 26 September 2026
(the page's own footer read "Last updated 2026-09-24 UTC"), Standard tier,
paid. Read twice, independently: once by hand with every figure quoted, and
once by the page reader below, and the two agreed on every figure.

**Published, not measured.** Nobody has yet compared these with a real Gemini
bill or a harness's own cost report. Please do, and open an issue either way.

Rules taken from the page and modelled here:

  - Output is priced "including thinking tokens". Gemini's own usage report
    counts thoughts separately from the answer, so an adapter or import must
    add them into output.
  - Cached input is 0.1x input on every text model that offers caching.
  - Long context: Gemini 3.1 Pro Preview, 2.5 Pro and 2.5 Computer Use charge
    2x input and cache rates and 1.5x output for prompts over 200K tokens.
  - Gemini 3.6, 3.7 and 3.8 Flash have two published prices, one through 31
    December 2026 and a higher one from 1 January 2027. Both are in the table
    as dated entries, so each call is priced at the rate in force that day.

Not modelled, and why:

  - Context cache storage, billed per million tokens per hour. Logs record
    tokens, not how long a cache lived.
  - Grounding with Google Search: free up to a monthly or daily allowance,
    then $14 or $35 per 1,000. What a search costs depends on the rest of
    your month, so searches are counted and priced at zero.
  - The Priority, Batch and Flex tiers, and audio input, which has its own
    higher rate.
"""

import re

PROVIDER = "google"
NAME = "Google"
SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
VERIFIED_ON = "2026-10-06"
MEASURED = False

# Gemini has no per-token cache write fee; creating a cache bills as input.
CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
# Grounding is not modelled; see above.
WEB_SEARCH_PER_1K = 0.0

# Stable versions carry a three-digit suffix: gemini-2.0-flash-001.
SNAPSHOT = r"-\d{3}$"

_LONG = {"over": 200_000, "in": 2.0, "out": 1.5}


def _row(inp, out, cached_mult=0.1, long=None, since=""):
    row = {"from": since, "in": inp, "out": out, "cache_read_mult": cached_mult, "fast": None}
    if long:
        row["long"] = long
    return row


PRICES = {
    # Launch prices through 31 December 2026, then the published list price.
    "gemini-3.8-flash":       [_row(0.75, 3.75), _row(1.50, 7.50, since="2027-01-01")],
    "gemini-3.7-flash":       [_row(0.75, 3.75), _row(1.50, 7.50, since="2027-01-01")],
    "gemini-3.6-flash":       [_row(0.75, 3.75), _row(1.50, 7.50, since="2027-01-01")],
    "gemini-3.5-flash":       [_row(1.50, 9.00)],
    "gemini-3.5-flash-lite":  [_row(0.30, 2.50)],
    "gemini-3.1-flash-lite":  [_row(0.25, 1.50)],
    "gemini-3.1-pro-preview": [_row(2.00, 12.00, long=_LONG)],
    "gemini-3-flash-preview": [_row(0.50, 3.00)],
    "gemini-2.5-pro":         [_row(1.25, 10.00, long=_LONG)],
    "gemini-2.5-flash":       [_row(0.30, 2.50)],
    "gemini-2.5-flash-lite":  [_row(0.10, 0.40)],
    # No caching row on the page, so no cache discount.
    "gemini-2.5-computer-use-preview-10-2025": [_row(1.25, 10.00, 1.0, long=_LONG)],
}

# Kept for older usage, at the last published price, though the page no
# longer lists them. Model id: retirement date. Shut down 28 July 2026 per
# https://ai.google.dev/gemini-api/docs/deprecations; the pricing page
# dropped it on 6 October 2026.
RETIRED = {"gemini-2.5-computer-use-preview-10-2025": "2026-07-28"}

# Other names for the same model, as the page gives them.
ALIASES = {"gemini-3.1-pro-preview-customtools": "gemini-3.1-pro-preview"}

FALLBACK_MODEL = "gemini-3.1-pro-preview"


# ---- reading the published page, for --check-prices and the startup lookup

_MONEY = re.compile(r"\$([\d.,]+)")


def _paid_cell(cell: str) -> dict:
    """One paid-tier cell as {"base", "long", "dated"}.

    A cell can hold several prices at once: text and audio, short and long
    context, a launch price and a later one, and a storage price. Each dollar
    figure is classified by the words that follow it. The cells also hold
    unescaped "<" and ">" (prompts <= 200k tokens), so tags are removed by name
    and never by a blanket pattern, which would eat the long-context half.
    """
    text = re.sub(r"<br\s*/?>", " ; ", cell)
    text = re.sub(r"</?(a|code|span|em|strong|p|sup)\b[^>]*>", "", text)
    out = {}
    for figure, tail in re.findall(r"\$([\d.,]+)([^$]*)", text):
        value = float(figure.replace(",", "").rstrip("."))
        tail = tail.lower()
        if "per hour" in tail or "storage" in tail or "(audio)" in tail:
            continue
        if "starting" in tail:
            date = re.search(r"starting (\w+ \d+, \d{4})", tail)
            out["dated"] = (value, date.group(1).title() if date else "")
        elif "> 200k" in tail or ">200k" in tail:
            out["long"] = value
        elif "base" not in out:
            out["base"] = value
    return out


def page_rates(fetch, tables, want=None):
    """Every Standard-tier rate on the page, as {model id: {field: $/MTok}}.

    Used by --check-prices, which reports differences and never edits this
    file, and by the startup lookup for a model this table lacks. The page
    is HTML: one heading per model, its id in <code>, then a Standard table.
    """
    import datetime as dt
    text = fetch(SOURCE)
    rates, seen = {}, []
    for block in re.split(r"<h2 ", text)[1:]:
        ids = re.findall(r"<code[^>]*>(gemini-[a-z0-9.\-]+)</code>", block[:2000])
        # The Standard table, or a model's only table when it has just one.
        std = (re.search(r'data-text="Standard".*?<tbody>(.*?)</tbody>', block, re.S)
               or re.search(r"<tbody>(.*?)</tbody>", block, re.S))
        if not ids or not std:
            continue
        cells = {}
        for label, paid in re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td>.*?</td>\s*<td>(.*?)</td>\s*</tr>",
                                      std.group(1), re.S):
            cells[re.sub(r"<[^>]+>", "", label).strip().lower()] = _paid_cell(paid)
        inp = next((v for k, v in cells.items() if k.startswith("input price")), {})
        out = next((v for k, v in cells.items() if k.startswith("output price")), {})
        cache = cells.get("context caching price", {})
        if "base" not in inp or "base" not in out:
            continue
        r = {"in": inp["base"], "out": out["base"],
             "cached": cache.get("base", inp["base"])}
        if "long" in inp and "long" in out:
            r["long_in"], r["long_out"] = inp["long"], out["long"]
        if "dated" in inp and "dated" in out:
            try:
                since = dt.datetime.strptime(inp["dated"][1], "%B %d, %Y").date().isoformat()
            except ValueError:
                since = "?"
            later = {"from": since, "in": inp["dated"][0], "out": out["dated"][0]}
            if "dated" in cache:
                later["cached"] = cache["dated"][0]
            r["_history"] = [{"from": "", "in": r["in"], "out": r["out"], "cached": r["cached"]}, later]
            # The newest price, which the table's last entry must match.
            r["in"], r["out"] = later["in"], later["out"]
            r["cached"] = later.get("cached", r["cached"])
        for mid in ids:
            seen.append(mid)
            rates.setdefault(mid, dict(r))
    # Only text models a coding harness would call are worth flagging; the page
    # also lists live, speech, image and robotics models on purpose left out.
    unknown = sorted(m for m in set(seen) if m not in PRICES and m not in ALIASES
                     and re.fullmatch(r"gemini-[\d.]+-(pro|flash|flash-lite)(-preview)?", m))
    return rates, unknown
