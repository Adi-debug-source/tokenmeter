#!/usr/bin/env python3
"""Tests for tokenmeter.py.

Standard library only, so this runs wherever the tool runs:

    python3 tests/test_tokenmeter.py

Most tests here exist because something was once wrong. The bug each one
guards is named in its docstring, so a failure says what broke rather than
only that something did. Nothing reads a real history and nothing touches the
network: fixtures are built in a temp directory and every fetch is faked, so
the suite is fast, deterministic and safe to run on any machine.
"""

import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tokenmeter as tm


def slurp(path, **kw):
    with open(path, **kw) as f:
        return f.read()


def usage(inp=0, out=0, read=0, w5=0, w1=0, think=0, searches=0, speed=None):
    u = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
         "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1},
         "output_tokens_details": {"thinking_tokens": think},
         "server_tool_use": {"web_search_requests": searches}}
    if speed:
        u["speed"] = speed
    return u


def record(mid, model="claude-opus-5", ts="2026-09-01T12:00:00.000Z", **kw):
    return json.dumps({"type": "assistant", "timestamp": ts, "uuid": mid,
                       "requestId": mid, "cwd": "/tmp",
                       "message": {"id": mid, "model": model, "usage": usage(**kw)}})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects", "-proj")
        os.makedirs(self.projects)
        self.ledger = os.path.join(self.tmp, "ledger.jsonl")
        tm._ROOTS[:] = [os.path.join(self.tmp, "projects")]
        tm._LEDGER[:] = [self.ledger]
        tm.CURRENT_RATES.clear()
        tm.DISPLAY.update(code="USD", symbol="$", rate=1.0, when="", live=True)
        # Sealed off from the machine running the tests: no other harness's
        # real logs, no network, no saved price lookups, no exchange rates.
        for name in tm.ADAPTERS:
            if name != "claude-code":
                tm.ADAPTER_ROOTS[name] = [os.path.join(self.tmp, "no-" + name)]
        tm._ONLY.clear()
        tm._IMPORTS.clear()
        tm._OWNER.clear()
        tm._PROJECT.clear()
        tm._SESSION.clear()
        tm.ONLINE_LOOKUP[0] = False
        tm.PRICE_CACHE = os.path.join(self.tmp, "prices.json")
        tm._PRICE_STATE.update(loaded=False, data={"fetched": {}, "misses": {}})
        tm.LOOKUPS.clear()
        # The rate cache lives in the temp folder, never beside the engine, and
        # each test starts as a new run would, with nothing remembered.
        tm.FX_CACHE = os.path.join(self.tmp, "fx_rates.json")
        tm._FX_MEMO.clear()
        self._fx = tm.fx_rates
        tm.fx_rates = lambda: (dict(tm.FALLBACK_RATES), "test", False)

    def tearDown(self):
        tm._ROOTS.clear()
        tm._LEDGER.clear()
        tm.CURRENT_RATES.clear()
        tm.ADAPTER_ROOTS.clear()
        tm.fx_rates = self._fx
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, *lines):
        p = os.path.join(self.projects, name)
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        return p


class TestMoney(Base):
    """"$0.0000" turned up in the menu bar. Three brackets, four faults."""

    def test_zero_is_two_decimals(self):
        """Zero read as $0.0000, which is not how anyone writes nothing."""
        self.assertEqual(tm.money(0), "$0.00")

    def test_ordinary_amounts_are_two_decimals(self):
        """48 pence used to print as $0.4800."""
        self.assertEqual(tm.money(0.48), "$0.48")
        self.assertEqual(tm.money(508.17), "$508.17")

    def test_thousands_keep_their_decimals(self):
        """Rounding above 1000 made the caching block fail to add up on screen."""
        self.assertEqual(tm.money(2533.428), "$2,533.43")
        self.assertEqual(tm.money(1000), "$1,000.00")

    def test_sub_penny_keeps_precision(self):
        """One cheap Haiku call must not read as free."""
        self.assertEqual(tm.money(0.0029), "$0.0029")

    def test_too_small_to_print_says_so(self):
        """A real amount below 0.00005 would round to $0.0000, reading as zero."""
        self.assertEqual(tm.money(0.0000004), "<$0.0001")
        self.assertNotEqual(tm.money(0.0000004), "$0.0000")

    def test_rates_keep_four_decimals(self):
        """The per-million rate is read against $5.00; $0.48 loses the point."""
        self.assertEqual(tm.unit_money(0.47612), "$0.4761")

    def test_currency_conversion_applies(self):
        tm.DISPLAY.update(code="GBP", symbol="£", rate=0.5)
        self.assertEqual(tm.money(100), "£50.00")

    def test_a_negative_amount_puts_its_minus_first(self):
        """A saving below zero printed as $-0.10; money is written -$0.10.
        Every bracket keeps the rule, and the digits are the positive ones."""
        self.assertEqual(tm.money(-0.1), "-$0.10")
        self.assertEqual(tm.money(-2533.428), "-$2,533.43")
        self.assertEqual(tm.money(-0.0029), "-$0.0029")
        self.assertEqual(tm.money(-0.0000004), "-<$0.0001")
        for x in (0.125, 2.675, 1.005, 0.00415):
            self.assertEqual(tm.money(-x), "-" + tm.money(x))
        tm.DISPLAY.update(code="GBP", symbol="£", rate=0.5)
        self.assertEqual(tm.money(-100), "-£50.00")


class TestMoneyOnEveryFace(Base):
    """The menu bar and the dashboard each carry their own copy of money(),
    in Swift and JavaScript. No Python test can run them, so these read their
    source for the parts that once disagreed with the terminal."""

    def swift(self):
        return slurp(os.path.join(os.path.dirname(FIXTURES), "..", "costbar", "main.swift"),
                     encoding="utf-8")

    def test_separators_do_not_follow_the_macs_language(self):
        """The menu bar's NumberFormatter and the dashboard's
        toLocaleString(undefined) took the system's locale, so on a Mac set to
        German they printed 1.234,50 beside a sub-penny 0.0042 and a terminal
        printing 1,234.50."""
        swift = self.swift()
        formatter = swift[swift.index("let groupedTwoDP"):swift.index("}()", swift.index("let groupedTwoDP"))]
        for line in ('f.locale = Locale(identifier: "en_US_POSIX")', 'f.groupingSeparator = ","',
                     'f.decimalSeparator = "."', "f.usesGroupingSeparator = true"):
            self.assertIn(line, formatter)
        calls = re.findall(r"toLocaleString\(([^)]*)\)", tm.DASH_JS)
        self.assertTrue(calls)
        for args in calls:
            self.assertTrue(args.startswith("'en-US'"), args)

    def test_every_copy_puts_the_minus_first(self):
        """$-0.10 was printed by all three copies; changing one alone would
        make the same saving read two ways."""
        swift = self.swift()
        money_swift = swift[swift.index("func money("):swift.index("func shownDifference")]
        fmt_js = tm.DASH_JS[tm.DASH_JS.index("function fmt("):tm.DASH_JS.index("let CUR")]
        for body in (money_swift, fmt_js):
            self.assertIn("sign + s + ", body)
            self.assertNotIn("return s + x", body)
            self.assertNotIn("return s + String(format", body)


class TestReportWording(Base):
    """The terminal report's words, where they once said something wrong."""

    def report(self, by=""):
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        return terminal(overall, groups, meta, unknown, by, "all time")

    def test_one_call_is_one_call(self):
        """The header read "1 API calls" and every --by table "1 calls"."""
        self.write("a.jsonl", record("msg_1", out=1000))
        out = self.report("model")
        self.assertIn("   1 API call\n", out)
        self.assertIn("   1 call  ", out)
        self.assertNotIn("1 API calls", out)
        self.assertNotIn("1 calls", out)
        self.assertIn("1 call  ", self.report("source"))
        self.write("b.jsonl", record("msg_2", out=10))
        self.assertIn("   2 API calls\n", self.report())

    def test_one_call_keeps_the_table_in_line(self):
        """'call' is a letter shorter than 'calls'; the bars must still start
        in one column."""
        self.write("a.jsonl", record("msg_1", out=1000),
                   record("msg_2", out=1000, ts="2026-09-02T12:00:00.000Z"),
                   record("msg_3", model="claude-opus-4-8", out=1000))
        rows = [ln for ln in self.report("model").splitlines() if "█" in ln and "call" in ln]
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual(rows[0].index("█"), rows[1].index("█"))

    def test_the_dollar_bracket_follows_moneys_rule(self):
        """Beside another currency the dollar figure had its own two-decimal
        rule, so a sub-penny total read "£0.0056 ($0.01)"."""
        self.write("a.jsonl", record("msg_1", out=300))      # $0.0075
        tm.DISPLAY.update(code="GBP", symbol="£", rate=0.75)
        head = self.report().splitlines()[3]
        self.assertIn("£0.0056", head)
        self.assertIn("($0.0075)", head)
        self.assertEqual(tm.format_money(2533.428, "$"), "$2,533.43")
        self.assertEqual(tm.format_money(-0.1, "€"), "-€0.10")


class TestWhenCachingCostsMore(Base):
    """One call that writes 20,000 tokens to the 1-hour cache and reads none
    costs more than the same tokens billed fresh. Every face assumed a saving:
    the terminal read "saved $-0.10 -99.7% cheaper, 0.5x" over "0.0% of prompt
    tokens came from cache at $0.0000 per million", the dashboard "Caching
    made it 0.5x less expensive", and the menu bar the same as the terminal."""

    def setUp(self):
        super().setUp()
        self.write("a.jsonl", record("msg_1", inp=5, out=10, w1=20000))
        self.result = tm.collect(tm.transcripts(), ledger=False)

    def test_the_terminal_names_it_a_cost(self):
        out = terminal(*self.result, "", "all time")
        self.assertRegex(out, r"\n    caching cost +\$0\.10   99\.7% dearer\n")
        for wrong in ("saved", "cheaper", "-$", "$-", "came from cache", "per million"):
            self.assertNotIn(wrong, out)

    def test_the_dashboard_names_it_a_cost(self):
        out = os.path.join(self.tmp, "d.html")
        tm.render_html(*self.result, "all time", out)
        page = slurp(out, encoding="utf-8")
        self.assertIn("<h3>Caching cost</h3>", page)
        self.assertIn("99.7% dearer. Writing to the cache cost more than reading from it saved.", page)
        # The positive difference, which the currency switcher recomputes.
        self.assertIn('data-usd-big="0.20027500" data-usd-small="0.10027500"', page)
        self.assertIn("0 of those prompt tokens were cache hits.</small>", page)
        for wrong in ("<h3>Saved</h3>", "less expensive", "cheaper", "per million", ">-$0"):
            self.assertFalse(wrong in page, wrong)

    def test_the_menu_bar_names_it_a_cost(self):
        swift = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "costbar", "main.swift"),
                      encoding="utf-8")
        self.assertIn('(dearer ? "Caching cost" : "Saved", shownSaved)', swift)
        self.assertIn('"%.1f%% dearer"', swift)
        self.assertIn("shownDifference(snap.all.total, snap.withoutCache)", swift)

    def test_a_saving_still_reads_as_one(self):
        self.write("b.jsonl", record("msg_2", inp=5, out=10, read=800000))
        overall, *rest = tm.collect(tm.transcripts(), ledger=False)
        out = terminal(overall, *rest, "", "all time")
        self.assertRegex(out, r"\n    saved +\$\d+\.\d\d   \d+\.\d% cheaper, \d+\.\dx\n")
        self.assertIn("of prompt tokens came from cache at $0.5000 per million", out)
        self.assertNotIn("dearer", out)

    def test_nothing_cached_is_neither_a_cost_nor_below_zero(self):
        """The two totals add the same parts in a different order, so with
        nothing cached they can differ in the last bit; that is not a cost,
        and must not print "-0.0% cheaper"."""
        self.assertFalse(tm.caching_dearer(0.3, 0.1 + 0.2))
        self.assertFalse(tm.caching_dearer(1.0, 1.0 + 1e-16))
        self.assertTrue(tm.caching_dearer(0.100275, 0.200275))
        overall, *rest = tm.collect([], ledger=False)
        overall["tokens"]["input"] = 100
        overall["total"], overall["no_cache"] = 0.1 + 0.2, 0.3
        out = terminal(overall, *rest, "", "all time")
        self.assertIn("0.0% cheaper, 1.0x", out)
        self.assertNotIn("-0.0%", out)
        self.assertNotIn("came from cache", out)


class TestReconciledColumn(Base):
    """with + saved must equal without as printed, in every currency."""

    def test_column_adds_up_after_rounding(self):
        """Three exact figures rounded separately left GBP a penny out."""
        for rate in (1.0, 0.739741, 95.0, 153.0, 1.38):
            with self.subTest(rate=rate):
                tm.DISPLAY.update(rate=rate, symbol="$")
                total, no_cache = 512.23107180, 2549.35816400
                shown = tm.shown_difference(no_cache, total)
                a = round(total * rate, 2)
                b = round(no_cache * rate, 2)
                self.assertAlmostEqual(a + round(shown * rate, 2), b, places=2)

    def test_shown_difference_is_close_to_the_truth(self):
        """It may not exceed half a penny against the real saving."""
        tm.DISPLAY.update(rate=1.0)
        self.assertAlmostEqual(tm.shown_difference(2549.358, 512.231),
                               2549.358 - 512.231, places=2)


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


class TestPublishedRates(Base):
    """The whole table against platform.claude.com, checked 11 September 2026.
    Sonnet 5.5 added from the same page on 6 October 2026.

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
        "claude-sonnet-5-5": (2, 10, 0.20),
        "claude-sonnet-4-6": (3, 15, 0.30), "claude-sonnet-4-5": (3, 15, 0.30),
        "claude-sonnet-4": (3, 15, 0.30), "claude-haiku-4-5": (1, 5, 0.10),
        "claude-haiku-3-5": (0.8, 4, 0.08),
    }

    def test_every_rate_matches_the_pricing_page(self):
        for model, (inp, out, hit) in self.OFFICIAL.items():
            with self.subTest(model=model):
                row, known = tm.lookup(model)
                self.assertTrue(known, f"{model} falls back to Opus rates")
                self.assertEqual(row["in"], inp)
                self.assertEqual(row["out"], out)
                self.assertAlmostEqual(row["in"] * row["cache_read_mult"], hit, places=9)

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


class TestDeduplication(Base):
    def test_same_call_in_two_files_counts_once(self):
        """Resuming a session copies earlier messages into a new transcript."""
        self.write("a.jsonl", record("msg_1", out=100))
        self.write("b.jsonl", record("msg_1", out=100))
        evs = list(tm.iter_events(tm.transcripts(), ledger=False))
        self.assertEqual(len(evs), 1)

    def test_streaming_partials_take_the_complete_copy(self):
        """Keeping the first copy priced a finished answer at four tokens in.
        This cost 212k output tokens, 7% of all output."""
        self.write("a.jsonl",
                   record("msg_1", out=4),
                   record("msg_1", out=4),
                   record("msg_1", out=1160))
        evs = list(tm.iter_events(tm.transcripts(), ledger=False))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["cost"]["_tokens"]["output"], 1160)

    def test_attribution_does_not_depend_on_the_order_files_are_read(self):
        """merge() kept the first sighting's time, session and project, and
        Claude Code's files arrive in whatever order the filesystem lists
        them, so a call copied into a resumed session was filed under either
        session depending on the machine. The earliest copy now keeps them."""
        early = self.write("sess-a.jsonl", record("msg_1", ts="2026-09-01T12:00:00.000Z", out=4))
        fork = os.path.join(self.tmp, "projects", "-fork")
        os.makedirs(fork)
        late = os.path.join(fork, "sess-b.jsonl")
        with open(late, "w") as f:
            f.write(record("msg_1", ts="2026-09-03T08:00:00.000Z", out=1160) + "\n")
        for order in ([early, late], [late, early]):
            with self.subTest(first=os.path.basename(order[0])):
                ev = tm.scan_transcripts(order)["msg_1"]
                self.assertEqual(ev["session"], "sess-a")
                self.assertEqual(ev["project"], "-proj")
                self.assertEqual(ev["when"], dt.datetime(2026, 9, 1, 12, tzinfo=dt.timezone.utc))
                # The complete usage block still wins, wherever it was written.
                self.assertEqual(ev["_usage"]["output_tokens"], 1160)
                _, groups, *_ = tm.collect(order, ledger=False)
                self.assertEqual(set(groups["session"]), {"sess-a"})

    def test_a_tie_keeps_the_first_sighting_and_a_date_beats_none(self):
        same = "2026-09-01T12:00:00.000Z"
        a = self.write("sess-a.jsonl", record("msg_1", ts=same, out=10))
        b = self.write("sess-b.jsonl", record("msg_1", ts=same, out=10))
        self.assertEqual(tm.scan_transcripts([a, b])["msg_1"]["session"], "sess-a")
        self.assertEqual(tm.scan_transcripts([b, a])["msg_1"]["session"], "sess-b")
        line = json.loads(record("msg_1", out=10))
        del line["timestamp"]
        undated = self.write("sess-c.jsonl", json.dumps(line))
        for order in ([undated, b], [b, undated]):
            with self.subTest(first=os.path.basename(order[0])):
                self.assertEqual(tm.scan_transcripts(order)["msg_1"]["session"], "sess-b")

    def test_synthetic_records_are_not_billed(self):
        self.write("a.jsonl", record("msg_1", model="<synthetic>", out=500))
        self.assertEqual(list(tm.iter_events(tm.transcripts(), ledger=False)), [])

    def test_subagent_transcripts_are_counted(self):
        """A */*.jsonl glob silently dropped every subagent's tokens."""
        sub = os.path.join(self.projects, "sess", "subagents")
        os.makedirs(sub)
        with open(os.path.join(sub, "agent-x.jsonl"), "w") as f:
            f.write(record("msg_sub", out=50) + "\n")
        self.assertEqual(len(list(tm.iter_events(tm.transcripts(), ledger=False))), 1)


class TestLedger(Base):
    def test_row_round_trips(self):
        u = usage(inp=2, out=1160, read=44115, w1=1854, think=500, searches=3)
        when = dt.datetime(2026, 9, 1, 12, tzinfo=dt.timezone.utc)
        row = tm.usage_to_row("msg_1", when, "claude-opus-5", "-proj", "sess", u)
        back = tm.row_to_usage(row)
        a = tm.price_record("claude-opus-5", u)
        b = tm.price_record("claude-opus-5", back)
        for k in tm.COMPONENTS:
            self.assertAlmostEqual(a[k], b[k], places=12, msg=k)

    def test_zero_fields_are_omitted(self):
        row = tm.usage_to_row("m", None, "claude-opus-5", "p", "s", usage(inp=5))
        self.assertNotIn("r", row)
        self.assertEqual(row["in"], 5)

    def test_survives_transcript_deletion(self):
        """The whole point: an all time that outlives cleanupPeriodDays."""
        self.write("a.jsonl", record("msg_1", out=1000))
        self.write("b.jsonl", record("msg_2", out=2000))
        before = sum(sum(e["cost"][k] for k in tm.COMPONENTS)
                     for e in tm.iter_events(tm.transcripts()))
        os.remove(os.path.join(self.projects, "a.jsonl"))
        after = sum(sum(e["cost"][k] for k in tm.COMPONENTS)
                    for e in tm.iter_events(tm.transcripts()))
        self.assertAlmostEqual(before, after, places=12)
        without = sum(sum(e["cost"][k] for k in tm.COMPONENTS)
                      for e in tm.iter_events(tm.transcripts(), ledger=False))
        self.assertLess(without, before)

    def test_append_only_never_rewrites(self):
        """It is versioned in git; a rewrite puts the file in every diff."""
        self.write("a.jsonl", record("msg_1", out=100))
        list(tm.iter_events(tm.transcripts()))
        first = slurp(self.ledger)
        self.write("b.jsonl", record("msg_2", out=200))
        list(tm.iter_events(tm.transcripts()))
        second = slurp(self.ledger)
        self.assertTrue(second.startswith(first), "existing lines were rewritten")

    def test_a_damaged_line_does_not_lose_the_history(self):
        self.write("a.jsonl", record("msg_1", out=100))
        list(tm.iter_events(tm.transcripts()))
        with open(self.ledger, "a") as f:
            f.write("this is not json\n")
        self.assertEqual(len(tm.read_ledger(self.ledger)), 1)

    def test_a_bigger_copy_supersedes(self):
        rows = tm.read_ledger
        tm.append_ledger([tm.usage_to_row("m", None, "claude-opus-5", "p", "s", usage(out=4))])
        tm.append_ledger([tm.usage_to_row("m", None, "claude-opus-5", "p", "s", usage(out=1160))])
        got = tm.read_ledger(self.ledger)
        self.assertEqual(got["m"]["o"], 1160)


class TestFiltersReachTheLedger(Base):
    """Calls restored from the ledger have no file, so a filter applied only to
    files let them all back in: a one-session report with the ledger on showed
    the whole history, $1,079 where the session had cost $95."""

    def setUp(self):
        super().setUp()
        other = os.path.join(self.tmp, "projects", "-other")
        os.makedirs(other)
        self.write("sess-a.jsonl", record("msg_a", out=1000))
        with open(os.path.join(other, "sess-b.jsonl"), "w") as f:
            f.write(record("msg_b", out=5000) + "\n")
        tm.collect(tm.transcripts(), ledger=True)          # both now in the ledger

    def test_a_session_report_is_that_session_only(self):
        tm._SESSION[:] = ["sess-a"]
        try:
            overall, *_ = tm.collect(tm.transcripts(session="sess-a"), ledger=True)
        finally:
            tm._SESSION.clear()
        self.assertEqual(overall["calls"], 1)
        self.assertEqual(overall["tokens"]["output"], 1000)

    def test_a_session_survives_its_transcript_being_swept(self):
        os.remove(os.path.join(self.projects, "sess-a.jsonl"))
        tm._SESSION[:] = ["sess-a"]
        try:
            overall, *_ = tm.collect(tm.transcripts(session="sess-a"), ledger=True)
        finally:
            tm._SESSION.clear()
        self.assertEqual(overall["tokens"]["output"], 1000)

    def test_a_project_report_is_that_project_only(self):
        tm._PROJECT[:] = ["other"]
        try:
            overall, *_ = tm.collect(tm.transcripts(project="other"), ledger=True)
        finally:
            tm._PROJECT.clear()
        self.assertEqual(overall["tokens"]["output"], 5000)

    def test_an_adapter_report_is_that_adapter_only(self):
        tm._ONLY[:] = ["codex"]
        overall, *_ = tm.collect(tm.transcripts(), ledger=True)
        self.assertEqual(overall["calls"], 0)


class TestWorkflowAgents(Base):
    """Workflow agents write to <session>/subagents/workflows/<id>/, and only a
    file directly in a subagents folder was recognised as an agent's, so every
    workflow agent's calls were filed under a project named after its workflow
    and a session named after its own file, and written to the ledger so."""

    def setUp(self):
        super().setUp()
        self.write("sess-1.jsonl", record("msg_main", out=100))
        self.agent = os.path.join(self.projects, "sess-1", "subagents", "workflows",
                                  "wf_0001", "agent-a1.jsonl")
        os.makedirs(os.path.dirname(self.agent))
        with open(self.agent, "w") as f:
            f.write(record("msg_wf", out=200) + "\n")

    def test_a_workflow_agent_is_filed_under_its_session_and_project(self):
        ev = tm.scan_transcripts([self.agent])["msg_wf"]
        self.assertEqual((ev["project"], ev["session"], ev["sidechain"]),
                         ("-proj", "sess-1", True))
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=True)
        self.assertEqual(overall["calls"], 2)
        self.assertEqual(set(groups["project"]), {"-proj"})
        self.assertEqual(set(groups["session"]), {"sess-1"})
        self.assertEqual({(r["p"], r["c"]) for r in tm.read_ledger().values()},
                         {("-proj", "sess-1")})

    def test_its_session_and_project_find_it(self):
        for flags in (["--session", "sess-1"], ["--project", "proj"]):
            for ledger in ([], ["--no-ledger"]):
                with self.subTest(flags=flags, ledger=ledger):
                    got = json.loads(cli("--json", *flags, *ledger))
                    self.assertEqual(got["calls"], 2)
                    self.assertEqual(got["tokens"]["output"], 300)

    def test_a_subagent_one_folder_down_is_read_as_before(self):
        p = os.path.join(self.projects, "sess-1", "subagents", "agent-b2.jsonl")
        with open(p, "w") as f:
            f.write(record("msg_sub", out=50) + "\n")
        ev = tm.scan_transcripts([p])["msg_sub"]
        self.assertEqual((ev["project"], ev["session"], ev["sidechain"]),
                         ("-proj", "sess-1", True))
        ev = tm.scan_transcripts([os.path.join(self.projects, "sess-1.jsonl")])["msg_main"]
        self.assertEqual((ev["project"], ev["session"], ev["sidechain"]),
                         ("-proj", "sess-1", False))


class TestSessionPath(Base):
    """--session given a file filtered on the file's name, but Codex and
    Gemini CLI name a session by the id inside the file and a Claude Code
    agent's file by the session that started it, so each of them found
    nothing; and Gemini CLI's files were read as Claude Code's, whose test
    for its format matches their first line too."""

    def json_for(self, path, *flags):
        return json.loads(cli("--json", "--session", path, *flags))

    def test_a_subagent_path_finds_its_calls(self):
        main = self.write("sess-1.jsonl", record("msg_main", out=100))
        agent = os.path.join(self.projects, "sess-1", "subagents", "agent-a.jsonl")
        os.makedirs(os.path.dirname(agent))
        with open(agent, "w") as f:
            f.write(record("msg_a", out=200) + "\n")
        got = self.json_for(agent, "--no-ledger")
        self.assertEqual((got["calls"], got["tokens"]["output"]), (1, 200))
        self.assertEqual(got["label"], "session sess-1")
        # A session's own transcript brings its agents' with it.
        got = self.json_for(main, "--no-ledger")
        self.assertEqual((got["calls"], got["tokens"]["output"]), (2, 300))
        # With the ledger on, the session's other calls come back from it, as
        # they do for a session given by its id.
        cli("--json")
        self.assertEqual(self.json_for(agent)["calls"], 2)

    def test_a_gemini_cli_path_is_read_by_its_own_adapter(self):
        home = os.path.join(self.tmp, "gemini-home")
        shutil.copytree(os.path.join(FIXTURES, "gemini-cli", "home"), home)
        path = os.path.join(home, ".gemini", "tmp", "demo", "chats",
                            "session-2026-09-26T09-12-3f9c1a2b.jsonl")
        self.assertIs(tm.adapter_for(path), tm.ADAPTERS["gemini-cli"])
        got = self.json_for(path, "--no-ledger")
        self.assertEqual(got["calls"], 3)
        self.assertEqual(got["label"], "session 3f9c1a2b")

    def test_a_codex_path_is_filtered_on_the_id_inside_it(self):
        folder = os.path.join(self.tmp, "elsewhere")
        os.makedirs(folder)
        path = os.path.join(folder, "rollout-2026-09-24T14-07-33-"
                                    "0198f3c1-6d2a-7b41-9e05-3c8d5a27b110.jsonl")
        shutil.copy(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"), path)
        got = self.json_for(path, "--no-ledger")
        self.assertEqual(got["calls"], 3)
        self.assertEqual(got["label"], "session 0198f3c1")
        packed = zstd_compress(slurp(path, mode="rb"))
        if packed is not None:
            with open(path + ".zst", "wb") as f:
                f.write(packed)
            tm._OWNER.clear()
            self.assertIs(tm.adapter_for(path + ".zst"), tm.codex)
            self.assertEqual(self.json_for(path + ".zst", "--no-ledger")["calls"], 3)

    def test_a_file_holding_two_sessions_keeps_both_and_is_named(self):
        text = slurp(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"))
        other = text.replace("0198f3c1-6d2a-7b41-9e05-3c8d5a27b110",
                             "0198f3c1-0000-7000-8000-00000000000b")
        path = os.path.join(self.tmp, "two-sessions.jsonl")
        with open(path, "w") as f:
            f.write(text + other)
        paths, ids = tm.session_paths(path)
        self.assertEqual(ids, ["0198f3c1-0000-7000-8000-00000000000b",
                               "0198f3c1-6d2a-7b41-9e05-3c8d5a27b110"])
        got = self.json_for(path, "--no-ledger")
        self.assertEqual(got["calls"], 6)
        self.assertEqual(got["label"], "two-sessions.jsonl")


class TestProjectNames(Base):
    """--project matched its text against Claude Code's folder slug, in which
    every character that is not a letter or digit is "-", so a folder's real
    name with a space or punctuation, its full path and "." found nothing."""

    WHERE = "/Users/sam/code/My App"

    def setUp(self):
        super().setUp()
        for slug, mid in (("-Users-sam-code-My-App", "msg_mine"),
                          ("-Users-sam-code-Other", "msg_other")):
            folder = os.path.join(self.tmp, "projects", slug)
            os.makedirs(folder)
            with open(os.path.join(folder, "sess-" + mid + ".jsonl"), "w") as f:
                f.write(record(mid, out=100) + "\n")

    def calls(self, *argv):
        return json.loads(cli("--json", *argv))["calls"]

    def test_a_name_a_path_and_dot_each_find_it(self):
        self.assertEqual(tm.claude_code.slug(self.WHERE), "-Users-sam-code-My-App")
        cli("--json")                              # both now in the ledger too
        for wanted in ("My App", "my app", self.WHERE, "code-My-App", "-Users-sam-code-My-App", "."):
            for ledger in ([], ["--no-ledger"]):
                with self.subTest(project=wanted, ledger=ledger), \
                        unittest.mock.patch("os.getcwd", return_value=self.WHERE):
                    self.assertEqual(self.calls("--project=" + wanted, *ledger), 1)
        with self.assertRaises(SystemExit):
            self.calls("--project", "No Such App")

    def test_the_current_folder_is_named_in_the_label(self):
        with unittest.mock.patch("os.getcwd", return_value=self.WHERE), \
                unittest.mock.patch.dict(os.environ, {"HOME": "/Users/sam"}):
            label = json.loads(cli("--json", "--project", ".", "--no-ledger"))["label"]
        self.assertEqual(label, "all time \u00b7 code/My App")

    def test_an_imports_real_path_still_matches(self):
        trial = os.path.join(self.tmp, "trial.jsonl")
        with open(trial, "w") as f:
            f.write(json.dumps(dict(TestImport.GOOD, project=self.WHERE)) + "\n")
        for wanted in ("My App", self.WHERE, "-Users-sam-code-My-App"):
            with self.subTest(project=wanted):
                self.assertEqual(self.calls("--project=" + wanted, "--adapter", "import",
                                            "--import", trial, "--no-ledger"), 1)

    def test_a_codex_session_is_found_by_its_folders_slug(self):
        day = os.path.join(self.tmp, "codex-home", "sessions", "2026", "09", "24")
        os.makedirs(day)
        shutil.copy(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"),
                    os.path.join(day, "rollout-2026-09-24T14-07-33-"
                                      "0198f3c1-6d2a-7b41-9e05-3c8d5a27b110.jsonl"))
        tm.ADAPTER_ROOTS["codex"] = [os.path.join(self.tmp, "codex-home", "sessions")]
        # The fixture's working folder is /Users/example/code/demo.
        for wanted in ("code/demo", "code-demo"):
            with self.subTest(project=wanted):
                self.assertEqual(self.calls("--project", wanted, "--adapter", "codex",
                                            "--no-ledger"), 3)


class TestTheRestoredCount(Base):
    """A --project alpha run said "ledger holds 5, 3 of them no longer in any
    transcript", and all three were in the other project's transcript, on
    disk: a filtered run never reads the other logs, so it cannot know."""

    def setUp(self):
        super().setUp()
        for project, session, mids in (("-alpha", "sess-a", ("a1", "a2")),
                                       ("-beta", "sess-b", ("b1", "b2", "b3"))):
            folder = os.path.join(self.tmp, "projects", project)
            os.makedirs(folder)
            with open(os.path.join(folder, session + ".jsonl"), "w") as f:
                f.write("".join(record(m, out=100) + "\n" for m in mids))
        cli("--json")                                      # every call now in the ledger

    def covered(self, *argv):
        lines = [line for line in cli(*argv).splitlines() if "ledger holds" in line]
        self.assertEqual(len(lines), 1, lines)
        return lines[0]

    def test_a_filtered_run_does_not_call_unread_logs_gone(self):
        trial = os.path.join(self.tmp, "trial.jsonl")
        with open(trial, "w") as f:
            f.write(json.dumps(TestImport.GOOD) + "\n")
        for flags in (["--project", "alpha"], ["--session", "sess-a"],
                      ["--adapter", "import", "--import", trial]):
            with self.subTest(flags=flags):
                line = self.covered(*flags)
                self.assertIn("ledger holds", line)
                self.assertNotIn("no longer in any transcript", line)

    def test_a_run_that_reads_every_log_still_counts_them(self):
        os.remove(os.path.join(self.tmp, "projects", "-beta", "sess-b.jsonl"))
        self.assertIn("ledger holds 5, 3 of them no longer in any transcript", self.covered())
        # A time window still reads every log, so its count stands.
        self.assertIn("ledger holds 5, 3 of them no longer in any transcript",
                      self.covered("--since", "2026-08-01"))


class TestRebuildLedger(Base):
    """--rebuild-ledger --project alpha rebuilt a five-call ledger from the two
    calls that project could see, and the same command again overwrote .old,
    the only copy left of the other three."""

    def setUp(self):
        super().setUp()
        other = os.path.join(self.tmp, "projects", "-other")
        os.makedirs(other)
        self.write("sess-a.jsonl", record("msg_a", out=1000))
        with open(os.path.join(other, "sess-b.jsonl"), "w") as f:
            f.write(record("msg_b", out=5000) + "\n")
        tm.collect(tm.transcripts(), ledger=True)          # both now in the ledger

    def leftovers(self):
        """Every file a rebuild leaves beside the ledger, the ledger aside."""
        return sorted(f for f in os.listdir(self.tmp) if f.startswith("ledger.jsonl."))

    def test_a_filtered_rebuild_is_refused_and_touches_nothing(self):
        """A rebuild from a filtered run replaced the whole ledger with the
        part of it that run could see."""
        before = slurp(self.ledger, mode="rb")
        for flags in (["--project", "proj"], ["--session", "sess-a"],
                      ["--adapter", "claude-code"], ["--since", "7d"],
                      ["--until", "2026-10-01"], ["--period", "today"], ["--no-ledger"]):
            with self.subTest(flags=flags):
                with self.assertRaises(SystemExit) as e:
                    cli("--rebuild-ledger", *flags)
                self.assertIn(f"run it without {flags[0]}", str(e.exception.code))
                self.assertEqual(slurp(self.ledger, mode="rb"), before)
                self.assertEqual(self.leftovers(), [])

    def test_every_backup_is_kept(self):
        """A second rebuild overwrote the first one's .old."""
        first = slurp(self.ledger)
        cli("--rebuild-ledger")
        self.assertEqual(self.leftovers(), ["ledger.jsonl.old"])
        self.assertEqual(slurp(self.ledger + ".old"), first)
        self.write("sess-c.jsonl", record("msg_c", out=200))
        tm.collect(tm.transcripts(), ledger=True)
        second = slurp(self.ledger)
        self.assertNotEqual(second, first)
        cli("--rebuild-ledger")
        cli("--rebuild-ledger")                            # often within the same second
        names = self.leftovers()
        self.assertEqual(len(names), 3, names)
        self.assertEqual(names[0], "ledger.jsonl.old")
        self.assertEqual(slurp(self.ledger + ".old"), first)
        self.assertEqual(slurp(os.path.join(self.tmp, names[1])), second)
        for name in names[1:]:
            self.assertRegex(name, r"^ledger\.jsonl\.old-\d{8}-\d{6}(-\d+)?$")
        self.assertEqual(len(tm.read_ledger(self.ledger)), 3)

    def test_the_message_counts_and_names_what_was_lost(self):
        """It said "1 calls from 1 transcripts", printed the backup's full path
        with the username in it, and never said that lost imported calls come
        back by passing the same --import files again."""
        from unittest import mock
        trial = os.path.join(self.tmp, "trial.jsonl")
        with open(trial, "w") as f:
            f.write(json.dumps(TestImport.GOOD) + "\n")
        cli("--import", trial)                             # now in the ledger too
        os.remove(os.path.join(self.projects, "sess-a.jsonl"))
        with mock.patch.dict(os.environ, {"HOME": self.tmp}):
            out = cli("--rebuild-ledger")
        self.assertIn("ledger rebuilt: 1 call from 1 transcript\n", out)
        self.assertIn("previous ledger held 3 calls, kept at ~/ledger.jsonl.old\n", out)
        self.assertIn("2 calls were in the old ledger and in no transcript.", out)
        self.assertIn("Restore from ~/ledger.jsonl.old to get them back.", out)
        self.assertIn("1 of them was imported: rebuild with the same --import files", out)


class TestSummaryJson(Base):
    """--summary-json was answered before any option was applied, from a
    summary() that always used the ledger: a trial import with --no-ledger was
    written to the ledger for good, and --since 1h --project zzz returned the
    whole history without saying so."""

    def trial(self):
        p = os.path.join(self.tmp, "trial.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps(TestImport.GOOD) + "\n")
        return p

    def test_no_ledger_leaves_an_absent_ledger_absent(self):
        self.write("a.jsonl", record("msg_1", out=10))
        got = json.loads(cli("--import", self.trial(), "--no-ledger", "--summary-json"))
        self.assertEqual(got["all"]["calls"], 2)
        self.assertFalse(os.path.exists(self.ledger))

    def test_no_ledger_leaves_the_ledger_as_it_was(self):
        """The trial import was still counted by every later run."""
        self.write("a.jsonl", record("msg_1", out=10))
        tm.collect(tm.transcripts(), ledger=True)
        before = slurp(self.ledger, mode="rb")
        cli("--import", self.trial(), "--no-ledger", "--summary-json")
        self.assertEqual(slurp(self.ledger, mode="rb"), before)
        self.assertEqual(json.loads(cli("--summary-json"))["all"]["calls"], 1)

    def test_a_window_or_a_filter_is_refused(self):
        for flags in (["--since", "1h"], ["--until", "2026-10-01"], ["--period", "today"],
                      ["--project", "zzz"], ["--session", "abc"]):
            with self.subTest(flags=flags):
                with self.assertRaises(SystemExit) as e:
                    cli("--summary-json", *flags)
                message = str(e.exception.code)
                self.assertIn("always covers today, the last 7 and 30 days and all time", message)
                self.assertIn(f"run it without {flags[0]}", message)
        self.assertFalse(os.path.exists(self.ledger))

    def test_adapter_and_import_are_honoured(self):
        self.write("a.jsonl", record("msg_1", out=10))
        got = json.loads(cli("--adapter", "import", "--import", self.trial(),
                             "--no-ledger", "--summary-json"))
        self.assertEqual(got["all"]["calls"], 1)
        self.assertEqual([s["name"] for s in got["sources"]], ["import"])

    def test_a_mistyped_currency_cannot_blank_the_menu_bar(self):
        """The menu bar passes no --currency, so TOKENMETER_CURRENCY=GPB made
        every refresh exit with an error and the menu read "no readable output"."""
        import contextlib, io
        from unittest import mock
        self.write("a.jsonl", record("msg_1", out=10))
        buf = io.StringIO()
        with mock.patch.object(tm, "DEFAULT_CURRENCY", "GPB"), contextlib.redirect_stdout(buf):
            tm.main(["--summary-json"])
        self.assertEqual(json.loads(buf.getvalue())["all"]["calls"], 1)


class TestDashboard(Base):
    """The dashboard has to be one self-contained file that works offline."""

    def render(self):
        self.write("a.jsonl", record("msg_1", out=900, read=50000, w1=2000))
        out = os.path.join(self.tmp, "d.html")
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        tm.render_html(overall, groups, meta, unknown, "all time", out, covered="a window")
        return slurp(out, encoding="utf-8")

    def test_fetches_nothing_when_opened(self):
        """A file on disk must not depend on a network that may not be there."""
        page = self.render()
        self.assertNotIn("fonts.googleapis", page)
        self.assertNotIn("cdn.", page)
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link rel=\"stylesheet\"", page)

    def test_fonts_are_embedded(self):
        page = self.render()
        self.assertIn("@font-face", page)
        self.assertIn("data:font/woff2;base64,", page)

    def test_survives_missing_font_files(self):
        """Deleting the fonts must degrade to system stacks, not crash."""
        real = tm.FONT_DIR
        tm.FONT_DIR = os.path.join(self.tmp, "no-fonts-here")
        try:
            page = self.render()
            self.assertNotIn("@font-face", page)
            self.assertIn("Georgia", page)   # the fallback stack is still there
        finally:
            tm.FONT_DIR = real

    def test_sections_are_numbered_in_page_order(self):
        """Tables were built before the page, so the first section read 03."""
        page = self.render()
        numbers = re.findall(r'<span class="no">(\d\d)</span>', page)
        self.assertEqual(numbers, [f"{i:02d}" for i in range(1, len(numbers) + 1)])
        self.assertNotIn("\u00a7NO\u00a7", page)

    def test_a_session_with_no_time_is_a_question_mark(self):
        """The empty "Last seen" cell was an em dash, the only dash character
        the engine printed; the terminal's sessions list has always said "?"."""
        self.write("a.jsonl", record("msg_1", out=900))
        out = os.path.join(self.tmp, "d.html")
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        for info in meta.values():
            info["last"] = None
        tm.render_html(overall, groups, meta, unknown, "all time", out)
        page = slurp(out, encoding="utf-8")
        self.assertIn('<td class="dim">?</td>', page)
        self.assertNotIn(chr(0x2014), page)                 # the em dash

    def test_renders_with_no_history_at_all(self):
        """A fresh install opens the dashboard before it has priced anything."""
        out = os.path.join(self.tmp, "empty.html")
        overall, groups, meta, unknown = tm.collect([], ledger=False)
        tm.render_html(overall, groups, meta, unknown, "all time", out)
        self.assertIn("</html>", slurp(out, encoding="utf-8"))


class TestPeriods(Base):
    def test_last_month_is_the_whole_previous_month(self):
        since, until = tm.period_range("lastmonth")
        self.assertEqual(since.day, 1)
        self.assertEqual(until.day, 1)
        self.assertLess(since, until)
        # the gap must be a real month length, not a fixed 30
        self.assertIn((until.date() - since.date()).days, (28, 29, 30, 31))

    def test_this_month_starts_on_the_first(self):
        since, until = tm.period_range("month")
        self.assertEqual(since.day, 1)
        self.assertIsNone(until)

    def test_weeks_start_monday(self):
        since, until = tm.period_range("lastweek")
        self.assertEqual(since.weekday(), 0)
        self.assertEqual((until.date() - since.date()).days, 7)

    def test_unknown_period_exits(self):
        with self.assertRaises(SystemExit):
            tm.period_range("fortnight")

    def test_until_bounds_the_far_end(self):
        self.write("a.jsonl", record("msg_1", ts="2026-08-01T12:00:00.000Z", out=100))
        self.write("b.jsonl", record("msg_2", ts="2026-09-05T12:00:00.000Z", out=100))
        cutoff = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
        evs = list(tm.iter_events(tm.transcripts(), ledger=False, until=cutoff))
        self.assertEqual(len(evs), 1)


class TestLocalMidnight(Base):
    @unittest.skipUnless(hasattr(time, "tzset"), "needs time.tzset to change the zone")
    def test_the_days_the_clocks_change_start_at_their_own_offset(self):
        """The status line took midnight as now().replace(hour=0), which keeps
        the offset in force now: in London its "today" started an hour late
        on 25 October 2026 and an hour early on 29 March."""
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/London"
        time.tzset()
        try:
            utc = dt.timezone.utc
            autumn = tm.local_midnight(dt.date(2026, 10, 25))
            self.assertEqual(autumn, dt.datetime(2026, 10, 24, 23, 0, tzinfo=utc))
            self.assertEqual(autumn.utcoffset(), dt.timedelta(hours=1))
            spring = tm.local_midnight(dt.date(2026, 3, 29))
            self.assertEqual(spring, dt.datetime(2026, 3, 29, 0, 0, tzinfo=utc))
            self.assertEqual(spring.utcoffset(), dt.timedelta(0))
            # The old rule, at ten in the morning, after the clocks went back.
            late = dt.datetime(2026, 10, 25, 10, 0).astimezone().replace(hour=0, minute=0)
            self.assertNotEqual(late, autumn)
            self.assertEqual(tm.period_range("today")[0], tm.local_midnight(dt.date.today()))
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()


class TestParseSince(Base):
    def test_relative_forms(self):
        for s in ("24h", "7d", "2w"):
            self.assertIsNotNone(tm.parse_since(s))

    def test_absolute_date(self):
        self.assertEqual(tm.parse_since("2026-09-01").date(), dt.date(2026, 9, 1))

    def test_nonsense_exits(self):
        with self.assertRaises(SystemExit):
            tm.parse_since("soonish")

    def test_a_timestamp_keeps_its_offset_and_its_z(self):
        """The text was lowercased before parsing, so '2026-10-01T10:00Z' was
        refused, and any offset was then replaced by UTC."""
        utc = dt.timezone.utc
        for flag in ("--since", "--until"):
            with self.subTest(flag=flag):
                self.assertEqual(tm.parse_since("2026-10-01T10:00Z", flag),
                                 dt.datetime(2026, 10, 1, 10, 0, tzinfo=utc))
                self.assertEqual(tm.parse_since("2026-10-01T11:00+02:00", flag),
                                 dt.datetime(2026, 10, 1, 9, 0, tzinfo=utc))
        self.assertEqual(tm.parse_since("2026-10-01 10:00:00+0100"),
                         dt.datetime(2026, 10, 1, 9, 0, tzinfo=utc))
        for s in ("7D", "24H", "2W"):
            self.assertIsNotNone(tm.parse_since(s))

    @unittest.skipUnless(hasattr(time, "tzset"), "needs time.tzset to change the zone")
    def test_a_date_is_local_midnight_and_a_bare_time_is_local(self):
        """A date was taken as midnight UTC, away from the local day
        boundaries --period and the day buckets use: in London in summer,
        --since 2026-10-01 began an hour into the day."""
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/London"
        time.tzset()
        try:
            utc = dt.timezone.utc
            day = tm.parse_since("2026-10-01")
            self.assertEqual(day, tm.local_midnight(dt.date(2026, 10, 1)))
            self.assertEqual(day, dt.datetime(2026, 9, 30, 23, 0, tzinfo=utc))
            self.assertEqual(tm.parse_since("2026-10-01T10:00", "--until"),
                             dt.datetime(2026, 10, 1, 9, 0, tzinfo=utc))
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()

    def test_a_value_too_large_exits_naming_its_flag(self):
        """'--since 99999999d' ended in an OverflowError traceback."""
        for s in ("99999999d", "-99999999d", "1e400w", "nanh", "2026-13-01"):
            for flag in ("--since", "--until"):
                with self.subTest(value=s, flag=flag):
                    with self.assertRaises(SystemExit) as cm:
                        tm.parse_since(s, flag)
                    self.assertIn(f"could not read {flag} {s!r}", str(cm.exception.code))
        self.write("a.jsonl", record("msg_1", out=100))
        with self.assertRaises(SystemExit) as cm:
            cli("--until", "99999999d", "--no-ledger")
        self.assertIn("could not read --until '99999999d'", str(cm.exception.code))

    def test_until_alone_is_labelled_until(self):
        """A run with --until and no --since was labelled 'all time'."""
        self.write("a.jsonl", record("msg_1", ts="2026-09-01T12:00:00.000Z", out=100),
                   record("msg_2", ts="2026-09-05T12:00:00.000Z", out=100))
        got = json.loads(cli("--json", "--until", "2026-09-03", "--no-ledger"))
        self.assertEqual((got["label"], got["calls"]), ("until 2026-09-03", 1))
        got = json.loads(cli("--json", "--since", "2026-09-01T00:00Z",
                             "--until", "2026-09-03T00:00Z", "--no-ledger"))
        self.assertEqual((got["label"], got["calls"]),
                         ("2026-09-01T00:00Z to 2026-09-03T00:00Z", 1))



FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def cost_of(c):
    return sum(c[k] for k in tm.COMPONENTS)


def zstd_compress(data):
    """data compressed with whichever zstd encoder this machine has: Python's
    own (3.14 and later), the zstandard package or the zstd command. None when
    it has none, and the test that needs one is skipped."""
    try:
        from compression import zstd
        return zstd.compress(data)
    except ImportError:
        pass
    try:
        import zstandard
        return zstandard.ZstdCompressor().compress(data)
    except ImportError:
        pass
    tool = tm.codex._zstd_tool()
    if tool:
        import subprocess
        return subprocess.run([tool, "-q", "-c"], input=data, capture_output=True,
                              check=True).stdout
    return None


class TestOtherProvidersPublishedRates(Base):
    """Every rate in the OpenAI, Google and xAI tables, typed from the pages.

    Read on 26 September 2026 from developers.openai.com/api/docs/pricing and
    its model pages, ai.google.dev/gemini-api/docs/pricing and
    docs.x.ai/developers/pricing. gpt-6.1-sol added from the OpenAI pages on
    6 October 2026. Typed here separately from the tables, so a
    slip in either one fails. A model with no cached rate is listed with its
    input rate: no discount.
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
        before = dt.datetime(2026, 12, 31, 12, tzinfo=dt.timezone.utc)
        after = dt.datetime(2027, 1, 2, 12, tzinfo=dt.timezone.utc)
        for model in ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"):
            with self.subTest(model=model):
                self.assertEqual(tm.lookup(model, before, "google")[0]["in"], 0.75)
                self.assertEqual(tm.lookup(model, after, "google")[0]["in"], 1.50)
                self.assertEqual(tm.lookup(model, after, "google")[0]["out"], 7.50)

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


class TestLedgerProviders(Base):
    def test_rows_written_before_providers_existed_still_price_as_anthropic(self):
        """An old ledger has no pv or a field. Every row in it is Claude Code."""
        old = {"i": "msg_old", "t": "2026-08-01T12:00:00Z", "m": "claude-opus-5",
               "p": "-proj", "c": "sess", "in": 10, "o": 1000, "r": 50000}
        with open(self.ledger, "w") as f:
            f.write(json.dumps(old) + "\n")
        evs = list(tm.iter_events([], ledger=True))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["provider"], "anthropic")
        self.assertEqual(evs[0]["source"], "claude-code")
        want = tm.price_record("claude-opus-5", usage(inp=10, out=1000, read=50000))
        self.assertAlmostEqual(cost_of(evs[0]["cost"]), cost_of(want), places=12)

    def test_claude_code_rows_keep_their_old_shape(self):
        """No new keys on a Claude Code row, so an existing ledger's diffs stay the same."""
        row = tm.usage_to_row("m", None, "claude-opus-5", "p", "s", usage(inp=5))
        self.assertNotIn("pv", row)
        self.assertNotIn("a", row)

    def test_other_providers_round_trip_through_the_ledger(self):
        row = tm.usage_to_row("codex:x:1", None, "gpt-6-sol", "p", "s", usage(inp=5, out=7),
                              provider="openai", source="codex")
        self.assertEqual((row["pv"], row["a"]), ("openai", "codex"))
        tm.append_ledger([row])
        evs = list(tm.iter_events([], ledger=True))
        self.assertEqual((evs[0]["provider"], evs[0]["source"], evs[0]["model"]),
                         ("openai", "codex", "gpt-6-sol"))


class TestImport(Base):
    def events(self, *objs, name="events.jsonl"):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as f:
            for o in objs:
                f.write((o if isinstance(o, str) else json.dumps(o)) + "\n")
        return p

    GOOD = {"id": "e1", "timestamp": "2026-09-20T10:00:00Z", "provider": "openai",
            "model": "gpt-6-sol", "input": 1000, "cache_read": 9000, "output": 500}

    def run_import(self, path, ledger=False):
        tm._IMPORTS[:] = [path]
        tm._ONLY[:] = ["import"]
        return tm.collect(tm.transcripts(), ledger=ledger)

    def test_prices_at_the_named_providers_rates(self):
        overall, groups, _, unknown = self.run_import(self.events(self.GOOD))
        want = (1000 * 2.0 + 9000 * 0.2 + 500 * 10.0) / 1e6
        self.assertAlmostEqual(overall["total"], want, places=12)
        self.assertEqual(set(groups["source"]), {"import"})
        self.assertFalse(unknown)

    def test_importing_twice_counts_once(self):
        p = self.events(self.GOOD)
        self.run_import(p, ledger=True)
        overall, *_ = self.run_import(p, ledger=True)
        self.assertEqual(overall["calls"], 1)

    def test_imports_are_kept_by_the_ledger(self):
        p = self.events(self.GOOD)
        self.run_import(p, ledger=True)
        tm._IMPORTS.clear()
        tm._ONLY.clear()
        overall, groups, _, _ = tm.collect(tm.transcripts(), ledger=True)
        self.assertEqual(overall["calls"], 1)
        self.assertIn("import", groups["source"])

    def test_bad_lines_are_skipped_and_explained(self):
        p = self.events(self.GOOD, "not json",
                        {"id": "e2", "timestamp": "2026-09-20T10:00:00Z", "model": "gpt-5", "input": 5},
                        {"id": "e3", "timestamp": "2026-09-20T10:00:00Z", "provider": "openai",
                         "model": "gpt-5", "input": -5},
                        {"id": "e4", "timestamp": "yesterday", "provider": "openai", "model": "gpt-5",
                         "input": 5})
        overall, groups, _, unknown = self.run_import(p)
        self.assertEqual(overall["calls"], 1)
        problems = tm.importer.PROBLEMS[p]
        self.assertEqual(problems["skipped"], 4)
        text = " ".join(problems["examples"])
        self.assertIn("not valid JSON", text)
        self.assertIn("missing provider", text)
        self.assertIn("whole number", text)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("4 lines skipped", notes)

    def test_an_infinite_count_skips_its_line(self):
        """json.loads reads 1e999 and Infinity as an infinite float, on which
        int() raises OverflowError, which parse() did not catch, so one such
        line ended the whole run in a traceback."""
        head = '{"id": "e%d", "timestamp": "2026-09-20T10:00:00Z", "provider": "openai", ' \
               '"model": "gpt-5", '
        p = self.events(self.GOOD, head % 2 + '"input": 1e999}', head % 3 + '"output": Infinity}',
                        head % 4 + '"cache_read": NaN}')
        overall, *_ = self.run_import(p)
        self.assertEqual(overall["calls"], 1)
        self.assertEqual(tm.importer.PROBLEMS[p], {"skipped": 3, "examples": [
            "line 2: input must be a whole number of tokens, not inf",
            "line 3: output must be a whole number of tokens, not inf",
            "line 4: cache_read must be a whole number of tokens, not nan"]})
        # An integer too large for a float overflowed when it was priced.
        with self.assertRaisesRegex(ValueError, "whole number"):
            tm.importer.parse(dict(self.GOOD, input=10 ** 400))

    def test_a_line_that_is_not_utf8_skips_that_line(self):
        """The file was decoded as strict UTF-8 outside the per-line check, so
        one Latin-1 byte (0xE9, an accented e) anywhere in a file or in
        standard input ended the whole run with UnicodeDecodeError."""
        import io
        bad = json.dumps(dict(self.GOOD, id="e2", project="café")).encode()
        data = b"\r\n".join([json.dumps(self.GOOD).encode(), bad.replace(b"\\u00e9", b"\xe9"),
                             json.dumps(dict(self.GOOD, id="e3")).encode()]) + b"\r\n"
        p = os.path.join(self.tmp, "latin1.jsonl")
        with open(p, "wb") as f:
            f.write(data)
        overall, *_ = self.run_import(p)
        self.assertEqual(overall["calls"], 2)
        self.assertEqual(tm.importer.PROBLEMS[p], {"skipped": 1, "examples": ["line 2: not valid UTF-8"]})
        stdin = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        try:
            overall, *_ = self.run_import("-")
        finally:
            sys.stdin = stdin
        self.assertEqual(overall["calls"], 2)
        self.assertEqual(tm.importer.PROBLEMS["-"]["examples"], ["line 2: not valid UTF-8"])

    def test_a_timestamp_reads_the_same_on_every_python(self):
        """Python 3.9's fromisoformat refuses a short offset, the basic format
        and a comma before the fraction, which 3.11 and later read, so the same
        import line was counted under Homebrew's python3 and skipped as an
        unreadable timestamp under /usr/bin/python3, the menu bar's."""
        utc = dt.timezone.utc
        plus1, minus530 = dt.timezone(dt.timedelta(hours=1)), dt.timezone(-dt.timedelta(hours=5.5))
        cases = {
            "2026-09-20T10:02:11+0100": dt.datetime(2026, 9, 20, 10, 2, 11, tzinfo=plus1),
            "20260920T100211Z": dt.datetime(2026, 9, 20, 10, 2, 11, tzinfo=utc),
            "2026-09-20T10:02:11,5Z": dt.datetime(2026, 9, 20, 10, 2, 11, 500000, tzinfo=utc),
            "2026-09-20 10:02:11+01": dt.datetime(2026, 9, 20, 10, 2, 11, tzinfo=plus1),
            "20260920T100211,25-0530": dt.datetime(2026, 9, 20, 10, 2, 11, 250000, tzinfo=minus530),
            "2026-09-20T1002Z": dt.datetime(2026, 9, 20, 10, 2, tzinfo=utc),
        }
        for text, want in cases.items():
            with self.subTest(text):
                got = tm.parse_time(text)
                self.assertEqual(got, want)
                self.assertEqual(got.utcoffset(), want.utcoffset())
        p = self.events(dict(self.GOOD, timestamp="20260920T100211Z"),
                        dict(self.GOOD, id="e2", timestamp="2026-09-20T10:02:11+0100"))
        overall, *_ = self.run_import(p)
        self.assertEqual(overall["calls"], 2)
        self.assertNotIn(p, tm.importer.PROBLEMS)

    def test_the_forms_read_before_still_read_the_same(self):
        utc = dt.timezone.utc
        cases = {
            "2026-09-20T10:02:11Z": dt.datetime(2026, 9, 20, 10, 2, 11, tzinfo=utc),
            "2026-09-20T10:02:11.123Z": dt.datetime(2026, 9, 20, 10, 2, 11, 123000, tzinfo=utc),
            "2026-09-20T10:02:11.1234567z": dt.datetime(2026, 9, 20, 10, 2, 11, 123456, tzinfo=utc),
            "2026-09-20T10:02:11.5-05:30": dt.datetime(2026, 9, 20, 10, 2, 11, 500000,
                                                       tzinfo=dt.timezone(-dt.timedelta(hours=5.5))),
            " 2026-09-20T10:02:11 ": dt.datetime(2026, 9, 20, 10, 2, 11, tzinfo=utc),
            "2026-09-20": dt.datetime(2026, 9, 20, tzinfo=utc),
        }
        for text, want in cases.items():
            with self.subTest(text):
                got = tm.parse_time(text)
                self.assertEqual(got, want)
                self.assertEqual(got.utcoffset(), want.utcoffset())
        for text in (None, "", "yesterday", 1726826531, "2026-13-01T00:00:00Z", "20260920T25"):
            with self.subTest(text):
                self.assertIsNone(tm.parse_time(text))

    def test_a_time_with_no_offset_is_utc(self):
        ev = dict(self.GOOD, timestamp="2026-09-20T10:00:00")
        key, parsed = tm.importer.parse(ev)
        self.assertEqual(parsed["when"].utcoffset(), dt.timedelta(0))

    def test_openai_style_cache_write_field_is_accepted(self):
        ev = dict(self.GOOD, cache_write=100_000, input=0, cache_read=0, output=0)
        _, parsed = tm.importer.parse(ev)
        c = tm.price_record("gpt-6-sol", parsed["_usage"], provider="openai")
        self.assertAlmostEqual(c["cache_write"], 0.25, places=9)


class TestCodexAdapter(Base):
    """Built from the published source and labelled unverified. These tests
    prove it reads the format the source writes, not that real files match."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "codex-home")
        tm.ADAPTER_ROOTS["codex"] = [os.path.join(self.home, "sessions"),
                                     os.path.join(self.home, "archived_sessions")]
        self.expected = json.loads(slurp(os.path.join(FIXTURES, "codex", "expected.json")))

    def place(self, fixture, day="2026/09/24", uuid="0198f3c1-6d2a-7b41-9e05-3c8d5a27b110",
              where="sessions"):
        d = os.path.join(self.home, where, *day.split("/"))
        os.makedirs(d, exist_ok=True)
        stamp = day.replace("/", "-") + "T14-07-33"
        dest = os.path.join(d, f"rollout-{stamp}-{uuid}.jsonl")
        shutil.copy(os.path.join(FIXTURES, "codex", fixture), dest)
        return dest

    def test_every_generation_reads_as_the_source_says(self):
        for fx in self.expected["fixtures"]:
            if fx["file"].startswith("exec"):
                continue
            with self.subTest(fixture=fx["file"]):
                tm.codex.reset()
                got = [ev for _, ev in tm.codex.records(os.path.join(FIXTURES, "codex", fx["file"]))]
                self.assertEqual(len(got), len(fx["expected_turns"]))
                for ev, want in zip(got, fx["expected_turns"]):
                    u = ev["_usage"]
                    self.assertEqual(u["input_tokens"], want["uncached_input_tokens"])
                    self.assertEqual(u["cache_read_input_tokens"], want["cached_input_tokens"])
                    self.assertEqual(u["cache_creation"]["ephemeral_5m_input_tokens"],
                                     want["cache_write_input_tokens"] or 0)
                    self.assertEqual(u["output_tokens"], want["output_tokens"])
                    self.assertEqual(u["output_tokens_details"]["thinking_tokens"],
                                     want["reasoning_output_tokens"])
                    self.assertEqual(ev["model"], want["model"])
                    self.assertEqual(ev["provider"], "openai")

    def test_repeated_and_empty_token_counts_are_not_counted(self):
        """token_count is re-sent on every rate-limit refresh, sometimes with info: null."""
        tm.codex.reset()
        got = list(tm.codex.records(os.path.join(FIXTURES, "codex", "gen3_turn_context.jsonl")))
        self.assertEqual(len(got), 3)
        self.assertEqual(len({k for k, _ in got}), 3)

    def test_fast_tier_is_carried_forward_from_settings(self):
        tm.codex.reset()
        got = [ev for _, ev in tm.codex.records(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"))]
        self.assertEqual([ev["_usage"]["speed"] for ev in got], ["standard", "standard", "fast"])

    def test_web_searches_are_attached_to_the_next_response(self):
        tm.codex.reset()
        got = [ev for _, ev in tm.codex.records(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"))]
        self.assertEqual([ev["_usage"]["server_tool_use"]["web_search_requests"] for ev in got], [0, 1, 0])

    def test_sessions_with_no_model_say_what_they_were_priced_as(self):
        self.place("gen2_envelope_no_turn_context.jsonl")
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("priced as gpt-5", notes)

    def test_an_archived_copy_is_not_counted_twice_in_the_gpt_5_note(self):
        """The note counted every record read, before de-duplication, so a
        pre-0.36 session in both sessions/ and archived_sessions/ said 6
        calls were priced as gpt-5 in a report of 3."""
        self.place("gen2_envelope_no_turn_context.jsonl")
        self.place("gen2_envelope_no_turn_context.jsonl", where="archived_sessions")
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("3 Codex calls came from sessions older than Codex 0.36", notes)

    def test_found_automatically_and_labelled_unverified(self):
        self.place("gen4_current_paginated.jsonl")
        self.assertIn("codex", tm.active_adapters())
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)
        warns = [t for level, t in tm.report_notes(groups, unknown) if level == "warn"]
        self.assertTrue(any("Codex figures are unverified" in t for t in warns))

    def test_the_same_session_archived_counts_once(self):
        self.place("gen4_current_paginated.jsonl")
        self.place("gen4_current_paginated.jsonl", where="archived_sessions")
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)

    def test_a_compressed_session_it_cannot_read_is_reported(self):
        p = self.place("gen4_current_paginated.jsonl")
        os.rename(p, p + ".zst")
        real = tm.codex._decompress
        tm.codex._decompress = lambda path: None
        try:
            overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        finally:
            tm.codex._decompress = real
        self.assertEqual(overall["calls"], 0)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("could not be read", notes)

    def place_compressed(self, data, uuid):
        """Bytes placed as Codex leaves a week-old session, compressed."""
        p = self.place("gen3_turn_context.jsonl", uuid=uuid) + ".zst"
        os.remove(p[:-len(".zst")])
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_a_damaged_compressed_session_is_reported_not_fatal(self):
        """A .jsonl.zst cut short (Codex compressing it while a run reads it)
        or corrupt raised EOFError or ZstdError on Python 3.14 and ended every
        run in a traceback; on 3.9 it was blamed on zstd not being installed."""
        whole = zstd_compress(slurp(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"),
                                    mode="rb"))
        if whole is None:
            self.skipTest("no zstd encoder on this machine")
        self.place_compressed(whole, "0198f3c1-0000-7000-8000-000000000001")
        self.place_compressed(whole[:len(whole) // 2], "0198f3c1-0000-7000-8000-000000000002")
        self.place_compressed(b"not zstd at all\n", "0198f3c1-0000-7000-8000-000000000003")
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)   # the whole file is still read
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("2 compressed Codex sessions (.jsonl.zst) could not be read; the files may "
                      "be damaged or still being compressed", notes)
        self.assertNotIn("Install zstd", notes)

    def no_decoder_but(self, *zstd_paths):
        """A machine like the menu bar's: /usr/bin/python3, so no compression.zstd
        and no zstandard, and launchd's PATH, so no zstd on it. zstd_paths
        stand in for where Homebrew puts the command."""
        from unittest import mock
        import contextlib
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.dict(sys.modules, {"compression": None,
                                                          "compression.zstd": None,
                                                          "zstandard": None}))
        stack.enter_context(mock.patch("shutil.which", return_value=None))
        stack.enter_context(mock.patch.object(tm.codex, "ZSTD_PATHS", zstd_paths))
        return stack

    def fake_zstd(self, where, executable=True):
        """A stand-in for `zstd -dc FILE` that prints FILE as it is."""
        os.makedirs(where, exist_ok=True)
        p = os.path.join(where, "zstd")
        with open(p, "w") as f:
            f.write('#!/bin/sh\nexec cat "$2"\n')
        os.chmod(p, 0o755 if executable else 0o644)
        return p

    def test_zstd_is_found_where_homebrew_puts_it(self):
        """The menu bar runs under launchd, whose PATH has no Homebrew folder,
        so shutil.which never found zstd there: every compressed session was
        left out and the menu said to install zstd, which was installed."""
        missing = os.path.join(self.tmp, "nowhere", "zstd")
        not_runnable = self.fake_zstd(os.path.join(self.tmp, "plain"), executable=False)
        tool = self.fake_zstd(os.path.join(self.tmp, "homebrew", "bin"))
        with self.no_decoder_but(missing, not_runnable, tool):
            self.assertEqual(tm.codex._zstd_tool(), tool)
            p = self.place("gen4_current_paginated.jsonl")
            os.rename(p, p + ".zst")
            overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertNotIn("could not be read", notes)

    def test_with_no_decoder_anywhere_it_says_to_install_zstd(self):
        """No decoder at all is a different problem from a damaged file, and
        only this one is solved by installing zstd."""
        p = self.place("gen4_current_paginated.jsonl")
        os.rename(p, p + ".zst")
        with self.no_decoder_but(os.path.join(self.tmp, "nowhere", "zstd")):
            self.assertIsNone(tm.codex._zstd_tool())
            overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 0)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("1 compressed Codex session (.jsonl.zst) could not be read. Install zstd "
                      "(brew install zstd) to include them", notes)
        self.assertNotIn("damaged", notes)

    def test_a_compressed_session_is_decompressed_once(self):
        """records() decompressed every .jsonl.zst twice, once to see whether
        it could and again to read it: two zstd runs per file per refresh."""
        from unittest import mock
        for n, fx in enumerate(("gen3_turn_context.jsonl", "gen4_current_paginated.jsonl")):
            p = self.place(fx, uuid=f"0198f3c1-0000-7000-8000-00000000000{n}")
            os.rename(p, p + ".zst")
        reads = []

        def read(path):   # the files are not really compressed
            reads.append(path)
            return slurp(path, mode="rb")
        with mock.patch.object(tm.codex, "_decoder", return_value=read):
            overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 6)
        self.assertEqual(len(reads), 2)
        self.assertEqual(len(set(reads)), 2)

    def test_a_compressed_session_splits_into_lines_as_a_plain_one_does(self):
        """Decompressed text was split with str.splitlines(), which also
        splits at a raw U+2028 inside a JSON string, so a turn_context line
        holding one was lost and its calls were priced as gpt-5."""
        from unittest import mock
        lines = slurp(os.path.join(FIXTURES, "codex", "gen3_turn_context.jsonl")).splitlines()
        for i, line in enumerate(lines):
            obj = json.loads(line)
            if obj["type"] == "turn_context":
                obj["payload"]["user_instructions"] = "first line second line"
                lines[i] = json.dumps(obj, ensure_ascii=False)
        plain = os.path.join(self.tmp, "rollout-2026-09-24T14-07-33-plain.jsonl")
        with open(plain, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        compressed = plain.replace(".jsonl", "-zst.jsonl.zst")
        shutil.copy(plain, compressed)
        with mock.patch.object(tm.codex, "_decoder", return_value=lambda path: slurp(path, mode="rb")):
            got = [ev["model"] for _, ev in tm.codex.records(compressed)]
        self.assertEqual(got, [ev["model"] for _, ev in tm.codex.records(plain)])
        self.assertEqual(got, ["gpt-5.2-codex", "gpt-5.2-codex", "gpt-5.3-codex"])

    def test_claude_code_alone_is_unchanged_by_codex_existing(self):
        """Adding an adapter must not move a Claude Code figure."""
        self.write("a.jsonl", record("msg_1", out=1000, read=5000))
        before, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.place("gen3_turn_context.jsonl")
        tm._ONLY[:] = ["claude-code"]
        after, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(before["total"], after["total"])


class TestGeminiCliAdapter(Base):
    """Built from the published source and labelled unverified."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "gemini-home")
        shutil.copytree(os.path.join(FIXTURES, "gemini-cli", "home"), self.home)
        tm.ADAPTER_ROOTS["gemini-cli"] = [os.path.join(self.home, ".gemini", "tmp")]
        self.expected = json.loads(slurp(os.path.join(FIXTURES, "gemini-cli", "expected.json")))
        tm._ONLY[:] = ["gemini-cli"]

    def test_reads_as_the_source_says(self):
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        t = self.expected["totals"]
        self.assertEqual(overall["calls"], t["calls"])
        self.assertEqual(overall["tokens"]["input"], t["uncached_input"] + t["tool_prompt"])
        self.assertEqual(overall["tokens"]["cache_read"], t["cache_read"])
        # Thinking is billed as output, and Gemini reports it separately.
        self.assertEqual(overall["tokens"]["output"], t["output"] + t["reasoning"])
        self.assertEqual(overall["tokens"]["thinking"], t["reasoning"])
        self.assertEqual(set(groups["project"]), {"/Users/example/code/demo"})
        self.assertEqual(set(groups["provider"]), {"google"})

    def test_a_message_written_twice_counts_once(self):
        """Each message is appended again when its tokens arrive."""
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)

    def test_a_legacy_json_copy_of_the_same_session_counts_once(self):
        chats = os.path.join(self.home, ".gemini", "tmp", "demo", "chats")
        src = os.path.join(chats, "session-2026-09-26T09-12-3f9c1a2b.jsonl")
        lines = [json.loads(l) for l in slurp(src).splitlines() if l.strip()]
        doc = {"sessionId": lines[0]["sessionId"], "projectHash": lines[0]["projectHash"],
               "messages": [l for l in lines[1:] if "id" in l]}
        with open(os.path.join(chats, "session-2026-09-26T09-12-3f9c1a2b.json"), "w") as f:
            json.dump(doc, f)
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 3)

    def test_labelled_unverified(self):
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertTrue(any("Gemini CLI figures are unverified" in t
                            for _, t in tm.report_notes(groups, unknown)))


class TestOpenCodeAdapter(Base):
    """Built from the published source and labelled unverified."""

    def setUp(self):
        super().setUp()
        import sqlite3
        root = os.path.join(self.tmp, "opencode-data", "opencode")
        os.makedirs(root)
        con = sqlite3.connect(os.path.join(root, "opencode.db"))
        con.executescript(slurp(os.path.join(FIXTURES, "opencode", "build_db.sql")))
        con.commit()
        con.close()
        tm.ADAPTER_ROOTS["opencode"] = [root]
        tm._ONLY[:] = ["opencode"]
        self.expected = json.loads(slurp(os.path.join(FIXTURES, "opencode", "expected.json")))

    def test_reads_both_write_paths_as_the_source_says(self):
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        t = self.expected["totals"]
        self.assertEqual(overall["calls"], t["calls"])
        self.assertEqual(overall["tokens"]["input"], t["uncached_input"])
        self.assertEqual(overall["tokens"]["cache_read"], t["cache_read"])
        self.assertEqual(overall["tokens"]["cache_write"], t["cache_write"])
        self.assertEqual(overall["tokens"]["output"], t["output"] + t["reasoning"])

    def test_multi_step_turns_are_counted_step_by_step(self):
        """The v1 message row holds only its last step's tokens; ccusage's mistake."""
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        v1 = groups["session"]["ses_v1demo0001"]
        cross = self.expected["cross_check"]["ses_v1demo0001"]
        self.assertEqual(v1["calls"], 2)
        self.assertEqual(v1["tokens"]["input"], cross["tokens_input"])
        self.assertEqual(v1["tokens"]["cache_write"], cross["tokens_cache_write"])

    def test_each_call_uses_its_own_providers_table(self):
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(set(groups["provider"]), {"anthropic", "openai"})
        self.assertFalse(unknown)
        want = 0.0
        for c in self.expected["calls"]:
            u = usage(inp=c["uncached_input"], read=c["cache_read"], w5=c["cache_write"],
                      out=c["output"] + c["reasoning"])
            want += cost_of(tm.price_record(c["model"], u, provider=c["provider"],
                                            when=dt.datetime.fromtimestamp(c["timestamp_ms"] / 1000,
                                                                           tz=dt.timezone.utc)))
        self.assertAlmostEqual(overall["total"], want, places=12)

    def test_project_filter_uses_the_recorded_folder(self):
        tm._PROJECT[:] = ["demo"]
        try:
            overall, *_ = tm.collect(tm.transcripts(project="demo"), ledger=False)
            self.assertEqual(overall["calls"], 4)
            tm._PROJECT[:] = ["elsewhere"]
            overall, *_ = tm.collect(tm.transcripts(project="elsewhere"), ledger=False)
            self.assertEqual(overall["calls"], 0)
        finally:
            tm._PROJECT.clear()


class TestOnlineLookup(Base):
    """The startup check, with every fetch faked. Nothing here uses the network."""

    PAGE = ("| Model | Base input tokens | 5m cache writes | 1h cache writes | "
            "Cache hits and refreshes | Output tokens |\n| :-- | :-- | :-- | :-- | :-- | :-- |\n"
            "| Claude Opus 9 | $6 / MTok | $7.50 / MTok | $12 / MTok | $0.60 / MTok | $30 / MTok |\n")
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
        lines = ["| Model | Base input tokens | 5m cache writes | 1h cache writes | "
                 "Cache hits and refreshes | Output tokens |", "| :-- | :-- | :-- | :-- | :-- | :-- |"]
        for name, mid in tm._anthropic.PAGE_NAMES.items():
            r = tm.PRICES[mid][-1]
            vals = [r["in"], r["in"] * 1.25, r["in"] * 2, r["in"] * r["cache_read_mult"], r["out"]]
            if tweak and tweak[0] == mid:
                vals[tweak[1]] = tweak[2]
            lines.append(f"| {name} | " + " | ".join(f"${v:g} / MTok" for v in vals) + " |")
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
        self.assertIn("19 of 19", out)
        self.assertEqual(before, json.dumps(tm.PRICES, sort_keys=True, default=str))

    def test_a_moved_rate_is_reported(self):
        code, out = self.run_check(lambda url: self.anthropic_page(("claude-sonnet-5", 4, 15.0)))
        self.assertEqual(code, 1)
        self.assertIn("claude-sonnet-5 out: table has $10, page says $15", out)

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
        self.assertIn("18 of 18", out)
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


class TestNamesAndNotes(Base):
    def test_project_names_drop_the_home_directory(self):
        home = os.path.expanduser("~")
        slug = re.sub(r"[^A-Za-z0-9]", "-", home)
        self.assertEqual(tm.project_name(slug + "-code-app"), "code-app")
        self.assertEqual(tm.project_name(os.path.join(home, "code", "app")), "code/app")
        self.assertEqual(tm.project_name("-srv-shared-app"), "-srv-shared-app")

    def test_a_stale_table_is_flagged(self):
        real = tm._anthropic.VERIFIED_ON
        tm._anthropic.VERIFIED_ON = "2020-01-01"
        try:
            self.write("a.jsonl", record("msg_1", out=100))
            overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
            warns = [t for level, t in tm.report_notes(groups, unknown) if level == "warn"]
        finally:
            tm._anthropic.VERIFIED_ON = real
        self.assertTrue(any("days ago" in t and "--check-prices" in t for t in warns))

    def test_every_report_says_when_its_rates_were_checked(self):
        self.write("a.jsonl", record("msg_1", out=100))
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        info = [t for level, t in tm.report_notes(groups, unknown) if level == "info"]
        self.assertTrue(any(t.startswith("Anthropic rates checked") for t in info))

    def test_dollars_need_no_exchange_rate(self):
        """The status line runs on every prompt; in dollars it must not fetch."""
        called = []
        real = tm.fx_rates
        tm.fx_rates = lambda: called.append(1) or ({}, "", True)
        try:
            tm.set_currency("USD")
        finally:
            tm.fx_rates = real
        self.assertEqual(called, [])


def lay_out_three_harnesses(test):
    """Claude Code, Codex and Gemini CLI side by side, from the repo's fixtures."""
    test.write("a.jsonl", record("msg_1", out=1000, read=5000))
    day = os.path.join(test.tmp, "codex-home", "sessions", "2026", "09", "24")
    os.makedirs(day)
    shutil.copy(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"),
                os.path.join(day, "rollout-2026-09-24T14-07-33-"
                                  "0198f3c1-6d2a-7b41-9e05-3c8d5a27b110.jsonl"))
    tm.ADAPTER_ROOTS["codex"] = [os.path.join(test.tmp, "codex-home", "sessions")]
    gemini = os.path.join(test.tmp, "gemini-home")
    shutil.copytree(os.path.join(FIXTURES, "gemini-cli", "home"), gemini)
    tm.ADAPTER_ROOTS["gemini-cli"] = [os.path.join(gemini, ".gemini", "tmp")]
    return tm.transcripts()


class TestReportsSayItOnce(Base):
    """How reports read with several harnesses: found by a clean-room run of
    1.0.0 on a home with four of them."""

    def several_harnesses(self):
        paths = lay_out_three_harnesses(self)
        return paths, tm.collect(paths, ledger=False)

    def test_unverified_harnesses_share_one_note(self):
        """Every report said "X figures are unverified" once per harness."""
        _, (overall, groups, _, unknown) = self.several_harnesses()
        notes = [t for _, t in tm.report_notes(groups, unknown) if "unverified" in t]
        self.assertEqual(len(notes), 1, notes)
        self.assertTrue(notes[0].startswith("Codex and Gemini CLI figures, "), notes[0])
        share = (groups["source"]["codex"]["total"]
                 + groups["source"]["gemini-cli"]["total"]) / overall["total"]
        self.assertIn(f"{share * 100:.1f}% of this total", notes[0])

    def test_one_harness_alone_gives_no_share(self):
        """Alone, "100% of this total" would say nothing worth reading."""
        self.several_harnesses()
        tm._ONLY[:] = ["codex"]
        _, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        notes = [t for _, t in tm.report_notes(groups, unknown) if "unverified" in t]
        self.assertEqual(len(notes), 1, notes)
        self.assertTrue(notes[0].startswith("Codex figures are unverified"), notes[0])

    def test_the_covered_line_reads_as_a_sentence(self):
        """It read "170 Claude Code transcripts and 2 Codex sessions and
        1 Gemini CLI sessions and 1 OpenCode databases"."""
        paths, (_, groups, _, _) = self.several_harnesses()
        self.assertIn("1 Claude Code transcript, 1 Codex session and 1 Gemini CLI session",
                      tm.covered_span(groups, paths))
        tm._OWNER.update({"a": "claude-code", "b": "claude-code", "c": "opencode", "d": "import"})
        self.assertIn("2 Claude Code transcripts, 1 import file and 1 OpenCode database",
                      tm.covered_span(groups, ["a", "b", "c", "d"]))

    def test_a_first_run_counts_what_it_just_wrote(self):
        """A first run said "ledger holds 0" having just written every call."""
        self.write("a.jsonl", record("msg_1", out=10), record("msg_2", out=20))
        paths = tm.transcripts()
        _, groups, *_ = tm.collect(paths)
        self.assertIn("ledger holds 2", tm.covered_span(groups, paths))
        # A second run writes nothing new, and a bigger copy of a call already
        # held supersedes it rather than adding a third.
        self.write("b.jsonl", record("msg_1", out=5000))
        paths = tm.transcripts()
        _, groups, *_ = tm.collect(paths)
        self.assertIn("ledger holds 2", tm.covered_span(groups, paths))

    def notes_for(self, model, fetch):
        """The notes naming a model, after a run whose every fetch is `fetch`."""
        self.write("a.jsonl", record("msg_1", model=model, out=100))
        tm.ONLINE_LOOKUP[0] = True
        real = tm.fetch_text
        tm.fetch_text = lambda url, timeout=8: fetch(url)
        try:
            _, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        finally:
            tm.fetch_text = real
            tm.ONLINE_LOOKUP[0] = False
        return [t for _, t in tm.report_notes(groups, unknown) if model in t]

    def test_a_model_found_nowhere_gets_one_note(self):
        """It had two: "looked up X online and found no published price" and
        "no price on file for X", about the same model."""
        def fetch(url):
            if url == tm.LITELLM_URL:
                return json.dumps({"claude-something-else": {}})
            return TestOnlineLookup.PAGE
        notes = self.notes_for("claude-nothing-1", fetch)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("no price on file for claude-nothing-1, and none published online either",
                      notes[0])

    def test_an_unreachable_lookup_says_so(self):
        """With the network down, a model was reported as having no price
        published anywhere, which nobody had found out."""
        def fetch(url):
            raise OSError("offline in tests")
        notes = self.notes_for("claude-nothing-1", fetch)
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("no price on file for claude-nothing-1, and the online lookup could not "
                      "reach its price lists (offline?)", notes[0])
        self.assertNotIn("none published", notes[0])

    def test_found_nowhere_and_unreachable_are_told_apart(self):
        """Each model in one note says which of the two happened to it."""
        self.write("a.jsonl", record("msg_1", model="claude-nothing-1", out=100),
                   record("msg_2", model="claude-nothing-2", out=100),
                   record("msg_3", model="claude-nothing-3", out=100))
        _, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        tm.LOOKUPS[:] = [
            {"provider": "anthropic", "model": "claude-nothing-1", "found": False, "error": False},
            {"provider": "anthropic", "model": "claude-nothing-2", "found": False, "error": True}]
        note = next(t for _, t in tm.report_notes(groups, unknown) if "no price on file" in t)
        self.assertIn("no price on file for claude-nothing-1, claude-nothing-2 and "
                      "claude-nothing-3 (and none published online for claude-nothing-1; "
                      "the online lookup could not reach its price lists for "
                      "claude-nothing-2). ", note)


def payload_of(page):
    """The dashboard's data block, as the browser receives it."""
    start = page.index("const D = ") + len("const D = ")
    return json.JSONDecoder().raw_decode(page[start:])[0]


def terminal(*args, **kw):
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tm.print_report(*args, **kw)
    return re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())


def cli(*argv):
    """The command line with these arguments: what it prints, without colour.
    In dollars unless a test names a currency, because the environment running
    the tests may set TOKENMETER_CURRENCY to another one."""
    import contextlib, io
    argv = list(argv)
    if "--currency" not in argv:
        argv += ["--currency", "USD"]
    # Each run starts as a new process would: main() sets these only from the
    # options it is given, so one run's --import or --session would leak on.
    tm._IMPORTS.clear()
    tm._PROJECT.clear()
    tm._SESSION.clear()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tm.main(argv)
    return re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())


class TestOneHarnessSeesNoChange(Base):
    """One harness on one provider must see exactly what it always did: the
    views for mixing tools appear only when tools are mixed."""

    def setUp(self):
        super().setUp()
        self.write("a.jsonl", record("msg_1", out=1000, read=5000),
                   record("msg_2", ts="2026-09-02T09:00:00.000Z", out=200))
        self.paths = tm.transcripts()
        whole, self.parts = tm.collect_views(self.paths, ledger=False)
        self.result = whole.result()

    def test_the_dashboard_has_none_of_the_new_sections(self):
        out = os.path.join(self.tmp, "d.html")
        tm.render_html(*self.result, "all time", out,
                       views=tm.harness_pages(self.parts, self.paths))
        page = slurp(out, encoding="utf-8")
        for mark in ('class="hsel"', "How far to trust this", 'class="slegend"',
                     'class="grp"', "By harness", 'data-view="claude-code"', 'class="chip"'):
            self.assertNotIn(mark, page)
        self.assertEqual(list(payload_of(page)["views"]), ["all"])
        self.assertNotIn("series", payload_of(page)["views"]["all"])

    def test_the_terminal_adds_nothing(self):
        out = terminal(*self.result, "", "all time")
        self.assertNotIn("by harness", out)
        self.assertNotIn("by provider", out)

    def test_the_menu_bar_is_told_not_to_change(self):
        s = tm.summary()
        self.assertFalse(s["multi"])
        self.assertEqual(len(s["harnesses"]), 1)


class TestSeveralHarnesses(Base):
    """Harnesses mixed: every figure still comes from the one engine."""

    def setUp(self):
        super().setUp()
        self.paths = lay_out_three_harnesses(self)
        self.whole, self.parts = tm.collect_views(self.paths, ledger=False)
        self.overall, self.groups, self.meta, self.unknown = self.whole.result()

    def test_each_harness_page_is_exactly_its_share(self):
        """A harness's page is built from its own part of the same pass, so it
        must match the whole run's figure for that harness to the last bit."""
        self.assertEqual(set(self.parts), {"claude-code", "codex", "gemini-cli"})
        for source, part in self.parts.items():
            self.assertEqual(part.overall["total"], self.groups["source"][source]["total"])
            self.assertEqual(part.overall["calls"], self.groups["source"][source]["calls"])
        self.assertAlmostEqual(sum(p.overall["total"] for p in self.parts.values()),
                               self.overall["total"], places=12)

    def test_split_bars_add_up_to_each_day(self):
        out = os.path.join(self.tmp, "d.html")
        tm.render_html(self.overall, self.groups, self.meta, self.unknown, "all time", out,
                       views=tm.harness_pages(self.parts, self.paths))
        page = slurp(out, encoding="utf-8")
        data = payload_of(page)
        self.assertEqual(set(data["views"]), {"all", "claude-code", "codex", "gemini-cli"})
        allv = data["views"]["all"]
        self.assertEqual([s["name"] for s in allv["series"]], ["claude-code", "codex", "gemini-cli"])
        for d in allv["days"]:
            self.assertAlmostEqual(sum(d["by"].values()), d["total"], places=9)
            self.assertEqual(sum(d["byCalls"].values()), d["calls"])
        # Every harness page draws over the whole run's days.
        for key in ("claude-code", "codex", "gemini-cli"):
            self.assertEqual([d["full"] for d in data["views"][key]["days"]],
                             [d["full"] for d in allv["days"]])
        for mark in ('class="hsel"', "How far to trust this", "By harness", 'class="grp"'):
            self.assertIn(mark, page)
        self.assertNotIn("..</p>", page)

    def test_trust_shares_add_up_and_name_the_unverified(self):
        ts = tm.trust_summary(self.groups, self.unknown)
        self.assertAlmostEqual(sum(ts["read"].values()), 1.0, places=12)
        self.assertAlmostEqual(sum(ts["price"].values()), 1.0, places=12)
        self.assertEqual(ts["unverified"], ["codex", "gemini-cli"])
        want = (self.groups["source"]["codex"]["total"]
                + self.groups["source"]["gemini-cli"]["total"]) / self.overall["total"]
        self.assertAlmostEqual(ts["unverified_share"], want, places=12)

    def test_models_are_grouped_under_their_provider(self):
        provs = {p["name"]: p for p in tm.models_by_provider(self.groups, self.unknown)}
        self.assertEqual(set(provs), {"anthropic", "openai", "google"})
        for p in provs.values():
            self.assertAlmostEqual(p["total"], self.groups["provider"][p["name"]]["total"], places=12)
        opus = [x for x in provs["anthropic"]["models"] if x["model"] == "claude-opus-5"][0]
        self.assertEqual(opus["harnesses"], ["Claude Code"])

    def test_the_terminal_compares_harnesses_only_when_asked(self):
        plain = terminal(self.overall, self.groups, self.meta, self.unknown, "", "all time")
        self.assertNotIn("by harness", plain)
        asked = terminal(self.overall, self.groups, self.meta, self.unknown, "source", "all time")
        self.assertIn("by harness", asked)
        self.assertIn("from cache", asked)
        self.assertIn("unverified", asked)

    def test_the_menu_bar_is_sent_what_mixing_needs(self):
        s = tm.summary()
        self.assertTrue(s["multi"])
        totals = [h["total"] for h in s["harnesses"]]
        self.assertEqual(len(totals), 3)
        self.assertEqual(totals, sorted(totals, reverse=True))   # dearest first
        self.assertEqual({p["name"] for p in s["providers"]}, {"anthropic", "openai", "google"})
        self.assertTrue(all("provider" in m for m in s["models"]))
        self.assertGreater(s["unverified_share"], 0)

    def test_your_own_imports_are_not_called_unverified(self):
        """An import is the user's own data: neither a verified reader nor an
        unverified one, and never counted as the second."""
        path = os.path.join(self.tmp, "events.jsonl")
        with open(path, "w") as f:
            f.write(json.dumps({"id": "e1", "timestamp": "2026-09-20T10:00:00Z", "provider": "openai",
                                "model": "gpt-6-sol", "input": 1000, "output": 500}) + "\n")
        tm._IMPORTS[:] = [path]
        tm._ONLY[:] = ["claude-code", "import"]
        _, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        ts = tm.trust_summary(groups, unknown)
        self.assertEqual(ts["unverified"], [])
        self.assertEqual(ts["read"]["unverified"], 0.0)
        self.assertGreater(ts["read"]["imported"], 0.0)
        self.assertAlmostEqual(ts["read"]["imported"] + ts["read"]["verified"], 1.0, places=12)

    def test_shares_never_read_as_none_or_all_when_they_are_not(self):
        self.assertEqual(tm.share_text(0.0000004), "under 0.1%")
        self.assertEqual(tm.share_text(0.9999996), "over 99.9%")
        self.assertEqual(tm.share_text(1.0), "100.0%")
        self.assertEqual(tm.share_text(0.1234), "12.3%")


class TestMenuBarCurrencies(Base):
    def test_the_menu_is_sent_every_currency_in_order(self):
        """The menu offered four currencies from a list of its own; the
        dashboard offered seven."""
        self.write("a.jsonl", record("msg_1", out=10))
        s = tm.summary()
        self.assertEqual(s["currency_order"], list(tm.CURRENCIES))
        self.assertEqual(set(s["currency_order"]), set(s["currencies"]))
        self.assertGreaterEqual(len(s["currency_order"]), 7)

    def test_the_menu_takes_its_list_from_the_engine(self):
        swift = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "costbar", "main.swift"))
        self.assertIn('root["currency_order"]', swift)


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


class TestSessionTotals(Base):
    def agent(self, rel, *lines):
        p = os.path.join(self.projects, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        return p

    def test_a_sessions_agents_are_in_its_cost(self):
        """The status line priced the session's own transcript alone, so the
        calls its subagents and workflow agents made for it were missing from
        "session". The context stays the main transcript's."""
        main = self.write("sess-1.jsonl", record("msg_main", inp=1000, read=500, out=100))
        a = self.agent("sess-1/subagents/agent-a.jsonl", record("msg_a", inp=7000, out=200))
        b = self.agent("sess-1/subagents/workflows/wf_1/agent-b.jsonl",
                       record("msg_b", inp=9000, out=300),
                       # A call the session's own transcript also holds counts once.
                       record("msg_main", inp=1000, read=500, out=100))
        # A neighbouring session whose name starts the same is not this one.
        self.write("sess-10.jsonl", record("msg_x", out=5000))
        self.agent("sess-10/subagents/agent-z.jsonl", record("msg_z", out=5000))
        self.assertEqual(tm.claude_code.session_files(main), [main, a, b])
        overall, *_ = tm.collect([main, a, b], ledger=False)
        alone, *_ = tm.collect([main], ledger=False)
        cost, ctx = tm.session_totals(main)
        self.assertEqual(overall["calls"], 3)
        self.assertAlmostEqual(cost, overall["total"], places=12)
        self.assertGreater(cost, alone["total"])
        self.assertEqual(ctx, 1500)

    def test_a_path_with_no_agents_is_read_on_its_own(self):
        """An agent's own transcript, or a session that started none, is one
        file, so its cost is what it was."""
        a = self.agent("sess-1/subagents/agent-a.jsonl", record("msg_a", inp=7000, out=200))
        self.assertEqual(tm.claude_code.session_files(a), [a])
        alone, *_ = tm.collect([a], ledger=False)
        self.assertAlmostEqual(tm.session_totals(a)[0], alone["total"], places=12)


class TestStatusLine(Base):
    def run_statusline(self, payload, counted=False, day_cache=None, **env):
        """statusline.py as Claude Code runs it, sealed: a copy in the temp
        folder (so its day cache lands there), the engine from this checkout,
        a temp home, ledger and price cache, and no network. day_cache, when
        given, is written as a fresh .today_cost.json first."""
        import subprocess
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        here = os.path.join(self.tmp, "statusline")
        os.makedirs(here)
        shutil.copy(os.path.join(repo, "statusline.py"), here)
        if day_cache is not None:
            with open(os.path.join(here, ".today_cost.json"), "w") as f:
                json.dump(day_cache, f)
        sealed = {k: v for k, v in os.environ.items()
                  if not k.startswith("TOKENMETER_")
                  and k not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_DATA_HOME", "OPENCODE_DB")}
        sealed.update(HOME=self.tmp, PYTHONPATH=repo,
                      TOKENMETER_CLAUDE_PROJECTS=os.path.join(self.tmp, "projects"),
                      TOKENMETER_LEDGER=self.ledger,
                      TOKENMETER_PRICE_CACHE=os.path.join(self.tmp, "prices.json"),
                      TOKENMETER_OFFLINE="1", TOKENMETER_CURRENCY="USD")
        sealed.update(env)
        script = [os.path.join(here, "statusline.py")]
        if counted:
            # Run through a wrapper that counts every request and answers none.
            with open(os.path.join(here, "counted.py"), "w") as f:
                f.write("import runpy, sys, urllib.request\n"
                        "calls = []\n"
                        "def refuse(*args, **kw):\n"
                        "    calls.append(args)\n"
                        "    raise OSError('no network in tests')\n"
                        "urllib.request.urlopen = refuse\n"
                        "try:\n"
                        "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
                        "finally:\n"
                        "    sys.stderr.write('requests: %d\\n' % len(calls))\n")
            script.insert(0, os.path.join(here, "counted.py"))
        return subprocess.run([sys.executable] + script,
                              input=json.dumps(payload), capture_output=True, text=True,
                              env=sealed, timeout=60)

    def test_a_mistyped_currency_still_prints_both_lines(self):
        """TOKENMETER_CURRENCY=GPB made set_currency() exit, which "except
        Exception" does not catch: no status line at all, exit 1."""
        path = self.write("sess.jsonl", record("msg_1", out=1000))
        cost, _ = tm.session_totals(path)
        for code in ("USD", "GPB"):
            with self.subTest(code=code):
                shutil.rmtree(os.path.join(self.tmp, "statusline"), ignore_errors=True)
                done = self.run_statusline({"model": {"display_name": "Opus"},
                                            "transcript_path": path},
                                           TOKENMETER_CURRENCY=code)
                self.assertEqual(done.returncode, 0, done.stderr)
                out = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout)
                self.assertEqual(len(out.splitlines()), 2, out)
                self.assertIn(f"{tm.money(cost)} session", out)

    def test_it_makes_no_network_request(self):
        """It runs on every prompt, and fetched exchange rates (as many times
        as it asked for them) whenever none were saved, so a slow network held
        up the prompt. Online lookups on, pounds, a model no table has and
        nothing saved: every reason to fetch, and still no request."""
        path = self.write("sess.jsonl", record("msg_1", out=1000),
                          record("msg_2", model="claude-opus-9", out=1000))
        done = self.run_statusline({"model": {"display_name": "Opus"}, "transcript_path": path},
                                   counted=True, TOKENMETER_OFFLINE="", TOKENMETER_CURRENCY="GBP")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("requests: 0", done.stderr)
        out = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout)
        self.assertEqual(len(out.splitlines()), 2, out)
        self.assertIn("£", out)

    def test_yesterdays_total_is_not_shown_as_todays(self):
        """.today_cost.json held no day and was trusted for 90 seconds on its
        age alone, so just after midnight yesterday's total read as today's."""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        path = self.write("sess.jsonl", record("msg_1", ts=now, out=1000))
        worked_out = tm.money(tm.session_totals(path)[0])
        today = dt.date.today().isoformat()
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        for cache, want in (({"day": yesterday, "total": 999.0}, worked_out),
                            ({"total": 999.0}, worked_out),  # written before the day was kept
                            ({"day": today, "total": 999.0}, tm.money(999.0))):
            with self.subTest(cache=cache):
                shutil.rmtree(os.path.join(self.tmp, "statusline"), ignore_errors=True)
                done = self.run_statusline({"model": {"display_name": "Opus"},
                                            "transcript_path": path}, day_cache=cache)
                self.assertEqual(done.returncode, 0, done.stderr)
                out = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout)
                self.assertIn(f"{want} today", out)
                saved = json.loads(slurp(os.path.join(self.tmp, "statusline", ".today_cost.json")))
                self.assertEqual(saved["day"], today)

    def test_the_context_window_is_the_one_claude_code_sends(self):
        """The window was guessed from the model's name, Haiku 200k and
        anything else 1M, so a 200k model read at a fifth of its real
        percentage and a 1M Haiku read full at 200k. Claude Code sends the
        window and the percentage; the guess is only for builds that send
        neither, and the count shown is always the transcript's own."""
        path = self.write("sess.jsonl", record("msg_1", inp=100_000, out=10))
        cases = (
            ("Opus", {"context_window_size": 200000, "used_percentage": 75}, "75%", "/ 200k"),
            ("Claude Haiku 5.5", {"context_window_size": 1000000, "used_percentage": 30},
             "30%", "/ 1M"),
            # A size alone: the percentage is worked out against it.
            ("Opus", {"context_window_size": 400000, "used_percentage": None}, "25%", "/ 400.0k"),
            # A size that is not positive is no size; the percentage is clamped.
            ("Opus", {"context_window_size": 0, "used_percentage": 140}, "100%", "/ 1M"),
            # Nulls fall back to the guess, as no object at all does.
            ("Opus", {"context_window_size": None, "used_percentage": None}, "10%", "/ 1M"),
            ("Claude Haiku 4.5", None, "50%", "/ 200k"),
        )
        for model, sent, pct, cap in cases:
            with self.subTest(model=model, sent=sent):
                shutil.rmtree(os.path.join(self.tmp, "statusline"), ignore_errors=True)
                payload = {"model": {"display_name": model}, "transcript_path": path}
                if sent is not None:
                    payload["context_window"] = sent
                done = self.run_statusline(payload)
                self.assertEqual(done.returncode, 0, done.stderr)
                line1, line2 = re.sub(r"\x1b\[[0-9;]*m", "", done.stdout).splitlines()
                self.assertRegex(line1, r"ctx +" + re.escape(pct))
                self.assertIn("100.0k " + cap + " ", line2)

    def test_the_command_line_names_where_a_bad_code_came_from(self):
        """A typo in TOKENMETER_CURRENCY read as if it had been typed on the
        command line, which had no --currency on it."""
        from unittest import mock
        self.write("a.jsonl", record("msg_1", out=10))
        with mock.patch.object(tm, "DEFAULT_CURRENCY", "GPB"):
            with self.assertRaises(SystemExit) as e:
                tm.main(["--json"])
        self.assertIn("unknown currency 'GPB' in TOKENMETER_CURRENCY; try one of",
                      str(e.exception.code))
        with self.assertRaises(SystemExit) as e:
            cli("--json", "--currency", "GPB")
        self.assertIn("unknown currency 'GPB'; try one of", str(e.exception.code))


class TestCommandLine(Base):
    def test_main_takes_its_arguments(self):
        """main() read only sys.argv, so no test could drive the command line,
        and every mode it chooses between went untested."""
        self.write("a.jsonl", record("msg_1", out=1000), record("msg_2", out=500))
        got = json.loads(cli("--json", "--no-ledger"))
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(got["calls"], 2)
        self.assertEqual(got["currency"], "USD")
        self.assertAlmostEqual(got["total_usd"], round(overall["total"], 6), places=9)
        self.assertFalse(os.path.exists(self.ledger))


if __name__ == "__main__":
    unittest.main(verbosity=2)
