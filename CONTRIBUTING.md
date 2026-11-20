# Contributing

Thank you for looking. Tokenmeter's only claim is that its numbers are right, so the most useful thing anyone can send is a check against reality.

## Three ways to help, smallest first

1. **Compare a figure with your own records.** If you use Codex, Gemini CLI, OpenCode, Kilo Code, Kimi Code or DeepSeek Harness, run `tokenmeter --by source` and compare it with what the harness or your invoice says. Open an issue whether it matches or not: one real sample is what promotes a reader from unverified to verified.
2. **Report a wrong or missing price.** `tokenmeter --check-prices` compares every table with its provider's live page. If it disagrees, or a model you use is labelled as looked up, open an issue with the model's name and the provider's pricing page.
3. **Send a change.** A new harness reader is described in [adapters/README.md](adapters/README.md); a new or changed price in [pricing/README.md](pricing/README.md).

Never attach a real transcript, ledger or dashboard to an issue: they show your projects and working days. A few invented lines in the same shape are enough, and `docs/screenshots/make_demo.py` writes a whole invented history if you need one.

## Before you open a pull request

```bash
python3 tests/test_tokenmeter.py
```

Standard library only, no network, about ten seconds. It must pass.

- **A bug fix starts with a test that fails without it.** The test's docstring names the bug, so a later failure says what broke.
- **Arithmetic lives in `tokenmeter.py` and nowhere else.** A reader never prices, a price table never adds up, and the faces only display.
- **A rate change is a new dated row.** The old row is never edited, so history keeps the price it was charged at.
- **Python 3.9 and up, no packages.**
- **One change per pull request,** titled in the conventional form with plain words: `fix(dashboard): the chart's tooltip sits beside the bar`.

[MAINTENANCE.md](MAINTENANCE.md) has the rest: how the parts fit together, the ledger, releases and the screenshots.

## Security

Please report a vulnerability privately, as [SECURITY.md](SECURITY.md) describes, not in a public issue.
