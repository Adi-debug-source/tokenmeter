"""Every published rate, typed from the provider's own pricing page.

Each figure here was read off the page, not copied from the tables in
pricing/, so a slip in either one fails. A rate change is a new dated row in
the table and a new figure here; see pricing/README.md.
"""

import datetime as dt
import os
import unittest

from helpers import FIXTURES, Base, cost_of, noon, slurp, tm, usage


class TestPublishedRates(Base):
    """The whole table against platform.claude.com, checked 11 September 2026.
    Sonnet 5.5 added from the same page on 6 October 2026; its cheaper cache
    reads and Haiku 5.5 read off it on 15 October 2026.

    Every figure here was read off Anthropic's pricing page, not recalled. If
    one of these fails, either a rate moved (add a dated entry, do not edit the
    old one) or someone mistyped the table.
    """

    # model: (base input, output, cache hit $/MTok)
    OFFICIAL = {
        "claude-fable-5-1": (10, 50, 0.25), "claude-mythos-5-1": (10, 50, 0.25),
        "claude-fable-5": (10, 50, 1.00), "claude-mythos-5": (10, 50, 1.00),
        "claude-opus-5-5": (4, 20, 0.20),
        "claude-opus-5": (5, 25, 0.50), "claude-opus-4-8": (5, 25, 0.50),
        "claude-opus-4-7": (5, 25, 0.50), "claude-opus-4-6": (5, 25, 0.50),
        "claude-opus-4-5": (5, 25, 0.50), "claude-opus-4-1": (15, 75, 1.50),
        "claude-opus-4": (15, 75, 1.50), "claude-sonnet-5": (2, 10, 0.20),
        "claude-sonnet-5-5": (2, 10, 0.10),
        "claude-sonnet-4-6": (3, 15, 0.30), "claude-sonnet-4-5": (3, 15, 0.30),
        "claude-sonnet-4": (3, 15, 0.30), "claude-haiku-5-5": (0.10, 0.50, 0.01),
        "claude-haiku-4-5": (1, 5, 0.10), "claude-haiku-3-5": (0.8, 4, 0.08),
    }

    def test_every_rate_matches_the_pricing_page(self):
        self.assertEqual(set(tm.PRICES), set(self.OFFICIAL), "table and pinned list differ")
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model)
                self.assertTrue(known, f"{model} falls back to Opus rates")
                self.assertEqual(row["in"], inp)
                self.assertEqual(row["out"], out)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_sonnet_5_5_cache_reads_were_halved_on_7_october_2026(self):
        """Anthropic's release notes, 7 October 2026: Sonnet 5.5 cache reads
        cut from $0.20 to $0.10 per million, 0.05x input instead of 0.1x.
        Cache writes and every other price unchanged. A call keeps the price
        of its own day, and a lookup with no date gives today's."""
        u = usage(inp=1_000_000, read=1_000_000, w5=1_000_000, w1=1_000_000, out=1_000_000)
        before = tm.price_record("claude-sonnet-5-5", u, when=noon("2026-10-06"))
        after = tm.price_record("claude-sonnet-5-5", u, when=noon("2026-10-07"))
        self.assertAlmostEqual(before["cache_read"], 0.20, places=9)
        self.assertAlmostEqual(after["cache_read"], 0.10, places=9)
        for c in (before, after):
            self.assertAlmostEqual(c["input"], 2.00, places=9)
            self.assertAlmostEqual(c["cache_write"], 2.50 + 4.00, places=9)
            self.assertAlmostEqual(c["output"], 10.00, places=9)
        row, known = tm.lookup("claude-sonnet-5-5")
        self.assertTrue(known)
        self.assertAlmostEqual(row["in"] * row["cache_read_mult"], 0.10, places=9)

    def test_haiku_5_5_is_priced_by_prompt_length(self):
        """Claude Haiku 5.5, launched 7 October 2026, typed from the page on
        15 October 2026. Up to 100,000 prompt tokens: $0.10 in, $0.125 a
        5-minute write, $0.20 a 1-hour write, $0.01 a cache hit, $0.50 out.
        Over 100,000: $0.50, $0.625, $1, $0.05 and $2.50. A request's prompt
        length counts all of its input tokens, cache reads and writes too."""
        up_to = {"in": 0.10, "w5": 0.125, "w1": 0.20, "hit": 0.01, "out": 0.50}
        over = {"in": 0.50, "w5": 0.625, "w1": 1.00, "hit": 0.05, "out": 2.50}
        # 90,000 of each prompt is cache: exactly 100,000, then 100,001.
        for inp, rate in ((10_000, up_to), (10_001, over)):
            with self.subTest(prompt=inp + 90_000):
                c = tm.price_record("claude-haiku-5-5",
                                    usage(inp=inp, read=60_000, w5=20_000, w1=10_000, out=1_000))
                self.assertFalse(c["_unknown_model"])
                self.assertAlmostEqual(c["input"], inp * rate["in"] / 1e6, places=12)
                self.assertAlmostEqual(c["cache_read"], 60_000 * rate["hit"] / 1e6, places=12)
                self.assertAlmostEqual(c["cache_write"],
                                       (20_000 * rate["w5"] + 10_000 * rate["w1"]) / 1e6, places=12)
                self.assertAlmostEqual(c["output"], 1_000 * rate["out"] / 1e6, places=12)
        # Cache reads alone can carry a request over the line.
        c = tm.price_record("claude-haiku-5-5", usage(inp=1, read=100_000, out=1_000_000))
        self.assertAlmostEqual(c["output"], 2.50, places=9)

    def test_cache_write_multipliers(self):
        """1.25x for 5-minute, 2x for 1-hour, per the pricing page."""
        self.assertEqual(tm.CACHE_WRITE_5M_MULT, 1.25)
        self.assertEqual(tm.CACHE_WRITE_1H_MULT, 2.0)

    def test_web_search_is_ten_dollars_per_thousand(self):
        self.assertEqual(tm.WEB_SEARCH_PER_1K, 10.0)

    def test_fast_mode_rates(self):
        """Opus 5.5, 5 and 4.8 only. 4.7 errors on fast; 4.6 runs standard."""
        self.assertEqual(tm.lookup("claude-opus-5-5")[0]["fast"], (8.0, 40.0))
        self.assertEqual(tm.lookup("claude-opus-5")[0]["fast"], (10.0, 50.0))
        self.assertEqual(tm.lookup("claude-opus-4-8")[0]["fast"], (10.0, 50.0))
        self.assertIsNone(tm.lookup("claude-opus-4-7")[0]["fast"])
        self.assertIsNone(tm.lookup("claude-sonnet-5")[0]["fast"])
        self.assertIsNone(tm.lookup("claude-sonnet-5-5")[0]["fast"])

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


class TestOtherProvidersPublishedRates(Base):
    """Every rate in the OpenAI, Google and xAI tables, typed from the pages.

    Read on 26 September 2026 from developers.openai.com/api/docs/pricing and
    its model pages, ai.google.dev/gemini-api/docs/pricing and
    docs.x.ai/developers/pricing. gpt-6.1-sol added from the OpenAI pages on
    6 October 2026. Typed here separately from the tables, so a
    slip in either one fails. A model with no cached rate is listed with its
    input rate: no discount. A retired model keeps its last published rate.
    """

    OPENAI = {
        "gpt-6-astra": (10, 50, 1.00), "gpt-6.1-sol": (2, 10, 0.10), "gpt-6-sol": (2, 10, 0.20), "gpt-6-luna": (0.10, 0.50, 0.01),
        "gpt-5.6-sol": (4, 20, 0.40), "gpt-5.6-terra": (2, 12, 0.20), "gpt-5.6-luna": (0.20, 1.20, 0.02),
        "gpt-5.5": (5, 30, 0.50), "gpt-5.5-pro": (30, 180, 30), "gpt-5.4": (2.50, 15, 0.25),
        "gpt-5.4-pro": (30, 180, 30), "gpt-5.4-mini": (0.75, 4.50, 0.075), "gpt-5.4-nano": (0.20, 1.25, 0.02),
        "gpt-5.3-codex": (1.75, 14, 0.175), "gpt-5.2-codex": (1.75, 14, 0.175),
        "gpt-5.1-codex-max": (1.25, 10, 0.125), "gpt-5.1-codex": (1.25, 10, 0.125),
        "gpt-5.1-codex-mini": (0.25, 2, 0.025), "gpt-5-codex": (1.25, 10, 0.125),
        "codex-mini-latest": (1.50, 6, 0.375), "gpt-5.2": (1.75, 14, 0.175), "gpt-5.2-pro": (21, 168, 21),
        "gpt-5.1": (1.25, 10, 0.125), "gpt-5": (1.25, 10, 0.125), "gpt-5-mini": (0.25, 2, 0.025),
        "gpt-5-nano": (0.05, 0.40, 0.005), "gpt-5-pro": (15, 120, 15), "gpt-4.1": (2, 8, 0.50),
        "gpt-4.1-mini": (0.40, 1.60, 0.10), "gpt-4.1-nano": (0.10, 0.40, 0.025), "gpt-4o": (2.50, 10, 1.25),
        "gpt-4o-2024-05-13": (5, 15, 5), "gpt-4o-mini": (0.15, 0.60, 0.075), "o3": (2, 8, 0.50),
        "o3-pro": (20, 80, 20), "o4-mini": (1.10, 4.40, 0.275), "o3-mini": (1.10, 4.40, 0.55),
        "o1": (15, 60, 7.50), "o1-pro": (150, 600, 150),
    }
    GOOGLE = {
        "gemini-3.5-flash": (1.50, 9, 0.15), "gemini-3.5-flash-lite": (0.30, 2.50, 0.03),
        "gemini-3.1-flash-lite": (0.25, 1.50, 0.025), "gemini-3.1-pro-preview": (2, 12, 0.20),
        "gemini-3-flash-preview": (0.50, 3, 0.05), "gemini-2.5-pro": (1.25, 10, 0.125),
        "gemini-2.5-flash": (0.30, 2.50, 0.03), "gemini-2.5-flash-lite": (0.10, 0.40, 0.01),
        "gemini-2.5-computer-use-preview-10-2025": (1.25, 10, 1.25),
    }
    XAI = {
        "grok-4.7": (2, 6, 0.50), "grok-4.6": (2, 6, 0.50), "grok-4.5": (2, 6, 0.30),
        "grok-4.3": (1.25, 2.50, 0.20), "grok-4.20-0309-reasoning": (1.25, 2.50, 0.20),
        "grok-4.20-0309-non-reasoning": (1.25, 2.50, 0.20),
        "grok-4.20-multi-agent-0309": (1.25, 2.50, 0.20), "grok-build-0.1": (1, 2, 0.20),
    }

    def check(self, provider, official):
        table = tm.TABLES[provider].PRICES
        self.assertEqual(set(table) - {"gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"},
                         set(official), f"{provider} table and pinned list differ")
        for model, (inp, out, hit) in official.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model, provider=provider)
                self.assertTrue(known)
                self.assertAlmostEqual(row["in"], inp, places=9)
                self.assertAlmostEqual(row["out"], out, places=9)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

    def test_openai(self):
        self.check("openai", self.OPENAI)

    def test_google(self):
        self.check("google", self.GOOGLE)

    def test_xai(self):
        self.check("xai", self.XAI)

    def test_openai_cache_writes_are_billed_only_on_gpt6_and_gpt56(self):
        """1.25x input on GPT-6 and GPT-5.6; ordinary input on everything older."""
        for model, write in (("gpt-6-astra", 12.50), ("gpt-6.1-sol", 2.50), ("gpt-6-sol", 2.50), ("gpt-6-luna", 0.125),
                             ("gpt-5.6-sol", 5.00), ("gpt-5.6-terra", 2.50), ("gpt-5.6-luna", 0.25),
                             ("gpt-5", 1.25), ("gpt-5.4", 2.50)):
            with self.subTest(model=model):
                # 100K, under the 272K long-context line, which would double it.
                c = tm.price_record(model, usage(w5=100_000), provider="openai")
                self.assertAlmostEqual(c["cache_write"], write / 10, places=9)

    def test_gemini_flash_prices_change_on_new_year(self):
        """Launch price through 31 December 2026, list price from 1 January 2027."""
        before, after = noon("2026-12-31"), noon("2027-01-02")
        for model in ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"):
            with self.subTest(model=model):
                self.assertEqual(tm.lookup(model, before, "google")[0]["in"], 0.75)
                self.assertEqual(tm.lookup(model, after, "google")[0]["in"], 1.50)
                self.assertEqual(tm.lookup(model, after, "google")[0]["out"], 7.50)

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

    def test_xai_aliases_are_the_same_model(self):
        for alias, canonical in (("grok-code-fast-1", "grok-build-0.1"),
                                 ("grok-4.20", "grok-4.20-0309-reasoning"),
                                 ("grok-4.5-latest", "grok-4.5")):
            with self.subTest(alias=alias):
                row, known = tm.lookup(alias, provider="xai")
                self.assertTrue(known)
                self.assertIs(row, tm.TABLES["xai"].PRICES[canonical][0])

    def test_openai_dated_snapshot_and_its_one_exception(self):
        """gpt-5-2025-08-07 is gpt-5; gpt-4o-2024-05-13 has its own, higher price."""
        self.assertEqual(tm.lookup("gpt-5-2025-08-07", provider="openai")[0]["in"], 1.25)
        self.assertEqual(tm.lookup("gpt-4o-2024-08-06", provider="openai")[0]["in"], 2.50)
        self.assertEqual(tm.lookup("gpt-4o-2024-05-13", provider="openai")[0]["in"], 5.00)


class TestSmallerProvidersPublishedRates(Base):
    """DeepSeek, Mistral, Moonshot and Z.ai, typed from their pages on 26
    September 2026. (input, output, cached), standard or peak rates."""

    OFFICIAL = {
        "deepseek": {"deepseek-flash": (0.30, 1.20, 0.006), "deepseek-v4-pro": (1.32, 3.96, 0.044)},
        "mistral": {"mistral-large-2512": (0.5, 1.5, 0.05), "mistral-medium-3-5": (1.5, 7.5, 0.15),
                    "mistral-small-2603": (0.15, 0.6, 0.015), "ministral-14b-2512": (0.2, 0.2, 0.02),
                    "ministral-8b-2512": (0.15, 0.15, 0.015), "ministral-3b-2512": (0.1, 0.1, 0.01),
                    "codestral-2508": (0.3, 0.9, 0.03), "zai-glm-5-3": (1.4, 4.4, 0.14),
                    "zai-glm-5-2": (1.4, 4.4, 0.14)},
        "moonshot": {"kimi-k3": (3, 15, 0.30), "kimi-k2.7-code": (0.95, 4, 0.19),
                     "kimi-k2.7-code-highspeed": (1.90, 8, 0.38), "kimi-k2.6": (0.95, 4, 0.16)},
        "zai": {"glm-5.3": (1.4, 4.4, 0.26), "glm-5.3-flash": (0.15, 0.5, 0.03),
                "glm-5.3-flashx": (0.37, 1.25, 0.075), "glm-5.2": (1.4, 4.4, 0.26),
                "glm-5.1": (1.4, 4.4, 0.26), "glm-5": (1, 3.2, 0.2), "glm-4.7": (0.6, 2.2, 0.11),
                "glm-4.7-flashx": (0.07, 0.4, 0.01), "glm-4.7-flash": (0, 0, 0),
                "glm-4.6": (0.6, 2.2, 0.11), "glm-4.5": (0.6, 2.2, 0.11), "glm-4.5-x": (2.2, 8.9, 0.45),
                "glm-4.5-air": (0.2, 1.1, 0.03), "glm-4.5-airx": (1.1, 4.5, 0.22),
                "glm-4.5-flash": (0, 0, 0), "glm-4-32b-0414-128k": (0.1, 0.1, 0.1)},
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

    def test_kimi_k3_bills_cache_writes_by_lifetime(self):
        c = tm.price_record("kimi-k3", usage(w5=100_000, w1=100_000), provider="moonshot")
        self.assertAlmostEqual(c["cache_write"], 0.1 * 3.00 + 0.1 * 6.00, places=9)
        k2 = tm.price_record("kimi-k2.6", usage(w5=100_000), provider="moonshot")
        self.assertAlmostEqual(k2["cache_write"], 0.1 * 0.95, places=9)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
