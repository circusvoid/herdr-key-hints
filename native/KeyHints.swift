// 原生展示层：只接收插件推断出的快捷键，不安装全局键盘监听。
import AppKit

struct Entry: Decodable {
    let id: Int
    let chord: String
    let count: Int
    let updated: Double
    let expires: Double
}
struct Frame: Decodable {
    let generated: Double
    let position: String
    let fade_ms: Double
    let max_visible: Int
    let terminal_apps: [String]
    let entries: [Entry]
}

func tokens(_ chord: String) -> [String] {
    var result: [String] = []
    let steps = chord.components(separatedBy: " → ")
    for (index, step) in steps.enumerated() {
        if index > 0 { result.append("sequence-separator") }
        var rest = step[...]
        while let first = rest.first, "⌃⌥⇧⌘".contains(first) {
            result.append(String(first)); rest.removeFirst()
        }
        if !rest.isEmpty { result.append(String(rest)) }
    }
    return result
}

// 用相同的视图绘制屏幕浮层和离线验收图片。
final class HintView: NSView {
    var entries: [Entry] = []
    var timestamp = Date().timeIntervalSince1970
    var fade: Double = 0.2
    var position = "bottom-right"
    var capacity: Int?
    var appeared: [Int: Double] = [:]
    func update(_ items: [Entry], now: Double) {
        let existing = Set(entries.map { $0.id })
        for item in items where !existing.contains(item.id) { appeared[item.id] = now }
        let alive = Set(items.map { $0.id })
        appeared = appeared.filter { alive.contains($0.key) }
        entries = items
        timestamp = now
    }
    let rowHeight: CGFloat = 66
    let rowGap: CGFloat = 10
    let inset: CGFloat = 16
    override var isFlipped: Bool { true }

    func keyWidth(_ token: String) -> CGFloat {
        let font = NSFont.systemFont(ofSize: 24, weight: .medium)
        return max(38, (token as NSString).size(withAttributes: [.font: font]).width + 22)
    }
    func rowWidth(_ entry: Entry) -> CGFloat {
        let parts = tokens(entry.chord)
        let keys = parts.reduce(CGFloat(0)) { $0 + ($1 == "sequence-separator" ? 24 : keyWidth($1)) }
        return 24 + keys + CGFloat(max(0, parts.count - 1)) * 7 + (entry.count > 1 ? 48 : 0)
    }
    func idealSize() -> NSSize {
        NSSize(width: max(140, entries.map(rowWidth).max() ?? 140) + inset * 2,
               height: CGFloat(capacity ?? entries.count) * (rowHeight + rowGap) - rowGap + inset * 2)
    }
    func text(_ value: String, in rect: NSRect, font: NSFont, color: NSColor) {
        let style = NSMutableParagraphStyle(); style.alignment = .center
        let size = (value as NSString).size(withAttributes: [.font: font])
        (value as NSString).draw(in: NSRect(x: rect.minX, y: rect.midY - size.height / 2,
                                           width: rect.width, height: size.height),
                                withAttributes: [.font: font, .foregroundColor: color, .paragraphStyle: style])
    }
    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        for (index, entry) in entries.enumerated() {
            let remaining = entry.expires - timestamp
            guard remaining > 0 else { continue }
            let opacity = fade > 0 ? min(1, remaining / fade) : 1
            // 淡入只应用于新增组；重复更新同组不闪烁。
            let entrance = min(1, max(0, (timestamp - (appeared[entry.id] ?? timestamp - 1)) / 0.10))
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current?.cgContext.setAlpha(opacity * entrance)
            let width = rowWidth(entry)
            let x: CGFloat = position.hasSuffix("left") ? inset : position.hasSuffix("center") ? (bounds.width-width)/2 : bounds.width - inset - width
            let offset = position.hasPrefix("bottom") ? max(0, (capacity ?? entries.count) - entries.count) : 0
            let y = inset + CGFloat(index + offset) * (rowHeight + rowGap)
            let row = NSRect(x: x, y: y, width: width, height: rowHeight)
            let shell = NSBezierPath(roundedRect: row, xRadius: 16, yRadius: 16)
            NSGraphicsContext.saveGraphicsState()
            let shadow = NSShadow(); shadow.shadowColor = NSColor.black.withAlphaComponent(0.22)
            shadow.shadowBlurRadius = 10; shadow.shadowOffset = NSSize(width: 0, height: 3); shadow.set()
            NSColor(calibratedWhite: 0.085, alpha: 0.94).setFill(); shell.fill()
            NSGraphicsContext.restoreGraphicsState()
            NSColor.white.withAlphaComponent(0.13).setStroke(); shell.lineWidth = 0.75; shell.stroke()
            var cursor = x + 12
            for token in tokens(entry.chord) {
                let keyW = token == "sequence-separator" ? 24 : keyWidth(token)
                let rect = NSRect(x: cursor, y: y + 12, width: keyW, height: 42)
                if token == "sequence-separator" {
                    text("→", in: rect, font: .systemFont(ofSize: 18), color: .white.withAlphaComponent(0.45))
                } else {
                    let modifier = token.count == 1 && "⌃⌥⇧⌘".contains(token)
                    let cap = NSBezierPath(roundedRect: rect, xRadius: 8, yRadius: 8)
                    NSColor.white.withAlphaComponent(modifier ? 0.065 : 0.12).setFill(); cap.fill()
                    NSColor.white.withAlphaComponent(0.10).setStroke(); cap.lineWidth = 0.6; cap.stroke()
                    text(token, in: rect, font: .systemFont(ofSize: 24, weight: .medium),
                         color: .white.withAlphaComponent(modifier ? 0.73 : 0.98))
                }
                cursor += keyW + 7
            }
            if entry.count > 1 {
                text("×\(min(entry.count, 999))", in: NSRect(x: cursor, y: y+12, width: 39, height: 42),
                     font: .monospacedDigitSystemFont(ofSize: 14, weight: .medium),
                     color: .white.withAlphaComponent(0.58))
            }
            NSGraphicsContext.restoreGraphicsState()
        }
    }
}

final class PassivePanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class Presenter {
    let panel: PassivePanel
    let view = HintView()
    let path: String
    let parent: pid_t
    var lastData: Data?
    var current: Frame?
    var suppressedBefore = Date().timeIntervalSince1970
    var timer: Timer?

    init(path: String, parent: pid_t) {
        self.path = path; self.parent = parent
        panel = PassivePanel(contentRect: NSRect(x: 0, y: 0, width: 400, height: 300),
                             styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isOpaque = false; panel.backgroundColor = .clear
        panel.hasShadow = false; panel.ignoresMouseEvents = true
        panel.level = .floating; panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.contentView = view
        panel.setAccessibilityLabel("Herdr 快捷键提示")
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 30, repeats: true) { [weak self] _ in self?.tick() }
        timer?.tolerance = 0.005
    }
    func tick() {
        if getppid() != parent || kill(parent, 0) != 0 { NSApp.terminate(nil); return }
        let now = Date().timeIntervalSince1970
        guard let data = try? Data(contentsOf: URL(fileURLWithPath: path)), data.count < 65536 else {
            panel.orderOut(nil); current = nil; lastData = nil; view.entries = []; view.appeared = [:]; return
        }
        if data != lastData {
            current = try? JSONDecoder().decode(Frame.self, from: data)
            lastData = data
        }
        guard let frame = current else { panel.orderOut(nil); return }
        let bundle = NSWorkspace.shared.frontmostApplication?.bundleIdentifier ?? ""
        guard frame.terminal_apps.contains(bundle) else {
            suppressedBefore = now; panel.orderOut(nil); view.entries = []; view.appeared = [:]; return
        }
        // 同一用户的多个会话中，只让最近产生操作的会话显示，避免浮层重叠。
        let ownURL = URL(fileURLWithPath: path)
        if let peers = try? FileManager.default.contentsOfDirectory(at: ownURL.deletingLastPathComponent(), includingPropertiesForKeys: nil) {
            for peer in peers where peer.lastPathComponent.hasSuffix(".overlay.json") && peer.path != path {
                if let otherData = try? Data(contentsOf: peer), otherData.count < 65536,
                   let other = try? JSONDecoder().decode(Frame.self, from: otherData), other.generated > frame.generated {
                    suppressedBefore = max(suppressedBefore, other.generated)
                    panel.orderOut(nil); return
                }
            }
        }
        let entries = frame.entries.filter { $0.expires > now && $0.updated >= suppressedBefore }
        guard !entries.isEmpty else { panel.orderOut(nil); return }
        view.update(entries, now: now); view.capacity = frame.max_visible; view.fade = frame.fade_ms / 1000; view.position = frame.position
        // 鼠标所在屏幕通常就是用户正在操作的终端屏幕；不申请辅助功能或录屏权限。
        let mouse = NSEvent.mouseLocation
        guard let screen = NSScreen.screens.first(where: { $0.frame.contains(mouse) }) ?? NSScreen.main else { return }
        let visible = screen.visibleFrame
        let ideal = view.idealSize()
        // 超长自定义组合键等比缩小，保证不会超出屏幕。
        let scale = min(1, (visible.width - 32) / ideal.width)
        let size = NSSize(width: ideal.width * scale, height: ideal.height * scale)
        let margin: CGFloat = 20
        let x: CGFloat = frame.position.hasSuffix("left") ? visible.minX + margin : frame.position.hasSuffix("center") ? visible.midX - size.width/2 : visible.maxX - margin - size.width
        let y: CGFloat = frame.position.hasPrefix("top") ? visible.maxY - margin - size.height : visible.minY + margin
        panel.setFrame(NSRect(origin: NSPoint(x: x, y: y), size: size), display: false)
        view.frame = NSRect(origin: .zero, size: size); view.bounds = NSRect(origin: .zero, size: ideal)
        view.needsDisplay = true
        if !panel.isVisible { panel.orderFrontRegardless() }
    }
}

let application = NSApplication.shared
application.setActivationPolicy(.accessory)
if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
    precondition(tokens("⇧⌘D") == ["⇧", "⌘", "D"])
    precondition(tokens("⌃B → ⇧N") == ["⌃", "B", "sequence-separator", "⇧", "N"])
    precondition(tokens("⌘Enter") == ["⌘", "Enter"])
    precondition(tokens("⌘→") == ["⌘", "→"])
    let presenter = Presenter(path: "/tmp/key-hints-unused", parent: getppid())
    precondition(!presenter.panel.canBecomeKey && !presenter.panel.canBecomeMain)
    precondition(presenter.panel.ignoresMouseEvents)
    precondition(presenter.panel.styleMask.contains(.nonactivatingPanel))
    print("原生键帽分词、非激活窗口和鼠标穿透属性通过")
} else if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--render-preview" {
    let view = HintView(frame: NSRect(x: 0, y: 0, width: 400, height: 280))
    let now = Date().timeIntervalSince1970
    view.timestamp = now
    view.entries = [Entry(id: 1, chord: "⌘T", count: 1, updated: now, expires: now+10),
                    Entry(id: 2, chord: "⇧⌘D", count: 1, updated: now, expires: now+10),
                    Entry(id: 3, chord: "⌃B → N", count: 3, updated: now, expires: now+10)]
    view.setFrameSize(view.idealSize())
    guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { exit(1) }
    view.cacheDisplay(in: view.bounds, to: bitmap)
    guard let png = bitmap.representation(using: .png, properties: [:]) else { exit(1) }
    try png.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
} else if CommandLine.arguments.count == 3, let parent = Int32(CommandLine.arguments[2]) {
    let presenter = Presenter(path: CommandLine.arguments[1], parent: parent)
    withExtendedLifetime(presenter) { application.run() }
} else {
    fputs("用法：key-hints <帧文件> <父进程 PID>\n", stderr)
    exit(2)
}
