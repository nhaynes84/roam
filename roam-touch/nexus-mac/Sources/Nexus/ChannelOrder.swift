import Foundation

/// The sidebar's running order, kept pure so it is a test rather than a running app.
///
/// ★ Owner: "you keep flopping the order of the channels; they should stay in their
///   place but i should be able to drag them manually, the notification is enough,
///   round robining them to the top of the pane is annoying af."
///
/// So position is OWNED BY HIM, not by activity. The hub re-sends the whole channel
/// list on every change and the client used to render it in arrival order, which is
/// why a channel appeared to jump. Here the remembered order wins; a channel the
/// order has never seen lands at the BOTTOM, never the top, because arriving at the
/// top is the exact behaviour he is objecting to. Unread is carried by the badge.
enum ChannelOrder {
    /// Sort `channels` by `order`, appending unknown panes in arrival order.
    static func apply(_ order: [String], to channels: [Channel]) -> [Channel] {
        var rank: [String: Int] = [:]
        for (i, pane) in order.enumerated() where rank[pane] == nil {
            rank[pane] = i
        }
        // enumerated() keeps arrival order as the tiebreak, so this is stable:
        // equal-rank channels never swap between frames.
        return channels.enumerated()
            .sorted { a, b in
                let ra = rank[a.element.paneId] ?? Int.max
                let rb = rank[b.element.paneId] ?? Int.max
                return ra == rb ? a.offset < b.offset : ra < rb
            }
            .map(\.element)
    }

    /// The order to persist after a render: every visible pane, in shown order,
    /// with remembered-but-absent panes kept so a channel that is merely
    /// scrolled out of the hub's list does not lose its slot.
    static func reconciled(_ order: [String], with channels: [Channel]) -> [String] {
        let visible = apply(order, to: channels).map(\.paneId)
        let seen = Set(visible)
        // keep known-but-not-currently-listed panes, in their old relative places
        var out: [String] = []
        var pending = visible
        for pane in order {
            if seen.contains(pane) {
                if let i = pending.firstIndex(of: pane) {
                    out.append(contentsOf: pending[..<i])
                    out.append(pane)
                    pending.removeSubrange(...i)
                }
            } else {
                out.append(pane)
            }
        }
        out.append(contentsOf: pending)
        var deduped: [String] = []
        var used = Set<String>()
        for pane in out where !used.contains(pane) {
            used.insert(pane)
            deduped.append(pane)
        }
        return deduped
    }

    /// Apply a drag. `offsets`/`destination` are SwiftUI's onMove indices, which
    /// address the VISIBLE list, so the move is computed there and then folded
    /// back into the full remembered order.
    static func move(_ order: [String], channels: [Channel],
                     from offsets: IndexSet, to destination: Int) -> [String] {
        var visible = apply(order, to: channels).map(\.paneId)
        let moving = offsets.sorted().compactMap { $0 < visible.count ? visible[$0] : nil }
        guard !moving.isEmpty else { return order }
        // insertion point in terms of the element it lands before
        let anchor: String? = destination < visible.count ? visible[destination] : nil
        visible.removeAll { moving.contains($0) }
        let at = anchor.flatMap { visible.firstIndex(of: $0) } ?? visible.count
        visible.insert(contentsOf: moving, at: at)
        return reconciled(visible, with: channels)
    }

    /// Step the selection through the visible list. Returns nil when there is
    /// nowhere to go, so the caller can leave selection alone rather than wrap.
    static func neighbour(of pane: String?, in channels: [Channel],
                          order: [String], delta: Int) -> String? {
        let visible = apply(order, to: channels).map(\.paneId)
        guard !visible.isEmpty else { return nil }
        guard let pane, let i = visible.firstIndex(of: pane) else {
            return delta > 0 ? visible.first : visible.last
        }
        let next = i + delta
        guard next >= 0, next < visible.count else { return nil }
        return visible[next]
    }
}
