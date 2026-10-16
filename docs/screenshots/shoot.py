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
   The page is shot from a copy with one script added at its end, which
   does two things and changes nothing else: it marks every section as
   scrolled into view, as the page's own observer does when one is, because
   a heading's rule waits for that even with reduced motion and headless
   Chrome sometimes shot the page first; and it records where each section
   sits, which the crops follow. Each crop is scaled to 1600 pixels wide
   and saved as a JPEG.
3. Every image is matched to sRGB with sips, then rewritten with nothing but
   what its format needs: a PNG keeps IHDR, IDAT, IEND and an sRGB mark, and
   a JPEG its JFIF header and the EXIF block that marks it sRGB. Nothing in
   a file names a device, a path or a person.

Headless Chrome can hang, so every call to it is given 60 seconds.

macOS only: it needs Google Chrome and sips. Python 3.9 or later, standard
library only.
"""

from __future__ import annotations

import argparse
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

SHOT_SCRIPT = """<script>
document.querySelectorAll('.fade,.reveal-on').forEach(el => el.classList.add('reveal'));
document.fonts.ready.then(function () {
  function box(el) {
    const r = el.getBoundingClientRect();
    return [r.top + window.scrollY, r.bottom + window.scrollY];
  }
  const view = document.querySelector('.view[data-view="all"]') || document.body;
  const sections = Array.prototype.slice.call(view.querySelectorAll('section'))
    .filter(s => s.parentElement === view).map(box);
  document.documentElement.dataset.boxes = JSON.stringify({
    height: Math.ceil(document.documentElement.scrollHeight), sections: sections});
});
</script>"""


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


def chrome(folder: str, *args: str, timeout: int = 60) -> str:
    """Headless Chrome with a profile of its own inside the demo folder,
    stopped after `timeout` seconds if it hangs."""
    cmd = ["perl", "-e", f"alarm {timeout}; exec @ARGV", CHROME, "--headless=new",
           "--disable-gpu", "--hide-scrollbars", f"--force-device-scale-factor={SCALE}",
           # Every frame finished before it is drawn: without it the masthead's
           # first line was missing from one capture in three.
           "--run-all-compositor-stages-before-draw",
           f"--user-data-dir={os.path.join(folder, 'chrome-profile')}", "--no-first-run",
           "--no-default-browser-check", *args]
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


def dashboard_images(folder: str, out_dir: str, work: str) -> list:
    page = os.path.join(work, "Tokenmeter.html")
    tokenmeter(folder, "--html", page, "--no-open")
    with open(page, encoding="utf-8") as f:
        html = f.read()
    shot = os.path.join(work, "Tokenmeter-shot.html")
    with open(shot, "w", encoding="utf-8") as f:
        f.write(html.replace("</body>", SHOT_SCRIPT + "</body>"))
    look = ["--force-dark-mode", "--blink-settings=preferredColorScheme=0",
            "--force-prefers-reduced-motion"]
    # Measured at the width the screenshots are taken at, or the text wraps
    # differently and every box is somewhere else.
    boxes = json.loads(dumped(folder, shot, "data-boxes", f"{DASH_WIDTH},1200", *look))
    sections = [(0.0, 0.0)] + [tuple(b) for b in boxes["sections"]]

    def edge(spec):
        index, side, offset = spec
        return sections[index][0 if side == "top" else 1] + offset

    made = []
    for name, top_spec, bottom_spec in CROPS:
        top, bottom = round(edge(top_spec)), round(edge(bottom_spec))
        raw = os.path.join(work, name.replace(".jpg", ".png"))
        if top == 0:
            # sips cannot crop from the very top (an offset of 0 0 means
            # centred), so the top crop is a window of exactly its height.
            chrome(folder, *look, f"--window-size={DASH_WIDTH},{bottom}",
                   "--virtual-time-budget=4000", f"--screenshot={raw}", "file://" + shot)
        else:
            full = os.path.join(work, "dashboard-full.png")
            if not os.path.exists(full):
                chrome(folder, *look, f"--window-size={DASH_WIDTH},{boxes['height']}",
                       "--virtual-time-budget=4000", f"--screenshot={full}", "file://" + shot)
            sips("-c", str((bottom - top) * SCALE), str(DASH_WIDTH * SCALE),
                 "--cropOffset", str(top * SCALE), "0", full, "--out", raw)
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
    for name in os.listdir(work):
        if name == "dashboard-full.png":
            os.remove(os.path.join(work, name))
    made = []
    if args.only != "dashboard":
        made += terminal_images(folder, args.out, work)
    if args.only != "terminal":
        made += dashboard_images(folder, args.out, work)
    report(made)


if __name__ == "__main__":
    main()
