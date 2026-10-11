"""Small helpers every adapter shares. Standard library only."""

from __future__ import annotations

import datetime as dt
import re

_FRACTION = re.compile(r"\.(\d+)")

# What Python 3.11 and later also read and 3.9 does not: a basic-format date
# and time, a comma before the fraction of a second, and a short offset.
_BASIC_DATE = re.compile(r"^(\d{4})(\d{2})(\d{2})(?!\d)")
_DATE_TIME = re.compile(
    r"^(\d{4}-\d{2}-\d{2}.)"                                  # date and separator
    r"(\d{2}(?::\d{2}(?::\d{2}(?:[.,]\d+)?)?)?"               # 10, 10:02, 10:02:11,5
    r"|\d{4}(?:\d{2}(?:[.,]\d+)?)?)"                           # 1002, 100211, 100211.5
    r"([+-]\d{2}(?::\d{2}(?::\d{2})?|\d{2}(?:\d{2})?)?)?$")    # +01, +0100, +01:00


def parse_time(ts, local=False) -> dt.datetime | None:
    """An ISO 8601 timestamp as an aware datetime, or None.

    Python 3.9's fromisoformat reads only the extended form with a +HH:MM
    offset and a fraction three or six digits long, while 3.11 and later read
    most of ISO 8601, so the same import line would count under one Python
    and be skipped under the other (the menu bar runs /usr/bin/python3, 3.9).
    A Z and a fraction of any length are rewritten before parsing; a string
    that still does not parse is tried again in the extended form, so the
    basic form (20260920T100211Z), a comma before the fraction and a short
    offset (+0100, +01) read the same on every version. A time with no offset
    is taken as UTC rather than rejected, because comparing a naive time with
    an aware one raises instead of answering; local=True takes it as local
    time instead, which is what a person typing one means.
    """
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip().replace("Z", "+00:00").replace("z", "+00:00")
    s = _FRACTION.sub(_six_digits, s, count=1)
    try:
        when = dt.datetime.fromisoformat(s)
    except ValueError:
        try:
            when = dt.datetime.fromisoformat(_extended(s))
        except ValueError:
            return None
    if when.tzinfo is None:
        when = when.astimezone() if local else when.replace(tzinfo=dt.timezone.utc)
    return when


def _six_digits(m) -> str:
    """A fraction of a second as the six digits Python 3.9 insists on."""
    return "." + (m.group(1) + "000000")[:6]


def _extended(s: str) -> str:
    """A timestamp in the extended form Python 3.9 reads: 20260920T100211,5+0100
    as 2026-09-20T10:02:11.500000+01:00. Anything else comes back as it was."""
    m = _DATE_TIME.match(_BASIC_DATE.sub(r"\1-\2-\3", s))
    if not m:
        return s
    date, time, offset = m.group(1), m.group(2), m.group(3) or ""
    if ":" not in time and len(time) >= 4:      # 1002, 100211 or 100211.5
        time = time[:2] + ":" + time[2:4] + (":" + time[4:] if len(time) > 4 else "")
    time = _FRACTION.sub(_six_digits, time.replace(",", "."))
    if offset and ":" not in offset:            # +01, +0100 or +010030
        seconds = ":" + offset[5:] if offset[5:] else ""
        offset = offset[:3] + ":" + (offset[3:5] or "00") + seconds
    return date + time + offset


def usage(input=0, output=0, cache_read=0, cache_write_5m=0, cache_write_1h=0,
          thinking=0, web_searches=0, speed="standard") -> dict:
    """Normalised token counts as the usage block the engine prices.

    Anthropic's shape is the engine's internal one, because it is the richest:
    it separates uncached input, cache reads and both cache-write lifetimes.
    Every adapter translates into it, and `input` always means uncached input
    only, whatever the provider's own convention.
    """
    return {
        "input_tokens": int(input),
        "output_tokens": int(output),
        "cache_read_input_tokens": int(cache_read),
        "cache_creation": {"ephemeral_5m_input_tokens": int(cache_write_5m),
                           "ephemeral_1h_input_tokens": int(cache_write_1h)},
        "output_tokens_details": {"thinking_tokens": int(thinking)},
        "server_tool_use": {"web_search_requests": int(web_searches)},
        "speed": speed or "standard",
    }
