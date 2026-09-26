"""Small helpers every adapter shares. Standard library only."""

from __future__ import annotations

import datetime as dt
import re

_FRACTION = re.compile(r"\.(\d+)")


def parse_time(ts) -> dt.datetime | None:
    """An ISO 8601 timestamp as an aware datetime, or None.

    Python 3.9's fromisoformat accepts neither a trailing Z nor a fraction
    that is not three or six digits long, and harnesses write both. A time
    with no offset is taken as UTC rather than rejected, because comparing a
    naive time with an aware one raises instead of answering.
    """
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip().replace("Z", "+00:00").replace("z", "+00:00")
    s = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
    try:
        when = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.timezone.utc)
    return when


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
