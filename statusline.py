#!/usr/bin/env python3
"""Tokenmeter's status line for Claude Code, two lines.

Line 1: model | context % | this session at API rates | today at API rates
Line 2: context window bar

With TOKENMETER_STATUS_TOKENS=1, today's figure also gives today's total
tokens, "$4.56 · 1.20M today". Off by default, so the line is exactly
what it always was unless asked.

"This session" is the session's transcript and every subagent and workflow
agent it started, because their calls were made for it. The context is the
main conversation's: its token count from the transcript, its window's size
and how full it is from Claude Code's own context_window. A build too old to
send that gets the window guessed from the model's name, as before.

On a subscription nothing here is billed. The money is the counterfactual:
what the same tokens would have cost through the raw API. All pricing lives in
tokenmeter.py beside this file, so there is one table, not two.

Receives session JSON on stdin (see Claude Code's statusLine documentation).
Set TOKENMETER_CURRENCY to show another currency (USD by default); a code it
does not know falls back to dollars rather than blanking the line.

It never makes a network request, because it runs on every prompt. Looked-up
prices and the exchange rate are whatever a report, the dashboard or the menu
bar last saved, at any age; with no saved exchange rate it uses the built-in
estimate.
"""

import datetime as dt
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".today_cost.json")
CACHE_TTL = 90  # seconds; the daily figure need not be to the second
# Today's total tokens beside today's cost, off unless set to anything but
# empty or 0, the rule TOKENMETER_OFFLINE follows.
TOKENS_ENV = "TOKENMETER_STATUS_TOKENS"

sys.path.insert(0, HERE)
try:
    from tokenmeter import (COMPONENTS, DEFAULT_CURRENCY, ONLINE_LOOKUP, money,
                            session_totals, set_currency, toks)
except Exception:  # the status line must never be the thing that breaks
    session_totals = None
    money = None
    toks = None
else:
    # Offline for everything this process does: set_currency() then reads the
    # exchange rate a report, the dashboard or the menu bar last saved instead
    # of fetching one, which could hold up every prompt for its timeout.
    ONLINE_LOOKUP[0] = False
    try:
        set_currency(DEFAULT_CURRENCY)
    except (SystemExit, Exception):
        # An unknown TOKENMETER_CURRENCY makes set_currency() exit, which
        # "except Exception" does not catch: a typo such as GPB printed no
        # status line at all. Dollars beat a blank line.
        set_currency("USD")


def session_cost(transcript_path):
    """Delegates to tokenmeter so there is one parser, one price table and
    one de-duplication rule, not a second copy that drifts."""
    if not (transcript_path and os.path.isfile(transcript_path)):
        return 0.0, 0
    if session_totals is None:
        return 0.0, 0
    try:
        return session_totals(transcript_path)
    except Exception:
        return 0.0, 0


def today_totals(want_tokens=False):
    """Every project, since local midnight: (cost, total tokens), or (None,
    None) when the engine cannot be used. Cached so this stays cheap: for
    CACHE_TTL seconds, and only on the day it was worked out. The tokens are
    the engine's total (token_totals()); a cache written before it kept them
    is worked out again only when they are wanted."""
    if session_totals is None:
        return None, None
    today = dt.date.today()
    try:
        st = os.stat(CACHE)
        if time.time() - st.st_mtime < CACHE_TTL:
            with open(CACHE) as f:
                saved = json.load(f)
            # The cache once held no day, so for a minute and a half after
            # midnight yesterday's total was shown as today's.
            if saved.get("day") == today.isoformat() and (
                    not want_tokens or isinstance(saved.get("tokens"), int)):
                return saved.get("total"), saved.get("tokens")
    except Exception:
        pass

    try:
        from tokenmeter import (add_to_row, empty_row, iter_events, local_midnight,
                                token_totals, transcripts)

        # At the day's own UTC offset. now().replace(hour=0) kept the offset
        # in force now, an hour out on the days the clocks change.
        midnight = local_midnight(today)
        # transcripts() recurses, so subagent tokens are included here too.
        paths = [p for p in transcripts()
                 if os.path.getmtime(p) >= midnight.timestamp()]
        total = 0.0
        counted = empty_row()
        # online=False: a status line must never wait on the network. Prices
        # the menu bar or a report already looked up are still used.
        for ev in iter_events(paths, midnight, ledger=False, online=False):
            total += sum(ev["cost"][k] for k in COMPONENTS)
            # The tokens go through the engine's own row and definition. The
            # money is added up as it always was, so it cannot move by a
            # rounding.
            add_to_row(counted, ev)
        tokens = token_totals(counted["tokens"])["total"]
        try:
            with open(CACHE, "w") as f:
                json.dump({"day": today.isoformat(), "total": total, "tokens": tokens}, f)
        except Exception:
            pass
        return total, tokens
    except Exception:
        return None, None


def context_window(sent, model, tokens):
    """(the window's size in tokens, the percentage of it in use).

    Claude Code sends both in context_window: context_window_size, and
    used_percentage once the session has made a call (null before then).
    Builds that send neither get the old guess from the model's name, Haiku
    200k and anything else 1M, which showed a 200k model other than Haiku at a
    fifth of its real percentage and a 1M Haiku as full at 200k.
    """
    def number(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        try:
            v = float(v)
        except OverflowError:
            return None
        return v if math.isfinite(v) else None

    sent = sent if isinstance(sent, dict) else {}
    size = number(sent.get("context_window_size"))
    if size is not None and int(size) > 0:
        limit = int(size)
    else:
        limit = 200_000 if "haiku" in model.lower() else 1_000_000
    used = number(sent.get("used_percentage"))
    if used is not None:
        return limit, max(0, min(100, int(used)))
    return limit, min(100, int(tokens * 100 / limit))


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    model = (data.get("model") or {}).get("display_name") or "unknown"
    sess_usd, tokens = session_cost(data.get("transcript_path") or "")
    show_tokens = os.environ.get(TOKENS_ENV, "").strip() not in ("", "0")
    day_usd, day_tokens = today_totals(show_tokens) if money is not None else (None, None)

    # The count shown is the transcript's own; the window and percentage are
    # Claude Code's when it sends them.
    limit, pct = context_window(data.get("context_window"), model, tokens)

    RESET, DIM, BOLD = "\x1b[0m", "\x1b[2m", "\x1b[1m"
    BLUE, GREEN, YELLOW, RED = "\x1b[36m", "\x1b[32m", "\x1b[33m", "\x1b[31m"

    colour = GREEN if pct < 50 else YELLOW if pct < 80 else RED

    bar_width = 30
    filled = max(0, min(bar_width, int(round(pct * bar_width / 100))))
    bar = "█" * filled + "░" * (bar_width - filled)

    def fmt_tok(t):
        return f"{t / 1000:.1f}k" if t >= 1000 else str(t)

    def fmt_usd(x):
        # Never print a plausible zero when pricing is unavailable. A broken
        # import once showed "$0.000" for hours and read as an idle session
        # rather than a fault. "cost n/a" cannot be misread.
        if money is None:
            return "cost n/a"
        return money(x)

    sep = f"{DIM}│{RESET}"
    parts = [
        f"{BOLD}{BLUE}{model}{RESET}",
        f"ctx {colour}{pct:3d}%{RESET}",
        (f"{YELLOW}{fmt_usd(sess_usd)}{RESET}{DIM} session{RESET}" if money is not None
         else f"{RED}pricing unavailable{RESET}"),
    ]
    if day_usd is not None and show_tokens and day_tokens is not None:
        parts.append(f"{fmt_usd(day_usd)}{DIM} · {RESET}{toks(day_tokens)}{DIM} today{RESET}")
    elif day_usd is not None:
        parts.append(f"{fmt_usd(day_usd)}{DIM} today{RESET}")
    line1 = f" {sep} ".join(parts)
    cap = {200_000: "200k", 1_000_000: "1M"}.get(limit) or (toks or fmt_tok)(limit)
    line2 = f"{colour}{bar}{RESET} {DIM}{fmt_tok(tokens)} / {cap} · would-be API spend{RESET}"

    sys.stdout.write(line1 + "\n" + line2)


if __name__ == "__main__":
    main()
