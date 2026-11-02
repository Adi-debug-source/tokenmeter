"""Xiaomi MiMo API rates, overseas, in dollars per million tokens.

Read off the maker's pay-as-you-go price page on 2 November 2026: the
prerendered English page at https://mimo.mi.com/docs/en-US/price/pay-as-you-go
and its markdown source at
https://mimo.mi.com/static/docs/price/pay-as-you-go.md, which give the same
rows. The Open Platform's 'API Pricing' link points at
https://mimo.mi.com/docs/price/pay-as-you-go, which is a JavaScript shell
with no figures in it. The page prints no effective date for any rate.

**Published, not measured.** Nobody has yet compared these with a real MiMo
bill. Please do, and open an issue either way.

The page has two price sections side by side: 'Domestic Pricing of the
Model' in yuan and 'Overseas Pricing of the Model' in dollars, with the
billing note 'Billing Unit: China: RMB / M tokens; Overseas: dollar / M
tokens'. Only the overseas section is used; a yuan figure is never
converted. Its 'Language Models' table has the columns Inference Type,
Model Name, Input (Cache Hit), Input (Cache Miss) and Output, in two groups:
'Real-time API' (mimo-v2.6-pro, mimo-v2.6-flash, mimo-v2.6-pro-ultraspeed)
and 'Batch API'. The page names every model by its API id, as the model list
at https://mimo.mi.com/static/docs/quick-start/summary/model.md confirms, so
this file needs no PAGE_NAMES.

Rules taken from the page and modelled here:

  - A cache hit bills at the page's 'Input (Cache Hit)' price and every other
    prompt token at 'Input (Cache Miss)', which is this table's `in`.
  - mimo-v2.6-pro-ultraspeed is its own id with its own row, at ten times
    mimo-v2.6-pro's prices in every column, not the `fast` price of
    mimo-v2.6-pro: the model list names it as a separate model id, and a
    call to it records that id.
  - Web search is billed per call, not per token: 'Overseas Internet
    Connectivity Service', $5 per 1,000 times, which the page says covers
    web search and web parsing. WEB_SEARCH_PER_1K is that $5. A log records
    searches only, so a parsing call it does not count is not priced.
  - No long-context tier. Each model has one row at one price; the model list
    gives each a 1M token context window with no bands.

What the engine cannot express, and the choice made:

  - Thinking and non-thinking output: the page prints one output price per
    model, so there is no choice to make. Reasoning tokens are priced as
    output.
  - Several prompt-length tiers: the page has none.
  - A discount with no end date: 'Cache Write: Limited-time Free', with no
    end date. Under the project's rule it is priced as the page charges now:
    no charge for writing beyond the price of the prompt tokens themselves.
    MiMo's OpenAI and Anthropic API references (read on 2 November 2026)
    report only a cache hit count, cached_tokens and cache_read_input_tokens,
    and no write count, so every written token reaches a log as a cache-miss
    input token and is billed at `in`. A write count a log might still carry
    is therefore priced as ordinary input, the default multiple of 1.0. When
    the free period ends the page should print a write price, and that is a
    new dated row.

What the page says and this table deliberately leaves out:

  - The 'Batch API' rows (mimo-v2.6-pro and mimo-v2.6-flash at half the
    real-time prices). A log does not say a call went through the batch API.
  - mimo-v2.5-asr, billed per hour of input audio, and the TTS models
    mimo-v2.5-tts, mimo-v2.5-tts-voiceclone and mimo-v2.5-tts-voicedesign,
    'Free for a limited time'. Neither is a per-token text price.
  - The yuan section, and the Token Plan subscription, which is a package
    quota and not a per-token price.
  - Retired models. mimo-v2.5-pro and mimo-v2.5 were deprecated on 21
    October 2026 and mimo-v2-pro, mimo-v2-omni and mimo-v2-flash on 30 June
    2026, by the maker's deprecation notice; the current page prices none of
    them, so none has a row and none is in RETIRED.

FALLBACK_MODEL is mimo-v2.6-pro, the dearest of the standard models. It is
a choice for an id the table does not know, flagged in every report, not a
figure off the page. mimo-v2.6-pro-ultraspeed costs more, but it is a
premium speed tier whose own id is in the table, so an unknown id is far
more likely a standard model than another ultraspeed one.

page_rates() reads the markdown source, whose tables are HTML. It reads only
the overseas section, only the 'Real-time API' rows, and only cells that are
dollar figures; anything else is skipped, so a changed layout reads as
models not found on the page, never as a wrong figure.
"""

import re
from html.parser import HTMLParser

from .common import money

PROVIDER = "mimo"
NAME = "Xiaomi MiMo"
SOURCE = "https://mimo.mi.com/docs/en-US/price/pay-as-you-go"
SOURCE_MD = "https://mimo.mi.com/static/docs/price/pay-as-you-go.md"
VERIFIED_ON = "2026-11-02"
MEASURED = False

CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 5.0
SNAPSHOT = r"(?!)"


def _row(cached, inp, out):
    """A row from the page's three columns, in the page's order: cache hit,
    cache miss, output."""
    return [{"from": "", "in": inp, "out": out, "cache_read_mult": cached / inp, "fast": None}]


PRICES = {
    "mimo-v2.6-pro":            _row(0.0036, 0.435, 0.87),
    "mimo-v2.6-flash":          _row(0.0028, 0.14, 0.28),
    "mimo-v2.6-pro-ultraspeed": _row(0.036, 4.35, 8.7),
}

# The dearest standard model; see the docstring.
FALLBACK_MODEL = "mimo-v2.6-pro"

# The page's column titles, as the names page_rates() returns.
COLUMNS = {"Input (Cache Hit)": "cached", "Input (Cache Miss)": "in", "Output": "out"}

# The section with dollar prices, up to the next heading.
_OVERSEAS = re.compile(r"^#+\s*Overseas Pricing of the Model\s*$(.*?)(?=^#)", re.M | re.S)
# The billing note's unit for that section.
_UNIT = re.compile(r"Overseas:\s*dollar\s*/\s*M tokens", re.I)
_ID = re.compile(r"mimo-[a-z0-9.\-]+")
_FIGURE = re.compile(r"\$\d+(?:\.\d+)?")


class _Tables(HTMLParser):
    """The HTML tables in a piece of the page, as rows of cell text, with a
    cell spanning several rows (the page's 'Inference Type') carried into
    each row it spans."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._rows, self._row, self._cell = [], None, None, None
        self._span, self._down = 1, {}

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._rows, self._down = [], {}
        elif tag == "tr" and self._rows is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            span = dict(attrs).get("rowspan") or "1"
            self._span = int(span) if span.isdigit() else 1

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append((" ".join("".join(self._cell).split()), self._span))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            full, given, col = [], list(self._row), 0
            while given or col in self._down:
                if col in self._down:
                    text, left = self._down.pop(col)
                    if left > 1:
                        self._down[col] = (text, left - 1)
                else:
                    text, span = given.pop(0)
                    if span > 1:
                        self._down[col] = (text, span - 1)
                full.append(text)
                col += 1
            self._rows.append(full)
            self._row = None
        elif tag == "table" and self._rows is not None:
            self.tables.append(self._rows)
            self._rows = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def page_rates(fetch, tables, want=None):
    """Every model in the overseas section's 'Real-time API' rows, with its
    input, output and cached input in dollars per million tokens, and the
    page ids the table lacks.

    The markdown source writes its tables in HTML, so `tables` (the markdown
    table reader) finds nothing and is not used; a small HTML parser reads
    them instead. Columns are matched by title, never position. Nothing is
    guessed: if the billing note no longer says the overseas unit is dollars
    per million tokens, nothing is read; a table not headed Inference Type,
    Model Name and the three price columns is skipped; and a row that is not
    'Real-time API', whose name is not an id, or whose cells are not all
    dollar figures, is skipped. The 'Batch API' rows are left out on
    purpose. The page is one fetch and every row is read, so `want` (a model
    the startup lookup is after) is not used."""
    text = fetch(SOURCE_MD)
    section = _OVERSEAS.search(text + "\n#")
    if not section or not _UNIT.search(text):
        return {}, []
    parser = _Tables()
    parser.feed(section.group(1).replace("**", "").replace("`", ""))
    rates, seen = {}, []
    for rows in parser.tables:
        if not rows or rows[0][:2] != ["Inference Type", "Model Name"]:
            continue
        keys = [COLUMNS.get(t) for t in rows[0][2:]]
        if not keys or None in keys:
            continue
        for row in rows[1:]:
            if len(row) != len(keys) + 2 or row[0] != "Real-time API":
                continue
            mid, cells = row[1], row[2:]
            if not _ID.fullmatch(mid) or not all(_FIGURE.fullmatch(c) for c in cells):
                continue
            seen.append(mid)
            rates[mid] = {k: money(c) for k, c in zip(keys, cells)}
    return rates, sorted(m for m in set(seen) if m not in PRICES)
