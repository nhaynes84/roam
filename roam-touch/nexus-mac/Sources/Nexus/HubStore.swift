import Foundation
import Observation

enum ConnectionState: Equatable {
    case connecting
    case connected
    case reconnecting(detail: String)
}

/// One channel's thread as held in memory. `delivered` is the set of `sent`
/// event ids whose echo receipt has come back — rendered once, as delivered,
/// never as a second row.
struct ChannelThread: Sendable {
    var events: [Event] = []
    var delivered: Set<Int> = []
    var historyLoaded: Bool = false

    init(events: [Event] = [], delivered: Set<Int> = [], historyLoaded: Bool = false) {
        self.events = events
        self.delivered = delivered
        self.historyLoaded = historyLoaded
    }

    mutating func upsert(_ event: Event) -> Bool {
        if let echoOf = event.echoOf {
            if events.contains(where: { $0.id == echoOf }) {
                // The confirmation that `sent` #echoOf reached the pane.
                delivered.insert(echoOf)
                return false
            }
            // Referenced sent is outside the window we hold: a message shown
            // twice is a nuisance, shown zero times is a lie — render it.
        }
        guard !events.contains(where: { $0.id == event.id }) else { return false }
        let at = events.firstIndex(where: { $0.id > event.id }) ?? events.endIndex
        events.insert(event, at: at)
        return true
    }
}

@MainActor @Observable
final class HubStore {
    var channels: [Channel] = []
    var threads: [String: ChannelThread] = [:]
    var connection: ConnectionState = .connecting
    var hubVersion: String?
    var pendingEvents = 0
    // Selection does NOT mark read here: the thread view snapshots the unread
    // boundary first (to place the NEW divider), then marks read itself.
    var selectedPane: String? {
        didSet { presenceDirty = true }
    }
    /// Set by the UI when the app is frontmost; gates read-tracking and presence.
    var appActive = false {
        didSet {
            presenceDirty = true
            // Coming back to the app (wake, unhide) with a broken link: don't
            // wait out the watchdog + backoff — reconnect right now.
            if appActive, !oldValue, connection != .connected { nudgeReconnect() }
        }
    }

    let api: HubAPI
    private let kv: KVStore
    private var clockSkew: Double = 0  // serverTime - local now, from hello
    private(set) var cursor: Int?
    private var readCursors: [String: Int]
    private var connectionTask: Task<Void, Never>?
    private var presenceTask: Task<Void, Never>?
    private var presenceDirty = false

    init(api: HubAPI, kv: KVStore = DefaultsKV()) {
        self.api = api
        self.kv = kv
        self.cursor = kv.int(forKey: "hub.cursor")
        self.readCursors = kv.intDict(forKey: "hub.readCursors")
    }

    // MARK: - Connection loop

    func start() {
        guard connectionTask == nil else { return }
        connectionTask = Task { await runConnectionLoop() }
        presenceTask = Task { await runPresenceLoop() }
    }

    /// Tear down the current socket and start over immediately, keeping the
    /// cursor. Safe to call any time; the store replays whatever was missed.
    func nudgeReconnect() {
        connectionTask?.cancel()
        connectionTask = Task { await runConnectionLoop() }
    }

    func stop() {
        connectionTask?.cancel(); connectionTask = nil
        presenceTask?.cancel(); presenceTask = nil
        Task { [api] in try? await api.removePresence() }
    }

    private func runConnectionLoop() async {
        var backoff = 1.0
        while !Task.isCancelled {
            connection = cursor == nil ? .connecting : connection
            do {
                for try await frame in HubSocket.frames(config: api.config, since: cursor) {
                    if case .hello = frame {
                        backoff = 1
                        connection = .connected
                        Task { await self.refreshStatus() }
                    }
                    apply(frame)
                }
                connection = .reconnecting(detail: "connection closed")
            } catch {
                connection = .reconnecting(detail: "\(error)")
            }
            try? await Task.sleep(for: .seconds(backoff))
            backoff = min(backoff * 2, 30)
        }
    }

    private func refreshStatus() async {
        if let s = try? await api.status() { pendingEvents = s.pendingEvents ?? 0 }
    }

    // MARK: - Frame application (the contract's cursor rules live here)

    func apply(_ frame: Frame) {
        switch frame {
        case .hello(let hello):
            hubVersion = hello.version
            clockSkew = hello.serverTime - Date().timeIntervalSince1970
            channels = hello.channels
            if cursor == nil {
                // First-ever launch: mark the snapshot read so the queue never
                // opens with a badge on history lived through at a keyboard.
                setCursor(hello.latestEventId)
                for c in hello.channels { readCursors[c.paneId] = hello.latestEventId }
                persistReadCursors()
            }
            // A resuming client's cursor moves only over applied events —
            // hello must NOT move it; backlog is about to replay the gap.

        case .backlog(_, let events):
            for e in events { integrate(e, advanceCursor: true) }

        case .event(let e):
            integrate(e, advanceCursor: true)

        case .channels(let list, _):
            channels = list

        case .channel(let c):
            if c.archived == true {
                channels.removeAll { $0.paneId == c.paneId }
                if selectedPane == c.paneId { selectedPane = nil }
            } else if let i = channels.firstIndex(where: { $0.paneId == c.paneId }) {
                channels[i] = c
            } else {
                channels.append(c)
            }

        case .activity(let panes, let serverTime):
            clockSkew = serverTime - Date().timeIntervalSince1970
            for (pane, t) in panes {
                if let i = channels.firstIndex(where: { $0.paneId == pane }) {
                    channels[i].lastOutputAt = t
                    channels[i].idleS = 0
                }
            }

        case .historyCleared(let pane):
            threads[pane] = ChannelThread()

        case .desync, .presence, .ping, .pong, .unknown, .error:
            break
        }
    }

    /// The single door for an event, live or replayed. Cursor only ever
    /// advances over events actually applied.
    func integrate(_ event: Event, advanceCursor: Bool) {
        let isNew = (threads[event.paneId]?.events.last?.id).map { event.id > $0 } ?? true
        let appended = threads[event.paneId, default: ChannelThread()].upsert(event)

        if advanceCursor { setCursor(max(cursor ?? 0, event.id)) }

        // Patch the channel summary — but a replayed event must never drag
        // last_event backwards or inflate event_count.
        if let i = channels.firstIndex(where: { $0.paneId == event.paneId }),
           appended, isNew, event.id > (channels[i].lastEvent?.id ?? 0) {
            channels[i].lastEvent = event
            channels[i].eventCount = (channels[i].eventCount ?? 0) + 1
            // status: working = last conversation event was sent/receipt.
            // A notice is not part of the conversation and never changes it.
            if channels[i].status != "dead" && event.kind != "notice" {
                channels[i].status = ["sent", "receipt"].contains(event.kind) ? "working" : "idle"
            }
        }

        // Reading along: on the selected channel of a frontmost app, arrivals
        // are seen as they land.
        if appended, appActive, event.paneId == selectedPane {
            markRead(event.paneId)
        }
    }

    private func setCursor(_ value: Int) {
        cursor = value
        kv.set(value, forKey: "hub.cursor")
    }

    // MARK: - Read state / unread badges

    func readUpTo(_ pane: String) -> Int { readCursors[pane] ?? 0 }

    func markRead(_ pane: String) {
        let latest = max(threads[pane]?.events.last?.id ?? 0,
                         channels.first(where: { $0.paneId == pane })?.lastEvent?.id ?? 0)
        guard latest > (readCursors[pane] ?? 0) else { return }
        readCursors[pane] = latest
        persistReadCursors()
    }

    /// Events worth a badge: things that arrived FOR him — answers, failures,
    /// notices. Not his own keystrokes (sent/receipt) and not channel plumbing.
    static let unreadKinds: Set<String> = ["outcome", "error", "notice"]

    func unreadCount(_ pane: String) -> Int {
        let readUpTo = readCursors[pane] ?? 0
        guard let thread = threads[pane] else {
            // No thread in memory: fall back to "is the last event unseen".
            if let last = channels.first(where: { $0.paneId == pane })?.lastEvent,
               last.id > readUpTo, Self.unreadKinds.contains(last.kind) { return 1 }
            return 0
        }
        return thread.events.filter { $0.id > readUpTo && Self.unreadKinds.contains($0.kind) }.count
    }

    private func persistReadCursors() {
        kv.set(readCursors, forKey: "hub.readCursors")
    }

    // MARK: - History

    func loadHistoryIfNeeded(_ pane: String) async {
        guard threads[pane]?.historyLoaded != true else { return }
        do {
            let history = try await api.history(pane: pane)
            for e in history.events { integrate(e, advanceCursor: false) }
            threads[pane, default: ChannelThread()].historyLoaded = true
        } catch {
            // Leave historyLoaded false; the view can retry on next open.
        }
    }

    // MARK: - Actions

    func send(_ text: String, to pane: String) async throws {
        let r = try await api.send(pane: pane, text: text)
        integrate(r.event, advanceCursor: true)
        markRead(pane)
    }

    func interrupt(_ pane: String, action: String = "escape") async throws {
        let r = try await api.interrupt(pane: pane, action: action)
        integrate(r.event, advanceCursor: true)
    }

    /// Spawn a new agent pane and land on it. The hub's channels frame will
    /// bring the authoritative list; the upsert here is just immediacy.
    func createSession(command: String, label: String?, cwd: String?) async throws {
        let channel = try await api.createChannel(command: command, label: label, cwd: cwd)
        if !channels.contains(where: { $0.paneId == channel.paneId }) {
            channels.insert(channel, at: 0)
        }
        markRead(channel.paneId)
        selectedPane = channel.paneId
    }

    /// Ends the pane; thread and history survive (contract: kill is not
    /// destructive of data).
    func killSession(_ pane: String) async throws {
        let r = try await api.kill(pane: pane)
        integrate(r.event, advanceCursor: true)
        if let i = channels.firstIndex(where: { $0.paneId == pane }) {
            channels[i] = r.channel
        }
    }

    func archiveChannel(_ pane: String) async throws {
        _ = try await api.archive(pane: pane, archived: true)
        channels.removeAll { $0.paneId == pane }
        if selectedPane == pane { selectedPane = nil }
    }

    func clearHistory(_ pane: String) async throws {
        _ = try await api.clearHistory(pane: pane)
        threads[pane] = ChannelThread(historyLoaded: true)
    }

    func expand(_ event: Event) async -> Event {
        guard event.isTruncated else { return event }
        return (try? await api.fullEvent(id: event.id)) ?? event
    }

    // MARK: - Presence (only ever the channel on screen; never covers_all)

    private func runPresenceLoop() async {
        var lastReported: String? = nil
        while !Task.isCancelled {
            let want: String? = appActive ? selectedPane : nil
            if presenceDirty || want != lastReported {
                presenceDirty = false
                if let pane = want {
                    try? await api.reportPresence(panes: [pane])
                } else if lastReported != nil {
                    try? await api.removePresence()
                }
                lastReported = want
            } else if want != nil {
                try? await api.reportPresence(panes: [want!])  // refresh, TTL 90s
            }
            try? await Task.sleep(for: .seconds(30))
        }
    }

    // MARK: - Display helpers

    /// idle_s aged locally between activity frames, using the server clock.
    func liveIdleS(_ channel: Channel) -> Double? {
        guard let lastOutputAt = channel.lastOutputAt else { return channel.idleS }
        let serverNow = Date().timeIntervalSince1970 + clockSkew
        return max(0, serverNow - lastOutputAt)
    }

    func liveness(_ channel: Channel) -> Liveness {
        // @host has no screen to fingerprint: idle_s is null, live is true.
        if channel.paneId == "@host" { return .none }
        return .of(status: channel.status, live: channel.live, idleS: liveIdleS(channel))
    }
}
