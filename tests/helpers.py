"""What the test modules share: the engine, a sealed temp home for every test,
and builders for the records, runs and reports they check.

Importing this module puts the repository first on the path, so every test
module takes tm, the engine, from here. Nothing here is a test.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tokenmeter as tm


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


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


# One good line of the import format (docs/import-format.md). The importer's
# tests and the command line's both use it.
GOOD_IMPORT = {"id": "e1", "timestamp": "2026-09-20T10:00:00Z", "provider": "openai",
               "model": "gpt-6-sol", "input": 1000, "cache_read": 9000, "output": 500}

# Anthropic's pricing page as markdown, cut down to one model no table has.
ANTHROPIC_PAGE = (
    "| Model | Base input tokens | 5m cache writes | 1h cache writes | "
    "Cache hits and refreshes | Output tokens |\n| :-- | :-- | :-- | :-- | :-- | :-- |\n"
    "| Claude Opus 9 | $6 / MTok | $7.50 / MTok | $12 / MTok | $0.60 / MTok | $30 / MTok |\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects", "-proj")
        os.makedirs(self.projects)
        self.ledger = os.path.join(self.tmp, "ledger.jsonl")
        # Sealed off from the machine running the tests: no real logs, no real
        # ledger, no network. First in the environment, which is where a run
        # looks once reset_run() has put everything back, so even a main()
        # that skipped cli() reads and writes only this temp folder.
        env = unittest.mock.patch.dict(os.environ, {
            tm.PROJECTS_ENV: os.path.join(self.tmp, "projects"), tm.LEDGER_ENV: self.ledger,
            tm.OFFLINE_ENV: "1", "CODEX_HOME": os.path.join(self.tmp, "no-codex"),
            "XDG_DATA_HOME": os.path.join(self.tmp, "no-xdg")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("OPENCODE_DB", None)
        # Each test starts as a new run would, with nothing left from the last.
        tm.reset_run()
        tm._ROOTS[:] = [os.path.join(self.tmp, "projects")]
        tm._LEDGER[:] = [self.ledger]
        for name in tm.ADAPTERS:
            if name != "claude-code":
                tm.ADAPTER_ROOTS[name] = [os.path.join(self.tmp, "no-" + name)]
        tm.ONLINE_LOOKUP[0] = False
        # No saved price lookups and no exchange rates: both caches live in the
        # temp folder, never beside the engine.
        tm.PRICE_CACHE = os.path.join(self.tmp, "prices.json")
        tm.FX_CACHE = os.path.join(self.tmp, "fx_rates.json")
        self._fx = tm.fx_rates
        tm.fx_rates = lambda: (dict(tm.FALLBACK_RATES), "test", False)

    def tearDown(self):
        tm.reset_run()
        tm.fx_rates = self._fx
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, *lines):
        p = os.path.join(self.projects, name)
        with open(p, "w") as f:
            f.write("\n".join(lines) + "\n")
        return p


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


def as_a_new_run():
    """main() starts every run afresh with reset_run(), as a new process does.
    A new process takes the folders it reads, its ledger and the lookup switch
    from its environment; under test they are the test's own, put back straight
    after that reset, so the command line reads and writes only what the test
    laid out."""
    sealed = (list(tm._ROOTS), list(tm._LEDGER), dict(tm.ADAPTER_ROOTS), tm.ONLINE_LOOKUP[0])
    reset = tm.reset_run

    def reset_then_seal():
        reset()
        tm._ROOTS[:], tm._LEDGER[:] = sealed[0], sealed[1]
        tm.ADAPTER_ROOTS.update(sealed[2])
        tm.ONLINE_LOOKUP[0] = sealed[3]
    return unittest.mock.patch.object(tm, "reset_run", reset_then_seal)


def cli(*argv):
    """The command line with these arguments: what it prints, without colour.
    In dollars unless a test names a currency, because the environment running
    the tests may set TOKENMETER_CURRENCY to another one."""
    import contextlib, io
    argv = list(argv)
    if "--currency" not in argv:
        argv += ["--currency", "USD"]
    buf = io.StringIO()
    with as_a_new_run(), contextlib.redirect_stdout(buf):
        tm.main(argv)
    return re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
