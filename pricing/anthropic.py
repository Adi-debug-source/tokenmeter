"""Anthropic's first-party API rates, in dollars per million tokens.

Verified three ways, most recently on 27 October 2026.

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
   Sonnet 5.5 was added on 6 October 2026 and measured the same way:
   $0.0744524, exact, with base input, a 0.1x cache read and a 1-hour write.
   Haiku 5.5, and Sonnet 5.5's cheaper cache reads, both from 7 October
   2026, come from the page and the release notes, and are not yet measured
   against Claude Code.

2. Against the published page, row by row: 11 September 2026 for every
   model, and again on 26 September 2026 for all eighteen rows, both cache
   write multipliers, the three cache read multipliers, both fast-mode rates
   and web search. Every figure matched. On 6 October 2026 --check-prices
   read all nineteen rows, Sonnet 5.5 included, and every column matched. On
   15 October 2026 the page and Anthropic's release notes were re-read by
   hand, and --check-prices matched all twenty models, both of Haiku 5.5's
   price tiers in every column. On 27 October 2026 the page's markdown form
   (SOURCE_MD) was read by hand twice, by two readers working apart, and
   once more wherever they differed: every figure of the twenty current
   models, both Haiku 5.5 tiers, the three fast-mode rates, the 1.25x and 2x
   write multiples, the 0.1x, 0.025x and 0.05x read multiples and web search
   at $10 per 1,000 agreed with this table, and no row was changed.

3. By the test suite. TestPublishedRates holds the published figure for every
   model and fails if this table drifts from it.

One assumption remains: the 5-minute cache write at 1.25x is published but not
measured, because Claude Code gives no way to force one. It carries about 3.6%
of a typical total. The retired models below were never measured.

Retired models. Every retirement date comes from Anthropic's deprecation
page, https://platform.claude.com/docs/en/about-claude/model-deprecations
(its "Model status" table and the notice named beside each entry in
RETIRED). Four retired models are still printed on the pricing page with a
"retired, except on ..." label (Opus 4.1, Opus 4, Sonnet 4, Haiku 3.5), so
they are priced and checked from the page today. Seven the page no longer
lists are priced at their last published rate, read on 27 October 2026 from
the Internet Archive's raw copy of Anthropic's own pricing page, the last
capture to carry each row (named in RETIRED):

  - Sonnet 3.7 and Sonnet 3.5 (one row for both of 3.5's snapshots): $3 in,
    $3.75 and $6 cache writes, $0.30 a hit, $15 out. Opus 3: $15, $18.75,
    $30, $1.50, $75.
  - Haiku 3: $0.25 in, $0.30 and $0.50 writes, $0.03 a hit, $1.25 out. Its
    5-minute write is 1.2x and its hit 0.12x, not the table's defaults, so
    its row carries its own write multiples and every printed figure is
    reproduced exactly.
  - Claude 3 Sonnet ($3 / $15) and Claude 2.1 and 2.0 ($8 / $24 each): the
    marketing page's price cards gave input and output only, and none of
    the three supported prompt caching. Their cache_read_mult and write_mult
    are 1.0, the engine's value for "no published cache price"; no cache
    token can reach them. Claude 2.1 and 2.0 were sold until 21 July 2025,
    but their cards left the pricing page between 24 and 29 October 2024
    (the Internet Archive holds captures at 20241024003303, cards present,
    and 20241029075133, cards absent, and none in between), so their capture
    is from 24 October 2024: the last published price, and no later page
    gave another.

Their ids are the API ids with the snapshot date stripped
(claude-3-7-sonnet-20250219 -> claude-3-7-sonnet), so SNAPSHOT reaches them
from what a log records. Haiku 3.5's row predates that rule and keeps its
page-name id, claude-haiku-3-5; ALIASES maps its API ids to it.

What the page lists and this table deliberately leaves out:

  - Long context is not surcharged. Claude 4.6 and later bill the full 1M
    window at standard rates, except Claude Haiku 5.5, which is priced by
    prompt length and is modelled: a request whose prompt is over 100,000
    tokens, cache reads and writes included, pays its higher prices. A
    prompt of exactly 100,000 is the lower tier ("up to 100,000 tokens").
  - The Batch API's 50% discount never applies to an interactive harness.
  - Web fetch is free. Only web search is billed, at $10 per 1,000.
  - `inference_geo`: the page says global routing, the default, is standard
    pricing, and `"us"` multiplies everything by 1.1x. Not modelled: every
    record seen says "not_available" or "global".
  - Code execution (per container-hour beyond a free allowance) and Managed
    Agents session time (per session-hour) are billed by time, not tokens.
  - Thinking has no price of its own: thinking tokens are output tokens,
    so there is no thinking or non-thinking choice to make here.
  - No time-of-day price is published, so no row has off_peak.
  - Sonnet 5's rise to $3 / $15 on 1 September 2026, announced at launch,
    was cancelled before it took effect, so it was never charged and has no
    row.
  - Claude Mythos Preview: no price was published on any copy of the page
    read, so it has no row.

What the page's history holds that the row format cannot express yet, or
the brief's rules do not yet allow, and so is not typed (every figure read
from archive captures of the page and Anthropic's release notes):

  - The 1M-context beta's premium: over 200K input tokens, 2x input and
    1.5x output ($6 / $22.50 on a $3 / $15 model, $10 / $37.50 on Opus 4.6),
    on Sonnet 4 from 12 August 2025, Sonnet 4.5 from 29 September 2025, and
    Opus 4.6 and Sonnet 4.6 from 5 and 17 February 2026 until 13 March 2026,
    when the full 1M window became standard pricing. The page stopped
    printing it for Sonnet 4.5 and 4 by the 1 April 2026 capture
    (20260401185808; the 30 March capture, 20260330161433, still prints
    $6 / $22.50 for "Claude Sonnet 4.5 / 4") while the beta ran to
    30 April 2026. Sonnet 4.5, 4.6 and Opus 4.6 are current models, whose
    price comes from today's page alone, and Sonnet 4's end date has no
    clear answer, so the rows price these requests at the standard rate:
    such a request is understated by 2x on input and 1.5x on output.
  - Past fast-mode rates: Opus 4.6 at $30 / $150 from 7 February to 29 June
    2026 ($60 / $225 over 200K input tokens until a day between 19 and 21
    February 2026)
    and Opus 4.7 at $30 / $150 from 12 May to 24 July 2026. Both models are
    current, so for the same reason the rows have fast None, and a fast call
    to either in those months prices at the standard rate.

Row fields:

  from              the day this rate took effect, "" meaning always
  in / out          base input and output
  cache_read_mult   multiple of base input for a cache hit
  fast              (input, output) when speed == "fast", None if unsupported
  long (optional)   {"over": tokens, "in": mult, "out": mult}: a request whose
                    prompt is over that many tokens pays those multiples
  write_mult, write_1h_mult (optional)
                    this model's own 5-minute and 1-hour cache write
                    multiples, where the page's figures are not the defaults

Rates are dated, and a call is priced at the rate in force on the day it was
made. Anthropic mostly prices a model for its life and releases a new one
rather than moving an old one (Sonnet 4.6 is $3/$15 and Sonnet 5 is $2/$10:
a cheaper Sonnet arrived, Sonnet did not get cheaper). The exception so far is
Sonnet 5.5, whose cache reads were cut on 7 October 2026, so it has two
entries. When a rate changes, add an entry with the date it took effect and
leave the old one alone.
"""

import re

from .common import money

PROVIDER = "anthropic"
NAME = "Anthropic"
SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
# The markdown form of the same page, which --check-prices reads.
SOURCE_MD = "https://platform.claude.com/docs/en/about-claude/pricing.md"
VERIFIED_ON = "2026-10-27"
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
    # Added 6 October 2026: the same rates as Sonnet 5, no fast mode. Matched
    # Claude Code's own cost to ten decimal places the same day. Anthropic's
    # release notes of 7 October 2026 cut its cache reads from $0.20 to $0.10
    # per million, 0.05x input; cache writes and every other price unchanged.
    "claude-sonnet-5-5": [{"from": "",           "in":  2.0, "out": 10.0, "cache_read_mult": 0.1,  "fast": None},
                          {"from": "2026-10-07", "in":  2.0, "out": 10.0, "cache_read_mult": 0.05, "fast": None}],
    "claude-sonnet-4-6": [{"from": "", "in":  3.0, "out": 15.0, "cache_read_mult": 0.1,   "fast": None}],
    # Launched 7 October 2026 and priced by prompt length: a request whose
    # prompt is over 100,000 tokens, cache reads and writes included, pays
    # 5x every rate ($0.50 in, $2.50 out, $0.05 a cache hit).
    "claude-haiku-5-5":  [{"from": "", "in":  0.1, "out":  0.5, "cache_read_mult": 0.1,   "fast": None,
                           "long": {"over": 100_000, "in": 5.0, "out": 5.0}}],
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
    # Added 27 October 2026: retired and no longer on the page, each at its
    # last published price from the Internet Archive capture of Anthropic's
    # pricing page named in RETIRED below.
    "claude-3-7-sonnet": [{"from": "", "in":  3.0, "out": 15.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-3-5-sonnet": [{"from": "", "in":  3.0, "out": 15.0, "cache_read_mult": 0.1,   "fast": None}],
    "claude-3-opus":     [{"from": "", "in": 15.0, "out": 75.0, "cache_read_mult": 0.1,   "fast": None}],
    # Printed as $0.25 / $0.30 / $0.50 / $0.03 / $1.25: the 5-minute write is
    # 1.2x and the hit 0.12x, not the table's defaults.
    "claude-3-haiku":    [{"from": "", "in":  0.25, "out": 1.25, "cache_read_mult": 0.12, "fast": None,
                           "write_mult": 1.2, "write_1h_mult": 2.0}],
    # Only input and output were ever published for the next three, and none
    # supported prompt caching, so cache_read_mult and write_mult are the
    # engine's "no published cache price" value, 1.0, as in the tables of
    # providers that print no cache write price. Without write_mult the rows
    # would take the table's 1.25x and 2x, and the price list would print
    # cache write figures Anthropic never published.
    "claude-3-sonnet":   [{"from": "", "in":  3.0, "out": 15.0, "cache_read_mult": 1.0,   "fast": None,
                           "write_mult": 1.0}],
    # Sold until 21 July 2025; their price cards left the pricing page
    # between 24 and 29 October 2024 (the archive holds no capture in
    # between), so the capture is from 24 October 2024.
    "claude-2.1":        [{"from": "", "in":  8.0, "out": 24.0, "cache_read_mult": 1.0,   "fast": None,
                           "write_mult": 1.0}],
    "claude-2.0":        [{"from": "", "in":  8.0, "out": 24.0, "cache_read_mult": 1.0,   "fast": None,
                           "write_mult": 1.0}],
}

# {model id: retirement date}, each date from Anthropic's deprecation page,
# https://platform.claude.com/docs/en/about-claude/model-deprecations, under
# the notice quoted. The first four are still printed on the pricing page
# with a "retired" label and are checked against it like any other row; the
# rest are priced from the Internet Archive capture named, the last copy of
# Anthropic's pricing page to carry the row, read in raw form.
RETIRED = {
    "claude-opus-4-1":   "2026-08-05",  # notice "2026-06-05: Claude Opus 4.1 model"; still on the page
    "claude-opus-4":     "2026-06-15",  # notice "2026-04-14: Claude Sonnet 4 and Claude Opus 4 models"; still on the page
    "claude-sonnet-4":   "2026-06-15",  # the same notice; still on the page
    "claude-haiku-3-5":  "2026-02-19",  # notice "2025-12-19: Claude Haiku 3.5 model"; still on the page
    # notice "2025-10-28: Claude Sonnet 3.7 model"; price from
    # https://web.archive.org/web/20260513172300/https://platform.claude.com/docs/en/about-claude/pricing
    "claude-3-7-sonnet": "2026-02-19",
    # notice "2025-08-13: Claude Sonnet 3.5 models", both snapshots; price from
    # https://web.archive.org/web/20251028160151/https://docs.claude.com/en/docs/about-claude/pricing
    "claude-3-5-sonnet": "2025-10-28",
    # notice "2025-06-30: Claude Opus 3 model"; price from
    # https://web.archive.org/web/20260513172300/https://platform.claude.com/docs/en/about-claude/pricing
    "claude-3-opus":     "2026-01-05",
    # notice "2026-02-19: Claude Haiku 3 model"; price from
    # https://web.archive.org/web/20260513172300/https://platform.claude.com/docs/en/about-claude/pricing
    "claude-3-haiku":    "2026-04-20",
    # notice "2025-01-21: Claude 2, Claude 2.1, and Claude Sonnet 3 models"; price from
    # https://web.archive.org/web/20250121003151/https://www.anthropic.com/pricing
    "claude-3-sonnet":   "2025-07-21",
    # the same notice; price from
    # https://web.archive.org/web/20241024003303/https://www.anthropic.com/pricing
    "claude-2.1":        "2025-07-21",
    "claude-2.0":        "2025-07-21",  # the same notice and the same capture
}

# Anthropic's own other names for a model whose row id differs from them.
# Haiku 3.5's row is named from the page, so its API id, the dateless alias
# and the -latest alias (from the models page as captured on 2 January 2025,
# https://web.archive.org/web/20250102194131/https://docs.anthropic.com/en/docs/about-claude/models)
# would otherwise price at the fallback. The other two -latest aliases are
# from the same capture, where each names the snapshot its row prices.
ALIASES = {
    "claude-3-5-haiku-20241022": "claude-haiku-3-5",
    "claude-3-5-haiku": "claude-haiku-3-5",
    "claude-3-5-haiku-latest": "claude-haiku-3-5",
    "claude-3-5-sonnet-latest": "claude-3-5-sonnet",
    "claude-3-opus-latest": "claude-3-opus",
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
    "Claude Sonnet 5.5": "claude-sonnet-5-5",
    "Claude Sonnet 5": "claude-sonnet-5",
    "Claude Sonnet 4.6": "claude-sonnet-4-6",
    "Claude Sonnet 4.5": "claude-sonnet-4-5",
    "Claude Sonnet 4": "claude-sonnet-4",
    "Claude Haiku 5.5": "claude-haiku-5-5",
    "Claude Haiku 4.5": "claude-haiku-4-5",
    "Claude Haiku 3.5": "claude-haiku-3-5",
}


def _name(cell: str) -> str:
    """"Claude Opus 4.1 ([retired, ...](...))" -> "Claude Opus 4.1"."""
    cell = re.sub(r"<sup>.*?</sup>", "", cell)
    return re.sub(r"\s*\(\[.*$", "", cell).strip()


# A model priced by prompt length is two rows on the page, "Claude Haiku 5.5
# (for prompts up to 100,000 tokens)" and "(for prompts over 100,000 tokens)".
_TIER = re.compile(r"^(.*?)\s*\(for prompts (up to|over) ([\d,]+) tokens\)$")


def page_id(name: str) -> str:
    """Anthropic's naming rule, "Claude Sonnet 5.5" -> "claude-sonnet-5-5".
    Used only for models the page lists that PAGE_NAMES does not yet know."""
    return name.lower().replace(".", "-").replace(" ", "-")


# The model table's columns, by their header on the page, and the field each
# gives. Read by name, never by position, so a page that reorders them still
# reads right; a table missing any of them is not read at all.
COLUMNS = {
    "base input tokens": "in",
    "5m cache writes": "write_5m",
    "1h cache writes": "write_1h",
    "cache hits and refreshes": "cached",
    "output tokens": "out",
}


def page_rates(fetch, tables, want=None):
    """Every rate the published page states, as {model id: {field: $/MTok}},
    plus the page's names for models this table does not have.

    Reads the markdown form of the page (SOURCE_MD), every pipe table with
    its nearest heading as `tables` gives them. Used by --check-prices, which
    reports differences and never edits this file, and by the startup lookup
    for a model the table lacks (`want`, the ids it asks for), which is saved
    separately and labelled as fetched.

    Two tables are read. The model table is the one whose header names
    every column in COLUMNS; its cells are read by header, not position. A
    model priced by prompt length is read as one id: the "up to N tokens"
    row gives its base figures, the "over N tokens" row the same five with
    long_ in front (long_in, long_cached and so on), and long_over is N. The
    fast-mode table is the one whose header is exactly Model, Input and
    Output, where one row can name two models ("Claude Opus 5 / Claude Opus
    4.8"). The prompt caching table and the web search price are prose and
    multiples the rows already check, and are not read."""
    want = want or ()
    rates, unknown = {}, []
    for title, header, rows in tables(fetch(SOURCE_MD)):
        h = [c.strip().lower() for c in header]
        if h and h[0] == "model" and all(c in h for c in COLUMNS):
            at = {field: h.index(col) for col, field in COLUMNS.items()}
            for r in rows:
                if len(r) != len(h):
                    continue
                name = _name(r[0])
                tier = _TIER.match(name)
                if tier:
                    name = tier.group(1)
                mid = PAGE_NAMES.get(name)
                if mid is None:
                    if name not in unknown:
                        unknown.append(name)
                    mid = page_id(name)
                    if mid not in want:
                        continue
                figures = {field: money(r[i]) for field, i in at.items()}
                got = rates.setdefault(mid, {})
                if tier and tier.group(2) == "over":
                    got.update({"long_" + k: v for k, v in figures.items()})
                    got["long_over"] = int(tier.group(3).replace(",", ""))
                else:
                    got.update(figures)
        elif h == ["model", "input", "output"]:
            # Fast mode, where one row can name two models.
            for r in rows:
                if len(r) != len(h):
                    continue
                for name in _name(r[0]).split(" / "):
                    mid = PAGE_NAMES.get(name.strip()) or page_id(name.strip())
                    if mid in rates:
                        rates[mid]["fast_in"] = money(r[1])
                        rates[mid]["fast_out"] = money(r[2])
    return rates, unknown
