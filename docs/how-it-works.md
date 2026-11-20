# How it works

1. **Read.** One adapter per harness reads its logs and says what each API call was: model, provider, time, and tokens split into uncached input, cache reads, cache writes and output.
2. **De-duplicate.** Harnesses write the same response more than once: once per streamed content block, again when a session is resumed or forked. Tokenmeter keys every call by its response id and keeps the complete copy, which is the largest. Counting log lines instead overstates usage several times over.
3. **Price.** Each call is priced from its own provider's table at the rate in force that day.
4. **Remember.** Every priced call is written to a ledger, so history outlives the logs.

All the arithmetic lives in `tokenmeter.py`. The menu bar and status line only display what it computes.

## The ledger: an "all time" that lasts

Claude Code deletes transcripts after 30 days by default, and Codex compresses them after a week, so a tool that reads only logs has an "all time" that quietly shrinks. Tokenmeter keeps its own record, `~/.claude/cost-ledger.jsonl`, one line per call:

- **Tokens, never money.** A ledger of dollars would be frozen at the prices on the day it was written; a ledger of tokens reprices the whole history whenever a table changes.
- **Append only.** A row that supersedes an earlier one is appended, never edited, so the file is safe to keep in git and every diff is only the new lines.
- **Updated by every run that uses it, never on a schedule.** The menu bar's 60-second refresh keeps it current.
- **Small.** About 220 bytes a call, a couple of megabytes a year.
- **Losing it degrades, it does not break.** Without it the tool falls back to the logs on disk.

```bash
tokenmeter --no-ledger          # price only what the logs hold
tokenmeter --ledger FILE        # use a different ledger
tokenmeter --rebuild-ledger     # rewrite it from every log on disk (takes no filters; every old copy is kept)
```

## Total tokens

One definition, used wherever a total is given: **total tokens = uncached input + cache writes + cache reads + output.** Thinking is already part of output, so it is not added again, and web searches are counted as requests, not as tokens. Each call is counted once, from its complete copy, however many times its log wrote it.

The report gives the total under the cost, in the same shape, and under that the fresh tokens: the total less cache reads. Cache reads are the context read again on every turn, usually the great majority of a total, so the total mostly measures re-reading and the fresh figure is the one that follows how much new work went in.

```
  $1,024.50   8,120 API calls
  1.62B tokens   8,120 API calls
  of which fresh (excluding cache reads): 61.30M
  21 Jul 2026 to 14 Oct 2026 · 214 transcripts on disk · ledger holds 8,120, 1,410 of them no longer in any transcript
  kept by the ledger 1.62B · on disk now 1.31B · 310.40M from 12 sessions whose transcripts are gone
```

The last line splits the same total by where its calls are now. Deleting a session deletes its transcript, so a total read from the transcripts goes down; the on-disk figure falls with it, while the kept figure does not, because the ledger keeps every call. A window or a filter applies to all three figures as it does to the money. With `--no-ledger` there is no such line, and the total, which is then only what the transcripts on disk hold, says so: `transcripts on disk only`.

`--by`, in every grouping, and `--sessions` give each row its total tokens beside its cost and calls.

The dashboard gives the total in a tile beside the API calls, with the fresh tokens under it. When the ledger holds calls no transcript has any more, a note under the tiles gives the same kept and on-disk split, and why: deleted sessions take their transcripts with them, and Tokenmeter keeps the record. The Tokens view of its Spend over time chart counts each day the same way, the days only the ledger still has included.

The status line can give today's total beside today's cost, `$4.56 · 1.20M today`, when `TOKENMETER_STATUS_TOKENS` is set to `1` (see [Settings](../README.md#settings)). The menu bar's Show tokens switch, in its menu, gives each window's total beside its cost: in the menu bar for the window shown, `$4.56 · 1.20M`, and on the four window rows of the menu, lined up:

```
Today                $4.56 ·   1.20M
Last 7 days         $61.20 ·  98.40M
Last 30 days       $250.75 · 410.00M
All time         $1,024.50 ·   1.62B
```

Flipping it changes the menu bar and every row at once and leaves the menu open. From the keyboard, Command-T toggles it while the menu is open. The status line's setting and the menu bar's switch are both off unless asked for, so each is otherwise exactly as it was.

`--summary-json`, which the menu bar reads, gives the same figures: a `tokens` object (`input`, `cache_write`, `cache_read`, `output`, `thinking`, `total` and `fresh`) for today, the last 7 days, the last 30 and all time, and for all time `tokens_on_disk` and `tokens_ledger_only`. `--json` gives them for its run.

## Rolling windows and calendar periods

`--since` is rolling and always the same length, so `--since 30d` is comparable with the thirty days before it. `--period` is the calendar, which is what you want when checking against a bill: `lastmonth` is whichever month just ended. Weeks start on Monday. The menu bar uses rolling windows, because "this week" on a Monday morning is an hour long.

`--since` and `--until` also take a date or a date and time, such as `2026-09-01` or `2026-09-01T10:00`. Both are local time unless they carry an offset or a `Z`, so a date starts at local midnight, as the calendar periods do. `--until` stops just before the moment it names.

## What orchestration costs

A session that spawns subagents costs more because every subagent makes its own API calls. Tokenmeter reads subagents' and workflow agents' transcripts too, and files their calls under the session that started them, so that cost is counted. On one real history a quarter of all spend was subagents. `--by session` and the dashboard show where it went. Effort settings change how many tokens a model produces, never the price per token, so they need no special handling.

## JSON for scripts

`--json` gives a script the same run: the totals with their components and tokens, the version, the window, the covered line, the notes, any model with no price, the cost without cache reads, and the tokens on disk and held only by the ledger. Each tokens object gives every kind of token and then the total and fresh tokens (see [Total tokens](#total-tokens)). With `--by` or `--sessions` it adds the groups or the dearest sessions, in the terminal's order. New keys are only ever added, so a script written for an older version keeps working.

## Next to other counters

Why the figures differ from Claude Code's Stats tab and from the Claude app, and what "all time" covers, are answered in the [README](../README.md#questions).
