"""Z.ai's GLM API rates, international, in dollars per million tokens.

Read off https://docs.z.ai/guides/overview/pricing on 26 September 2026,
twice, independently, and again on 27 October 2026, twice independently and
a third time to settle, all three from one byte-identical copy of the page
(which Z.ai last changed on 21 October 2026). The page says "All prices are
in USD." Every figure on it matched the rows already here; the one model new
to the table is GLM-5.3-FlashX-Legal, sold at the FlashX figures to
enterprise customers by application (Z.ai's GLM-5.3-Flash guide).

The page is plain markdown, so --check-prices reads it exactly. The older
models sit in an "Other Pricing" accordion, which the markdown copy writes
as a blockquote ("> | GLM-4.5 | ..."); page_rates() strips that prefix
before parsing, or those eight models would read as missing from the page.

**Published, not measured.** Nobody has yet compared these with a real Z.ai
bill. Please do, and open an issue either way.

Rules taken from the page and modelled here:

  - Cached input has its own published rate per model, from the pricing
    table. (Z.ai's caching guide says hits are "usually 50%"; the table's
    per-model figures are lower, and the table is what bills.)
  - GLM-4-32B-0414-128K prints "-" for cached input: no lower rate is
    offered, so a cache hit costs its input price.
  - No cache write charge. Cache storage is "Limited-time Free", with no
    start date, end date or later price on the page, so it is priced as the
    page charges now, which is nothing: both write multiples are 1.0. If the
    offer ends, the page will have to print a rate before one can be added.
  - GLM-4.7-Flash and GLM-4.5-Flash are free.
  - One output price per model: the page prints a single Output column, so
    thinking and non-thinking output cost the same, and nothing about
    thinking is read from the log.
  - No long-context tier, no fast or priority tier and no time-of-day price
    on the API page. Every row is one rate, in force since launch.
  - Web search is modelled at the page's "Built-in Tools" price of $0.01
    per use: WEB_SEARCH_PER_1K is 10.0, dollars per 1,000 searches, as the
    Anthropic, OpenAI and xAI tables give theirs, so each search a harness
    logs against a GLM model is billed at the page's figure. The maintainer
    decided this on 1 November 2026; before, the constant was 0.0 (not
    modelled). The page gives no date from which searches were billed, so
    there is no dated WEB_SEARCH_RATES entry to start from: the figure
    applies to every call, earlier ones included, and a search logged
    before this change, priced at nothing then, now costs $0.01. If Z.ai
    states a start date, it becomes a dated list, as DeepSeek's is.

What the page lists and this table deliberately leaves out:

  - The GLM Coding Plan's off-peak rule (usage at 50% of the plan's credit
    rate outside Monday to Friday, 14:00 to 18:00 Singapore time). It is a
    subscription credit rule on the Coding Plan page, not a per-token API
    price, so no row has an off_peak key.
  - Vision models, per million tokens as input, cached input, output:
    GLM-4.6V $0.30, $0.05, $0.90; GLM-4.6V-FlashX $0.04, $0.004, $0.40;
    GLM-4.5V $0.60, $0.11, $1.80; GLM-OCR $0.03 input and $0.03 output with
    no cached rate; GLM-4.6V-Flash free.
  - Priced per item rather than per token: GLM-Image $0.015 and CogView-4
    $0.01 per image, CogVideoX-3 $0.20 per video, GLM-ASR-2512 $0.03 per
    million tokens of audio, and the agents (GLM Slide/Poster Agent $0.70 a
    million tokens, General-Purpose Translation $3 a million tokens, Popular
    Special Effects Video Templates $0.20 per video), which are products
    rather than chat model ids.
  - No batch, fine-tuning, embedding or rerank rate is printed, and no model
    is priced only in another currency.

No model has left the page and Z.ai has published no retirement notice for
any GLM text model, so there is no RETIRED entry. The page writes each model
as its display name (GLM-4.5-AirX); its id is that name in lowercase, so no
PAGE_NAMES is needed. Eleven of the seventeen ids are printed that way in
Z.ai's own guides and API reference; the other six (glm-4.7-flashx,
glm-4.7-flash, glm-4.5-x, glm-4.5-air, glm-4.5-airx, glm-4.5-flash) are
printed on none of the maker's pages read on 27 October 2026 and follow the
same pattern rather than a printed code. A call under a different string
passes through to the online lookup and shows in --by model.
"""

import re

from .common import money

PROVIDER = "zai"
NAME = "Z.ai"
SOURCE = "https://docs.z.ai/guides/overview/pricing"
SOURCE_MD = "https://docs.z.ai/guides/overview/pricing.md"
VERIFIED_ON = "2026-10-27"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 10.0
SNAPSHOT = r"(?!)"


def _row(inp, out, cached=None):
    mult = (cached / inp) if (cached is not None and inp) else (0.0 if not inp else 1.0)
    return [{"from": "", "in": inp, "out": out, "cache_read_mult": mult, "fast": None}]


PRICES = {
    "glm-5.3":              _row(1.40, 4.40, 0.26),
    "glm-5.3-flash":        _row(0.15, 0.50, 0.03),
    "glm-5.3-flashx":       _row(0.37, 1.25, 0.075),
    "glm-5.3-flashx-legal": _row(0.37, 1.25, 0.075),
    "glm-5.2":              _row(1.40, 4.40, 0.26),
    "glm-5.1":              _row(1.40, 4.40, 0.26),
    "glm-5":                _row(1.00, 3.20, 0.20),
    "glm-4.7":              _row(0.60, 2.20, 0.11),
    "glm-4.7-flashx":       _row(0.07, 0.40, 0.01),
    "glm-4.7-flash":        _row(0.0, 0.0),
    "glm-4.6":              _row(0.60, 2.20, 0.11),
    "glm-4.5":              _row(0.60, 2.20, 0.11),
    "glm-4.5-x":            _row(2.20, 8.90, 0.45),
    "glm-4.5-air":          _row(0.20, 1.10, 0.03),
    "glm-4.5-airx":         _row(1.10, 4.50, 0.22),
    "glm-4.5-flash":        _row(0.0, 0.0),
    "glm-4-32b-0414-128k":  _row(0.10, 0.10),
}

FALLBACK_MODEL = "glm-5.3"

# A blockquote marker at the start of a line, nested or not.
_QUOTE = re.compile(r"^(?:\s*>\s?)+")


def page_rates(fetch, tables, want=None):
    """Every text model on the markdown copy of the page, with its input,
    output and cached input in dollars per million tokens, and the page ids
    the table lacks. Every text model is returned, so `want` (a model the
    startup lookup is after) needs no filtering and is not used."""
    # The older models sit in an "Other Pricing" accordion, which the
    # markdown copy writes as a blockquote ("> | GLM-4.5 | ..."). Strip the
    # prefix so the table parser sees those rows and their heading.
    text = "\n".join(_QUOTE.sub("", line) for line in fetch(SOURCE_MD).splitlines())
    rates, seen = {}, []
    for title, header, rows in tables(text):
        # "Vision Models" has the same columns and is left out on purpose.
        if not title.lower().startswith(("latest models", "text models")):
            continue
        h = [c.strip().lower() for c in header]
        if h[:3] != ["model", "input", "cached input"]:
            continue
        for r in rows:
            mid = r[0].strip().lower()
            seen.append(mid)
            # The page writes a free model's prices as "Free". A figure stops at
            # a comma, as this reader always has; Z.ai's are all under $10.
            inp, cached, out = (money(r[i], free_is_zero=True, commas=False) for i in (1, 2, 4))
            rates[mid] = {"in": inp, "out": out, "cached": inp if cached is None else cached}
    return rates, sorted(m for m in set(seen) if m not in PRICES)
