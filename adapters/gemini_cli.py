"""Google Gemini CLI sessions. Unverified.

Built from the published source of google-gemini/gemini-cli (read at commit
2fe7c2d, 25 September 2026) and checked against the Gemini parser in
ccusage. It has not yet been run against real session files, so every report
that uses it says so. If a figure looks wrong, please open an issue with a
sample.

What Gemini CLI writes, and what this reader does with it:

  - Every session is recorded, with no setting to turn it off, under
    ~/.gemini/tmp/<project>/chats/session-*.jsonl (subagents one folder
    deeper). Under the macOS sandbox the root is ~/.cache/.gemini instead.
  - The first line is the session's metadata; each later line is a message.
    Only "gemini" messages carry a model and a "tokens" block, and a message
    is appended again every time it changes: first with "tokens": null, then
    with the figures. The copy with the most tokens is the one kept.
  - Older installs kept a whole session as one .json document, and resuming
    one re-appends every message to a new .jsonl beside it. Both are read and
    keyed by session and message id, so a message in both counts once.
  - Gemini reports input INCLUDING cached tokens and output EXCLUDING thinking
    ("thoughts"), which Google bills at the output rate. So uncached input is
    input minus cached, plus the separate tool-use prompt count, and output is
    output plus thoughts. Where the recorded total does not agree with that
    reading, input is taken as already excluding the cache.
  - A rewound turn is still counted. It was a real API call and it was billed;
    rewinding changes the conversation, not the invoice.
  - No cost, provider or working directory is recorded. The provider is
    Google, and the folder comes from ~/.gemini/projects.json or the
    .project_root file beside each session folder.
"""

from __future__ import annotations

import glob
import json
import os

from .common import parse_time, usage

NAME = "gemini-cli"
LABEL = "Gemini CLI"
STATUS = "unverified"
PROVIDER = "google"
FILES = "sessions"


def default_roots() -> list:
    return [os.path.expanduser("~/.gemini/tmp"), os.path.expanduser("~/.cache/.gemini/tmp")]


def files(roots: list, project: str = "", session: str = "") -> list:
    paths = []
    for root in roots:
        for pattern in ("*.jsonl", "*.json"):
            paths.extend(p for p in glob.glob(os.path.join(root, "*", "chats", "**", pattern),
                                              recursive=True))
    if session:
        paths = [p for p in paths if session in os.path.basename(p)]
    return sorted(paths)


def looks_like(line: str) -> bool:
    return '"projectHash"' in line or ('"type":"gemini"' in line.replace(" ", "")
                                       and '"tokens"' in line)


def _project_dir(path: str) -> str:
    """The session's project folder: <root>/<project>/chats/..."""
    parts = path.split(os.sep)
    if "chats" in parts:
        i = len(parts) - 1 - parts[::-1].index("chats")
        return os.sep.join(parts[:i])
    return os.path.dirname(path)


def _cwd(project_dir: str) -> str:
    """The working directory a project folder belongs to, if Gemini CLI says."""
    try:
        with open(os.path.join(project_dir, ".project_root"), encoding="utf-8") as f:
            root = f.read().strip()
            if root:
                return root
    except OSError:
        pass
    registry = os.path.join(os.path.dirname(os.path.dirname(project_dir)), "projects.json")
    try:
        with open(registry, encoding="utf-8") as f:
            projects = json.load(f).get("projects") or {}
        slug = os.path.basename(project_dir)
        for path, name in projects.items():
            if name == slug:
                return path
    except (OSError, ValueError, AttributeError):
        pass
    return os.path.basename(project_dir)


def _messages(path: str):
    """Every message object in a session file, in either format."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            if path.endswith(".json"):
                doc = json.load(f)
                if isinstance(doc, dict):
                    yield {"sessionId": doc.get("sessionId"), "_meta": True}
                    for m in doc.get("messages") or []:
                        if isinstance(m, dict):
                            yield m
                return
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    if "projectHash" in obj and "sessionId" in obj and "type" not in obj:
                        obj["_meta"] = True
                    yield obj
    except (OSError, ValueError):
        return


def records(path: str):
    project = _cwd(_project_dir(path))
    session = os.path.basename(path).rsplit(".", 1)[0]
    for m in _messages(path):
        if m.get("_meta"):
            session = m.get("sessionId") or session
            continue
        if m.get("type") != "gemini" or not isinstance(m.get("tokens"), dict):
            continue
        t = m["tokens"]

        def n(k):
            v = t.get(k)
            return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
        inp, out, cached, thoughts, tool, total = (n("input"), n("output"), n("cached"),
                                                   n("thoughts"), n("tool"), n("total"))
        if not any((inp, out, cached, thoughts, tool)):
            continue
        # Google's contract is that the prompt count includes cached tokens.
        # When the recorded total says otherwise, trust the total.
        includes_cache = not total or total == inp + out + thoughts + tool
        uncached = max(0, inp - cached) if includes_cache else inp
        yield f"gemini:{session}:{m.get('id')}", {
            "when": parse_time(m.get("timestamp")),
            "model": m.get("model") or "",
            "provider": PROVIDER,
            "project": project,
            "session": session,
            "cwd": project,
            "sidechain": False,
            "source": NAME,
            "_usage": usage(input=uncached + tool, output=out + thoughts, cache_read=cached,
                            thinking=thoughts),
        }
