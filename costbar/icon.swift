// Draws the Tokenmeter app icon and writes a full .iconset.
//
// Source rather than a binary blob, so the icon can be changed by editing
// numbers and rebuilt on any Mac with the command line tools. Every size is
// drawn as vectors at its own resolution rather than downsampled from one
// large bitmap, which is what keeps the 16pt version from turning to mud.
//
//   swiftc -O -o /tmp/mkicon icon.swift && /tmp/mkicon out.iconset
//
// The picture is the app's own chart: rising bars with a cumulative line over
// them. Someone who has seen the dashboard recognises it, and someone who has
// not still reads "spend, going up".

import AppKit
import Foundation

let ACC_HI  = NSColor(srgbRed: 0.925, green: 0.588, blue: 0.451, alpha: 1)   // #ec9673
let ACC_LO  = NSColor(srgbRed: 0.769, green: 0.373, blue: 0.216, alpha: 1)   // #c45f37
let LINE    = NSColor(srgbRed: 0.427, green: 0.678, blue: 0.878, alpha: 1)   // #6dade0
let BG_HI   = NSColor(srgbRed: 0.137, green: 0.153, blue: 0.173, alpha: 1)   // #23272c
let BG_LO   = NSColor(srgbRed: 0.043, green: 0.051, blue: 0.063, alpha: 1)   // #0b0d10

/// Apple's icon outline is a squircle, not a rounded rectangle. Circular
/// corners read as subtly wrong beside native icons, and the difference is
/// most visible at large sizes in the Dock.
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

func gradient(_ from: NSColor, _ to: NSColor) -> NSGradient {
    NSGradient(starting: from, ending: to)!
}

/// One icon at one size. `s` is the edge length in pixels; everything is
/// expressed as a fraction of it so the drawing is resolution independent.
func drawIcon(size s: CGFloat) -> NSImage {
    let img = NSImage(size: NSSize(width: s, height: s))
    img.lockFocus()
    let ctx = NSGraphicsContext.current!
    ctx.imageInterpolation = .high
    ctx.shouldAntialias = true

    // Apple's grid: the shape occupies 824 of a 1024 canvas, leaving room for
    // the shadow the system expects an icon to carry itself.
    let inset = s * 0.098
    let box = CGRect(x: inset, y: inset * 1.14, width: s - inset * 2, height: s - inset * 2)
    let shape = squircle(in: box)

    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.55)
    shadow.shadowBlurRadius = s * 0.035
    shadow.shadowOffset = NSSize(width: 0, height: -s * 0.012)
    shadow.set()
    BG_LO.setFill()
    shape.fill()
    NSGraphicsContext.restoreGraphicsState()

    NSGraphicsContext.saveGraphicsState()
    shape.addClip()
    gradient(BG_HI, BG_LO).draw(in: box, angle: -90)

    // A warm bloom in the upper left, the same light source the dashboard uses.
    // Drawn over the whole box, not a sub-rectangle: a radial gradient is only
    // transparent at the edge of the rect it is given, so a smaller rect left
    // a visible horizontal seam across the icon where it stopped.
    let bloom = NSGradient(colorsAndLocations:
        (NSColor(srgbRed: 0.851, green: 0.467, blue: 0.341, alpha: 0.22), 0.0),
        (NSColor(srgbRed: 0.851, green: 0.467, blue: 0.341, alpha: 0.06), 0.45),
        (NSColor(srgbRed: 0.851, green: 0.467, blue: 0.341, alpha: 0.0), 1.0))!
    bloom.draw(in: box.insetBy(dx: -box.width * 0.3, dy: -box.height * 0.3),
               relativeCenterPosition: CGPoint(x: -0.34, y: 0.42))

    // ---- the chart -------------------------------------------------------
    // Below 32pt the full drawing turns to porridge, so the small sizes get
    // fewer, fatter bars and no dot. Apple's own icons simplify the same way.
    let small = s < 32
    let heights: [CGFloat] = small ? [0.34, 0.56, 0.78, 1.0]
                                   : [0.30, 0.45, 0.36, 0.68, 1.0]

    // Bars sit in the lower half; the line sweeps through the upper half.
    // Together they fill the square rather than hugging one corner.
    let plot = CGRect(x: box.minX + box.width * 0.155, y: box.minY + box.height * 0.235,
                      width: box.width * 0.69, height: box.height * 0.34)

    let gap = plot.width * (small ? 0.10 : 0.085)
    let bw = (plot.width - gap * CGFloat(heights.count - 1)) / CGFloat(heights.count)
    let radius = min(bw * 0.28, s * 0.022)

    for (i, h) in heights.enumerated() {
        let bh = max(plot.height * h, s * 0.022)
        let r = CGRect(x: plot.minX + (bw + gap) * CGFloat(i), y: plot.minY,
                       width: bw, height: bh)
        let bar = NSBezierPath(roundedRect: r, xRadius: radius, yRadius: radius)
        NSGraphicsContext.saveGraphicsState()
        bar.addClip()
        gradient(ACC_HI, ACC_LO).draw(in: r, angle: -90)
        NSGraphicsContext.restoreGraphicsState()
    }

    // The cumulative line: always climbing, which is the one honest thing a
    // running total does. It rises across the upper half, clear of the bars.
    let lineLo = plot.minY + plot.height * 0.62
    let lineHi = box.minY + box.height * 0.775
    let pts: [CGPoint] = heights.enumerated().map { i, _ in
        let run = heights[0...i].reduce(0, +) / heights.reduce(0, +)
        return CGPoint(x: plot.minX + (bw + gap) * CGFloat(i) + bw / 2,
                       y: lineLo + (lineHi - lineLo) * run)
    }
    let line = NSBezierPath()
    line.lineWidth = max(s * (small ? 0.032 : 0.021), 1)
    line.lineCapStyle = .round
    line.lineJoinStyle = .round
    for (i, p) in pts.enumerated() {
        if i == 0 { line.move(to: p) } else { line.line(to: p) }
    }
    // A dark backing stroke keeps the line readable where it crosses a bar.
    // Kept tight: too wide and the line reads as a clumsy tube.
    let halo = line.copy() as! NSBezierPath
    halo.lineWidth = line.lineWidth * 1.75
    NSColor(srgbRed: 0.043, green: 0.051, blue: 0.063, alpha: 0.9).setStroke()
    halo.stroke()
    LINE.setStroke()
    line.stroke()

    // The head of the line, so the eye lands on "now".
    if !small, let last = pts.last {
        let rr = s * 0.026
        NSColor(srgbRed: 0.043, green: 0.051, blue: 0.063, alpha: 1).setFill()
        NSBezierPath(ovalIn: CGRect(x: last.x - rr, y: last.y - rr,
                                    width: rr * 2, height: rr * 2)).fill()
        LINE.setFill()
        NSBezierPath(ovalIn: CGRect(x: last.x - rr * 0.6, y: last.y - rr * 0.6,
                                    width: rr * 1.2, height: rr * 1.2)).fill()
    }
    NSGraphicsContext.restoreGraphicsState()

    // A hairline rim, the thing that stops a dark icon looking like a hole.
    NSGraphicsContext.saveGraphicsState()
    let rim = squircle(in: box.insetBy(dx: s * 0.003, dy: s * 0.003))
    rim.lineWidth = max(s * 0.0055, 0.6)
    NSColor.white.withAlphaComponent(0.085).setStroke()
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
