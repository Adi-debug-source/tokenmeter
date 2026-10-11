"""OpenAI Codex CLI sessions. Unverified.

Built from the published source of openai/codex (read at commit e72da2b, 26
September 2026, and at tags rust-v0.30.0 to rust-v0.45.0) and checked against
the Codex parser in ccusage. It has not yet been run against real session
files, so every report that uses it says so. If a figure looks wrong, please
open an issue with a sample.

What Codex writes, and what this reader does with it:

  - Sessions live in $CODEX_HOME/sessions/YYYY/MM/DD/rollout-*.jsonl, and in
    $CODEX_HOME/archived_sessions/. CODEX_HOME defaults to ~/.codex.
  - Each line is {"timestamp", "type", "payload"}. Usage arrives as an
    event_msg whose payload type is "token_count", carrying the last
    response's usage and the thread's running total.
  - The same token_count is re-sent whenever rate limits refresh, with an
    unchanged total, and sometimes with "info": null. A token_count counts only
    when the running total has moved.
  - Current versions also write a token_usage_record for every response, with
    the same numbers. Only one stream may be counted, or every figure doubles;
    this reader counts token_count, the stream every generation has.
  - Codex follows OpenAI's convention: input_tokens INCLUDES cached reads and
    cache writes, and output_tokens INCLUDES reasoning. Uncached input is
    input minus both, which is what the engine calls input.
  - The model comes from the latest turn_context line (Codex 0.36 and later),
    else from thread_settings_applied. Sessions from before 0.36 record no
    model at all; they are priced as gpt-5, Codex's default at the time, and
    the report says how many calls that applies to.
  - Fast mode ("priority" or "fast" service tier) is state carried forward from
    thread_settings_applied events, not recorded per call.
  - Codex compresses sessions older than seven days to .jsonl.zst. Python has
    no zstd reader before 3.14, so those are read with the `zstd` command or
    the `zstandard` package when either is installed, and counted and reported
    when neither is. The command is looked for on PATH and then where Homebrew
    puts it (ZSTD_PATHS), because the menu bar runs under launchd, whose PATH
    has no Homebrew folder. A compressed file that will not decode, because it
    is cut short or corrupt (Codex may still be compressing it), is skipped
    and reported as possibly damaged rather than ending the run. The ledger
    keeps every call it has already seen, so a session read before it was
    compressed is never lost.
"""

from __future__ import annotations

import glob
import io
import json
import os
import shutil
import subprocess

from .claude_code import project_matches
from .common import parse_time, usage

NAME = "codex"
LABEL = "Codex"
STATUS = "unverified"
PROVIDER = "openai"
FILES = "sessions"
FILE = "session"

# Codex before 0.36 recorded no model. Its default then was gpt-5.
LEGACY_MODEL = "gpt-5"

# Provider ids Codex records, mapped to Tokenmeter's price tables. Anything
# else is passed through as written, and priced only if a table or the online
# lookup knows it; a local model (ollama, lmstudio) is not a billed API call.
PROVIDERS = {"openai": "openai"}

# Where Homebrew puts the zstd command, on Apple silicon and on Intel. The menu
# bar runs under launchd, whose PATH has neither, so PATH alone is not enough.
ZSTD_PATHS = ("/opt/homebrew/bin/zstd", "/usr/local/bin/zstd")

# Per run. "guessed" holds the keys of calls priced as LEGACY_MODEL, so a
# call read from both sessions/ and archived_sessions/ is counted once.
_STATE = {"guessed": set(), "compressed_unread": 0, "compressed_damaged": 0}


def default_roots() -> list:
    homes = os.environ.get("CODEX_HOME", "").strip() or "~/.codex"
    roots = []
    for home in homes.replace(",", os.pathsep).split(os.pathsep):
        if home.strip():
            home = os.path.expanduser(home.strip())
            roots += [os.path.join(home, "sessions"), os.path.join(home, "archived_sessions")]
    return roots


def _first_meta(path: str) -> dict:
    for obj in _lines(path, limit=5):
        if obj.get("type") == "session_meta":
            return obj.get("payload") or {}
    return {}


def files(roots: list, project: str = "", session: str = "") -> list:
    paths = []
    for root in roots:
        for pattern in ("*.jsonl", "*.jsonl.zst"):
            paths.extend(glob.glob(os.path.join(root, "**", pattern), recursive=True))
    if session:
        paths = [p for p in paths if session in os.path.basename(p)]
    if project:
        paths = [p for p in paths if project_matches(project, _first_meta(p).get("cwd") or "")]
    return sorted(paths)


def looks_like(line: str) -> bool:
    return '"payload"' in line and ('"session_meta"' in line or '"turn_context"' in line
                                    or '"token_count"' in line)


def notes() -> list:
    """What the report must say about this run's Codex figures."""
    out = []
    if _STATE["guessed"]:
        n = len(_STATE["guessed"])
        out.append(f"{n:,} Codex call{'' if n == 1 else 's'} came from sessions older than "
                   f"Codex 0.36, which record no model, and {'was' if n == 1 else 'were'} "
                   f"priced as {LEGACY_MODEL}, Codex's default at the time")
    if _STATE["compressed_unread"]:
        n = _STATE["compressed_unread"]
        out.append(f"{n:,} compressed Codex session{'' if n == 1 else 's'} (.jsonl.zst) could "
                   "not be read. Install zstd (brew install zstd) to include them")
    if _STATE["compressed_damaged"]:
        n = _STATE["compressed_damaged"]
        out.append(f"{n:,} compressed Codex session{'' if n == 1 else 's'} (.jsonl.zst) could "
                   f"not be read; the file{'' if n == 1 else 's'} may be damaged or still "
                   "being compressed")
    return out


def reset() -> None:
    _STATE.update(guessed=set(), compressed_unread=0, compressed_damaged=0)


def _zstd_tool():
    """The zstd command: the one on PATH, else the first of ZSTD_PATHS that
    can be run, else None."""
    tool = shutil.which("zstd")
    if tool:
        return tool
    for path in ZSTD_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class _Damaged(Exception):
    """A .jsonl.zst that a zstd decoder could not read: cut short, corrupt, or
    still being written."""


def _decoder():
    """A function from a .zst file's path to its bytes, or None when this
    machine has no zstd decoder: Python's own (3.14 and later), the zstandard
    package, or the zstd command, in that order."""
    try:
        from compression import zstd  # Python 3.14 and later
    except ImportError:
        pass
    else:
        def read(path):
            with zstd.open(path, "rb") as f:
                return f.read()
        return read
    try:
        import zstandard
    except ImportError:
        pass
    else:
        def read(path):
            with open(path, "rb") as f:
                return zstandard.ZstdDecompressor().stream_reader(f).read()
        return read
    tool = _zstd_tool()
    if tool:
        def read(path):
            return subprocess.run([tool, "-dc", path], capture_output=True, timeout=30,
                                  check=True).stdout
        return read
    return None


def _decompress(path: str):
    """The text of a .jsonl.zst file, or None when nothing here can read it.

    Raises _Damaged when a decoder exists but the file will not decode, which
    is not the same problem: installing zstd would not help.
    """
    read = _decoder()
    if read is None:
        return None
    try:
        return read(path).decode("utf-8", "ignore")
    except Exception as e:  # EOFError, ZstdError, OSError, a failed zstd command
        raise _Damaged(path) from e


def _lines(path: str, limit: int = 0, text: str | None = None):
    """Parsed JSON objects from a session file, compressed or not.

    A caller that has already decompressed a .jsonl.zst passes its text, so it
    is decompressed once. The text is split into lines exactly as a plain file
    is read: str.splitlines() would also split at a raw U+2028 inside a JSON
    string, which Codex writes unescaped.
    """
    if text is None and path.endswith(".zst"):
        try:
            text = _decompress(path)
        except _Damaged:
            return
        if text is None:
            return
    if text is not None:
        source = io.StringIO(text, newline=None)
    else:
        try:
            source = open(path, "r", encoding="utf-8", errors="ignore")
        except OSError:
            return
    try:
        for n, line in enumerate(source):
            if limit and n >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                yield obj
    finally:
        source.close()


def _counts(u: dict) -> tuple:
    """(input, cached, cache write, output, reasoning) from a TokenUsage."""
    def n(k):
        v = u.get(k)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
    return (n("input_tokens"), n("cached_input_tokens"), n("cache_write_input_tokens"),
            n("output_tokens"), n("reasoning_output_tokens"))


def _minus(a: tuple, b: tuple) -> tuple:
    return tuple(max(0, x - y) for x, y in zip(a, b))


def records(path: str):
    """Yield (key, event) for every response in one session file."""
    text = None
    if path.endswith(".zst"):
        try:
            text = _decompress(path)
        except _Damaged:
            _STATE["compressed_damaged"] += 1
            return
        if text is None:
            _STATE["compressed_unread"] += 1
            return
    name = os.path.basename(path)
    thread = name.split(".")[0][len("rollout-") + 20:] if name.startswith("rollout-") else name
    session = root = thread
    project, model, provider, speed = "", "", PROVIDER, "standard"
    previous = None       # the running total at the last counted token_count
    searches = 0          # web searches since the last counted response

    for obj in _lines(path, text=text):
        kind = obj.get("type")
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        if kind == "session_meta":
            session = payload.get("id") or session
            root = payload.get("session_id") or session
            project = payload.get("cwd") or project
            if payload.get("model_provider"):
                provider = PROVIDERS.get(payload["model_provider"], payload["model_provider"])
        elif kind == "turn_context":
            model = payload.get("model") or model
            project = payload.get("cwd") or project
        elif kind == "response_item":
            if payload.get("type") == "web_search_call" and payload.get("status", "completed") == "completed":
                searches += 1
        elif kind == "event_msg":
            ptype = payload.get("type")
            if ptype == "thread_settings_applied":
                ts = payload.get("thread_settings") or {}
                model = ts.get("model") or model
                if ts.get("model_provider_id"):
                    provider = PROVIDERS.get(ts["model_provider_id"], ts["model_provider_id"])
                if "service_tier" in ts:
                    tier = str(ts.get("service_tier") or "").lower()
                    speed = "fast" if tier in ("fast", "priority") else "standard"
            elif ptype == "token_count":
                info = payload.get("info")
                if not isinstance(info, dict):
                    continue  # a rate-limit refresh with no usage in it
                total = info.get("total_token_usage")
                last = info.get("last_token_usage")
                total_c = _counts(total) if isinstance(total, dict) else None
                if total_c is not None and total_c == previous:
                    continue  # the same snapshot re-sent
                if isinstance(last, dict) and (total_c is None or total_c != previous):
                    got = _counts(last)
                elif total_c is not None:
                    got = _minus(total_c, previous or (0, 0, 0, 0, 0))
                else:
                    continue
                if total_c is not None:
                    previous = total_c
                inp, cached, written, out, reasoning = got
                if not any((inp, cached, written, out)):
                    continue
                cached = min(cached, inp)
                written = min(written, inp - cached)
                # Keyed on the thread's root and the running total, so a
                # forked thread that replays its parent's totals, or a copy of
                # the same file in archived_sessions, counts once.
                key = f"codex:{root}:{':'.join(str(x) for x in (total_c or got))}"
                use_model = model
                if not use_model:
                    use_model = LEGACY_MODEL
                    _STATE["guessed"].add(key)
                yield key, {
                    "when": parse_time(obj.get("timestamp")),
                    "model": use_model,
                    "provider": provider,
                    "project": project,
                    "session": session,
                    "cwd": project,
                    "sidechain": False,
                    "source": NAME,
                    "_usage": usage(input=inp - cached - written, output=out, cache_read=cached,
                                    cache_write_5m=written, thinking=reasoning,
                                    web_searches=searches, speed=speed),
                }
                searches = 0
