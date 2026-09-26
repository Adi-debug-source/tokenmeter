"""Harness adapters. See README.md in this folder before writing one.

An adapter is a module with these names:

  NAME             short id, used by --adapter and stored in the ledger
  LABEL            how reports name it
  STATUS           "verified" or "unverified"; see README.md for the rule
  FILES            what it reads, in words ("transcripts", "sessions")
  FILE             the same, for one of them ("transcript", "session")
  default_roots()  the folders it reads when nothing overrides them
  files(roots, project="", session="")   the log files under those folders
  looks_like(line) whether one line of an unknown file is in its format
  records(path)    yield (key, event) for every API call in one file

and optionally:

  notes()          sentences the report must print about this run's figures
  reset()          clear per-run state before a scan

The engine does everything else: de-duplication, the ledger, pricing, windows
and every report. An adapter only reads its harness's logs and says what each
call was, which keeps the arithmetic in one place.
"""

from . import claude_code, codex, gemini_cli, importer, opencode

# Discovered automatically when their folders exist, in this order.
ADAPTERS = {m.NAME: m for m in (claude_code, codex, gemini_cli, opencode)}

# Every source a ledger row can name, including the importer, which is only
# ever used explicitly.
ALL = {**ADAPTERS, importer.NAME: importer}
