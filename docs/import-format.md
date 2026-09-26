# The import format

For any harness Tokenmeter has no adapter for. Write one JSON object per API
call, one per line, and pass the file:

```bash
python3 ~/.claude/tools/tokenmeter/tokenmeter.py --import calls.jsonl
your-exporter | python3 ~/.claude/tools/tokenmeter/tokenmeter.py --import -
```

The calls are priced like everything else, appear in every report, the
dashboard and the menu bar, and are written to the ledger, so a later run
still has them after the file is gone. Importing the same file again counts
nothing twice.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique per API call. The provider's own response id is ideal. |
| `timestamp` | yes | ISO 8601, such as `2026-09-20T14:03:11Z`. No offset means UTC. |
| `provider` | yes | Whose price table to use: `anthropic`, `openai`, `google`, `xai`, `deepseek`, `mistral`, `moonshot`, `zai`, or another name, which is looked up online. |
| `model` | yes | The provider's model id, exactly as the API calls it. |
| `input` | | Input tokens **not** served from cache and not written to it. |
| `cache_read` | | Input tokens served from the prompt cache. |
| `cache_write` | | Input tokens written to the cache (use this if the provider has one kind). |
| `cache_write_5m` | | Anthropic: tokens written with the 5-minute lifetime. |
| `cache_write_1h` | | Anthropic: tokens written with the 1-hour lifetime. |
| `output` | | Output tokens, **including** any reasoning or thinking tokens. |
| `thinking` | | Of `output`, how many were reasoning. Reported, never billed twice. |
| `web_searches` | | Web search calls made during this request. |
| `speed` | | `standard` (default) or `fast`, for providers with a fast or priority tier. |
| `session` | | Any grouping key you like, for `--by session`. |
| `project` | | Any grouping key you like, for `--by project`. |

Every token field is a whole number and defaults to 0. A line with no tokens
at all, a missing required field, or an unreadable timestamp is skipped, and
the report says how many lines were skipped and why.

## The one thing to get right: what `input` means

Providers disagree about whether their input count includes cached tokens.
Tokenmeter's `input` never does. Convert before writing:

| Provider reports | Write |
|---|---|
| Anthropic `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | `input` = `input_tokens`, `cache_read` = `cache_read_input_tokens`, `cache_write_5m` = `cache_creation_input_tokens` (or split by lifetime if you have `cache_creation`) |
| OpenAI `input_tokens` with `input_tokens_details.cached_tokens` (and `cache_write_tokens`) | `input` = `input_tokens` minus both, `cache_read` = `cached_tokens`, `cache_write` = `cache_write_tokens` |
| OpenAI `output_tokens` with `output_tokens_details.reasoning_tokens` | `output` = `output_tokens` (already includes reasoning), `thinking` = `reasoning_tokens` |
| Gemini `promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount` | `input` = prompt minus cached, `cache_read` = cached, `output` = candidates plus thoughts, `thinking` = thoughts |
| DeepSeek `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens` | `input` = miss, `cache_read` = hit |

Getting this wrong double-counts cached tokens at the full input rate, which
on a coding agent is most of the bill.

## Examples

```json
{"id": "msg_01A", "timestamp": "2026-09-20T09:14:02Z", "provider": "anthropic", "model": "claude-sonnet-5", "input": 412, "cache_read": 81200, "cache_write_5m": 2300, "output": 910}
{"id": "resp_7f2", "timestamp": "2026-09-20T09:20:40Z", "provider": "openai", "model": "gpt-6-sol", "input": 1880, "cache_read": 44032, "cache_write": 0, "output": 1204, "thinking": 640, "session": "refactor", "project": "api"}
{"id": "gem-331", "timestamp": "2026-09-20T10:02:11+01:00", "provider": "google", "model": "gemini-3.5-flash", "input": 5120, "cache_read": 20480, "output": 1733, "thinking": 1100}
{"id": "ds-0042", "timestamp": "2026-09-21T02:30:00Z", "provider": "deepseek", "model": "deepseek-flash", "input": 9000, "cache_read": 30000, "output": 800}
```

The last one was made at 02:30 UTC on a Monday, inside DeepSeek's peak hours,
so it is priced at the peak rate; the same call at 12:00 would be half.

## Checking an import

```bash
python3 ~/.claude/tools/tokenmeter/tokenmeter.py --adapter import --import calls.jsonl --no-ledger --by model
```

`--adapter import` shows the imported calls alone, and `--no-ledger` keeps a
trial run out of your history. Drop both once the figures look right.
