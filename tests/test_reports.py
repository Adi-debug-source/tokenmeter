"""Reports and the command line: windows and periods, filters and labels,
notes, several harnesses side by side, --summary-json for the menu bar,
--json and plain text for scripts and pipes, opening the dashboard, what a
first run and a filter that matches nothing say, the installer's check of
the Python the menu bar runs, and a run starting afresh.
"""

import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import unittest.mock

from helpers import (ANTHROPIC_PAGE, FIXTURES, GOOD_IMPORT, Base, as_a_new_run, cli,
                     lay_out_three_harnesses, payload_of, record, slurp, terminal, tm)


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
            f.write(json.dumps(dict(GOOD_IMPORT, project=self.WHERE)) + "\n")
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


class TestSummaryJson(Base):
    """--summary-json was answered before any option was applied, from a
    summary() that always used the ledger: a trial import with --no-ledger was
    written to the ledger for good, and --since 1h --project zzz returned the
    whole history without saying so."""

    def trial(self):
        p = os.path.join(self.tmp, "trial.jsonl")
        with open(p, "w") as f:
            f.write(json.dumps(GOOD_IMPORT) + "\n")
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
        with mock.patch.object(tm, "DEFAULT_CURRENCY", "GPB"), as_a_new_run(), \
                contextlib.redirect_stdout(buf):
            tm.main(["--summary-json"])
        self.assertEqual(json.loads(buf.getvalue())["all"]["calls"], 1)

    def lay_out_a_month(self):
        """Calls today, 3, 20 and 45 days ago, all in the ledger, then the
        3-day-old one's transcript deleted."""
        today = dt.date.today()

        def noon(days_ago):
            local = dt.datetime.combine(today - dt.timedelta(days=days_ago), dt.time(12)).astimezone()
            return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        self.write("a.jsonl", record("msg_1", ts=noon(0), inp=10, out=1000, think=300, read=50000),
                   record("msg_3", ts=noon(20), out=500, read=9000, w1=700),
                   record("msg_4", ts=noon(45), out=100, w5=40, searches=2))
        gone = self.write("b.jsonl", record("msg_2", ts=noon(3), inp=5, out=2000, w5=4000))
        tm.collect(tm.transcripts(), ledger=True)
        os.remove(gone)

    def test_the_tokens_add_up_and_every_old_key_keeps_its_value(self):
        """The menu bar had money and calls for each window and no tokens.
        Each window and all time gain a tokens object by token_totals(), and
        all time the on-disk split; nothing it read before moves."""
        self.lay_out_a_month()
        got = json.loads(cli("--summary-json"))
        overall, groups, _meta, _unknown = tm.collect(tm.transcripts(), ledger=True)
        windows = tm.rolling_windows(groups, dt.date.today())
        kinds = ["input", "cache_write", "cache_read", "output", "thinking", "total", "fresh"]
        for k in ("today", "week", "month"):
            with self.subTest(window=k):
                self.assertEqual(list(got[k]), list(tm.COMPONENTS) + ["total", "calls", "tokens"])
                self.assertEqual({key: got[k][key] for key in got[k] if key != "tokens"},
                                 {key: windows[k][key] for key in windows[k] if key != "tokens"})
        self.assertEqual(list(got["all"]), list(tm.COMPONENTS) + [
            "total", "calls", "tokens", "tokens_on_disk", "tokens_ledger_only"])
        self.assertAlmostEqual(got["all"]["total"], overall["total"], places=12)
        self.assertEqual(got["all"]["calls"], 4)
        self.assertEqual(got["tokens"], overall["tokens"])     # unchanged, searches and all
        self.assertNotIn("total", got["tokens"])
        for k in ("today", "week", "month", "all"):
            with self.subTest(period=k):
                t = got[k]["tokens"]
                self.assertEqual(list(t), kinds)
                self.assertEqual(t["total"], t["input"] + t["cache_write"] + t["cache_read"]
                                 + t["output"])
                self.assertEqual(t["fresh"], t["total"] - t["cache_read"])
        self.assertEqual([got[k]["tokens"]["total"] for k in ("today", "week", "month", "all")],
                         [51010, 57015, 67215, 67355])
        self.assertEqual(got["all"]["tokens"]["thinking"], 300)
        self.assertEqual({k: got["all"]["tokens"][k] for k in kinds[:5]},
                         {k: got["tokens"][k] for k in kinds[:5]})
        self.assertEqual((got["all"]["tokens_on_disk"], got["all"]["tokens_ledger_only"]),
                         (61350, 6005))
        self.assertEqual(got["all"]["tokens_on_disk"] + got["all"]["tokens_ledger_only"],
                         got["all"]["tokens"]["total"])

    def test_no_ledger_gives_the_on_disk_figure(self):
        """--summary-json once ignored --no-ledger, which would have made its
        on-disk figure the ledger's. Without the ledger, all time is what the
        transcripts hold, none of it is ledger only, and the ledger is left
        as it was."""
        self.lay_out_a_month()
        before = slurp(self.ledger, mode="rb")
        kept = json.loads(cli("--summary-json"))["all"]
        on_disk = json.loads(cli("--summary-json", "--no-ledger"))["all"]
        self.assertEqual(on_disk["tokens"]["total"], kept["tokens_on_disk"])
        self.assertEqual((on_disk["tokens_on_disk"], on_disk["tokens_ledger_only"]),
                         (on_disk["tokens"]["total"], 0))
        self.assertEqual(on_disk["calls"], kept["calls"] - 1)
        self.assertEqual(slurp(self.ledger, mode="rb"), before)

    def test_days_are_the_last_30_calendar_days(self):
        """The menu bar's "Daily spend, last 30 days" sparkline was sent the
        last 30 days that had calls, so after any quiet spell it reached back
        further than 30 days and drew the days either side of a gap as
        neighbours."""
        today = dt.date.today()

        def noon(days_ago):
            local = dt.datetime.combine(today - dt.timedelta(days=days_ago), dt.time(12)).astimezone()
            return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        self.write("a.jsonl", record("msg_1", ts=noon(0), out=1000),
                   record("msg_2", ts=noon(3), out=2000), record("msg_3", ts=noon(45), out=500))
        days = tm.summary(ledger=False)["days"]
        self.assertEqual([d["day"] for d in days],
                         [(today - dt.timedelta(days=n)).isoformat() for n in range(29, -1, -1)])
        self.assertAlmostEqual(days[-1]["total"], 1000 * 25 / 1e6, places=12)
        self.assertAlmostEqual(days[-4]["total"], 2000 * 25 / 1e6, places=12)
        self.assertEqual(days[-2]["total"], 0.0)                 # a day with no calls
        self.assertEqual(sum(1 for d in days if d["total"]), 2)  # 45 days ago is not in it
        # Now always 30 entries, so the menu bar draws nothing for a month of
        # zeros rather than an empty line.
        swift = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "costbar", "main.swift"),
                      encoding="utf-8")
        self.assertIn("if snap.days.contains(where: { $0 > 0 }) {", swift)


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


class TestWeeksAndMonths(Base):
    """--by offered days but not weeks or months, so a month's figure meant
    adding up a column of days by hand. Both are summed from the day rows,
    listed oldest first as days are, in the terminal and in --json.

    The calls are at noon UTC, which is the same date in every time zone from
    UTC-11 to UTC+11, so the local days are the ones written."""

    def rows(self, by):
        got = json.loads(cli("--json", "--by", by, "--no-ledger"))
        return got, [(r["key"], r["calls"]) for r in got["groups"]]

    def table(self, by):
        text = cli("--by", by, "--no-ledger")
        return [line.split()[0] for line in
                text.split(f"by {by}\n", 1)[1].split("\n\n", 1)[0].splitlines()]

    def test_months_across_a_boundary_add_up_to_the_whole(self):
        self.write("a.jsonl", record("m1", ts="2026-09-30T12:00:00.000Z", out=1000),
                   record("m2", ts="2026-10-01T12:00:00.000Z", out=2000, read=4000))
        self.write("b.jsonl", record("m3", ts="2026-10-02T12:00:00.000Z", inp=300, out=500))
        got, rows = self.rows("month")
        self.assertEqual(rows, [("2026-09", 1), ("2026-10", 2)])
        self.assertAlmostEqual(sum(r["total_usd"] for r in got["groups"]), got["total_usd"],
                               places=9)
        self.assertEqual(self.table("month"), ["2026-09", "2026-10"])

        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        months = dict(tm.grouped(groups, "month"))
        self.assertAlmostEqual(sum(v["total"] for v in months.values()), overall["total"],
                               places=12)
        october = [groups["day"]["2026-10-01"], groups["day"]["2026-10-02"]]
        for k in tm.COMPONENTS + ("total", "no_cache", "calls"):
            self.assertEqual(months["2026-10"][k], october[0][k] + october[1][k], k)
        for k in overall["tokens"]:
            self.assertEqual(sum(v["tokens"][k] for v in months.values()), overall["tokens"][k])

    def test_weeks_are_iso_weeks_from_monday(self):
        self.assertEqual(tm.week_of("2026-12-31"), "2026-W53")
        self.assertEqual(tm.week_of("2027-01-01"), "2026-W53")
        self.assertEqual(tm.week_of("2026-12-27"), "2026-W52")   # a Sunday
        self.assertEqual(tm.week_of("2026-12-28"), "2026-W53")   # the Monday after it
        self.assertEqual(tm.week_of("2027-01-04"), "2027-W01")
        # --period week starts on the Monday of the week today is in.
        today = dt.date.today()
        monday = tm.period_range("week")[0].date()
        self.assertEqual(tm.week_of(monday.isoformat()), tm.week_of(today.isoformat()))
        self.assertNotEqual(tm.week_of((monday - dt.timedelta(days=1)).isoformat()),
                            tm.week_of(today.isoformat()))

    def test_the_new_year_is_one_week_and_two_months(self):
        self.write("a.jsonl", record("y1", ts="2026-12-31T12:00:00.000Z", out=1000),
                   record("y2", ts="2027-01-01T12:00:00.000Z", out=2000))
        self.write("b.jsonl", record("y3", ts="2027-01-04T12:00:00.000Z", out=500))
        got, rows = self.rows("week")
        self.assertEqual(rows, [("2026-W53", 2), ("2027-W01", 1)])
        self.assertEqual([r["label"] for r in got["groups"]], ["2026-W53", "2027-W01"])
        self.assertAlmostEqual(sum(r["total_usd"] for r in got["groups"]), got["total_usd"],
                               places=9)
        self.assertEqual(self.table("week"), ["2026-W53", "2027-W01"])
        self.assertEqual(self.rows("month")[1], [("2026-12", 1), ("2027-01", 2)])


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
            return ANTHROPIC_PAGE
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


class TestMenuBarFailure(Base):
    def test_a_failed_read_shows_a_hyphen(self):
        """The menu bar's title after a failed read was two spaces and an en
        dash, the last dash character in the project. It is a hyphen; what went
        wrong is still in the tooltip and the menu."""
        swift = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "costbar", "main.swift"),
                      encoding="utf-8")
        failed = swift[swift.index("if let err = snap.failed {"):]
        failed = failed[:failed.index("} else {")]
        self.assertIn('item.button?.title = "  -"', failed)
        self.assertIn("item.button?.toolTip = err", failed)
        self.assertIn('add(menu, "Could not read usage: \\(err)")', swift)
        for dash in (chr(0x2013), chr(0x2014)):
            self.assertNotIn(dash, swift)


class TestInstallerSystemPython(Base):
    """install.sh is never run by the tests. Its check of the Python the menu
    bar runs is cut out of it and run in bash under set -e, with stand-ins for
    that Python and for xcode-select."""

    def installer(self):
        return slurp(os.path.join(os.path.dirname(FIXTURES), "..", "install.sh"),
                     encoding="utf-8")

    def stand_in(self, version=None, fails=False):
        """A stand-in for /usr/bin/python3 that leaves a mark when run: this
        Python, reporting `version` when one is given, or a developer tools
        stub that only fails."""
        path, mark = os.path.join(self.tmp, "python3"), os.path.join(self.tmp, "ran")
        lines = ["#!/bin/sh", "touch %s" % shlex.quote(mark)]
        if fails:
            lines += ["echo 'xcode-select: note: No developer tools were found' >&2", "exit 1"]
        elif version:
            fake = os.path.join(self.tmp, "old.py")
            with open(fake, "w") as f:
                f.write("import sys\nsys.version_info = %r\nsys.version = %r\nexec(sys.argv[2])\n"
                        % (version, "%d.%d.%d (stand-in)" % version))
            lines.append('exec %s %s "$@"' % (shlex.quote(sys.executable), shlex.quote(fake)))
        else:
            lines.append('exec %s "$@"' % shlex.quote(sys.executable))
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(path, 0o755)
        return path, mark

    def run_check(self, python, tools=True):
        """(exit status, output) of the check, with xcode-select answering as
        if the developer tools were installed or not."""
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("no bash")
        script = self.installer()
        say = re.search(r"^say\(\) \{.*\}$", script, re.M).group(0)
        start = script.index('if [ -x "$SYSTEM_PYTHON" ]')
        check = script[start:script.index("\n# 2.", start)]
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        tool = os.path.join(bin_dir, "xcode-select")
        with open(tool, "w") as f:
            f.write("#!/bin/sh\nexit %d\n" % (0 if tools else 2))
        os.chmod(tool, 0o755)
        env = {"PATH": bin_dir + os.pathsep + "/usr/bin:/bin", "SYSTEM_PYTHON": python}
        done = subprocess.run([bash, "-c", "set -e\n%s\n%s\necho finished\n" % (say, check)],
                              env=env, capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout

    def test_an_old_system_python_is_a_warning_not_a_failure(self):
        """The menu bar app runs /usr/bin/python3, but install.sh checked only
        the python3 on PATH, so a Mac whose /usr/bin/python3 was 3.8 installed
        cleanly and its menu bar could not run the engine. It now warns, names
        the fix and carries on."""
        python, mark = self.stand_in(version=(3, 8, 9))
        status, out = self.run_check(python)
        self.assertEqual(status, 0)
        self.assertTrue(os.path.exists(mark))
        self.assertIn("warning: the menu bar app runs %s, which is 3.8.9; it needs 3.9 or later."
                      % python, out)
        self.assertIn("softwareupdate --list, or xcode-select --install", out)
        self.assertTrue(out.endswith("finished\n"))

    def test_a_current_or_unusable_system_python_says_nothing(self):
        """No warning for 3.9 or later, for a stub that cannot run, for a
        missing path, or without developer tools, when the path is not run at
        all because it would only offer to install them. None stops the
        install."""
        for name, version, fails, tools, runs in (
                ("this python", None, False, True, True),
                ("3.9.0", (3, 9, 0), False, True, True),
                ("a failing stub", None, True, True, True),
                ("no developer tools", (3, 8, 9), False, False, False)):
            with self.subTest(name):
                python, mark = self.stand_in(version=version, fails=fails)
                if os.path.exists(mark):
                    os.remove(mark)
                self.assertEqual(self.run_check(python, tools=tools), (0, "finished\n"))
                self.assertEqual(os.path.exists(mark), runs)
        self.assertEqual(self.run_check(os.path.join(self.tmp, "missing")), (0, "finished\n"))

    def test_it_checks_the_python_the_menu_bar_runs(self):
        swift = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "costbar", "main.swift"),
                      encoding="utf-8")
        path = re.search(r"^SYSTEM_PYTHON=(\S+)", self.installer(), re.M).group(1)
        self.assertIn('URL(fileURLWithPath: "%s")' % path, swift)
        self.assertNotIn("/usr/bin/python3", swift.replace('"%s"' % path, ""))


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

    def test_by_offers_every_grouping_the_tally_keeps(self):
        """--by's choices were a second, hand-copied list of the groupings
        _Tally builds. BY_CHOICES is the one list: every grouping of a single
        key, in _Tally's order, with the weeks and months summed from the
        days, and each one prints its table."""
        self.assertEqual(tuple(c for c in tm.BY_CHOICES if c not in tm.ROLLUPS),
                         tuple(g for g in tm._Tally().groups if "_" not in g))
        self.assertTrue(set(tm.ROLLUPS) <= set(tm.BY_CHOICES))
        self.write("a.jsonl", record("msg_1", out=1000))
        for choice in tm.BY_CHOICES:
            with self.subTest(by=choice):
                self.assertEqual(tm.build_parser().parse_args(["--by", choice]).by, choice)
                out = cli("--by", choice, "--no-ledger")
                self.assertIn("by harness" if choice == "source" else f"by {choice}", out)
        import contextlib, io
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            tm.build_parser().parse_args(["--by", "colour"])

    def test_the_label_says_what_the_run_covers(self):
        """report_label() builds every report's label from the parsed options:
        the window first, then the session, else "all time", then the project
        and today's rates. --until alone reads "until X", not "all time"."""
        def label(*argv, project="", session=""):
            return tm.report_label(tm.build_parser().parse_args(list(argv)), project, session)
        self.assertEqual(label(), "all time")
        self.assertEqual(label("--until", "2026-10-02"), "until 2026-10-02")
        self.assertEqual(label("--since", "7d"), "last 7d")
        self.assertEqual(label("--since", "2026-09-01", "--until", "2026-09-03"),
                         "2026-09-01 to 2026-09-03")
        self.assertEqual(label("--period", "lastmonth"), tm.period_label("lastmonth"))
        self.assertEqual(label(session="session abcdef12"), "session abcdef12")
        self.assertEqual(label("--since", "7d", session="session abcdef12"), "last 7d")
        project = "/Users/sam/code/app"
        self.assertEqual(label("--current-rates", project=project),
                         f"all time · {tm.project_name(project)} · at today's rates")

    def test_the_dashboard_is_written_and_opened(self):
        """--html had no test through the command line: it writes the page to
        the path given, says where, and asks the system to open it."""
        self.write("a.jsonl", record("msg_1", out=1000))
        out = os.path.join(self.tmp, "dash.html")
        with unittest.mock.patch.object(tm.subprocess, "run") as run, \
                unittest.mock.patch("sys.platform", "darwin"):
            printed = cli("--html", out, "--no-ledger")
        self.assertEqual(printed, f"wrote {out}\n")
        run.assert_called_once_with(["open", out], check=False)
        self.assertEqual(list(payload_of(slurp(out, encoding="utf-8"))["views"]), ["all"])

    def test_help_is_grouped_and_names_what_the_readme_uses(self):
        """--help printed the ledger's default with the username in it, gave
        --by no help, called --until's end nothing and --summary-json "today,
        week and all time". Its options now sit in named groups, the home folder
        is written as ~, every option the README's usage blocks use is in it,
        and its examples are commands the README shows."""
        import contextlib, io
        buf = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"COLUMNS": "200"}), as_a_new_run():
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as done:
                tm.main(["--help"])
        self.assertEqual(done.exception.code, 0)
        # Python 3.14 colours help written to a terminal.
        text = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())

        for title in ("About", "What to read", "Window", "Report", "Output",
                      "Prices and the ledger", "Examples"):
            self.assertIn("\n%s:\n" % title, text)
        self.assertNotIn("/Users/", text)
        home = os.path.expanduser("~").rstrip(os.sep)
        if home:
            self.assertNotIn(home + os.sep, text)
        self.assertIn("(default ~/.claude/cost-ledger.jsonl, or set TOKENMETER_LEDGER)", text)
        self.assertIn("--html [PATH]", text)
        self.assertIn("(default ~/Downloads/Tokenmeter.html)", text)
        self.assertIn("up to but not including", text)
        self.assertIn("today, the last 7 and 30 days, all time, models and notes", text)
        self.assertIn(", ".join(tm.BY_CHOICES[:-1]), text)

        readme = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "README.md"),
                       encoding="utf-8")
        commands = [line.split("#")[0].strip()
                    for block in re.findall(r"```bash\n(.*?)```", readme, re.S)
                    for line in block.splitlines() if re.match(r"tokenmeter( |$)", line)]
        options = {o for c in commands for o in re.findall(r"--[a-z][a-z-]*", c)}
        self.assertTrue({"--by", "--html", "--rebuild-ledger"} <= options, options)
        for option in sorted(options):
            with self.subTest(option=option):
                self.assertRegex(text, r"[\s\[]%s[\s\]]" % re.escape(option))
        examples = [re.split(r"\s{2,}", line.strip())[0]
                    for line in tm.HELP_EXAMPLES.splitlines() if line.startswith("  tokenmeter")]
        self.assertGreaterEqual(len(examples), 4)
        for example in examples:
            with self.subTest(example=example):
                self.assertIn(example, commands)

    def test_the_settings_table_names_every_variable(self):
        """README's Settings table left out TOKENMETER_PRICE_CACHE, which the
        engine read under its bare name. Every TOKENMETER_ variable now has a
        named constant, and the table has a row for each one."""
        readme = slurp(os.path.join(os.path.dirname(FIXTURES), "..", "README.md"),
                       encoding="utf-8")
        table = readme.split("## Settings", 1)[1].split("\n## ", 1)[0]
        names = {v for k, v in vars(tm).items() if k.endswith("_ENV") and isinstance(v, str)}
        self.assertIn("TOKENMETER_PRICE_CACHE", names)
        # The status line's own setting, read only there. Its source is read
        # rather than imported, because importing it sets up a run.
        statusline = slurp(os.path.join(os.path.dirname(tm.__file__), "statusline.py"),
                           encoding="utf-8")
        own = set(re.findall(r'^[A-Z_]+_ENV = "(TOKENMETER_[A-Z_]+)"$', statusline, re.M))
        self.assertEqual(own, {"TOKENMETER_STATUS_TOKENS"})
        names |= own
        for name in sorted(names):
            with self.subTest(name=name):
                self.assertIn("| `%s` |" % name, table)
        for source in (slurp(tm.__file__, encoding="utf-8"), statusline):
            for name in re.findall(r"TOKENMETER_[A-Z_]+", source):
                self.assertIn(name, names)


class TestOpeningTheDashboard(Base):
    """--html ran macOS's open on every platform, so a machine without it
    wrote the page and then ended in a FileNotFoundError traceback, and
    nothing could write the page without showing it. open_file() uses open on
    macOS and xdg-open elsewhere, says nothing more when there is neither,
    and --no-open opens nothing."""

    def setUp(self):
        super().setUp()
        self.write("a.jsonl", record("msg_1", out=1000))
        self.out = os.path.join(self.tmp, "dash.html")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)

    def never_run(self, *args, **kw):
        raise AssertionError("ran %r" % (args,))

    def test_no_open_writes_the_page_and_opens_nothing(self):
        for platform in ("darwin", "linux"):
            with self.subTest(platform=platform), \
                    unittest.mock.patch.object(tm.subprocess, "run", self.never_run), \
                    unittest.mock.patch("sys.platform", platform):
                os.makedirs(os.path.join(self.tmp, platform))
                out = os.path.join(self.tmp, platform, "dash.html")
                self.assertEqual(cli("--html", out, "--no-open", "--no-ledger"), f"wrote {out}\n")
                self.assertIn("</html>", slurp(out, encoding="utf-8"))

    def test_a_platform_with_no_opener_only_writes_the_page(self):
        """With PATH emptied there is no xdg-open to find, so nothing is run;
        on macOS, open is tried and cannot start. Either way the run ends
        with the one line saying where the page is."""
        with unittest.mock.patch.dict(os.environ, {"PATH": self.bin}):
            with unittest.mock.patch.object(tm.subprocess, "run", self.never_run), \
                    unittest.mock.patch("sys.platform", "linux"):
                self.assertEqual(cli("--html", self.out, "--no-ledger"), f"wrote {self.out}\n")
            os.remove(self.out)
            with unittest.mock.patch("sys.platform", "darwin"):
                self.assertEqual(cli("--html", self.out, "--no-ledger"), f"wrote {self.out}\n")
        self.assertTrue(os.path.isfile(self.out))
        failing = unittest.mock.Mock(side_effect=PermissionError("not allowed"))
        with unittest.mock.patch.object(tm.subprocess, "run", failing):
            tm.open_file(self.out)
        failing.assert_called_once()

    def test_xdg_open_is_used_where_there_is_one(self):
        opener = os.path.join(self.bin, "xdg-open")
        with open(opener, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(opener, 0o755)
        with unittest.mock.patch.dict(os.environ, {"PATH": self.bin}), \
                unittest.mock.patch.object(tm.subprocess, "run") as run, \
                unittest.mock.patch("sys.platform", "linux"):
            self.assertEqual(cli("--html", self.out, "--no-ledger"), f"wrote {self.out}\n")
        run.assert_called_once_with([opener, self.out], check=False)

    def test_the_default_is_downloads_else_the_current_folder(self):
        home = os.path.join(self.tmp, "home")
        here = os.path.join(self.tmp, "here")
        os.makedirs(here)
        with unittest.mock.patch.dict(os.environ, {"HOME": home}), \
                unittest.mock.patch("os.getcwd", return_value=here):
            self.assertEqual(tm.default_dashboard_path(), os.path.join(here, "Tokenmeter.html"))
            os.makedirs(os.path.join(home, "Downloads"))
            self.assertEqual(tm.default_dashboard_path(),
                             os.path.join(home, "Downloads", "Tokenmeter.html"))
            printed = cli("--html", "--no-open", "--no-ledger")
        self.assertEqual(printed, "wrote %s\n" % os.path.join(home, "Downloads", "Tokenmeter.html"))
        self.assertTrue(os.path.isfile(os.path.join(home, "Downloads", "Tokenmeter.html")))


class TestEmptyAndNoMatch(Base):
    """A first run gave the menu bar a bare $0.00; a --project, --session or
    --adapter that matched nothing said "nothing to price. Looked for:" and
    listed folders full of logs; and three messages sent the installed
    engine, which has no docs/ folder, to docs/import-format.md."""

    def lay_out_projects(self, n=7):
        """n Claude Code projects under /Users/sam/code, one call each, a day
        apart, the last the latest."""
        for i in range(n):
            folder = os.path.join(self.tmp, "projects", "-Users-sam-code-p%d" % i)
            os.makedirs(folder)
            with open(os.path.join(folder, "sess-%d.jsonl" % i), "w") as f:
                f.write(record("msg_%d" % i, out=100, ts="2026-09-%02dT12:00:00Z" % (i + 1)) + "\n")

    def refused(self, *argv):
        """The one message a run exits with."""
        with self.assertRaises(SystemExit) as e:
            cli(*argv)
        return str(e.exception.code)

    def test_a_first_run_tells_the_menu_bar_where_it_looked(self):
        notes = json.loads(cli("--summary-json"))["notes"]
        self.assertEqual(notes[0]["level"], "info")
        text = notes[0]["text"]
        self.assertTrue(text.startswith("Nothing to price yet. Looked for Claude Code transcripts in "
                                        + os.path.join(self.tmp, "projects")), text)
        self.assertIn("Codex sessions in " + os.path.join(self.tmp, "no-codex"), text)
        self.assertIn("Run tokenmeter --list-adapters", text)
        self.assertEqual(sum("Nothing to price yet" in n["text"] for n in notes), 1)
        # One call, from a log or from the ledger alone, and the note goes.
        path = self.write("a.jsonl", record("msg_1", out=100))
        self.assertNotIn("Nothing to price yet", cli("--summary-json"))
        os.remove(path)
        summary = json.loads(cli("--summary-json"))
        self.assertEqual(summary["all"]["calls"], 1)
        self.assertNotIn("Nothing to price yet", json.dumps(summary["notes"]))

    def test_a_project_that_matches_nothing_names_projects_that_do(self):
        self.lay_out_projects()
        with unittest.mock.patch.dict(os.environ, {"HOME": "/Users/sam"}):
            cli("--json")                         # every call now in the ledger too
            os.remove(os.path.join(self.tmp, "projects", "-Users-sam-code-p6", "sess-6.jsonl"))
            with_ledger = self.refused("--project", "zzz")
            without = self.refused("--project", "zzz", "--no-ledger")
            windowed = self.refused("--project", "zzz", "--since", "7d")
            here = self.refused("--project", ".", "--no-ledger")
        self.assertEqual(with_ledger.splitlines(), [
            "no calls match --project zzz",
            "Projects with calls, latest first: code-p6, code-p5, code-p4, code-p3, code-p2 "
            "(and 2 more; --by project lists them all)"])
        # Without the ledger, the swept project is gone from the list too.
        self.assertEqual(without.splitlines()[1],
                         "Projects with calls, latest first: code-p5, code-p4, code-p3, code-p2, "
                         "code-p1 (and 1 more; --by project lists them all)")
        self.assertEqual(windowed.splitlines()[0], "no calls match --project zzz")
        self.assertTrue(here.startswith("no calls match --project . ("), here)
        for message in (with_ledger, without, windowed, here):
            self.assertNotIn("nothing to price", message)

    def test_session_and_adapter_name_their_flag(self):
        self.lay_out_projects(2)
        self.assertEqual(self.refused("--session", "nosuch"), "no calls match --session nosuch")
        self.assertEqual(self.refused("--session", "nosuch", "--no-ledger"),
                         "no calls match --session nosuch")
        self.assertEqual(self.refused("--adapter", "codex"), "no calls match --adapter codex")
        self.assertEqual(self.refused("--adapter", "gemini-cli", "--project", "p1"),
                         "no calls match --project p1 --adapter gemini-cli")
        # A few projects, all listed, with nothing more to say.
        self.assertEqual(self.refused("--project", "zzz", "--no-ledger").splitlines()[1],
                         "Projects with calls, latest first: %s, %s" % (
                             tm.project_name("-Users-sam-code-p1"),
                             tm.project_name("-Users-sam-code-p0")))

    def test_a_window_with_nothing_in_it_is_still_a_report(self):
        """The filter matches; only the window is empty, so the report is
        printed at zero, as before."""
        self.lay_out_projects(2)
        out = cli("--project", "p1", "--until", "2026-01-01", "--no-ledger")
        self.assertIn("0 API calls", out)
        # Matched only by the ledger, its transcript swept.
        cli("--json")
        os.remove(os.path.join(self.tmp, "projects", "-Users-sam-code-p1", "sess-1.jsonl"))
        self.assertIn("0 API calls", cli("--project", "p1", "--until", "2026-01-01"))
        self.assertIn("no calls match --project p1",
                      self.refused("--project", "p1", "--until", "2026-01-01", "--no-ledger"))

    def test_nothing_anywhere_still_says_where_it_looked(self):
        for argv in ((), ("--project", "zzz"), ("--session", "nosuch"), ("--adapter", "codex")):
            with self.subTest(argv=argv):
                self.assertTrue(self.refused(*argv).startswith("nothing to price. Looked for:"))

    def test_the_import_format_is_linked_not_a_file_the_install_lacks(self):
        import contextlib, io
        url = "https://github.com/Adi-debug-source/tokenmeter/blob/main/docs/import-format.md"
        self.assertEqual(tm.IMPORT_FORMAT_URL, url)
        # The page it links to is in the repository, at the same path.
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(tm.__file__),
                                                    url.split("/blob/main/")[1])))
        buf = io.StringIO()
        with unittest.mock.patch.dict(os.environ, {"COLUMNS": "80"}), as_a_new_run(), \
                contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            tm.main(["--help"])
        help_text = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
        self.assertIn("  " + url + "\n", help_text)     # whole, on a line of its own
        self.assertIn("linked at the end of", help_text)
        for name, text in (("nothing_found", tm.nothing_found()),
                           ("list_adapters", cli("--list-adapters")), ("help", help_text)):
            with self.subTest(text=name):
                self.assertIn(url, text)
                self.assertEqual(text.count("docs/import-format.md"), text.count(url))


class TestTokenTotals(Base):
    """The report gave each kind of token a row of its own and never their
    sum, so the only token total anyone saw was one counted another way, by
    a tool that adds up every log line. Total tokens are now one definition,
    token_totals(): uncached input, cache writes, cache reads and output."""

    def report(self, *argv):
        return cli(*argv)

    def headline(self, text):
        lines = text.splitlines()
        money = next(i for i, line in enumerate(lines) if "API call" in line)
        return lines[money + 1]

    def test_the_total_is_the_four_kinds_with_thinking_inside_output(self):
        """Thinking is part of output, so adding it again would count it
        twice, and web searches are billed per request, not as tokens."""
        self.write("a.jsonl", record("msg_1", inp=10, out=1000, think=400, read=5000,
                                     w5=300, w1=200, searches=3))
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        got = tm.token_totals(overall["tokens"])
        self.assertEqual(got, {"input": 10, "cache_write": 500, "cache_read": 5000,
                               "output": 1000, "thinking": 400, "total": 6510, "fresh": 1510})
        self.assertEqual(list(got), ["input", "cache_write", "cache_read", "output",
                                     "thinking", "total", "fresh"])
        self.assertEqual(self.headline(self.report()), "  6.5k tokens   1 API call")
        # The dashboard's Tokens chart counts a day by the same definition.
        page = os.path.join(self.tmp, "d.html")
        tm.render_html(overall, groups, meta, unknown, "all time", page)
        days = payload_of(slurp(page, encoding="utf-8"))["views"]["all"]["days"]
        self.assertEqual([d["tokens"] for d in days], [6510])

    def test_three_partial_copies_of_a_streamed_reply_count_once(self):
        """A streamed reply is written once per content block, so one call
        leaves three usage lines; summed line by line they come to 16,172
        tokens, where the call itself is 6,160."""
        self.write("a.jsonl", record("msg_1", out=4, read=5000), record("msg_1", out=8, read=5000),
                   record("msg_1", out=1160, read=5000))
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(tm.token_totals(overall["tokens"])["total"], 6160)
        self.assertEqual(self.headline(self.report()), "  6.2k tokens   1 API call")

    def test_fresh_tokens_leave_out_the_cache_reads(self):
        """Cache reads are the context read again on every turn and most of
        any total, so the total alone read as that much new text."""
        self.write("a.jsonl", record("msg_1", inp=1000, out=4000, read=95000, w5=0))
        text = self.report()
        lines = text.splitlines()
        at = lines.index(self.headline(text))
        self.assertEqual(lines[at], "  100.0k tokens   1 API call")
        self.assertEqual(lines[at + 1], "  of which fresh (excluding cache reads): 5.0k")
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        got = tm.token_totals(overall["tokens"])
        self.assertEqual(got["fresh"], got["total"] - got["cache_read"])
        # A window with nothing in it says nothing of fresh tokens.
        empty = cli("--no-ledger", "--until", "2026-01-01")
        self.assertIn("  0 tokens   0 API calls", empty)
        self.assertNotIn("fresh", empty)

    def test_every_grouping_and_the_sessions_list_give_tokens(self):
        """--by and --sessions gave each row its cost and calls but not its
        tokens. Each grouping is checked, not assumed: every row carries its
        total tokens, in one column."""
        self.write("sess-a.jsonl", record("a1", ts="2026-09-01T12:00:00.000Z", out=1000, read=5000),
                   record("a2", model="claude-sonnet-5", ts="2026-09-02T09:00:00.000Z",
                          out=20000, w5=300))
        self.write("sess-b.jsonl", record("b1", ts="2026-09-09T18:00:00.000Z", inp=40, out=500))
        _, groups, *_ = tm.collect(tm.transcripts(), ledger=False)

        def table(text, head):
            rows = text.split(head + "\n", 1)[1].split("\n\n", 1)[0].splitlines()
            self.assertEqual(len({row.index(" tokens") for row in rows}), 1, rows)
            return rows

        for by in tm.BY_CHOICES:
            with self.subTest(by=by):
                rows = table(cli("--by", by), "by harness" if by == "source" else f"by {by}")
                want = [tm.toks(tm.token_totals(v["tokens"])["total"]) for _, v in tm.grouped(groups, by)]
                self.assertEqual(len(rows), len(want))
                for row, shown in zip(rows, want):
                    self.assertRegex(row, rf" {re.escape(shown)} tokens ")
        rows = table(cli("--sessions"), "sessions, dearest first")
        self.assertEqual([row.split()[1] for row in rows], ["26.3k", "540"])

    def test_a_total_reads_as_the_rows_for_each_kind_do(self):
        """999, then 1.0k, 1.00M and 1.00B, as toks() writes the rows for
        each kind."""
        self.assertEqual([tm.toks(n) for n in (999, 1000, 1_000_000, 1_000_000_000)],
                         ["999", "1.0k", "1.00M", "1.00B"])
        for out, shown in ((999, "999"), (1000, "1.0k"), (1_000_000, "1.00M"),
                           (1_000_000_000, "1.00B")):
            with self.subTest(out=out):
                self.write("a.jsonl", record("msg_1", out=out))
                text = self.report()
                self.assertEqual(self.headline(text), f"  {shown} tokens   1 API call")
                self.assertRegex(text, rf"\n    output +{re.escape(shown)} ")


class TestPlainOutput(Base):
    """The report always carried colour codes, so a pipe, a file and Claude
    Code's /tokenmeter, which reads the output as text, got escape sequences
    among the figures. Only a terminal gets colour now; NO_COLOR turns it off,
    FORCE_COLOR or CLICOLOR_FORCE keep it in a pipe, and NO_COLOR wins."""

    COLOUR_VARS = ("NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE")

    def report(self, stdout=None, **env):
        """main() with these colour settings alone (the environment running
        the tests may set any of them), printing into stdout, a pipe-like
        StringIO unless a test gives another."""
        import contextlib, io
        self.write("a.jsonl", record("msg_1", out=1000, read=5000))
        clean = {k: v for k, v in os.environ.items() if k not in self.COLOUR_VARS}
        clean.update(env)
        buf = io.StringIO() if stdout is None else stdout
        with unittest.mock.patch.dict(os.environ, clean, clear=True), as_a_new_run():
            with contextlib.redirect_stdout(buf):
                tm.main(["--no-ledger", "--currency", "USD", "--by", "model", "--sessions"])
        return buf.getvalue()

    def test_a_pipe_gets_plain_text(self):
        out = self.report()
        self.assertIn("1 API call", out)
        self.assertNotIn("\x1b", out)
        for var in ("FORCE_COLOR", "CLICOLOR_FORCE"):
            for value in ("", "0"):
                with self.subTest(**{var: value}):
                    self.assertNotIn("\x1b", self.report(**{var: value}))

    def test_a_terminal_gets_colour(self):
        import io

        class Terminal(io.StringIO):
            def isatty(self):
                return True
        self.assertIn("\x1b[1m", self.report(stdout=Terminal()))
        self.assertNotIn("\x1b", self.report(stdout=Terminal(), NO_COLOR="1"))

    def test_force_color_keeps_it_in_a_pipe(self):
        for var in ("FORCE_COLOR", "CLICOLOR_FORCE"):
            with self.subTest(var=var):
                out = self.report(**{var: "1"})
                self.assertIn("\x1b[1m", out)
                # The same report, colour aside.
                self.assertEqual(re.sub(r"\x1b\[[0-9;]*m", "", out), self.report())

    def test_no_color_wins(self):
        self.assertNotIn("\x1b", self.report(NO_COLOR="1", FORCE_COLOR="1"))
        self.assertNotIn("\x1b", self.report(NO_COLOR="1", CLICOLOR_FORCE="1"))
        # Set but empty is not set, as https://no-color.org has it.
        self.assertIn("\x1b[1m", self.report(NO_COLOR="", FORCE_COLOR="1"))

    def test_the_next_run_and_the_functions_have_it_back(self):
        """Blanked for one run, the codes come back with reset_run(), so a
        function called on its own still writes them."""
        import contextlib, io
        self.report()
        self.assertEqual(tm.BOLD, "")
        tm.reset_run()
        self.assertEqual((tm.BOLD, tm.DIM, tm.RESET, tm.CYAN, tm.GREEN, tm.YELLOW),
                         tm.COLOUR_CODES)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tm.print_report(*tm.collect(tm.transcripts(), ledger=False), "", "all time")
        self.assertIn("\x1b[1m", buf.getvalue())


class TestJson(Base):
    """--json printed the same seven keys whatever was asked: no window, no
    covered line, no notes, and nothing of --by or --sessions, so a script
    had to read the terminal's text for them. The seven keep their values,
    and everything else is added after them."""

    OLD = ["total_usd", "total_display", "currency", "calls", "components", "tokens", "label"]

    def setUp(self):
        super().setUp()
        self.write("sess-a.jsonl", record("a1", ts="2026-09-01T12:00:00.000Z", out=1000, read=5000),
                   record("a2", ts="2026-09-02T12:00:00.000Z", out=2000, w5=3000))
        self.write("sess-b.jsonl", record("b1", ts="2026-09-02T13:00:00.000Z", inp=500, out=300))
        self.write("sess-c.jsonl", record("c1", model="claude-opus-9",
                                          ts="2026-09-03T12:00:00.000Z", out=10))

    def run_json(self, *argv):
        return json.loads(cli("--json", "--no-ledger", *argv))

    def test_the_old_keys_keep_their_values(self):
        got = self.run_json()
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(list(got)[:len(self.OLD)], self.OLD)
        self.assertEqual(got["total_usd"], round(overall["total"], 6))
        self.assertEqual(got["total_display"], round(overall["total"], 6))
        self.assertEqual(got["currency"], "USD")
        self.assertEqual(got["calls"], 4)
        self.assertEqual(got["components"], {c: round(overall[c], 6) for c in tm.COMPONENTS})
        # The counts it always had, in their order, then total and fresh.
        self.assertEqual({k: got["tokens"][k] for k in overall["tokens"]}, overall["tokens"])
        self.assertEqual(list(got["tokens"]), list(overall["tokens"]) + ["total", "fresh"])
        self.assertEqual(got["label"], "all time")
        for argv in (["--by", "model"], ["--sessions"], ["--by", "day", "--sessions"]):
            with self.subTest(argv=argv):
                more = self.run_json(*argv)
                self.assertEqual({k: more[k] for k in self.OLD}, {k: got[k] for k in self.OLD})

    def test_it_says_what_the_terminal_says_around_the_totals(self):
        got = self.run_json()
        paths = tm.transcripts()
        overall, groups, _meta, unknown = tm.collect(paths, ledger=False)
        self.assertEqual(got["version"], tm.__version__)
        self.assertIsNone(got["since"])
        self.assertIsNone(got["until"])
        self.assertEqual(got["covered"], tm.covered_span(groups, paths))
        self.assertIn("3 transcripts", got["covered"])
        self.assertEqual(got["notes"], [{"level": level, "text": text}
                                        for level, text in tm.report_notes(groups, unknown)])
        self.assertIn("warn", [n["level"] for n in got["notes"]])
        self.assertEqual(got["unknown_models"], ["claude-opus-9"])
        self.assertEqual(got["without_cache_usd"],
                         round(tm.caching_summary(overall)["without_cache"], 6))
        self.assertGreater(got["without_cache_usd"], got["total_usd"])
        self.assertNotIn("groups", got)
        self.assertNotIn("sessions", got)

        got = self.run_json("--since", "2026-09-02T00:00Z", "--until", "2026-09-03T00:00+01:00")
        self.assertEqual(got["since"], "2026-09-02T00:00:00+00:00")
        self.assertEqual(got["until"], "2026-09-03T00:00:00+01:00")
        self.assertEqual(got["calls"], 2)
        got = self.run_json("--period", "lastmonth")
        self.assertEqual([got["since"], got["until"]],
                         [t.isoformat() for t in tm.period_range("lastmonth")])

    def test_by_sends_the_groups_in_the_terminals_order(self):
        other = os.path.join(self.tmp, "projects", "-other")
        os.makedirs(other)
        with open(os.path.join(other, "sess-d.jsonl"), "w") as f:
            f.write(record("d1", ts="2026-09-04T12:00:00.000Z", out=50000) + "\n")
        _, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        for by in tm.BY_CHOICES:
            with self.subTest(by=by):
                got = self.run_json("--by", by)
                rows = got["groups"]
                self.assertEqual([r["key"] for r in rows], [k for k, _ in tm.grouped(groups, by)])
                self.assertEqual([r["label"] for r in rows],
                                 [tm.display_name(by, r["key"]) for r in rows])
                self.assertEqual(list(rows[0]),
                                 ["key", "label", "total_usd", "calls", "components", "tokens"])
                self.assertAlmostEqual(sum(r["total_usd"] for r in rows), got["total_usd"],
                                       places=5)
                self.assertEqual(sum(r["calls"] for r in rows), got["calls"])
                for c in tm.COMPONENTS:
                    self.assertAlmostEqual(sum(r["components"][c] for r in rows),
                                           got["components"][c], places=5)
                for k in got["tokens"]:
                    self.assertEqual(sum(r["tokens"][k] for r in rows), got["tokens"][k])
                self.assertNotIn("sessions", got)
        # The same rows, in the same order, as the terminal's table.
        for by in ("project", "model", "day"):
            with self.subTest(terminal=by):
                text = cli("--by", by, "--no-ledger")
                table = text.split(f"by {by}\n", 1)[1].split("\n\n", 1)[0]
                self.assertEqual([line.split()[0] for line in table.splitlines()],
                                 [r["label"] for r in self.run_json("--by", by)["groups"]])
        self.assertEqual([r["label"] for r in self.run_json("--by", "project")["groups"]],
                         ["-other", "-proj"])

    def test_sessions_only_when_asked(self):
        for n in range(22):
            self.write(f"many-{n:02d}.jsonl",
                       record(f"m{n}", ts="2026-09-05T12:00:00.000Z", out=10000 * (n + 1)))
        self.assertNotIn("sessions", self.run_json())
        self.assertNotIn("sessions", self.run_json("--by", "model"))
        got = self.run_json("--sessions")
        self.assertNotIn("groups", got)
        rows = got["sessions"]
        _, groups, meta, _ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(len(rows), tm.SESSIONS_LISTED)
        self.assertEqual([r["id"] for r in rows],
                         [k for k, _ in tm.grouped(groups, "session")[:tm.SESSIONS_LISTED]])
        totals = [r["total_usd"] for r in rows]
        self.assertEqual(totals, sorted(totals, reverse=True))
        first = rows[0]
        self.assertEqual(list(first), ["id", "project", "last", "total_usd", "calls", "tokens"])
        self.assertEqual(first["id"], "many-21")
        self.assertEqual(first["project"], tm.project_name(meta["many-21"]["project"]))
        self.assertEqual(dt.datetime.fromisoformat(first["last"]),
                         dt.datetime(2026, 9, 5, 12, tzinfo=dt.timezone.utc))
        self.assertEqual((first["total_usd"], first["calls"]),
                         (round(groups["session"]["many-21"]["total"], 6), 1))
        self.assertEqual((first["tokens"]["total"], first["tokens"]["fresh"]), (220000, 220000))
        text = cli("--sessions", "--no-ledger")
        for r in rows:
            self.assertIn(r["id"][:8], text)


class TestRunState(Base):
    """A run's options and findings are module globals, and nothing put them
    back between runs in one process: the tests reset thirteen of them by
    hand and missed the rest, and main() reset none."""

    def test_a_run_without_the_ledger_reports_none(self):
        """A collect with ledger=False after one with the ledger printed the
        earlier run's "ledger holds 2, 1 of them no longer in any transcript"
        for a ledger it never read. Run after TestLedger's deletion test, the
        covered line of a test that never used the ledger read that way."""
        self.write("a.jsonl", record("msg_1", out=1000))
        self.write("b.jsonl", record("msg_2", out=2000))
        tm.collect(tm.transcripts(), ledger=True)
        os.remove(os.path.join(self.projects, "a.jsonl"))
        paths = tm.transcripts()
        _, groups, *_ = tm.collect(paths, ledger=True)
        self.assertIn("ledger holds 2, 1 of them no longer in any transcript",
                      tm.covered_span(groups, paths))
        _, groups, *_ = tm.collect(paths, ledger=False)
        self.assertNotIn("ledger", tm.covered_span(groups, paths))
        tm.collect(paths, ledger=True)
        list(tm.iter_events(paths, ledger=False))
        self.assertEqual(tm.LEDGER_STATE, tm.LEDGER_UNUSED)

    def test_reset_run_puts_every_value_back(self):
        """Base.setUp missed LEDGER_STATE, FETCHED_USED and importer.PROBLEMS,
        so one test's ledger figures, looked-up models and skipped import
        lines reached the next. Every value goes back, in the same object,
        because the status line and other scripts import them by name."""
        names = ("_ROOTS", "ADAPTER_ROOTS", "_ONLY", "_IMPORTS", "_OWNER", "_PROJECT",
                 "_SESSION", "_LEDGER", "CURRENT_RATES", "ONLINE_LOOKUP", "DISPLAY",
                 "LEDGER_STATE", "_PRICE_STATE", "LOOKUPS", "FETCHED_USED", "_FX_MEMO")
        same = {name: getattr(tm, name) for name in names}
        for offline, online in (("1", False), ("", True), ("0", True)):
            with self.subTest(offline=offline):
                tm._ROOTS[:] = ["/Users/sam/old-mac/projects"]
                tm.ADAPTER_ROOTS["codex"] = ["/Users/sam/.codex/sessions"]
                tm._ONLY[:] = ["codex"]
                tm._IMPORTS[:] = ["/Users/sam/trial.jsonl"]
                tm._OWNER["/Users/sam/a.jsonl"] = "codex"
                tm._PROJECT[:] = ["app"]
                tm._SESSION[:] = ["abc"]
                tm._LEDGER[:] = ["/Users/sam/ledger.jsonl"]
                tm.CURRENT_RATES.append(True)
                tm.ONLINE_LOOKUP[0] = not online
                tm.DISPLAY.update(code="GBP", symbol="\u00a3", rate=0.5, when="cached", live=False)
                tm.LEDGER_STATE.update(written=1, restored=2, rows=3, used=True)
                tm._PRICE_STATE.update(loaded=True, data={"fetched": {"openai:x": {}}, "misses": {}})
                tm.LOOKUPS.append({"provider": "openai", "model": "x", "found": False})
                tm.FETCHED_USED[("openai", "x")] = "LiteLLM"
                tm._FX_MEMO.append(({"USD": 1.0}, "cached", False))
                tm.importer.PROBLEMS["/Users/sam/trial.jsonl"] = {"skipped": 1, "examples": []}
                tm.codex._STATE["guessed"].add("call")
                tm.codex._STATE["compressed_unread"] = 2
                tm.set_colour(False)
                with unittest.mock.patch.dict(os.environ, {tm.OFFLINE_ENV: offline}):
                    tm.reset_run()
                for name in names:
                    self.assertIs(getattr(tm, name), same[name], name)
                for box in (tm._ROOTS, tm.ADAPTER_ROOTS, tm._ONLY, tm._IMPORTS, tm._OWNER,
                            tm._PROJECT, tm._SESSION, tm._LEDGER, tm.CURRENT_RATES, tm.LOOKUPS,
                            tm.FETCHED_USED, tm._FX_MEMO, tm.importer.PROBLEMS):
                    self.assertFalse(box, box)
                self.assertEqual(tm.ONLINE_LOOKUP, [online])
                self.assertEqual(tm.DISPLAY, {"code": "USD", "symbol": "$", "rate": 1.0,
                                              "when": "", "live": True})
                self.assertEqual(tm.LEDGER_STATE, {"written": 0, "restored": 0, "rows": 0,
                                                   "used": False})
                self.assertEqual(tm._PRICE_STATE, {"loaded": False,
                                                   "data": {"fetched": {}, "misses": {}}})
                self.assertEqual(tm.codex._STATE, {"guessed": set(), "compressed_unread": 0,
                                                   "compressed_damaged": 0})
                self.assertEqual((tm.BOLD, tm.DIM, tm.RESET, tm.CYAN, tm.GREEN, tm.YELLOW),
                                 tm.COLOUR_CODES)

    def test_each_command_line_run_starts_afresh(self):
        """main() set these only from the options it was given, so in one
        process a run's --import and --session carried on into the next, and
        the tests' cli() cleared them by hand."""
        self.write("sess-a.jsonl", record("a1", out=100))
        self.write("sess-b.jsonl", record("b1", out=100))
        trial = os.path.join(self.tmp, "trial.jsonl")
        with open(trial, "w") as f:
            f.write(json.dumps(GOOD_IMPORT) + "\n")

        def calls(*argv):
            return json.loads(cli("--json", "--no-ledger", *argv))["calls"]
        self.assertEqual(calls("--import", trial), 3)
        self.assertEqual(calls(), 2)
        self.assertEqual(calls("--session", "sess-a"), 1)
        self.assertEqual(calls(), 2)
        cli("--json")
        self.assertIn("ledger holds 2", cli())
        self.assertNotIn("ledger", cli("--no-ledger"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
