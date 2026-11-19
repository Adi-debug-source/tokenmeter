"""Moonshot AI's Kimi API rates, international, in dollars per million tokens.

Read off https://platform.kimi.ai/docs/pricing/chat (where
platform.moonshot.ai/docs/pricing/chat now redirects), from the page's HTML,
on 27 October 2026: twice, independently, and a third time to settle. All
three copies were byte for byte the same page, and every figure agreed. The
page's metadata says it was last modified on 23 October 2026; it prints no
effective date for any rate. The first four rows were first read off the
page's markdown form on 26 September 2026 and are unchanged.

Read again on 19 November 2026, from two fetches at about 00:15 and at 00:46
UTC that were byte for byte the same (145,640 bytes), after the site was
rebuilt on Mintlify: every model and every figure as on 27 October. The
page's metadata now says it was last modified on 12 November 2026.

**Published, not measured.** Nobody has yet compared these with a real Kimi
bill. Please do, and open an issue either way.

The page has two tables. "K3 Series Models" lists kimi-k3.1-pro,
kimi-k3.1-pro-highspeed and kimi-k3, each with input, output, cached input,
a 5-minute cache write and a 1-hour cache write. "K2 Series Models" lists
kimi-k2.7-code, kimi-k2.7-code-highspeed and kimi-k2.6, with input, output
and cached input only. The page names every model by its API id, so this
file needs no PAGE_NAMES.

Rules taken from the page and modelled here:

  - The K3 series bills cache writes by lifetime: the 5-minute tier at the
    input rate and the 1-hour tier at twice it. A cache hit bills only at the
    cached rate.
  - kimi-k3.1-pro-highspeed's cached input is $0.20, the same as
    kimi-k3.1-pro's, while its input, output and both writes are double. That
    is what the page prints, in three identical copies, so its
    cache_read_mult is 0.05, not 0.1. It is not a slip; do not "correct" it.
  - The K2 models bill no cache write: the page lists no write price for
    them, and the maker's context caching guide says they do not support
    cache writes. A write a log records for one is priced as ordinary input,
    the table's default multiple of 1.0.
  - No long-context tier. Every K3 series model has a 1,048,576-token window
    and every K2 series model a 262,144-token one, each at one flat price;
    the K3.1 Pro and K3 guides say there is no tiering by context length.
  - A highspeed model is its own id with its own row, not the `fast` price of
    its base model, because a highspeed call records the highspeed id.

What the engine cannot express, and the choice made:

  - Thinking and non-thinking output: the page prints one output price per
    model, so there is no choice to make. K3.1 Pro, K3 and K2.7 Code always
    think; K2.6 can turn thinking off, at the same price. Thinking tokens
    are priced as output.
  - Several prompt-length tiers, and a discount with no end date: the page
    has neither.

What the page and the maker's guides say and this table deliberately leaves
out:

  - The context caching guide, and the K3.1 Pro and K3 guides after it (not
    the price page), say the cache is stored in blocks and a partial block
    is billed as a miss. A log records hits and writes as the API reported
    them, so this is already inside the counts.
  - Prices exclude taxes. A tax is not a per-token rate.
  - The file APIs are "temporarily free" and not priced per token. Web
    search prices are on another page and not modelled (WEB_SEARCH_PER_1K
    is 0.0); rate limits are access rules, not rates.
  - Batch: since November 2026 the page says kimi-k3.1-pro and kimi-k3
    support batch inference "billed at 60% of the standard price", with the
    batch prices on another page. Only the real-time rates are priced, as a
    log cannot tell a batch call.
  - The page's notice says that from 31 October 2026 the K2 series will no
    longer be available to newly registered users, existing users being
    unaffected, and that Moonshot plans to retire all K2 series models by
    the end of December 2026. On 19 November 2026 the page still carries
    that notice word for word, still lists and prices all three at the
    figures here, and still gives no retirement day, so none is in RETIRED
    yet. When the page drops them, their rows stay and go into RETIRED with
    the date Moonshot states.
  - The context caching guide writes kimi-k2.7 and kimi-k2.7-highspeed in
    its prose. They are not aliases here: the price page and the K2.7 Code
    guide name the models kimi-k2.7-code and kimi-k2.7-code-highspeed, and
    the shorter spellings are not confirmed as API ids.

FALLBACK_MODEL stays kimi-k3, as before. It is a choice for an id the table
does not know, flagged in every report, not a figure off the page.
"""

import json
import re

from .common import money

PROVIDER = "moonshot"
NAME = "Moonshot"
SOURCE = "https://platform.kimi.ai/docs/pricing/chat"
VERIFIED_ON = "2026-11-19"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 0.0
SNAPSHOT = r"(?!)"

PRICES = {
    "kimi-k3.1-pro":           [{"from": "", "in": 2.00, "out": 10.00, "cache_read_mult": 0.1, "fast": None,
                                 "write_mult": 1.0, "write_1h_mult": 2.0}],
    # Cached $0.20 as the page prints it, the same as kimi-k3.1-pro's.
    "kimi-k3.1-pro-highspeed": [{"from": "", "in": 4.00, "out": 20.00, "cache_read_mult": 0.05, "fast": None,
                                 "write_mult": 1.0, "write_1h_mult": 2.0}],
    "kimi-k3": [{"from": "", "in": 3.00, "out": 15.00, "cache_read_mult": 0.1, "fast": None,
                 "write_mult": 1.0, "write_1h_mult": 2.0}],
    "kimi-k2.7-code":           [{"from": "", "in": 0.95, "out": 4.00, "cache_read_mult": 0.19 / 0.95, "fast": None}],
    "kimi-k2.7-code-highspeed": [{"from": "", "in": 1.90, "out": 8.00, "cache_read_mult": 0.38 / 1.90, "fast": None}],
    "kimi-k2.6":                [{"from": "", "in": 0.95, "out": 4.00, "cache_read_mult": 0.16 / 0.95, "fast": None}],
}

FALLBACK_MODEL = "kimi-k3"

# The page's column titles, as the names page_rates() returns.
COLUMNS = {"Input": "in", "Output": "out", "Cached Input": "cached",
           "5m writes": "write_5m", "1h writes": "write_1h"}

_MANIFEST = '<template data-mint="manifest">'
# Each alternative opens with a different character and every `[^`]*` stops
# at a backtick, so neither pattern can backtrack badly on a hostile page.
# A column title: plain text, or a tooltip's text.
_TITLE = re.compile(r"`([^`]*)`|_jsx\(Tooltip,\{tip:`[^`]*`,children:`([^`]*)`\}\)")
# A row: the model's id, as plain text or as a link's text, then its cells.
_ROW = re.compile(r"(?:`(kimi-[a-z0-9.\-]+)`|_jsx\(_components\.a,\{href:`[^`]*`,children:`(kimi-[a-z0-9.\-]+)`\}\))"
                  r"((?:,`[^`]*`)*)")
_CELL = re.compile(r"`([^`]*)`")
_PER_MILLION = re.compile(r"\$[\d.,]+ / MTok")


def _tables(source):
    """Each table's column list and rows, as text, found by plain searches
    that only move forward, so the work stays linear in the page's size."""
    found, pos = [], 0
    while True:
        start = source.find("columns:[", pos)
        mid = source.find("],rows:[[", start) if start >= 0 else -1
        end = source.find("]]", mid) if mid >= 0 else -1
        if end < 0:
            return found
        start = source.rfind("columns:[", start, mid)
        found.append((source[start + len("columns:["):mid], source[mid + len("],rows:[["):end]))
        pos = end


def page_rates(fetch, tables, want=None):
    """Rates from the page's HTML, for every model it lists.

    The figures are in no HTML table and not in the markdown form: the
    markdown prints the tables empty, and the HTML holds no table, only
    <!-- --> where each would be. They are in embedded data, the page's
    manifest, a JSON object in <template data-mint="manifest">, whose
    page.mdx.mdxSource.compiledSource is the compiled page. There each table
    is written as columns:[{title:`Input`}, ...],rows:[[the model,
    `$2.00 / MTok`, ...], ...]; a cache column's title sits in a tooltip as
    children:`Cached Input`, and a model is its id as plain text (the K2
    rows) or as a link's text (the K3 rows). Columns are matched by title,
    never position: the two tables list different columns. Until November
    2026 the page was a Next.js build and the same compiled page arrived in
    self.__next_f.push script chunks; this reads only the manifest.

    Nothing is guessed. A page with no manifest gives no rates; a manifest
    without the compiled page raises, and --check-prices reports the page
    unreadable. A table with a column title not in COLUMNS, or not led by
    Model, is skipped whole; a row whose cells are not all dollars per MTok,
    or do not match the columns in number, is skipped. A row in a kept table
    that names no model in a form read here, or a model given two different
    figures for one column, raises, as the page does not say which applies.
    A changed layout therefore reads as models not found on the page or as
    a page that could not be read, never as a wrong figure. `tables` (the
    markdown tables) and `want` are not used: the page is one fetch and
    every row is read."""
    html = fetch(SOURCE)
    start = html.find(_MANIFEST)
    end = html.find("</template>", start) if start >= 0 else -1
    if end < 0:
        return {}, []
    manifest = json.loads(html[start + len(_MANIFEST):end])
    rates, seen = {}, []
    for cols, body in _tables(manifest["page"]["mdx"]["mdxSource"]["compiledSource"]):
        titles = []
        for part in cols.split("{title:")[1:]:
            t = _TITLE.match(part)
            titles.append((t.group(1) or t.group(2)) if t else None)
        keys = [COLUMNS.get(t) for t in titles[1:]]
        if not titles or titles[0] != "Model" or not keys or None in keys:
            continue
        for row in body.split("],["):
            m = _ROW.fullmatch(row)
            if not m:
                raise ValueError(f"a row in a price table the reader cannot read: {row[:80]!r}")
            model, cells = m.group(1) or m.group(2), _CELL.findall(m.group(3))
            if len(cells) != len(keys) or not all(_PER_MILLION.fullmatch(c) for c in cells):
                continue
            seen.append(model)
            into = rates.setdefault(model, {})
            for k, v in zip(keys, map(money, cells)):
                if into.get(k, v) != v:
                    raise ValueError(f"{model} {k}: the page prints both ${into[k]:g} and ${v:g}")
                into[k] = v
    return rates, sorted(m for m in set(seen) if m not in PRICES)
