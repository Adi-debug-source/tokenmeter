# Price tables

One file per provider. Each holds the rates, the evidence for them, and how
to read the provider's own pricing page. The engine does the arithmetic.

The tool's one claim is that its numbers are right, so every rate here must
come from the provider's own published pricing, read on a date that is
recorded, and pinned by a test. Never from memory, a blog, or an aggregator.

## A table file

| Name | What it is |
|---|---|
| `PROVIDER` | Id used in events and the ledger: `openai`. |
| `NAME` | How reports name it: `OpenAI`. |
| `SOURCE` | The pricing page, as a person would open it. |
| `VERIFIED_ON` | The date every figure was last read off that page, `YYYY-MM-DD`. |
| `MEASURED` | `True` only if checked against real bills or the harness's own cost figures. |
| `CACHE_WRITE_5M_MULT`, `CACHE_WRITE_1H_MULT` | Default cache write multiples of input. `1.0` if writes are not billed extra. |
| `WEB_SEARCH_PER_1K` | Dollars per 1,000 searches, or `0.0` if not modelled. |
| `SNAPSHOT` | Regex for a dated suffix that means "the same model", or `r"(?!)"` for none. |
| `PRICES` | `{model id: [rows]}`, dollars per million tokens. |
| `FALLBACK_MODEL` | The row an unknown id is priced at, flagged in every report. |
| `ALIASES` *(optional)* | Other published names for the same model. |
| `RETIRED` *(optional)* | `{model id: "YYYY-MM-DD"}`: models the page no longer lists, kept at their last published price so older usage is still priced, with the retirement date from the provider's own deprecation notice. |
| `LONG_OVER` *(optional)* | The provider's long-context threshold in prompt tokens, as the engine tests it ("more than"). Its rows' `long` use it, and the startup lookup gives it to a looked-up model the page lists long-context rates for. |
| `page_rates(fetch, tables, want=None)` *(optional)* | Reads the live page, for `--check-prices` and the startup lookup. |
| `SOURCE_MD`, `PAGE_NAMES` *(optional)* | Read only by the file's own `page_rates()`: the page in markdown, and the page's model names mapped to ids. |

A row:

```python
{"from": "", "in": 2.00, "out": 10.00, "cache_read_mult": 0.1, "fast": (4.00, 20.00)}
```

| Key | Meaning |
|---|---|
| `from` | The day this rate took effect. `""` for always. |
| `in`, `out` | Base input and output, per million tokens. |
| `cache_read_mult` | A cache hit's price as a multiple of `in`. |
| `fast` | `(in, out)` when a call is recorded as fast or priority, else `None`. |
| `write_mult`, `write_1h_mult` *(optional)* | Override the table's cache write multiples for this model. |
| `long` *(optional)* | `{"over": tokens, "in": mult, "out": mult}`: above that many prompt tokens (cache included), the whole request is priced higher. |
| `off_peak` *(optional)* | Time-of-day pricing: `{"mult": 0.5, "peak_utc_hours": [[1, 4]], "peak_weekdays": [0, 1, 2, 3, 4]}`. |

`page_rates()` returns `({model id: figures}, [page ids the table lacks])`.
The figures are dollars per million tokens, under whichever of these names
the page gives: `in`, `out`, `cached`, `write` or `write_5m`, `write_1h`,
`fast_in` and `fast_out`, `long_in` and `long_out` (with `long_cached`,
`long_write_5m` and `long_write_1h` when the page lists the higher tier in
full, as Anthropic's does for Haiku 5.5), and optionally `long_over` (the
threshold in tokens, when the page states its own) and `_history` (dated
prices, oldest first, each with `from`, `in`, `out` and `cached`).
`--check-prices` compares every field it finds; the startup lookup turns
them into rows, one per dated price.

`common.py` is not a table. It holds what the page readers share:
`money(cell)` reads the first dollar figure in a page's cell, so
`"$1,250.00 / MTok"` gives `1250.0` and a cell with no figure gives `None`;
`free_is_zero=True` reads a cell that says only "Free" as `0.0`, and
`commas=False` stops a figure at a comma. Use it rather than writing another.

## Adding a provider or a model

1. Read the provider's pricing page. Save the raw page if you can; the
   markdown form (append `.md` to many docs URLs) is the easiest to check.
2. Add the rows, with a docstring saying which page, which date, which tier,
   and every rule you modelled or deliberately did not.
3. Pin every rate in `tests/test_prices_pinned.py`, typed from the page, not
   copied from your table. A slip in either then fails.
4. Write `page_rates()` if the page can be read reliably, and run
   `python3 tokenmeter.py --check-prices`. It must report every model matching.
5. Register the file in `__init__.py`.
6. Regenerate `docs/prices.md` with
   `python3 tokenmeter.py --list-prices --markdown > docs/prices.md`, and give
   the provider its row in the README's price table: its models, any retired,
   the date its page was checked, and whether it was measured against real
   bills. Tests in `tests/test_prices_pinned.py` fail until both match the
   tables.

A model the tables lack is still priced, by the startup lookup, but it is
labelled as looked up rather than checked. Adding it here is what turns it
into a checked figure.

## When a rate changes

Add a row with the date it took effect. **Never edit the old row.** Calls
before that date keep the old rate, which is the whole point: history stays
what it was.

```python
# Illustrative figures, not a real price change.
"example-model": [
    {"from": "",           "in": 4.00, "out": 20.00, ...},
    {"from": "2027-03-01", "in": 5.00, "out": 25.00, ...},
],
```

Then update `VERIFIED_ON`, the pinned test, `docs/prices.md` and the
provider's row in the README's price table, as in step 6 above.

## When a model leaves the page

`--check-prices` names a model the page no longer lists. Find out why from
the provider's own deprecation notice or changelog. If it was retired at its
existing price, keep its row, so older usage is still priced, and add it to
`RETIRED` with the retirement date and a comment naming the source. The
README's price table counts it as retired, as in "12 (3 retired)". If it was
renamed, add the new name instead. Never delete a row that history still uses.

## Checking a table is still right

```bash
python3 tokenmeter.py --check-prices
```

It fetches each provider's page, compares every column it can read, and names
any model the page lists that the table does not. It changes nothing. Every
report also warns once a table's `VERIFIED_ON` is more than 90 days old.

## Deliberately absent

**Qwen (Alibaba Model Studio).** Its price depends on the region, on a
prompt-length tier, on whether the model was thinking, on a temporary
discount, and on whether a cache hit was implicit or explicit. A log records
almost none of that, so any table would be a guess. Qwen models are priced by
the startup lookup and labelled as such.
