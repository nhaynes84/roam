import SwiftUI

/// A worn client must degrade to a visible bar, never to nothing — the desk client
/// keeps the same rule.
///
/// ★ The three things worth knowing when the link drops: **why**, **when it retries**,
/// and **how to retry now**. The old bar showed a raw `NSURLErrorDomain` dump and no
/// way to act on it, which read as broken even while the retry logic was working.
struct StatusBar: View {
    var store: HubStore
    /// Drives the countdown; only ticks while something is actually counting down.
    @State private var now = Date()
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 8) {
            switch store.connection {
            case .connected:
                Circle().fill(.green).frame(width: 8, height: 8)
                Text("hub \(store.hubVersion ?? "")")
                    .font(.system(size: 14)).foregroundStyle(.secondary)

            case .connecting:
                ProgressView().controlSize(.small)
                Text("connecting…").font(.system(size: 14)).foregroundStyle(.secondary)

            case .reconnecting(let reason, let attempt, let retryAt):
                ProgressView().controlSize(.small)
                Text(reason)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(tint)
                    .lineLimit(1)
                if let retryAt, let countdown = ConnectionReason.countdown(to: retryAt, now: now) {
                    Text("· retrying \(countdown)")
                        .font(.system(size: 14)).foregroundStyle(.secondary)
                        .monospacedDigit()
                }
                // ⚠️ Only once it has actually failed a few times. A sleeping laptop
                //    produces one blip on every wake, and shouting about that trains
                //    him to ignore the bar.
                if attempt >= 3 {
                    Text("· \(attempt) tries")
                        .font(.system(size: 14)).foregroundStyle(.secondary)
                }
                if let down = downFor {
                    Text("· down \(down)")
                        .font(.system(size: 14)).foregroundStyle(.secondary)
                }
                Button("Retry now") { store.nudgeReconnect() }
                    .buttonStyle(.link)
                    .font(.system(size: 14))
            }

            if store.pendingEvents > 0 {
                // Events written while the hub process was down, not yet adopted.
                Label("\(store.pendingEvents) pending on the hub", systemImage: "tray.full")
                    .font(.system(size: 14)).foregroundStyle(.orange)
            }
            Spacer()
        }
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background {
            // A tinted bar, not just red text: on a dark ground a coloured word is
            // easy to miss, a coloured strip is not.
            ZStack {
                Rectangle().fill(.bar)
                if !store.connection.isConnected {
                    Rectangle().fill(tint.opacity(store.connection.isStruggling ? 0.18 : 0.10))
                }
            }
            .ignoresSafeArea()
        }
        .overlay(alignment: .top) {
            if !store.connection.isConnected {
                Rectangle().fill(tint.opacity(0.55)).frame(height: 1)
            }
        }
        .onReceive(tick) { t in
            // Don't re-render once a second forever — only while counting down.
            if !store.connection.isConnected { now = t }
        }
        .animation(.easeOut(duration: 0.2), value: store.connection)
    }

    /// Amber while it is just retrying, red once it has been failing for a while.
    /// A brief drop on wake is normal and should not look like an outage.
    private var tint: Color {
        store.connection.isStruggling ? .red : .orange
    }

    private var downFor: String? {
        guard let since = store.lastConnected else { return nil }
        let seconds = Int(now.timeIntervalSince(since))
        guard seconds >= 30 else { return nil }
        return ConnectionReason.age(seconds)
    }
}
