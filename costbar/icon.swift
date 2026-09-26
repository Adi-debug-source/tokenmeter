// Draws the Tokenmeter app icon and writes a full .iconset.
//
// Source rather than a binary blob, so the icon can be changed by editing
// numbers and rebuilt on any Mac with the command line tools. Every size is
// drawn as vectors at its own resolution rather than downsampled from one
// large bitmap, which is what keeps the 16pt version from turning to mud.
//
//   swiftc -O -o /tmp/mkicon icon.swift && /tmp/mkicon out.iconset
//
// The picture is a T whose crossbar is a meter: the solid part is the
// reading so far, a clay tick marks where it stands, and the rest of the
// scale is a groove the reading has yet to travel. It is drawn in the macOS
// 26 dark icon style: a graphite body lit from above, the glyph lifted off it
// by a soft shadow, and one accent that gives off light, the way Stocks and
// Activity Monitor light theirs.

import AppKit
import Foundation

func hex(_ h: UInt32, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((h >> 16) & 0xff) / 255, green: CGFloat((h >> 8) & 0xff) / 255,
            blue: CGFloat(h & 0xff) / 255, alpha: a)
}

let BODY_HI = hex(0x2B2F36)   // graphite, top
let BODY_LO = hex(0x0E1013)   // graphite, bottom
let INK_HI  = hex(0xFFFFFF)   // the T, top
let INK_LO  = hex(0xC3C8D0)   // the T, bottom
let GROOVE  = hex(0x07080A)
// The reading is the dashboard's accent, exactly: --acc2 at the top, the
// chart bars' foot at the bottom, and --acc for its light. Change them together.
let ACC_HI  = hex(0xE8916F)   // the reading, top
let ACC_LO  = hex(0xC9663F)   // the reading, bottom
let GLOW    = hex(0xD97757)   // light the reading gives off

/// Apple's icon outline is a squircle, not a rounded rectangle. Circular
/// corners read as subtly wrong beside native icons, and the difference is
/// most visible at large sizes in the Dock. macOS 26 and later re-mask an
/// icon to their own shape and add a glass edge, but only when the icon
/// already follows this outline; otherwise it is shrunk onto a grey tile.
func squircle(in r: CGRect, n: CGFloat = 5) -> NSBezierPath {
    let p = NSBezierPath()
    let a = r.width / 2, b = r.height / 2
    let cx = r.midX, cy = r.midY
    let steps = 720
    for i in 0...steps {
        let t = CGFloat(i) / CGFloat(steps) * 2 * .pi
        let ct = cos(t), st = sin(t)
        let x = cx + a * pow(abs(ct), 2 / n) * (ct < 0 ? -1 : 1)
        let y = cy + b * pow(abs(st), 2 / n) * (st < 0 ? -1 : 1)
        if i == 0 { p.move(to: CGPoint(x: x, y: y)) } else { p.line(to: CGPoint(x: x, y: y)) }
    }
    p.close()
    return p
}

/// A polygon with its own corner radius at each vertex; zero for a sharp one.
func roundedPolygon(_ pts: [CGPoint], _ radii: [CGFloat], into p: NSBezierPath) {
    let n = pts.count
    p.move(to: CGPoint(x: (pts[n - 1].x + pts[0].x) / 2, y: (pts[n - 1].y + pts[0].y) / 2))
    for i in 0..<n {
        if radii[i] <= 0 { p.line(to: pts[i]) }
        else { p.appendArc(from: pts[i], to: pts[(i + 1) % n], radius: radii[i]) }
    }
    p.close()
}

func withShadow(_ color: NSColor, blur: CGFloat, dy: CGFloat, _ body: () -> Void) {
    NSGraphicsContext.saveGraphicsState()
    let sh = NSShadow()
    sh.shadowColor = color
    sh.shadowBlurRadius = blur
    sh.shadowOffset = NSSize(width: 0, height: dy)
    sh.set()
    body()
    NSGraphicsContext.restoreGraphicsState()
}

/// One icon at one size. `s` is the edge length in pixels. The mark is laid
/// out on a 1024 unit grid, origin top left, and mapped to pixels; below
/// 128px every edge is rounded to a whole pixel so small sizes stay crisp.
func drawIcon(size s: CGFloat) -> NSImage {
    let img = NSImage(size: NSSize(width: s, height: s))
    img.lockFocus()
    let ctx = NSGraphicsContext.current!
    ctx.imageInterpolation = .high
    ctx.shouldAntialias = true

    let k = s / 1024
    let snap = s < 128
    func X(_ x: CGFloat) -> CGFloat { snap ? (x * k).rounded() : x * k }
    func Y(_ y: CGFloat) -> CGFloat { snap ? (s - y * k).rounded() : s - y * k }
    func P(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: X(x), y: Y(y)) }
    func R(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat) -> CGRect {
        let x0 = X(x), x1 = X(x + w), y0 = Y(y + h), y1 = Y(y)
        return CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
    }

    // Apple's grid: the shape occupies 824 of a 1024 canvas, leaving room for
    // the shadow the system expects an icon to carry itself.
    let inset = s * 0.098
    let box = CGRect(x: inset, y: inset * 1.14, width: s - inset * 2, height: s - inset * 2)
    let shape = squircle(in: box)

    withShadow(NSColor.black.withAlphaComponent(0.5), blur: s * 0.03, dy: -s * 0.012) {
        BODY_LO.setFill()
        shape.fill()
    }

    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    NSGradient(starting: BODY_HI, ending: BODY_LO)!.draw(in: box, angle: -90)
    // Light from above: a broad, faint pool at the top centre. Drawn over a
    // box larger than the icon, not a sub-rectangle: a radial gradient is only
    // transparent at the edge of the rect it is given, so a smaller rect
    // leaves a visible seam where it stops.
    NSGradient(colorsAndLocations: (NSColor.white.withAlphaComponent(0.075), 0),
               (NSColor.white.withAlphaComponent(0.0), 1))!
        .draw(in: box.insetBy(dx: -box.width * 0.25, dy: -box.height * 0.25),
              relativeCenterPosition: CGPoint(x: 0, y: 0.75))

    // ---- the mark ----------------------------------------------------------
    // Sat a little below the body's centre, because the crossbar makes a T
    // top heavy. The crossbar is thinner than the stem, as in a typeface:
    // equal strokes make the horizontal look the heavier of the two.
    let cy = 1024 - (inset * 1.14 + box.height / 2) / k
    let H: CGFloat = 424
    let top = cy + 16 - H / 2
    let barL: CGFloat = 228, barR: CGFloat = 796, barH: CGFloat = 88
    let barB = top + barH
    let stemW: CGFloat = 104, foot = top + H
    let stemL = 512 - stemW / 2, stemR = 512 + stemW / 2
    let reading: CGFloat = 626
    let term = 22 * k

    if s < 32 {
        // Sixteen pixels: a plain T on whole pixels. A meter cannot survive
        // at this size, and a tick one pixel wide only makes the T look broken.
        let path = NSBezierPath()
        let bh = 2 / k, sw = 2 / k
        path.append(NSBezierPath(rect: R(barL + 24, top + 16, barR - barL - 48, bh)))
        path.append(NSBezierPath(rect: R(512 - sw / 2, top + 16, sw, H - 40)))
        hex(0xF2F4F6).setFill()
        path.fill()
    } else {
        // The groove the reading travels along, milled into the body. Lit from
        // above, so its upper edge is in shadow and its lower lip catches a
        // sliver of light.
        let groove = NSBezierPath()
        roundedPolygon([P(barL, top), P(barR, top), P(barR, barB), P(barL, barB)],
                       [term, term, term, term], into: groove)
        GROOVE.setFill()
        groove.fill()
        NSGraphicsContext.saveGraphicsState()
        groove.addClip()
        let outside = NSBezierPath(rect: box.insetBy(dx: -s, dy: -s))
        outside.append(groove)
        outside.windingRule = .evenOdd
        withShadow(NSColor.black.withAlphaComponent(0.9), blur: s * 0.012, dy: -s * 0.006) {
            NSColor.black.setFill()
            outside.fill()
        }
        withShadow(NSColor.white.withAlphaComponent(0.10), blur: s * 0.002, dy: s * 0.003) {
            NSColor.black.setFill()
            outside.fill()
        }
        // Light from the reading, spilling a short way down the groove.
        NSGradient(starting: GLOW.withAlphaComponent(0.30), ending: GLOW.withAlphaComponent(0))!
            .draw(in: R(reading, top, 170, barH), angle: 0)
        NSGraphicsContext.restoreGraphicsState()

        // The T: the reading so far and the stem, one shape, lifted off the
        // body by its shadow. The stem starts inside the crossbar so the two
        // join without a seam.
        let ink = NSBezierPath()
        roundedPolygon([P(barL, top), P(reading, top), P(reading, barB), P(barL, barB)],
                       [term, 0, 0, term], into: ink)
        roundedPolygon([P(stemL, top + 10), P(stemR, top + 10), P(stemR, foot), P(stemL, foot)],
                       [0, 0, term, term], into: ink)
        withShadow(NSColor.black.withAlphaComponent(0.55), blur: s * 0.022, dy: -s * 0.010) {
            INK_LO.setFill()
            ink.fill()
        }
        NSGraphicsContext.saveGraphicsState()
        ink.addClip()
        // The gradient covers the whole glyph's box, so the crossbar and the
        // stem read as one piece of material.
        NSGradient(starting: INK_HI, ending: INK_LO)!.draw(in: ink.bounds, angle: -90)
        // A faint shade along the crossbar's underside, where it turns away
        // from the light, so the glyph reads as a solid rather than a sticker.
        NSGradient(starting: NSColor.black.withAlphaComponent(0),
                   ending: NSColor.black.withAlphaComponent(0.10))!
            .draw(in: R(barL, top, reading - barL, barH), angle: -90)
        if s >= 128 {
            // The specular edge along the top; below 128px it is under a pixel.
            NSColor.white.withAlphaComponent(0.95).setFill()
            NSBezierPath(rect: R(barL, top, reading - barL, 3)).fill()
        }
        NSGraphicsContext.restoreGraphicsState()

        // The reading: the one accent, and the only thing that gives off
        // light. It stands proud of the crossbar above and below, like the
        // cursor on an instrument.
        let tw = max(16, 1.6 / k), over: CGFloat = 30
        let tickR = R(reading - tw / 2, top - over, tw, barH + over * 2)
        let tick = NSBezierPath(roundedRect: tickR, xRadius: tickR.width / 2, yRadius: tickR.width / 2)
        withShadow(GLOW.withAlphaComponent(0.85), blur: s * 0.035, dy: 0) { GLOW.setFill(); tick.fill() }
        withShadow(GLOW.withAlphaComponent(0.6), blur: s * 0.012, dy: 0) { GLOW.setFill(); tick.fill() }
        NSGraphicsContext.saveGraphicsState()
        tick.addClip()
        NSGradient(starting: ACC_HI, ending: ACC_LO)!.draw(in: tickR, angle: -90)
        NSGraphicsContext.restoreGraphicsState()
    }
    NSGraphicsContext.restoreGraphicsState()

    // A hairline edge, the thing that stops a dark icon looking like a hole
    // on macOS 12 to 15, which show the icon exactly as drawn. macOS 26 and
    // later draw their own glass edge over it.
    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    let rim = squircle(in: box.insetBy(dx: s * 0.002, dy: s * 0.002))
    rim.lineWidth = max(s * 0.004, 0.5)
    NSColor.white.withAlphaComponent(0.07).setStroke()
    rim.stroke()
    NSGraphicsContext.restoreGraphicsState()

    img.unlockFocus()
    return img
}

func writePNG(_ img: NSImage, _ path: String, px: Int) {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px,
                               bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                               isPlanar: false, colorSpaceName: .deviceRGB,
                               bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: px, height: px)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    img.draw(in: CGRect(x: 0, y: 0, width: px, height: px))
    NSGraphicsContext.restoreGraphicsState()
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: path))
}

let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "Tokenmeter.iconset"
try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)

// Every entry macOS asks for. Each is drawn at its own size, not scaled down.
let sizes: [(name: String, px: Int)] = [
    ("icon_16x16", 16), ("icon_16x16@2x", 32),
    ("icon_32x32", 32), ("icon_32x32@2x", 64),
    ("icon_128x128", 128), ("icon_128x128@2x", 256),
    ("icon_256x256", 256), ("icon_256x256@2x", 512),
    ("icon_512x512", 512), ("icon_512x512@2x", 1024),
]
for (name, px) in sizes {
    writePNG(drawIcon(size: CGFloat(px)), "\(out)/\(name).png", px: px)
}
print("wrote \(sizes.count) sizes into \(out)")
