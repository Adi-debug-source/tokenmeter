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

// Which currencies exist and what they look like is tokenmeter.py's business,
// not this file's. These are only what shows before the first load returns.
let currencyOrder = ["USD", "GBP", "EUR", "INR"]
var currencySymbols: [String: String] = ["GBP": "\u{00A3}", "USD": "$"]

// Everything is held in dollars. Only display converts.
var displayCurrency = UserDefaults.standard.string(forKey: "currency") ?? "USD"
var displayRates: [String: Double] = ["USD": 1.0]

func rate(_ code: String) -> Double { displayRates[code] ?? (code == "USD" ? 1.0 : 1.0) }

struct Window {
    var total = 0.0, calls = 0
    var input = 0.0, cacheWrite = 0.0, cacheRead = 0.0, output = 0.0
    // Billed per request, not per token. Zero for most people, but leaving it
    // out of the breakdown made the four lines fail to add up to the total.
    var webSearch = 0.0
}

struct Snapshot {
    var today = Window(), week = Window(), month = Window(), all = Window()
    var models: [(String, Double, Int)] = []
    var days: [Double] = []
    var cacheHit = 0.0
    var withoutCache = 0.0
    var saved = 0.0
    var rateWhen = ""
    var rateLive = true
    var covered = ""
    var tokens: [String: Int] = [:]
    // What the engine says must be shown beside the figures: when each price
    // table was checked, and any warning about how far to trust a number.
    var notes: [(level: String, text: String)] = []
    var failed: String?
}

let groupedTwoDP: NumberFormatter = {
    let f = NumberFormatter()
    f.numberStyle = .decimal
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
    if x == 0 { return s + "0.00" }
    // Real money below the smallest printable figure. "0.0000" would read as
    // nothing at all, which is the thing being fixed here.
    if abs(x) < 0.00005 { return (x < 0 ? "-" : "") + "<" + s + "0.0001" }
    if abs(x) < 0.01 { return s + String(format: "%.4f", x) }
    return s + (groupedTwoDP.string(from: NSNumber(value: x)) ?? String(format: "%.2f", x))
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

func toks(_ n: Int) -> String {
    if n >= 1_000_000_000 { return String(format: "%.2fB", Double(n) / 1_000_000_000) }
    if n >= 1_000_000 { return String(format: "%.1fM", Double(n) / 1_000_000) }
    if n >= 1_000 { return String(format: "%.0fk", Double(n) / 1_000) }
    return "\(n)"
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
        return w
    }

    snap.today = window("today")
    snap.week = window("week")
    snap.month = window("month")
    snap.all = window("all")
    snap.cacheHit = root["cache_hit_pct"] as? Double ?? 0
    snap.withoutCache = root["without_cache"] as? Double ?? 0
    snap.saved = root["no_cache_saved"] as? Double ?? 0
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
    snap.tokens = root["tokens"] as? [String: Int] ?? [:]
    if let ms = root["models"] as? [[String: Any]] {
        snap.models = ms.map { (($0["name"] as? String) ?? "?",
                                ($0["total"] as? Double) ?? 0,
                                ($0["calls"] as? Int) ?? 0) }
    }
    if let ds = root["days"] as? [[String: Any]] {
        snap.days = ds.map { ($0["total"] as? Double) ?? 0 }
    }
    if let ns = root["notes"] as? [[String: Any]] {
        snap.notes = ns.map { (($0["level"] as? String) ?? "info", ($0["text"] as? String) ?? "") }
    }
    return snap
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

    func windowName(_ key: String) -> String {
        Controller.windowNames[key]?.long ?? "All time"
    }

    func windowPossessive(_ key: String) -> String {
        Controller.windowNames[key]?.possessive ?? "all of it"
    }

    func current() -> Window {
        switch mode {
        case "week": return snap.week
        case "month": return snap.month
        case "all": return snap.all
        default: return snap.today
        }
    }

    func render() {
        if let err = snap.failed {
            item.button?.title = "  –"
            item.button?.toolTip = err
        } else {
            // Just the amount. Which window it is was the user's own choice
            // from this menu, so prefixing it says something already known
            // and costs width in a crowded menu bar. The tooltip still says.
            item.button?.title = "  \(money(current().total))"
            item.button?.toolTip = "\(windowName(mode)), at API rates"
        }
        buildMenu()
    }

    @discardableResult
    func add(_ menu: NSMenu, _ title: String, _ action: Selector? = nil,
             key: String = "", indent: Int = 0, enabled: Bool? = nil,
             mono: Bool = false, state: Bool = false) -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: key)
        mi.target = self
        mi.indentationLevel = indent
        mi.isEnabled = enabled ?? (action != nil)
        if action == nil && enabled == nil { mi.isEnabled = false }
        if state { mi.state = .on }
        if mono {
            mi.attributedTitle = NSAttributedString(string: title, attributes: [
                .font: NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
            ])
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
        for (key, w) in [("today", snap.today), ("week", snap.week),
                         ("month", snap.month), ("all", snap.all)] {
            let label = windowName(key)
            let line = padRight(label, 14) + padLeft(money(w.total), 12)
            let mi = add(menu, line, #selector(setMode(_:)), enabled: true,
                         mono: true, state: mode == key)
            mi.representedObject = key
            mi.toolTip = key == "all" && !snap.covered.isEmpty
                ? "\(w.calls) API calls, covering \(snap.covered). Show this one in the menu bar."
                : "\(w.calls) API calls. Show this one in the menu bar."
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

        if !snap.models.isEmpty {
            menu.addItem(.separator())
            add(menu, "By model, all time")
            for (name, total, calls) in snap.models.prefix(6) {
                let short = name.replacingOccurrences(of: "claude-", with: "")
                add(menu, padRight(short, 26) + padLeft(money(total), 11) + padLeft("\(calls)", 7) + (calls == 1 ? " call" : " calls"),
                    indent: 1, mono: true)
            }
        }

        menu.addItem(.separator())
        add(menu, "What caching is worth, all time")
        // Saved is derived from the two rounded figures rather than rounded on
        // its own, so the three lines add up as printed. Rounding each
        // separately left the column a penny out in some currencies; the
        // figures behind them were always exact. Same rule as the report.
        let shownSaved = shownDifference(snap.withoutCache, snap.all.total)
        let cmp: [(String, Double)] = [("With cache reads", snap.all.total),
                                       ("Without cache reads", snap.withoutCache),
                                       ("Saved", shownSaved)]
        for (label, v) in cmp {
            add(menu, padRight(label, 21) + padLeft(money(v), 12), indent: 1, mono: true)
        }
        if snap.withoutCache > 0 && snap.all.total > 0 {
            add(menu, String(format: "%.1f%% cheaper, %.1fx", 
                             snap.saved / snap.withoutCache * 100,
                             snap.withoutCache / snap.all.total), indent: 1)
        }

        menu.addItem(.separator())
        if !snap.days.isEmpty {
            add(menu, sparkline(snap.days.suffix(30).map { $0 }), indent: 1, mono: true)
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

    @objc func setCurrency(_ sender: NSMenuItem) {
        if let code = sender.representedObject as? String {
            displayCurrency = code
            UserDefaults.standard.set(code, forKey: "currency")
        }
        render()
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
