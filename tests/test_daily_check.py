"""The daily price check: each provider's live pricing page reread at most
once a day, after the report is out, and the note that says when the page
last agreed with the table, or warns when it stopped agreeing.

Every table here is a fake built in the test, so nothing depends on the
figures in pricing/, and every fetch is faked: urlopen itself is refused
wherever a run could reach it.
"""

import contextlib
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import types
import unittest.mock

from helpers import Base, as_a_new_run, cli, record, slurp, tm

import test_statusline

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = dt.date.today()


def pretty(day):
    return day.strftime("%d %b %Y").lstrip("0")


def row(inp, out, cached=0.1, frm=""):
    return {"from": frm, "in": inp, "out": out, "cache_read_mult": cached, "fast": None}


def fake_table(key, name, prices, retired=None, verified=None, measured=False, reader=True):
    """A price table shaped as pricing/ shapes one, whose page is the JSON
    text its fetch returns for its SOURCE: {"rates": ..., "unlisted": ...}."""
    t = types.SimpleNamespace(
        NAME=name, SOURCE=f"https://pricing.example/{key}", MEASURED=measured,
        VERIFIED_ON=(verified or TODAY - dt.timedelta(days=10)).isoformat(),
        CACHE_WRITE_5M_MULT=1.25, CACHE_WRITE_1H_MULT=2.0, SNAPSHOT=r"-\d{8}$",
        PRICES=prices, RETIRED=retired or {})
    if reader:
        def page_rates(fetch, tables, want=None):
            page = json.loads(fetch(t.SOURCE))
            return page["rates"], page.get("unlisted", [])
        t.page_rates = page_rates
    return t


def page(rates, unlisted=()):
    return json.dumps({"rates": rates, "unlisted": list(unlisted)})


ALPHA = {"alpha-big": [row(3, 15)]}
ALPHA_PAGE = page({"alpha-big": {"in": 3, "out": 15, "cached": 0.3}})


class Pages(Base):
    """A run whose tables are the test's own fakes and whose fetch answers
    from self.pages (an exception there is raised), recording each address."""

    def setUp(self):
        super().setUp()
        self.pages = {}
        self.fetched = []
        tables = unittest.mock.patch.dict(tm.TABLES, {"alpha": fake_table("alpha", "Alphaco", ALPHA)},
                                          clear=True)
        tables.start()
        self.addCleanup(tables.stop)
        self.pages["https://pricing.example/alpha"] = ALPHA_PAGE

        def refuse(*args, **kw):
            raise AssertionError("urlopen was reached: a fetch that was not faked")
        net = unittest.mock.patch("urllib.request.urlopen", refuse)
        net.start()
        self.addCleanup(net.stop)

    def fetch(self, url):
        self.fetched.append(url)
        got = self.pages.get(url, OSError(f"no page at {url}"))
        if isinstance(got, Exception):
            raise got
        return got

    def state(self, provider="alpha"):
        with open(tm.PRICE_CACHE) as f:
            return json.load(f)[tm.DAILY_CHECK_KEY][provider]

    def note(self, provider="alpha"):
        tm._PRICE_STATE["loaded"] = False
        name = tm.TABLES[provider].NAME
        found = [n for n in tm.report_notes({"provider": {provider: {}}}, []) if name in n[1]]
        self.assertEqual(len(found), 1, found)
        return found[0]

    def save_state(self, **state):
        full = {"tried": "", "matched": "", "differs": [], "unlisted": [], "differs_since": "",
                "error": "", "failures": 0, "failing_since": ""}
        full.update(state)
        with open(tm.PRICE_CACHE, "w") as f:
            json.dump({"fetched": {}, "misses": {}, tm.DAILY_CHECK_KEY: {"alpha": full}}, f)
        tm._PRICE_STATE["loaded"] = False


class TestCheckPricesOutput(Pages):
    """--check-prices, now that its comparison is shared with the daily check."""

    def setUp(self):
        super().setUp()
        tm.TABLES.update({
            "beta": fake_table("beta", "Betaco", {
                "beta-one": [row(1, 5)], "beta-two": [row(2, 8)], "beta-gone": [row(1, 1)],
                "beta-dated": [row(1, 2), row(1.5, 3, frm="2026-06-01")]}),
            "gamma": fake_table("gamma", "Gammaco", {"gamma-one": [row(1, 2)]}),
            "delta": fake_table("delta", "Deltaco", {"delta-one": [row(1, 2)]}),
            "omega": fake_table("omega", "Omegaco", {"omega-one": [row(1, 2)]}, reader=False),
        })
        tm.TABLES["alpha"].PRICES = dict(ALPHA, **{"alpha-old": [row(2, 10)]})
        tm.TABLES["alpha"].RETIRED = {"alpha-old": "2026-01-01"}
        self.pages.update({
            "https://pricing.example/beta": page({
                "beta-one": {"in": 1, "out": 6, "cached": 0.1},
                "beta-two": {"in": 2, "out": 8, "cached": 0.2},
                "beta-dated": {"in": 1.5, "out": 3, "cached": 0.15, "_history": [
                    {"from": "", "in": 1, "out": 2, "cached": 0.1},
                    {"from": "2026-06-01", "in": 1.5, "out": 3, "cached": 0.15},
                    {"from": "2026-09-01", "in": 2, "out": 4}]}},
                unlisted=["beta-new"]),
            "https://pricing.example/gamma": OSError("no network"),
            "https://pricing.example/delta": page({}),
        })

    def run_check(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tm.check_prices(fetch=self.fetch)
        return code, buf.getvalue()

    # Printed by check_prices() before its comparison moved into
    # compare_with_page(), with these same tables and pages.
    BEFORE = (
        "\n  \x1b[1mChecking price tables against the published pages\x1b[0m\n"
        "\n  \x1b[1mAlphaco\x1b[0m  \x1b[2mhttps://pricing.example/alpha\x1b[0m\n"
        "    \x1b[32m1 of 1 models match\x1b[0m the page in every column it lists"
        " \x1b[2m(1 retired, kept at the last published price)\x1b[0m\n"
        "\n  \x1b[1mBetaco\x1b[0m  \x1b[2mhttps://pricing.example/beta\x1b[0m\n"
        "    \x1b[32m2 of 4 models match\x1b[0m the page in every column it lists\n"
        "    \x1b[33mdiffers\x1b[0m  beta-one out: table has $5, page says $6\n"
        "    \x1b[33mdiffers\x1b[0m  beta-dated from 2026-09-01 entry: table has nothing, page says $2\n"
        "    \x1b[2mnot found on the page: beta-gone\x1b[0m\n"
        "    \x1b[33mon the page but not in the table\x1b[0m: beta-new\n"
        "\n  \x1b[1mGammaco\x1b[0m  \x1b[2mhttps://pricing.example/gamma\x1b[0m\n"
        "    \x1b[33mcould not read the page\x1b[0m (OSError: no network).\n"
        "    \x1b[2mNothing was changed. Check by hand at https://pricing.example/gamma\x1b[0m\n"
        "\n  \x1b[1mDeltaco\x1b[0m  \x1b[2mhttps://pricing.example/delta\x1b[0m\n"
        "    \x1b[33mthe page was read but no rates were found in it\x1b[0m; its layout may "
        "have changed. Check by hand.\n"
        "\n  \x1b[1mOmegaco\x1b[0m  \x1b[2mhttps://pricing.example/omega\x1b[0m\n"
        "    \x1b[33mcould not read the page\x1b[0m (AttributeError: 'types.SimpleNamespace' "
        "object has no attribute 'page_rates').\n"
        "    \x1b[2mNothing was changed. Check by hand at https://pricing.example/omega\x1b[0m\n"
        "\n  \x1b[2mNothing was changed. A rate change is added as a new dated entry under "
        "pricing/, never by editing the old one.\x1b[0m\n\n")

    def test_its_output_is_unchanged_by_the_shared_comparison(self):
        """The daily check reuses --check-prices' comparison rather than a
        second copy, which is how six past bugs began. Moving that comparison
        into compare_with_page() must not change a character of what
        --check-prices prints, colours included, for a match with a retired
        model, a moved rate, a dated price the table lacks, a model missing
        from the page, one missing from the table, an unreadable page, an
        empty page and a table with no page reader; nor its exit status."""
        code, out = self.run_check()
        self.assertEqual(code, 2)
        self.assertEqual(out, self.BEFORE)

    def test_a_clean_check_exits_0_with_its_closing_line(self):
        """The all-clear path of the same output: exit 0 and the closing
        line that says nothing was touched."""
        for key in ("beta", "gamma", "delta", "omega"):
            del tm.TABLES[key]
        code, out = self.run_check()
        self.assertEqual(code, 0)
        self.assertIn("Everything matches. The tables were not touched.", out)

    def test_it_records_what_it_found_for_the_note(self):
        """The warning says "run --check-prices"; a check that then finds
        the page agreeing must clear it, or the warning would stand until the
        next day's check whatever --check-prices showed."""
        self.run_check()
        self.assertEqual(self.state("alpha")["matched"], TODAY.isoformat())
        beta = self.state("beta")
        self.assertEqual(beta["differs"], ["beta-dated", "beta-one"])
        self.assertEqual(beta["unlisted"], ["beta-new"])
        self.assertEqual(self.state("gamma")["error"], "OSError: no network")


class TestDailyCheck(Pages):
    """When the pages are read, and when they are not."""

    def setUp(self):
        super().setUp()
        tm.ONLINE_LOOKUP[0] = True
        real = tm.fetch_text
        tm.fetch_text = lambda url, timeout=20: self.fetch(url)
        self.addCleanup(setattr, tm, "fetch_text", real)

    def test_a_second_run_on_the_same_day_does_not_fetch(self):
        """The page is reread at most once a local day: a menu bar that runs
        every minute must not download every pricing page every minute. The
        second run, the same day, reads the date from the cache instead, and
        the note carries it."""
        cli("--summary-json")
        self.assertEqual(self.fetched, ["https://pricing.example/alpha"])
        cli("--summary-json")
        self.write("a.jsonl", record("msg_1", out=1000))
        self.pages["https://pricing.example/alpha"] = OSError("a lookup, not the daily check")
        cli("--json")
        cli()
        self.fetched = [u for u in self.fetched if u.startswith("https://pricing.example/")]
        self.assertEqual(self.fetched, ["https://pricing.example/alpha"])
        self.assertIn(f"live page matched {pretty(TODAY)}", self.note()[1])

    def test_the_next_day_reads_the_page_again(self):
        """Once a day, not once ever: an attempt dated yesterday is due."""
        self.save_state(tried=(TODAY - dt.timedelta(days=1)).isoformat(),
                        matched=(TODAY - dt.timedelta(days=1)).isoformat())
        cli("--summary-json")
        self.assertEqual(self.fetched, ["https://pricing.example/alpha"])
        self.assertEqual(self.state()["tried"], TODAY.isoformat())

    def test_the_report_is_written_before_any_page_is_read(self):
        """The check runs after the output, so a report is never held up by
        it: when the first page is asked for, the report is already printed."""
        self.write("a.jsonl", record("msg_1", out=1000))
        seen = []
        buf = io.StringIO()
        # The model's own table is not among the fakes, so the online lookup
        # asks for it while pricing; only the daily check reads this address.
        self.fetch = lambda url: (url == "https://pricing.example/alpha"
                                  and seen.append(buf.getvalue())) or ALPHA_PAGE
        with as_a_new_run(), contextlib.redirect_stdout(buf):
            tm.main(["--currency", "USD"])
        self.assertEqual(len(seen), 1)
        self.assertIn("1 API call", seen[0])
        self.assertIn("note:", seen[0])

    def test_a_page_that_never_answers_does_not_hold_the_run(self):
        """A hung connection would hold the menu bar's run, which waits for
        the process to end. The check gives up at its deadline, counts it as
        a failed read and returns."""
        gate = threading.Event()
        self.addCleanup(gate.set)

        def hang(url):
            gate.wait(30)
            return ALPHA_PAGE
        start = time.monotonic()
        tm.daily_price_check(fetch=hang, deadline=0.2)
        self.assertLess(time.monotonic() - start, 5)
        state = self.state()
        self.assertEqual(state["failures"], 1)
        self.assertIn("no answer within", state["error"])

    def test_a_table_with_no_page_reader_is_not_fetched(self):
        """Only tables pricing/ can read a page for are checked daily."""
        tm.TABLES["omega"] = fake_table("omega", "Omegaco", {"omega-one": [row(1, 2)]}, reader=False)
        checked = tm.daily_price_check(fetch=self.fetch)
        self.assertEqual(checked, ["alpha"])


class TestOffline(Pages):
    """--offline and TOKENMETER_OFFLINE=1 make no request at all."""

    def test_offline_makes_no_request(self):
        """With the lookup off the daily check returns before anything is
        fetched: the fetch fails the test if it is called, and so does
        urlopen, for every kind of report."""
        def forbidden(url, timeout=20):
            self.fail(f"fetched {url} while offline")
        real = tm.fetch_text
        tm.fetch_text = forbidden
        self.addCleanup(setattr, tm, "fetch_text", real)
        self.write("a.jsonl", record("msg_1", out=1000))
        for argv in ([], ["--json"], ["--summary-json"]):
            with unittest.mock.patch.dict(os.environ, {tm.OFFLINE_ENV: "1"}):
                tm.ONLINE_LOOKUP[0] = tm.online_by_default()
                cli(*argv)
            with unittest.mock.patch.dict(os.environ, {tm.OFFLINE_ENV: ""}):
                tm.ONLINE_LOOKUP[0] = tm.online_by_default()
                cli("--offline", *argv)
        self.assertEqual(tm.daily_price_check(fetch=forbidden), [])
        self.assertFalse(os.path.exists(tm.PRICE_CACHE))

    def run_engine(self, *argv, **env):
        """tokenmeter.py as its own process, sealed in the temp folder (a copy
        of the engine, so its exchange-rate file lands there too), through a
        wrapper that refuses every request and prints each address."""
        here = os.path.join(self.tmp, "engine")
        os.makedirs(here, exist_ok=True)
        shutil.copy(os.path.join(REPO, "tokenmeter.py"), here)
        with open(os.path.join(here, "counted.py"), "w") as f:
            f.write("import runpy, sys, urllib.request\n"
                    "def refuse(req, *args, **kw):\n"
                    "    sys.stderr.write('request: %s\\n' % getattr(req, 'full_url', req))\n"
                    "    raise OSError('no network in tests')\n"
                    "urllib.request.urlopen = refuse\n"
                    "sys.argv = sys.argv[1:]\n"
                    "runpy.run_path(sys.argv[0], run_name='__main__')\n")
        sealed = {k: v for k, v in os.environ.items()
                  if not k.startswith("TOKENMETER_")
                  and k not in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "XDG_DATA_HOME", "OPENCODE_DB")}
        sealed.update(HOME=self.tmp, PYTHONPATH=REPO,
                      TOKENMETER_CLAUDE_PROJECTS=os.path.join(self.tmp, "projects"),
                      TOKENMETER_LEDGER=self.ledger, TOKENMETER_PRICE_CACHE=tm.PRICE_CACHE,
                      TOKENMETER_CURRENCY="USD", CODEX_HOME=os.path.join(self.tmp, "no-codex"),
                      XDG_DATA_HOME=os.path.join(self.tmp, "no-xdg"))
        sealed.update(env)
        done = subprocess.run([sys.executable, os.path.join(here, "counted.py"),
                               os.path.join(here, "tokenmeter.py")] + list(argv),
                              capture_output=True, text=True, env=sealed, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return [u for u in re.findall(r"request: (\S+)", done.stderr) if u != tm.FX_URL]

    def test_a_real_process_offline_makes_no_request(self):
        """The same as a new process sees it, with the real tables: no page
        request with TOKENMETER_OFFLINE=1 or with --offline, while the same
        run online asks for the pages once and, the same day, not again."""
        self.write("a.jsonl", record("msg_1", out=1000))
        self.assertEqual(self.run_engine("--summary-json", TOKENMETER_OFFLINE="1"), [])
        self.assertEqual(self.run_engine("--offline", TOKENMETER_OFFLINE=""), [])
        self.assertFalse(os.path.exists(tm.PRICE_CACHE))
        self.assertTrue(self.run_engine("--summary-json", TOKENMETER_OFFLINE=""))
        self.assertEqual(self.run_engine("--json", TOKENMETER_OFFLINE=""), [])

    def test_the_status_line_does_not_fetch(self):
        """The status line runs on every prompt and must never wait on a
        page: online, with no check recorded yet today, it makes no request
        and leaves no daily-check state behind."""
        path = self.write("s.jsonl", record("msg_1", out=1000))
        done = test_statusline.TestStatusLine.run_statusline(
            self, {"model": {"display_name": "Opus"}, "transcript_path": path},
            counted=True, TOKENMETER_OFFLINE="")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("requests: 0", done.stderr)
        cache = os.path.join(self.tmp, "prices.json")
        if os.path.exists(cache):
            self.assertNotIn(tm.DAILY_CHECK_KEY, json.loads(slurp(cache)))


class TestTheNote(Pages):
    """What the note says in each state, with VERIFIED_ON's wording kept."""

    def base(self):
        return f"Alphaco rates checked {pretty(TODAY - dt.timedelta(days=10))} " \
               "(published rates, not yet checked against a real bill)"

    def setUp(self):
        super().setUp()
        tm.ONLINE_LOOKUP[0] = True

    def check(self, text):
        self.pages["https://pricing.example/alpha"] = text
        tm.daily_price_check(fetch=self.fetch)

    def test_no_check_yet_leaves_the_note_as_it_was(self):
        """Before any page is read, offline for instance, the note is the
        hand-checked date alone, worded as it always was."""
        self.assertEqual(self.note(), ("info", self.base()))

    def test_a_match_appends_the_live_date(self):
        """Two dates kept apart: VERIFIED_ON, the day a person read every
        figure, stays as it was, and the day the live page last agreed is
        added to the same note."""
        verified = tm.TABLES["alpha"].VERIFIED_ON
        self.check(ALPHA_PAGE)
        self.assertEqual(self.note(), ("info", f"{self.base()}; live page matched {pretty(TODAY)}"))
        self.assertEqual(tm.TABLES["alpha"].VERIFIED_ON, verified)

    def test_a_difference_warns_and_names_the_models(self):
        """A page that stopped agreeing must not leave a calm "matched" line
        standing: the note becomes a warning naming what differs and what the
        table lacks, and says to run --check-prices."""
        self.check(ALPHA_PAGE)
        self.check_tomorrow(page({"alpha-big": {"in": 4, "out": 15, "cached": 0.4}},
                                 unlisted=["alpha-new"]))
        level, text = self.note()
        self.assertEqual(level, "warn")
        self.assertTrue(text.startswith(self.base()), text)
        self.assertEqual(text, f"{self.base()}; since {pretty(TODAY)} the live page differs for "
                               "alpha-big and lists alpha-new, which the table lacks; "
                               "run --check-prices")
        self.assertNotIn("matched", text)

    def check_tomorrow(self, text):
        """A check on the next day: the last one's date moved back a day."""
        with open(tm.PRICE_CACHE) as f:
            data = json.load(f)
        data[tm.DAILY_CHECK_KEY]["alpha"]["tried"] = (TODAY - dt.timedelta(days=1)).isoformat()
        with open(tm.PRICE_CACHE, "w") as f:
            json.dump(data, f)
        tm._PRICE_STATE["loaded"] = False
        self.check(text)

    def test_one_failed_read_does_not_warn(self):
        """The threshold's lower edge: one failed fetch on a bad connection
        is not evidence the prices moved, so the note still gives the last
        match, calmly."""
        yesterday = TODAY - dt.timedelta(days=1)
        self.save_state(tried=yesterday.isoformat(), matched=yesterday.isoformat())
        self.check(OSError("timed out"))
        self.assertEqual(self.state()["failures"], 1)
        self.assertEqual(self.note(), ("info", f"{self.base()}; live page matched {pretty(yesterday)}"))

    def test_failed_reads_on_two_days_warn(self):
        """The threshold itself: the page unreadable on two daily attempts in
        a row warns, saying since when and to run --check-prices, and the
        calm line is gone."""
        last = TODAY - dt.timedelta(days=5)
        since = TODAY - dt.timedelta(days=1)
        self.save_state(tried=since.isoformat(), matched=last.isoformat(), failures=1,
                        failing_since=since.isoformat(), error="OSError: timed out")
        self.check(OSError("timed out"))
        level, text = self.note()
        self.assertEqual(level, "warn")
        self.assertTrue(text.startswith(self.base()), text)
        self.assertEqual(text, f"{self.base()}; live page last matched {pretty(last)}, but could "
                               f"not be read since {pretty(since)}; run --check-prices")

    def test_two_failures_on_one_day_count_once(self):
        """The threshold counts days, not attempts: a failed daily read and a
        failed --check-prices the same day are one bad day, not two."""
        self.check(OSError("timed out"))
        with contextlib.redirect_stdout(io.StringIO()):
            tm.check_prices(fetch=self.fetch)
        self.assertEqual(self.state()["failures"], 1)
        self.assertEqual(self.note()[0], "info")

    def test_a_good_read_clears_the_failures(self):
        """A page read again after failures starts the count afresh."""
        self.save_state(tried=(TODAY - dt.timedelta(days=1)).isoformat(), failures=3,
                        failing_since="2026-01-01", error="OSError: timed out")
        self.check(ALPHA_PAGE)
        state = self.state()
        self.assertEqual((state["failures"], state["failing_since"], state["error"]), (0, "", ""))
        self.assertEqual(self.note(), ("info", f"{self.base()}; live page matched {pretty(TODAY)}"))

    def test_a_stale_table_keeps_its_warning_and_gains_the_date(self):
        """VERIFIED_ON's stale warning keeps its wording; a live match does
        not hide that nobody has read the figures by hand for months."""
        tm.TABLES["alpha"].VERIFIED_ON = "2020-01-01"
        self.check(ALPHA_PAGE)
        level, text = self.note()
        self.assertEqual(level, "warn")
        self.assertIn("rates were last checked 1 Jan 2020", text)
        self.assertTrue(text.endswith(f"; live page matched {pretty(TODAY)}"), text)


class TestTheCacheFile(Pages):
    """The price cache keeps its shape: one new key, nothing else moved."""

    OLD = {"fetched": {"deepseek:deepseek-chat": {
        "rows": [{"from": "", "in": 0.28, "out": 0.42, "cache_read_mult": 0.1, "fast": None}],
        "via": "LiteLLM's public price list", "url": "https://example.com/list",
        "checked": "2026-10-01", "first": "2026-10-01"}},
        "misses": {"openai:gpt-nothing": 1.0}, "failed": {}}

    def test_an_older_cache_without_the_key_still_loads(self):
        """A cache written before the daily check has no page_checks key. It
        loads, its saved rates still price, the note is the plain one, and
        after a check every key it had is exactly as it was."""
        with open(tm.PRICE_CACHE, "w") as f:
            json.dump(self.OLD, f)
        self.assertEqual(tm.fetched_row("deepseek", "deepseek-chat")["in"], 0.28)
        self.assertEqual(self.note()[0], "info")
        self.assertNotIn("live page", self.note()[1])
        tm.ONLINE_LOOKUP[0] = True
        tm.daily_price_check(fetch=self.fetch)
        with open(tm.PRICE_CACHE) as f:
            after = json.load(f)
        self.assertEqual(set(after), set(self.OLD) | {tm.DAILY_CHECK_KEY})
        self.assertEqual({k: after[k] for k in self.OLD}, self.OLD)
        self.assertEqual(sorted(after[tm.DAILY_CHECK_KEY]["alpha"]),
                         sorted(["tried", "matched", "differs", "unlisted", "differs_since",
                                 "error", "failures", "failing_since"]))

    def test_a_damaged_state_is_ignored(self):
        """A hand-edited or half-written state must not end a report in a
        traceback: anything not shaped as expected reads as no check yet."""
        for bad in ("nonsense", {"alpha": "x"}, {"alpha": {"matched": "not a date"}},
                    {"alpha": {"differs": [1]}}, {"alpha": {"failures": True}}):
            with open(tm.PRICE_CACHE, "w") as f:
                json.dump(dict(self.OLD, **{tm.DAILY_CHECK_KEY: bad}), f)
            self.assertEqual(self.note()[0], "info")
            tm.ONLINE_LOOKUP[0] = True
            tm.daily_price_check(fetch=self.fetch)
            self.assertEqual(self.state()["matched"], TODAY.isoformat())


class TestJsonKeys(Pages):
    """--json and --summary-json only ever gain keys, appended."""

    JSON = ["total_usd", "total_display", "currency", "calls", "components", "tokens", "label",
            "version", "since", "until", "covered", "notes", "unknown_models",
            "without_cache_usd", "tokens_on_disk", "tokens_ledger_only"]
    GROUPED = JSON[:14] + ["groups", "sessions"] + JSON[14:]
    SUMMARY = ["today", "week", "month", "all", "models", "days", "tokens", "cache_hit_pct",
               "without_cache", "currencies", "currency_order", "rates", "rate_when",
               "rate_live", "no_cache_saved", "saved_pct", "multiple", "covered",
               "unknown_models", "notes", "sources", "multi", "harnesses", "providers",
               "unverified_share", "generated"]

    def test_the_keys_are_only_appended(self):
        """The menu bar and scripts read these by name and in order; the
        daily check reaches them through the notes and moves no key. The
        lists are the keys as they stood before it."""
        self.write("a.jsonl", record("msg_1", out=1000))
        tm.ONLINE_LOOKUP[0] = True
        real = tm.fetch_text
        tm.fetch_text = lambda url, timeout=20: self.fetch(url)
        self.addCleanup(setattr, tm, "fetch_text", real)
        for argv, want in ((["--json"], self.JSON),
                           (["--json", "--by", "model", "--sessions"], self.GROUPED),
                           (["--summary-json"], self.SUMMARY)):
            keys = list(json.loads(cli(*argv)))
            self.assertEqual(keys[:len(want)], want, argv)


if __name__ == "__main__":
    unittest.main(verbosity=2)
