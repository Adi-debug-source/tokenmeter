#!/usr/bin/env python3
"""
Take the README's screenshots from a demo made by make_demo.py.

    python3 docs/screenshots/make_demo.py /tmp/tokenmeter-demo --now 2026-10-16T17:40 --force
    python3 docs/screenshots/shoot.py /tmp/tokenmeter-demo

The second command rewrites six images in docs/screenshots: the three
terminal images and the three dashboard crops. menu-bar.png is captured by
hand from the menu bar app run against the same demo (MAINTENANCE.md says
how), then made plain like the others with

    python3 docs/screenshots/shoot.py --plain docs/screenshots/menu-bar.png

and icon.png is drawn from the app icon. Neither is otherwise touched here.

Every run of the engine here reads the demo and nothing else. The
environment it is given is built from scratch: the demo's (make_demo.py's
demo_env(), the one definition), the PATH, and nothing from the shell that
started it, so a TOKENMETER_ setting of your own cannot leak in. It refuses a
folder make_demo.py did not make. --check-prices reads each provider's
public pricing page, so that image needs the network; the others do not.

How each image is made
----------------------
1. A terminal image is the engine's output, captured with FORCE_COLOR=1 so
   its colours survive the pipe, drawn in a terminal window by
   terminal_page.py, and screenshotted by headless Chrome at twice the size.
   A first pass with --dump-dom reads the size the page asks for, so the
   second takes the window at exactly that size.
2. The dashboard is the engine's --html page, drawn by headless Chrome 1400
   CSS pixels wide at twice the size, in dark mode and with reduced motion,
   which shows every section at once instead of fading each in on scroll.
   It is measured and shot in one page, which shoot.py drives over Chrome's
   DevTools protocol (Browser). A script run in the page (SETTLE) marks
   every section as scrolled into view, as the page's own observer does
   when one is, because a heading's rule waits for that even with reduced
   motion; waits until both typefaces have loaded; and reads where each
   section sits until six readings 100 ms apart agree. The page is then
   shot whole, in a window as tall as itself, and each crop follows the
   sections. Before anything is written, check_edges() looks at the pixels:
   beyond every section edge a crop follows there must be bare page, and
   just inside it something drawn, both on the whole page and in the crop,
   so a crop that would start or end inside a section stops the run. Each
   crop is scaled to 1600 pixels wide and saved as a JPEG.
3. Every image is matched to sRGB with sips, then rewritten with nothing but
   what its format needs: a PNG keeps IHDR, IDAT, IEND and an sRGB mark, and
   a JPEG its JFIF header and the EXIF block that marks it sRGB. Nothing in
   a file names a device, a path or a person.

Headless Chrome can hang, so every call to it is given 60 seconds, and the
dashboard's page 120.

macOS only: it needs Google Chrome and sips. Python 3.9 or later, standard
library only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import make_demo  # noqa: E402
import terminal_page  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SRGB = "/System/Library/ColorSync/Profiles/sRGB Profile.icc"
SCALE = 2
DASH_WIDTH = 1400        # CSS pixels: the width the README's dashboard images show
JPEG_WIDTH = 1600        # pixels, as the README has always had them
JPEG_QUALITY = "60"      # sips' 0 to 100; about the file sizes the README has had

# (file, arguments): the terminal images. Each is drawn as a terminal 120
# columns wide, and a longer line wraps at a space (terminal_page.py).
TERMINAL = [
    ("terminal-report.png", ["--by", "model"]),
    ("terminal-adapters.png", ["--list-adapters"]),
    ("terminal-check-prices.png", ["--check-prices"]),
]
COLUMNS = 120

# Where each dashboard crop starts and ends, as (section, edge, offset in CSS
# pixels). Sections are the page's numbered sections, 1 to 6, in the first
# (all harnesses) view; 0 is the page's top. The offsets reproduce the
# margins of the README's first images.
CROPS = [
    ("dashboard-overview.jpg", (0, "top", 0), (1, "bottom", 20)),
    ("dashboard-breakdown.jpg", (2, "top", -21), (4, "bottom", 50)),
    ("dashboard-harnesses.jpg", (5, "top", 0), (6, "bottom", 19)),
]

# The typefaces the page embeds (FONTS in tokenmeter.py), at the ends of the
# weights each one covers. A face starts loading only when it is first
# needed, so the page is measured only once every one of them has loaded.
FACES = ['400 16px "Inter Tight"', '700 16px "Inter Tight"', '300 16px Fraunces',
         '700 16px Fraunces']

# Run in the dashboard by Browser.settle(). It marks every section as
# scrolled into view, as the page's own observer does when one is, because a
# heading's rule waits for that even with reduced motion; waits for the
# typefaces; then reads where each section sits every 100 ms until six
# readings in a row agree, so nothing is still moving.
SETTLE = """new Promise(function (done) {
  document.querySelectorAll('.fade,.reveal-on').forEach(el => el.classList.add('reveal'));
  function measure() {
    const view = document.querySelector('.view[data-view="all"]') || document.body;
    return JSON.stringify({height: Math.ceil(document.documentElement.scrollHeight),
      sections: Array.prototype.slice.call(view.querySelectorAll('section'))
        .filter(s => s.parentElement === view).map(function (s) {
          const r = s.getBoundingClientRect();
          return [r.top + window.scrollY, r.bottom + window.scrollY];
        })});
  }
  const started = performance.now();
  Promise.all(FACES.map(f => document.fonts.load(f))).then(() => document.fonts.ready)
    .then(function () {
      let last = '', same = 0;
      (function poll() {
        const now = measure();
        same = now === last ? same + 1 : 0;
        last = now;
        if (same < 5 && performance.now() - started < 15000) {
          setTimeout(() => requestAnimationFrame(poll), 100);
          return;
        }
        const faces = [];
        document.fonts.forEach(f => faces.push(f.family.replace(/["']/g, '') + ' ' + f.status));
        done(JSON.stringify({boxes: JSON.parse(now), settled: same >= 5, faces: faces}));
      })();
    });
})""".replace("FACES", json.dumps(FACES))


def demo_folder(path: str) -> str:
    folder = os.path.abspath(path)
    if not os.path.isfile(os.path.join(folder, make_demo.MARKER)):
        sys.exit(f"shoot.py: {path} is not a demo made by make_demo.py")
    return folder


def engine_env(folder: str) -> dict:
    """A from-scratch environment that reads the demo and nothing else, with
    the colours kept for a pipe."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "en_GB.UTF-8",
           "PYTHONIOENCODING": "utf-8", "TMPDIR": os.path.join(folder, "tmp")}
    os.makedirs(env["TMPDIR"], exist_ok=True)
    env.update(make_demo.demo_env(folder))
    env["FORCE_COLOR"] = "1"
    return env


def tokenmeter(folder: str, *args: str) -> str:
    out = subprocess.run([sys.executable, os.path.join(REPO, "tokenmeter.py"), *args],
                         env=engine_env(folder), cwd=folder, capture_output=True, text=True,
                         timeout=600)
    if out.returncode:
        sys.exit(f"shoot.py: tokenmeter.py {' '.join(args)} failed:\n{out.stderr}")
    return out.stdout


def chrome_command(folder: str) -> list:
    """Headless Chrome with a profile of its own inside the demo folder."""
    return [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            f"--user-data-dir={os.path.join(folder, 'chrome-profile')}", "--no-first-run",
            "--no-default-browser-check"]


def chrome(folder: str, *args: str, timeout: int = 60) -> str:
    """One page in headless Chrome, as the command line drives it, stopped
    after `timeout` seconds if it hangs."""
    cmd = ["perl", "-e", f"alarm {timeout}; exec @ARGV", *chrome_command(folder),
           f"--force-device-scale-factor={SCALE}",
           # Every frame finished before it is drawn: without it the masthead's
           # first line was missing from one capture in three.
           "--run-all-compositor-stages-before-draw", *args]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"shoot.py: Chrome failed or hung: {' '.join(args[-2:])}\n{out.stderr[-2000:]}")
    return out.stdout


def dumped(folder: str, page: str, attr: str, size: str, *flags: str) -> str:
    """The value of an attribute a page's own script set on its root element,
    read from the page as Chrome lays it out in a window of `size`."""
    dom = chrome(folder, *flags, f"--window-size={size}", "--virtual-time-budget=4000",
                 "--dump-dom", "file://" + page)
    m = re.search(attr + r'="([^"]*)"', dom)
    if not m:
        sys.exit(f"shoot.py: no {attr} in {page}")
    return m.group(1).replace("&quot;", '"')


class Browser:
    """One page in headless Chrome, driven over the DevTools protocol on a
    pipe: Chrome reads commands on its descriptor 3 and answers on 4, which
    sh joins to this process's pipes. The dashboard is measured and shot in
    this one page. Read in one run of Chrome and shot in another, under
    --virtual-time-budget, the boxes were taken before the embedded
    typefaces reached the layout, at a moment no script in the page could
    see, and the crops cut through sections."""

    def __init__(self, folder: str, *flags: str, timeout: int = 120):
        self.proc = subprocess.Popen(
            ["perl", "-e", f"alarm {timeout}; exec @ARGV", "sh", "-c",
             'exec "$@" 3<&0 4>&1 0</dev/null 1>/dev/null', "sh", *chrome_command(folder),
             "--remote-debugging-pipe", *flags, "about:blank"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.waiting, self.events, self.count, self.session = b"", [], 0, None
        try:
            target = self.call("Target.createTarget", url="about:blank")["targetId"]
            self.session = self.call("Target.attachToTarget", targetId=target,
                                     flatten=True)["sessionId"]
        except BaseException:
            self.stop()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    def stop(self) -> None:
        """Chrome closed, whether the run worked or stopped."""
        if self.proc.poll() is None:
            try:
                self.call("Browser.close")
                self.proc.wait(timeout=30)
            except (OSError, SystemExit, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait()
        self.proc.stdin.close()
        self.proc.stdout.close()

    def message(self) -> dict:
        while b"\0" not in self.waiting:
            chunk = os.read(self.proc.stdout.fileno(), 1 << 20)
            if not chunk:
                sys.exit("shoot.py: Chrome stopped or hung while drawing the dashboard")
            self.waiting += chunk
        text, self.waiting = self.waiting.split(b"\0", 1)
        return json.loads(text)

    def call(self, method: str, **params) -> dict:
        self.count += 1
        sent = {"id": self.count, "method": method, "params": params}
        if self.session and not method.startswith("Browser."):
            sent["sessionId"] = self.session
        self.proc.stdin.write(json.dumps(sent).encode() + b"\0")
        self.proc.stdin.flush()
        while True:
            got = self.message()
            if got.get("id") == self.count:
                if "error" in got:
                    sys.exit(f"shoot.py: Chrome refused {method}: {got['error']}")
                return got["result"]
            self.events.append(got.get("method"))

    def open(self, page: str, height: int) -> None:
        self.size(height)
        self.call("Page.enable")
        self.events = []
        if self.call("Page.navigate", url="file://" + page).get("errorText"):
            sys.exit(f"shoot.py: Chrome could not open {page}")
        while "Page.loadEventFired" not in self.events:
            self.events.append(self.message().get("method"))

    def size(self, height: int) -> None:
        self.call("Emulation.setDeviceMetricsOverride", width=DASH_WIDTH, height=height,
                  deviceScaleFactor=SCALE, mobile=False)

    def settle(self) -> dict:
        """Where each section sits, once the page has its typefaces and has
        stopped moving (SETTLE)."""
        result = self.call("Runtime.evaluate", expression=SETTLE, awaitPromise=True,
                           returnByValue=True)
        if "exceptionDetails" in result:
            sys.exit("shoot.py: the dashboard could not be measured: "
                     + json.dumps(result["exceptionDetails"]))
        found = json.loads(result["result"]["value"])
        families = sorted({face.split(" ", 2)[2].strip('"') for face in FACES})
        missing = [f for f in families if f + " loaded" not in found["faces"]]
        if missing:
            sys.exit("shoot.py: the dashboard did not load its typefaces: " + ", ".join(missing))
        if not found["settled"]:
            sys.exit("shoot.py: the dashboard's sections were still moving after 15 seconds")
        return found["boxes"]

    def shot(self, path: str, top: int = 0, height: int = 0) -> None:
        """The page from `top`, `height` CSS pixels of it, or all of it."""
        params = {"format": "png"}
        if height:
            params["clip"] = {"x": 0, "y": top, "width": DASH_WIDTH, "height": height,
                              "scale": 1}
        with open(path, "wb") as f:
            f.write(base64.b64decode(self.call("Page.captureScreenshot", **params)["data"]))


def sips(*args: str) -> None:
    out = subprocess.run(["sips", *args], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"shoot.py: sips {' '.join(args)} failed:\n{out.stderr}")


# MARK: - Metadata

def plain_png(path: str) -> None:
    """Rewrite a PNG as IHDR, an sRGB mark, one IDAT and IEND, nothing else.
    The image data is compressed again at zlib's highest level; the pixels
    and the filters sips chose are unchanged."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        sys.exit(f"shoot.py: {path} is not a PNG")
    pos, header, image = 8, None, []
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IHDR":
            header = data[pos:pos + 12 + length]
        elif kind == b"IDAT":
            image.append(data[pos + 8:pos + 8 + length])
        pos += 12 + length
    if header is None or not image:
        sys.exit(f"shoot.py: could not read {path}")
    pixels = zlib.compress(zlib.decompress(b"".join(image)), 9)
    with open(path, "wb") as f:
        f.write(data[:8] + header + png_chunk(b"sRGB", b"\x00") + png_chunk(b"IDAT", pixels)
                + png_chunk(b"IEND", b""))


def png_chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(
        ">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def png_chunks(path: str) -> list:
    with open(path, "rb") as f:
        data = f.read()
    pos, kinds = 8, []
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        kinds.append(kind.decode("ascii"))
        pos += 12 + length
    return kinds


# The only EXIF tags a JPEG may keep: the pointer to the EXIF directory, the
# colour space (sRGB) and the pixel size, which is all sips writes.
EXIF_ALLOWED = {0x8769: "ExifIFD", 0xA001: "ColorSpace", 0xA002: "PixelXDimension",
                0xA003: "PixelYDimension"}


def exif_tags(segment: bytes) -> list:
    """Every tag in an APP1 EXIF segment's directories, the EXIF one
    included."""
    tiff = segment[10:]
    order = {b"MM": ">", b"II": "<"}.get(tiff[:2])
    if order is None:
        return [-1]
    tags, todo, seen = [], [struct.unpack(order + "I", tiff[4:8])[0]], set()
    while todo:
        at = todo.pop()
        if at in seen or at + 2 > len(tiff):
            continue
        seen.add(at)
        count = struct.unpack(order + "H", tiff[at:at + 2])[0]
        for i in range(count):
            entry = tiff[at + 2 + 12 * i:at + 14 + 12 * i]
            tag, _kind, _n, value = struct.unpack(order + "HHII", entry)
            tags.append(tag)
            if tag == 0x8769:
                todo.append(value)
        following = at + 2 + 12 * count
        if following + 4 <= len(tiff):
            nxt = struct.unpack(order + "I", tiff[following:following + 4])[0]
            if nxt:
                todo.append(nxt)
    return tags


def plain_jpeg(path: str) -> None:
    """Rewrite a JPEG with nothing but its image and two small marks: JFIF,
    and the EXIF block sips writes, which says sRGB and the pixel size and
    nothing else, as exif_tags() checks; a tag beyond those stops the run.
    XMP, comments, ICC profiles and every other application segment go."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"\xff\xd8":
        sys.exit(f"shoot.py: {path} is not a JPEG")
    out, pos = [data[:2]], 2
    while pos < len(data):
        if data[pos] != 0xFF:
            sys.exit(f"shoot.py: could not read the segments of {path}")
        marker = data[pos + 1]
        if marker == 0xDA:                       # start of scan: the rest is image data
            out.append(data[pos:])
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        segment = data[pos:pos + 2 + length]
        if marker == 0xE0 and segment[4:9] == b"JFIF\x00":
            out.append(segment)
        elif marker == 0xE1 and segment[4:10] == b"Exif\x00\x00":
            extra = [t for t in exif_tags(segment) if t not in EXIF_ALLOWED]
            if extra:
                sys.exit(f"shoot.py: {path} has EXIF tags beyond the colour space and size: "
                         + ", ".join(hex(t) for t in extra))
            out.append(segment)
        elif not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            out.append(segment)                  # tables and the frame header
        pos += 2 + length
    with open(path, "wb") as f:
        f.write(b"".join(out))


def jpeg_segments(path: str) -> list:
    with open(path, "rb") as f:
        data = f.read()
    pos, names = 2, []
    while pos < len(data) and data[pos] == 0xFF:
        marker = data[pos + 1]
        if marker == 0xDA:
            names.append("SOS")
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        tag = data[pos + 4:pos + 4 + 12].split(b"\x00")[0].decode("latin-1")
        names.append(f"APP{marker - 0xE0}:{tag}" if 0xE0 <= marker <= 0xEF else f"{marker:02X}")
        pos += 2 + length
    return names


# MARK: - The images

def terminal_images(folder: str, out_dir: str, work: str) -> list:
    made = []
    for name, args in TERMINAL:
        text = tokenmeter(folder, *args)
        with open(os.path.join(work, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
        page = os.path.join(work, name + ".html")
        with open(page, "w", encoding="utf-8") as f:
            f.write(terminal_page.page(text, "python3 tokenmeter.py " + " ".join(args), COLUMNS))
        size = dumped(folder, page, "data-size", "3000,3000")
        raw = os.path.join(work, name)
        chrome(folder, f"--window-size={size}", f"--screenshot={raw}", "file://" + page)
        target = os.path.join(out_dir, name)
        sips("--matchTo", SRGB, raw, "--out", target)
        plain_png(target)
        made.append(target)
    return made


# What check_edges() counts as drawn. The page's ground is #090a0c under a
# grain that lifts a channel to 21 at most; the faintest thing a section
# draws at its edges, a 1 pixel rule in --line (#212429), reaches 41.
INK = 28
CLEAR = 40   # CSS pixels: sections stand 52 apart, and this much beyond an edge must be bare
REACH = 8    # CSS pixels: a section draws this close inside its edge; a heading's text is 5.5 in


def drawn_rows(png: str, work: str) -> list:
    """For each row of pixels in a PNG, whether anything is drawn in it.
    sips turns the PNG into an uncompressed 24-bit BMP, whose rows can be
    read as they are."""
    bmp = os.path.join(work, "rows.bmp")
    sips("-s", "format", "bmp", png, "--out", bmp)
    try:
        with open(bmp, "rb") as f:
            data = f.read()
    finally:
        os.remove(bmp)
    start = struct.unpack("<I", data[10:14])[0]
    width, height = struct.unpack("<ii", data[18:26])
    if data[:2] != b"BM" or struct.unpack("<H", data[28:30])[0] != 24:
        sys.exit(f"shoot.py: could not read the pixels of {png}")
    stride = (width * 3 + 3) & ~3
    rows = [max(data[at:at + width * 3]) > INK
            for at in range(start, start + abs(height) * stride, stride)]
    return rows if height < 0 else rows[::-1]


def check_edges(rows: list, origin: int, picture: str, edges: list) -> None:
    """Stop the run unless a picture shows each section edge a crop follows
    where it was measured: bare beyond the edge, for CLEAR pixels or the
    crop's whole margin if that is more, and something drawn within REACH
    pixels inside it. `rows` are the picture's drawn_rows(), and its first
    row is `origin` CSS pixels down the page; a band is checked as far as
    the picture reaches. Boxes that do not match the picture put a crop's
    edge inside a section, which fails one test or the other."""
    def any_drawn(a: float, b: float) -> bool:
        a, b = int((a - origin) * SCALE), int((b - origin) * SCALE)
        return any(rows[max(0, a):max(0, min(len(rows), b))])

    for at, side, offset in edges:
        margin = max(CLEAR, abs(offset))
        if side == "top":
            beyond, inside = any_drawn(at - margin, at - 1), any_drawn(at, at + REACH)
        else:
            beyond, inside = any_drawn(at + 1, at + margin), any_drawn(at - REACH, at)
        if beyond or not inside:
            found = "something is drawn beyond it" if beyond else "nothing is drawn inside it"
            sys.exit(f"shoot.py: {picture} does not show a section's {side} at {at:.1f} CSS "
                     f"pixels, where it was measured: {found}")


def dashboard_images(folder: str, out_dir: str, work: str) -> list:
    page = os.path.join(work, "Tokenmeter.html")
    tokenmeter(folder, "--html", page, "--no-open")
    with Browser(folder, "--force-dark-mode", "--blink-settings=preferredColorScheme=0",
                 "--force-prefers-reduced-motion") as browser:
        return dashboard_crops(browser, page, out_dir, work)


def dashboard_crops(browser: Browser, page: str, out_dir: str, work: str) -> list:
    browser.open(page, 1200)
    boxes = browser.settle()
    # Then a window as tall as the page, so the page's grain, which is fixed
    # to the window, covers all of it, as it does on screen.
    for _ in range(3):
        browser.size(boxes["height"])
        settled = browser.settle()
        if settled == boxes:
            break
        boxes = settled
    else:
        sys.exit("shoot.py: the dashboard did not keep one height in a window as tall as itself")
    sections = [(0.0, 0.0)] + [tuple(b) for b in boxes["sections"]]
    full = os.path.join(work, "dashboard-full.png")
    browser.shot(full)
    rows = drawn_rows(full, work)

    def edge(spec):
        index, side, offset = spec
        return sections[index][0 if side == "top" else 1] + offset

    crops = []
    for name, top_spec, bottom_spec in CROPS:
        edges = [(sections[i][0 if side == "top" else 1], side, offset)
                 for i, side, offset in (top_spec, bottom_spec) if i]
        check_edges(rows, 0, f"the whole dashboard, around {name}", edges)
        crops.append((name, round(edge(top_spec)), round(edge(bottom_spec)), edges))
    # Each crop is checked again as it is shot, since that is what the README
    # shows, and nothing is written until all of them pass.
    for name, top, bottom, edges in crops:
        raw = os.path.join(work, name.replace(".jpg", ".png"))
        browser.shot(raw, top, bottom - top)
        check_edges(drawn_rows(raw, work), top, name, edges)
    if browser.settle() != boxes:
        sys.exit("shoot.py: the dashboard's sections moved while it was shot")
    made = []
    for name, *_ in crops:
        raw = os.path.join(work, name.replace(".jpg", ".png"))
        target = os.path.join(out_dir, name)
        sips("--matchTo", SRGB, raw, "--out", raw)
        sips("--resampleWidth", str(JPEG_WIDTH), raw, "--out", raw)
        sips("-s", "format", "jpeg", "-s", "formatOptions", JPEG_QUALITY, raw, "--out", target)
        plain_jpeg(target)
        made.append(target)
    return made


def plain(path: str) -> None:
    """An image made by hand, such as the menu bar capture, made plain as
    shoot.py's own are: matched to sRGB from whatever display profile it
    carries, then rewritten with only what its format needs."""
    sips("--matchTo", SRGB, path, "--out", path)
    if path.lower().endswith(".png"):
        plain_png(path)
    else:
        plain_jpeg(path)


def report(paths: list) -> None:
    for path in paths:
        w, h = (re.search(r"pixel%s: (\d+)" % k, subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
            capture_output=True, text=True).stdout).group(1) for k in ("Width", "Height"))
        parts = png_chunks(path) if path.lower().endswith(".png") else jpeg_segments(path)
        where = os.path.relpath(path, REPO) if path.startswith(REPO) else path
        print(f"{where}  {w} x {h}  {os.path.getsize(path):,} bytes  {' '.join(parts)}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Take the README's screenshots from a demo.")
    ap.add_argument("folder", nargs="?", help="a demo folder made by make_demo.py")
    ap.add_argument("--out", default=HERE, help="where the images go (default: this folder)")
    ap.add_argument("--only", choices=("terminal", "dashboard"), default="",
                    help="take one kind of image only")
    ap.add_argument("--plain", nargs="+", metavar="IMAGE", default=[],
                    help="instead, make these images plain sRGB with no metadata, "
                         "as for the menu bar capture")
    args = ap.parse_args(argv)

    if args.plain:
        paths = [os.path.abspath(p) for p in args.plain]
        for path in paths:
            plain(path)
        report(paths)
        return
    if not args.folder:
        ap.error("give the demo folder, or --plain with images")
    folder = demo_folder(args.folder)
    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(folder, "shots")
    os.makedirs(work, exist_ok=True)
    made = []
    if args.only != "dashboard":
        made += terminal_images(folder, args.out, work)
    if args.only != "terminal":
        made += dashboard_images(folder, args.out, work)
    report(made)


if __name__ == "__main__":
    main()
