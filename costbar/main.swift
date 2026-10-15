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
    var days: [Double] = []
    var cacheHit = 0.0
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
    var notes: [(level: String, text: String)] = []
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

// Column padding. String(format:) ignores a width on %@, so "%-16@" never
// padded anything and every column in the menu sat ragged. These pad by
// character count, which is exact in the monospaced font the rows use.
func padRight(_ s: String, _ width: Int) -> String {
    s.count >= width ? s : s + String(repeating: " ", count: width - s.count)
}

func padLeft(_ s: String, _ width: Int) -> String {
    s.count >= width ? s : String(repeating: " ", count: width - s.count) + s
}

// The font the padded rows are drawn in; the padding above counts on it.
func monospaced(_ s: String) -> NSAttributedString {
    NSAttributedString(string: s, attributes: [
        .font: NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
    ])
}

// A long note, broken into lines at word boundaries rather than cut off.
func wrapped(_ text: String, _ width: Int) -> String {
    var lines: [String] = [], line = ""
    for word in text.split(separator: " ") {
        if !line.isEmpty && line.count + 1 + word.count > width {
            lines.append(line)
            line = String(word)
        } else {
            line = line.isEmpty ? String(word) : line + " " + word
        }
    }
    if !line.isEmpty { lines.append(line) }
    return lines.joined(separator: "\n")
}

func sparkline(_ values: [Double]) -> String {
    let blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    guard let peak = values.max(), peak > 0 else { return "" }
    let top: Int = blocks.count - 1
    var out = ""
    for v in values {
        let scaled: Double = (v / peak) * Double(top)
        var i: Int = Int(scaled.rounded())
        if i < 0 { i = 0 }
        if i > top { i = top }
        out += blocks[i]
    }
    return out
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
    snap.cacheHit = root["cache_hit_pct"] as? Double ?? 0
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
    if let ds = root["days"] as? [[String: Any]] {
        snap.days = ds.map { ($0["total"] as? Double) ?? 0 }
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
        snap.notes = ns.map { (($0["level"] as? String) ?? "info", ($0["text"] as? String) ?? "") }
    }
    return snap
}

// The Show tokens row: its label and a small switch, set out like the menu's
// plain rows, in the menu's font and the system's own colours, so it follows
// the light or dark menu as they do. Clicking the switch leaves the menu open,
// so the change shows at once. A view in a menu gets no keyboard events; its
// menu item keeps the title and a key equivalent for that.
final class SwitchRow: NSView {
    // Where a plain item's title starts, where its key equivalent ends and
    // how tall it is, in this macOS's menus, which have changed with its
    // versions. AppKit has no call for these, but it gives a menu's size
    // without showing it: a view item is the view plus the menu's border, a
    // plain item its title plus the room around it, and a ticked one the
    // checkmark column as well. The room is taken as even on both sides, the
    // checkmark column on the left; this menu always has that column.
    static let metrics: (leading: CGFloat, trailing: CGFloat, height: CGFloat) = {
        func size(_ item: NSMenuItem) -> NSSize {
            let menu = NSMenu()
            menu.addItem(item)
            return menu.size
        }
        let probe = NSMenuItem()
        probe.view = NSView(frame: NSRect(x: 0, y: 0, width: 100, height: 20))
        let border = NSSize(width: size(probe).width - 100, height: size(probe).height - 20)
        let title = "Show tokens"
        let text = (title as NSString).size(withAttributes: [.font: NSFont.menuFont(ofSize: 0)]).width
        let plain = size(NSMenuItem(title: title, action: nil, keyEquivalent: ""))
        let ticked = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        ticked.state = .on
        let side = max(0, (plain.width - border.width - text) / 2)
        let column = max(0, size(ticked).width - plain.width)
        return ((side + column).rounded(), side.rounded(), max(22, plain.height - border.height))
    }()
    static let gap: CGFloat = 16

    let label = NSTextField(labelWithString: "")
    let toggle = NSSwitch()

    init(title: String, on: Bool, tip: String, target: AnyObject, action: Selector) {
        let m = SwitchRow.metrics
        super.init(frame: .zero)
        label.stringValue = title
        label.font = NSFont.menuFont(ofSize: 0)
        label.textColor = .labelColor
        // The switch names itself; the label read out as well would say it twice.
        label.setAccessibilityElement(false)
        toggle.controlSize = .small
        toggle.state = on ? .on : .off
        toggle.target = target
        toggle.action = action
        toggle.setAccessibilityLabel(title)
        toggle.setAccessibilityHelp(tip)
        for v in [self, label, toggle] as [NSView] { v.toolTip = tip }
        for v in [label, toggle] as [NSView] {
            v.translatesAutoresizingMaskIntoConstraints = false
            addSubview(v)
        }
        // The width the row asks of the menu, which widens it to its own.
        // Outside a window a switch can give its regular size, larger than
        // the small one it takes in the menu, so this is never too narrow.
        // The constraints place the switch at whatever size it takes there.
        frame = NSRect(x: 0, y: 0, width: m.leading + label.intrinsicContentSize.width.rounded(.up)
                           + SwitchRow.gap + toggle.intrinsicContentSize.width + m.trailing,
                       height: m.height)
        autoresizingMask = [.width]
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: leadingAnchor, constant: m.leading),
            label.centerYAnchor.constraint(equalTo: centerYAnchor),
            toggle.leadingAnchor.constraint(greaterThanOrEqualTo: label.trailingAnchor,
                                            constant: SwitchRow.gap),
            toggle.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -m.trailing),
            toggle.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
    }

    required init?(coder: NSCoder) { fatalError("SwitchRow is built in code") }
}

final class Controller: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var timer: Timer?
    var snap = Snapshot()
    var busy = false

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

    // Total tokens beside each cost, in the title and on every window row.
    // Off unless switched on from the menu, so both are what they always
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
    static let windowNames: [String: (long: String, possessive: String)] = [
        "today": ("Today", "today's"),
        "week":  ("Last 7 days", "the week's"),
        "month": ("Last 30 days", "the last 30 days'"),
        "all":   ("All time", "all of it"),
    ]

    // In the order the menu lists them.
    static let windowKeys = ["today", "week", "month", "all"]

    func windowName(_ key: String) -> String {
        Controller.windowNames[key]?.long ?? "All time"
    }

    func windowPossessive(_ key: String) -> String {
        Controller.windowNames[key]?.possessive ?? "all of it"
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

    // A window's row: its name and cost, and with Show tokens on its total
    // tokens after the cost, as the title writes them, for example
    // "All time         $1,024.50 · 1.62B". With it on, the cost and token
    // columns are as wide as the widest of the four rows, so the dots and
    // the counts line up; off, the row is the name and the cost alone.
    func windowLine(_ key: String) -> String {
        let w = window(key), keys = Controller.windowKeys
        guard showTokens else { return padRight(windowName(key), 14) + padLeft(money(w.total), 12) }
        let costs = max(12, keys.map { money(window($0).total).count }.max() ?? 0)
        let counts = keys.map { toks(window($0).tokens).count }.max() ?? 0
        return padRight(windowName(key), 14) + padLeft(money(w.total), costs)
            + " · " + padLeft(toks(w.tokens), counts)
    }

    func render() {
        showTitle()
        buildMenu()
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
             key: String = "", indent: Int = 0, enabled: Bool? = nil,
             mono: Bool = false, state: Bool = false) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: key)
        mi.target = self
        mi.indentationLevel = indent
        mi.isEnabled = enabled ?? (action != nil)
        if state { mi.state = .on }
        if mono {
            mi.attributedTitle = monospaced(title)
        } else if title.contains("\n") {
            // A plain title draws on one line; an attributed one honours breaks.
            mi.attributedTitle = NSAttributedString(string: title, attributes: [
                .font: NSFont.menuFont(ofSize: 0)
            ])
        }
        menu.addItem(mi)
        return mi
    }

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

        add(menu, "Tokenmeter at API rates")

        menu.addItem(.separator())
        for key in Controller.windowKeys {
            let w = window(key)
            let mi = add(menu, windowLine(key), #selector(setMode(_:)), enabled: true,
                         mono: true, state: mode == key)
            mi.representedObject = key
            let calls = "\(w.calls) API call" + (w.calls == 1 ? "" : "s")
            mi.toolTip = key == "all" && !snap.covered.isEmpty
                ? "\(calls), covering \(snap.covered). Show this one in the menu bar."
                : "\(calls). Show this one in the menu bar."
        }

        let w = current()
        menu.addItem(.separator())
        add(menu, "Where \(windowPossessive(mode)) went")
        var parts: [(String, Double)] = [("Cache writes", w.cacheWrite), ("Cache reads", w.cacheRead),
                                         ("Output", w.output), ("Input, uncached", w.input)]
        if w.webSearch > 0 { parts.append(("Web searches", w.webSearch)) }
        for (label, v) in parts {
            let pct = w.total > 0 ? v / w.total * 100 : 0
            add(menu, padRight(label, 16) + padLeft(money(v), 11) + padLeft(String(format: "%.1f%%", pct), 8),
                indent: 1, mono: true)
        }

        func callsText(_ n: Int) -> String { padLeft("\(n)", 7) + (n == 1 ? " call" : " calls") }

        // By model is the breakdown that matters most and always the default.
        // Only when harnesses or providers are mixed can the menu be switched
        // to show those instead, from the "Break down by" submenu.
        let choice = snap.multi ? breakdown : "model"
        if choice == "harness" && snap.harnesses.count > 1 {
            menu.addItem(.separator())
            add(menu, "By harness, all time")
            let width = max(snap.harnesses.map { $0.label.count }.max() ?? 0, 10)
            for h in snap.harnesses {
                let mark = h.status == "verified" ? "\u{2713}" : "\u{25CB}"
                add(menu, mark + " " + padRight(h.label, width) + padLeft(money(h.total), 11)
                        + callsText(h.calls), indent: 1, mono: true).toolTip =
                    h.status == "verified" ? "Verified: checked against real logs"
                    : h.status == "yours" ? "Imported by you"
                    : "Unverified: built from the published log format"
            }
        } else if choice == "provider" && snap.providers.count > 1 {
            menu.addItem(.separator())
            add(menu, "By provider, all time")
            for p in snap.providers {
                add(menu, padRight(p.label, 26) + padLeft(money(p.total), 11) + callsText(p.calls),
                    indent: 1, mono: true).toolTip = p.measured
                    ? "Rates checked against real usage" : "Published rates"
                for (name, total, calls) in p.models.prefix(4) {
                    let short = name.replacingOccurrences(of: "claude-", with: "")
                    add(menu, padRight("  " + short, 26) + padLeft(money(total), 11) + callsText(calls),
                        indent: 1, mono: true)
                }
            }
        } else if !snap.models.isEmpty {
            menu.addItem(.separator())
            add(menu, "By model, all time")
            for (name, total, calls) in snap.models.prefix(6) {
                let short = name.replacingOccurrences(of: "claude-", with: "")
                add(menu, padRight(short, 26) + padLeft(money(total), 11) + callsText(calls),
                    indent: 1, mono: true)
            }
        }
        if snap.multi {
            let names = [("model", "Model"), ("harness", "Harness"), ("provider", "Provider")]
            let offered = names.filter { key, _ in
                key == "model" || (key == "harness" && snap.harnesses.count > 1)
                    || (key == "provider" && snap.providers.count > 1)
            }
            let current = offered.first { $0.0 == choice }?.1 ?? "Model"
            let byItem = NSMenuItem(title: "Break down by: \(current)", action: nil, keyEquivalent: "")
            let sub = NSMenu()
            sub.autoenablesItems = false
            for (key, label) in offered {
                let mi = add(sub, label, #selector(setBreakdown(_:)), enabled: true, state: key == choice)
                mi.representedObject = key
            }
            byItem.submenu = sub
            menu.addItem(byItem)
        }

        menu.addItem(.separator())
        add(menu, "What caching is worth, all time")
        // Saved is derived from the two rounded figures rather than rounded on
        // its own, so the three lines add up as printed. Rounding each
        // separately left the column a penny out in some currencies; the
        // figures behind them were always exact. Same rule as the report.
        // When caching cost more than it saved, that is named as a cost; a
        // saving below zero read "-99.7% cheaper, 0.5x".
        let dearer = cachingDearer(snap.withoutCache, snap.all.total)
        let shownSaved = dearer ? shownDifference(snap.all.total, snap.withoutCache)
                                : shownDifference(snap.withoutCache, snap.all.total)
        let cmp: [(String, Double)] = [("With cache reads", snap.all.total),
                                       ("Without cache reads", snap.withoutCache),
                                       (dearer ? "Caching cost" : "Saved", shownSaved)]
        for (label, v) in cmp {
            add(menu, padRight(label, 21) + padLeft(money(v), 12), indent: 1, mono: true)
        }
        if snap.withoutCache > 0 && snap.all.total > 0 {
            add(menu, dearer
                ? String(format: "%.1f%% dearer", -snap.savedPct)
                : String(format: "%.1f%% cheaper, %.1fx", max(snap.savedPct, 0), snap.multiple),
                indent: 1)
        }

        menu.addItem(.separator())
        // The engine sends the last 30 calendar days, a quiet day at zero. A
        // month with no spend at all has nothing to draw.
        if snap.days.contains(where: { $0 > 0 }) {
            add(menu, sparkline(Array(snap.days.suffix(30))), indent: 1, mono: true)
                .toolTip = "Daily spend, last 30 days"
        }
        // %.1f, matching the terminal report. At 95.5 the two faces were
        // printing 96% and 95.5% for one number.
        add(menu, String(format: "%.1f%% of prompt tokens served from cache", snap.cacheHit), indent: 1)

        // Provenance and warnings, exactly as the terminal report words them.
        // Long lines are shortened here and kept whole in the tooltip.
        if !snap.notes.isEmpty {
            menu.addItem(.separator())
            for note in snap.notes {
                let prefix = note.level == "warn" ? "\u{26A0}\u{FE0E} " : ""
                // Shown whole, wrapped onto as many lines as it needs.
                add(menu, wrapped(prefix + note.text, 58), indent: 1).toolTip = note.text
            }
        }

        menu.addItem(.separator())
        let curItem = NSMenuItem(title: "Currency", action: nil, keyEquivalent: "")
        let curMenu = NSMenu()
        curMenu.autoenablesItems = false
        for code in currencyOrder {
            let sym = currencySymbols[code] ?? ""
            let line = code == "USD"
                ? "\(sym) USD  (billed)"
                : String(format: "%@ %@  %.4f", sym, code, rate(code))
            let mi = NSMenuItem(title: line, action: #selector(setCurrency(_:)), keyEquivalent: "")
            mi.target = self
            mi.isEnabled = true
            mi.representedObject = code
            if code == displayCurrency { mi.state = .on }
            curMenu.addItem(mi)
        }
        curMenu.addItem(.separator())
        let src = NSMenuItem(title: snap.rateLive ? "Live rates, \(snap.rateWhen)"
                                                  : "Rates: \(snap.rateWhen)",
                             action: nil, keyEquivalent: "")
        src.isEnabled = false
        curMenu.addItem(src)
        curItem.submenu = curMenu
        menu.addItem(curItem)
        // One switch for the tokens in the title and on every window row. The
        // item's own title and key equivalent are the keyboard's way to it,
        // since the switch in its view never gets a key.
        let tip = "Total tokens beside the cost, in the menu bar and on every row: uncached input, "
            + "cache writes, cache reads and output. \u{2318}T switches it while this menu is open."
        let tokensItem = NSMenuItem(title: "Show tokens", action: #selector(toggleTokens(_:)),
                                    keyEquivalent: "t")
        tokensItem.target = self
        tokensItem.toolTip = tip
        tokensItem.view = SwitchRow(title: "Show tokens", on: showTokens, tip: tip,
                                    target: self, action: #selector(switchTokens(_:)))
        menu.addItem(tokensItem)

        menu.addItem(.separator())
        add(menu, "Open the full dashboard", #selector(openDashboard))
        add(menu, "Refresh now", #selector(doRefresh), key: "r")
        add(menu, "Quit Tokenmeter", #selector(doQuit), key: "q")

        item.menu = menu
    }

    @objc func setMode(_ sender: NSMenuItem) {
        if let key = sender.representedObject as? String { mode = key }
        render()
    }

    @objc func setBreakdown(_ sender: NSMenuItem) {
        if let key = sender.representedObject as? String { breakdown = key }
        render()
    }

    @objc func setCurrency(_ sender: NSMenuItem) {
        if let code = sender.representedObject as? String {
            displayCurrency = code
            UserDefaults.standard.set(code, forKey: "currency")
        }
        render()
    }

    // The switch, clicked: the menu stays open.
    @objc func switchTokens(_ sender: NSSwitch) {
        showTokens = sender.state == .on
        tokensChanged(sender.enclosingMenuItem?.menu)
    }

    // Command-T, the keyboard's way to the same setting.
    @objc func toggleTokens(_ sender: NSMenuItem) {
        showTokens.toggle()
        tokensChanged(sender.menu)
    }

    // Show tokens takes effect at once: the title, and every window row and
    // the switch of the menu as it stands. They are changed in place, since
    // the menu may be open and one built afresh would only show the next
    // time it opened. A refresh can build the status item a new menu while
    // the old one is still open, so both are changed.
    func tokensChanged(_ open: NSMenu?) {
        showTitle()
        var menus = [item.menu].compactMap { $0 }
        if let open = open, open !== item.menu { menus.append(open) }
        for menu in menus {
            for mi in menu.items {
                if mi.action == #selector(setMode(_:)), let key = mi.representedObject as? String {
                    mi.title = windowLine(key)
                    mi.attributedTitle = monospaced(mi.title)
                } else if let row = mi.view as? SwitchRow {
                    row.toggle.state = showTokens ? .on : .off
                }
            }
        }
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
