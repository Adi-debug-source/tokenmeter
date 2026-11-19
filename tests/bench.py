#!/usr/bin/env python3
"""How long Tokenmeter takes, measured the way it is really run.

    python3 tests/bench.py                      # a tenth of a heavy history
    python3 tests/bench.py --scale 1            # the whole of one
    python3 tests/bench.py --save before.json   # keep the figures
    python3 tests/bench.py --against before.json   # and compare with them

Not a test, and the gate does not run it. It writes an invented Claude Code
history into a temp folder, copies the engine beside it, as install.sh does,
and times each face as a fresh process, because that is how the menu bar
(every 60 seconds), the status line (every prompt) and the command line run
it. Nothing real is read or written: the copy's home, ledger and caches are
all inside the temp folder, and it runs offline.

The history has the shape of one real one, measured on 19 November 2026:
2,420 transcripts holding 3.0 GB, 145,000 lines with a usage block averaging
3.8 kB among 340,000 other lines averaging 7.1 kB, spread over 60 days.
--scale 1 writes all of that; the default writes a tenth. Every reply is
written twice, a partial copy and then the complete one, as a streamed reply
is.

What is timed, each the fastest of --runs fresh processes, since a slower
run is the machine doing something else as well:

  start-up     importing the engine and doing nothing (five times as many runs,
               being short enough for the machine's noise to show)
  first run    --summary-json with no ledger and no caches yet
  refresh      --summary-json again, after one session has made one more call:
               what the menu bar does every minute
  report       the terminal report
  dashboard    --html, written and not opened
  status line  statusline.py for the longest session, its today figure cached
  status line, today
               the same once the today figure has expired
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = ("tokenmeter.py", "statusline.py", "adapters", "pricing", "dashboard", "fonts")

FILES, CALLS_PER_FILE, DAYS = 2420, 30, 60
USAGE_LINE, OTHER_LINE, OTHERS_PER_USAGE_LINE = 3800, 7100, 2.34
# The session in use, which the status line reads on every prompt: 44 MB.
LONGEST = 1800
MODELS = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")


def stamp(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def call_lines(mid: str, model: str, when: dt.datetime, cwd: str, n: int) -> list:
    """One reply as Claude Code writes it: a partial copy, then the complete one."""
    lines = []
    for out in (4, 400 + n % 900):
        usage = {"input_tokens": 12 + n % 40, "output_tokens": out,
                 "cache_read_input_tokens": 60000 + 500 * (n % 200),
                 "cache_creation_input_tokens": 1500,
                 "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                    "ephemeral_1h_input_tokens": 1500},
                 "service_tier": "standard"}
        line = json.dumps({"type": "assistant", "timestamp": stamp(when), "uuid": f"{mid}-{out}",
                           "requestId": "req_" + mid, "cwd": cwd, "sessionId": "s",
                           "message": {"id": mid, "model": model, "role": "assistant",
                                       "content": [{"type": "text", "text": ""}],
                                       "usage": usage}})
        pad = "x" * max(0, USAGE_LINE - len(line))
        lines.append(line.replace('"text": ""', '"text": "%s"' % pad))
    return lines


def write_history(home: str, scale: float, now: dt.datetime) -> tuple:
    """The invented transcripts under home/.claude/projects. Returns the
    longest one and how many calls were written."""
    files = max(8, round(FILES * scale))
    other = json.dumps({"type": "user", "timestamp": "", "message": {
        "role": "user", "content": [{"type": "tool_result", "content": "y" * OTHER_LINE}]}})
    longest, calls = ("", 0), 0
    for f in range(files):
        cwd = f"/Users/sam/code/project-{f % 8}"
        folder = os.path.join(home, ".claude", "projects", cwd.replace("/", "-"))
        os.makedirs(folder, exist_ok=True)
        # The newest file is today's and the longest, as a session in use is.
        age = dt.timedelta(days=DAYS * (files - 1 - f) / files)
        n_calls = LONGEST if f == files - 1 else CALLS_PER_FILE
        start = now - age - dt.timedelta(minutes=n_calls)
        path = os.path.join(folder, f"session-{f:05d}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            owed = 0.0
            for n in range(n_calls):
                when = start + dt.timedelta(minutes=n)
                fh.write("\n".join(call_lines(f"msg_{f:05d}_{n:04d}", MODELS[(f + n) % 3],
                                              when, cwd, n)) + "\n")
                owed += OTHERS_PER_USAGE_LINE * 2
                while owed >= 1:
                    fh.write(other + "\n")
                    owed -= 1
        end = (start + dt.timedelta(minutes=n_calls)).timestamp()
        os.utime(path, (end, end))
        calls += n_calls
        if n_calls > longest[1]:
            longest = (path, n_calls)
    return longest[0], calls


def one_more_call(path: str, n: int) -> None:
    """A session in use makes another call, as one does between two refreshes."""
    now = dt.datetime.now(dt.timezone.utc)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(call_lines(f"msg_live_{n:04d}", MODELS[0], now,
                                      "/Users/sam/code/project-0", n)) + "\n")


def timed(cmd: list, env: dict, stdin: str = "") -> float:
    began = time.perf_counter()
    done = subprocess.run(cmd, env=env, input=stdin, text=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE)
    took = time.perf_counter() - began
    if done.returncode:
        sys.exit(f"{' '.join(cmd)} failed:\n{done.stderr}")
    return took


def measure(python: str, scale: float, runs: int) -> dict:
    tmp = tempfile.mkdtemp(prefix="tokenmeter-bench-")
    try:
        home, engine = os.path.join(tmp, "home"), os.path.join(tmp, "engine")
        os.makedirs(engine)
        for name in ENGINE:
            src = os.path.join(REPO, name)
            if os.path.isdir(src):
                shutil.copytree(src, os.path.join(engine, name),
                                ignore=shutil.ignore_patterns("__pycache__", ".*"))
            else:
                shutil.copy(src, engine)
        longest, calls = write_history(home, scale, dt.datetime.now().astimezone())
        size = sum(os.path.getsize(os.path.join(d, f))
                   for d, _, fs in os.walk(os.path.join(home, ".claude")) for f in fs)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": home,
               "CLAUDE_CONFIG_DIR": os.path.join(home, ".claude"),
               "TOKENMETER_CLAUDE_PROJECTS": os.path.join(home, ".claude", "projects"),
               "TOKENMETER_LEDGER": os.path.join(home, ".claude", "cost-ledger.jsonl"),
               "TOKENMETER_PRICE_CACHE": os.path.join(tmp, "prices.json"),
               "TOKENMETER_OFFLINE": "1", "TOKENMETER_CURRENCY": "USD",
               "TOKENMETER_STATUS_TOKENS": "1",
               "CODEX_HOME": os.path.join(home, "no-codex"),
               "XDG_DATA_HOME": os.path.join(home, "no-xdg"),
               "KIMI_CODE_HOME": os.path.join(home, "no-kimi"),
               "DSH_HOME": os.path.join(home, "no-dsh"),
               "GEMINI_CLI_HOME": os.path.join(home, "no-gemini")}
        tm = [python, os.path.join(engine, "tokenmeter.py")]
        status = [python, os.path.join(engine, "statusline.py")]
        session = json.dumps({"model": {"display_name": "Opus 5.5"}, "transcript_path": longest})
        today = os.path.join(engine, ".today_cost.json")

        def fastest(fn, times: int = 1) -> float:
            return min(fn(i) for i in range(runs * times))

        def refresh(i):
            one_more_call(longest, i)
            return timed(tm + ["--summary-json"], env)

        def status_today(i):
            if os.path.exists(today):
                os.remove(today)
            return timed(status, env, session)

        results = {"first run": timed(tm + ["--summary-json"], env)}
        results["start-up"] = fastest(lambda i: timed(
            [python, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import tokenmeter",
             engine], env), times=5)
        results["refresh"] = fastest(refresh)
        results["report"] = fastest(lambda i: timed(tm, env))
        results["dashboard"] = fastest(lambda i: timed(
            tm + ["--html", os.path.join(tmp, "page.html"), "--no-open"], env))
        results["status line, today"] = fastest(status_today)
        results["status line"] = fastest(lambda i: timed(status, env, session))
        return {"python": subprocess.run([python, "--version"], capture_output=True,
                                         text=True).stdout.strip(),
                "scale": scale, "runs": runs, "calls": calls, "megabytes": round(size / 1e6),
                "seconds": results}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


ORDER = ("start-up", "first run", "refresh", "report", "dashboard", "status line",
         "status line, today")


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--scale", type=float, default=0.1,
                    help="how much of the measured history to write (default 0.1; 1 is 3 GB)")
    ap.add_argument("--runs", type=int, default=5, help="processes per figure (default 5)")
    ap.add_argument("--python", default=sys.executable,
                    help="the Python to time (the menu bar runs /usr/bin/python3)")
    ap.add_argument("--save", metavar="FILE", help="write the figures here as JSON")
    ap.add_argument("--against", metavar="FILE", help="compare with figures saved earlier")
    args = ap.parse_args()

    got = measure(args.python, args.scale, args.runs)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(got, f, indent=2)
    print(f"{got['python']}, {got['calls']:,} calls in {got['megabytes']:,} MB of transcripts, "
          f"fastest of {got['runs']}")
    before = None
    if args.against:
        with open(args.against, encoding="utf-8") as f:
            before = json.load(f)
        if (before["scale"], before["python"]) != (got["scale"], got["python"]):
            sys.exit(f"{args.against} was measured at scale {before['scale']} on "
                     f"{before['python']}: not comparable")
    for name in ORDER:
        now = got["seconds"][name]
        if before:
            was = before["seconds"][name]
            print(f"  {name:<20}{was:8.3f} s  to{now:8.3f} s   {was / now:5.1f}x")
        else:
            print(f"  {name:<20}{now:8.3f} s")


if __name__ == "__main__":
    main()
