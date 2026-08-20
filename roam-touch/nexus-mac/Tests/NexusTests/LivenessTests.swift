import Testing
@testable import Nexus

// The 0,1,0,1 lesson: idle_s on a working pane is sampled mid-repaint and can
// only read 0–2 floored — so WORKING shows no number, ever.

@Suite struct LivenessTests {
    @Test func workingShowsNoNumber() {
        #expect(Liveness.of(status: "working", live: true, idleS: 0.3) == .working)
        #expect(Liveness.of(status: "working", live: true, idleS: 2.1) == .working)
        #expect(Liveness.of(status: "working", live: true, idleS: nil) == .working)
        #expect(Liveness.working.text == "working…")
    }

    @Test func quietIsTheKillDecision() {
        #expect(Liveness.of(status: "working", live: true, idleS: 10.0) == .quiet(10))
        #expect(Liveness.of(status: "working", live: true, idleS: 245) == .quiet(245))
        #expect(Liveness.quiet(245).text == "quiet 4m")
    }

    @Test func idleShowsANumberOnlyPastFiveSeconds() {
        #expect(Liveness.of(status: "idle", live: true, idleS: 2.0) == .none)
        #expect(Liveness.of(status: "idle", live: true, idleS: 5.0) == .idle(5))
        #expect(Liveness.of(status: "idle", live: true, idleS: 3700) == .idle(3700))
        #expect(Liveness.idle(3700).text == "idle 1h 1m")
    }

    @Test func deadIsDeadRegardless() {
        #expect(Liveness.of(status: "dead", live: false, idleS: nil) == .dead)
        #expect(Liveness.of(status: "idle", live: false, idleS: 3.0) == .dead)
    }

    @Test func nullIdleOnAnIdlePaneSaysNothing() {
        // @host: no screen to fingerprint; never a fake zero.
        #expect(Liveness.of(status: "idle", live: true, idleS: nil) == .none)
    }
}
