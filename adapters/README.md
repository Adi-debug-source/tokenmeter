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
| `default_roots()` | The folders it reads, honouring the harness's own environment variables. |
| `files(roots, project="", session="")` | The log files under those folders. |
| `looks_like(line)` | Whether one line of an unknown file is in this format. |
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
conversions.

## De-duplication

`key` must identify the API call itself, not the log line. Harnesses write the
same call more than once (once per streamed block, again on resume, again when
a message is edited), and the engine keeps one copy per key: the first
sighting's time and session, and the largest usage block. So:

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
and `tests/test_tokenmeter.py` has a class per adapter.

Run `python3 tests/test_tokenmeter.py` before and after. The Claude Code
figures must not move by a single token.

## Candidates

Worth an adapter, as far as anyone has looked: Aider, Goose, Cline, Roo Code,
Continue. Closed harnesses such as Cursor are better served by an exporter to
the import format than by guessing at their storage.
