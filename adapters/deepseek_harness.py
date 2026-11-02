"""DeepSeek Harness sessions. Unverified.

Built from the published source of deepseek-ai/deepseek-harness (read at
commit ce7073d, 30 October 2026, Session format 4, with its format references
for 0 to 3) and, for the routes it sends through pi-ai, @earendil-works/pi-ai
1.3.0 (the version its pnpm-lock.yaml pins). Its routes and subagents were
read again at the same commit, still the latest, on 2 November 2026. It has
not yet been run against real session files, so every report that uses it
says so. If a figure looks wrong, please open an issue with a sample.

What DeepSeek Harness writes, and what this reader does with it:

  - Sessions live in $DSH_HOME/sessions/--<project>--/<session id>/, one
    folder per session. DSH_HOME defaults to ~/.dsh (a blank value counts as
    unset). A profile's cordis.patch.yml can name another root; that is not
    read here.
  - Each folder holds one file per Session format generation:
    session.jsonl (format 0) or session.vN.jsonl, with .zstd added under the
    default compression, which writes one checksummed Zstandard frame per
    append. Opening an older session writes a migrated successor and keeps
    its predecessors, so only the highest generation in a folder is read.
  - The first line is a header {"type": "session", "version", "id",
    "createdAt", "cwd", "delegationDepth", ...}; every later line is one
    event {"type", "seq", "time" (Unix milliseconds), "data"}.
  - One model call settles as one assistant/message event, whose data.usage
    (or, failing that, the last "usage" chunk in data.stream) is that call's
    TokenUsage and whose data.message.source names the route ("provider")
    and model as requested. Its data.message.id is a UUID kept through
    migrations and copied verbatim into forks, so it is the key: a fork's
    inherited prefix (the events before its last session/end-seed marked
    inherited, or the header's seedLength in formats 0 and 1) counts once
    with its parent, and is credited to the parentSession its header names,
    when it names one.
  - A call that ended in an error settles as assistant/attempt, with no model
    and the usage, if any arrived, as a "usage" chunk in data.stream. Its
    route is the latest request/context: the agent loop is the only writer of
    that event, one agent owns a session's log, and it logs one before any
    request whose route differs from the latest (agent.ts buildRequest), then
    settles that request before building the next. A usage of all zeros
    (pi-ai's report of a transport failure) is not a call. Formats 0 and 1
    have no assistant/attempt: a failed call there is a run of assistant/chunk
    events that no assistant/message cites, closed as the harness's own
    migration to format 2 closes it, and is read the same way.
  - Compaction is its own call, metered on compaction/summary (compact/summary
    in an early format 0) with its provider, model and usage, keyed on
    compactionId. Only a summary marked llmStreamCall is one call through the
    harness's own model client; another summariser's usage may cover any
    number of calls, so it is not counted and a note says how many. A
    summarisation call that failed is not logged.
  - TokenUsage is disjoint, as the harness defines it ("Counts are
    DISJOINT", llm/src/types.ts; reasoning an "output subset" in
    token-meter): inputTokens is uncached input, cacheReadTokens and
    cacheWriteTokens are separate, outputTokens includes any reasoning.
    DeepSeek's own routes
    (deepseek-official, deepseek-account) call DeepSeek's Anthropic-format
    endpoint, whose input_tokens "excludes cache hits", and copy
    input_tokens, cache_read_input_tokens, cache_creation_input_tokens and
    output_tokens across as they come. pi-ai reports input net of cache reads
    and writes, and output with reasoning, for every API it speaks.
    reasoningTokens is never filled in by either at this commit.
  - Each call has one timestamp, its own event's time: when it settled, after
    its last streamed chunk. The time its request was sent is not recorded
    (request/context is logged only when the route changes); the first
    chunk's arrival is, inside data.stream. DeepSeek's page does not say
    which moment decides peak or off-peak, so a call is priced at one rate,
    exactly, unless it was in flight across 01:00, 04:00, 06:00 or 10:00 UTC
    on a weekday, when the rate is the one in force as it settled.
  - A cache write's lifetime is not recorded: pi-ai writes one-hour entries
    when a profile's cacheRetention is "long" or PI_CACHE_RETENTION=long was
    set, and neither reaches the log. DeepSeek bills a write as ordinary
    input whatever its lifetime, so its routes' calls are exact; a call on
    any other route that wrote to a cache is not counted, and a note says
    how many.
  - The session-title and DeepSeek web-search requests are logged before
    dispatch with no usage, so they are not counted, and a note says how
    many there were. So is a call the user interrupted before its usage
    arrived.
  - A subagent the harness hands to another agent's process (Claude Code,
    Codex, an ACP agent, OAR, or a separate harness through its SDK) records
    no usage in this log, so nothing here is counted twice. But the Claude
    Code and Codex subagents keep no log of their own either: Claude Code's
    runs with persistSession: false (subagent-claude-code src/run.ts:330),
    Codex's in an ephemeral thread (subagent-codex README.md:95). Their calls
    are missing, from this report and from every other. The parent logs each
    such run as a subagent/catalog event with mode "external" and the run's
    childId (packages/subagent/subagent/src/catalog.ts and manager.ts
    startExternal), but not which agent ran it, so a note counts those
    runs, once each, and says their calls may be missing. A subagent the
    harness runs in its own process writes a session of its own here, and
    is counted.
  - Compressed sessions are read frame by frame with Python 3.14's own zstd
    or the zstandard package, else as a whole with the zstd command, as
    Codex's reader finds them, and are counted and reported when there is
    none. One that ends in a torn frame (a crash, or a write in progress) is
    read up to it and reported. The suffix is .jsonl.zstd, not Codex's
    .jsonl.zst.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import re

from . import codex as _codex
from .claude_code import project_matches
from .common import usage, whole

NAME = "deepseek-harness"
LABEL = "DeepSeek Harness"
STATUS = "unverified"
PROVIDER = "deepseek"
FILES = "sessions"
FILE = "session"

# Provider routes as the harness records them, where they differ from
# Tokenmeter's table names. deepseek-official (API key) and deepseek-account
# (DeepSeek login) are its own; the rest are pi-ai's (1.3.0's catalogue).
# A plan route that serves only its maker's models is priced by the maker's
# table: openai-codex (ChatGPT sign-in, GPT models only), kimi-coding (Kimi
# Code plan, Kimi models only), and Xiaomi's MiMo routes outside China.
# Routes that serve several makers (github-copilot, openrouter and the other
# gateways), and the China routes (moonshotai-cn, minimax-cn, zai-coding-cn,
# xiaomi-token-plan-cn), whose makers bill from a separate yuan price list,
# pass through, as does anything else, and are priced by a table or the
# online lookup. minimax and zai already carry their tables' names.
PROVIDERS = {"deepseek-official": "deepseek", "deepseek-account": "deepseek",
             "moonshotai": "moonshot", "google-vertex": "google",
             "openai-codex": "openai", "kimi-coding": "moonshot", "xiaomi": "mimo",
             "xiaomi-token-plan-ams": "mimo", "xiaomi-token-plan-sgp": "mimo"}

# session.jsonl is format 0; session.v1.jsonl and later carry their number.
_GENERATION = re.compile(r"^session(?:\.v([1-9][0-9]*))?\.jsonl(\.zstd)?$")

# Requests the harness logs before dispatch and never meters.
_UNMETERED = ("session/title-llm-request", "web/deepseek-search-llm-request")

# Formats 0 and 1: the events that end a run of assistant/chunk events, as
# the migration to format 2 ends one (session-format-v1-to-v2 closesAttempt),
# and the packed rows that hold a run's text, reasoning and tool-call deltas.
_CLOSES_RUN = ("turn/start", "turn/end", "step/end", "llm/retry", "llm/retry-started")
_PACKED = ("text-chunks", "reasoning-chunks", "tool-call-chunks")


def _fresh() -> dict:
    return {"compressed_unread": 0, "compressed_damaged": 0, "lifetime_unknown": set(),
            "unmetered": set(), "interrupted": set(), "summariser": set(), "external": set()}


_STATE = _fresh()


def default_roots() -> list:
    home = os.environ.get("DSH_HOME", "")
    home = home if home.strip() else "~/.dsh"
    return [os.path.join(os.path.abspath(os.path.expanduser(home)), "sessions")]


def _decode_segment(segment: str) -> str:
    """A session id from its folder name: ~XXXX is one UTF-16 code unit."""
    return re.sub(r"~([0-9A-F]{4})", lambda m: chr(int(m.group(1), 16)), segment)


def files(roots: list, project: str = "", session: str = "") -> list:
    paths = []
    for root in roots:
        for folder in glob.glob(os.path.join(root, "*", "*")):
            if session and session not in _decode_segment(os.path.basename(folder)):
                continue
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            found = []
            for name in names:
                m = _GENERATION.match(name)
                if m:
                    found.append((int(m.group(1) or 0), name))
            if found:
                paths.append(os.path.join(folder, max(found)[1]))
    if project:
        paths = [p for p in paths if project_matches(project, _header(p).get("cwd") or "")]
    return sorted(paths)


def _header(path: str) -> dict:
    if path.endswith(".zstd"):
        text = _codex._head(path, 1) or ""
    else:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.readline()
        except OSError:
            return {}
    try:
        obj = json.loads(text)
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) and obj.get("type") == "session" else {}


def looks_like(line: str) -> bool:
    try:
        obj = json.loads(line)
    except ValueError:
        return False
    if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
        return False
    if obj["type"] == "session":
        # Every format's header has these; formats 0 and 1 have seedLength
        # where later ones have isSeeded.
        return (isinstance(obj.get("version"), int) and "delegationDepth" in obj
                and "createdAt" in obj and isinstance(obj.get("id"), str))
    return ("/" in obj["type"] and isinstance(obj.get("seq"), int)
            and isinstance(obj.get("time"), int) and "data" in obj)


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def notes() -> list:
    out = []
    n = _STATE["compressed_unread"]
    if n:
        out.append(f"{n:,} compressed DeepSeek Harness session{_plural(n, '', 's')} (.jsonl.zstd) "
                   "could not be read. Install zstd (brew install zstd) to include them")
    n = _STATE["compressed_damaged"]
    if n:
        out.append(f"{n:,} compressed DeepSeek Harness session{_plural(n, '', 's')} (.jsonl.zstd) "
                   f"ended in a damaged or unfinished frame; {_plural(n, 'its', 'their')} calls "
                   "before it were read")
    n = len(_STATE["lifetime_unknown"])
    if n:
        out.append(f"{n:,} DeepSeek Harness call{_plural(n, '', 's')} on a route other than "
                   f"DeepSeek's wrote to a prompt cache and {_plural(n, 'is', 'are')} not counted: "
                   "the harness does not record whether a write lasts five minutes or an hour")
    n = len(_STATE["summariser"])
    if n:
        out.append(f"{n:,} DeepSeek Harness compaction{_plural(n, '', 's')} by another summariser "
                   f"{_plural(n, 'is', 'are')} not counted: its usage is not one call's")
    n = len(_STATE["unmetered"])
    if n:
        out.append(f"{n:,} DeepSeek Harness title or web-search request{_plural(n, '', 's')} "
                   f"{_plural(n, 'is', 'are')} not counted: the harness records no usage for them")
    n = len(_STATE["interrupted"])
    if n:
        out.append(f"{n:,} interrupted DeepSeek Harness call{_plural(n, '', 's')} "
                   f"{_plural(n, 'is', 'are')} not counted: "
                   f"{_plural(n, 'it', 'they')} stopped before the provider reported usage")
    n = len(_STATE["external"])
    if n:
        out.append(f"{n:,} DeepSeek Harness subagent run{_plural(n, '', 's')} went to another "
                   "agent's process, which the session does not name. A Claude Code or Codex "
                   "subagent keeps no log, so its calls are missing; another agent's are counted "
                   "only where it keeps a log Tokenmeter reads")
    return out


def reset() -> None:
    _STATE.update(_fresh())


def _frame_decoder():
    """(a new one-frame decompressor, its error class), from Python 3.14's own
    zstd or the zstandard package, in the order Codex's _decoder() tries
    them; None when neither is here."""
    try:
        from compression import zstd  # Python 3.14 and later
    except ImportError:
        pass
    else:
        return zstd.ZstdDecompressor, zstd.ZstdError
    try:
        import zstandard
    except ImportError:
        return None
    return (lambda: zstandard.ZstdDecompressor().decompressobj()), zstandard.ZstdError


def _frames(path: str, new, error):
    """(bytes, damaged), one frame at a time. A decompressor stops at the end
    of its frame, so the harness's one frame per append needs one each; and
    a torn last frame keeps every whole frame before it, which a stream
    reader that fails on the torn one would lose with its last block."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return b"", True
    out = []
    try:
        while data:
            frame = new()
            out.append(frame.decompress(data))
            if not frame.eof:
                return b"".join(out), True
            data = frame.unused_data
    except error:
        return b"".join(out), True
    return b"".join(out), False


def _decompress(path: str):
    """(text, damaged): the text of a .jsonl.zstd, read as far as it decodes,
    whole lines only; text is None when nothing here can read it."""
    decoder = _frame_decoder()
    if decoder is not None:
        data, damaged = _frames(path, *decoder)
    else:
        open_ = _codex._decoder()     # the zstd command: every frame, failing at a torn one
        if open_ is None:
            return None, False
        chunks, damaged = [], False
        try:
            with open_(path) as f:
                while True:
                    block = f.read(1 << 16)
                    if not block:
                        break
                    chunks.append(block)
        except Exception:  # OSError, a failed zstd command
            damaged = True
        data = b"".join(chunks)
    if damaged:
        data = data[:data.rfind(b"\n") + 1]
    return data.decode("utf-8", "ignore"), damaged


def _rows(path: str):
    if path.endswith(".zstd"):
        text, damaged = _decompress(path)
        if text is None:
            _STATE["compressed_unread"] += 1
            return
        if damaged:
            _STATE["compressed_damaged"] += 1
        lines = text.split("\n")
    else:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore", newline="\n") as f:
                lines = f.read().split("\n")
        except OSError:
            return
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue  # a torn last line
        if isinstance(obj, dict):
            yield obj


def _when(ms):
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not math.isfinite(ms):
        return None
    try:
        return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _counts(u) -> tuple:
    """(uncached input, cache read, cache write, output, reasoning) from one
    TokenUsage."""
    if not isinstance(u, dict):
        return (0, 0, 0, 0, 0)
    return tuple(whole(u.get(k)) for k in ("inputTokens", "cacheReadTokens", "cacheWriteTokens",
                                            "outputTokens", "reasoningTokens"))


def _stream_usage(stream):
    """The last "usage" chunk record in a compact stream, as the harness's
    lastAssistantStreamChunk() finds it, or None."""
    last = None
    for rec in stream if isinstance(stream, list) else []:
        if (isinstance(rec, dict) and rec.get("type") == "chunk"
                and isinstance(rec.get("chunk"), dict) and rec["chunk"].get("type") == "usage"):
            last = rec
    return last


def _attempt_key(usage_time, turn, step, got) -> str:
    # No id: the usage chunk's time, the step and the counts are the same in
    # every copy of this attempt (a fork, a migration) and nowhere else.
    return (f"{NAME}:attempt:{usage_time}:{turn}:{step}:"
            + ":".join(str(x) for x in got[:4]))


def records(path: str):
    """Yield (key, event) for every metered model call in one session file."""
    head, found = {}, []
    sid, project = "", ""
    cwd = ""
    route = ("", "")
    cut = None            # the seq of the last tagged session/end-seed
    legacy = False        # formats 0 and 1: failed calls are runs of assistant/chunk
    run = None            # the open run there, with the route and folder its usage came under

    def close_run():
        nonlocal run
        if run is not None and run["usage"] is not None and run["route"][1]:
            rec = run["usage"]
            got = _counts(rec["chunk"].get("usage"))
            found.append((_attempt_key(rec.get("time"), run["turn"], run["step"], got), run["seq"],
                          run["time"], run["route"][0], run["route"][1], got, run["cwd"]))
        run = None

    for obj in _rows(path):
        kind = obj.get("type")
        if kind == "session" and not head:
            head = obj
            sid = obj.get("id") if isinstance(obj.get("id"), str) else ""
            project = cwd = obj.get("cwd") if isinstance(obj.get("cwd"), str) else ""
            legacy = isinstance(obj.get("version"), int) and obj["version"] < 2
            continue
        data = obj.get("data")
        if not isinstance(data, dict):
            continue
        seq = obj.get("seq")
        if legacy:
            if kind == "assistant/chunk" or kind in _PACKED:
                turn, step = data.get("turn"), data.get("step")
                if run is not None and (run["done"] or (run["turn"], run["step"]) != (turn, step)):
                    close_run()
                if run is None:
                    run = {"turn": turn, "step": step, "usage": None, "time": None,
                           "seq": seq, "done": False, "route": route, "cwd": cwd}
                if kind == "assistant/chunk":
                    chunk = data.get("chunk") if isinstance(data.get("chunk"), dict) else {}
                    run["time"], run["seq"] = obj.get("time"), seq
                    if chunk.get("type") == "usage":
                        run["usage"] = {"time": obj.get("time"), "chunk": chunk}
                        run["route"], run["cwd"] = route, cwd
                    elif chunk.get("type") == "finish":
                        run["done"] = True
                continue
            if kind in _CLOSES_RUN:
                close_run()
        if kind == "working-directory/change" and isinstance(data.get("cwd"), str):
            cwd = data["cwd"]
        elif kind == "request/context":
            route = (str(data.get("provider") or ""), str(data.get("model") or ""))
        elif kind == "session/end-seed" and data.get("inherited") is True:
            cut = seq
        elif kind in _UNMETERED:
            _STATE["unmetered"].add(f"{kind}:{obj.get('time')}")
        elif kind == "subagent/catalog" and data.get("mode") == "external":
            run_id = data.get("childId")
            if isinstance(run_id, str) and run_id:
                _STATE["external"].add(run_id)   # a fork's copy has the same childId
        elif kind == "assistant/message":
            if legacy and run is not None:
                cited = obj.get("sourceEventSeqs")
                if ((run["turn"], run["step"]) == (data.get("turn"), data.get("step"))
                        and not (isinstance(cited, list) and not cited)):
                    run = None            # the run this message settles
                else:
                    close_run()
            message = data.get("message") if isinstance(data.get("message"), dict) else {}
            source = message.get("source") if isinstance(message.get("source"), dict) else {}
            mid = message.get("id")
            key = f"{NAME}:{mid}" if isinstance(mid, str) and mid else f"{NAME}:{sid}:{seq}"
            u = data.get("usage")
            if not isinstance(u, dict):
                last = _stream_usage(data.get("stream"))
                u = last["chunk"].get("usage") if last else None
            if u is None and data.get("interrupted") is True:
                _STATE["interrupted"].add(key)
            found.append((key, seq, obj.get("time"), str(source.get("provider") or ""),
                          str(source.get("model") or ""), _counts(u), cwd))
        elif kind == "assistant/attempt":
            last = _stream_usage(data.get("stream"))
            if last is None or not route[1]:
                continue
            got = _counts(last["chunk"].get("usage"))
            found.append((_attempt_key(last.get("time"), data.get("turn"), data.get("step"), got),
                          seq, obj.get("time"), route[0], route[1], got, cwd))
        elif kind in ("compaction/summary", "compact/summary"):
            cid = data.get("compactionId")
            got = _counts(data.get("usage"))
            key = (f"{NAME}:compaction:{cid}" if isinstance(cid, str) and cid
                   else f"{NAME}:compaction:{obj.get('time')}:" + ":".join(str(x) for x in got[:4]))
            if data.get("llmStreamCall") is not True:
                if any(got[:4]):
                    _STATE["summariser"].add(key)
                continue
            found.append((key, seq, obj.get("time"), str(data.get("provider") or ""),
                          str(data.get("model") or ""), got, cwd))
    if legacy:
        close_run()        # as the migration closes a run left open at the end

    if cut is None and isinstance(head.get("seedLength"), int):
        cut = head["seedLength"]      # formats 0 and 1 kept the cut in the header
    child = head.get("origin") == "subagent"
    parent = head.get("parentSession") if isinstance(head.get("parentSession"), str) else ""
    for key, seq, ms, route_name, model, got, where in found:
        inp, cached, written, out, reasoning = got
        if not any((inp, cached, written, out)):
            continue  # no usage reported, or a failure that billed nothing
        provider = PROVIDERS.get(route_name, route_name)
        if written and provider != "deepseek":
            _STATE["lifetime_unknown"].add(key)
            continue
        inherited = cut is not None and isinstance(seq, int) and seq < cut
        yield key, {
            "when": _when(ms),
            "model": model,
            "provider": provider,
            "project": project,
            "session": (parent or sid) if inherited else sid,
            "cwd": where,
            "sidechain": child and not inherited,
            "source": NAME,
            "_usage": usage(input=inp, output=out, cache_read=cached, cache_write_5m=written,
                            thinking=min(reasoning, out)),
        }
