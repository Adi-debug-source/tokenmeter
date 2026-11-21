---
name: verify
description: Smoke-test Tokenmeter end to end on an invented history. Use before committing any change to Tokenmeter, after the test gate passes, to check the engine, the dashboard and the menu bar app really run and look right.
---

# Verify Tokenmeter

The gate (`python3 tests/test_tokenmeter.py`) proves the rules. This proves the tool runs and looks right. Run the gate first; nothing here repeats it.

Every step runs on the invented history `docs/screenshots/make_demo.py` writes, inside a subshell that has sourced its `env.sh`, so no real log, ledger or cache is read or written. Never verify against real usage or the installed copy in `~/.claude/tools/tokenmeter/`.

## 1. Make the invented home

```sh
T=$(mktemp -d -t tokenmeter-verify)
TZ=Europe/London python3 docs/screenshots/make_demo.py "$T/demo"
```

## 2. Run the engine on it

```sh
( . "$T/demo/env.sh"
  python3 tokenmeter.py > "$T/report.txt"
  python3 tokenmeter.py --by model > "$T/by_model.txt"
  python3 tokenmeter.py --summary-json | python3 -m json.tool > /dev/null
  python3 tokenmeter.py --html "$T/Tokenmeter.html" --no-open )
grep -c "no price table" "$T/by_model.txt"
```

Working means: every command exits 0; `report.txt` shows a dollar total, about 4,000 API calls and all four harnesses (Claude Code, Codex, Gemini CLI, OpenCode); the `grep` prints 0, so every model has a price; the summary is valid JSON; the dashboard is written.

## 3. Look at the dashboard

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory "$T" > /dev/null 2>&1 &
PID=$!
```

Open `http://127.0.0.1:8765/Tokenmeter.html` in a browser with JavaScript on. Working means: the headline figure and the chart draw, the console shows no errors, no request leaves 127.0.0.1, and clicking a currency button changes every figure. Then `kill $PID`, never a kill by name.

## 4. Compile the menu bar app

```sh
swiftc -O -o "$T/costbar" costbar/main.swift -framework AppKit
```

Working means it compiles with no errors. This writes only to the temp folder. Do not verify with `costbar/build.sh` or `./install.sh`: both replace the installed app. The menu itself needs a click, so a change to how it looks is checked by eye against the demo (MAINTENANCE.md, 'Screenshots').

The temp folder holds only invented data; delete it by its printed path when done.

## When it fails

- Fix the cause and run the failing step again. If it still fails after three rounds, stop and bring in a person, with the command and its output.
- Never skip a step or a test, add a sleep, or retry a flaky one until it passes. Find the root cause; if you cannot, stop and say so.

## Keep this file current

When a command here, in AGENTS.md or in MAINTENANCE.md changes, update this file in the same commit, and cut any step that no longer earns its place.
