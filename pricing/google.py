"""Google's Gemini Developer API rates, in dollars per million tokens.

Read off https://ai.google.dev/gemini-api/docs/pricing on 26 September 2026
(the page's own footer read "Last updated 2026-09-24 UTC"), Standard tier,
paid. Read twice, independently: once by hand with every figure quoted, and
once by the page reader below, and the two agreed on every figure. Re-read in
full on 6 October 2026, and again on 15 October 2026 (footer "Last updated
2026-10-15 UTC"), by which time gemini-3.5-flash and gemini-3.7-flash had
left the page; see RETIRED. Gemini 4 Argon was read off the page on 16
October 2026, the rest matching as before.

On 27 October 2026 (footer "Last updated 2026-10-27 UTC") the page was read
again in full, Paid Tier, by two readers working apart, each of whom typed
every figure of the ten current text models in all four priced tiers
(Standard, Flex, Priority, Contributor); every figure they typed was then
checked against the page's own HTML, and every difference between them
settled by reading the page again. No Standard rate had changed. The Priority
tier was added to every row that has one (`fast`, below), and nineteen
retired models are now kept. The sixteen new here are each priced from an
Internet Archive copy of this same Google page; the other three (2.5 Computer
Use, 3.5 Flash and 3.7 Flash) were read off the live page before it dropped
them, except the Priority pairs of 3.5 and 3.7 Flash, added on 27 October
from capture 20261008045525 (see RETIRED).

By 2 November 2026 the page had moved: the old address above redirects to
https://aistudio.google.com/docs/pricing, which is rendered in the browser
from Markdoc, so the old reader found no rates in it. The page reader now
reads the same Markdoc at SOURCE_MD, and on 2 November 2026 it found every
figure of the ten current text models as this table holds it. The old
address's own markdown copy (pricing.md.txt) is still served but no longer
agrees with the page in every tier, so it is not read.

**Published, not measured.** Nobody has yet compared these with a real Gemini
bill or a harness's own cost report. Please do, and open an issue either way.

Rules taken from the page and modelled here:

  - Output is priced "including thinking tokens". Gemini's own usage report
    counts thoughts separately from the answer, so an adapter or import must
    add them into output.
  - Cached input is 0.1x input on every current text model that offers
    caching, except Gemini 4 Argon, at 0.05x (implicit caching only). The
    retired models carry their own multiples, as their pages printed them.
  - Long context: Gemini 3.1 Pro Preview and 2.5 Pro, and the retired 3 Pro
    Preview and 2.5 Pro Previews, charge 2x input and cache rates and 1.5x
    output for prompts over 200K tokens. The retired 2.5 Computer Use did the
    same for input and output; it printed no caching price, so it has no
    cache rate to double. The retired 1.5 series doubled input, output and
    cache above 128K tokens.
  - Gemini 3.6 and 3.8 Flash have two published prices, one through 31
    December 2026 and a higher one from 1 January 2027, as 3.7 Flash had
    before it was retired, and Gemini 4 Argon one through 30 November 2026
    and double from 1 December. Both are in the table as dated entries, so
    each call is priced at the rate in force that day.
  - The Priority tier is `fast`: the engine's rate for a call a reader records
    as fast or priority, which is how the Codex reader already maps a
    "priority" service tier. The existing rows had no fast price; filling it
    is an edit to old rows, agreed by the maintainer on 1 November 2026, and
    it moves a figure: no Gemini log reader records a tier, but a call brought
    in with --import as provider "google" and speed "fast" was priced at
    Standard and is now priced at Priority (gemini-2.5-flash, a million tokens
    in and out: $2.80 before, $5.04 now). A reader that later records Priority
    prices it right without a change here. A Priority cache read is Priority
    input times the row's cache multiple, which is the page's Priority caching
    price on every model but one: Gemini 3.5 Flash-Lite prints $0.05, and the
    engine charges 0.54 x 0.1 = $0.054. A Priority prompt over 200K takes the
    same long-context multiples, which reproduces the page's Priority figures
    for 3.1 Pro Preview ($7.20 in, $32.40 out, $0.72 cached) and 2.5 Pro
    ($4.50, $27.00, $0.45) exactly.

Not modelled, and why:

  - Context cache storage, billed per million tokens per hour. Logs record
    tokens, not how long a cache lived.
  - Grounding with Google Search and Google Maps: free up to a monthly or
    daily allowance, then $14 or $35 per 1,000 (Maps $25 for 2.5 models).
    What a search costs depends on the rest of your month, so searches are
    counted and priced at zero. The File search embedding charge ($0.15 per
    million tokens) is left out for the same kind of reason.
  - The Flex and Contributor tiers. The row has no key for a cheaper tier
    chosen per call, and no reader records one. Flex is half of Standard on
    input and output (Gemini 4 Argon $1.00 and $5.00 through 30 November,
    then $2.00 and $10.00; 3.6 and 3.8 Flash $0.375 and $1.875, then $0.75
    and $3.75; 3.5 Flash-Lite $0.15 and $1.25, cached $0.02; 3.1 Flash-Lite
    $0.125 and $0.75; 3.1 Pro Preview $1.00 and $6.00, $2.00 and $9.00 over
    200K; 3 Flash Preview $0.25 and $1.50; 2.5 Pro $0.625 and $5.00, $1.25
    and $7.50 over 200K; 2.5 Flash $0.15 and $1.25; 2.5 Flash-Lite $0.05 and
    $0.20). Contributor, an invite-only private preview, is printed for
    Gemini 4 Argon, 3.8 Flash, 3.5 Flash-Lite and 3.1 Pro Preview. On 27
    October it was at the Flex figures except its cache prices (3.5
    Flash-Lite $0.015, 3.1 Pro Preview $0.10 and $0.20 over 200K). The page
    updated 30 October 2026 prints Argon's and 3.8 Flash's Contributor
    prices without the dated rise ($1.00, $5.00 and $0.05 cached; $0.375,
    $1.875 and $0.0375), while their Flex prices still rise on 1 December
    2026 and 1 January 2027.
  - The Batch tier.
  - Audio input and audio cache reads, which have their own higher rate
    (for example 2.5 Flash: $1.00 audio input, $0.1 audio cache). Logs
    record token counts, not modalities.
  - Live, speech, transcription, image, video, music, embedding and robotics
    models, which the page also lists: real-time or media endpoints, not the
    chat or code calls a harness makes. Gemma is "Not available" on the Paid
    Tier.

Choices for what the engine cannot express:

  - Gemini 2.5 Flash Preview 04-17 and 05-20 printed two output prices,
    "Non-thinking: $0.60" and "Thinking: $3.50". A row holds one, and the
    pages do not say which mode was the default, so the row prices output at
    the Thinking $3.50: a call that thought at all paid it on its whole
    output, and the ledger records thoughts per call, so an engine change
    can later apply $0.60 to a call with none.
  - The 2.5 Pro Previews printed cached $0.31, and $0.625 over 200K. One
    multiple cannot give both: 0.248 makes $0.31 exact and a long cache read
    $0.62, half a cent under the page.
  - Gemini 1.5 Flash-8B's cache price, $0.01 against $0.0375 input, is no
    round multiple, so the row holds the quotient and reproduces $0.01 and
    $0.02 exactly.
  - Where a retired model's page printed no caching price, its multiple is
    1.0, the engine's value for "no published cache price".

Models a call may be routed to: the changelog says requests to retired
gemini-3.5-flash and gemini-3.7-flash now go to 3.6 and 3.8 Flash, and that
gemini-3-pro-preview points at 3.1 Pro Preview, but never what a routed call
is billed at, so each keeps its own last published price. Earlier rates of
current models that only the Internet Archive shows (2.5 Pro, 2.5 Flash and
2.5 Flash-Lite caching before October 2025; 3.6 Flash before 13 August 2026)
are not in the table: Google gives no date for them, and an archive copy is
used here only for a retired model.
"""

import datetime as dt
import re

PROVIDER = "google"
NAME = "Google"
SOURCE = "https://aistudio.google.com/docs/pricing"
# The same page's Markdoc source, which the page itself carries verbatim.
SOURCE_MD = "https://aistudio.google.com/docs/pricing.md"
VERIFIED_ON = "2026-11-02"
MEASURED = False

# Gemini has no per-token cache write fee; creating a cache bills as input.
CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
# Grounding is not modelled; see above.
WEB_SEARCH_PER_1K = 0.0

# Stable versions carry a three-digit suffix: gemini-2.0-flash-001.
SNAPSHOT = r"-\d{3}$"

# Long context: above this many prompt tokens ("> 200k" on the page). The
# startup lookup applies it to a model the page gives long-context rates for.
LONG_OVER = 200_000
_LONG = {"over": LONG_OVER, "in": 2.0, "out": 1.5}
# The 1.5 series: "<= 128k" and "> 128k", with every rate doubled above it.
_LONG_128K = {"over": 128_000, "in": 2.0, "out": 2.0}


def _row(inp, out, cached_mult=0.1, fast=None, long=None, since=""):
    row = {"from": since, "in": inp, "out": out, "cache_read_mult": cached_mult, "fast": fast}
    if long:
        row["long"] = long
    return row


PRICES = {
    # Added 16 October 2026: the flagship reasoning model, GA on 13 October
    # 2026. Launch prices through 30 November 2026, then double from 1
    # December; cached input is 0.05x, where every other model's is 0.1x.
    # No long-context tier: the page gives one price whatever the prompt.
    "gemini-4-argon":         [_row(2.00, 10.00, 0.05, fast=(3.60, 18.00)),
                               _row(4.00, 20.00, 0.05, fast=(7.20, 36.00), since="2026-12-01")],
    # Launch prices through 31 December 2026, then the published list price.
    "gemini-3.8-flash":       [_row(0.75, 3.75, fast=(1.35, 6.75)),
                               _row(1.50, 7.50, fast=(2.70, 13.50), since="2027-01-01")],
    "gemini-3.7-flash":       [_row(0.75, 3.75, fast=(1.35, 6.75)),
                               _row(1.50, 7.50, fast=(2.70, 13.50), since="2027-01-01")],
    "gemini-3.6-flash":       [_row(0.75, 3.75, fast=(1.35, 6.75)),
                               _row(1.50, 7.50, fast=(2.70, 13.50), since="2027-01-01")],
    "gemini-3.5-flash":       [_row(1.50, 9.00, fast=(2.70, 16.20))],
    "gemini-3.5-flash-lite":  [_row(0.30, 2.50, fast=(0.54, 4.50))],
    "gemini-3.1-flash-lite":  [_row(0.25, 1.50, fast=(0.45, 2.70))],
    "gemini-3.1-pro-preview": [_row(2.00, 12.00, fast=(3.60, 21.60), long=_LONG)],
    "gemini-3-flash-preview": [_row(0.50, 3.00, fast=(0.90, 5.40))],
    "gemini-2.5-pro":         [_row(1.25, 10.00, fast=(2.25, 18.00), long=_LONG)],
    "gemini-2.5-flash":       [_row(0.30, 2.50, fast=(0.54, 4.50))],
    "gemini-2.5-flash-lite":  [_row(0.10, 0.40, fast=(0.18, 0.72))],
    # No caching row on the page, so no cache discount; one table, no Priority.
    "gemini-2.5-computer-use-preview-10-2025": [_row(1.25, 10.00, 1.0, long=_LONG)],
    # Retired, added 27 October 2026 (see RETIRED): each priced from the
    # Internet Archive copy of this page named there, Standard paid tier.
    # Standard and Batch tabs only, so no Priority.
    "gemini-3-pro-preview":   [_row(2.00, 12.00, long=_LONG)],
    "gemini-3.1-flash-lite-preview": [_row(0.25, 1.50, fast=(0.45, 2.70))],
    "gemini-2.0-flash":       [_row(0.10, 0.40, 0.25)],
    # The copy cited prints "Context caching price | Not available".
    "gemini-2.0-flash-lite":  [_row(0.075, 0.30, 1.0)],
    "gemini-2.5-flash-lite-preview-09-2025": [_row(0.10, 0.40)],
    "gemini-2.5-flash-preview-09-2025": [_row(0.30, 2.50)],
    "gemini-2.5-flash-lite-preview-06-17": [_row(0.10, 0.40, 0.25)],
    # Output at the "Thinking" price; the page also printed "Non-thinking:
    # $0.60". See the docstring.
    "gemini-2.5-flash-preview-05-20": [_row(0.15, 3.50, 0.25)],
    "gemini-2.5-flash-preview-04-17": [_row(0.15, 3.50, 0.25)],
    # Cached $0.31 = 0.248 x 1.25; the page's > 200k cache price was $0.625.
    "gemini-2.5-pro-preview-06-05": [_row(1.25, 10.00, 0.248, long=_LONG)],
    "gemini-2.5-pro-preview-05-06": [_row(1.25, 10.00, 0.248, long=_LONG)],
    "gemini-2.5-pro-preview-03-25": [_row(1.25, 10.00, 0.248, long=_LONG)],
    "gemini-1.5-pro":         [_row(1.25, 5.00, 0.25, long=_LONG_128K)],
    "gemini-1.5-flash":       [_row(0.075, 0.30, 0.25, long=_LONG_128K)],
    # Cached $0.01 against $0.0375 input: no round multiple, so the quotient.
    "gemini-1.5-flash-8b":    [_row(0.0375, 0.15, 0.01 / 0.0375, long=_LONG_128K)],
    # Caching "Not available".
    "gemini-1.0-pro":         [_row(0.50, 1.50, 1.0)],
}

# Kept for older usage, at the last published price, though the page no
# longer lists them. Model id: retirement date. The notices are Google's
# changelog (https://ai.google.dev/gemini-api/docs/changelog) and its
# deprecations page (https://ai.google.dev/gemini-api/docs/deprecations),
# both read on 27 October 2026. A price comes from the Internet Archive's
# copy of this table's SOURCE at the timestamp named,
# https://web.archive.org/web/<timestamp>/https://ai.google.dev/gemini-api/docs/pricing,
# the last copy before the retirement that prints the model's table.
RETIRED = {
    # Shut down 28 July 2026 per the deprecations page; the pricing page
    # dropped it on 6 October 2026, so its price was read off the live page.
    "gemini-2.5-computer-use-preview-10-2025": "2026-07-28",
    # Deprecated on 8 October 2026 per the changelog: requests to them are
    # routed to gemini-3.6-flash and gemini-3.8-flash, and the pricing page
    # no longer lists them. Neither the changelog nor the deprecations page
    # says what a routed call is billed at, so both keep their last published
    # price. For 3.7 Flash the two answers are the same; 3.5 Flash's price is
    # above 3.6 Flash's, so which one a routed call pays is an open question.
    # Their Standard rates were read off the live page before 8 October
    # 2026; their Priority pairs were added on 27 October 2026 from capture
    # 20261008045525, when the live page no longer listed them.
    "gemini-3.5-flash": "2026-10-08",
    "gemini-3.7-flash": "2026-10-08",
    # Changelog, 1 June 2026: "now shut down"; deprecations page. Priced from
    # capture 20260531114408. Their -001 ids reach these rows by SNAPSHOT.
    "gemini-2.0-flash": "2026-06-01",
    "gemini-2.0-flash-lite": "2026-06-01",
    # Changelog, 25 May 2026: "has been shut down"; deprecations page.
    # Capture 20260523192931.
    "gemini-3.1-flash-lite-preview": "2026-05-25",
    # Changelog, 31 March 2026: "has been shut down"; deprecations page.
    # Capture 20260329190628.
    "gemini-2.5-flash-lite-preview-09-2025": "2026-03-31",
    # Changelog, 9 March 2026: "has been shut down. The gemini-3-pro-preview
    # now points to gemini-3.1-pro-preview"; deprecations page. Capture
    # 20260308060347.
    "gemini-3-pro-preview": "2026-03-09",
    # Changelog, 17 February 2026: shut down; deprecations page, which spells
    # it gemini-2.5-flash-preview-09-25 (see ALIASES). Capture 20260216042333.
    "gemini-2.5-flash-preview-09-2025": "2026-02-17",
    # Changelog, 4 November 2025, announcing shutdown on 2 December 2025;
    # deprecations page. Captures 20250616024644 (06-05), 20250605100850
    # (05-06) and 20250506015835 (03-25, the last copy to name it).
    "gemini-2.5-pro-preview-06-05": "2025-12-02",
    "gemini-2.5-pro-preview-05-06": "2025-12-02",
    "gemini-2.5-pro-preview-03-25": "2025-12-02",
    # Changelog, 4 November 2025, announcing shutdown on 18 November 2025;
    # 05-20 is also on the deprecations page. Captures 20250616024644 (05-20)
    # and 20250722012816 (Flash-Lite 06-17).
    "gemini-2.5-flash-preview-05-20": "2025-11-18",
    "gemini-2.5-flash-lite-preview-06-17": "2025-11-18",
    # Changelog, 29 September 2025: "now shut down". Capture 20250926115107.
    "gemini-1.5-pro": "2025-09-29",
    "gemini-1.5-flash": "2025-09-29",
    "gemini-1.5-flash-8b": "2025-09-29",
    # Changelog, 17 June 2025: "gemini-2.5-flash-preview-04-17 will be
    # deprecated on July 15, 2025". Capture 20250520002359.
    "gemini-2.5-flash-preview-04-17": "2025-07-15",
    # Changelog, 18 February 2025: "Gemini 1.0 Pro is no longer supported".
    # The capture's own sentence reads "will be shut down on February 15th,
    # 2024", year as printed. Capture 20250211163751.
    "gemini-1.0-pro": "2025-02-18",
}

# Other names for the same model, as Google's pages give them: the pricing
# page heads one section with both 3.1 Pro Preview ids; the deprecations page
# and changelog spell the September 2025 Flash Preview -09-25; the pricing
# page's AI Studio link in July 2025 spelled the June Flash-Lite Preview
# without "preview".
ALIASES = {
    "gemini-3.1-pro-preview-customtools": "gemini-3.1-pro-preview",
    "gemini-2.5-flash-preview-09-25": "gemini-2.5-flash-preview-09-2025",
    "gemini-2.5-flash-lite-06-17": "gemini-2.5-flash-lite-preview-06-17",
}

FALLBACK_MODEL = "gemini-3.1-pro-preview"

# A text model's id on the page, for page_rates(): see the note there.
TEXT_MODEL = re.compile(r"gemini-[\d.]+-(?!(?:live|transcribe|tts|image|audio|embedding|robotics)\b)"
                        r"[a-z]+(?:-lite)?(?:-preview)?")


# ---- reading the published page, for --check-prices and the startup lookup


# Markdoc's own tags ({% sup %}, {% /tab %}, ...) and a markdown link's target.
_TAG = re.compile(r"\{%.*?%\}")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# A Markdoc table, a tier's tab, a row's rule and a cell's bullet.
_TABLE = re.compile(r"\{% table %\}(.*?)\{% /table %\}", re.S)
_RULE = re.compile(r"^[ \t]*---[ \t]*$", re.M)
_BULLET = re.compile(r"^[ \t]*\* ", re.M)


def _plain(text: str) -> str:
    """Markdoc text with its tags, link targets and code ticks taken out."""
    return _LINK.sub(r"\1", _TAG.sub("", text)).replace("`", "")


def _paid_cell(cell: str) -> dict:
    """One paid-tier cell as {"base", "long", "over", "dated"}.

    A cell can hold several prices at once, one to a line: text and audio,
    short and long context, a launch price and a later one, and a storage
    price. Each dollar figure is classified by the words that follow it, up
    to the next figure; the cell's lines are joined with " ; " so that the
    words of one line never run into the next. "over" is the long-context
    threshold in tokens, read from "> 200k".
    """
    text = " ; ".join(line.strip() for line in _plain(cell).splitlines())
    out = {}
    for figure, tail in re.findall(r"\$([\d.,]+)([^$]*)", text):
        value = float(figure.replace(",", "").rstrip("."))
        tail = tail.lower()
        if "per hour" in tail or "storage" in tail or "(audio)" in tail:
            continue
        over = re.search(r">\s*([\d,]+)k\b", tail)
        if "starting" in tail:
            date = re.search(r"starting (\w+ \d+, \d{4})", tail)
            out["dated"] = (value, date.group(1).title() if date else "")
        elif over:
            out["long"] = value
            out["over"] = int(over.group(1).replace(",", "")) * 1000
        elif "base" not in out:
            out["base"] = value
    return out


def _cells(table: str) -> dict:
    """A Markdoc table's rows as {row label: _paid_cell() of the Paid Tier}.

    Rows are separated by a "---" line, and each row is three bullets
    (label, Free Tier, Paid Tier); a cell's further lines carry no bullet.
    A row of any other shape is not a price row and is skipped."""
    cells = {}
    for row in _RULE.split(table):
        parts = _BULLET.split(row)[1:]
        if len(parts) == 3:
            label = " ".join(_plain(parts[0]).split()).lower()
            cells[label] = _paid_cell(parts[2])
    return cells


def _tier(section: str, name: str) -> dict:
    """A model's table for one tier, as _cells() gives it, or {}.

    The tier's table is the one inside its own {% tab %}, which ends at
    {% /tab %}, so a model with no table of that tier gives nothing rather
    than the next tier's figures."""
    tab = re.search(r'\{%% tab title="%s" %%\}(.*?)\{%% /tab %%\}' % re.escape(name), section, re.S)
    table = _TABLE.search(tab.group(1)) if tab else None
    return _cells(table.group(1)) if table else {}


def _in_out(cells: dict) -> tuple:
    """The input and output cells of a tier's table."""
    inp = next((v for k, v in cells.items() if k.startswith("input price")), {})
    out = next((v for k, v in cells.items() if k.startswith("output price")), {})
    return inp, out


def page_rates(fetch, tables, want=None):
    """Every rate on the page, as {model id: {field: $/MTok}}, and the text
    models on it that this table lacks.

    Used by --check-prices, which reports differences and never edits this
    file, and by the startup lookup for a model this table lacks. Since the
    page moved to aistudio.google.com (by 2 November 2026) it is rendered in
    the browser from Markdoc source, which the HTML carries verbatim in a
    <pre> block and which Google also serves alone at SOURCE_MD; that plain
    copy is what is read. It has one "## " heading per model, its ids in
    backticks above the tables (a section can name two ids, as 3.1 Pro
    Preview's does), then one {% tab title=... %} per tier, each with a
    {% table %} of three-cell rows (label, Free Tier, Paid Tier). The page
    names models by id, so PAGE_NAMES is not needed; the tables are Markdoc,
    not markdown, so `tables` is unused; every id is returned, so `want`
    needs no filtering.

    From the Standard table, or a model's only table: `in`, `out`, `cached`
    (input when no caching row is printed), `long_in`, `long_out`,
    `long_cached` and `long_over` where the cells give a "> 200k" price, and
    `_history` where they give a dated later price. From the Priority table:
    `fast_in` and `fast_out`, in each dated entry too. Flex, Contributor and
    Batch are not read, nor audio and storage prices, none of which the table
    models.
    """
    text = fetch(SOURCE_MD)
    rates, seen = {}, []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        # The ids are named above the first tab or table, not in its prose.
        head = re.split(r"\{% (?:tabs|table) %\}", block, maxsplit=1)[0]
        ids = re.findall(r"`(gemini-[a-z0-9.\-]+)`", head)
        # The Standard table, or a model's only table when it has just one.
        std = _tier(block, "Standard")
        if not std:
            only = _TABLE.search(block)
            std = _cells(only.group(1)) if only else {}
        if not ids or not std:
            continue
        inp, out = _in_out(std)
        cache = std.get("context caching price", {})
        if "base" not in inp or "base" not in out:
            continue
        r = {"in": inp["base"], "out": out["base"],
             "cached": cache.get("base", inp["base"])}
        if "long" in inp and "long" in out:
            r["long_in"], r["long_out"] = inp["long"], out["long"]
            if "long" in cache:
                r["long_cached"] = cache["long"]
            if "over" in inp:
                r["long_over"] = inp["over"]
        p_in, p_out = _in_out(_tier(block, "Priority"))
        fast = None
        if "base" in p_in and "base" in p_out:
            fast = [(p_in["base"], p_out["base"])]
            if "dated" in p_in and "dated" in p_out:
                fast.append((p_in["dated"][0], p_out["dated"][0]))
            r["fast_in"], r["fast_out"] = fast[-1]
        if "dated" in inp and "dated" in out:
            try:
                since = dt.datetime.strptime(inp["dated"][1], "%B %d, %Y").date().isoformat()
            except ValueError:
                since = "?"
            later = {"from": since, "in": inp["dated"][0], "out": out["dated"][0]}
            if "dated" in cache:
                later["cached"] = cache["dated"][0]
            first = {"from": "", "in": r["in"], "out": r["out"], "cached": r["cached"]}
            if fast:
                first["fast_in"], first["fast_out"] = fast[0]
                later["fast_in"], later["fast_out"] = fast[-1]
            r["_history"] = [first, later]
            # The newest price, which the table's last entry must match.
            r["in"], r["out"] = later["in"], later["out"]
            r["cached"] = later.get("cached", r["cached"])
        for mid in ids:
            seen.append(mid)
            rates.setdefault(mid, dict(r))
    # Only text models a coding harness would call are worth flagging; the page
    # also lists live, speech, image and robotics models on purpose left out.
    # A text model is named gemini-<version>-<word>, with -lite or -preview
    # after it: pro, flash and flash-lite, and from Gemini 4 a name such as
    # argon, so the word is not fixed; only the words the other kinds use are
    # left out. Matching pro, flash and flash-lite alone let Gemini 4 Argon
    # sit on the page for three days unflagged.
    unknown = sorted(m for m in set(seen) if m not in PRICES and m not in ALIASES
                     and TEXT_MODEL.fullmatch(m))
    return rates, unknown
