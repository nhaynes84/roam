import Foundation
import Testing
@testable import Nexus

/// Position belongs to the owner, not to activity:
/// "they should stay in their place but i should be able to drag them manually …
///  round robining them to the top of the pane is annoying af."
@Suite struct ChannelOrderTests {

    private func ch(_ pane: String) -> Channel {
        Channel(paneId: pane, label: pane, session: "agents",
                live: true, status: "idle", archived: false)
    }

    @Test func rememberedOrderWinsOverArrivalOrder() {
        let order = ["%1", "%2", "%3"]
        // the hub re-sends the list with %3 first — the classic "it jumped" frame
        let arrived = [ch("%3"), ch("%1"), ch("%2")]
        #expect(ChannelOrder.apply(order, to: arrived).map(\.paneId) == ["%1", "%2", "%3"])
    }

    @Test func aChannelNeverMovesBecauseSomethingHappenedInIt() {
        let order = ["%1", "%2", "%3"]
        let quiet = ChannelOrder.apply(order, to: [ch("%1"), ch("%2"), ch("%3")])
        // same panes, hub now lists the busy one first
        let busy = ChannelOrder.apply(order, to: [ch("%2"), ch("%3"), ch("%1")])
        #expect(quiet.map(\.paneId) == busy.map(\.paneId))
    }

    @Test func unknownChannelsLandAtTheBottomNeverTheTop() {
        let ordered = ChannelOrder.apply(["%1"], to: [ch("%9"), ch("%1")])
        #expect(ordered.map(\.paneId) == ["%1", "%9"], "a new pane must not jump the queue")
    }

    @Test func unknownChannelsKeepArrivalOrderAmongThemselves() {
        let ordered = ChannelOrder.apply([], to: [ch("%5"), ch("%3"), ch("%4")])
        #expect(ordered.map(\.paneId) == ["%5", "%3", "%4"], "stable, so nothing swaps")
    }

    @Test func draggingDownReordersAndSticks() {
        let channels = [ch("%1"), ch("%2"), ch("%3")]
        let moved = ChannelOrder.move(["%1", "%2", "%3"], channels: channels,
                                      from: IndexSet(integer: 0), to: 3)
        #expect(moved == ["%2", "%3", "%1"])
        #expect(ChannelOrder.apply(moved, to: channels).map(\.paneId) == ["%2", "%3", "%1"])
    }

    @Test func draggingUpReorders() {
        let channels = [ch("%1"), ch("%2"), ch("%3")]
        let moved = ChannelOrder.move(["%1", "%2", "%3"], channels: channels,
                                      from: IndexSet(integer: 2), to: 0)
        #expect(moved == ["%3", "%1", "%2"])
    }

    @Test func aRememberedPaneThatIsNotListedKeepsItsSlot() {
        // %2 is off the list this frame; it must not be forgotten, so that when it
        // comes back it returns to the middle rather than to the bottom.
        let out = ChannelOrder.reconciled(["%1", "%2", "%3"], with: [ch("%1"), ch("%3")])
        #expect(out == ["%1", "%2", "%3"])
    }

    @Test func reconcileAdoptsNewPanesAtTheEnd() {
        let out = ChannelOrder.reconciled(["%1"], with: [ch("%1"), ch("%7")])
        #expect(out == ["%1", "%7"])
    }

    @Test func reconcileNeverDuplicates() {
        let out = ChannelOrder.reconciled(["%1", "%1", "%2"], with: [ch("%1"), ch("%2")])
        #expect(out == ["%1", "%2"])
    }

    // MARK: ⌘⇧↑ / ⌘⇧↓

    @Test func neighbourStepsThroughTheVisibleOrder() {
        let channels = [ch("%3"), ch("%1"), ch("%2")]   // hub order, deliberately not his
        let order = ["%1", "%2", "%3"]
        #expect(ChannelOrder.neighbour(of: "%1", in: channels, order: order, delta: 1) == "%2")
        #expect(ChannelOrder.neighbour(of: "%2", in: channels, order: order, delta: -1) == "%1")
    }

    @Test func neighbourDoesNotWrapAtEitherEnd() {
        let channels = [ch("%1"), ch("%2")]
        let order = ["%1", "%2"]
        #expect(ChannelOrder.neighbour(of: "%1", in: channels, order: order, delta: -1) == nil)
        #expect(ChannelOrder.neighbour(of: "%2", in: channels, order: order, delta: 1) == nil)
    }

    @Test func neighbourWithNoSelectionEntersFromTheRightEnd() {
        let channels = [ch("%1"), ch("%2")]
        let order = ["%1", "%2"]
        #expect(ChannelOrder.neighbour(of: nil, in: channels, order: order, delta: 1) == "%1")
        #expect(ChannelOrder.neighbour(of: nil, in: channels, order: order, delta: -1) == "%2")
        #expect(ChannelOrder.neighbour(of: "gone", in: channels, order: order, delta: 1) == "%1")
    }

    @Test func neighbourOnAnEmptyListIsNil() {
        #expect(ChannelOrder.neighbour(of: nil, in: [], order: [], delta: 1) == nil)
    }
}
