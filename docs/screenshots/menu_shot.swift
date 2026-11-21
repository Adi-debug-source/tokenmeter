// Takes the README's picture of the menu, from the real app running on the
// demo history that make_demo.py writes:
//
//   swift docs/screenshots/menu_shot.swift <demo folder> <output.png>
//       [--mode today|week|month|all] [--currency CODE] [--tokens on|off] [--open TITLE ...]
//
// It builds nothing and installs nothing. It starts the app built beside its
// source, costbar/costbar, with the demo's environment (env.sh, which
// make_demo.py writes, and TZ from this shell) and --open-menu, waits for the
// menu, has macOS's own screencapture take the menu's window, trims the
// picture to the menu's edge, so there is no shadow, ends that copy by its
// process id, and makes the file plain sRGB with shoot.py --plain.
//
// The settings come in on the command line, in the argument domain, which
// the app reads before its saved settings and never writes: Show Tokens on
// and US dollars unless told otherwise, the README's picture. So the
// installed app's settings are never touched, and only the demo's menu is
// ever captured, never the menu bar with a real figure in it.
//
// --mode ticks another period. Each --open opens the submenu whose title
// contains TITLE, one level deeper each time, and saves it beside the output
// as <output>-1.png, -2.png and so on: --open Where --open "Break Down By".
// It goes through the accessibility interface, which reaches the copy alone
// and which macOS lets this shell use only with its permission to control
// the computer. A key posted to the copy closes its menu instead.
//
// Run it from the top of the repository, after building the app:
//   swiftc -O -o costbar/costbar costbar/main.swift -framework AppKit
// The app runs the installed engine, so install the version the picture is
// for first. Take it on the day make_demo.py's --now names, since Today and
// the last 7 and 30 days come from the real clock, on a Retina screen, in
// dark mode, as the dashboard is dark too. macOS asks once for this shell to
// record the screen.

import AppKit
import ApplicationServices
import ImageIO
import UniformTypeIdentifiers

/// The copy while it runs and the whole captures before they are trimmed, so
/// a failure at any point ends the one and removes the others. `exit` skips
/// every `defer`, so `fail` and the last line see to both.
var runningDemo: Process?
var scratch: [URL] = []

func tidyUp() {
    runningDemo?.terminate()
    for file in scratch { try? FileManager.default.removeItem(at: file) }
}

func fail(_ message: String) -> Never {
    tidyUp()
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

/// Runs a tool and fails with its own words if it does.
func run(_ tool: String, _ arguments: [String]) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: tool)
    process.arguments = arguments
    do { try process.run() } catch { fail("Could not run \(tool): \(error)") }
    process.waitUntilExit()
    guard process.terminationStatus == 0 else { fail("\(tool) \(arguments.joined(separator: " ")) failed.") }
}

let usage = "Usage: swift docs/screenshots/menu_shot.swift <demo folder> <output.png> "
    + "[--mode today|week|month|all] [--currency CODE] [--tokens on|off] [--open TITLE ...]"
var positional: [String] = []
var settings = ["mode": "today", "currency": "USD", "showTokens": "YES"]
var submenus: [String] = []
var rest = CommandLine.arguments.dropFirst()
while let word = rest.popFirst() {
    switch word {
    case "--mode", "--currency", "--tokens", "--open":
        guard let value = rest.popFirst() else { fail(usage) }
        if word == "--open" {
            submenus.append(value)
        } else if word == "--mode" {
            guard ["today", "week", "month", "all"].contains(value) else { fail(usage) }
            settings["mode"] = value
        } else if word == "--currency" {
            settings["currency"] = value.uppercased()
        } else {
            guard ["on", "off"].contains(value) else { fail(usage) }
            settings["showTokens"] = value == "on" ? "YES" : "NO"
        }
    default:
        guard !word.hasPrefix("-") else { fail(usage) }
        positional.append(word)
    }
}
guard positional.count == 2 else { fail(usage) }
let folder = URL(fileURLWithPath: positional[0])
let output = URL(fileURLWithPath: positional[1])
let binary = FileManager.default.currentDirectoryPath + "/costbar/costbar"
guard FileManager.default.isExecutableFile(atPath: binary) else {
    fail("No build at \(binary). Run: swiftc -O -o costbar/costbar costbar/main.swift -framework AppKit")
}

// env.sh is make_demo.py's own: one export KEY='value' a line.
guard let envFile = try? String(contentsOf: folder.appendingPathComponent("env.sh"), encoding: .utf8) else {
    fail("No env.sh in \(folder.path). Write the demo first with docs/screenshots/make_demo.py.")
}
var environment: [String: String] = [:]
for line in envFile.split(separator: "\n") where line.hasPrefix("export ") {
    let pair = line.dropFirst("export ".count)
    guard let equals = pair.firstIndex(of: "=") else { continue }
    environment[String(pair[..<equals])] = String(pair[pair.index(after: equals)...]).trimmingCharacters(in: ["'"])
}
guard environment["HOME"] != nil, environment["TOKENMETER_LEDGER"] != nil else {
    fail("\(folder.path)/env.sh does not point Tokenmeter at a demo.")
}
if let zone = ProcessInfo.processInfo.environment["TZ"] { environment["TZ"] = zone }

/// A window of the copy's: where it is, and whether it is the one drawn on screen.
struct Window {
    let id: Int
    let bounds: CGRect
    let onScreen: Bool
}

func windows(of pid: Int32) -> [Window] {
    let list = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]] ?? []
    return list.compactMap { window in
        guard (window[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid,
              let id = (window[kCGWindowNumber as String] as? NSNumber)?.intValue,
              let box = window[kCGWindowBounds as String] as? [String: CGFloat] else { return nil }
        return Window(id: id,
                      bounds: CGRect(x: box["X"] ?? 0, y: box["Y"] ?? 0, width: box["Width"] ?? 0, height: box["Height"] ?? 0),
                      onScreen: (window[kCGWindowIsOnscreen as String] as? NSNumber)?.boolValue ?? false)
    }
}

/// An open menu is two windows, one inside the other: the menu itself, and
/// around it the one macOS draws on screen, which carries the shadow as well.
/// The menu bar item is a window too, but no window sits inside it.
func menus(of pid: Int32) -> [(drawn: Window, menu: Window)] {
    let found = windows(of: pid)
    return found.filter(\.onScreen).compactMap { outer in
        found.filter { !$0.onScreen && outer.bounds.contains($0.bounds) && $0.bounds.minX > outer.bounds.minX }
            .max { $0.bounds.height < $1.bounds.height }
            .map { (outer, $0) }
    }
}

/// screencapture takes the drawn window; this keeps only the menu inside it.
/// A submenu's window comes with the menu it hangs from, so its picture
/// covers both, and starts where they do.
func capture(_ pair: (drawn: Window, menu: Window), among open: [(drawn: Window, menu: Window)], to file: URL) {
    let whole = FileManager.default.temporaryDirectory.appendingPathComponent("tokenmeter_menu_\(UUID().uuidString).png")
    scratch.append(whole)
    run("/usr/sbin/screencapture", ["-x", "-o", "-l", String(pair.drawn.id), whole.path])
    guard let source = CGImageSourceCreateWithURL(whole as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        fail("screencapture wrote nothing. Allow this terminal to record the screen in System Settings, "
             + "Privacy & Security, Screen Recording.")
    }
    let all = open.map(\.drawn.bounds).reduce(pair.drawn.bounds) { $0.union($1) }
    guard let area = [pair.drawn.bounds, all].first(where: { area in
        let scale = CGFloat(image.width) / area.width
        return abs(area.height * scale - CGFloat(image.height)) < 2
    }) else { fail("screencapture took more or less than the menu's window.") }
    let scale = CGFloat(image.width) / area.width
    let box = CGRect(x: (pair.menu.bounds.minX - area.minX) * scale,
                     y: (pair.menu.bounds.minY - area.minY) * scale,
                     width: pair.menu.bounds.width * scale, height: pair.menu.bounds.height * scale).integral
    guard let trimmed = image.cropping(to: box),
          let destination = CGImageDestinationCreateWithURL(file as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        fail("Could not trim the picture to the menu.")
    }
    CGImageDestinationAddImage(destination, trimmed, nil)
    guard CGImageDestinationFinalize(destination) else { fail("Could not write \(file.path).") }
    written.append(file)
}
var written: [URL] = []

/// Opens the submenu whose title contains `name`, through the accessibility
/// interface, which reaches the copy alone. A key posted to the copy closes
/// its menu instead, and one posted to the system goes to whatever app is in
/// front.
func openSubmenu(_ name: String, of pid: Int32) {
    func children(_ element: AXUIElement) -> [AXUIElement] {
        var value: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXChildrenAttribute as CFString, &value)
        return value as? [AXUIElement] ?? []
    }
    func title(_ element: AXUIElement) -> String {
        var value: CFTypeRef?
        AXUIElementCopyAttributeValue(element, kAXTitleAttribute as CFString, &value)
        return value as? String ?? ""
    }
    guard AXIsProcessTrusted() else {
        fail("--open needs this terminal allowed to control the computer, in System Settings, "
             + "Privacy & Security, Accessibility.")
    }
    var queue = [AXUIElementCreateApplication(pid)]
    while !queue.isEmpty {
        let element = queue.removeFirst()
        if title(element).contains(name) {
            AXUIElementPerformAction(element, kAXPressAction as CFString)
            return
        }
        queue += children(element)
    }
    fail("No \(name) item in the open menu.")
}

/// Waits until `count` menus are open, then a moment more for them to draw.
func waitForMenus(_ count: Int, of demo: Process) -> [(drawn: Window, menu: Window)] {
    for _ in 0..<60 {
        usleep(250_000)
        guard demo.isRunning else { fail("The demo copy did not stay running.") }
        let open = menus(of: demo.processIdentifier)
        if open.count >= count {
            usleep(600_000)
            return menus(of: demo.processIdentifier)
        }
    }
    fail(count == 1 ? "The demo's menu did not open." : "The submenu did not open.")
}

let demo = Process()
demo.executableURL = URL(fileURLWithPath: binary)
demo.environment = environment
demo.arguments = ["--open-menu"] + settings.sorted { $0.key < $1.key }.flatMap { ["-" + $0.key, $0.value] }
do { try demo.run() } catch { fail("Could not start the demo copy: \(error)") }
runningDemo = demo

let opened = waitForMenus(1, of: demo)
capture(opened[0], among: opened, to: output)
// A submenu opens to the right, or to the left where the screen ends, so the
// new one is told apart by its window rather than its place.
var seen = Set(opened.map(\.menu.id))
for (level, name) in submenus.enumerated() {
    openSubmenu(name, of: demo.processIdentifier)
    let open = waitForMenus(level + 2, of: demo)
    guard let fresh = open.first(where: { !seen.contains($0.menu.id) }) else { fail("The submenu did not open.") }
    seen.insert(fresh.menu.id)
    capture(fresh, among: open, to: output.deletingLastPathComponent()
        .appendingPathComponent(output.deletingPathExtension().lastPathComponent + "-\(level + 1).png"))
}
tidyUp()
// Plain sRGB with nothing but what a PNG needs, as every README image is.
// Done once the copy has gone, since it takes a moment the open menu might not wait.
run("/usr/bin/python3", ["docs/screenshots/shoot.py", "--plain"] + written.map(\.path))
for file in written { print("Wrote \(file.path).") }
