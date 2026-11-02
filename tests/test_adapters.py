"""The adapters: each harness's logs read as its source writes them, from
the fixtures in tests/fixtures/, and the import format.
"""

import datetime as dt
import io
import json
import os
import shutil
import sqlite3
import sys
import unittest
import unittest.mock

from helpers import (FIXTURES, GOOD_IMPORT, Base, cli, cost_of, record, slurp, tm, usage,
                     zstd_compress)

from adapters import codex as codex_module
from adapters import gemini_cli, opencode
from adapters.common import parse_time


# The Codex reader rechecked against openai/codex at a098129 (1 November
# 2026). Since e72da2b, a response that ends incomplete has its usage added to
# the running total while the token_count that follows still carries the
# previous response as last_token_usage.
_CODEX_FIXTURE = "gen5_incomplete_response.jsonl"


def _codex_usage(inp, cached=0, written=0, out=0, reasoning=0):
    return {"input_tokens": inp, "cached_input_tokens": cached,
            "cache_write_input_tokens": written, "output_tokens": out,
            "reasoning_output_tokens": reasoning, "total_tokens": inp + out}


def _codex_count(total, last, at="2026-10-28T10:00:05.000Z"):
    return {"timestamp": at, "type": "event_msg",
            "payload": {"type": "token_count",
                        "info": {"total_token_usage": total, "last_token_usage": last,
                                 "model_context_window": 258400}, "rate_limits": None}}


def _codex_record(u, response="resp_1", at="2026-10-28T10:00:04.900Z"):
    return {"timestamp": at, "type": "token_usage_record",
            "payload": {"thread_id": "t1", "turn_id": "turn_1", "session_id": "t1",
                        "root_turn_id": "turn_1", "response_id": response, "usage": u,
                        "turn_token_usage": u, "thread_token_usage": u}}


def _codex_session(*lines, meta=None):
    head = [{"timestamp": "2026-10-28T10:00:00.000Z", "type": "session_meta",
             "payload": dict({"id": "t1", "session_id": "t1",
                              "cwd": "/Users/example/code/demo"}, **(meta or {}))},
            {"timestamp": "2026-10-28T10:00:00.100Z", "type": "turn_context",
             "payload": {"cwd": "/Users/example/code/demo", "model": "gpt-6.1-sol"}}]
    return head + list(lines)


def _codex_calls(path):
    tm.codex.reset()
    return list(tm.codex.records(path))


# Gemini CLI reader, rechecked against google-gemini/gemini-cli at 6814e00
# (30 October 2026). The reader was built from 2fe7c2d (25 September 2026); in
# between Gemini CLI began writing $patch lines and stopped writing the $set
# full-history checkpoint. The message records, and when tokens reach them,
# did not move. These tests pin the newer files to the per-call figures in
# tests/fixtures/gemini-cli/recheck-6814e00/expected.json.
_GEMINI_HERE = os.path.join(FIXTURES, "gemini-cli", "recheck-6814e00")
_GEMINI_MAIN = "session-2026-10-30T10-05-7c2e9d41.jsonl"
_GEMINI_MAIN_ID = "7c2e9d41-5b3a-4e8f-a1d2-0f6c9b8e7a35"
_GEMINI_SUB = os.path.join(_GEMINI_MAIN_ID, "0b6d2f84-4e1a-4c7b-9d3e-5f8a1c2b7e60.jsonl")
_GEMINI_COLLIDED = "session-2026-10-30T10-05-1-9a0b1c2d.jsonl"
_GEMINI_COLLIDED_ID = "9a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d"

# A Qwen Code session line, with the field names and nesting of ChatRecord in
# QwenLM/qwen-code packages/core/src/services/chatRecordingService.ts (dd020dd).
_GEMINI_QWEN_ASSISTANT = json.dumps({
    "uuid": "0f1e2d3c-4b5a-4968-8776-655443322110", "parentUuid": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
    "sessionId": "5d6e7f80-91a2-4b3c-8d4e-5f6071829304", "timestamp": "2026-10-30T10:05:14.920Z",
    "type": "assistant", "provenance": "assistant_output", "cwd": "/Users/example/code/demo2",
    "version": "0.9.0", "message": {"role": "model", "parts": [{"text": "Done."}]},
    "usageMetadata": {"promptTokenCount": 5200, "candidatesTokenCount": 240,
                      "cachedContentTokenCount": 0, "thoughtsTokenCount": 410, "totalTokenCount": 5850},
    "model": "qwen3-coder-plus"})
_GEMINI_QWEN_USER = json.dumps({
    "uuid": "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d", "parentUuid": None,
    "sessionId": "5d6e7f80-91a2-4b3c-8d4e-5f6071829304", "timestamp": "2026-10-30T10:05:08.301Z",
    "type": "user", "provenance": "real_user", "cwd": "/Users/example/code/demo2", "version": "0.9.0",
    "message": {"role": "user", "parts": [{"text": "Find where the config file is parsed."}]}})


# OpenCode reader, rechecked against anomalyco/opencode at 8bca532
# (1 November 2026). The reader was built from b65de4d (26 September 2026); in
# between OpenCode stopped writing the v1 tables, copies each v1 session into
# the v2 tables on upgrade (leaving the v1 rows), keeps v2 sessions in
# session_v2, and gained a claude-agent provider that runs the user's own
# claude binary. These tests pin a database laid out as 8bca532 leaves one to
# the per-call figures in tests/fixtures/opencode/recheck-8bca532/expected.json.
_OPENCODE_HERE = os.path.join(FIXTURES, "opencode", "recheck-8bca532")


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

    def test_a_folder_named_subagents_above_the_projects_folder_marks_nothing(self):
        """Any folder named subagents, up to the root, marked an agent, so a
        projects folder kept below one filed every call under the folders
        above it, and the ledger kept them so. Only the two layouts Claude
        Code writes mark an agent."""
        root = os.path.join(self.tmp, "subagents", "projects", "-proj")
        own = os.path.join(root, "sess-9.jsonl")
        agent = os.path.join(root, "sess-9", "subagents", "agent-c.jsonl")
        os.makedirs(os.path.dirname(agent))
        for path, mid in ((own, "msg_own"), (agent, "msg_agent")):
            with open(path, "w") as f:
                f.write(record(mid, out=10) + "\n")
        best = tm.scan_transcripts([own, agent])
        self.assertEqual([(ev["project"], ev["session"], ev["sidechain"])
                          for ev in (best["msg_own"], best["msg_agent"])],
                         [("-proj", "sess-9", False), ("-proj", "sess-9", True)])

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
        self.assertEqual((got["calls"], got["tokens"]["output"]), (2, 300))
        self.assertEqual(got["label"], "session sess-1")
        # A session's own transcript brings its agents' with it.
        got = self.json_for(main, "--no-ledger")
        self.assertEqual((got["calls"], got["tokens"]["output"]), (2, 300))

    def test_an_agent_path_is_its_whole_session_with_or_without_the_ledger(self):
        """An agent's file was read alone while the session id it carries
        kept the session's other calls from the ledger, so the report said
        the session's own transcript was gone while it was on disk, and the
        same command without the ledger priced the agent alone."""
        self.write("sess-1.jsonl", record("msg_main", out=3000))
        sub = os.path.join(self.projects, "sess-1", "subagents", "agent-a.jsonl")
        flow = os.path.join(self.projects, "sess-1", "subagents", "workflows", "wf_1", "agent-b.jsonl")
        for path, mid in ((sub, "msg_a"), (flow, "msg_b")):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(record(mid, out=300) + "\n")
        cli()                                             # every call now in the ledger
        for agent in (sub, flow):
            for ledger in ([], ["--no-ledger"]):
                with self.subTest(agent=os.path.basename(agent), ledger=ledger):
                    got = self.json_for(agent, *ledger)
                    self.assertEqual((got["calls"], got["tokens"]["output"]), (3, 3600))
                    self.assertEqual((got["tokens_on_disk"], got["tokens_ledger_only"]), (3600, 0))
            text = cli("--session", agent)
            self.assertIn("kept by the ledger 3.6k · on disk now 3.6k\n", text)
            self.assertNotIn("gone", text)
        # Once the session's own transcript is deleted, its calls are gone.
        os.remove(os.path.join(self.projects, "sess-1.jsonl"))
        self.assertEqual(tm.claude_code.session_files(sub), [sub, flow])
        self.assertIn("kept by the ledger 3.6k · on disk now 600 · 3.0k from 1 session "
                      "whose transcripts are gone", cli("--session", sub))

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


class TestImport(Base):
    def events(self, *objs, name="events.jsonl"):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as f:
            for o in objs:
                f.write((o if isinstance(o, str) else json.dumps(o)) + "\n")
        return p

    GOOD = GOOD_IMPORT

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

    def test_a_byte_order_mark_does_not_cost_the_first_line(self):
        """A file saved by an editor that starts it with a byte order mark
        lost its first line as "not valid JSON", from a file or from standard
        input. A mark anywhere else is still a bad line."""
        import io
        lines = [json.dumps(dict(self.GOOD, id="e%d" % i)).encode() for i in range(3)]
        data = b"\xef\xbb\xbf" + b"\r\n".join(lines) + b"\r\n"
        p = os.path.join(self.tmp, "bom.jsonl")
        with open(p, "wb") as f:
            f.write(data)
        overall, *_ = self.run_import(p)
        self.assertEqual(overall["calls"], 3)
        self.assertNotIn(p, tm.importer.PROBLEMS)
        stdin = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8")
        try:
            overall, *_ = self.run_import("-")
        finally:
            sys.stdin = stdin
        self.assertEqual(overall["calls"], 3)
        with open(p, "wb") as f:
            f.write(lines[0] + b"\n\xef\xbb\xbf" + lines[1] + b"\n")
        overall, *_ = self.run_import(p)
        self.assertEqual(overall["calls"], 1)
        self.assertEqual(tm.importer.PROBLEMS[p]["examples"], ["line 2: not valid JSON"])

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
        """Every rollout generation, read as the source writes it. A headless
        session, the saved output of `codex exec --json`, is not read: it is
        not a rollout and names no model and no time, so its fixture is
        pinned to give no calls."""
        for fx in self.expected["fixtures"]:
            if fx["file"].startswith("exec"):
                tm.codex.reset()
                path = os.path.join(FIXTURES, "codex", fx["file"])
                self.assertEqual(list(tm.codex.records(path)), [], fx["file"])
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

        def open_(path):   # the files are not really compressed
            reads.append(path)
            return io.BytesIO(slurp(path, mode="rb"))
        with mock.patch.object(tm.codex, "_decoder", return_value=open_):
            overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 6)
        self.assertEqual(len(reads), 2)
        self.assertEqual(len(set(reads)), 2)

    def test_under_project_a_compressed_session_is_decompressed_in_full_once(self):
        """--project reads each session's first line for its folder, and did
        so by decompressing the whole file, then decompressed it again to
        read its calls. The first read now stops after those lines: a
        session with a long tail costs one full decompression, and the
        stream is closed early, as the zstd command's would be."""
        from unittest import mock
        text = slurp(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl"), mode="rb")
        tail = (json.dumps({"timestamp": "2026-09-24T14:08:00.000Z", "type": "response_item",
                            "payload": {"type": "message", "text": "x" * 500}}) + "\n").encode()
        sizes, read, closed_early = {}, [], []
        for n, fx in enumerate(("gen3_turn_context.jsonl", "gen4_current_paginated.jsonl")):
            p = self.place(fx, uuid=f"0198f3c1-0000-7000-8000-00000000000{n}") + ".zst"
            os.rename(p[:-4], p)
            with open(p, "ab") as f:
                f.write(tail * 400)        # about 200 KB after the calls
            sizes[p] = os.path.getsize(p)

        class Stream(io.BytesIO):
            def __init__(self, path):
                super().__init__(slurp(path, mode="rb"))
                self.path = path

            def read(self, n=-1):
                data = super().read(n)
                read.append(len(data))
                return data

            def read1(self, n=-1):
                data = super().read1(n)
                read.append(len(data))
                return data

            def readinto(self, b):
                n = super().readinto(b)
                read.append(n)
                return n

            def close(self):
                if not self.closed and self.tell() < len(self.getvalue()):
                    closed_early.append(self.path)
                super().close()
        with mock.patch.object(tm.codex, "_decoder", return_value=Stream):
            paths = tm.transcripts(project="/Users/example/code/demo")
            self.assertEqual(len(paths), 2)
            overall, *_ = tm.collect(paths, ledger=False)
        self.assertEqual(overall["calls"], 6)
        total = sum(sizes.values())
        self.assertLess(sum(read), total + 2 * 65536, "the project check read far more than the first lines")
        self.assertEqual(sorted(closed_early), sorted(sizes))

    def test_the_zstd_command_is_read_as_a_stream_and_stopped_early(self):
        """The zstd command's output, read line by line and ended early, and
        read to the end, where a failing exit means a damaged file."""
        tool = self.fake_zstd(os.path.join(self.tmp, "homebrew", "bin"))
        with self.no_decoder_but(tool):
            p = self.place("gen4_current_paginated.jsonl")
            os.rename(p, p + ".zst")
            head = tm.codex._head(p + ".zst", 2)
            self.assertEqual(head.count("\n"), 2)
            self.assertIn("session_meta", head)
            self.assertEqual(tm.codex._first_meta(p + ".zst").get("cwd"), "/Users/example/code/demo")
            whole = tm.codex._decompress(p + ".zst")
            self.assertEqual(whole, slurp(p + ".zst", encoding="utf-8"))
            with self.assertRaises(tm.codex._Damaged):
                tm.codex._decompress(os.path.join(self.tmp, "no-such-file.zst"))

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
        with mock.patch.object(tm.codex, "_decoder",
                               return_value=lambda path: io.BytesIO(slurp(path, mode="rb"))):
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


class TestCodexIncompleteResponses(Base):
    """Codex at a098129: an incomplete response adds its usage to the running
    total while the next token_count still names the previous response."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "codex-home")
        tm.ADAPTER_ROOTS["codex"] = [os.path.join(self.home, "sessions"),
                                     os.path.join(self.home, "archived_sessions")]
        tm._ONLY[:] = ["codex"]
        self.expected = json.loads(slurp(os.path.join(FIXTURES, "codex", "gen5_expected.json")))

    def place(self, where="sessions"):
        d = os.path.join(self.home, where, "2026", "10", "28")
        os.makedirs(d, exist_ok=True)
        dest = os.path.join(d, "rollout-2026-10-28T09-12-04-0199a2e4-3b7c-7d10-8f21-6a4c9e0b5d32.jsonl")
        shutil.copy(os.path.join(FIXTURES, "codex", _CODEX_FIXTURE), dest)
        return dest

    def test_an_incomplete_response_is_counted_as_itself(self):
        """After an incomplete response, token_count's last_token_usage is the
        response before it: the reader counted that earlier response twice and
        never the incomplete one."""
        got = [ev for _, ev in _codex_calls(os.path.join(FIXTURES, "codex", _CODEX_FIXTURE))]
        want = self.expected["expected_turns"]
        self.assertEqual(len(got), len(want))
        for ev, w in zip(got, want):
            u = ev["_usage"]
            self.assertEqual(u["input_tokens"], w["uncached_input_tokens"], w["line"])
            self.assertEqual(u["cache_read_input_tokens"], w["cached_input_tokens"], w["line"])
            self.assertEqual(u["cache_creation"]["ephemeral_5m_input_tokens"],
                             w["cache_write_input_tokens"], w["line"])
            self.assertEqual(u["output_tokens"], w["output_tokens"], w["line"])
            self.assertEqual(u["output_tokens_details"]["thinking_tokens"],
                             w["reasoning_output_tokens"], w["line"])
            self.assertEqual(ev["model"], w["model"], w["line"])
            self.assertEqual(ev["provider"], "openai")
            self.assertEqual(u["speed"], "standard")

    def test_an_incomplete_response_after_an_estimate_is_not_lost(self):
        """A recomputed context estimate zeroes last_token_usage; an incomplete
        response after it moved the total with a zero last_token_usage, and
        the reader dropped it as a call with no usage."""
        got = [ev for _, ev in _codex_calls(os.path.join(FIXTURES, "codex", _CODEX_FIXTURE))]
        self.assertEqual(got[-1]["_usage"]["cache_read_input_tokens"], 8960)
        self.assertEqual(got[-1]["_usage"]["output_tokens"], 1200)

    def test_the_calls_add_up_to_the_running_total(self):
        """Per-call figures that do not add up to Codex's own running total
        mean a call was dropped or counted twice."""
        got = [ev["_usage"] for _, ev in _codex_calls(os.path.join(FIXTURES, "codex", _CODEX_FIXTURE))]
        total = self.expected["expected_session_totals"]
        written = sum(u["cache_creation"]["ephemeral_5m_input_tokens"] for u in got)
        read = sum(u["cache_read_input_tokens"] for u in got)
        self.assertEqual(sum(u["input_tokens"] for u in got) + read + written,
                         total["input_tokens_raw"])
        self.assertEqual(read, total["cached_input_tokens"])
        self.assertEqual(written, total["cache_write_input_tokens"])
        self.assertEqual(sum(u["output_tokens"] for u in got), total["output_tokens"])
        self.assertEqual(sum(u["output_tokens_details"]["thinking_tokens"] for u in got),
                         total["reasoning_output_tokens"])

    def test_two_identical_responses_are_both_counted(self):
        """A last_token_usage equal to the one before is also what two
        identical responses look like; the incomplete-response rule must not
        turn the second into anything but itself."""
        u = {"input_tokens": 1000, "cached_input_tokens": 0, "cache_write_input_tokens": 0,
             "output_tokens": 50, "reasoning_output_tokens": 0, "total_tokens": 1050}
        double = {k: v * 2 for k, v in u.items()}
        lines = [
            {"timestamp": "2026-10-28T10:00:00.000Z", "type": "session_meta",
             "payload": {"id": "t1", "session_id": "t1", "cwd": "/Users/example/code/demo"}},
            {"timestamp": "2026-10-28T10:00:00.100Z", "type": "turn_context",
             "payload": {"cwd": "/Users/example/code/demo", "model": "gpt-6.1-sol"}},
            {"timestamp": "2026-10-28T10:00:05.000Z", "type": "event_msg",
             "payload": {"type": "token_count", "info": {"total_token_usage": u, "last_token_usage": u}}},
            {"timestamp": "2026-10-28T10:00:09.000Z", "type": "event_msg",
             "payload": {"type": "token_count", "info": {"total_token_usage": double, "last_token_usage": u}}},
        ]
        path = os.path.join(self.tmp, "rollout-2026-10-28T10-00-00-t1.jsonl")
        with open(path, "w") as f:
            f.write("\n".join(json.dumps(o) for o in lines) + "\n")
        got = [ev["_usage"] for _, ev in _codex_calls(path)]
        self.assertEqual([g["input_tokens"] for g in got], [1000, 1000])

    def write_session(self, lines):
        path = os.path.join(self.tmp, "rollout-2026-10-28T10-00-00-t1.jsonl")
        with open(path, "w") as f:
            f.write("\n".join(json.dumps(o) for o in lines) + "\n")
        return path

    def inputs(self, path):
        return [ev["_usage"]["input_tokens"] + ev["_usage"]["cache_read_input_tokens"]
                for _, ev in _codex_calls(path)]

    def test_two_incomplete_responses_in_a_row_are_two_calls(self):
        """Each incomplete response writes its own token_count; were they
        merged, one call of their summed input could cross a long-context
        threshold neither crossed."""
        a, b, c = _codex_usage(1000, out=50), _codex_usage(2000, out=0), _codex_usage(3000, out=0)
        ab = {k: a[k] + b[k] for k in a}
        abc = {k: ab[k] + c[k] for k in a}
        path = self.write_session(_codex_session(_codex_record(a), _codex_count(a, a),
                                         _codex_record(b, "resp_2"), _codex_count(ab, a),
                                         _codex_record(c, "resp_3"), _codex_count(abc, a)))
        self.assertEqual(self.inputs(path), [1000, 2000, 3000])
        self.assertEqual(tm.codex.notes(), [])

    def test_a_forked_threads_first_call_incomplete_is_not_its_parents(self):
        """A forked or sub-agent thread starts from its parent's figures
        without its parent's lines; if its first response is incomplete,
        last_token_usage is the parent's last response, which the reader
        counted again in place of the incomplete one."""
        parent_total = _codex_usage(50000, cached=40000, out=900)
        parent_last = _codex_usage(9000, out=300)
        mine = _codex_usage(7000, cached=6000, out=0)
        total = {k: parent_total[k] + mine[k] for k in mine}
        path = self.write_session(_codex_session(_codex_record(mine), _codex_count(total, parent_last),
                                         meta={"forked_from_id": "t0"}))
        got = [ev["_usage"] for _, ev in _codex_calls(path)]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["cache_read_input_tokens"], 6000)
        self.assertEqual(got[0]["input_tokens"], 1000)

    def test_a_forked_threads_first_call_complete_is_itself(self):
        """The rule for a forked thread's first incomplete response must not
        replace a complete first response, whose last_token_usage is its own."""
        parent_total, mine = _codex_usage(50000, out=900), _codex_usage(7000, out=40)
        total = {k: parent_total[k] + mine[k] for k in mine}
        self.assertEqual(self.inputs(self.write_session(_codex_session(_codex_record(mine),
                                                               _codex_count(total, mine)))),
                         [7000])
        # Codex versions before token_usage_record: last_token_usage is the call.
        self.assertEqual(self.inputs(self.write_session(_codex_session(_codex_count(total, mine)))), [7000])

    def test_a_threads_first_response_incomplete_is_counted(self):
        """A new thread whose first response is incomplete writes a zero
        last_token_usage; the reader dropped the call as one with no usage."""
        mine = _codex_usage(4000, out=100)
        zero = _codex_usage(0)
        self.assertEqual(self.inputs(self.write_session(_codex_session(_codex_record(mine),
                                                               _codex_count(mine, zero)))),
                         [4000])

    def test_a_move_nothing_can_attribute_is_reported_not_guessed(self):
        """Where nothing says which response moved the total, the reader must
        neither count the previous response again nor invent one call from a
        sum; the report says how many such counts it left out."""
        parent_total, parent_last = _codex_usage(50000, out=900), _codex_usage(9000, out=300)
        one, two = _codex_usage(7000), _codex_usage(8000)
        total = {k: parent_total[k] + one[k] + two[k] for k in one}
        path = self.write_session(_codex_session(_codex_record(one), _codex_record(two, "resp_2"),
                                         _codex_count(total, parent_last)))
        self.assertEqual(_codex_calls(path), [])
        self.assertEqual(len(tm.codex.notes()), 1)
        self.assertIn("1 Codex token count moved the running total", tm.codex.notes()[0])
        # A total that went down with last_token_usage unchanged: not a call.
        a, b = _codex_usage(1000, out=50), _codex_usage(500)
        path = self.write_session(_codex_session(_codex_count(a, a), _codex_count(b, a)))
        self.assertEqual(self.inputs(path), [1000])
        self.assertEqual(len(tm.codex.notes()), 1)
        tm.codex.reset()
        self.assertEqual(tm.codex.notes(), [])

    def test_through_the_engine_and_labelled_unverified(self):
        """The fixed figures reach the report, a copy in archived_sessions
        counts once, and the report still says Codex is unverified."""
        self.place()
        self.place(where="archived_sessions")
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], 4)
        warns = [t for level, t in tm.report_notes(groups, unknown) if level == "warn"]
        self.assertTrue(any("Codex figures are unverified" in t for t in warns))
        out = json.loads(cli("--json", "--no-ledger"))
        self.assertEqual(out["calls"], 4)
        # Codex's own total_tokens at the session's last token_count.
        self.assertEqual(out["tokens_on_disk"], 36658)


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

    def test_a_whole_session_id_finds_its_file(self):
        """Gemini CLI names a file after the first eight characters of its
        session's id, and --session was matched against the name, so the
        whole id found no file: nothing without the ledger, and with it the
        session's calls taken for ones whose transcripts were gone."""
        sid = "3f9c1a2b-6d41-4f0e-9a52-2b7c8e5d1140"
        path = os.path.join(self.home, ".gemini", "tmp", "demo", "chats",
                            "session-2026-09-26T09-12-3f9c1a2b.jsonl")
        gemini = tm.ADAPTERS["gemini-cli"]
        for given in (sid, sid[:8]):
            with self.subTest(session=given):
                self.assertEqual(gemini.files(tm.adapter_roots("gemini-cli"), session=given), [path])
                got = json.loads(cli("--json", "--no-ledger", "--session", given))
                self.assertEqual(got["calls"], 3)
        cli("--json")                                     # every call now in the ledger
        got = json.loads(cli("--json", "--session", sid))
        self.assertEqual((got["calls"], got["tokens_ledger_only"]), (3, 0))

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


class TestGeminiCliRecheck6814e00(Base):
    """Gemini CLI session files as 6814e00 writes them."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "gemini-home")
        shutil.copytree(os.path.join(_GEMINI_HERE, "home"), self.home)
        self.root = os.path.join(self.home, ".gemini", "tmp")
        self.chats = os.path.join(self.root, "demo2", "chats")
        tm.ADAPTER_ROOTS[gemini_cli.NAME] = [self.root]
        tm._ONLY[:] = [gemini_cli.NAME]
        self.expected = json.loads(slurp(os.path.join(_GEMINI_HERE, "expected.json")))

    def _calls(self):
        """Every record the reader yields, last copy of each key kept."""
        got = {}
        for path in gemini_cli.files([self.root]):
            for key, ev in gemini_cli.records(path):
                got[key] = (path, ev)
        return got

    def test_each_call_reads_as_the_source_says(self):
        """Guards the per-call translation of a 6814e00 message: uncached input
        is input minus cached plus tool, output adds thoughts, and the model,
        time and folder are the ones the file records. A drift in any field
        name since 2fe7c2d would show here as a wrong or missing call."""
        got = self._calls()
        self.assertEqual(sorted(got), sorted(c["key"] for c in self.expected["calls"]))
        for c in self.expected["calls"]:
            with self.subTest(key=c["key"]):
                path, ev = got[c["key"]]
                self.assertEqual(os.path.relpath(path, self.chats), c["file"])
                u = ev["_usage"]
                self.assertEqual((ev["model"], ev["provider"], ev["project"]),
                                 (c["model"], "google", self.expected["project"]))
                self.assertEqual(ev["when"], parse_time(c["timestamp"]))
                self.assertEqual((u["input_tokens"], u["cache_read_input_tokens"], u["output_tokens"],
                                  u["output_tokens_details"]["thinking_tokens"]),
                                 (c["input"], c["cache_read"], c["output"], c["thinking"]))
                self.assertEqual(sum(u["cache_creation"].values()), 0)

    def test_engine_totals_equal_the_per_call_figures(self):
        """Guards against a message counted twice through the engine: one
        call is written three times (first with tokens, then with tool calls,
        then inside a legacy $set checkpoint), another twice."""
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        t = self.expected["totals"]
        self.assertEqual(overall["calls"], t["calls"])
        self.assertEqual(overall["tokens"]["input"], t["input"])
        self.assertEqual(overall["tokens"]["cache_read"], t["cache_read"])
        self.assertEqual(overall["tokens"]["output"], t["output"])
        self.assertEqual(overall["tokens"]["thinking"], t["thinking"])
        self.assertEqual(set(groups["project"]), {self.expected["project"]})
        self.assertEqual(set(groups["provider"]), {"google"})
        got = json.loads(cli("--json", "--no-ledger"))
        self.assertEqual(got["calls"], t["calls"])

    def test_patch_set_and_rewind_lines_yield_nothing(self):
        """Guards against a $patch, $set or $rewindTo line, new or changed
        since 2fe7c2d, being read as a message: none carries tokens, and a
        $set checkpoint's messages were already appended one by one."""
        path = os.path.join(self.chats, _GEMINI_MAIN)
        keys = [k for k, _ in gemini_cli.records(path)]
        self.assertEqual(len(keys), 4)            # one message written twice
        self.assertEqual(len(set(keys)), 3)
        lines = [l for l in slurp(path).splitlines() if l.startswith('{"$')]
        self.assertEqual({next(iter(json.loads(l))) for l in lines}, {"$set", "$patch", "$rewindTo"})

    def test_a_removed_or_rewound_call_still_counts(self):
        """Guards against dropping a call because a later $patch removeIds or
        $rewindTo took it out of the conversation: the API call was made and
        billed, and rewinding changes the conversation, not the invoice."""
        removed = [c["key"] for c in self.expected["calls"] if c.get("removed_by_patch")]
        self.assertEqual(len(removed), 1)
        self.assertIn(removed[0], self._calls())

    def test_a_message_with_no_tokens_and_a_cut_off_line_yield_nothing(self):
        """Guards against a synthetic gemini message from a history sync (no
        tokens, no model) or a half-written last line becoming a call."""
        keys = self._calls()
        self.assertNotIn(f"gemini:{_GEMINI_MAIN_ID}:b1d3f5a7-9c1e-4a3c-8e5a-7b9d1f3a5c8e", keys)
        self.assertNotIn(f"gemini:{_GEMINI_MAIN_ID}:e9f1a3b5-7d9f-4b1d-8f3b-9c1e3a5c7e0b", keys)

    def test_a_subagent_session_is_read_under_its_parent(self):
        """Guards against missing subagent calls: 6814e00 writes a subagent's
        session as chats/<parent session id>/<its own id>.jsonl, a name with no
        session- prefix, and its folder is still the parent's project."""
        path = os.path.join(self.chats, _GEMINI_SUB)
        self.assertIn(path, gemini_cli.files([self.root]))
        (key, ev), = list(gemini_cli.records(path))
        self.assertEqual(ev["session"], "0b6d2f84-4e1a-4c7b-9d3e-5f8a1c2b7e60")
        self.assertEqual(ev["project"], "/Users/example/code/demo2")

    def test_a_collided_file_name_is_found_by_its_session(self):
        """Guards --session against the collision name 6814e00 gives a second
        file in the same minute, session-<time>-<n>-<id[:8]>.jsonl."""
        path = os.path.join(self.chats, _GEMINI_COLLIDED)
        for given in (_GEMINI_COLLIDED_ID, _GEMINI_COLLIDED_ID[:8]):
            with self.subTest(session=given):
                self.assertEqual(gemini_cli.files([self.root], session=given), [path])
                self.assertEqual(json.loads(cli("--json", "--no-ledger", "--session", given))["calls"], 1)

    def test_looks_like_takes_its_own_lines_and_no_other_format(self):
        """Guards against a line of another harness, Qwen Code (a Gemini CLI
        fork) above all, being taken for Gemini CLI's, which would count its
        calls twice or under the wrong source."""
        main = slurp(os.path.join(self.chats, _GEMINI_MAIN)).splitlines()
        self.assertTrue(gemini_cli.looks_like(main[0]))             # metadata
        self.assertTrue(gemini_cli.looks_like(main[3]))             # a gemini message
        codex = slurp(os.path.join(FIXTURES, "codex", "gen4_current_paginated.jsonl")).splitlines()
        others = {"qwen-code assistant": _GEMINI_QWEN_ASSISTANT, "qwen-code user": _GEMINI_QWEN_USER,
                  "claude-code": record("msg_01"), "import": json.dumps(GOOD_IMPORT)}
        others.update((f"codex line {i}", l) for i, l in enumerate(codex) if l.strip())
        for name, line in others.items():
            with self.subTest(other=name):
                self.assertFalse(gemini_cli.looks_like(line))

    def test_labelled_unverified(self):
        """Guards against the rechecked reader's figures losing their
        unverified label in the report."""
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


class TestOpenCodeAt8bca532(Base):
    """The OpenCode reader against the database layout of 8bca532."""

    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.tmp, "opencode-data", "opencode")
        os.makedirs(self.root)
        self.db = os.path.join(self.root, "opencode.db")
        con = sqlite3.connect(self.db)
        con.executescript(slurp(os.path.join(_OPENCODE_HERE, "build_db.sql")))
        con.commit()
        con.close()
        tm.ADAPTER_ROOTS[opencode.NAME] = [self.root]
        tm._ONLY[:] = [opencode.NAME]
        self.expected = json.loads(slurp(os.path.join(_OPENCODE_HERE, "expected.json")))

    def records(self):
        return dict(opencode.records(self.db))

    def test_every_call_matches_its_per_call_figures(self):
        """Any drift between the reader and OpenCode's 8bca532 layout shows
        here as a call missing, extra, or with the wrong counts or folder."""
        got = self.records()
        self.assertEqual(sorted(got), sorted(c["key"] for c in self.expected["calls"]))
        for c in self.expected["calls"]:
            with self.subTest(key=c["key"]):
                ev = got[c["key"]]
                u = ev["_usage"]
                self.assertEqual(ev["model"], c["model"])
                self.assertEqual(ev["provider"], c["provider"])
                self.assertEqual(ev["session"], c["session"])
                self.assertEqual(ev["cwd"], c["cwd"])
                self.assertEqual(ev["when"], dt.datetime.fromtimestamp(c["timestamp_ms"] / 1000,
                                                                       tz=dt.timezone.utc))
                self.assertEqual(u["input_tokens"], c["uncached_input"])
                self.assertEqual(u["cache_read_input_tokens"], c["cache_read"])
                self.assertEqual(u["cache_creation"]["ephemeral_5m_input_tokens"], c["cache_write"])
                self.assertEqual(u["output_tokens"], c["output"] + c["reasoning"])

    def test_a_v1_turn_copied_on_upgrade_counts_once(self):
        """The upgrade copies each v1 assistant message into session_message
        under its own id with its last step's tokens; read beside the v1
        step-finish rows, every upgraded turn was counted once more."""
        got = self.records()
        self.assertNotIn("opencode:msg_v1asst0101", sorted(got))
        v1 = [k for k, ev in got.items() if ev["session"] == "ses_v1keep0001"]
        self.assertEqual(sorted(v1), ["opencode:prt_v1step0101", "opencode:prt_v1step0102"])

    def test_claude_agent_calls_are_left_to_claude_code(self):
        """The claude-agent provider runs the user's claude binary, which
        saves each call in Claude Code's own log; counting OpenCode's row too
        priced every such call twice."""
        got = self.records()
        self.assertNotIn("opencode:msg_v2cla0001", sorted(got))
        self.assertFalse([ev for ev in got.values() if ev["session"] == "ses_v2claude001"])

    def test_a_fork_does_not_count_its_parents_calls_again(self):
        """A v2 fork starts with copies of its parent's rows under new ids;
        counting them charged the parent's calls a second time."""
        got = self.records()
        self.assertNotIn("opencode:msg_forkevt01_1", sorted(got))
        self.assertIn("opencode:msg_v2fork0001", sorted(got))
        self.assertIn("opencode:msg_v2nat0001", sorted(got))

    def test_a_v2_session_carries_its_folder(self):
        """v2 sessions live in session_v2 now, so a reader that looked only
        in session gave every new call an empty folder and --project lost it."""
        tm._PROJECT[:] = ["widget"]
        try:
            overall, *_ = tm.collect(tm.transcripts(project="widget"), ledger=False)
            self.assertEqual(overall["calls"], 3)
        finally:
            tm._PROJECT.clear()

    def test_a_row_still_streaming_or_a_compaction_is_not_a_call(self):
        """A step still streaming has no tokens yet, and a compaction's tokens
        are a total over several calls; neither may be priced as one call."""
        got = self.records()
        self.assertNotIn("opencode:msg_v2nat0003", sorted(got))
        self.assertNotIn("opencode:msg_v2natcomp01", sorted(got))

    def test_the_engine_totals_match(self):
        """The engine's totals for the 8bca532 layout equal the sum of the
        per-call figures, so no call is lost or doubled on the way."""
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        t = self.expected["totals"]
        self.assertEqual(overall["calls"], t["calls"])
        self.assertEqual(overall["tokens"]["input"], t["uncached_input"])
        self.assertEqual(overall["tokens"]["cache_read"], t["cache_read"])
        self.assertEqual(overall["tokens"]["cache_write"], t["cache_write"])
        self.assertEqual(overall["tokens"]["output"], t["output"] + t["reasoning"])
        self.assertEqual(set(groups["provider"]), {"anthropic", "openai"})
        self.assertFalse(unknown)

    def test_json_counts_the_calls(self):
        """--json is what scripts read; it must show the same five calls."""
        out = json.loads(cli("--json", "--no-ledger"))
        self.assertEqual(out["calls"], self.expected["totals"]["calls"])

    def next_db(self):
        path = os.path.join(self.root, "opencode-next.db")
        con = sqlite3.connect(path)
        con.executescript(slurp(os.path.join(_OPENCODE_HERE, "next_db.sql")))
        con.commit()
        con.close()
        return path

    def test_a_copy_in_opencode_next_counts_once(self):
        """OpenCode copies opencode-next.db's rows into opencode.db under the
        same ids and leaves the file; both match opencode*.db, so a key that
        changed with the file would count every such call twice."""
        self.next_db()
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], self.expected["totals"]["calls"])

    def test_a_fork_in_opencode_next_does_not_count_its_parents_calls(self):
        """opencode-next.db keeps its v2 sessions, fork_session_id included,
        in a table named session; a reader that looked for forks only in
        session_v2 counted the fork's copy of its parent's call from that
        file, once more than the parent's own row."""
        got = dict(opencode.records(self.next_db()))
        self.assertEqual(sorted(got), ["opencode:msg_v2fork0001", "opencode:msg_v2nat0001",
                                       "opencode:msg_v2nat0002"])
        self.assertEqual(got["opencode:msg_v2fork0001"]["cwd"], "/Users/example/code/widget")

    def test_labelled_unverified(self):
        """The reader has not been run against a real database, so the report must say so."""
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertTrue(any("OpenCode figures are unverified" in t
                            for _, t in tm.report_notes(groups, unknown)))


class TestTokenCounts(Base):
    """Codex, Gemini CLI and OpenCode each kept their own copy of the rule for
    reading a count from a log, and a count of Infinity or NaN, both of which
    json.loads accepts, ended the run in a traceback in Codex and Gemini CLI.
    whole() is the one rule now."""

    def test_a_count_is_a_whole_number_or_none(self):
        from adapters.common import whole
        for value, want in ((7, 7), (7.9, 7), (-3.5, -3), (0, 0), (10 ** 30, 10 ** 30),
                            (True, 0), (False, 0), (None, 0), ("12", 0), ([3], 0),
                            (float("inf"), 0), (float("-inf"), 0), (float("nan"), 0)):
            with self.subTest(value=value):
                self.assertEqual(whole(value), want)
                self.assertIs(type(whole(value)), int)

    def test_opencode_still_reads_a_negative_count_as_none(self):
        from adapters import opencode
        _, ev = opencode._event("opencode:k", 0, "gpt-6-sol", "openai", "", "ses_1",
                                {"input": -5, "output": 3.9, "reasoning": True,
                                 "cache": {"read": 2, "write": float("nan")}})
        u = ev["_usage"]
        self.assertEqual((u["input_tokens"], u["output_tokens"], u["cache_read_input_tokens"],
                          u["cache_creation"]["ephemeral_5m_input_tokens"]), (0, 3, 2, 0))

    def test_an_infinite_count_does_not_end_the_run(self):
        from adapters import gemini_cli
        codex_file = os.path.join(self.tmp, "rollout-2026-09-24T10-00-00-thread-1.jsonl")
        with open(codex_file, "w", encoding="utf-8") as f:
            f.write('{"timestamp":"2026-09-24T10:00:01.000Z","type":"turn_context",'
                    '"payload":{"model":"gpt-5.2-codex","cwd":"/Users/sam/code/demo"}}\n'
                    '{"timestamp":"2026-09-24T10:00:02.000Z","type":"event_msg",'
                    '"payload":{"type":"token_count","info":{'
                    '"total_token_usage":{"input_tokens":100,"output_tokens":Infinity},'
                    '"last_token_usage":{"input_tokens":100,"output_tokens":Infinity}}}}\n')
        tm.codex.reset()
        (_, ev), = list(tm.codex.records(codex_file))
        self.assertEqual((ev["_usage"]["input_tokens"], ev["_usage"]["output_tokens"]), (100, 0))

        chats = os.path.join(self.tmp, "gemini", "proj", "chats")
        os.makedirs(chats)
        gemini_file = os.path.join(chats, "session-1.jsonl")
        with open(gemini_file, "w", encoding="utf-8") as f:
            f.write('{"type":"gemini","id":"m1","timestamp":"2026-09-24T10:00:00Z",'
                    '"model":"gemini-3.1-pro-preview","tokens":{"input":50,"output":NaN,'
                    '"cached":0,"thoughts":0,"tool":0,"total":50}}\n')
        (_, ev), = list(gemini_cli.records(gemini_file))
        self.assertEqual((ev["_usage"]["input_tokens"], ev["_usage"]["output_tokens"]), (50, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
