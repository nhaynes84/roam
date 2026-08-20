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
