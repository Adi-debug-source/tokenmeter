# Tokenmeter

A Python tool that prices the local usage logs of Claude Code and other harnesses at API rates, with a dashboard, a menu bar app and a status line. Its only claim is that its numbers are right, so every rule below protects that.

## The worst mistakes here

- Editing the installed copy in `~/.claude/tools/tokenmeter/`: it is the live tool, and the next install overwrites it. Change the repo, run the gate, then `./install.sh`.
- Rewriting the real ledger, `~/.claude/cost-ledger.jsonl`, or running `--rebuild-ledger` on it: calls whose logs have been swept are lost for good. Tests build their own in a temp folder; the real one is only appended to (MAINTENANCE.md, "The ledger").
- Real usage in anything that goes online, a README image or pull request evidence: it shows someone's spend, projects and working days. Capture from the invented history `docs/screenshots/make_demo.py` writes.

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
- The caches beside the engine (`.fx_rates.json`, `.today_cost.json`, `.fetched_prices.json`, `.scan_cache.db`) and any `cost-ledger.jsonl` are usage data and git-ignored; they are never committed.
- A published tag never moves: the Homebrew formula pins the checksum of its tarball.

## Tests and code

- Test what can break, not what types guarantee, trivial logic or copy. Extend an existing test or table first, at one layer: the lowest that fails without the fix, usually the engine.
- No sleep, timeout or retry in a test; a flaky test is fixed, not retried.
- Proof follows the bug: a logic bug gets a failing test first, then the fix; a purely visual one in the dashboard or the menu bar gets before and after captures and no test.
- Builds and any server run from your own shell, so they end with the session. Stop what you started by the process id you kept; never kill by matching a name, which can hit the installed menu bar app (`costbar/build.sh` stops and reloads it through launchd).
- No comment unless it records a constraint, an outside quirk or a fact the code cannot show.

## Working here

- One task per session, with the check that proves it named at the start. Plan first only when the change touches several files; a session that has gone wrong is rewound or abandoned, not argued with.
- The test command above is the gate. It runs before anything is called done, and its output is the evidence: a report names the command that passed and the count. A failing run is reported with its output, never worked around, and a test is never weakened to make it pass.
- The task's scope is the task. No refactors, features, renames or tidying beyond what was asked; a bug found nearby is reported as a follow-up, not fixed in the same change.
- State what a change assumes before writing it. Where the ask reads two ways, or a simpler route exists, ask; never pick silently.
- Understand the real constraint first, then choose the smallest design that makes the right behaviour unsurprising. Inside the task, do not keep complexity only because it is already there. This is for logic and backend code; for the interface, be generous with features and polish.
- The least code that does the job: no option, layer or abstraction nobody asked for, nothing generalised for one caller, no handling for a state that cannot happen. Cut an over-long diff before calling it done.
- Every changed line traces to the task, in the existing style. Remove what your change left unused; older dead code is mentioned, not deleted.
- A correction made twice becomes a check: a test in `tests/`, its docstring naming the mistake, shown to fail on the old code. A line here only when nothing stronger fits.
- Parallel work runs one task per worktree (`claude -w <name>`; `.claude/worktrees/` is ignored by git). Each agent is given the list of files it owns and touches nothing outside it. Two agents never share a file.
- Before a commit: the diff is reviewed in a fresh context (`/code-review`, or `/simplify` for cleanups), then the gate runs again.
- Commits carry the repository's own git identity and say what changed and why. Claude Code's standard co-author line is left on.
- Nothing is pushed, tagged or released without the maintainer's yes, given in chat for that push. Force-pushes are denied in `.claude/settings.json`; a push to main needs that yes like any other.

## Pull requests

- The title is in the conventional form, in plain words saying what changed for the person using it: `fix(dashboard): the chart's tooltip sits beside the bar`. The body gives the problem in a sentence or two, then the fix.
- One request is one pull request.
- A pull request description ends with Claude Code's standard line and always names the model that did the work; the effort level is added only when the session knows it, never guessed.
- A visible change carries before and after images; motion or timing, a short video or GIF. They are made from the invented history, uploaded to the pull request on GitHub and never committed.
