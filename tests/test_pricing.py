"""Pricing: the rate a call is charged, from the tables and the rules
around them: dated rows, today's rates, long context, fast mode, and reading
a dollar figure off a provider's page.
"""

import datetime as dt
import json
import os
import re
import unittest

from helpers import Base, cli, cost_of, noon, tm, usage

M = 1_000_000
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
