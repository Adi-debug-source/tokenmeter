"""Pricing: the rate a call is charged, from the tables and the rules
around them: dated rows, today's rates, long context, fast mode, and reading
a dollar figure off a provider's page.
"""

import datetime as dt
import json
import os
import re
import unittest

from helpers import Base, cli, cost_of, tm, usage


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
