# Maintenance

How to keep Tokenmeter correct. Its only claim is that its numbers are right,
so everything here is about protecting that.

## Before anything else

    python3 tests/test_tokenmeter.py

Standard library only, no network, well under a second. Most tests guard a
bug that was once real and name it in their docstring, so a failure tells you
what broke rather than only that something did. Run it after any change. The
suite was checked by mutation: past bugs were put back one at a time and each
was caught by its own test.

## How it fits together

| Part | Does | Owns |
|---|---|---|
| `tokenmeter.py` | the engine | merging, the ledger, pricing arithmetic, reports, the dashboard, the online lookup |
| `adapters/` | one reader per harness | turning a log into calls; nothing else |
| `pricing/` | one table per provider | rates, the evidence for them, reading the provider's page |
| `costbar/` | menu bar app | display only; runs `--summary-json` |
| `statusline.py` | Claude Code status line | display only; calls `session_totals()` |
| `tests/` | the safety net | |

The rule that matters: **arithmetic lives in `tokenmeter.py` and nowhere
else.** Six bugs in this tool's history were a second copy of some logic
drifting from the first: a hardcoded rate, a second transcript parser, a
second de-duplication key, a second currency table. When the menu bar needs a
number it does not compute, add it to `--summary-json`. An adapter never
prices; a price file never adds up.

The one deliberate exception is `money()`, which exists three times, in
Python, Swift and the dashboard's JavaScript, because each renders in its own
runtime. All three carry the same comment. **Change one and you must change
all three**, or the same figure reads differently in different places, which
has happened.

## When a harness updates

The harness owns its log format, so an update can move the ground.

1. Run the tests.
2. Run `tokenmeter.py --by model`. A model you do not recognise, or a note
   that one was looked up or had no price, means a table needs a row.
3. Check the call count is still plausible. A sudden collapse means the log
   shape changed and an adapter is silently skipping records.
4. For Claude Code, check the Stats tab has not changed what it counts. It is
   not this tool's business, but it is what people compare against, and it
   has changed once already.

## Prices

Everything about adding a model, recording a rate change and checking a table
is in [pricing/README.md](pricing/README.md). In short:

- A rate change is a new dated row. Never edit the old one.
- Every rate is pinned by a test typed from the provider's page.
- `tokenmeter.py --check-prices` compares every table with its live page and
  changes nothing.
- Every report warns once a table is more than 90 days past its
  `VERIFIED_ON`. Re-read the page, update the date, and the warning goes.

### Checking Anthropic's table against reality

Claude Code reports its own cost, which is the ground truth:

    claude -p --output-format json 'say hi'

Take `total_cost_usd` from the result and price the same `usage` block through
`price_record()`. They should agree to ten decimal places. Doing this once per
model exercises base input and output, cache reads at each multiplier, and the
1-hour cache write. The table was confirmed this way on 10 September 2026.

**Still unverified:** the 5-minute cache write at 1.25x. The CLI gives no way
to force one, so it remains documentation-only. It carries roughly 3.6% of a
typical total. If a way to force a 5-minute write appears, this is the first
thing to check.

### The online lookup

A model no table has is looked up once at startup (`resolve_prices()`), saved
to `.fetched_prices.json` beside the engine, and rechecked weekly. A model
found nowhere is not asked about again for a day. Delete that file to forget
every lookup. The status line never looks anything up; it only reads what a
report or the menu bar already saved.

## Adapters

Everything about writing one and promoting it from unverified is in
[adapters/README.md](adapters/README.md). Claude Code's figures must not move
by a single token when any adapter changes; there is a test for that.

## The app icon

`costbar/icon.swift` draws it with Core Graphics and writes a full `.iconset`;
`build.sh` runs it and `iconutil` turns that into `AppIcon.icns`. Source, not a
binary blob, so it is changed by editing numbers and rebuilds anywhere the app
does. `AppIcon.icns` is gitignored for the same reason the compiled binary is.

It only re-renders when `icon.swift` is newer than the `.icns`, so ordinary
builds stay quick. Force it with `rm AppIcon.icns && ./build.sh`.

The design is a T whose crossbar is a meter: the solid part is the reading so
far, a clay tick marks where it stands, and the rest of the scale is a groove
still to travel. It follows the macOS 26 dark icon style: a graphite body lit
from above, the glyph lifted off it by a soft shadow, and one accent that
gives off light. The tick's clay is the dashboard's accent (`--acc`,
`--acc2` and the chart bars' foot colour); change one and change the other.

Four things it gets right that are easy to lose:

1. **The outline is a squircle, not a rounded rectangle.** Circular corners
   read as subtly wrong next to native icons. `squircle()` is a superellipse
   at n=5. It matters more since macOS 26: the system re-masks an icon to its
   own shape and adds a glass edge only when the icon already follows this
   outline, and shrinks anything else onto a grey tile.
2. **Every size is drawn at its own resolution**, not downsampled from 1024.
   Below 128px every edge is rounded to a whole pixel, and at 16px the mark
   becomes a plain two-pixel T with no meter, because a one-pixel tick only
   makes the T look broken.
3. **Every gradient covers the whole box it fills.** A radial gradient is
   transparent only at the edge of the rectangle it is given, so drawing one
   into a smaller rect leaves a hard seam across the icon. The glyph's
   gradient spans the whole T, so crossbar and stem read as one piece.
4. **The crossbar is thinner than the stem** (88 and 104 units), as in a
   typeface. Equal strokes make the horizontal look the heavier of the two.

Check a change at 16 and 32 magnified, not just at 512, and look at it the
way the system presents it (`NSWorkspace.shared.icon(forFile:)` on the built
app), since macOS 26 and later redraw the edge. If Finder still shows the old
icon after a rebuild, that is its cache: `touch` the bundle.

## Rebuilding the menu bar app

`costbar/build.sh` stops the app, swaps the bundle in whole, signs it ad hoc,
and reloads it with a full launchd `bootout` and `bootstrap`. Do not
"simplify" that to `kickstart`: launchd caches the signature it registered,
an ad hoc signature changes on every build, and the kernel kills the new
binary with `OS_REASON_CODESIGNING`.

## The dashboard's fonts

`fonts/` holds latin-subset variable woff2 files that are base64'd into every
rendered dashboard, about 216 KB, so the page looks the same with no network.
Delete them and it falls back to the system serif and sans rather than
breaking; a test covers that.

To refresh or change them, take the URL out of the `/* latin */` block, not
`latin-ext`:

    curl -sA "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) \
      AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" \
      "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT,WONK@9..144,300..700,0..100,0..1"

The axes matter: the headline animates `opsz` and `SOFT` on hover, so a build
requesting only `wght` will load but sit still. Both families are SIL Open
Font License, which permits embedding; keep `fonts/README.md` with them so the
attribution travels.

## Two things the chart gets wrong if you touch it

1. **The SVG viewBox must match the pixel box the JavaScript draws in.** It
   was once a fixed `0 0 900 268` while the drawing used `clientWidth`, so the
   crosshair landed to the right of the bar it was describing. `drawChart()`
   sets the viewBox from the measured width every time.
2. **The tooltip sits beside the bar, never over it.** Covering the thing you
   are describing hides the answer.

## When a number looks wrong

In order, because each step rules out the one below:

1. `--no-ledger`. If the figure changes, the ledger and the logs disagree, and
   the ledger is holding calls the logs have lost. That is usually correct
   behaviour, not a fault.
2. `--by model`. An unknown model priced at a stand-in rate is the most likely
   single cause of a total that is too high.
3. `--by source`. An unverified adapter is the next suspect.
4. `--by day`. A day that is wildly out points at one session; find it with
   `--sessions` and price it alone with `--session <id>`.

## The ledger

`~/.claude/cost-ledger.jsonl`, one JSON object per line, append only.

- **Never rewrite it in place.** Supersede a row by appending a new one;
  readers take the largest usage per call id.
- **It stores tokens, never money**, so the whole history reprices when a
  table changes. That is the reason the tool can answer both pricing
  questions at all.
- Rows carry `pv` (provider) and `a` (source) only when they are not Anthropic
  and Claude Code, so rows written before other providers existed are still
  read correctly, and Claude Code rows keep their original shape.
- `--rebuild-ledger` is the only destructive operation. It can only rebuild
  from logs that still exist, so anything already swept is lost. It prints
  the count and keeps the old file as `.old`. Not routine maintenance.

## Releasing a change

1. Tests pass.
2. `--currency USD`, `--by model`, `--by source`, `--sessions`, `--since 30d`,
   `--period lastmonth`, `--json`, `--summary-json`, `--html`,
   `--list-adapters` and `--check-prices` all run.
3. The status line renders: pipe a session JSON into `statusline.py`.
4. `./install.sh`, then confirm the menu bar is alive:
   `pgrep -f Tokenmeter.app/Contents/MacOS/Tokenmeter`.
5. The headline figure has not moved unless you meant it to.
6. Update `CHANGELOG.md`, commit with what changed and why.

## What a Linux port would need

Not attempted. The split is better than it looks: the engine is portable and
only the macOS furniture is not.

| Part | State on Linux | Work |
|---|---|---|
| `tokenmeter.py`, `adapters/`, `pricing/` | **one line** | `subprocess.run(["open", out])` for `--html` needs `xdg-open`. Everything else is standard library. |
| `statusline.py` | **works as is** | |
| `costbar/` (Swift) | **does not apply** | AppKit, `NSStatusBar`, launchd and `codesign`. A tray equivalent is a rewrite, not a port. |
| `install.sh`, `build.sh`, `install-login-item.sh` | **does not apply** | systemd user units are the equivalent. |

The menu bar is only a face over `--summary-json`, so a Linux tray applet, a
waybar or polybar module, or a GNOME extension would consume the same JSON and
none of the arithmetic moves.

## Known limits

- **macOS only**, for now; see above.
- **Python 3.9 and up.** `from __future__ import annotations` keeps the
  `X | None` annotations working on 3.9, which is what macOS ships. Do not
  remove it.
- **Only what is on this Mac.** Usage on a phone or in a browser leaves no
  local log and goes uncounted without saying so.
- **The 5-minute cache write multiplier is assumed**, see above.
