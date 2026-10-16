"""The network: the online price lookup, --check-prices and exchange rates.

Every fetch is faked, and urlopen itself refuses and counts, so nothing here
uses the network.
"""

import datetime as dt
import json
import os
import time
import unittest

from helpers import (ANTHROPIC_PAGE, Base, cli, cost_of, payload_of, record, slurp, terminal, tm,
                     usage)


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

    GOOGLE_PAGE = (
        '<h2 id="g">Gemini 9 Flash</h2><p><code>gemini-9-flash</code></p><table><tbody>'
        '<tr><td>Input price</td><td>Free</td>'
        '<td>$0.75 ; $1.50 starting January 1, 2027</td></tr>'
        '<tr><td>Output price</td><td>Free</td>'
        '<td>$3.75 ; $7.50 starting January 1, 2027</td></tr>'
        '<tr><td>Context caching price</td><td>Free</td>'
        '<td>$0.075 ; $0.15 starting January 1, 2027</td></tr>'
        '</tbody></table>')

    def test_a_looked_up_price_keeps_its_dates(self):
        """A page with a launch price and a later one was saved as one row at
        the later price, so every call was charged it from the first day."""
        def fetch(url):
            self.fetched.append(url)
            if url == tm.TABLES["google"].SOURCE:
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
        OpenAI's figure, though Google's starts above 200,000."""
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
        for name in ("openai", "google", "xai"):
            table = tm.TABLES[name]
            with self.subTest(table=name):
                long = [x["long"] for rows in table.PRICES.values() for x in rows if x.get("long")]
                self.assertTrue(long and all(x["over"] == table.LONG_OVER for x in long))

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
        page = "".join(l for l in self.anthropic_page().splitlines(True) if "Claude Haiku 3.5" not in l)
        code, out = self.run_check(lambda url: page)
        self.assertIn("not found on the page: claude-haiku-3-5", out)

    def test_a_retired_model_missing_from_the_page_is_expected(self):
        page = "".join(l for l in self.anthropic_page().splitlines(True) if "Claude Haiku 3.5" not in l)
        tm._anthropic.RETIRED = {"claude-haiku-3-5": "2026-01-01"}
        try:
            code, out = self.run_check(lambda url: page)
        finally:
            del tm._anthropic.RETIRED
        self.assertEqual(code, 0)
        self.assertNotIn("not found", out)
        self.assertIn("19 of 19", out)
        self.assertIn("1 retired, kept at the last published price", out)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
