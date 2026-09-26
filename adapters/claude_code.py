"""Claude Code transcripts. Verified.

Claude Code writes one JSONL transcript per session under its projects folder,
one line per event. Lines that carry an API response have a `message` with an
`id`, a `model` and Anthropic's own `usage` block, which is the shape the
engine prices natively, so nothing here translates tokens.

Verified against real transcripts and against Claude Code's own
`total_cost_usd` to ten decimal places. The test suite guards every way this
reader has been wrong before.
"""

from __future__ import annotations

import glob
import json
import os

from .common import parse_time

NAME = "claude-code"
LABEL = "Claude Code"
STATUS = "verified"
PROVIDER = "anthropic"
FILES = "transcripts"
FILE = "transcript"


def default_roots() -> list:
    """Claude Code's projects folder: $CLAUDE_CONFIG_DIR/projects, else
    ~/.claude/projects. The override is documented by Claude Code and moves
    everything it writes, transcripts included."""
    base = os.environ.get("CLAUDE_CONFIG_DIR", "").strip() or "~/.claude"
    return [os.path.join(os.path.expanduser(base), "projects")]


def files(roots: list, project: str = "", session: str = "") -> list:
    """Every transcript under the given folders, at any depth.

    The single place that knows the on-disk layout. Subagent transcripts live
    in <session>/subagents/agent-*.jsonl, a level deeper than the session
    files, so a "*/*.jsonl" glob silently drops every subagent's tokens, which
    are real API calls and real money.
    """
    paths = []
    for root in roots:
        paths.extend(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
    if session:
        # The session's own transcript, plus the subagents it spawned.
        paths = [p for p in paths
                 if os.path.basename(p).startswith(session)
                 or f"{os.sep}{session}" in p and f"{os.sep}subagents{os.sep}" in p]
    if project:
        paths = [p for p in paths if project.lower() in p.lower()]
    return paths


def looks_like(line: str) -> bool:
    """Whether a line from an unknown file is a Claude Code transcript line."""
    return '"sessionId"' in line or ('"message"' in line and '"payload"' not in line)


def dedup_key(msg: dict, record: dict):
    """One API response can be written to disk many times, once per content
    block and again whenever a session is resumed. The message id is what
    identifies the response itself."""
    return msg.get("id") or f"{record.get('requestId')}|{record.get('uuid')}"


def records(path: str):
    """Yield (key, event) for every line that carries an API response.

    The same key is yielded more than once when a response was written more
    than once. The engine keeps the first sighting's attribution and the
    largest usage block, because the early copies of a streamed reply carry an
    output count that is still climbing.
    """
    parent = os.path.dirname(path)
    if os.path.basename(parent) == "subagents":
        # <project>/<session>/subagents/agent-*.jsonl
        session = os.path.basename(os.path.dirname(parent))
        project = os.path.basename(os.path.dirname(os.path.dirname(parent)))
        is_subagent = True
    else:
        session = os.path.basename(path)[:-6]
        project = os.path.basename(parent)
        is_subagent = False
    try:
        fh = open(path, "r", encoding="utf-8", errors="ignore")
    except OSError:
        return
    with fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            msg = d.get("message")
            if not isinstance(msg, dict):
                continue
            usage = msg.get("usage")
            if not isinstance(usage, dict):
                continue
            model = msg.get("model") or ""
            if not model or model.startswith("<"):
                continue  # synthetic, no API call was made
            yield dedup_key(msg, d), {
                "when": parse_time(d.get("timestamp")),
                "model": model,
                "provider": PROVIDER,
                "project": project,
                "session": session,
                "cwd": d.get("cwd") or "",
                "sidechain": is_subagent or bool(d.get("isSidechain")),
                "source": NAME,
                "_usage": usage,
            }
