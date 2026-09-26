"""Anthropic's first-party API rates, in dollars per million tokens.

Verified three ways, most recently on 26 September 2026.

1. By measurement, 10 September 2026, against Claude Code's own
   `total_cost_usd`: controlled calls through `claude -p --output-format json`,
   pricing the same usage block here. Every one exact to ten decimal places:

     Haiku 4.5    $0.0290032     Sonnet 5     $0.0781294
     Opus 5       $0.3810900     Opus 4.8     $0.3594400
     Fable 5.1    $0.7564800     Fable 5.1    $0.2647945  (warm, cache read)

   Between them those exercise base input, base output, cache read at 0.1x,
   cache read at 0.025x (the Fable exception) and the 1-hour cache write at 2x
   on three separate models. Opus 5.5 was later matched to the cent against
   the per-model `costUSD` summaries Claude Code writes into transcripts.

2. Against the published page, row by row: 11 September 2026 for every
   model, and again on 26 September 2026 for all eighteen rows, both cache
   write multipliers, the three cache read multipliers, both fast-mode rates
   and web search. Every figure matched.

3. By the test suite. TestPublishedRates holds the published figure for every
   model and fails if this table drifts from it.

One assumption remains: the 5-minute cache write at 1.25x is published but not
measured, because Claude Code gives no way to force one. It carries about 3.6%
of a typical total.

What the page lists and this table deliberately leaves out:

  - Long context is not surcharged. Claude 4.6 and later bill the full 1M
    window at standard rates.
  - The Batch API's 50% discount never applies to an interactive harness.
  - Web fetch is free. Only web search is billed, at $10 per 1,000.
  - `inference_geo: "us"` multiplies everything by 1.1x. Claude Code has never
    set it (every record seen says "not_available"), so it is not modelled.

Row fields:

  from              the day this rate took effect, "" meaning always
  in / out          base input and output
  cache_read_mult   multiple of base input for a cache hit
  fast              (input, output) when speed == "fast", None if unsupported

Rates are dated, and a call is priced at the rate in force on the day it was
made. Anthropic has so far priced each model for its life and released a new
one rather than moving an old one (Sonnet 4.6 is $3/$15 and Sonnet 5 is $2/$10:
a cheaper Sonnet arrived, Sonnet did not get cheaper), so every model has one
entry. The dating is insurance. When a rate changes, add an entry with the date
it took effect and leave the old one alone.
"""

PROVIDER = "anthropic"
NAME = "Anthropic"
SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
# The markdown form of the same page, which --check-prices reads.
SOURCE_MD = "https://platform.claude.com/docs/en/about-claude/pricing.md"
VERIFIED_ON = "2026-09-26"
# "measured" means checked against real bills or the harness's own cost
# figures, not only against the pricing page.
MEASURED = True

CACHE_WRITE_5M_MULT = 1.25
CACHE_WRITE_1H_MULT = 2.0
WEB_SEARCH_PER_1K = 10.0

# A dated snapshot id, such as claude-haiku-4-5-20251001, is the same model.
SNAPSHOT = r"-\d{8}$"

PRICES = {
    "claude-fable-5-1":  [{"from": "", "in": 10.0, "out": 50.0, "cache_read_mult": 0.025, "fast": None}],
    "claude-mythos-5-1": [{"from": "", "in": 10.0, "out": 50.0, "cache_read_mult": 0.025, "fast": None}],
    "claude-fable-5":    [{"from": "", "in": 10.0, "out": 50.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-mythos-5":   [{"from": "", "in": 10.0, "out": 50.0, "cache_read_mult": 0.1,   "fast": None}],
    # Cheaper than Opus 5 in every column, and its cache reads are 0.05x
    # rather than the usual 0.1x.
    "claude-opus-5-5":   [{"from": "", "in":  4.0, "out": 20.0, "cache_read_mult": 0.05,  "fast": (8.0, 40.0)}],
    "claude-opus-5":     [{"from": "", "in":  5.0, "out": 25.0, "cache_read_mult": 0.1,   "fast": (10.0, 50.0)}],
    "claude-opus-4-8":   [{"from": "", "in":  5.0, "out": 25.0, "cache_read_mult": 0.1,   "fast": (10.0, 50.0)}],
    "claude-opus-4-7":   [{"from": "", "in":  5.0, "out": 25.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-opus-4-6":   [{"from": "", "in":  5.0, "out": 25.0, "cache_read_mult": 0.1,   "fast": None}],
    # Launched at $2/$10 as introductory pricing, with a rise to $3/$15
    # announced for 1 September 2026. The rise was cancelled and $2/$10 is now
    # the standard price, per the page's own footnote. One entry, not two.
    "claude-sonnet-5":   [{"from": "", "in":  2.0, "out": 10.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-sonnet-4-6": [{"from": "", "in":  3.0, "out": 15.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-haiku-4-5":  [{"from": "", "in":  1.0, "out":  5.0, "cache_read_mult": 0.1,   "fast": None}],
    # Older and retired models. Cheap to carry, and the alternative is the
    # fallback quietly pricing an Opus 4.1 call at a third of its real rate,
    # or a Haiku 3.5 call at six times.
    "claude-opus-4-5":   [{"from": "", "in":  5.0, "out": 25.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-opus-4-1":   [{"from": "", "in": 15.0, "out": 75.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-opus-4":     [{"from": "", "in": 15.0, "out": 75.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-sonnet-4-5": [{"from": "", "in":  3.0, "out": 15.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-sonnet-4":   [{"from": "", "in":  3.0, "out": 15.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-haiku-3-5":  [{"from": "", "in":  0.8, "out":  4.0, "cache_read_mult": 0.1,   "fast": None}],
}

# An id not in the table is priced here and flagged in every report. Opus is
# the dearest model a harness is likely to call by default, so an unknown id
# errs towards overstating rather than hiding cost.
FALLBACK_MODEL = "claude-opus-5"

# How the pricing page names each model, for --check-prices.
PAGE_NAMES = {
    "Claude Fable 5.1": "claude-fable-5-1",
    "Claude Mythos 5.1": "claude-mythos-5-1",
    "Claude Fable 5": "claude-fable-5",
    "Claude Mythos 5": "claude-mythos-5",
    "Claude Opus 5.5": "claude-opus-5-5",
    "Claude Opus 5": "claude-opus-5",
    "Claude Opus 4.8": "claude-opus-4-8",
    "Claude Opus 4.7": "claude-opus-4-7",
    "Claude Opus 4.6": "claude-opus-4-6",
    "Claude Opus 4.5": "claude-opus-4-5",
    "Claude Opus 4.1": "claude-opus-4-1",
    "Claude Opus 4": "claude-opus-4",
    "Claude Sonnet 5": "claude-sonnet-5",
    "Claude Sonnet 4.6": "claude-sonnet-4-6",
    "Claude Sonnet 4.5": "claude-sonnet-4-5",
    "Claude Sonnet 4": "claude-sonnet-4",
    "Claude Haiku 4.5": "claude-haiku-4-5",
    "Claude Haiku 3.5": "claude-haiku-3-5",
}


def _money(cell: str):
    """"$0.25 / MTok<sup>1</sup>" -> 0.25. Anything without a figure -> None."""
    import re
    m = re.search(r"\$([\d.,]+)", cell)
    return float(m.group(1).replace(",", "")) if m else None


def _name(cell: str) -> str:
    """"Claude Opus 4.1 ([retired, ...](...))" -> "Claude Opus 4.1"."""
    import re
    cell = re.sub(r"<sup>.*?</sup>", "", cell)
    return re.sub(r"\s*\(\[.*$", "", cell).strip()


def page_id(name: str) -> str:
    """Anthropic's naming rule, "Claude Sonnet 5.5" -> "claude-sonnet-5-5".
    Used only for models the page lists that PAGE_NAMES does not yet know."""
    return name.lower().replace(".", "-").replace(" ", "-")


def page_rates(fetch, tables, want=()):
    """Every rate the published page states, as {model id: {field: $/MTok}},
    plus the page's names for models this table does not have.

    Used by --check-prices, which reports differences and never edits this
    file, and by the startup lookup for a model the table lacks (`want`),
    which is saved separately and labelled as fetched."""
    rates, unknown = {}, []
    for title, header, rows in tables(fetch(SOURCE_MD)):
        h = [c.strip().lower() for c in header]
        if "base input tokens" in h:
            for r in rows:
                name = _name(r[0])
                mid = PAGE_NAMES.get(name)
                if mid is None:
                    unknown.append(name)
                    mid = page_id(name)
                    if mid not in want:
                        continue
                rates[mid] = {"in": _money(r[1]), "write_5m": _money(r[2]),
                              "write_1h": _money(r[3]), "cached": _money(r[4]),
                              "out": _money(r[5])}
        elif h == ["model", "input", "output"]:
            # Fast mode, where one row can name two models.
            for r in rows:
                for name in _name(r[0]).split(" / "):
                    mid = PAGE_NAMES.get(name.strip()) or page_id(name.strip())
                    if mid in rates:
                        rates[mid]["fast_in"] = _money(r[1])
                        rates[mid]["fast_out"] = _money(r[2])
    return rates, unknown
