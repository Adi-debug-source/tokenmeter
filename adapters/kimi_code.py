"""Kimi Code sessions. Unverified.

Built from the published source of MoonshotAI/kimi-code (read at commit
a2afdbc, 30 October 2026; rechecked at fc3b521, 2 November 2026, where the
files cited below had not changed except two, whose lines are given at
both), with MoonshotAI/kimi-cli, the older Python harness it replaces, read
at commit 9ab1286, 22 September 2026. It has not yet been run against real
session files, so every report that uses it says so. If a figure looks
wrong, please open an issue with a sample. Paths below are under
packages/agent-core-v2/src/ unless they name another package.

What Kimi Code writes, and what this reader does with it:

  - Sessions live in $KIMI_CODE_HOME/sessions/<workspace>/<session>/, and
    KIMI_CODE_HOME defaults to ~/.kimi-code (resolveKimiHome(),
    app/bootstrap/bootstrap.ts).
  - Each agent has its own agents/<agent>/wire.jsonl: "main", and "agent-0"
    and so on for subagents, whose calls are marked as a subagent's. Every
    agent of a session, however it was started, is one folder under the
    session's agents/ (session/agentLifecycle/agentLifecycleService.ts:254,
    with ids from nextAvailableAgentId() at 183-196, which never holds a
    slash; subagents are created without an id at session/subagent/
    subagentService.ts:163 and features/tower/tools/spawn/spawnTool.ts:408),
    and a fork writes the same place (workspace/sessionLifecycle/internal/
    addressing.ts:15-17). Nothing in Kimi Code writes a wire.jsonl beside
    the session's state.json, nor a usage.record deeper under agents/: the
    export scan and the search index that look in both places
    (app/sessionExport/wire-scan.ts:45-62, packages/kap-server/src/search/
    indexCore.ts:1378-1395) only read, and the migration from kimi-cli,
    which writes agents/<id>/ with ids it carries over, writes no usage
    (below). So agents/*/wire.jsonl is every file that holds calls, and
    only it is read. The
    session's state.json records its working folder ("cwd").
  - wire.jsonl is append-only JSON lines, each {"type", ...payload, "time"}
    with time in milliseconds since the epoch (Event2.serialize() in
    src/app/event/event2.ts). After every successful API call the requester
    (src/agent/loop/requester.ts) writes one "usage.record" carrying that
    call's own usage: never a turn or session total. Its usageScope says
    only whether a turn or the session (compaction) made the call. A call
    whose provider sent no usage is written with every count zero, and is
    skipped here. llm.request and usage.record go through one queue per
    agent (src/state/eventDispatcherService.ts) into the same file, so a
    call's request is always above its usage.
  - The counts are already split: inputOther is uncached input, then
    inputCacheRead, inputCacheCreation and output. Kimi Code takes the
    cached count out of OpenAI-style prompt_tokens itself (Moonshot's
    convention, prompt including cached), so inputOther is the engine's
    input as it stands. Output includes any thinking; no split is recorded.
    Kimi Code marks Anthropic-style prompts {"type": "ephemeral"} with no
    lifetime, so a cache write is a 5-minute one.
  - usage.record's "model" is the configured alias (kimi-code/k3), not the
    model the API was asked for. Every attempt first writes an
    "llm.request" with the alias, the model as sent ("model": "k3", the
    name the request carries, protocolAdapterRegistry.ts), the wire
    protocol ("provider": "openai", "anthropic", "openai_responses" or
    "google-genai") and its kind ("loop" for a turn's step, "compaction").
    Nothing links the two records but their order, so the pairing rests on
    this: one agent has at most one step in flight, and at most one
    compaction, which may run beside a step (an automatic compaction is
    started before or after a step without waiting). A step's usage.record
    says usageScope "turn" and a compaction's "session", so a call takes
    the latest llm.request of the same agent, alias and kind, and uses it
    up: a retry writes a new request over the failed one, and no request
    serves two calls. A model changed mid session is followed call by
    call. A usage.record with no such request is not counted, and the
    report says how many.
  - A step made with no turn active would be the one exception: its usage
    says "session" (session/usage/usageAgentModel.ts:34-36) but its request
    "loop" (requestKindForRecord(), agent/loop/requester.ts:833-837 at
    a2afdbc, 941-945 at fc3b521), as the loop gives no source then
    (agent/loop/loopService.ts:241-248 at a2afdbc, 242-249 at fc3b521). It
    does not happen: the loop's gate refuses a step when no turn is active
    (loopService.ts:1031-1032 at a2afdbc, 1042-1043 at fc3b521), the source
    is read straight after the gate passes (agent/loop/machine/requester.ts:
    60-82), and a turn is only ended while a step is in flight by
    cancelling it first, which aborts the step's request before it records
    any usage. The only other caller is full compaction, whose source says
    "full_compaction" (agent/fullCompaction/fullCompactionService.ts:
    665-670). Were it to happen, the call would find no compaction request
    and be left out, and the report would say so.
  - The protocol is not the vendor: Kimi's own models are reached over the
    OpenAI and Anthropic protocols. The price table is chosen from the
    model's family (PROVIDERS below); a model of no known family is given
    the provider "unknown", which no table prices.
  - Over the OpenAI protocol Kimi Code takes cached input from
    "cached_tokens" or "prompt_tokens_details.cached_tokens" only, and
    never records a cache write (openai/decode.ts). Those are Moonshot's
    and OpenAI's fields; another vendor reached that way could have its
    cached input recorded as uncached (DeepSeek's is prompt_cache_hit_tokens,
    as OpenCode's openai-chat.ts notes), so such calls are not counted, and
    the report says how many.
  - Over the Google protocol Kimi Code records candidatesTokenCount alone
    as output, without the thinking tokens Google bills as output, so those
    calls are not counted, and the report says how many.
  - A fork copies every record of the session it forks, times included,
    and a resumed session appends to the same files. The key is the agent,
    time, alias and counts, the same in every copy, so a forked call counts
    once. An undo appends branch records and removes nothing
    (src/wire/wireService.ts), and the undone calls were made, so they
    count. A subagent's total on subagent.completed in its parent's file is
    a sum of calls already in its own file, and is not read.
  - Kimi Code drives no other harness's binary. Its import from Claude
    Code and Codex (a built-in skill) brings instructions, skills and MCP
    settings, never sessions, and its migration from kimi-cli
    (packages/migration-legacy) writes messages only, never a
    usage.record, so nothing is counted twice.
  - kimi-cli (~/.kimi, or KIMI_SHARE_DIR) is not read. Its wire.jsonl
    records each step's usage on StatusUpdate, but not the model of the
    call (a subagent's meta.json names a configured alias, and only when
    one was chosen for it), and not the compaction calls at all, so its
    calls cannot be priced exactly.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
import re

from .claude_code import project_matches
from .common import usage, whole

NAME = "kimi-code"
LABEL = "Kimi Code"
STATUS = "unverified"
FILES = "sessions"
FILE = "session"

MAIN_AGENT = "main"

# Price tables by model family. Kimi Code records the wire protocol, never the
# vendor, and the protocol cannot say it: Kimi's own models are reached over
# the OpenAI and Anthropic protocols. The family of the model as sent can.
PROVIDERS = (
    (re.compile(r"^(kimi-|moonshot-|k\d+(\.\d+)?($|-))"), "moonshot"),
    (re.compile(r"^claude-"), "anthropic"),
    (re.compile(r"^(gpt-|chatgpt-|codex-|o\d+($|-))"), "openai"),
    (re.compile(r"^gemini-"), "google"),
    (re.compile(r"^deepseek-"), "deepseek"),
    (re.compile(r"^grok-"), "xai"),
    (re.compile(r"^glm-"), "zai"),
    (re.compile(r"^(mistral|devstral|codestral|magistral|ministral)"), "mistral"),
)
UNKNOWN_PROVIDER = "unknown"

# The protocol whose recorded output leaves out thinking (see the docstring).
OUTPUT_WITHOUT_THINKING = {"google-genai"}

# Over the OpenAI protocol, the families whose cached input Kimi Code reads
# (see the docstring).
OPENAI_PROTOCOL = "openai"
OPENAI_PROTOCOL_FAMILIES = {"moonshot", "openai"}

# usage.record's usageScope -> the kind of the llm.request that made it
# (usageAgentModel.ts record(), requester.ts requestKindForRecord()).
KIND_OF_SCOPE = {"turn": "loop", "session": "compaction"}

# Per run: the keys of calls left out, so a call read from a fork counts once.
_STATE = {"no_model": set(), "no_thinking": set(), "cache_unread": set()}


def default_roots() -> list:
    home = os.environ.get("KIMI_CODE_HOME", "").strip() or "~/.kimi-code"
    return [os.path.join(os.path.expanduser(home), "sessions")]


def _session_dir(path: str) -> str:
    """<root>/<workspace>/<session>/agents/<agent>/wire.jsonl -> the session folder."""
    parts = path.split(os.sep)
    if "agents" in parts[:-1]:
        return os.sep.join(parts[:parts.index("agents")])
    return os.path.dirname(path)


def _state(session_dir: str) -> dict:
    try:
        with open(os.path.join(session_dir, "state.json"), encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def files(roots: list, project: str = "", session: str = "") -> list:
    paths = []
    for root in roots:
        paths.extend(glob.glob(os.path.join(root, "*", "*", "agents", "*", "wire.jsonl")))
    if session:
        paths = [p for p in paths if session in os.path.basename(_session_dir(p))]
    if project:
        keep = []
        for p in paths:
            cwd = _state(_session_dir(p)).get("cwd")
            if not isinstance(cwd, str) or not cwd or project_matches(project, cwd):
                keep.append(p)
        paths = keep
    return sorted(set(paths))


def looks_like(line: str) -> bool:
    flat = line.replace(" ", "")
    if '"type":"usage.record"' in flat:
        return '"usage":{' in flat and '"inputOther"' in flat
    if '"type":"llm.request"' in flat:
        return '"systemPromptHash"' in flat and '"toolsHash"' in flat
    if '"type":"metadata"' in flat and '"created_at"' in flat:
        try:
            obj = json.loads(line)
        except ValueError:
            return False
        return isinstance(obj, dict) and set(obj) == {"type", "protocol_version", "created_at"}
    return False


def notes() -> list:
    """What the report must say about this run's Kimi Code figures."""
    out = []
    n = len(_STATE["no_model"])
    if n:
        out.append(f"{n:,} Kimi Code call{'' if n == 1 else 's'} had no model recorded "
                   f"before {'it' if n == 1 else 'them'} and {'was' if n == 1 else 'were'} "
                   "not counted")
    n = len(_STATE["cache_unread"])
    if n:
        out.append(f"{n:,} Kimi Code call{'' if n == 1 else 's'} over the OpenAI protocol to a "
                   f"model outside Moonshot's and OpenAI's families {'was' if n == 1 else 'were'} "
                   "not counted: Kimi Code reads cached input only from the fields those two "
                   f"use, so {'its' if n == 1 else 'their'} cached tokens could read as uncached")
    n = len(_STATE["no_thinking"])
    if n:
        out.append(f"{n:,} Kimi Code call{'' if n == 1 else 's'} to a Gemini model "
                   f"{'was' if n == 1 else 'were'} not counted: Kimi Code records "
                   f"{'its' if n == 1 else 'their'} output without the thinking tokens "
                   "Google bills")
    return out


def reset() -> None:
    _STATE.update(no_model=set(), no_thinking=set(), cache_unread=set())


def provider_for(model: str) -> str:
    """The price table for a model as Kimi Code sent it."""
    m = model.lower()
    for pattern, provider in PROVIDERS:
        if pattern.search(m):
            return provider
    return UNKNOWN_PROVIDER


def _lines(path: str):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue       # a line still being written
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def _when(ms):
    if isinstance(ms, bool) or not isinstance(ms, (int, float)):
        return None
    if not math.isfinite(ms) or ms <= 0:
        return None
    try:
        return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _cwd_of(rec: dict) -> str:
    """The working folder a config.update or profile.bind names."""
    disclosure = rec.get("environmentDisclosure")
    if isinstance(disclosure, dict) and isinstance(disclosure.get("cwd"), str):
        return disclosure["cwd"]
    return ""


def records(path: str):
    session_dir = _session_dir(path)
    session = os.path.basename(session_dir)
    state = _state(session_dir)
    cwd = state.get("cwd") if isinstance(state.get("cwd"), str) else ""
    file_agent = os.path.basename(os.path.dirname(path))
    if file_agent == session:
        file_agent = MAIN_AGENT
    requests = {}          # (agent, alias, kind) -> the request not yet used
    done = {}              # key -> its event (None if left out), for a repeated line
    for rec in _lines(path):
        kind = rec.get("type")
        agent = rec.get("agentId") if isinstance(rec.get("agentId"), str) else file_agent
        if kind in ("config.update", "profile.bind") and not cwd:
            cwd = _cwd_of(rec)
            continue
        if kind == "llm.request":
            alias = rec.get("modelAlias")
            if isinstance(alias, str) and isinstance(rec.get("model"), str):
                requests[(agent, alias, rec.get("kind"))] = rec
            continue
        if kind != "usage.record" or not isinstance(rec.get("usage"), dict):
            continue
        u = rec["usage"]
        other, read, write, out = (whole(u.get(k)) for k in
                                   ("inputOther", "inputCacheRead", "inputCacheCreation", "output"))
        if not any((other, read, write, out)):
            continue       # the provider sent no usage
        when = _when(rec.get("time"))
        alias = rec.get("model") if isinstance(rec.get("model"), str) else ""
        if when is None:
            continue       # a partial record
        key = f"{NAME}:{agent}:{rec.get('time')}:{alias}:{other}:{read}:{write}:{out}"
        if key in done:    # the same record again: its request is already used
            if done[key] is not None:
                yield key, done[key]
            continue
        done[key] = None
        req = requests.pop((agent, alias, KIND_OF_SCOPE.get(rec.get("usageScope"))), None)
        if req is None or not req["model"]:
            _STATE["no_model"].add(key)
            continue
        provider = provider_for(req["model"])
        if req.get("provider") in OUTPUT_WITHOUT_THINKING:
            _STATE["no_thinking"].add(key)
            continue
        if req.get("provider") == OPENAI_PROTOCOL and provider not in OPENAI_PROTOCOL_FAMILIES:
            _STATE["cache_unread"].add(key)
            continue
        project = cwd or os.path.basename(os.path.dirname(session_dir))
        done[key] = {
            "when": when,
            "model": req["model"],
            "provider": provider,
            "project": project,
            "session": session,
            "cwd": project,
            "sidechain": agent != MAIN_AGENT,
            "source": NAME,
            "_usage": usage(input=other, output=out, cache_read=read, cache_write_5m=write),
        }
        yield key, done[key]
