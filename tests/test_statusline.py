"""The status line, run as Claude Code runs it, sealed in a temp folder: the
session and day totals it shows, its context window, and local midnight.
"""

import datetime as dt
import json
import os
import re
import shutil
import sys
import time
import unittest

from helpers import Base, as_a_new_run, cli, cost_of, record, slurp, tm


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
        # An agent's own transcript stands for its session.
        self.assertEqual(tm.claude_code.session_files(b), [main, a, b])
        overall, *_ = tm.collect([main, a, b], ledger=False)
        alone, *_ = tm.collect([main], ledger=False)
        cost, ctx = tm.session_totals(main)
        self.assertEqual(overall["calls"], 3)
        self.assertAlmostEqual(cost, overall["total"], places=12)
        self.assertGreater(cost, alone["total"])
        self.assertEqual(ctx, 1500)

    def test_a_path_with_no_agents_is_read_on_its_own(self):
        """A session that started no agents, or an agent whose session's
        transcript is no longer on disk, is one file, so its cost is what it
        was."""
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

    def test_it_keeps_its_colours_in_a_pipe(self):
        """The command line now prints plain text into a pipe. Claude Code
        reads the status line through one and renders its colours, so the
        status line keeps them."""
        path = self.write("sess.jsonl", record("msg_1", out=1000))
        done = self.run_statusline({"model": {"display_name": "Opus"}, "transcript_path": path})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("\x1b[", done.stdout)

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

    def test_without_the_token_setting_the_line_is_exactly_what_it_was(self):
        """Today's tokens are opt in. With TOKENMETER_STATUS_TOKENS unset,
        empty or 0 the line is byte for byte the one printed before the
        setting existed, colours included."""
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        path = self.write("sess.jsonl", record("msg_1", ts=now, inp=1000, out=500, read=20000))
        cost = tm.money(tm.session_totals(path)[0])
        R, D = "\x1b[0m", "\x1b[2m"
        want = (f"\x1b[1m\x1b[36mOpus{R} {D}│{R} ctx \x1b[32m  2%{R} {D}│{R} "
                f"\x1b[33m{cost}{R}{D} session{R} {D}│{R} {cost}{D} today{R}\n"
                f"\x1b[32m█{'░' * 29}{R} {D}21.0k / 1M · would-be API spend{R}")
        for setting in (None, "", "0", " 0 "):
            with self.subTest(setting=setting):
                shutil.rmtree(os.path.join(self.tmp, "statusline"), ignore_errors=True)
                env = {} if setting is None else {"TOKENMETER_STATUS_TOKENS": setting}
                done = self.run_statusline({"model": {"display_name": "Opus"},
                                            "transcript_path": path}, **env)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stdout, want)

    def test_with_the_token_setting_it_gives_todays_total_tokens(self):
        """TOKENMETER_STATUS_TOKENS=1 adds today's total tokens beside today's
        cost, by the engine's one definition: uncached input, cache writes,
        cache reads and output, thinking not added again. Yesterday's calls
        are not today's, wherever they were written."""
        now = dt.datetime.now(dt.timezone.utc)
        stamp = lambda t: t.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        path = self.write("sess.jsonl", record("msg_1", ts=stamp(now), inp=1000, out=500,
                                               read=200_000, w1=3000, think=100))
        self.write("other.jsonl", record("msg_2", ts=stamp(now), out=2500),
                   record("msg_3", ts=stamp(now - dt.timedelta(days=2)), out=9999))
        today_usd = sum(cost_of(ev["cost"])
                        for ev in tm.iter_events(tm.transcripts(), tm.local_midnight(dt.date.today()),
                                                 ledger=False, online=False))
        R, D = "\x1b[0m", "\x1b[2m"
        for setting in ("1", "yes"):
            with self.subTest(setting=setting):
                shutil.rmtree(os.path.join(self.tmp, "statusline"), ignore_errors=True)
                done = self.run_statusline({"model": {"display_name": "Opus"}, "transcript_path": path},
                                           TOKENMETER_STATUS_TOKENS=setting)
                self.assertEqual(done.returncode, 0, done.stderr)
                line1 = done.stdout.splitlines()[0]
                # 1,000 + 500 + 200,000 + 3,000 + 2,500 = 207,000
                self.assertTrue(line1.endswith(f" {tm.money(today_usd)}{D} · {R}207.0k{D} tok today{R}"),
                                line1)
                saved = json.loads(slurp(os.path.join(self.tmp, "statusline", ".today_cost.json")))
                self.assertEqual(saved["tokens"], 207_000)
        # A cache of today's figures is used for its 90 seconds; one written
        # before the tokens were kept is worked out again when they are asked
        # for, and still used when they are not.
        today = dt.date.today().isoformat()
        for cache, setting, want in (
                ({"day": today, "total": 999.0, "tokens": 1_234_567}, "1", "{saved}{D} · {R}1.23M{D} tok today"),
                ({"day": today, "total": 999.0}, "1", "{cost}{D} · {R}207.0k{D} tok today"),
                ({"day": today, "total": 999.0}, "", "{saved}{D} today")):
            with self.subTest(cache=cache, setting=setting):
                shutil.rmtree(os.path.join(self.tmp, "statusline"), ignore_errors=True)
                done = self.run_statusline({"model": {"display_name": "Opus"}, "transcript_path": path},
                                           day_cache=cache, TOKENMETER_STATUS_TOKENS=setting)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertTrue(done.stdout.splitlines()[0].endswith(
                    want.format(D=D, R=R, cost=tm.money(today_usd), saved=tm.money(999.0)) + R),
                    done.stdout)

    def test_the_command_line_names_where_a_bad_code_came_from(self):
        """A typo in TOKENMETER_CURRENCY read as if it had been typed on the
        command line, which had no --currency on it."""
        from unittest import mock
        self.write("a.jsonl", record("msg_1", out=10))
        with mock.patch.object(tm, "DEFAULT_CURRENCY", "GPB"), as_a_new_run():
            with self.assertRaises(SystemExit) as e:
                tm.main(["--json"])
        self.assertIn("unknown currency 'GPB' in TOKENMETER_CURRENCY; try one of",
                      str(e.exception.code))
        with self.assertRaises(SystemExit) as e:
            cli("--json", "--currency", "GPB")
        self.assertIn("unknown currency 'GPB'; try one of", str(e.exception.code))


if __name__ == "__main__":
    unittest.main(verbosity=2)
