"""Kilo Code sessions (the extension and CLI from 7.0 on). Unverified.

Built from the published source of Kilo Code (Kilo-Org/kilocode at commit
e4833e5, 2 November 2026, version 7.8.25, read 2 November 2026; earlier
releases read at the tags v7.0.26, v7.2.5, v7.2.6, v7.3.63, v7.4.15 and
v7.4.16). It has not yet been run against a real database, so every report
that uses it says so. If a figure looks wrong, please open an issue with a
sample.

Kilo Code 7 is a fork of OpenCode: the VS Code extension, the JetBrains
plugin and the kilo CLI all run the same kilo server, which keeps every
session in one SQLite database much like OpenCode's. Kilo Code 5 and earlier,
a fork of Roo Code that kept ui_messages.json task folders, reached end of
life on 31 July 2026; those folders name no model on any call and are not
read (see the finding in adapters/README.md).

What Kilo Code writes, and what this reader does with it:

  - The database is <data>/kilo.db, where <data> is $XDG_DATA_HOME/kilo, or
    ~/.local/share/kilo when XDG_DATA_HOME is unset or empty, on every
    platform (packages/core/src/global.ts 12 to 24, xdg-basedir 5.1.0).
    KILO_DB names another file, relative to <data> unless absolute; a build
    from a channel other than latest, beta or prod writes kilo-<channel>.db,
    or an opencode-<channel>.db already there (database/database.ts 50 to
    67). The extension starts its server with KILO_DISABLE_CHANNEL_DB, so it
    always writes kilo.db (kilo-vscode server-manager.ts 32). Every kilo*.db
    and opencode-*.db in <data> is read; session-export.db, an upload queue,
    is not. Kilo Code strips line breaks from XDG_DATA_HOME but resolves any
    other value that is not absolute against the folder it was started in,
    which Tokenmeter cannot know, so it reads the default folder and notes()
    names the value.
  - One step-finish row in the part table per API call, written when that
    call's stream ends (session/processor.ts 612 to 721). Its tokens, from
    Session.getUsage (session/session.ts 420 to 463), hold input EXCLUDING
    cache reads and writes, and, from 7.2.6 (14 April 2026), output
    EXCLUDING reasoning, which is billed as output and so is added back.
    The assistant message the row belongs to names the model and provider,
    fixed for that message (session/prompt.ts 1722 to 1736). When a custom
    auto router sends the call on to one of the user's own providers, the row
    itself names that provider and model (step-finish "model", from 7.3.63,
    kilocode/session/routed-model.ts), and that wins, as it does in Kilo's
    own usage view (kilocode/session/model-usage.ts 70 to 80).
  - Before 7.2.6 the row's output was the SDK's own figure: up to 7.2.4,
    AI SDK 5's, which counted reasoning inside output for some providers
    (OpenAI) and outside it for others (Google); in 7.2.5 (13 April 2026),
    AI SDK 6's, which counts it inside for every provider. The row does not
    say which. Rows from before 7.4.16 (24 July 2026)
    carry no time, so their version cannot be told; for one of those with
    reasoning, the row's own total decides: input, cache and output adding
    up to it means reasoning was inside output, adding reasoning too means
    it was outside. A row whose total settles neither is not counted, and
    notes() says how many. Rows from 7.4.16 on carry time and are read as
    the current source writes them.
  - Forking a session, and copying a subagent's session into the fork, copy
    every step-finish row under new ids with the cost set to 0 and the
    tokens, the step's time and the message's created time kept
    (session/session.ts 878 to 907, kilocode/session/fork.ts 110 to 150);
    importing a session from Kilo's cloud does the same
    (kilo-gateway/src/cloud-sessions.ts 257 to 362). So the key is built
    from what a copy keeps: the message's created time, the step's place
    in it, the model and the counts. A copy then counts once with its
    original, and once on its own when the original was deleted.
  - Sessions moved over from Kilo Code 5, and sessions resumed from Claude
    Code or Codex transcripts, get assistant messages with zero tokens and
    no step-finish rows, so nothing is counted twice.
  - A second, event-sourced layout, the session_message table, gets one
    assistant row per call only from the newer /api/session routes, which
    Kilo Code's own clients do not use at e4833e5. Those rows are read the
    way the OpenCode reader reads them.
  - No provider hands a call to another harness's binary at e4833e5, so
    nothing is skipped for that.
  - Kilo Code's own cost figure is not used: it is what the endpoint
    reported or a catalogue price, not the API rate.

Not counted, because Kilo Code keeps no record of them: calls made to write a
title, a commit message, a branch name or a prompt enhancement (they go
straight to the model, session/prompt.ts 315 to 345), the calls of a
compaction split into chunks (each chunk's message is deleted when it ends,
kilocode/session/compaction-chunks.ts 320 to 323), a reply holding only
reasoning that Kilo Code retries (kilocode/session/processor.ts 445 to 460),
and calls in messages or sessions deleted, reverted or cleaned up before
Tokenmeter read them.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import shutil
import sqlite3

from .common import usage, whole
from .opencode import _connect

NAME = "kilo-code"
LABEL = "Kilo Code"
STATUS = "unverified"
PROVIDER = ""
FILES = "databases"
FILE = "database"

DATA_ENV = "XDG_DATA_HOME"
DB_ENV = "KILO_DB"
DEFAULT_DATA = "~/.local/share"

# Kilo Code's provider ids, which are models.dev's (Kilo Code loads its
# catalogue from models.dev, packages/core/src/models-dev.ts 171), where they
# differ from Tokenmeter's table names. Each one serves one maker's models on
# that maker's international endpoint (models.dev 42012513d8eb, 2 November
# 2026); the plans are mapped to their maker's table by the maintainer's
# decision of 2 November 2026. google-vertex is kept as the OpenCode reader
# keeps it, for the maintainer to decide (Vertex also serves other makers'
# models, which then get Google's stand-in rate and a warning). Routes serving
# several makers (kilo, openrouter, github-copilot, vercel and other gateways)
# pass through and get the engine's "no price table" note, as do the makers'
# China platforms, billed from yuan lists, plans included: moonshotai-cn,
# zhipuai and zhipuai-coding-plan (open.bigmodel.cn), minimax-cn and
# minimax-cn-coding-plan (api.minimax.cn, which Kilo Code itself calls its
# "china" region, kilocode/provider-usage/minimax/usage.ts 11 to 14), and
# xiaomi-token-plan-cn.
PROVIDERS = {"moonshotai": "moonshot", "kimi-for-coding": "moonshot",
             "kimi-code-plan-cn": "moonshot", "kimi-code-plan-global": "moonshot",
             "zai-coding-plan": "zai", "minimax-coding-plan": "minimax",
             "xiaomi": "mimo", "xiaomi-token-plan-ams": "mimo",
             "xiaomi-token-plan-sgp": "mimo", "google-vertex": "google"}

# The XDG_DATA_HOME value the default folder was last read in place of, or
# None. Not cleared by reset(), because the roots are chosen before each scan
# starts its notes afresh; notes() names it only while the environment still
# holds that value.
_UNFOLLOWED = [None]

_STATE = {"unsettled": set()}


def default_roots() -> list:
    """<data>/kilo, where <data> is $XDG_DATA_HOME when that is an absolute
    path, else ~/.local/share (see the docstring)."""
    value = os.environ.get(DATA_ENV)
    _UNFOLLOWED[0] = None
    base = ""
    if value:
        cleaned = re.sub(r"[\r\n]+", "", value)
        if os.path.isabs(cleaned):
            base = cleaned
        else:
            _UNFOLLOWED[0] = value
    return [os.path.join(base or os.path.expanduser(DEFAULT_DATA), "kilo")]


def files(roots: list, project: str = "", session: str = "") -> list:
    override = os.environ.get(DB_ENV, "")
    paths = []
    if override and override != ":memory:":
        for root in roots:
            candidate = override if os.path.isabs(override) else os.path.join(root, override)
            if os.path.isfile(candidate):
                paths.append(candidate)
    for root in roots:
        for pattern in ("kilo*.db", "opencode-*.db"):
            paths.extend(glob.glob(os.path.join(root, pattern)))
    return sorted(set(paths))


def looks_like(line: str) -> bool:
    return False  # a database, never handed over as a text file


def notes() -> list:
    """What the report must say about this run's Kilo Code figures."""
    out = []
    value = _UNFOLLOWED[0]
    if value is not None and os.environ.get(DATA_ENV) == value:
        out.append(f'{DATA_ENV} is "{value}", which {LABEL} reads as a folder relative to the '
                   f"one it was started in: Tokenmeter cannot know that folder, so it read "
                   f"{DEFAULT_DATA}/kilo instead, and {LABEL} {FILES} kept elsewhere are not "
                   "counted")
    n = len(_STATE["unsettled"])
    if n:
        out.append(f"{n:,} {LABEL} call{'' if n == 1 else 's'} from before 7.4.16 "
                   f"{'was' if n == 1 else 'were'} not counted: {'its' if n == 1 else 'their'} "
                   "record does not say whether output includes the reasoning tokens")
    return out


def reset() -> None:
    _STATE.update(unsettled=set())


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _counts(tokens):
    """(input, output, reasoning, cache read, cache write), a negative count
    read as none, or None when there is no usage block."""
    if not isinstance(tokens, dict):
        return None
    cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
    return tuple(max(0, whole(v)) for v in (
        tokens.get("input"), tokens.get("output"), tokens.get("reasoning"),
        cache.get("read"), cache.get("write")))


def _billed_output(tokens, counts, current: bool):
    """Output including reasoning, or None when the record cannot say.

    current: the row is from 7.4.16 or later, whose output excludes
    reasoning. Older rows are settled by their total (see the docstring)."""
    inp, out, reasoning, read, write = counts
    if not reasoning or current:
        return out + reasoning
    total = tokens.get("total")
    if not _number(total):
        return None
    if total == inp + read + write + out + reasoning:
        return out + reasoning
    if total == inp + read + write + out:
        return out
    return None


def _when(ms):
    if _number(ms) and ms > 0:
        try:
            return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _directory(value) -> str:
    """The session's folder as Kilo Code reads it back: stored with forward
    slashes on Windows (packages/core/src/database/path.ts 22 to 25)."""
    if not isinstance(value, str):
        return ""
    if os.name == "nt" and (re.match(r"^[A-Za-z]:/", value) or value.startswith("//")):
        return value.replace("/", "\\")
    return value


def _event(key, when, model, provider, project, session, sidechain, counts, output):
    inp, _, reasoning, read, write = counts
    provider = provider if isinstance(provider, str) else ""
    return key, {
        "when": when,
        "model": model if isinstance(model, str) else "",
        "provider": PROVIDERS.get(provider, provider),
        "project": project,
        "session": session,
        "cwd": project,
        "sidechain": sidechain,
        "source": NAME,
        "_usage": usage(input=inp, output=output, cache_read=read,
                        cache_write_5m=write, thinking=reasoning),
    }


def _load(data):
    try:
        d = json.loads(data)
    except (ValueError, TypeError):
        return None
    return d if isinstance(d, dict) else None


def _steps(con, sessions):
    """One event per step-finish row of an assistant message."""
    messages = {}
    for mid, created, data in con.execute("SELECT id, time_created, data FROM message"):
        d = _load(data)
        if d is not None and d.get("role") == "assistant":
            messages[mid] = (created, d)
    place = {}
    for pid, mid, sid, created, data in con.execute(
            "SELECT id, message_id, session_id, time_created, data FROM part "
            "WHERE data LIKE '%step-finish%' ORDER BY message_id, id"):
        d = _load(data)
        if d is None or d.get("type") != "step-finish" or mid not in messages:
            continue
        # The step's place in its message, which a copy keeps.
        place[mid] = place.get(mid, -1) + 1
        m_created, m = messages[mid]
        counts = _counts(d.get("tokens"))
        if counts is None or not any(counts):
            continue
        routed = d.get("model") if isinstance(d.get("model"), dict) else {}
        model = routed.get("modelID") or m.get("modelID")
        provider = routed.get("providerID") or m.get("providerID")
        timing = d.get("time") if isinstance(d.get("time"), dict) else {}
        current = _number(timing.get("end"))
        output = _billed_output(d["tokens"], counts, current)
        mtime = m.get("time") if isinstance(m.get("time"), dict) else {}
        started = mtime.get("created") if _number(mtime.get("created")) else m_created
        if output is None:
            _STATE["unsettled"].add(f"{NAME}:{started}:{place[mid]}:{counts}")
            continue
        if current:
            when = _when(timing["end"])
        else:
            # A copy's row is dated when it was copied; its message keeps the
            # original's completion, which no step of the original is after.
            done = mtime.get("completed")
            stamps = [t for t in (created, done) if _number(t) and t > 0]
            when = _when(min(stamps)) if stamps else None
        if not _number(started):
            key = f"{NAME}:part:{pid}"
        else:
            key = (f"{NAME}:{int(started)}:{place[mid]}:{provider}:{model}:"
                   + ":".join(str(c) for c in counts))
        directory, parent = sessions.get(sid, ("", None))
        path = m.get("path") if isinstance(m.get("path"), dict) else {}
        cwd = path.get("cwd") if isinstance(path.get("cwd"), str) and path.get("cwd") else directory
        yield _event(key, when, model, provider, cwd, sid, parent is not None, counts, output)


def _rows(con, sessions, v1_ids):
    """One event per assistant row of the event-sourced layout."""
    for mid, sid, created, data in con.execute(
            "SELECT id, session_id, time_created, data FROM session_message "
            "WHERE type = 'assistant'"):
        if mid in v1_ids:
            continue
        d = _load(data)
        if d is None:
            continue
        counts = _counts(d.get("tokens"))
        if counts is None or not any(counts):
            continue
        model = d.get("model") if isinstance(d.get("model"), dict) else {}
        mtime = d.get("time") if isinstance(d.get("time"), dict) else {}
        when = _when(mtime.get("created")) or _when(created)
        directory, parent = sessions.get(sid, ("", None))
        yield _event(f"{NAME}:{mid}", when, model.get("id"), model.get("providerID"),
                     directory, sid, parent is not None, counts, counts[1] + counts[2])


def records(path: str):
    con, tmp = _connect(path)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        sessions = {}
        if "session" in tables:
            for sid, directory, parent in con.execute(
                    "SELECT id, directory, parent_id FROM session"):
                sessions[sid] = (_directory(directory), parent)
        v1_ids = set()
        if "message" in tables and "part" in tables:
            v1_ids = {r[0] for r in con.execute("SELECT id FROM message")}
            yield from _steps(con, sessions)
        if "session_message" in tables:
            yield from _rows(con, sessions, v1_ids)
    except sqlite3.Error:
        return
    finally:
        con.close()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
