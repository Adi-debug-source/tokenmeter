// Draws the repository's social preview, 1280 by 640, the size GitHub asks
// for: what a link to the repository shows on LinkedIn, Slack and X.
//
// Source rather than a binary blob, like the app icon (costbar/icon.swift),
// so the words and figures can be changed here and drawn again on any Mac
// with the command line tools. From the repository's top folder:
//
//   swiftc -O -o /tmp/mkpreview docs/github/social_preview.swift -framework AppKit
//   /tmp/mkpreview . docs/github/social-preview.png
//   python3 docs/screenshots/shoot.py --plain docs/github/social-preview.png
//
// It uses the dashboard's own typefaces (fonts/), colours
// (dashboard/dashboard.css) and the app icon (docs/screenshots/icon.png).
// The figures are the invented demo's, the ones in the README's menu bar
// image (docs/screenshots/make_demo.py), not anyone's usage.

import AppKit
import CoreText
import Foundation

let W: CGFloat = 1280, H: CGFloat = 640

func hex(_ h: UInt32, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((h >> 16) & 0xff) / 255, green: CGFloat((h >> 8) & 0xff) / 255,
            blue: CGFloat(h & 0xff) / 255, alpha: a)
}

// dashboard.css: --bg, --card, --line2, --ink, --dim, --acc, then the series.
let BG = hex(0x090A0C), CARD = hex(0x121417), LINE = hex(0x2C313A), RULE = hex(0x212429)
let INK = hex(0xEEF0F4), DIM = hex(0x8C94A2), ACC = hex(0xD97757)
let SERIES: [(NSColor, CGFloat)] = [(ACC, 0.282), (hex(0x5B9DD9), 0.536), (hex(0xD4A03C), 0.178),
                                    (hex(0x9085E9), 0.004)]

let args = CommandLine.arguments
guard args.count == 3 else {
    FileHandle.standardError.write("usage: mkpreview <repository folder> <out.png>\n".data(using: .utf8)!)
    exit(2)
}
let repo = URL(fileURLWithPath: args[1])
for name in ["fraunces.woff2", "inter-tight.woff2"] {
    let url = repo.appendingPathComponent("fonts").appendingPathComponent(name)
    guard CTFontManagerRegisterFontsForURL(url as CFURL, .process, nil) else {
        FileHandle.standardError.write("cannot load \(url.path)\n".data(using: .utf8)!)
        exit(1)
    }
}

func font(_ name: String, _ size: CGFloat) -> NSFont {
    guard let f = NSFont(name: name, size: size) else {
        FileHandle.standardError.write("no typeface named \(name)\n".data(using: .utf8)!)
        exit(1)
    }
    return f
}

/// Text with its top-left corner at (x, top), measured from the top of the
/// picture as a page is. Returns its width.
@discardableResult
func draw(_ runs: [(String, NSColor)], _ f: NSFont, x: CGFloat, top: CGFloat,
          tracking: CGFloat = 0, rightEdge: CGFloat? = nil) -> CGFloat {
    let text = NSMutableAttributedString()
    for (s, colour) in runs {
        text.append(NSAttributedString(string: s, attributes: [
            .font: f, .foregroundColor: colour, .kern: tracking]))
    }
    let size = text.size()
    let left = rightEdge.map { $0 - size.width } ?? x
    text.draw(at: CGPoint(x: left, y: H - top - size.height))
    return size.width
}

func pill(_ rect: CGRect, radius: CGFloat, fill: NSColor, stroke: NSColor) {
    let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    fill.setFill()
    path.fill()
    stroke.setStroke()
    path.lineWidth = 1
    path.stroke()
}

let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(W), pixelsHigh: Int(H),
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                           isPlanar: false, colorSpaceName: .deviceRGB,
                           bytesPerRow: 0, bitsPerPixel: 0)!
rep.size = NSSize(width: W, height: H)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)

BG.setFill()
CGRect(x: 0, y: 0, width: W, height: H).fill()
// A little of the accent's light from the top left, as the icon is lit.
NSGradient(colors: [ACC.withAlphaComponent(0.13), ACC.withAlphaComponent(0)])!
    .draw(fromCenter: CGPoint(x: 150, y: H - 60), radius: 0,
          toCenter: CGPoint(x: 150, y: H - 60), radius: 620, options: [])

// The mark and the name.
let left: CGFloat = 84
if let icon = NSImage(contentsOf: repo.appendingPathComponent("docs/screenshots/icon.png")) {
    icon.draw(in: CGRect(x: left - 8, y: H - 70 - 100, width: 100, height: 100))
}
draw([("Tokenmeter", INK)], font("Fraunces-SemiBold", 62), x: left + 112, top: 80, tracking: -1)

// What it is, in the README's own first line.
let headline = font("Fraunces-Regular", 51)
draw([("What your AI coding would", INK)], headline, x: left, top: 214, tracking: -0.6)
draw([("have cost ", INK), ("at API rates", ACC), (".", INK)], headline, x: left, top: 276,
     tracking: -0.6)

let body = font("InterTight-Regular", 25)
draw([("Reads the logs your coding agent already writes", DIM)], body, x: left, top: 372)
draw([("and prices every call. Your usage stays on your Mac.", DIM)], body, x: left, top: 407)

// The four faces.
var x = left
let label = font("InterTight-Regular_Medium", 19)
for face in ["Menu bar", "Status line", "Terminal", "Dashboard"] {
    let w = NSAttributedString(string: face, attributes: [.font: label]).size().width + 36
    pill(CGRect(x: x, y: H - 486 - 40, width: w, height: 40), radius: 20, fill: CARD, stroke: LINE)
    draw([(face, INK)], label, x: x + 18, top: 494)
    x += w + 12
}

// A card of figures, as the menu gives them.
let card = CGRect(x: 800, y: H - 128 - 384, width: 396, height: 384)
pill(card, radius: 18, fill: CARD, stroke: LINE)
let inner = card.minX + 30, edge = card.maxX - 30
draw([("ALL TIME, AT API RATES", DIM)], font("InterTight-Regular_Medium", 15), x: inner, top: 158,
     tracking: 1.1)
draw([("$151.71", INK)], font("Fraunces-Regular", 62), x: inner, top: 182, tracking: -1)
let row = font("InterTight-Regular", 22), figure = font("InterTight-Regular_SemiBold", 22)
for (i, (name, value)) in [("Today", "$0.50"), ("Last 7 days", "$18.63"),
                           ("Last 30 days", "$59.60")].enumerated() {
    let top = 282 + CGFloat(i) * 52
    RULE.setFill()
    CGRect(x: inner, y: H - top, width: edge - inner, height: 1).fill()
    draw([(name, DIM)], row, x: inner, top: top + 12)
    draw([(value, INK)], figure, x: 0, top: top + 12, rightEdge: edge)
}
// The parts of a bill, in the dashboard's colours.
var barX = inner
let barTop: CGFloat = 458, barW = edge - inner
NSGraphicsContext.saveGraphicsState()
NSBezierPath(roundedRect: CGRect(x: inner, y: H - barTop - 10, width: barW, height: 10),
             xRadius: 5, yRadius: 5).addClip()
for (colour, share) in SERIES {
    colour.setFill()
    CGRect(x: barX, y: H - barTop - 10, width: barW * share + 1, height: 10).fill()
    barX += barW * share
}
NSGraphicsContext.restoreGraphicsState()

NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: args[2]))
print("wrote \(args[2])")
