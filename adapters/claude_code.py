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
import re

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
    files, and workflow agents' in <session>/subagents/workflows/<id>/, so a
    "*/*.jsonl" glob silently drops every agent's tokens, which are real API
    calls and real money.
    """
    paths = []
    for root in roots:
        paths.extend(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))
    if session:
        # The session's own transcript, plus the agents it started.
        paths = [p for p in paths
                 if os.path.basename(p).startswith(session)
                 or f"{os.sep}{session}" in p and f"{os.sep}subagents{os.sep}" in p]
    if project:
        paths = [p for p in paths if project_matches(project, _where(p)[0])]
    return paths


def slug(text: str) -> str:
    """A working directory as Claude Code names its project folder: every
    character that is not a letter or digit becomes "-", so /Users/sam/code/My
    App becomes -Users-sam-code-My-App."""
    return re.sub(r"[^A-Za-z0-9]", "-", text)


def project_matches(wanted: str, project: str) -> bool:
    """Whether --project's text names this project, ignoring case: found in
    it as written, or its slug found in the project's slug.

    Claude Code records a project as its folder's slug and every other source
    as a real path, so the folder's own name ("My App"), its full path, the
    slug and any part of these each find the project whichever way it was
    recorded. Matching the text alone found nothing for a folder whose name
    has a space or punctuation, or for a full path.
    """
    wanted, project = wanted.lower(), project.lower()
    return wanted in project or slug(wanted) in slug(project)


def session_files(path: str) -> list:
    """One session's transcript followed by the transcripts of every agent it
    started, at any depth below <folder>/<stem>/.

    Subagents write to <stem>/subagents/agent-*.jsonl and workflow agents to
    <stem>/subagents/workflows/<id>/agent-*.jsonl, beside the session's own
    <stem>.jsonl. Their calls are made for that session, so its cost includes
    them. An agent's own transcript stands for its session, so the session's
    transcript and every agent's come back for it too, the session's left out
    once it is no longer on disk; reading the agent's file alone priced part
    of a session under the session's name. A session that started no agents
    is its transcript alone.
    """
    folder = _session_folder(path)
    stem = folder or os.path.splitext(path)[0]
    own = stem + ".jsonl" if folder else path
    agents = glob.glob(os.path.join(glob.escape(stem), "**", "*.jsonl"), recursive=True)
    return ([own] if own == path or os.path.isfile(own) else []) + sorted(agents)


def looks_like(line: str) -> bool:
    """Whether a line from an unknown file is a Claude Code transcript line."""
    return '"sessionId"' in line or ('"message"' in line and '"payload"' not in line)


def dedup_key(msg: dict, record: dict):
    """One API response can be written to disk many times, once per content
    block and again whenever a session is resumed. The message id is what
    identifies the response itself."""
    return msg.get("id") or f"{record.get('requestId')}|{record.get('uuid')}"


def _session_folder(path: str) -> str:
    """The <project>/<session> folder an agent's transcript lies under, or ""
    for a session's own transcript.

    A subagent's transcript lies directly in <session>/subagents/, a workflow
    agent's in <session>/subagents/workflows/<id>/, and these two layouts are
    the only ones that mark an agent. Looking only at the file's own folder
    missed every workflow agent; looking for a folder named subagents at any
    depth would take one above the projects folder for an agent's too.
    """
    folder = os.path.dirname(path)
    if os.path.basename(folder) == "subagents":
        return os.path.dirname(folder)
    workflows = os.path.dirname(folder)
    subagents = os.path.dirname(workflows)
    if os.path.basename(workflows) == "workflows" and os.path.basename(subagents) == "subagents":
        return os.path.dirname(subagents)
    return ""


def _where(path: str) -> tuple:
    """(project, session, is_subagent) for one transcript, from where it lies.

    A session's own transcript is <project>/<session>.jsonl, and an agent's
    lies below <project>/<session>/ (_session_folder()). Taking the agent's
    own folder as the project filed every workflow agent's calls under a
    project named after its workflow and a session named after its file.
    """
    folder = _session_folder(path)
    if folder:
        return os.path.basename(os.path.dirname(folder)), os.path.basename(folder), True
    return os.path.basename(os.path.dirname(path)), os.path.basename(path)[:-6], False


def records(path: str):
    """Yield (key, event) for every line that carries an API response.

    The same key is yielded more than once when a response was written more
    than once. The engine keeps the earliest sighting's attribution and the
    largest usage block, because the early copies of a streamed reply carry an
    output count that is still climbing.
    """
    project, session, is_subagent = _where(path)
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
