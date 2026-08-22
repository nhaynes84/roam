import Testing
import Foundation
@testable import Nexus

@Suite struct ConfigTests {
    @Test func wsURLDerivedFromHTTPBase() {
        let c = HubConfig(baseURL: URL(string: "http://talos:8787")!, token: "t")
        #expect(c.wsURL(since: 412).absoluteString == "ws://talos:8787/ws?since=412")
        #expect(c.wsURL(since: nil).absoluteString == "ws://talos:8787/ws")
    }

    @Test func httpsBecomesWss() {
        let c = HubConfig(baseURL: URL(string: "https://example.com:9000")!, token: "t")
        #expect(c.wsURL(since: 1).absoluteString == "wss://example.com:9000/ws?since=1")
    }

    @Test func envConfigWins() throws {
        let cfg = HubConfig.load(environment: [
            "ROAM_HUB_TOKEN": " secret\n",
            "ROAM_HUB_URL": "http://100.67.237.109:8787",
        ], home: URL(fileURLWithPath: "/nonexistent"))
        #expect(cfg?.token == "secret")
        #expect(cfg?.baseURL.absoluteString == "http://100.67.237.109:8787")
    }

    @Test func missingEverythingIsNil() {
        #expect(HubConfig.load(environment: [:], home: URL(fileURLWithPath: "/nonexistent")) == nil)
    }
}

/// The disconnect/reconnect surface: "fix you disconnect / reconnect status and
/// UI, it is pretty raw right now."
@Suite struct ConnectionStateTests {

    @Test func urlErrorsBecomeWordsAPersonCanActize() {
        #expect(ConnectionReason.describe(URLError(.notConnectedToInternet)) == "no network")
        #expect(ConnectionReason.describe(URLError(.cannotConnectToHost)) == "hub not answering")
        #expect(ConnectionReason.describe(URLError(.timedOut)) == "timed out")
        #expect(ConnectionReason.describe(URLError(.userAuthenticationRequired))
                == "hub rejected the token")
    }

    @Test func anUnknownErrorNeverLeaksARawDump() {
        /// The bug: detail was "\(error)", so the bar rendered
        /// "Error Domain=NSURLErrorDomain Code=-1004 …" truncated to one line.
        struct Weird: Error { let payload = "Domain=NSURLErrorDomain Code=-1004" }
        let described = ConnectionReason.describe(Weird())
        #expect(described == "connection failed")
        #expect(!described.contains("Domain"))
    }

    @Test func countdownReadsAsTimeRemaining() {
        let base = Date(timeIntervalSince1970: 1_000_000)
        #expect(ConnectionReason.countdown(to: base.addingTimeInterval(4), now: base) == "in 4s")
        #expect(ConnectionReason.countdown(to: base.addingTimeInterval(65), now: base) == "in 1m 5s")
    }

    @Test func aPastRetryTimeShowsNoCountdown() {
        let base = Date(timeIntervalSince1970: 1_000_000)
        #expect(ConnectionReason.countdown(to: base.addingTimeInterval(-1), now: base) == nil)
    }

    @Test func oneBlipIsNotAnOutage() {
        /// A sleeping laptop drops the socket on every wake. Shouting about that
        /// trains him to ignore the bar.
        #expect(!ConnectionState.reconnecting(reason: "network dropped", attempt: 1,
                                              retryAt: nil).isStruggling)
        #expect(ConnectionState.reconnecting(reason: "network dropped", attempt: 3,
                                             retryAt: nil).isStruggling)
        #expect(!ConnectionState.connected.isStruggling)
    }

    @Test func ageReadsAtEveryScale() {
        #expect(ConnectionReason.age(12) == "12s")
        #expect(ConnectionReason.age(245) == "4m")
        #expect(ConnectionReason.age(7830) == "2h 10m")
    }
}
