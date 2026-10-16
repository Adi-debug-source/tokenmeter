#!/usr/bin/env python3
"""
Make a synthetic home folder of coding agent logs, for the README's
screenshots and for trying Tokenmeter without logs of your own.

    python3 docs/screenshots/make_demo.py <folder> [--now TIME] [--force] [--seed N]
    (. <folder>/env.sh; python3 tokenmeter.py --by model)

The first command writes <folder>/home, a home folder holding nothing but
invented logs and a ledger to match, and <folder>/env.sh, which points every
reader Tokenmeter has at that folder. It refuses a folder that already holds
anything unless given --force, and --force only replaces a folder this script
made. Run the engine in a subshell that has sourced env.sh, as the second
command does, so your own shell keeps its home folder.

TIME is a local date and time such as 2026-10-16T17:40. The history ends at
that minute, and nothing is dated after it. Without --now it ends at the
current minute. Tokenmeter works out today, the last 7 days and the last 30
from the real clock, so make the demo on the day it is used: the README's
images were made with --now 2026-10-16T17:40 on 16 October 2026, in
Europe/London (TZ=Europe/London).

Every figure is invented
------------------------
Nothing here is read from anyone's logs. The projects, prompts, sessions,
rhythm and token counts are all made up in this file; only the line formats
are the harnesses' own. So a screenshot of the result says nothing about
whoever ran it, which is why the README's screenshots can be published. The
person is "sam", an invented user whose projects live under /Users/sam.

It is deterministic. The random seed is fixed and only random() and
getrandbits() are used, whose sequences are the same on every Python 3, so
two runs with the same --now, in the same time zone, write the same logs and
the same ledger, byte for byte. The one exception is OpenCode's SQLite
database, whose header records the SQLite version that wrote it; its rows
are the same.

What it writes
--------------
About three months of Claude Code use ending at --now: weekdays mostly, a
side project at some weekends, a summer holiday with nothing at all, two
crunch days, and a slow rise in use. Sessions run as turns of tool calls,
with the context growing call by call and cached, a compaction when it gets
long, and subagents (Explore on Haiku, the rest on the session's model) in
their own transcripts. The models change as newer ones arrive, on the dates
given below: Opus 5 to Opus 5.5 on 22 September 2026, Sonnet 5 to Sonnet 5.5
on 6 October and Haiku 4.5 to Haiku 5.5 on 7 October, with Fable 5.1 for the
hardest work throughout.

Claude Code deletes a transcript 30 days after it was last written
(cleanupPeriodDays), so only the last 30 days of transcripts are on disk.
The ledger holds every call, as it would on a Mac where Tokenmeter has been
running all along: each transcript is written, read by the engine's own
reconcile_ledger(), exactly as a run reads one, and the older ones are then
deleted, as Claude Code deletes them. The ledger's rows are therefore the
engine's own, not a second copy of its arithmetic, and the first real run
finds nothing to add.

Three other harnesses were tried in the last three weeks, in each one's own
format as the adapters and tests/fixtures read it: Codex (GPT-6 Sol) this
week, Gemini CLI (Gemini 3.8 Flash), and OpenCode with Sonnet 5.5 and GPT-6
Sol, so the dashboard's harness views and --list-adapters have something to
show.

It finishes by checking its own output: a second reconcile against the
transcripts left on disk must add nothing to the ledger and restore exactly
the calls whose transcripts were deleted.

Python 3.9 or later, standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import random
import shutil
import sqlite3
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

# The seed the README's images use. Of the first 700, it is one whose history
# to 16 October 2026 has every model in use, each other harness tried a few
# times, a steady rise week on week, and a last chart label that clears the
# one before it.
DEFAULT_SEED = 610
DAYS = 95                     # a little over three months, ending on --now's day
CLEANUP_DAYS = 30             # Claude Code's cleanupPeriodDays default
MARKER = ".tokenmeter-demo"   # written into every folder this script makes

# When each model arrived. A session starts on the newer model from that day,
# with a few days of overlap while habits change.
OPUS_5_5 = dt.date(2026, 9, 22)
SONNET_5_5 = dt.date(2026, 10, 6)
HAIKU_5_5 = dt.date(2026, 10, 7)
OVERLAP_DAYS = 3

USER_HOME = "/Users/sam"


# MARK: - Dice

class Dice:
    """Every random choice, from random() and getrandbits() only: their
    sequences for a given seed are the same on every Python 3, which is not
    promised of the helpers built on them."""

    def __init__(self, seed: int):
        self.r = random.Random(seed)

    def chance(self, p: float) -> bool:
        return self.r.random() < p

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.r.random()

    def between(self, a: int, b: int) -> int:
        """A whole number from a to b, both included."""
        return a + int(self.r.random() * (b - a + 1))

    def pick(self, items):
        return items[int(self.r.random() * len(items))]

    def weighted(self, pairs):
        """One of [(item, weight), ...], in proportion to the weights."""
        total = sum(w for _, w in pairs)
        x = self.r.random() * total
        for item, w in pairs:
            x -= w
            if x < 0:
                return item
        return pairs[-1][0]

    def normal(self) -> float:
        """A standard normal draw, by Box and Muller, from two random()s."""
        u1 = max(self.r.random(), 1e-12)
        u2 = self.r.random()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def lognormal(self, median: float, sigma: float, low: int, high: int) -> int:
        return int(min(high, max(low, median * math.exp(sigma * self.normal()))))

    def bits(self, n: int) -> int:
        return self.r.getrandbits(n)

    def uuid4(self) -> str:
        return str(uuid.UUID(int=self.bits(128), version=4))

    def uuid7(self, when: dt.datetime) -> str:
        """A time-ordered id, as Codex names its threads."""
        ms = int(when.timestamp() * 1000)
        value = (ms << 80) | (0x7 << 76) | (self.bits(12) << 64) | (0b10 << 62) | self.bits(62)
        return str(uuid.UUID(int=value))

    def token(self, n: int) -> str:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        return "".join(alphabet[self.bits(6) % 62] for _ in range(n))

    def hex(self, n: int) -> str:
        return "".join("0123456789abcdef"[self.bits(4)] for _ in range(n))


# MARK: - Time

def utc(local: dt.datetime) -> dt.datetime:
    """A naive local wall-clock time as an aware UTC one. Wall clock
    arithmetic first, then converted, so a clock change lands on the right
    local hour, which is what the engine dates a call by."""
    return local.astimezone(dt.timezone.utc)


def stamp(when: dt.datetime) -> str:
    """ISO 8601 in UTC with milliseconds and a Z, as Claude Code, Codex and
    Gemini CLI write it."""
    when = when.astimezone(dt.timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{when.microsecond // 1000:03d}Z"


def millis(when: dt.datetime) -> int:
    return int(round(when.timestamp() * 1000))


# MARK: - The person

# (folder, weight early, weight late, weekend weight, branches, prompts, files)
PROJECTS = [
    ("code/orbit-api", 0.46, 0.16, 0.05, ["main", "feat/rate-limits", "fix/token-refresh"],
     ["Add rate limiting to the public endpoints",
      "The token refresh test is flaky. Find out why",
      "Write a migration that adds an index on orders.created_at",
      "Explain how the webhook retries work",
      "Add pagination to GET /v1/orders",
      "Upgrade the Postgres driver and fix whatever breaks"],
     ["api/routes/orders.py", "api/auth/tokens.py", "api/webhooks.py",
      "migrations/0042_orders_index.py", "tests/test_orders.py", "pyproject.toml"]),
    ("code/my-app", 0.16, 0.46, 0.05, ["main", "feat/settings-page", "fix/date-picker"],
     ["Build the settings page from the design in docs/settings.md",
      "The date picker shows the wrong week on Sundays",
      "Move the API client to the generated types",
      "Add a dark theme toggle that remembers the choice",
      "Why is the bundle 300 KB bigger since Tuesday?",
      "Write tests for the checkout form"],
     ["src/pages/Settings.tsx", "src/components/DatePicker.tsx", "src/api/client.ts",
      "src/theme.ts", "vite.config.ts", "src/pages/Checkout.test.tsx"]),
    ("code/tidepool", 0.12, 0.12, 0.70, ["main", "feat/watch-mode"],
     ["Add a --watch flag that reruns on file changes",
      "Make the parser handle CRLF line endings",
      "Profile the import of a 2 GB file and speed it up",
      "Tidy the error messages so they say what to do next"],
     ["src/main.rs", "src/parser.rs", "src/watch.rs", "Cargo.toml", "tests/cli.rs"]),
    ("code/field-notes", 0.08, 0.08, 0.15, ["main"],
     ["Draft the post about the parser rewrite from my notes",
      "Fix the broken links the checker found",
      "Add an RSS feed"],
     ["src/content/posts/parser-rewrite.md", "astro.config.mjs", "src/pages/rss.xml.ts"]),
    ("dotfiles", 0.06, 0.06, 0.05, ["main"],
     ["Make the prompt show the git branch",
      "Why does tmux lose its colours over ssh?"],
     ["zsh/prompt.zsh", "tmux.conf", "install.sh"]),
    ("", 0.12, 0.12, 0.0, ["main"],
     ["What is using all the disk space in Library/Caches?",
      "Write a one-line command to rename these screenshots by date",
      "How do I check which process holds port 5432?"],
     ["Library/Caches", "Desktop", "Downloads"]),
]

TOOLS = [("Read", 30), ("Edit", 22), ("Bash", 24), ("Grep", 10), ("Glob", 5),
         ("Write", 4), ("TodoWrite", 4)]

ANSWERS = ["Done. The tests pass.", "Fixed, and I added a test for it.",
           "Here is what I found.", "That is in place now.",
           "I have made the change; the build is clean.",
           "The cause was a stale cache entry. It is fixed."]


def project_path(folder: str) -> str:
    return USER_HOME + ("/" + folder if folder else "")


def slug(path: str) -> str:
    """A working directory as Claude Code names its project folder."""
    return "".join(c if c.isalnum() and c.isascii() else "-" for c in path)


# MARK: - Models

def era(day: dt.date, new_from: dt.date, old: str, new: str, dice: Dice) -> str:
    if day < new_from:
        return old
    if day < new_from + dt.timedelta(days=OVERLAP_DAYS):
        return new if dice.chance(0.6) else old
    return new


def opus(day, dice):
    return era(day, OPUS_5_5, "claude-opus-5", "claude-opus-5-5", dice)


def sonnet(day, dice):
    return era(day, SONNET_5_5, "claude-sonnet-5", "claude-sonnet-5-5", dice)


def haiku(day, dice):
    # Claude Code records Haiku 4.5 by its dated id.
    return era(day, HAIKU_5_5, "claude-haiku-4-5-20251001", "claude-haiku-5-5", dice)


def main_model(day: dt.date, folder: str, dice: Dice) -> str:
    if folder == "" and day >= HAIKU_5_5:
        return "claude-haiku-5-5"       # quick questions, once there is a Haiku that fast
    if folder in ("", "dotfiles"):
        return sonnet(day, dice)
    if day < OPUS_5_5:
        kind = dice.weighted([("opus", 0.42), ("sonnet", 0.49), ("fable", 0.09)])
    else:
        # Opus 5.5 is cheaper than Opus 5 in every column, so it is used more.
        kind = dice.weighted([("opus", 0.55), ("sonnet", 0.38), ("fable", 0.07)])
    if kind == "opus":
        return opus(day, dice)
    if kind == "fable":
        return "claude-fable-5-1"
    return sonnet(day, dice)


def thinks(model: str) -> bool:
    return "haiku" not in model


# MARK: - A Claude Code session, as calls

class Call:
    __slots__ = ("when", "model", "input", "read", "w5", "w1", "output", "thinking",
                 "tool", "result", "turn_start", "prompt", "compact")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def tool_result_size(tool: str, dice: Dice) -> int:
    return {
        "Read": lambda: dice.lognormal(4400, 0.9, 120, 40000),
        "Bash": lambda: dice.lognormal(900, 1.1, 20, 24000),
        "Grep": lambda: dice.lognormal(480, 0.9, 20, 8000),
        "Glob": lambda: dice.lognormal(160, 0.7, 20, 2000),
        "Edit": lambda: dice.lognormal(180, 0.5, 60, 900),
        "Write": lambda: dice.between(60, 120),
        "TodoWrite": lambda: dice.between(80, 220),
        "Task": lambda: dice.lognormal(1400, 0.5, 400, 5000),
    }[tool]()


def run_thread(dice: Dice, start: dt.datetime, model: str, turns: list, system: int,
               ttl_1h: bool, compact_at: int, cold: bool, spawn=None, tools=TOOLS):
    """The calls one thread makes: turns of tool calls, each call's prompt the
    last one's plus what came back, read from the cache that the previous call
    wrote. spawn(call, when) may start a subagent and returns how long it
    ran, in seconds. Returns (calls, end)."""
    calls = []
    t = start
    prompt = 0          # the previous call's prompt, all cached
    pending = system    # what the next call adds to the cache
    if not cold:
        # Most of the system prompt and tools are shared with a session from
        # the last hour, so the first call finds them cached.
        prompt = int(system * dice.uniform(0.6, 0.85))
        pending = system - prompt
    last = None
    for ti, (prompt_text, length) in enumerate(turns):
        if ti:
            t += dt.timedelta(seconds=dice.lognormal(240, 0.9, 25, 3000))
        pending += dice.between(12, 160)              # the user's message
        for k in range(length):
            final = k == length - 1
            if last is not None:
                gap = (last.output / dice.uniform(55, 90)          # generating
                       + dice.lognormal(9, 0.9, 1, 240))            # the tool running
                t += dt.timedelta(seconds=gap)
            if last is not None and (t - last.when).total_seconds() > (3600 if ttl_1h else 300):
                # The cache expired: everything is written again.
                pending += prompt
                prompt = 0
            if final:
                tool = None
                out = dice.lognormal(210, 0.7, 30, 2400)
            else:
                tool = dice.weighted(tools)
                big = tool in ("Write", "Edit") and dice.chance(0.3)
                out = (dice.lognormal(1800, 0.6, 400, 9000) if big
                       else dice.lognormal(150, 0.8, 18, 3000))
            think = 0
            if thinks(model) and dice.chance(0.62):
                think = int(out * dice.uniform(0.18, 0.55))
                out += think
            write = pending
            call = Call(when=t, model=model, input=dice.between(1, 9), read=prompt,
                        w5=0 if ttl_1h else write, w1=write if ttl_1h else 0,
                        output=out, thinking=think, tool=tool, turn_start=(k == 0),
                        prompt=prompt_text if k == 0 else None, compact=False)
            calls.append(call)
            prompt = call.input + call.read + write
            pending = out
            last = call
            if tool:
                if tool == "Task" and spawn is not None:
                    t += dt.timedelta(seconds=spawn(call, t))
                call.result = tool_result_size(tool, dice)
                pending += call.result
            if prompt + pending > compact_at and not final:
                # Auto-compact: one call reads the whole context and writes a
                # summary, which starts the context again after the system
                # prompt, which stays cached.
                t += dt.timedelta(seconds=dice.uniform(20, 50))
                summary = dice.lognormal(3200, 0.3, 1500, 7000)
                calls.append(Call(when=t, model=model, input=dice.between(1, 9),
                                  read=prompt, w5=0 if ttl_1h else pending,
                                  w1=pending if ttl_1h else 0, output=summary, thinking=0,
                                  tool=None, turn_start=False, prompt=None,
                                  compact=True))
                last = calls[-1]
                prompt = system
                pending = summary + dice.between(800, 2400)
    return calls, t


class Session:
    def __init__(self, folder, sid, version, branch, start):
        self.folder, self.sid, self.version, self.branch = folder, sid, version, branch
        self.cwd = project_path(folder)
        self.start = start
        self.calls = []
        self.agents = []      # (agent id, kind, calls)

    @property
    def end(self):
        times = [c.when for c in self.calls]
        for _, _, calls in self.agents:
            times += [c.when for c in calls]
        return max(times)


def claude_session(dice: Dice, day: dt.date, start_local: dt.datetime, folder: str,
                   version: str, cold: bool, light: bool) -> Session:
    proj = next(p for p in PROJECTS if p[0] == folder)
    sess = Session(folder, dice.uuid4(), version, dice.pick(proj[4]), utc(start_local))
    model = main_model(day, folder, dice)
    n_turns = dice.between(1, 2) if light else dice.weighted(
        [(1, 2), (2, 3), (3, 3), (4, 3), (5, 2), (6, 1), (8, 1)])
    turns = [(dice.pick(proj[5]), dice.lognormal(5 if light else 8, 0.55, 1, 40))
             for _ in range(n_turns)]
    system = dice.between(15800, 21400)

    def spawn(call, when):
        kind = "Explore" if dice.chance(0.6) else "general-purpose"
        sub_model = haiku(day, dice) if kind == "Explore" else (
            model if dice.chance(0.5) else sonnet(day, dice))
        aid = dice.hex(8)
        length = dice.lognormal(9, 0.6, 3, 40)
        calls, end = run_thread(
            dice, when + dt.timedelta(seconds=dice.uniform(1, 3)), sub_model,
            [(f"[{kind}] Find where {dice.pick(proj[6])} handles this and report back.",
              length)],
            system=dice.between(7800, 12600), ttl_1h=False, compact_at=150000,
            cold=False, tools=[("Read", 40), ("Grep", 30), ("Glob", 20), ("Bash", 10)])
        sess.agents.append((aid, kind, calls))
        return (end - when).total_seconds() + dice.uniform(1, 4)

    tools = list(TOOLS)
    if not light and dice.chance(0.45):
        tools.append(("Task", 3))
    sess.calls, _ = run_thread(dice, sess.start, model, turns, system, ttl_1h=True,
                               compact_at=dice.between(150000, 185000), cold=cold,
                               spawn=spawn, tools=tools)
    return sess


# MARK: - The calendar

def weekday_from(day: dt.date) -> dt.date:
    """The day itself, or the Monday after when it falls at a weekend."""
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    return day


def plan(dice: Dice, now: dt.datetime):
    """Every session of every harness, oldest first, none after now."""
    first = now.date() - dt.timedelta(days=DAYS - 1)
    # A summer holiday: ten days from the fourth Saturday, with nothing at all.
    sat = first + dt.timedelta(days=(5 - first.weekday()) % 7 + 21)
    holiday = (sat, sat + dt.timedelta(days=9))
    crunch = {weekday_from(first + dt.timedelta(days=59)),
              weekday_from(first + dt.timedelta(days=81))}
    claude, codex, gemini, opencode = [], [], [], []
    last_end = None
    for i in range(DAYS):
        day = first + dt.timedelta(days=i)
        progress = i / (DAYS - 1)
        if holiday[0] <= day <= holiday[1]:
            continue
        weekend = day.weekday() >= 5
        today = i == DAYS - 1
        if day in crunch:
            n = 5
        elif weekend:
            n = 1 if dice.chance(0.35) else 0
        elif today or dice.chance(0.94):
            n = max(1, round(1.3 + 1.2 * progress + dice.uniform(-0.8, 0.8)))
        else:
            n = 0
        version = f"2.{3 + int(progress * 3.2)}.{1 + (i * 7) % 13}"
        starts = []
        for _ in range(n):
            if weekend:
                h = dice.uniform(10.5, 16.5)
            elif today:
                # A working day so far: every session has had time to run.
                h = dice.uniform(9.0, max(9.5, now.hour + now.minute / 60 - 1.5))
            else:
                h = dice.weighted([(dice.uniform(9.0, 12.2), 5), (dice.uniform(13.4, 18.3), 6),
                                   (dice.uniform(20.0, 22.6), 1)])
            starts.append(h)
        for h in sorted(starts):
            start = dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=h)
            if weekend:
                weights = [(p[0], p[3]) for p in PROJECTS]
            else:
                weights = [(p[0], p[1] + (p[2] - p[1]) * progress) for p in PROJECTS]
            folder = dice.weighted(weights)
            cold = last_end is None or (utc(start) - last_end).total_seconds() > 3600
            sess = claude_session(dice, day, start, folder, version, cold,
                                  light=weekend or folder in ("", "dotfiles"))
            sess.calls = [c for c in sess.calls if c.when <= utc(now)]
            sess.agents = [(a, k, [c for c in cs if c.when <= utc(now)])
                           for a, k, cs in sess.agents]
            sess.agents = [a for a in sess.agents if a[2]]
            if not sess.calls:
                continue
            claude.append(sess)
            last_end = max(last_end or sess.end, sess.end)

        # The other harnesses, tried lately.
        left = DAYS - 1 - i
        if left < 8 and not weekend and dice.chance(0.9):
            codex.append(other_session(dice, day, "codex", now))
        if 2 <= left < 21 and not weekend and dice.chance(0.45):
            gemini.append(other_session(dice, day, "gemini", now))
        if 1 <= left < 16 and dice.chance(0.35):
            opencode.append(other_session(dice, day, "opencode", now))
    return claude, [s for s in codex if s], [s for s in gemini if s], [s for s in opencode if s]


class Other:
    """A session in another harness: when, where, which model, and its calls
    as (time, prompt tokens, cached, written, output, reasoning)."""

    def __init__(self, harness, sid, folder, model, provider):
        self.harness, self.sid, self.folder = harness, sid, folder
        self.cwd = project_path(folder)
        self.model, self.provider = model, provider
        self.calls = []
        self.prompts = []


def other_session(dice: Dice, day: dt.date, harness: str, now: dt.datetime):
    start = utc(dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=dice.uniform(10.0, 17.5)))
    if harness == "codex":
        folder = dice.weighted([("code/my-app", 3), ("code/tidepool", 2)])
        model, provider, block = "gpt-6-sol", "openai", 128
        n, system = dice.lognormal(18, 0.4, 8, 34), dice.between(9800, 12400)
    elif harness == "gemini":
        folder = dice.weighted([("code/field-notes", 2), ("code/orbit-api", 2)])
        model, provider, block = "gemini-3.8-flash", "google", 1024
        n, system = dice.lognormal(11, 0.4, 5, 22), dice.between(7200, 9600)
    else:
        folder = "code/tidepool"
        if day >= SONNET_5_5 and dice.chance(0.7):
            model, provider = "claude-sonnet-5-5", "anthropic"
        else:
            model, provider = "gpt-6-sol", "openai"
        block = 1 if provider == "anthropic" else 128
        n, system = dice.lognormal(13, 0.4, 6, 26), dice.between(11200, 13800)
    sid = dice.uuid7(start) if harness == "codex" else dice.uuid4()
    s = Other(harness, sid, folder, model, provider)
    proj = next(p for p in PROJECTS if p[0] == folder)
    t, prompt, ctx = start, 0, system + dice.between(20, 120)
    for k in range(n):
        if k:
            t += dt.timedelta(seconds=dice.lognormal(14, 0.8, 2, 400))
            ctx += dice.lognormal(900, 1.0, 40, 16000)
        if k == 0 or dice.chance(0.12):
            s.prompts.append((len(s.calls), dice.pick(proj[5])))
            ctx += dice.between(12, 160)
        if t > utc(now):
            break
        cached = (prompt // block) * block if k else 0
        written = 0
        if harness == "codex" and k == 0:
            written = int(ctx * 0.9)
        if provider == "anthropic":
            written = ctx - cached
        out = dice.lognormal(260, 0.8, 20, 4000)
        reasoning = int(out * dice.uniform(0.2, 0.6)) if dice.chance(0.7) else 0
        if harness == "gemini":
            reasoning = dice.lognormal(500, 0.7, 60, 3000) if dice.chance(0.6) else 0
        s.calls.append((t, ctx, cached, written, out, reasoning))
        prompt = ctx
        ctx += out
    return s if s.calls else None


# MARK: - Writing Claude Code transcripts

def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def cc_usage(c: Call) -> dict:
    return {"input_tokens": c.input,
            "cache_creation_input_tokens": c.w5 + c.w1,
            "cache_read_input_tokens": c.read,
            "cache_creation": {"ephemeral_5m_input_tokens": c.w5,
                               "ephemeral_1h_input_tokens": c.w1},
            "output_tokens": c.output,
            "output_tokens_details": {"thinking_tokens": c.thinking},
            "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
            "service_tier": "standard"}


def tool_input(tool: str, cwd: str, files: list, dice: Dice) -> dict:
    path = cwd + "/" + dice.pick(files)
    return {
        "Read": lambda: {"file_path": path},
        "Edit": lambda: {"file_path": path, "old_string": "...", "new_string": "..."},
        "Write": lambda: {"file_path": path, "content": "..."},
        "Bash": lambda: {"command": dice.pick(["npm test", "pytest -q", "cargo test", "git status",
                                               "git diff --stat", "make lint"]),
                         "description": "Run the checks"},
        "Grep": lambda: {"pattern": dice.pick(["TODO", "refresh", "paginate", "theme"]),
                         "path": cwd},
        "Glob": lambda: {"pattern": "**/*." + dice.pick(["py", "ts", "tsx", "rs", "md"])},
        "TodoWrite": lambda: {"todos": [{"content": "Make the change", "status": "in_progress"}]},
        "Task": lambda: {"description": "Survey the code", "subagent_type": "Explore",
                         "prompt": "Find where this is handled and report back."},
    }[tool]()


def thread_lines(dice: Dice, sess: Session, calls: list, agent=None) -> list:
    proj = next(p for p in PROJECTS if p[0] == sess.folder)
    base = {"parentUuid": None, "isSidechain": agent is not None, "userType": "external",
            "cwd": sess.cwd, "sessionId": sess.sid, "version": sess.version,
            "gitBranch": sess.branch}
    if agent is not None:
        base["agentId"] = agent
    lines, parent = [], None

    def add(t, **fields):
        nonlocal parent
        u = dice.uuid4()
        line = dict(base, parentUuid=parent)
        line.update(fields)
        line["uuid"] = u
        line["timestamp"] = stamp(t)
        lines.append((t, dumps(line)))
        parent = u

    for c in calls:
        if c.turn_start:
            add(c.when - dt.timedelta(seconds=dice.uniform(1.0, 3.0)), type="user",
                message={"role": "user", "content": c.prompt})
        mid = "msg_01" + dice.token(22)
        req = "req_011C" + dice.token(18)
        blocks = []
        if c.thinking:
            blocks.append({"type": "thinking", "thinking": "Look at how this is wired first.",
                           "signature": dice.token(40)})
        if c.tool:
            tid = "toolu_01" + dice.token(22)
            blocks.append({"type": "tool_use", "id": tid, "name": c.tool,
                           "input": tool_input(c.tool, sess.cwd, proj[6], dice)})
        elif c.compact:
            blocks.append({"type": "text", "text": "Summary of the conversation so far."})
        else:
            blocks.append({"type": "text", "text": dice.pick(ANSWERS)})
        stop = "tool_use" if c.tool else "end_turn"
        # One line per content block, as Claude Code writes a streamed reply:
        # each copy carries the usage so far, and only the last is complete.
        for b, block in enumerate(blocks):
            usage = cc_usage(c)
            done = b == len(blocks) - 1
            if not done:
                partial = max(1, c.thinking // 2)
                usage["output_tokens"] = partial
                usage["output_tokens_details"] = {"thinking_tokens": partial}
            add(c.when + dt.timedelta(seconds=0.4 * b), type="assistant", requestId=req,
                message={"id": mid, "type": "message", "role": "assistant", "model": c.model,
                         "content": [block], "stop_reason": stop if done else None,
                         "stop_sequence": None, "usage": usage})
        if c.tool:
            add(c.when + dt.timedelta(seconds=0.4 * len(blocks) + dice.uniform(0.2, 6.0)),
                type="user",
                message={"role": "user", "content": [
                    {"tool_use_id": tid, "type": "tool_result",
                     "content": f"({c.result:,} tokens of output)"}]})
    return [text for _, text in sorted(lines, key=lambda x: x[0])]


def write_lines(path: str, lines: list, when: dt.datetime) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    t = when.timestamp()
    os.utime(path, (t, t))


def write_claude(dice: Dice, sessions: list, live_root: str, swept_root: str,
                 now: dt.datetime) -> tuple:
    """Each session's transcript, and its agents', under live_root when it was
    last written in the last CLEANUP_DAYS days, else under swept_root."""
    cutoff = utc(now) - dt.timedelta(days=CLEANUP_DAYS)
    live = swept = 0
    for s in sessions:
        root = live_root if s.end >= cutoff else swept_root
        folder = os.path.join(root, slug(s.cwd))
        write_lines(os.path.join(folder, s.sid + ".jsonl"), thread_lines(dice, s, s.calls), s.end)
        n = 1
        for aid, _kind, calls in s.agents:
            write_lines(os.path.join(folder, s.sid, "subagents", f"agent-{aid}.jsonl"),
                        thread_lines(dice, s, calls, agent=aid), calls[-1].when)
            n += 1
        if root == live_root:
            live += n
        else:
            swept += n
    return live, swept


# MARK: - Writing the other harnesses

def write_codex(dice: Dice, sessions: list, codex_home: str) -> None:
    for s in sessions:
        start = s.calls[0][0] - dt.timedelta(seconds=dice.uniform(3, 9))
        local = start.astimezone()
        name = f"rollout-{local.strftime('%Y-%m-%dT%H-%M-%S')}-{s.sid}.jsonl"
        path = os.path.join(codex_home, "sessions", local.strftime("%Y"), local.strftime("%m"),
                            local.strftime("%d"), name)
        lines, ordinal = [], [0]

        def add(t, kind, payload):
            lines.append(dumps({"timestamp": stamp(t), "ordinal": ordinal[0], "type": kind,
                                "payload": payload}))
            ordinal[0] += 1

        add(start, "session_meta", {
            "session_id": s.sid, "id": s.sid, "timestamp": stamp(start), "cwd": s.cwd,
            "originator": "codex_cli_rs", "cli_version": "0.161.0", "source": "cli",
            "model_provider": "openai", "base_instructions": None,
            "history_mode": "paginated",
            "git": {"commit_hash": dice.hex(40), "branch": "main",
                    "repository_url": "https://git.example.com/sam/"
                                      + s.folder.split("/")[-1] + ".git"}})
        add(start, "turn_context", {
            "turn_id": "turn_000001", "cwd": s.cwd, "current_date": local.strftime("%Y-%m-%d"),
            "timezone": "Europe/London", "approval_policy": "on-request",
            "sandbox_policy": {"type": "workspace-write", "network_access": False},
            "model": s.model, "effort": "medium", "summary": "auto"})
        add(start, "event_msg", {
            "type": "thread_settings_applied", "thread_id": s.sid,
            "thread_settings": {"model": s.model, "model_provider_id": "openai",
                                "service_tier": "default", "approval_policy": "on-request",
                                "cwd": s.cwd}})
        prompts = dict(s.prompts)
        total = {"input_tokens": 0, "cached_input_tokens": 0, "cache_write_input_tokens": 0,
                 "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 0}
        used = 0.0
        for k, (t, ctx, cached, written, out, reasoning) in enumerate(s.calls):
            if k in prompts:
                add(t - dt.timedelta(seconds=2), "response_item", {
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": prompts[k]}]})
            last = {"input_tokens": ctx, "cached_input_tokens": cached,
                    "cache_write_input_tokens": written, "output_tokens": out,
                    "reasoning_output_tokens": reasoning, "total_tokens": ctx + out}
            for key in total:
                total[key] += last[key]
            turn = f"turn_{k + 1:06d}"
            add(t, "token_usage_record", {
                "thread_id": s.sid, "turn_id": turn, "session_id": s.sid, "root_turn_id": turn,
                "response_id": "resp_" + dice.hex(10), "usage": last,
                "turn_token_usage": last, "thread_token_usage": dict(total)})
            used += 0.35
            add(t + dt.timedelta(milliseconds=20), "event_msg", {
                "type": "token_count",
                "info": {"total_token_usage": dict(total), "last_token_usage": last,
                         "model_context_window": 272000},
                "rate_limits": {"limit_id": "plus_5h", "limit_name": "5h",
                                "primary": {"used_percent": round(used, 1), "window_minutes": 300},
                                "secondary": {"used_percent": round(used / 6, 1),
                                              "window_minutes": 10080},
                                "plan_type": "plus"}})
        write_lines(path, lines, s.calls[-1][0])


def write_gemini(dice: Dice, sessions: list, home: str) -> None:
    root = os.path.join(home, ".gemini")
    registry = {}
    for s in sessions:
        name = s.folder.split("/")[-1]
        registry[s.cwd] = name
        folder = os.path.join(root, "tmp", name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, ".project_root"), "w", encoding="utf-8") as f:
            f.write(s.cwd)
        start = s.calls[0][0] - dt.timedelta(seconds=dice.uniform(4, 9))
        local = start.astimezone()
        path = os.path.join(folder, "chats",
                            f"session-{local.strftime('%Y-%m-%dT%H-%M')}-{s.sid[:8]}.jsonl")
        lines = [dumps({"sessionId": s.sid,
                        "projectHash": hashlib.sha256(s.cwd.encode()).hexdigest(),
                        "startTime": stamp(start), "lastUpdated": stamp(start), "kind": "main"})]
        prompts = dict(s.prompts)
        for k, (t, ctx, cached, _written, out, thoughts) in enumerate(s.calls):
            if k in prompts:
                lines.append(dumps({"id": dice.uuid4(),
                                    "timestamp": stamp(t - dt.timedelta(seconds=3)),
                                    "type": "user", "content": prompts[k]}))
            mid = dice.uuid4()
            msg = {"id": mid, "timestamp": stamp(t), "type": "gemini",
                   "content": dice.pick(ANSWERS), "model": s.model, "thoughts": [], "tokens": None}
            lines.append(dumps(msg))
            # Gemini counts the prompt with its cached part in it, and the
            # thoughts apart from the visible output.
            msg["tokens"] = {"input": ctx, "output": out, "cached": cached,
                             "thoughts": thoughts, "tool": 0, "total": ctx + out + thoughts}
            lines.append(dumps(msg))
            later = stamp(t + dt.timedelta(milliseconds=200))
            lines.append(dumps({"$set": {"lastUpdated": later}}))
        write_lines(path, lines, s.calls[-1][0])
    with open(os.path.join(root, "projects.json"), "w", encoding="utf-8") as f:
        json.dump({"projects": dict(sorted(registry.items()))}, f, indent=2)
        f.write("\n")


OPENCODE_SCHEMA = """
CREATE TABLE project (
  id text PRIMARY KEY NOT NULL, worktree text NOT NULL, vcs text, name text,
  icon_url text, icon_url_override text, icon_color text,
  time_created integer NOT NULL, time_updated integer NOT NULL, time_initialized integer,
  sandboxes text NOT NULL, commands text);
CREATE TABLE session (
  id text PRIMARY KEY NOT NULL, project_id text NOT NULL REFERENCES project(id) ON DELETE cascade,
  workspace_id text, parent_id text, slug text NOT NULL, directory text NOT NULL, path text,
  title text NOT NULL, version text NOT NULL, share_url text, summary_additions integer,
  summary_deletions integer, summary_files integer, summary_diffs text, metadata text,
  cost real DEFAULT 0 NOT NULL, tokens_input integer DEFAULT 0 NOT NULL,
  tokens_output integer DEFAULT 0 NOT NULL, tokens_reasoning integer DEFAULT 0 NOT NULL,
  tokens_cache_read integer DEFAULT 0 NOT NULL, tokens_cache_write integer DEFAULT 0 NOT NULL,
  revert text, permission text, agent text, model text,
  time_created integer NOT NULL, time_updated integer NOT NULL, time_compacting integer,
  time_archived integer);
CREATE TABLE message (
  id text PRIMARY KEY NOT NULL, session_id text NOT NULL REFERENCES session(id) ON DELETE cascade,
  time_created integer NOT NULL, time_updated integer NOT NULL, data text NOT NULL);
CREATE TABLE part (
  id text PRIMARY KEY NOT NULL, message_id text NOT NULL REFERENCES message(id) ON DELETE cascade,
  session_id text NOT NULL, time_created integer NOT NULL, time_updated integer NOT NULL,
  data text NOT NULL);
CREATE TABLE session_message (
  id text PRIMARY KEY NOT NULL, session_id text NOT NULL REFERENCES session(id) ON DELETE cascade,
  type text NOT NULL, seq integer NOT NULL, time_created integer NOT NULL,
  time_updated integer NOT NULL, data text NOT NULL);
CREATE UNIQUE INDEX session_message_session_seq_idx ON session_message (session_id, seq);
"""


def write_opencode(dice: Dice, sessions: list, data_home: str) -> str:
    folder = os.path.join(data_home, "opencode")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "opencode.db")
    con = sqlite3.connect(path)
    try:
        con.executescript(OPENCODE_SCHEMA)
        projects = {}
        for s in sessions:
            first, last = millis(s.calls[0][0]), millis(s.calls[-1][0])
            pid = projects.get(s.cwd)
            if pid is None:
                pid = projects[s.cwd] = "prj_" + dice.hex(8)
                con.execute("INSERT INTO project VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            (pid, s.cwd, "git", s.folder.split("/")[-1], None, None, None,
                             first, first, first, "[]", None))
            sid = "ses_" + dice.token(26)
            sums = [0, 0, 0, 0, 0]
            rows = []
            prompts = dict(s.prompts)
            seq = 1
            for k, (t, ctx, cached, written, out, reasoning) in enumerate(s.calls):
                if k in prompts:
                    ms = millis(t) - 2000
                    rows.append(("msg_" + dice.token(26), sid, "user", seq, ms, ms, dumps(
                        {"text": prompts[k], "files": [], "agents": [], "time": {"created": ms}})))
                    seq += 1
                uncached = ctx - cached - written
                tokens = {"input": uncached, "output": out - reasoning, "reasoning": reasoning,
                          "cache": {"read": cached, "write": written}}
                for j, v in enumerate((uncached, out - reasoning, reasoning, cached, written)):
                    sums[j] += v
                ms = millis(t)
                done = ms + dice.between(4000, 40000)
                rows.append(("msg_" + dice.token(26), sid, "assistant", seq, ms, done, dumps({
                    "agent": "build", "model": {"id": s.model, "providerID": s.provider},
                    "content": [{"type": "text", "id": "txt_" + dice.token(10),
                                 "text": dice.pick(ANSWERS)}],
                    "finish": "tool-calls" if k < len(s.calls) - 1 else "stop", "cost": 0,
                    "tokens": tokens, "time": {"created": ms, "completed": done}})))
                seq += 1
            title = dict(s.prompts).get(0, "Session")
            con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                        "?,?,?,?,?,?,?,?)",
                        (sid, pid, None, None, title.lower().replace(" ", "-")[:40], s.cwd, None,
                         title, "1.6.3", None, 0, 0, 0, None, None, 0.0, *sums, None, None,
                         "build", dumps({"id": s.model, "providerID": s.provider}),
                         first, last, None, None))
            con.executemany("INSERT INTO session_message VALUES (?,?,?,?,?,?,?)", rows)
        con.commit()
    finally:
        con.close()
    return path


# MARK: - The ledger, by the engine

def demo_env(folder: str) -> dict:
    """The environment that points every reader and every cache Tokenmeter
    has at the demo. HOME moves Gemini CLI's folder, which has no variable of
    its own, and makes every path the engine prints read as ~. Python is told
    not to write bytecode, which macOS's own python3 would otherwise cache
    under the demo's home."""
    home = os.path.join(folder, "home")
    return {
        "HOME": home,
        "CLAUDE_CONFIG_DIR": os.path.join(home, ".claude"),
        "TOKENMETER_CLAUDE_PROJECTS": os.path.join(home, ".claude", "projects"),
        "TOKENMETER_LEDGER": os.path.join(home, ".claude", "cost-ledger.jsonl"),
        "TOKENMETER_PRICE_CACHE": os.path.join(folder, "fetched-prices.json"),
        "TOKENMETER_OFFLINE": "1",
        "TOKENMETER_CURRENCY": "USD",
        "CODEX_HOME": os.path.join(home, ".codex"),
        "XDG_DATA_HOME": os.path.join(home, ".local", "share"),
        "OPENCODE_DB": os.path.join(home, ".local", "share", "opencode", "opencode.db"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def engine(env: dict):
    """tokenmeter.py from this repository, imported with the demo's
    environment in place, so even a path it works out at import time is the
    demo's."""
    os.environ.update(env)
    sys.path.insert(0, REPO)
    import tokenmeter
    return tokenmeter


def seal(tm, env: dict, extra_projects=()) -> None:
    """Every folder and file this process's engine reads: the demo's only."""
    tm.reset_run()
    tm.ONLINE_LOOKUP[0] = False
    tm._ROOTS[:] = [env["TOKENMETER_CLAUDE_PROJECTS"], *extra_projects]
    tm._LEDGER[:] = [env["TOKENMETER_LEDGER"]]
    codex = env["CODEX_HOME"]
    tm.ADAPTER_ROOTS.update({
        "codex": [os.path.join(codex, "sessions"), os.path.join(codex, "archived_sessions")],
        "gemini-cli": [os.path.join(env["HOME"], ".gemini", "tmp")],
        "opencode": [os.path.join(env["XDG_DATA_HOME"], "opencode")],
    })


def build_ledger(env: dict, swept: str) -> tuple:
    """Write the ledger as every run would have: read each log, the swept
    transcripts included, and append what the ledger lacks."""
    tm = engine(env)
    seal(tm, env, [swept])
    paths = tm.transcripts()
    best = tm.scan_transcripts(paths)
    written, _ = tm.reconcile_ledger(best)
    return tm, written


def check(tm, env: dict, made: int, written: int, swept_calls: int) -> None:
    """The engine read every call made here, and a run over what is left on
    disk adds nothing to the ledger and restores exactly the calls whose
    transcripts are gone."""
    problems = []
    if written != made:
        problems.append(f"the engine read {written} calls of the {made} made")
    seal(tm, env)
    best = tm.scan_transcripts(tm.transcripts())
    written, restored = tm.reconcile_ledger(best)
    rows = len(tm.read_ledger())
    if written:
        problems.append(f"a run would add {written} rows to the ledger")
    if restored != swept_calls:
        problems.append(f"{restored} calls restored from the ledger, not {swept_calls}")
    if rows != made:
        problems.append(f"the ledger holds {rows} calls, not {made}")
    if problems:
        sys.exit("make_demo.py: the demo does not check out: " + "; ".join(problems))


# MARK: - Main

def parse_now(text: str) -> dt.datetime:
    if not text:
        return dt.datetime.now().replace(second=0, microsecond=0)
    try:
        return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M")
    except ValueError:
        sys.exit(f"--now: expected a local date and time such as 2026-10-16T17:40, not {text!r}")


def prepare(folder: str, force: bool) -> None:
    real_home = os.path.realpath(os.path.expanduser("~"))
    target = os.path.realpath(folder)
    if real_home == target or real_home.startswith(target + os.sep):
        sys.exit("make_demo.py: refusing to write over a home folder")
    if os.path.exists(target) and os.listdir(target):
        if not force:
            sys.exit(f"make_demo.py: {folder} is not empty; "
                     "pass --force to replace a demo made here")
        if not os.path.isfile(os.path.join(target, MARKER)):
            sys.exit(f"make_demo.py: {folder} was not made by this script, "
                     "so --force leaves it alone")
        for name in os.listdir(target):
            path = os.path.join(target, name)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    os.makedirs(target, exist_ok=True)
    with open(os.path.join(target, MARKER), "w", encoding="utf-8") as f:
        f.write("Made by Tokenmeter's docs/screenshots/make_demo.py. Every figure is invented.\n")


def write_env(folder: str, env: dict) -> str:
    path = os.path.join(folder, "env.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# The Tokenmeter demo's environment, written by docs/screenshots/make_demo.py.\n"
                "# Source it in a subshell: (. env.sh; python3 tokenmeter.py)\n")
        for k, v in env.items():
            f.write(f"export {k}='{v}'\n")
    return path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Write a synthetic home folder of coding agent "
                                             "logs for Tokenmeter's screenshots.")
    ap.add_argument("folder")
    ap.add_argument("--now", default="", metavar="TIME",
                    help="local date and time the history ends, such as 2026-10-16T17:40 "
                         "(default: the current minute)")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--force", action="store_true",
                    help="replace a demo this script made in the same folder")
    args = ap.parse_args(argv)

    now = parse_now(args.now)
    folder = os.path.abspath(args.folder)
    prepare(folder, args.force)
    env = demo_env(folder)
    home = env["HOME"]
    os.makedirs(os.path.join(home, "Downloads"), exist_ok=True)

    dice = Dice(args.seed)
    claude, codex, gemini, opencode = plan(dice, now)
    swept = os.path.join(folder, "swept-transcripts")
    live_files, swept_files = write_claude(dice, claude, env["TOKENMETER_CLAUDE_PROJECTS"],
                                           swept, now)
    write_codex(dice, codex, env["CODEX_HOME"])
    write_gemini(dice, gemini, home)
    write_opencode(dice, opencode, env["XDG_DATA_HOME"])

    tm, written = build_ledger(env, swept)
    cutoff = utc(now) - dt.timedelta(days=CLEANUP_DAYS)

    def calls(s):
        return len(s.calls) + sum(len(a[2]) for a in s.agents)

    swept_calls = sum(calls(s) for s in claude if s.end < cutoff)
    other = sum(len(s.calls) for s in codex + gemini + opencode)
    # Claude Code has since deleted the transcripts older than its cleanup
    # period. The ledger kept their calls.
    shutil.rmtree(swept)
    check(tm, env, sum(calls(s) for s in claude) + other, written, swept_calls)
    env_file = write_env(folder, env)

    print(f"Wrote an invented history ending {now:%d %b %Y %H:%M} to {folder}")
    print(f"  Claude Code: {len(claude)} sessions, {live_files} transcripts on disk, "
          f"{swept_files} deleted after {CLEANUP_DAYS} days")
    print(f"  Codex {len(codex)}, Gemini CLI {len(gemini)} and OpenCode {len(opencode)} sessions, "
          f"{other} calls")
    print(f"  ledger: {written} calls, {swept_calls} of them only in the ledger")
    print(f"Run Tokenmeter against it in a subshell: (. {env_file}; python3 tokenmeter.py)")


if __name__ == "__main__":
    main()
