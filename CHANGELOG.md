# Changelog

## 1.2.0, unreleased

Total tokens on every face, by one definition, beside the money, and the
tokens the ledger has kept that the transcripts on disk no longer hold. Prices
read again on 15 October 2026, and fixes across the engine, the status line,
the dashboard and the menu bar.

### Prices

- `--check-prices` no longer names a retired model as missing from its page. A
  table can list models the provider has retired in `RETIRED`, with the date
  from the provider's own notice; they keep their last published price, so
  older usage is still priced, and the price list marks them. Four so far:
  `gemini-2.5-computer-use-preview-10-2025` (shut down 28 July 2026),
  `zai-glm-5-2` on Mistral (retires 31 October 2026, replaced by GLM 5.3 at
  the same price), and `gemini-3.5-flash` and `gemini-3.7-flash` (below).
  Google's and Mistral's tables were re-read in full and marked verified on 6
  October 2026.
- Claude Sonnet 5.5 cache reads cost $0.10 per million from 7 October 2026,
  0.05x input instead of 0.1x, per Anthropic's release notes of that day and
  the pricing page, read on 15 October 2026. Cache writes and every other
  price are unchanged. A call made before 7 October keeps the $0.20 it cost
  then; until now every Sonnet 5.5 cache read was priced at $0.20.
- Claude Haiku 5.5, launched on 7 October 2026 per Anthropic's release notes,
  is in the table, read off the pricing page on 15 October 2026. It is priced
  by prompt length: up to 100,000 tokens, $0.10 in, $0.50 out, $0.01 a cache
  hit, $0.125 and $0.20 for 5-minute and 1-hour cache writes; over 100,000
  tokens (cache reads and writes count towards it), five times each. Until
  now it was priced by the online lookup, and the status line, which never
  looks anything up, priced it at the Opus 5 stand-in rate until a report
  had saved a lookup.
- `--check-prices` reads a model the page lists as two prompt-length rows as
  one model, and checks every column of both tiers and the threshold.
  Anthropic's table is marked verified on 15 October 2026, all 20 models
  matching.
- `gemini-3.5-flash` and `gemini-3.7-flash` are retired as of 8 October 2026,
  when the Gemini API changelog deprecated them and began routing their
  requests to `gemini-3.6-flash` and `gemini-3.8-flash`; the pricing page no
  longer lists them. Both keep their last published price for older usage.
  Neither the changelog nor the deprecations page says what a routed call is
  billed at, which matters for 3.5 Flash, priced above 3.6 Flash. Google's
  table is marked verified on 15 October 2026.
- The built-in exchange rates, used only when no rate can be fetched and none
  is saved, are refreshed from open.er-api.com as read on 15 October 2026.
  Four of them had drifted 3 to 4% low.

### Fixes

- `--rebuild-ledger` refuses `--project`, `--session`, `--adapter`, a window
  (`--since`, `--until`, `--period`) and `--no-ledger`, and touches nothing
  when it does. A rebuild from a filtered run replaced the whole ledger with
  the part of it that run could see.
- `--rebuild-ledger` never overwrites a backup. The old ledger goes to `.old`,
  or, when that exists, to `.old` stamped with the date and time; a second
  rebuild used to overwrite the first one's `.old`. Its message counts in
  correct plurals, prints paths with `~`, and says how many of the calls it
  could not keep were imported, which passing the same `--import` files keeps.
- `--summary-json` honours `--no-ledger`, so a trial import with it is no
  longer written to the ledger for good. It always covers today, the last 7
  and 30 days and all time, so it refuses `--since`, `--until`, `--period`,
  `--project` and `--session` instead of ignoring them; `--adapter` and
  `--import` still narrow or add to what it reads. A mistyped
  `TOKENMETER_CURRENCY` no longer stops it, so it cannot blank the menu bar.
- A report filtered with `--project`, `--session` or `--adapter` no longer
  says the ledger's other calls are "no longer in any transcript": that run
  never read the other logs, so it cannot know. It still says how many calls
  the ledger holds. Unfiltered and windowed reports, which read every log,
  count them as before.
- A usage block whose cache writes are given both as a total and split by
  lifetime, with the two disagreeing, is priced, written to the ledger and
  sized by one rule. Three rules applied: such a call was written to the
  ledger again on every run, and a zero split beside a total was stored as no
  writes at all, so once its transcript was gone it was priced without them.
  No such block has been seen in Claude Code's logs, so no total moves.
- A call written to several transcripts, as a resumed or forked session
  copies its earlier calls, is filed under its earliest copy's time, session
  and project, and copies made at the same moment, which a resume's always
  are, go to the copy whose project and session sort first. It went to the
  first copy read, and the order files are listed in differs from one machine
  to the next. Nothing in the copies says which session made the call, so the
  rule is fixed rather than found. No total moves; some calls move between
  sessions of the same project.
- Calls made by workflow agents, whose transcripts lie in
  `<session>/subagents/workflows/<id>/`, are filed under the session that
  started them and its project, as subagents' calls are. They were filed under
  a project named after the workflow and a session named after the agent's own
  file, so `--session` and `--project` missed them. Calls the ledger already
  holds keep the project and session they were written with once their
  transcripts are swept, because the ledger is only ever added to.
- `--session` given a file reads it with the adapter its format belongs to
  and keeps the session ids its calls carry. It filtered on the file's name,
  which is not how Codex, Gemini CLI or a Claude Code agent's transcript names
  its session, so each of them found nothing; and a Gemini CLI file was read
  as Claude Code's. A Claude Code transcript now brings its agents' with it,
  and the report is labelled with the session's id.
- `--project` finds a project by its folder's own name, its full path, or
  `.` for the current folder. Claude Code names a project's folder after its
  path with every character that is not a letter or digit turned into `-`,
  and the filter was matched against that alone, so a name with a space or
  punctuation, such as `My App`, or a full path found nothing. Every harness's
  projects are now matched both ways, ignoring case, and the report's label
  names the project without the home folder.
- A `--project`, `--session` or `--adapter` that matches no call stops with
  "no calls match" and the filters as given, and for `--project` lists up to
  five projects that do have calls, latest first. It said "nothing to price.
  Looked for:" and listed folders full of logs, or, where a reader cannot
  narrow its files by project, printed an empty report; `--session` had a
  message of its own. A window that leaves a matching filter with no calls
  still prints its empty report, and a machine with no logs and an empty
  ledger still says where it looked.
- `--since` and `--until` take a date as local midnight, as `--period` and
  the day buckets always have; it was midnight UTC. A time with no offset is
  local time, and an offset or a `Z` is kept: the whole value was lowercased,
  so `2026-10-01T10:00Z` was refused and an offset was read as UTC. A value
  too large to count back, such as `99999999d`, exits with a message naming
  the flag instead of a traceback, and a report with `--until` alone is
  labelled "until ..." rather than "all time".
- `--current-rates` prices every call at the rates in force today. It took
  each model's newest price even when that starts later: Gemini 3.6, 3.7 and
  3.8 Flash have a list price Google has set from 1 January 2027, twice their
  launch price, so their calls were charged double. A call with no timestamp
  is priced at today's rates the same way.
- `--offline` and `TOKENMETER_OFFLINE=1` now make no network requests at all.
  They used to stop only the price lookup, and exchange rates were still
  fetched. Offline, the last saved rate is used at any age and marked
  "cached" with its date; with none saved, the built-in estimate is used and
  labelled as one.
- A run asks for exchange rates once. The menu bar asked three times per
  refresh, and on a dead network each attempt sat through its timeout. A
  failed fetch is now recorded and not retried for an hour; the last saved
  rate, marked stale, or the estimate stands in meanwhile.
- The exchange-rate note says what it is once: it read
  "(OFFLINE ESTIMATE, offline estimate, no cached rate)".
- The online price lookup downloads each page at most once a run, so an
  unreachable source costs one timeout instead of one per model.
- A lookup that could not reach its price lists is no longer remembered for a
  day as found nowhere. It is tried again after ten minutes, and the report
  says the price lists could not be reached instead of that no price is
  published.
- A looked-up rate whose weekly recheck fails is kept and rechecked the next
  day. The recheck used to be downloaded again on every run.
- A model priced from its provider's page keeps the page's dated prices
  (Google's launch prices and the ones that follow them), its provider's
  long-context threshold (above 200,000 tokens for Google and 199,999 for
  xAI, where every looked-up model used OpenAI's 272,000) and a 1-hour cache
  write that differs from the table's default.
- The status line never makes a network request. Showing another currency,
  it fetched exchange rates once the saved rate was 12 hours old, and on
  every prompt while the network was down, each time holding the prompt up
  for as long as 8 seconds. It now uses the rate a report, the dashboard or
  the menu bar last saved.
- A mistyped `TOKENMETER_CURRENCY`, such as `GPB`, no longer stops the status
  line: it shows dollars instead of printing nothing. The command line still
  refuses an unknown code, and now says when it came from
  `TOKENMETER_CURRENCY` rather than from `--currency`.
- The status line's session cost includes the session's subagents and
  workflow agents. It priced the session's own transcript alone, which left
  out every call its agents made for it. The context figure is still the main
  conversation's.
- The status line's "today" starts at local midnight at that day's own UTC
  offset. It used the offset in force when it ran, so on the days the clocks
  change it started an hour late or early: in London it would have left out
  the first hour of 25 October 2026. Its saved total now carries its date, so
  for the first 90 seconds after midnight it no longer shows yesterday's total
  as today's.
- The status line takes the context window's size and how full it is from
  Claude Code, which sends both. It guessed them from the model's name (Haiku
  200k, anything else 1M), so a 200k model other than Haiku showed a fifth of
  its real percentage, and a Haiku with a 1M window read full at 200k. Claude
  Code builds that send neither still get the guess. A window other than 200k
  or 1M is shown at its size, for example 400.0k.
- A compressed Codex session (`.jsonl.zst`) that is cut short or corrupt, as
  one is while Codex is still compressing it, is skipped and reported as
  possibly damaged. On Python 3.14 it ended every run in a traceback, and on
  older versions the report said to install zstd when zstd was installed.
- The menu bar reads compressed Codex sessions when zstd came from Homebrew.
  It runs under launchd, whose PATH has no Homebrew folder, so it never found
  the command: it left out every Codex session older than a week until a
  terminal run had recorded it, and said to install zstd. The command is now
  also looked for in `/opt/homebrew/bin` and `/usr/local/bin`.
- Each compressed Codex session is decompressed once a run, not twice. Its
  text is now split into lines as a plain session's is: a raw U+2028
  character inside a line split it in two, and when that line named the model
  its calls were priced as gpt-5.
- The note on Codex calls priced as gpt-5 counts each call once. A session
  from before Codex 0.36 in both `sessions` and `archived_sessions` was
  counted twice in the note, though once in the figures.
- A token count of `Infinity` or `NaN` in a Codex, Gemini CLI or OpenCode
  log, both of which JSON readers accept, reads as none, where it could end
  the run in a traceback. The three readers now share one rule for a count.
- An import line with a count of `1e999`, `Infinity`, `NaN` or a number too
  large to price, or with a byte that is not UTF-8, is skipped and explained
  like any other bad line. One such line ended the whole run in a traceback,
  from a file or from standard input.
- Import timestamps in the basic form (`20260920T100211Z`), with a comma
  before the fraction of a second, or with an offset written `+0100` or `+01`
  are read on every Python version. Python 3.9, which the menu bar runs,
  skipped them as unreadable while a newer Python in the terminal counted
  them, so the two disagreed.
- A negative amount puts its minus before the currency symbol, `-$0.10`, in
  the terminal, the dashboard and the menu bar alike. It printed `$-0.10`.
- The menu bar and the dashboard write `1,234.50` on a Mac set to any
  language, as the terminal does. They followed the system's locale, so on a
  Mac set to German the same figure read `1.234,50` there and `1,234.50` in
  the terminal, and the menu bar's own sub-penny amounts kept the full stop.
- One call is "1 API call" in the terminal's header and "1 call" in its
  `--by` tables, the dashboard's chart tooltip and the menu bar's tooltips,
  instead of "1 API calls" and "1 calls". The dollar figure printed beside
  another currency follows the rule every other amount does, so a sub-penny
  total reads `£0.0056 ($0.0075)` rather than `£0.0056 ($0.01)`.
- When caching cost more than it saved, as it does when cache writes are
  never read back, every face says so: the terminal and the menu bar read
  "caching cost $0.10, 99.7% dearer" and the dashboard's card is titled
  "Caching cost". They read "saved $-0.10, -99.7% cheaper, 0.5x" and
  "Caching made it 0.5x less expensive". With no cache reads at all, the
  terminal and the dashboard no longer quote a cache rate of $0.0000 per
  million.
- The dashboard writes a provider's name as text wherever it appears: in an
  attribute, in its data block and in the chart's tooltip. Provider names come
  from import files and from OpenCode's and Codex's logs, and one holding
  markup, such as `</script>` or a double quote, broke the page and ran as
  part of it when the page was opened.
- The dashboard's fourth window tile and the caption of "When the work
  happens" are named for the run's own window, such as "September 2026" for
  `--period lastmonth`. They always said "All time", though the tile showed
  that window's total and the section covered only that window.
- The dashboard's "Last seen" cell for a session with no time reads "?", as
  the terminal's sessions list does, instead of a dash.
- The Tokens view of the dashboard's Spend over time chart writes its
  running total as every other token count is written (`950.0k`,
  `1.62B`). Under half a million it read `0M tokens`, and above that it
  dropped the decimals the day's own count beside it has.
- `--html` opens the page with `open` on macOS and with `xdg-open`
  elsewhere, and where neither can be run it writes the page and says
  where, with no error. It ran `open` everywhere, so on Linux the run
  ended in a traceback after writing the page. With no `~/Downloads`
  folder, its default path is `Tokenmeter.html` in the current folder.
- The dashboard prints. Every section below the first screen waited at
  opacity 0 to be scrolled into view, so a print or a PDF of it was blank
  pages; a page printed straight after opening also caught the headline
  part way through counting up to its total. On paper every section,
  table row, bar and chart line is drawn as it ends, the headline shows its
  total, the currency and harness menus and the chart's toggles are left
  out, cards and table rows are not split across pages, and the page stays
  dark to its edges with no header or footer carrying the file's path.
- The menu bar's "Daily spend, last 30 days" sparkline covers the last 30
  calendar days, a day with no calls at zero. It drew the last 30 days that
  had any calls, so after a break it reached further back and drew the days
  either side of the gap as neighbours. `--summary-json`'s `days` now always
  holds those 30 days, oldest first.
- When the menu bar cannot read usage, its title is a hyphen instead of an en
  dash, and the reason is still in its tooltip and menu.
- The README describes `TOKENMETER_CLAUDE_PROJECTS` as it works: the Claude
  Code folders to read instead of the default, so `~/.claude/projects` must
  be one of them to count this Mac as well as a copied folder. It called them
  "extra" folders, and following it left this Mac's own transcripts out.
- "Nothing to price", `--list-adapters` and `--help` link to the import
  format on GitHub. They named `docs/import-format.md`, which the installer
  does not copy, so the installed engine pointed at a file it did not have.

### New

- The terminal report gives total tokens under the cost, in the same shape
  ("1.62B tokens   8,120 API calls"). Total tokens have one definition,
  stated in the README and used wherever a total is given: uncached input,
  cache writes, cache reads and output. Thinking is already inside output,
  so it is not added again, and web searches are not tokens. The report
  listed each kind of token but never their sum, so the only total anyone
  saw was one counted another way.
- Under the total, the report gives the fresh tokens: the total less cache
  reads ("of which fresh (excluding cache reads): 61.30M"). Cache reads are
  the context read again on every turn and most of any total, so the total
  alone read as that much new text.
- Beside the covered line's "ledger holds", the report splits the total by
  where its calls are now: "kept by the ledger 1.62B · on disk now 1.31B ·
  310.40M from 12 sessions whose transcripts are gone". Deleting a session
  deletes its transcript, so a total read from the transcripts goes down;
  the ledger's does not, and the report now says so in tokens as well as in
  calls. Windows and filters apply to all three figures as to the money.
  With `--no-ledger` the total says it covers the transcripts on disk only.
- `--summary-json` gives tokens: a `tokens` object (`input`, `cache_write`,
  `cache_read`, `output`, `thinking`, `total` and `fresh`) in `today`,
  `week`, `month` and `all`, and `tokens_on_disk` and `tokens_ledger_only`
  in `all`. `--json` adds `total` and `fresh` to each of its tokens objects,
  gives each listed session its tokens, and sends `tokens_on_disk` and
  `tokens_ledger_only`. Every key already there keeps its value.
- `--by`, in every grouping, and `--sessions` give each row its total tokens
  in a column of its own, beside its cost and calls.
- The dashboard gives total tokens in a tile beside the API calls, with the
  fresh tokens under it. When the ledger holds calls no transcript has any
  more, a note under the tiles gives the report's kept and on-disk split
  and the reason: deleted sessions take their transcripts with them, and
  Tokenmeter keeps the record. The tiles sit closer together so all five
  keep one line in a full-width card. The Tokens view of the Spend over
  time chart was checked and already counted each day by the same
  definition, the days only the ledger still has included.
- The status line can give today's total tokens beside today's cost,
  `$4.56 · 1.20M tok today`, when `TOKENMETER_STATUS_TOKENS` is set to
  `1`. It is off by default, and without it the line is byte for byte what
  it was. The tokens are the engine's total, counted in the same pass as
  today's cost and kept in the same 90-second cache.
- The menu bar can give the total tokens of the window it shows beside its
  cost, `$4.56 · 1.20M tok`, from "Show tokens in the menu bar" in its
  menu. It is off until switched on and is remembered as its currency is.
  It reads each window's `tokens` object from `--summary-json`.
- The README answers "Why doesn't this match the Claude app?" in three
  points: the app's figure falls when sessions are deleted while the
  ledger keeps them, it appears to count partial copies of streamed
  replies that Tokenmeter counts once, and so for the same work
  Tokenmeter's total was the lower and does not go down. Each is put as
  what was observed, not as how the app works.
- `--help` groups its options under headings (what to read, the window, the
  report, the output, prices and the ledger) and ends with examples from the
  README. It says what `--by` groups by, that `--until` stops just before the
  moment it names, where `--html` writes by default and everything
  `--summary-json` carries, and it writes the ledger's default path with `~`
  rather than with the username in it.
- The command line prints plain text when its output is not a terminal, so a
  pipe, a file and Claude Code's `/tokenmeter` no longer get colour codes
  among the figures. `NO_COLOR` turns colour off anywhere, and `FORCE_COLOR`
  or `CLICOLOR_FORCE` keeps it in a pipe; `NO_COLOR` wins over both. The
  status line keeps its colours, which Claude Code shows.
- `--json` carries what the terminal says around the totals: the version,
  the window as ISO 8601 (`since` and `until`, null for an open end), the
  covered line, the notes, any model with no price and the cost without
  cache reads. With `--by` it adds the groups, and with `--sessions` the 20
  dearest sessions, in the terminal's order. It printed the same seven keys
  whatever was asked; those keep their values.
- `--by week` and `--by month` group a report by ISO week (`2026-W41`,
  Monday to Sunday, as `--period week` counts one) and by calendar month
  (`2026-10`), oldest first like `--by day`, in the terminal and in
  `--json`. Each is the sum of its local days, so they add up to the same
  total.
- `--no-open` writes the dashboard with `--html` and opens nothing, for a
  page made by a script or on a machine with no desktop.
- On a first run, with no logs and no calls, the menu bar says where
  Tokenmeter looked and to run `tokenmeter --list-adapters`, instead of a
  bare $0.00. `--summary-json` sends it as the first of its notes.
- The `/tokenmeter` command takes "this project" as `--project .` and "tokens"
  as the report, and shows its token lines as the script prints them.

### Project

- `--summary-json` sends `saved_pct` and `multiple`, the figures behind the
  menu bar's "N% cheaper, Nx" line, which the menu bar used to divide out for
  itself. Every other key keeps its value. The terminal, the dashboard and
  the summary now take their rolling windows and caching figures from one
  place in the engine each.
- The tests are split by area, one module each for money, pricing, the pinned
  published rates, the ledger, the adapters, the network lookups, reports, the
  dashboard and the status line, with what they share in `tests/helpers.py`.
  `python3 tests/test_tokenmeter.py` still runs them all, and one area runs on
  its own. 295 tests in all.
- The dashboard's stylesheet and script are files of their own,
  `dashboard/dashboard.css` and `dashboard/dashboard.js`, instead of about
  550 lines of strings inside the engine. They are read when a page is
  written, so the page is still one file that fetches nothing, and the
  status line never reads them. `install.sh` copies the folder; an install
  missing either file says so and to reinstall, rather than writing a page
  that does not work.
- CI uses `actions/checkout@v7` and `actions/setup-python@v7`, which run on
  Node 24; GitHub removed Node 20 from its runners on 23 September 2026. The
  engine is tested on Python 3.9, 3.13 and 3.14, the first with
  `compression.zstd`, which the Codex reader tries first. That job runs on
  `ubuntu-24.04` rather than `ubuntu-latest`, because Python 3.9 is not built
  for Ubuntu 26.04.
- CI also checks that every Python file compiles with warnings as errors,
  that the Homebrew formula and both property lists parse, and that the
  dashboard's script parses.
- `install.sh` warns when `/usr/bin/python3` is older than 3.9. The menu bar
  app runs that Python whatever your PATH says, while the installer checked
  only the `python3` on your PATH, so a Mac with older command line tools
  installed cleanly and then had a menu bar that could not run the engine.
  It is a warning, not a failure, and it says to update the command line
  tools.
- README's Settings table has a row for every variable the engine reads, and
  a test keeps it so: `TOKENMETER_PRICE_CACHE` (where looked-up prices are
  saved) and `OPENCODE_DB` are listed, and `TOKENMETER_CURRENCY` says it sets
  the terminal, the dashboard and the status line, while the menu bar keeps
  the choice made in its Currency menu.
- The README and the `/tokenmeter` command mention `--period yesterday` and
  `--by provider`, which both worked already, and the README's harness table
  names Gemini CLI's folder under the macOS sandbox, `~/.cache/.gemini/tmp`,
  which was already read.
- The README says the menu bar app runs `/usr/bin/python3`, which the Xcode
  command line tools provide, rather than that any Python 3.9 will do; that
  uninstalling removes the login item's plist rather than moving it to the
  Bin; and that variables set in that plist must be added again after an
  uninstall and reinstall, which writes it afresh.
- README's price table is checked against the tables by a test, row by row:
  each provider's models and any retired, the date its page was checked and
  whether it was measured against real bills, with the Anthropic count above
  it. It had drifted once, to 18 and 38 models checked on 26 September while
  the tables held more.
- The README's harness table includes workflow agents, says what Codex's
  compressed sessions need and names every OpenCode database it reads, and its
  usage block shows `--project` and `--session`. MAINTENANCE names every
  folder, the rule the three `money()` copies share and where a version is
  set.

## 1.1.2, 6 October 2026

- Prices: Claude Sonnet 5.5 ($2 in, $10 out, cache hits $0.20, no fast mode)
  and gpt-6.1-sol ($2 in, $10 out, cached input $0.10, which is 5% of input
  rather than the usual 10%; cache writes $2.50; long context and fast mode as
  on the page). Both were read off the providers' pages on 6 October 2026 and
  pinned in the tests. Sonnet 5.5 also matched Claude Code's own cost to ten
  decimal places. Until now both were priced by the online lookup and labelled
  as such.
- `--check-prices` reads every row of the Anthropic and OpenAI tables as
  matching, so both are marked verified on 6 October 2026.

## 1.1.1, 6 October 2026

- Homebrew: the formula now lives in this repository, at
  `Formula/tokenmeter.rb`, and the separate `homebrew-tokenmeter` tap is
  retired. Install with
  `brew tap adi-debug-source/tokenmeter https://github.com/Adi-debug-source/tokenmeter`,
  then `brew install adi-debug-source/tokenmeter/tokenmeter`. Anyone who
  tapped the old repository runs `brew untap adi-debug-source/tokenmeter`
  first.
- `fonts/` now carries the SIL Open Font License texts for Fraunces and Inter
  Tight, as Google Fonts publishes them, which the licence asks for.

## 1.1.0, 26 September 2026

### Several harnesses

When more than one harness or provider is in view, every face shows what
mixing tools needs. One harness on one provider sees exactly what it did.

- Dashboard: a Harness menu beside the currencies shows any one harness on a
  page of its own. Every page is built by the engine in the same pass, drawn
  over the same days, and nothing is recomputed in the browser.
- The spend chart splits each day by harness, with a legend to leave one out.
- By model groups models under the provider whose prices they were charged
  at, each naming the harnesses that used it, and flags any model priced from
  an online lookup or a stand-in rate.
- A By harness table compares calls, cost per call, cache use and the share of
  each harness's cost that is output.
- "How far to trust this" shows, as shares of the total, how much was read by
  verified readers and where each price came from.
- Projects name the harnesses that worked on them.
- Menu bar: By model stays the default. "Break down by" switches it to
  harnesses or to providers with their models, and remembers the choice.
- Terminal: `--by source` compares harnesses with cost per call and cache use.

### Look

- A new app icon: a T whose crossbar is a meter, on a graphite body, in the
  macOS 26 dark icon style. Its reading is the dashboard's clay accent. Every
  size is drawn at its own resolution, on whole pixels below 128px.
- The dashboard's "where the money goes" bar shows Output in gold and
  uncached input in violet. The old green and mustard were too close to tell
  apart even with full colour vision; the new four were checked as a set for
  colour-blind separation, and a thin gap now divides the parts.

### Fixes

Each found by a clean-room run of 1.0.0 on a home with four harnesses, and
each with a test.

- Reports said "X figures are unverified" once per harness. One note now names
  them all, and beside another source it says what share of the total they
  carry.
- The covered line read "2 Codex sessions and 1 Gemini CLI sessions and
  1 OpenCode databases". Adapters now have a singular name for what they read
  (`FILE`), and the list reads as a sentence.
- A first run said "ledger holds 0" having just written every call to it. The
  count is now taken after the run's own writes.
- A model looked up online and found nowhere got two notes saying so. It now
  gets one.
- The menu bar offered four currencies from a list of its own while the
  dashboard offered seven. The engine now sends the list, in order, and the
  menu shows all of it.
- An unused function was removed from the menu bar app.
- The dashboard's "where the money goes" left out web searches, so its parts
  did not add up to the total. They now have a part of their own when there
  are any.
- Dashboard notes that already ended in a full stop printed two.
- The spend chart's axis read $0.0 on every line when a page's figures were
  pennies. Small figures now get the decimals they need.

### Project

- Homebrew: `brew install adi-debug-source/tokenmeter/tokenmeter`, then
  `tokenmeter-setup`, which runs the same installer a clone does. The
  `tokenmeter` command runs the one installed engine, so the terminal, the
  menu bar and the status line cannot drift apart after an upgrade.
- `install.sh` says so when the menu bar app fails to build, rather than
  saying nothing.

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
