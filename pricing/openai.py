"""OpenAI's API rates, in dollars per million tokens. Standard tier.

Every current figure is read off OpenAI's own pricing page, in its markdown
form, as fetched on 27 October 2026 (12:33 UTC, HTTP 200) and read twice, by
two readers who did not see each other's notes:

  https://developers.openai.com/api/docs/pricing      the page a person opens
  https://developers.openai.com/api/docs/pricing.md   the same page, read here

The Internet Archive holds that day's copy as
https://web.archive.org/web/20261027103203/https://developers.openai.com/api/docs/pricing.
A retired model's figures come from the archive copy of OpenAI's own pricing
page named beside it in RETIRED, and its retirement date from
https://developers.openai.com/api/docs/deprecations, under the notice quoted
there. The dated GPT-5.6 rows come from the archive copies of the markdown
page of 29 July, 31 July, 12 August and 12 September 2026, and the dates
themselves from OpenAI's changelog (30 July and 21 August 2026).

The table was first typed on 26 September 2026 and checked again on 6 October
2026; the rows added on 27 October 2026 are marked "added". gpt-6-rosalind
was added on 2 November 2026 from the same markdown page, read twice: once
from the copy fetched on 1 November 2026 at 23:54 UTC and once from the
copy fetched on 2 November 2026 at 00:03 UTC (HTTP 200, 23,508 bytes; the
two are byte for byte the same, sha256 56e3da9b...4922cfc). Its release
date, 30 October 2026, is from OpenAI's changelog. gpt-6-astra-law was
added on 2 November 2026, as the maintainer decided that day, from the
same markdown page fetched again at 17:30 UTC (HTTP 200, 23,508 bytes,
the same sha256) and from the page a person opens, fetched at the same
time, which prints the same three figures.

**Published, not measured.** Nobody has yet checked these figures against a
real OpenAI bill or against a harness's own cost report, the way the Anthropic
table was checked against Claude Code. The rates are the published ones; what
is unproven is the way a harness's logs map onto them. If you use this daily,
please compare a month against your bill and open an issue either way.

Rules the page states, modelled here:

  - Cached input is a fixed fraction of input: 0.1x on GPT-5 and GPT-6,
    0.05x on GPT-6.1 Sol and GPT-6.1 Terra, 0.25x or 0.5x on older models. A
    "-" in the cached column means no cached rate, recorded as 1.0x (the
    ordinary input rate), as on the pro models.
  - Cache writes. A 30-minute write is 1.25x input (write_mult) on the GPT-6,
    GPT-6.1 and GPT-5.6 families, gpt-6-rosalind and gpt-5.6-cyber. Since
    20 October 2026 (the changelog's date for 12-hour prompt caching) the
    page also prints a 12-hour write at 2.5x input, which is held in the
    write_1h_mult slot: the engine's two write lifetimes are named after
    Anthropic's 5 minutes and 1 hour, and for OpenAI the short slot holds
    the 30-minute write and the long slot the 12-hour write. For every model
    sold before that day it is a dated row from 20 October 2026, so no
    earlier call is priced at it; gpt-6.1-terra and gpt-6-rosalind, released
    after it, have one row that carries it. No OpenAI log reader records
    cache writes today, so this moves no logged figure yet; it lets
    --check-prices compare the page's 12-hour column. Older models have no
    write charge: the tokens are ordinary input.
  - Long context: a prompt of more than 272K input tokens is priced at 2x
    input and cache rates and 1.5x output for the whole request (the
    gpt-6-astra and gpt-5.6-sol model pages say "for the full request"). The
    page never says whether K is 1,000 or 1,024; 272,000 is used.
  - Fast mode, called Priority processing until 30 July 2026, has its own
    published rates, used when a call is recorded as fast. They are a typed
    pair, never a multiple: 2x Standard on most rows, but 2.5x on gpt-5.5
    ($12.50 / $75 against $5 / $30), 1.8x on gpt-5-mini, 1.75x on gpt-4.1
    and o3 and 1.7x on gpt-4o, among others.
  - Dated price cuts: gpt-5.6-terra (20% less) and gpt-5.6-luna (80% less) on
    30 July 2026, and gpt-5.6-sol on 21 August 2026, each a dated row.
  - Web search is $10 per 1,000 calls; gpt-5-search-api bills its searches on
    top of its token rates.

Two corrections, made on 1 November 2026 with the maintainer's agreement.
They are the two agreed exceptions to "an old row is never edited":

  - The undated rows of gpt-5.6-terra, gpt-5.6-luna and gpt-5.6-sol were
    typed on 26 September 2026, after the cuts, so they priced July and
    August 2026 usage at the cut rate. They never recorded a rate read on
    their own date, so they now hold the pre-cut figures, and the cut rates
    are the dated rows after them.
  - The retired gpt-5-codex, gpt-5.1-codex, gpt-5.1-codex-max and
    gpt-5.2-codex rows had no fast rate, a gap rather than a reading: the
    30 July 2026 capture prints their rates in its "Fast mode" pane, which
    now fill it. Their Standard figures are unchanged, but a call on one of
    them recorded as fast now costs its published fast rate instead of
    Standard: gpt-5-codex, 1M in and 1M out, was $1.25 + $10 and is now
    $2.50 + $20.

Rules deliberately not modelled, and what is charged instead:

  - Batch: excluded, as the work is not interactive.
  - Flex: half of Standard on every figure ("Batch and Flex are priced at 50%
    of Standard rates", gpt-6-astra model page). A row has no key for it, so
    a flex call is charged at Standard.
  - Ultrafast (gpt-6-astra and gpt-6.1-sol only, 6x Standard on every
    figure): no row key either, so Standard is charged unless the call is
    recorded as fast, when the fast pair is.
  - A fast call of more than 272K input tokens on gpt-5.5 or gpt-5.4: the
    Fast table prints "-" in every long column for these two, and the gpt-5.5
    model page gives the long rate "for standard, batch, and flex". The row's
    long rule is needed for standard calls and also applies to fast ones, so
    such a call is charged 2x fast input and 1.5x fast output.
  - Thinking: the page prints no thinking or non-thinking split; output
    prices include reasoning tokens. Nothing to apply.
  - gpt-5.6-sol's promotional pricing is "available at least through November
    21, 2026", with no end date and no regular price printed. It is priced as
    the page charges now; when it ends, a new dated row.
  - gpt-6-astra-law's likewise: "GPT-6 Astra for Law promotional pricing is
    available at least through December 31, 2026", with no regular price
    printed. One row at the page's current price; when it ends, a new dated
    row.
  - gpt-rosalind-research: "Billing for gpt-rosalind-research begins on
    October 5, 2026." Its row has no date, since a first row dated 5 October
    would price earlier calls the same anyway.
  - o1-mini: the openai.com captures of 9, 15 and 29 January 2025 print $3.00
    in and $12.00 out, the 1 February 2025 capture $1.10 and $4.40. OpenAI
    states no date for the cut, so there is one row at the last published
    price, and January 2025 o1-mini calls are under-priced by it.
  - The 10% uplift for regional processing and FedRAMP endpoints (a log does
    not say which endpoint served a call), and container, file-search and
    other tool fees.

Access: gpt-5.6-cyber and gpt-5.5-cyber need Daybreak approval, and the
Rosalind models, gpt-6-rosalind included, the trusted-access programme;
chat-latest points to the latest ChatGPT Instant model, so the model behind
it changes.

gpt-6-astra-law: since at least 1 November 2026 the page prints it under
"Legal model configurations", headed "Model configuration", at $10 in, $50
out and $1 cached, and nothing else: no fast, flex, ultrafast, cache-write
or long-context figure. It has no model page (HTTP 404 on 2 November 2026)
and no changelog entry. The maintainer decided on 2 November 2026 to price
it as an API model id, so its row holds those three figures alone: no
write charge (the page prints no write column, which the reader takes as
the ordinary input rate), no long-context tier and no fast pair.

Left out on purpose: gpt-5.4-cyber (retired 1 October 2026; every copy that
lists it prints "-" in every column, so no price was ever published);
gpt-5-codex-mini (no copy of the pricing page lists it); gpt-oss-120b and
gpt-oss-20b (open weights, priced by the startup lookup); realtime, audio,
speech, image, transcription, embedding and moderation models, which are not
chat or code text models; models retired before 1 January 2025 though still
printed in 2026 copies; and dated snapshots, which price as their alias
through SNAPSHOT (gpt-4o-2024-05-13 keeps its own row because its price
differs). The -completions names (gpt-3.5-turbo-completions,
gpt-4-completions, gpt-4-0613-completions, gpt-4-turbo-completions and
gpt-4-turbo-preview-completions) have no row of their own: the deprecations
page lists each with the snapshot it points to, so ALIASES maps them there.

Row fields are the same as the Anthropic table, plus two optional ones:

  write_mult      30-minute cache write, a multiple of base input (default 1.0)
  write_1h_mult   12-hour cache write, a multiple of base input
  long            {"over": tokens, "in": mult, "out": mult} for long context
"""

import re
import urllib.error

from .common import money

PROVIDER = "openai"
NAME = "OpenAI"
SOURCE = "https://developers.openai.com/api/docs/pricing"
SOURCE_MD = "https://developers.openai.com/api/docs/pricing.md"
MODEL_PAGE_MD = "https://developers.openai.com/api/docs/models/{model}.md"
VERIFIED_ON = "2026-10-27"
MEASURED = False

# Table defaults: no write charge. Rows that bill writes override them.
CACHE_WRITE_5M_MULT = 1.0
CACHE_WRITE_1H_MULT = 1.0
WEB_SEARCH_PER_1K = 10.0

# OpenAI snapshots carry a dashed date: gpt-5-2025-08-07.
SNAPSHOT = r"-\d{4}-\d{2}-\d{2}$"

# The ids whose model page the startup lookup may fetch; see page_rates().
PAGE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

# Long context: above this many prompt tokens. The startup lookup applies it
# to a model the page gives long-context rates for.
LONG_OVER = 272_000
_LONG = {"over": LONG_OVER, "in": 2.0, "out": 1.5}


def _row(inp, out, cached_mult, fast=None, write_mult=1.0, long=None,
         write_1h_mult=None, frm=""):
    row = {"from": frm, "in": inp, "out": out, "cache_read_mult": cached_mult,
           "fast": fast, "write_mult": write_mult}
    if write_1h_mult is not None:
        row["write_1h_mult"] = write_1h_mult
    if long:
        row["long"] = long
    return row


# The 12-hour cache write, from 20 October 2026: 2.5x input.
_12H = {"write_1h_mult": 2.5, "frm": "2026-10-20"}

PRICES = {
    # GPT-6. Cache writes billed at 1.25x; long context above 272K.
    "gpt-6-astra":        [_row(10.00, 50.00, 0.1, (20.00, 100.00), 1.25, _LONG),
                           _row(10.00, 50.00, 0.1, (20.00, 100.00), 1.25, _LONG, **_12H)],
    # Added 6 October 2026. The same base rates as gpt-6-sol, but cached input
    # is 5% of input, not 10%, per its model page.
    "gpt-6.1-sol":        [_row( 2.00, 10.00, 0.05, ( 4.00,  20.00), 1.25, _LONG),
                           _row( 2.00, 10.00, 0.05, ( 4.00,  20.00), 1.25, _LONG, **_12H)],
    # Added 27 October 2026; released 26 October 2026, after 12-hour caching
    # began, so its one row carries the 12-hour write.
    "gpt-6.1-terra":      [_row( 1.00,  5.00, 0.05, ( 2.00,  10.00), 1.25, _LONG, 2.5)],
    "gpt-6-sol":          [_row( 2.00, 10.00, 0.1, ( 4.00,  20.00), 1.25, _LONG),
                           _row( 2.00, 10.00, 0.1, ( 4.00,  20.00), 1.25, _LONG, **_12H)],
    "gpt-6-luna":         [_row( 0.10,  0.50, 0.1, ( 0.20,   1.00), 1.25, _LONG),
                           _row( 0.10,  0.50, 0.1, ( 0.20,   1.00), 1.25, _LONG, **_12H)],
    # GPT-5.6. The undated rows hold the pre-cut figures (see the docstring),
    # from the markdown page as captured on 29 July and 12 August 2026. Sol
    # is on promotional pricing "at least through November 21, 2026". When
    # that ends, add a dated entry; do not edit this one.
    "gpt-5.6-sol":        [_row( 5.00, 30.00, 0.1, (10.00,  60.00), 1.25, _LONG),
                           _row( 4.00, 20.00, 0.1, ( 8.00,  40.00), 1.25, _LONG, frm="2026-08-21"),
                           _row( 4.00, 20.00, 0.1, ( 8.00,  40.00), 1.25, _LONG, **_12H)],
    "gpt-5.6-terra":      [_row( 2.50, 15.00, 0.1, ( 5.00,  30.00), 1.25, _LONG),
                           _row( 2.00, 12.00, 0.1, ( 4.00,  24.00), 1.25, _LONG, frm="2026-07-30"),
                           _row( 2.00, 12.00, 0.1, ( 4.00,  24.00), 1.25, _LONG, **_12H)],
    "gpt-5.6-luna":       [_row( 1.00,  6.00, 0.1, ( 2.00,  12.00), 1.25, _LONG),
                           _row( 0.20,  1.20, 0.1, ( 0.40,   2.40), 1.25, _LONG, frm="2026-07-30"),
                           _row( 0.20,  1.20, 0.1, ( 0.40,   2.40), 1.25, _LONG, **_12H)],
    # GPT-5.5 and 5.4. Long context, no write charge.
    "gpt-5.5":            [_row( 5.00, 30.00, 0.1, (12.50,  75.00), long=_LONG)],
    "gpt-5.5-pro":        [_row(30.00, 180.00, 1.0, long=_LONG)],
    "gpt-5.4":            [_row( 2.50, 15.00, 0.1, ( 5.00,  30.00), long=_LONG)],
    "gpt-5.4-pro":        [_row(30.00, 180.00, 1.0, long=_LONG)],
    "gpt-5.4-mini":       [_row( 0.75,  4.50, 0.1, ( 1.50,   9.00))],
    "gpt-5.4-nano":       [_row( 0.20,  1.25, 0.1)],
    # Codex models. gpt-5.3-codex is on the page's specialised table; the
    # rest are retired, priced from the capture named in RETIRED. The fast
    # pairs of four of them were filled on 1 November 2026 (see the
    # docstring).
    "gpt-5.3-codex":      [_row( 1.75, 14.00, 0.1, ( 3.50,  28.00))],
    "gpt-5.2-codex":      [_row( 1.75, 14.00, 0.1, ( 3.50,  28.00))],
    "gpt-5.1-codex-max":  [_row( 1.25, 10.00, 0.1, ( 2.50,  20.00))],
    "gpt-5.1-codex":      [_row( 1.25, 10.00, 0.1, ( 2.50,  20.00))],
    "gpt-5.1-codex-mini": [_row( 0.25,  2.00, 0.1)],
    "gpt-5-codex":        [_row( 1.25, 10.00, 0.1, ( 2.50,  20.00))],
    "codex-mini-latest":  [_row( 1.50,  6.00, 0.25)],
    # GPT-5, 5.1 and 5.2.
    "gpt-5.2":            [_row( 1.75, 14.00, 0.1, ( 3.50,  28.00))],
    "gpt-5.2-pro":        [_row(21.00, 168.00, 1.0)],
    "gpt-5.1":            [_row( 1.25, 10.00, 0.1, ( 2.50,  20.00))],
    "gpt-5":              [_row( 1.25, 10.00, 0.1, ( 2.50,  20.00))],
    "gpt-5-mini":         [_row( 0.25,  2.00, 0.1, ( 0.45,   3.60))],
    "gpt-5-nano":         [_row( 0.05,  0.40, 0.1)],
    "gpt-5-pro":          [_row(15.00, 120.00, 1.0)],
    # Older models a harness may still be pointed at.
    "gpt-4.1":            [_row( 2.00,  8.00, 0.25, ( 3.50,  14.00))],
    "gpt-4.1-mini":       [_row( 0.40,  1.60, 0.25, ( 0.70,   2.80))],
    "gpt-4.1-nano":       [_row( 0.10,  0.40, 0.25, ( 0.20,   0.80))],
    "gpt-4o":             [_row( 2.50, 10.00, 0.5, ( 4.25,  17.00))],
    # A snapshot with its own, higher price. Matched exactly before any
    # snapshot date is stripped, so it never falls through to gpt-4o.
    "gpt-4o-2024-05-13":  [_row( 5.00, 15.00, 1.0, ( 8.75,  26.25))],
    "gpt-4o-mini":        [_row( 0.15,  0.60, 0.5, ( 0.25,   1.00))],
    "o3":                 [_row( 2.00,  8.00, 0.25, ( 3.50,  14.00))],
    "o3-pro":             [_row(20.00, 80.00, 1.0)],
    "o4-mini":            [_row( 1.10,  4.40, 0.25, ( 2.00,   8.00))],
    "o3-mini":            [_row( 1.10,  4.40, 0.5)],
    "o1":                 [_row(15.00, 60.00, 0.5)],
    "o1-pro":             [_row(150.00, 600.00, 1.0)],
    # Added 27 October 2026: text models sold per token, from the page.
    # Cyber: "-" in every long column and no fast row. The page of 12 August
    # 2026, the first to list it, prints one cache writes column ($15.625);
    # the 12-hour write ($31.25) is a dated row, as for the families above.
    "gpt-5.6-cyber":      [_row(12.50, 75.00, 0.1, None, 1.25),
                           _row(12.50, 75.00, 0.1, None, 1.25, **_12H)],
    "gpt-5.5-cyber":      [_row(12.50, 75.00, 0.1)],
    # Added 2 November 2026; released 30 October 2026, after 12-hour caching
    # began, so its one row carries the 12-hour write. No fast row.
    "gpt-6-rosalind":     [_row(15.00, 75.00, 0.1, None, 1.25, _LONG, 2.5)],
    # Added 2 November 2026, read off the page that day. Promotional: "GPT-6
    # Astra for Law promotional pricing is available at least through
    # December 31, 2026." When it ends, add a dated row; do not edit this
    # one. The page prints input, output and cached input only, so there is
    # no write charge, no long tier and no fast pair (see the docstring).
    "gpt-6-astra-law":    [_row(10.00, 50.00, 0.1, None, 1.0)],
    # "Cache-write pricing does not apply to this model."
    "gpt-rosalind-research":  [_row(5.00, 25.00, 0.1)],
    "gpt-rosalind-discovery": [_row(5.00, 25.00, 0.1)],
    "chat-latest":        [_row( 5.00, 30.00, 0.1)],
    # Web search calls are billed on top, at WEB_SEARCH_PER_1K.
    "gpt-5-search-api":   [_row( 1.25, 10.00, 0.1)],
    # Added 27 October 2026, retired: priced as named in RETIRED.
    "gpt-4-turbo-2024-04-09":     [_row(10.00, 30.00, 1.0)],
    "gpt-4-0613":                 [_row(30.00, 60.00, 1.0)],
    "gpt-3.5-turbo":              [_row( 0.50,  1.50, 1.0)],
    # Its own row: SNAPSHOT does not match "-0125".
    "gpt-3.5-turbo-0125":         [_row( 0.50,  1.50, 1.0)],
    "gpt-4-1106-preview":         [_row(10.00, 30.00, 1.0)],
    "gpt-5-chat-latest":          [_row( 1.25, 10.00, 0.1)],
    "gpt-5.1-chat-latest":        [_row( 1.25, 10.00, 0.1)],
    "o3-deep-research":           [_row(10.00, 40.00, 0.25)],
    "o4-mini-deep-research":      [_row( 2.00,  8.00, 0.25)],
    "computer-use-preview":       [_row( 3.00, 12.00, 1.0)],
    "gpt-4o-search-preview":      [_row( 2.50, 10.00, 1.0)],
    "gpt-4o-mini-search-preview": [_row( 0.15,  0.60, 1.0)],
    "gpt-5.2-chat-latest":        [_row( 1.75, 14.00, 0.1)],
    "gpt-5.3-chat-latest":        [_row( 1.75, 14.00, 0.1)],
    "gpt-3.5-turbo-1106":         [_row( 1.00,  2.00, 1.0)],
    "gpt-3.5-turbo-instruct":     [_row( 1.50,  2.00, 1.0)],
    "davinci-002":                [_row( 2.00,  2.00, 1.0)],
    "babbage-002":                [_row( 0.40,  0.40, 1.0)],
    "gpt-4-0314":                 [_row(30.00, 60.00, 1.0)],
    "gpt-4-0125-preview":         [_row(10.00, 30.00, 1.0)],
    "chatgpt-4o-latest":          [_row( 5.00, 15.00, 1.0)],
    "o1-mini":                    [_row( 1.10,  4.40, 0.5)],
    "o1-preview":                 [_row(15.00, 60.00, 0.5)],
    "gpt-4.5-preview":            [_row(75.00, 150.00, 0.5)],
    "gpt-4-32k":                  [_row(60.00, 120.00, 1.0)],
}

# {model id: retirement date}, each date from OpenAI's deprecation page,
# https://developers.openai.com/api/docs/deprecations (read 27 October 2026),
# under the notice quoted. The first ten are still printed on the pricing
# page and are checked against it like any other row; the rest are priced
# from the Internet Archive capture named, the last copy of OpenAI's pricing
# page to carry the row.
_C20260730 = "https://web.archive.org/web/20260730195107/https://developers.openai.com/api/docs/pricing"
RETIRED = {
    # notice "2026-04-22: Legacy GPT model snapshots", shut down 23 October
    # 2026; still on the page.
    "gpt-4.1-nano":           "2026-10-23",
    "gpt-4o-2024-05-13":      "2026-10-23",
    "o4-mini":                "2026-10-23",
    "o3-mini":                "2026-10-23",
    "o1":                     "2026-10-23",
    "o1-pro":                 "2026-10-23",
    "gpt-4-turbo-2024-04-09": "2026-10-23",
    "gpt-4-0613":             "2026-10-23",
    "gpt-3.5-turbo":          "2026-10-23",
    "gpt-3.5-turbo-0125":     "2026-10-23",
    # the same notice; no longer on the page. Price from _C20260730.
    "gpt-4-1106-preview":     "2026-10-23",
    # notice "2026-04-22: Legacy GPT model snapshots (July 2026 shutdown)".
    # Price from _C20260730, the last capture to list them.
    "gpt-5.2-codex":              "2026-07-23",
    "gpt-5.1-codex-max":          "2026-07-23",
    "gpt-5.1-codex":              "2026-07-23",
    "gpt-5.1-codex-mini":         "2026-07-23",
    "gpt-5-codex":                "2026-07-23",
    "gpt-5-chat-latest":          "2026-07-23",
    "gpt-5.1-chat-latest":        "2026-07-23",
    "o3-deep-research":           "2026-07-23",
    "o4-mini-deep-research":      "2026-07-23",
    "computer-use-preview":       "2026-07-23",
    "gpt-4o-search-preview":      "2026-07-23",
    "gpt-4o-mini-search-preview": "2026-07-23",
    # notice "2026-05-08: gpt-5.2-chat-latest and gpt-5.3-chat-latest model
    # snapshots"; price from
    # https://web.archive.org/web/20260811103033/https://developers.openai.com/api/docs/pricing
    "gpt-5.2-chat-latest": "2026-08-10",
    "gpt-5.3-chat-latest": "2026-08-10",
    # notice "2025-09-26: Legacy GPT model snapshots", shut down 28 September
    # 2026; price from
    # https://web.archive.org/web/20261010170540/https://developers.openai.com/api/docs/pricing.md
    "gpt-3.5-turbo-1106":     "2026-09-28",
    "gpt-3.5-turbo-instruct": "2026-09-28",
    "davinci-002":            "2026-09-28",
    "babbage-002":            "2026-09-28",
    # notice "2025-09-26: Legacy GPT model snapshots (March 2026 shutdown)";
    # price from _C20260730.
    "gpt-4-0314":         "2026-03-26",
    "gpt-4-0125-preview": "2026-03-26",
    # notice "2025-11-18: chatgpt-4o-latest snapshot"; price from _C20260730.
    "chatgpt-4o-latest": "2026-02-17",
    # notice "2025-11-17: codex-mini-latest model snapshot"; price from _C20260730.
    "codex-mini-latest": "2026-02-12",
    # notice "2025-04-28: o1-preview and o1-mini"; price from _C20260730.
    "o1-mini": "2025-10-27",
    # the same notice; price from
    # https://web.archive.org/web/20250211094612/https://openai.com/api/pricing/
    "o1-preview": "2025-07-28",
    # notice "2025-04-14: GPT-4.5-preview"; price from the card "GPT-4.5" in
    # https://web.archive.org/web/20250413004940/https://openai.com/api/pricing/
    "gpt-4.5-preview": "2025-07-14",
    # notice "2024-06-06: GPT-4-32K and Vision Preview models", which prints
    # the price itself, as does _C20260730.
    "gpt-4-32k": "2025-06-06",
}

# OpenAI's own other names for a model whose row id differs from them, from
# the deprecations page (gpt-4, gpt-4-turbo, gpt-4-turbo-preview, the five
# -completions names and the two gpt-4-32k snapshots) and the model pages,
# where both gpt-daybreak aliases read "This alias is deprecated". SNAPSHOT
# does not strip any of these.
ALIASES = {
    "gpt-4": "gpt-4-0613",
    "gpt-4-turbo": "gpt-4-turbo-2024-04-09",
    "gpt-4-turbo-preview": "gpt-4-0125-preview",
    # "gpt-3.5-turbo-0125 | gpt-3.5-turbo, gpt-3.5-turbo-completions" and the
    # like; gpt-4-turbo-preview-completions is among the names that "point
    # to" gpt-4-0125-preview.
    "gpt-3.5-turbo-completions": "gpt-3.5-turbo-0125",
    "gpt-4-completions": "gpt-4-0613",
    "gpt-4-0613-completions": "gpt-4-0613",
    "gpt-4-turbo-completions": "gpt-4-turbo-2024-04-09",
    "gpt-4-turbo-preview-completions": "gpt-4-0125-preview",
    "gpt-4-32k-0613": "gpt-4-32k",
    "gpt-4-32k-0314": "gpt-4-32k",
    "gpt-daybreak-blue-latest": "gpt-5.6-sol",
    "gpt-daybreak-red-latest": "gpt-5.6-cyber",
}

# The flagship, so an unknown id errs towards overstating. It is flagged in
# every report either way.
FALLBACK_MODEL = "gpt-6-astra"

# Models the page lists that this table leaves out on purpose. None is left
# out on purpose, so the set is empty; --check-prices names any id matching
# WATCH that it finds on the page and not here.
WATCH = r"^(gpt-[5-9]|o\d|codex)"
IGNORE = set()

# The page's row labels are API ids, so no PAGE_NAMES map is needed.

# A column header, less any "short context " or "long context " in front, as
# the field page_rates() gives it. A long-context column takes "long_" in
# front, and its writes are named by lifetime (long_write_5m, long_write_1h).
COLUMNS = {"input": "in", "output": "out", "cached input": "cached",
           "30m write": "write", "12h write": "write_1h"}
_LONG_FIELD = {"in": "long_in", "out": "long_out", "cached": "long_cached",
               "write": "long_write_5m", "write_1h": "long_write_1h"}
_FOOTNOTE = re.compile(r">\s*(\d+)K input tokens")


def _model(cell: str) -> str:
    """"gpt-5.5 (<272K context length)" -> "gpt-5.5"."""
    return cell.split("(")[0].strip()


def _fields(header: list) -> dict:
    """{field: column position} for a price table's header, read by name."""
    at = {}
    for i, cell in enumerate(header):
        name = cell.strip().lower()
        long = name.startswith("long context ")
        for prefix in ("short context ", "long context "):
            if name.startswith(prefix):
                name = name[len(prefix):]
        field = COLUMNS.get(name)
        if field:
            at[_LONG_FIELD[field] if long else field] = i
    return at


def _fill(r: dict) -> dict:
    """A "-" on the page means no discount or no premium: the ordinary input
    rate applies. Recorded as that, so it compares like any other figure. A
    missing cached or 30-minute write column reads the same way; a 12-hour
    write is filled only where its column printed "-", so a model page that
    has no such column leaves the 12-hour write to follow the 30-minute one.
    A long-context figure the page leaves out is dropped."""
    if r.get("in") is not None:
        for field in ("cached", "write"):
            if r.get(field) is None:
                r[field] = r["in"]
        if "write_1h" in r and r["write_1h"] is None:
            r["write_1h"] = r["in"]
    return {k: v for k, v in r.items() if v is not None}


def page_rates(fetch, tables, want=None):
    """Every rate the published page states, as {model id: {field: $/MTok}},
    plus page model ids this table does not have.

    Reads the markdown form of the page (SOURCE_MD), every pipe table with
    its nearest heading as `tables` gives them, cells by header name, never
    by position. Tables headed "Standard pricing data" give the standard
    figures, ten-column (short and long context, two write lifetimes) and
    four-column (input, output, cached input) alike: on the page of 2
    November 2026 the flagship pair, then a three-row ten-column table each
    for the Cyber and the Life sciences (Rosalind) models. Tables headed
    "Fast pricing data" give fast_in and fast_out. Of the "Grouped Pricing
    Table data" tables, one headed Model or Model configuration, then Input,
    Output and Cached input, is standard (the Rosalind models on 27 October
    2026, the Legal model configurations since), and of those headed
    Category, Model and the same three, the first is standard and the second
    fast. Batch, Flex, Ultrafast, fine-tuning, audio, image and tool tables
    are not read for rates. The model ids in them, and in any table this
    reader does not recognise, are still checked against the table, so a
    model printed only in a new layout is named rather than dropped; a dated
    snapshot of a row (fine-tuning lists o4-mini-2025-04-16) is not new. The
    long-context threshold is read from the page's footnote (">272K input
    tokens"), else LONG_OVER.

    With want=None (--check-prices, which reports differences and never
    edits this file) only the main page is fetched: every current model is
    on it, and a retired one is expected to be absent. For the startup
    lookup (want: the ids it asks for) a wanted model the main page lacks is
    read from its own model page; one that answers with an HTTP error, such
    as a 404, is skipped, so it cannot fail the rest."""
    text = fetch(SOURCE_MD)
    rates, fast, seen, unread, grouped = {}, {}, [], [], 0
    for title, header, rows in tables(text):
        t = title.strip().lower()
        h = [c.strip().lower() for c in header]
        at = _fields(header)
        kind = ""
        if "in" in at and "out" in at:
            if t.startswith("standard") and h[0] == "model":
                kind, name_at = "standard", 0
            elif t.startswith("fast") and h[0] == "model":
                kind, name_at = "fast", 0
            elif (t == "grouped pricing table data" and h[0] in ("model", "model configuration")
                  and h[1:] == ["input", "output", "cached input"]):
                kind, name_at = "standard", 0
            elif t == "grouped pricing table data" and h[:2] == ["category", "model"] and len(h) == 5:
                grouped += 1
                if grouped <= 2:
                    kind, name_at = ("standard" if grouped == 1 else "fast"), 1
        if not kind:
            unread.extend(_model(r[0]) for r in rows if r)
            continue
        for r in rows:
            if len(r) != len(h):
                continue
            mid = _model(r[name_at])
            seen.append(mid)
            figures = {field: money(r[i]) for field, i in at.items()}
            if kind == "fast":
                fast[mid] = (figures["in"], figures["out"])
            else:
                rates.setdefault(mid, {}).update(figures)
    for mid, (fin, fout) in fast.items():
        if mid in rates:
            rates[mid]["fast_in"], rates[mid]["fast_out"] = fin, fout
    m = _FOOTNOTE.search(text)
    over = int(m.group(1)) * 1000 if m else LONG_OVER
    for r in rates.values():
        if r.get("long_in") is not None:
            r["long_over"] = over
    for mid in (want or ()):
        if mid in rates:
            continue
        # A model id names its own page. One from a log or an import file can
        # be anything, so only an id shaped like OpenAI's is put in the
        # address: letters, digits, dots, hyphens and underscores, never a
        # slash, a dot pair, a query or a fragment.
        if not PAGE_ID.fullmatch(mid):
            continue
        try:
            page = fetch(MODEL_PAGE_MD.format(model=mid))
        except urllib.error.HTTPError:
            continue
        r = {}
        for title, header, rows in tables(page):
            if [c.strip().lower() for c in header][:2] != ["metric", "price"]:
                continue
            for row in rows:
                key = {"input": "in", "cached input": "cached", "cache writes": "write",
                       "output": "out"}.get(row[0].strip().lower())
                if key and key not in r:
                    r[key] = money(row[1])
            break
        if r:
            rates[mid] = r
    def new(m):
        return bool(re.match(WATCH, m)) and m not in PRICES and m not in IGNORE
    unknown = sorted({m for m in seen if new(m)}
                     | {m for m in unread if new(m) and re.sub(SNAPSHOT, "", m) not in PRICES})
    return {m: _fill(r) for m, r in rates.items()}, unknown
