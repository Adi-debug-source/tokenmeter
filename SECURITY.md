# Security

Tokenmeter reads the logs your coding harness writes on your Mac and prices
them. Nothing about your usage leaves the machine: the only requests it makes
are for exchange rates and, for a model no table has, published price lists,
and `--offline` or `TOKENMETER_OFFLINE=1` stops both. A report that it sends
anything else, fetches anything else, or can be made to run something, is a
security report.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability. Use GitHub's private
vulnerability reporting instead: on the repository's Security tab, choose
Report a vulnerability. That reaches the maintainer alone.

Say what you found, how to reproduce it (an invented log or import file is
ideal; never a real one), and which version (`tokenmeter --version`). You will
get a reply within a week, and a fix, when one is needed, in the next release,
with credit if you want it.

## What is in scope

- Anything that sends usage data, totals, project names or session ids off
  the Mac, or that fetches from an address other than the price lists and the
  exchange-rate service named in the README.
- A log line, an import file or a model name that runs script in the
  dashboard, breaks out of its HTML, or reaches a command.
- A way for another user account on the same Mac to read or change the
  ledger, the caches beside the engine or the dashboard.
- A crash or a wrong figure caused by crafted input: a damaged transcript, a
  compressed session, an import file, a price page, a rate response.

## Supported versions

The latest release only. Homebrew and a clone both install from source, so a
fix is available as soon as it is tagged and the formula points at it.
