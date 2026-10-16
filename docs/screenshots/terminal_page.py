#!/usr/bin/env python3
"""
Draw a terminal's output, colours and all, in a dark terminal window, as a
page for a browser to screenshot. The README's terminal images are made this
way, from the demo's output (see make_demo.py and shoot.py).

    FORCE_COLOR=1 python3 tokenmeter.py --by model > report.txt
    TITLE="python3 tokenmeter.py --by model"
    python3 docs/screenshots/terminal_page.py "$TITLE" < report.txt > report.html

The first argument is the window's title, the command as typed. The page is
the window on a dark backdrop with a 28 pixel margin, sized to its text: as
wide as its longest row and two columns more, which leaves the same margin
on the right as the engine's two-space indent leaves on the left. A line
longer than --columns (120 unless given) is wrapped at its last space that
fits and carries on under its own indent, the way the engine wraps its own
notes. The blank line the engine prints first and last is left out. Every
character the engine printed is drawn, in the order it printed them.

Only the codes the engine writes are drawn: bold, dim, reset, cyan, green
and yellow (tokenmeter.py's COLOUR_CODES), in the colours of the README's
first terminal images. Anything else in an escape sequence is ignored. A
run of full blocks, a bar chart's bar, is drawn as one solid bar the width
of its characters.

Python 3.9 or later, standard library only.
"""

from __future__ import annotations

import argparse
import html
import re
import sys

SGR = re.compile(r"\x1b\[([0-9;]*)m")

FG = {"36": "c", "32": "g", "33": "y"}

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
:root{{--backdrop:#0a0b0d;--body:#14161a;--bar:#1b1e23;--edge:#2a2e35;
  --ink:#e6e8eb;--dim:#7d8590;--cyan:#5bc0d9;--green:#5cab7f;--yellow:#e0b44c}}
html,body{{margin:0;background:var(--backdrop)}}
body{{padding:28px;display:inline-block}}
.win{{border:1px solid var(--edge);border-radius:12px;background:var(--body);overflow:hidden;
  box-shadow:0 20px 34px rgba(0,0,0,.5)}}
.bar{{height:34px;background:var(--bar);border-bottom:1px solid var(--edge);display:flex;
  align-items:center;padding-left:14px}}
.bar i{{width:12px;height:12px;border-radius:50%;margin-right:8px;display:block}}
.bar i:nth-child(1){{background:#ff5f57}}.bar i:nth-child(2){{background:#febc2e}}
.bar i:nth-child(3){{background:#28c840}}
.bar span{{margin-left:12px;color:var(--dim);font:12px/1 -apple-system,"SF Pro Text",
  "Helvetica Neue",sans-serif;letter-spacing:.08px}}
pre{{margin:0;padding:18px 12px 22px;color:var(--ink);width:{width}ch;
  font:13.5px/20.25px "SF Mono",ui-monospace,Menlo,monospace;
  font-variant-ligatures:none;-webkit-font-smoothing:antialiased}}
pre b{{font-weight:700}}
.blk{{display:inline-block;height:14px;margin-top:4px;vertical-align:top;background:currentColor}}
.d{{color:var(--dim)}}.c{{color:var(--cyan)}}.g{{color:var(--green)}}.y{{color:var(--yellow)}}
</style></head>
<body><div class="win"><div class="bar"><i></i><i></i><i></i><span>{title}</span></div>
<pre>{rows}</pre></div>
<script>
// For a first pass with --dump-dom: the size the window needs to show the
// whole page, in CSS pixels, so the screenshot can be taken at exactly that.
const r = document.body.getBoundingClientRect();
document.documentElement.dataset.size = Math.ceil(r.width) + "," + Math.ceil(r.height);
</script>
</body></html>
"""


def spans(line: str) -> list:
    """A line as (text, bold, dim, colour) runs, the escape codes read."""
    out = []
    bold = dim = False
    colour = ""
    pos = 0
    for m in SGR.finditer(line):
        if m.start() > pos:
            out.append((line[pos:m.start()], bold, dim, colour))
        for code in (m.group(1) or "0").split(";"):
            if code in ("", "0"):
                bold = dim = False
                colour = ""
            elif code == "1":
                bold = True
            elif code == "2":
                dim = True
            elif code == "22":
                bold = dim = False
            elif code in FG:
                colour = FG[code]
            elif code == "39":
                colour = ""
        pos = m.end()
    if pos < len(line):
        out.append((line[pos:], bold, dim, colour))
    return out


def wrap(runs: list, columns: int) -> list:
    """Runs cut into rows of at most `columns` characters. A long line breaks
    at its last space that fits, and goes on under its own indent, as the
    engine wraps its own notes, so no word is cut in two; a word longer than
    a whole row is cut where it reaches the edge."""
    chars = [(ch, *style) for text, *style in runs for ch in text]
    rows = []
    indent = len(chars) - len(lstrip(chars))
    lead = []
    while len(lead) + len(chars) > columns:
        room = columns - len(lead)
        cut = max((i for i in range(min(room, len(chars) - 1) + 1) if chars[i][0] == " "
                   and i > 0 and any(c[0] != " " for c in chars[:i])), default=-1)
        if cut <= 0:
            rows.append(lead + chars[:room])
            chars = chars[room:]
        else:
            rows.append(lead + chars[:cut])
            chars = lstrip(chars[cut:])
        lead = [(" ", False, False, "")] * indent
    rows.append(lead + chars)
    return [regroup(row) for row in rows]


def lstrip(chars: list) -> list:
    i = 0
    while i < len(chars) and chars[i][0] == " ":
        i += 1
    return chars[i:]


def regroup(chars: list) -> list:
    """Characters with their styles back into runs."""
    runs = []
    for ch, *style in chars:
        if runs and runs[-1][1:] == tuple(style):
            runs[-1] = (runs[-1][0] + ch, *style)
        else:
            runs.append((ch, *style))
    return runs


BLOCKS = re.compile("\u2588+")


def render_row(row: list) -> str:
    """One row as HTML. A run of full blocks, the engine's bar charts, is
    drawn as one solid bar as wide as the run, so the bar has no seams
    between its characters."""
    parts = []
    for text, bold, dim, colour in row:
        text = BLOCKS.sub(lambda m: f'<i class="blk" style="width:{len(m.group(0))}ch"></i>',
                          html.escape(text, quote=False))
        cls = " ".join(c for c in (colour, "d" if dim and not colour else "") if c)
        if cls:
            text = f'<span class="{cls}">{text}</span>'
        if bold:
            text = f"<b>{text}</b>"
        parts.append(text)
    return "".join(parts)


def page(text: str, title: str, columns: int = 120) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    plain = [SGR.sub("", line) for line in lines]
    while plain and not plain[0].strip():
        lines.pop(0)
        plain.pop(0)
    while plain and not plain[-1].strip():
        lines.pop()
        plain.pop()
    rows = []
    for line in lines:
        rows.extend(wrap(spans(line.rstrip()), columns))
    width = max((sum(len(r[0]) for r in row) for row in rows), default=0) + 2
    return PAGE.format(title=html.escape(title), width=width,
                       rows="\n".join(render_row(row) for row in rows))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Draw terminal output in a terminal window page.")
    ap.add_argument("title", help="the window's title: the command as typed")
    ap.add_argument("--columns", type=int, default=120,
                    help="wrap rows longer than this many characters (default 120)")
    args = ap.parse_args(argv)
    sys.stdout.write(page(sys.stdin.read(), args.title, args.columns))


if __name__ == "__main__":
    main()
