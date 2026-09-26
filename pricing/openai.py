"""OpenAI's API rates, in dollars per million tokens. Standard tier.

Read off OpenAI's published pages on 26 September 2026, row by row:

  https://developers.openai.com/api/docs/pricing            the main table
  https://developers.openai.com/api/docs/models/<model-id>  one page per model

The main table no longer lists the older Codex models (gpt-5-codex,
gpt-5.1-codex and the rest), so those rates come from their own model pages,
which still publish them.

**Published, not measured.** Nobody has yet checked these figures against a
real OpenAI bill or against a harness's own cost report, the way the Anthropic
table was checked against Claude Code. The rates are the published ones; what
is unproven is the way a harness's logs map onto them. If you use this daily,
please compare a month against your bill and open an issue either way.

Rules taken from the model pages and modelled here:

  - Cached input is a fixed fraction of input: 0.1x on the GPT-5 and GPT-6
    families, 0.25x or 0.5x on older models, and no discount at all on the pro
    models, which offer no cached rate.
  - Cache writes are billed at 1.25x input on GPT-6 and GPT-5.6. Older models
    have no write charge; the tokens are ordinary input.
  - Long context: on the 1.05M-window models, a prompt of more than 272K input
    tokens is priced at 2x input and cache rates and 1.5x output for the whole
    request. The GPT-5.5 and 5.4 pages say "for the full session" where the
    newer pages say "for the full request"; this table reads both as the
    request, which is the only unit a log records.
  - Fast mode (formerly priority processing) has its own published rates,
    used when a call is recorded as fast.
  - Web search is $10 per 1,000 calls on reasoning models, which is every
    model a coding harness calls.

Not modelled: the Batch and Flex discounts (not interactive), the 10% uplift
for regional processing and FedRAMP endpoints, and container and file-search
tool fees.

Row fields are the same as the Anthropic table, plus two optional ones:

  write_mult   cache write multiple of base input (default 1.0 here)
  long         {"over": tokens, "in": mult, "out": mult} for long-context rates
"""

PROVIDER = "openai"
NAME = "OpenAI"
SOURCE = "https://developers.openai.com/api/docs/pricing"
SOURCE_MD = "https://developers.openai.com/api/docs/pricing.md"
MODEL_PAGE_MD = "https://developers.openai.com/api/docs/models/{model}.md"
VERIFIED_ON = "2026-09-26"
MEASURED = False

# OpenAI has one kind of cache write; both columns take the same multiple, and
# rows that bill writes override it.
CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 10.0

# OpenAI snapshots carry a dashed date: gpt-5-2025-08-07.
SNAPSHOT = r"-\d{4}-\d{2}-\d{2}$"

_LONG = {"over": 272_000, "in": 2.0, "out": 1.5}


def _row(inp, out, cached_mult, fast=None, write_mult=1.0, long=None):
    row = {"from": "", "in": inp, "out": out, "cache_read_mult": cached_mult,
           "fast": fast, "write_mult": write_mult}
    if long:
        row["long"] = long
    return row


PRICES = {
    # GPT-6. Cache writes billed at 1.25x; long context above 272K.
    "gpt-6-astra":        [_row(10.00, 50.00, 0.1, (20.00, 100.00), 1.25, _LONG)],
    "gpt-6-sol":          [_row( 2.00, 10.00, 0.1, ( 4.00,  20.00), 1.25, _LONG)],
    "gpt-6-luna":         [_row( 0.10,  0.50, 0.1, ( 0.20,   1.00), 1.25, _LONG)],
    # GPT-5.6. Sol is on promotional pricing "at least through November 21,
    # 2026". When that ends, add a dated entry; do not edit this one.
    "gpt-5.6-sol":        [_row( 4.00, 20.00, 0.1, ( 8.00,  40.00), 1.25, _LONG)],
    "gpt-5.6-terra":      [_row( 2.00, 12.00, 0.1, ( 4.00,  24.00), 1.25, _LONG)],
    "gpt-5.6-luna":       [_row( 0.20,  1.20, 0.1, ( 0.40,   2.40), 1.25, _LONG)],
    # GPT-5.5 and 5.4. Long context, no write charge.
    "gpt-5.5":            [_row( 5.00, 30.00, 0.1, (12.50,  75.00), long=_LONG)],
    "gpt-5.5-pro":        [_row(30.00, 180.00, 1.0, long=_LONG)],
    "gpt-5.4":            [_row( 2.50, 15.00, 0.1, ( 5.00,  30.00), long=_LONG)],
    "gpt-5.4-pro":        [_row(30.00, 180.00, 1.0, long=_LONG)],
    "gpt-5.4-mini":       [_row( 0.75,  4.50, 0.1, ( 1.50,   9.00))],
    "gpt-5.4-nano":       [_row( 0.20,  1.25, 0.1)],
    # Codex models, from their own model pages.
    "gpt-5.3-codex":      [_row( 1.75, 14.00, 0.1, ( 3.50,  28.00))],
    "gpt-5.2-codex":      [_row( 1.75, 14.00, 0.1)],
    "gpt-5.1-codex-max":  [_row( 1.25, 10.00, 0.1)],
    "gpt-5.1-codex":      [_row( 1.25, 10.00, 0.1)],
    "gpt-5.1-codex-mini": [_row( 0.25,  2.00, 0.1)],
    "gpt-5-codex":        [_row( 1.25, 10.00, 0.1)],
    "codex-mini-latest":  [_row( 1.50,  6.00, 0.25)],
    # GPT-5, 5.1 and 5.2.
    "gpt-5.2":            [_row( 1.75, 14.00, 0.1, ( 3.50,  28.00))],
    "gpt-5.2-pro":        [_row(21.00, 168.00, 1.0)],
    "gpt-5.1":            [_row( 1.25, 10.00, 0.1, ( 2.50,  20.00))],
    "gpt-5":              [_row( 1.25, 10.00, 0.1, ( 2.50,  20.00))],
    "gpt-5-mini":         [_row( 0.25,  2.00, 0.1, ( 0.45,   3.60))],
    "gpt-5-nano":         [_row( 0.05,  0.40, 0.1)],
    "gpt-5-pro":          [_row(15.00, 120.00, 1.0)],
    # Older models a harness may still be pointed at.
    "gpt-4.1":            [_row( 2.00,  8.00, 0.25, ( 3.50,  14.00))],
    "gpt-4.1-mini":       [_row( 0.40,  1.60, 0.25, ( 0.70,   2.80))],
    "gpt-4.1-nano":       [_row( 0.10,  0.40, 0.25, ( 0.20,   0.80))],
    "gpt-4o":             [_row( 2.50, 10.00, 0.5, ( 4.25,  17.00))],
    # A snapshot with its own, higher price. Matched exactly before any
    # snapshot date is stripped, so it never falls through to gpt-4o.
    "gpt-4o-2024-05-13":  [_row( 5.00, 15.00, 1.0, ( 8.75,  26.25))],
    "gpt-4o-mini":        [_row( 0.15,  0.60, 0.5, ( 0.25,   1.00))],
    "o3":                 [_row( 2.00,  8.00, 0.25, ( 3.50,  14.00))],
    "o3-pro":             [_row(20.00, 80.00, 1.0)],
    "o4-mini":            [_row( 1.10,  4.40, 0.25, ( 2.00,   8.00))],
    "o3-mini":            [_row( 1.10,  4.40, 0.5)],
    "o1":                 [_row(15.00, 60.00, 0.5)],
    "o1-pro":             [_row(150.00, 600.00, 1.0)],
}

# The flagship, so an unknown id errs towards overstating. It is flagged in
# every report either way.
FALLBACK_MODEL = "gpt-6-astra"

# Models the page lists that this table leaves out on purpose: legacy, audio,
# image and single-purpose models no coding harness calls. --check-prices
# names anything else it finds on the page and not here.
WATCH = r"^(gpt-[5-9]|o\d|codex)"
IGNORE = {"gpt-5-search-api", "gpt-5.5-cyber", "gpt-5.6-cyber", "gpt-rosalind-research"}


def _money(cell: str):
    """"$10.00" -> 10.0. "-" and "Free" -> None."""
    import re
    m = re.search(r"\$([\d.,]+)", cell)
    return float(m.group(1).replace(",", "")) if m else None


def _model(cell: str) -> str:
    """"gpt-5.5 (<272K context length)" -> "gpt-5.5"."""
    return cell.split("(")[0].strip()


def _fill(r: dict) -> dict:
    """A "-" on the page means no discount or no premium: the ordinary input
    rate applies. Recorded as that, so it compares like any other figure."""
    if r.get("in") is not None:
        if r.get("cached") is None:
            r["cached"] = r["in"]
        if r.get("write") is None:
            r["write"] = r["in"]
    return {k: v for k, v in r.items() if v is not None}


def page_rates(fetch, tables, want=None):
    """Every rate the published pages state, as {model id: {field: $/MTok}},
    plus page model ids this table does not have. The main page first; a
    model it does not list is read from its own model page.

    Used by --check-prices (want=None: every model in this table), which
    reports differences and never edits this file, and by the startup lookup
    for models the table lacks (want: just those)."""
    import re
    rates, seen, grouped = {}, [], 0
    for title, header, rows in tables(fetch(SOURCE_MD)):
        h = [c.strip().lower() for c in header]
        if h[:2] == ["model", "short context input"]:
            fast = title.lower().startswith("fast")
            if not (fast or title.lower().startswith("standard")):
                continue
            for r in rows:
                mid = _model(r[0])
                seen.append(mid)
                if fast:
                    if mid in rates:
                        rates[mid]["fast_in"] = _money(r[1])
                        rates[mid]["fast_out"] = _money(r[4])
                    continue
                rates[mid] = {"in": _money(r[1]), "cached": _money(r[2]),
                              "write": _money(r[3]), "out": _money(r[4]),
                              "long_in": _money(r[5]), "long_out": _money(r[8])}
        elif h == ["category", "model", "input", "cached input", "output"]:
            grouped += 1
            for r in rows:
                mid = r[1].strip()
                seen.append(mid)
                if grouped == 1:
                    rates[mid] = {"in": _money(r[2]), "cached": _money(r[3]),
                                  "out": _money(r[4])}
                elif mid in rates:
                    rates[mid]["fast_in"] = _money(r[2])
                    rates[mid]["fast_out"] = _money(r[4])
    for mid in (PRICES if want is None else want):
        if mid in rates:
            continue
        r = {}
        for title, header, rows in tables(fetch(MODEL_PAGE_MD.format(model=mid))):
            if [c.strip().lower() for c in header][:2] != ["metric", "price"]:
                continue
            for row in rows:
                key = {"input": "in", "cached input": "cached", "cache writes": "write",
                       "output": "out"}.get(row[0].strip().lower())
                if key and key not in r:
                    r[key] = _money(row[1])
            break
        if r:
            rates[mid] = r
    unknown = sorted({m for m in seen if re.match(WATCH, m) and m not in PRICES
                      and m not in IGNORE})
    return {m: _fill(r) for m, r in rates.items()}, unknown
