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
import unittest

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


class TestParseSince(Base):
    def test_relative_forms(self):
        for s in ("24h", "7d", "2w"):
            self.assertIsNotNone(tm.parse_since(s))

    def test_absolute_date(self):
        self.assertEqual(tm.parse_since("2026-09-01").date(), dt.date(2026, 9, 1))

    def test_nonsense_exits(self):
        with self.assertRaises(SystemExit):
            tm.parse_since("soonish")



FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def cost_of(c):
    return sum(c[k] for k in tm.COMPONENTS)


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

    def test_a_model_found_nowhere_gets_one_note(self):
        """It had two: "looked up X online and found no published price" and
        "no price on file for X", about the same model."""
        self.write("a.jsonl", record("msg_1", model="claude-nothing-1", out=100))
        tm.ONLINE_LOOKUP[0] = True
        real = tm.fetch_text

        def offline(url, timeout=8):
            raise OSError("offline in tests")
        tm.fetch_text = offline
        try:
            _, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        finally:
            tm.fetch_text = real
            tm.ONLINE_LOOKUP[0] = False
        notes = [t for _, t in tm.report_notes(groups, unknown) if "claude-nothing-1" in t]
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("no price on file for claude-nothing-1, and none published online either",
                      notes[0])


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
