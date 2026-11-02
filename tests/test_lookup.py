"""The network: the online price lookup, --check-prices and exchange rates.

Every fetch is faked, and urlopen itself refuses and counts, so nothing here
uses the network.
"""

import contextlib
import datetime as dt
import io
import json
import os
import re
import time
import unittest
import unittest.mock
import urllib.error

from helpers import (ANTHROPIC_PAGE, FIXTURES, Base, cli, cost_of, payload_of, record, slurp, terminal,
                     tm, usage)

from pricing import mimo, minimax

M = 1_000_000


class TestOnlineLookup(Base):
    """The startup check, with every fetch faked. Nothing here uses the network."""

    PAGE = ANTHROPIC_PAGE
    LITELLM = json.dumps({"deepseek/deepseek-chat": {
        "litellm_provider": "deepseek", "input_cost_per_token": 2.8e-07,
        "output_cost_per_token": 4.2e-07, "cache_read_input_token_cost": 2.8e-08}})

    def setUp(self):
        super().setUp()
        tm.ONLINE_LOOKUP[0] = True
        self.fetched = []

    def tearDown(self):
        tm.ONLINE_LOOKUP[0] = False
        super().tearDown()

    def fetch(self, url):
        self.fetched.append(url)
        if url == tm.LITELLM_URL:
            return self.LITELLM
        if "platform.claude.com" in url:
            return self.PAGE
        raise OSError("offline in tests")

    def test_a_new_model_is_priced_from_its_providers_page(self):
        done = tm.resolve_prices([("anthropic", "claude-opus-9")], fetch=self.fetch)
        self.assertEqual(done[0]["via"], "Anthropic's pricing page")
        row, known = tm.lookup("claude-opus-9")
        self.assertTrue(known)
        self.assertEqual((row["in"], row["out"]), (6.0, 30.0))
        self.assertAlmostEqual(row["cache_read_mult"], 0.1, places=9)
        c = tm.price_record("claude-opus-9", usage(inp=1_000_000))
        self.assertEqual(c["_fetched"], "Anthropic's pricing page")

    def test_other_providers_fall_back_to_the_public_price_list(self):
        done = tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        self.assertEqual(done[0]["via"], tm.LITELLM_NAME)
        c = tm.price_record("deepseek-chat", usage(inp=1_000_000, out=1_000_000), provider="deepseek")
        self.assertAlmostEqual(cost_of(c), 0.28 + 0.42, places=9)

    def test_a_saved_lookup_is_used_without_the_network(self):
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        tm._PRICE_STATE.update(loaded=False)   # a fresh run reads the saved file
        n = len(self.fetched)
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        self.assertEqual(len(self.fetched), n)
        self.assertTrue(tm.lookup("deepseek-chat", provider="deepseek")[1])

    def test_a_model_found_nowhere_is_not_looked_up_again_for_a_day(self):
        tm.resolve_prices([("anthropic", "claude-nothing-1")], fetch=self.fetch)
        n = len(self.fetched)
        tm.resolve_prices([("anthropic", "claude-nothing-1")], fetch=self.fetch)
        self.assertEqual(len(self.fetched), n)
        self.assertFalse(tm.lookup("claude-nothing-1")[1])

    def test_a_table_entry_is_never_looked_up_or_replaced(self):
        tm.resolve_prices([("anthropic", "claude-opus-5"), ("openai", "gpt-5-2025-08-07")],
                          fetch=self.fetch)
        self.assertEqual(self.fetched, [])
        self.assertNotIn("_via", tm.lookup("claude-opus-5")[0])

    def test_offline_means_no_fetch_at_all(self):
        tm.ONLINE_LOOKUP[0] = False
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        self.assertEqual(self.fetched, [])

    def test_a_changed_price_is_added_as_a_dated_entry(self):
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        entry = tm._price_cache()["fetched"]["deepseek:deepseek-chat"]
        entry["checked"] = "2020-01-01"                     # due for a recheck
        self.LITELLM = self.LITELLM.replace("2.8e-07", "5.6e-07")
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        rows = tm._price_cache()["fetched"]["deepseek:deepseek-chat"]["rows"]
        self.assertEqual([r["in"] for r in rows], [0.28, 0.56])
        self.assertEqual(rows[1]["from"], dt.date.today().isoformat())

    def test_reports_say_a_rate_was_looked_up(self):
        self.write("a.jsonl", record("msg_1", model="claude-opus-9", out=1000))
        real = tm.fetch_text
        tm.fetch_text = lambda url, timeout=8: self.fetch(url)
        try:
            overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        finally:
            tm.fetch_text = real
        self.assertFalse(unknown)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("claude-opus-9 is priced at $6 in and $30 out", notes)
        self.assertIn("not checked by hand", notes)

    def test_only_an_id_shaped_like_openais_reaches_a_model_page(self):
        """OpenAI's lookup fetches a model's own page, whose address is the
        model id. The id comes from a log or an import file, so "../x",
        "a/b", "x?y" and "x#y" were put straight into the address. Only an
        id of letters, digits, dots, hyphens and underscores is fetched; the
        rest are left for LiteLLM's list, like any other unknown model."""
        asked = []

        def fetch(url):
            asked.append(url)
            if url == tm.LITELLM_URL:
                return "{}"
            return ""       # OpenAI's main page lists nothing
        bad = ("../../../etc/passwd", "gpt/evil", "gpt-6?x=1", "gpt-6#frag", "gpt 6", "", ".hidden")
        tm.resolve_prices([("openai", m) for m in bad], fetch=fetch)
        pages = [u for u in asked if "/models/" in u]
        self.assertEqual(pages, [], pages)
        asked.clear()
        tm.resolve_prices([("openai", "gpt-9-nova_2"), ("openai", "o5")], fetch=fetch)
        self.assertEqual(sorted(u for u in asked if "/models/" in u),
                         [tm.TABLES["openai"].MODEL_PAGE_MD.format(model=m)
                          for m in ("gpt-9-nova_2", "o5")])

    def down(self, url):
        """A network that is not there."""
        self.fetched.append(url)
        raise OSError("offline in tests")

    def test_each_page_is_downloaded_once_a_run(self):
        """Every model looked up downloaded its provider's page again, and an
        unreachable source cost one timeout per model."""
        tm.resolve_prices([("anthropic", "claude-opus-9"), ("anthropic", "claude-nothing-1"),
                           ("anthropic", "claude-nothing-2")], fetch=self.fetch)
        self.assertEqual(sorted(self.fetched), sorted(set(self.fetched)))
        self.fetched.clear()
        tm.resolve_prices([("deepseek", "deepseek-x1"), ("deepseek", "deepseek-x2")],
                          fetch=self.down)
        self.assertEqual(len(self.fetched), 2, self.fetched)    # its page and LiteLLM's list
        self.assertEqual(sorted(self.fetched), sorted(set(self.fetched)))

    def test_an_unreachable_lookup_is_not_remembered_as_a_miss(self):
        """A failed fetch was saved as "found nowhere", so the model went
        unpriced for a day after the network came back."""
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.down)
        cache = tm._price_cache()
        self.assertNotIn("deepseek:deepseek-chat", cache["misses"])
        self.assertIn("deepseek:deepseek-chat", cache["failed"])
        self.assertEqual(tm.LOOKUPS, [{"provider": "deepseek", "model": "deepseek-chat",
                                       "found": False, "error": True}])
        # Not tried again for ten minutes, by this run or the next.
        for minutes, tries in ((0, 0), (9, 0), (11, 1)):
            with self.subTest(minutes=minutes):
                tm._PRICE_STATE.update(loaded=False)   # a fresh run reads the saved file
                cache = tm._price_cache()
                cache["failed"]["deepseek:deepseek-chat"] = time.time() - minutes * 60
                tm._save_price_cache()
                n = len(self.fetched)
                tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
                self.assertEqual(len(self.fetched) - n, tries * 2)
        self.assertTrue(tm.lookup("deepseek-chat", provider="deepseek")[1])
        self.assertNotIn("deepseek:deepseek-chat", tm._price_cache()["failed"])

    def test_a_failed_recheck_is_not_retried_on_every_run(self):
        """A saved rate due for its weekly recheck, with the recheck failing,
        was downloaded again on every run, because nothing recorded the try."""
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        entry = tm._price_cache()["fetched"]["deepseek:deepseek-chat"]
        entry["checked"] = "2020-01-01"                     # due for a recheck
        tm._save_price_cache()
        self.fetched.clear()
        for run in range(2):
            tm._PRICE_STATE.update(loaded=False)
            tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.down)
        self.assertEqual(len(self.fetched), 2, self.fetched)    # one run's worth
        entry = tm._price_cache()["fetched"]["deepseek:deepseek-chat"]
        self.assertEqual(entry["checked"], "2020-01-01")       # the last check that worked
        self.assertEqual([r["in"] for r in entry["rows"]], [0.28])
        self.assertTrue(tm.lookup("deepseek-chat", provider="deepseek")[1])
        # A day later it is rechecked, and a recheck that works moves the date.
        entry["tried"] -= tm.MISS_RETRY_HOURS * 3600
        tm.resolve_prices([("deepseek", "deepseek-chat")], fetch=self.fetch)
        entry = tm._price_cache()["fetched"]["deepseek:deepseek-chat"]
        self.assertEqual(entry["checked"], dt.date.today().isoformat())
        self.assertNotIn("tried", entry)

    # In the Markdoc the page has been written in since it moved to
    # aistudio.google.com (2 November 2026); it was HTML before.
    GOOGLE_PAGE = (
        '## Gemini 9 Flash  {% id="gemini-9-flash" %}\n'
        '*[`gemini-9-flash`](/docs/models/gemini-9-flash)*\n'
        '{% table %}\n'
        '* Input price\n* Free\n* $0.75\n$1.50 starting January 1, 2027\n---\n'
        '* Output price\n* Free\n* $3.75\n$7.50 starting January 1, 2027\n---\n'
        '* Context caching price\n* Free\n* $0.075\n$0.15 starting January 1, 2027\n'
        '{% /table %}\n')

    def test_a_looked_up_price_keeps_its_dates(self):
        """A page with a launch price and a later one was saved as one row at
        the later price, so every call was charged it from the first day."""
        def fetch(url):
            self.fetched.append(url)
            if url == tm.TABLES["google"].SOURCE_MD:
                return self.GOOGLE_PAGE
            raise OSError("offline in tests")
        tm.resolve_prices([("google", "gemini-9-flash")], fetch=fetch)
        rows = tm._price_cache()["fetched"]["google:gemini-9-flash"]["rows"]
        self.assertEqual([(r["from"], r["in"], r["out"]) for r in rows],
                         [("", 0.75, 3.75), ("2027-01-01", 1.50, 7.50)])
        u = usage(inp=1_000_000, out=1_000_000)
        before = dt.datetime(2026, 10, 1, 12, tzinfo=dt.timezone.utc)
        after = dt.datetime(2027, 1, 2, 12, tzinfo=dt.timezone.utc)
        self.assertAlmostEqual(cost_of(tm.price_record("gemini-9-flash", u, when=before,
                                                       provider="google")), 0.75 + 3.75)
        self.assertAlmostEqual(cost_of(tm.price_record("gemini-9-flash", u, when=after,
                                                       provider="google")), 1.50 + 7.50)

    def test_a_recheck_keeps_history_and_adds_what_the_page_dates(self):
        """Saved rows are history: a recheck adds the page's new prices after
        them and never rewrites what calls were already charged."""
        saved = [{"from": "", "in": 1.5, "out": 7.5, "cache_read_mult": 0.1}]
        found = [{"from": "", "in": 0.75, "out": 3.75, "cache_read_mult": 0.1},
                 {"from": "2027-01-01", "in": 1.5, "out": 7.5, "cache_read_mult": 0.1}]
        merged = tm._merge_rows(saved, found, "2026-10-10")
        self.assertEqual([(r["from"], r["in"]) for r in merged],
                         [("", 1.5), ("2026-10-10", 0.75), ("2027-01-01", 1.5)])
        self.assertIs(tm._merge_rows(merged, found, "2026-10-17"), merged)


class TestPageRows(Base):
    """A provider page's figures as price rows, for a model no table has."""

    def test_dated_prices_give_dated_rows(self):
        """Google's launch price and the one after it became one row at the
        later price."""
        r = {"in": 1.50, "out": 7.50, "cached": 0.15,
             "_history": [{"from": "", "in": 0.75, "out": 3.75, "cached": 0.075},
                          {"from": "2027-01-01", "in": 1.50, "out": 7.50, "cached": 0.15}]}
        rows = tm.rows_from_page(r, tm.TABLES["google"])
        self.assertEqual([(x["from"], x["in"], x["out"]) for x in rows],
                         [("", 0.75, 3.75), ("2027-01-01", 1.50, 7.50)])
        for x in rows:
            self.assertAlmostEqual(x["cache_read_mult"], 0.1, places=9)
        self.assertEqual(tm.rate_on(rows, dt.datetime(2026, 10, 1, 12, tzinfo=dt.timezone.utc))["in"],
                         0.75)

    def test_long_context_keeps_its_providers_threshold(self):
        """Every looked-up long-context rate started above 272,000 tokens,
        OpenAI's figure, though Google's starts above 200,000. Also guards
        that every table row uses its provider's threshold, except a retired
        model whose own page printed another (Google's 1.5 series, 128k)."""
        r = {"in": 2.00, "out": 12.00, "cached": 0.20, "long_in": 4.00, "long_out": 18.00}
        row, = tm.rows_from_page(r, tm.TABLES["google"])
        self.assertEqual(row["long"], {"over": 200_000, "in": 2.0, "out": 1.5})
        row, = tm.rows_from_page(r, tm.TABLES["xai"])
        self.assertEqual(row["long"]["over"], 199_999)
        row, = tm.rows_from_page(dict(r, long_over=128_000), tm.TABLES["google"])
        self.assertEqual(row["long"]["over"], 128_000)
        # A table that states no threshold gets no long-context rule at all.
        row, = tm.rows_from_page(r, tm.TABLES["anthropic"])
        self.assertNotIn("long", row)
        # Every long rule in a table uses its LONG_OVER, with one named
        # exception: Google's retired 1.5 series, whose archived page printed
        # "prompts <= 128k tokens" and "> 128k", so those rows carry their own
        # 128,000 (the rule changed on 27 October 2026, when the table gained
        # them). A row's own threshold is honoured by the engine, and allowed
        # here only on a retired model listed below.
        own_line = {"google": {"gemini-1.5-pro": 128_000, "gemini-1.5-flash": 128_000,
                               "gemini-1.5-flash-8b": 128_000}}
        for name in ("openai", "google", "xai"):
            table = tm.TABLES[name]
            with self.subTest(table=name):
                long = {(m, x["long"]["over"]) for m, rows in table.PRICES.items()
                        for x in rows if x.get("long")}
                own = {m: over for m, over in long if over != table.LONG_OVER}
                self.assertTrue(any(over == table.LONG_OVER for _, over in long))
                self.assertEqual(own, own_line.get(name, {}))
                retired = getattr(table, "RETIRED", {})
                self.assertTrue(all(m in retired for m in own), own)

    def test_a_one_hour_write_off_the_default_is_kept(self):
        """The page's 1-hour cache write was read and then dropped."""
        r = {"in": 1.00, "out": 4.00, "cached": 0.10, "write_5m": 1.00, "write_1h": 2.00}
        row, = tm.rows_from_page(r, tm.TABLES["moonshot"])
        self.assertEqual(row["write_1h_mult"], 2.0)
        self.assertNotIn("write_mult", row)
        # Anthropic charges 2x by default, so a page saying 2x adds nothing.
        r = {"in": 5.00, "out": 25.00, "cached": 0.50, "write_5m": 6.25, "write_1h": 10.00}
        row, = tm.rows_from_page(r, tm.TABLES["anthropic"])
        self.assertNotIn("write_1h_mult", row)
        self.assertNotIn("write_mult", row)


class TestGooglePageReader(Base):
    """pricing/google.py reads Google's page in Markdoc: one "## " heading per
    model, its id in backticks, then a Standard tab holding a table of
    three-cell rows. The real page is not fetched here; these blocks are
    shaped like it. They were HTML until the page moved to
    aistudio.google.com and the reader with it (2 November 2026)."""

    def page(self, *models):
        """One block per (id, input cell, output cell, caching cell)."""
        out = ""
        for mid, inp, out_, cache in models:
            rows = "---\n".join(f"* {label}\n* Not available\n* {paid}\n"
                                for label, paid in (("Input price", inp),
                                                    ("Output price (including thinking tokens)", out_),
                                                    ("Context caching price", cache)))
            out += (f'## {mid}  {{% id="{mid}" %}}\n*[`{mid}`](/docs/models/{mid})*\n'
                    f'{{% tabs %}}\n{{% tab title="Standard" %}}\n{{% table %}}\n{rows}'
                    f'{{% /table %}}\n{{% /tab %}}\n{{% /tabs %}}\n')
        return out

    def test_a_text_model_with_a_new_kind_of_name_is_flagged_as_unlisted(self):
        """The unlisted filter named only ids shaped gemini-N-pro, -flash or
        -flash-lite, so Gemini 4 Argon sat on the page for three days with
        --check-prices saying every model matched. Any gemini-N-<word> text
        model counts now; live, transcription, speech, image, audio, embedding
        and robotics models are still left out, as they always were."""
        names = ("gemini-5-boron", "gemini-4.2-pro-preview", "gemini-4.1-flash-lite",
                 "gemini-4-live", "gemini-4-transcribe", "gemini-4-flash-tts", "gemini-4-flash-image",
                 "gemini-4-flash-live-preview", "gemini-4-audio", "gemini-embedding-3",
                 "gemini-4-argon")
        page = self.page(*((m, "$1.00", "$2.00", "$0.10") for m in names))
        rates, unknown = tm.TABLES["google"].page_rates(lambda url: page, tm.md_tables)
        self.assertEqual(set(rates), set(names))
        self.assertEqual(unknown, ["gemini-4.1-flash-lite", "gemini-4.2-pro-preview", "gemini-5-boron"])

    def test_dated_prices_are_read_as_two_rows(self):
        """Argon's cells as the page writes them on 16 October 2026."""
        page = self.page(("gemini-4-argon", "$2.00 through November 30, 2026. $4.00 starting December 1, 2026.",
                          "$10.00 through November 30, 2026. $20.00 starting December 1, 2026.",
                          "$0.10 through November 30, 2026. $0.20 starting December 1, 2026. "
                          "Implicit caching only (explicit caching is not supported)."))
        rates, unknown = tm.TABLES["google"].page_rates(lambda url: page, tm.md_tables)
        got = rates["gemini-4-argon"]
        self.assertEqual((got["in"], got["out"], got["cached"]), (4.00, 20.00, 0.20))
        self.assertEqual(got["_history"], [{"from": "", "in": 2.00, "out": 10.00, "cached": 0.10},
                                           {"from": "2026-12-01", "in": 4.00, "out": 20.00, "cached": 0.20}])
        self.assertNotIn("long_in", got)
        self.assertEqual(unknown, [])


class TestCheckPrices(Base):
    def anthropic_page(self, tweak=None):
        """The page as the table implies it. A model priced by prompt length
        is two rows, as the real page writes Haiku 5.5. tweak is (model id,
        column, figure), with a fourth item, True, for the higher tier."""
        lines = ["| Model | Base input tokens | 5m cache writes | 1h cache writes | "
                 "Cache hits and refreshes | Output tokens |", "| :-- | :-- | :-- | :-- | :-- | :-- |"]
        for name, mid in tm._anthropic.PAGE_NAMES.items():
            r = tm.PRICES[mid][-1]
            tiers = [("", r["in"], r["out"], False)]
            if r.get("long"):
                lg = r["long"]
                tiers = [(f" (for prompts up to {lg['over']:,} tokens)", r["in"], r["out"], False),
                         (f" (for prompts over {lg['over']:,} tokens)",
                          r["in"] * lg["in"], r["out"] * lg["out"], True)]
            for suffix, inp, out, over in tiers:
                vals = [inp, inp * 1.25, inp * 2, inp * r["cache_read_mult"], out]
                if tweak and tweak[0] == mid and (tweak[3] if len(tweak) > 3 else False) == over:
                    vals[tweak[1]] = tweak[2]
                lines.append(f"| {name}{suffix} | " + " | ".join(f"${v:g} / MTok" for v in vals) + " |")
        return "\n".join(lines) + "\n"

    def run_check(self, page):
        real = dict(tm.TABLES)
        tm.TABLES.clear()
        tm.TABLES["anthropic"] = real["anthropic"]
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = tm.check_prices(fetch=page)
            return code, buf.getvalue()
        finally:
            tm.TABLES.clear()
            tm.TABLES.update(real)

    def test_a_matching_page_passes_and_changes_nothing(self):
        before = json.dumps(tm.PRICES, sort_keys=True, default=str)
        code, out = self.run_check(lambda url: self.anthropic_page())
        self.assertEqual(code, 0)
        self.assertIn("20 of 20", out)
        self.assertNotIn("not in the table", out)
        self.assertEqual(before, json.dumps(tm.PRICES, sort_keys=True, default=str))

    def test_a_moved_rate_is_reported(self):
        code, out = self.run_check(lambda url: self.anthropic_page(("claude-sonnet-5", 4, 15.0)))
        self.assertEqual(code, 1)
        self.assertIn("claude-sonnet-5 out: table has $10, page says $15", out)

    def test_both_of_haiku_5_5s_tiers_are_read_as_one_model(self):
        """The page lists Haiku 5.5 as two rows, one per prompt length, and
        the reader named both as models the table lacked. Rows typed from the
        page on 15 October 2026."""
        page = ("| Model | Base input tokens | 5m cache writes | 1h cache writes | "
                "Cache hits and refreshes | Output tokens |\n| :-- | :-- | :-- | :-- | :-- | :-- |\n"
                "| Claude Haiku 5.5 (for prompts up to 100,000 tokens) | $0.10 / MTok | $0.125 / MTok "
                "| $0.20 / MTok | $0.01 / MTok | $0.50 / MTok |\n"
                "| Claude Haiku 5.5 (for prompts over 100,000 tokens) | $0.50 / MTok | $0.625 / MTok "
                "| $1 / MTok | $0.05 / MTok | $2.50 / MTok |\n"
                "| Claude Haiku 9 (for prompts up to 50,000 tokens) | $1 / MTok | $1.25 / MTok "
                "| $2 / MTok | $0.10 / MTok | $5 / MTok |\n"
                "| Claude Haiku 9 (for prompts over 50,000 tokens) | $2 / MTok | $2.50 / MTok "
                "| $4 / MTok | $0.20 / MTok | $10 / MTok |\n")
        rates, unknown = tm._anthropic.page_rates(lambda url: page, tm.md_tables,
                                                  want=("claude-haiku-9",))
        self.assertEqual(rates["claude-haiku-5-5"], {
            "in": 0.10, "write_5m": 0.125, "write_1h": 0.20, "cached": 0.01, "out": 0.50,
            "long_in": 0.50, "long_write_5m": 0.625, "long_write_1h": 1.0, "long_cached": 0.05,
            "long_out": 2.50, "long_over": 100_000})
        # A tiered model no table has is one unknown name, and a lookup of it
        # keeps the page's own threshold.
        self.assertEqual(unknown, ["Claude Haiku 9"])
        row, = tm.rows_from_page(rates["claude-haiku-9"], tm.TABLES["anthropic"])
        self.assertEqual(row["long"], {"over": 50_000, "in": 2.0, "out": 2.0})
        exp = tm.expected_rates(tm.PRICES["claude-haiku-5-5"][-1], tm._anthropic)
        for field, value in rates["claude-haiku-5-5"].items():
            with self.subTest(field=field):
                self.assertAlmostEqual(exp[field], value, places=12)

    def test_a_moved_figure_in_the_higher_tier_is_reported(self):
        code, out = self.run_check(lambda url: self.anthropic_page(("claude-haiku-5-5", 4, 3.0, True)))
        self.assertEqual(code, 1)
        self.assertIn("claude-haiku-5-5 long_out: table has $2.5, page says $3", out)
        page = self.anthropic_page().replace("100,000 tokens", "200,000 tokens")
        code, out = self.run_check(lambda url: page)
        self.assertEqual(code, 1)
        self.assertIn("claude-haiku-5-5 long_over: table has 100000, page says 200000", out)

    def test_a_model_missing_from_the_page_is_named(self):
        """A current model whose row has gone from the page is named, so a
        price the table still charges is checked by hand. The model was Haiku
        3.5 until the table marked it retired on 27 October 2026; Sonnet 4.5
        is current, and the first assertion says so if that changes."""
        self.assertNotIn("claude-sonnet-4-5", tm._anthropic.RETIRED)
        page = "".join(l for l in self.anthropic_page().splitlines(True)
                       if "| Claude Sonnet 4.5 |" not in l)
        code, out = self.run_check(lambda url: page)
        self.assertIn("not found on the page: claude-sonnet-4-5", out)

    def test_a_retired_model_missing_from_the_page_is_expected(self):
        """A retired model missing from the page is counted as retired, not
        named as missing, and the check passes. Runs on the real table, which
        lists Haiku 3.5 as retired since 27 October 2026; the test used to
        swap the table's RETIRED for its own and then delete it, which took
        the real one away from every later test in the process."""
        retired = tm._anthropic.RETIRED
        self.assertIn("claude-haiku-3-5", retired)
        page = "".join(l for l in self.anthropic_page().splitlines(True) if "Claude Haiku 3.5" not in l)
        code, out = self.run_check(lambda url: page)
        self.assertIs(tm._anthropic.RETIRED, retired)
        self.assertEqual(code, 0)
        self.assertNotIn("not found", out)
        on_page = len(tm._anthropic.PAGE_NAMES) - 1
        self.assertIn(f"{on_page} of {on_page}", out)
        off_page = [m for m in retired if m == "claude-haiku-3-5"
                    or m not in tm._anthropic.PAGE_NAMES.values()]
        self.assertIn(f"{len(off_page)} retired, kept at the last published price", out)

    def test_every_retired_model_is_still_priced(self):
        """Retiring a model never removes its row; older usage needs it."""
        for table in tm.TABLES.values():
            for model, date in getattr(table, "RETIRED", {}).items():
                with self.subTest(model=model):
                    self.assertIn(model, table.PRICES)
                    self.assertRegex(date, r"^\d{4}-\d{2}-\d{2}$")

    def test_an_unreachable_page_says_so(self):
        def down(url):
            raise OSError("no network")
        code, out = self.run_check(down)
        self.assertEqual(code, 2)
        self.assertIn("could not read the page", out)


class TestExchangeRates(Base):
    """fx_rates() itself, against a network that counts every request and
    answers none. With TOKENMETER_OFFLINE=1 it still fetched; with the network
    down it fetched on every call, three times per menu bar refresh."""

    WHEN = "Fri, 02 Oct 2026"

    def setUp(self):
        super().setUp()
        from unittest import mock
        tm.fx_rates = self._fx
        self.requests = []

        def refuse(*args, **kw):
            self.requests.append(args)
            raise OSError("no network in tests")
        patcher = mock.patch("urllib.request.urlopen", refuse)
        patcher.start()
        self.addCleanup(patcher.stop)

    def save(self, age_hours, **extra):
        data = {"rates": {"USD": 1.0, "GBP": 0.5}, "when": self.WHEN, "live": True,
                "fetched": time.time() - age_hours * 3600}
        data.update(extra)
        with open(tm.FX_CACHE, "w") as f:
            json.dump(data, f)

    def new_run(self):
        tm._FX_MEMO.clear()
        return tm.fx_rates()

    def test_a_rate_that_is_not_a_number_is_not_used(self):
        """The service's reply and the saved file are read as given, so a rate
        written as text, a bool, zero or less, or infinity reached money()
        and ended the run in a TypeError or a nonsense figure. Such a rate is
        left out and its currency takes the built-in estimate; a reply with no
        usable rate at all is treated as a failed fetch."""
        import io
        from unittest import mock
        reply = {"result": "success", "time_last_update_utc": "Fri, 02 Oct 2026 00:02:31 +0000",
                 "rates": {"GBP": "0.76", "EUR": True, "INR": 0, "CAD": -1.4, "AUD": 1.5,
                           "JPY": float("inf"), "XXX": 3.0}}
        tm.ONLINE_LOOKUP[0] = True
        with mock.patch("urllib.request.urlopen",
                        return_value=io.BytesIO(json.dumps(reply).encode())):
            rates, when, live = self.new_run()
        self.assertTrue(live)
        self.assertEqual(rates, {"AUD": 1.5, "USD": 1.0})
        tm.set_currency("GBP")
        self.assertEqual(tm.DISPLAY["rate"], tm.FALLBACK_RATES["GBP"])
        tm.set_currency("AUD")
        self.assertEqual(tm.DISPLAY["rate"], 1.5)
        # The same rule on the file a run saved, which anything may have written.
        self.save(1, rates={"GBP": "nope", "EUR": None})
        rates, when, live = self.new_run()
        self.assertEqual(rates, tm.FALLBACK_RATES)
        self.assertTrue(when.startswith("ESTIMATE"), when)
        # No usable rate in the reply is a failed fetch, remembered as one.
        with mock.patch("urllib.request.urlopen",
                        return_value=io.BytesIO(b'{"result": "success", "rates": {"GBP": "x"}}')):
            rates, when, live = self.new_run()
        self.assertEqual(rates, tm.FALLBACK_RATES)
        with open(tm.FX_CACHE) as f:
            self.assertIn("failed", json.load(f))

    def test_offline_with_nothing_saved_makes_no_request(self):
        """Offline with no rate saved, it fetched one anyway."""
        rates, when, live = tm.fx_rates()
        self.assertEqual(self.requests, [])
        self.assertEqual(rates, tm.FALLBACK_RATES)
        self.assertFalse(live)
        self.assertTrue(when.startswith("ESTIMATE"), when)
        self.assertFalse(os.path.exists(tm.FX_CACHE))

    def test_offline_uses_a_saved_rate_at_any_age(self):
        """Offline, a rate saved more than 12 hours ago was fetched again."""
        self.save(1)
        self.assertEqual(self.new_run(), ({"USD": 1.0, "GBP": 0.5}, self.WHEN, True))
        self.save(48)
        self.assertEqual(self.new_run(), ({"USD": 1.0, "GBP": 0.5}, f"cached, {self.WHEN}", False))
        self.assertEqual(self.requests, [])

    def test_offline_set_currency_makes_no_request(self):
        """A report in another currency fetched rates under --offline."""
        tm.set_currency("GBP")
        self.assertEqual(self.requests, [])
        self.assertEqual(tm.DISPLAY["rate"], tm.FALLBACK_RATES["GBP"])
        self.assertFalse(tm.DISPLAY["live"])

    def test_online_a_fresh_saved_rate_needs_no_request(self):
        """The memo and the failure record must not stop a fresh rate being
        read from the file as it always was."""
        tm.ONLINE_LOOKUP[0] = True
        self.save(1)
        self.assertEqual(tm.fx_rates(), ({"USD": 1.0, "GBP": 0.5}, self.WHEN, True))
        self.assertEqual(self.requests, [])

    def test_a_file_from_before_fetch_times_is_dated_by_its_last_write(self):
        """Files written by earlier versions carry no fetch time."""
        with open(tm.FX_CACHE, "w") as f:
            json.dump({"rates": {"USD": 1.0, "GBP": 0.5}, "when": self.WHEN, "live": True}, f)
        self.assertTrue(self.new_run()[2])
        old = time.time() - 48 * 3600
        os.utime(tm.FX_CACHE, (old, old))
        self.assertEqual(self.new_run()[1], f"cached, {self.WHEN}")

    def test_a_failed_fetch_is_tried_once_and_not_again_for_an_hour(self):
        """A failed fetch was forgotten at once, so every call in a run, and
        every run after it, sat through the timeout again."""
        tm.ONLINE_LOOKUP[0] = True
        self.save(48)
        for _ in range(3):
            got = tm.fx_rates()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(got, ({"USD": 1.0, "GBP": 0.5}, f"stale, {self.WHEN}", False))
        # The failure is in the file; the rates it held are kept, and still old.
        saved = json.loads(slurp(tm.FX_CACHE))
        self.assertEqual(saved["rates"], {"USD": 1.0, "GBP": 0.5})
        self.assertLess(saved["fetched"], time.time() - tm.FX_TTL)
        self.assertEqual(self.new_run(), got)                # the next run, within the hour
        self.assertEqual(len(self.requests), 1)
        saved["failed"] -= tm.FX_RETRY
        with open(tm.FX_CACHE, "w") as f:
            json.dump(saved, f)
        self.new_run()                                       # an hour later
        self.assertEqual(len(self.requests), 2)

    def test_a_run_asks_once_even_where_nothing_can_be_saved(self):
        """With the rate file unwritable, every call in a run fetched again."""
        tm.ONLINE_LOOKUP[0] = True
        tm.FX_CACHE = os.path.join(self.tmp, "no-such-folder", "fx_rates.json")
        answers = [tm.fx_rates() for _ in range(3)]
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(answers, [(tm.FALLBACK_RATES, tm.FX_ESTIMATE, False)] * 3)

    def test_a_failure_with_nothing_saved_is_never_used_as_rates(self):
        """The record of a failed fetch, with no rates beside it, must read
        as no rate at all, not as an empty set of rates."""
        tm.ONLINE_LOOKUP[0] = True
        rates, when, live = tm.fx_rates()
        self.assertEqual((rates, live), (tm.FALLBACK_RATES, False))
        self.assertEqual(when, tm.FX_ESTIMATE)
        self.assertNotIn("rates", json.loads(slurp(tm.FX_CACHE)))
        self.assertEqual(self.new_run(), (tm.FALLBACK_RATES, tm.FX_ESTIMATE, False))
        self.assertEqual(len(self.requests), 1)

    def test_an_offline_run_makes_no_request(self):
        """--offline stopped only the price lookup: a report in pounds and
        the menu bar's summary still fetched exchange rates."""
        self.write("a.jsonl", record("msg_1", out=10),
                   record("msg_2", model="claude-opus-9", out=10))
        tm.ONLINE_LOOKUP[0] = True
        out = cli("--offline", "--currency", "GBP")
        self.assertIn(f"to the dollar ({tm.FX_ESTIMATE_OFFLINE}). ", out)
        self.assertIn("no price on file for claude-opus-9", out)
        tm._FX_MEMO.clear()
        tm.ONLINE_LOOKUP[0] = True
        s = json.loads(cli("--offline", "--summary-json"))
        self.assertEqual((s["rate_when"], s["rate_live"]), (tm.FX_ESTIMATE_OFFLINE, False))
        self.assertEqual(self.requests, [])

    def test_summary_asks_once(self):
        """summary() called fx_rates() three times, once per field."""
        self.write("a.jsonl", record("msg_1", out=10))
        calls = []
        tm.fx_rates = lambda: calls.append(1) or ({"USD": 1.0, "GBP": 0.5}, self.WHEN, False)
        s = tm.summary()
        self.assertEqual(len(calls), 1)
        self.assertEqual((s["rates"], s["rate_when"], s["rate_live"]),
                         ({"USD": 1.0, "GBP": 0.5}, self.WHEN, False))

    def test_the_rate_says_what_it_is_once(self):
        """The footer read "(OFFLINE ESTIMATE, offline estimate, no cached rate)"."""
        self.write("a.jsonl", record("msg_1", out=10))
        result = tm.collect(tm.transcripts(), ledger=False)
        out = os.path.join(self.tmp, "d.html")
        for when, live, shown in ((tm.FX_ESTIMATE_OFFLINE, False, tm.FX_ESTIMATE_OFFLINE),
                                  (tm.FX_ESTIMATE, False, tm.FX_ESTIMATE),
                                  (f"stale, {self.WHEN}", False, f"stale, {self.WHEN}"),
                                  (f"cached, {self.WHEN}", False, f"cached, {self.WHEN}"),
                                  (self.WHEN, True, f"live, {self.WHEN}")):
            with self.subTest(when=when):
                tm.DISPLAY.update(code="GBP", symbol="£", rate=0.5, when=when, live=live)
                footer = terminal(*result, "", "all time").strip().splitlines()[-1]
                self.assertIn(f"to the dollar ({shown}). ", footer)
                self.assertLessEqual(footer.lower().count("estimate"), 1, footer)
                tm.fx_rates = lambda: ({"USD": 1.0, "GBP": 0.5}, when, live)
                tm.render_html(*result, "all time", out)
                self.assertEqual(payload_of(slurp(out, encoding="utf-8"))["rateWhen"], shown)


# Anthropic: the page reader in pricing/anthropic.py, run on a saved copy of
# the page with a faked fetch, and each rule the table models.
#
# The saved page, fixtures/pages/anthropic_page.md, is lines cut verbatim from
# https://platform.claude.com/docs/en/about-claude/pricing.md as fetched on 27
# October 2026: the "Model pricing" heading and its table, and the "Fast mode
# pricing" heading and its table. Nothing in it was typed by hand. A test that
# needs a different page builds it from that copy.

ANTHROPIC_PAGE_FILE = os.path.join(FIXTURES, "pages", "anthropic_page.md")


# Typed from the page on 27 October 2026, not copied from the table:
# base input, 5m write, 1h write, cache hit, output.
ANTHROPIC_ON_THE_PAGE = {
    "claude-fable-5-1": (10, 12.50, 20, 0.25, 50),
    "claude-opus-5-5": (4, 5, 8, 0.20, 20),
    "claude-opus-4-1": (15, 18.75, 30, 1.50, 75),
    "claude-sonnet-5-5": (2, 2.50, 4, 0.10, 10),
    "claude-sonnet-5": (2, 2.50, 4, 0.20, 10),
    "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50),
    "claude-haiku-3-5": (0.80, 1, 1.60, 0.08, 4),
}


ANTHROPIC_FIELDS = ("in", "write_5m", "write_1h", "cached", "out")


def anthropic_model_table(text):
    """The saved page's model table, as its header and its rows of cells."""
    lines = [l for l in text.splitlines() if l.startswith("| ")]
    split = [[c.strip() for c in l.strip()[1:-1].split("|")] for l in lines]
    start = next(i for i, r in enumerate(split) if r[0] == "Model" and len(r) == 6)
    end = next(i for i in range(start + 2, len(split)) if len(split[i]) != 6)
    return split[start], split[start + 2:end]


def anthropic_as_markdown(header, rows):
    """A header and rows written back as a markdown pipe table."""
    out = ["| " + " | ".join(header) + " |", "|" + " :-- |" * len(header)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out) + "\n"


class TestAnthropicPageReader(Base):
    def setUp(self):
        super().setUp()
        self.table = tm.TABLES["anthropic"]
        self.page = slurp(ANTHROPIC_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def read(self, text, **kw):
        def fetch(url):
            self.urls.append(url)
            return text
        return self.table.page_rates(fetch, tm.md_tables, **kw)

    def test_every_model_is_read_off_the_saved_page(self):
        """Guards the reader losing a model to a name cell it cannot clean:
        a "retired, except on ..." link, a <sup> footnote marker, a "limited
        availability" link or Haiku 5.5's two prompt-length rows. Every one
        of the twenty is read, at the figures the page prints, from one fetch
        of the markdown form."""
        rates, unknown = self.read(self.page)
        self.assertEqual(self.urls, [self.table.SOURCE_MD])
        self.assertEqual(unknown, [])
        self.assertEqual(sorted(rates), sorted(self.table.PAGE_NAMES.values()))
        for model, official in ANTHROPIC_ON_THE_PAGE.items():
            with self.subTest(model=model):
                for field, want in zip(ANTHROPIC_FIELDS, official):
                    self.assertAlmostEqual(rates[model][field], want, places=9, msg=field)

    def test_haiku_5_5_higher_tier_and_fast_rates_are_read(self):
        """Guards the "over 100,000 tokens" row overwriting the base figures
        instead of filling the long_ fields, and the fast-mode row that names
        two models giving its rates to only one."""
        rates, _ = self.read(self.page)
        haiku = rates["claude-haiku-5-5"]
        for field, want in zip(ANTHROPIC_FIELDS, (0.50, 0.625, 1, 0.05, 2.50)):
            self.assertAlmostEqual(haiku["long_" + field], want, places=9, msg=field)
        self.assertEqual(haiku["long_over"], 100_000)
        self.assertAlmostEqual(haiku["in"], 0.10, places=9)
        for model, fast in (("claude-opus-5-5", (8, 40)), ("claude-opus-5", (10, 50)),
                            ("claude-opus-4-8", (10, 50))):
            with self.subTest(model=model):
                self.assertEqual((rates[model]["fast_in"], rates[model]["fast_out"]), fast)
        self.assertNotIn("fast_in", rates["claude-opus-4-7"])

    def test_the_saved_page_agrees_with_the_table(self):
        """Guards a table row drifting from the page, and a retired model
        the page no longer lists being reported as missing: --check-prices's
        own comparison finds all twenty current models matching in every
        column and the seven archive-priced ones retired."""
        r = tm.compare_with_page(self.table, lambda url: self.page)
        self.assertEqual(r["error"], "")
        self.assertEqual((r["matched"], r["expected"]), (20, 20))
        self.assertEqual((r["diffs"], r["absent"], r["unlisted"]), ([], [], []))
        self.assertEqual(sorted(r["retired"]), sorted(
            ["claude-3-7-sonnet", "claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku",
             "claude-3-sonnet", "claude-2.1", "claude-2.0"]))

    def test_columns_are_read_by_header_not_position(self):
        """Guards the page's HTML column order (Input, Output, then the cache
        columns) reaching the markdown form: read by position, output would
        be taken as the 5-minute write and every model would differ. Read by
        header, the reordered table gives the same figures."""
        header, rows = anthropic_model_table(self.page)
        order = [0, 1, 5, 2, 3, 4]
        moved = anthropic_as_markdown([header[i] for i in order], [[r[i] for i in order] for r in rows])
        self.assertEqual(self.read(moved), self.read(anthropic_as_markdown(header, rows)))
        rates, _ = self.read(moved)
        self.assertAlmostEqual(rates["claude-opus-5-5"]["out"], 20, places=9)
        self.assertAlmostEqual(rates["claude-opus-5-5"]["write_5m"], 5, places=9)

    def test_a_table_missing_a_column_is_not_read(self):
        """Guards a guess: a model table without one of its five figure
        columns is skipped whole, so a changed layout reads as models not
        found on the page, never as a wrong figure."""
        header, rows = anthropic_model_table(self.page)
        keep = [0, 1, 2, 3, 4]
        cut = anthropic_as_markdown([header[i] for i in keep], [[r[i] for i in keep] for r in rows])
        self.assertEqual(self.read(cut), ({}, []))

    def test_a_model_new_on_the_page_is_named_and_read_when_wanted(self):
        """Guards a model the table lacks going unseen: --check-prices names
        it, and the startup lookup, which asks for its id, gets its rates.
        want=None, the signature pricing/README.md gives, reads as no ids."""
        rates, unknown = self.read(ANTHROPIC_PAGE, want=None)
        self.assertEqual((rates, unknown), ({}, ["Claude Opus 9"]))
        rates, _ = self.read(ANTHROPIC_PAGE, want=("claude-opus-9",))
        self.assertAlmostEqual(rates["claude-opus-9"]["in"], 6, places=9)
        self.assertAlmostEqual(rates["claude-opus-9"]["out"], 30, places=9)


# OpenAI: the page reader in pricing/openai.py, run on a saved copy of the
# page with a faked fetch, and each rule the table models.
#
# The saved page, fixtures/pages/openai_page.md, is lines cut verbatim from
# https://developers.openai.com/api/docs/pricing.md as fetched on 2 November
# 2026 at 00:03 UTC (sha256 56e3da9bb29246cad60003e01f3fdc6b536149a09f5effe5e79af020a4922cfc):
# the two Standard tables, the Flex tables, the two Fast tables, the
# Ultrafast table with the long-context footnote under it, the Cyber and the
# Life sciences Standard tables, the Legal model configurations table, the
# two specialised (Category) tables and one fine-tuning table. Nothing in it
# was typed by hand. The same cut of the page of 27 October 2026 differs only
# in the Life sciences and Legal tables. A test that needs a different page
# builds it from that copy.

OPENAI_PAGE_FILE = os.path.join(FIXTURES, "pages", "openai_page.md")


# Typed from the page on 27 October 2026 (gpt-6-rosalind and gpt-6-astra-law
# on 2 November 2026), not copied from the table: input, output, cached
# input (Standard).
OPENAI_ON_THE_PAGE = {
    "gpt-6-astra": (10, 50, 1.00),
    "gpt-6.1-terra": (1, 5, 0.05),
    "gpt-5.6-sol": (4, 20, 0.40),
    "gpt-5.5": (5, 30, 0.50),
    "gpt-5.5-pro": (30, 180, 30),
    "gpt-5.4-mini": (0.75, 4.50, 0.075),
    "gpt-4o-2024-05-13": (5, 15, 5),
    "gpt-3.5-turbo-0125": (0.50, 1.50, 0.50),
    "gpt-5.6-cyber": (12.50, 75, 1.25),
    "gpt-rosalind-discovery": (5, 25, 0.50),
    "gpt-6-rosalind": (15, 75, 1.50),
    "gpt-6-astra-law": (10, 50, 1.00),
    "chat-latest": (5, 30, 0.50),
    "gpt-5.3-codex": (1.75, 14, 0.175),
    "gpt-5-search-api": (1.25, 10, 0.125),
}


# The models the saved page does not list, all in RETIRED.
OPENAI_OFF_THE_PAGE = [
    "gpt-4-1106-preview", "gpt-5.2-codex", "gpt-5.1-codex-max", "gpt-5.1-codex",
    "gpt-5.1-codex-mini", "gpt-5-codex", "gpt-5-chat-latest", "gpt-5.1-chat-latest",
    "o3-deep-research", "o4-mini-deep-research", "computer-use-preview",
    "gpt-4o-search-preview", "gpt-4o-mini-search-preview", "gpt-5.2-chat-latest",
    "gpt-5.3-chat-latest", "gpt-3.5-turbo-1106", "gpt-3.5-turbo-instruct", "davinci-002",
    "babbage-002", "gpt-4-0314", "gpt-4-0125-preview", "chatgpt-4o-latest",
    "codex-mini-latest", "o1-mini", "o1-preview", "gpt-4.5-preview", "gpt-4-32k",
]


class TestOpenAIPageReader(Base):
    def setUp(self):
        super().setUp()
        self.table = tm.TABLES["openai"]
        self.page = slurp(OPENAI_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def read(self, text, **kw):
        def fetch(url):
            self.urls.append(url)
            return text
        return self.table.page_rates(fetch, tm.md_tables, **kw)

    def test_every_model_is_read_off_the_saved_page(self):
        """Guards the baseline's HTTP 404: the old reader skipped the page's
        four-column tables, so 27 models fell through to their own model
        pages and one of those answered 404, failing the whole check. Now
        one fetch of the markdown page gives every model, and a "-" cached
        cell (pro and legacy rows) reads as the ordinary input rate. No id
        is named: gpt-6-astra-law, the one named until the maintainer
        decided on 2 November 2026 to price it, now has a row."""
        rates, unknown = self.read(self.page)
        self.assertEqual(self.urls, [self.table.SOURCE_MD])
        self.assertEqual(unknown, [])
        for model, official in OPENAI_ON_THE_PAGE.items():
            with self.subTest(model=model):
                for field, want in zip(("in", "out", "cached"), official):
                    self.assertAlmostEqual(rates[model][field], want, places=9, msg=field)

    def test_ten_column_tables_are_read_by_header(self):
        """Guards the old nine-column order being applied to the page's ten
        columns, which read gpt-6-astra's output as its cache write and its
        long output as $2: every figure of the row, both write lifetimes and
        the long tier, comes from the column that names it."""
        rates, _ = self.read(self.page)
        astra = rates["gpt-6-astra"]
        want = {"in": 10, "out": 50, "cached": 1, "write": 12.50, "write_1h": 25,
                "long_in": 20, "long_out": 75, "long_cached": 2, "long_write_5m": 25,
                "long_write_1h": 50, "fast_in": 20, "fast_out": 100, "long_over": 272_000}
        self.assertEqual(set(astra), set(want))
        for field, value in want.items():
            self.assertAlmostEqual(astra[field], value, places=9, msg=field)

    def test_columns_are_read_by_header_not_position(self):
        """Guards a reordered page reading as wrong figures: the saved page's
        ten-column Standard table with its Output column moved to the end
        reads exactly as the page does."""
        lines = self.page.splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("| Model | Short context input"))

        def move(line):
            cells = [c.strip() for c in line.strip()[1:-1].split("|")]
            cells.append(cells.pop(2))
            return "| " + " | ".join(cells) + " |"
        end = next(i for i in range(start, len(lines)) if not lines[i].startswith("|"))
        moved = lines[:start] + [move(l) for l in lines[start:end]] + lines[end:]
        before, _ = self.read(self.page)
        after, _ = self.read("\n".join(moved) + "\n")
        for model in ("gpt-6-astra", "gpt-5.5", "gpt-5.4-pro"):
            with self.subTest(model=model):
                self.assertEqual(after[model], before[model])

    def test_flex_batch_and_ultrafast_are_not_read_as_standard_or_fast(self):
        """Guards the tiers a row cannot hold overwriting Standard or Fast:
        the Flex tables print gpt-5.4-mini at $0.375 and gpt-6-astra at $5,
        and Ultrafast prints gpt-6-astra at $60 in; the reader keeps the
        Standard $0.75 and $10 and the Fast $20."""
        rates, _ = self.read(self.page)
        self.assertAlmostEqual(rates["gpt-5.4-mini"]["in"], 0.75, places=9)
        self.assertAlmostEqual(rates["gpt-6-astra"]["in"], 10, places=9)
        self.assertAlmostEqual(rates["gpt-6-astra"]["fast_in"], 20, places=9)

    def test_specialised_tables_give_standard_then_fast(self):
        """Guards the specialised (Category) tables, whose columns moved to
        Input, Output, Cached input: the first is Standard, the second Fast,
        so gpt-5.3-codex is $1.75 / $14 with fast $3.50 / $28, and chat-latest,
        on the first only, has no fast rate."""
        rates, _ = self.read(self.page)
        codex = rates["gpt-5.3-codex"]
        self.assertEqual((codex["in"], codex["out"], codex["fast_in"], codex["fast_out"]),
                         (1.75, 14, 3.50, 28))
        self.assertNotIn("fast_in", rates["chat-latest"])

    def test_the_saved_page_agrees_with_the_table(self):
        """Guards a table row drifting from the page, and a retired model the
        page no longer lists being reported as missing: --check-prices's own
        comparison finds all 46 models the page prints that the table holds
        matching in every column, gpt-6-astra-law (added on 2 November
        2026) among them, the 27 archive-priced ones retired, and none
        unlisted."""
        r = tm.compare_with_page(self.table, lambda url: self.page)
        self.assertEqual(r["error"], "")
        self.assertEqual((r["matched"], r["expected"]), (46, 46))
        self.assertEqual((r["diffs"], r["absent"]), ([], []))
        self.assertEqual(r["unlisted"], [])
        self.assertEqual(sorted(r["retired"]), sorted(OPENAI_OFF_THE_PAGE))

    def test_the_long_context_threshold_is_read_from_the_footnote(self):
        """Guards long_over being assumed: it comes from the page's footnote
        (">272K input tokens"), follows a changed footnote, and falls back to
        LONG_OVER only when the footnote is gone."""
        rates, _ = self.read(self.page)
        self.assertEqual(rates["gpt-5.4"]["long_over"], 272_000)
        self.assertNotIn("long_over", rates["gpt-5.4-mini"])
        rates, _ = self.read(self.page.replace(">272K input tokens", ">300K input tokens"))
        self.assertEqual(rates["gpt-5.4"]["long_over"], 300_000)
        gone = "\n".join(l for l in self.page.splitlines() if not l.startswith("Short context:"))
        rates, _ = self.read(gone)
        self.assertEqual(rates["gpt-5.4"]["long_over"], self.table.LONG_OVER)

    def test_a_model_new_on_the_page_is_named(self):
        """Guards a new model going unnoticed: a row the table lacks, added
        to the saved page's four-column Standard table, is named as unlisted,
        while fine-tuning ids such as o4-mini-2025-04-16 never are."""
        row = "| gpt-5.4-mini | $0.75 | $4.50 | $0.075 |"
        self.assertIn(row, self.page)
        page = self.page.replace(row, row + "\n| gpt-9-nova | $0.75 | $4.50 | $0.075 |")
        rates, unknown = self.read(page)
        self.assertEqual(unknown, ["gpt-9-nova"])
        self.assertAlmostEqual(rates["gpt-9-nova"]["in"], 0.75, places=9)
        self.assertIn("o4-mini-2025-04-16", self.page)

    def test_a_table_it_does_not_price_from_still_names_its_models(self):
        """Guards a model printed only in a table the reader does not
        recognise being dropped without a word, as the Legal model
        configurations table was: its header starts "Model configuration",
        and gpt-6-astra-law was neither read nor named. Now that table is
        read as Standard ($10 / $50 / $1, which gpt-6-astra-law's row has
        held since 2 November 2026, so it is no longer named), and an id in
        a table of a layout
        the reader has never seen is still named, while a dated snapshot of
        a row there (o4-mini-2025-04-16, as fine-tuning lists it) is not."""
        rates, unknown = self.read(self.page)
        law = rates["gpt-6-astra-law"]
        self.assertEqual((law["in"], law["out"], law["cached"]), (10, 50, 1))
        self.assertEqual(unknown, [])
        page = self.page + ("\n### Some new tier\n\n| Model | Price per call |\n| --- | --- |\n"
                            "| gpt-9-nova | $1.00 |\n| o4-mini-2025-04-16 | $1.00 |\n")
        rates, unknown = self.read(page)
        self.assertEqual(unknown, ["gpt-9-nova"])
        self.assertNotIn("gpt-9-nova", rates)

    def test_a_model_page_404_skips_only_that_model(self):
        """Guards one model page's 404 failing every other model: with want
        given, a wanted id the main page lacks is read from its own model
        page, an HTTP error there skips that id alone, and --check-prices
        (want=None) fetches no model page at all."""
        model_page = ("| Metric | Price | Unit |\n| --- | --- | --- |\n"
                      "| Input | $1.00 | per 1M tokens |\n| Output | $8.00 | per 1M tokens |\n")

        def fetch(url):
            self.urls.append(url)
            if url == self.table.SOURCE_MD:
                return self.page
            if url.endswith("/gpt-9-gone.md"):
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b""))
            return model_page
        rates, _ = self.table.page_rates(fetch, tm.md_tables, want=("gpt-9-gone", "gpt-9-here"))
        self.assertNotIn("gpt-9-gone", rates)
        self.assertEqual((rates["gpt-9-here"]["in"], rates["gpt-9-here"]["out"]), (1.0, 8.0))
        self.assertNotIn("write_1h", rates["gpt-9-here"])
        self.urls.clear()
        self.table.page_rates(fetch, tm.md_tables)
        self.assertEqual(self.urls, [self.table.SOURCE_MD])


# Google (Gemini API): the page reader in pricing/google.py, run on a saved
# copy of the page with a faked fetch, and each rule the table models.
#
# The saved page, fixtures/pages/google_page.md, is five model sections cut
# verbatim, in page order, from https://aistudio.google.com/docs/pricing.md as
# fetched on 2 November 2026, each from its "## " heading to the next: Gemini 4
# Argon (dated prices), 3.5 Flash-Lite, the 3.8 Live section (a model kind the
# reader leaves out), 3.1 Pro Preview (long context, two ids) and 2.5 Flash
# (audio prices beside the text ones). Nothing in it was typed by hand. A test
# that needs a different page builds it from that copy. It replaced a cut of
# the HTML page at https://ai.google.dev/gemini-api/docs/pricing of 27 October
# 2026, because the page moved and its HTML no longer holds the tables.

GOOGLE_PAGE_FILE = os.path.join(FIXTURES, "pages", "google_page.md")


# Typed from the page on 27 October 2026, not copied from the table: the
# Standard and Priority tables of each text model. The copy of 2 November
# 2026 that the saved page is cut from prints the same figures.
GOOGLE_ON_THE_PAGE = {
    "gemini-4-argon": {
        "in": 4.00, "out": 20.00, "cached": 0.20, "fast_in": 7.20, "fast_out": 36.00,
        "_history": [
            {"from": "", "in": 2.00, "out": 10.00, "cached": 0.10, "fast_in": 3.60, "fast_out": 18.00},
            {"from": "2026-12-01", "in": 4.00, "out": 20.00, "cached": 0.20,
             "fast_in": 7.20, "fast_out": 36.00}]},
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50, "cached": 0.03, "fast_in": 0.54, "fast_out": 4.50},
    "gemini-3.1-pro-preview": {"in": 2.00, "out": 12.00, "cached": 0.20, "long_in": 4.00,
                               "long_out": 18.00, "long_cached": 0.40, "long_over": 200_000,
                               "fast_in": 3.60, "fast_out": 21.60},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50, "cached": 0.03, "fast_in": 0.54, "fast_out": 4.50},
}
GOOGLE_ON_THE_PAGE["gemini-3.1-pro-preview-customtools"] = GOOGLE_ON_THE_PAGE["gemini-3.1-pro-preview"]


# The live section's ids: on the page, and on purpose not text models.
GOOGLE_LIVE = ("gemini-3.8-live", "gemini-3.8-live-extended-thinking", "gemini-3.1-flash-live-preview")


class TestGooglePageReaderOnTheSavedPage(Base):
    def setUp(self):
        super().setUp()
        self.table = tm.TABLES["google"]
        self.html = slurp(GOOGLE_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def read(self, html):
        def fetch(url):
            self.urls.append(url)
            return html
        return self.table.page_rates(fetch, tm.md_tables)

    def test_every_text_model_is_read_figure_for_figure(self):
        """The reader read only the Standard table, so --check-prices could
        never see a Priority figure, nor the "> 200k" cache price or the
        threshold the page states. Every one of them, in every dated entry,
        must come out of the saved page as printed, and the audio and storage
        figures beside them must not."""
        rates, unknown = self.read(self.html)
        self.assertEqual({m: r for m, r in rates.items() if m not in GOOGLE_LIVE}, GOOGLE_ON_THE_PAGE)
        self.assertEqual(unknown, [])
        self.assertEqual(self.urls, [self.table.SOURCE_MD])

    def test_the_page_is_read_where_it_now_lives(self):
        """By 2 November 2026 Google's pricing page had moved to
        aistudio.google.com and was rendered in the browser from Markdoc, so
        the reader, which looked for <h2> headings and <tbody> tables in the
        HTML, found no rates at all and --check-prices could check nothing.
        The reader must fetch the page's Markdoc copy at the new address and
        read every text model's Standard and Priority figures from it."""
        self.assertTrue(self.table.SOURCE.startswith("https://aistudio.google.com/"))
        self.assertEqual(self.table.SOURCE_MD, self.table.SOURCE + ".md")
        rates, _ = self.read(self.html)
        self.assertEqual(self.urls, [self.table.SOURCE_MD])
        self.assertEqual(rates["gemini-3.1-pro-preview"]["fast_out"], 21.60)
        self.assertEqual(sorted(m for m in rates if m not in GOOGLE_LIVE), sorted(GOOGLE_ON_THE_PAGE))

    def test_the_saved_page_agrees_with_the_table(self):
        """A table row that drifted from the page, in any column the page
        lists, Priority and the long tier included, would price every
        Gemini call wrongly and still be reported as checked."""
        c = tm.compare_with_page(self.table, lambda url: self.html)
        self.assertEqual((c["error"], c["found"]), ("", True))
        self.assertEqual((c["diffs"], c["unlisted"]), ([], []))
        self.assertEqual(c["matched"], 4)
        self.assertNotIn("gemini-4-argon", c["absent"])

    def test_a_changed_priority_figure_is_reported(self):
        """The Priority figures are checked, not just read: a page whose
        Priority output moved must show as a difference against the table."""
        page = self.html.replace("$21.60, prompts <= 200k", "$22.00, prompts <= 200k")
        self.assertNotEqual(page, self.html)
        c = tm.compare_with_page(self.table, lambda url: page)
        self.assertIn(("gemini-3.1-pro-preview", "fast_out", 21.60, 22.00), c["diffs"])

    def test_a_model_with_no_priority_table_has_no_fast_figures(self):
        """A tier is read from its own table only. Searching past the end of
        a section's tiers would hand one model the next model's Priority
        figures; with the Priority tables taken out, no model has any."""
        page = self.html.replace('{% tab title="Priority" %}', '{% tab title="Removed" %}')
        rates, _ = self.read(page)
        for mid, r in rates.items():
            self.assertNotIn("fast_in", r, mid)
            for h in r.get("_history", []):
                self.assertNotIn("fast_in", h, mid)
        self.assertEqual(rates["gemini-2.5-flash"]["in"], 0.30)

    def test_a_text_model_new_on_the_page_is_named(self):
        """A model the page sells and the table lacks must be named, or a new
        model would be priced by the lookup with nobody told."""
        page = self.html.replace("gemini-3.5-flash-lite", "gemini-4.5-flash-lite")
        rates, unknown = self.read(page)
        self.assertEqual(unknown, ["gemini-4.5-flash-lite"])
        self.assertEqual(rates["gemini-4.5-flash-lite"]["in"], 0.30)


# Mistral: why --check-prices stopped finding Mistral Large 3 and Mistral
# Medium 3.5, and the page reader in pricing/mistral.py run on a saved copy of
# the page with a faked fetch.
#
# On 27 October 2026 the check read 8 of 8 Mistral models matching; on 1
# November 2026 it read 6 of 8, with mistral-large-2512 and mistral-medium-3-5
# "not found on the page". The reader was right: Mistral deprecated both on 31
# October 2026 and took them off the pricing page. The table "Deprecated &
# retired models" at https://docs.mistral.ai/models/overview gives each
# "Deprecation 10/31/2026, Retirement 4/30/2027, Alternative Mistral Large 4".
#
# The saved page, fixtures/pages/mistral_page_2026-11-02.html, is
# https://docs.mistral.ai/inference/pricing as fetched on 2 November 2026, cut
# down to its price blocks (Generalist, OCR, Audio and Code models) with
# scripts, styles, icons and class attributes removed. No figure in it was
# typed by hand.
#
# Mistral Large 4 (mistral-large-4), on the page since its Public Preview on 6
# October 2026, went into the table on 2 November 2026 at the price the page
# prints that day, as one row from launch. Mistral's changelog says "Launch
# pricing: 50% off for 2 weeks" without figures, but Internet Archive copies
# of the pricing page printed a sale price and then a higher one before the
# cut to today's price; pricing/mistral.py's docstring gives them. The table
# has no dated rows for them yet, because it takes archive prices only for a
# retired model and neither boundary is printed to the day.

MISTRAL_PAGE_FILE = os.path.join(FIXTURES, "pages", "mistral_page_2026-11-02.html")


# Typed from the page on 2 November 2026, not copied from the table: input,
# output and cached input, dollars per million tokens, for each model the
# table knows that the page still prices.
MISTRAL_ON_THE_PAGE = {
    "mistral-large-4": (0.7, 2.1, 0.07),
    "mistral-small-2603": (0.15, 0.6, 0.015),
    "ministral-14b-2512": (0.2, 0.2, 0.02),
    "ministral-8b-2512": (0.15, 0.15, 0.015),
    "ministral-3b-2512": (0.1, 0.1, 0.01),
    "codestral-2508": (0.3, 0.9, 0.03),
    "zai-glm-5-3": (1.4, 4.4, 0.14),
}


# The two models Mistral deprecated on 31 October 2026, with the last price
# the page printed for each (typed from the pinned test's reading of 26
# September 2026): input, output.
MISTRAL_DEPRECATED = {"mistral-large-2512": (0.50, 1.50), "mistral-medium-3-5": (1.50, 7.50)}


class TestMistralPageReader(Base):
    def setUp(self):
        super().setUp()
        self.table = tm.TABLES["mistral"]
        self.page = slurp(MISTRAL_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return self.page

    def read(self):
        return self.table.page_rates(self.fetch, tm.md_tables)

    def test_every_current_model_is_read_off_the_saved_page(self):
        """Every model the table knows that the page still prices is read,
        at the figures the page prints, from the one page the table names."""
        rates, unlisted = self.read()
        self.assertEqual(self.urls, [self.table.SOURCE])
        self.assertEqual(unlisted, [])
        self.assertEqual(sorted(rates), sorted(MISTRAL_ON_THE_PAGE))
        for model, (inp, out, cached) in MISTRAL_ON_THE_PAGE.items():
            with self.subTest(model=model):
                got = rates[model]
                self.assertAlmostEqual(got["in"], inp, places=9)
                self.assertAlmostEqual(got["out"], out, places=9)
                self.assertAlmostEqual(got["cached"], cached, places=9)

    def test_the_page_no_longer_prices_the_two_deprecated_models(self):
        """The cause of 6 of 8 on 1 November 2026: the page as it is no
        longer prints Mistral Large 3 or Mistral Medium 3.5 under any name,
        so no change to the reader could find them."""
        rates, _ = self.read()
        for model in MISTRAL_DEPRECATED:
            self.assertNotIn(model, rates)
        names = [n for n, mid in self.table.PAGE_NAMES.items() if mid in MISTRAL_DEPRECATED]
        self.assertEqual(sorted(names), ["Mistral Large 3", "Mistral Medium 3.5"])
        for name in names:
            self.assertNotIn(name, self.page)

    def test_glm_5_3_is_not_read_off_the_flash_row(self):
        """The page now lists "Z.ai GLM 5.3 Flash" above "Z.ai GLM 5.3"; a
        reader that matched the shorter name as a prefix would price GLM 5.3
        at the Flash model's $0.15 and $0.50."""
        rates, _ = self.read()
        self.assertIn("Z.ai GLM 5.3 Flash", self.page)
        self.assertAlmostEqual(rates["zai-glm-5-3"]["in"], 1.4, places=9)
        self.assertAlmostEqual(rates["zai-glm-5-3"]["out"], 4.4, places=9)

    def test_the_saved_page_agrees_with_the_table(self):
        """--check-prices's own comparison finds every current model
        matching, nothing absent and the three retired models expected
        missing. Before the two deprecated models went into RETIRED it
        reported them as not found on the page."""
        out = tm.compare_with_page(self.table, self.fetch)
        self.assertEqual(out["error"], "")
        self.assertTrue(out["found"])
        self.assertEqual(out["diffs"], [])
        self.assertEqual(out["absent"], [])
        self.assertEqual(out["unlisted"], [])
        self.assertEqual(sorted(out["retired"]),
                         ["mistral-large-2512", "mistral-medium-3-5", "zai-glm-5-2"])
        self.assertEqual(out["expected"], len(MISTRAL_ON_THE_PAGE))
        self.assertEqual(out["matched"], len(MISTRAL_ON_THE_PAGE))

    def test_check_prices_prints_a_full_match(self):
        """The line a person reads: every Mistral model matches and the three
        retired ones are counted as kept, with no "not found" line."""
        real = dict(tm.TABLES)
        tm.TABLES.clear()
        tm.TABLES["mistral"] = real["mistral"]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = tm.check_prices(fetch=self.fetch)
        finally:
            tm.TABLES.clear()
            tm.TABLES.update(real)
        text = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn(f"{len(MISTRAL_ON_THE_PAGE)} of {len(MISTRAL_ON_THE_PAGE)} models match", text)
        self.assertIn("3 retired, kept at the last published price", text)
        self.assertNotIn("not found on the page", text)

    def test_the_retirement_dates_are_mistrals(self):
        """Each RETIRED date is the retirement date Mistral states, not the
        deprecation date: the API still answers to both models until 30
        April 2027, and GLM 5.2 retired on 31 October 2026."""
        self.assertEqual(self.table.RETIRED, {
            "zai-glm-5-2": "2026-10-31",
            "mistral-large-2512": "2027-04-30",
            "mistral-medium-3-5": "2027-04-30",
        })

    def test_the_deprecated_models_keep_their_last_price(self):
        """Retiring a model never moves or removes its row: each keeps one
        row from launch at its last published price, so a call before or
        after the deprecation prices the same and is still recognised."""
        before = dt.datetime(2026, 10, 1, 12, tzinfo=dt.timezone.utc)
        after = dt.datetime(2026, 11, 2, 12, tzinfo=dt.timezone.utc)
        for model, (inp, out) in MISTRAL_DEPRECATED.items():
            with self.subTest(model=model):
                rows = self.table.PRICES[model]
                self.assertEqual([r["from"] for r in rows], [""])
                self.assertEqual((rows[0]["in"], rows[0]["out"]), (inp, out))
                for when in (before, after):
                    row, ok = tm.lookup(model, when=when, provider="mistral")
                    self.assertTrue(ok)
                    c = tm.price_record(model, usage(inp=1_000_000, out=1_000_000),
                                        when=when, provider="mistral")
                    self.assertAlmostEqual(cost_of(c), inp + out, places=9)


    def test_large_4_is_read_off_the_price_table_not_the_featured_card(self):
        """Guards Mistral Large 4 going unread or half read. The page shows
        it twice: first in a featured card with input and output only, then
        in the price table with input, cached input and output. The reader
        must find it under the page's name and take all three figures from
        the table row, read off the saved page."""
        self.assertIn("Mistral Large 4", self.page)
        self.assertEqual(self.table.PAGE_NAMES["Mistral Large 4"], "mistral-large-4")
        rates, _ = self.read()
        self.assertEqual(rates["mistral-large-4"], {"in": 0.7, "cached": 0.07, "out": 2.1})

    def test_large_4_has_one_row_at_the_price_the_page_prints(self):
        """Guards a dated Large 4 row typed from an Internet Archive copy
        before it is settled. The live page prints $0.70 in, $2.10 out and
        $0.07 cached; archive copies of it printed a launch sale ($0.68,
        $2.09, $0.07) and then $1.36, $4.18 and $0.14 until a cut between 29
        October and 1 November 2026. The table takes archive prices only
        for a retired model, so Large 4 keeps a single row from launch, and
        a call on 10 October 2026 prices the same as one on 2 November 2026.
        If dated rows are approved, this test changes with them."""
        rows = self.table.PRICES["mistral-large-4"]
        self.assertEqual([r["from"] for r in rows], [""])
        self.assertEqual((rows[0]["in"], rows[0]["out"]), (0.70, 2.10))
        self.assertAlmostEqual(rows[0]["in"] * rows[0]["cache_read_mult"], 0.07, places=9)
        self.assertEqual(self.table.CACHE_WRITE_5M_MULT, 1.0)
        for when in (dt.datetime(2026, 10, 10, 12, tzinfo=dt.timezone.utc),
                     dt.datetime(2026, 11, 2, 12, tzinfo=dt.timezone.utc)):
            with self.subTest(when=when):
                row, ok = tm.lookup("mistral-large-4", when=when, provider="mistral")
                self.assertTrue(ok)
                c = tm.price_record("mistral-large-4",
                                    usage(inp=1_000_000, out=1_000_000, read=1_000_000),
                                    when=when, provider="mistral")
                self.assertAlmostEqual(cost_of(c), 0.70 + 2.10 + 0.07, places=9)

    def test_the_fallback_is_a_current_model_not_a_deprecated_one(self):
        """Guards an unknown Mistral id being priced at Mistral Medium 3.5,
        which Mistral deprecated on 31 October 2026 and no longer prices on
        its page. The fallback is mistral-large-4, the model Mistral names as
        its replacement, and an id the table does not know is still flagged
        as unrecognised."""
        self.assertEqual(self.table.FALLBACK_MODEL, "mistral-large-4")
        self.assertNotIn(self.table.FALLBACK_MODEL, self.table.RETIRED)
        row, ok = tm.lookup("mistral-made-up-9", provider="mistral")
        self.assertFalse(ok)
        self.assertEqual((row["in"], row["out"]), (0.70, 2.10))

    def test_large_4_is_recognised_under_both_names_its_card_gives(self):
        """Guards a call recorded as mistral-large-4-0 falling to the fallback
        unrecognised. Mistral Large 4's model card lists two API names for
        it, mistral-large-4 and mistral-large-4-0; both price at the one row
        and neither counts as a second model."""
        self.assertEqual(self.table.ALIASES, {"mistral-large-4-0": "mistral-large-4"})
        self.assertNotIn("mistral-large-4-0", self.table.PRICES)
        for name in ("mistral-large-4", "mistral-large-4-0"):
            with self.subTest(name=name):
                row, ok = tm.lookup(name, provider="mistral")
                self.assertTrue(ok)
                self.assertEqual((row["in"], row["out"]), (0.70, 2.10))


# Moonshot (Kimi): the page reader in pricing/moonshot.py, run on a saved
# copy of the page with a faked fetch, and each rule the table models.
#
# The saved page, fixtures/pages/moonshot_page.html, is four script tags cut
# verbatim from https://platform.kimi.ai/docs/pricing/chat as fetched on 27
# October 2026: the compiled page that holds both price tables, and the copy
# for browsers without JavaScript, whose tables are empty. Nothing in it was
# typed by hand. A test that needs a different page builds it from that copy.

MOONSHOT_PAGE_FILE = os.path.join(FIXTURES, "pages", "moonshot_page.html")


MOONSHOT_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')


# Typed from the page on 27 October 2026, not copied from the table.
MOONSHOT_ON_THE_PAGE = {
    "kimi-k3.1-pro": {"in": 2.00, "out": 10.00, "cached": 0.20, "write_5m": 2.00, "write_1h": 4.00},
    "kimi-k3.1-pro-highspeed": {"in": 4.00, "out": 20.00, "cached": 0.20, "write_5m": 4.00,
                                "write_1h": 8.00},
    "kimi-k3": {"in": 3.00, "out": 15.00, "cached": 0.30, "write_5m": 3.00, "write_1h": 6.00},
    "kimi-k2.7-code": {"in": 0.95, "out": 4.00, "cached": 0.19},
    "kimi-k2.7-code-highspeed": {"in": 1.90, "out": 8.00, "cached": 0.38},
    "kimi-k2.6": {"in": 0.95, "out": 4.00, "cached": 0.16},
}


def moonshot_payload(html):
    """The page's Next.js payload: its push chunks, decoded and joined."""
    return "".join(json.loads(m.group(1)) for m in MOONSHOT_PUSH.finditer(html))


def moonshot_as_page(*pieces):
    """A payload written back as push chunks, one script tag per piece."""
    return "".join(f"<script>self.__next_f.push([1,{json.dumps(p)}])</script>" for p in pieces)


class TestMoonshotPageReader(Base):
    def setUp(self):
        super().setUp()
        self.table = tm.TABLES["moonshot"]
        self.html = slurp(MOONSHOT_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def read(self, html):
        def fetch(url):
            self.urls.append(url)
            return html
        return self.table.page_rates(fetch, tm.md_tables)

    def test_every_model_is_read_off_the_saved_page(self):
        """The old reader looked in the markdown page for JavaScript arrays
        that are no longer there, so --check-prices found no Kimi rates at
        all. The figures now live only in the HTML's Next.js payload; every
        model and every column must come out of it, figure for figure."""
        rates, unlisted = self.read(self.html)
        self.assertEqual(rates, MOONSHOT_ON_THE_PAGE)
        self.assertEqual(unlisted, [])
        self.assertEqual(self.urls, [self.table.SOURCE])

    def test_the_saved_page_agrees_with_the_table(self):
        """A table row that drifted from the page, in any column the page
        lists, would price every Kimi call wrongly and be reported as
        checked."""
        c = tm.compare_with_page(self.table, lambda url: self.html)
        self.assertEqual((c["error"], c["found"]), ("", True))
        self.assertEqual((c["matched"], c["expected"]), (6, 6))
        self.assertEqual((c["diffs"], c["absent"], c["unlisted"], c["retired"]), ([], [], [], []))

    def test_a_table_split_across_two_pushes_is_still_read(self):
        """The page arrives in many push chunks, and a deploy can cut a
        table anywhere. A reader that looked inside one chunk would lose
        the models after the cut."""
        p = moonshot_payload(self.html)
        cut = p.index("kimi-k3.1-pro-highspeed")
        rates, _ = self.read(moonshot_as_page(p[:cut], p[cut:]))
        self.assertEqual(rates, MOONSHOT_ON_THE_PAGE)

    def test_a_model_new_on_the_page_is_named(self):
        """A model the page lists and the table lacks must be named, so it
        is added rather than priced at the fallback without anyone
        noticing. kimi-k3.1-pro was new on the page on 27 October 2026."""
        less = {k: v for k, v in self.table.PRICES.items() if k != "kimi-k3.1-pro"}
        with unittest.mock.patch.object(self.table, "PRICES", less):
            rates, unlisted = self.read(self.html)
        self.assertIn("kimi-k3.1-pro", rates)
        self.assertEqual(unlisted, ["kimi-k3.1-pro"])

    def test_an_unknown_column_is_skipped_not_guessed(self):
        """Columns are matched by title, and the two tables list different
        ones. A column the reader does not know must make it skip that
        table, never shift the figures into the wrong fields."""
        p = moonshot_payload(self.html)
        k2 = p.index("kimi-k2.7-code")
        start = p.rindex("columns:[", 0, k2)
        renamed = p[:start] + p[start:k2].replace("children:`Cached Input`", "children:`Batch Input`") + p[k2:]
        rates, _ = self.read(moonshot_as_page(renamed))
        self.assertEqual(rates, {k: v for k, v in MOONSHOT_ON_THE_PAGE.items() if k.startswith("kimi-k3")})

    def test_a_cell_not_per_million_tokens_is_skipped(self):
        """A price in another unit read as dollars per million would be a
        wrong figure by a factor of a thousand or more. Such a row is
        skipped, and --check-prices then says the model was not found."""
        p = moonshot_payload(self.html).replace("`$0.16 / MTok`", "`$0.16 / 1K tokens`")
        rates, _ = self.read(moonshot_as_page(p))
        self.assertNotIn("kimi-k2.6", rates)
        self.assertEqual(len(rates), 5)

    def test_the_empty_tables_give_no_rates(self):
        """The markdown copy and the copy for browsers without JavaScript
        render both tables empty. Read alone, either must give no rates, so
        --check-prices says the page was read but no rates were found,
        never that every model matched."""
        markdown = "## K3 Series Models\n\n<table><thead><tr /></thead><tbody /></table>\n"
        self.assertEqual(self.read(markdown), ({}, []))
        chunks = [json.loads(m.group(1)) for m in MOONSHOT_PUSH.finditer(self.html)]
        no_js = [c for c in chunks if "const DocTable=()=>null" in c]
        self.assertEqual(len(no_js), 1)
        self.assertEqual(self.read(moonshot_as_page(no_js[0])), ({}, []))


# Z.ai (GLM): the page reader in pricing/zai.py, run on a saved copy of the
# page with a faked fetch, and each rule the table models.
#
# The saved page, fixtures/pages/zai_page.md, is lines cut verbatim from the
# markdown copy of https://docs.z.ai/guides/overview/pricing as fetched on 27
# October 2026: the "Latest Models" and "Text Models" tables, and the "Other
# Pricing" accordion's blockquoted "Text Models" and "Vision Models" tables.
# Nothing in it was typed by hand.

ZAI_PAGE_FILE = os.path.join(FIXTURES, "pages", "zai_page.md")


# Typed from the page on 27 October 2026, not copied from the table:
# input, output and cached input, dollars per million tokens. "Free" is 0,
# and GLM-4-32B-0414-128K's "-" for cached input reads as its input price.
ZAI_ON_THE_PAGE = {
    "glm-5.3": (1.4, 4.4, 0.26), "glm-5.3-flash": (0.15, 0.50, 0.03),
    "glm-5.3-flashx": (0.37, 1.25, 0.075), "glm-5.3-flashx-legal": (0.37, 1.25, 0.075),
    "glm-5.2": (1.4, 4.4, 0.26), "glm-5.1": (1.4, 4.4, 0.26), "glm-5": (1.0, 3.2, 0.2),
    "glm-4.7": (0.6, 2.2, 0.11), "glm-4.6": (0.6, 2.2, 0.11),
    "glm-4.7-flashx": (0.07, 0.4, 0.01), "glm-4.5": (0.6, 2.2, 0.11),
    "glm-4.5-x": (2.2, 8.9, 0.45), "glm-4.5-air": (0.2, 1.1, 0.03),
    "glm-4.5-airx": (1.1, 4.5, 0.22), "glm-4-32b-0414-128k": (0.1, 0.1, 0.1),
    "glm-4.7-flash": (0.0, 0.0, 0.0), "glm-4.5-flash": (0.0, 0.0, 0.0),
}


# The accordion's rows, which the markdown copy writes as a blockquote.
ZAI_IN_THE_ACCORDION = ("glm-4.7-flashx", "glm-4.5", "glm-4.5-x", "glm-4.5-air", "glm-4.5-airx",
                    "glm-4-32b-0414-128k", "glm-4.7-flash", "glm-4.5-flash")


class TestZaiPageReader(Base):
    def setUp(self):
        super().setUp()
        self.table = tm.TABLES["zai"]
        self.page = slurp(ZAI_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return self.page

    def read(self):
        return self.table.page_rates(self.fetch, tm.md_tables)

    def test_every_model_is_read_off_the_saved_page(self):
        """Every text model the page prices is read, at the figures the page
        prints, from the markdown copy, and none is named as missing from
        the table."""
        rates, unlisted = self.read()
        self.assertEqual(self.urls, [self.table.SOURCE_MD])
        self.assertEqual(unlisted, [])
        self.assertEqual(sorted(rates), sorted(ZAI_ON_THE_PAGE))
        for model, (inp, out, cached) in ZAI_ON_THE_PAGE.items():
            with self.subTest(model=model):
                got = rates[model]
                self.assertAlmostEqual(got["in"], inp, places=9)
                self.assertAlmostEqual(got["out"], out, places=9)
                self.assertAlmostEqual(got["cached"], cached, places=9)

    def test_the_blockquoted_accordion_is_read(self):
        """The "Other Pricing" accordion is a blockquote in the markdown copy
        ("> | GLM-4.5 | ..."), which the table parser never saw, so
        --check-prices reported eight current models as gone from the page
        (27 October 2026)."""
        quoted = [line for line in self.page.splitlines() if line.startswith("> | GLM-4.5-AirX")]
        self.assertEqual(len(quoted), 1)
        self.assertEqual(tm.md_tables(quoted[0]), [])
        rates, _ = self.read()
        for model in ZAI_IN_THE_ACCORDION:
            with self.subTest(model=model):
                self.assertIn(model, rates)
        self.assertEqual(rates["glm-4.5-airx"], {"in": 1.1, "out": 4.5, "cached": 0.22})

    def test_the_saved_page_agrees_with_the_table(self):
        """--check-prices against the saved page: every model matches in
        every column the page lists, none is absent and none unlisted. A slip
        in a row, or a model the reader drops, fails here."""
        out = tm.compare_with_page(self.table, self.fetch)
        self.assertEqual(out["error"], "")
        self.assertTrue(out["found"])
        self.assertEqual(out["diffs"], [])
        self.assertEqual(out["absent"], [])
        self.assertEqual(out["unlisted"], [])
        self.assertEqual((out["matched"], out["expected"]), (17, 17))

    def test_vision_models_are_not_read(self):
        """The accordion's "Vision Models" table has the same columns as the
        text tables. Read, it would name GLM-4.6V and the rest as models the
        table lacks every day; its heading keeps it out."""
        rates, unlisted = self.read()
        for model in ("glm-4.6v", "glm-ocr", "glm-4.6v-flashx", "glm-4.5v", "glm-4.6v-flash"):
            with self.subTest(model=model):
                self.assertNotIn(model, rates)
                self.assertNotIn(model, unlisted)

    def test_a_model_new_on_the_page_is_named(self):
        """A model on the page that the table lacks is named, so it is added
        rather than priced silently by the lookup. GLM-5.3-FlashX-Legal was
        such a model before 27 October 2026."""
        with unittest.mock.patch.dict(self.table.PRICES):
            del self.table.PRICES["glm-5.3-flashx-legal"]
            _, unlisted = self.read()
        self.assertEqual(unlisted, ["glm-5.3-flashx-legal"])

    def test_free_and_dash_cells(self):
        """A cell reading "Free" is a price of nothing, not a missing figure, and the "-"
        GLM-4-32B-0414-128K prints for cached input means no lower rate, so
        its cached figure is its input price rather than None or zero."""
        rates, _ = self.read()
        self.assertEqual(rates["glm-4.7-flash"], {"in": 0.0, "out": 0.0, "cached": 0.0})
        self.assertEqual(rates["glm-4-32b-0414-128k"], {"in": 0.1, "out": 0.1, "cached": 0.1})


# MiniMax: the page reader in pricing/minimax.py, run on a saved copy of the
# page with a faked fetch, and each rule the table models.
#
# The saved page, fixtures/pages/minimax_page.md, is lines cut verbatim from the
# markdown copy of https://platform.minimax.io/docs/pricing/overview as fetched
# on 2 November 2026: the whole "LLM" section (the untabbed MiniMax-M3.1-Flash
# table and the "Standard" and "Priority" tabs for MiniMax-M3), the "Video"
# heading, and the "Context-IR" table under it, which is priced per million
# tokens but is not a text model. Nothing in it was typed by hand.
#
# These tests were written before the table was registered in
# pricing/__init__.py, so they import it directly and add it to tm.TABLES for
# each test; now that it is registered, that changes nothing.

MINIMAX_PAGE_FILE = os.path.join(FIXTURES, "pages", "minimax_page.md")


# Typed from the page on 2 November 2026, not copied from the table: the
# charged figures, dollars per million tokens (the struck list prices are not
# what is charged).
MINIMAX_ON_THE_PAGE = {
    "MiniMax-M3.1-Flash": {"in": 0.15, "out": 0.60, "cached": 0.015},
    "MiniMax-M3": {"in": 0.30, "out": 1.20, "cached": 0.06,
                   "long_in": 0.60, "long_out": 2.40, "long_cached": 0.12, "long_over": 512_000,
                   "fast_in": 0.45, "fast_out": 1.80, "fast_cached": 0.09,
                   "fast_long_in": 0.90, "fast_long_out": 3.60, "fast_long_cached": 0.18},
}


# The Priority tab's cache hit and over-512k figures, which the engine's
# expected_rates() had no field for until 2 November 2026.
MINIMAX_PRIORITY_EXTRAS = ("fast_cached", "fast_long_cached", "fast_long_in", "fast_long_out")


class MiniMaxBase(Base):
    def setUp(self):
        super().setUp()
        tables = unittest.mock.patch.dict(tm.TABLES, {"minimax": minimax})
        tables.start()
        self.addCleanup(tables.stop)

    def cost(self, model, speed="standard", **kw):
        return tm.price_record(model, usage(**kw), speed=speed, provider="minimax")


class TestMiniMaxPageReader(MiniMaxBase):
    def setUp(self):
        super().setUp()
        self.page = slurp(MINIMAX_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        return self.page

    def read(self, page=None):
        if page is not None:
            self.page = page
        return minimax.page_rates(self.fetch, tm.md_tables)

    def test_every_model_is_read_off_the_saved_page(self):
        """Both text models are read from the markdown copy at the figures
        the page charges, with MiniMax-M3's over-512k row as its long_
        figures and its Priority tab's two rows as its fast_ and fast_long_
        figures, each as printed, and none is named as missing from the
        table."""
        rates, unlisted = self.read()
        self.assertEqual(self.urls, [minimax.SOURCE_MD])
        self.assertEqual(unlisted, [])
        self.assertEqual(sorted(rates), sorted(MINIMAX_ON_THE_PAGE))
        for model, figures in MINIMAX_ON_THE_PAGE.items():
            with self.subTest(model=model):
                self.assertEqual(sorted(rates[model]), sorted(figures))
                for field, value in figures.items():
                    self.assertAlmostEqual(rates[model][field], value, places=9)

    def test_the_struck_list_price_is_not_read(self):
        """Each MiniMax-M3 cell prints the list price struck through before
        the charged one ("~~$0.60~~ $0.30", "Permanent 50% off"). Reading
        the first figure in the cell would check the table against twice
        what MiniMax charges."""
        self.assertIn("~~\\$0.60~~ \\$0.30", self.page)
        rates, _ = self.read()
        self.assertAlmostEqual(rates["MiniMax-M3"]["in"], 0.30, places=9)
        self.assertAlmostEqual(rates["MiniMax-M3"]["fast_in"], 0.45, places=9)

    def test_the_saved_page_agrees_with_the_table(self):
        """--check-prices against the saved page: both models match in every
        column the page lists, none is absent and none unlisted. A slip in a
        row, or a model the reader drops, fails here.

        The Priority tab's cache hit and over-512k figures are compared by
        the engine's expected_rates(), the one place the priority rule
        lives. Until that function gives a field for one of them, the field
        must still come back as a difference (the table's figure None), so
        the check fails rather than pass a figure it never compared; the
        reader once checked them against its own copy of the engine's
        arithmetic instead. Once the fields exist, this is 2 of 2 with no
        difference at all."""
        out = tm.compare_with_page(minimax, self.fetch)
        exp = tm.expected_rates(minimax.PRICES["MiniMax-M3"][-1], minimax)
        pending = [f for f in MINIMAX_PRIORITY_EXTRAS if f not in exp]
        self.assertEqual(out["error"], "")
        self.assertTrue(out["found"])
        self.assertEqual(out["diffs"], [("MiniMax-M3", f, None, MINIMAX_ON_THE_PAGE["MiniMax-M3"][f])
                                        for f in sorted(pending)])
        self.assertEqual(out["absent"], [])
        self.assertEqual(out["unlisted"], [])
        self.assertEqual((out["matched"], out["expected"]), (2 - bool(pending), 2))

    def test_only_the_llm_section_is_read(self):
        """MiniMax-H3-Context-IR sits under Video with per-million-token
        columns. Read, it would be named every day as a text model the table
        lacks; only the LLM section's tables are read."""
        self.assertIn("MiniMax-H3-Context-IR", self.page)
        rates, unlisted = self.read()
        self.assertNotIn("MiniMax-H3-Context-IR", rates)
        self.assertNotIn("MiniMax-H3-Context-IR", unlisted)

    def test_a_model_new_on_the_page_is_named(self):
        """A model the page lists and the table lacks is named, so
        --check-prices fails until it is added."""
        with unittest.mock.patch.dict(minimax.PRICES):
            del minimax.PRICES["MiniMax-M3.1-Flash"]
            _, unlisted = self.read()
        self.assertEqual(unlisted, ["MiniMax-M3.1-Flash"])

    def test_a_changed_priority_cache_or_long_figure_is_a_difference(self):
        """The Priority tab's cache hit and over-512k row are read as
        printed, not worked out in the price file. A Priority cache price or
        long output price that moves must come back as a difference on that
        field at the page's new figure, not pass unread."""
        for field, old, new, value in (
                ("fast_cached", "~~\\$0.18~~ \\$0.09", "~~\\$0.18~~ \\$0.10", 0.10),
                ("fast_long_out", "~~\\$7.20~~ \\$3.60", "~~\\$7.20~~ \\$3.70", 3.70)):
            with self.subTest(field=field):
                self.page = self.page.replace(old, new)
                self.assertIn(new, self.page)
                rates, unlisted = self.read()
                self.assertEqual(unlisted, [])
                self.assertAlmostEqual(rates["MiniMax-M3"][field], value, places=9)
                out = tm.compare_with_page(minimax, self.fetch)
                self.assertIn(field, [f for m, f, _, _ in out["diffs"] if m == "MiniMax-M3"])
                got = next(v for m, f, _, v in out["diffs"] if (m, f) == ("MiniMax-M3", field))
                self.assertAlmostEqual(got, value, places=9)
                self.assertEqual(out["matched"], 1)
                self.page = self.page.replace(new, old)

    def test_a_lost_priority_tab_long_row_or_cache_column_is_named(self):
        """A Priority tab renamed ("Priority Tier") or removed used to drop
        its rows from the reading, so --check-prices said "2 of 2 models
        match" with MiniMax-M3's fast price never compared. A model whose
        row charges a rate the page no longer gives (a lost tab, a lost
        over-512k row, a dropped cache column) must be named with the
        fields missing, so the check fails. It is reported as the page not
        read, never among the models the table lacks: there it printed
        "2 of 2 models match" over "on the page but not in the table:
        MiniMax-M3 (not on the page: ...)", which contradicts itself. The
        startup lookup, which asks only for ids the table lacks, still
        reads the page."""
        fast = "fast_cached, fast_in, fast_long_cached, fast_long_in, fast_long_out, fast_out"
        start = self.page.index("> [tab] Priority")
        end = self.page.index("\n", self.page.index("~~\\$7.20~~", start)) + 1
        flash = ("| **Model** | **Input** \\$ / M tokens | **Output** \\$ / M tokens |\n"
                 "| :- | :-: | :-: |\n"
                 "| **MiniMax-M3.1-Flash** | \\$0.15 | \\$0.60 |\n")
        flash_at = self.page.index("| **Model**")
        flash_end = self.page.index("\n", self.page.index("\\$0.015 |")) + 1
        long_row = self.page.index("> | **MiniMax-M3** > 512k input tokens\\*")
        long_end = self.page.index("\n", long_row) + 1
        cases = {
            "renamed tab": (self.page.replace("> [tab] Priority\\*", "> [tab] Priority Tier\\*"),
                            f"MiniMax-M3 (not on the page: {fast})"),
            "removed tab": (self.page[:start] + self.page[end:],
                            f"MiniMax-M3 (not on the page: {fast})"),
            "no over-512k row": (self.page[:long_row] + self.page[long_end:],
                                 "MiniMax-M3 (not on the page: long_cached, long_in, long_out,"
                                 " long_over)"),
            "no cache column": (self.page[:flash_at] + flash + self.page[flash_end:],
                                "MiniMax-M3.1-Flash (not on the page: cached)"),
        }
        saved = self.page
        for case, (page, named) in cases.items():
            with self.subTest(case=case):
                self.assertNotEqual(page, saved)
                self.page = page
                with self.assertRaises(ValueError) as raised:
                    minimax.page_rates(self.fetch, tm.md_tables)
                self.assertIn(named, str(raised.exception))
                rates, unlisted = minimax.page_rates(self.fetch, tm.md_tables,
                                                     want=("MiniMax-M4",))
                self.assertEqual(unlisted, [])
                self.assertEqual(sorted(rates), sorted(MINIMAX_ON_THE_PAGE))
                out = tm.compare_with_page(minimax, self.fetch)
                self.assertIn(named, out["error"])
                self.assertFalse(out["found"])
                self.assertEqual(out["unlisted"], [])

    def test_an_unexpected_row_label_is_not_read(self):
        """A model cell is read only as its id, a prompt-length tier and a
        "Permanent N% off" label. A discount that gains an end date needs
        dated rows, so a changed label leaves the model unread (named as not
        found on the page) rather than read at figures that may expire."""
        page = self.page.replace("Permanent 50% off", "50% off until 30 November 2026")
        self.assertNotEqual(page, self.page)
        rates, _ = self.read(page)
        self.assertNotIn("MiniMax-M3", rates)
        self.assertIn("MiniMax-M3.1-Flash", rates)

    def test_a_second_threshold_is_named(self):
        """The engine holds one prompt-length threshold per row. A page whose
        Priority tab splits at a different length than the Standard tab must
        be named, not read as one of them, and reported as the page not read
        rather than as a model the table lacks."""
        page = self.page.replace("**MiniMax-M3** > 512k input tokens Permanent",
                                 "**MiniMax-M3** > 256k input tokens Permanent")
        self.assertNotEqual(page, self.page)
        with self.assertRaises(ValueError) as raised:
            self.read(page)
        self.assertIn("MiniMax-M3 (more than one prompt-length threshold)",
                      str(raised.exception))
        rates, unlisted = minimax.page_rates(self.fetch, tm.md_tables, want=("MiniMax-M4",))
        self.assertNotIn("MiniMax-M3", rates)
        self.assertEqual(unlisted, [])


# Xiaomi MiMo: the page reader in pricing/mimo.py, run on a saved copy of the
# page with a faked fetch, and each rule the table models.
#
# The saved page, fixtures/pages/mimo_page.md, is lines cut verbatim from the
# markdown source of the price page,
# https://mimo.mi.com/static/docs/price/pay-as-you-go.md, as fetched on 2
# November 2026: the page's opening and billing note, the domestic 'Language
# Models' table in yuan, and the overseas section's 'Language Models' and 'ASR
# Series' tables in dollars. Nothing in it was typed by hand.
#
# These tests were written before the table was registered in
# pricing/__init__.py, so they put it into tm.TABLES for the length of each
# test; now that it is registered, that changes nothing.

MIMO_PAGE_FILE = os.path.join(FIXTURES, "pages", "mimo_page.md")


# Typed from the page's overseas 'Real-time API' rows on 2 November 2026, not
# copied from the table: input (cache miss), output and input (cache hit),
# dollars per million tokens.
MIMO_ON_THE_PAGE = {
    "mimo-v2.6-pro": (0.435, 0.87, 0.0036),
    "mimo-v2.6-flash": (0.14, 0.28, 0.0028),
    "mimo-v2.6-pro-ultraspeed": (4.35, 8.7, 0.036),
}


class WithMimo(Base):
    def setUp(self):
        super().setUp()
        tables = unittest.mock.patch.dict(tm.TABLES, {"mimo": mimo})
        tables.start()
        self.addCleanup(tables.stop)


class TestMimoPageReader(WithMimo):
    def setUp(self):
        super().setUp()
        self.page = slurp(MIMO_PAGE_FILE, encoding="utf-8")
        self.urls = []

    def read(self, page=None):
        def fetch(url):
            self.urls.append(url)
            return self.page if page is None else page
        return mimo.page_rates(fetch, tm.md_tables)

    def overseas(self):
        """The fixture's overseas section, from its heading on."""
        at = self.page.index("### Overseas Pricing of the Model")
        return self.page[:at], self.page[at:]

    def test_every_model_is_read_off_the_saved_page(self):
        """Every overseas real-time model is read at the figures the page
        prints, from the markdown source, including the two rows after the
        first in the group, which carry no 'Inference Type' cell because the
        first row's spans them; none is named as missing from the table."""
        rates, unlisted = self.read()
        self.assertEqual(self.urls, [mimo.SOURCE_MD])
        self.assertEqual(unlisted, [])
        self.assertEqual(sorted(rates), sorted(MIMO_ON_THE_PAGE))
        for model, (inp, out, cached) in MIMO_ON_THE_PAGE.items():
            with self.subTest(model=model):
                self.assertEqual(rates[model], {"in": inp, "out": out, "cached": cached})

    def test_the_saved_page_agrees_with_the_table(self):
        """--check-prices's own comparison finds every model in the table on
        the saved page, matching in every column, with nothing missing either
        way: a slip in a row, or in the page reader, fails here."""
        c = tm.compare_with_page(mimo, lambda url: self.page)
        self.assertEqual(c["error"], "")
        self.assertEqual((c["matched"], c["expected"]), (3, 3))
        self.assertEqual((c["diffs"], c["absent"], c["unlisted"]), ([], [], []))

    def test_yuan_figures_are_never_read(self):
        """The domestic section prices the same ids in yuan. Without the
        overseas section the reader must find nothing, rather than read a
        yuan figure as dollars."""
        domestic, _ = self.overseas()
        self.assertIn("¥3.00", domestic)
        self.assertEqual(self.read(domestic), ({}, []))

    def test_batch_rows_are_left_out(self):
        """The 'Batch API' rows price mimo-v2.6-pro and mimo-v2.6-flash at
        half the real-time figures. A log cannot tell a batch call, so the
        reader must never return a batch figure, even when a batch row is the
        only row left for a model."""
        domestic, overseas = self.overseas()
        self.assertIn("$0.2175", overseas)
        self.assertEqual(self.read()[0]["mimo-v2.6-pro"]["in"], 0.435)
        no_real_time = overseas.replace("Real-time API", "Some other API")
        self.assertEqual(self.read(domestic + no_real_time), ({}, []))

    def test_a_changed_unit_reads_nothing(self):
        """The cells print '$0.435' with no unit; the unit is in the billing
        note. If that note no longer says dollars per million tokens for
        overseas, the figures' unit is unknown and nothing is read."""
        note = "Overseas: dollar / M tokens"
        self.assertIn(note, self.page)
        page = self.page.replace(note, "Overseas: dollar / K tokens")
        self.assertEqual(self.read(page), ({}, []))

    def test_a_model_new_on_the_page_is_named(self):
        """A model the page lists and the table lacks is named, and the one it
        replaced is reported as not found on the page."""
        domestic, overseas = self.overseas()
        page = domestic + overseas.replace("`mimo-v2.6-flash`", "`mimo-v2.7-flash`", 1)
        rates, unlisted = self.read(page)
        self.assertEqual(unlisted, ["mimo-v2.7-flash"])
        self.assertEqual(rates["mimo-v2.7-flash"], {"in": 0.14, "out": 0.28, "cached": 0.0028})
        c = tm.compare_with_page(mimo, lambda url: page)
        self.assertEqual((c["absent"], c["unlisted"]), (["mimo-v2.6-flash"], ["mimo-v2.7-flash"]))

    def test_a_cell_that_is_not_a_dollar_figure_is_skipped(self):
        """A price cell that is not a plain dollar figure drops its row rather
        than being guessed at, so the model reads as not found."""
        domestic, overseas = self.overseas()
        self.assertEqual(overseas.count("$0.87<"), 1)
        rates, _ = self.read(domestic + overseas.replace("$0.87<", "0.87<"))
        self.assertNotIn("mimo-v2.6-pro", rates)
        self.assertIn("mimo-v2.6-flash", rates)

    def test_an_unknown_column_skips_the_table(self):
        """Columns are matched by title. A table with a column title the
        reader does not know is skipped whole, never read by position."""
        page = self.page.replace("**Input (Cache Miss)** ", "**Input (Cache Miss, per K)** ")
        self.assertEqual(self.read(page), ({}, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
