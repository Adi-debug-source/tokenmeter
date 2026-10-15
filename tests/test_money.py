"""Money: how an amount is written on every face, and what caching was worth.

The menu bar and the dashboard keep their own copies of money(), in Swift
and JavaScript; the tests here that read their source hold all three to the
one rule.
"""

import datetime as dt
import os
import re
import unittest

from helpers import FIXTURES, Base, record, slurp, terminal, tm


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
        calls = re.findall(r"toLocaleString\(([^)]*)\)", tm.dashboard_asset("dashboard.js"))
        self.assertTrue(calls)
        for args in calls:
            self.assertTrue(args.startswith("'en-US'"), args)

    def test_every_copy_puts_the_minus_first(self):
        """$-0.10 was printed by all three copies; changing one alone would
        make the same saving read two ways."""
        swift = self.swift()
        money_swift = swift[swift.index("func money("):swift.index("func shownDifference")]
        js = tm.dashboard_asset("dashboard.js")
        fmt_js = js[js.index("function fmt("):js.index("let CUR")]
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


class TestWindowsAndCaching(Base):
    """Each face worked out the rolling windows and what caching was worth for
    itself: the dashboard and summary() each walked the day groups, the
    terminal, the dashboard and summary() each divided out the saving, and the
    menu bar divided again in Swift, against the rule that arithmetic lives in
    the engine. Now rolling_windows() and caching_summary() do it once."""

    def setUp(self):
        super().setUp()
        today = dt.date.today()

        def noon(days_ago):
            local = dt.datetime.combine(today - dt.timedelta(days=days_ago), dt.time(12)).astimezone()
            return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        self.write("a.jsonl", record("msg_1", ts=noon(0), inp=10, out=1000, read=50000),
                   record("msg_2", ts=noon(3), out=2000, w5=4000),
                   record("msg_3", ts=noon(20), out=500, read=9000),
                   record("msg_4", ts=noon(45), out=100))
        self.result = tm.collect(tm.transcripts(), ledger=False)
        self.page = os.path.join(self.tmp, "d.html")
        tm.render_html(*self.result, "all time", self.page)

    def test_the_windows_count_today_and_reach_back_6_and_29_days(self):
        _, groups, *_ = self.result
        w = tm.rolling_windows(groups, dt.date.today())
        self.assertEqual([w[k]["calls"] for k in ("today", "week", "month")], [1, 2, 3])
        s = tm.summary(ledger=False)
        page = slurp(self.page, encoding="utf-8")
        for k in ("today", "week", "month"):
            self.assertEqual(list(w[k]), list(tm.COMPONENTS) + ["total", "calls", "tokens"])
            self.assertAlmostEqual(sum(w[k][c] for c in tm.COMPONENTS), w[k]["total"], places=12)
            self.assertEqual(s[k], w[k])
            self.assertIn(f'<div class="win-v"><span class="m" data-usd="{w[k]["total"]:.8f}"', page)

    def test_every_face_shows_one_caching_summary(self):
        overall, groups, meta, unknown = self.result
        c = tm.caching_summary(overall)
        saved = overall["no_cache"] - overall["total"]
        self.assertEqual((c["saved"], c["saved_pct"], c["multiple"], c["hit_pct"]),
                         (saved, saved / overall["no_cache"] * 100,
                          overall["no_cache"] / overall["total"], tm.cache_hit_pct(overall)))
        s = tm.summary(ledger=False)
        self.assertEqual((s["without_cache"], s["no_cache_saved"], s["saved_pct"], s["multiple"],
                          s["cache_hit_pct"]),
                         (c["without_cache"], c["saved"], c["saved_pct"], c["multiple"], c["hit_pct"]))
        out = terminal(overall, groups, meta, unknown, "", "all time")
        self.assertIn(f"{c['saved_pct']:.1f}% cheaper, {c['multiple']:.1f}x", out)
        rate = tm.unit_money(c["cache_read_per_million"])
        self.assertIn(f"{c['hit_pct']:.1f}% of prompt tokens came from cache at {rate} per million", out)
        page = slurp(self.page, encoding="utf-8")
        self.assertIn(f"{c['saved_pct']:.1f}% cheaper. Caching made it {c['multiple']:.1f}x "
                      "less expensive.", page)
        self.assertIn(f"<b>{c['hit_pct']:.1f}%</b><span>From cache</span>", page)
        self.assertIn(f"at {rate} per million against full input rates", page)

    def test_a_dearer_run_and_an_empty_one(self):
        overall, *_ = tm.collect([], ledger=False)
        c = tm.caching_summary(overall)
        self.assertEqual((c["prompt_tokens"], c["hit_pct"], c["saved"], c["saved_pct"], c["multiple"]),
                         (0, 0.0, 0.0, 0, 0))
        overall["tokens"]["cache_write"] = 20005
        overall["total"], overall["no_cache"] = 0.200275, 0.100275
        c = tm.caching_summary(overall)
        self.assertEqual(f"{-c['saved_pct']:.1f}% dearer", "99.7% dearer")
        self.assertAlmostEqual(c["multiple"], 0.100275 / 0.200275, places=15)

    def test_the_menu_bar_reads_them_and_divides_nothing(self):
        swift = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "costbar", "main.swift"),
                      encoding="utf-8")
        self.assertIn('snap.savedPct = root["saved_pct"] as? Double ?? 0', swift)
        self.assertIn('snap.multiple = root["multiple"] as? Double ?? 0', swift)
        self.assertIn('String(format: "%.1f%% dearer", -snap.savedPct)', swift)
        self.assertIn('max(snap.savedPct, 0), snap.multiple)', swift)
        for division in ("/ snap.withoutCache", "snap.withoutCache /", "/ snap.all.total"):
            self.assertNotIn(division, swift)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
