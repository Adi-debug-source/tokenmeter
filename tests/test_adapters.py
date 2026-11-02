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
from adapters import deepseek_harness, gemini_cli, kimi_code, opencode
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


# Kimi Code reader, built from MoonshotAI/kimi-code at a2afdbc (30 October
# 2026). These tests pin the fixture sessions under tests/fixtures/kimi-code to
# the per-call figures in its expected.json: one usage.record per API call,
# its model taken from the llm.request of its own kind before it, a
# duplicated line and a forked session counted once, and the calls Kimi Code
# cannot record exactly left out and reported.
_KIMI_HERE = os.path.join(FIXTURES, "kimi-code")
_KIMI_WS = "wd_demo_f2d28b381d98"
_KIMI_A = "session_4c1f9e2a-7b3d-4e8a-9f61-2d5c8b0a3e17"
_KIMI_B = "session_9e0d7c6b-5a4f-4b3e-8d2c-1f0e9a8b7c65"

# A kimi-cli wire.jsonl line, with the field names and nesting of
# WireMessageRecord and StatusUpdate in MoonshotAI/kimi-cli
# src/kimi_cli/wire/file.py and wire/types.py (9ab1286). Kimi Code does not
# read it, and this reader must not either: it records no model.
_KIMI_CLI_STATUS = json.dumps({
    "timestamp": 1793354409.412,
    "message": {"type": "StatusUpdate", "payload": {
        "context_usage": 0.02, "context_tokens": 4590, "max_context_tokens": 262144,
        "token_usage": {"input_other": 4210, "output": 380, "input_cache_read": 0,
                        "input_cache_creation": 0},
        "message_id": "chatcmpl-7f3a9c", "plan_mode": False, "mcp_status": None}}})
_KIMI_CLI_META = json.dumps({"type": "metadata", "protocol_version": "1.9"})


# The DeepSeek Harness reader: its session files read as the harness's source
# writes them (deepseek-ai/deepseek-harness ce7073d, 30 October 2026), from the
# fixtures in tests/fixtures/deepseek-harness/.
_DSH_HERE = os.path.join(FIXTURES, "deepseek-harness")
_DSH_DEMO = "--Users-example-code-demo--"
_DSH_S1 = "0f3b7c2e-5a91-4d6e-8c40-2b9e1d7a6f53"
_DSH_S2 = "7d1c3e5a-2f4b-4c6d-9e8f-0a1b2c3d4e5f"
_DSH_S3 = "4e8a2c6d-9b1f-4a3e-8d7c-5f0e2a4b6c8d"
_DSH_S4 = "2b9d4f6a-8c1e-4d3b-9a5f-7e0c2d4b6a81"
_DSH_API = "--Users-example-code-api--"


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


_GEMINI_SESSION = os.path.join("demo", "chats", "session-2026-09-26T09-12-3f9c1a2b.jsonl")


def _gemini_home(home, runtime=".gemini"):
    """A Gemini CLI home folder holding the fixture session, with its runtime
    folder (.gemini, or .cache/.gemini under the macOS sandbox) inside it."""
    target = os.path.join(home, runtime)
    shutil.copytree(os.path.join(FIXTURES, "gemini-cli", "home", ".gemini"), target)
    return os.path.join(target, "tmp", _GEMINI_SESSION)


class TestGeminiCliHome(Base):
    """Where the Gemini CLI reader looks: GEMINI_CLI_HOME stands in for the
    home folder (packages/core/src/utils/paths.ts:22-28 at google-gemini/
    gemini-cli 6814e00, read 2 November 2026)."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "user")
        os.makedirs(self.home)

    def found(self, **env):
        env.setdefault("HOME", self.home)
        env.setdefault("USERPROFILE", self.home)  # what ~ means on Windows
        with unittest.mock.patch.dict(os.environ, env):
            return gemini_cli.files(gemini_cli.default_roots())

    def test_gemini_cli_home_is_read(self):
        """The reader only looked in ~/.gemini/tmp and never read
        GEMINI_CLI_HOME, so every session of a Gemini CLI run with that
        variable set (a shared machine, a CI job) was missed and its cost
        reported as nothing. Gemini CLI puts .gemini inside the folder the
        variable names (packages/core/src/utils/paths.ts:22-28 at 6814e00)."""
        moved = os.path.join(self.tmp, "job-123")
        path = _gemini_home(moved)
        self.assertEqual(self.found(GEMINI_CLI_HOME=moved), [path])

    def test_gemini_cli_home_under_the_macos_sandbox_is_read(self):
        """Under the macOS sandbox Gemini CLI writes to .cache/.gemini inside
        homedir(), which is GEMINI_CLI_HOME when it is set
        (packages/core/src/config/storage.ts:97-101 at 6814e00); the reader
        only looked in ~/.cache/.gemini, so those sessions were missed."""
        moved = os.path.join(self.tmp, "job-123")
        path = _gemini_home(moved, os.path.join(".cache", ".gemini"))
        self.assertEqual(self.found(GEMINI_CLI_HOME=moved), [path])

    def test_home_gemini_is_not_read_when_gemini_cli_home_is_set(self):
        """With GEMINI_CLI_HOME set Gemini CLI writes nothing under ~/.gemini,
        so a reader that still read it counted sessions from another
        configuration (another job, another user's copy) as this one's."""
        _gemini_home(self.home)
        moved = os.path.join(self.tmp, "job-123")
        os.makedirs(moved)
        self.assertEqual(self.found(GEMINI_CLI_HOME=moved), [])

    def test_an_empty_gemini_cli_home_counts_as_unset(self):
        """Gemini CLI ignores an empty GEMINI_CLI_HOME and uses the home
        folder; reading the empty value as a folder would look in the
        current one and miss ~/.gemini."""
        path = _gemini_home(self.home)
        self.assertEqual(self.found(GEMINI_CLI_HOME=""), [path])

    def test_a_tilde_in_gemini_cli_home_is_not_expanded(self):
        """Gemini CLI uses GEMINI_CLI_HOME as given and never expands a ~ in
        it (packages/core/src/utils/paths.ts:22-28 at 6814e00), so with the
        value "~" its sessions are under a folder named ~, not under the home
        folder. A reader that expanded it read ~/.gemini instead and counted
        sessions Gemini CLI had not written there as this run's."""
        with unittest.mock.patch.dict(os.environ, {"GEMINI_CLI_HOME": "~", "HOME": self.home,
                                                   "USERPROFILE": self.home}):
            roots = gemini_cli.default_roots()
        self.assertEqual(roots, [os.path.join("~", ".gemini", "tmp"),
                                 os.path.join("~", ".cache", ".gemini", "tmp")])

    def test_a_run_prices_sessions_under_gemini_cli_home(self):
        """The whole command line, not only the reader: with no folder given
        for Gemini CLI, a run reads GEMINI_CLI_HOME and prices the fixture's
        three calls. Before, it found none of them."""
        moved = os.path.join(self.tmp, "job-123")
        _gemini_home(moved)
        tm.ADAPTER_ROOTS.pop("gemini-cli", None)
        env = {"GEMINI_CLI_HOME": moved, "HOME": self.home, "USERPROFILE": self.home}
        with unittest.mock.patch.dict(os.environ, env):
            got = json.loads(cli("--json", "--no-ledger", "--adapter", "gemini-cli"))
        self.assertEqual(got["calls"], 3)


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


class TestKimiCodeAdapter(Base):
    """Kimi Code session files as a2afdbc writes them."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "kimi-home")
        shutil.copytree(os.path.join(_KIMI_HERE, "home"), self.home)
        self.root = os.path.join(self.home, ".kimi-code", "sessions")
        tm.ADAPTER_ROOTS[kimi_code.NAME] = [self.root]
        tm._ONLY[:] = [kimi_code.NAME]
        kimi_code.reset()
        self.expected = json.loads(slurp(os.path.join(_KIMI_HERE, "expected.json")))

    def _wire(self, session, agent="main"):
        return os.path.join(self.root, _KIMI_WS, session, "agents", agent, "wire.jsonl")

    def _calls(self):
        """Every record the reader yields, by key, with how often it was seen."""
        got, seen = {}, {}
        for path in kimi_code.files([self.root]):
            for key, ev in kimi_code.records(path):
                got.setdefault(key, ev)
                seen[key] = seen.get(key, 0) + 1
        return got, seen

    def test_each_call_reads_as_the_source_says(self):
        """Guards the per-call translation of a usage.record: inputOther is
        uncached input as it stands, inputCacheCreation a 5-minute write, the
        model is the one on the llm.request (not the alias usage.record
        names), and the time, folder, session and subagent flag are the ones
        the files record. A wrong field name would show as a wrong or missing
        call."""
        got, _ = self._calls()
        self.assertEqual(sorted(got), sorted(c["dedup_key"] for c in self.expected["calls"]))
        for c in self.expected["calls"]:
            with self.subTest(key=c["dedup_key"]):
                ev = got[c["dedup_key"]]
                u = ev["_usage"]
                self.assertEqual((ev["model"], ev["provider"], ev["project"], ev["cwd"],
                                  ev["session"], ev["sidechain"], ev["source"]),
                                 (c["model"], c["provider"], c["cwd"], c["cwd"],
                                  c["session_id"], c["sidechain"], kimi_code.NAME))
                self.assertEqual(ev["when"], dt.datetime.fromtimestamp(c["time_ms"] / 1000,
                                                                       tz=dt.timezone.utc))
                self.assertEqual((u["input_tokens"], u["cache_read_input_tokens"],
                                  u["cache_creation"]["ephemeral_5m_input_tokens"],
                                  u["cache_creation"]["ephemeral_1h_input_tokens"],
                                  u["output_tokens"], u["output_tokens_details"]["thinking_tokens"]),
                                 (c["uncached_input"], c["cache_read"], c["cache_write_5m"], 0,
                                  c["output"], 0))

    def test_engine_totals_equal_the_per_call_figures(self):
        """Guards against a call counted twice through the engine: the first
        call's usage.record is written twice, and the forked session repeats
        the first turn of the session it forked, times and all."""
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        t = self.expected["totals"]
        self.assertEqual(overall["calls"], t["calls"])
        self.assertEqual(overall["tokens"]["input"], t["uncached_input"])
        self.assertEqual(overall["tokens"]["cache_read"], t["cache_read"])
        self.assertEqual(overall["tokens"]["cache_write"], t["cache_write_5m"])
        self.assertEqual(overall["tokens"]["output"], t["output"])
        self.assertEqual(set(groups["project"]), {"/Users/example/code/demo"})
        self.assertEqual(set(groups["session"]), {_KIMI_A, _KIMI_B})
        self.assertEqual(set(groups["provider"]), {"moonshot", "anthropic"})
        got = json.loads(cli("--json", "--no-ledger"))
        self.assertEqual(got["calls"], t["calls"])

    def test_each_call_is_priced_on_its_own(self):
        """Guards against figures summed before pricing: the engine's total
        must be the sum of each expected call priced alone, with its own
        model, table and day."""
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        want = 0.0
        for c in self.expected["calls"]:
            u = usage(inp=c["uncached_input"], read=c["cache_read"], w5=c["cache_write_5m"],
                      out=c["output"])
            want += cost_of(tm.price_record(
                c["model"], u, provider=c["provider"],
                when=dt.datetime.fromtimestamp(c["time_ms"] / 1000, tz=dt.timezone.utc)))
        self.assertAlmostEqual(overall["total"], want, places=12)

    def test_a_duplicated_line_and_a_fork_count_once(self):
        """Guards against de-duplication by line, and against a repeated
        line being reported as a call with no model (its request is already
        used): a line is repeated, and a fork copies every record of the
        session it forks, so the same call is seen four times."""
        _, seen = self._calls()
        first = self.expected["calls"][0]["dedup_key"]
        self.assertEqual(seen[first], 4)
        fork_keys = {k for k, _ in kimi_code.records(self._wire(_KIMI_B))}
        self.assertEqual(len(fork_keys), 3)
        self.assertEqual(len(fork_keys & {k for k, _ in kimi_code.records(self._wire(_KIMI_A))}), 2)

    def test_a_model_change_mid_session_is_followed_call_by_call(self):
        """Guards against one model for a whole session: the alias changes
        after the first turn, and a custom alias names an Anthropic model, so
        each call takes the model of the llm.request for its own alias."""
        models = [ev["model"] for _, ev in kimi_code.records(self._wire(_KIMI_A))]
        self.assertEqual(models, ["k3", "k3", "k3", "kimi-for-coding", "claude-sonnet-4-6", "k3",
                                  "k3", "k3"])

    def test_calls_that_cannot_be_counted_exactly_are_left_out_and_reported(self):
        """Guards against a guessed model, an understated output or cached
        input priced as uncached: a usage.record with no llm.request for its
        alias has no model, a call over Google's protocol is recorded without
        its thinking tokens, and a DeepSeek model over the OpenAI protocol
        has its cache hits in a field Kimi Code does not read. All are left
        out, and the report says how many."""
        got, _ = self._calls()
        left = self.expected["not_counted"]
        for key in left["no_model"] + left["no_thinking"] + left["cache_unread"]:
            self.assertNotIn(key, got)
        self.assertEqual(kimi_code._STATE["no_model"], set(left["no_model"]))
        self.assertEqual(kimi_code._STATE["no_thinking"], set(left["no_thinking"]))
        self.assertEqual(kimi_code._STATE["cache_unread"], set(left["cache_unread"]))
        notes = kimi_code.notes()
        self.assertEqual(len(notes), 3)
        self.assertIn("1 Kimi Code call had no model recorded", notes[0])
        self.assertIn("1 Kimi Code call over the OpenAI protocol", notes[1])
        self.assertIn("Gemini", notes[2])
        kimi_code.reset()
        self.assertEqual(kimi_code.notes(), [])

    def test_no_usage_a_subagent_total_and_a_cut_off_line_yield_nothing(self):
        """Guards against counting what is not one API call: a usage.record
        whose counts are all zero (the provider sent none), the subagent's
        total on subagent.completed in its parent's file (a sum of the calls
        in the subagent's own file), and a last line cut off as written."""
        lines = slurp(self._wire(_KIMI_A)).splitlines()
        self.assertTrue(any('"inputOther":0,"output":0' in l for l in lines))
        self.assertTrue(any('"type":"subagent.completed"' in l and '"usage"' in l for l in lines))
        with self.assertRaises(ValueError):
            json.loads(lines[-1])
        keys = [k for k, _ in kimi_code.records(self._wire(_KIMI_A))]
        self.assertEqual(len(keys), 8)                     # seven calls, one written twice
        self.assertFalse(any(":0:0:0:0" in k for k in keys))
        self.assertFalse(any(k.startswith("kimi-code:agent-0:") for k in keys))

    def _write(self, lines):
        path = os.path.join(self.root, _KIMI_WS, "session_c", "agents", "main", "wire.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(l) for l in lines) + "\n")
        return path

    @staticmethod
    def _req(model, kind, at, alias="kimi-code/k3", protocol="openai"):
        return {"type": "llm.request", "agentId": "main", "kind": kind, "provider": protocol,
                "model": model, "modelAlias": alias, "toolSelect": False,
                "systemPromptHash": "sp_1", "toolsHash": "th_1", "messageCount": 2, "time": at}

    @staticmethod
    def _use(other, scope, at, alias="kimi-code/k3"):
        return {"type": "usage.record", "agentId": "main", "model": alias,
                "usage": {"inputOther": other, "output": 10, "inputCacheRead": 0,
                          "inputCacheCreation": 0}, "usageScope": scope, "time": at}

    def test_a_compaction_beside_a_step_takes_its_own_request(self):
        """Guards against the latest request of any kind giving a call its
        model: an automatic compaction runs beside a step, both requests are
        written before either usage, and if the alias was pointed at another
        model in between, the step's call must keep the step's model."""
        path = self._write([self._req("kimi-k2.6", "loop", 1793354400000),
                            self._req("kimi-k3", "compaction", 1793354400500),
                            self._use(100, "session", 1793354405000),
                            self._use(200, "turn", 1793354406000)])
        got = {ev["_usage"]["input_tokens"]: ev["model"] for _, ev in kimi_code.records(path)}
        self.assertEqual(got, {100: "kimi-k3", 200: "kimi-k2.6"})

    def test_a_request_serves_one_call(self):
        """Guards against a stale request naming a later call's model: each
        call writes its own request first, so a second usage with no request
        of its own after the first is left out, not given the old model."""
        path = self._write([self._req("kimi-k3", "loop", 1793354400000),
                            self._use(100, "turn", 1793354401000),
                            self._use(200, "turn", 1793354402000)])
        self.assertEqual([ev["_usage"]["input_tokens"] for _, ev in kimi_code.records(path)], [100])
        self.assertEqual(len(kimi_code._STATE["no_model"]), 1)

    def test_the_openai_protocol_counts_only_families_whose_cache_it_reads(self):
        """Guards against cached input priced as uncached: over the OpenAI
        protocol Kimi Code reads only cached_tokens and
        prompt_tokens_details.cached_tokens, Moonshot's and OpenAI's fields,
        so another family's call over it is left out, while over the
        Anthropic protocol any family is counted."""
        lines, t = [], 1793354400000
        for i, (model, protocol) in enumerate((("kimi-k3", "openai"), ("gpt-5.5", "openai"),
                                               ("deepseek-v4", "openai"), ("glm-5", "openai"),
                                               ("deepseek-v4", "anthropic"))):
            lines += [self._req(model, "loop", t + 2 * i, protocol=protocol),
                      self._use(100 + i, "turn", t + 2 * i + 1)]
        got = [ev["model"] for _, ev in kimi_code.records(self._write(lines))]
        self.assertEqual(got, ["kimi-k3", "gpt-5.5", "deepseek-v4"])
        self.assertEqual(len(kimi_code._STATE["cache_unread"]), 2)

    def test_a_subagents_calls_are_marked_as_a_subagents(self):
        """Guards against a subagent's calls counted as the main agent's."""
        evs = [ev for _, ev in kimi_code.records(self._wire(_KIMI_A, "agent-0"))]
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["sidechain"])
        self.assertEqual(evs[0]["session"], _KIMI_A)

    def test_the_provider_comes_from_the_models_family(self):
        """Guards against pricing by protocol: llm.request's provider is the
        wire protocol, and Kimi's own models go over the OpenAI one, which
        would price k3 from OpenAI's table."""
        for model, want in (("k3", "moonshot"), ("kimi-for-coding", "moonshot"),
                            ("kimi-k2.6", "moonshot"), ("claude-sonnet-4-6", "anthropic"),
                            ("gpt-5.5", "openai"), ("o4-mini", "openai"),
                            ("gemini-3-pro-preview", "google"), ("deepseek-v4", "deepseek"),
                            ("grok-5", "xai"), ("glm-5", "zai"), ("devstral-2", "mistral"),
                            ("qwen3-coder-plus", "unknown"), ("kestrel", "unknown")):
            with self.subTest(model=model):
                self.assertEqual(kimi_code.provider_for(model), want)

    def test_session_and_project_narrow_the_files(self):
        """Guards against --session or --project reading the wrong files: a
        session is its folder's name, a project the cwd in state.json."""
        self.assertEqual(kimi_code.files([self.root], session=_KIMI_B), [self._wire(_KIMI_B)])
        self.assertEqual(len(kimi_code.files([self.root], session=_KIMI_A)), 2)
        self.assertEqual(len(kimi_code.files([self.root], project="demo")), 3)
        self.assertEqual(kimi_code.files([self.root], project="elsewhere"), [])
        got = json.loads(cli("--json", "--no-ledger", "--session", _KIMI_B))
        self.assertEqual(got["calls"], 3)

    def test_a_missing_state_file_falls_back_to_the_wires_folder(self):
        """Guards against a call losing its project when state.json is gone:
        config.update in the wire names the working folder too."""
        os.remove(os.path.join(self.root, _KIMI_WS, _KIMI_A, "state.json"))
        evs = [ev for _, ev in kimi_code.records(self._wire(_KIMI_A))]
        self.assertTrue(evs)
        self.assertEqual({ev["project"] for ev in evs}, {"/Users/example/code/demo"})

    def test_default_roots_honour_kimi_code_home(self):
        """Guards against reading ~/.kimi-code when KIMI_CODE_HOME moves it,
        as resolveKimiHome() in Kimi Code's bootstrap does."""
        with unittest.mock.patch.dict(os.environ, {"KIMI_CODE_HOME": os.path.join(self.home, ".kimi-code")}):
            self.assertEqual(kimi_code.default_roots(), [self.root])
            self.assertEqual(len(kimi_code.files(kimi_code.default_roots())), 3)
        with unittest.mock.patch.dict(os.environ, {"KIMI_CODE_HOME": ""}):
            self.assertEqual(kimi_code.default_roots(),
                             [os.path.join(os.path.expanduser("~/.kimi-code"), "sessions")])

    def test_looks_like_takes_its_own_lines_and_no_other_format(self):
        """Guards against a line of another harness being taken for Kimi
        Code's, which would count its calls under the wrong source, and
        against kimi-cli's wire.jsonl, which records no model, being read."""
        lines = slurp(self._wire(_KIMI_A)).splitlines()
        self.assertTrue(kimi_code.looks_like(lines[0]))             # metadata
        self.assertTrue(any(kimi_code.looks_like(l) for l in lines if '"llm.request"' in l))
        self.assertTrue(any(kimi_code.looks_like(l) for l in lines if '"usage.record"' in l))
        others = {"claude-code": record("msg_01"), "import": json.dumps(GOOD_IMPORT),
                  "kimi-cli status": _KIMI_CLI_STATUS, "kimi-cli metadata": _KIMI_CLI_META}
        for path in self._other_fixture_lines_files():
            for i, line in enumerate(slurp(path).splitlines()):
                if line.strip():
                    others[f"{os.path.relpath(path, FIXTURES)}:{i}"] = line
        self.assertTrue(any(k.startswith("gemini-cli") for k in others))
        self.assertTrue(any(k.startswith("codex") for k in others))
        for name, line in others.items():
            with self.subTest(other=name):
                self.assertFalse(kimi_code.looks_like(line))

    @staticmethod
    def _other_fixture_lines_files():
        """Every line-based fixture of another reader, hidden folders
        (.gemini) included, which glob leaves out."""
        out = []
        for top, dirs, names in os.walk(FIXTURES):
            if os.path.relpath(top, FIXTURES).split(os.sep)[0] == "kimi-code":
                continue
            out += [os.path.join(top, n) for n in names if n.endswith(".jsonl")]
        return sorted(out)

    def test_labelled_unverified(self):
        """Guards against the reader's figures losing their unverified label
        in the report."""
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertTrue(any("Kimi Code figures are unverified" in t
                            for _, t in tm.report_notes(groups, unknown)))


class TestDeepSeekHarnessAdapter(Base):
    """Built from the published source and labelled unverified."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "dsh-home")
        shutil.copytree(os.path.join(_DSH_HERE, "dsh-home"), self.home)
        self.root = os.path.join(self.home, "sessions")
        tm.ADAPTER_ROOTS[deepseek_harness.NAME] = [self.root]
        tm._ONLY[:] = [deepseek_harness.NAME]
        self.expected = json.loads(slurp(os.path.join(_DSH_HERE, "expected.json")))

    def session_file(self, project, sid, name="session.v4.jsonl"):
        return os.path.join(self.root, project, sid, name)

    def read_all(self, paths=None):
        deepseek_harness.reset()
        out = []
        for path in paths or deepseek_harness.files([self.root]):
            out.extend(deepseek_harness.records(path))
        return out

    def test_reads_as_the_source_says(self):
        """The whole tree through the engine: eight calls, each counted once,
        with input uncached, cache reads and writes apart, and output whole."""
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        t = self.expected["totals"]
        self.assertEqual(overall["calls"], t["calls"])
        self.assertEqual(overall["tokens"]["input"], t["uncached_input"])
        self.assertEqual(overall["tokens"]["cache_read"], t["cache_read"])
        self.assertEqual(overall["tokens"]["cache_write"], t["cache_write"])
        self.assertEqual(overall["tokens"]["output"], t["output"])
        self.assertEqual(set(groups["provider"]), {"deepseek", "anthropic", "openai"})
        self.assertEqual(set(groups["project"]), {"/Users/example/code/demo", "/Users/example/code/api"})

    def test_every_call_as_expected(self):
        """Each call's model, route, time, folder and counts, against the
        per-call figures in expected.json. A count read from the wrong field,
        or a time from the wrong event, changes one of them."""
        got = {}
        for key, ev in self.read_all():
            got.setdefault(key, ev)
        self.assertEqual(set(got), {c["key"] for c in self.expected["calls"]})
        for c in self.expected["calls"]:
            with self.subTest(key=c["key"]):
                ev = got[c["key"]]
                self.assertEqual(ev["model"], c["model"])
                self.assertEqual(ev["provider"], c["provider"])
                self.assertEqual(ev["session"], c["session_id"])
                self.assertEqual(ev["project"], c["project"])
                self.assertEqual(ev["cwd"], c["cwd"])
                self.assertEqual(ev["when"], dt.datetime.fromtimestamp(c["time_ms"] / 1000,
                                                                       tz=dt.timezone.utc))
                self.assertEqual(ev["source"], "deepseek-harness")
                self.assertEqual(ev["_usage"], usage(inp=c["uncached_input"], read=c["cache_read"],
                                                     w5=c["cache_write"], out=c["output"],
                                                     think=c["reasoning"], speed="standard"))

    def test_priced_per_call_at_peak_and_off_peak(self):
        """DeepSeek charges half outside 01:00 to 04:00 and 06:00 to 10:00 UTC
        on weekdays. A figure summed over calls either side of 10:00 could not
        be priced right; each call here is priced at its own time."""
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        want = 0.0
        for c in self.expected["calls"]:
            u = usage(inp=c["uncached_input"], read=c["cache_read"], w5=c["cache_write"],
                      out=c["output"], think=c["reasoning"])
            when = dt.datetime.fromtimestamp(c["time_ms"] / 1000, tz=dt.timezone.utc)
            want += cost_of(tm.price_record(c["model"], u, provider=c["provider"], when=when))
        self.assertAlmostEqual(overall["total"], want, places=12)
        flash = [c for c in self.expected["calls"] if c["model"] == "deepseek-flash"
                 and c["timestamp"].startswith("2026-09-30T10:00")][0]
        u = usage(inp=flash["uncached_input"], read=flash["cache_read"], out=flash["output"])
        at = dt.datetime.fromtimestamp(flash["time_ms"] / 1000, tz=dt.timezone.utc)
        off = cost_of(tm.price_record("deepseek-flash", u, provider="deepseek", when=at))
        peak = cost_of(tm.price_record("deepseek-flash", u, provider="deepseek",
                                       when=at - dt.timedelta(minutes=1)))
        self.assertAlmostEqual(off, peak / 2, places=12)

    def test_only_the_highest_generation_is_read(self):
        """Opening an older session writes a migrated successor and keeps the
        predecessor beside it. Reading both read the same session twice."""
        found = deepseek_harness.files([self.root])
        folder = os.path.join(self.root, _DSH_DEMO, _DSH_S1)
        self.assertIn(os.path.join(folder, "session.v4.jsonl"), found)
        self.assertNotIn(os.path.join(folder, "session.v3.jsonl"), found)
        os.remove(os.path.join(folder, "session.v4.jsonl"))
        self.assertIn(os.path.join(folder, "session.v3.jsonl"), deepseek_harness.files([self.root]))
        # A temporary migration file is not a generation.
        open(os.path.join(folder, "session.v5.jsonl.tmp-123"), "w").close()
        self.assertIn(os.path.join(folder, "session.v3.jsonl"), deepseek_harness.files([self.root]))

    def test_a_fork_counts_its_inherited_calls_once(self):
        """A subagent child starts with a byte copy of its parent's history up
        to a tagged session/end-seed. Keyed by message id, the copied calls
        count once, and stay the parent's even though the child's file ends
        first; the child's own call counts as a subagent's."""
        child = self.read_all([self.session_file(_DSH_DEMO, _DSH_S3)])
        self.assertEqual(len(child), 3)
        own = [ev for _, ev in child if ev["sidechain"]]
        self.assertEqual([ev["model"] for ev in own], ["deepseek-flash"])
        self.assertEqual(sum(1 for _, ev in child if not ev["sidechain"]), 2)
        overall, groups, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], self.expected["totals"]["calls"])
        self.assertEqual(groups["session"][_DSH_S3]["calls"], 1)
        self.assertEqual(groups["session"][_DSH_S1]["calls"], 4)

    def test_repeated_interrupted_and_torn_rows(self):
        """A row written twice counts once, a call cancelled before its usage
        arrived has nothing to count, and a torn last line is skipped rather
        than ending the run."""
        rows = self.read_all([self.session_file(_DSH_DEMO, _DSH_S1)])
        keys = [k for k, _ in rows]
        self.assertEqual(len(keys), 5)          # the repeated row is yielded twice
        self.assertEqual(len(set(keys)), 4)
        self.assertNotIn("deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e04", keys)

    def test_a_failed_attempt_with_usage_counts_and_a_zero_one_does_not(self):
        """An error that came back with usage was billed; it is an
        assistant/attempt with no model, whose route is the latest
        request/context. pi-ai reports zeros for a transport failure, which
        billed nothing."""
        rows = self.read_all([self.session_file(_DSH_API, _DSH_S2)])
        attempt = [ev for k, ev in rows if k.startswith("deepseek-harness:attempt:")]
        self.assertEqual(len(attempt), 1)
        self.assertEqual((attempt[0]["provider"], attempt[0]["model"]),
                         ("anthropic", "claude-sonnet-4-5"))
        self.assertEqual(attempt[0]["_usage"]["input_tokens"], 5120)

    def test_a_failed_attempt_takes_the_route_of_its_own_request(self):
        """A retry on another route logs a new request/context before its
        request, after the failed attempt settled. Reading the route at the
        end of the step gave the failed call the fallback's model."""
        path = self.session_file(_DSH_API, _DSH_S2)
        lines = slurp(path).splitlines()
        fallback = json.dumps({"type": "request/context", "seq": 9, "time": 1791037212900,
                               "data": {"provider": "deepseek-official", "model": "deepseek-flash",
                                        "contextWindow": 1000000}})
        at = next(i for i, l in enumerate(lines) if '"llm/retry-started"' in l) + 1
        with open(path, "w") as f:
            f.write("\n".join(lines[:at] + [fallback] + lines[at:]) + "\n")
        rows = self.read_all([path])
        attempt = [ev for k, ev in rows if k.startswith("deepseek-harness:attempt:")]
        self.assertEqual((attempt[0]["provider"], attempt[0]["model"]),
                         ("anthropic", "claude-sonnet-4-5"))

    def test_a_cache_write_on_another_route_is_not_counted(self):
        """pi-ai writes one-hour cache entries when a profile asks for long
        retention, and the log does not say which a write was. Priced as a
        five-minute write, such a call could be understated; it is left out
        and the report counts it. DeepSeek bills a write as input either
        way, so its own routes are not affected."""
        keys = {k for k, _ in self.read_all([self.session_file(_DSH_API, _DSH_S2)])}
        self.assertNotIn("deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e07", keys)
        self.assertEqual(deepseek_harness._STATE["lifetime_unknown"],
                         {"deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e07"})
        path = self.session_file(_DSH_DEMO, _DSH_S1)
        text = slurp(path).replace('"cacheReadTokens":9344,', '"cacheReadTokens":9344,"cacheWriteTokens":64,')
        with open(path, "w") as f:
            f.write(text)
        rows = dict(self.read_all([path]))
        written = rows["deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e02"]["_usage"]["cache_creation"]
        self.assertEqual(written["ephemeral_5m_input_tokens"], 64)
        self.assertEqual(deepseek_harness._STATE["lifetime_unknown"], set())

    def test_format_1_failed_runs_are_calls_too(self):
        """Formats 0 and 1 have no assistant/attempt: a failed call is a run
        of assistant/chunk events that no assistant/message cites, ended by a
        retry, as the harness's own migration ends it. Only messages were
        read before, so a billed failure there was lost; and a run that a
        message cites must not count again."""
        rows = self.read_all([self.session_file(_DSH_API, _DSH_S4, "session.v1.jsonl")])
        self.assertEqual(sorted(k for k, _ in rows),
                         ["deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e08",
                          "deepseek-harness:attempt:1790074802400:1:1:3100:1024:0:9"])
        self.assertTrue(all(ev["model"] == "gpt-5-mini" and ev["provider"] == "openai"
                            for _, ev in rows))
        self.assertIs(tm.adapter_for(self.session_file(_DSH_API, _DSH_S4, "session.v1.jsonl")),
                      deepseek_harness)

    def test_a_message_without_data_usage_reads_its_stream(self):
        """The harness meters a message by data.usage, or else the last usage
        chunk in its stream (token-meter usageOf). Reading data.usage alone
        lost such a call."""
        path = self.session_file(_DSH_DEMO, _DSH_S1)
        lines = slurp(path).splitlines()
        for i, l in enumerate(lines):
            if "5e01" in l and '"assistant/message"' in l:
                ev = json.loads(l)
                del ev["data"]["usage"]
                lines[i] = json.dumps(ev)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        rows = dict(self.read_all([path]))
        self.assertEqual(rows["deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e01"]["_usage"]["input_tokens"],
                         9412)

    def test_compaction_is_its_own_call(self):
        """The summary call is metered on compaction/summary, not on any
        assistant/message; missing it undercounts every compacted session."""
        rows = dict(self.read_all([self.session_file(_DSH_DEMO, _DSH_S1)]))
        ev = rows["deepseek-harness:compaction:a7e3c9d1-2b4f-4e6a-8c0d-3f5e7a9b1c2d"]
        self.assertEqual((ev["model"], ev["provider"]), ("deepseek-flash", "deepseek"))
        self.assertEqual(ev["_usage"]["cache_read_input_tokens"], 10240)

    def test_another_summarisers_compaction_is_not_counted(self):
        """Only a summary marked llmStreamCall is one call through the
        harness's own model client. Another summariser's usage may cover
        several calls, which priced as one could cross a threshold none of
        them did; it is left out and the report counts it."""
        path = self.session_file(_DSH_DEMO, _DSH_S1)
        text = slurp(path).replace('"llmStreamCall":true,', "")
        with open(path, "w") as f:
            f.write(text)
        keys = {k for k, _ in self.read_all([path])}
        self.assertNotIn("deepseek-harness:compaction:a7e3c9d1-2b4f-4e6a-8c0d-3f5e7a9b1c2d", keys)
        self.assertEqual(len(deepseek_harness._STATE["summariser"]), 1)

    def test_notes(self):
        """The report says the figures are unverified, and how many calls it
        left out: a cache write of unknown lifetime, the title request and
        the interrupted call. A silent omission reads as a complete total."""
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("DeepSeek Harness figures", notes)
        self.assertIn("are unverified", notes)
        self.assertIn("1 DeepSeek Harness call on a route other than DeepSeek's wrote to a "
                      "prompt cache and is not counted", notes)
        self.assertIn("1 DeepSeek Harness title or web-search request is not counted", notes)
        self.assertIn("1 interrupted DeepSeek Harness call is not counted", notes)

    def test_labelled_unverified(self):
        """A reader built from source alone, never run on real files, must
        say so on every report; figures without the caveat read as checked."""
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertTrue(any("DeepSeek Harness figures are unverified" in t
                            for _, t in tm.report_notes(groups, unknown)))

    def test_the_command_line(self):
        """--json counts the same calls as the engine does; a reader that
        works only through collect() would vanish from the command line."""
        got = json.loads(cli("--json", "--no-ledger"))
        self.assertEqual(got["calls"], self.expected["totals"]["calls"])

    def test_session_and_project_filters(self):
        """A session is named by its folder, and a project by the header's cwd."""
        self.assertEqual(deepseek_harness.files([self.root], session=_DSH_S2),
                         [self.session_file(_DSH_API, _DSH_S2)])
        self.assertEqual(len(deepseek_harness.files([self.root], project="/Users/example/code/demo")), 2)
        self.assertEqual(deepseek_harness.files([self.root], project="/Users/example/code/elsewhere"), [])
        got = json.loads(cli("--json", "--no-ledger", "--session", _DSH_S1))
        self.assertEqual(got["calls"], 4)

    def test_default_roots_honour_dsh_home(self):
        """$DSH_HOME moves everything the harness keeps; a blank one is unset."""
        with unittest.mock.patch.dict(os.environ, {"DSH_HOME": self.home}):
            self.assertEqual(deepseek_harness.default_roots(), [self.root])
        with unittest.mock.patch.dict(os.environ, {"DSH_HOME": "  "}):
            self.assertEqual(deepseek_harness.default_roots(), [os.path.expanduser("~/.dsh/sessions")])
        env = dict(os.environ)
        env.pop("DSH_HOME", None)
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(deepseek_harness.default_roots(), [os.path.expanduser("~/.dsh/sessions")])

    def test_looks_like_is_strict(self):
        """Claude Code's test is the loosest and runs last; this one must not
        claim a line of any other reader's format, hidden folders (.gemini,
        .kimi-code) included, which glob leaves out."""
        others = [record("msg_1"), json.dumps(GOOD_IMPORT)]
        paths = [os.path.join(top, n) for top, _, names in os.walk(FIXTURES) for n in names
                 if ".json" in n]
        for path in sorted(paths):
            if os.sep + "deepseek-harness" + os.sep in path or path.endswith("expected.json"):
                continue
            others.extend(l for l in slurp(path, encoding="utf-8", errors="ignore").splitlines()
                          if l.strip())
        self.assertTrue(others)
        for line in others:
            with self.subTest(line=line[:80]):
                self.assertFalse(deepseek_harness.looks_like(line))
        own = slurp(self.session_file(_DSH_DEMO, _DSH_S1)).splitlines()
        self.assertTrue(deepseek_harness.looks_like(own[0]))
        self.assertTrue(all(deepseek_harness.looks_like(l) for l in own[1:-1]))
        self.assertIs(tm.adapter_for(self.session_file(_DSH_DEMO, _DSH_S1)), deepseek_harness)

    def compress(self, frames_of, cut=0):
        """The v4 session as the harness compresses it: one frame for the
        header, then one per append batch."""
        raw = slurp(self.session_file(_DSH_DEMO, _DSH_S1), mode="rb").split(b"\n")
        lines = [l + b"\n" for l in raw if l.strip()][:-1]          # drop the torn line
        frames = [lines[:1]] + [lines[i:i + frames_of] for i in range(1, len(lines), frames_of)]
        parts = [zstd_compress(b"".join(f)) for f in frames]
        if parts[0] is None:
            self.skipTest("no zstd encoder on this machine")
        data = b"".join(parts)
        if cut:
            data = data[:-cut]
        folder = os.path.join(self.root, _DSH_DEMO, _DSH_S1)
        for name in os.listdir(folder):
            os.remove(os.path.join(folder, name))
        path = os.path.join(folder, "session.v4.jsonl.zstd")
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_a_compressed_session_is_read_across_every_frame(self):
        """The harness writes one Zstandard frame per append. A decoder that
        stops at the end of the first frame (the zstandard package's default)
        read the header and nothing else."""
        path = self.compress(frames_of=3)
        rows = self.read_all([path])
        self.assertEqual(len({k for k, _ in rows}), 4)
        self.assertEqual(deepseek_harness.files([self.root], project="/Users/example/code/demo"),
                         sorted([path, self.session_file(_DSH_DEMO, _DSH_S3)]))
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(overall["calls"], self.expected["totals"]["calls"])

    def test_a_torn_last_frame_keeps_the_calls_before_it(self):
        """A crash or a write in progress leaves a torn final frame. Treating
        the whole file as unreadable lost every call in the session."""
        path = self.compress(frames_of=10, cut=7)
        keys = {k for k, _ in self.read_all([path])}
        self.assertIn("deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e01", keys)
        self.assertIn("deepseek-harness:9c4f1d2e-7a3b-4e5c-8d6f-1a2b3c4d5e02", keys)
        self.assertEqual(deepseek_harness._STATE["compressed_damaged"], 1)
        overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
        notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        self.assertIn("1 compressed DeepSeek Harness session (.jsonl.zstd) ended in a damaged "
                      "or unfinished frame", notes)

    def test_python_decoders_read_one_frame_at_a_time(self):
        """Python's own zstd and the zstandard package decode one frame per
        decompressor. Reading on with one decompressor stopped at the first
        frame (the header); a stream reader that fails at a torn last frame
        dropped the whole frames in its last block. A stand-in decoder, one
        frame per b"F" + length + payload, shows the loop reads every frame
        and keeps those before a torn one."""

        class Torn(Exception):
            pass

        class Frame:
            def __init__(self):
                self.eof, self.unused_data = False, b""

            def decompress(self, data):
                if data[:1] != b"F":
                    raise Torn()
                size = int.from_bytes(data[1:5], "big")
                body = data[5:5 + size]
                if len(body) < size:
                    return body[:0]
                self.eof, self.unused_data = True, data[5 + size:]
                return body

        def frame(b):
            return b"F" + len(b).to_bytes(4, "big") + b

        path = os.path.join(self.tmp, "frames.jsonl.zstd")
        whole_ = frame(b"one\n") + frame(b"two\n") + frame(b"three\n")
        with open(path, "wb") as f:
            f.write(whole_)
        self.assertEqual(deepseek_harness._frames(path, Frame, Torn), (b"one\ntwo\nthree\n", False))
        with open(path, "wb") as f:
            f.write(whole_[:-3])
        self.assertEqual(deepseek_harness._frames(path, Frame, Torn), (b"one\ntwo\n", True))
        with open(path, "wb") as f:
            f.write(whole_ + b"junk")
        self.assertEqual(deepseek_harness._frames(path, Frame, Torn), (b"one\ntwo\nthree\n", True))

    def test_no_decoder_is_reported_not_fatal(self):
        """Without zstd anywhere a compressed session cannot be read: it is
        counted and reported, and the run goes on."""
        folder = os.path.join(self.root, _DSH_DEMO, _DSH_S1)
        for name in os.listdir(folder):
            os.remove(os.path.join(folder, name))
        with open(os.path.join(folder, "session.v4.jsonl.zstd"), "wb") as f:
            f.write(b"\x28\xb5\x2f\xfd not really\n")
        with unittest.mock.patch.dict(sys.modules, {"compression": None, "compression.zstd": None,
                                                    "zstandard": None}), \
                unittest.mock.patch.object(codex_module, "_decoder", lambda: None):
            overall, groups, _, unknown = tm.collect(tm.transcripts(), ledger=False)
            notes = " ".join(t for _, t in tm.report_notes(groups, unknown))
        # Session 2's one call, the format 1 session's two and the child's
        # three: its copies of the parent's calls now stand alone.
        self.assertEqual(overall["calls"], 6)
        self.assertIn("1 compressed DeepSeek Harness session (.jsonl.zstd) could not be read", notes)


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


_ROUTES_HEADER = {"type": "session", "version": 4, "id": "5a0c9e2b-7d41-4f8a-9b36-1e2d3c4b5a69",
           "createdAt": 1791037198000, "cwd": "/Users/example/code/demo", "isSeeded": False,
           "delegationDepth": 0}


def _dsh_call(seq, mid, route, model, time_ms):
    """One settled call as the harness writes it: an assistant/message whose
    source names the route and model, and whose usage is the call's own."""
    return {"type": "assistant/message", "seq": seq, "time": time_ms,
            "data": {"turn": 1, "step": seq,
                     "message": {"id": mid, "role": "assistant",
                                 "content": [{"type": "text", "text": "Done."}],
                                 "source": {"kind": "model", "provider": route, "model": model}},
                     "usage": {"inputTokens": 1200, "outputTokens": 300, "totalTokens": 3500,
                               "cacheReadTokens": 2000}}}


def _external(seq, child, time_ms):
    """The parent's record of a subagent run in another agent's process
    (establishExternalCatalogChild, catalog version 2)."""
    return {"type": "subagent/catalog", "seq": seq, "time": time_ms,
            "data": {"version": 2, "childId": child, "childCreatedAt": time_ms,
                     "mode": "external", "label": "Review the diff"}}


class _DeepSeekHarnessSession(Base):
    def setUp(self):
        super().setUp()
        self.root = os.path.join(self.tmp, "dsh-home", "sessions")
        self.folder = os.path.join(self.root, "--Users-example-code-demo--", _ROUTES_HEADER["id"])
        os.makedirs(self.folder)
        deepseek_harness.reset()
        self.addCleanup(deepseek_harness.reset)

    def session(self, *events, header=None):
        path = os.path.join(self.folder, "session.v4.jsonl")
        with open(path, "w") as f:
            for obj in (header or _ROUTES_HEADER,) + events:
                f.write(json.dumps(obj) + "\n")
        return path

    def provider_of(self, route, model):
        path = self.session(_dsh_call(1, "3e9b1c7a-0d2f-4a6b-8c5e-7f1a2b3c4d5e", route, model,
                                      1791037231000))
        got = [ev for _, ev in deepseek_harness.records(path)]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["model"], model)
        return got[0]["provider"]


class TestDeepSeekHarnessPlanRoutes(_DeepSeekHarnessSession):
    """pi-ai 1.3.0's plan routes that serve one maker's models only."""

    def test_openai_codex_is_priced_by_openai(self):
        """A call over openai-codex (ChatGPT sign-in, GPT models only) was
        recorded under the route's own name, which no table has, so it was
        priced at nothing offline and sent to the online lookup online."""
        self.assertEqual(self.provider_of("openai-codex", "gpt-6.1-sol"), "openai")

    def test_xiaomi_is_priced_by_mimo(self):
        """A call over pi-ai's xiaomi route (MiMo models only) was recorded
        under "xiaomi", which no table has, instead of the mimo table."""
        self.assertEqual(self.provider_of("xiaomi", "mimo-v2.6-pro"), "mimo")

    def test_kimi_coding_is_priced_by_moonshot(self):
        """A call over kimi-coding (the Kimi Code plan, Kimi models only) was
        recorded under "kimi-coding", which no table has, instead of Moonshot's."""
        self.assertEqual(self.provider_of("kimi-coding", "k3"), "moonshot")

    def test_xiaomi_token_plan_ams_is_priced_by_mimo(self):
        """A call over Xiaomi's European token plan (MiMo models only) was
        recorded under the route's name, which no table has."""
        self.assertEqual(self.provider_of("xiaomi-token-plan-ams", "mimo-v2.6-flash"), "mimo")

    def test_xiaomi_token_plan_sgp_is_priced_by_mimo(self):
        """A call over Xiaomi's Singapore token plan (MiMo models only) was
        recorded under the route's name, which no table has."""
        self.assertEqual(self.provider_of("xiaomi-token-plan-sgp", "mimo-v2.6-flash"), "mimo")

    def test_minimax_already_names_its_table(self):
        """pi-ai's minimax route is the table's own name: a mapping added for
        it, or a rename of the table, would send MiniMax calls elsewhere."""
        self.assertEqual(self.provider_of("minimax", "MiniMax-M3"), "minimax")

    def test_routes_of_several_makers_or_another_price_list_pass_through(self):
        """github-copilot serves several makers, and the China routes bill from
        a yuan price list the international tables are not: mapping any of
        them to one maker's table would price a call at a rate nobody charged."""
        for route, model in (("github-copilot", "claude-sonnet-4.6"), ("openrouter", "z-ai/glm-5.3"),
                             ("moonshotai-cn", "kimi-k3"), ("minimax-cn", "MiniMax-M3"),
                             ("zai-coding-cn", "glm-5.3"), ("xiaomi-token-plan-cn", "mimo-v2.6-pro")):
            with self.subTest(route=route):
                self.assertEqual(self.provider_of(route, model), route)


class TestDeepSeekHarnessExternalSubagents(_DeepSeekHarnessSession):
    """Subagents run in another agent's process leave no usage in this log."""

    def test_external_subagent_runs_are_named_in_a_note(self):
        """A Claude Code or Codex subagent keeps no log (persistSession: false,
        an ephemeral thread), so its calls were missing without a word. Each
        run the parent records as external is counted once, a fork's copy of
        the same record included, and a local child is not one."""
        local = {"type": "subagent/catalog", "seq": 3, "time": 1791037240000,
                 "data": {"version": 0, "childId": "9f8e7d6c-5b4a-4392-8a1b-0c9d8e7f6a5b",
                          "childCreatedAt": 1791037240000, "mode": "continuable",
                          "label": "Explore"}}
        path = self.session(
            _dsh_call(1, "3e9b1c7a-0d2f-4a6b-8c5e-7f1a2b3c4d5e", "deepseek-official",
                      "deepseek-v4-pro", 1791037231000),
            _external(2, "1b2c3d4e-5f60-4718-9a2b-3c4d5e6f7081", 1791037235000),
            local,
            _external(4, "2c3d4e5f-6071-4829-8b3c-4d5e6f708192", 1791037250000),
            _external(5, "1b2c3d4e-5f60-4718-9a2b-3c4d5e6f7081", 1791037235000))
        calls = list(deepseek_harness.records(path))
        self.assertEqual(len(calls), 1)
        notes = [n for n in deepseek_harness.notes() if "subagent" in n]
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].startswith("2 DeepSeek Harness subagent runs went to another "
                                            "agent's process"), notes[0])
        self.assertIn("A Claude Code or Codex subagent keeps no log, so its calls are missing",
                      notes[0])
        deepseek_harness.reset()
        self.assertFalse([n for n in deepseek_harness.notes() if "subagent" in n])

    def test_no_note_without_an_external_run(self):
        """A session whose subagents all ran in the harness's own process has
        every call in a session file here, so no note says otherwise."""
        path = self.session(_dsh_call(1, "3e9b1c7a-0d2f-4a6b-8c5e-7f1a2b3c4d5e",
                                      "deepseek-official", "deepseek-v4-pro", 1791037231000))
        list(deepseek_harness.records(path))
        self.assertFalse([n for n in deepseek_harness.notes() if "subagent" in n])


def _opencode_db(path, provider_id, model, mid="msg_route0001"):
    """A database with one v2 session and one assistant call, laid out as
    OpenCode's session_v2 and session_message tables are."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE session_v2 (id text PRIMARY KEY, project_id text NOT NULL,
          fork_session_id text, slug text NOT NULL, directory text NOT NULL,
          title text, version text NOT NULL, time_created integer NOT NULL);
        CREATE TABLE session_message (id text PRIMARY KEY NOT NULL, session_id text NOT NULL,
          type text NOT NULL, seq integer NOT NULL, time_created integer NOT NULL,
          time_updated integer NOT NULL, data text NOT NULL);
    """)
    con.execute("INSERT INTO session_v2 VALUES ('ses_route0001', 'prj_demo', NULL, 'demo', "
                "'/Users/example/code/demo', 'Demo', '2.0.0', 1790000300000)")
    data = {"agent": "build", "model": {"id": model, "providerID": provider_id},
            "content": [{"type": "text", "id": "txt_01", "text": "Done."}], "finish": "stop",
            "cost": 0, "tokens": {"input": 900, "output": 120, "reasoning": 0,
                                  "cache": {"read": 4000, "write": 0}},
            "time": {"created": 1790000310000, "completed": 1790000320000}}
    con.execute("INSERT INTO session_message VALUES (?, 'ses_route0001', 'assistant', 1, "
                "1790000310000, 1790000320000, ?)", (mid, json.dumps(data)))
    con.commit()
    con.close()
    return path


class TestOpenCodePlanRoutes(Base):
    """models.dev's plan routes, as OpenCode records them, that serve one
    maker's models only."""

    def provider_of(self, provider_id, model):
        path = _opencode_db(os.path.join(self.tmp, provider_id, "opencode", "opencode.db"),
                            provider_id, model)
        got = [ev for _, ev in opencode.records(path)]
        self.assertEqual(len(got), 1)
        return got[0]["provider"]

    def test_kimi_for_coding_is_priced_by_moonshot(self):
        """models.dev's Kimi Code plan id until 18 September 2026: its calls
        were recorded under "kimi-for-coding", which no table has."""
        self.assertEqual(self.provider_of("kimi-for-coding", "k3"), "moonshot")

    def test_kimi_code_plan_cn_is_priced_by_moonshot(self):
        """The Kimi Code plan at api.kimi.com, the endpoint DeepSeek Harness's
        kimi-coding uses: recorded under the route's name, which no table has."""
        self.assertEqual(self.provider_of("kimi-code-plan-cn", "k3.1-pro"), "moonshot")

    def test_kimi_code_plan_global_is_priced_by_moonshot(self):
        """The Kimi Code plan at api.kimi.ai: recorded under the route's name,
        which no table has."""
        self.assertEqual(self.provider_of("kimi-code-plan-global", "k3"), "moonshot")

    def test_minimax_coding_plan_is_priced_by_minimax(self):
        """MiniMax's international token plan (MiniMax models only): recorded
        under the route's name, which no table has."""
        self.assertEqual(self.provider_of("minimax-coding-plan", "MiniMax-M3"), "minimax")

    def test_zai_coding_plan_is_priced_by_zai(self):
        """Z.ai's international coding plan (GLM models only): recorded under
        the route's name, which no table has."""
        self.assertEqual(self.provider_of("zai-coding-plan", "glm-5.3"), "zai")

    def test_xiaomi_is_priced_by_mimo(self):
        """Xiaomi's pay-as-you-go route (MiMo models only): recorded under
        "xiaomi", which no table has, instead of the mimo table."""
        self.assertEqual(self.provider_of("xiaomi", "mimo-v2.6-pro"), "mimo")

    def test_xiaomi_token_plan_ams_is_priced_by_mimo(self):
        """Xiaomi's European token plan: recorded under the route's name."""
        self.assertEqual(self.provider_of("xiaomi-token-plan-ams", "mimo-v2.6-flash"), "mimo")

    def test_xiaomi_token_plan_sgp_is_priced_by_mimo(self):
        """Xiaomi's Singapore token plan: recorded under the route's name."""
        self.assertEqual(self.provider_of("xiaomi-token-plan-sgp", "mimo-v2.6-flash"), "mimo")

    def test_minimax_already_names_its_table(self):
        """models.dev's minimax id is the table's own name: a mapping added for
        it, or a rename of the table, would send MiniMax calls elsewhere."""
        self.assertEqual(self.provider_of("minimax", "MiniMax-M3"), "minimax")

    def test_routes_of_several_makers_or_another_price_list_pass_through(self):
        """github-copilot and OpenCode's own gateways serve several makers, and
        the China routes bill from a yuan price list: mapping any of them to one
        maker's table would price a call at a rate nobody charged."""
        for route, model in (("github-copilot", "claude-sonnet-4.6"), ("opencode", "kimi-k3"),
                             ("moonshotai-cn", "kimi-k3"), ("minimax-cn-coding-plan", "MiniMax-M3"),
                             ("zhipuai-coding-plan", "glm-5.3"),
                             ("xiaomi-token-plan-cn", "mimo-v2.6-pro")):
            with self.subTest(route=route):
                self.assertEqual(self.provider_of(route, model), route)

    def test_zhipuai_china_platform_passes_through(self):
        """models.dev's zhipuai is Zhipu's China platform (open.bigmodel.cn,
        billed from a yuan list: glm-5.3 at $1.19516 in and $4.18306 out
        against Z.ai's $1.40 and $4.40 in models.dev 4201251), but the reader
        recorded it under zai, so Z.ai's international table priced it at
        rates nobody charged."""
        self.assertEqual(self.provider_of("zhipuai", "glm-5.3"), "zhipuai")

if __name__ == "__main__":
    unittest.main(verbosity=2)
