"""xAI's Grok API rates, in dollars per million tokens. Standard tier.

Read off https://docs.x.ai/developers/pricing on 26 September 2026, twice,
independently, and checked against each model's own page. The page is plain
markdown, so --check-prices reads it exactly. Read again on 20 November 2026:
the seven models it lists, web search and the priority multiple are
unchanged, and grok-build-0.1 has left it (see RETIRED).

**Published, not measured.** Nobody has yet compared these with a real xAI
bill. Please do, and open an issue either way.

Rules taken from the pages and modelled here:

  - Cached input has its own published rate per model.
  - Long context: every model is billed at its higher rate, for every token
    in the request, once the prompt (cached tokens included) reaches 200K.
  - Reasoning tokens are billed as output.
  - Priority processing is 2x every rate, cache discount applied first. It is
    used when a call is recorded as fast.
  - Web search is $5 per 1,000 calls.

Not modelled: the 1.1x US regional endpoint, the Batch discount, other tool
fees (X search, code execution, collections), and Grok 4.7 Fast, which is
not on the public API.
"""

from .common import money

PROVIDER = "xai"
NAME = "xAI"
SOURCE = "https://docs.x.ai/developers/pricing"
SOURCE_MD = "https://docs.x.ai/developers/pricing.md"
VERIFIED_ON = "2026-11-20"
MEASURED = False

# No cache write fee: caching is automatic and only reads are discounted.
CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 5.0

# Dated ids (grok-4.20-0309) are listed as their own models or as aliases,
# so nothing is stripped.
SNAPSHOT = r"(?!)"

# "Reaches 200k" means 200,000 or more, and the engine tests "more than". The
# startup lookup applies it to a model the page gives long-context rates for.
LONG_OVER = 199_999
_LONG = {"over": LONG_OVER, "in": 2.0, "out": 2.0}


def _row(inp, out, cached):
    return {"from": "", "in": inp, "out": out, "cache_read_mult": cached / inp,
            "fast": (inp * 2, out * 2), "long": _LONG}


PRICES = {
    "grok-4.7":                     [_row(2.00, 6.00, 0.50)],
    "grok-4.6":                     [_row(2.00, 6.00, 0.50)],
    "grok-4.5":                     [_row(2.00, 6.00, 0.30)],
    "grok-4.3":                     [_row(1.25, 2.50, 0.20)],
    "grok-4.20-0309-reasoning":     [_row(1.25, 2.50, 0.20)],
    "grok-4.20-0309-non-reasoning": [_row(1.25, 2.50, 0.20)],
    "grok-4.20-multi-agent-0309":   [_row(1.25, 2.50, 0.20)],
    # The coding model. Retired (see RETIRED), at its last published price.
    "grok-build-0.1":               [_row(1.00, 2.00, 0.20)],
}

# xAI published no notice for grok-build-0.1: its release notes, read 20
# November 2026, announce the model and never its removal. The page listed
# it when this tool's daily check read it on 19 November 2026 (no public
# copy of that day exists; the archive's last are below) and not on the 20th,
# when its own page, docs.x.ai/developers/models/grok-build-0.1, answered
# with a redirect to the models list, which no longer names it either. So
# the date is the first day the page was read without it, not a shutdown
# xAI announced, and whether the API still answers to the id is not known.
# Its price is unchanged from 26 September: the Internet Archive's copy of
# the page of 14 November 2026 (20261114113159) prints $1.00, $0.20 cached
# and $2.00, twice that from 200K, and its copy of the model's own page of
# 17 November (20261117194518) the same, with the three grok-code-fast
# aliases below. Nothing xAI publishes says the id or those aliases now
# reach another model, so they are not moved.
RETIRED = {"grok-build-0.1": "2026-11-20"}

# Every alias the model pages list, to its canonical id.
ALIASES = {
    "grok-4.5-latest": "grok-4.5", "grok-build-latest": "grok-4.5",
    "grok-4.3-latest": "grok-4.3",
    "grok-code-fast-1": "grok-build-0.1", "grok-code-fast": "grok-build-0.1",
    "grok-code-fast-1-0825": "grok-build-0.1",
    **{a: "grok-4.20-0309-reasoning" for a in (
        "grok-4.20-reasoning-latest", "grok-4.20", "grok-4.20-reasoning", "grok-4.20-0309",
        "grok-4.20-beta-0309-reasoning", "grok-4.20-beta", "grok-4.20-beta-0309",
        "grok-4.20-beta-latest", "grok-4.20-beta-latest-reasoning", "grok-4.20-beta-reasoning",
        "grok-4.20-experimental-beta-0304-reasoning", "grok-4.20-experimental-beta-0304",
        "grok-4.20-experimental-beta-reasoning-latest", "grok-4.20-experimental-beta-latest",
        "grok-4.20-reasoning-gv2")},
    **{a: "grok-4.20-0309-non-reasoning" for a in (
        "grok-4.20-non-reasoning", "grok-4.20-non-reasoning-latest",
        "grok-4.20-beta-non-reasoning", "grok-4.20-beta-latest-non-reasoning",
        "grok-4.20-experimental-beta-0304-non-reasoning",
        "grok-4.20-experimental-beta-non-reasoning-latest",
        "grok-4.20-beta-0309-non-reasoning", "grok-4.20-non-reasoning-gv2")},
    **{a: "grok-4.20-multi-agent-0309" for a in (
        "grok-4.20-multi-agent", "grok-4.20-multi-agent-latest",
        "grok-4.20-multi-agent-beta-latest", "grok-4.20-multi-agent-experimental-beta-0304",
        "grok-4.20-multi-agent-experimental-beta-latest", "grok-4.20-multi-agent-beta-0309")},
}

FALLBACK_MODEL = "grok-4.7"


def page_rates(fetch, tables, want=None):
    """Every text-model rate on the page, as {model id: {field: $/MTok}}.
    Used by --check-prices and the startup lookup; never edits this file."""
    rates, seen = {}, []
    for title, header, rows in tables(fetch(SOURCE_MD)):
        h = [c.strip().lower() for c in header]
        if h[:3] != ["model", "context", "input / 1m tokens"]:
            continue
        for r in rows:
            mid, _, qual = r[0].partition(" (")
            mid = mid.strip()
            seen.append(mid)
            entry = rates.setdefault(mid, {})
            if "≥" in qual or ">=" in qual:
                entry["long_in"], entry["long_out"] = money(r[2]), money(r[4])
            else:
                entry.update({"in": money(r[2]), "cached": money(r[3]), "out": money(r[4])})
    unknown = sorted(m for m in set(seen) if m not in PRICES and m not in ALIASES)
    return rates, unknown
