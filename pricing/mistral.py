"""Mistral's API rates, in dollars per million tokens. Standard tier.

Read off https://docs.mistral.ai/inference/pricing on 26 September 2026,
twice, independently, with every API id confirmed from its model card, and
re-read in full on 6 October 2026. Mistral Large 4 added from the page as
saved on 2 November 2026, its id mistral-large-4 (and the card's second
name, mistral-large-4-0) from its model card and Mistral's changelog.

**Published, not measured.** Nobody has yet compared these with a real
Mistral bill. Please do, and open an issue either way.

Rules taken from the page and modelled here: cached input at the published
rate (a tenth of input on every model), no cache write charge, no long-context
tier. "-latest" aliases are not mapped, because the pages do not say which
model each points to today; a harness that records one is priced by the
online lookup and says so.

Mistral Large 4 has one row, from launch, at the price the page prints on 2
November 2026: $0.70 in, $0.07 cached, $2.10 out. Mistral did not charge
that for the whole of Large 4's life. Internet Archive copies of this same
pricing page (https://web.archive.org/web/<capture>/ followed by SOURCE)
print three prices for it, per million tokens:

- Launch sale. Mistral's changelog, 6 October 2026: "Launch pricing: 50% off
  for 2 weeks". The captures of 11 and 17 October 2026 (20261011225712,
  20261017055018) print "Sale price" $0.68 in, $0.07 cached, $2.09 out,
  against "Original price" $1.36, $0.14 and $4.18.
- After the sale: $1.36 in, $0.14 cached, $4.18 out, in the captures of 21
  and 29 October 2026 (20261021005556, 20261029025927).
- From a cut made between the captures of 29 October 2026, 02:59 UTC, and 1
  November 2026, 13:01 UTC (20261101130106): $0.70, $0.07 and $2.10.

So a call in the launch sale is priced a little above what Mistral charged
($0.70 against $0.68 in, $2.10 against $2.09 out), and a call between the
end of the sale (after 17 October and by 21 October) and the cut at about
half of it: a million tokens in and a million out cost $2.80 here against
$5.54 on the page then. These are not dated rows yet,
because these tables take a price from an archive copy only for a retired
model, and neither boundary is printed to the day. Whether to add them is an
open question. If they are added, each needs its own cache_read_mult: the
archived cached rates are 0.07/0.68 and 0.14/1.36 of input, not a tenth.

FALLBACK_MODEL is mistral-large-4, the dearest of Mistral's own models the
page prices, and the model Mistral names as the replacement for both Mistral
Large 3 and Mistral Medium 3.5, the fallback until 2 November 2026, which
Mistral deprecated on 31 October 2026. Z.ai GLM 5.3 costs more, but it is
another maker's model hosted by Mistral. The fallback is a choice for an id
the table does not know, flagged in every report, not a figure off the page.
"""

import html
import re

PROVIDER = "mistral"
NAME = "Mistral"
SOURCE = "https://docs.mistral.ai/inference/pricing"
VERIFIED_ON = "2026-11-02"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 0.0
SNAPSHOT = r"(?!)"


def _row(inp, out):
    return [{"from": "", "in": inp, "out": out, "cache_read_mult": 0.1, "fast": None}]


PRICES = {
    "mistral-large-4":    _row(0.70, 2.10),
    "mistral-large-2512": _row(0.50, 1.50),
    "mistral-medium-3-5": _row(1.50, 7.50),
    "mistral-small-2603": _row(0.15, 0.60),
    "ministral-14b-2512": _row(0.20, 0.20),
    "ministral-8b-2512":  _row(0.15, 0.15),
    "ministral-3b-2512":  _row(0.10, 0.10),
    "codestral-2508":     _row(0.30, 0.90),
    # Z.ai's models, hosted and billed by Mistral at Mistral's own price.
    "zai-glm-5-3":        _row(1.40, 4.40),
    "zai-glm-5-2":        _row(1.40, 4.40),
}

# Kept for older usage, at the last published price, though the pricing page
# no longer lists them. Model id: retirement date. Mistral's changelog, read
# 6 October 2026: GLM 5.2 deprecated 29 September, retires 31 October 2026,
# "Use Z.ai GLM 5.3 (zai-glm-5-3) instead, at the same price".
# Mistral Large 3 and Mistral Medium 3.5 left the pricing page when Mistral
# deprecated them on 31 October 2026. Notice: the table "Deprecated & retired
# models" at https://docs.mistral.ai/models/overview, read 2 November 2026,
# gives each "Deprecation 10/31/2026, Retirement 4/30/2027, Alternative
# Mistral Large 4", and each model card says "This model is deprecated. Use
# Mistral Large 4 for new integrations." The API answers to them until the
# retirement date, but no page prints a price for them any more, so calls
# made after 31 October 2026 are priced at the last published rate.
RETIRED = {
    "zai-glm-5-2": "2026-10-31",
    "mistral-large-2512": "2027-04-30",
    "mistral-medium-3-5": "2027-04-30",
}

# Other published names. Mistral Large 4's model card, read 2 November 2026,
# lists its API names as mistral-large-4 and mistral-large-4-0. They are the
# same model at the same price today, but not for good: Mistral's lifecycle
# page calls a model-name-major id such as mistral-large-4 an alias for the
# "Latest minor version of that major generation", warning that "Using an
# alias may expose you to silent updates in model behavior and pricing", and
# the major-minor id, mistral-large-4-0, the fixed version. If a later minor
# version (a Large 4.1) is priced differently, mistral-large-4 gets a dated
# row and mistral-large-4-0 leaves this map for a row of its own at the 4.0
# price, or its calls would move with the alias.
ALIASES = {"mistral-large-4-0": "mistral-large-4"}

# How the page names each model.
PAGE_NAMES = {
    "Mistral Large 4": "mistral-large-4",
    "Mistral Large 3": "mistral-large-2512", "Mistral Medium 3.5": "mistral-medium-3-5",
    "Mistral Small 4": "mistral-small-2603", "Ministral 3 14B": "ministral-14b-2512",
    "Ministral 3 8B": "ministral-8b-2512", "Ministral 3 3B": "ministral-3b-2512",
    "Codestral": "codestral-2508", "Z.ai GLM 5.3": "zai-glm-5-3", "Z.ai GLM 5.2": "zai-glm-5-2",
}

FALLBACK_MODEL = "mistral-large-4"


def page_rates(fetch, tables, want=None):
    """The page lays prices out in styled blocks, not <table> elements, so it
    is read as text: each model's name followed by input, cached and output."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", fetch(SOURCE), flags=re.S)
    text = re.sub(r"\s*\|[\s|]*", " | ", html.unescape(re.sub(r"<[^>]+>", "|", t)))
    rates = {}
    for name, mid in PAGE_NAMES.items():
        m = re.search(re.escape(name) + r" \| (?:↗ \| )?\$([\d.]+) \| \$([\d.]+) \| \$([\d.]+)", text)
        if m:
            inp, cached, out = (float(x) for x in m.groups())
            rates[mid] = {"in": inp, "cached": cached, "out": out}
    return rates, []
