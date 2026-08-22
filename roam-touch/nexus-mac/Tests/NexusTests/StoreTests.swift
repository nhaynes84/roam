import Testing
import Foundation
@testable import Nexus

@MainActor
private func makeStore() -> HubStore {
    let config = HubConfig(baseURL: URL(string: "http://test:1")!, token: "t")
    return HubStore(api: HubAPI(config: config), kv: MemoryKV())
}

private func event(_ id: Int, pane: String = "%0", kind: String = "outcome",
                   body: String = "x", echoOf: Int? = nil) -> Event {
    Event(id: id, paneId: pane, kind: kind, body: body, summary: body,
          bodyChars: body.count, bodyTruncated: false, coverage: nil,
          meta: echoOf.map { EventMeta(echoOf: $0) }, ts: 0, archived: false)
}

private func channel(_ pane: String, status: String = "idle", live: Bool = true,
                     lastEvent: Event? = nil, eventCount: Int = 0) -> Channel {
    Channel(paneId: pane, label: pane, session: "main", window: 0, index: 0,
            command: "claude", live: live, status: status, archived: false,
            firstSeen: 0, lastSeen: 0, lastOutputAt: nil, idleS: nil,
            lastInputSource: nil, lastInputAt: nil,
            eventCount: eventCount, lastEvent: lastEvent)
}

private func hello(latest: Int, channels: [Channel] = []) -> Frame {
    .hello(Hello(protocolVersion: 1, version: "1.4.0",
                 serverTime: Date().timeIntervalSince1970,
                 latestEventId: latest, channels: channels))
}

@Suite @MainActor struct CursorRules {
    @Test func firstLaunchMarksSnapshotRead() {
        let s = makeStore()
        s.apply(hello(latest: 400, channels: [channel("%0", lastEvent: event(400))]))
        #expect(s.cursor == 400)
        #expect(s.unreadCount("%0") == 0)  // history lived through at a keyboard
    }

    @Test func helloNeverMovesAnEstablishedCursor() {
        let s = makeStore()
        s.apply(hello(latest: 400))
        // Reconnect: hello says 500, but backlog is about to replay 401–500.
        // A cursor moved by hello would skip all of it if the socket died here.
        s.apply(hello(latest: 500))
        #expect(s.cursor == 400)
    }

    @Test func cursorAdvancesOnlyOverAppliedEvents() {
        let s = makeStore()
        s.apply(hello(latest: 100))
        s.apply(.backlog(since: 100, events: [event(101), event(102)]))
        #expect(s.cursor == 102)
        s.apply(.event(event(103)))
        #expect(s.cursor == 103)
    }

    @Test func replayedEventNeitherRegressesLastEventNorInflatesCount() {
        let s = makeStore()
        let e5 = event(5)
        s.apply(hello(latest: 5, channels: [channel("%0", lastEvent: e5, eventCount: 5)]))
        s.apply(.event(e5))  // catch-up re-delivery of something the snapshot counted
        #expect(s.channels[0].eventCount == 5)
        #expect(s.channels[0].lastEvent?.id == 5)
        s.apply(.event(event(3)))  // stale replay, out of order
        #expect(s.channels[0].lastEvent?.id == 5)
        #expect(s.channels[0].eventCount == 5)
        s.apply(.event(event(6)))  // genuinely new
        #expect(s.channels[0].lastEvent?.id == 6)
        #expect(s.channels[0].eventCount == 6)
    }

    @Test func duplicateEventAppliesOnce() {
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0")]))
        s.apply(.event(event(1)))
        s.apply(.event(event(1)))
        #expect(s.threads["%0"]?.events.count == 1)
        #expect(s.channels[0].eventCount == 1)
    }
}

@Suite @MainActor struct EchoCollapse {
    @Test func echoReceiptCollapsesIntoItsSent() {
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0")]))
        s.apply(.event(event(340, kind: "sent", body: "Not done yet.")))
        s.apply(.event(event(341, kind: "receipt", body: "Not done yet.", echoOf: 340)))
        let t = s.threads["%0"]!
        #expect(t.events.count == 1)             // one thing he said, one entry
        #expect(t.delivered.contains(340))        // moved to delivered state
        #expect(s.cursor == 341)                  // but the cursor still advanced
    }

    @Test func echoWithoutItsSentRendersAsAMessage() {
        // Window starts after the sent: shown twice is a nuisance, zero times a lie.
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0")]))
        s.apply(.event(event(341, kind: "receipt", body: "Not done yet.", echoOf: 340)))
        #expect(s.threads["%0"]?.events.count == 1)
    }

    @Test func keyboardReceiptIsNeverSuppressed() {
        // No echo_of = he typed it in tmux; this receipt is the only record.
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0")]))
        s.apply(.event(event(10, kind: "receipt", body: "typed at the desk")))
        #expect(s.threads["%0"]?.events.count == 1)
    }
}

@Suite @MainActor struct StatusAndUnread {
    @Test func sentAndReceiptMakeWorkingOutcomeMakesIdle() {
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0", status: "idle")]))
        s.apply(.event(event(1, kind: "sent")))
        #expect(s.channels[0].status == "working")
        s.apply(.event(event(2, kind: "outcome")))
        #expect(s.channels[0].status == "idle")
    }

    @Test func noticeNeverChangesStatus() {
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0", status: "idle")]))
        s.apply(.event(event(1, kind: "receipt")))
        #expect(s.channels[0].status == "working")
        s.apply(.event(event(2, kind: "notice")))  // "I'm still going" is not an answer
        #expect(s.channels[0].status == "working")
    }

    @Test func unreadCountsAnswersNotKeystrokes() {
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0")]))
        s.apply(.event(event(1, kind: "sent")))
        s.apply(.event(event(2, kind: "receipt")))
        s.apply(.event(event(3, kind: "outcome")))
        s.apply(.event(event(4, kind: "notice")))
        s.apply(.event(event(5, kind: "error")))
        #expect(s.unreadCount("%0") == 3)  // outcome + notice + error
        s.markRead("%0")
        #expect(s.unreadCount("%0") == 0)
    }

    @Test func watchingTheSelectedChannelReadsAlong() {
        let s = makeStore()
        s.apply(hello(latest: 0, channels: [channel("%0")]))
        s.appActive = true
        s.selectedPane = "%0"
        s.apply(.event(event(1, kind: "outcome")))
        #expect(s.unreadCount("%0") == 0)
        s.appActive = false  // backgrounded: arrivals accumulate
        s.apply(.event(event(2, kind: "outcome")))
        #expect(s.unreadCount("%0") == 1)
    }
}

@Suite @MainActor struct ActivityFrames {
    @Test func activityUpdatesLastOutputAt() {
        let s = makeStore()
        var c = channel("%0", status: "working")
        c.lastOutputAt = 100
        s.apply(hello(latest: 0, channels: [c]))
        let now = Date().timeIntervalSince1970
        s.apply(.activity(panes: ["%0": now], serverTime: now))
        #expect(s.channels[0].lastOutputAt == now)
        #expect(s.liveIdleS(s.channels[0])! < 1.0)
    }
}

/// Drafts: "so when you kill my screen on reboot or anything else does, i don't
/// lose partly typed messages."
@Suite struct DraftTests {
    @MainActor private func store(_ kv: KVStore) -> HubStore {
        HubStore(api: HubAPI(config: HubConfig(baseURL: URL(string: "http://x")!, token: "t")),
                 kv: kv)
    }

    @MainActor @Test func aDraftSurvivesANewStore() {
        let kv = MemoryKV()
        store(kv).setDraft("half a thought", for: "%1")
        // same persistence, brand new process
        #expect(store(kv).draft(for: "%1") == "half a thought")
    }

    @MainActor @Test func draftsAreKeptPerChannel() {
        let kv = MemoryKV()
        let s = store(kv)
        s.setDraft("for one", for: "%1")
        s.setDraft("for two", for: "%2")
        #expect(s.draft(for: "%1") == "for one")
        #expect(s.draft(for: "%2") == "for two")
        #expect(s.draft(for: "%3") == "")
    }

    @MainActor @Test func clearingRemovesItFromStorage() {
        let kv = MemoryKV()
        let s = store(kv)
        s.setDraft("typed", for: "%1")
        s.clearDraft(for: "%1")
        #expect(store(kv).draft(for: "%1") == "")
        #expect(kv.stringDict(forKey: "hub.drafts")["%1"] == nil, "no empty leftovers")
    }

    @MainActor @Test func emptyingTheFieldDoesNotLeaveAGhostEntry() {
        let kv = MemoryKV()
        let s = store(kv)
        s.setDraft("abc", for: "%1")
        s.setDraft("", for: "%1")
        #expect(kv.stringDict(forKey: "hub.drafts").isEmpty)
    }
}

/// Live selector state: "we should be able to pipe that experience in and out."
@Suite struct PromptFrameTests {
    @MainActor private func store() -> HubStore {
        HubStore(api: HubAPI(config: HubConfig(baseURL: URL(string: "http://x")!, token: "t")),
                 kv: MemoryKV())
    }

    private func payload(_ q: String) -> PromptPayload {
        PromptPayload(question: q, options: [
            PromptOption(n: 1, text: "Yes", selected: true),
            PromptOption(n: 2, text: "No", selected: false),
        ])
    }

    @MainActor @Test func aPromptFrameOpensTheQuestion() {
        let s = store()
        s.apply(.prompt(pane: "%1", prompt: payload("trust this folder?")))
        #expect(s.openPrompts["%1"]?.options.count == 2)
    }

    @MainActor @Test func aNilPromptClosesIt() {
        let s = store()
        s.apply(.prompt(pane: "%1", prompt: payload("trust this folder?")))
        s.apply(.prompt(pane: "%1", prompt: nil))
        #expect(s.openPrompts["%1"] == nil, "an answered question stops being answerable")
    }

    @MainActor @Test func promptsAreTrackedPerPane() {
        let s = store()
        s.apply(.prompt(pane: "%1", prompt: payload("one?")))
        s.apply(.prompt(pane: "%2", prompt: payload("two?")))
        s.apply(.prompt(pane: "%1", prompt: nil))
        #expect(s.openPrompts["%1"] == nil)
        #expect(s.openPrompts["%2"] != nil, "closing one must not close the other")
    }
}
