import SwiftUI

struct ThreadView: View {
    @Bindable var store: HubStore
    var pane: String

    private var channel: Channel? { store.channels.first { $0.paneId == pane } }
    private var thread: ChannelThread { store.threads[pane] ?? ChannelThread() }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        ForEach(thread.events) { event in
                            EventRow(store: store, event: event,
                                     delivered: thread.delivered.contains(event.id))
                                .id(event.id)
                        }
                    }
                    .padding(12)
                }
                .onChange(of: thread.events.last?.id, initial: true) { _, last in
                    if let last { proxy.scrollTo(last, anchor: .bottom) }
                }
            }
            Divider()
            Composer(store: store, pane: pane, sendable: channel?.live == true && pane != "@host")
        }
        .navigationTitle(channel?.label ?? pane)
        .navigationSubtitle(subtitle)
        .task(id: pane) {
            await store.loadHistoryIfNeeded(pane)
            store.markRead(pane)
        }
    }

    private var subtitle: String {
        guard let channel else { return "" }
        let liveness = store.liveness(channel).text
        return liveness.isEmpty ? channel.status : liveness
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
