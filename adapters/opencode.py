"""OpenCode sessions. Unverified.

Built from the published source of OpenCode (anomalyco/opencode, formerly
sst/opencode, read at commit b65de4d, 26 September 2026, again at commit
8bca532, 1 November 2026, and for its provider ids and OPENCODE_DB at
d9184f2, 2 November 2026, with models.dev at 4201251 the same day) and
checked against the OpenCode parser in ccusage.
It has not yet been run against a real database, so every report that uses it
says so. If a figure looks wrong, please open an issue with a sample.

OpenCode can drive almost any provider, so this is the adapter where one
harness's calls land in many price tables: each call carries the provider id
it was made through.

What OpenCode writes, and what this reader does with it:

  - Everything is in one SQLite database, ~/.local/share/opencode/opencode.db
    ($XDG_DATA_HOME moves it; OPENCODE_DB names another file; a release
    channel other than latest, dev, beta, next or prod writes
    opencode-<channel>.db beside it, and an older "next" build left
    opencode-next.db, whose rows OpenCode copies under the same ids). Every
    opencode*.db there is read; a copied row has the same key, so it counts
    once. It is opened read-only, and Python's own sqlite3 reads it, so
    nothing is installed.
  - Two layouts can share that database, and both are read:
      v2, table session_message: one assistant row per API call, its
      session in session_v2 (named session before August 2026).
      v1, tables message and part: one assistant message per turn, whose
      tokens are only the LAST step's while its cost is the sum. The real
      per-call figures are the "step-finish" rows in part, so those are what
      count. Reading the message rows instead undercounts every multi-step
      turn, which is the mistake ccusage makes. At 8bca532 nothing writes v1
      any more: an upgrade copies each v1 session into session_v2 and
      session_message, keeps the v1 rows, and gives each copied assistant
      row its v1 message's id and that message's last-step tokens. A
      session_message row whose id is a v1 message is that copy, so it is
      skipped and the step-finish rows stand.
  - OpenCode stores input EXCLUDING cache reads and writes, and output
    EXCLUDING reasoning. Reasoning is billed at the output rate, so it is
    added back into output.
  - A forked v2 session (fork_session_id set, in session_v2 or, in
    opencode-next.db, in session) starts with copies of its parent's
    settled rows under new ids but with the parent's time_created. As
    OpenCode's own statistics do, a row in a forked session created before
    the fork itself is skipped; the fork's own calls come later and count.
  - The claude-agent provider hands each call to the user's own claude
    binary, which saves it in Claude Code's own log (persistSession). Those
    rows are skipped, or every such call would be counted twice.
  - OpenCode's own cost figure is not used: it is what the endpoint reported
    or OpenCode's catalogue price, not the API rate.

Not handled: v1 sessions forked from another copy the parent's rows under new
ids, and older installs may also hold JSON files under storage/message/.
Neither is read, so a v1 forked session's copied history is counted again.
Calls made to write a title or a compaction summary are not counted: OpenCode
records their tokens without a model, or as a total over several calls.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import shutil
import sqlite3
import tempfile

from .common import usage, whole

NAME = "opencode"
LABEL = "OpenCode"
STATUS = "unverified"
PROVIDER = ""
FILES = "databases"
FILE = "database"

# OpenCode's provider ids, where they differ from Tokenmeter's table names.
# The ids are models.dev's (OpenCode ships a snapshot of its catalogue). A
# plan route that serves only its maker's models is priced by the maker's
# table: the Kimi Code plan (kimi-for-coding until models.dev split it on 18
# September 2026 into kimi-code-plan-cn, the same api.kimi.com endpoint, and
# kimi-code-plan-global), MiniMax's and Z.ai's international plans, and
# Xiaomi's MiMo routes outside China. Routes that serve several makers
# (github-copilot, opencode, openrouter and the other gateways), and the
# China routes (zhipuai and zhipuai-coding-plan at open.bigmodel.cn,
# moonshotai-cn, minimax-cn, minimax-cn-coding-plan, xiaomi-token-plan-cn),
# whose makers bill from a separate yuan price list, pass through, as does
# anything else, and are priced by a table or the online lookup.
PROVIDERS = {"moonshotai": "moonshot", "z-ai": "zai",
             "google-vertex": "google", "gemini": "google", "x-ai": "xai",
             "kimi-for-coding": "moonshot", "kimi-code-plan-cn": "moonshot",
             "kimi-code-plan-global": "moonshot", "minimax-coding-plan": "minimax",
             "zai-coding-plan": "zai", "xiaomi": "mimo", "xiaomi-token-plan-ams": "mimo",
             "xiaomi-token-plan-sgp": "mimo"}

# Providers that hand the call to another harness's binary, whose own log
# already holds it.
HANDED_OVER = {"claude-agent"}


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
        paths.extend(glob.glob(os.path.join(root, "opencode*.db")))
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
    if not isinstance(tokens, dict) or provider in HANDED_OVER:
        return None
    cache = tokens.get("cache") or {}
    # A negative count is read as none.
    inp, out, reasoning, read, write = (max(0, whole(v)) for v in (
        tokens.get("input"), tokens.get("output"), tokens.get("reasoning"),
        cache.get("read"), cache.get("write")))
    if not any((inp, out, reasoning, read, write)):
        return None
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
        # session holds v1 sessions, or v2 ones in opencode-next.db and in a
        # database from before August 2026; session_v2 wins where both do.
        directory, forked = {}, {}
        for table in ("session", "session_v2"):
            if table not in tables:
                continue
            directory.update(con.execute(f"SELECT id, directory FROM {table}"))
            columns = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            if "fork_session_id" in columns:
                forked.update(con.execute(f"SELECT id, time_created FROM {table} "
                                          "WHERE fork_session_id IS NOT NULL"))

        messages = {}
        if "part" in tables and "message" in tables:
            for mid, data in con.execute("SELECT id, data FROM message"):
                try:
                    messages[mid] = json.loads(data)
                except (ValueError, TypeError):
                    messages[mid] = {}

        if "session_message" in tables:
            for mid, sid, created, data in con.execute(
                    "SELECT id, session_id, time_created, data FROM session_message "
                    "WHERE type = 'assistant'"):
                if mid in messages:
                    continue  # a v1 message copied on upgrade; its step-finish rows count
                if sid in forked and isinstance(created, (int, float)) and created < forked[sid]:
                    continue  # the parent's row, copied into the fork
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

        if messages:
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
