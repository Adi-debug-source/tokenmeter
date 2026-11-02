"""Pricing: the rate a call is charged, from the tables and the rules
around them: dated rows, today's rates, long context, fast mode, reading a
dollar figure off a provider's page, the rules each provider's table models,
web search rates, and the name translation that prices a host's or a
harness's spelling of a model at its maker's id.
"""

import datetime as dt
import json
import os
import re
import types
import unittest
import unittest.mock

from helpers import Base, cli, cost_of, noon, tm, usage

from pricing import mimo, minimax
from test_lookup import MIMO_ON_THE_PAGE, MiniMaxBase, WithMimo

M = 1_000_000
# A prompt well under the 272K long-context line, so a rate is read as printed.
K = 100_000
UTC = dt.timezone.utc


class TestPricing(Base):
    def test_known_model_is_recognised(self):
        row, ok = tm.lookup("claude-opus-5")
        self.assertTrue(ok)
        self.assertEqual(row["in"], 5.0)

    def test_dated_snapshot_suffix(self):
        """claude-haiku-4-5-20251001 fell through to Opus, 5x the true rate."""
        row, ok = tm.lookup("claude-haiku-4-5-20251001")
        self.assertTrue(ok)
        self.assertEqual(row["in"], 1.0)

    def test_unknown_model_is_flagged_not_hidden(self):
        row, ok = tm.lookup("claude-something-new")
        self.assertFalse(ok)

    def test_rate_in_force_at_the_time(self):
        """A flat table reprices every past call the day a rate moves."""
        tm.PRICES["test-model"] = [
            {"from": "", "in": 1.0, "out": 1.0, "cache_read_mult": 0.1, "fast": None},
            {"from": "2026-09-01", "in": 10.0, "out": 10.0, "cache_read_mult": 0.1, "fast": None},
        ]
        try:
            before = dt.datetime(2026, 8, 15, tzinfo=dt.timezone.utc)
            after = dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc)
            self.assertEqual(tm.lookup("test-model", before)[0]["in"], 1.0)
            self.assertEqual(tm.lookup("test-model", after)[0]["in"], 10.0)
            tm.CURRENT_RATES.append(True)
            self.assertEqual(tm.lookup("test-model", before)[0]["in"], 10.0)
        finally:
            del tm.PRICES["test-model"]

    def test_no_cache_counterfactual_pays_for_web_search(self):
        """Leaving searches out understated "saved" by the search bill."""
        c = tm.price_record("claude-opus-5", usage(inp=1000, out=100, searches=10))
        self.assertGreater(c["_no_cache"], 0)
        self.assertAlmostEqual(c["_no_cache"] - c["web_search"],
                               1000 * 5.0 / 1e6 + 100 * 25.0 / 1e6, places=9)

    def test_fast_speed_costs_more(self):
        std = tm.price_record("claude-opus-5", usage(inp=1_000_000))
        fast = tm.price_record("claude-opus-5", usage(inp=1_000_000, speed="fast"), "fast")
        self.assertGreater(fast["input"], std["input"])

    def test_one_hour_cache_write_is_double(self):
        h1 = tm.price_record("claude-opus-5", usage(w1=1_000_000))
        m5 = tm.price_record("claude-opus-5", usage(w5=1_000_000))
        self.assertAlmostEqual(h1["cache_write"], 5.0 * 2.0, places=9)
        self.assertAlmostEqual(m5["cache_write"], 5.0 * 1.25, places=9)


class TestCurrentRates(Base):
    """--current-rates took each model's newest row, so it charged a price
    announced for a date still to come: a gemini-3.8-flash call of 1M in and
    1M out cost $4.50 at its own date and $9.00 "at today's rates", the price
    Google has set for 2027."""

    def setUp(self):
        super().setUp()
        prices = tm.TABLES["google"].PRICES
        rows = prices["gemini-3.8-flash"]
        # The table's own later row, kept a year ahead whatever day this runs.
        ahead = (dt.date.today() + dt.timedelta(days=365)).isoformat()
        prices["gemini-3.8-flash"] = [rows[0], dict(rows[1], **{"from": ahead})]
        self.addCleanup(prices.__setitem__, "gemini-3.8-flash", rows)
        self.rows = prices["gemini-3.8-flash"]
        self.trial = os.path.join(self.tmp, "trial.jsonl")
        with open(self.trial, "w") as f:
            f.write(json.dumps({"id": "g1", "timestamp": "2026-10-01T10:00:00Z",
                                "provider": "google", "model": "gemini-3.8-flash",
                                "input": 1_000_000, "output": 1_000_000}) + "\n")

    def total(self, *flags):
        return json.loads(cli("--json", "--adapter", "import", "--import", self.trial,
                              "--no-ledger", *flags))["total_usd"]

    def test_todays_rates_are_the_ones_in_force_today(self):
        self.assertEqual((self.rows[0]["in"], self.rows[0]["out"]), (0.75, 3.75))
        self.assertAlmostEqual(self.total(), 4.5, places=9)
        self.assertAlmostEqual(self.total("--current-rates"), 4.5, places=9)

    def test_a_call_with_no_date_is_priced_as_of_today(self):
        self.assertIs(tm.rate_on(self.rows), self.rows[0])
        later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=400)
        self.assertIs(tm.rate_on(self.rows, later), self.rows[1])
        tm.CURRENT_RATES.append(True)
        self.assertIs(tm.rate_on(self.rows, later), self.rows[0])


class TestLongContextAndSpeed(Base):
    def test_openai_long_context_prices_the_whole_request(self):
        """Over 272K input: 2x input and cache, 1.5x output, whole request."""
        short = tm.price_record("gpt-6-astra", usage(inp=100_000, read=172_000, out=1_000_000),
                                provider="openai")
        long = tm.price_record("gpt-6-astra", usage(inp=100_000, read=172_001, out=1_000_000),
                               provider="openai")
        self.assertAlmostEqual(short["output"], 50.0, places=9)
        self.assertAlmostEqual(long["output"], 75.0, places=9)
        self.assertAlmostEqual(long["input"], short["input"] * 2, places=9)
        self.assertAlmostEqual(long["cache_read"], short["cache_read"] * 2 * 172_001 / 172_000, places=9)

    def test_gpt61_sol_long_context_and_fast_rates(self):
        """Typed from the page's Standard and Fast tables, 6 October 2026:
        long context $4.00 in, $0.20 cached, $5.00 writes, $15.00 out; fast
        $4.00 in, $0.20 cached, $20.00 out."""
        c = tm.price_record("gpt-6.1-sol", usage(inp=1_000_000, read=1_000_000, w5=1_000_000,
                                                 out=1_000_000), provider="openai")
        self.assertAlmostEqual(c["input"], 4.00, places=9)
        self.assertAlmostEqual(c["cache_read"], 0.20, places=9)
        self.assertAlmostEqual(c["cache_write"], 5.00, places=9)
        self.assertAlmostEqual(c["output"], 15.00, places=9)
        f = tm.price_record("gpt-6.1-sol", usage(inp=100_000, read=100_000, out=1_000_000,
                                                 speed="fast"), "fast", provider="openai")
        self.assertAlmostEqual(f["input"], 0.40, places=9)
        self.assertAlmostEqual(f["cache_read"], 0.02, places=9)
        self.assertAlmostEqual(f["output"], 20.00, places=9)

    def test_xai_long_context_starts_at_exactly_200k(self):
        """xAI's rule is "reaches 200k", so 200,000 itself is long."""
        below = tm.price_record("grok-4.7", usage(inp=199_999, out=1_000_000), provider="xai")
        at = tm.price_record("grok-4.7", usage(inp=200_000, out=1_000_000), provider="xai")
        self.assertAlmostEqual(below["output"], 6.0, places=9)
        self.assertAlmostEqual(at["output"], 12.0, places=9)

    def test_gemini_long_context_is_over_200k(self):
        at = tm.price_record("gemini-2.5-pro", usage(inp=200_000, out=1_000_000), provider="google")
        over = tm.price_record("gemini-2.5-pro", usage(inp=200_001, out=1_000_000), provider="google")
        self.assertAlmostEqual(at["output"], 10.0, places=9)
        self.assertAlmostEqual(over["output"], 15.0, places=9)

    def test_anthropic_has_no_long_context_surcharge(self):
        c = tm.price_record("claude-opus-5", usage(inp=900_000, out=1_000_000))
        self.assertAlmostEqual(c["output"], 25.0, places=9)

    def test_fast_mode_stacks_with_long_context(self):
        c = tm.price_record("gpt-6-sol", usage(inp=300_000, out=1_000_000, speed="fast"), "fast",
                            provider="openai")
        self.assertAlmostEqual(c["output"], 20.0 * 1.5, places=9)

    def test_a_provider_with_no_table_is_counted_at_zero_and_flagged(self):
        c = tm.price_record("some-model", usage(inp=1000, out=1000), provider="nobody")
        self.assertEqual(cost_of(c), 0.0)
        self.assertTrue(c["_unknown_model"])
        self.assertEqual(c["_tokens"]["input"], 1000)


class TestPageMoney(Base):
    """Four page readers each kept a copy of the rule for reading a dollar
    figure off a pricing page; pricing.common.money() is the one rule now, and
    it must read every cell exactly as each copy did."""

    CELLS = ("$0.25 / MTok<sup>1</sup>", "$10.00", "$1,250.00", "$1,250", "-", "", "Free",
             " free ", "FREE", "Free tier, then $2.50", "Input: $3 / Output: $15", "n/a",
             "$0.0375 / MTok", "$.5", "about $7")

    @staticmethod
    def with_commas(cell):
        """Anthropic's, OpenAI's and xAI's copy, as it was."""
        m = re.search(r"\$([\d.,]+)", cell)
        return float(m.group(1).replace(",", "")) if m else None

    @staticmethod
    def zai(cell):
        """Z.ai's copy, as it was: "Free" is zero, and a figure stops at a comma."""
        if cell.strip().lower() == "free":
            return 0.0
        m = re.search(r"\$([\d.]+)", cell)
        return float(m.group(1)) if m else None

    def test_every_cell_reads_as_it_did(self):
        from pricing.common import money
        for cell in self.CELLS:
            with self.subTest(cell=cell):
                self.assertEqual(money(cell), self.with_commas(cell))
                self.assertEqual(money(cell, free_is_zero=True, commas=False), self.zai(cell))
        self.assertEqual(money("$1,250.00 / MTok"), 1250.0)
        self.assertIsNone(money("Free"))
        self.assertEqual(money(" Free ", free_is_zero=True), 0.0)

    def test_no_table_keeps_a_copy(self):
        import pricing
        for table in pricing.TABLES.values():
            with self.subTest(table=table.PROVIDER):
                # Either spelling: Google's unused regex was named in capitals.
                self.assertEqual([n for n in vars(table) if n.lower() == "_money"], [])
        self.assertNotIn("common", pricing.TABLES)


# Anthropic: the rules the table models. Its page reader, and the saved
# page that reader is tested on, are in test_lookup.py.

class TestAnthropicRules(Base):
    def table(self):
        return tm.TABLES["anthropic"]

    def test_a_dated_row_is_in_force_from_its_date(self):
        """Guards Sonnet 5.5's cache read cut of 7 October 2026 being applied
        to earlier calls, or not to calls from that day: $0.20 a million hits
        on 6 October, $0.10 from 7 October, every other rate unchanged."""
        u = usage(inp=M, out=M, read=M)
        before = tm.price_record("claude-sonnet-5-5", u, when=noon("2026-10-06"))
        on = tm.price_record("claude-sonnet-5-5", u, when=noon("2026-10-07"))
        self.assertAlmostEqual(before["cache_read"], 0.20, places=9)
        self.assertAlmostEqual(on["cache_read"], 0.10, places=9)
        for part in ("input", "output"):
            self.assertAlmostEqual(before[part], on[part], places=9)

    def test_long_prompts_cross_at_over_100000_with_cache_counted(self):
        """Guards Haiku 5.5's prompt-length tiers: exactly 100,000 prompt
        tokens is the lower tier ("up to 100,000"), one more is the higher,
        and cache reads and writes count towards the prompt."""
        at = tm.price_record("claude-haiku-5-5", usage(inp=60_000, read=30_000, w5=10_000, out=M))
        over = tm.price_record("claude-haiku-5-5", usage(inp=60_000, read=30_000, w5=10_001, out=M))
        self.assertAlmostEqual(at["output"], 0.50, places=9)
        self.assertAlmostEqual(over["output"], 2.50, places=9)
        self.assertAlmostEqual(over["cache_read"], 30_000 * 0.05 / M, places=12)

    def test_no_row_has_an_off_peak_price(self):
        """Guards an invented time-of-day price: the page publishes none, so
        no row carries off_peak and a call at 03:00 UTC on a weekday costs
        what it costs at noon."""
        for model, rows in self.table().PRICES.items():
            for row in rows:
                with self.subTest(model=model, row=row["from"]):
                    self.assertNotIn("off_peak", row)
        u = usage(inp=M, out=M)
        night = dt.datetime(2026, 10, 20, 3, tzinfo=dt.timezone.utc)
        noonish = dt.datetime(2026, 10, 20, 12, tzinfo=dt.timezone.utc)
        self.assertAlmostEqual(cost_of(tm.price_record("claude-opus-5", u, when=night)),
                               cost_of(tm.price_record("claude-opus-5", u, when=noonish)), places=9)

    def test_fast_mode_is_priced_only_where_the_page_lists_it(self):
        """Guards fast mode: Opus 5.5 fast is $8 / $40, and a fast call to a
        model the page gives no fast rate (Opus 4.7 today) prices at its
        standard rate rather than at another model's fast rate."""
        u = usage(inp=M, out=M, speed="fast")
        c = tm.price_record("claude-opus-5-5", u, "fast")
        self.assertAlmostEqual(c["input"], 8.0, places=9)
        self.assertAlmostEqual(c["output"], 40.0, places=9)
        c = tm.price_record("claude-opus-4-7", u, "fast")
        self.assertAlmostEqual(c["input"], 5.0, places=9)
        self.assertAlmostEqual(c["output"], 25.0, places=9)

    def test_retired_models_keep_their_last_published_price(self):
        """Guards a retired model dropping to the fallback: every RETIRED id
        has a row and an ISO date, a call long after its retirement is still
        recognised and priced at its row, and Haiku 3's printed figures,
        whose write and hit are not the table's default multiples, are
        reproduced exactly."""
        table = self.table()
        self.assertEqual(len(table.RETIRED), 11)
        later = dt.datetime(2026, 10, 27, 12, tzinfo=dt.timezone.utc)
        for model, day in table.RETIRED.items():
            with self.subTest(model=model):
                self.assertIn(model, table.PRICES)
                dt.date.fromisoformat(day)
                row, ok = tm.lookup(model, when=later)
                self.assertTrue(ok)
                self.assertEqual(row, table.PRICES[model][-1])
        c = tm.price_record("claude-3-haiku", usage(inp=M, w5=M, w1=M, read=M, out=M))
        self.assertAlmostEqual(c["input"], 0.25, places=9)
        self.assertAlmostEqual(c["cache_write"], 0.30 + 0.50, places=9)
        self.assertAlmostEqual(c["cache_read"], 0.03, places=9)
        self.assertAlmostEqual(c["output"], 1.25, places=9)
        c = tm.price_record("claude-2.1", usage(inp=M, out=M))
        self.assertAlmostEqual((c["input"], c["output"]), (8.0, 24.0))

    def test_models_with_no_published_cache_price_print_no_cache_write(self):
        """Guards the price list printing cache write figures Anthropic never
        published: Claude 3 Sonnet's card (archive capture 20250121003151)
        and Claude 2.1's and 2.0's (20241024003303) print Input and Output
        only, so their rows carry write_mult 1.0 beside cache_read_mult 1.0.
        Without it they took the table's 1.25x and 2x, and --list-prices
        printed "1-hour cache write $6" for Claude 3 Sonnet and "$16" for
        Claude 2.1 and 2.0."""
        table = self.table()
        listing = tm.price_listing(markdown=True).splitlines()
        for model, inp, out in (("claude-3-sonnet", "$3", "$15"),
                                ("claude-2.1", "$8", "$24"), ("claude-2.0", "$8", "$24")):
            with self.subTest(model=model):
                self.assertEqual(tm.write_mults(table.PRICES[model][-1], table), (1.0, 1.0))
                line = [l for l in listing if l.startswith(f"| `{model}` |")]
                self.assertEqual(len(line), 1)
                cells = [c.strip() for c in line[0].strip("|").split("|")]
                self.assertEqual(cells[1:5], [inp, "-", "-", out])
                self.assertNotIn("cache write", cells[5])

    def test_api_ids_and_aliases_price_as_their_model(self):
        """Guards the API's own names reaching the fallback ($5 / $25): Haiku
        3.5's row is named from the page (claude-haiku-3-5), so its dated id
        claude-3-5-haiku-20241022 and its aliases resolve only through
        ALIASES; the new retired rows' dated ids resolve through SNAPSHOT."""
        table = self.table()
        for alias, model in table.ALIASES.items():
            with self.subTest(alias=alias):
                self.assertIn(model, table.PRICES)
                c = tm.price_record(alias, usage(inp=M, out=M))
                self.assertFalse(c.get("_unknown_model"))
                self.assertAlmostEqual(c["output"], table.PRICES[model][-1]["out"], places=9)
        self.assertEqual(tm.lookup("claude-3-5-haiku-20241022")[0]["in"], 0.8)
        for dated, model in (("claude-3-7-sonnet-20250219", "claude-3-7-sonnet"),
                             ("claude-3-5-sonnet-20240620", "claude-3-5-sonnet"),
                             ("claude-3-opus-20240229", "claude-3-opus"),
                             ("claude-3-haiku-20240307", "claude-3-haiku"),
                             ("claude-3-sonnet-20240229", "claude-3-sonnet")):
            with self.subTest(dated=dated):
                row, ok = tm.lookup(dated)
                self.assertTrue(ok)
                self.assertEqual(row, table.PRICES[model][-1])


# OpenAI: the rules the table models. Its page reader, and the saved
# page that reader is tested on, are in test_lookup.py.

def openai_in_force(model, day):
    """OpenAI's row for a model on a day."""
    return tm.lookup(model, when=noon(day), provider="openai")[0]


class TestOpenAIRules(Base):
    def table(self):
        return tm.TABLES["openai"]

    def test_the_gpt_5_6_cuts_are_in_force_from_their_dates(self):
        """Guards the GPT-5.6 cuts being applied to earlier calls, or not to
        calls from their day: Terra $2.50 / $15 and Luna $1 / $6 until 29
        July 2026, $2 / $12 and $0.20 / $1.20 from 30 July; Sol $5 / $30
        until 20 August, $4 / $20 from 21 August."""
        for model, before_day, on_day, before, on in (
                ("gpt-5.6-terra", "2026-07-29", "2026-07-30", (2.50, 15), (2, 12)),
                ("gpt-5.6-luna", "2026-07-29", "2026-07-30", (1, 6), (0.20, 1.20)),
                ("gpt-5.6-sol", "2026-08-20", "2026-08-21", (5, 30), (4, 20))):
            with self.subTest(model=model):
                u = usage(inp=K, out=K)
                b = tm.price_record(model, u, when=noon(before_day), provider="openai")
                o = tm.price_record(model, u, when=noon(on_day), provider="openai")
                self.assertAlmostEqual(b["input"], before[0] * K / M, places=12)
                self.assertAlmostEqual(b["output"], before[1] * K / M, places=12)
                self.assertAlmostEqual(o["input"], on[0] * K / M, places=12)
                self.assertAlmostEqual(o["output"], on[1] * K / M, places=12)

    def test_the_12_hour_write_is_charged_from_20_october_2026(self):
        """Guards the 12-hour cache write, held in the write_1h_mult slot,
        reaching calls before OpenAI introduced it: on gpt-6-astra a long
        write is $12.50 a million (the 30-minute rate) on 19 October 2026
        and $25 from 20 October, while the 30-minute write stays $12.50. The
        same for gpt-5.6-cyber, $15.625 then $31.25, whose one undated row
        once charged the 12-hour rate on every earlier call."""
        long_write = usage(w1=K)
        short_write = usage(w5=K)
        for model, w30, w12 in (("gpt-6-astra", 12.50, 25.0), ("gpt-5.6-cyber", 15.625, 31.25)):
            for day, want in (("2026-09-01", w30), ("2026-10-19", w30), ("2026-10-20", w12)):
                with self.subTest(model=model, day=day):
                    c = tm.price_record(model, long_write, when=noon(day), provider="openai")
                    self.assertAlmostEqual(c["cache_write"], want * K / M, places=12)
                    c = tm.price_record(model, short_write, when=noon(day), provider="openai")
                    self.assertAlmostEqual(c["cache_write"], w30 * K / M, places=12)

    def test_gpt_6_astra_law_prices_at_the_pages_promotional_rates(self):
        """Guards gpt-6-astra-law, priced on the maintainer's decision of 2
        November 2026 at the page's promotional rates ("available at least
        through December 31, 2026"), being charged anything else: $10 a
        million in, $50 out, $1 cached. The page prints no other column for
        it, so a cache write of either lifetime is ordinary input ($10), a
        prompt over 272K stays at those rates (no long tier), a call
        recorded as fast is charged Standard (no fast pair), and the call
        is priced from the table, not the lookup."""
        self.assertEqual([r["from"] for r in self.table().PRICES["gpt-6-astra-law"]], [""])
        for day in ("2026-10-27", "2026-11-02", "2026-12-31"):
            for speed in ("standard", "fast"):
                with self.subTest(day=day, speed=speed):
                    c = tm.price_record("gpt-6-astra-law",
                                        usage(inp=K, read=K, w5=K, w1=K, out=K),
                                        speed=speed, when=noon(day), provider="openai")
                    self.assertFalse(c["_unknown_model"])
                    self.assertAlmostEqual(c["input"], 10 * K / M, places=12)
                    self.assertAlmostEqual(c["cache_read"], 1 * K / M, places=12)
                    self.assertAlmostEqual(c["cache_write"], 2 * 10 * K / M, places=12)
                    self.assertAlmostEqual(c["output"], 50 * K / M, places=12)
        over = tm.price_record("gpt-6-astra-law", usage(inp=300_000, read=K, out=M),
                               when=noon("2026-11-02"), provider="openai")
        self.assertAlmostEqual(over["input"], 300_000 * 10 / M, places=12)
        self.assertAlmostEqual(over["cache_read"], K * 1 / M, places=12)
        self.assertAlmostEqual(over["output"], 50, places=9)

    def test_no_row_has_an_off_peak_price(self):
        """Guards an invented time-of-day price: the page publishes none, so
        no row carries off_peak and a call at 03:00 UTC on a weekday costs
        what it costs at noon."""
        for model, rows in self.table().PRICES.items():
            for row in rows:
                with self.subTest(model=model, row=row["from"]):
                    self.assertNotIn("off_peak", row)
        u = usage(inp=M, out=M)
        night = dt.datetime(2026, 10, 28, 3, tzinfo=dt.timezone.utc)
        noonish = dt.datetime(2026, 10, 28, 12, tzinfo=dt.timezone.utc)
        self.assertAlmostEqual(cost_of(tm.price_record("gpt-6-astra", u, when=night, provider="openai")),
                               cost_of(tm.price_record("gpt-6-astra", u, when=noonish, provider="openai")),
                               places=9)

    def test_long_prompts_cross_at_over_272000_with_cache_counted(self):
        """Guards the long-context rule: exactly 272,000 prompt tokens is
        short context ("<=272K"), one more is long, cache reads count towards
        the prompt, and the whole request moves to 2x input and cache and
        1.5x output. A model without the rule (gpt-5.4-mini) never moves."""
        at = tm.price_record("gpt-5.4", usage(inp=200_000, read=72_000, out=M), provider="openai")
        over = tm.price_record("gpt-5.4", usage(inp=200_001, read=72_000, out=M), provider="openai")
        self.assertAlmostEqual(at["output"], 15, places=9)
        self.assertAlmostEqual(over["output"], 22.50, places=9)
        self.assertAlmostEqual(over["input"], 200_001 * 5.00 / M, places=12)
        self.assertAlmostEqual(over["cache_read"], 72_000 * 0.50 / M, places=12)
        mini = tm.price_record("gpt-5.4-mini", usage(inp=400_000, out=M), provider="openai")
        self.assertAlmostEqual(mini["output"], 4.50, places=9)

    def test_a_fast_call_over_272000_on_gpt_5_5_takes_the_long_rule(self):
        """Guards the documented choice for a case the page leaves blank: a
        fast gpt-5.5 call of more than 272K input tokens is charged 2x fast
        input and 1.5x fast output, because the row's long rule, needed for
        standard calls, applies to fast ones too."""
        c = tm.price_record("gpt-5.5", usage(inp=300_000, out=M, speed="fast"), "fast",
                            provider="openai")
        self.assertAlmostEqual(c["input"], 300_000 * 25.0 / M, places=12)
        self.assertAlmostEqual(c["output"], 112.50, places=9)

    def test_fast_rates_are_the_typed_pairs_and_only_where_published(self):
        """Guards fast rates being taken as a multiple, or borrowed: gpt-4o
        fast is the printed $4.25 / $17 (1.7x), the retired gpt-5.1-codex
        takes its Priority $2.50 / $20 from the 30 July 2026 capture, and a
        fast call to gpt-5.1-codex-mini, which never had one, prices at its
        standard $0.25 / $2."""
        u = usage(inp=M, out=M, speed="fast")
        for model, want in (("gpt-4o", (4.25, 17)), ("gpt-5.1-codex", (2.50, 20)),
                            ("gpt-5.1-codex-mini", (0.25, 2))):
            with self.subTest(model=model):
                c = tm.price_record(model, u, "fast", provider="openai")
                self.assertAlmostEqual(c["input"], want[0], places=9)
                self.assertAlmostEqual(c["output"], want[1], places=9)

    def test_retired_models_keep_their_last_published_price(self):
        """Guards a retired model dropping to the fallback: each of the 37
        RETIRED ids has a row and an ISO date, a call long after retirement
        is still recognised and priced at its row, and archive-priced figures
        (gpt-4-32k $60 / $120, davinci-002 $2 / $2) are reproduced."""
        table = self.table()
        self.assertEqual(len(table.RETIRED), 37)
        later = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc)
        for model, day in table.RETIRED.items():
            with self.subTest(model=model):
                self.assertIn(model, table.PRICES)
                dt.date.fromisoformat(day)
                row, ok = tm.lookup(model, when=later, provider="openai")
                self.assertTrue(ok)
                self.assertEqual(row, table.PRICES[model][-1])
        for model, want in (("gpt-4-32k", (60, 120)), ("davinci-002", (2, 2))):
            with self.subTest(model=model):
                c = tm.price_record(model, usage(inp=M, out=M), provider="openai")
                self.assertAlmostEqual((c["input"], c["output"]), want)

    def test_aliases_and_snapshots_price_as_their_model(self):
        """Guards OpenAI's other names reaching the fallback ($10 / $50):
        gpt-4, gpt-4-turbo, gpt-4-turbo-preview, the five -completions
        names, the gpt-4-32k snapshots and the two deprecated gpt-daybreak
        aliases resolve only through ALIASES, and a dated snapshot of a
        retired row through SNAPSHOT."""
        table = self.table()
        for alias, model in table.ALIASES.items():
            with self.subTest(alias=alias):
                self.assertIn(model, table.PRICES)
                self.assertNotIn(alias, table.PRICES)
                c = tm.price_record(alias, usage(inp=K, out=K), provider="openai")
                self.assertFalse(c.get("_unknown_model"))
                self.assertAlmostEqual(c["output"], table.PRICES[model][-1]["out"] * K / M,
                                       places=12)
        self.assertEqual(openai_in_force("gpt-4", "2026-10-01")["in"], 30.0)
        # The deprecations page: "gpt-4-0613 | gpt-4, gpt-4-0613-completions,
        # gpt-4-completions", and gpt-4-turbo-preview-completions points to
        # gpt-4-0125-preview ($10 / $30).
        self.assertEqual(openai_in_force("gpt-4-completions", "2026-10-01")["in"], 30.0)
        self.assertEqual(openai_in_force("gpt-4-turbo-preview-completions", "2026-03-01")["out"], 30.0)
        self.assertEqual(openai_in_force("gpt-3.5-turbo-completions", "2026-10-01")["in"], 0.50)
        self.assertEqual(openai_in_force("gpt-daybreak-blue-latest", "2026-10-28")["in"], 4.0)
        row, ok = tm.lookup("o1-preview-2024-09-12", provider="openai")
        self.assertTrue(ok)
        self.assertEqual(row["in"], 15.0)


# Google (Gemini API): the rules the table models. Its page reader, and the saved
# page that reader is tested on, are in test_lookup.py.

class TestGoogleRules(Base):
    def cost(self, model, day=None, speed="standard", **kw):
        when = noon(day) if day else None
        return tm.price_record(model, usage(**kw), speed, when=when, provider="google")

    def test_a_dated_row_is_in_force_from_its_date(self):
        """Gemini 4 Argon's launch price runs through 30 November 2026 and
        doubles from 1 December. A call is priced at the rate on its own day;
        charging the later price early, or the launch price late, is wrong
        by half or double."""
        before = self.cost("gemini-4-argon", "2026-11-30", inp=M, out=M, read=M)
        after = self.cost("gemini-4-argon", "2026-12-01", inp=M, out=M, read=M)
        self.assertAlmostEqual(before["input"], 2.00, places=9)
        self.assertAlmostEqual(before["output"], 10.00, places=9)
        self.assertAlmostEqual(before["cache_read"], 0.10, places=9)
        self.assertAlmostEqual(after["input"], 4.00, places=9)
        self.assertAlmostEqual(after["output"], 20.00, places=9)
        self.assertAlmostEqual(after["cache_read"], 0.20, places=9)
        jan = self.cost("gemini-3.8-flash", "2027-01-01", inp=M, out=M)
        dec = self.cost("gemini-3.8-flash", "2026-12-31", inp=M, out=M)
        self.assertAlmostEqual((dec["input"], dec["output"]), (0.75, 3.75))
        self.assertAlmostEqual((jan["input"], jan["output"]), (1.50, 7.50))

    def test_priority_is_the_fast_rate_and_follows_the_dates(self):
        """A call recorded as fast or priority is billed at the page's
        Priority tier, from its own dated entry, with the cache read at the
        row's multiple. With fast left at None it was billed at Standard,
        about 45% under."""
        f = self.cost("gemini-4-argon", "2026-11-30", "fast", inp=M, out=M, read=M)
        self.assertAlmostEqual(f["input"], 3.60, places=9)
        self.assertAlmostEqual(f["output"], 18.00, places=9)
        self.assertAlmostEqual(f["cache_read"], 0.18, places=9)
        later = self.cost("gemini-4-argon", "2026-12-01", "fast", inp=M, out=M)
        self.assertAlmostEqual((later["input"], later["output"]), (7.20, 36.00))
        std = self.cost("gemini-2.5-flash", "2026-10-27", inp=M, out=M)
        self.assertAlmostEqual((std["input"], std["output"]), (0.30, 2.50))

    def test_no_time_of_day_price(self):
        """The page prints no peak or off-peak hours, so no row may carry an
        off_peak discount: a call at 03:00 UTC costs what one at noon does."""
        for mid, rows in tm.TABLES["google"].PRICES.items():
            for row in rows:
                self.assertNotIn("off_peak", row, mid)

    def test_long_context_is_over_200k_with_priority_on_top(self):
        """Above 200,000 prompt tokens, cache included, the whole request is
        2x input and cache and 1.5x output; 200,000 itself is not long. The
        page's Priority long figures ($7.20, $32.40, $0.72 for 3.1 Pro
        Preview) come out of the same multiples."""
        at = self.cost("gemini-3.1-pro-preview", inp=150_000, read=50_000, out=M)
        over = self.cost("gemini-3.1-pro-preview", inp=150_000, read=50_001, out=M)
        self.assertAlmostEqual(at["output"], 12.00, places=9)
        self.assertAlmostEqual(over["output"], 18.00, places=9)
        self.assertAlmostEqual(over["cache_read"], 50_001 * 0.40 / M, places=12)
        f = self.cost("gemini-3.1-pro-preview", None, "fast", inp=M, read=M, out=M)
        self.assertAlmostEqual(f["input"], 7.20, places=9)
        self.assertAlmostEqual(f["output"], 32.40, places=9)
        self.assertAlmostEqual(f["cache_read"], 0.72, places=9)

    def test_gemini_1_5_long_context_is_over_128k_and_doubles_everything(self):
        """The 1.5 series doubled input, output and cache above 128K, not at
        Gemini's usual 200K with 1.5x output: $1.25 and $2.50 in, $5.00 and
        $10.00 out, $0.3125 and $0.625 cached for 1.5 Pro."""
        at = self.cost("gemini-1.5-pro", inp=128_000, out=M)
        over = self.cost("gemini-1.5-pro", inp=128_001, out=M)
        self.assertAlmostEqual(at["output"], 5.00, places=9)
        self.assertAlmostEqual(over["output"], 10.00, places=9)
        long = self.cost("gemini-1.5-pro", inp=M, read=M, out=M)
        self.assertAlmostEqual(long["input"], 2.50, places=9)
        self.assertAlmostEqual(long["cache_read"], 0.625, places=9)

    def test_a_retired_model_is_still_priced_and_recognised(self):
        """A model the page dropped keeps its last published price for usage
        before and after its shutdown, and is not flagged as unknown; without
        its row a 2025 Gemini 2.0 Flash call was priced at the fallback, 3.1
        Pro Preview, twenty times too high on input."""
        table = tm.TABLES["google"]
        for mid, day in table.RETIRED.items():
            self.assertIn(mid, table.PRICES, mid)
            self.assertRegex(day, r"^\d{4}-\d{2}-\d{2}$")
        c = self.cost("gemini-2.0-flash", "2025-06-01", inp=M, out=M, read=M)
        self.assertFalse(c["_unknown_model"])
        self.assertAlmostEqual((c["input"], c["output"], c["cache_read"]), (0.10, 0.40, 0.025))
        late = self.cost("gemini-2.0-flash", "2026-10-27", inp=M)
        self.assertFalse(late["_unknown_model"])
        self.assertAlmostEqual(late["input"], 0.10, places=9)

    def test_a_retired_model_with_no_cache_price_gets_no_discount(self):
        """Where the copy cited printed no caching price (2.0 Flash-Lite,
        1.0 Pro), a cache read is billed as input, not at a 0.1x discount
        the page never offered."""
        c = self.cost("gemini-2.0-flash-lite", inp=M, read=M)
        self.assertAlmostEqual(c["cache_read"], c["input"], places=12)
        c = self.cost("gemini-1.0-pro", read=M)
        self.assertAlmostEqual(c["cache_read"], 0.50, places=9)

    def test_odd_cache_prices_are_reproduced_as_printed(self):
        """Prices that are no round multiple of input must still come out at
        the printed figure: 1.5 Flash-8B cached $0.01 against $0.0375 input,
        the 2.5 Pro Previews $0.31 against $1.25."""
        # Under each model's long-context threshold, so the short price applies.
        read = 100_000
        self.assertAlmostEqual(self.cost("gemini-1.5-flash-8b", read=read)["cache_read"],
                               read * 0.01 / M, places=15)
        self.assertAlmostEqual(self.cost("gemini-2.5-pro-preview-06-05", read=read)["cache_read"],
                               read * 0.31 / M, places=15)

    def test_the_flash_previews_bill_output_at_the_thinking_price(self):
        """2.5 Flash Preview 04-17 and 05-20 printed $0.60 non-thinking and
        $3.50 thinking output; the log cannot tell which, and the docstring
        says the row uses $3.50. A change to that choice must be deliberate."""
        for mid in ("gemini-2.5-flash-preview-04-17", "gemini-2.5-flash-preview-05-20"):
            c = self.cost(mid, inp=M, out=M)
            self.assertAlmostEqual((c["input"], c["output"]), (0.15, 3.50), msg=mid)

    def test_aliases_and_snapshots_reach_their_rows(self):
        """Google spells some ids two ways, and stable versions carry -001.
        Each spelling must reach the same row, recognised; an unmatched one
        was priced at the fallback with a warning."""
        for alias, mid in (("gemini-3.1-pro-preview-customtools", "gemini-3.1-pro-preview"),
                           ("gemini-2.5-flash-preview-09-25", "gemini-2.5-flash-preview-09-2025"),
                           ("gemini-2.5-flash-lite-06-17", "gemini-2.5-flash-lite-preview-06-17"),
                           ("gemini-2.0-flash-001", "gemini-2.0-flash"),
                           ("gemini-2.0-flash-lite-001", "gemini-2.0-flash-lite"),
                           ("gemini-1.5-flash-8b-001", "gemini-1.5-flash-8b")):
            row, ok = tm.lookup(alias, provider="google")
            self.assertTrue(ok, alias)
            self.assertEqual(row, tm.TABLES["google"].PRICES[mid][-1], alias)


# Moonshot (Kimi): the rules the table models. Its page reader, and the saved
# page that reader is tested on, are in test_lookup.py.

class TestMoonshotRules(Base):
    def cost(self, model, when=None, **kw):
        return tm.price_record(model, usage(**kw), when=when, provider="moonshot")

    def test_k3_series_bills_cache_writes_by_lifetime(self):
        """The K3 series prints a 5-minute write at the input rate and a
        1-hour write at twice it; the table's default of 1.0 for both would
        undercharge every 1-hour write by half."""
        for model, inp in (("kimi-k3.1-pro", 2.00), ("kimi-k3.1-pro-highspeed", 4.00), ("kimi-k3", 3.00)):
            with self.subTest(model=model):
                c = self.cost(model, w5=100_000, w1=100_000)
                self.assertAlmostEqual(c["cache_write"], 0.1 * inp + 0.1 * 2 * inp, places=9)

    def test_highspeed_cache_hit_is_as_printed(self):
        """kimi-k3.1-pro-highspeed's cached input is $0.20, the same as
        kimi-k3.1-pro's, though everything else is double. Writing it as the
        usual tenth of input would charge $0.40 a million."""
        c = self.cost("kimi-k3.1-pro-highspeed", read=1_000_000)
        self.assertAlmostEqual(c["cache_read"], 0.20, places=9)
        self.assertAlmostEqual(self.cost("kimi-k3.1-pro", read=1_000_000)["cache_read"], 0.20, places=9)

    def test_k2_cache_write_is_ordinary_input(self):
        """The K2 models print no write price and support no cache write, so
        a write a log records is ordinary input, not the K3 series' 2x."""
        for model, inp in (("kimi-k2.7-code", 0.95), ("kimi-k2.7-code-highspeed", 1.90), ("kimi-k2.6", 0.95)):
            with self.subTest(model=model):
                c = self.cost(model, w5=100_000, w1=100_000)
                self.assertAlmostEqual(c["cache_write"], 0.2 * inp, places=9)

    def test_no_long_context_surcharge(self):
        """Kimi prices the whole window flat. A long-context rule here would
        charge a large prompt more than the page does."""
        table = tm.TABLES["moonshot"]
        self.assertFalse(hasattr(table, "LONG_OVER"))
        self.assertFalse([m for m, rows in table.PRICES.items() for r in rows if r.get("long")])
        c = self.cost("kimi-k3.1-pro", inp=1_000_000, out=1_000_000)
        self.assertAlmostEqual(cost_of(c), 2.00 + 10.00, places=9)

    def test_one_output_price_whatever_the_thinking(self):
        """The page prints one output price per model, thinking or not, so
        thinking tokens must cost exactly what other output does."""
        plain = self.cost("kimi-k2.6", out=1_000_000)
        thinking = self.cost("kimi-k2.6", out=1_000_000, think=600_000)
        self.assertAlmostEqual(cost_of(plain), 4.00, places=9)
        self.assertAlmostEqual(cost_of(thinking), cost_of(plain), places=9)

    def test_highspeed_is_its_own_model_not_fast_mode(self):
        """A highspeed call records its own id, not a fast speed on the base
        id. Priced as `fast` of kimi-k3.1-pro it would be charged the base
        rate; so the id has its own row, and no row has a fast price that a
        call recorded as fast could pick up."""
        row, ok = tm.lookup("kimi-k3.1-pro-highspeed", provider="moonshot")
        self.assertTrue(ok)
        self.assertEqual((row["in"], row["out"]), (4.00, 20.00))
        self.assertTrue(all(r["fast"] is None for rows in tm.TABLES["moonshot"].PRICES.values()
                            for r in rows))
        fast = tm.price_record("kimi-k3.1-pro", usage(inp=1_000_000), speed="fast", provider="moonshot")
        self.assertAlmostEqual(fast["input"], 2.00, places=9)

    def test_k2_is_still_priced_after_the_notice_date(self):
        """The notice closes the K2 series to new users on 31 October 2026
        and plans a retirement by the end of December with no day given.
        Existing users keep calling them, so they are neither RETIRED nor
        repriced, and a call after that date is priced and recognised."""
        table = tm.TABLES["moonshot"]
        self.assertEqual(getattr(table, "RETIRED", {}), {})
        later = dt.datetime(2026, 11, 15, 12, tzinfo=dt.timezone.utc)
        for model in ("kimi-k2.7-code", "kimi-k2.7-code-highspeed", "kimi-k2.6"):
            with self.subTest(model=model):
                row, ok = tm.lookup(model, when=later, provider="moonshot")
                self.assertTrue(ok)
                self.assertEqual(row, table.PRICES[model][-1])

    def test_one_rate_since_launch_and_no_page_rule_not_printed(self):
        """The page prints no effective date, no time-of-day price and no
        other spelling of any id. A dated row, an off-peak rule or an alias
        here would be invented; and the caching guide's loose spelling
        kimi-k2.7 must stay unrecognised rather than be guessed."""
        table = tm.TABLES["moonshot"]
        for model, rows in table.PRICES.items():
            with self.subTest(model=model):
                self.assertEqual([r["from"] for r in rows], [""])
                self.assertNotIn("off_peak", rows[0])
        self.assertEqual(getattr(table, "ALIASES", {}), {})
        early = dt.datetime(2026, 1, 5, 12, tzinfo=dt.timezone.utc)
        row, ok = tm.lookup("kimi-k3.1-pro", when=early, provider="moonshot")
        self.assertTrue(ok)
        self.assertEqual(row["in"], 2.00)
        _, ok = tm.lookup("kimi-k2.7", provider="moonshot")
        self.assertFalse(ok)


# Z.ai (GLM): the rules the table models. Its page reader, and the saved
# page that reader is tested on, are in test_lookup.py.

class TestZaiRules(Base):
    def cost(self, model, when=None, **kw):
        return tm.price_record(model, usage(**kw), when=when, provider="zai")

    def test_cached_input_is_the_page_figure_per_model(self):
        """Each model's cache hit is billed at its own printed rate, not the
        caching guide's "usually 50%": GLM-5.3 at $0.26, not $0.70."""
        for model, inp, cached in (("glm-5.3", 1.4, 0.26), ("glm-4.5-air", 0.2, 0.03),
                                   ("glm-5.3-flashx-legal", 0.37, 0.075)):
            with self.subTest(model=model):
                c = self.cost(model, read=1_000_000)
                self.assertAlmostEqual(c["cache_read"], cached, places=9)
                self.assertLess(c["cache_read"], inp / 2)

    def test_a_dash_for_cached_input_bills_a_hit_at_input(self):
        """GLM-4-32B-0414-128K offers no cached rate, so a cache hit costs
        what fresh input does, not nothing."""
        c = self.cost("glm-4-32b-0414-128k", read=1_000_000)
        self.assertAlmostEqual(c["cache_read"], 0.10, places=9)

    def test_no_cache_write_charge(self):
        """The page prints no write rate and its cache storage is
        "Limited-time Free" with no end date, so a cache write of either
        lifetime costs the input price and nothing more."""
        c = self.cost("glm-5.3", w5=500_000, w1=500_000)
        self.assertAlmostEqual(c["cache_write"], 1.40, places=9)

    def test_the_flash_models_are_free(self):
        """GLM-4.7-Flash and GLM-4.5-Flash are "Free" in every column, so a
        call to either costs nothing and is still recognised, not priced at
        the fallback model."""
        for model in ("glm-4.7-flash", "glm-4.5-flash"):
            with self.subTest(model=model):
                _, ok = tm.lookup(model, provider="zai")
                self.assertTrue(ok)
                c = self.cost(model, inp=1_000_000, out=1_000_000, read=1_000_000, w5=1_000_000)
                self.assertEqual(cost_of(c), 0.0)

    def test_one_output_price_whatever_the_thinking(self):
        """The page prints one output price per model, thinking or not, so
        thinking tokens must cost exactly what other output does."""
        plain = self.cost("glm-5.3", out=1_000_000)
        thinking = self.cost("glm-5.3", out=1_000_000, think=600_000)
        self.assertAlmostEqual(cost_of(plain), 4.40, places=9)
        self.assertAlmostEqual(cost_of(thinking), cost_of(plain), places=9)

    def test_no_long_context_fast_or_off_peak_price(self):
        """The API page has no prompt-length tier, no fast tier and no
        time-of-day price. The Coding Plan's 50% off-peak rule discounts plan
        credits, not API tokens, so a call outside its peak hours costs the
        same as one inside them, and a huge prompt or a fast call pays the
        ordinary rate."""
        table = tm.TABLES["zai"]
        self.assertFalse(hasattr(table, "LONG_OVER"))
        for model, rows in table.PRICES.items():
            for r in rows:
                with self.subTest(model=model):
                    self.assertIsNone(r["fast"])
                    self.assertNotIn("long", r)
                    self.assertNotIn("off_peak", r)
        peak = dt.datetime(2026, 10, 27, 7, tzinfo=dt.timezone.utc)      # 15:00 in Singapore
        off_peak = dt.datetime(2026, 10, 27, 14, tzinfo=dt.timezone.utc)  # 22:00 in Singapore
        a = self.cost("glm-5.3", when=peak, inp=1_000_000)
        b = self.cost("glm-5.3", when=off_peak, inp=1_000_000)
        self.assertAlmostEqual(cost_of(a), 1.40, places=9)
        self.assertAlmostEqual(cost_of(b), cost_of(a), places=9)
        big = self.cost("glm-5.3", inp=900_000, read=300_000)
        self.assertAlmostEqual(cost_of(big), 0.9 * 1.4 + 0.3 * 0.26, places=9)
        fast = tm.price_record("glm-5.3", usage(inp=1_000_000), speed="fast", provider="zai")
        self.assertAlmostEqual(fast["input"], 1.40, places=9)

    def test_one_rate_since_launch(self):
        """No price has changed on the page, so every model has one row in
        force from the start: an old call and today's are priced alike."""
        table = tm.TABLES["zai"]
        early = dt.datetime(2025, 1, 1, 12, tzinfo=dt.timezone.utc)
        for model, rows in table.PRICES.items():
            with self.subTest(model=model):
                self.assertEqual([r["from"] for r in rows], [""])
                row, ok = tm.lookup(model, when=early, provider="zai")
                self.assertTrue(ok)
                self.assertEqual(row, rows[0])

    def test_nothing_retired_and_no_alias(self):
        """No GLM text model has left the page or carries a retirement
        notice, and the page's names are the ids in lowercase. A RETIRED
        entry would stop --check-prices expecting a current model; an alias
        would map a name the maker never published."""
        table = tm.TABLES["zai"]
        self.assertEqual(getattr(table, "RETIRED", {}), {})
        self.assertEqual(getattr(table, "ALIASES", {}), {})
        self.assertFalse(hasattr(table, "PAGE_NAMES"))

    def test_verified_and_not_measured(self):
        """The table says when it was last read off the page, and does not
        claim a comparison with a real bill that nobody has made."""
        table = tm.TABLES["zai"]
        self.assertEqual(table.VERIFIED_ON, "2026-10-27")
        self.assertIs(table.MEASURED, False)


# MiniMax: the rules the table models. Its page reader, and the saved
# page that reader is tested on, are in test_lookup.py.

class TestMiniMaxRules(MiniMaxBase):
    def test_both_ids_are_recognised(self):
        """The ids are the API's own, as the page, the model list and the
        API guides print them; neither falls to the fallback."""
        for model in ("MiniMax-M3.1-Flash", "MiniMax-M3"):
            with self.subTest(model=model):
                self.assertFalse(self.cost(model, inp=1)["_unknown_model"])

    def test_cache_hits_bill_at_the_page_figure(self):
        """A cache hit is $0.015 a million for MiniMax-M3.1-Flash (0.1 of
        input) and $0.06 for MiniMax-M3 (0.2 of input), not a shared
        multiple."""
        # 100,000 tokens, under MiniMax-M3's 512k threshold.
        self.assertAlmostEqual(self.cost("MiniMax-M3.1-Flash", read=100_000)["cache_read"], 0.0015, places=9)
        self.assertAlmostEqual(self.cost("MiniMax-M3", read=100_000)["cache_read"], 0.006, places=9)

    def test_a_cache_write_bills_as_input(self):
        """MiniMax prints no write price; new input tokens, cache writes
        included, bill at the standard input price."""
        for model, inp in (("MiniMax-M3.1-Flash", 0.15), ("MiniMax-M3", 0.30)):
            with self.subTest(model=model):
                c = self.cost(model, w5=50_000, w1=50_000)
                self.assertAlmostEqual(c["cache_write"], 0.1 * inp, places=9)

    def test_one_output_price_whatever_the_thinking(self):
        """The page prints one output price per model: thinking tokens are
        part of output and add nothing on top."""
        c = self.cost("MiniMax-M3.1-Flash", out=M, think=M // 2)
        self.assertAlmostEqual(cost_of(c), 0.60, places=9)

    def test_the_long_tier_starts_over_512000_prompt_tokens(self):
        """MiniMax-M3 at 512,000 prompt tokens pays the up-to-512k rates; at
        512,001 the whole request pays the over-512k rates ($0.60 in, $2.40
        out, $0.12 a cache hit), and cache hits count towards the length."""
        at = self.cost("MiniMax-M3", inp=512_000, out=M)
        self.assertAlmostEqual(at["input"], 0.512 * 0.30, places=9)
        self.assertAlmostEqual(at["output"], 1.20, places=9)
        over = self.cost("MiniMax-M3", inp=1, read=512_000, out=M)
        self.assertAlmostEqual(over["output"], 2.40, places=9)
        self.assertAlmostEqual(over["cache_read"], 0.512 * 0.12, places=9)
        self.assertAlmostEqual(over["input"], 0.60 / M, places=12)

    def test_flash_has_no_long_tier(self):
        """MiniMax-M3.1-Flash has one flat price at any prompt length."""
        c = self.cost("MiniMax-M3.1-Flash", inp=900_000, out=M)
        self.assertAlmostEqual(c["input"], 0.9 * 0.15, places=9)
        self.assertAlmostEqual(c["output"], 0.60, places=9)

    def test_priority_is_the_fast_price_with_its_cache_and_long_tier(self):
        """A MiniMax-M3 call recorded as priority pays the Priority tab: $0.45
        in, $1.80 out, $0.09 a cache hit, and over 512k $0.90, $3.60 and
        $0.18, every figure the tab prints."""
        c = self.cost("MiniMax-M3", speed="fast", inp=M, out=M, read=M)
        self.assertAlmostEqual(c["input"], 0.45 * 2, places=9)
        self.assertAlmostEqual(c["output"], 1.80 * 2, places=9)
        self.assertAlmostEqual(c["cache_read"], 0.09 * 2, places=9)
        c = self.cost("MiniMax-M3", speed="fast", inp=100_000, out=M, read=100_000)
        self.assertAlmostEqual(c["input"], 0.1 * 0.45, places=9)
        self.assertAlmostEqual(c["output"], 1.80, places=9)
        self.assertAlmostEqual(c["cache_read"], 0.1 * 0.09, places=9)

    def test_flash_priority_prices_at_standard(self):
        """The page prints no Priority row for MiniMax-M3.1-Flash, so a call
        recorded as priority is not given a figure the page does not print."""
        fast = self.cost("MiniMax-M3.1-Flash", speed="fast", inp=M, out=M)
        standard = self.cost("MiniMax-M3.1-Flash", inp=M, out=M)
        self.assertAlmostEqual(cost_of(fast), cost_of(standard), places=12)
        self.assertAlmostEqual(cost_of(standard), 0.75, places=9)

    def test_web_search_is_a_cent_a_request(self):
        """The web_search server tool is $0.01 a request on the page."""
        c = self.cost("MiniMax-M3", searches=3)
        self.assertAlmostEqual(c["web_search"], 0.03, places=9)

    def test_an_unknown_id_prices_at_minimax_m3_and_is_flagged(self):
        """An id the table lacks and no lookup has priced (MiniMax-M2.7, for
        one, which existing users can call until 18 November 2026 but no
        current MiniMax page prices) is priced at the fallback, MiniMax-M3,
        and flagged as unrecognised, never passed off as its own price."""
        c = self.cost("MiniMax-M2.7", inp=100_000)
        self.assertTrue(c["_unknown_model"])
        self.assertAlmostEqual(c["input"], 0.1 * 0.30, places=9)

    def test_one_rate_since_launch(self):
        """The page prints no effective date, so each model has one row,
        from launch, and no off-peak or dated price."""
        for model, rows in minimax.PRICES.items():
            with self.subTest(model=model):
                self.assertEqual([r["from"] for r in rows], [""])
                self.assertNotIn("off_peak", rows[0])


# Xiaomi MiMo: the rules the table models. Its page reader, and the saved
# page that reader is tested on, are in test_lookup.py.

class TestMimoRules(WithMimo):
    def cost(self, model, **kw):
        return tm.price_record(model, usage(**kw), provider="mimo")

    def test_input_output_and_cache_hit_are_as_printed(self):
        """A cache hit bills at 'Input (Cache Hit)', every other prompt token
        at 'Input (Cache Miss)' and output at 'Output', for each model."""
        for model, (inp, out, cached) in MIMO_ON_THE_PAGE.items():
            with self.subTest(model=model):
                c = self.cost(model, inp=1_000_000, out=1_000_000, read=1_000_000)
                self.assertFalse(c["_unknown_model"])
                self.assertAlmostEqual(c["input"], inp, places=9)
                self.assertAlmostEqual(c["output"], out, places=9)
                self.assertAlmostEqual(c["cache_read"], cached, places=9)

    def test_cache_write_is_ordinary_input(self):
        """'Cache Write: Limited-time Free' has no end date and MiMo's API
        reports no write count, so a write a log does carry is priced as an
        ordinary cache-miss input token, never at a premium and never free."""
        c = self.cost("mimo-v2.6-pro", w5=1_000_000, w1=1_000_000)
        self.assertAlmostEqual(c["cache_write"], 2 * 0.435, places=9)

    def test_web_search_is_five_dollars_per_thousand(self):
        """The overseas 'Internet Connectivity Service' is $5 per 1,000 calls,
        billed apart from tokens."""
        c = self.cost("mimo-v2.6-flash", searches=1000)
        self.assertAlmostEqual(c["web_search"], 5.0, places=9)
        self.assertAlmostEqual(cost_of(c), 5.0, places=9)

    def test_ultraspeed_is_its_own_model_not_fast_mode(self):
        """mimo-v2.6-pro-ultraspeed is a separate id at ten times
        mimo-v2.6-pro's prices. No row has a fast price, so a call recorded
        as fast on mimo-v2.6-pro is priced at mimo-v2.6-pro's own rates."""
        self.assertTrue(all(r["fast"] is None for rows in mimo.PRICES.values() for r in rows))
        fast = tm.price_record("mimo-v2.6-pro", usage(inp=1_000_000), speed="fast", provider="mimo")
        self.assertAlmostEqual(fast["input"], 0.435, places=9)
        self.assertAlmostEqual(self.cost("mimo-v2.6-pro-ultraspeed", inp=1_000_000)["input"], 4.35,
                               places=9)

    def test_no_long_context_surcharge(self):
        """The page prints one price per model whatever the prompt length, so
        a prompt near the 1M token window costs the same per token."""
        self.assertFalse(any("long" in r for rows in mimo.PRICES.values() for r in rows))
        self.assertFalse(hasattr(mimo, "LONG_OVER"))
        c = self.cost("mimo-v2.6-flash", inp=900_000, read=90_000)
        self.assertAlmostEqual(c["input"], 0.9 * 0.14, places=9)
        self.assertAlmostEqual(c["cache_read"], 0.09 * 0.0028, places=9)

    def test_one_output_price_whatever_the_thinking(self):
        """The page prints one output price, so reasoning tokens inside the
        output count cost nothing extra."""
        plain = self.cost("mimo-v2.6-pro", out=1_000_000)
        thinking = self.cost("mimo-v2.6-pro", out=1_000_000, think=600_000)
        self.assertAlmostEqual(cost_of(plain), cost_of(thinking), places=9)
        self.assertAlmostEqual(cost_of(plain), 0.87, places=9)

    def test_an_unknown_id_is_priced_at_the_fallback_and_flagged(self):
        """An id the table does not know is priced at mimo-v2.6-pro, the
        dearest standard model, and flagged as unknown."""
        c = self.cost("mimo-v9-unknown", inp=1_000_000)
        self.assertTrue(c["_unknown_model"])
        self.assertAlmostEqual(c["input"], 0.435, places=9)


# Two engine changes agreed on 2 November 2026: a web search rate that
# starts at a stated instant, and the Priority figures expected_rates() gives
# for a fast row.
#
# Every figure is invented for the test or read from a table; no real usage.

# DeepSeek starts billing Claude Code's searches at 00:00 Beijing time on
# 1 November 2026, which is this instant.
WEB_SEARCH_START = dt.datetime(2026, 10, 31, 16, 0, tzinfo=UTC)


def search_cost(when, provider="deepseek", model="deepseek-flash", searches=1):
    return tm.price_record(model, usage(inp=1, searches=searches), when=when,
                           provider=provider)


class TestDatedWebSearchRate(Base):
    """A table can say when its web search rate starts, and a call's searches
    are priced at the rate in force at the call's own timestamp."""

    def test_a_deepseek_search_before_the_start_is_free_and_after_it_is_charged(self):
        """Guards against charging the searches DeepSeek gave away before
        billing began, and against missing the ones after: one undated
        WEB_SEARCH_PER_1K charged every call alike, so DeepSeek's was left
        at 0.0 and every search after 31 October 2026 16:00 UTC was free."""
        before = search_cost(WEB_SEARCH_START - dt.timedelta(seconds=1))
        self.assertEqual(before["web_search"], 0.0)
        for when in (WEB_SEARCH_START, WEB_SEARCH_START + dt.timedelta(seconds=1)):
            c = search_cost(when)
            self.assertAlmostEqual(c["web_search"], 0.00075, places=12)
            # The counterfactual with no caching pays for the search too.
            self.assertAlmostEqual(c["_no_cache"] - before["_no_cache"], 0.00075, places=12)

    def test_the_start_is_an_instant_not_a_local_day(self):
        """Guards against dating a search by the local day, as rate_on()
        dates token rates: billing starts at 16:00 UTC on 31 October, which
        is midnight in Beijing, so a local-day reading would charge or free
        hours of searches depending on the machine's time zone."""
        beijing = dt.timezone(dt.timedelta(hours=8))
        self.assertEqual(search_cost(dt.datetime(2026, 10, 31, 23, 59, 59,
                                                 tzinfo=beijing))["web_search"], 0.0)
        self.assertAlmostEqual(search_cost(dt.datetime(2026, 11, 1, 0, 0,
                                                       tzinfo=beijing))["web_search"],
                               0.00075, places=12)

    def test_a_timestamp_with_only_a_date_never_charges_a_free_search(self):
        """Guards the boundary for a call whose timestamp has no time: it is
        read as 00:00 UTC, so a call dated 31 October 2026 stays free."""
        when = tm.parse_time("2026-10-31")
        self.assertEqual(when, dt.datetime(2026, 10, 31, tzinfo=UTC))
        self.assertEqual(search_cost(when)["web_search"], 0.0)

    def test_a_call_with_no_timestamp_and_current_rates_take_the_rate_now(self):
        """Guards that a call with no timestamp, and every call under
        --current-rates, takes the search rate in force now, as rate_on()
        does for token rates, rather than the oldest entry."""
        self.assertAlmostEqual(search_cost(None)["web_search"], 0.00075, places=12)
        tm.CURRENT_RATES.append(True)
        self.assertAlmostEqual(search_cost(WEB_SEARCH_START - dt.timedelta(days=30))["web_search"],
                               0.00075, places=12)

    def test_the_ledger_keeps_the_time_a_search_is_priced_by(self):
        """Guards that a call read back from the ledger prices its searches
        as it did when read fresh: the row keeps the call's full time."""
        for when in (WEB_SEARCH_START - dt.timedelta(seconds=1), WEB_SEARCH_START):
            row = tm.usage_to_row("m", when, "deepseek-flash", "p", "s",
                                  usage(inp=1, searches=3), provider="deepseek")
            again = tm.price_record("deepseek-flash", tm.row_to_usage(row),
                                    when=tm.parse_time(row["t"]), provider="deepseek")
            self.assertEqual(again["web_search"], search_cost(when, searches=3)["web_search"])

    def test_a_table_with_only_the_undated_constant_prices_as_before(self):
        """Guards every table that states one undated figure: its searches
        cost WEB_SEARCH_PER_1K whenever the call was made, as before the
        dated list existed."""
        for when in (None, dt.datetime(2020, 1, 1, tzinfo=UTC), WEB_SEARCH_START,
                     dt.datetime(2030, 1, 1, tzinfo=UTC)):
            c = search_cost(when, provider="anthropic", model="claude-opus-5", searches=2)
            self.assertAlmostEqual(c["web_search"], 2 * 10.0 / 1000, places=12)
        for provider, table in tm.TABLES.items():
            if getattr(table, "WEB_SEARCH_RATES", None):
                continue
            for when in (None, WEB_SEARCH_START - dt.timedelta(seconds=1), WEB_SEARCH_START):
                with self.subTest(provider=provider, when=when):
                    self.assertEqual(tm.web_search_per_1k(table, when), table.WEB_SEARCH_PER_1K)

    def test_a_dated_list_is_ordered_in_utc_and_ends_at_the_constant(self):
        """Guards a dated list a table can get wrong: entries out of order,
        a start that is not a UTC instant, or a WEB_SEARCH_PER_1K that no
        longer matches the newest entry, which is the rate in force now."""
        dated = {p: t for p, t in tm.TABLES.items() if getattr(t, "WEB_SEARCH_RATES", None)}
        self.assertIn("deepseek", dated)
        for provider, table in dated.items():
            with self.subTest(provider=provider):
                rates = table.WEB_SEARCH_RATES
                starts = [r["from"] for r in rates if r["from"]]
                for s in starts:
                    self.assertTrue(s.endswith("Z"), s)
                    tm.parse_time(s)
                parsed = [tm.parse_time(s) for s in starts]
                self.assertEqual(parsed, sorted(parsed))
                self.assertEqual(rates[-1]["per_1k"], table.WEB_SEARCH_PER_1K)

    def test_a_dated_list_starts_with_an_entry_for_always(self):
        """Guards web_search_per_1k() charging a rate before its own start:
        a call earlier than every start takes the first entry, so a list
        whose first entry was dated ahead (2027, say) charged 2026 searches
        at it. Every dated list must open with "" (always), as DeepSeek's
        opens with its free searches, and only the first entry may."""
        dated = {p: t for p, t in tm.TABLES.items() if getattr(t, "WEB_SEARCH_RATES", None)}
        self.assertIn("deepseek", dated)
        for provider, table in dated.items():
            with self.subTest(provider=provider):
                froms = [r["from"] for r in table.WEB_SEARCH_RATES]
                self.assertEqual(froms[0], "")
                self.assertNotIn("", froms[1:])


# The name translation: host and harness spellings of a model priced at the
# maker's table and id (pricing/names.py, maker_name() in the engine).

NAMES_WHEN = "2026-10-20T10:00:00Z"


# One OpenRouter call to an open-weight model, in the import format.
OPENROUTER_K3 = {"id": "or-1", "timestamp": NAMES_WHEN, "provider": "openrouter",
                 "model": "moonshotai/kimi-k3", "input": 1000, "cache_read": 9000, "output": 500}


class NamesBase(Base):
    def imported(self, *calls):
        """An import file holding these calls, registered as --import would."""
        path = os.path.join(self.tmp, "calls.jsonl")
        with open(path, "w") as f:
            f.write("".join(json.dumps(c) + "\n" for c in calls))
        tm._IMPORTS.append(path)
        return path

    def events(self, ledger=False):
        return list(tm.iter_events(tm.transcripts(), ledger=ledger))

    def maker_cost(self, ev, provider, model):
        """What the event's tokens cost at this table and id, priced directly."""
        tokens = ev["cost"]["_tokens"]
        usage = {"input_tokens": tokens["input"], "output_tokens": tokens["output"],
                 "cache_read_input_tokens": tokens["cache_read"]}
        return tm.price_record(model, usage, "standard", ev["when"], provider)


class TestHostServedOpenWeights(NamesBase):
    def test_openrouter_kimi_k3_prices_at_moonshots_table(self):
        """Guards an open-weight model served by a host being priced at the
        host's rate, or at nothing, instead of its maker's. OpenRouter records
        moonshotai/kimi-k3; the call must be priced from Moonshot's table as
        kimi-k3, recognised, with no online lookup involved."""
        self.imported(OPENROUTER_K3)
        [ev] = self.events()
        self.assertEqual((ev["provider"], ev["model"]), ("moonshot", "kimi-k3"))
        self.assertEqual(ev["source"], "import")
        self.assertTrue(tm.lookup("kimi-k3", ev["when"], "moonshot")[1])
        want = self.maker_cost(ev, "moonshot", "kimi-k3")
        self.assertGreater(cost_of(want), 0)
        self.assertEqual(ev["cost"], want)

    def test_kimi_code_bare_k3_is_moonshots_kimi_k3_for_that_harness_only(self):
        """Guards Kimi Code's bare "k3" (the model as sent, never the alias
        kimi-code/k3) pricing at Moonshot's fallback as an unrecognised id,
        and guards the opposite mistake: another harness's "k3" being caught
        by a mapping that belongs to Kimi Code alone."""
        self.assertEqual(tm.maker_name("kimi-code", "moonshot", "k3"), ("moonshot", "kimi-k3"))
        self.assertEqual(tm.maker_name("import", "moonshot", "k3"), ("moonshot", "k3"))
        self.assertEqual(tm.maker_name("opencode", "moonshot", "k3"), ("moonshot", "k3"))
        self.assertFalse(tm.lookup("k3", None, "moonshot")[1])

    def test_status_line_session_cost_uses_the_makers_name_too(self):
        """Guards the status line's session cost (session_totals()) pricing a
        host's spelling differently from every report, which go through
        iter_events(): both must price OpenRouter's moonshotai/kimi-k3 as
        Moonshot's kimi-k3."""
        path = self.imported(OPENROUTER_K3)
        [ev] = self.events()
        tm.transcripts()
        total, _ = tm.session_totals(path)
        want = cost_of(self.maker_cost(ev, "moonshot", "kimi-k3"))
        self.assertGreater(want, 0)
        self.assertAlmostEqual(total, want, places=12)
        self.assertAlmostEqual(total, cost_of(ev["cost"]), places=12)


class TestUnmappedIds(NamesBase):
    def test_an_unmappable_id_stays_with_the_lookup(self):
        """Guards the translation guessing. OpenRouter's
        anthropic/claude-sonnet-4.5 is a frontier model bought per token
        through a host, which keeps the host's price: it is not in the map,
        so it passes through as recorded and is priced by the online lookup's
        saved rate, labelled as looked up."""
        self.assertEqual(tm.maker_name("import", "openrouter", "anthropic/claude-sonnet-4.5"),
                         ("openrouter", "anthropic/claude-sonnet-4.5"))
        with open(tm.PRICE_CACHE, "w") as f:
            json.dump({"fetched": {"openrouter:anthropic/claude-sonnet-4.5": {
                "rows": [{"from": "", "in": 3.0, "out": 15.0, "cache_read_mult": 0.1,
                          "fast": None}],
                "via": "a saved lookup", "checked": "2026-10-20"}}, "misses": {}}, f)
        self.imported(dict(OPENROUTER_K3, model="anthropic/claude-sonnet-4.5"))
        [ev] = self.events()
        self.assertEqual((ev["provider"], ev["model"]),
                         ("openrouter", "anthropic/claude-sonnet-4.5"))
        row, recognised = tm.lookup(ev["model"], ev["when"], ev["provider"])
        self.assertTrue(recognised)
        self.assertEqual(row["_via"], "a saved lookup")
        # 1,000 input at $3, 9,000 cache reads at $0.30, 500 output at $15.
        self.assertAlmostEqual(cost_of(ev["cost"]), 0.003 + 0.0027 + 0.0075, places=12)

    def test_an_id_its_recorded_table_lists_is_never_moved(self):
        """Guards the translation changing a price the engine already gets
        right: an id the recorded table lists (exactly, by alias or by
        snapshot) keeps that table's price even if a mapping names it."""
        bad = {("", "moonshot", "kimi-k3"): ("zai", "glm-5.3"),
               ("", "openai", "gpt-4-turbo"): ("zai", "glm-5.3")}
        with unittest.mock.patch.dict(tm.NAMES, bad):
            self.assertEqual(tm.maker_name("import", "moonshot", "kimi-k3"), ("moonshot", "kimi-k3"))
            self.assertEqual(tm.maker_name("codex", "openai", "gpt-4-turbo"),
                             ("openai", "gpt-4-turbo"))


class TestFreshAndLedger(NamesBase):
    def test_the_same_call_prices_the_same_fresh_and_from_the_ledger(self):
        """Guards a call costing one thing while its log exists and another
        once only the ledger holds it. The ledger keeps the spelling as
        recorded (moonshotai/kimi-k3 through openrouter), and a row read back
        is translated exactly as a fresh record is, so a fixture ledger row
        and the same call read fresh both price as Moonshot's kimi-k3."""
        self.imported(OPENROUTER_K3)
        [fresh] = self.events(ledger=False)

        with open(self.ledger, "w") as f:
            f.write(json.dumps({"i": "or-1", "t": NAMES_WHEN, "m": "moonshotai/kimi-k3",
                                "pv": "openrouter", "a": "import",
                                "in": 1000, "r": 9000, "o": 500}) + "\n")
        tm._IMPORTS.clear()
        [restored] = self.events(ledger=True)
        self.assertTrue(restored.get("ledger_only"))
        self.assertEqual((restored["provider"], restored["model"]), ("moonshot", "kimi-k3"))
        self.assertEqual(restored["cost"], fresh["cost"])

    def test_the_ledger_keeps_the_spelling_as_recorded(self):
        """Guards the translation being written into the ledger, which would
        freeze today's map into history: a mapping corrected later could
        never reach rows already written. The row keeps the recorded model
        and provider."""
        self.imported(OPENROUTER_K3)
        self.events(ledger=True)
        [row] = tm.read_ledger().values()
        self.assertEqual((row["m"], row["pv"]), ("moonshotai/kimi-k3", "openrouter"))


class TestUnregisteredTables(NamesBase):
    def test_a_mapping_to_an_unregistered_table_passes_through(self):
        """Guards a spelling recorded before its table is registered (MiniMax
        and MiMo until 2 November 2026) raising an error or pricing at another
        table: it passes through as recorded, without an error, and starts
        to map once the table is in TABLES."""
        spelling = ("", "openrouter", "example/open-model")
        with unittest.mock.patch.dict(tm.NAMES, {spelling: ("example", "open-model")}):
            self.assertNotIn("example", tm.TABLES)
            self.assertEqual(tm.maker_name("import", "openrouter", "example/open-model"),
                             ("openrouter", "example/open-model"))
            table = types.SimpleNamespace(
                PROVIDER="example", SNAPSHOT=r"(?!)",
                PRICES={"open-model": [{"from": "", "in": 1.0, "out": 2.0,
                                        "cache_read_mult": 0.1, "fast": None}]})
            with unittest.mock.patch.dict(tm.TABLES, {"example": table}):
                self.assertEqual(tm.maker_name("import", "openrouter", "example/open-model"),
                                 ("example", "open-model"))

    def test_minimax_and_mimo_spellings_wait_for_their_tables(self):
        """Guards OpenRouter's minimax/minimax-m3 and xiaomi/mimo-v2.6-pro
        failing or mispricing while their tables are not registered: each
        passes through unchanged until its table is in TABLES, then maps."""
        for spelling, target in ((("", "openrouter", "minimax/minimax-m3"), "minimax"),
                                 (("", "openrouter", "xiaomi/mimo-v2.6-pro"), "mimo")):
            with self.subTest(spelling=spelling):
                self.assertEqual(tm.NAMES[spelling][0], target)
                got = tm.maker_name(*spelling)
                if target in tm.TABLES:
                    self.assertEqual(got, tm.NAMES[spelling])
                else:
                    self.assertEqual(got, spelling[1:])


class TestTheMap(unittest.TestCase):
    def test_every_entry_names_an_id_its_table_lists(self):
        """Guards a mapping that is silently skipped because its maker's table
        renamed or dropped the id it points at: every entry whose table is
        registered must point at an id that table lists, and no target may
        itself be a key, so translating twice changes nothing."""
        for key, (table, mid) in tm.NAMES.items():
            with self.subTest(key=key):
                self.assertEqual(len(key), 3)
                if table in tm.TABLES:
                    self.assertTrue(tm.table_name(tm.TABLES[table], mid), (table, mid))
                self.assertNotIn((key[0], table, mid), tm.NAMES)
                self.assertNotIn(("", table, mid), tm.NAMES)


class TestZaiWebSearch(Base):
    def test_one_zai_web_search_costs_one_cent(self):
        """Guards Z.ai web searches being billed at nothing (the table's old
        WEB_SEARCH_PER_1K of 0.0) or at another maker's rate. The page's
        "Built-in Tools" table prices web search at $0.01 per use, so one
        logged search with no tokens costs exactly $0.01."""
        c = tm.price_record("glm-5.3", usage(searches=1), provider="zai")
        self.assertAlmostEqual(c["web_search"], 0.01, places=9)
        self.assertAlmostEqual(cost_of(c), 0.01, places=9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
