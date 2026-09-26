"""Mistral's API rates, in dollars per million tokens. Standard tier.

Read off https://docs.mistral.ai/inference/pricing on 26 September 2026,
twice, independently, with every API id confirmed from its model card.

**Published, not measured.** Nobody has yet compared these with a real
Mistral bill. Please do, and open an issue either way.

Rules taken from the page and modelled here: cached input at the published
rate (a tenth of input on every model), no cache write charge, no long-context
tier. "-latest" aliases are not mapped, because the pages do not say which
model each points to today; a harness that records one is priced by the
online lookup and says so.
"""

import html
import re

PROVIDER = "mistral"
NAME = "Mistral"
SOURCE = "https://docs.mistral.ai/inference/pricing"
VERIFIED_ON = "2026-09-26"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 0.0
SNAPSHOT = r"(?!)"


def _row(inp, out):
    return [{"from": "", "in": inp, "out": out, "cache_read_mult": 0.1, "fast": None}]


PRICES = {
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

# How the page names each model.
PAGE_NAMES = {
    "Mistral Large 3": "mistral-large-2512", "Mistral Medium 3.5": "mistral-medium-3-5",
    "Mistral Small 4": "mistral-small-2603", "Ministral 3 14B": "ministral-14b-2512",
    "Ministral 3 8B": "ministral-8b-2512", "Ministral 3 3B": "ministral-3b-2512",
    "Codestral": "codestral-2508", "Z.ai GLM 5.3": "zai-glm-5-3", "Z.ai GLM 5.2": "zai-glm-5-2",
}

FALLBACK_MODEL = "mistral-medium-3-5"


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
