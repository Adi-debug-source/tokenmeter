"""Events you supply yourself, in the documented import format.

For any harness this tool has no adapter for, including closed ones: write a
short script that emits one JSON object per API call and pass the file with
`--import`. The format is in docs/import-format.md.

Nothing here is reverse-engineered, so it cannot misread a log. The figures
are yours; the tool supplies the prices, the ledger, the windows and the
dashboard. Import a file twice and nothing is counted twice, because events
are de-duplicated by `id` exactly as transcripts are.
"""

from __future__ import annotations

import json
import math
import sys

from .common import parse_time, usage

NAME = "import"
LABEL = "Imported events"
STATUS = "yours"
FILES = "import files"
FILE = "import file"

TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write", "cache_write_5m",
                "cache_write_1h", "thinking", "web_searches")

# UTF-8's byte order mark, which some editors write at the start of a file.
BOM = b"\xef\xbb\xbf"

# What went wrong, per file, for the report to say out loud. A bad line is
# skipped rather than fatal, so one typo cannot cost a whole import.
PROBLEMS: dict = {}


def default_roots() -> list:
    return []


def files(roots: list, project: str = "", session: str = "") -> list:
    return []


def _problem(path, lineno, why):
    entry = PROBLEMS.setdefault(path, {"skipped": 0, "examples": []})
    entry["skipped"] += 1
    if len(entry["examples"]) < 3:
        entry["examples"].append(f"line {lineno}: {why}")


def _is_count(v) -> bool:
    """Whether v is a count of tokens: a whole number, finite, not negative.

    json.loads reads 1e999 and Infinity as an infinite float, on which int()
    raises OverflowError rather than ValueError, and NaN, on which it raises
    ValueError with its own wording; an integer too large for a float would
    overflow later, when it is priced.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v) and v >= 0 and v == int(v)
    except OverflowError:  # an integer too large for a float
        return False


def parse(obj: dict):
    """One import object as (key, event), or raise ValueError saying why."""
    if not isinstance(obj, dict):
        raise ValueError("not a JSON object")
    missing = [k for k in ("id", "timestamp", "provider", "model") if not obj.get(k)]
    if missing:
        raise ValueError("missing " + ", ".join(missing))
    when = parse_time(obj["timestamp"])
    if when is None:
        raise ValueError(f"unreadable timestamp {obj['timestamp']!r}")
    counts = {}
    for k in TOKEN_FIELDS:
        v = obj.get(k, 0)
        if v is None:
            v = 0
        if not _is_count(v):
            raise ValueError(f"{k} must be a whole number of tokens, not {v!r}")
        counts[k] = int(v)
    if not any(counts[k] for k in TOKEN_FIELDS if k != "thinking"):
        raise ValueError("no tokens at all")
    speed = obj.get("speed") or "standard"
    if speed not in ("standard", "fast"):
        raise ValueError(f"speed must be standard or fast, not {speed!r}")
    return str(obj["id"]), {
        "when": when,
        "model": str(obj["model"]),
        "provider": str(obj["provider"]).lower(),
        "project": str(obj.get("project") or ""),
        "session": str(obj.get("session") or ""),
        "cwd": "",
        "sidechain": False,
        "source": NAME,
        "_usage": usage(input=counts["input"], output=counts["output"],
                        cache_read=counts["cache_read"],
                        cache_write_5m=counts["cache_write_5m"] + counts["cache_write"],
                        cache_write_1h=counts["cache_write_1h"],
                        thinking=counts["thinking"],
                        web_searches=counts["web_searches"], speed=speed),
    }


def records(path: str):
    """Yield (key, event) for every valid line; count and explain the rest."""
    PROBLEMS.pop(path, None)
    try:
        if path == "-":
            data = sys.stdin.buffer.read()
        else:
            with open(path, "rb") as fh:
                data = fh.read()
    except OSError as e:
        _problem(path, 0, f"could not open: {e.strerror}")
        return
    # Read as bytes and decoded a line at a time, so a line that is not UTF-8
    # is skipped like any other bad line. bytes.splitlines() splits where a
    # text file would: at \n, \r and \r\n. A byte order mark, which Windows
    # editors put first, is not part of the first line: kept, it made that
    # line invalid JSON.
    if data.startswith(BOM):
        data = data[len(BOM):]
    for n, raw in enumerate(data.splitlines(), 1):
        try:
            line = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            _problem(path, n, "not valid UTF-8")
            continue
        if not line or line.startswith("//"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            _problem(path, n, "not valid JSON")
            continue
        try:
            yield parse(obj)
        except ValueError as e:
            _problem(path, n, str(e))
