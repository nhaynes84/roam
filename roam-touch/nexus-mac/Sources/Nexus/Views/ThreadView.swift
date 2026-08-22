import SwiftUI

struct ThreadView: View {
    @Bindable var store: HubStore
    var pane: String

    /// Unread boundary, snapshotted when the channel opens — before markRead.
    @State private var newMarkerId: Int?
    @State private var newCount = 0
    /// Initial positioning done; only then do new arrivals auto-follow.
    @State private var positioned = false
    @State private var showCapture = false

    private var channel: Channel? { store.channels.first { $0.paneId == pane } }
    private var thread: ChannelThread { store.threads[pane] ?? ChannelThread() }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        ForEach(thread.events) { event in
                            if event.id == newMarkerId {
                                NewMarker(count: newCount).id("new-marker")
                            }
                            EventRow(store: store, event: event,
                                     delivered: thread.delivered.contains(event.id))
                                .id(event.id)
                        }
                        // ★ Owner: "i'd like to see the in message 'Working…'".
                        //   The status bar and the subtitle already carry it, but the
                        //   thread is where he is actually looking while he waits.
                        //   Sits after the last event, where the reply will appear.
                        if let channel, store.liveness(channel).isActive {
                            WorkingRow(text: store.liveness(channel).text)
                                .id("working")
                        }
                    }
                    .padding(12)
                }
                .task(id: pane) { await openChannel(proxy) }
                .onChange(of: channel.map { store.liveness($0).isActive } ?? false) { _, active in
                    if positioned, active {
                        withAnimation { proxy.scrollTo("working", anchor: .bottom) }
                    }
                }
                .onChange(of: thread.events.last?.id) { _, last in
                    // Follow new arrivals only once the opening scroll landed,
                    // so history inserts don't yank the view around.
                    if positioned, let last {
                        withAnimation { proxy.scrollTo(last, anchor: .bottom) }
                    }
                }
                .toolbar {
                    if newCount > 0 {
                        Button {
                            withAnimation { proxy.scrollTo("new-marker", anchor: .center) }
                        } label: {
                            Label("\(newCount) new", systemImage: "arrow.down.to.line")
                                .font(.system(size: 14))
                        }
                        .help("Jump to the first unread message")
                    }
                    if channel?.live == true && pane != "@host" {
                        Button { showCapture = true } label: {
                            Image(systemName: "terminal")
                        }
                        .help("Show the pane's screen")
                    }
                }
                .sheet(isPresented: $showCapture) { CaptureSheet(store: store, pane: pane) }
            }
            Divider()
            Composer(store: store, pane: pane, sendable: channel?.live == true && pane != "@host")
        }
        .navigationTitle(channel?.label ?? pane)
        .navigationSubtitle(subtitle)
    }

    /// Snapshot what is unread, THEN mark read, THEN land the scroll on the
    /// divider (or the bottom when nothing is new). Order matters: marking
    /// read first would erase the very thing being shown.
    private func openChannel(_ proxy: ScrollViewProxy) async {
        let readUpTo = store.readUpTo(pane)
        await store.loadHistoryIfNeeded(pane)
        let events = store.threads[pane]?.events ?? []
        let fresh = events.filter { $0.id > readUpTo }
        newMarkerId = fresh.first?.id
        newCount = fresh.count
        store.markRead(pane)

        // Let the lazy list lay out before asking it to scroll — a scrollTo
        // issued during load is silently dropped, which left threads at the top.
        try? await Task.sleep(for: .milliseconds(80))
        if newMarkerId != nil {
            proxy.scrollTo("new-marker", anchor: .top)
        } else if let last = events.last {
            proxy.scrollTo(last.id, anchor: .bottom)
        }
        positioned = true
    }

    private var subtitle: String {
        guard let channel else { return "" }
        let liveness = store.liveness(channel).text
        return liveness.isEmpty ? channel.status : liveness
    }
}

/// The live "the agent is on it" row, shown at the tail of the thread.
///
/// ⚠️ No number, ever — idle_s is time-since-output-changed sampled live, so a working
/// pane reads 0.3, 2.1, 0.2… and floored to seconds it looks stuck at 0,1,0,1. That was
/// already fixed for the labels; this row inherits the same rule via Liveness.text.
struct WorkingRow: View {
    var text: String

    var body: some View {
        HStack(spacing: 8) {
            ProgressView()
                .controlSize(.small)
                .progressViewStyle(.circular)
            Text(text)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .transition(.opacity)
    }
}


/// The unread boundary: everything below arrived since the last visit.
struct NewMarker: View {
    var count: Int

    var body: some View {
        HStack(spacing: 8) {
            Rectangle().fill(.tint).frame(height: 1)
            Text(count == 1 ? "1 new" : "\(count) new")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(.tint)
                .fixedSize()
            Rectangle().fill(.tint).frame(height: 1)
        }
        .padding(.vertical, 2)
    }
}

struct Composer: View {
    var store: HubStore
    var pane: String
    var sendable: Bool
    @State private var draft = ""
    @State private var failure: String?
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let failure {
                Text(failure)
                    .font(.system(size: 14))
                    .foregroundStyle(.red)
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField(sendable ? "Message this channel" : "Channel is not live",
                          text: $draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(size: 14))
                    .lineLimit(1...8)
                    .focused($focused)
                    .disabled(!sendable)
                    .onSubmit(send)
                Button(action: send) { Image(systemName: "paperplane.fill") }
                    .disabled(!sendable || draft.trimmed.isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
                    .help("Send (⌘↩)")
                Button {
                    Task {
                        do { try await store.interrupt(pane) }
                        catch { failure = "interrupt failed: \(error)" }
                    }
                } label: { Image(systemName: "stop.fill") }
                    .disabled(!sendable)
                    .help("Interrupt — sends Escape to the agent")
            }
        }
        .padding(10)
    }

    private func send() {
        let text = draft.trimmed
        guard sendable, !text.isEmpty else { return }
        draft = ""
        failure = nil
        focused = true
        Task {
            do { try await store.send(text, to: pane) }
            catch {
                // The message did not reach the pane; put it back rather than lose it.
                failure = "send failed: \(error)"
                if draft.isEmpty { draft = text }
            }
        }
    }
}
