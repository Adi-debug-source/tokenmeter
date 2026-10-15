"""The ledger and de-duplication: each call counted once, kept after its
transcript is swept, never rewritten, and never lost by a rebuild.
"""

import datetime as dt
import json
import os
import unittest

from helpers import GOOD_IMPORT, Base, cli, cost_of, record, slurp, tm, usage


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
        tm.append_ledger([tm.usage_to_row("m", None, "claude-opus-5", "p", "s", usage(out=4))])
        tm.append_ledger([tm.usage_to_row("m", None, "claude-opus-5", "p", "s", usage(out=1160))])
        got = tm.read_ledger(self.ledger)
        self.assertEqual(got["m"]["o"], 1160)


class TestCacheWrites(Base):
    """A usage block's cache writes were read three ways: price_record() took
    the lifetime breakdown, else the total when both parts were zero;
    usage_to_row() the breakdown, else the total only when it was missing; and
    usage_size() the total first. A block whose breakdown disagreed with its
    total was charged one figure, stored in the ledger as another and sized as
    a third, and because it then looked larger than its ledger row it was
    written to the ledger again on every run."""

    BLOCKS = (
        # A zero breakdown beside a total: charged, but stored as nothing.
        ({"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 1000,
          "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}},
         (1000, 0)),
        # A breakdown short of the total: the breakdown is what was billed.
        ({"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 1000,
          "cache_creation": {"ephemeral_5m_input_tokens": 300, "ephemeral_1h_input_tokens": 200}},
         (300, 200)),
        # The total alone, as older records send it.
        ({"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 1000},
         (1000, 0)),
    )

    def test_pricing_the_ledger_and_sizing_read_writes_alike(self):
        for u, (w5, w1) in self.BLOCKS:
            with self.subTest(usage=u):
                self.assertEqual(tm.cache_writes(u), (w5, w1))
                c = tm.price_record("claude-opus-5", u)
                self.assertEqual(c["_tokens"]["cache_write"], w5 + w1)
                self.assertAlmostEqual(c["cache_write"], (w5 * 1.25 + w1 * 2.0) * 5.0 / 1e6, places=12)
                row = tm.usage_to_row("m", None, "claude-opus-5", "p", "s", u)
                self.assertEqual((row.get("w5", 0), row.get("w1", 0)), (w5, w1))
                self.assertEqual(tm.usage_size(u), tm.row_size(row))

    def test_a_call_is_written_to_the_ledger_once(self):
        for i, (u, _) in enumerate(self.BLOCKS):
            self.write(f"s{i}.jsonl", json.dumps(
                {"type": "assistant", "timestamp": "2026-09-01T12:00:00.000Z", "uuid": f"m{i}",
                 "requestId": f"m{i}", "cwd": "/tmp",
                 "message": {"id": f"m{i}", "model": "claude-opus-5", "usage": u}}))
        for _ in range(3):
            tm.collect(tm.transcripts(), ledger=True)
        self.assertEqual(len(slurp(self.ledger).splitlines()), len(self.BLOCKS))

    def test_a_rows_own_write_prices_come_before_the_tables(self):
        """The rule was written out three times: in pricing, in --check-prices
        and in the price list. All three now ask write_mults()."""
        anthropic, moonshot = tm.TABLES["anthropic"], tm.TABLES["moonshot"]
        self.assertEqual(tm.write_mults({}, anthropic), (1.25, 2.0))
        self.assertEqual(tm.write_mults({"write_mult": 1.5}, anthropic), (1.5, 1.5))
        self.assertEqual(tm.write_mults({"write_mult": 1.0, "write_1h_mult": 2.0}, moonshot),
                         (1.0, 2.0))
        for provider, table in tm.TABLES.items():
            for model, rows in table.PRICES.items():
                with self.subTest(model=model):
                    row = tm.rate_on(rows)
                    m5, m1 = tm.write_mults(row, table)
                    exp = tm.expected_rates(row, table)
                    self.assertEqual((exp["write_5m"], exp["write_1h"]),
                                     (row["in"] * m5, row["in"] * m1))
                    c = tm.price_record(model, usage(w5=1000, w1=1000), provider=provider)
                    self.assertEqual(c["cache_write"], (1000 * m5 + 1000 * m1) * row["in"] / 1e6)


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
            f.write(json.dumps(GOOD_IMPORT) + "\n")
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


class TestKeptAndOnDisk(Base):
    """Deleting a session deletes its transcript, so a total read from the
    transcripts goes down. The ledger keeps every call, and the report now
    says so in tokens: what it keeps, what is on disk now, and what only the
    ledger still has."""

    def setUp(self):
        super().setUp()
        self.write("sess-a.jsonl", record("a1", ts="2026-09-01T12:00:00.000Z", out=1000, read=4000))
        self.write("sess-b.jsonl", record("b1", ts="2026-09-02T12:00:00.000Z", out=2000, read=8000),
                   record("b2", ts="2026-09-03T12:00:00.000Z", out=500, read=1500))
        self.before = cli()                               # every call now in the ledger
        os.remove(os.path.join(self.projects, "sess-b.jsonl"))

    @staticmethod
    def line(text, start):
        found = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(start)]
        return found[0] if found else None

    def test_a_deleted_session_is_kept_and_no_longer_on_disk(self):
        """A ledger row with no transcript counts as kept and as ledger only,
        never as on disk. The deletion lowers the on-disk figure and leaves
        the kept one, and the headline, where they were."""
        self.assertEqual(self.line(self.before, "kept by"),
                         "kept by the ledger 17.0k · on disk now 17.0k")
        after = cli()
        self.assertEqual(self.line(after, "kept by"),
                         "kept by the ledger 17.0k · on disk now 5.0k"
                         " · 12.0k from 1 session whose transcripts are gone")
        self.assertEqual(self.line(after, "17.0k tokens"), "17.0k tokens   3 API calls")
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=True)
        self.assertEqual(tm.kept_and_on_disk(overall, groups),
                         {"kept": 17000, "on_disk": 5000, "ledger_only": 12000, "sessions": 1})

    def test_it_counts_the_calls_the_covered_line_calls_gone(self):
        """One test decides both lines, so the calls "no longer in any
        transcript" are exactly the calls whose tokens are ledger only."""
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=True)
        gone = sum(row["calls"] for row in groups["ledger_only"].values())
        self.assertEqual(gone, tm.LEDGER_STATE["restored"])
        self.assertEqual(gone, 2)
        self.assertIn("ledger holds 3, 2 of them no longer in any transcript", cli())

    def test_json_sends_the_same_split(self):
        got = json.loads(cli("--json"))
        self.assertEqual((got["tokens"]["total"], got["tokens_on_disk"], got["tokens_ledger_only"]),
                         (17000, 5000, 12000))
        got = json.loads(cli("--json", "--no-ledger"))
        self.assertEqual((got["tokens"]["total"], got["tokens_on_disk"], got["tokens_ledger_only"]),
                         (5000, 5000, 0))
        # Added after every key that was there before, the groups and sessions too.
        got = json.loads(cli("--json", "--by", "model", "--sessions"))
        self.assertEqual(list(got)[-4:], ["groups", "sessions", "tokens_on_disk", "tokens_ledger_only"])

    def test_without_the_ledger_it_counts_whats_on_disk_and_says_so(self):
        text = cli("--no-ledger")
        self.assertEqual(self.line(text, "5.0k tokens"),
                         "5.0k tokens   1 API call · transcripts on disk only")
        self.assertIsNone(self.line(text, "kept by"))
        self.assertNotIn("ledger", text)
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(tm.kept_and_on_disk(overall, groups),
                         {"kept": 5000, "on_disk": 5000, "ledger_only": 0, "sessions": 0})

    def test_filters_apply_to_all_three_as_to_the_money(self):
        self.assertEqual(self.line(cli("--since", "2026-09-02"), "kept by"),
                         "kept by the ledger 12.0k · on disk now 0"
                         " · 12.0k from 1 session whose transcripts are gone")
        self.assertEqual(self.line(cli("--until", "2026-09-02"), "kept by"),
                         "kept by the ledger 5.0k · on disk now 5.0k")
        self.assertEqual(self.line(cli("--session", "sess-b"), "kept by"),
                         "kept by the ledger 12.0k · on disk now 0"
                         " · 12.0k from 1 session whose transcripts are gone")
        self.assertEqual(self.line(cli("--session", "sess-a"), "kept by"),
                         "kept by the ledger 5.0k · on disk now 5.0k")
        self.assertEqual(self.line(cli("--project", "proj"), "kept by"),
                         "kept by the ledger 17.0k · on disk now 5.0k"
                         " · 12.0k from 1 session whose transcripts are gone")
        # A window with nothing in it has nothing kept to speak of.
        self.assertIsNone(self.line(cli("--until", "2026-01-01"), "kept by"))

    def test_a_call_with_no_session_is_named_without_one(self):
        """An imported call can carry no session, and "from 0 sessions" would
        read as nothing gone."""
        when = dt.datetime(2026, 9, 4, 12, tzinfo=dt.timezone.utc)
        tm._LEDGER[:] = [os.path.join(self.tmp, "other-ledger.jsonl")]
        tm.append_ledger([tm.usage_to_row("c1", when, "claude-opus-5", "-proj", "",
                                          usage(out=700))])
        overall, groups, *_ = tm.collect([], ledger=True)
        split = tm.kept_and_on_disk(overall, groups)
        self.assertEqual(split, {"kept": 700, "on_disk": 0, "ledger_only": 700, "sessions": 0})
        self.assertEqual(tm.kept_line(split),
                         "kept by the ledger 700 · on disk now 0 · 700 no longer in any transcript")


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
            f.write(json.dumps(GOOD_IMPORT) + "\n")
        cli("--import", trial)                             # now in the ledger too
        os.remove(os.path.join(self.projects, "sess-a.jsonl"))
        with mock.patch.dict(os.environ, {"HOME": self.tmp}):
            out = cli("--rebuild-ledger")
        self.assertIn("ledger rebuilt: 1 call from 1 transcript\n", out)
        self.assertIn("previous ledger held 3 calls, kept at ~/ledger.jsonl.old\n", out)
        self.assertIn("2 calls were in the old ledger and in no transcript.", out)
        self.assertIn("Restore from ~/ledger.jsonl.old to get them back.", out)
        self.assertIn("1 of them was imported: rebuild with the same --import files", out)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
