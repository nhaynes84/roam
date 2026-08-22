import SwiftUI

struct ChannelList: View {
    @Bindable var store: HubStore
    @Binding var destination: MainDestination?
    /// Re-render tick so liveness ages between activity frames.
    @State private var now = Date()
    @State private var showNewSession = false
    @State private var paneToKill: String?
    @State private var actionFailure: String?
    private let tick = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    private var selectedChannel: Binding<String?> {
        Binding(
            get: {
                if case .channel(let p) = destination { return p }
                return nil
            },
            set: { destination = $0.map { .channel($0) } }
        )
    }

    var body: some View {
        // ForEach (not List's data initialiser) because onMove needs it — and the
        // order rendered is HIS, not the hub's arrival order.
        List(selection: selectedChannel) {
            ForEach(store.orderedChannels) { channel in
                ChannelRow(channel: channel,
                           liveness: store.liveness(channel),
                           unread: store.unreadCount(channel.paneId),
                           onDismiss: channel.live ? nil : {
                               run { try await store.archiveChannel(channel.paneId) }
                           })
                    .tag(channel.paneId)
                    .contextMenu { menu(for: channel) }
            }
            .onMove { store.moveChannels(from: $0, to: $1) }
        }
        .listStyle(.sidebar)
        // ★ Tint OVER the window material, not instead of it: the rail keeps macOS
        //   vibrancy but stops being the same grey wash as the thread beside it.
        .scrollContentBackground(.hidden)
        .background { Theme.railTint.ignoresSafeArea() }
        .onChange(of: store.channels.map(\.paneId), initial: true) { _, _ in
            // A pane the order has never seen gets a slot at the bottom.
            store.adoptNewChannels()
        }
        .navigationTitle("Nexus")
        .onReceive(tick) { now = $0 }
        .toolbar {
            Button { showNewSession = true } label: {
                Image(systemName: "plus")
            }
            .help("New session — spawn an agent pane on talos")
        }
        .sheet(isPresented: $showNewSession) { NewSessionSheet(store: store) }
        .confirmationDialog(
            "Kill this session?",
            isPresented: Binding(get: { paneToKill != nil },
                                 set: { if !$0 { paneToKill = nil } })
        ) {
            Button("Kill \(paneToKill ?? "")", role: .destructive) {
                if let pane = paneToKill { run { try await store.killSession(pane) } }
            }
        } message: {
            Text("Ends the pane and whatever runs in it. The thread and its history stay.")
        }
        .alert("Action failed", isPresented: Binding(get: { actionFailure != nil },
                                                     set: { if !$0 { actionFailure = nil } })) {
            Button("OK") { actionFailure = nil }
        } message: {
            Text(actionFailure ?? "")
        }
    }

    @ViewBuilder
    private func menu(for channel: Channel) -> some View {
        if channel.live && channel.paneId != "@host" {
            Button("Kill session…", role: .destructive) { paneToKill = channel.paneId }
        }
        if !channel.live {
            Button("Archive") { run { try await store.archiveChannel(channel.paneId) } }
        }
        Button("Clear history") { run { try await store.clearHistory(channel.paneId) } }
        Button("Mark read") { store.markRead(channel.paneId) }
    }

    private func run(_ body: @escaping () async throws -> Void) {
        Task {
            do { try await body() }
            catch { actionFailure = "\(error)" }
        }
    }
}

struct ChannelRow: View {
    var channel: Channel
    var liveness: Liveness
    var unread: Int
    /// Present only on dead channels: archive it — the thread is over.
    var onDismiss: (() -> Void)?

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            // a ring rather than a dot: reads as a state light, and the halo keeps it
            // visible against both the vibrant rail and a selected row
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
                .overlay(Circle().stroke(statusColor.opacity(0.30), lineWidth: 3))
                .padding(.top, 6)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(channel.label)
                        .font(.system(size: 15, weight: unread > 0 ? .bold : .medium))
                        .foregroundStyle(unread > 0 ? Color.primary : Color.primary.opacity(0.85))
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    if let ts = channel.lastEvent?.ts {
                        Text(Date(timeIntervalSince1970: ts), style: .time)
                            .font(.system(size: 14))
                            .foregroundStyle(.quaternary)
                    }
                }
                HStack(spacing: 6) {
                    if !liveness.text.isEmpty {
                        Text(liveness.text)
                            .font(.system(size: 14, weight: .medium))
                            .foregroundStyle(livenessColor)
                    }
                    if let last = channel.lastEvent, liveness != .dead {
                        Text(last.summary)
                            .font(.system(size: 14))
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 4)
                    if unread > 0 {
                        // the one saturated thing in the column, so the eye lands on it
                        Text("\(unread)")
                            .font(.system(size: 13, weight: .bold))
                            .monospacedDigit()
                            .padding(.horizontal, 7).padding(.vertical, 2)
                            .background(Capsule().fill(Color.accentColor))
                            .foregroundStyle(.white)
                    }
                    if let onDismiss {
                        Button(action: onDismiss) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        .help("Dismiss — archives this dead channel; history stays readable")
                    }
                }
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 2)
        .contentShape(.rect)
    }

    private var livenessColor: Color {
        switch liveness {
        case .dead: return .red
        case .working: return .cyan
        case .quiet: return .orange
        case .idle, .none: return .secondary
        }
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
