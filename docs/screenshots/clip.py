#!/usr/bin/env python3
"""
Record the README's two short clips from a demo made by make_demo.py.

    DEMO=/tmp/tokenmeter-demo
    TZ=Europe/London python3 docs/screenshots/make_demo.py "$DEMO" --now 2026-11-21T12:20 --force
    TZ=Europe/London python3 docs/screenshots/clip.py "$DEMO"

It writes dashboard.gif and terminal.gif beside itself. Like shoot.py, whose
engine runs and headless Chrome it borrows, it reads the demo and nothing
else, and opens no window.

1. dashboard.gif is the engine's --html page as it opens: the chart drawing
   itself, a day picked out on it, the currency switched to pounds and back,
   then a scroll down through the sections. The page's own motion
   runs in real time, so each frame is taken on a clock; the pointer, the
   click and the scroll are sent over Chrome's DevTools protocol.
2. terminal.gif is two commands typed into a terminal window drawn as
   terminal_page.py draws the stills, with the engine's real output for
   each. Every frame is set from here, so it comes out the same every run.
   It opens on the first report and loops through the typing.

Both are scaled to 900 pixels wide at 10 frames a second with a palette of
their own. macOS only: it needs Google Chrome and ffmpeg. Python 3.9 or
later, standard library only.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import shoot  # noqa: E402
import terminal_page  # noqa: E402

FPS = 10
OUT_WIDTH = 900
# CSS pixels: shoot.py's dashboard width, and tall enough to hold the page
# from its title to the foot of the chart, so the first frame is the whole
# first screen and the chart is seen drawing itself.
VIEW = (1400, 1250)

# The terminal clip: each command as typed, and the arguments the engine gets.
COMMANDS = [("tokenmeter --period week --by day", ["--period", "week", "--by", "day"]),
            ("tokenmeter --by model", ["--by", "model"])]
COLUMNS = 104
ROWS = 36
PROMPT = '<span class="p">$</span> '

TERMINAL_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><style>
:root{--backdrop:#0a0b0d;--body:#14161a;--bar:#1b1e23;--edge:#2a2e35;
  --ink:#e6e8eb;--dim:#7d8590;--cyan:#5bc0d9;--green:#5cab7f;--yellow:#e0b44c;--clay:#d97757}
html,body{margin:0;background:var(--backdrop)}
body{padding:28px;display:inline-block}
.win{border:1px solid var(--edge);border-radius:12px;background:var(--body);overflow:hidden}
.bar{height:34px;background:var(--bar);border-bottom:1px solid var(--edge);display:flex;
  align-items:center;padding-left:14px}
.bar i{width:12px;height:12px;border-radius:50%;margin-right:8px;display:block}
.bar i:nth-child(1){background:#ff5f57}.bar i:nth-child(2){background:#febc2e}
.bar i:nth-child(3){background:#28c840}
.bar span{margin-left:12px;color:var(--dim);font:12px/1 -apple-system,"SF Pro Text",
  "Helvetica Neue",sans-serif}
pre{margin:0;padding:18px 12px 22px;color:var(--ink);width:COLUMNSch;height:HEIGHTpx;
  font:13.5px/20.25px "SF Mono",ui-monospace,Menlo,monospace;
  font-variant-ligatures:none;-webkit-font-smoothing:antialiased;overflow:hidden}
pre b{font-weight:700}
.blk{display:inline-block;height:14px;margin-top:4px;vertical-align:top;background:currentColor}
.d{color:var(--dim)}.c{color:var(--cyan)}.g{color:var(--green)}.y{color:var(--yellow)}
.p{color:var(--clay);font-weight:700}
.cur{display:inline-block;width:1ch;height:16px;margin-top:2px;vertical-align:top;background:var(--ink)}
</style></head>
<body><div class="win"><div class="bar"><i></i><i></i><i></i><span>tokenmeter</span></div>
<pre id="t"></pre></div></body></html>
"""

MEASURE = """JSON.stringify((function () {
  const view = document.querySelector('.view[data-view="all"]') || document.body;
  const hit = document.querySelector('.hit').getBoundingClientRect();
  return {sections: Array.prototype.slice.call(view.querySelectorAll('section'))
            .filter(s => s.parentElement === view)
            .map(s => s.getBoundingClientRect().top + window.scrollY),
          hit: [hit.left, hit.top, hit.width, hit.height],
          height: document.documentElement.scrollHeight};
})())"""


def ease(p: float) -> float:
    p = min(1.0, max(0.0, p))
    return p * p * (3 - 2 * p)


class Page(shoot.Browser):
    """shoot.py's Chrome, in a window the size of one clip frame."""

    def view(self, width: int, height: int) -> None:
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height,
                  deviceScaleFactor=1, mobile=False)

    def go(self, page: str) -> None:
        self.call("Page.enable")
        self.events = []
        if self.call("Page.navigate", url="file://" + page).get("errorText"):
            sys.exit(f"clip.py: Chrome could not open {page}")
        while "Page.loadEventFired" not in self.events:
            self.events.append(self.message().get("method"))

    def run(self, script: str):
        result = self.call("Runtime.evaluate", expression=script, returnByValue=True)
        if "exceptionDetails" in result:
            sys.exit("clip.py: the page refused a script: " + json.dumps(result["exceptionDetails"]))
        return result["result"].get("value")

    def frame(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(base64.b64decode(self.call("Page.captureScreenshot", format="png")["data"]))


def gif(frames: str, target: str) -> None:
    """The numbered frames as one looping GIF with a palette of its own."""
    out = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i",
         os.path.join(frames, "%04d.png"), "-vf",
         f"scale={OUT_WIDTH}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:"
         "stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle",
         "-loop", "0", target], capture_output=True, text=True)
    if out.returncode:
        sys.exit("clip.py: ffmpeg failed:\n" + out.stderr[-2000:])


def dashboard_clip(folder: str, target: str, work: str) -> None:
    page = os.path.join(work, "Tokenmeter.html")
    shoot.tokenmeter(folder, "--html", page, "--no-open")
    frames = os.path.join(work, "dashboard-frames")
    os.makedirs(frames)
    with Page(folder, "--force-dark-mode", "--blink-settings=preferredColorScheme=0",
              timeout=300) as browser:
        browser.view(*VIEW)
        browser.go(page)
        browser.run("try { localStorage.clear() } catch (e) {}")
        time.sleep(1.5)
        found = json.loads(browser.run(MEASURE))
        tops = found["sections"]
        left, top, width, height = found["hit"]
        last = found["height"] - VIEW[1]
        # (from second, to second, scroll from, scroll to)
        stops = [0, max(0, tops[1] - 40), min(last, tops[4] - 40)]
        scrolls = [(5.9, 6.9, stops[0], stops[1]), (8.1, 9.1, stops[1], stops[2])]
        clicks = {4.0: "GBP", 5.1: "USD"}
        # The first frame is taken once the headline figure has faded in,
        # because it is what a viewer that never plays the clip shows.
        first, total = 0.7, 10.3

        browser.go(page)
        started = time.monotonic()
        done = set()
        for i in range(int((total - first) * FPS)):
            t = first + i / FPS
            wait = started + t - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            if 2.0 <= t < 3.7:
                p = ease((t - 2.0) / 1.6)
                browser.call("Input.dispatchMouseEvent", type="mouseMoved",
                             x=left + width * (0.45 + 0.5 * p), y=top + height * 0.45)
            elif 3.7 <= t and "leave" not in done:
                done.add("leave")
                browser.call("Input.dispatchMouseEvent", type="mouseMoved", x=20, y=20)
            for at, cur in clicks.items():
                if t >= at and cur not in done:
                    done.add(cur)
                    browser.run(f"document.querySelector('.pill[data-cur=\"{cur}\"]').click()")
            for begin, end, a, b in scrolls:
                if begin <= t <= end + 1 / FPS:
                    y = a + (b - a) * ease((t - begin) / (end - begin))
                    browser.run(f"window.scrollTo(0, {y:.1f})")
            browser.frame(os.path.join(frames, f"{i:04d}.png"))
    gif(frames, target)


def rows_of(text: str) -> list:
    """The engine's output as the HTML rows terminal_page.py draws."""
    lines = text.replace("\r\n", "\n").strip("\n").split("\n")
    rows = []
    for line in lines:
        rows.extend(terminal_page.wrap(terminal_page.spans(line.rstrip()), COLUMNS))
    return [terminal_page.render_row(row) for row in rows]


def terminal_clip(folder: str, target: str, work: str) -> None:
    """A terminal ROWS tall. What is on screen is the last ROWS rows of
    everything typed and printed so far, as a real one scrolls."""
    states = []                      # one list of rows per frame

    def hold(rows: list, seconds: float) -> None:
        states.extend([rows] * round(seconds * FPS))

    screen = []
    opening = 0
    for typed, args in COMMANDS:
        out = rows_of(shoot.tokenmeter(folder, *args))
        hold(screen + [PROMPT + '<i class="cur"></i>'], 0.5)
        for n in range(2, len(typed) + 1, 2):
            states.append(screen + [PROMPT + html.escape(typed[:n]) + '<i class="cur"></i>'])
        hold(screen + [PROMPT + html.escape(typed) + '<i class="cur"></i>'], 0.4)
        screen = screen + [PROMPT + html.escape(typed)]
        hold(screen, 0.4)
        step = max(1, len(out) // 5)
        for n in range(step, len(out), step):
            states.append(screen + [""] + out[:n])
        screen = screen + [""] + out + [""]
        opening = opening or len(states)
        hold(screen + [PROMPT + '<i class="cur"></i>'], 3.6)
    # The clip opens on the first report, whole, because its first frame is
    # what a viewer that never plays it shows; the typing that led to it
    # comes round at the end.
    states = states[opening:] + states[:opening]

    page = os.path.join(work, "terminal.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(TERMINAL_PAGE.replace("COLUMNS", str(COLUMNS))
                .replace("HEIGHT", f"{ROWS * 20.25:.2f}"))
    frames = os.path.join(work, "terminal-frames")
    os.makedirs(frames)
    with Page(folder, timeout=300) as browser:
        browser.view(1600, 1200)
        browser.go(page)
        size = json.loads(browser.run(
            "JSON.stringify([document.body.getBoundingClientRect().width,"
            "document.body.getBoundingClientRect().height])"))
        browser.view(int(size[0] + 0.999), int(size[1] + 0.999))
        for i, rows in enumerate(states):
            shown = "\n".join(rows[-ROWS:])
            browser.run("document.getElementById('t').innerHTML = " + json.dumps(shown))
            browser.frame(os.path.join(frames, f"{i:04d}.png"))
    gif(frames, target)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Record the README's clips from a demo.")
    ap.add_argument("folder", help="a demo folder made by make_demo.py")
    ap.add_argument("--out", default=HERE, help="where the clips go (default: this folder)")
    ap.add_argument("--only", choices=("terminal", "dashboard"), default="",
                    help="record one clip only")
    args = ap.parse_args(argv)
    if not shutil.which("ffmpeg"):
        sys.exit("clip.py: ffmpeg is needed to join the frames (brew install ffmpeg)")
    folder = shoot.demo_folder(args.folder)
    os.makedirs(args.out, exist_ok=True)
    made = []
    with tempfile.TemporaryDirectory(dir=os.path.join(folder, "tmp")) as work:
        if args.only != "terminal":
            made.append(os.path.join(args.out, "dashboard.gif"))
            dashboard_clip(folder, made[-1], work)
        if args.only != "dashboard":
            made.append(os.path.join(args.out, "terminal.gif"))
            terminal_clip(folder, made[-1], work)
    for path in made:
        print(f"{path}  {os.path.getsize(path):,} bytes")


if __name__ == "__main__":
    main()
