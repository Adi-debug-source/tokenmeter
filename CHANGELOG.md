# Changelog

## 1.0.0, 26 September 2026

First public release. The engine was built and used privately for Claude Code
in September 2026; this release makes it a standalone project that reads other
harnesses and prices other providers.

### Harnesses

- Claude Code, verified: every transcript, subagents included, checked
  against Claude Code's own `total_cost_usd` to ten decimal places.
- OpenAI Codex CLI, Gemini CLI and OpenCode, unverified: built from each
  harness's published source and tested against sample files in its format.
  Every report that uses one says so.
- `--import FILE` for any other harness, in a documented format
  (`docs/import-format.md`). Imports are de-duplicated and kept by the ledger.
- `--list-adapters` shows what was found and how far to trust it;
  `--adapter NAME` reads only one source; `--by source` and `--by provider`.

### Pricing

- Price tables for Anthropic, OpenAI, Google, xAI, DeepSeek, Mistral, Moonshot
  and Z.ai, 107 models, each read from the provider's own pricing page on
  26 September 2026 and pinned by a test.
- Rates are dated. A call is priced at the rate in force on the day it was
  made; `--current-rates` reprices history at today's rates instead.
- Modelled where published: cache reads, cache writes by lifetime,
  long-context surcharges, fast or priority tiers, dated price changes and
  time-of-day pricing.
- `--check-prices` fetches every provider's page and reports any difference.
  It never edits a table.
- `--list-prices` prints every model with its rates; `docs/prices.md` is
  generated from it, and a test fails if the two ever differ.
- A model no table has is looked up online at startup, from the provider's
  page where possible and LiteLLM's public price list otherwise, saved locally
  with its source and date, and labelled wherever it is used. `--offline`
  turns this off.
- Every report states when each table it used was last checked, and warns
  once that is more than 90 days ago.

### The history outlives the logs

- A ledger, `~/.claude/cost-ledger.jsonl`, holds one row per priced call, so
  "all time" survives Claude Code deleting transcripts after 30 days. It
  stores tokens, never money, so the whole history reprices when a table
  changes. Rows for other providers carry the provider and source; rows
  written before that are read as Claude Code and Anthropic, unchanged.
- `--rebuild-ledger`, `--no-ledger`, `--ledger FILE`.

### Correctness

Each of these was found by using the tool and not believing it, and each has
a test named after it.

- A streamed reply is written once per content block, and every copy but the
  last carries a partial usage block. Keeping the first copy priced a finished
  answer at the length it had four tokens in: 7% of all output missing.
- A `*/*.jsonl` glob silently skipped every subagent transcript.
- Dated model ids such as `claude-haiku-4-5-20251001` fell through to the
  fallback rate, five times Haiku's real price.
- A newer model was priced as an older one it happened to start with: Opus 5.5
  billed at Opus 5 rates, a third too high, and reported as recognised. Only a
  trailing date now means "the same model".
- With the ledger on, `--session` and `--project` reports also counted every
  call the ledger restored, so one session could show the whole history. The
  filters now apply to restored calls too.
- The no-cache counterfactual left out web searches, understating the saving.
- A synthetic record reset the status line's context size to zero.

### Presentation

- Money reads as money: two decimals, thousands separated, four only below a
  penny, `<$0.0001` below that. The "saved" figure is derived from the two
  rounded figures beside it, so the column adds up as printed in every
  currency, on every face.
- Dollars are the default currency; `TOKENMETER_CURRENCY` or `--currency`
  changes it, and no exchange rate is fetched when showing dollars.
- `--since` is rolling, `--period` is the calendar, `--until` closes a range.
- The dashboard is one self-contained file that fetches nothing when opened,
  with fonts embedded; its sections are numbered in page order.
- Paths print with `~` for the home folder, and project names drop it.
- The menu bar's columns line up (a width on `%@` in Swift's
  `String(format:)` is silently ignored, so they never had), and long notes
  wrap onto a second line instead of being cut off.

### Project

- `install.sh` works from any clone, never replaces an existing status line
  unless asked, and `--uninstall` moves files to the Bin rather than deleting.
- 108 tests, standard library only, no network. Past bugs were reintroduced
  deliberately, one at a time, to confirm each test catches its own.
