import SwiftUI

struct ChannelList: View {
    @Bindable var store: HubStore
    /// Re-render tick so liveness ages between activity frames.
    @State private var now = Date()
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    var body: some View {
        List(store.channels, selection: $store.selectedPane) { channel in
            ChannelRow(channel: channel,
                       liveness: store.liveness(channel),
                       unread: store.unreadCount(channel.paneId))
                .tag(channel.paneId)
        }
        .listStyle(.sidebar)
        .navigationTitle("Nexus")
        .onReceive(tick) { now = $0 }
    }
}

struct ChannelRow: View {
    var channel: Channel
    var liveness: Liveness
    var unread: Int

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(statusColor)
                .frame(width: 9, height: 9)
            VStack(alignment: .leading, spacing: 2) {
                Text(channel.label)
                    .font(.system(size: 14, weight: unread > 0 ? .semibold : .regular))
                    .lineLimit(1)
                HStack(spacing: 6) {
                    if !liveness.text.isEmpty {
                        Text(liveness.text)
                            .font(.system(size: 14))
                            .foregroundStyle(liveness == .dead ? .red : .secondary)
                    }
                    if let last = channel.lastEvent, liveness != .dead {
                        Text(last.summary)
                            .font(.system(size: 14))
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                    }
                }
            }
            Spacer(minLength: 4)
            if unread > 0 {
                Text("\(unread)")
                    .font(.system(size: 14, weight: .semibold))
                    .padding(.horizontal, 7).padding(.vertical, 1)
                    .background(Capsule().fill(.tint))
                    .foregroundStyle(.white)
            }
        }
        .padding(.vertical, 2)
    }

    private var statusColor: Color {
        switch liveness {
        case .dead: return .red.opacity(0.7)
        case .working: return .cyan
        case .quiet: return .orange
        case .idle, .none: return channel.live ? .green.opacity(0.6) : .gray
        }
    }
}
