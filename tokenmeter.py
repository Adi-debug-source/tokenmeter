#!/usr/bin/env python3
"""Tokenmeter: what your AI coding would have cost at API rates.

On a subscription, none of this is billed per token. This works out the
counterfactual: the same work, driven through the provider's raw API at its
published rates.

Everything comes from the logs your coding harness already writes on this Mac,
read by one adapter per harness. Nothing leaves the machine except a request
for exchange rates.

Usage:
    tokenmeter.py                      totals for everything found, all time
    tokenmeter.py --since 7d           last 7 days (also 24h, 30d, 2026-09-01)
    tokenmeter.py --session <id|path>  one session
    tokenmeter.py --by project         group by project, model, day, source...
    tokenmeter.py --sessions           list sessions, dearest first
    tokenmeter.py --html [path]        write the dashboard and open it
    tokenmeter.py --import FILE        price events from any harness
    tokenmeter.py --list-adapters      what was found, and how far to trust it
    tokenmeter.py --check-prices       compare the tables with the live pages
    tokenmeter.py --json               machine readable
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict

from adapters import ADAPTERS, ALL as ALL_SOURCES
from adapters import claude_code, codex, importer
from adapters.common import parse_time
from pricing import TABLES
from pricing import anthropic as _anthropic

__version__ = "1.0.0"

PROJECTS_DIR = claude_code.default_roots()[0]

# Extra folders to read, so two machines can be counted as one history.
# Colon separated, the same shape as PATH.
PROJECTS_ENV = "TOKENMETER_CLAUDE_PROJECTS"
_ROOTS: list = []


def projects_dirs() -> list:
    """Every folder Claude Code transcripts are read from.

    One Mac needs no configuration. Two do, and so does an archived copy of an
    old one. Transcripts carry no account id, so everything written under one
    folder is already counted as one history whichever account was signed in;
    combining machines means naming both folders, with --projects-dir or by
    setting TOKENMETER_CLAUDE_PROJECTS. The environment variable is the route
    for the menu bar and the status line, which pass no flags of their own.

    De-duplication is by message id across every root at once, so an
    overlapping copy of the same history still counts once.
    """
    if _ROOTS:
        return list(_ROOTS)
    raw = os.environ.get(PROJECTS_ENV, "")
    if raw.strip():
        return [os.path.expanduser(p) for p in raw.split(os.pathsep) if p.strip()]
    return [PROJECTS_DIR]


# Folders to read per adapter, when something other than its default is
# wanted. Claude Code keeps _ROOTS above, which predates adapters.
ADAPTER_ROOTS: dict = {}
# --adapter: read only these. Empty means every adapter whose folders exist.
_ONLY: list = []
# --import: files in the documented import format, read as one more source.
_IMPORTS: list = []
# Which adapter produced each file this run, so a path always goes back to the
# reader that found it.
_OWNER: dict = {}
# --project and --session. Files are filtered on the way in where the path
# says enough, and every call is filtered again on the way out, because calls
# restored from the ledger have no file. Before this second filter, a single
# session's report with the ledger on showed the whole history.
_PROJECT: list = []
_SESSION: list = []


def adapter_roots(name: str) -> list:
    if name == claude_code.NAME:
        return projects_dirs()
    if name in ADAPTER_ROOTS:
        return list(ADAPTER_ROOTS[name])
    return ALL_SOURCES[name].default_roots()


def active_adapters() -> list:
    """The adapters this run reads: the ones asked for, or every one found."""
    if _ONLY:
        return [n for n in _ONLY if n in ADAPTERS]
    return [n for n in ADAPTERS if any(os.path.isdir(r) for r in adapter_roots(n))]


def adapter_for(path: str):
    """The adapter that reads this file.

    Files found by scanning are remembered as they are found. A path handed
    over directly, as --session accepts, is recognised from its first line
    that parses, and falls back to Claude Code, the one format that is
    verified.
    """
    name = _OWNER.get(path)
    if name:
        return ALL_SOURCES[name]
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for _, line in zip(range(50), fh):
                for a in ADAPTERS.values():
                    if a.looks_like(line):
                        return a
    except OSError:
        pass
    return claude_code


# Everything is computed in dollars, because that is what both providers bill
# in. Display happens in whatever currency is selected; only the last step
# converts. TOKENMETER_CURRENCY changes the default everywhere at once: the
# command line, the status line and the dashboard.
CURRENCY_ENV = "TOKENMETER_CURRENCY"
DEFAULT_CURRENCY = (os.environ.get(CURRENCY_ENV, "").strip() or "USD").upper()

CURRENCIES = {
    "GBP": ("£", "pounds"),
    "USD": ("$", "dollars"),
    "EUR": ("€", "euro"),
    "INR": ("₹", "rupees"),
    "CAD": ("C$", "Canadian dollars"),
    "AUD": ("A$", "Australian dollars"),
    "JPY": ("¥", "yen"),
}

# Used only when the rate lookup cannot reach the network. Roughly right beats
# refusing to print a number, but the report says when it is falling back.
FALLBACK_RATES = {"USD": 1.0, "GBP": 0.74, "EUR": 0.86, "INR": 95.0,
                  "CAD": 1.38, "AUD": 1.38, "JPY": 153.0}

FX_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fx_rates.json")
# Half a day, so a rate checked in the morning is never yesterday afternoon's.
# The menu bar calls this every 60 seconds, so expiry heals itself with no
# scheduler, no cron and no agent run.
FX_TTL = 43200


def fx_rates() -> tuple:
    """Dollars to everything else. Returns (rates, when, live).

    The only thing that leaves the Mac is the string "USD". No usage data,
    no totals, nothing identifying.
    """
    cached = None
    try:
        with open(FX_CACHE) as f:
            cached = json.load(f)
        if time.time() - os.path.getmtime(FX_CACHE) < FX_TTL:
            return cached["rates"], cached.get("when", "cached"), True
    except Exception:
        cached = None

    try:
        import urllib.request
        with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=8) as r:
            payload = json.load(r)
        if payload.get("result") == "success":
            rates = {k: v for k, v in payload["rates"].items() if k in CURRENCIES}
            rates["USD"] = 1.0
            when = payload.get("time_last_update_utc", "")[:16]
            try:
                with open(FX_CACHE, "w") as f:
                    json.dump({"rates": rates, "when": when, "live": True}, f)
            except OSError:
                pass
            return rates, when, True
    except Exception:
        pass

    # The fetch failed. A real rate from yesterday beats a constant from
    # whenever this file was last edited, so prefer the stale cache.
    if cached and cached.get("rates"):
        return cached["rates"], f"stale, {cached.get('when', 'unknown')}", False

    return FALLBACK_RATES, "offline estimate, no cached rate", False


DISPLAY = {"code": "USD", "symbol": "$", "rate": 1.0, "when": "", "live": True}


def set_currency(code: str) -> None:
    code = (code or DEFAULT_CURRENCY).upper()
    if code not in CURRENCIES:
        sys.exit(f"unknown currency {code!r}; try one of {', '.join(CURRENCIES)}")
    if code == "USD":
        # Nothing to convert, so nothing to fetch. The dashboard and the menu
        # bar still ask for the rates themselves, for their currency switchers.
        DISPLAY.update(code="USD", symbol="$", rate=1.0, when="", live=True)
        return
    rates, when, live = fx_rates()
    DISPLAY.update(code=code, symbol=CURRENCIES[code][0],
                   rate=rates.get(code, FALLBACK_RATES.get(code, 1.0)),
                   when=when, live=live)

# ---------------------------------------------------------------- pricing
#
# The tables live in pricing/, one file per provider, each carrying the
# evidence for its figures and the date they were last checked. The arithmetic
# lives here and nowhere else.
#
# Every call is priced at the rate in force on the day it was made, not at
# today's. When a rate changes, a dated entry is added to that model's list and
# the old one is left alone, so history stays what it actually was.

# Anthropic's table under its historical names, which the tests and the
# maintenance notes use.
PRICES = _anthropic.PRICES
FALLBACK = PRICES[_anthropic.FALLBACK_MODEL][0]
CACHE_WRITE_5M_MULT = _anthropic.CACHE_WRITE_5M_MULT
CACHE_WRITE_1H_MULT = _anthropic.CACHE_WRITE_1H_MULT
WEB_SEARCH_PER_1K = _anthropic.WEB_SEARCH_PER_1K

DEFAULT_PROVIDER = _anthropic.PROVIDER

# A price table older than this is flagged in every report, so a stale fork
# cannot quietly report wrong figures for a year.
STALE_DAYS = 90

# Price the whole history at the newest rates instead of the ones in force at
# the time. Off by default: "what it would have cost" means what it would have
# cost then. On, it answers the other question, "what would running all of this
# again cost me now".
CURRENT_RATES = []


def rate_on(rows: list, when=None) -> dict:
    """The entry in force on `when`, or the newest if there is no date.

    Rows are ordered oldest first. No date means the caller has no timestamp to
    work from, as the status line does not, in which case the newest rate is
    both the best guess and almost always right, since the call being priced is
    one happening now.
    """
    if when is None or CURRENT_RATES:
        return rows[-1]
    try:
        day = when.astimezone().strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return rows[-1]
    chosen = rows[0]
    for r in rows:
        if r["from"] and r["from"] > day:
            break
        chosen = r
    return chosen


def lookup(model: str, when=None, provider: str = DEFAULT_PROVIDER):
    """Price row for a model id on a given day, tolerating snapshot suffixes.

    Harnesses use dated ids for some models (claude-haiku-4-5-20251001,
    gpt-5-2025-08-07). An exact-match-only table silently prices those at the
    fallback, which was 5x the true rate for Haiku, so a trailing snapshot date
    in the provider's own format is stripped and retried.

    Returns (row, recognised). An unrecognised id is priced at the provider's
    fallback and flagged, and the report says so out loud rather than hiding
    it. A provider with no table at all returns (None, False).
    """
    provider = provider or DEFAULT_PROVIDER
    table = TABLES.get(provider)
    if table is not None:
        name = table_name(table, model)
        if name:
            return rate_on(table.PRICES[name], when), True

    # Not in a checked table. A rate looked up online at startup comes next;
    # its row carries "_via", so every report can say where it came from.
    got = fetched_row(provider, model, when)
    if got is not None:
        return got, True
    if table is None:
        return None, False

    # Deliberately no loose prefix match here. It used to take "the longest
    # known id this one starts with", which reads as a safety net and is the
    # opposite: "claude-opus-5-5" starts with "claude-opus-5", so a genuinely
    # new and cheaper model was silently billed at the older one's rates and
    # reported as recognised, so no warning ever fired. Opus 5.5 is 20% under
    # Opus 5 on input and output and half of it on cache reads.
    #
    # A trailing date is the only suffix that means "the same model", and that
    # is handled above. Anything else is a model we do not know, and saying so
    # loudly beats guessing quietly.
    return rate_on(table.PRICES[table.FALLBACK_MODEL], when), False


def table_name(table, model: str) -> str:
    """The id a model is listed under in a table, or "" if it is not listed.

    Exact first. Then a published alias (xAI lists a dozen for one model).
    Then with a trailing snapshot date stripped, in that provider's format,
    because a dated snapshot is the same model at the same price.
    """
    prices = table.PRICES
    if model in prices:
        return model
    alias = getattr(table, "ALIASES", {}).get(model)
    if alias in prices:
        return alias
    base = re.sub(table.SNAPSHOT, "", model)
    if base in prices:
        return base
    return ""


def verification(provider: str) -> dict:
    """When a provider's table was last checked, and whether that is too long ago."""
    table = TABLES.get(provider)
    if table is None:
        return {"provider": provider, "name": provider, "verified_on": "",
                "measured": False, "stale": True, "age_days": None, "source": ""}
    day = dt.date.fromisoformat(table.VERIFIED_ON)
    age = (dt.date.today() - day).days
    return {"provider": provider, "name": table.NAME, "verified_on": table.VERIFIED_ON,
            "pretty": day.strftime("%d %b %Y").lstrip("0"),
            "measured": table.MEASURED, "stale": age > STALE_DAYS,
            "age_days": age, "source": table.SOURCE}


# ---------------------------------------------------------------- online lookup
#
# The checked tables in pricing/ come first, always. For a model none of them
# has, a run looks the price up online once, before pricing anything: the
# provider's own pricing page where pricing/ knows how to read it, otherwise
# LiteLLM's public price list, which covers thousands of models across every
# major provider. What it finds is saved on this machine with its source and
# the date, so the next run reads the file instead of the network, and it is
# rechecked weekly. A changed figure is added as a new dated entry, so a
# fetched rate keeps its history exactly as a checked one does.
#
# Fetched rates are labelled in every report as fetched, not checked by hand.
# They never replace a table entry. Only price lists are downloaded; no usage,
# no totals and nothing identifying leaves the machine. Set TOKENMETER_OFFLINE=1
# or pass --offline to switch this off, and the old behaviour returns: an
# unknown model is priced at a stand-in rate and flagged.

LITELLM_URL = ("https://raw.githubusercontent.com/BerriAI/litellm/main/"
               "model_prices_and_context_window.json")
LITELLM_NAME = "LiteLLM's public price list"
PRICE_CACHE = os.environ.get("TOKENMETER_PRICE_CACHE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".fetched_prices.json")
OFFLINE_ENV = "TOKENMETER_OFFLINE"
ONLINE_LOOKUP = [os.environ.get(OFFLINE_ENV, "").strip() in ("", "0")]
RECHECK_DAYS = 7          # how long a fetched rate is trusted before a recheck
MISS_RETRY_HOURS = 24     # how long "found nowhere" is remembered

# How each provider's models are keyed in LiteLLM's list, and which of its
# provider labels count as the same first-party API.
LITELLM_KEYS = {
    "anthropic": ([""], {"anthropic"}),
    "openai": ([""], {"openai"}),
    "google": (["gemini/", ""], {"gemini", "vertex_ai-language-models"}),
    "xai": (["xai/"], {"xai"}),
    "deepseek": (["deepseek/"], {"deepseek"}),
    "mistral": (["mistral/"], {"mistral"}),
    "moonshot": (["moonshot/"], {"moonshot"}),
    "zai": (["zai/"], {"zai"}),
    "qwen": (["dashscope/"], {"dashscope"}),
}

_PRICE_STATE = {"loaded": False, "data": {"fetched": {}, "misses": {}}}
# What this run looked up, for the report to say.
LOOKUPS: list = []


def _price_cache() -> dict:
    if not _PRICE_STATE["loaded"]:
        try:
            with open(PRICE_CACHE, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("fetched", {})
            data.setdefault("misses", {})
            _PRICE_STATE["data"] = data
        except (OSError, ValueError):
            pass
        _PRICE_STATE["loaded"] = True
    return _PRICE_STATE["data"]


def _save_price_cache() -> None:
    try:
        tmp = PRICE_CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_PRICE_STATE["data"], f, indent=1, sort_keys=True)
        os.replace(tmp, PRICE_CACHE)
    except OSError:
        pass


def fetched_row(provider: str, model: str, when=None):
    """A saved online rate for this model, or None. Never touches the network,
    so the status line can call it on every keystroke."""
    entry = _price_cache()["fetched"].get(f"{provider}:{model}")
    if not entry:
        return None
    rows = [dict(r, fast=tuple(r["fast"]) if r.get("fast") else None) for r in entry["rows"]]
    row = dict(rate_on(rows, when))
    row["_via"] = entry["via"]
    row["_checked"] = entry["checked"]
    return row


def _row_from_page(r: dict, table) -> dict:
    """A provider page's figures (per million) as a price row."""
    inp = r["in"]
    row = {"from": "", "in": inp, "out": r["out"],
           "cache_read_mult": (r["cached"] / inp) if inp and r.get("cached") is not None else 1.0,
           "fast": (r["fast_in"], r["fast_out"]) if r.get("fast_in") and r.get("fast_out") else None}
    write = r.get("write", r.get("write_5m"))
    if inp and write is not None and table is not None:
        mult = write / inp
        if abs(mult - table.CACHE_WRITE_5M_MULT) > 1e-9:
            row["write_mult"] = mult
    if inp and r.get("long_in") and r.get("long_out") and r["out"]:
        row["long"] = {"over": 272_000, "in": r["long_in"] / inp, "out": r["long_out"] / r["out"]}
    return row


def _row_from_litellm(e: dict) -> dict | None:
    """One LiteLLM entry (dollars per token) as a price row (per million)."""
    inp, out = e.get("input_cost_per_token"), e.get("output_cost_per_token")
    if not isinstance(inp, (int, float)) or not isinstance(out, (int, float)) or inp <= 0:
        return None
    row = {"from": "", "in": round(inp * 1e6, 6), "out": round(out * 1e6, 6),
           "cache_read_mult": 1.0, "fast": None}
    read = e.get("cache_read_input_token_cost")
    if isinstance(read, (int, float)):
        row["cache_read_mult"] = round(read / inp, 6)
    write = e.get("cache_creation_input_token_cost")
    if isinstance(write, (int, float)) and write > 0:
        row["write_mult"] = round(write / inp, 6)
    write_1h = e.get("cache_creation_input_token_cost_above_1hr")
    if isinstance(write_1h, (int, float)) and write_1h > 0:
        row["write_1h_mult"] = round(write_1h / inp, 6)
    for k, v in e.items():
        m = re.fullmatch(r"input_cost_per_token_above_(\d+)k_tokens", k)
        o = e.get(f"output_cost_per_token_above_{m.group(1)}k_tokens") if m else None
        if m and isinstance(v, (int, float)) and isinstance(o, (int, float)) and out:
            row["long"] = {"over": int(m.group(1)) * 1000, "in": round(v / inp, 6),
                           "out": round(o / out, 6)}
            break
    return row


def _from_provider_page(provider: str, model: str, fetch):
    """The provider's own published rate, when pricing/ can read its page."""
    table = TABLES.get(provider)
    if table is None or not hasattr(table, "page_rates"):
        return None
    page, _ = table.page_rates(fetch, md_tables, want=(model,))
    base = re.sub(table.SNAPSHOT, "", model)
    r = page.get(model) or page.get(base)
    if not r or r.get("in") is None or r.get("out") is None:
        return None
    return _row_from_page(r, table), f"{table.NAME}'s pricing page", table.SOURCE


def _from_litellm(provider: str, model: str, fetch, cache: dict):
    if "litellm" not in cache:
        cache["litellm"] = json.loads(fetch(LITELLM_URL))
    data = cache["litellm"]
    prefixes, labels = LITELLM_KEYS.get(provider, ([f"{provider}/"], {provider}))
    base = model
    table = TABLES.get(provider)
    if table is not None:
        base = re.sub(table.SNAPSHOT, "", model)
    for name in dict.fromkeys((model, base)):
        for prefix in prefixes:
            e = data.get(prefix + name)
            if isinstance(e, dict) and e.get("litellm_provider") in labels:
                row = _row_from_litellm(e)
                if row:
                    return row, LITELLM_NAME, LITELLM_URL
    return None


def resolve_prices(pairs, fetch=None) -> list:
    """The startup check: make sure every (provider, model) seen has a price.

    Anything in a checked table is skipped at once. Anything else is taken
    from the saved lookups if they are fresh, or looked up online and saved.
    Returns what was looked up this run, for the report to say.
    """
    if not ONLINE_LOOKUP[0]:
        return []
    fetch = fetch or (lambda url: fetch_text(url, timeout=8))
    cache = _price_cache()
    today = dt.date.today()
    now = time.time()
    session, done, changed = {}, [], False
    for provider, model in sorted(set(pairs)):
        table = TABLES.get(provider)
        if table is not None and table_name(table, model):
            continue
        key = f"{provider}:{model}"
        entry = cache["fetched"].get(key)
        if entry and (today - dt.date.fromisoformat(entry["checked"])).days < RECHECK_DAYS:
            continue
        if not entry and now - cache["misses"].get(key, 0) < MISS_RETRY_HOURS * 3600:
            continue
        found = None
        for source in (_from_provider_page, _from_litellm):
            try:
                found = (source(provider, model, fetch) if source is _from_provider_page
                         else source(provider, model, fetch, session))
            except Exception:
                found = None
            if found:
                break
        if not found:
            cache["misses"][key] = now
            done.append({"provider": provider, "model": model, "found": False})
            changed = True
            continue
        row, via, url = found
        stamp = today.isoformat()
        if entry:
            last = entry["rows"][-1]
            same = all(abs(float(last.get(k) or 0) - float(row.get(k) or 0)) < 1e-9
                       for k in ("in", "out", "cache_read_mult"))
            if not same:
                row["from"] = stamp
                entry["rows"].append(row)
            entry.update(checked=stamp, via=via, url=url)
        else:
            cache["fetched"][key] = {"rows": [row], "via": via, "url": url,
                                     "checked": stamp, "first": stamp}
        cache["misses"].pop(key, None)
        done.append({"provider": provider, "model": model, "found": True, "via": via,
                     "in": row["in"], "out": row["out"]})
        changed = True
    if changed:
        _save_price_cache()
    LOOKUPS[:] = done
    return done


M = 1_000_000.0

COMPONENTS = ("input", "cache_write", "cache_read", "output", "web_search")


def transcripts(project: str = "", session: str = "") -> list:
    """Every log file this run reads, from every active adapter, plus any
    import files. Each adapter alone knows its own on-disk layout."""
    paths = []
    for name in active_adapters():
        for p in ADAPTERS[name].files(adapter_roots(name), project, session):
            _OWNER[p] = name
            paths.append(p)
    if not _ONLY or importer.NAME in _ONLY:
        for p in _IMPORTS:
            _OWNER[p] = importer.NAME
            paths.append(p)
    return paths


def session_totals(path: str) -> tuple:
    """Cost so far and live context size for one transcript. Used by the
    status line, which must stay fast, so it reads a single file. Shares this
    module's pricing and de-duplication rather than keeping its own copy."""
    ctx, best = 0, {}
    for key, ev in adapter_for(path).records(path):
        usage = ev["_usage"]
        # Synthetic records are already gone: no API call, and an empty
        # usage block. Read before that check it reported the context as zero.
        ctx = (int(usage.get("input_tokens") or 0)
               + int(usage.get("cache_creation_input_tokens") or 0)
               + int(usage.get("cache_read_input_tokens") or 0))
        merge(best, key, ev)
    total = 0.0
    for ev in best.values():
        # Dated, like everywhere else: a session resumed from weeks ago is
        # priced at what its calls cost then, not at today's rates.
        usage = ev["_usage"]
        c = price_record(ev["model"], usage, usage.get("speed") or "standard",
                         ev["when"], ev["provider"])
        total += sum(c[k] for k in COMPONENTS)
    return total, ctx


def usage_size(usage: dict) -> int:
    """Every token in one usage block, for telling a complete record from a
    partial one. Never used for pricing, where the components differ in rate."""
    cc = usage.get("cache_creation") or {}
    written = int(usage.get("cache_creation_input_tokens") or 0)
    if not written:
        written = (int(cc.get("ephemeral_5m_input_tokens") or 0)
                   + int(cc.get("ephemeral_1h_input_tokens") or 0))
    return (int(usage.get("input_tokens") or 0)
            + int(usage.get("output_tokens") or 0)
            + int(usage.get("cache_read_input_tokens") or 0)
            + written)


def merge(best: dict, key, ev: dict) -> None:
    """Fold one sighting of an API call into the running set.

    The first sighting keeps the attribution: timestamp, session and project
    stay those of the run that made the call. The largest usage block wins,
    because a streamed reply is written once per content block and every copy
    but the last carries an output count that is still climbing.
    """
    size = usage_size(ev["_usage"])
    prev = best.get(key)
    if prev is not None:
        if size > prev["_size"]:
            prev["_size"], prev["_usage"] = size, ev["_usage"]
        return
    ev["_size"] = size
    best[key] = ev


def in_peak(when, off: dict) -> bool:
    """Whether a call fell inside a provider's published peak hours (UTC)."""
    try:
        u = when.astimezone(dt.timezone.utc)
    except (ValueError, OSError):
        return True
    return (u.weekday() in off["peak_weekdays"]
            and any(a <= u.hour < b for a, b in off["peak_utc_hours"]))


class _NO_TABLE:
    """Defaults for a rate fetched for a provider that has no checked table:
    cache writes at the input rate unless the row says otherwise, and web
    searches unpriced, because no published figure was read for them."""
    CACHE_WRITE_5M_MULT = 1.0
    CACHE_WRITE_1H_MULT = 1.0
    WEB_SEARCH_PER_1K = 0.0


def price_record(model: str, usage: dict, speed: str = "standard", when=None,
                 provider: str = DEFAULT_PROVIDER) -> dict:
    """Cost in USD for one API response, split by component.

    `when` selects the rate: a call is priced at what it cost on the day it was
    made. Pass None only where there is no timestamp to hand. `provider` picks
    the table; the default keeps every older caller on Anthropic's.
    """
    table = TABLES.get(provider or DEFAULT_PROVIDER) or _NO_TABLE
    p, recognised = lookup(model, when, provider)

    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    read = int(usage.get("cache_read_input_tokens") or 0)

    # Prefer the TTL breakdown; a 1 hour write costs 2x, a 5 minute write 1.25x.
    cc = usage.get("cache_creation") or {}
    w5 = int(cc.get("ephemeral_5m_input_tokens") or 0)
    w1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
    if not (w5 or w1):
        w5 = int(usage.get("cache_creation_input_tokens") or 0)

    searches = int((usage.get("server_tool_use") or {}).get("web_search_requests") or 0)
    tokens = {
        "input": inp,
        "cache_write": w5 + w1,
        "cache_read": read,
        "output": out,
        "thinking": int((usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0),
        "searches": searches,
    }

    if p is None:
        # No table for this provider at all. Counted, never guessed at: every
        # component is zero and the report names the provider.
        zero = {c: 0.0 for c in COMPONENTS}
        return {**zero, "_no_cache": 0.0, "_tokens": tokens, "_unknown_model": True,
                "_no_table": True}

    rate_in, rate_out = p["in"], p["out"]
    if speed == "fast" and p["fast"]:
        rate_in, rate_out = p["fast"]
    off = p.get("off_peak")
    if off and when is not None and not in_peak(when, off):
        # Time-of-day pricing (DeepSeek): outside the published peak hours
        # every rate is discounted, cache included.
        rate_in, rate_out = rate_in * off["mult"], rate_out * off["mult"]
    long = p.get("long")
    if long and inp + w5 + w1 + read > long["over"]:
        # Long-context rates apply to the whole request, cache included.
        rate_in, rate_out = rate_in * long["in"], rate_out * long["out"]
    m5 = p.get("write_mult", table.CACHE_WRITE_5M_MULT)
    m1 = p.get("write_1h_mult", p.get("write_mult", table.CACHE_WRITE_1H_MULT))

    return {
        "input": inp * rate_in / M,
        "cache_write": (w5 * m5 + w1 * m1) * rate_in / M,
        "cache_read": read * p["cache_read_mult"] * rate_in / M,
        "output": out * rate_out / M,
        "web_search": searches * table.WEB_SEARCH_PER_1K / 1000.0,
        # What this same call would have cost with no caching at all: every
        # prompt token billed as fresh input, at this model's own rate. Web
        # searches are billed per request and caching does nothing to them, so
        # the counterfactual pays for them too. Leaving them out understated
        # "saved" by exactly the search bill.
        "_no_cache": ((inp + w5 + w1 + read) * rate_in / M + out * rate_out / M
                      + searches * table.WEB_SEARCH_PER_1K / 1000.0),
        "_tokens": tokens,
        "_unknown_model": not recognised,
        "_fetched": p.get("_via", ""),
    }


# ---------------------------------------------------------------- the ledger
#
# Transcripts are not permanent. Claude Code deletes them after
# cleanupPeriodDays, 30 by default, so a tool that reads only transcripts has
# an "all time" that quietly shrinks. The ledger is this tool's own record of
# every call it has ever priced, so a swept transcript costs nothing.
#
# It stores tokens, never money. Rates change, and a ledger of dollars would be
# frozen at the price on the day it was written; a ledger of tokens reprices
# the whole history the moment the table above changes.
#
# Append only, one JSON object per line, sorted by time. It is versioned in
# git, so rewriting the file would put the whole thing in every diff. A row
# that supersedes an earlier one is appended, not edited, and readers take the
# largest usage for any message id, which is the same rule the transcript
# scanner uses for the partial copies of a streaming reply.

# What the last reconcile did, for the report to declare. Same pattern as
# DISPLAY: one module-level fact set once per run, rather than threaded
# through six call sites that do not otherwise care.
LEDGER_STATE = {"written": 0, "restored": 0, "rows": 0, "used": False}

LEDGER_ENV = "TOKENMETER_LEDGER"
DEFAULT_LEDGER = os.path.expanduser("~/.claude/cost-ledger.jsonl")
_LEDGER: list = []

# Short keys because every call is a row. Zero fields are left out entirely,
# and so are the two defaults, which keeps every Claude Code row exactly the
# shape it had before other providers existed.
#   i  message id      t  timestamp        m  model
#   p  project         c  session          f  1 when speed was "fast"
#   in input           o  output           r  cache read
#   w5 5-minute write  w1 1-hour write     th thinking   s  web searches
#   pv provider, when not "anthropic"      a  source, when not "claude-code"
_TOKEN_KEYS = ("in", "o", "r", "w5", "w1", "th", "s")


def ledger_path() -> str:
    """Where the ledger lives: --ledger, then the environment, then the default."""
    if _LEDGER:
        return _LEDGER[0]
    return os.path.expanduser(os.environ.get(LEDGER_ENV, "") or DEFAULT_LEDGER)


def usage_to_row(mid, when, model, project, session, usage,
                 provider=DEFAULT_PROVIDER, source=claude_code.NAME) -> dict:
    """One call, as it is written to the ledger."""
    cc = usage.get("cache_creation") or {}
    w5 = int(cc.get("ephemeral_5m_input_tokens") or 0)
    w1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
    if not cc:
        w5 = int(usage.get("cache_creation_input_tokens") or 0)
    row = {
        "i": mid,
        "t": when.isoformat().replace("+00:00", "Z") if when else "",
        "m": model,
        "p": project,
        "c": session,
        "in": int(usage.get("input_tokens") or 0),
        "o": int(usage.get("output_tokens") or 0),
        "r": int(usage.get("cache_read_input_tokens") or 0),
        "w5": w5,
        "w1": w1,
        "th": int((usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0),
        "s": int((usage.get("server_tool_use") or {}).get("web_search_requests") or 0),
    }
    if (usage.get("speed") or "standard") == "fast":
        row["f"] = 1
    if provider and provider != DEFAULT_PROVIDER:
        row["pv"] = provider
    if source and source != claude_code.NAME:
        row["a"] = source
    return {k: v for k, v in row.items() if v not in (0, "")}


def row_to_usage(row: dict) -> dict:
    """A ledger row back into the usage block price_record() expects."""
    return {
        "input_tokens": row.get("in", 0),
        "output_tokens": row.get("o", 0),
        "cache_read_input_tokens": row.get("r", 0),
        "cache_creation": {"ephemeral_5m_input_tokens": row.get("w5", 0),
                           "ephemeral_1h_input_tokens": row.get("w1", 0)},
        "output_tokens_details": {"thinking_tokens": row.get("th", 0)},
        "server_tool_use": {"web_search_requests": row.get("s", 0)},
        "speed": "fast" if row.get("f") else "standard",
    }


def row_size(row: dict) -> int:
    """Total tokens in a row, for picking the complete copy of a call."""
    return sum(int(row.get(k, 0)) for k in ("in", "o", "r", "w5", "w1"))


def read_ledger(path: str = "") -> dict:
    """Every recorded call, keyed by message id, largest copy winning.

    A missing or damaged ledger is not an error. The tool falls back to the
    transcripts, which is exactly what it did before the ledger existed; it
    loses history, not correctness.
    """
    path = path or ledger_path()
    out = {}
    try:
        fh = open(path, "r", encoding="utf-8", errors="ignore")
    except OSError:
        return out
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue  # one bad line must not cost the whole history
            mid = row.get("i")
            if not mid:
                continue
            prev = out.get(mid)
            if prev is None or row_size(row) > row_size(prev):
                out[mid] = row
    return out


def append_ledger(rows: list, path: str = "") -> int:
    """Add rows to the end of the ledger, in one write.

    One write because the menu bar, the status line and a command line run can
    all be reading at once; a single append of complete lines cannot interleave
    into a half-written row.
    """
    if not rows:
        return 0
    path = path or ledger_path()
    rows = sorted(rows, key=lambda r: (r.get("t", ""), r.get("i", "")))
    blob = "".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in rows)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(blob)
    except OSError:
        return 0
    return len(rows)


def parse_since(s: str) -> dt.datetime | None:
    if not s:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    s = s.strip().lower()
    try:
        if s.endswith("h"):
            return now - dt.timedelta(hours=float(s[:-1]))
        if s.endswith("d"):
            return now - dt.timedelta(days=float(s[:-1]))
        if s.endswith("w"):
            return now - dt.timedelta(weeks=float(s[:-1]))
        return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)
    except ValueError:
        sys.exit(f"could not read --since {s!r}: use 24h, 7d, 2w or 2026-09-01")


def month_first(d: dt.date) -> dt.date:
    """The first of d's month."""
    return d.replace(day=1)


def period_range(name: str) -> tuple:
    """(since, until) for a named calendar period, in local time.

    Calendar, not rolling. "Last month" is the month that just ended, whatever
    length it happened to be, which is the question you ask when checking a
    figure against a bill or a budget. Rolling windows stay on --since, where
    "30d" is always exactly thirty days and so is always comparable with the
    thirty before it. The two answer different questions and the tool offers
    both rather than picking for you.
    """
    name = (name or "").strip().lower()
    today = dt.date.today()

    def at(d):
        return dt.datetime.combine(d, dt.time.min).astimezone()

    if name == "today":
        return at(today), None
    if name == "yesterday":
        return at(today - dt.timedelta(days=1)), at(today)
    if name == "week":                      # this week, Monday to now
        return at(today - dt.timedelta(days=today.weekday())), None
    if name == "lastweek":
        start = today - dt.timedelta(days=today.weekday() + 7)
        return at(start), at(start + dt.timedelta(days=7))
    if name == "month":                     # this calendar month, 1st to now
        return at(month_first(today)), None
    if name == "lastmonth":
        end = month_first(today)
        return at(month_first(end - dt.timedelta(days=1))), at(end)
    if name == "year":
        return at(today.replace(month=1, day=1)), None
    sys.exit(f"unknown period {name!r}: try today, yesterday, week, lastweek, "
             f"month, lastmonth or year")


def period_label(name: str) -> str:
    """How a named period reads in the report header."""
    name = (name or "").strip().lower()
    today = dt.date.today()
    if name == "lastmonth":
        return month_first(month_first(today) - dt.timedelta(days=1)).strftime("%B %Y")
    if name == "month":
        return today.strftime("%B %Y") + ", so far"
    if name == "lastweek":
        start = today - dt.timedelta(days=today.weekday() + 7)
        return f"week of {start.strftime('%d %b')}"
    if name == "week":
        return "this week, so far"
    if name == "year":
        return f"{today.year}, so far"
    return name


def iter_events(paths, since=None, ledger=True, until=None, online=None):
    """Yield one priced event per API response, de-duplicated across files.

    Resuming or forking a session copies earlier messages into a new transcript,
    so the same response can appear in several files. Keying on the message id
    stops it being counted twice.

    One id is also written repeatedly inside its own transcript while the reply
    streams, once as each content block lands, and every copy but the last
    carries a half-finished usage block with the output count still climbing.
    Keeping whichever copy came first therefore prices a finished answer at the
    length it had four tokens in. The complete block is the largest, so that is
    the one kept: on one real three-month history, taking the first lost 212k
    output tokens, 7% of all output.

    A response is attributed to where it was first seen, so the timestamp,
    session and project stay those of the run that made the call.

    With ledger=True this also reconciles against the ledger: anything the
    transcripts know and the ledger does not gets written there, and anything
    the ledger knows and the transcripts no longer do gets read back. That is
    what makes "all time" survive Claude Code deleting old transcripts. Pass
    ledger=False for a partial scan, such as the status line's one-day window,
    where the ledger would be read for nothing.

    Before anything is priced, every model seen is checked against the price
    tables, and one they lack is looked up online (see resolve_prices). Pass
    online=False where a network wait is unacceptable, as the status line does.
    """
    best = scan_transcripts(paths)
    if ledger:
        reconcile_ledger(best)
    if online is None or online:
        # The startup check: every model seen gets a price before anything is
        # priced. Instant when the tables already cover everything.
        resolve_prices((ev["provider"], ev["model"]) for ev in best.values())

    for ev in best.values():
        if _ONLY and ev["source"] not in _ONLY:
            continue
        if _PROJECT and _PROJECT[0].lower() not in (ev["project"] or "").lower():
            continue
        if _SESSION and not (ev["session"] or "").startswith(_SESSION[0]):
            continue
        if since and ev["when"] and ev["when"] < since:
            continue
        if until and ev["when"] and ev["when"] >= until:
            continue
        usage = ev.pop("_usage")
        ev.pop("_size")
        ev["cost"] = price_record(ev["model"], usage, usage.get("speed") or "standard",
                                  ev["when"], ev["provider"])
        yield ev


def scan_transcripts(paths) -> dict:
    """The log half of the work: call id -> event, complete copy won.

    Each file goes to the adapter that reads its format, and every record it
    yields is folded in by merge(), so de-duplication is one rule for every
    harness. Split out from iter_events so the ledger rebuild can reach the
    call ids, which the priced events deliberately do not carry.
    """
    for a in ALL_SOURCES.values():
        if hasattr(a, "reset"):
            a.reset()
    best = {}
    for path in paths:
        for key, ev in adapter_for(path).records(path):
            merge(best, key, ev)
    return best


def reconcile_ledger(best: dict) -> tuple:
    """Write what the transcripts know, read back what they have lost.

    Returns (written, restored). Both directions matter: without the write the
    ledger never learns, and without the read a swept transcript still costs
    you its history.
    """
    known = read_ledger()
    LEDGER_STATE.update(rows=len(known), used=True)

    fresh, new = [], 0
    for mid, ev in best.items():
        row = known.get(mid)
        if row is None or ev["_size"] > row_size(row):
            new += row is None
            fresh.append(usage_to_row(mid, ev["when"], ev["model"],
                                      ev["project"], ev["session"], ev["_usage"],
                                      ev["provider"], ev["source"]))
    written = append_ledger(fresh)
    # What the ledger holds now, not before this run wrote to it: a first run
    # used to report "ledger holds 0" having just written every call there.
    if written:
        LEDGER_STATE.update(rows=len(known) + new)

    restored = 0
    for mid, row in known.items():
        prev = best.get(mid)
        if prev is not None and prev["_size"] >= row_size(row):
            continue
        best[mid] = {
            "when": parse_time(row.get("t")),
            "model": row.get("m", ""),
            # Rows written before providers existed carry neither field, and
            # every one of them is a Claude Code call priced by Anthropic.
            "provider": row.get("pv", DEFAULT_PROVIDER),
            "project": row.get("p", ""),
            "session": row.get("c", ""),
            "cwd": "",
            "sidechain": False,
            "source": row.get("a", claude_code.NAME),
            "_usage": row_to_usage(row),
            "_size": row_size(row),
        }
        if prev is None:
            restored += 1
    LEDGER_STATE.update(written=written, restored=restored)
    return written, restored

def covered_span(groups, n_files) -> str:
    """What "all time" actually means, in words.

    It is not the subscription, the account or the install. It is every API
    response in the transcripts on disk right now, so the honest label is the
    window those transcripts happen to cover. Claude Code sweeps transcripts
    older than cleanupPeriodDays (30 by default), at which point the earliest
    date here quietly moves forward, and saying so beats a bare "all time".
    """
    days = sorted(groups["day"])
    if not days:
        return ""
    def pretty(d):
        return dt.datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")
    window = pretty(days[0]) if days[0] == days[-1] else f"{pretty(days[0])} to {pretty(days[-1])}"
    roots = projects_dirs()
    where = "" if len(roots) == 1 else f" across {len(roots)} folders"
    if isinstance(n_files, int):
        n_files = [None] * n_files
    counts = defaultdict(int)
    for p in n_files:
        counts[_OWNER.get(p, claude_code.NAME) if p else claude_code.NAME] += 1
    if set(counts) <= {claude_code.NAME}:
        n = counts[claude_code.NAME]
        files = f"{n:,} transcript{'' if n == 1 else 's'} on disk{where}"
    else:
        parts = []
        for name, n in sorted(counts.items()):
            a = ALL_SOURCES[name]
            what = getattr(a, "FILE", a.FILES) if n == 1 else a.FILES
            # The importer's label is "Imported events"; its files need no prefix.
            parts.append(f"{n:,} {what}" if name == importer.NAME else f"{n:,} {a.LABEL} {what}")
        files = join_words(parts)
    line = f"{window} · {files}"
    if LEDGER_STATE["used"]:
        line += f" · ledger holds {LEDGER_STATE['rows']:,}"
        if LEDGER_STATE["restored"]:
            line += f", {LEDGER_STATE['restored']:,} of them no longer in any transcript"
    return line


def join_words(items) -> str:
    """A list as a sentence names it: "a", "a and b", "a, b and c"."""
    items = list(items)
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def blank():
    row = {c: 0.0 for c in COMPONENTS}
    row["total"] = 0.0
    row["no_cache"] = 0.0
    row["calls"] = 0
    row["tokens"] = {k: 0 for k in ("input", "cache_write", "cache_read", "output", "thinking", "searches")}
    return row


def add(row, ev):
    c = ev["cost"]
    for comp in COMPONENTS:
        row[comp] += c[comp]
        row["total"] += c[comp]
    row["calls"] += 1
    row["no_cache"] += c["_no_cache"]
    for k, v in c["_tokens"].items():
        row["tokens"][k] += v


# Models priced this run from a rate looked up online: (provider, model) -> source.
FETCHED_USED: dict = {}


def model_label(model: str, provider: str) -> str:
    """A model named for a report: bare for Anthropic, as it always was, and
    with its provider otherwise, since two providers can share a model name."""
    return model if provider == DEFAULT_PROVIDER else f"{model} ({provider})"


def unknown_label(model: str, provider: str) -> str:
    """How an unpriced model is named in a warning. Anthropic ids are named
    bare, as they always were; anything else says whose table it missed."""
    if provider == DEFAULT_PROVIDER:
        return model
    if provider not in TABLES:
        return f"{model} ({provider}, no price table)"
    return f"{model} ({provider})"


def collect(paths, since=None, ledger=True, until=None):
    overall = blank()
    groups = {"project": defaultdict(blank), "model": defaultdict(blank),
              "day": defaultdict(blank), "session": defaultdict(blank),
              # For the dashboard's rhythm charts: when in the day and week the
              # work actually happens. Free to collect in the pass we already make.
              "hour": defaultdict(blank), "weekday": defaultdict(blank),
              # Which harness each call came from, and whose price table it
              # used. Also what decides the verification notes in each report.
              "source": defaultdict(blank), "provider": defaultdict(blank)}
    meta = {}
    unknown = set()
    FETCHED_USED.clear()
    for ev in iter_events(paths, since, ledger=ledger, until=until):
        add(overall, ev)
        add(groups["project"][ev["project"]], ev)
        add(groups["model"][ev["model"]], ev)
        add(groups["session"][ev["session"]], ev)
        add(groups["source"][ev["source"]], ev)
        add(groups["provider"][ev["provider"]], ev)
        if ev["when"]:
            local = ev["when"].astimezone()
            add(groups["day"][local.strftime("%Y-%m-%d")], ev)
            add(groups["hour"][local.strftime("%H")], ev)
            add(groups["weekday"][str(local.weekday())], ev)
        if ev["cost"]["_unknown_model"]:
            unknown.add(unknown_label(ev["model"], ev["provider"]))
        elif ev["cost"]["_fetched"]:
            FETCHED_USED[(ev["provider"], ev["model"])] = ev["cost"]["_fetched"]
        m = meta.setdefault(ev["session"], {"project": ev["project"], "cwd": ev["cwd"],
                                            "first": ev["when"], "last": ev["when"]})
        if ev["when"]:
            if not m["first"] or ev["when"] < m["first"]:
                m["first"] = ev["when"]
            if not m["last"] or ev["when"] > m["last"]:
                m["last"] = ev["when"]
    return overall, groups, meta, unknown


# ---------------------------------------------------------------- rendering

def money(usd: float) -> str:
    """Format a dollar amount in the selected display currency.

    Two decimals, the way money is written, thousands separated. One
    exception: a non-zero amount below a penny keeps four, so a single cheap
    call reads as $0.0290 rather than as free.

    Rounding anything over a thousand to whole units, which this used to do,
    made the report contradict itself on the page. "Without cache reads
    $2,519" over "Saved $2,011" over "With cache reads $508.17" does not add
    up when read, though the figures behind them agree exactly. Zero showed as
    $0.0000, which is not how anyone writes nothing.
    """
    x = usd * DISPLAY["rate"]
    sym = DISPLAY["symbol"]
    if x == 0:
        return f"{sym}0.00"
    if abs(x) < 0.00005:
        # Real money, but below the smallest figure worth printing. $0.0000
        # would read as nothing at all, which is the thing being fixed here.
        return ("-" if x < 0 else "") + f"<{sym}0.0001"
    if abs(x) < 0.01:
        return f"{sym}{x:.4f}"
    return f"{sym}{x:,.2f}"


def unit_money(usd: float) -> str:
    """A per-million-token rate rather than a total.

    Always four decimals. This one sits beside a full input rate of $5.00 and
    the whole point of the sentence is the size of the gap, so rounding it to
    $0.48 like a total throws away the comparison.
    """
    return f"{DISPLAY['symbol']}{usd * DISPLAY['rate']:,.4f}"


def shown_difference(big: float, small: float) -> float:
    """A difference that still adds up once both sides have been rounded.

    with, without and saved are each rounded to the penny on their own, and
    three roundings of exact figures can leave the column a penny out:
    GBP 378.92 over 1,506.95 reads as 1,885.87 beside a "without" of 1,885.86.
    The arithmetic underneath is exact, it is the printing that disagrees, and
    a report whose own subtraction looks wrong is not worth much. Taking the
    difference of the two rounded figures costs at most half a penny against
    the true saving and makes the page self-consistent in every currency.
    """
    r = DISPLAY["rate"] or 1.0
    return (round(big * r, 2) - round(small * r, 2)) / r


def toks(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


BOLD, DIM, RESET = "\x1b[1m", "\x1b[2m", "\x1b[0m"
CYAN, GREEN, YELLOW = "\x1b[36m", "\x1b[32m", "\x1b[33m"


def project_name(project: str) -> str:
    """A project as a person would name it, without the home directory.

    Claude Code stores a project as its folder slug: the working directory
    with every character that is not a letter or digit turned into "-", so
    /Users/sam/code/app becomes -Users-sam-code-app. Other adapters and
    imports carry a real path. Either way the home directory is dropped, which
    reads better and keeps a username out of every screenshot.
    """
    if not project:
        return project
    home = os.path.expanduser("~").rstrip(os.sep)
    if project.startswith(home + os.sep):
        return project[len(home) + 1:]
    slug = re.sub(r"[^A-Za-z0-9]", "-", home) + "-"
    if project.startswith(slug):
        return project[len(slug):]
    return project


def display_name(by: str, key: str) -> str:
    """A group key as it reads in a report."""
    if by == "project":
        return project_name(key)
    if by == "source":
        a = ALL_SOURCES.get(key)
        return a.LABEL if a else key
    if by == "provider":
        t = TABLES.get(key)
        return t.NAME if t else key
    return key


def share_text(fraction: float) -> str:
    """A share of a total, for a sentence: "12.3%", or "under 0.1%" rather
    than a "0.0%" that reads as none at all."""
    pct = fraction * 100
    return "under 0.1%" if 0 < pct < 0.05 else f"{pct:.1f}%"


UNVERIFIED_NOTE = ("unverified: built from the published log format, not yet checked "
                   "against real logs. If a figure looks wrong, please open an issue "
                   "with a sample.")


def report_notes(groups, unknown) -> list:
    """What every face must say alongside the figures, as (level, text).

    The same list feeds the terminal, the dashboard and the menu bar, so the
    three never disagree about how far a number can be trusted. "warn" is
    something to act on; "info" is the provenance every report carries.
    """
    notes = []
    sources = groups.get("source", {})
    unverified = [n for n in sorted(sources)
                  if getattr(ALL_SOURCES.get(n), "STATUS", "") == "unverified"]
    if unverified:
        # One line naming them all, not one per harness saying the same thing.
        # Beside another source it also says how much of the total they carry,
        # which is the figure that decides how far to trust the whole.
        names = join_words(ALL_SOURCES[n].LABEL for n in unverified)
        share = ""
        whole = sum(v["total"] for v in sources.values())
        if len(sources) > 1 and whole:
            share = f", {share_text(sum(sources[n]['total'] for n in unverified) / whole)} of this total,"
        notes.append(("warn", f"{names} figures{share} are {UNVERIFIED_NOTE}"))
    for a in ALL_SOURCES.values():
        for text in (a.notes() if hasattr(a, "notes") else []):
            notes.append(("warn", text))
    for path, p in sorted(importer.PROBLEMS.items()):
        shown = "standard input" if path == "-" else os.path.basename(path)
        notes.append(("warn", f"{p['skipped']:,} line{'' if p['skipped'] == 1 else 's'} "
                              f"skipped in {shown}: " + "; ".join(p["examples"])))
    for (provider, model), via in sorted(FETCHED_USED.items()):
        row = fetched_row(provider, model) or {}
        checked = row.get("_checked", "")
        when = dt.date.fromisoformat(checked).strftime("%d %b %Y").lstrip("0") if checked else ""
        notes.append(("warn", f"{model_label(model, provider)} is priced at "
                              f"${row.get('in', 0):g} in and ${row.get('out', 0):g} out per million "
                              f"from {via}, looked up online {when}, not checked by hand"))
    if unknown:
        # A model looked up online and found nowhere is the same problem as one
        # with no price on file, so it is one note, which says both.
        missed = sorted(set(unknown) & {unknown_label(i["model"], i["provider"])
                                         for i in LOOKUPS if not i["found"]})
        online = ""
        if missed and len(missed) == len(unknown):
            online = ", and none published online either"
        elif missed:
            online = f" (and none published online for {join_words(missed)})"
        notes.append(("warn", f"no price on file for {join_words(sorted(unknown))}{online}. "
                              "Priced at that provider's flagship rate as a stand-in "
                              "(zero where there is no table at all). "
                              f"Add {'it' if len(unknown) == 1 else 'them'} under pricing/."
                              + ("" if ONLINE_LOOKUP[0] else " The online lookup is off.")))
    for provider in sorted(groups.get("provider", {})):
        v = verification(provider)
        if not v["verified_on"]:
            continue
        how = "verified against real usage" if v["measured"] else "published rates, not yet checked against a real bill"
        if v["stale"]:
            notes.append(("warn", f"{v['name']} rates were last checked {v['pretty']}, "
                                  f"{v['age_days']} days ago. Prices may have moved; "
                                  f"run --check-prices or compare with {v['source']}"))
        else:
            notes.append(("info", f"{v['name']} rates checked {v['pretty']} ({how})"))
    return notes


def print_report(overall, groups, meta, unknown, by, label, sessions=False, covered=""):
    print()
    print(f"  {BOLD}{CYAN}Tokenmeter{RESET}  {DIM}at API rates · {label}{RESET}")
    print(f"  {DIM}{'-' * 64}{RESET}")
    alt = ""
    if DISPLAY["code"] != "USD":
        alt = f"   {DIM}(${overall['total']:,.2f}){RESET}"
    print(f"  {BOLD}{YELLOW}{money(overall['total'])}{RESET}{alt}"
          f"   {DIM}{overall['calls']:,} API calls{RESET}")
    if covered:
        print(f"  {DIM}{covered}{RESET}")
    print()

    t = overall["tokens"]
    rows = [
        ("input, uncached", t["input"], overall["input"]),
        ("cache writes", t["cache_write"], overall["cache_write"]),
        ("cache reads", t["cache_read"], overall["cache_read"]),
        ("output", t["output"], overall["output"]),
    ]
    for name, tk, cost in rows:
        share = (cost / overall["total"] * 100) if overall["total"] else 0
        bar = "█" * int(round(share / 4))
        print(f"    {name:<18}{toks(tk):>9}  {money(cost):>10}  {DIM}{share:4.1f}%{RESET} {GREEN}{bar}{RESET}")
    if overall["web_search"]:
        print(f"    {'web searches':<18}{t['searches']:>9}  {money(overall['web_search']):>10}")
    if t["thinking"]:
        print(f"  {DIM}    of which thinking: {toks(t['thinking'])} output tokens{RESET}")

    prompt_tokens = sum(t[k] for k in ("input", "cache_write", "cache_read"))
    if prompt_tokens:
        no_cache = overall["no_cache"]
        saved = no_cache - overall["total"]
        pct = (saved / no_cache * 100) if no_cache else 0
        multiple = (no_cache / overall["total"]) if overall["total"] else 0
        print()
        print(f"  {BOLD}what caching is worth{RESET}")
        print(f"    {'with cache reads':<24}{money(overall['total']):>12}   {DIM}what you actually ran{RESET}")
        print(f"    {'without cache reads':<24}{money(no_cache):>12}   {DIM}every prompt token billed fresh{RESET}")
        shown = shown_difference(no_cache, overall["total"])
        print(f"    {'saved':<24}{GREEN}{money(shown):>12}{RESET}   {DIM}{pct:.1f}% cheaper, {multiple:.1f}x{RESET}")
        print(f"  {DIM}  {t['cache_read'] / prompt_tokens * 100:.1f}% of prompt tokens came from cache "
              f"at {unit_money(overall['cache_read'] / max(t['cache_read'], 1) * 1e6)} per million, "
              f"against full input rates{RESET}")

    if by:
        print()
        print(f"  {BOLD}by {by}{RESET}")
        items = sorted(groups[by].items(), key=lambda kv: -kv[1]["total"])
        if by == "day":
            items = sorted(groups[by].items())
        width = max((len(display_name(by, k)) for k, _ in items), default=10)
        width = min(width, 46)
        peak = max((v["total"] for _, v in items), default=0) or 1
        for k, v in items:
            name = display_name(by, k)
            name = name if len(name) <= width else "…" + name[-(width - 1):]
            bar = "█" * int(round(v["total"] / peak * 22))
            print(f"    {name:<{width}}  {money(v['total']):>10}  {DIM}{v['calls']:>4} calls{RESET}  {CYAN}{bar}{RESET}")

    if sessions:
        print()
        print(f"  {BOLD}sessions, dearest first{RESET}")
        items = sorted(groups["session"].items(), key=lambda kv: -kv[1]["total"])[:20]
        for sid, v in items:
            m = meta.get(sid, {})
            when = m.get("last").astimezone().strftime("%d %b %H:%M") if m.get("last") else "?"
            proj = project_name(m.get("project") or "")[-30:]
            print(f"    {money(v['total']):>10}  {DIM}{when:<13}{RESET} {sid[:8]}  {DIM}{proj}{RESET}")

    notes = report_notes(groups, unknown)
    if notes:
        print()
    for level, text in notes:
        tag = f"{YELLOW}note{RESET}: " if level == "warn" else ""
        colour = "" if level == "warn" else DIM
        print(f"  {tag}{colour}{text}{RESET}")
    if DISPLAY["code"] != "USD":
        tag = "live" if DISPLAY["live"] else "OFFLINE ESTIMATE"
        print()
        print(f"  {DIM}shown in {CURRENCIES[DISPLAY['code']][1]} at "
              f"{DISPLAY['rate']:.4f} to the dollar ({tag}, {DISPLAY['when']}). "
              f"--currency USD for the billed figures.{RESET}")
    print()


FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# opsz and SOFT are the axes the headline animates on hover; wght is the rest.
FONTS = (("Fraunces", "fraunces.woff2", "300 700"),
         ("Inter Tight", "inter-tight.woff2", "400 700"))


def font_faces() -> str:
    """The typefaces, base64'd straight into the page.

    The dashboard is a file on disk that has to look the same in five years
    with the wifi off, so it carries its own fonts rather than fetching them.
    Latin subsets, about 216 KB base64. Missing files are not an error: the
    stacks in the stylesheet fall back to the system serif and sans.
    """
    out = []
    for family, filename, weights in FONTS:
        path = os.path.join(FONT_DIR, filename)
        try:
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
        except OSError:
            continue
        out.append("@font-face{font-family:'" + family + "';font-style:normal;"
                   "font-weight:" + weights + ";font-display:block;"
                   "src:url(data:font/woff2;base64," + b64 + ") format('woff2-variations')}")
    return "".join(out)


DASH_CSS = """/* Tokenmeter dashboard.
   An instrument, not a landing page. One accent, tabular numerals wherever a
   figure appears, and motion that reports something rather than decorating. */
:root{
  --bg:#090a0c; --card:#121417; --card2:#171a1f;
  --line:#212429; --line2:#2c313a;
  --ink:#eef0f4; --dim:#8c94a2; --dimmer:#5c6371;
  /* --acc and --acc2 are also the app icon's tick (costbar/icon.swift). */
  --acc:#d97757; --acc2:#e8916f; --cool:#5b9dd9; --good:#5cab7f; --warm:#c9a227;
  /* The four parts of a bill, as a set: checked together for colour-blind
     separation on --bg (worst neighbouring pair Delta E 18.6 under
     protanopia, against a floor of 8). Change one and re-check them all. */
  --s1:var(--acc); --s2:var(--cool); --s3:#d4a03c; --s4:#9085e9;
  --r:15px; --ease:cubic-bezier(.22,.68,.16,1);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;background:var(--bg)}
body{
  margin:0;padding:0 0 90px;background:var(--bg);color:var(--ink);
  font-family:"Inter Tight",ui-sans-serif,-apple-system,"SF Pro Text",Segoe UI,sans-serif;
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;
  font-variation-settings:"wght" 430;
}
/* the grain is what stops a flat dark page reading as a template */
body::before{
  content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.035;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.82' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E");
}
.num,.n,td.n,.big,.kpi b,.win-v,.cmp .v,.lg-v,.lg-t{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}
.wrap{max-width:1180px;margin:0 auto;padding:0 30px;position:relative;z-index:1}

/* ---------- opening sweep ---------- */
#sweep{position:fixed;top:0;left:0;height:2px;width:100%;background:var(--acc);z-index:99;
  transform-origin:left;transform:scaleX(0);animation:sweep 1.15s var(--ease) forwards}
@keyframes sweep{0%{transform:scaleX(0);opacity:1}70%{transform:scaleX(1);opacity:1}100%{transform:scaleX(1);opacity:0}}

/* ---------- masthead ---------- */
.top{position:relative;border-bottom:1px solid var(--line);padding:56px 0 0;margin-bottom:38px;overflow:hidden}
.top::after{content:"";position:absolute;top:-260px;left:8%;width:620px;height:620px;pointer-events:none;
  background:radial-gradient(circle,#d9775726 0%,transparent 66%);
  animation:bloom 1.6s var(--ease) both}
@keyframes bloom{from{opacity:0;transform:scale(.75)}to{opacity:1;transform:scale(1)}}
.eyebrow{font-size:11px;letter-spacing:.42em;text-transform:uppercase;color:var(--dimmer);
  margin:0 0 16px;font-weight:520;animation:track 1.1s var(--ease) both}
@keyframes track{from{opacity:0;letter-spacing:.9em}to{opacity:1;letter-spacing:.42em}}
h1{font-family:Fraunces,"Iowan Old Style",Georgia,serif;
  font-size:clamp(32px,5.4vw,58px);line-height:1.02;margin:0 0 14px;font-weight:400;
  letter-spacing:-.022em;font-variation-settings:"SOFT" 0,"WONK" 1,"opsz" 144;
  transition:font-variation-settings 1s var(--ease)}
h1:hover{font-variation-settings:"SOFT" 100,"WONK" 1,"opsz" 9}
h1 .ln{display:block;overflow:hidden}
h1 .ln>span{display:block;transform:translateY(105%);animation:rise .95s var(--ease) forwards}
h1 .ln:nth-child(2)>span{animation-delay:.09s}
@keyframes rise{to{transform:translateY(0)}}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim);font-size:13.5px;margin:0 0 4px;animation:up .8s var(--ease) .3s both}
.sub code{font-family:inherit;color:var(--dimmer)}
@keyframes up{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}

/* ---------- pills ---------- */
.pills{display:flex;gap:7px;flex-wrap:wrap;margin:26px 0 0;padding-bottom:30px}
.pill{background:transparent;border:1px solid var(--line2);color:var(--dim);border-radius:999px;
  padding:7px 15px;font:inherit;font-size:12.5px;font-weight:500;cursor:pointer;
  transition:color .2s,border-color .2s,background .2s,transform .2s var(--ease);
  animation:up .6s var(--ease) both}
.pill:hover{color:var(--ink);border-color:var(--dim);transform:translateY(-2px)}
.pill.on{background:var(--acc);border-color:var(--acc);color:#141010;font-weight:600}

/* ---------- hero ---------- */
.hero{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);gap:22px;margin-bottom:24px}
@media(max-width:900px){.hero{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
  padding:28px 30px;position:relative;overflow:hidden}
.card.lift{transition:border-color .3s,transform .3s var(--ease)}
.card.lift:hover{border-color:var(--line2)}
.hero .card{animation:up .85s var(--ease) .42s both}
.hero .card:nth-child(2){animation-delay:.54s}
.big{font-family:Fraunces,Georgia,serif;font-weight:400;
  font-size:clamp(48px,7.8vw,80px);line-height:.97;letter-spacing:-.034em;color:var(--acc);
  font-variation-settings:"SOFT" 24,"opsz" 144;display:block}
.big.settling{filter:blur(7px);opacity:.55}
.big{transition:filter .7s var(--ease),opacity .7s var(--ease)}
.big-sub{color:var(--dim);font-size:13px;margin-top:14px}
.hero-foot{display:flex;gap:32px;flex-wrap:wrap;margin-top:26px;padding-top:22px;border-top:1px solid var(--line)}
.kpi b{display:block;font-size:22px;font-weight:600;letter-spacing:-.012em}
.kpi span{display:block;font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--dimmer);margin-top:4px}

/* ---------- window strip ---------- */
.wins{display:flex;flex-direction:column;justify-content:center}
.win{display:flex;align-items:center;gap:16px;padding:14px 6px;border-bottom:1px solid var(--line);
  cursor:default;transition:padding-left .3s var(--ease),background .25s;border-radius:8px}
.win:last-child{border-bottom:0}
.win:hover{padding-left:12px;background:#ffffff05}
.win-k{color:var(--dim);font-size:13px}
.win-v{font-size:22px;font-weight:600;letter-spacing:-.014em}
.win-bar{height:2px;background:linear-gradient(90deg,var(--acc),var(--acc2));border-radius:2px;margin-top:7px;
  transform-origin:left;transform:scaleX(0);transition:transform 1.1s var(--ease)}
.reveal .win-bar{transform:scaleX(1)}
.win-c{color:var(--dimmer);font-size:11.5px;margin-left:auto;padding-left:14px;min-width:46px;text-align:right}

/* ---------- sections ---------- */
section{margin:52px 0 0;position:relative}
.hd{display:flex;align-items:baseline;gap:14px;margin-bottom:5px}
.no{font-family:Fraunces,Georgia,serif;font-size:13px;color:var(--acc);opacity:.75;
  font-variation-settings:"opsz" 9}
h2{font-size:11.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);font-weight:600;margin:0}
.rule{height:1px;background:var(--line2);flex:1;transform-origin:left;transform:scaleX(0);
  transition:transform 1.1s var(--ease) .1s}
.reveal .rule{transform:scaleX(1)}
.lede{color:var(--dimmer);font-size:13px;margin:0 0 20px;max-width:66ch}

/* ---------- chart ---------- */
.chart-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.toggles{display:flex;gap:5px}
.tg{background:transparent;border:1px solid var(--line2);color:var(--dim);border-radius:9px;
  padding:6px 13px;font:inherit;font-size:12px;cursor:pointer;transition:.2s}
.tg:hover{color:var(--ink);border-color:var(--dim)}
.tg.on{background:var(--card2);color:var(--ink);border-color:var(--dim)}
.chart{position:relative}
svg{display:block;width:100%;overflow:visible}
.gridline{stroke:var(--line);stroke-width:1}
.axlab{fill:var(--dimmer);font-size:10.5px;font-variant-numeric:tabular-nums}
.dbar{fill:url(#bargrad);transition:opacity .18s}
.dbar.dull{opacity:.3}
.cum{fill:none;stroke:var(--cool);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.cumfill{fill:url(#cumgrad)}
.hit{fill:transparent;cursor:crosshair}
.cross{stroke:var(--dim);stroke-width:1;stroke-dasharray:3 4;opacity:0;transition:opacity .14s}
.knob{fill:var(--cool);stroke:var(--bg);stroke-width:2.5;opacity:0;transition:opacity .14s}
.tip{position:absolute;pointer-events:none;opacity:0;background:#1c2027;border:1px solid var(--line2);
  border-radius:10px;padding:10px 13px;font-size:12.5px;white-space:nowrap;z-index:6;
  box-shadow:0 14px 38px #000b;transition:opacity .15s,transform .22s var(--ease)}
.tip.on{opacity:1}
.tip b{font-size:15px;display:block;margin:3px 0;font-variant-numeric:tabular-nums}
.tip i{font-style:normal;color:var(--dimmer);display:block;font-size:11.5px}

/* ---------- composition ---------- */
.stack{display:flex;height:46px;border-radius:10px;overflow:hidden;border:1px solid var(--line)}
/* a hairline of page between parts, so neighbours never merge */
.seg+.seg{border-left:2px solid var(--bg)}
.seg{transform:scaleX(0);transform-origin:left;transition:transform .95s var(--ease),filter .2s}
.reveal .seg{transform:scaleX(1)}
.seg:hover{filter:brightness(1.25)}
.legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0 22px;margin-top:20px}
.lg{display:flex;align-items:baseline;gap:10px;padding:12px 2px;border-bottom:1px solid var(--line);
  transition:opacity .22s}
.legend.muted .lg:not(:hover){opacity:.4}
.dot{width:9px;height:9px;border-radius:3px;flex:0 0 auto;transform:translateY(1px)}
.lg-k{color:var(--dim);font-size:13px}
.lg-v{margin-left:auto;font-weight:600}
.lg-t{color:var(--dimmer);font-size:11.5px;min-width:62px;text-align:right}

/* ---------- comparison ---------- */
.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.cmp .card{padding:24px 26px}
.cmp h3{margin:0 0 12px;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--dimmer);font-weight:600}
.cmp .v{font-size:29px;font-weight:600;letter-spacing:-.018em}
.cmp small{display:block;color:var(--dimmer);font-size:12px;margin-top:10px;line-height:1.55}
.cmp .card.good{border-color:#2d5a43}
.cmp .card.good .v{color:var(--good)}

/* ---------- tables ---------- */
table{width:100%;border-collapse:collapse;font-size:13.5px}
td,th{padding:12px 10px;text-align:left;border-bottom:1px solid var(--line);position:relative}
th{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--dimmer);font-weight:600}
th.n,td.n{text-align:right}          /* both, or the column reads crooked */
tbody tr{transition:background .18s;opacity:0;transform:translateY(7px)}
.reveal tbody tr{opacity:1;transform:none;transition:opacity .5s var(--ease),transform .5s var(--ease),background .18s}
tbody tr:hover{background:#ffffff07}
td.dim,.dim{color:var(--dim)}
.bar-cell i{position:absolute;left:10px;bottom:0;height:2px;border-radius:2px;
  background:linear-gradient(90deg,var(--acc),transparent);
  transform-origin:left;transform:scaleX(0);transition:transform 1s var(--ease)}
.reveal .bar-cell i{transform:scaleX(1)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}

/* ---------- rhythm ---------- */
.rhythm{display:grid;grid-template-columns:1fr 1fr;gap:30px}
@media(max-width:780px){.rhythm{grid-template-columns:1fr}}
.sub-h{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dimmer);margin:0 0 12px;font-weight:600}
.cols{display:flex;align-items:flex-end;gap:3px;height:112px}
.col{flex:1;background:linear-gradient(180deg,var(--acc2),var(--acc));border-radius:3px 3px 0 0;min-height:2px;
  transform-origin:bottom;transform:scaleY(0);transition:transform .85s var(--ease),filter .18s}
.reveal .col{transform:scaleY(1)}
.col:hover{filter:brightness(1.3)}
.cols-x{display:flex;gap:3px;margin-top:8px}
.cols-x span{flex:1;text-align:center;font-size:9.5px;color:var(--dimmer);font-variant-numeric:tabular-nums}

/* ---------- footer ---------- */
footer{margin-top:58px;padding-top:26px;border-top:1px solid var(--line);color:var(--dimmer);font-size:12.5px}
footer p{margin:0 0 8px;max-width:78ch}
.warn{color:var(--warm)}

/* ---------- reveal ---------- */
.fade{opacity:0;transform:translateY(18px);transition:opacity .75s var(--ease),transform .75s var(--ease)}
.fade.reveal{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){
  *{transition-duration:.01ms!important;animation-duration:.01ms!important;animation-iteration-count:1!important}
  .fade,h1 .ln>span,.pill,.sub,.hero .card{opacity:1!important;transform:none!important}
  .win-bar,.col,.bar-cell i,.seg{transform:none!important}
  tbody tr{opacity:1!important;transform:none!important}
  #sweep{display:none}
  .big.settling{filter:none;opacity:1}
}
"""

DASH_JS = """/* Tokenmeter dashboard behaviour.
   Convert currency in place, draw the time chart, reveal on scroll. No
   framework, no build step, nothing fetched at open time. */
const D = __PAYLOAD__;
const SLOW = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const clamp = (lo, hi, v) => Math.max(lo, Math.min(hi, v));

/* ---- money. Same rule as money() in tokenmeter.py. Three copies of this
   exist, one per face, and they must agree or one figure reads two ways. ---- */
function fmt(usd, cur) {
  const x = usd * (D.rates[cur] || 1), s = D.symbols[cur] || '$';
  if (x === 0) return s + '0.00';
  if (Math.abs(x) < 0.00005) return (x < 0 ? '-' : '') + '<' + s + '0.0001';
  if (Math.abs(x) < 0.01) return s + x.toFixed(4);
  return s + x.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
let CUR = D.current;

function valueOf(el) {
  if (el.dataset.usdBig !== undefined) {
    // Rounded first, then subtracted, so the column still adds up after
    // conversion and not only in the currency it was rendered in.
    const r = D.rates[CUR] || 1;
    return (Math.round(parseFloat(el.dataset.usdBig) * r * 100) -
            Math.round(parseFloat(el.dataset.usdSmall) * r * 100)) / 100 / r;
  }
  return parseFloat(el.dataset.usd);
}

/* Tween every figure to its new value rather than snapping. A switch you can
   watch happen is a switch you believe. */
function tweenAll(dur) {
  const els = [].slice.call(document.querySelectorAll('.m'));
  const from = els.map(el => parseFloat(el.dataset.shown || '0'));
  const to = els.map(valueOf);
  if (SLOW || !dur) {
    els.forEach((el, i) => { el.textContent = fmt(to[i], CUR); el.dataset.shown = to[i]; });
    return;
  }
  const t0 = performance.now();
  (function step(now) {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
    els.forEach(function (el, i) {
      const v = from[i] + (to[i] - from[i]) * e;
      el.textContent = fmt(v, CUR);
      if (p === 1) el.dataset.shown = to[i];
    });
    if (p < 1) requestAnimationFrame(step);
  })(t0);
}

function paint(cur, tween) {
  CUR = cur;
  tweenAll(tween ? 620 : 0);
  document.querySelectorAll('.pill').forEach(b => b.classList.toggle('on', b.dataset.cur === cur));
  const note = document.getElementById('rate-note');
  if (note) note.textContent = cur === 'USD'
    ? 'Billed currency. No conversion applied.'
    : (D.rates[cur] || 1).toFixed(4) + ' to the dollar · ' + D.rateWhen;
  try { localStorage.setItem('cur', cur); } catch (e) {}
  drawChart();
}
document.querySelectorAll('.pill').forEach(function (b) {
  b.addEventListener('click', () => paint(b.dataset.cur, true));
});

/* ---- the time chart ---- */
let MODE = 'cost';
const days = D.days;
let geom = null;

function drawChart() {
  const host = document.getElementById('chart');
  const svg = host && host.querySelector('svg');
  if (!svg || !days.length) return;
  const W = Math.max(320, host.clientWidth), H = 268;
  /* The viewBox must match the pixel box we draw in. It used to be a fixed
     900 while the drawing used clientWidth, so everything rendered scaled by
     clientWidth/900 and the crosshair landed to the right of its own bar. */
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('height', H);

  const padL = 54, padR = 16, padT = 16, padB = 28;
  const iw = W - padL - padR, ih = H - padT - padB;
  const rate = D.rates[CUR] || 1, sym = D.symbols[CUR] || '$';

  const val = d => MODE === 'cost' ? d.total * rate : d.tokens;
  const peak = Math.max.apply(null, days.map(val)) || 1;
  let run = 0;
  const cum = days.map(d => (run += val(d)));
  const cumPeak = run || 1;

  const bw = iw / days.length;
  const x = i => padL + i * bw;
  const y = v => padT + ih - (v / peak) * ih;
  const yc = v => padT + ih - (v / cumPeak) * ih;
  geom = {padL, padT, ih, bw, x, yc, cum, rate};

  const shortNum = v => MODE === 'cost'
    ? (v >= 1000 ? sym + Math.round(v / 1000) + 'k' : sym + v.toFixed(v < 10 ? 1 : 0))
    : (v >= 1e9 ? (v / 1e9).toFixed(1) + 'B' : v >= 1e6 ? Math.round(v / 1e6) + 'M'
       : v >= 1e3 ? Math.round(v / 1e3) + 'k' : Math.round(v));

  let g = '';
  for (let i = 0; i <= 4; i++) {
    const yy = padT + ih - (i / 4) * ih;
    g += '<line class="gridline" x1="' + padL + '" y1="' + yy + '" x2="' + (W - padR) + '" y2="' + yy + '"/>' +
         '<text class="axlab" x="' + (padL - 9) + '" y="' + (yy + 3.5) + '" text-anchor="end">' +
         shortNum(peak * i / 4) + '</text>';
  }

  let bars = '';
  days.forEach(function (d, i) {
    const v = val(d), h = Math.max(v > 0 ? 1.5 : 0, (v / peak) * ih);
    const bx = x(i) + bw * 0.17, bwid = Math.max(1, bw * 0.66);
    bars += '<rect class="dbar" data-i="' + i + '" x="' + bx.toFixed(2) + '" y="' + (padT + ih - h).toFixed(2) +
            '" width="' + bwid.toFixed(2) + '" height="' + h.toFixed(2) + '" rx="' + Math.min(2.5, bw * 0.3).toFixed(2) + '">' +
            (SLOW ? '' :
              '<animate attributeName="height" values="0;' + h.toFixed(2) + '" dur="0.75s" begin="' +
              Math.min(500, i * 8) + 'ms" fill="freeze" calcMode="spline" keySplines="0.22 0.68 0.16 1" keyTimes="0;1"/>' +
              '<animate attributeName="y" values="' + (padT + ih) + ';' + (padT + ih - h).toFixed(2) + '" dur="0.75s" begin="' +
              Math.min(500, i * 8) + 'ms" fill="freeze" calcMode="spline" keySplines="0.22 0.68 0.16 1" keyTimes="0;1"/>') +
            '</rect>';
  });

  let line = '';
  days.forEach(function (d, i) {
    line += (i ? 'L' : 'M') + (x(i) + bw / 2).toFixed(1) + ' ' + yc(cum[i]).toFixed(1) + ' ';
  });
  const area = line + 'L' + (x(days.length - 1) + bw / 2).toFixed(1) + ' ' + (padT + ih) +
               ' L' + (x(0) + bw / 2).toFixed(1) + ' ' + (padT + ih) + ' Z';

  let ticks = '';
  const every = Math.max(1, Math.round(days.length / 8));
  days.forEach(function (d, i) {
    if (i % every && i !== days.length - 1) return;
    ticks += '<text class="axlab" x="' + (x(i) + bw / 2).toFixed(1) + '" y="' + (H - 7) +
             '" text-anchor="middle">' + d.short + '</text>';
  });

  svg.innerHTML =
    '<defs>' +
    '<linearGradient id="bargrad" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="#e8916f"/><stop offset="100%" stop-color="#c9663f"/></linearGradient>' +
    '<linearGradient id="cumgrad" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="#5b9dd9" stop-opacity=".22"/>' +
      '<stop offset="100%" stop-color="#5b9dd9" stop-opacity="0"/></linearGradient></defs>' +
    g + '<path class="cumfill" d="' + area + '"/>' + bars +
    '<path class="cum" d="' + line + '"' +
      (SLOW ? '' : ' stroke-dasharray="5000" stroke-dashoffset="5000">' +
        '<animate attributeName="stroke-dashoffset" values="5000;0" dur="1.7s" begin="0.15s" fill="freeze"/></path>') +
      (SLOW ? '/>' : '') +
    '<line class="cross" id="cross" y1="' + padT + '" y2="' + (padT + ih) + '"/>' +
    '<circle class="knob" id="knob" r="4.5"/>' + ticks +
    '<rect class="hit" x="' + padL + '" y="' + padT + '" width="' + iw + '" height="' + ih + '"/>';

  svg.querySelector('.hit').addEventListener('mousemove', onMove);
  svg.querySelector('.hit').addEventListener('mouseleave', onLeave);
}

function onMove(e) {
  const host = document.getElementById('chart'), box = host.getBoundingClientRect();
  const {padL, padT, ih, bw, x, yc, cum, rate} = geom;
  const i = clamp(0, days.length - 1, Math.floor((e.clientX - box.left - padL) / bw));
  const d = days[i], cx = x(i) + bw / 2;

  const cross = document.getElementById('cross'), knob = document.getElementById('knob');
  cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.style.opacity = 1;
  knob.setAttribute('cx', cx); knob.setAttribute('cy', yc(cum[i])); knob.style.opacity = 1;
  host.querySelectorAll('.dbar').forEach(b => b.classList.toggle('dull', +b.dataset.i !== i));

  const running = MODE === 'cost' ? fmt(cum[i] / rate, CUR)
    : (cum[i] >= 1e9 ? (cum[i] / 1e9).toFixed(2) + 'B' : Math.round(cum[i] / 1e6) + 'M') + ' tokens';
  const tip = document.getElementById('tip');
  tip.innerHTML = '<i>' + d.full + '</i><b>' + fmt(d.total, CUR) + '</b><i>' +
    d.calls.toLocaleString() + ' calls · ' + d.tokShort + ' tokens</i><i>running ' + running + '</i>';
  tip.classList.add('on');

  /* Sit beside the bar, never on top of it. Flip to the other side near the
     right edge. Overlapping the thing you are describing hides the answer. */
  const gap = 18, tw = tip.offsetWidth, th = tip.offsetHeight;
  let left = cx + gap;
  if (left + tw > box.width - 2) left = cx - gap - tw;
  tip.style.left = clamp(0, Math.max(0, box.width - tw), left) + 'px';
  tip.style.top = clamp(0, Math.max(0, box.height - th), e.clientY - box.top - th / 2) + 'px';
}

function onLeave() {
  document.getElementById('tip').classList.remove('on');
  document.getElementById('cross').style.opacity = 0;
  document.getElementById('knob').style.opacity = 0;
  document.querySelectorAll('.dbar').forEach(b => b.classList.remove('dull'));
}

document.querySelectorAll('.tg').forEach(function (b) {
  b.addEventListener('click', function () {
    document.querySelectorAll('.tg').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); MODE = b.dataset.mode; drawChart();
  });
});

/* legend hover dims the rest, so one component can be read alone */
const legend = document.querySelector('.legend');
if (legend) {
  legend.addEventListener('mouseenter', () => legend.classList.add('muted'));
  legend.addEventListener('mouseleave', () => legend.classList.remove('muted'));
}

/* ---- reveal on scroll, with the table rows stepping in ---- */
const io = new IntersectionObserver(function (entries) {
  entries.forEach(function (en) {
    if (!en.isIntersecting) return;
    en.target.classList.add('reveal');
    en.target.querySelectorAll('tbody tr').forEach(function (tr, i) {
      tr.style.transitionDelay = Math.min(360, i * 42) + 'ms';
    });
    io.unobserve(en.target);
  });
}, {threshold: 0.1, rootMargin: '0px 0px -40px 0px'});
document.querySelectorAll('.fade,.reveal-on').forEach(el => io.observe(el));

let rt;
window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(drawChart, 130); });

let stored = null;
try { stored = localStorage.getItem('cur'); } catch (e) {}
paint(stored && D.rates[stored] ? stored : D.current, false);

/* headline settles out of a blur as it counts */
const hero = document.getElementById('headline');
if (hero && !SLOW) {
  hero.classList.add('settling');
  const target = parseFloat(hero.dataset.usd), t0 = performance.now(), dur = 1250;
  (function step(now) {
    const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 4);
    hero.textContent = fmt(target * e, CUR);
    if (p < 1) requestAnimationFrame(step);
    else { hero.dataset.shown = target; hero.classList.remove('settling'); }
  })(t0);
}
"""


def render_html(overall, groups, meta, unknown, label, out_path, covered=""):
    """The full dashboard: everything the engine knows, laid out to be read.

    The menu bar is a glance and the terminal report is a check. This is the
    one with room, so it shows what the other two cannot: spend over time with
    a running total, where the money goes by component, by model, by project
    and by session, and when in the day and week the work actually happens.

    One file, no framework, no build step, nothing fetched when it opens.
    """
    days = sorted(groups["day"].items())
    t = overall["tokens"]
    rates, when, live = fx_rates()
    total = overall["total"]

    def m(usd):
        """A money value the currency switcher can rewrite in place."""
        return f'<span class="m" data-usd="{usd:.8f}" data-shown="{usd:.8f}">{money(usd)}</span>'

    def m_sub(big, small):
        """A difference the switcher recomputes from both rounded operands."""
        v = shown_difference(big, small)
        return (f'<span class="m" data-usd-big="{big:.8f}" data-usd-small="{small:.8f}" '
                f'data-shown="{v:.8f}">{money(v)}</span>')

    def head(title, lede):
        """A numbered section rule. Editorial, and it gives the eye an anchor.

        Sections are built out of order (the tables before the page around
        them), so each gets a placeholder and the numbers are filled in page
        order once the document is assembled. Numbering them as they were
        built made the first section on the page read 03.
        """
        return (f'<div class="hd"><span class="no">\u00a7NO\u00a7</span><h2>{title}</h2>'
                f'<span class="rule"></span></div><p class="lede">{lede}</p>')

    # ---- rolling windows, the definitions the menu bar uses ----------------
    today = dt.date.today()

    def window(first_day):
        acc = {"total": 0.0, "calls": 0}
        for day, v in groups["day"].items():
            try:
                d = dt.datetime.strptime(day, "%Y-%m-%d").date()
            except ValueError:
                continue
            if d >= first_day:
                acc["total"] += v["total"]
                acc["calls"] += v["calls"]
        return acc

    wins = [("Today", window(today)),
            ("Last 7 days", window(today - dt.timedelta(days=6))),
            ("Last 30 days", window(today - dt.timedelta(days=29))),
            ("All time", {"total": total, "calls": overall["calls"]})]
    wmax = max((w[1]["total"] for w in wins), default=0) or 1
    win_html = ""
    for i, (name, w) in enumerate(wins):
        win_html += (f'<div class="win"><div style="flex:1"><div class="win-k">{name}</div>'
                     f'<div class="win-bar" style="width:{w["total"] / wmax * 100:.1f}%;'
                     f'transition-delay:{i * 90}ms"></div></div>'
                     f'<div class="win-v">{m(w["total"])}</div>'
                     f'<div class="win-c">{w["calls"]:,}</div></div>')

    # ---- component composition -------------------------------------------
    comp = [("Cache reads", t["cache_read"], overall["cache_read"], "var(--s1)"),
            ("Cache writes", t["cache_write"], overall["cache_write"], "var(--s2)"),
            ("Output", t["output"], overall["output"], "var(--s3)"),
            ("Input, uncached", t["input"], overall["input"], "var(--s4)")]
    stack, legend = "", ""
    for i, (name, tk, cost, col) in enumerate(comp):
        pct = (cost / total * 100) if total else 0
        if pct > 0.15:
            stack += (f'<div class="seg" style="width:{pct:.3f}%;background:{col};'
                      f'transition-delay:{i * 110}ms" title="{name}"></div>')
        legend += (f'<div class="lg"><span class="dot" style="background:{col}"></span>'
                   f'<span class="lg-k">{name}</span><span class="lg-t">{toks(tk)}</span>'
                   f'<span class="lg-v">{m(cost)}</span></div>')

    # ---- caching ----------------------------------------------------------
    prompt_tokens = sum(t[k] for k in ("input", "cache_write", "cache_read"))
    hit = (t["cache_read"] / prompt_tokens * 100) if prompt_tokens else 0
    no_cache = overall["no_cache"]
    saved = no_cache - total
    saved_pct = (saved / no_cache * 100) if no_cache else 0
    multiple = (no_cache / total) if total else 0
    per_m = overall["cache_read"] / max(t["cache_read"], 1) * 1e6

    # ---- tables -----------------------------------------------------------
    def table(key, heading, lede, limit=10, strip="", name_of=None):
        items = sorted(groups[key].items(), key=lambda kv: -kv[1]["total"])[:limit]
        if not items:
            return ""
        peak = max((v["total"] for _, v in items), default=0) or 1
        rows = ""
        for k, v in items:
            name = name_of(k) if name_of else (k.replace(strip, "") if strip else k)
            name = html.escape(name if len(name) < 46 else "\u2026" + name[-44:])
            per_call = v["total"] / v["calls"] if v["calls"] else 0
            rows += (f'<tr><td class="bar-cell">{name}'
                     f'<i style="width:calc({v["total"] / peak * 100:.1f}% - 20px)"></i></td>'
                     f'<td class="n dim mono">{v["calls"]:,}</td>'
                     f'<td class="n dim mono">{m(per_call)}</td>'
                     f'<td class="n">{m(v["total"])}</td></tr>')
        return (f'<section class="fade">{head(heading, lede)}'
                f'<table><thead><tr><th></th><th class="n">Calls</th>'
                f'<th class="n">Per call</th><th class="n">Total</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></section>')

    # ---- sessions ---------------------------------------------------------
    sess = sorted(groups["session"].items(), key=lambda kv: -kv[1]["total"])[:10]
    srows = ""
    speak = max((v["total"] for _, v in sess), default=0) or 1
    for sid, v in sess:
        info = meta.get(sid, {})
        stamp = info.get("last")
        pretty = stamp.astimezone().strftime("%d %b, %H:%M") if stamp else "\u2014"
        proj = html.escape(project_name(info.get("project") or "")[-34:])
        srows += (f'<tr><td class="bar-cell mono">{html.escape(sid[:8])}'
                  f'<i style="width:calc({v["total"] / speak * 100:.1f}% - 20px)"></i></td>'
                  f'<td class="dim">{proj}</td><td class="dim">{pretty}</td>'
                  f'<td class="n dim mono">{v["calls"]:,}</td>'
                  f'<td class="n">{m(v["total"])}</td></tr>')
    sessions_html = ('<section class="fade">'
                     + head("Dearest sessions", "A single session can be a large share of a "
                            "month. These are the ten that cost the most.")
                     + '<table><thead><tr><th>Session</th><th>Project</th><th>Last seen</th>'
                       '<th class="n">Calls</th><th class="n">Total</th></tr></thead>'
                       f'<tbody>{srows}</tbody></table></section>') if srows else ""

    # ---- rhythm -----------------------------------------------------------
    def columns(key, labels, fmt_label):
        vals = [groups[key].get(k, {}).get("total", 0.0) for k in labels]
        peak = max(vals) or 1
        cols = "".join(
            f'<div class="col" style="height:{max(2, v / peak * 100):.1f}%;'
            f'transition-delay:{i * 26}ms" title="{fmt_label(labels[i]) or labels[i]}: '
            f'{money(v)}"></div>' for i, v in enumerate(vals))
        xs = "".join(f'<span>{fmt_label(k)}</span>' for k in labels)
        return f'<div class="cols">{cols}</div><div class="cols-x">{xs}</div>'

    hours = [f"{h:02d}" for h in range(24)]
    wdays = [str(i) for i in range(7)]
    wnames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rhythm = ('<section class="fade">'
              + head("When the work happens",
                     "Local time, all time. Spend rather than calls, so a quiet hour of heavy "
                     "thinking outweighs a busy hour of small ones.")
              + '<div class="rhythm">'
              f'<div><p class="sub-h">By hour</p>'
              f'{columns("hour", hours, lambda h: h if int(h) % 3 == 0 else "")}</div>'
              f'<div><p class="sub-h">By day of week</p>'
              f'{columns("weekday", wdays, lambda d: wnames[int(d)])}</div>'
              '</div></section>')

    # ---- chart payload ----------------------------------------------------
    day_rows = []
    for day, v in days:
        d = dt.datetime.strptime(day, "%Y-%m-%d")
        tk = sum(v["tokens"][k] for k in ("input", "cache_write", "cache_read", "output"))
        day_rows.append({"total": v["total"], "calls": v["calls"], "tokens": tk,
                         "short": d.strftime("%d %b"), "full": d.strftime("%a %d %b %Y"),
                         "tokShort": toks(tk)})

    pills = "".join(
        f'<button data-cur="{c}" class="pill{" on" if c == DISPLAY["code"] else ""}" '
        f'style="animation-delay:{.58 + i * .045:.3f}s">{CURRENCIES[c][0]} {c}</button>'
        for i, c in enumerate(CURRENCIES))

    warn = "".join(
        f'<p class="{"warn" if level == "warn" else ""}">{html.escape(text[:1].upper() + text[1:])}.</p>'
        for level, text in report_notes(groups, unknown))

    payload = json.dumps({
        "rates": rates, "symbols": {c: CURRENCIES[c][0] for c in CURRENCIES},
        "current": DISPLAY["code"], "rateWhen": ("live, " + when) if live else when,
        "days": day_rows,
    })

    avg_call = total / overall["calls"] if overall["calls"] else 0
    avg_day = total / len(days) if days else 0
    busiest = max(days, key=lambda kv: kv[1]["total"]) if days else None

    doc = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Tokenmeter</title>'
        '<style>' + font_faces() + DASH_CSS + '</style></head><body>'
        '<div id="sweep"></div>'

        '<div class="top"><div class="wrap">'
        '<p class="eyebrow">Tokenmeter \u00b7 counterfactual</p>'
        '<h1><span class="ln"><span>What this would have cost</span></span>'
        '<span class="ln"><span><em>at API rates</em></span></span></h1>'
        f'<p class="sub">{html.escape(label)} \u00b7 The same work, priced at '
        'each provider\u2019s published API rates.</p>'
        f'<p class="sub"><code>{html.escape(covered)}</code></p>'
        f'<div class="pills">{pills}</div>'
        '</div></div>'

        '<div class="wrap">'
        '<div class="hero">'
        f'<div class="card lift"><span class="big m" id="headline" data-usd="{total:.8f}" '
        f'data-shown="{total:.8f}">{money(total)}</span>'
        '<div class="big-sub" id="rate-note"></div>'
        '<div class="hero-foot">'
        f'<div class="kpi"><b>{overall["calls"]:,}</b><span>API calls</span></div>'
        f'<div class="kpi"><b>{toks(prompt_tokens)}</b><span>Prompt tokens</span></div>'
        f'<div class="kpi"><b>{toks(t["output"])}</b><span>Output tokens</span></div>'
        f'<div class="kpi"><b>{hit:.1f}%</b><span>From cache</span></div>'
        '</div></div>'
        f'<div class="card lift wins reveal-on">{win_html}</div>'
        '</div>'

        '<section class="fade"><div class="chart-head"><div>'
        + head("Spend over time", "Bars are each day. The line is the running total.")
        + '</div><div class="toggles">'
        '<button class="tg on" data-mode="cost">Cost</button>'
        '<button class="tg" data-mode="tokens">Tokens</button>'
        '</div></div>'
        '<div class="chart" id="chart"><div class="tip" id="tip"></div>'
        '<svg viewBox="0 0 900 268" height="268"></svg></div></section>'

        '<section class="fade">'
        + head("Where the money goes", "Cache reads are the great majority of the tokens and "
               "a minority of the cost, which is the whole argument for caching.")
        + f'<div class="stack">{stack}</div><div class="legend">{legend}</div></section>'

        '<section class="fade">'
        + head("What caching is worth",
               "The same tokens, priced as if none of them had ever been cached.")
        + '<div class="cmp">'
        f'<div class="card"><h3>With cache reads</h3><div class="v">{m(total)}</div>'
        f'<small>What you actually ran. {toks(t["cache_read"])} of those prompt tokens were '
        f'cache hits, at {unit_money(per_m)} per million against full input rates.</small></div>'
        f'<div class="card"><h3>Without cache reads</h3><div class="v">{m(no_cache)}</div>'
        f'<small>The same {toks(prompt_tokens)} prompt tokens billed fresh on every call, at '
        'each model\u2019s own rate.</small></div>'
        f'<div class="card good"><h3>Saved</h3><div class="v">{m_sub(no_cache, total)}</div>'
        f'<small>{saved_pct:.1f}% cheaper. Caching made it {multiple:.1f}x less expensive.'
        '</small></div></div></section>'

        + table("model", "By model", "Cost per call is the honest comparison between models: "
                "a cheap model called often is not a cheap model.", 10, "claude-")
        + table("project", "By project", "Which folders the spend actually went into.", 10,
                name_of=project_name)
        + (table("source", "By harness", "Which tool made the calls. Only shown when more "
                 "than one did.", 10, name_of=lambda k: display_name("source", k))
           if len(groups.get("source", {})) > 1 else "")
        + rhythm
        + sessions_html

        + '<footer>'
        f'<p>{html.escape(covered)}</p>'
        f'<p>Average {money(avg_call)} per call, {money(avg_day)} per active day'
        + (f', busiest was {dt.datetime.strptime(busiest[0], "%Y-%m-%d").strftime("%d %b")} at '
           f'{money(busiest[1]["total"])}' if busiest else '') + '. '
        f'Of {toks(t["output"])} output tokens, {toks(t["thinking"])} were thinking.</p>'
        '<p>Every call is priced at the rate in force on the day it was made. Fraunces and '
        'Inter Tight are embedded under the SIL Open Font License. Tokenmeter is not '
        'affiliated with any provider it prices.</p>'
        + warn + '</footer></div>'

        '<script>' + DASH_JS.replace("__PAYLOAD__", payload) + '</script>'
        '</body></html>')

    parts = doc.split("\u00a7NO\u00a7")
    doc = parts[0] + "".join(f"{i:02d}" + p for i, p in enumerate(parts[1:], 1))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)

def rebuild_ledger(paths) -> None:
    """Rewrite the ledger from the transcripts still on disk.

    The only operation here that can lose history, because anything Claude Code
    has already swept is not in the transcripts to rebuild from. It exists for
    a ledger that has been corrupted, where starting again from what survives
    beats carrying rows nobody trusts. The previous file is kept as .old rather
    than deleted, and the count of unrecoverable rows is printed before it goes.
    """
    path = ledger_path()
    had = read_ledger(path)
    best = scan_transcripts(paths)

    rows = [usage_to_row(mid, ev["when"], ev["model"], ev["project"],
                         ev["session"], ev["_usage"], ev["provider"], ev["source"])
            for mid, ev in best.items()]
    rows.sort(key=lambda r: (r.get("t", ""), r.get("i", "")))
    lost = set(had) - set(best)

    tmp = path + ".new"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n"
                        for r in rows))
    if os.path.exists(path):
        os.replace(path, path + ".old")
    os.replace(tmp, path)

    print()
    print(f"  ledger rebuilt: {len(rows):,} calls from {len(paths):,} transcripts")
    if had:
        print(f"  previous ledger held {len(had):,}, kept at {path}.old")
    if lost:
        print(f"  {YELLOW}{len(lost):,} calls were in the old ledger and in no transcript.{RESET}")
        print(f"  {DIM}They are not in the new one. Restore from .old to get them back.{RESET}")
    print()


def summary() -> dict:
    """Everything the menu bar needs, from a single pass over the logs."""
    paths = transcripts()
    overall, groups, _meta, unknown = collect(paths)

    today = dt.date.today()
    week_start = today - dt.timedelta(days=6)
    month_start = today - dt.timedelta(days=29)

    def window(first_day):
        acc = {c: 0.0 for c in COMPONENTS}
        acc["total"] = 0.0
        acc["calls"] = 0
        for day, v in groups["day"].items():
            try:
                d = dt.datetime.strptime(day, "%Y-%m-%d").date()
            except ValueError:
                continue
            if d >= first_day:
                for c in COMPONENTS:
                    acc[c] += v[c]
                acc["total"] += v["total"]
                acc["calls"] += v["calls"]
        return acc

    t = overall["tokens"]
    prompt_tokens = sum(t[k] for k in ("input", "cache_write", "cache_read"))

    return {
        "today": window(today),
        "week": window(week_start),
        "month": window(month_start),
        "all": {**{c: overall[c] for c in COMPONENTS},
                "total": overall["total"], "calls": overall["calls"]},
        "models": [{"name": k, "total": v["total"], "calls": v["calls"]}
                   for k, v in sorted(groups["model"].items(), key=lambda kv: -kv[1]["total"])],
        "days": [{"day": k, "total": v["total"]} for k, v in sorted(groups["day"].items())][-30:],
        "tokens": t,
        "cache_hit_pct": (t["cache_read"] / prompt_tokens * 100) if prompt_tokens else 0.0,
        "without_cache": overall["no_cache"],
        "currencies": {c: {"symbol": CURRENCIES[c][0], "name": CURRENCIES[c][1]}
                       for c in CURRENCIES},
        # The same order the dashboard's pills use. A JSON object's key order
        # does not survive into Swift, so the order travels as a list.
        "currency_order": list(CURRENCIES),
        "rates": fx_rates()[0],
        "rate_when": fx_rates()[1],
        "rate_live": fx_rates()[2],
        "no_cache_saved": overall["no_cache"] - overall["total"],
        "covered": covered_span(groups, paths),
        "unknown_models": sorted(unknown),
        # What the menu must say beside the figures: verification dates, and
        # any warning (an unverified adapter, a stand-in or looked-up rate).
        "notes": [{"level": level, "text": text} for level, text in report_notes(groups, unknown)],
        "sources": [{"name": k, "label": display_name("source", k),
                     "status": getattr(ALL_SOURCES.get(k), "STATUS", ""), "calls": v["calls"]}
                    for k, v in sorted(groups["source"].items(), key=lambda kv: -kv[1]["total"])],
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
    }


def fetch_text(url: str, timeout: int = 20) -> str:
    """One page, as text. Only --check-prices uses this."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": f"tokenmeter/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def md_tables(text: str) -> list:
    """Every markdown table in a page, as (nearest heading, header, rows)."""
    out, title, header, rows = [], "", None, []
    for line in text.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s[1:-1].split("|")]
            if header is None:
                header = cells
            elif not all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                rows.append(cells)
            continue
        if header is not None:
            out.append((title, header, rows))
            header, rows = None, []
        if s.startswith("#"):
            title = s.lstrip("#").strip()
    return out


def expected_rates(row: dict, table) -> dict:
    """What a table row implies the pricing page should say, per field."""
    inp = row["in"]
    exp = {"in": inp, "out": row["out"], "cached": inp * row["cache_read_mult"],
           "write_5m": inp * row.get("write_mult", table.CACHE_WRITE_5M_MULT),
           "write_1h": inp * row.get("write_1h_mult", row.get("write_mult", table.CACHE_WRITE_1H_MULT))}
    exp["write"] = exp["write_5m"]
    if row["fast"]:
        exp["fast_in"], exp["fast_out"] = row["fast"]
    long = row.get("long")
    if long:
        exp["long_in"] = inp * long["in"]
        exp["long_out"] = row["out"] * long["out"]
    return exp


def check_prices(fetch=None) -> int:
    """Compare every table with its provider's live pricing page.

    Reports, never edits: a difference is for a person to read, date and
    record as a new entry, because a rate change is history and not a typo.
    Returns 0 when everything matches, 1 on any difference or unlisted model,
    2 when a page could not be read at all.
    """
    fetch = fetch or fetch_text
    worst = 0
    print()
    print(f"  {BOLD}Checking price tables against the published pages{RESET}")
    for provider, table in TABLES.items():
        print()
        print(f"  {BOLD}{table.NAME}{RESET}  {DIM}{table.SOURCE}{RESET}")
        try:
            page, unlisted = table.page_rates(fetch, md_tables)
        except Exception as e:  # no network, a moved page, a changed layout
            print(f"    {YELLOW}could not read the page{RESET} ({e.__class__.__name__}: {e}).")
            print(f"    {DIM}Nothing was changed. Check by hand at {table.SOURCE}{RESET}")
            worst = max(worst, 2)
            continue
        if not page:
            print(f"    {YELLOW}the page was read but no rates were found in it{RESET}; "
                  f"its layout may have changed. Check by hand.")
            worst = max(worst, 2)
            continue
        matched, diffs, absent = 0, [], []
        for model, rows in table.PRICES.items():
            got = page.get(model)
            if not got:
                absent.append(model)
                continue
            # A page that states dated prices (one rate through a date, a
            # higher one after) is checked entry by entry against the table's
            # own dated entries; otherwise the newest entry must match.
            checks = [(rows[-1], {k: v for k, v in got.items() if k != "_history"}, "")]
            for h in got.get("_history", []):
                row = next((r for r in rows if r["from"] == h["from"]), None)
                label = f" from {h['from'] or 'launch'}"
                if row is None:
                    diffs.append((model + label, "entry", None, h.get("in") or 0))
                    continue
                checks.append((row, {k: v for k, v in h.items() if k != "from"}, label))
            bad = False
            for row, fields, label in checks:
                exp = expected_rates(row, table)
                for field, value in sorted(fields.items()):
                    if value is None:
                        continue
                    want = exp.get(field)
                    if want is None or abs(want - value) > 1e-9 * max(1.0, abs(value)):
                        diffs.append((model + label, field, want, value))
                        bad = True
            matched += not bad
        print(f"    {GREEN}{matched} of {len(table.PRICES)} models match{RESET} "
              f"the page in every column it lists")
        for model, field, want, value in diffs:
            have = "nothing" if want is None else f"${want:g}"
            print(f"    {YELLOW}differs{RESET}  {model} {field}: table has {have}, "
                  f"page says ${value:g}")
        if absent:
            print(f"    {DIM}not found on the page: {', '.join(absent)}{RESET}")
        if unlisted:
            print(f"    {YELLOW}on the page but not in the table{RESET}: {', '.join(unlisted)}")
        if diffs or unlisted:
            worst = max(worst, 1)
    print()
    if worst == 0:
        print(f"  {DIM}Everything matches. The tables were not touched.{RESET}")
    else:
        print(f"  {DIM}Nothing was changed. A rate change is added as a new dated entry "
              f"under pricing/, never by editing the old one.{RESET}")
    print()
    return worst


def price_listing(markdown: bool = False) -> str:
    """Every model in every table, with its rates and how they were checked.

    The same text is docs/prices.md, and a test fails if the two differ, so
    the published list can never drift from the tables that do the pricing.
    """
    def fmt(x):
        if x is None:
            return "-"
        text = f"{x:.6f}".rstrip("0").rstrip(".")
        if "." in text and len(text.split(".")[1]) == 1:
            text += "0"
        return "$" + text

    out = []
    if markdown:
        out += ["# Supported models and prices", "",
                "Every model Tokenmeter has a checked price for, generated from the tables in",
                "`pricing/` by `python3 tokenmeter.py --list-prices --markdown`. US dollars per",
                "million tokens, standard tier. A model not listed here is still priced, by the",
                "online lookup at startup, and labelled as looked up rather than checked.", ""]
    for provider, table in TABLES.items():
        v = verification(provider)
        how = ("checked against the published page and against real usage" if v["measured"]
               else "checked against the published page; not yet against a real bill")
        if markdown:
            out += [f"## {table.NAME}", "",
                    f"Source: <{table.SOURCE}>. Last verified {v['pretty']}, {how}.", "",
                    "| Model | Input | Cached input | Cache write | Output | Also |",
                    "|---|---:|---:|---:|---:|---|"]
        else:
            out += ["", f"  {BOLD}{table.NAME}{RESET}  {DIM}verified {v['pretty']}, {how}{RESET}"]
        for model, rows in table.PRICES.items():
            for row in rows:
                inp = row["in"]
                cached = inp * row["cache_read_mult"]
                write = inp * row.get("write_mult", table.CACHE_WRITE_5M_MULT)
                w1 = inp * row.get("write_1h_mult", row.get("write_mult", table.CACHE_WRITE_1H_MULT))
                also = []
                if row["from"]:
                    also.append(f"from {row['from']}")
                elif len(rows) > 1:
                    also.append(f"until {rows[rows.index(row) + 1]['from']}")
                if abs(w1 - write) > 1e-12:
                    also.append(f"1-hour cache write {fmt(w1)}")
                if row.get("long"):
                    lg = row["long"]
                    over = lg["over"] + (1 if lg["over"] % 1000 == 999 else 0)
                    also.append(f"over {over // 1000}K prompt tokens: input x{lg['in']:g}, output x{lg['out']:g}")
                if row["fast"]:
                    also.append(f"fast {fmt(row['fast'][0])} / {fmt(row['fast'][1])}")
                if row.get("off_peak"):
                    also.append("half price off-peak")
                aliases = sorted(a for a, m in getattr(table, "ALIASES", {}).items() if m == model)
                if aliases:
                    also.append("also " + ", ".join(aliases[:3]) + (f" and {len(aliases) - 3} more" if len(aliases) > 3 else ""))
                # "-" where the provider charges nothing separate: no cache
                # discount, or no fee for writing the cache beyond input.
                bills_writes = (abs(write - inp) > 1e-12 or "write_1h_mult" in row) and inp > 0
                discounted = row["cache_read_mult"] != 1.0 or inp == 0
                cells = [model, fmt(inp), fmt(cached) if discounted else "-",
                         fmt(write) if bills_writes else "-", fmt(row["out"]), "; ".join(also)]
                if markdown:
                    out.append("| " + " | ".join(f"`{c}`" if i == 0 else c for i, c in enumerate(cells)) + " |")
                else:
                    out.append(f"    {model:<30}{cells[1]:>9} in {cells[2]:>9} cached {cells[4]:>9} out"
                               + (f"  {DIM}{'; '.join(also)}{RESET}" if also else ""))
        if markdown:
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def tilde(path: str) -> str:
    """A path with the home folder written as ~, for anything printed.
    Shorter, and a screenshot of it does not carry a username."""
    home = os.path.expanduser("~").rstrip(os.sep)
    if path == home or path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def nothing_found() -> str:
    """Where the tool looked, for a run that found nothing to price."""
    lines = ["nothing to price. Looked for:"]
    for name, a in ADAPTERS.items():
        for root in adapter_roots(name):
            lines.append(f"  {a.LABEL} {a.FILES} in {tilde(root)}")
    lines.append("Another harness? Write its calls in the import format and pass "
                 "--import FILE (see docs/import-format.md).")
    return "\n".join(lines)


def list_adapters() -> None:
    """Every source, what it found on this machine, and how far to trust it."""
    status_words = {"verified": f"{GREEN}verified{RESET}  ",
                    "unverified": f"{YELLOW}unverified{RESET}",
                    "yours": f"{CYAN}your data{RESET} "}
    print()
    print(f"  {BOLD}Adapters{RESET}")
    for name, a in ADAPTERS.items():
        roots = adapter_roots(name)
        found = a.files(roots) if any(os.path.isdir(r) for r in roots) else []
        where = ", ".join(tilde(r) for r in roots)
        state = (f"{len(found):,} {a.FILES} in {where}" if found
                 else f"{DIM}nothing found in {where}{RESET}")
        print(f"    {name:<13}{status_words.get(a.STATUS, a.STATUS)}  {state}")
    print(f"    {importer.NAME:<13}{status_words['yours']}  "
          f"{DIM}--import FILE, any harness (docs/import-format.md){RESET}")
    unverified = [a.LABEL for a in ADAPTERS.values() if a.STATUS == "unverified"]
    if unverified:
        import textwrap
        print()
        for line in textwrap.wrap(f"{', '.join(unverified)}: {UNVERIFIED_NOTE}", 88):
            print(f"  {DIM}{line}{RESET}")
    print()
    print(f"  {BOLD}Price tables{RESET}")
    for provider in TABLES:
        v = verification(provider)
        how = "checked against real usage" if v["measured"] else "published rates only"
        flag = f"  {YELLOW}over {STALE_DAYS} days old{RESET}" if v["stale"] else ""
        print(f"    {v['name']:<13}{len(TABLES[provider].PRICES):>3} models, "
              f"verified {v['pretty']}, {how}{flag}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="tokenmeter",
        description="What your AI coding would have cost at API rates.")
    ap.add_argument("--version", action="version", version=f"tokenmeter {__version__}")
    ap.add_argument("--since", default="", help="rolling window: 24h, 7d, 30d, 2w or 2026-09-01")
    ap.add_argument("--until", default="", help="stop at this date, for a closed range")
    ap.add_argument("--period", default="", metavar="NAME",
                    help="calendar period: today, yesterday, week, lastweek, "
                         "month, lastmonth, year")
    ap.add_argument("--session", default="", help="session id or transcript path")
    ap.add_argument("--project", default="", help="substring of the project folder")
    ap.add_argument("--ledger", default="", metavar="FILE",
                    help=f"ledger file (default {DEFAULT_LEDGER}, or set {LEDGER_ENV})")
    ap.add_argument("--current-rates", action="store_true",
                    help="price the whole history at today's rates instead of "
                         "the rates in force at the time")
    ap.add_argument("--no-ledger", action="store_true",
                    help="price only the transcripts; do not read or write the ledger")
    ap.add_argument("--rebuild-ledger", action="store_true",
                    help="rewrite the ledger from the transcripts on disk")
    ap.add_argument("--projects-dir", action="append", default=[], metavar="DIR",
                    help="a Claude Code projects folder to read; repeat to combine "
                         f"machines (or set {PROJECTS_ENV}, colon separated)")
    ap.add_argument("--import", dest="imports", action="append", default=[], metavar="FILE",
                    help="price events in the import format (docs/import-format.md), "
                         "from any harness; - reads standard input; repeatable")
    ap.add_argument("--adapter", action="append", default=[], metavar="NAME",
                    choices=sorted(ALL_SOURCES),
                    help="read only this source; repeatable. Default: every adapter "
                         "whose folders exist, plus any --import")
    ap.add_argument("--list-adapters", action="store_true",
                    help="show each adapter, what it found, and how far to trust it")
    ap.add_argument("--list-prices", action="store_true",
                    help="every model with a checked price, and its rates")
    ap.add_argument("--markdown", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--offline", action="store_true",
                    help="never look prices up online; unknown models get a flagged "
                         f"stand-in rate (or set {OFFLINE_ENV}=1)")
    ap.add_argument("--check-prices", action="store_true",
                    help="fetch each provider's pricing page and report any difference "
                         "from the tables; changes nothing")
    ap.add_argument("--by", choices=["project", "model", "day", "session",
                                     "hour", "weekday", "source", "provider"], default="")
    ap.add_argument("--sessions", action="store_true", help="list the dearest sessions")
    ap.add_argument("--html", nargs="?", const="auto", default="",
                    help="write the dashboard and open it")
    ap.add_argument("--currency", default=DEFAULT_CURRENCY,
                    help=f"display currency: {', '.join(CURRENCIES)} (default {DEFAULT_CURRENCY})")
    ap.add_argument("--json", action="store_true", help="machine readable")
    ap.add_argument("--summary-json", action="store_true",
                    help="today, week and all time plus a model split, in one scan")
    args = ap.parse_args()
    if args.current_rates:
        CURRENT_RATES.append(True)
    if args.ledger:
        _LEDGER[:] = [os.path.expanduser(args.ledger)]
    if args.projects_dir:
        _ROOTS[:] = [os.path.expanduser(p) for p in args.projects_dir]
        missing = [p for p in _ROOTS if not os.path.isdir(p)]
        if missing:
            sys.exit("not a folder: " + ", ".join(missing))
    for f in args.imports:
        f = f if f == "-" else os.path.expanduser(f)
        if f != "-" and not os.path.isfile(f):
            sys.exit(f"not a file: {f}")
        _IMPORTS.append(f)
    _ONLY[:] = args.adapter
    if args.offline:
        ONLINE_LOOKUP[0] = False

    if args.list_adapters:
        list_adapters()
        return
    if args.list_prices:
        sys.stdout.write(price_listing(markdown=args.markdown))
        return
    if args.check_prices:
        sys.exit(check_prices())

    set_currency(args.currency)

    if args.summary_json:
        print(json.dumps(summary()))
        return

    if args.session:
        if os.path.isfile(args.session):
            paths = [args.session]
            _SESSION[:] = [os.path.basename(args.session).split(".")[0]]
        else:
            paths = transcripts(session=args.session)
            _SESSION[:] = [args.session]
            if not paths and not any(str(r.get("c", "")).startswith(args.session)
                                     for r in read_ledger().values()):
                sys.exit(f"no transcript found for session {args.session}")
    else:
        paths = transcripts(project=args.project)
        _PROJECT[:] = [args.project] if args.project else []
    if not paths and (args.no_ledger or not read_ledger()):
        sys.exit(nothing_found())

    if args.rebuild_ledger:
        rebuild_ledger(paths)
        return

    until = None
    if args.period:
        if args.since or args.until:
            sys.exit("--period sets both ends; do not pass --since or --until with it")
        since, until = period_range(args.period)
    else:
        since = parse_since(args.since)
        until = parse_since(args.until) if args.until else None
    overall, groups, meta, unknown = collect(paths, since, ledger=not args.no_ledger,
                                             until=until)
    if not overall["calls"] and not paths and not (args.since or args.until or args.period):
        sys.exit(nothing_found())

    if args.period:
        label = period_label(args.period)
    elif args.since and args.until:
        label = f"{args.since} to {args.until}"
    elif args.since:
        label = f"last {args.since}"
    elif args.session:
        label = f"session {args.session[:8]}"
    else:
        label = "all time"
    if args.project:
        label += f" · {args.project}"
    if args.current_rates:
        label += " · at today's rates"

    if args.json:
        print(json.dumps({
            "total_usd": round(overall["total"], 6),
            "total_display": round(overall["total"] * DISPLAY["rate"], 6),
            "currency": DISPLAY["code"],
            "calls": overall["calls"],
            "components": {c: round(overall[c], 6) for c in COMPONENTS},
            "tokens": overall["tokens"],
            "label": label,
        }))
        return

    if args.html:
        out = args.html
        if out == "auto":
            out = os.path.expanduser("~/Downloads/Tokenmeter.html")
        render_html(overall, groups, meta, unknown, label, out,
                    covered=covered_span(groups, paths))
        print(f"wrote {out}")
        # macOS. The one line a Linux port would change, to xdg-open.
        subprocess.run(["open", out], check=False)
        return

    print_report(overall, groups, meta, unknown, args.by, label, args.sessions,
                 covered=covered_span(groups, paths))


if __name__ == "__main__":
    main()
