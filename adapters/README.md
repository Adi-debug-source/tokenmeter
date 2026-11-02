# Writing an adapter

An adapter teaches Tokenmeter to read one harness's logs. It does one thing:
say what each API call was. The engine does everything else (de-duplication,
the ledger, pricing, windows, every report), which keeps the arithmetic in one
place. An adapter never prices anything.

Before writing one, ask whether the importer is enough. If the harness can
export per-call token counts, a ten-line script that emits the
[import format](../docs/import-format.md) works today and cannot misread a log.
An adapter earns its place when the logs are already on disk and people would
otherwise have to convert them by hand every time.

## The contract

A module in this folder, added to `ADAPTERS` in `__init__.py`, with:

| Name | What it is |
|---|---|
| `NAME` | Short id: `codex`. Used by `--adapter` and stored in the ledger. |
| `LABEL` | How reports name it: `Codex`. |
| `STATUS` | `"verified"` or `"unverified"`. See the rule below. |
| `FILES` | What it reads, in words: `sessions`. |
| `FILE` | The same for one of them: `session`. Reports say "1 Codex session". |
| `default_roots()` | The folders it reads, honouring the harness's own environment variables. |
| `files(roots, project="", session="")` | The log files under those folders, narrowed by `project` and `session` where the files say enough (match a project with `claude_code.project_matches()`). The engine filters every call again, so reading too many is safe and too few is not. |
| `looks_like(line)` | Whether one line of an unknown file is in this format. Claude Code's, the loosest, is tried after every other, so keep yours strict. |
| `records(path)` | Yield `(key, event)` for every API call in one file. |
| `notes()` *(optional)* | Sentences every report must print about this run's figures. |
| `reset()` *(optional)* | Clear per-run state before a scan. |

Each event is a dict:

```python
{
    "when": datetime,        # aware; adapters.common.parse_time() handles ISO 8601
    "model": "gpt-6-sol",    # exactly as the API names it
    "provider": "openai",    # which table in pricing/ prices it
    "project": "/Users/sam/code/app",
    "session": "abc123",
    "cwd": "/Users/sam/code/app",
    "sidechain": False,      # True for a subagent's call
    "source": NAME,
    "_usage": adapters.common.usage(input=..., output=..., cache_read=..., ...),
}
```

`usage()` takes the normalised counts: `input` is uncached input only, never
including cache reads or writes; `output` includes any reasoning; `thinking`
says how much of `output` was reasoning. Every harness reports these
differently, and translating them correctly is most of an adapter's job. The
table in [docs/import-format.md](../docs/import-format.md) shows the usual
conversions. Read each count with `adapters.common.whole()`, which keeps an
int or a float and reads anything else (a bool, a string, `Infinity`, `NaN`)
as 0, so one odd value in a log cannot end the run. The counts are also the
report's total tokens (uncached input, cache writes, cache reads and output,
with `thinking` never added again), so a count in the wrong field moves the
total as well as the price.

## De-duplication

`key` must identify the API call itself, not the log line. Harnesses write the
same call more than once (once per streamed block, again on resume, again when
a message is edited), and the engine keeps one copy per key: the earliest
sighting's time, session and project (on a tie, the copy in the file whose
last call comes first, which for a resume is the session it copied; then the
copy whose project and session sort first, so the order files are read in
never decides), and the largest usage block. So:

- Use the provider's response id when the log has one.
- Otherwise build a key that is the same wherever the same call appears, and
  prefix it with your adapter's name so it cannot collide with another's.
- Yield every sighting and let the engine choose. Do not filter duplicates
  yourself unless the format needs it (Codex re-sends a running total, so its
  adapter counts only when the total moves).

## The rule for "verified"

An adapter ships as `unverified` until someone has run it against real logs
and checked its figures against an independent number: the harness's own cost
report, the provider's billing page for the same period, or a hand count.
Every report that uses an unverified adapter prints a note saying so.

To promote one:

1. Capture a real sample: one session file, with any content you would not
   share removed but every usage field untouched.
2. Add it under `tests/fixtures/<adapter>/` with an `expected.json` of the
   per-call figures you checked independently, and a test that reads it.
3. Say in the pull request what you compared against and how close it was.
4. Change `STATUS` to `"verified"`.

## Testing

Build fixtures from the harness's source: every field name and nesting exactly
as the source writes it, with invented content. Cover the traps the format
has: repeated lines, partial records, a record with no usage, a model change
mid-session. The existing fixtures under `tests/fixtures/` show the pattern,
and `tests/test_adapters.py` has a class per adapter.

Run `python3 tests/test_tokenmeter.py` before and after. The Claude Code
figures must not move by a single token.

## Model id spellings

Each reader records the model id exactly as its harness wrote it; the engine's
name translation maps host and harness spellings to the maker's ids. What each one sees:

- **Claude Code:** the id the API returned, `claude-sonnet-4-5`.
- **Codex:** OpenAI's slug from `turn_context`, `gpt-6.1-sol`, and other slugs such as `codex-auto-review`.
- **Gemini CLI:** the bare resolved Google id, `gemini-3.1-pro-preview` (aliases such as `auto` are resolved before recording).
- **OpenCode:** the model id beside its provider id, `claude-sonnet-4-5` through `anthropic`, `gpt-5.2-codex` through `openai`.
- **Kimi Code:** the model as sent in `llm.request`, never the alias (`kimi-code/k3`): for example `k3`, or whatever a custom provider is configured with (`claude-sonnet-4-6`). Kimi's own names come from a server catalogue, so the source does not list them.
- **DeepSeek Harness:** the model as requested, beside its route: `deepseek-flash` or `deepseek-v4-pro` through `deepseek-official` or `deepseek-account`, and pi-ai routes' own ids such as `claude-sonnet-4-5` through `anthropic`.

## Harnesses without a reader

A reader ships only when every call it counts is exact: per API call, or
provably equal to the per-call figures. These harnesses were read on 1
November 2026 and do not meet that, so each has a finding instead: where its
logs live, what they record, the evidence, and what a precise reader would
need. Anyone who can get at per-call counts some other way can still use the
importer.

### Aider

- **Where it writes.** By default only two files, inside each project (at the git root, else the working folder; `aider/args.py:270`): `.aider.input.history` (typed prompts, no counts) and `.aider.chat.history.md`. Two more exist only on request: `--llm-history-file` (messages sent and received with a timestamp, no counts, no model; `aider/io.py:754`) and `--analytics-log` (JSON lines; `aider/analytics.py:242`). There is no global usage file and no list of projects (`~/.aider/analytics.json` holds only an id), and Aider registers no litellm callback, so no other log exists.
- **Chat history.** One line per user message, rounded for display by `format_tokens()` (`aider/utils.py:279`): `> Tokens: 2.3k sent, 1.1k received. Cost: $0.01 message, $0.05 session.`, with rounded cache write and cache hit figures added when the response had them. Rounded, and with no model on the line.
- **Analytics log.** Opt in only. The one event with counts is `message_send` (`aider/coders/base_coder.py:2102`): `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost`, `total_cost` and an int `time` in seconds. Its counters are per user message: in practice they hold that message's last successful call, while a call cut off at the output limit and continued with assistant prefill is never counted (`FinishReasonLength` is raised at lines 1898 and 1911, before the count at line 1811). It has no cache fields: under litellm 1.82.3 an Anthropic `prompt_tokens` already includes cache reads and writes (`litellm/llms/anthropic/chat/transformation.py:1581` to 1604) and Aider adds the writes again (`base_coder.py:2011`), so writes are counted twice and nothing can be split back out. `main_model` is `provider/REDACTED` or `None` for a model missing from Aider's cached copy of litellm's model list (`analytics.py:195`).
- **Not exact even where present.** Streaming is on by default (`args.py:323`). A streamed response is litellm's `CustomStreamWrapper`, which has no `usage` attribute (`litellm_core_utils/streaming_handler.py:82`), so Aider falls back to `litellm.token_counter()` on its own messages (`base_coder.py:2017`, `models.py:650`): an estimate, not the provider's count. Aider sets no `stream_options` and never reads a usage chunk (it skips chunks with no choices, `base_coder.py:1904`), so even `include_usage` set through model settings would not help. With `--no-stream` the counts are the provider's, but the per message, cache and dropped call problems above remain. Aider itself warns "Cost estimates may be inaccurate when using streaming and caching" (`aider/main.py:1121`).
- **Calls never recorded anywhere.** Weak model commit messages (`aider/repo.py:361`) and chat summaries (`aider/history.py:116`) go through `simple_send_with_retries()` (`models.py:1039`), and cache warming pings through `warm_cache()` (`base_coder.py:1340`, which prints a rounded cache hit figure only under `--verbose`); none of them logs a count.
- **Evidence.** https://github.com/Aider-AI/aider at 5dc9490 (22 May 2026, version 0.86.3.dev), read 1 November 2026: the files above, and `requirements.txt` (pins litellm 1.82.3, read from its PyPI wheel). The latest PyPI release, aider-chat 0.86.2 (12 February 2026), has the same `analytics.py` and the same counting code in `base_coder.py`, but pins litellm 1.81.10, which was not read.
- **What a precise reader would need.** Aider to write, per API call and by default to a known global place, the provider's own usage block (input, output, cache read, cache write) with the model id and a timestamp, including the weak model, summary and cache warming calls. Until then the importer is the route for anyone who logs those calls themselves (for example through a litellm callback).

### Cline CLI

- **Where:** one folder per session, `~/.cline/data/sessions/<id>/<id>.messages.json`, with each subagent's `<stem>.messages.json` beside it (`core/src/services/session-artifacts.ts` 74 to 79, 142). `CLINE_DIR`, `CLINE_DATA_DIR` and `CLINE_SESSION_DATA_DIR` move it (`shared/src/storage/paths.ts` 162, 187, 195); the index `sessions.db` sits in `data/db` (or `CLINE_DB_DATA_DIR`, line 248) and holds `provider` and `model` per session but no token counts (`shared/src/db/sqlite-db.ts` 188).
- **What it records:** each assistant message has `id`, `ts` (milliseconds), `modelInfo {id, provider}` and `metrics {inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens, cost}`, the difference in running usage across one model stream (`usageDelta`, `agents/src/agent-runtime.ts` 439 and 2088). `inputTokens` includes cache reads and writes for gateway providers (Cline's own formula, `llms/src/providers/ai-sdk.ts` 1176 to 1179). No request id is saved.
- **Why output is short:** `normalizeUsage` takes reasoning out of `outputTokens` (`ai-sdk.ts` 1358 to 1371: "Providers report reasoning tokens as a subset of outputTokens ... Strip them back out"), keeping it as `reasoningTokenCount`, and `agentMetricsToMetrics` leaves that field out when the message is saved (`core/src/runtime/config/agent-message-codec.ts` 321 to 332). This includes Anthropic: `@ai-sdk/anthropic` 4.0.78, the version Cline locks, reports `output_tokens_details.thinking_tokens` as reasoning (`convertAnthropicUsage`), so no provider or model is safe, and the saved record gives no sign of whether anything was taken out (Cline itself logs reasoning from models told not to think, `agent-runtime.ts` 2216 to 2241). The VS Code extension's `ui_messages.json` (`api_req_started`) drops it too (`apps/vscode/src/sdk/message-translator.ts` 91 to 114); the CLI does not write that format.
- **A sum that looks like a call:** when no assistant message of a run has metrics, the last one is given the whole run's usage in the same shape, with no mark (`core/src/services/session-data.ts` 170 to 187).
- **Double counting:** the `claude-code`, `openai-codex-cli` and `opencode` providers run that harness's own binary (`llms/src/providers/vendors/community.ts`), and session import (`core/src/services/session-import/`: Claude Code, Codex, OpenCode) copies that harness's usage into these files.
- **The only full counts:** the hub event log (`data/db/hub-events*.db`, `usage.updated`) keeps `reasoningTokenCount` per stream (`core/src/hub/server/handlers/session-event-projector.ts` 313 to 331), but with no model, and it is pruned after 7 days (`hub-event-log.ts` 21).
- **Evidence:** https://github.com/cline/cline at commit a6507a6 (30 October 2026, CLI 3.0.74), read 1 November 2026; paths under `sdk/packages` unless shown.
- **What a precise reader needs:** Cline saving `reasoningTokenCount` (or the output before reasoning is taken out) in `metrics`, and marking metrics that cover a whole run.

### Crush

- **Where:** one SQLite database per project, `<project>/.crush/crush.db` (or the `data_directory` option). The global list of projects, `projects.json` (`path`, `data_dir`), sits beside `crush.json` in `$CRUSH_GLOBAL_DATA`, else `$XDG_DATA_HOME/crush`, else `~/.local/share/crush` (`%LOCALAPPDATA%\crush` on Windows), so the databases could be found without searching the disk.
- **What it records:** the `messages` table has `model` and `provider` per message but no token counts; the `parts` JSON holds text, reasoning, tool calls and a `finish` part (reason, time), no usage. The only counts are in `sessions`: `prompt_tokens`, `completion_tokens`, `cost`.
- **Why they are not usable:** after each step, `updateSessionTokenCounters` overwrites `prompt_tokens` with that step's context size (input + cache read + cache write, folded into one figure) and `completion_tokens` with its output; they are neither per-call history nor session totals. Title generation then adds its own usage (from the small model) on top, through `UpdateSessionTitleAndUsage`. When a provider reports no usage, Crush stores an estimate (`fallbackStepUsage`). Cache reads and writes are never kept apart. Only `cost` accumulates, and it is Crush's own price (catwalk rates, OpenRouter's reported cost, nothing for flat-rate or estimated steps), so it cannot be repriced; `crush stats` simply sums these columns.
- **Per-call counts:** sent only to PostHog telemetry (`event.TokensUsed`), not written locally (with `CRUSH_DISABLE_METRICS`, `DO_NOT_TRACK` or `disable_metrics` not even that). `<data dir>/logs/crush.log` has HTTP bodies only in debug mode, cut to a tail; the one non-debug line carrying usage is an error logged when PostHog fails to queue an event, which is not a record of every call.
- **Evidence:** https://github.com/charmbracelet/crush at commit ef4993a (1 November 2026), read 1 November 2026: `internal/db/migrations/*.sql`, `internal/db/models.go`, `internal/db/sql/sessions.sql`, `internal/agent/agent.go` (step usage at 1126 to 1127, summary at 1543, title usage at 1940 to 1960, `updateSessionUsage` 2027, `contextTokens` 2067, `updateSessionTokenCounters` 2071), `internal/db/sessions.sql.go` 286 (title SQL adds), `internal/event/event.go` 84 to 96, `internal/log/http.go`, `internal/cmd/stats.go`, `internal/agent/usage_fallback.go`, `internal/agent/event.go`, `internal/message/content.go`, `internal/projects/projects.go`, `internal/config/load.go` (`GlobalConfigData`).
- **What a precise reader needs:** Crush storing each step's `fantasy.Usage` (input, output, cache read, cache creation) with the message that step produced, flagged when it was an estimate.

### Goose

- **Where:** one SQLite database, `<data dir>/sessions/sessions.db`, where the data dir is `$GOOSE_PATH_ROOT/data` when that variable holds an absolute path, else the platform data dir for app "goose" (`$XDG_DATA_HOME/goose`, by default `~/.local/share/goose`, on Linux). Older sessions were `.jsonl` files in `sessions/` whose first line holds session metadata and totals only.
- **What it records:** table `usage_ledger` (schema 15; no later migration touches it) gets one row per model stream attempt that reported usage: `id`, `session_id`, `created_timestamp` (epoch seconds at insert), `model`, `input_tokens` (including cache reads and writes), `output_tokens`, `total_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cost`, `cost_source` (`provider_reported`, `estimated`, `carried_forward` or NULL), `is_compaction`. An empty-response retry gets its own row; a stream that fails before its usage arrives gets none. The `accumulated_*` columns on `sessions` are running totals and unusable.
- **Why no reader:** a ledger row carries no provider, request id or message id. The provider lives only on the session row (overwritten when the user switches provider mid-session) and in assistant messages' `metadata_json.inference.provider`; compaction keeps messages (hidden from the agent), but rewind deletes them while their ledger rows stay, and nothing joins a row to a message except a timestamp in seconds. Goose's `claude-code`, `codex`, `gemini-cli`, `cursor-agent` and ACP (`claude-acp`, `codex-acp`, `amp-acp`, `copilot-acp`, `pi-acp`) providers run another harness's binary and write ledger rows too, one per delegated turn (that turn's total over several API calls), under Goose's configured model name, with a `cost_source` like any other row. Those calls are already in that harness's own log and cannot be told apart, so they would be counted twice. The per-message `metadata_json.usage` is no way round this: it misses compaction calls and rewound turns, and keeps only the last of several attempts.
- **Also:** `carried_forward` rows (no model) are written at the next recorded call whenever a session's running totals exceed its ledger sums: whole-session totals from before the ledger existed, or from a session imported from Claude Code, Codex or Pi (calls already in those logs). A compaction row (`is_compaction` 1) can hold tokenizer estimates when the provider returned no usage, with nothing in the row saying so. `logs/llm_request.*.jsonl` under the state dir keeps only the last 10 requests.
- **Evidence:** https://github.com/block/goose at commit b23d21c (31 October 2026), read 1 November 2026: `crates/goose/src/session/session_manager.rs` (schema and migration 15, `insert_usage_ledger_row`, `record_usage_metrics`, `replace_conversation_inner`, `truncate_conversation`), `crates/goose/src/agents/state_machine/usage.rs`, `crates/goose/src/providers/canonical_cost.rs`, `crates/goose-agent/src/inference.rs` (usage per stream attempt), `crates/goose-provider-types/src/conversation/token_usage.rs` (input convention), `crates/goose/src/providers/claude_code.rs`, `crates/goose/src/acp/provider.rs`, `crates/goose/src/context_mgmt/mod.rs`, `crates/goose-context-management/src/summarize.rs`, `crates/goose/src/session/import_formats/claude_code.rs`, `crates/goose/src/config/paths.rs`.
- **A precise reader would need:** a `provider` column on `usage_ledger`, written from the provider's name at record time, plus a marker on rows whose counts were estimated. With those, it would read ledger rows, skip `carried_forward`, estimated and delegating-provider rows, and key each row as `goose:<session_id>:<id>`.

### Hermes Agent

- **Where:** `~/.hermes/state.db` (SQLite; `HERMES_HOME` or `HERMES_DATA_DIR_SUFFIX` moves the home, which is `%LOCALAPPDATA%\hermes` on Windows, and each profile has its own home under `profiles/<name>/`), `logs/agent.log` in the same home, plus `sessions/` transcripts, `request_dump_*.json` and `cron/usage_audit.jsonl`.
- **state.db is totals only:** each call's delta is queued, adjacent deltas on the same route are merged, and `update_token_counts()` adds them into the `sessions` row (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `reasoning_tokens`, `api_call_count`) and, by upsert, into `session_model_usage` (keyed by session, model, `billing_provider`, `billing_base_url`, `billing_mode`, `task`). An `absolute` mode that overwrites with cumulative values exists, though nothing in the tree passes it at this commit. `messages.token_count` is never filled in; transcripts, request dumps and the opt-in trajectory files hold no response usage; `cron/usage_audit.jsonl` has one line per cron run; `moa-traces/` is off by default and has counts only for the advisor calls.
- **No row is provably one request, even with `api_call_count = 1`:** an MoA turn folds every advisor's usage into the aggregator's single delta, a Gemini long decode sums several `generateContent` hops into one delta, a Codex app-server turn counts as one call carrying only its last request's usage, and background review records N fork calls in one write. A total can cross a long-context threshold no single request crossed.
- **Per-call counts do exist, in `logs/agent.log`:** on by default (INFO), one line per main-loop or side-question response: `API call #<n>: model=<model> provider=<provider> in=<prompt> out=<output> total=<total> latency=<s>s cache=<read>/<prompt> (<pct>%) write=<written> id=<response id> upstream=<served by>`, where `in` is uncached plus cache read plus cache write, `cache=` and `write=` appear only when non-zero, and reasoning tokens sit inside `out`.
- **Why that log does not yet support a precise reader:** it is a diagnostic line, not a record: it rotates (5 MB, three backups, shared with every other INFO record) and goes silent if `logging.level` is raised; its timestamp is local time with no zone; MoA lines carry folded counts under the virtual `moa` route; a Gemini long decode line sums hops and nothing on it says so; auxiliary calls (titles, compression, vision) never reach it; and the only stable key is `id=`, present only when the provider returns one.
- **Double counting to keep in mind:** Codex app-server turns (`agent/codex_runtime.py`) go into state.db (not agent.log) and are already in Codex's own logs. ACP external-process providers such as Copilot (`agent/acp_client.py`) report zero usage, so they add calls but no tokens.
- **Evidence:** https://github.com/NousResearch/hermes-agent at 9a56be3 (1 November 2026), read 1 November 2026: `hermes_state_common.py` (SCHEMA_SQL), `hermes_state_usage.py`, `hermes_state.py`, `agent/turn_usage.py`, `hermes_logging.py`, `agent/gemini_long_decode.py`, `agent/codex_runtime.py`, `agent/transports/codex_app_server_session.py`, `agent/acp_client.py`, `agent/background_review.py`, `agent/session_persistence.py`, `cron/scheduler.py`, `agent/moa_trace.py`, `agent/trajectory.py`.
- **What a precise reader would need:** one durable row per HTTP request, with its own key, a zoned timestamp, the model and provider that served it and the five counts, written before any adding up (a `usage_events` table, or the counts on each assistant `messages` row); or, from agent.log, a marker for long-decode hops and a decision that a rotating log is an acceptable source.

### Qwen Code

- **Where:** each session is one JSONL file, `~/.qwen/projects/<cwd with every non-alphanumeric character as "-", lower-cased on Windows>/chats/<sessionId>.jsonl`. `QWEN_HOME` moves `~/.qwen`; `QWEN_RUNTIME_DIR`, or the `runtimeOutputDir` setting, moves the base folder that `projects/` sits in. A second per-call file, `<same base>/usage/token-usage-<YYYY-MM>.jsonl`, is written while the `usageStatisticsEnabled` setting is on (the default).
- **What the session file records:** each line is a `ChatRecord` (`uuid`, `parentUuid`, `sessionId`, `timestamp`, `type`, `cwd`, `version`, `message`); `/branch` copies records with the same `uuid` under a new `sessionId`. Each `type: "assistant"` line is one streamed API call with `model` and a Gemini-shaped `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`, `cachedContentTokenCount`, `thoughtsTokenCount`, `totalTokenCount`) from the last chunk, but no auth type. Each successful call also gets a `type: "system"`, `subtype: "ui_telemetry"` line whose `systemPayload.uiEvent` (`event.name: "api_response"`) carries `model`, `auth_type`, `response_id`, `prompt_id`, `event.timestamp` and the same five counts as `input_token_count`, `output_token_count`, `cached_content_token_count`, `thoughts_token_count`, `total_token_count`. The usage file holds the same figures with `authType`.
- **The auth type is known for each call:** every generator, including the one a `modelFallbacks` capacity fallback switches to (which may be another provider), is wrapped in its own `LoggingContentGenerator` that stamps its own auth type. What is missing is the counts each auth type needs:
  - **`gemini`, `vertex-ai`:** Google's figures are passed through unchanged (prompt includes cached, output excludes thoughts). Exact for each logged call.
  - **`anthropic`:** `promptTokenCount` is input plus cache reads plus cache writes, and only cache reads are kept separately. The cache-write figure goes to an in-memory `WeakMap` (`setGenAiUsageProvenance`) and never reaches either file, so cache writes cannot be told apart from uncached input.
  - **`openai`, `qwen-oauth`, `openai-responses`:** output is `completion_tokens` or `output_tokens`, which include reasoning, so output is exact; when the Chat Completions provider omits `reasoning_tokens`, `thoughtsTokenCount` is an estimate from the text (Responses writes 0). But only `cached_tokens` is read: DashScope requests carry `cache_control` breakpoints and any cache-creation count the provider returns is dropped, and the base URL (any host) is not in the call's record. There is also no Alibaba or DashScope table in `pricing/`.
- **Calls missing from both files:** every call with an internal prompt id (`prompt_suggestion`, `forked_query`, `speculation`, and every `side-query:*`, which includes chat compression, web fetch, session recap, tool-use summaries and goal verification) is skipped, as is a stream that ended by timeout or abort. So even the `gemini` and `vertex-ai` calls, exact one by one, would give a session total short by calls the logs never show.
- **Evidence:** https://github.com/QwenLM/qwen-code at commit dd020dd (1 November 2026, UTC), read 1 November 2026. In `packages/core/src/`: `config/storage.ts`, `utils/paths.ts` (`sanitizeCwd`), `services/chatRecordingService.ts` (`ChatRecord`, `createBaseRecord`, `recordAssistantTurn`, `recordUiTelemetryEvent`), `services/tokenUsageService.ts`, `telemetry/loggers.ts` (`logApiResponse`), `telemetry/types.ts` (`ApiResponseEvent`), `utils/internalPromptIds.ts`, `core/llm-chat.ts` (`processStreamResponse`, `makeFallbackStream`), `core/baseLlmClient.ts` (`resolveForModel`), `core/contentGenerator.ts`, `core/loggingContentGenerator/loggingContentGenerator.ts`, `core/openaiContentGenerator/converter.ts`, `core/openaiContentGenerator/provider/dashscope.ts`, `core/openaiResponsesContentGenerator/responses-converter.ts`, `core/anthropicContentGenerator/usage.ts`, `telemetry/gen-ai-usage.ts`.
- **What a precise reader would need:** Qwen Code would have to record internal and side-query calls (and aborted streams that were billed), write the cache-write count beside the cache-read count for every auth type, and write the base URL with each call. Tokenmeter would also need a DashScope price table.

### kimi-cli (the older Python Kimi CLI)

The Kimi Code reader covers MoonshotAI/kimi-code only. The older MoonshotAI/kimi-cli, which Kimi Code is replacing, cannot be priced exactly, so it is not read.

- Where: `$KIMI_SHARE_DIR` (default `~/.kimi`), `sessions/<md5 of the work folder>/<session>/wire.jsonl` beside `context.jsonl` and `state.json`; subagents under `subagents/`. `kimi.json` maps work folders to buckets.
- What it records: each step's usage on a `StatusUpdate` wire message (`{"timestamp", "message": {"type": "StatusUpdate", "payload": {"token_usage": {"input_other", "output", "input_cache_read", "input_cache_creation"}, "message_id"}}}`), per API call and already split into uncached, cached and cache-write input.
- What it does not: no model or provider for the main agent's calls anywhere in the session files (not on `StatusUpdate`, `StepBegin`, `TurnBegin`, `state.json` or `context.jsonl`); a subagent's `meta.json` has `launch_spec.effective_model`, but that is a configured alias, and empty when the subagent inherits its parent's model; compaction calls write their usage to the log file only, never the wire; a subagent's steps also appear inside `SubagentEvent` in the parent's wire.
- Evidence: github.com/MoonshotAI/kimi-cli at 9ab1286 (22 September 2026), read 1 November 2026: `src/kimi_cli/share.py`, `metadata.py`, `session.py`, `wire/file.py`, `wire/types.py` (StatusUpdate), `soul/kimisoul.py` (step usage at "2e.5"), `soul/compaction.py`, `subagents/store.py` and `subagents/builder.py` (meta.json, `clone_llm_with_model_alias`); `packages/kosong/src/kosong/chat_provider/__init__.py` (TokenUsage).
- Kimi Code's own migration from kimi-cli (`packages/migration-legacy` in MoonshotAI/kimi-code at a2afdbc) carries messages across but no usage, so migrated sessions add nothing to the Kimi Code reader's figures.
- A precise reader would need kimi-cli to record the model on each step's usage (and the compaction calls' usage in the wire); the model in today's `config.toml` is not the model of a past call.

### T3 Code

**T3 Code** (https://github.com/pingdotgg/t3code, commit fa31b66, read 1 November 2026): no reader. Its agent turns run through the harnesses it drives (Claude Code via the Agent SDK, Codex app-server, OpenCode, Pi, Grok and others over ACP, Cursor via `@cursor/sdk`), whose own logs hold those calls; its own usage view reads those logs too (`apps/server/src/usage/usageTranscriptReader.ts`).

It does keep token figures of its own, in `<base dir>/userdata/statev2.sqlite` (`T3CODE_HOME`, `apps/server/src/config.ts` lines 140 to 150): a `tokenUsage` object (`usedTokens`, `inputTokens`, `cachedInputTokens`, `outputTokens`, `reasoningOutputTokens`) inside `payload_json` of `orchestration_v2_projection_provider_turns` (`packages/contracts/src/orchestrationV2.ts` lines 216 to 227, `apps/server/src/orchestration-v2/ProjectionStore.ts` lines 2336 to 2360). These are per turn copies of what the driven harness reported, not per call, so they would double count and could not be priced exactly.

Calls that escape every log: thread titles, commit messages, PR text, branch names and review guides are generated by `claude -p --no-session-persistence` (`apps/server/src/textGeneration/ClaudeTextGeneration.ts` lines 52 and 202 to 232) and `codex exec --ephemeral` (`CodexTextGeneration.ts` lines 280 to 300), Pi with `ephemeral: true` (`packages/provider-pi/src/server/textGeneration.ts` line 49). Neither harness writes a log for these, and T3 Code records no usage for them (no usage parsing in `apps/server/src/textGeneration/`), so no reader could count them.

## Candidates

Worth an adapter, as far as anyone has looked: Roo Code, Continue. Aider,
Cline, Goose, Crush, Hermes Agent and Qwen Code were looked at and have
findings above. Closed harnesses such as Cursor are better served by an
exporter to the import format than by guessing at their storage.
