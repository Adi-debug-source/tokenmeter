"""Small helpers the price tables' page readers share. Standard library only.

A helper, not a price table: it defines none of a table's names, and TABLES
in __init__.py does not list it.
"""

import re

_FIGURE = re.compile(r"\$([\d.,]+)")
_FIGURE_NO_COMMAS = re.compile(r"\$([\d.]+)")


def money(cell: str, free_is_zero: bool = False, commas: bool = True):
    """The first dollar figure in a pricing page's cell, in dollars.

    "$0.25 / MTok<sup>1</sup>" -> 0.25 and "$1,250.00" -> 1250.0. A cell with
    no figure ("-", "Free") -> None. With free_is_zero, a cell that reads
    "Free" and nothing else -> 0.0, for a page that writes a free model so.
    With commas=False a figure stops at a comma, as Z.ai's reader always has.
    """
    if free_is_zero and cell.strip().lower() == "free":
        return 0.0
    m = (_FIGURE if commas else _FIGURE_NO_COMMAS).search(cell)
    return float(m.group(1).replace(",", "")) if m else None
