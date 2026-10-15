---
description: What your usage would have cost at API rates (Tokenmeter)
allowed-tools: Bash(python3 ~/.claude/tools/tokenmeter/tokenmeter.py:*)
---

Run `~/.claude/tools/tokenmeter/tokenmeter.py` and report the result.

Arguments given: `$ARGUMENTS`

Pick the invocation from the arguments:

1. Nothing, or a word like "all" or "total": `python3 ~/.claude/tools/tokenmeter/tokenmeter.py --by model`
2. A rolling window such as "7d" or "30d": pass it as `--since`. "Today" is `--period today`,
   and "yesterday" is `--period yesterday`.
3. A calendar period ("this week", "last month"): `--period week`, `--period lastmonth`, and so on.
4. "session" or "this session": `--session <the current session id>`. "This project" is
   `--project .`, and a project's name is `--project <name>`.
5. "html", "dashboard" or "open": `--html` (writes to ~/Downloads and opens it).
6. "projects", "models", "days", "weeks", "months", "harnesses", "providers" or "sessions": the
   matching `--by` value (`project`, `model`, `day`, `week`, `month`, `source`, `provider`), or
   `--sessions`.
7. A currency ("in pounds", "gbp", "euro"): add `--currency GBP` and so on.
   USD is the default; GBP, EUR, INR, CAD, AUD and JPY also work.
8. "prices" or "check prices": `--check-prices`.
9. "tokens" or "how many tokens": the same as 1. The report gives total tokens and fresh
   tokens (the total less cache reads) under the cost, and `--by` and `--sessions` give each
   row its tokens.

Show the figures as the script prints them, the token lines and any notes it
prints included.
Do not recompute anything by hand and do not round the headline number. Say in
one line that this is the counterfactual at API rates, not a bill.
