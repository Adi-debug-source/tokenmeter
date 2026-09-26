"""OpenCode sessions. Unverified.

Built from the published source of OpenCode (anomalyco/opencode, formerly
sst/opencode, read at commit b65de4d, 26 September 2026) and checked against
the OpenCode parser in ccusage. It has not yet been run against a real
database, so every report that uses it says so. If a figure looks wrong,
please open an issue with a sample.

OpenCode can drive almost any provider, so this is the adapter where one
harness's calls land in many price tables: each call carries the provider id
it was made through.

What OpenCode writes, and what this reader does with it:

  - Everything is in one SQLite database, ~/.local/share/opencode/opencode.db
    ($XDG_DATA_HOME moves it; OPENCODE_DB names another file). It is opened
    read-only, and Python's own sqlite3 reads it, so nothing is installed.
  - Two write paths share that database, and both are read:
      v2, table session_message: one assistant row per API call.
      v1, tables message and part: one assistant message per turn, whose
      tokens are only the LAST step's while its cost is the sum. The real
      per-call figures are the "step-finish" rows in part, so those are what
      count. Reading the message rows instead undercounts every multi-step
      turn, which is the mistake ccusage makes.
  - OpenCode stores input EXCLUDING cache reads and writes, and output
    EXCLUDING reasoning. Reasoning is billed at the output rate, so it is
    added back into output.
  - OpenCode's own cost figure is not used: the v2 path always records 0.

Not handled: sessions forked from another copy the parent's rows under new
ids, and older installs may also hold JSON files under storage/message/.
Neither is read, so a forked session's copied history is counted again.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import sqlite3
import tempfile

from .common import usage

NAME = "opencode"
LABEL = "OpenCode"
STATUS = "unverified"
PROVIDER = ""
FILES = "databases"
FILE = "database"

# OpenCode's provider ids, where they differ from Tokenmeter's table names.
# Anything else passes through and is priced by a table or the online lookup.
PROVIDERS = {"moonshotai": "moonshot", "zhipuai": "zai", "z-ai": "zai",
             "google-vertex": "google", "gemini": "google", "x-ai": "xai"}


def default_roots() -> list:
    base = os.environ.get("XDG_DATA_HOME", "").strip() or os.path.expanduser("~/.local/share")
    return [os.path.join(base, "opencode")]


def files(roots: list, project: str = "", session: str = "") -> list:
    override = os.environ.get("OPENCODE_DB", "").strip()
    paths = []
    if override and override != ":memory:":
        for root in roots:
            candidate = override if os.path.isabs(override) else os.path.join(root, override)
            if os.path.isfile(candidate):
                paths.append(candidate)
    for root in roots:
        paths.extend(p for p in glob.glob(os.path.join(root, "opencode*.db")))
    return sorted(set(paths))


def looks_like(line: str) -> bool:
    return False  # a database, never handed over as a text file


def _connect(path: str):
    """Read-only, and from a private copy if the live file cannot be opened
    that way (a write-ahead log that needs its shared-memory file, say)."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return con, None
    except sqlite3.Error:
        tmp = tempfile.mkdtemp(prefix="tokenmeter-")
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                shutil.copy(path + suffix, os.path.join(tmp, "db" + suffix))
        return sqlite3.connect(os.path.join(tmp, "db")), tmp


def _event(key, when_ms, model, provider, project, session, tokens):
    if not isinstance(tokens, dict):
        return None
    cache = tokens.get("cache") or {}

    def n(v):
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else 0
    inp, out, reasoning = n(tokens.get("input")), n(tokens.get("output")), n(tokens.get("reasoning"))
    read, write = n(cache.get("read")), n(cache.get("write"))
    if not any((inp, out, reasoning, read, write)):
        return None
    import datetime as dt
    when = None
    if isinstance(when_ms, (int, float)) and when_ms > 0:
        when = dt.datetime.fromtimestamp(when_ms / 1000, tz=dt.timezone.utc)
    provider = PROVIDERS.get(provider or "", provider or "")
    return key, {
        "when": when,
        "model": model or "",
        "provider": provider,
        "project": project,
        "session": session,
        "cwd": project,
        "sidechain": False,
        "source": NAME,
        "_usage": usage(input=inp, output=out + reasoning, cache_read=read,
                        cache_write_5m=write, thinking=reasoning),
    }


def records(path: str):
    con, tmp = _connect(path)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        directory = {}
        if "session" in tables:
            directory = dict(con.execute("SELECT id, directory FROM session"))

        if "session_message" in tables:
            for mid, sid, created, data in con.execute(
                    "SELECT id, session_id, time_created, data FROM session_message "
                    "WHERE type = 'assistant'"):
                try:
                    d = json.loads(data)
                except (ValueError, TypeError):
                    continue
                model = d.get("model") or {}
                ev = _event(f"opencode:{mid}", (d.get("time") or {}).get("created") or created,
                            model.get("id"), model.get("providerID"),
                            directory.get(sid, ""), sid, d.get("tokens"))
                if ev:
                    yield ev

        if "part" in tables and "message" in tables:
            messages = {}
            for mid, data in con.execute("SELECT id, data FROM message"):
                try:
                    messages[mid] = json.loads(data)
                except (ValueError, TypeError):
                    continue
            for pid, msg_id, sid, created, data in con.execute(
                    "SELECT id, message_id, session_id, time_created, data FROM part "
                    "WHERE data LIKE '%step-finish%'"):
                try:
                    d = json.loads(data)
                except (ValueError, TypeError):
                    continue
                if d.get("type") != "step-finish":
                    continue
                m = messages.get(msg_id) or {}
                cwd = (m.get("path") or {}).get("cwd") or directory.get(sid, "")
                ev = _event(f"opencode:{pid}", created, m.get("modelID"), m.get("providerID"),
                            cwd, sid, d.get("tokens"))
                if ev:
                    yield ev
    except sqlite3.Error:
        return
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
