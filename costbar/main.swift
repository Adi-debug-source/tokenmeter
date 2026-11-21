// Tokenmeter: a menu bar readout of what your AI coding would have cost at
// API rates. On a subscription this is the counterfactual, not a bill.
//
// All the arithmetic lives in ~/.claude/tools/tokenmeter/tokenmeter.py, where
// install.sh puts it. This is only a face for it, so there is one price table
// and not two.

import AppKit
import Foundation

let engine = ("~/.claude/tools/tokenmeter/tokenmeter.py" as NSString).expandingTildeInPath
let refreshSeconds: TimeInterval = 60

// Which currencies exist, in what order and what they look like is
// tokenmeter.py's business, not this file's. These are only what shows before
// the first load returns; a list kept here once offered four currencies while
// the dashboard offered seven.
var currencyOrder = ["USD", "GBP", "EUR", "INR"]
var currencySymbols: [String: String] = ["GBP": "\u{00A3}", "USD": "$"]

// Everything is held in dollars. Only display converts.
var displayCurrency = UserDefaults.standard.string(forKey: "currency") ?? "USD"
var displayRates: [String: Double] = ["USD": 1.0]

func rate(_ code: String) -> Double { displayRates[code] ?? 1.0 }

struct Window {
    var total = 0.0, calls = 0
    var input = 0.0, cacheWrite = 0.0, cacheRead = 0.0, output = 0.0
    // Billed per request, not per token. Zero for most people, but leaving it
    // out of the breakdown made the four lines fail to add up to the total.
    var webSearch = 0.0
    // The window's total tokens, the engine's one definition (token_totals()),
    // for the title and the window's row when Show tokens is on.
    var tokens = 0.0
}

struct Snapshot {
    var today = Window(), week = Window(), month = Window(), all = Window()
    var models: [(String, Double, Int)] = []
    var withoutCache = 0.0
    // The engine works these out (caching_summary()); the menu only shows them.
    var savedPct = 0.0
    var multiple = 0.0
    var rateWhen = ""
    var rateLive = true
    var covered = ""
    // Only filled when harnesses or providers are mixed. One harness on one
    // provider sees the menu it always had.
    var multi = false
    var harnesses: [(label: String, status: String, total: Double, calls: Int)] = []
    var providers: [(label: String, measured: Bool, total: Double, calls: Int,
                     models: [(String, Double, Int)])] = []
    // What the engine says must be shown beside the figures: when each price
    // table was checked, and any warning about how far to trust a number.
    var notes: [(level: String, text: String, attention: Bool)] = []
    var failed: String?
}

// A fixed locale and separators, not the Mac's own: with a German locale this
// printed 1.234,50 while the sub-penny branch below, the terminal and the
// dashboard all print 1,234.50.
let groupedTwoDP: NumberFormatter = {
    let f = NumberFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.numberStyle = .decimal
    f.usesGroupingSeparator = true
    f.groupingSeparator = ","
    f.groupingSize = 3
    f.decimalSeparator = "."
    f.minimumFractionDigits = 2
    f.maximumFractionDigits = 2
    return f
}()

func money(_ usd: Double) -> String {
    let x = usd * rate(displayCurrency)
    let s = currencySymbols[displayCurrency] ?? "$"
    // Same rule as money() in tokenmeter.py, so the menu bar and the terminal
    // never disagree about the same figure. Two decimals, thousands separated;
    // four only for a non-zero amount under a penny, so one cheap call reads as
    // 0.0290 and not as free. Rounding thousands to whole units used to make
    // this menu contradict itself, with Saved and With not adding up to
    // Without on screen even though the figures behind them agreed exactly.
    // A negative amount takes its minus before the symbol, -$0.10, not $-0.10.
    if x == 0 { return s + "0.00" }
    let sign = x < 0 ? "-" : "", a = abs(x)
    // Real money below the smallest printable figure. "0.0000" would read as
    // nothing at all, which is the thing being fixed here.
    if a < 0.00005 { return sign + "<" + s + "0.0001" }
    if a < 0.01 { return sign + s + String(format: "%.4f", a) }
    return sign + s + (groupedTwoDP.string(from: NSNumber(value: a)) ?? String(format: "%.2f", a))
}

// A token count as toks() in tokenmeter.py writes it: 999, 1.0k, 1.00M,
// 1.00B. String(format:) rounds the same double the same way Python does.
func toks(_ n: Double) -> String {
    if n >= 1_000_000_000 { return String(format: "%.2fB", n / 1_000_000_000) }
    if n >= 1_000_000 { return String(format: "%.2fM", n / 1_000_000) }
    if n >= 1000 { return String(format: "%.1fk", n / 1000) }
    return String(Int(n))
}

func shownDifference(_ big: Double, _ small: Double) -> Double {
    // A difference that still adds up once both sides have been rounded.
    // With, without and saved were each rounded to the penny on their own, and
    // three roundings of exact figures can leave the column a penny out. The
    // arithmetic behind them is exact; it was the printing that disagreed.
    // Mirrors shown_difference() in tokenmeter.py.
    let r = rate(displayCurrency)
    guard r != 0 else { return big - small }
    return (((big * r * 100).rounded() - (small * r * 100).rounded()) / 100) / r
}

// True when caching cost more than it saved: cache writes that cost more
// than the reads they made possible saved. With nothing cached the two totals
// differ only in the last bit, which is not a cost. Mirrors caching_dearer()
// in tokenmeter.py.
func cachingDearer(_ withoutCache: Double, _ withCache: Double) -> Bool {
    withCache - withoutCache > 1e-9 * max(withCache, withoutCache)
}

func loadSnapshot() -> Snapshot {
    var snap = Snapshot()

    guard FileManager.default.fileExists(atPath: engine) else {
        snap.failed = "tokenmeter.py not found; run install.sh"
        return snap
    }

    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    task.arguments = [engine, "--summary-json"]
    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = Pipe()

    do { try task.run() } catch {
        snap.failed = "could not run python3"
        return snap
    }
    let out = pipe.fileHandleForReading.readDataToEndOfFile()
    task.waitUntilExit()

    guard let root = (try? JSONSerialization.jsonObject(with: out)) as? [String: Any] else {
        snap.failed = "no readable output"
        return snap
    }

    func window(_ key: String) -> Window {
        var w = Window()
        guard let d = root[key] as? [String: Any] else { return w }
        w.total = d["total"] as? Double ?? 0
        w.calls = d["calls"] as? Int ?? 0
        w.input = d["input"] as? Double ?? 0
        w.cacheWrite = d["cache_write"] as? Double ?? 0
        w.cacheRead = d["cache_read"] as? Double ?? 0
        w.output = d["output"] as? Double ?? 0
        w.webSearch = d["web_search"] as? Double ?? 0
        w.tokens = (d["tokens"] as? [String: Any])?["total"] as? Double ?? 0
        return w
    }

    snap.today = window("today")
    snap.week = window("week")
    snap.month = window("month")
    snap.all = window("all")
    snap.withoutCache = root["without_cache"] as? Double ?? 0
    snap.savedPct = root["saved_pct"] as? Double ?? 0
    snap.multiple = root["multiple"] as? Double ?? 0
    snap.covered = root["covered"] as? String ?? ""
    snap.rateWhen = root["rate_when"] as? String ?? ""
    snap.rateLive = root["rate_live"] as? Bool ?? true
    if let r = root["rates"] as? [String: Double] {
        displayRates = r
        displayRates["USD"] = 1.0
    }
    if let cur = root["currencies"] as? [String: [String: String]] {
        for (code, info) in cur where info["symbol"] != nil {
            currencySymbols[code] = info["symbol"]!
        }
    }
    if let order = root["currency_order"] as? [String], !order.isEmpty {
        currencyOrder = order
    }
    if let ms = root["models"] as? [[String: Any]] {
        snap.models = ms.map { (($0["name"] as? String) ?? "?",
                                ($0["total"] as? Double) ?? 0,
                                ($0["calls"] as? Int) ?? 0) }
    }
    snap.multi = root["multi"] as? Bool ?? false
    if let hs = root["harnesses"] as? [[String: Any]] {
        snap.harnesses = hs.map { (($0["label"] as? String) ?? "?", ($0["status"] as? String) ?? "",
                                   ($0["total"] as? Double) ?? 0, ($0["calls"] as? Int) ?? 0) }
    }
    if let ps = root["providers"] as? [[String: Any]] {
        snap.providers = ps.map { p in
            let ms = (p["models"] as? [[String: Any]] ?? []).map {
                (($0["name"] as? String) ?? "?", ($0["total"] as? Double) ?? 0, ($0["calls"] as? Int) ?? 0)
            }
            return ((p["label"] as? String) ?? "?", (p["measured"] as? Bool) ?? false,
                    (p["total"] as? Double) ?? 0, (p["calls"] as? Int) ?? 0, ms)
        }
    }
    if let ns = root["notes"] as? [[String: Any]] {
        // The engine says which notes need attention. One from before 1.3.6
        // does not, and its warnings are taken to.
        snap.notes = ns.map {
            let level = ($0["level"] as? String) ?? "info"
            return (level, ($0["text"] as? String) ?? "",
                    ($0["attention"] as? Bool) ?? (level == "warn"))
        }
    }
    return snap
}

// The rows of the menu, copied from Bytemeter's Sources/Bytemeter/MenuRows.swift
// so the two apps' menus share one set of measurements, and adapted to this
// one-file build.
//
// The rows that only inform are drawn by views: AppKit draws a disabled menu
// item grey whatever colour its attributed title asks for, and these rows
// must stay disabled, or they would highlight on hover and look clickable. A
// view is drawn exactly as it is.
//
// The four period rows are standard items, because they are chosen, and
// AppKit gives a view item no key events, so Return cannot choose one
// (tested on macOS 27): as standard items Return, the tick, the highlight and
// VoiceOver are AppKit's own. Their figures sit at right tab stops, and the
// views draw to the same edge, so every figure lines up.
enum MenuRows {

    /// Where a standard item's title starts. Measured on macOS 27: AppKit pads
    /// a titled item by 34 points in all, and while any item shows a tick it
    /// adds a 14 point column on the left. The period rows always carry a
    /// tick, so the column is always there.
    static let inset: CGFloat = 17 + 14
    /// Where a submenu's rows start: it has no ticks, so no tick column.
    static let plainInset: CGFloat = 17
    /// The right edge of the figures, measured from the text start. AppKit
    /// keeps its shortcut column, about 47 points, to the right of a standard
    /// item's title, so this makes the menu 316 points wide.
    static let figureColumn: CGFloat = 235
    /// How wide a sentence may run before it wraps: to the shortcuts' right
    /// edge, past the figures, since a sentence has no figure to line up.
    static let textColumn: CGFloat = 268
    /// The notes are long sentences, so their submenu is wider.
    static let noteColumn: CGFloat = 360
    static let trailingInset: CGFloat = 17
    /// The height AppKit gives a standard item here, so the rows keep the
    /// same rhythm as the commands below them.
    static let rowHeight: CGFloat = 24
    /// Between a figure and the grey one beside it.
    static let gap: CGFloat = 12

    /// One size for every row, AppKit's own menu size, so the rows read at
    /// the same size as the commands; 11 points for headers.
    static let textFont = NSFont.systemFont(ofSize: NSFont.systemFontSize)
    static let figureFont = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
    static let headerFont = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize, weight: .semibold)

    /// The parts of a bill in the dashboard's colours, --s1 to --s5 in
    /// dashboard/dashboard.css, which a test holds these to. The only colour
    /// in the menu.
    static let cacheReadColour = colour(0xd97757)
    static let cacheWriteColour = colour(0x5b9dd9)
    static let outputColour = colour(0xd4a03c)
    static let inputColour = colour(0x9085e9)
    static let webSearchColour = colour(0x1aa382)

    static func colour(_ hex: Int) -> NSColor {
        NSColor(srgbRed: CGFloat((hex >> 16) & 0xff) / 255, green: CGFloat((hex >> 8) & 0xff) / 255,
                blue: CGFloat(hex & 0xff) / 255, alpha: 1)
    }

    static func width(inset: CGFloat) -> CGFloat { inset + textColumn + trailingInset }

    /// The widest of these figures, so a column of them can be lined up.
    static func figureWidth(_ texts: [String]) -> CGFloat {
        texts.map { ceil(($0 as NSString).size(withAttributes: [.font: figureFont]).width) }.max() ?? 0
    }

    // MARK: - Items

    static func header(_ text: String, inset: CGFloat = inset, width: CGFloat? = nil) -> NSMenuItem {
        let view = MenuRowView(content: .header(text), inset: inset, height: rowHeight, width: width)
        view.setAccessibilityLabel(text)
        return item(view)
    }

    /// One of the four periods the menu bar can show: the cost in full
    /// contrast and, with Show Tokens on, the tokens grey beside it, ticked
    /// when it is the one showing, and chosen with a click, Return or
    /// VoiceOver, which send the item's action. `tokensWidth` is the widest
    /// of the four token figures, so the costs line up too.
    static func period(_ label: String, cost: String, tokens: String?, tokensWidth: CGFloat, chosen: Bool,
                       toolTip: String?, action: Selector, target: AnyObject, representedObject: Any) -> NSMenuItem {
        let style = NSMutableParagraphStyle()
        if tokens == nil {
            style.tabStops = [NSTextTab(textAlignment: .right, location: figureColumn)]
        } else {
            style.tabStops = [NSTextTab(textAlignment: .right, location: figureColumn - tokensWidth - gap),
                              NSTextTab(textAlignment: .right, location: figureColumn)]
        }
        // No colour on the label or the cost, so AppKit draws them in its
        // own, white while highlighted.
        let title = NSMutableAttributedString(string: label + "\t", attributes: [.font: textFont, .paragraphStyle: style])
        title.append(NSAttributedString(string: cost, attributes: [.font: figureFont, .paragraphStyle: style]))
        if let tokens = tokens {
            title.append(NSAttributedString(string: "\t" + tokens, attributes: [
                .font: figureFont, .paragraphStyle: style, .foregroundColor: NSColor.secondaryLabelColor]))
        }
        let row = NSMenuItem(title: label, action: action, keyEquivalent: "")
        row.attributedTitle = title
        row.target = target
        row.representedObject = representedObject
        row.state = chosen ? .on : .off
        row.toolTip = toolTip
        return row
    }

    /// A sentence, grey unless it is news. One wider than its column wraps
    /// rather than widening the menu.
    static func text(_ text: String, inset: CGFloat = inset, column: CGFloat = textColumn,
                     colour: NSColor = .secondaryLabelColor, toolTip: String? = nil) -> NSMenuItem {
        let wraps = (text as NSString).size(withAttributes: [.font: textFont]).width > column
        let height = wraps ? wrappedHeight(text, column: column) : rowHeight
        let view = MenuRowView(content: .text(text, column: column, wraps: wraps, colour: colour), inset: inset,
                               height: height, width: inset + column + trailingInset)
        view.setAccessibilityLabel(text)
        view.toolTip = toolTip
        let row = item(view)
        row.toolTip = toolTip
        return row
    }

    /// The widths of a breakdown's columns, the widest of each, so that every
    /// row of the submenu lines up whatever its section.
    struct Columns {
        var label: CGFloat = 0, amount: CGFloat = 0, detail: CGFloat = 0
        static let dot: CGFloat = 14, indent: CGFloat = 12, labelGap: CGFloat = 20

        mutating func fit(_ label: String, dot: Bool, indent: Bool, amount: String, detail: String) {
            let name = ceil((label as NSString).size(withAttributes: [.font: MenuRows.textFont]).width)
            self.label = max(self.label, name + (dot ? Columns.dot : 0) + (indent ? Columns.indent : 0))
            self.amount = max(self.amount, MenuRows.figureWidth([amount]))
            self.detail = max(self.detail, MenuRows.figureWidth([detail]))
        }

        var width: CGFloat {
            max(MenuRows.width(inset: MenuRows.plainInset),
                MenuRows.plainInset + label + Columns.labelGap + amount + MenuRows.gap + detail + MenuRows.trailingInset)
        }
    }

    /// One row of a breakdown: a dot in its colour if it has one, the name,
    /// the amount, and grey at the edge its share or its calls.
    static func part(_ label: String, dot: NSColor?, indent: Bool = false, amount: String, detail: String,
                     columns: Columns, toolTip: String? = nil) -> NSMenuItem {
        let view = MenuRowView(content: .part(label: label, dot: dot, indent: indent, amount: amount, detail: detail,
                                              detailWidth: columns.detail),
                               inset: plainInset, height: rowHeight, width: columns.width)
        view.setAccessibilityLabel("\(label): \(amount), \(detail)")
        view.toolTip = toolTip
        let row = item(view)
        row.toolTip = toolTip
        return row
    }

    /// One bar split into the parts, each its share of the whole.
    static func split(_ parts: [(share: Double, colour: NSColor)], width: CGFloat) -> NSMenuItem {
        let view = MenuRowView(content: .split(parts), inset: plainInset, height: 14, width: width)
        view.setAccessibilityElement(false)
        return item(view)
    }

    /// The warning row's title: a yellow triangle, then the words.
    static func warningTitle(_ text: String) -> NSAttributedString {
        let title = NSMutableAttributedString()
        if let symbol = NSImage(systemSymbolName: "exclamationmark.triangle", accessibilityDescription: "Warning")?
            .withSymbolConfiguration(NSImage.SymbolConfiguration(paletteColors: [.systemYellow])) {
            let mark = NSTextAttachment()
            mark.image = symbol
            mark.bounds = NSRect(x: 0, y: -2, width: symbol.size.width, height: symbol.size.height)
            title.append(NSAttributedString(attachment: mark))
            title.append(NSAttributedString(string: " "))
        }
        title.append(NSAttributedString(string: text))
        title.addAttribute(.font, value: textFont, range: NSRange(location: 0, length: title.length))
        return title
    }

    private static func item(_ view: MenuRowView) -> NSMenuItem {
        let item = NSMenuItem(title: "", action: nil, keyEquivalent: "")
        item.isEnabled = false
        item.view = view
        return item
    }

    private static func wrappedHeight(_ text: String, column: CGFloat) -> CGFloat {
        let bounds = (text as NSString).boundingRect(
            with: NSSize(width: column, height: .greatestFiniteMagnitude),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: [.font: textFont])
        return max(rowHeight, ceil(bounds.height) + 8)
    }
}

final class MenuRowView: NSView {

    enum Content {
        case header(String)
        case text(String, column: CGFloat, wraps: Bool, colour: NSColor)
        case part(label: String, dot: NSColor?, indent: Bool, amount: String, detail: String, detailWidth: CGFloat)
        case split([(share: Double, colour: NSColor)])
    }

    private let content: Content
    private let inset: CGFloat

    init(content: Content, inset: CGFloat, height: CGFloat, width: CGFloat? = nil) {
        self.content = content
        self.inset = inset
        super.init(frame: NSRect(x: 0, y: 0, width: width ?? MenuRows.width(inset: inset), height: height))
        // The menu may be wider than this row, for a long command title; the
        // row stretches, and the figures keep to its right edge.
        autoresizingMask = [.width]
        setAccessibilityElement(true)
        setAccessibilityRole(.staticText)
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    override var isFlipped: Bool { true }

    private var right: CGFloat { bounds.width - MenuRows.trailingInset }

    private static func lineHeight(_ font: NSFont) -> CGFloat { ceil(font.ascender - font.descender) }

    /// Colours are the dynamic system ones, resolved at draw time against the
    /// menu's own appearance, so light and dark menus both come out right.
    override func draw(_ dirtyRect: NSRect) {
        switch content {
        case let .header(text):
            drawLine(text, font: MenuRows.headerFont, colour: .secondaryLabelColor, x: inset, width: right - inset)

        case let .text(text, column, wraps, colour):
            let attributes: [NSAttributedString.Key: Any] = [.font: MenuRows.textFont, .foregroundColor: colour]
            if wraps {
                (text as NSString).draw(with: NSRect(x: inset, y: 4, width: column, height: bounds.height - 8),
                                        options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: attributes)
            } else {
                drawLine(text, font: MenuRows.textFont, colour: colour, x: inset, width: column)
            }

        case let .part(label, dot, indent, amount, detail, detailWidth):
            drawRight(detail, colour: .secondaryLabelColor, right: right)
            let amountRight = right - detailWidth - MenuRows.gap
            let amountWidth = drawRight(amount, colour: .labelColor, right: amountRight)
            var x = inset + (indent ? MenuRows.Columns.indent : 0)
            if let dot = dot {
                dot.setFill()
                NSBezierPath(ovalIn: NSRect(x: x, y: (bounds.height - 8) / 2, width: 8, height: 8)).fill()
                x += MenuRows.Columns.dot
            }
            drawLine(label, font: MenuRows.textFont, colour: .labelColor, x: x,
                     width: amountRight - amountWidth - 8 - x)

        case let .split(parts):
            let track = NSRect(x: inset, y: (bounds.height - 6) / 2, width: right - inset, height: 6)
            NSGraphicsContext.saveGraphicsState()
            NSBezierPath(roundedRect: track, xRadius: 3, yRadius: 3).addClip()
            NSColor.quaternaryLabelColor.setFill()
            track.fill()
            var x = track.minX
            for part in parts where part.share > 0 {
                let width = track.width * CGFloat(min(1, part.share))
                part.colour.setFill()
                NSRect(x: x, y: track.minY, width: width, height: track.height).fill()
                x += width
            }
            NSGraphicsContext.restoreGraphicsState()
        }
    }

    /// One line from `x`, vertically centred, cut short with an ellipsis
    /// rather than overflowing.
    private func drawLine(_ text: String, font: NSFont, colour: NSColor, x: CGFloat, width: CGFloat) {
        let style = NSMutableParagraphStyle()
        style.lineBreakMode = .byTruncatingTail
        let lineHeight = Self.lineHeight(font)
        (text as NSString).draw(with: NSRect(x: x, y: (bounds.height - lineHeight) / 2, width: max(0, width),
                                             height: lineHeight),
                                options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine],
                                attributes: [.font: font, .foregroundColor: colour, .paragraphStyle: style])
    }

    /// A figure right-aligned at `right`, vertically centred. Returns its width.
    @discardableResult
    private func drawRight(_ text: String, colour: NSColor, right: CGFloat) -> CGFloat {
        let attributes: [NSAttributedString.Key: Any] = [.font: MenuRows.figureFont, .foregroundColor: colour]
        let width = (text as NSString).size(withAttributes: attributes).width
        (text as NSString).draw(at: NSPoint(x: right - width, y: (bounds.height - Self.lineHeight(MenuRows.figureFont)) / 2),
                                withAttributes: attributes)
        return width
    }
}

// Preferences, a small window modelled on Bytemeter's
// Sources/Bytemeter/PreferencesWindow.swift. Plain controls, no tabs. A menu
// item cannot take Command-comma for a submenu, so this is a window, and
// there is only ever one: a second Command-comma brings it to the front.
final class PreferencesWindow: NSWindowController {

    private let controller: Controller
    private var currencyPopUp: NSPopUpButton!
    private var ratesNote: NSTextField!
    private var tokensSwitch: NSSwitch!

    private static let textWidth: CGFloat = 320

    init(controller: Controller) {
        self.controller = controller
        let window = PreferencesPanel(
            contentRect: NSRect(x: 0, y: 0, width: 368, height: 200),
            styleMask: [.titled, .closable],
            backing: .buffered, defer: false)
        window.title = "Tokenmeter Preferences"
        window.isReleasedWhenClosed = false
        super.init(window: window)
        buildContent()
        window.center()
    }

    required init?(coder: NSCoder) { fatalError("not used") }

    private func buildContent() {
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 8
        stack.edgeInsets = NSEdgeInsets(top: 22, left: 24, bottom: 22, right: 24)
        stack.translatesAutoresizingMaskIntoConstraints = false

        currencyPopUp = NSPopUpButton(frame: .zero, pullsDown: false)
        currencyPopUp.target = self
        currencyPopUp.action = #selector(chooseCurrency)
        currencyPopUp.setAccessibilityLabel("Currency")
        stack.addArrangedSubview(labelled("Currency", currencyPopUp))
        ratesNote = caption("")
        stack.addArrangedSubview(ratesNote)

        stack.setCustomSpacing(16, after: ratesNote)
        stack.addArrangedSubview(divider())
        stack.setCustomSpacing(16, after: stack.arrangedSubviews.last!)

        tokensSwitch = NSSwitch()
        tokensSwitch.target = self
        tokensSwitch.action = #selector(switchTokens)
        // The switch names itself; the label read out as well would say it twice.
        tokensSwitch.setAccessibilityLabel("Show Tokens")
        let tokensRow = labelled("Show Tokens", tokensSwitch)
        tokensRow.arrangedSubviews.first?.setAccessibilityElement(false)
        stack.addArrangedSubview(tokensRow)
        stack.addArrangedSubview(caption("Total tokens beside the cost, in the menu bar and on every period row: "
                                         + "uncached input, cache writes, cache reads and output."))

        guard let window = window, let content = window.contentView else { return }
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor),
        ])
        window.initialFirstResponder = currencyPopUp
    }

    /// The controls from the settings and the latest figures: the currencies
    /// the engine offers, at its rates, and when those were fetched.
    func refresh(_ snap: Snapshot) {
        currencyPopUp.removeAllItems()
        for code in currencyOrder {
            let sym = currencySymbols[code] ?? ""
            currencyPopUp.addItem(withTitle: code == "USD"
                ? "\(sym) USD  (billed)"
                : String(format: "%@ %@  %.4f", sym, code, rate(code)))
            currencyPopUp.lastItem?.representedObject = code
            if code == displayCurrency { currencyPopUp.select(currencyPopUp.lastItem) }
        }
        ratesNote.stringValue = snap.rateLive ? "Live rates, \(snap.rateWhen)" : "Rates: \(snap.rateWhen)"
        tokensSwitch.state = controller.showTokens ? .on : .off
    }

    func show(_ snap: Snapshot) {
        refresh(snap)
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    // MARK: - Controls

    private func caption(_ text: String) -> NSTextField {
        let field = NSTextField(wrappingLabelWithString: text)
        field.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        field.textColor = .secondaryLabelColor
        field.translatesAutoresizingMaskIntoConstraints = false
        field.widthAnchor.constraint(equalToConstant: Self.textWidth).isActive = true
        return field
    }

    private func divider() -> NSView {
        let line = NSBox()
        line.boxType = .separator
        line.translatesAutoresizingMaskIntoConstraints = false
        line.widthAnchor.constraint(equalToConstant: Self.textWidth).isActive = true
        return line
    }

    private func labelled(_ title: String, _ control: NSView) -> NSStackView {
        let row = NSStackView(views: [NSTextField(labelWithString: title), control])
        row.orientation = .horizontal
        row.spacing = 10
        return row
    }

    // MARK: - Actions

    @objc private func chooseCurrency() {
        if let code = currencyPopUp.selectedItem?.representedObject as? String {
            controller.chooseCurrency(code)
        }
    }

    @objc private func switchTokens() {
        controller.showTokens = tokensSwitch.state == .on
        controller.render()
    }
}

// The app has no menu bar of its own to carry Close, so the window answers
// Escape and Command-W itself.
final class PreferencesPanel: NSWindow {
    override func cancelOperation(_ sender: Any?) { close() }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.modifierFlags.intersection(.deviceIndependentFlagsMask) == .command,
           event.charactersIgnoringModifiers == "w" {
            close()
            return true
        }
        return super.performKeyEquivalent(with: event)
    }
}

final class Controller: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var timer: Timer?
    var snap = Snapshot()
    var busy = false
    var preferences: PreferencesWindow?
    // --open-menu opens the menu by itself once the figures are in, so a
    // script can take its picture (docs/screenshots/menu_shot.swift).
    var menuToOpen = CommandLine.arguments.contains("--open-menu")

    var mode: String {
        get { UserDefaults.standard.string(forKey: "mode") ?? "today" }
        set { UserDefaults.standard.set(newValue, forKey: "mode") }
    }

    // What the breakdown section shows when tools are mixed: model, harness
    // or provider. Model unless changed.
    var breakdown: String {
        get { UserDefaults.standard.string(forKey: "breakdown") ?? "model" }
        set { UserDefaults.standard.set(newValue, forKey: "breakdown") }
    }

    // Total tokens beside each cost, in the title and on every period row.
    // Off unless switched on in Preferences, so both are what they always
    // were. Kept under the key it had as a checkmark item, so a Mac that
    // turned it on then still has it on.
    var showTokens: Bool {
        get { UserDefaults.standard.bool(forKey: "showTokens") }
        set { UserDefaults.standard.set(newValue, forKey: "showTokens") }
    }

    func applicationDidFinishLaunching(_ note: Notification) {
        item.button?.font = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .regular)
        item.button?.title = "  ···"
        item.menu = NSMenu()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: refreshSeconds, repeats: true) { [weak self] _ in
            self?.refresh()
        }
    }

    func refresh() {
        if busy { return }
        busy = true
        DispatchQueue.global(qos: .utility).async {
            let s = loadSnapshot()
            DispatchQueue.main.async {
                self.snap = s
                self.busy = false
                self.render()
            }
        }
    }

    // Every window named once. Three places used to spell these out
    // separately and a fourth window would have had to be added to each.
    // The place is what the submenu's title says went: "Where 7 Days Went".
    static let windowNames: [String: (long: String, place: String)] = [
        "today": ("Today", "Today"),
        "week":  ("Last 7 days", "7 Days"),
        "month": ("Last 30 days", "30 Days"),
        "all":   ("All time", "It All"),
    ]

    // In the order the menu lists them.
    static let windowKeys = ["today", "week", "month", "all"]

    func windowName(_ key: String) -> String {
        Controller.windowNames[key]?.long ?? "All time"
    }

    func windowPlace(_ key: String) -> String {
        Controller.windowNames[key]?.place ?? "It All"
    }

    func window(_ key: String) -> Window {
        switch key {
        case "week": return snap.week
        case "month": return snap.month
        case "all": return snap.all
        default: return snap.today
        }
    }

    func current() -> Window { window(mode) }

    func render() {
        showTitle()
        buildMenu()
        preferences?.refresh(snap)
        if menuToOpen {
            menuToOpen = false
            // A moment for the status item to draw its figure first, so the
            // menu hangs from where it will be.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.item.button?.performClick(nil) }
        }
    }

    func showTitle() {
        if let err = snap.failed {
            // A plain hyphen: the project writes no en or em dash anywhere.
            // What went wrong is in the tooltip and the menu.
            item.button?.title = "  -"
            item.button?.toolTip = err
        } else {
            // Just the amount, and its tokens only when switched on. Which
            // window it is was the user's own choice from this menu, so
            // prefixing it says something already known and costs width in a
            // crowded menu bar. The tooltip still says.
            let w = current()
            item.button?.title = showTokens ? "  \(money(w.total)) · \(toks(w.tokens))"
                                            : "  \(money(w.total))"
            item.button?.toolTip = "\(windowName(mode)), at API rates"
        }
    }

    @discardableResult
    func add(_ menu: NSMenu, _ title: String, _ action: Selector? = nil,
             key: String = "", enabled: Bool? = nil, state: Bool = false) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: key)
        mi.target = self
        mi.isEnabled = enabled ?? (action != nil)
        if state { mi.state = .on }
        menu.addItem(mi)
        return mi
    }

    // Short on purpose, the same pattern as Bytemeter's: the four periods,
    // one line about caching, a warning only when a note needs attention,
    // where the ticked period went one level down, then the commands.
    // Everything else is on the dashboard. The menu this replaced was taller
    // than a 13-inch screen.
    func buildMenu() {
        let menu = NSMenu()
        menu.autoenablesItems = false

        if let err = snap.failed {
            add(menu, "Could not read usage: \(err)")
            menu.addItem(.separator())
            add(menu, "Refresh", #selector(doRefresh))
            add(menu, "Quit", #selector(doQuit), key: "q")
            item.menu = menu
            return
        }

        menu.addItem(MenuRows.header("At API rates"))
        let tokens = Controller.windowKeys.map { toks(window($0).tokens) }
        let tokensWidth = MenuRows.figureWidth(tokens)
        for (key, count) in zip(Controller.windowKeys, tokens) {
            let w = window(key)
            let calls = "\(w.calls) API call" + (w.calls == 1 ? "" : "s")
            menu.addItem(MenuRows.period(
                windowName(key), cost: money(w.total), tokens: showTokens ? count : nil, tokensWidth: tokensWidth,
                chosen: mode == key,
                toolTip: key == "all" && !snap.covered.isEmpty
                    ? "\(calls), covering \(snap.covered). Show this one in the menu bar."
                    : "\(calls). Show this one in the menu bar.",
                action: #selector(setMode(_:)), target: self, representedObject: key))
        }

        var middle: [NSMenuItem] = []
        if snap.withoutCache > 0 && snap.all.total > 0 {
            // Saved is derived from the two rounded figures rather than
            // rounded on its own, so it is the difference of the totals as
            // the report and the dashboard print them. Rounding each
            // separately left the column a penny out in some currencies; the
            // figures behind them were always exact. When caching cost more
            // than it saved, that is named as a cost; a saving below zero
            // read "-99.7% cheaper, 0.5x".
            let dearer = cachingDearer(snap.withoutCache, snap.all.total)
            let shownSaved = dearer ? shownDifference(snap.all.total, snap.withoutCache)
                                    : shownDifference(snap.withoutCache, snap.all.total)
            middle.append(MenuRows.text(dearer
                ? "Caching cost \(money(shownSaved)) extra all time, " + String(format: "%.1f%% dearer", -snap.savedPct)
                : "Caching saved \(money(shownSaved)) all time, " + String(format: "%.1fx", snap.multiple)))
        }
        // A warning row only when a note needs attention, with every note
        // under it; the dashboard's footer carries them all as well. Every
        // note in the menu itself pushed the commands off a 900 point screen
        // on a day with nothing wrong.
        let attention = snap.notes.filter { $0.attention }.count
        if attention > 0 {
            let row = NSMenuItem(title: "", action: nil, keyEquivalent: "")
            row.attributedTitle = MenuRows.warningTitle(attention == 1 ? "1 Note Needs Attention"
                                                                       : "\(attention) Notes Need Attention")
            let notes = NSMenu()
            notes.autoenablesItems = false
            for note in snap.notes {
                let text = note.text.prefix(1).uppercased() + note.text.dropFirst()
                notes.addItem(MenuRows.text((note.attention ? "\u{26A0}\u{FE0E} " : "") + text,
                                            inset: MenuRows.plainInset, column: MenuRows.noteColumn,
                                            colour: note.attention ? .labelColor : .secondaryLabelColor))
            }
            row.submenu = notes
            middle.append(row)
        }
        if !middle.isEmpty {
            menu.addItem(.separator())
            middle.forEach(menu.addItem)
        }

        menu.addItem(.separator())
        let whereItem = NSMenuItem(title: "Where \(windowPlace(mode)) Went", action: nil, keyEquivalent: "")
        whereItem.submenu = whereMenu()
        menu.addItem(whereItem)
        add(menu, "Open Dashboard", #selector(openDashboard), key: "d")
        add(menu, "Refresh Now", #selector(doRefresh), key: "r")
        add(menu, "Preferences\u{2026}", #selector(openPreferences), key: ",")
        menu.addItem(.separator())
        add(menu, "Quit Tokenmeter", #selector(doQuit), key: "q")

        item.menu = menu
    }

    // Where the ticked period went: its cost in parts, in the dashboard's
    // colours, then the breakdown, which the engine sends for all time only.
    func whereMenu() -> NSMenu {
        let w = current()
        var parts: [(String, Double, NSColor)] = [("Cache writes", w.cacheWrite, MenuRows.cacheWriteColour),
                                                  ("Cache reads", w.cacheRead, MenuRows.cacheReadColour),
                                                  ("Output", w.output, MenuRows.outputColour),
                                                  ("Input, uncached", w.input, MenuRows.inputColour)]
        if w.webSearch > 0 { parts.append(("Web searches", w.webSearch, MenuRows.webSearchColour)) }
        let shares = parts.map { w.total > 0 ? $0.1 / w.total : 0 }

        func callsText(_ n: Int) -> String { "\(n) call" + (n == 1 ? "" : "s") }
        func short(_ name: String) -> String { name.replacingOccurrences(of: "claude-", with: "") }

        // By model is the breakdown that matters most and always the default.
        // Only when harnesses or providers are mixed can it be switched to
        // show those instead, from Break Down By below it.
        let choice = snap.multi ? breakdown : "model"
        var heading = "By model, all time"
        var rows: [(label: String, total: Double, calls: Int, indent: Bool, tip: String?)] = []
        if choice == "harness" && snap.harnesses.count > 1 {
            heading = "By harness, all time"
            rows = snap.harnesses.map { h in
                ((h.status == "verified" ? "\u{2713}" : "\u{25CB}") + " " + h.label, h.total, h.calls, false,
                 h.status == "verified" ? "Verified: checked against real logs"
                 : h.status == "yours" ? "Imported by you"
                 : "Unverified: built from the published log format")
            }
        } else if choice == "provider" && snap.providers.count > 1 {
            heading = "By provider, all time"
            for p in snap.providers {
                rows.append((p.label, p.total, p.calls, false,
                             p.measured ? "Rates checked against real usage" : "Published rates"))
                rows += p.models.prefix(4).map { (short($0.0), $0.1, $0.2, true, nil) }
            }
        } else {
            rows = snap.models.prefix(6).map { (short($0.0), $0.1, $0.2, false, nil) }
        }

        var columns = MenuRows.Columns()
        for (part, share) in zip(parts, shares) {
            columns.fit(part.0, dot: true, indent: false, amount: money(part.1),
                        detail: String(format: "%.1f%%", share * 100))
        }
        for row in rows {
            columns.fit(row.label, dot: false, indent: row.indent, amount: money(row.total), detail: callsText(row.calls))
        }

        let sub = NSMenu()
        sub.autoenablesItems = false
        sub.addItem(MenuRows.header("\(windowName(mode)), \(money(w.total))", inset: MenuRows.plainInset,
                                    width: columns.width))
        sub.addItem(MenuRows.split(zip(parts, shares).map { ($0.1, $0.0.2) }, width: columns.width))
        for (part, share) in zip(parts, shares) {
            sub.addItem(MenuRows.part(part.0, dot: part.2, amount: money(part.1),
                                      detail: String(format: "%.1f%%", share * 100), columns: columns))
        }
        if !rows.isEmpty {
            sub.addItem(.separator())
            sub.addItem(MenuRows.header(heading, inset: MenuRows.plainInset, width: columns.width))
            for row in rows {
                sub.addItem(MenuRows.part(row.label, dot: nil, indent: row.indent, amount: money(row.total),
                                          detail: callsText(row.calls), columns: columns, toolTip: row.tip))
            }
        }
        if snap.multi {
            let names = [("model", "Model"), ("harness", "Harness"), ("provider", "Provider")]
            let offered = names.filter { key, _ in
                key == "model" || (key == "harness" && snap.harnesses.count > 1)
                    || (key == "provider" && snap.providers.count > 1)
            }
            let byItem = NSMenuItem(title: "Break Down By", action: nil, keyEquivalent: "")
            let by = NSMenu()
            by.autoenablesItems = false
            for (key, label) in offered {
                add(by, label, #selector(setBreakdown(_:)), enabled: true,
                    state: key == choice).representedObject = key
            }
            byItem.submenu = by
            sub.addItem(.separator())
            sub.addItem(byItem)
        }
        return sub
    }

    @objc func setMode(_ sender: NSMenuItem) {
        if let key = sender.representedObject as? String { mode = key }
        render()
    }

    @objc func setBreakdown(_ sender: NSMenuItem) {
        if let key = sender.representedObject as? String { breakdown = key }
        render()
    }

    // From the Preferences window, which reads the codes from the engine.
    func chooseCurrency(_ code: String) {
        displayCurrency = code
        UserDefaults.standard.set(code, forKey: "currency")
        render()
    }

    @objc func openPreferences() {
        if preferences == nil { preferences = PreferencesWindow(controller: self) }
        preferences?.show(snap)
    }

    @objc func doRefresh() { refresh() }

    @objc func openDashboard() {
        let out = ("~/Downloads/Tokenmeter.html" as NSString).expandingTildeInPath
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        task.arguments = [engine, "--html", out]
        try? task.run()
    }

    @objc func doQuit() { NSApp.terminate(nil) }
}

let app = NSApplication.shared
let controller = Controller()
app.delegate = controller
app.setActivationPolicy(.accessory)
app.run()
