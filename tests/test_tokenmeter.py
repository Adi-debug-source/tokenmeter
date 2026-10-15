#!/usr/bin/env python3
"""Tests for tokenmeter.py.

Standard library only, so this runs wherever the tool runs:

    python3 tests/test_tokenmeter.py

Most tests here exist because something was once wrong. The bug each one
guards is named in its docstring, so a failure says what broke rather than
only that something did. Nothing reads a real history and nothing touches the
network: fixtures are built in a temp directory and every fetch is faked, so
the suite is fast, deterministic and safe to run on any machine.

The tests live beside this file, one module per area: test_money.py,
test_pricing.py, test_prices_pinned.py, test_ledger.py, test_adapters.py,
test_lookup.py, test_reports.py, test_dashboard.py and test_statusline.py,
with what they share in helpers.py. This file holds no tests: it finds them
all, runs them, and exits non-zero if any fails. Options pass through to
unittest (-f stops at the first failure, -k runs only the tests whose names
match), and one area runs on its own, as python3 tests/test_ledger.py.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    unittest.main(module=None, verbosity=2,
                  argv=[sys.argv[0], "discover", "-s", HERE, "-t", HERE, "-p", "test_*.py"]
                  + sys.argv[1:])
