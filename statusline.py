#!/usr/bin/env python3
"""Tokenmeter's status line for Claude Code, two lines.

Line 1: model | context % | this session at API rates | today at API rates
Line 2: context window bar

On a subscription nothing here is billed. The money is the counterfactual:
what the same tokens would have cost through the raw API. All pricing lives in
tokenmeter.py beside this file, so there is one table, not two.

Receives session JSON on stdin (see Claude Code's statusLine documentation).
Set TOKENMETER_CURRENCY to show another currency (USD by default).
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".today_cost.json")
CACHE_TTL = 90  # seconds; the daily figure need not be to the second

sys.path.insert(0, HERE)
try:
    from tokenmeter import (COMPONENTS, DEFAULT_CURRENCY, money, session_totals,
                            set_currency)
    set_currency(DEFAULT_CURRENCY)
except Exception:  # the status line must never be the thing that breaks
    session_totals = None
    money = None


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


def today_cost():
    """Every project, since local midnight. Cached so this stays cheap."""
    if session_totals is None:
        return None
    try:
        st = os.stat(CACHE)
        if time.time() - st.st_mtime < CACHE_TTL:
            with open(CACHE) as f:
                return json.load(f).get("total")
    except Exception:
        pass

    try:
        import datetime as dt
        from tokenmeter import iter_events, transcripts

        midnight = dt.datetime.now().astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0)
        # transcripts() recurses, so subagent tokens are included here too.
        paths = [p for p in transcripts()
                 if os.path.getmtime(p) >= midnight.timestamp()]
        total = 0.0
        # online=False: a status line must never wait on the network. Prices
        # the menu bar or a report already looked up are still used.
        for ev in iter_events(paths, midnight, ledger=False, online=False):
            total += sum(ev["cost"][k] for k in COMPONENTS)
        try:
            with open(CACHE, "w") as f:
                json.dump({"total": total}, f)
        except Exception:
            pass
        return total
    except Exception:
        return None


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    model = (data.get("model") or {}).get("display_name") or "unknown"
    sess_usd, tokens = session_cost(data.get("transcript_path") or "")
    day_usd = today_cost() if money is not None else None

    limit = 200_000 if "haiku" in model.lower() else 1_000_000
    pct = min(100, int(tokens * 100 / limit)) if limit else 0

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
    if day_usd is not None:
        parts.append(f"{fmt_usd(day_usd)}{DIM} today{RESET}")
    line1 = f" {sep} ".join(parts)
    cap = "200k" if limit == 200_000 else "1M"
    line2 = f"{colour}{bar}{RESET} {DIM}{fmt_tok(tokens)} / {cap} · would-be API spend{RESET}"

    sys.stdout.write(line1 + "\n" + line2)


if __name__ == "__main__":
    main()
