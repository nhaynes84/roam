import Testing
import Foundation
@testable import Nexus

// JSON verbatim from hub/API.md — if these fail after a contract change, the
// contract moved, not the client.

@Suite struct DecodingTests {
    @Test func eventFromContract() throws {
        let json = """
        {"id": 412, "pane_id": "%0", "kind": "outcome",
         "body": "Tailscale beats the BLE permission wall.",
         "summary": "Tailscale beats the BLE permission wall.",
         "body_chars": 319, "body_truncated": false,
         "coverage": {"known": true, "covered": false, "by": [], "last_input": "app"},
         "meta": {"source": "claude-hook", "session_id": "44c6d5f1"},
         "ts": 1786511500.066308, "archived": false}
        """
        let e = try JSONDecoder.hub.decode(Event.self, from: Data(json.utf8))
        #expect(e.id == 412)
        #expect(e.paneId == "%0")
        #expect(e.kind == "outcome")
        #expect(e.coverage?.covered == false)
        #expect(e.coverage?.lastInput == "app")
        #expect(e.meta?.source == "claude-hook")
        #expect(e.isTruncated == false)
    }

    @Test func echoReceipt() throws {
        let json = """
        {"id": 341, "pane_id": "%3", "kind": "receipt", "body": "Not done yet.",
         "summary": "Not done yet.",
         "meta": {"source": "claude-hook", "echo_of": 340}, "ts": 1786511500.0}
        """
        let e = try JSONDecoder.hub.decode(Event.self, from: Data(json.utf8))
        #expect(e.echoOf == 340)
    }

    @Test func channelFromContract() throws {
        let json = """
        {"pane_id": "%0", "label": "◑ Roam Touch rebuild discussion",
         "session": "main", "window": 1, "index": 1, "command": "claude.exe",
         "live": true, "status": "idle", "archived": false,
         "first_seen": 1786511486.69, "last_seen": 1786511488.84,
         "last_output_at": 1786511500.31, "idle_s": 2.4,
         "last_input_source": "app", "last_input_at": 1786511490.0,
         "event_count": 7, "last_event": null}
        """
        let c = try JSONDecoder.hub.decode(Channel.self, from: Data(json.utf8))
        #expect(c.paneId == "%0")
        #expect(c.live)
        #expect(c.idleS == 2.4)
        #expect(c.lastEvent == nil)
    }

    @Test func atHostChannelWithNullIdle() throws {
        let json = """
        {"pane_id": "@host", "label": "@host", "session": null, "window": null,
         "index": null, "command": null, "live": true, "status": "idle",
         "idle_s": null, "last_output_at": null, "event_count": 3, "last_event": null}
        """
        let c = try JSONDecoder.hub.decode(Channel.self, from: Data(json.utf8))
        #expect(c.paneId == "@host")
        #expect(c.idleS == nil)
    }

    @Test func helloFrame() throws {
        let json = """
        {"type": "hello", "protocol": 1, "version": "1.4.0",
         "server_time": 1786511500.1, "latest_event_id": 412,
         "channels": [], "presence": {"present": false}}
        """
        guard case .hello(let h) = try FrameDecoder.decode(Data(json.utf8)) else {
            Issue.record("not a hello"); return
        }
        #expect(h.protocolVersion == 1)
        #expect(h.latestEventId == 412)
    }

    @Test func activityFrameKeepsPaneKeys() throws {
        // convertFromSnakeCase must not mangle "%0"-style dictionary keys.
        let json = """
        {"type": "activity", "panes": {"%0": 1786511500.3, "%12": 1786511501.0},
         "server_time": 1786511500.4}
        """
        guard case .activity(let panes, _) = try FrameDecoder.decode(Data(json.utf8)) else {
            Issue.record("not activity"); return
        }
        #expect(panes["%0"] == 1786511500.3)
        #expect(panes["%12"] == 1786511501.0)
    }

    @Test func desyncAndUnknownFrames() throws {
        guard case .desync(let latest) = try FrameDecoder.decode(
            Data(#"{"type": "desync", "latest_event_id": 999}"#.utf8)) else {
            Issue.record("not desync"); return
        }
        #expect(latest == 999)
        // Contract: ignore unknown types, never drop the connection over one.
        guard case .unknown(let t) = try FrameDecoder.decode(
            Data(#"{"type": "confetti", "amount": 5}"#.utf8)) else {
            Issue.record("unknown type must decode as .unknown"); return
        }
        #expect(t == "confetti")
    }

    @Test func healthProtocolField() throws {
        let json = """
        {"ok": true, "service": "roam-hub", "version": "1.4.0", "protocol": 1,
         "uptime_s": 2.15,
         "build": {"version": "1.4.0", "protocol": 1, "commit": "99bb9f2", "schema": 6}}
        """
        let h = try JSONDecoder.hub.decode(HealthResponse.self, from: Data(json.utf8))
        #expect(h.protocolVersion == 1)
        #expect(h.build?.commit == "99bb9f2")
    }
}
