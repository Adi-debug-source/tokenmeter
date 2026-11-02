"""Every published rate, typed from the provider's own pricing page.

Each figure here was read off the page, not copied from the tables in
pricing/, so a slip in either one fails. A rate change is a new dated row in
the table and a new figure here; see pricing/README.md.
"""

import datetime as dt
import os
import types
import unittest
import unittest.mock

from helpers import FIXTURES, Base, cost_of, noon, slurp, tm, usage

from pricing import mimo, minimax

M = 1_000_000
UTC = dt.timezone.utc


# Anthropic (Claude) rates, typed from the maker's own pricing page by a
# third reader, so a slip in the table, in either earlier reading or here fails.
#
# Each figure was read off the page on 27 October 2026, or, for a retired model
# the page no longer prints, off the Internet Archive copy of Anthropic's own
# pricing page named beside it. None was copied from pricing/anthropic.py. A
# rate change is a new dated row in the table and a new figure here; see
# pricing/README.md.


class TestAnthropicPublishedRates(Base):
    """Every rate in the Anthropic table, typed from the page.

    Read on 27 October 2026 at 17:46 UTC from
    https://platform.claude.com/docs/en/about-claude/pricing.md (the markdown
    form, 53,397 bytes; a fetch at 18:05 UTC the same day was 53,425 bytes,
    the difference being fourteen straight quotes in the prose turned curly,
    with no figure changed). The page says "All
    prices are in USD." Its "Model pricing" table has the columns Base input
    tokens, 5m cache writes, 1h cache writes, Cache hits and refreshes, and
    Output tokens, each in dollars per million tokens ("MTok").

    The page names models by display name; the table id for each:
    Claude Fable 5.1 claude-fable-5-1, Claude Mythos 5.1 claude-mythos-5-1,
    Claude Fable 5 claude-fable-5, Claude Mythos 5 claude-mythos-5, Claude
    Opus 5.5 claude-opus-5-5, Claude Opus 5 claude-opus-5, Claude Opus 4.8
    claude-opus-4-8, Claude Opus 4.7 claude-opus-4-7, Claude Opus 4.6
    claude-opus-4-6, Claude Opus 4.5 claude-opus-4-5, Claude Opus 4.1
    claude-opus-4-1, Claude Opus 4 claude-opus-4, Claude Sonnet 5.5
    claude-sonnet-5-5, Claude Sonnet 5 claude-sonnet-5, Claude Sonnet 4.6
    claude-sonnet-4-6, Claude Sonnet 4.5 claude-sonnet-4-5, Claude Sonnet 4
    claude-sonnet-4, Claude Haiku 5.5 claude-haiku-5-5, Claude Haiku 4.5
    claude-haiku-4-5, Claude Haiku 3.5 claude-haiku-3-5. Opus 4.1, Opus 4,
    Sonnet 4 and Haiku 3.5 are marked retired on the page and still priced
    there.

    Retired models the page no longer prints, each from the raw archive copy
    of Anthropic's own pricing page:
    - Claude Sonnet 3.7 claude-3-7-sonnet, Claude Opus 3 claude-3-opus and
      Claude Haiku 3 claude-3-haiku: web.archive.org/web/20260513172300/
      https://platform.claude.com/docs/en/about-claude/pricing, "Model
      pricing" table, same five columns.
    - Claude Sonnet 3.5 claude-3-5-sonnet: web.archive.org/web/
      20251028160151/https://docs.claude.com/en/docs/about-claude/pricing,
      "Model pricing" table, row "Claude Sonnet 3.5 (deprecated)".
    - Claude 3 Sonnet claude-3-sonnet: web.archive.org/web/20250121003151/
      https://www.anthropic.com/pricing, the "Claude 3 Sonnet" card, which
      prints Input and Output only.
    - Claude 2.1 claude-2.1 and Claude 2.0 claude-2.0: web.archive.org/web/
      20241024003303/https://www.anthropic.com/pricing, "Explore legacy
      models", cards printing Input and Output only.
    Those three cards print no cache price (the models never offered prompt
    caching), so, as in the other pinned classes, each is listed with its
    input rate as the cache hit: no discount.

    OFFICIAL is (Base input, Output, Cache hits) and WRITES is (5m cache
    writes, 1h cache writes), in dollars per million tokens. Claude Haiku
    5.5's row is the page's "for prompts up to 100,000 tokens" row; its
    higher row is pinned in its own test below. The page prints no
    thinking and non-thinking split, no time-of-day rate and no discount
    with an end date. Data residency (1.1x for US-only inference) is a
    per-request parameter, not a rate, and the Batch API is not a rate this
    tool applies, so neither is pinned here.
    """

    # model: (base input, output, cache hit $/MTok)
    OFFICIAL = {
        "claude-fable-5-1": (10, 50, 0.25),
        "claude-mythos-5-1": (10, 50, 0.25),
        "claude-fable-5": (10, 50, 1),
        "claude-mythos-5": (10, 50, 1),
        "claude-opus-5-5": (4, 20, 0.20),
        "claude-opus-5": (5, 25, 0.50),
        "claude-opus-4-8": (5, 25, 0.50),
        "claude-opus-4-7": (5, 25, 0.50),
        "claude-opus-4-6": (5, 25, 0.50),
        "claude-opus-4-5": (5, 25, 0.50),
        "claude-opus-4-1": (15, 75, 1.50),
        "claude-opus-4": (15, 75, 1.50),
        "claude-sonnet-5-5": (2, 10, 0.10),
        "claude-sonnet-5": (2, 10, 0.20),
        "claude-sonnet-4-6": (3, 15, 0.30),
        "claude-sonnet-4-5": (3, 15, 0.30),
        "claude-sonnet-4": (3, 15, 0.30),
        "claude-haiku-5-5": (0.10, 0.50, 0.01),
        "claude-haiku-4-5": (1, 5, 0.10),
        "claude-haiku-3-5": (0.80, 4, 0.08),
        # Retired, from the archive copies named in the docstring.
        "claude-3-7-sonnet": (3, 15, 0.30),
        "claude-3-5-sonnet": (3, 15, 0.30),
        "claude-3-opus": (15, 75, 1.50),
        "claude-3-haiku": (0.25, 1.25, 0.03),
        "claude-3-sonnet": (3, 15, 3),
        "claude-2.1": (8, 24, 8),
        "claude-2.0": (8, 24, 8),
    }

    # model: (5-minute cache write, 1-hour cache write $/MTok). The three
    # models whose cards print no cache price are absent.
    WRITES = {
        "claude-fable-5-1": (12.50, 20),
        "claude-mythos-5-1": (12.50, 20),
        "claude-fable-5": (12.50, 20),
        "claude-mythos-5": (12.50, 20),
        "claude-opus-5-5": (5, 8),
        "claude-opus-5": (6.25, 10),
        "claude-opus-4-8": (6.25, 10),
        "claude-opus-4-7": (6.25, 10),
        "claude-opus-4-6": (6.25, 10),
        "claude-opus-4-5": (6.25, 10),
        "claude-opus-4-1": (18.75, 30),
        "claude-opus-4": (18.75, 30),
        "claude-sonnet-5-5": (2.50, 4),
        "claude-sonnet-5": (2.50, 4),
        "claude-sonnet-4-6": (3.75, 6),
        "claude-sonnet-4-5": (3.75, 6),
        "claude-sonnet-4": (3.75, 6),
        "claude-haiku-5-5": (0.125, 0.20),
        "claude-haiku-4-5": (1.25, 2),
        "claude-haiku-3-5": (1, 1.60),
        "claude-3-7-sonnet": (3.75, 6),
        "claude-3-5-sonnet": (3.75, 6),
        "claude-3-opus": (18.75, 30),
        "claude-3-haiku": (0.30, 0.50),
    }

    def test_every_rate_matches_the_pricing_page(self):
        """Guards against a mistyped base rate in pricing/anthropic.py, a model
        missing from the table, or one the page does not price: the table must
        hold exactly these ids, each at the page's input, output and cache-hit
        figures, and recognised rather than priced at the fallback."""
        self.assertEqual(set(tm.TABLES["anthropic"].PRICES), set(self.OFFICIAL),
                         "table and pinned list differ")
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model, provider="anthropic")
                self.assertTrue(known, f"{model} falls back to the default rates")
                self.assertEqual(row["in"], inp)
                self.assertEqual(row["out"], out)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_every_cache_write_matches_the_pricing_page(self):
        """Guards against a cache-write price that drifts from the page's 5m
        and 1h columns, including Claude Haiku 3's, which the 13 May 2026
        archive copy prints at $0.30 and $0.50 (1.2x and 2x its $0.25 input)
        rather than the 1.25x and 2x every other model follows. Priced through
        price_record() with 1,000 tokens of each, so the multiples the engine
        really applies are what is checked."""
        for model, (w5, w1) in self.WRITES.items():
            with self.subTest(model=model):
                c5 = tm.price_record(model, usage(w5=1_000), provider="anthropic")
                c1 = tm.price_record(model, usage(w1=1_000), provider="anthropic")
                self.assertFalse(c5["_unknown_model"])
                self.assertAlmostEqual(c5["cache_write"], 1_000 * w5 / M, places=12)
                self.assertAlmostEqual(c1["cache_write"], 1_000 * w1 / M, places=12)

    def test_cache_write_multipliers(self):
        """Guards the table defaults against the page's "Prompt caching"
        table: a 5-minute cache write is "1.25x base input price" and a 1-hour
        write "2x base input price"."""
        self.assertEqual(tm.TABLES["anthropic"].CACHE_WRITE_5M_MULT, 1.25)
        self.assertEqual(tm.TABLES["anthropic"].CACHE_WRITE_1H_MULT, 2.0)

    def test_sonnet_5_5_cache_reads_were_halved_on_7_october_2026(self):
        """Guards the one dated rate change in the table. Anthropic's release
        notes (platform.claude.com/docs/en/release-notes/overview.md, read 27
        October 2026), under "October 7, 2026": "We've lowered the price of
        prompt cache reads on Claude Sonnet 5.5 from $0.20 USD to $0.10 USD per
        million tokens ... Cache writes and all other prices are unchanged."
        The archive copy of the pricing page at 20261006213610 prints $0.20 in
        Sonnet 5.5's "Hits and refreshes" column and the one at 20261008043247
        prints $0.10, with $2 in, $10 out, $2.50 and $4 writes in both. A call
        keeps the price of its own day."""
        u = usage(inp=M, read=M, w5=M, w1=M, out=M)
        before = tm.price_record("claude-sonnet-5-5", u, when=noon("2026-10-06"),
                                 provider="anthropic")
        after = tm.price_record("claude-sonnet-5-5", u, when=noon("2026-10-07"),
                                provider="anthropic")
        self.assertAlmostEqual(before["cache_read"], 0.20, places=9)
        self.assertAlmostEqual(after["cache_read"], 0.10, places=9)
        for c in (before, after):
            self.assertFalse(c["_unknown_model"])
            self.assertAlmostEqual(c["input"], 2.00, places=9)
            self.assertAlmostEqual(c["cache_write"], 2.50 + 4.00, places=9)
            self.assertAlmostEqual(c["output"], 10.00, places=9)

    def test_haiku_5_5_is_priced_by_prompt_length(self):
        """Guards the page's one prompt-length tier. "Claude Haiku 5.5 (for
        prompts up to 100,000 tokens)": $0.10 in, $0.125 5m write, $0.20 1h
        write, $0.01 hit, $0.50 out. "(for prompts over 100,000 tokens)":
        $0.50, $0.625, $1, $0.05, $2.50. "Long context pricing": "A request's
        prompt length counts all of its input tokens, including cache reads
        and cache writes", and a request over the line pays the higher prices
        on all of it. So exactly 100,000 is the lower row, 100,001 the higher."""
        up_to = {"in": 0.10, "w5": 0.125, "w1": 0.20, "hit": 0.01, "out": 0.50}
        over = {"in": 0.50, "w5": 0.625, "w1": 1.00, "hit": 0.05, "out": 2.50}
        # 90,000 of each prompt is cache: exactly 100,000, then 100,001.
        for inp, rate in ((10_000, up_to), (10_001, over)):
            with self.subTest(prompt=inp + 90_000):
                c = tm.price_record("claude-haiku-5-5",
                                    usage(inp=inp, read=60_000, w5=20_000, w1=10_000, out=1_000),
                                    provider="anthropic")
                self.assertFalse(c["_unknown_model"])
                self.assertAlmostEqual(c["input"], inp * rate["in"] / M, places=12)
                self.assertAlmostEqual(c["cache_read"], 60_000 * rate["hit"] / M, places=12)
                self.assertAlmostEqual(c["cache_write"],
                                       (20_000 * rate["w5"] + 10_000 * rate["w1"]) / M,
                                       places=12)
                self.assertAlmostEqual(c["output"], 1_000 * rate["out"] / M, places=12)
        # Cache reads alone can carry a request over the line.
        c = tm.price_record("claude-haiku-5-5", usage(inp=1, read=100_000, out=M),
                            provider="anthropic")
        self.assertAlmostEqual(c["output"], 2.50, places=9)

    def test_no_other_model_has_a_long_context_premium(self):
        """Guards against a long-context tier leaking onto a model the page
        prices flat. "Long context pricing": "Claude 4.6 and later models
        (except Claude Haiku 5.5) ... include the full 1M token context window
        at standard pricing. (A 900k-token request is billed at the same
        per-token rate as a 9k-token request.)" Today's rate, the page's own
        two request sizes."""
        flat = ("claude-fable-5-1", "claude-mythos-5-1", "claude-fable-5", "claude-mythos-5",
                "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
                "claude-opus-4-6", "claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6")
        for model in flat:
            inp, out, hit = self.OFFICIAL[model]
            for size in (9_000, 900_000):
                with self.subTest(model=model, prompt=size):
                    c = tm.price_record(model, usage(inp=size - 1_000, read=1_000, out=1_000),
                                        provider="anthropic")
                    self.assertAlmostEqual(c["input"], (size - 1_000) * inp / M, places=12)
                    self.assertAlmostEqual(c["cache_read"], 1_000 * hit / M, places=12)
                    self.assertAlmostEqual(c["output"], 1_000 * out / M, places=12)

    def test_fast_mode_rates(self):
        """Guards the "Fast mode pricing" table: Claude Opus 5.5 $8 in and $40
        out; "Claude Opus 5 / Claude Opus 4.8" $10 and $50. The page offers
        fast mode for those three models only, so every other row has none."""
        fast = {"claude-opus-5-5": (8, 40), "claude-opus-5": (10, 50),
                "claude-opus-4-8": (10, 50)}
        for model in self.OFFICIAL:
            with self.subTest(model=model):
                row, _ = tm.lookup(model, provider="anthropic")
                if model in fast:
                    self.assertEqual(tuple(row["fast"]), fast[model])
                else:
                    self.assertFalse(row.get("fast"), f"{model} has a fast rate")

    def test_cache_multipliers_apply_on_top_of_fast_mode(self):
        """Guards the page's rule under "Fast mode pricing": "Prompt caching
        multipliers apply on top of fast mode pricing." On Claude Opus 5.5 at
        $8 fast input, a hit (0.05x, per the "Prompt caching" table) is $0.40,
        a 5m write (1.25x) $10 and a 1h write (2x) $16; output is $40."""
        c = tm.price_record("claude-opus-5-5", usage(inp=M, read=M, w5=M, w1=M, out=M),
                            speed="fast", provider="anthropic")
        self.assertAlmostEqual(c["input"], 8.0, places=9)
        self.assertAlmostEqual(c["cache_read"], 0.40, places=9)
        self.assertAlmostEqual(c["cache_write"], 10.0 + 16.0, places=9)
        self.assertAlmostEqual(c["output"], 40.0, places=9)

    def test_web_search_is_ten_dollars_per_thousand(self):
        """Guards the "Web search tool" price: "$10 USD per 1,000 searches",
        charged in addition to tokens."""
        self.assertEqual(tm.TABLES["anthropic"].WEB_SEARCH_PER_1K, 10.0)
        c = tm.price_record("claude-sonnet-4-6", usage(searches=1_000), provider="anthropic")
        self.assertAlmostEqual(c["web_search"], 10.0, places=9)

    def test_a_newer_model_is_never_priced_as_the_older_one(self):
        """The bug the menu bar exposed on 26 September 2026.

        lookup() used to fall back to "the longest known id this one starts
        with". claude-opus-5-5 starts with claude-opus-5, so a new and cheaper
        model was billed at the old one's rates and reported as recognised, so
        no warning fired. Only a trailing date means "the same model".
        """
        for unknown in ("claude-opus-6", "claude-sonnet-5-7", "claude-haiku-9"):
            with self.subTest(model=unknown):
                _, known = tm.lookup(unknown)
                self.assertFalse(known, f"{unknown} was silently prefix-matched")

    def test_a_dated_snapshot_is_still_the_same_model(self):
        """The tolerance that must survive: a trailing -YYYYMMDD."""
        row, known = tm.lookup("claude-opus-5-5-20260901")
        self.assertTrue(known)
        self.assertEqual(row["in"], 4.0)


# OpenAI rates, typed from the maker's own pricing page by a third reader, so
# a slip in the table, in either earlier reading or here fails.
#
# Each figure was read off the page, or for a retired model off the Internet
# Archive's copy of the maker's own page, not copied from pricing/openai.py.
# A rate change is a new dated row in the table and a new figure here; see
# pricing/README.md.

# The day the page was read. Lookups are made on this day, so every row the
# table dates (the 12-hour cache writes from 20 October 2026) is in force.
OPENAI_READ_ON = noon("2026-10-27")


class TestOpenAIPublishedRates(Base):
    """Every rate in the OpenAI table, typed from the page.

    Current models: https://developers.openai.com/api/docs/pricing.md, the
    markdown form of https://developers.openai.com/api/docs/pricing, fetched
    27 October 2026 at 12:33 UTC (22,824 bytes, sha256
    93d302a9b7a384877533bc3ab5bb48eebf4b56bd6add0f194095054b2a13f952). The
    Standard tables are what OFFICIAL pins: "Standard pricing data" under
    Flagship models and under Cyber models, the Life sciences table and the
    Standard tab of the specialised models table. The Fast tables are what
    the table's `fast` holds. Batch, Flex and Ultrafast are not pinned: the
    row has no key for them. gpt-6-rosalind, released 30 October 2026 (the
    changelog), is from the same page fetched 2 November 2026 at 00:03 UTC
    (23,508 bytes, sha256
    56e3da9bb29246cad60003e01f3fdc6b536149a09f5effe5e79af020a4922cfc), the
    ten-column Standard table under Life sciences models. gpt-6-astra-law,
    added on 2 November 2026 on the maintainer's decision that day, is
    from the same page fetched again on 2 November 2026 at 17:30 UTC (the
    same 23,508 bytes and sha256), the "Model configuration" table under
    Legal model configurations, which prints input, output and cached
    input only.

    Retired models, each from the copy of the maker's page cited beside it:
      https://web.archive.org/web/20260730195107/https://developers.openai.com/api/docs/pricing
        sha256 47fc2f9d0436f0e2761c28bfb0965a75119bc04fa7217a53b5666e1247101b09
      https://web.archive.org/web/20260811103033/https://developers.openai.com/api/docs/pricing
        sha256 983cbc4ccbae303d32d91f73d377e4408b68e01b26b77597fc5b2302ca37a120
      https://web.archive.org/web/20261010170540/https://developers.openai.com/api/docs/pricing.md
        sha256 e0767b5009dcc929a2f9eeb9ce6096a57ff12e5d8c011de9d69ff145aef2fc28
      https://web.archive.org/web/20250211094612/https://openai.com/api/pricing/
        sha256 5ce05a90151c6cb4b354d4affaab2c7f90e5161c5e07682abb618bd07124123a
      https://web.archive.org/web/20250413004940/https://openai.com/api/pricing/
        sha256 7fd15e5eebe60b29dc71ace78dffb1b12393fc0759ef7e16ced0703d095dba1d
    and the shutdown dates from https://developers.openai.com/api/docs/deprecations.md
    (sha256 3fddf4c625d689e43e559c236bcdd675de8a3b3d035070ba205827d8ad0a2fc2).

    OFFICIAL is (input, output, cached input), dollars per million tokens,
    at short context. A "-" in the cached input column means no cached rate,
    so the input rate is listed: no discount. A retired model keeps its last
    published rate.
    """

    OFFICIAL = {
        # Flagship models, Standard, short context (27 October 2026).
        "gpt-6-astra": (10.00, 50.00, 1.00), "gpt-6.1-sol": (2.00, 10.00, 0.10),
        "gpt-6.1-terra": (1.00, 5.00, 0.05), "gpt-6-luna": (0.10, 0.50, 0.01),
        "gpt-6-sol": (2.00, 10.00, 0.20), "gpt-5.6-sol": (4.00, 20.00, 0.40),
        "gpt-5.6-terra": (2.00, 12.00, 0.20), "gpt-5.6-luna": (0.20, 1.20, 0.02),
        "gpt-5.5": (5.00, 30.00, 0.50), "gpt-5.5-pro": (30.00, 180.00, 30.00),
        "gpt-5.4": (2.50, 15.00, 0.25), "gpt-5.4-pro": (30.00, 180.00, 30.00),
        # The four-column Standard table under it.
        "gpt-5.4-mini": (0.75, 4.50, 0.075), "gpt-5.4-nano": (0.20, 1.25, 0.02),
        "gpt-5.2": (1.75, 14.00, 0.175), "gpt-5.2-pro": (21.00, 168.00, 21.00),
        "gpt-5.1": (1.25, 10.00, 0.125), "gpt-5": (1.25, 10.00, 0.125),
        "gpt-5-mini": (0.25, 2.00, 0.025), "gpt-5-nano": (0.05, 0.40, 0.005),
        "gpt-5-pro": (15.00, 120.00, 15.00), "gpt-4.1": (2.00, 8.00, 0.50),
        "gpt-4.1-mini": (0.40, 1.60, 0.10), "gpt-4o": (2.50, 10.00, 1.25),
        "gpt-4o-mini": (0.15, 0.60, 0.075), "o3-pro": (20.00, 80.00, 20.00),
        "o3": (2.00, 8.00, 0.50),
        # Cyber models, Standard.
        "gpt-5.6-cyber": (12.50, 75.00, 1.25), "gpt-5.5-cyber": (12.50, 75.00, 1.25),
        # Life sciences models (gpt-6-rosalind from the page of 2 November 2026).
        "gpt-6-rosalind": (15.00, 75.00, 1.50),
        "gpt-rosalind-research": (5.00, 25.00, 0.50),
        "gpt-rosalind-discovery": (5.00, 25.00, 0.50),
        # Legal model configurations, from the page of 2 November 2026.
        "gpt-6-astra-law": (10.00, 50.00, 1.00),
        # Specialised models, Standard tab.
        "chat-latest": (5.00, 30.00, 0.50), "gpt-5.3-codex": (1.75, 14.00, 0.175),
        "gpt-5-search-api": (1.25, 10.00, 0.125),
        # Shut down 23 October 2026, still printed on the page of 27 October 2026.
        "gpt-4.1-nano": (0.10, 0.40, 0.025), "gpt-4o-2024-05-13": (5.00, 15.00, 5.00),
        "o1": (15.00, 60.00, 7.50), "o1-pro": (150.00, 600.00, 150.00),
        "o4-mini": (1.10, 4.40, 0.275), "o3-mini": (1.10, 4.40, 0.55),
        "gpt-4-turbo-2024-04-09": (10.00, 30.00, 10.00), "gpt-4-0613": (30.00, 60.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50, 0.50), "gpt-3.5-turbo-0125": (0.50, 1.50, 0.50),
        # The 30 July 2026 copy: the flagship table, then the specialised table.
        "gpt-4-1106-preview": (10.00, 30.00, 10.00), "gpt-4-0314": (30.00, 60.00, 30.00),
        "gpt-4-0125-preview": (10.00, 30.00, 10.00), "o1-mini": (1.10, 4.40, 0.55),
        "gpt-4-32k": (60.00, 120.00, 60.00),
        "gpt-5.2-codex": (1.75, 14.00, 0.175), "gpt-5.1-codex-max": (1.25, 10.00, 0.125),
        "gpt-5.1-codex": (1.25, 10.00, 0.125), "gpt-5.1-codex-mini": (0.25, 2.00, 0.025),
        "gpt-5-codex": (1.25, 10.00, 0.125), "codex-mini-latest": (1.50, 6.00, 0.375),
        "gpt-5-chat-latest": (1.25, 10.00, 0.125), "gpt-5.1-chat-latest": (1.25, 10.00, 0.125),
        "chatgpt-4o-latest": (5.00, 15.00, 5.00),
        "o3-deep-research": (10.00, 40.00, 2.50), "o4-mini-deep-research": (2.00, 8.00, 0.50),
        "computer-use-preview": (3.00, 12.00, 3.00),
        "gpt-4o-search-preview": (2.50, 10.00, 2.50),
        "gpt-4o-mini-search-preview": (0.15, 0.60, 0.15),
        # The 11 August 2026 copy, specialised table, ChatGPT group.
        "gpt-5.2-chat-latest": (1.75, 14.00, 0.175), "gpt-5.3-chat-latest": (1.75, 14.00, 0.175),
        # The 10 October 2026 markdown copy, Standard pricing data.
        "gpt-3.5-turbo-1106": (1.00, 2.00, 1.00), "gpt-3.5-turbo-instruct": (1.50, 2.00, 1.50),
        "davinci-002": (2.00, 2.00, 2.00), "babbage-002": (0.40, 0.40, 0.40),
        # openai.com/api/pricing, 11 February 2025 ("o1-preview") and
        # 13 April 2025 (the card "GPT-4.5", the API's gpt-4.5-preview).
        "o1-preview": (15.00, 60.00, 7.50), "gpt-4.5-preview": (75.00, 150.00, 37.50),
    }

    # Fast tables of 27 October 2026 (Fast was named Priority until 30 July
    # 2026): (input, output, cached input). gpt-5.3-codex is from the Fast
    # tab of the specialised table. gpt-4o-2024-05-13 prints "-" for cached
    # input, listed at its fast input rate. Every other model is absent from
    # the Fast tables and its copy, so it has no fast rate.
    FAST = {
        "gpt-6-astra": (20.00, 100.00, 2.00), "gpt-6.1-sol": (4.00, 20.00, 0.20),
        "gpt-6.1-terra": (2.00, 10.00, 0.10), "gpt-6-luna": (0.20, 1.00, 0.02),
        "gpt-6-sol": (4.00, 20.00, 0.40), "gpt-5.6-sol": (8.00, 40.00, 0.80),
        "gpt-5.6-terra": (4.00, 24.00, 0.40), "gpt-5.6-luna": (0.40, 2.40, 0.04),
        "gpt-5.5": (12.50, 75.00, 1.25), "gpt-5.4": (5.00, 30.00, 0.50),
        "gpt-5.4-mini": (1.50, 9.00, 0.15), "gpt-5.2": (3.50, 28.00, 0.35),
        "gpt-5.1": (2.50, 20.00, 0.25), "gpt-5": (2.50, 20.00, 0.25),
        "gpt-5-mini": (0.45, 3.60, 0.045), "gpt-4.1": (3.50, 14.00, 0.875),
        "gpt-4.1-mini": (0.70, 2.80, 0.175), "gpt-4.1-nano": (0.20, 0.80, 0.05),
        "gpt-4o": (4.25, 17.00, 2.125), "gpt-4o-2024-05-13": (8.75, 26.25, 8.75),
        "gpt-4o-mini": (0.25, 1.00, 0.125), "o3": (3.50, 14.00, 0.875),
        "o4-mini": (2.00, 8.00, 0.50), "gpt-5.3-codex": (3.50, 28.00, 0.35),
    }

    # The Fast tab of the specialised table in the 30 July 2026 copy, for four
    # Codex models shut down on 23 July 2026. Pinned in their own test below.
    RETIRED_FAST = {
        "gpt-5.2-codex": (3.50, 28.00, 0.35), "gpt-5.1-codex-max": (2.50, 20.00, 0.25),
        "gpt-5.1-codex": (2.50, 20.00, 0.25), "gpt-5-codex": (2.50, 20.00, 0.25),
    }

    # The ten-column tables, short context: (30m write, 12h write), for the
    # rows that print both. Every other row prints "-" or has no such column.
    WRITES = {
        "gpt-6-astra": (12.50, 25.00), "gpt-6.1-sol": (2.50, 5.00),
        "gpt-6.1-terra": (1.25, 2.50), "gpt-6-luna": (0.125, 0.25),
        "gpt-6-sol": (2.50, 5.00), "gpt-5.6-sol": (5.00, 10.00),
        "gpt-5.6-terra": (2.50, 5.00), "gpt-5.6-luna": (0.25, 0.50),
        "gpt-5.6-cyber": (15.625, 31.25), "gpt-6-rosalind": (18.75, 37.50),
    }
    FAST_WRITES = {
        "gpt-6-astra": (25.00, 50.00), "gpt-6.1-sol": (5.00, 10.00),
        "gpt-6.1-terra": (2.50, 5.00), "gpt-6-luna": (0.25, 0.50),
        "gpt-6-sol": (5.00, 10.00), "gpt-5.6-sol": (10.00, 20.00),
        "gpt-5.6-terra": (5.00, 10.00), "gpt-5.6-luna": (0.50, 1.00),
    }

    # Long context, "Long context: >272K input tokens": (input, output,
    # cached input, 30m write, 12h write). None where the page prints "-".
    LONG = {
        "gpt-6-astra": (20.00, 75.00, 2.00, 25.00, 50.00),
        "gpt-6.1-sol": (4.00, 15.00, 0.20, 5.00, 10.00),
        "gpt-6.1-terra": (2.00, 7.50, 0.10, 2.50, 5.00),
        "gpt-6-luna": (0.20, 0.75, 0.02, 0.25, 0.50),
        "gpt-6-sol": (4.00, 15.00, 0.40, 5.00, 10.00),
        "gpt-5.6-sol": (8.00, 30.00, 0.80, 10.00, 20.00),
        "gpt-5.6-terra": (4.00, 18.00, 0.40, 5.00, 10.00),
        "gpt-5.6-luna": (0.40, 1.80, 0.04, 0.50, 1.00),
        "gpt-6-rosalind": (30.00, 112.50, 3.00, 37.50, 75.00),
        "gpt-5.5": (10.00, 45.00, 1.00, None, None),
        "gpt-5.5-pro": (60.00, 270.00, None, None, None),
        "gpt-5.4": (5.00, 22.50, 0.50, None, None),
        "gpt-5.4-pro": (60.00, 270.00, None, None, None),
    }
    FAST_LONG = {
        "gpt-6-astra": (40.00, 150.00, 4.00, 50.00, 100.00),
        "gpt-6.1-sol": (8.00, 30.00, 0.40, 10.00, 20.00),
        "gpt-6.1-terra": (4.00, 15.00, 0.20, 5.00, 10.00),
        "gpt-6-luna": (0.40, 1.50, 0.04, 0.50, 1.00),
        "gpt-6-sol": (8.00, 30.00, 0.80, 10.00, 20.00),
        "gpt-5.6-sol": (16.00, 60.00, 1.60, 20.00, 40.00),
        "gpt-5.6-terra": (8.00, 36.00, 0.80, 10.00, 20.00),
        "gpt-5.6-luna": (0.80, 3.60, 0.08, 1.00, 2.00),
    }

    # Shutdown dates from the deprecations page.
    RETIRED = {
        "gpt-3.5-turbo-0125": "2026-10-23", "gpt-3.5-turbo": "2026-10-23",
        "gpt-4-0613": "2026-10-23", "gpt-4-1106-preview": "2026-10-23",
        "gpt-4-turbo-2024-04-09": "2026-10-23", "gpt-4.1-nano": "2026-10-23",
        "gpt-4o-2024-05-13": "2026-10-23", "o1": "2026-10-23", "o1-pro": "2026-10-23",
        "o3-mini": "2026-10-23", "o4-mini": "2026-10-23",
        "computer-use-preview": "2026-07-23", "gpt-4o-mini-search-preview": "2026-07-23",
        "gpt-4o-search-preview": "2026-07-23", "gpt-5-chat-latest": "2026-07-23",
        "gpt-5-codex": "2026-07-23", "gpt-5.1-chat-latest": "2026-07-23",
        "gpt-5.1-codex": "2026-07-23", "gpt-5.1-codex-max": "2026-07-23",
        "gpt-5.1-codex-mini": "2026-07-23", "o3-deep-research": "2026-07-23",
        "o4-mini-deep-research": "2026-07-23", "gpt-5.2-codex": "2026-07-23",
        "gpt-5.2-chat-latest": "2026-08-10", "gpt-5.3-chat-latest": "2026-08-10",
        "gpt-3.5-turbo-instruct": "2026-09-28", "babbage-002": "2026-09-28",
        "davinci-002": "2026-09-28", "gpt-3.5-turbo-1106": "2026-09-28",
        "gpt-4-0314": "2026-03-26", "gpt-4-0125-preview": "2026-03-26",
        "chatgpt-4o-latest": "2026-02-17", "codex-mini-latest": "2026-02-12",
        "o1-preview": "2025-07-28", "o1-mini": "2025-10-27",
        "gpt-4.5-preview": "2025-07-14", "gpt-4-32k": "2025-06-06",
    }

    def _row(self, model, when=OPENAI_READ_ON):
        row, known = tm.lookup(model, when=when, provider="openai")
        self.assertTrue(known, f"{model} is not in the OpenAI table")
        return row

    def test_every_rate_matches_the_pricing_page(self):
        """Guards against an OpenAI rate typed wrongly into pricing/openai.py,
        a model on the page or in the archive missing from the table, or a
        table row no reading accounts for: the table must hold exactly these
        73 ids (36 current, 37 retired), each at the Standard input, output
        and cached input price on the day the page was read."""
        self.assertEqual(set(tm.TABLES["openai"].PRICES), set(self.OFFICIAL),
                         "openai table and the page's model list differ")
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row = self._row(model)
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_fast_rates(self):
        """Guards against a fast pair typed wrongly or left out, a fast rate
        given to a model the Fast tables do not list, and a fast cached rate
        that is not what the page prints. Fast is not a multiple of Standard
        on the older rows (gpt-4.1 is 1.75x, gpt-4o 1.7x), so each pair is
        typed from the page."""
        self.assertLessEqual(set(self.FAST), set(self.OFFICIAL))
        for model in self.OFFICIAL:
            if model in self.FAST or model in self.RETIRED_FAST:
                continue
            with self.subTest(model=model, fast=None):
                self.assertIsNone(self._row(model)["fast"], f"{model} has no Fast row on its page")
        for model, (inp, out, hit) in self.FAST.items():
            with self.subTest(model=model):
                fin, fout = self._row(model)["fast"]
                self.assertAlmostEqual(fin, inp, places=9)
                self.assertAlmostEqual(fout, out, places=9)
                # 100K in, 100K cached, 100K out: under the 272K line.
                c = tm.price_record(model, usage(inp=100_000, read=100_000, out=100_000),
                                    speed="fast", when=OPENAI_READ_ON, provider="openai")
                self.assertFalse(c["_unknown_model"])
                self.assertAlmostEqual(c["input"], inp / 10, places=9)
                self.assertAlmostEqual(c["cache_read"], hit / 10, places=9)
                self.assertAlmostEqual(c["output"], out / 10, places=9)

    def test_retired_codex_models_keep_their_fast_rates(self):
        """The 30 July 2026 copy prints Fast rates for four Codex models shut
        down on 23 July 2026: gpt-5.2-codex $3.50 in, $0.35 cached, $28 out;
        gpt-5.1-codex-max, gpt-5.1-codex and gpt-5-codex $2.50, $0.25, $20.
        Guards against a fast call on one of them being charged the Standard
        rate because the row's `fast` was left empty."""
        for model, (inp, out, hit) in self.RETIRED_FAST.items():
            with self.subTest(model=model):
                self.assertEqual(self._row(model)["fast"], (inp, out))
                c = tm.price_record(model, usage(inp=100_000, read=100_000, out=100_000),
                                    speed="fast", when=OPENAI_READ_ON, provider="openai")
                self.assertAlmostEqual(c["cache_read"], hit / 10, places=9)

    def test_cache_writes_by_lifetime(self):
        """The ten-column tables print a 30-minute and a 12-hour cache write
        for the GPT-6, GPT-6.1, GPT-5.6, gpt-6-rosalind and gpt-5.6-cyber
        rows. The table
        holds the 30-minute write in its shorter write lifetime and the
        12-hour write in its longer one (the slot named for Anthropic's one
        hour). Guards against either write billed at the wrong multiple, or
        a 12-hour write charged as a 30-minute one."""
        for model, (w30, w12) in self.WRITES.items():
            with self.subTest(model=model):
                # 100K each, under the 272K line.
                c5 = tm.price_record(model, usage(w5=100_000), when=OPENAI_READ_ON, provider="openai")
                c1 = tm.price_record(model, usage(w1=100_000), when=OPENAI_READ_ON, provider="openai")
                self.assertAlmostEqual(c5["cache_write"], w30 / 10, places=9)
                self.assertAlmostEqual(c1["cache_write"], w12 / 10, places=9)
        for model, (w30, w12) in self.FAST_WRITES.items():
            with self.subTest(model=model, speed="fast"):
                c5 = tm.price_record(model, usage(w5=100_000), speed="fast",
                                     when=OPENAI_READ_ON, provider="openai")
                c1 = tm.price_record(model, usage(w1=100_000), speed="fast",
                                     when=OPENAI_READ_ON, provider="openai")
                self.assertAlmostEqual(c5["cache_write"], w30 / 10, places=9)
                self.assertAlmostEqual(c1["cache_write"], w12 / 10, places=9)

    def test_twelve_hour_cache_writes_from_20_october_2026(self):
        """The changelog, 20 October 2026: "You can now choose 12-hour prompt
        caching in the API ... 12-hour cache writes cost 2.5x the input token
        price." Before it the page had a single cache writes column: the
        copies of 12 August to 10 October 2026 (web.archive.org/web/20260812024913
        to 20261010170540, pricing.md) print gpt-5.6-cyber at $15.625, its
        30-minute rate. Guards against the 12-hour price missing on the day
        it began, or reaching a call the day before."""
        for model in ("gpt-6-astra", "gpt-6.1-sol", "gpt-6-sol", "gpt-6-luna",
                      "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-cyber"):
            w30, w12 = self.WRITES[model]
            for day, want in (("2026-10-19", w30), ("2026-10-20", w12)):
                with self.subTest(model=model, day=day):
                    c = tm.price_record(model, usage(w1=100_000), when=noon(day),
                                        provider="openai")
                    self.assertAlmostEqual(c["cache_write"], want / 10, places=9)

    def test_long_context_tier(self):
        """The page's footnote: "Short context: ≤272K input tokens. Long
        context: >272K input tokens." Each long figure as the page prints it, Standard and Fast,
        for a whole request over the line. The page does not say whether K is
        1,000 or 1,024, so the request under the line is 272,000 prompt
        tokens (short context on either reading) and the one over it is
        280,000 (long on either reading, above 272 x 1,024 = 278,528).
        Guards against a long tier missing, a wrong multiple, or the line
        counted on fresh input alone when cache reads and writes are prompt
        tokens too."""
        under = usage(inp=200_000, read=52_000, w5=10_000, w1=10_000, out=1_000_000)
        over = usage(inp=200_000, read=60_000, w5=10_000, w1=10_000, out=1_000_000)
        for speed, short, long, writes in (
                ("standard", self.OFFICIAL, self.LONG, self.WRITES),
                ("fast", self.FAST, self.FAST_LONG, self.FAST_WRITES)):
            for model, (l_in, l_out, l_hit, l_w30, l_w12) in long.items():
                with self.subTest(model=model, speed=speed):
                    s_in, s_out, s_hit = short[model]
                    c = tm.price_record(model, under, speed=speed, when=OPENAI_READ_ON, provider="openai")
                    self.assertAlmostEqual(c["input"], 0.2 * s_in, places=9)
                    self.assertAlmostEqual(c["cache_read"], 0.052 * s_hit, places=9)
                    self.assertAlmostEqual(c["output"], s_out, places=9)
                    if model in writes:
                        w30, w12 = writes[model]
                        self.assertAlmostEqual(c["cache_write"], 0.01 * (w30 + w12), places=9)
                    c = tm.price_record(model, over, speed=speed, when=OPENAI_READ_ON, provider="openai")
                    self.assertAlmostEqual(c["input"], 0.2 * l_in, places=9)
                    self.assertAlmostEqual(c["output"], l_out, places=9)
                    if l_hit is not None:
                        self.assertAlmostEqual(c["cache_read"], 0.06 * l_hit, places=9)
                    if l_w30 is not None:
                        self.assertAlmostEqual(c["cache_write"], 0.01 * (l_w30 + l_w12), places=9)

    def test_gpt_5_6_terra_and_luna_cut_on_30_july_2026(self):
        """The changelog, 30 July 2026: "Starting July 30, GPT-5.6 Luna costs
        80% less, while GPT-5.6 Terra costs 20% less." The 29 July 2026 copy
        (web.archive.org/web/20260729122800, pricing.md, sha256
        e643f692d1880a075471531586882fd6496d02d7422caf77275012b18c1199fa):
        Terra $2.50 in, $0.25 cached, $3.125 write, $15 out, Priority $5 and
        $30; Luna $1, $0.10, $1.25, $6, Priority $2 and $12. The 31 July 2026
        copy (web.archive.org/web/20260731081840, sha256
        2e8818bf672d681e711a9e8b63e950bd839f0477914104b83300e779438d48c3):
        Terra $2, $0.20, $2.50, $12, Fast $4 and $24; Luna $0.20, $0.02,
        $0.25, $1.20, Fast $0.40 and $2.40. Guards against July 2026 calls
        being priced at the cut rate, or later calls at the old one."""
        for model, before, after in (
                ("gpt-5.6-terra", (2.50, 15.00, 0.25, 3.125, (5.00, 30.00)),
                 (2.00, 12.00, 0.20, 2.50, (4.00, 24.00))),
                ("gpt-5.6-luna", (1.00, 6.00, 0.10, 1.25, (2.00, 12.00)),
                 (0.20, 1.20, 0.02, 0.25, (0.40, 2.40)))):
            for day, (inp, out, hit, w30, fast) in (("2026-07-29", before), ("2026-07-30", after)):
                with self.subTest(model=model, day=day):
                    row = self._row(model, noon(day))
                    self.assertAlmostEqual(row["in"], inp, places=9)
                    self.assertAlmostEqual(row["out"], out, places=9)
                    self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)
                    self.assertEqual(row["fast"], fast)
                    c = tm.price_record(model, usage(w5=100_000), when=noon(day), provider="openai")
                    self.assertAlmostEqual(c["cache_write"], w30 / 10, places=9)

    def test_gpt_5_6_sol_cut_on_21_august_2026(self):
        """The changelog, 21 August 2026: "GPT-5.6 Sol now costs $4 per
        million input tokens and $20 per million output tokens", promotional
        pricing "available at least through November 21, 2026" (no end date,
        so priced as the page charges now). The 12 August 2026 copy
        (web.archive.org/web/20260812024913, pricing.md, sha256
        4cb79c32d4e1d6d8d134494e95d94b3945ca7f35e3e982f0bc52ccdc6959017d):
        $5 in, $0.50 cached, $6.25 write, $30 out, Fast $10 and $60. The
        12 September 2026 copy (web.archive.org/web/20260912021448, sha256
        8a7113ac04dc17811de6901f715262719a866a324f041e3d44649f91f35a930c):
        $4, $0.40, $5, $20, Fast $8 and $40. Guards against calls before the
        cut being priced at the promotional rate."""
        for day, (inp, out, hit, w30, fast) in (
                ("2026-08-20", (5.00, 30.00, 0.50, 6.25, (10.00, 60.00))),
                ("2026-08-21", (4.00, 20.00, 0.40, 5.00, (8.00, 40.00)))):
            with self.subTest(day=day):
                row = self._row("gpt-5.6-sol", noon(day))
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)
                self.assertEqual(row["fast"], fast)
                c = tm.price_record("gpt-5.6-sol", usage(w5=100_000), when=noon(day),
                                    provider="openai")
                self.assertAlmostEqual(c["cache_write"], w30 / 10, places=9)

    def test_retired_models_and_their_shutdown_dates(self):
        """The deprecations page's shutdown date for each of the 37 retired
        ids. Guards against a retired model reported as current, a current
        one reported as retired, or a wrong date in the report's note that a
        retired model is kept at its last published price."""
        self.assertEqual(dict(tm.TABLES["openai"].RETIRED), self.RETIRED)
        self.assertLessEqual(set(self.RETIRED), set(self.OFFICIAL))

    def test_openai_cache_writes_are_billed_only_on_gpt6_and_gpt56(self):
        """1.25x input on GPT-6 and GPT-5.6; ordinary input on everything older."""
        for model, write in (("gpt-6-astra", 12.50), ("gpt-6.1-sol", 2.50), ("gpt-6-sol", 2.50), ("gpt-6-luna", 0.125),
                             ("gpt-5.6-sol", 5.00), ("gpt-5.6-terra", 2.50), ("gpt-5.6-luna", 0.25),
                             ("gpt-5", 1.25), ("gpt-5.4", 2.50)):
            with self.subTest(model=model):
                # 100K, under the 272K long-context line, which would double it.
                c = tm.price_record(model, usage(w5=100_000), provider="openai")
                self.assertAlmostEqual(c["cache_write"], write / 10, places=9)

    def test_openai_dated_snapshot_and_its_one_exception(self):
        """gpt-5-2025-08-07 is gpt-5; gpt-4o-2024-05-13 has its own, higher price."""
        self.assertEqual(tm.lookup("gpt-5-2025-08-07", provider="openai")[0]["in"], 1.25)
        self.assertEqual(tm.lookup("gpt-4o-2024-08-06", provider="openai")[0]["in"], 2.50)
        self.assertEqual(tm.lookup("gpt-4o-2024-05-13", provider="openai")[0]["in"], 5.00)


# Google (Gemini API) rates, typed from the maker's own pricing page by a
# third reader, so a slip in the table, in either earlier reading or here fails.
#
# Each figure was read off the page, or for a retired model off the Internet
# Archive's copy of the same page, on 27 October 2026, not copied from
# pricing/google.py. A rate change is a new dated row in the table and a new
# figure here; see pricing/README.md.

# The day the page was read. Lookups are made on this day, so a launch price
# that ends later (Gemini 4 Argon on 1 December 2026, the Flash models on
# 1 January 2027) stays pinned at what the page charged when it was read.
GOOGLE_READ_ON = noon("2026-10-27")


class TestGooglePublishedRates(Base):
    """Every rate in the Google table, typed from the page.

    Current models: read on 27 October 2026 at 17:58 UTC from
    https://ai.google.dev/gemini-api/docs/pricing (HTML, 253,876 bytes) and
    its markdown form pricing.md.txt (80,273 bytes, md5
    edbfca78dea0ed272447172cbc55889b), footer "Last updated 2026-10-27 UTC".
    Each model section has tier tabs (Standard, Batch, Flex, Priority and on
    some Contributor); the "Paid Tier, per 1M tokens in USD" column of the
    Standard tab is what OFFICIAL pins, and the Priority tab is what the
    table's `fast` holds. Batch, Flex and Contributor are not pinned.

    Retired models: the page no longer lists them, so each is read from the
    Internet Archive copy of the same page,
    https://web.archive.org/web/<timestamp>id_/https://ai.google.dev/gemini-api/docs/pricing,
    fetched 27 October 2026, at the timestamp noted beside it below.

    OFFICIAL is (Input price, Output price, Context caching price), dollars
    per million tokens, at prompts up to the long-context line where a model
    has one. Where the page splits input by modality, the text / image /
    video figure is pinned; the audio figure is not, because the table holds
    one input price. "Output price (including thinking tokens)" is one figure
    on every current model. A model whose section prints no caching price is
    listed with its input price: no discount. Storage per hour, grounding and
    the free tier are not pinned.
    """

    OFFICIAL = {
        # Current, from the live page.
        "gemini-4-argon": (2.00, 10.00, 0.10),
        "gemini-3.8-flash": (0.75, 3.75, 0.075),
        "gemini-3.6-flash": (0.75, 3.75, 0.075),
        "gemini-3.5-flash-lite": (0.30, 2.50, 0.03),
        "gemini-3.1-flash-lite": (0.25, 1.50, 0.025),
        "gemini-3.1-pro-preview": (2.00, 12.00, 0.20),
        "gemini-3-flash-preview": (0.50, 3.00, 0.05),
        "gemini-2.5-pro": (1.25, 10.00, 0.125),
        "gemini-2.5-flash": (0.30, 2.50, 0.03),
        "gemini-2.5-flash-lite": (0.10, 0.40, 0.01),
        # Retired, each from the archive copy named.
        "gemini-3.7-flash": (0.75, 3.75, 0.075),                 # 20261008045525
        "gemini-3.5-flash": (1.50, 9.00, 0.15),                  # 20261008045525
        # One table, no "Context caching price" row.
        "gemini-2.5-computer-use-preview-10-2025": (1.25, 10.00, 1.25),  # 20260727133516
        "gemini-2.0-flash": (0.10, 0.40, 0.025),                 # 20260531114408
        # "Context caching price: Not available".
        "gemini-2.0-flash-lite": (0.075, 0.30, 0.075),           # 20260531114408
        "gemini-3.1-flash-lite-preview": (0.25, 1.50, 0.025),    # 20260523192931
        "gemini-2.5-flash-lite-preview-09-2025": (0.10, 0.40, 0.01),  # 20260329190628
        "gemini-3-pro-preview": (2.00, 12.00, 0.20),             # 20260308060347
        "gemini-2.5-flash-preview-09-2025": (0.30, 2.50, 0.03),  # 20260216042333
        # The capture names it gemini-2.5-flash-lite-06-17.
        "gemini-2.5-flash-lite-preview-06-17": (0.10, 0.40, 0.025),   # 20250722012816
        # Output is printed "Non-thinking: $0.60" and "Thinking: $3.50"; the
        # table holds one output price and prices it at Thinking.
        "gemini-2.5-flash-preview-05-20": (0.15, 3.50, 0.0375),  # 20250616024644
        "gemini-2.5-flash-preview-04-17": (0.15, 3.50, 0.0375),  # 20250520002359
        "gemini-2.5-pro-preview-06-05": (1.25, 10.00, 0.31),     # 20250616024644
        "gemini-2.5-pro-preview-05-06": (1.25, 10.00, 0.31),     # 20250605100850
        "gemini-2.5-pro-preview-03-25": (1.25, 10.00, 0.31),     # 20250506015835
        "gemini-1.5-pro": (1.25, 5.00, 0.3125),                  # 20250926115107
        "gemini-1.5-flash": (0.075, 0.30, 0.01875),              # 20250926115107
        "gemini-1.5-flash-8b": (0.0375, 0.15, 0.01),             # 20250926115107
        # "Gemini 1.0 Pro - Deprecated"; caching "Not available".
        "gemini-1.0-pro": (0.50, 1.50, 0.50),                    # 20250211163751
    }

    # The Priority tab's (Input price, Output price), from the same page or
    # capture. None where the section has no Priority tab: Standard and Batch
    # only, or a single table.
    PRIORITY = {
        "gemini-4-argon": (3.60, 18.00),
        "gemini-3.8-flash": (1.35, 6.75),
        "gemini-3.6-flash": (1.35, 6.75),
        "gemini-3.5-flash-lite": (0.54, 4.50),
        "gemini-3.1-flash-lite": (0.45, 2.70),
        "gemini-3.1-pro-preview": (3.60, 21.60),
        "gemini-3-flash-preview": (0.90, 5.40),
        "gemini-2.5-pro": (2.25, 18.00),
        "gemini-2.5-flash": (0.54, 4.50),
        "gemini-2.5-flash-lite": (0.18, 0.72),
        "gemini-3.7-flash": (1.35, 6.75),
        "gemini-3.5-flash": (2.70, 16.20),
        "gemini-3.1-flash-lite-preview": (0.45, 2.70),
        "gemini-2.5-computer-use-preview-10-2025": None,
        "gemini-2.0-flash": None,
        "gemini-2.0-flash-lite": None,
        "gemini-2.5-flash-lite-preview-09-2025": None,
        "gemini-3-pro-preview": None,
        "gemini-2.5-flash-preview-09-2025": None,
        "gemini-2.5-flash-lite-preview-06-17": None,
        "gemini-2.5-flash-preview-05-20": None,
        "gemini-2.5-flash-preview-04-17": None,
        "gemini-2.5-pro-preview-06-05": None,
        "gemini-2.5-pro-preview-05-06": None,
        "gemini-2.5-pro-preview-03-25": None,
        "gemini-1.5-pro": None,
        "gemini-1.5-flash": None,
        "gemini-1.5-flash-8b": None,
        "gemini-1.0-pro": None,
    }

    # The Priority tab's "Context caching price", text / image / video.
    # One exception: Gemini 3.5 Flash-Lite's Priority tab prints "Context
    # caching price | $0.05" (27 October copy, and again on the page updated
    # 30 October 2026), which the engine cannot express. A Priority cache read
    # is Priority input times the row's cache multiple, 0.54 x 0.1 = $0.054,
    # the figure chosen for the table and stated in its docstring, so $0.054
    # is pinned here.
    PRIORITY_CACHE = {
        "gemini-4-argon": 0.18, "gemini-3.8-flash": 0.135, "gemini-3.6-flash": 0.135,
        "gemini-3.5-flash-lite": 0.054, "gemini-3.1-flash-lite": 0.045,
        "gemini-3.1-pro-preview": 0.36, "gemini-3-flash-preview": 0.09,
        "gemini-2.5-pro": 0.225, "gemini-2.5-flash": 0.054, "gemini-2.5-flash-lite": 0.018,
        "gemini-3.7-flash": 0.135, "gemini-3.5-flash": 0.27,
        "gemini-3.1-flash-lite-preview": 0.045,
    }

    # Standard tab, prompts over the line: (line in tokens, input, output,
    # caching). The page prints the line as "prompts <= 200k tokens" and
    # "prompts > 200k" (on the 1.5 series "128k"), read as 200,000 and
    # 128,000 tokens. No model has a second line.
    LONG = {
        "gemini-3.1-pro-preview": (200_000, 4.00, 18.00, 0.40),
        "gemini-2.5-pro": (200_000, 2.50, 15.00, 0.25),
        # No caching row, so a cache read is billed as input.
        "gemini-2.5-computer-use-preview-10-2025": (200_000, 2.50, 15.00, 2.50),
        "gemini-3-pro-preview": (200_000, 4.00, 18.00, 0.40),
        # The captures print "Context caching price | $0.31, prompts <= 200k
        # tokens ; $0.625, prompts > 200k" (20250616024644, 20250605100850,
        # 20250506015835). One cache multiple cannot give both; the table's
        # 0.248 keeps $0.31 exact, so over the line a cache read is
        # 2.50 x 0.248 = $0.62, the figure chosen for the table and stated in
        # its docstring, and $0.62 is pinned here.
        "gemini-2.5-pro-preview-06-05": (200_000, 2.50, 15.00, 0.62),
        "gemini-2.5-pro-preview-05-06": (200_000, 2.50, 15.00, 0.62),
        "gemini-2.5-pro-preview-03-25": (200_000, 2.50, 15.00, 0.62),
        "gemini-1.5-pro": (128_000, 2.50, 10.00, 0.625),
        "gemini-1.5-flash": (128_000, 0.15, 0.60, 0.0375),
        "gemini-1.5-flash-8b": (128_000, 0.075, 0.30, 0.02),
    }

    # Priority tab, prompts over 200k: (input, output, caching).
    PRIORITY_LONG = {
        "gemini-3.1-pro-preview": (7.20, 32.40, 0.72),
        "gemini-2.5-pro": (4.50, 27.00, 0.45),
    }

    # Launch prices with a published end: (first day of the new price,
    # Standard (input, output, caching), Priority (input, output, caching)).
    # Argon: "$2.00 through November 30, 2026. $4.00 starting December 1,
    # 2026." The Flash models: "through December 31, 2026" and "starting
    # January 1, 2027"; 3.7 Flash from capture 20261008045525.
    DATED = {
        "gemini-4-argon": ("2026-12-01", (4.00, 20.00, 0.20), (7.20, 36.00, 0.36)),
        "gemini-3.8-flash": ("2027-01-01", (1.50, 7.50, 0.15), (2.70, 13.50, 0.27)),
        "gemini-3.7-flash": ("2027-01-01", (1.50, 7.50, 0.15), (2.70, 13.50, 0.27)),
        "gemini-3.6-flash": ("2027-01-01", (1.50, 7.50, 0.15), (2.70, 13.50, 0.27)),
    }
    DAY_BEFORE = {"2026-12-01": "2026-11-30", "2027-01-01": "2026-12-31"}

    def price(self, model, u, when=GOOGLE_READ_ON, speed="standard"):
        c = tm.price_record(model, u, speed, when=when, provider="google")
        self.assertFalse(c["_unknown_model"], f"{model} is not in the google table")
        return c

    def test_every_rate_matches_the_pricing_page(self):
        """Guards against a Gemini rate typed wrongly into pricing/google.py,
        a model on the page or in the archive missing from the table, or a
        table row no reading accounts for: the table must hold exactly these
        29 ids, each at the Standard tab's input, output and caching price on
        the day the page was read."""
        self.assertEqual(set(tm.TABLES["google"].PRICES), set(self.OFFICIAL),
                         "google table and the page's model list differ")
        self.assertEqual(set(self.PRIORITY), set(self.OFFICIAL))
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model, when=GOOGLE_READ_ON, provider="google")
                self.assertTrue(known)
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_priority_tier_rates(self):
        """Guards the Priority tab's input and output prices, held as `fast`:
        a call recorded as fast is billed at these, and a model whose section
        has no Priority tab has no fast price at all, so it is never billed
        at a rate the page does not print."""
        for model, fast in self.PRIORITY.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model, when=GOOGLE_READ_ON, provider="google")
                self.assertTrue(known)
                if fast is None:
                    self.assertIsNone(row["fast"])
                else:
                    self.assertIsNotNone(row["fast"])
                    self.assertAlmostEqual(row["fast"][0], fast[0], places=9)
                    self.assertAlmostEqual(row["fast"][1], fast[1], places=9)

    def test_priority_tier_cache_reads(self):
        """Guards the Priority tab's "Context caching price": cached tokens on
        a call recorded as fast cost the figure the page prints. 100,000
        tokens keeps the prompt under every long-context line. Gemini 3.5
        Flash-Lite's page figure is $0.05, which no cache multiple of its
        Priority input of $0.54 gives; the engine's $0.054, the table's
        documented choice, is pinned instead, so a change to that choice
        fails here."""
        for model, hit in self.PRIORITY_CACHE.items():
            with self.subTest(model=model):
                c = self.price(model, usage(read=100_000), speed="fast")
                self.assertAlmostEqual(c["cache_read"], 100_000 * hit / M, places=12)

    def test_long_context_tier(self):
        """Guards the "prompts > 200k tokens" (1.5 series: 128k) tier: a
        prompt of exactly the line is billed at the lower input and output
        prices, one token more at the higher ones for the whole request, and
        the prompt counts cache reads too. A model the page prints one price
        for has no tier at all."""
        for model, (over, inp, out, _) in self.LONG.items():
            base_in, base_out, _ = self.OFFICIAL[model]
            for prompt, rate_in, rate_out in ((over, base_in, base_out), (over + 1, inp, out)):
                with self.subTest(model=model, prompt=prompt):
                    c = self.price(model, usage(inp=prompt, out=M))
                    self.assertAlmostEqual(c["input"], prompt * rate_in / M, places=12)
                    self.assertAlmostEqual(c["output"], rate_out, places=9)
            with self.subTest(model=model, crossed_by="cache reads"):
                c = self.price(model, usage(inp=1, read=over, out=M))
                self.assertAlmostEqual(c["output"], out, places=9)
        for model in set(self.OFFICIAL) - set(self.LONG):
            with self.subTest(model=model, tier="none"):
                row, _ = tm.lookup(model, when=GOOGLE_READ_ON, provider="google")
                self.assertFalse(row.get("long"), f"{model} has a tier the page does not print")

    def test_long_context_cache_reads(self):
        """Guards the caching price on each side of the long-context line.
        For the 2.5 Pro Previews the page prints $0.31 up to 200k and $0.625
        over it, which one cache multiple cannot give; over the line the
        table's documented $0.62 (2.50 x 0.248) is pinned, so a change to
        that choice fails here."""
        for model, (over, _, _, long_hit) in self.LONG.items():
            hit = self.OFFICIAL[model][2]
            for read, rate in ((over - 1, hit), (over, long_hit)):
                with self.subTest(model=model, prompt=read + 1):
                    c = self.price(model, usage(inp=1, read=read))
                    self.assertAlmostEqual(c["cache_read"], read * rate / M, places=12)

    def test_priority_long_context_tier(self):
        """Guards the Priority tab's "prompts > 200k" prices on the two
        models that have both: a fast call over the line is billed at the
        Priority long-context input, output and caching prices."""
        for model, (inp, out, hit) in self.PRIORITY_LONG.items():
            with self.subTest(model=model):
                c = self.price(model, usage(inp=200_001, read=M, out=M), speed="fast")
                self.assertAlmostEqual(c["input"], 200_001 * inp / M, places=12)
                self.assertAlmostEqual(c["cache_read"], hit, places=9)
                self.assertAlmostEqual(c["output"], out, places=9)

    def test_launch_prices_end_on_the_published_date(self):
        """Guards the dated price changes the page prints: Gemini 4 Argon
        doubles on 1 December 2026 and 3.8, 3.7 and 3.6 Flash double on
        1 January 2027, on Standard and Priority alike. A call keeps the
        price of its own day, so the last launch day and the first new day
        are each pinned."""
        for model, (day, (inp, out, hit), (f_in, f_out, f_hit)) in self.DATED.items():
            b_in, b_out, b_hit = self.OFFICIAL[model]
            bf_in, bf_out = self.PRIORITY[model]
            bf_hit = self.PRIORITY_CACHE[model]
            for when, std, pri in ((self.DAY_BEFORE[day], (b_in, b_out, b_hit), (bf_in, bf_out, bf_hit)),
                                   (day, (inp, out, hit), (f_in, f_out, f_hit))):
                with self.subTest(model=model, day=when):
                    u = usage(inp=M, read=M, out=M)
                    c = self.price(model, u, when=noon(when))
                    self.assertAlmostEqual(c["input"], std[0], places=9)
                    self.assertAlmostEqual(c["output"], std[1], places=9)
                    self.assertAlmostEqual(c["cache_read"], std[2], places=9)
                    f = self.price(model, u, when=noon(when), speed="fast")
                    self.assertAlmostEqual(f["input"], pri[0], places=9)
                    self.assertAlmostEqual(f["output"], pri[1], places=9)
                    self.assertAlmostEqual(f["cache_read"], pri[2], places=9)

    def test_custom_tools_variant_is_priced_as_3_1_pro_preview(self):
        """Guards the page's one section for two ids: "gemini-3.1-pro-preview
        and gemini-3.1-pro-preview-customtools" share one price table, so a
        call under the second id is recognised and billed as the first."""
        row, known = tm.lookup("gemini-3.1-pro-preview-customtools", when=GOOGLE_READ_ON,
                               provider="google")
        self.assertTrue(known)
        self.assertEqual(row, tm.lookup("gemini-3.1-pro-preview", when=GOOGLE_READ_ON,
                                        provider="google")[0])

    def test_gemini_flash_prices_change_on_new_year(self):
        """Launch price through 31 December 2026, list price from 1 January 2027."""
        before, after = noon("2026-12-31"), noon("2027-01-02")
        for model in ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"):
            with self.subTest(model=model):
                self.assertEqual(tm.lookup(model, before, "google")[0]["in"], 0.75)
                self.assertEqual(tm.lookup(model, after, "google")[0]["in"], 1.50)
                self.assertEqual(tm.lookup(model, after, "google")[0]["out"], 7.50)

    def test_gemini_4_argon_doubles_on_1_december(self):
        """Read off ai.google.dev/gemini-api/docs/pricing on 16 October 2026:
        $2.00 in and $10.00 out through 30 November 2026, $4.00 and $20.00
        from 1 December 2026, context caching $0.10 then $0.20 (0.05x input,
        not the 0.1x every other Gemini model charges), no long-context tier.
        The model was on the page from 13 October and the table lacked it,
        so its calls were priced by the online lookup, and flagged as such,
        and the page reader did not name it as missing."""
        before, after = noon("2026-11-30"), noon("2026-12-01")
        row, known = tm.lookup("gemini-4-argon", before, "google")
        self.assertTrue(known)
        self.assertEqual((row["in"], row["out"]), (2.00, 10.00))
        self.assertAlmostEqual(row["in"] * row["cache_read_mult"], 0.10, places=9)
        self.assertNotIn("long", row)
        row, known = tm.lookup("gemini-4-argon", after, "google")
        self.assertEqual((row["in"], row["out"]), (4.00, 20.00))
        self.assertAlmostEqual(row["in"] * row["cache_read_mult"], 0.20, places=9)
        c = tm.price_record("gemini-4-argon", usage(inp=1_000_000, read=1_000_000, out=100_000),
                            when=before, provider="google")
        self.assertAlmostEqual(cost_of(c), 2.00 + 0.10 + 1.00, places=9)
        self.assertFalse(c["_unknown_model"])

    def test_gemini_flash_models_retired_on_8_october_2026_keep_their_price(self):
        """The Gemini API changelog, 8 October 2026: gemini-3.5-flash and
        gemini-3.7-flash are deprecated and their requests routed to newer
        models, and the pricing page no longer lists them. Older usage keeps
        the last published price: $1.50 and $9 for 3.5 Flash, $0.75 and $3.75
        for 3.7 Flash through 31 December 2026."""
        retired = tm.TABLES["google"].RETIRED
        when = dt.datetime(2026, 10, 1, 12, tzinfo=dt.timezone.utc)
        for model, (inp, out) in (("gemini-3.5-flash", (1.50, 9.00)),
                                  ("gemini-3.7-flash", (0.75, 3.75))):
            with self.subTest(model=model):
                self.assertEqual(retired[model], "2026-10-08")
                row, known = tm.lookup(model, when, "google")
                self.assertTrue(known)
                self.assertEqual((row["in"], row["out"]), (inp, out))


class TestXaiPublishedRates(Base):
    """Every rate in the xAI table, typed from docs.x.ai/developers/pricing
    on 26 September 2026, separately from the table, so a slip in either one
    fails. A retired model keeps its last published rate.
    """

    XAI = {
        "grok-4.7": (2, 6, 0.50), "grok-4.6": (2, 6, 0.50), "grok-4.5": (2, 6, 0.30),
        "grok-4.3": (1.25, 2.50, 0.20), "grok-4.20-0309-reasoning": (1.25, 2.50, 0.20),
        "grok-4.20-0309-non-reasoning": (1.25, 2.50, 0.20),
        "grok-4.20-multi-agent-0309": (1.25, 2.50, 0.20), "grok-build-0.1": (1, 2, 0.20),
    }

    def test_xai(self):
        table = tm.TABLES["xai"].PRICES
        self.assertEqual(set(table), set(self.XAI), "xai table and pinned list differ")
        for model, (inp, out, hit) in self.XAI.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model, provider="xai")
                self.assertTrue(known)
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_xai_aliases_are_the_same_model(self):
        for alias, canonical in (("grok-code-fast-1", "grok-build-0.1"),
                                 ("grok-4.20", "grok-4.20-0309-reasoning"),
                                 ("grok-4.5-latest", "grok-4.5")):
            with self.subTest(alias=alias):
                row, known = tm.lookup(alias, provider="xai")
                self.assertTrue(known)
                self.assertIs(row, tm.TABLES["xai"].PRICES[canonical][0])


class TestSmallerProvidersPublishedRates(Base):
    """DeepSeek and Mistral, typed from their pages on 26 September 2026.
    (input, output, cached), standard or peak rates. Mistral Large 4 added
    from Mistral's page as saved on 2 November 2026, as its second reading
    prints it in TestMistralLarge4PublishedRates below. Moonshot and Z.ai
    have their own classes below."""

    OFFICIAL = {
        "deepseek": {"deepseek-flash": (0.30, 1.20, 0.006), "deepseek-v4-pro": (1.32, 3.96, 0.044)},
        "mistral": {"mistral-large-2512": (0.5, 1.5, 0.05), "mistral-medium-3-5": (1.5, 7.5, 0.15),
                    "mistral-small-2603": (0.15, 0.6, 0.015), "ministral-14b-2512": (0.2, 0.2, 0.02),
                    "ministral-8b-2512": (0.15, 0.15, 0.015), "ministral-3b-2512": (0.1, 0.1, 0.01),
                    "codestral-2508": (0.3, 0.9, 0.03), "zai-glm-5-3": (1.4, 4.4, 0.14),
                    "zai-glm-5-2": (1.4, 4.4, 0.14), "mistral-large-4": (0.7, 2.1, 0.07)},
    }

    def test_every_rate(self):
        for provider, official in self.OFFICIAL.items():
            self.assertEqual(set(tm.TABLES[provider].PRICES), set(official), provider)
            for model, (inp, out, hit) in official.items():
                with self.subTest(provider=provider, model=model):
                    row, known = tm.lookup(model, provider=provider)
                    self.assertTrue(known)
                    self.assertAlmostEqual(row["in"], inp, places=9)
                    self.assertAlmostEqual(row["out"], out, places=9)
                    self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_deepseek_is_half_price_outside_peak_hours(self):
        """Peak is 01:00 to 04:00 and 06:00 to 10:00 UTC, Monday to Friday."""
        u = usage(inp=1_000_000, out=1_000_000, read=1_000_000)
        cases = [(dt.datetime(2026, 9, 21, 2, 30, tzinfo=dt.timezone.utc), 1.0),   # Monday, peak
                 (dt.datetime(2026, 9, 21, 4, 0, tzinfo=dt.timezone.utc), 0.5),    # Monday, gap
                 (dt.datetime(2026, 9, 21, 9, 59, tzinfo=dt.timezone.utc), 1.0),   # Monday, peak
                 (dt.datetime(2026, 9, 21, 10, 0, tzinfo=dt.timezone.utc), 0.5),   # Monday, after
                 (dt.datetime(2026, 9, 26, 2, 30, tzinfo=dt.timezone.utc), 0.5)]   # Saturday
        peak = cost_of(tm.price_record("deepseek-flash", u, provider="deepseek"))
        self.assertAlmostEqual(peak, 0.30 + 1.20 + 0.006, places=9)
        for when, factor in cases:
            with self.subTest(when=when):
                c = tm.price_record("deepseek-flash", u, when=when, provider="deepseek")
                self.assertAlmostEqual(cost_of(c), peak * factor, places=9)


# DeepSeek's web search rate and the instant it starts, typed from the
# maker's own pricing page, not copied from pricing/deepseek.py, so a slip in
# the table fails here.
#
# A rate change is a new dated entry in WEB_SEARCH_RATES and a new figure here;
# see pricing/README.md.


class TestDeepSeekPublishedSearchRate(Base):
    """Read on 2 November 2026 from
    https://api-docs.deepseek.com/quick_start/pricing (saved as
    pages/deepseek_2026-11-02.html, and fetched again the same day with the
    same sha256). Its "Search & Fetch Pricing" table reads "Search | Per
    1,000 successful requests | $0.75", and its note says that for DeepSeek
    Harness, Claude Code and Codex, whose server-side tool calls use that
    API, "per-request billing starts at 00:00 Beijing time on November 1,
    2026". Beijing time is UTC+8, so the start is 16:00 UTC on 31 October
    2026; before it the searches were free."""

    PER_1K = 0.75
    STARTS = dt.datetime(2026, 11, 1, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=8)))

    def test_the_search_rate_and_its_start_match_the_page(self):
        """Guards the $0.75 per 1,000 figure, the free period before it, and
        the start instant against the page."""
        table = tm.TABLES["deepseek"]
        self.assertEqual(table.WEB_SEARCH_PER_1K, self.PER_1K)
        self.assertEqual(table.WEB_SEARCH_RATES[0], {"from": "", "per_1k": 0.0})
        self.assertEqual(len(table.WEB_SEARCH_RATES), 2)
        newest = table.WEB_SEARCH_RATES[-1]
        self.assertEqual(newest["per_1k"], self.PER_1K)
        self.assertEqual(tm.parse_time(newest["from"]), self.STARTS)
        self.assertEqual(self.STARTS, dt.datetime(2026, 10, 31, 16, 0, tzinfo=UTC))

    def test_a_thousand_searches_cost_what_the_page_says(self):
        """Guards the charge itself: a thousand searches in one call just
        before the start cost nothing, and from the start cost $0.75."""
        def cost(when):
            return tm.price_record("deepseek-v4-pro", usage(inp=1, searches=1000),
                                   when=when, provider="deepseek")["web_search"]
        self.assertEqual(cost(self.STARTS - dt.timedelta(microseconds=1)), 0.0)
        self.assertAlmostEqual(cost(self.STARTS), self.PER_1K, places=12)


# Mistral Large 4 rates, typed by hand from Mistral's own pricing page as
# the second reading, so a slip in the table or in the other reading fails.
#
# Each figure was read off the saved page on 2 November 2026, not copied from
# pricing/mistral.py. A rate change is a new dated row in the table and a new
# figure here; see pricing/README.md.

MISTRAL_READ_ON = noon("2026-11-02")


class TestMistralLarge4PublishedRates(Base):
    """Mistral Large 4, typed from https://docs.mistral.ai/inference/pricing
    as saved on 2 November 2026 (mistral_2026-11-02.html, 622,962 bytes, in
    the run's checkpoint pages folder, outside the repository), with the
    Standard and USD buttons pressed, which is how the page loads.

    The "Generalist models" table prints Mistral Large 4 at Input $0.7,
    Cached input $0.07 and Output $2.1, under "Prices /M Tokens". Its model
    card, https://docs.mistral.ai/models/mistral-large-4-0 (saved the same
    day as mistral_2026-11-02_card_large4.html), prints the same three
    figures in USD and names the model "mistral-large-4" with one more name,
    "mistral-large-4-0". The lifecycle policy page calls model-name-major an
    alias for the latest minor version and model-name-major-minor the fixed
    version, so both ids are pinned at the same price.

    Neither page prints a prompt-length tier, although the card gives a 1M
    context, so a long prompt is pinned at the same rate.

    Launch price. The changelog (saved as mistral_2026-11-02_changelogs.html)
    says, under October 6 of 2026, that Large 4 "is now available in Public
    Preview" and "Launch pricing: 50% off for 2 weeks." The changelog prints
    no figures, but the pricing page did: Internet Archive copies of it
    print "Sale price" $0.68 in, $0.07 cached, $2.09 out against "Original
    price" $1.36, $0.14, $4.18 (11 and 17 October 2026), then $1.36, $0.14,
    $4.18 alone (21 and 29 October 2026), then $0.7, $0.07, $2.1 (1 November
    2026). Archive prices are taken only for a retired model, and neither
    boundary is printed to the day, so no dated row is pinned here: the row
    is the price the live page prints on 2 November 2026, and whether to add
    the archived prices as dated rows is an open question.
    """

    OFFICIAL = {
        # (Input, Output, Cached input), dollars per million tokens.
        "mistral-large-4": (0.7, 2.1, 0.07),
        "mistral-large-4-0": (0.7, 2.1, 0.07),
    }

    def test_every_rate(self):
        """Guards a Large 4 rate that differs from the page, or a Large 4 id
        the page names that the table does not recognise and so prices at
        the fallback."""
        for model, (inp, out, hit) in self.OFFICIAL.items():
            for when in (None, MISTRAL_READ_ON):
                with self.subTest(model=model, when=when):
                    row, known = tm.lookup(model, when=when, provider="mistral")
                    self.assertTrue(known)
                    self.assertAlmostEqual(row["in"], inp, places=9)
                    self.assertAlmostEqual(row["out"], out, places=9)
                    self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_one_call_on_the_day_the_page_was_read(self):
        """Guards the sum: a million each of input, output and cache reads on
        2 November 2026 costs 0.7 + 2.1 + 0.07 dollars, whichever id is
        logged."""
        u = usage(inp=1_000_000, out=1_000_000, read=1_000_000)
        for model in self.OFFICIAL:
            with self.subTest(model=model):
                c = tm.price_record(model, u, when=MISTRAL_READ_ON, provider="mistral")
                self.assertAlmostEqual(cost_of(c), 0.7 + 2.1 + 0.07, places=9)

    def test_no_long_prompt_surcharge(self):
        """Guards a long-context rate applied to Large 4 when the page prints
        one input and one output rate for its whole 1M context: a 900,000
        token prompt costs 900,000 tokens at $0.7 per million."""
        u = usage(inp=900_000, out=10_000)
        c = tm.price_record("mistral-large-4", u, when=MISTRAL_READ_ON, provider="mistral")
        self.assertAlmostEqual(cost_of(c), 0.9 * 0.7 + 0.01 * 2.1, places=9)


# Moonshot (Kimi) rates, typed from the maker's own pricing page by a third
# reader, so a slip in the table, in either earlier reading or here fails.
#
# Each figure was read off the page on 27 October 2026, not copied from
# pricing/moonshot.py. A rate change is a new dated row in the table and a new
# figure here; see pricing/README.md.

class TestMoonshotPublishedRates(Base):
    """Every rate in the Moonshot table, typed from the page.

    Read on 27 October 2026 at 17:28 UTC from
    https://platform.kimi.ai/docs/pricing/chat (platform.moonshot.ai redirects
    there), the international page in US dollars per million tokens ("1 MTok =
    1,000,000 tokens"). The figures sit in the page's two tables, "K3 Series
    Models" and "K2 Series Models", inside the HTML's Next.js payload (301,716
    bytes, md5 9b2795ca9a1c631279a7a98ac2b3bef6, the same copy as at 12:20 UTC).

    OFFICIAL is (Input, Output, Cached Input). kimi-k3.1-pro-highspeed's
    Cached Input is $0.20, the same as kimi-k3.1-pro's, while its other four
    figures are twice kimi-k3.1-pro's: that is what the page prints, so it is
    pinned as printed. The page prints one price per model, with no thinking
    and non-thinking split, no prompt-length tier, no time-of-day rate and no
    dated rate change. Its only date is the notice that the K2 series closes to
    newly registered users on 31 October 2026 and is to be retired by the end
    of December 2026; existing users keep the same rates, so no figure moves.
    """

    OFFICIAL = {
        "kimi-k3.1-pro": (2.00, 10.00, 0.20),
        "kimi-k3.1-pro-highspeed": (4.00, 20.00, 0.20),
        "kimi-k3": (3.00, 15.00, 0.30),
        "kimi-k2.7-code": (0.95, 4.00, 0.19),
        "kimi-k2.7-code-highspeed": (1.90, 8.00, 0.38),
        "kimi-k2.6": (0.95, 4.00, 0.16),
    }
    # The K3 series table's "Prompt caching" columns "5m writes" and
    # "1h writes", dollars per million. The K2 series table has no write column.
    CACHE_WRITES = {
        "kimi-k3.1-pro": (2.00, 4.00),
        "kimi-k3.1-pro-highspeed": (4.00, 8.00),
        "kimi-k3": (3.00, 6.00),
    }
    # "All K3 series models support a 1,048,576-token context window."
    # "All K2 series models support a 262,144-token context window."
    WINDOW = {"kimi-k3.1-pro": 1_048_576, "kimi-k3.1-pro-highspeed": 1_048_576,
              "kimi-k3": 1_048_576, "kimi-k2.7-code": 262_144,
              "kimi-k2.7-code-highspeed": 262_144, "kimi-k2.6": 262_144}

    def test_every_rate_matches_the_pricing_page(self):
        """Guards against a Moonshot rate typed wrongly into pricing/moonshot.py,
        a model on the page missing from the table, or a table row the page
        does not list: the table must hold exactly the page's six ids, each at
        the page's Input, Output and Cached Input."""
        self.assertEqual(set(tm.TABLES["moonshot"].PRICES), set(self.OFFICIAL),
                         "moonshot table and the page's model list differ")
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model, provider="moonshot")
                self.assertTrue(known)
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_k3_series_bills_cache_writes_by_ttl(self):
        """Guards the page's rule that "for K3 series models, cache writes are
        billed separately by TTL (5min / 1h)": a 5 minute write and a 1 hour
        write on each K3 series id cost the page's "5m writes" and "1h writes"
        figures, not the input rate for both."""
        for model, (w5, w1) in self.CACHE_WRITES.items():
            with self.subTest(model=model):
                c5 = tm.price_record(model, usage(w5=1_000_000), provider="moonshot")
                self.assertAlmostEqual(c5["cache_write"], w5, places=9)
                c1 = tm.price_record(model, usage(w1=1_000_000), provider="moonshot")
                self.assertAlmostEqual(c1["cache_write"], w1, places=9)

    def test_one_flat_price_up_to_the_whole_context_window(self):
        """Guards against a prompt-length tier the page does not have: the page
        prints one price per model and states only each series' context
        window, so a prompt that fills the window costs the same per token as a
        short one."""
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                n = self.WINDOW[model]
                short = tm.price_record(model, usage(inp=1_000, out=1_000), provider="moonshot")
                full = tm.price_record(model, usage(inp=n, out=1_000), provider="moonshot")
                self.assertAlmostEqual(short["input"], inp * 1_000 / 1e6, places=12)
                self.assertAlmostEqual(full["input"], inp * n / 1e6, places=9)
                self.assertAlmostEqual(full["output"], out * 1_000 / 1e6, places=12)
                self.assertAlmostEqual(cost_of(full) - full["input"], cost_of(short) - short["input"],
                                       places=12)

    def test_kimi_k3_bills_cache_writes_by_lifetime(self):
        c = tm.price_record("kimi-k3", usage(w5=100_000, w1=100_000), provider="moonshot")
        self.assertAlmostEqual(c["cache_write"], 0.1 * 3.00 + 0.1 * 6.00, places=9)
        k2 = tm.price_record("kimi-k2.6", usage(w5=100_000), provider="moonshot")
        self.assertAlmostEqual(k2["cache_write"], 0.1 * 0.95, places=9)


# Z.ai (GLM) rates, typed from the maker's own pricing page by a third
# reader, so a slip in the table, in either earlier reading or here fails.
#
# Each figure was read off the page on 27 October 2026, not copied from
# pricing/zai.py. A rate change is a new dated row in the table and a new
# figure here; see pricing/README.md.


class TestZaiPublishedRates(Base):
    """Every rate in the Z.ai table, typed from the page.

    Read on 27 October 2026 at 17:33 UTC from
    https://docs.z.ai/guides/overview/pricing.md (the markdown form, 3,010
    bytes) and checked cell by cell against the HTML form at
    https://docs.z.ai/guides/overview/pricing (161,623 bytes), which prints
    the same figures. The page says "All prices are in USD." and "Prices per
    1M tokens." over each text table, and its HTML records that it was last
    changed on 21 October 2026.

    The text models sit in three tables: "Latest Models", "Text Models", and
    a second "Text Models" inside the "Other Pricing" section further down.
    The API id is the page's model name in lower case. OFFICIAL is (Input,
    Output, Cached Input) in dollars per million tokens. GLM-4-32B-0414-128K
    prints "-" for Cached Input, so, as in the other pinned classes, it is
    listed with its input rate: no discount. GLM-4.7-Flash and GLM-4.5-Flash
    print "Free" in every column.

    The page prints one Input, one Cached Input and one Output figure per
    model: no prompt-length tier, no time-of-day rate, no fast tier, no
    thinking and non-thinking split, no cache-write rate and no dated rate
    change. "Cached Input Storage" reads "Limited-time Free" with no dates, so
    it is priced as the page charges now, which is nothing. The one per-call
    figure is the "Built-in Tools" table's Web Search, "$0.01 / use". No GLM
    text model has left the page, so nothing here comes from an archive copy.
    """

    OFFICIAL = {
        # Latest Models
        "glm-5.3": (1.4, 4.4, 0.26),
        "glm-5.3-flash": (0.15, 0.50, 0.03),
        "glm-5.3-flashx": (0.37, 1.25, 0.075),
        # Text Models
        "glm-5.3-flashx-legal": (0.37, 1.25, 0.075),
        "glm-5.2": (1.4, 4.4, 0.26),
        "glm-5.1": (1.4, 4.4, 0.26),
        "glm-5": (1, 3.2, 0.2),
        "glm-4.7": (0.6, 2.2, 0.11),
        "glm-4.6": (0.6, 2.2, 0.11),
        # Other Pricing, Text Models
        "glm-4.7-flashx": (0.07, 0.4, 0.01),
        "glm-4.5": (0.6, 2.2, 0.11),
        "glm-4.5-x": (2.2, 8.9, 0.45),
        "glm-4.5-air": (0.2, 1.1, 0.03),
        "glm-4.5-airx": (1.1, 4.5, 0.22),
        "glm-4-32b-0414-128k": (0.1, 0.1, 0.1),
        "glm-4.7-flash": (0, 0, 0),
        "glm-4.5-flash": (0, 0, 0),
    }

    def test_every_rate_matches_the_pricing_page(self):
        """Guards a mistyped Z.ai rate, a model the table dropped, and a model
        it carries that the page does not price. The eight "Other Pricing"
        models sit in a collapsed section the page reader once could not see;
        they are listed here so the table cannot lose them quietly."""
        self.assertEqual(set(tm.TABLES["zai"].PRICES), set(self.OFFICIAL),
                         "zai table and pinned list differ")
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model, provider="zai")
                self.assertTrue(known, f"{model} falls back to another model's rates")
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_one_price_whatever_the_prompt_length_hour_or_speed(self):
        """Guards a long-context tier, an off-peak discount or a fast tier
        creeping into the Z.ai table. The API page prints one flat price per
        model; the GLM Coding Plan's off-peak credit rule is a subscription
        rule, not an API rate, and must not change what a call costs."""
        u = usage(inp=900_000, out=M, read=900_000)
        weekday_peak = dt.datetime(2026, 10, 27, 7, 0, tzinfo=dt.timezone.utc)
        night = dt.datetime(2026, 10, 27, 20, 0, tzinfo=dt.timezone.utc)
        saturday = dt.datetime(2026, 10, 31, 3, 0, tzinfo=dt.timezone.utc)
        for model, (inp, out, hit) in self.OFFICIAL.items():
            flat = 0.9 * inp + out + 0.9 * hit
            for when in (None, weekday_peak, night, saturday):
                for speed in ("standard", "fast"):
                    with self.subTest(model=model, when=when, speed=speed):
                        c = tm.price_record(model, u, speed=speed, when=when, provider="zai")
                        self.assertAlmostEqual(cost_of(c), flat, places=9)

    def test_a_cache_write_costs_the_input_price(self):
        """Guards a cache-write surcharge on Z.ai. The page prints no
        cache-write rate and its "Cached Input Storage" is "Limited-time
        Free", so a write of either lifetime is billed as ordinary input."""
        for model, (inp, _out, _hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                c = tm.price_record(model, usage(w5=100_000, w1=100_000), provider="zai")
                self.assertAlmostEqual(c["cache_write"], 0.2 * inp, places=9)

    def test_web_search_is_one_cent_per_use(self):
        """Guards Z.ai web searches being billed at nothing, or at another
        maker's rate. The "Built-in Tools" table prints Web Search at
        "$0.01 / use", which is $10 per 1,000."""
        self.assertAlmostEqual(tm.TABLES["zai"].WEB_SEARCH_PER_1K, 10.0, places=9)
        c = tm.price_record("glm-5.3", usage(searches=3), provider="zai")
        self.assertAlmostEqual(c["web_search"], 0.03, places=9)


# MiniMax rates, typed by hand from the maker's own pricing page by a reader
# who has not seen the table, so a slip in either one fails.
#
# Each figure was read off the saved page on 2 November 2026, not copied from
# pricing/minimax.py. A rate change is a new dated row in the table and a new
# figure here; see pricing/README.md.

# The day the page was read. The row checked is the one in force on it: the
# last row whose "from" is "" or on or before this day.
MINIMAX_READ_ON = "2026-11-02"


def in_force(rows, day=MINIMAX_READ_ON):
    """The last row whose "from" is empty or on or before `day`."""
    chosen = None
    for r in rows:
        if not r["from"] or r["from"] <= day:
            chosen = r
    return chosen


class TestMiniMaxPublishedRates(Base):
    """Every rate in the MiniMax table, typed from the page.

    Read on 2 November 2026 from https://platform.minimax.io/docs/pricing/overview,
    the international page in US dollars per million tokens, saved as its
    markdown form (the same URL with ".md") in
    minimax_pricing-overview_2026-11-02.md, fetched at 17:30:52 UTC, sha256
    730417be1e730b04c27aa6936bf87c8d81d7958b4a8a8e0d9a8f067954fbab19. The
    figures are the section "LLM". The ids are the API's own, as the page
    prints them and as https://platform.minimax.io/docs/faq/models lists them
    under "Available Models" (saved as minimax_model-list_2026-11-02.md).

    OFFICIAL is (Input, Output, Prompt caching Read). Only two text models are
    priced per token: MiniMax-M3.1-Flash and MiniMax-M3. The model list's
    table marks every older text model (the M2.7, M2.5, M2.1 and M2 series and
    M2-her) as retired, though a notice on the same page lets existing users
    call the M2.5 and M2.7 models until 18 November 2026. None has a price on
    the page, so none is pinned here.

    Which figures the row carries, by the brief's rule for what the engine
    cannot express yet:

    - Prompt length. MiniMax-M3 has one threshold, "<= 512k input tokens" and
      "> 512k input tokens", every figure exactly double above it, so it fits
      the engine's single "long" rule with no approximation. The page does not
      say whether 512k is 512,000 or 524,288 tokens; this reading takes
      512,000, as the engine reads OpenAI's "272K", and that choice is
      unverified against MiniMax. MiniMax-M3.1-Flash has one row, no tier.
    - Discount. Every MiniMax-M3 row reads "Permanent 50% off" with the list
      price struck through. It has no end date, so it is priced as the page
      charges now: the second, charged figure, never the struck one.
    - Priority. A "Priority" tab, "Set service_tier to priority to enable it.
      Pricing is 1.5x standard.", prints MiniMax-M3 only, so its figures are
      the row's "fast" and MiniMax-M3.1-Flash has none.
    - Thinking. The page prints one price per model, with no thinking and
      non-thinking split, so the price is the same whatever the log records.
    - Cache writes. The prompt caching page bills new input tokens, cache
      writes among them, "at standard input price", so a write costs 1x input.
    """

    OFFICIAL = {
        "MiniMax-M3.1-Flash": (0.15, 0.60, 0.015),
        "MiniMax-M3": (0.30, 1.20, 0.06),
    }
    # The same columns above 512k input tokens (MiniMax-M3 only).
    OVER_512K = {"MiniMax-M3": (0.60, 2.40, 0.12)}
    # The Priority tab: (Input, Output, Prompt caching Read), up to and over 512k.
    PRIORITY = {"MiniMax-M3": ((0.45, 1.80, 0.09), (0.90, 3.60, 0.18))}
    # The struck list prices of MiniMax-M3, up to 512k: what is NOT charged.
    STRUCK = {"MiniMax-M3": (0.60, 2.40, 0.12)}
    LONG_OVER = 512_000

    def registered(self):
        """The table registered for one test, so price_record() can be
        checked end to end. Written before pricing/__init__.py listed the
        table; now that it does, this changes nothing."""
        patch = unittest.mock.patch.dict(tm.TABLES, {minimax.PROVIDER: minimax})
        patch.start()
        self.addCleanup(patch.stop)
        return minimax.PROVIDER

    def test_every_rate_matches_the_pricing_page(self):
        """Guards against a MiniMax rate typed wrongly into pricing/minimax.py,
        a model on the page missing from the table, or a table row the page
        does not list: the table must hold exactly the page's two ids, each
        row in force on 2 November 2026 at the page's Input, Output and Prompt
        caching Read."""
        self.assertEqual(set(minimax.PRICES), set(self.OFFICIAL),
                         "minimax table and the page's model list differ")
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row = in_force(minimax.PRICES[model])
                self.assertIsNotNone(row, f"{model} has no row in force on {MINIMAX_READ_ON}")
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_m3_is_charged_at_the_permanent_half_price_not_the_struck_list_price(self):
        """Guards against typing MiniMax-M3's struck-through list price, which
        the page shows beside the charged one: "Permanent 50% off" has no end
        date, so the row in force carries the charged figure, half the list."""
        row = in_force(minimax.PRICES["MiniMax-M3"])
        inp, out, hit = self.STRUCK["MiniMax-M3"]
        self.assertAlmostEqual(row["in"], inp / 2, places=9)
        self.assertAlmostEqual(row["out"], out / 2, places=9)
        self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit / 2, places=9)
        self.assertNotAlmostEqual(row["in"], inp, places=9)

    def test_m3_doubles_over_512k_input_tokens(self):
        """Guards MiniMax-M3's prompt-length tier: up to 512,000 input tokens
        (cache reads included) the whole request is at the lower rates, one
        token more and every rate is the "> 512k" row, cache reads too."""
        row = in_force(minimax.PRICES["MiniMax-M3"])
        self.assertEqual(row.get("long"), {"over": self.LONG_OVER, "in": 2.0, "out": 2.0})
        provider = self.registered()
        low, high = self.OFFICIAL["MiniMax-M3"], self.OVER_512K["MiniMax-M3"]
        # 500,000 of each prompt is cache: exactly 512,000, then 512,001.
        for inp, (r_in, r_out, r_hit) in ((12_000, low), (12_001, high)):
            with self.subTest(prompt=inp + 500_000):
                c = tm.price_record("MiniMax-M3", usage(inp=inp, read=500_000, out=1_000),
                                    when=noon(MINIMAX_READ_ON), provider=provider)
                self.assertFalse(c["_unknown_model"])
                self.assertAlmostEqual(c["input"], inp * r_in / 1e6, places=12)
                self.assertAlmostEqual(c["cache_read"], 500_000 * r_hit / 1e6, places=12)
                self.assertAlmostEqual(c["output"], 1_000 * r_out / 1e6, places=12)

    def test_flash_has_one_price_at_any_prompt_length(self):
        """Guards against a prompt-length tier the page does not print for
        MiniMax-M3.1-Flash: it has one row, so a prompt of 1,000,000 tokens
        costs the same per token as a short one."""
        row = in_force(minimax.PRICES["MiniMax-M3.1-Flash"])
        self.assertIsNone(row.get("long"))
        provider = self.registered()
        inp, out, _ = self.OFFICIAL["MiniMax-M3.1-Flash"]
        c = tm.price_record("MiniMax-M3.1-Flash", usage(inp=1_000_000, out=1_000_000),
                            when=noon(MINIMAX_READ_ON), provider=provider)
        self.assertAlmostEqual(cost_of(c), inp + out, places=9)

    def test_m3_priority_tier_is_one_and_a_half_times_standard(self):
        """Guards the Priority tab ("Pricing is 1.5x standard"): a MiniMax-M3
        call recorded as priority costs the tab's figures at both prompt
        lengths, cache reads included, and MiniMax-M3.1-Flash, which the tab
        does not list, has no priority rate."""
        (p_in, p_out, p_hit), (q_in, q_out, q_hit) = self.PRIORITY["MiniMax-M3"]
        row = in_force(minimax.PRICES["MiniMax-M3"])
        self.assertIsNotNone(row.get("fast"))
        self.assertAlmostEqual(row["fast"][0], p_in, places=9)
        self.assertAlmostEqual(row["fast"][1], p_out, places=9)
        self.assertIsNone(in_force(minimax.PRICES["MiniMax-M3.1-Flash"]).get("fast"))
        provider = self.registered()
        # 500,000 of each prompt is cache: exactly 512,000, then 512,001.
        for inp, (r_in, r_out, r_hit) in ((12_000, (p_in, p_out, p_hit)),
                                          (12_001, (q_in, q_out, q_hit))):
            with self.subTest(prompt=inp + 500_000):
                c = tm.price_record("MiniMax-M3", usage(inp=inp, read=500_000, out=1_000_000),
                                    speed="fast", when=noon(MINIMAX_READ_ON), provider=provider)
                self.assertAlmostEqual(c["input"], inp * r_in / 1e6, places=12)
                self.assertAlmostEqual(c["cache_read"], 500_000 * r_hit / 1e6, places=12)
                self.assertAlmostEqual(c["output"], r_out, places=9)

    def test_cache_writes_bill_at_the_standard_input_price(self):
        """Guards the prompt caching page's rule that new input tokens, what is
        written to the cache among them, are "Billed at standard input price":
        no write premium, for either cache lifetime, on either model."""
        for model in self.OFFICIAL:
            with self.subTest(model=model):
                row = in_force(minimax.PRICES[model])
                self.assertEqual(tm.write_mults(row, minimax), (1.0, 1.0))


# Xiaomi MiMo rates, typed from the maker's own pricing page by a second
# reader, so a slip in the table or in this reading fails.
#
# Each figure was read off the saved page on 2 November 2026, not copied from
# pricing/mimo.py. A rate change is a new dated row in the table and a new
# figure here; see pricing/README.md.

MIMO_READ_ON = "2026-11-02"


def row_in_force(model, when=MIMO_READ_ON):
    """The row in force on a day: the last row whose from is "" or on or
    before that day."""
    rows = [r for r in mimo.PRICES[model] if r["from"] == "" or r["from"] <= when]
    return rows[-1] if rows else None


class TestMimoPublishedRates(Base):
    """Every rate in the Xiaomi MiMo table, typed from the page.

    The page is https://mimo.mi.com/docs/price/pay-as-you-go ('API Pricing'
    on platform.xiaomimimo.com). That path serves only a JavaScript shell, so
    the copy read is its markdown source,
    https://mimo.mi.com/static/docs/price/pay-as-you-go.md, fetched at 17:32
    UTC on 2 November 2026 and saved as mimo_pricing_2026-11-02.md (10,854
    bytes, sha256 3aa9c9bd5b91dd86...). The ids were checked against the
    model list saved beside it, mimo_models_2026-11-02.md, section 'Text
    Generation Model', which names the same three text models.

    Only the section 'Overseas Pricing of the Model' is used: the page bills
    'Overseas: dollar / M tokens'. The 'Domestic Pricing of the Model'
    section is in yuan and is not read.

    OFFICIAL is (Input (Cache Miss), Output, Input (Cache Hit)), dollars per
    million tokens, from the 'Real-time API' group of the 'Language Models'
    table. The 'Batch API' group (half price, mimo-v2.6-pro and
    mimo-v2.6-flash only), the ASR model (billed per hour of audio), the TTS
    models and the web search plugin (billed per call) are not per-token chat
    prices and are left out.

    Under the brief's rule for what the engine cannot express yet:
    - Prompt-length tiers: the page prints one price per model, with no
      prompt-length band, so a row carries no long tier.
    - Thinking and non-thinking: the model list says the models support
      'Deep Thinking', but the page prints one Output price with no thinking
      split, so that one price applies whatever the log records.
    - Temporary discounts: 'Cache Write: Limited-time Free' gives no end
      date, so it is priced as the page charges now: no charge beyond the
      cache-miss input price, since the page bills every prompt token at
      either Input (Cache Hit) or Input (Cache Miss) and prints no write
      price. Noted here.
    mimo-v2.6-pro-ultraspeed is its own API id with its own prices, not a
    faster mode of mimo-v2.6-pro, so no row carries a fast pair.

    The cache hit figures are pinned as printed even though they are not one
    fraction of input: $0.0036 against $0.435 for mimo-v2.6-pro, $0.0028
    against $0.14 for mimo-v2.6-flash, $0.036 against $4.35 for the
    ultraspeed id. The page prints no dated rate change for these ids; its
    one date is the notice that mimo-v2.5-pro and mimo-v2.5 were deprecated
    on 21 October 2026, and it prints no price for either.
    """

    OFFICIAL = {
        "mimo-v2.6-pro": (0.435, 0.87, 0.0036),
        "mimo-v2.6-flash": (0.14, 0.28, 0.0028),
        "mimo-v2.6-pro-ultraspeed": (4.35, 8.7, 0.036),
    }

    def _row(self, model):
        row = row_in_force(model)
        self.assertIsNotNone(row, f"{model} has no row in force on {MIMO_READ_ON}")
        return row

    def test_every_rate_matches_the_pricing_page(self):
        """Guards against a MiMo rate typed wrongly into pricing/mimo.py, a
        Batch API or yuan figure taken in place of the overseas Real-time
        API one, a text model on the page missing from the table, or a table
        row the page does not list: the table must hold exactly the page's
        three ids, each at the page's Input (Cache Miss), Output and Input
        (Cache Hit) in the row in force on the day the page was read."""
        self.assertEqual(set(mimo.PRICES), set(self.OFFICIAL),
                         "mimo table and the page's model list differ")
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row = self._row(model)
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_cache_writes_cost_only_the_cache_miss_input_price(self):
        """Guards the page's rule 'Cache Write: Limited-time Free', which
        gives no end date: under the brief it is priced as the page charges
        now. The page bills every prompt token at Input (Cache Hit) or Input
        (Cache Miss) and prints no write price, and a written token is a
        miss, so a cache write of either lifetime costs the input rate on
        every id (multiple 1.0): neither free, which would make billed
        cache-miss tokens cost nothing, nor Anthropic's surcharge multiples."""
        for model in self.OFFICIAL:
            with self.subTest(model=model):
                m5, m1 = tm.write_mults(self._row(model), mimo)
                self.assertEqual(m5, 1.0)
                self.assertEqual(m1, 1.0)

    def test_one_price_at_every_prompt_length_and_hour(self):
        """Guards against a long-context tier or a time-of-day discount the
        page does not have: each model has one row on the page, with no
        prompt-length band and no off-peak rate."""
        for model in self.OFFICIAL:
            with self.subTest(model=model):
                row = self._row(model)
                self.assertIsNone(row.get("long"))
                self.assertIsNone(row.get("off_peak"))

    def test_ultraspeed_is_its_own_model_not_a_fast_mode(self):
        """Guards against mimo-v2.6-pro-ultraspeed's prices being folded into
        mimo-v2.6-pro as a fast pair: the page and the model list give it its
        own API id and its own row, and print no fast or priority rate for
        any id."""
        for model in self.OFFICIAL:
            with self.subTest(model=model):
                self.assertIsNone(self._row(model).get("fast"))

    def test_no_rate_change_after_the_reading(self):
        """Guards against a dated row the page does not announce: the page
        prints no future price change for any of these ids, and the cache
        write offer has no end date, so no row takes effect after the day the
        page was read."""
        for model in self.OFFICIAL:
            with self.subTest(model=model):
                later = [r["from"] for r in mimo.PRICES[model] if r["from"] > MIMO_READ_ON]
                self.assertEqual(later, [])


class TestPublishedPriceList(Base):
    def test_docs_prices_matches_the_tables(self):
        """docs/prices.md is generated; it must never drift from what prices."""
        path = os.path.join(os.path.dirname(FIXTURES), "..", "docs", "prices.md")
        self.assertEqual(slurp(path, encoding="utf-8"), tm.price_listing(markdown=True),
                         "regenerate: python3 tokenmeter.py --list-prices --markdown > docs/prices.md")

    def test_every_model_is_listed(self):
        text = tm.price_listing(markdown=True)
        for table in tm.TABLES.values():
            for model in table.PRICES:
                self.assertIn(f"`{model}`", text)

    def test_readme_price_table_matches_the_tables(self):
        """README's price table said 18 and 38 models, checked 26 Sep 2026,
        while the tables held 19 and 39, checked on 6 October, and the
        sentence above it already said 19: nothing tied it to the tables. Each
        row is now built here from TABLES and verification(), in the tables'
        order: the provider's name (the README may add a word in brackets),
        its models with any retired ones noted, the date its page was checked,
        and whether it was measured against real bills. So are the Anthropic
        count above the table and the providers the second level names."""
        readme = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "README.md"),
                       encoding="utf-8")
        head = "| Provider | Models | Page checked | Against real bills |"
        self.assertIn(head, readme)
        rows = []
        for line in readme.split(head, 1)[1].splitlines()[2:]:
            if not line.startswith("|"):
                break
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        self.assertEqual(len(rows), len(tm.TABLES), "one row per price table")

        for row, (provider, table) in zip(rows, tm.TABLES.items()):
            v = tm.verification(provider)
            retired = len(getattr(table, "RETIRED", {}))
            models = (f"{len(table.PRICES)} ({retired} retired)" if retired
                      else str(len(table.PRICES)))
            want = [models, v["pretty"], "**yes**" if v["measured"] else "not yet"]
            self.assertTrue(row[0] == table.NAME or row[0].startswith(table.NAME + " ("),
                            f"README's row {row[0]!r} should be {table.NAME}'s")
            self.assertEqual(row[1:], want, f"README's {table.NAME} row")

        anthropic = f"Anthropic: all {len(tm.TABLES['anthropic'].PRICES)} models"
        self.assertTrue(anthropic in readme, f"README should say {anthropic!r}")
        names = [t.NAME for t in tm.TABLES.values() if not t.MEASURED]
        second = ", ".join(names[:-1]) + " and " + names[-1] + "."
        self.assertTrue(second in readme, f"README's second level should name {second!r}")


class TestListPricesCacheWrites(Base):
    # A table whose defaults bill cache writes (1.25x for 5 minutes, 2x for
    # 1 hour, as Anthropic's do), with one row that has no cache discount and
    # one that has.
    TABLE = types.SimpleNamespace(
        NAME="Example", SOURCE="https://example.com/pricing", VERIFIED_ON="2026-11-01",
        MEASURED=False, CACHE_WRITE_5M_MULT=1.25, CACHE_WRITE_1H_MULT=2.0,
        PRICES={
            "no-discount-model": [{"from": "", "in": 3.0, "out": 15.0,
                                   "cache_read_mult": 1.0, "fast": None}],
            "discounted-model": [{"from": "", "in": 3.0, "out": 15.0,
                                  "cache_read_mult": 0.1, "fast": None}],
        })

    def rows(self, markdown):
        with unittest.mock.patch.dict(tm.TABLES, {"example": self.TABLE}, clear=True):
            text = tm.price_listing(markdown=markdown)
        return {name: next(line for line in text.splitlines() if name in line)
                for name in self.TABLE.PRICES}

    def test_a_row_with_no_cache_discount_lists_no_cache_writes(self):
        """Guards --list-prices (and so docs/prices.md) printing a 5-minute
        or 1-hour cache-write price the maker never published, taken from
        the table's default write multiples, for a row whose cache_read_mult
        is 1.0. Such a row shows "-" for writes in both forms of the list; a
        row with a cache discount still shows its write prices. Pricing is
        untouched: the row's write multiples are still the table's."""
        md = self.rows(markdown=True)
        cells = [c.strip() for c in md["no-discount-model"].strip("|").split("|")]
        self.assertEqual(cells[1:5], ["$3", "-", "-", "$15"])
        self.assertNotIn("cache write", cells[5])
        cells = [c.strip() for c in md["discounted-model"].strip("|").split("|")]
        self.assertEqual(cells[1:5], ["$3", "$0.30", "$3.75", "$15"])
        self.assertIn("1-hour cache write $6", cells[5])

        plain = self.rows(markdown=False)
        self.assertNotIn("cache write", plain["no-discount-model"])
        self.assertIn("1-hour cache write $6", plain["discounted-model"])

        row = self.TABLE.PRICES["no-discount-model"][0]
        self.assertEqual(tm.write_mults(row, self.TABLE), (1.25, 2.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
