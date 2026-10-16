# Tokenmeter

A Python tool that prices the local usage logs of Claude Code and other harnesses at API rates, with a dashboard, a menu bar app and a status line. Its only claim is that its numbers are right, so every rule below protects that.

## Commands

- Test: `python3 tests/test_tokenmeter.py` (the gate: a Stop hook runs it at the end of every turn; a few hundred tests in about five seconds, standard library only, no network; one area alone runs as `python3 tests/test_ledger.py`)
- Run: `python3 tokenmeter.py`, with `--by model`, `--by source`, `--sessions`, `--json`, `--summary-json`, `--html`, `--check-prices`
- Prices document: `python3 tokenmeter.py --list-prices --markdown > docs/prices.md`
- Install locally: `./install.sh`
- Release, Homebrew, screenshots, the menu bar app and the dashboard's fonts: MAINTENANCE.md is the authority. Read the section the task needs; nothing from it is copied here.

## Layout

The table in MAINTENANCE.md, "How it fits together", names every part. In short: `tokenmeter.py` is the engine; `adapters/` has one reader per harness; `pricing/` one table per provider; `dashboard/`, `costbar/` and `statusline.py` display only; `tests/` one module per area, with `test_tokenmeter.py` running them all.

## Conventions this code keeps

- Arithmetic lives in `tokenmeter.py` and nowhere else: an adapter never prices, a price file never adds up, and a figure the menu bar or a script needs is added to `--summary-json` rather than computed again. Six past bugs were a second copy of some logic drifting from the first.
- `--json` and `--summary-json` only ever gain keys, appended after the existing ones, because the menu bar and scripts read them by name.
- `money()` and `toks()` exist three times on purpose (Python, Swift in `costbar/main.swift`, JavaScript in `dashboard/dashboard.js`) and follow one rule each. A change to one is a change to all three, or the same figure reads differently in different places.
- A rate change is a new dated row in its table; the old row is never edited. Every rate is pinned by a test typed from the provider's page, and `docs/prices.md` and the README's price table must match the tables or a test fails.
- Python 3.9 and up. `from __future__ import annotations` stays at the top of the engine; CI compiles everything with `-W error` on 3.9, 3.13, 3.14 and 3.15 and runs the suite on each.
- Every test names in its docstring the bug it guards, so a failure says what broke. A new test does the same. Tests build fixtures in a temp folder and fake every fetch.

## Gotchas

- Output that does not go to a terminal is plain text; captured output needs `FORCE_COLOR=1` to keep its colours.
- The chart (`drawChart()` in `dashboard/dashboard.js`): the SVG viewBox is set from the measured width every draw, the tooltip sits beside the bar, and every page's gradient ids carry the page's name. Each of the three was once a bug.
- An element hidden until it scrolls into view needs a line in the stylesheet's `@media print` block; a test in `tests/test_dashboard.py` fails for any it does not cover.
- A harness update can change its log format. After one: the tests, then `--by model` for a model with no price, then whether the call count is still plausible.
- When a number looks wrong, in this order: `--no-ledger`, `--by model`, `--by source`, `--by day`. Each rules out the one below.
- The caches beside the engine (`.fx_rates.json`, `.today_cost.json`, `.fetched_prices.json`) and any `cost-ledger.jsonl` are usage data and git-ignored; they are never committed.
- A published tag never moves: the Homebrew formula pins the checksum of its tarball.

## Working here

- One task per session, with the check that proves it named at the start. Plan first only when the change touches several files; a session that has gone wrong is rewound or abandoned, not argued with.
- The test command above is the gate. It runs before anything is called done, and its output is the evidence: a report names the command that passed and the count. A failing run is reported with its output, never worked around, and a test is never weakened to make it pass.
- The task's scope is the task. No refactors, features, renames or tidying beyond what was asked; a bug found nearby is reported as a follow-up, not fixed in the same change.
- Parallel work runs one task per worktree (`claude -w <name>`; `.claude/worktrees/` is ignored by git). Each agent is given the list of files it owns and touches nothing outside it. Two agents never share a file.
- Before a commit: the diff is reviewed in a fresh context (`/code-review`, or `/simplify` for cleanups), then the gate runs again.
- Commits carry the repository's own git identity and say what changed and why. No AI attribution lines or trailers, ever.
- Nothing is pushed, tagged or released without the maintainer's yes, given in chat for that push. Force-pushes and pushes to main are denied in `.claude/settings.json`; a release push is the maintainer's own command.
