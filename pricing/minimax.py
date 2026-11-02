"""MiniMax's API rates, international, in dollars per million tokens.

Read off https://platform.minimax.io/docs/pricing/overview, section "LLM",
from the page's markdown form (the same URL with .md), saved on 2 November
2026 and read by script into rows. The page names every model by its API id
(MiniMax-M3.1-Flash, MiniMax-M3), the ids the model list and the API guides
use, so this file needs no PAGE_NAMES. The page prints no effective date for
any rate.

**Published, not measured.** Nobody has yet compared these with a real
MiniMax bill. Please do, and open an issue either way.

The section has three tables, all with the columns Model, Input, Output and
"Prompt caching Read", in dollars per million tokens: an untabbed one for
MiniMax-M3.1-Flash, and two tabs, "Standard" and "Priority", for MiniMax-M3,
each with a row up to 512k input tokens and a row over it.

Rules taken from the page and modelled here:

  - A cache hit bills at the page's "Prompt caching Read" figure: $0.015 for
    MiniMax-M3.1-Flash (0.1 of input) and $0.06 for MiniMax-M3 (0.2 of
    input).
  - No cache write charge. The page prints no write price, and the prompt
    caching guide says new input tokens bill at the standard input price,
    so a write is priced as ordinary input, the table's default of 1.0.
  - MiniMax-M3 is priced by prompt length. A request over 512k input tokens
    pays twice every rate ($0.60 in, $2.40 out, $0.12 a cache hit, against
    $0.30, $1.20 and $0.06), for the whole request, cache hits included.
    MiniMax writes its 1M context window as 1,000,000 tokens, so 512k is
    read as 512,000. MiniMax-M3.1-Flash has one flat price.
  - MiniMax-M3's "Priority" tab (service_tier "priority", "1.5x standard")
    is its `fast` price, as Codex's priority tier is: $0.45 in and $1.80
    out. Its cache hit ($0.09) and its over-512k row ($0.90, $3.60, $0.18)
    are what the engine charges a priority call from those, with the same
    0.2 cache multiple and the same doubling, so one row holds every
    Priority figure. The tests pin that against the engine's own charge;
    page_rates() returns the four figures as the page prints them
    (fast_cached and fast_long_in, fast_long_out, fast_long_cached) for the
    live check to compare, and works none of them out itself.
  - Web search, a server tool, is $0.01 a request: $10 per 1,000.

What the engine cannot express, and the choice made:

  - A discount with no end date. Every MiniMax-M3 row reads "Permanent 50%
    off", with the list price struck through beside the charged one. As the
    brief rules, it is priced as the page charges now; the struck list
    prices were $0.60 in, $2.40 out and $0.12 cached up to 512k, $1.20,
    $4.80 and $0.24 over it, and for Priority $0.90, $3.60 and $0.18 up to
    512k, $1.80, $7.20 and $0.36 over it.
  - Thinking and non-thinking output: the page prints one output price per
    model, so there is no choice to make. MiniMax-M3.1-Flash always thinks;
    MiniMax-M3 thinks only when asked. Thinking tokens are priced as output.
  - Several prompt-length tiers: MiniMax-M3 has one threshold, which the
    engine's single `long` holds.

What the page and the maker's guides say and this table deliberately leaves
out:

  - A Priority price for MiniMax-M3.1-Flash. The page prints no Priority row
    for it, so a call recorded as priority prices at its standard rate. The
    footnote's "1.5x standard" is not applied to a row the page does not
    print.
  - Caching applies only to calls of 512 or more input tokens (the caching
    guide). A log records hits as the API reported them, so this is already
    inside the counts.
  - The rest of the page: video (including MiniMax-H3-Context-IR, which the
    page lists under Video per million tokens), audio, image and music are
    not text models, and API-vlm (an MCP tool) bills $0.01 a request; none
    is priced here. Audio and video packages and the M Plan are
    subscriptions, not per-token rates.
  - The M2 models. The model list's table marks MiniMax-M2.7,
    MiniMax-M2.7-highspeed, MiniMax-M2.5, MiniMax-M2.5-highspeed,
    MiniMax-M2.1, MiniMax-M2.1-highspeed, MiniMax-M2 and M2-her as retired,
    yet a notice on the same page says existing users can call the M2.5 and
    M2.7 models until their retirement on 18 November 2026. So calls to
    those are made today, while the price page prices none of the M2
    models, and none has a row here: no current price was read for any of
    them. A call to one goes to the startup lookup, which tries this page
    (no row) and then LiteLLM's list, and a figure found there is labelled
    as looked up. With no looked-up price, the engine prices the call at
    FALLBACK_MODEL, MiniMax-M3, and flags it as unrecognised in every
    report; that charge is a stand-in, not MiniMax's price for the model.

FALLBACK_MODEL is MiniMax-M3, the dearer of the two models at the standard
rate. It is a choice for an id the table does not know, flagged in every
report, not a figure off the page.
"""

import re

from .common import money

PROVIDER = "minimax"
NAME = "MiniMax"
SOURCE = "https://platform.minimax.io/docs/pricing/overview"
SOURCE_MD = "https://platform.minimax.io/docs/pricing/overview.md"
VERIFIED_ON = "2026-11-02"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 10.0
SNAPSHOT = r"(?!)"

# "≤ 512k input tokens" and "> 512k input tokens" on the page.
LONG_OVER = 512_000

PRICES = {
    "MiniMax-M3.1-Flash": [{"from": "", "in": 0.15, "out": 0.60, "cache_read_mult": 0.015 / 0.15,
                            "fast": None}],
    "MiniMax-M3": [{"from": "", "in": 0.30, "out": 1.20, "cache_read_mult": 0.06 / 0.30,
                    "fast": (0.45, 1.80),
                    "long": {"over": LONG_OVER, "in": 2.0, "out": 2.0}}],
}

# The dearer of the two at the standard rate.
FALLBACK_MODEL = "MiniMax-M3"

# The page's column titles, less their "$ / M tokens", as page_rates() names.
COLUMNS = {"input": "in", "output": "out", "prompt caching read": "cached"}
# The LLM section's tabs: none (MiniMax-M3.1-Flash), Standard and Priority.
TABS = {"": "standard", "standard": "standard", "priority": "fast"}

_QUOTE = re.compile(r"^(?:\s*>\s?)+")
_TAB = re.compile(r"\[tab\]\s*(.+)")
_STRUCK = re.compile(r"~~.*?~~")
_FIGURE = re.compile(r"\$\d+(?:\.\d+)?")
_NAME = re.compile(r"\*\*([^*]+)\*\*\s*(.*)")
_TIER = re.compile(r"(≤|<=|>)\s*(\d+)\s*([kM])\s*input tokens")
_DISCOUNT = re.compile(r"Permanent \d+% off")


def _llm_text(page):
    """The page's LLM section with its blockquotes opened, markdown escapes
    removed and each tab written as a heading, "LLM [tab] Priority", so the
    table parser sees which tab a table sits in."""
    out, section = [], ""
    for line in page.replace("\\", "").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        if section != "LLM":
            continue
        s = _QUOTE.sub("", line).strip()
        tab = _TAB.fullmatch(s)
        out.append("### LLM [tab] " + tab.group(1).strip("* ") if tab else s)
    return "\n".join(out)


def _needed(row):
    """The fields the page must give for a table row to be checked in full:
    every rate the row charges, so none can go stale unread."""
    need = {"in", "out", "cached"}
    if row.get("long"):
        need |= {"long_over", "long_in", "long_out", "long_cached"}
    if row["fast"]:
        need |= {"fast_in", "fast_out", "fast_cached"}
        if row.get("long"):
            need |= {"fast_long_in", "fast_long_out", "fast_long_cached"}
    return need


def page_rates(fetch, tables, want=None):
    """Every text model in the page's LLM section, read off its markdown
    form, as {model id: {field: $/MTok}}, and the page ids the table lacks.

    Each model's untabbed or Standard rows give in, out and cached; a row
    over N input tokens gives the same three with long_ in front, and
    long_over is N. The Priority tab's rows give the same with fast_ and
    fast_long_ in front: fast_in, fast_out, fast_cached, fast_long_in,
    fast_long_out and fast_long_cached. A cell reads the charged figure: a
    struck list price ("~~$0.60~~ $0.30") is dropped first. Every figure is
    returned as the page prints it, and nothing is worked out here: the
    engine's expected_rates() says what each field should be, so the rule
    for a priority call's cache hit and long tier lives in one place.

    Nothing is guessed. A table outside the LLM section, in a tab not in
    TABS, or with a column not in COLUMNS or not in "$ / M tokens", is
    skipped whole; so is a row whose model cell holds anything but the id,
    a length tier and a "Permanent N% off" label, or whose cells are not
    each one dollar figure. A skipped table or row cannot let a rate go
    unchecked: a model in PRICES that the page lists without every field its
    row charges (a renamed or removed Priority tab, a lost over-N row, a
    dropped cache column) raises ValueError naming it and the fields
    missing, so --check-prices reports the page as not read and fails. So
    does a model with more than one prompt-length threshold, or listed twice
    at different figures. These were once named among the models the table
    lacks, where the check printed "2 of 2 models match" above "on the page
    but not in the table: MiniMax-M3 (not on the page: ...)". Every model is
    returned; `want` (the ids the startup lookup asks for, which the table
    lacks) only narrows the problems that raise to those ids, so a lost tab
    does not stop the lookup reading a new model."""
    found, seen, problems = {}, [], []
    for title, header, rows in tables(_llm_text(fetch(SOURCE_MD))):
        if title == "LLM":
            tab = ""
        elif title.startswith("LLM [tab] "):
            tab = title[len("LLM [tab] "):].strip().lower()
        else:
            continue
        kind = TABS.get(tab)
        h = [c.replace("*", "").strip().lower() for c in header]
        if kind is None or not h or h[0] != "model":
            continue
        keys = []
        for col in h[1:]:
            name, unit, _ = col.partition(" $ / m tokens")
            keys.append(COLUMNS.get(name) if unit and not _ else None)
        if not keys or None in keys:
            continue
        for r in rows:
            name = _NAME.fullmatch(r[0].strip()) if len(r) == len(h) else None
            if not name:
                continue
            mid = name.group(1).strip()
            label = _DISCOUNT.sub("", name.group(2).replace("*", "")).strip()
            tier = _TIER.fullmatch(label) if label else None
            cells = [_STRUCK.sub("", c).strip() for c in r[1:]]
            if (label and not tier) or not all(_FIGURE.fullmatch(c) for c in cells):
                continue
            seen.append(mid)
            figures = {k: money(c) for k, c in zip(keys, cells)}
            band, over = "base", None
            if tier:
                over = int(tier.group(2)) * (1000 if tier.group(3) == "k" else 1_000_000)
                band = "long" if tier.group(1) == ">" else "base"
            bands = found.setdefault(mid, {}).setdefault(kind, {})
            if band in bands and bands[band] != (figures, over):
                problems.append((mid, f"{mid} (listed twice at different figures)"))
            bands[band] = (figures, over)

    rates = {}
    for mid, kinds in found.items():
        std, pri = kinds.get("standard", {}), kinds.get("fast", {})
        if "base" not in std:
            continue
        overs = {o for bands in (std, pri) for _, o in bands.values() if o is not None}
        if len(overs) > 1:
            problems.append((mid, f"{mid} (more than one prompt-length threshold)"))
            continue
        got = rates[mid] = dict(std["base"][0])
        if "long" in std:
            got.update({"long_" + k: v for k, v in std["long"][0].items()})
            got["long_over"] = std["long"][1]
        if "base" in pri:
            got.update({"fast_" + k: v for k, v in pri["base"][0].items()})
        if "long" in pri:
            got.update({"fast_long_" + k: v for k, v in pri["long"][0].items()})
        if mid in PRICES:
            missing = _needed(PRICES[mid][-1]) - set(got)
            if missing:
                problems.append((mid, f"{mid} (not on the page: {', '.join(sorted(missing))})"))
    # A problem is not a model the table lacks, so it is never put in that
    # list, where --check-prices would print it under "on the page but not
    # in the table". The page is reported as not read instead, as a changed
    # layout is. The startup lookup asks only for ids the table lacks, so a
    # problem with another model does not stop it reading the one it wants.
    bad = sorted({text for mid, text in problems if want is None or mid in want})
    if bad:
        raise ValueError("the page's LLM rates could not be read in full: " + "; ".join(bad))
    unlisted = sorted(m for m in set(seen) if m not in PRICES)
    return rates, unlisted
