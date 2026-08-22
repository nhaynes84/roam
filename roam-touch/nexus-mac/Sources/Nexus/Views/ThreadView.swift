import SwiftUI
import AppKit

struct ThreadView: View {
    @Bindable var store: HubStore
    var pane: String

    /// Unread boundary, snapshotted when the channel opens — before markRead.
    @State private var newMarkerId: Int?
    @State private var newCount = 0
    /// Initial positioning done; only then do new arrivals auto-follow.
    @State private var positioned = false
    @State private var showCapture = false
    /// ⌘↑ / ⌘↓ land here; the proxy only exists inside ScrollViewReader, so the
    /// command sets a request and the reader performs it.
    @State private var scrollRequest: ScrollRequest?
    @State private var dropped: URL?
    @State private var dropTargeted = false

    enum ScrollRequest { case top, bottom }

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
                .onChange(of: scrollRequest) { _, req in
                    guard let req else { return }
                    scrollRequest = nil
                    withAnimation {
                        switch req {
                        case .top:
                            if let first = thread.events.first { proxy.scrollTo(first.id, anchor: .top) }
                        case .bottom:
                            if let last = thread.events.last { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
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
            Composer(store: store, pane: pane,
                     sendable: channel?.live == true && pane != "@host",
                     dropped: $dropped)
        }
        // ★ Drag a file anywhere onto the conversation. Same door as the paperclip;
        //   dropping where you are already looking beats a file picker.
        .dropDestination(for: URL.self) { urls, _ in
            guard let url = urls.first else { return false }
            dropped = url
            return true
        } isTargeted: { dropTargeted = $0 }
        .overlay {
            if dropTargeted {
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(Color.accentColor, style: StrokeStyle(lineWidth: 2, dash: [7, 5]))
                    .padding(6)
                    .allowsHitTesting(false)
            }
        }
        .navigationTitle(channel?.label ?? pane)
        .navigationSubtitle(subtitle)
        .focusedSceneValue(\.threadScroll, ThreadScrollAction(
            toTop: { scrollRequest = .top },
            toBottom: { scrollRequest = .bottom }))
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
    @Binding var dropped: URL?
    @State private var failure: String?
    @State private var attaching = false
    /// Survives view teardown, app quit, crash and reboot — see HubStore.setDraft.
    private var draft: Binding<String> {
        Binding(get: { store.draft(for: pane) },
                set: { store.setDraft($0, for: pane) })
    }
    @State private var attached: String?
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let failure {
                Text(failure)
                    .font(.system(size: 14))
                    .foregroundStyle(.red)
            }
            if store.openPrompts[pane] != nil {
                // ⚠️ Say it BEFORE he sends, not after. His words are safe either way
                //    — the hub holds them — but a message that appears to vanish is
                //    indistinguishable from the bug this feature exists to fix.
                Label("There's a question above — this will be held until you answer it",
                      systemImage: "hand.raised.fill")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.accentColor)
            }
            if let attached {
                // ⚠️ The honest promise: the inbox is SWEPT by the prompt hook, not
                //    watched. It is in front of Claude on the NEXT message, not now.
                Label("\(attached) attached — send a message and it goes with it",
                      systemImage: "checkmark.circle.fill")
                    .font(.system(size: 14))
                    .foregroundStyle(.secondary)
            }
            // ★ The composer is the NAVIGATION layer, so this is where glass belongs —
            //   not on the bubbles. `.roundedBorder` was the ugly bit: a 2005 bezel with
            //   a hairline that vanishes on a dark ground. A glass slab with a real focus
            //   ring reads as a place to type.
            GlassEffectContainer(spacing: 10) {
                HStack(alignment: .bottom, spacing: 10) {
                    TextField(sendable ? "Message this channel" : "Channel is not live",
                              text: draft, axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .lineLimit(1...8)
                        .focused($focused)
                        .disabled(!sendable)
                        .onSubmit(send)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 9)
                        .glassEffect(.regular, in: .rect(cornerRadius: Theme.composerRadius))
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.composerRadius)
                                .strokeBorder(focused ? Color.accentColor.opacity(0.65)
                                                      : Theme.railHairline,
                                              lineWidth: focused ? 2 : 1)
                        )
                        .animation(.easeOut(duration: 0.12), value: focused)

                    Button { startDictation() } label: {
                        Image(systemName: "mic.fill").frame(width: 16, height: 16)
                    }
                    .buttonStyle(.glass)
                    .controlSize(.large)
                    .disabled(!sendable)
                    .help("Dictate — macOS dictation, straight into the message")

                    Button { pickAttachment() } label: {
                        Image(systemName: attaching ? "arrow.up.circle" : "paperclip")
                            .frame(width: 16, height: 16)
                    }
                    .buttonStyle(.glass)
                    .controlSize(.large)
                    .disabled(attaching)
                    .help("Attach a file — lands in front of Claude on your next message")

                    Button {
                        Task {
                            do { try await store.interrupt(pane) }
                            catch { failure = "interrupt failed: \(error)" }
                        }
                    } label: {
                        Image(systemName: "stop.fill").frame(width: 16, height: 16)
                    }
                    .buttonStyle(.glass)
                    .controlSize(.large)
                    .disabled(!sendable)
                    .help("Interrupt — sends Escape to the agent")

                    Button(action: send) {
                        Image(systemName: "arrow.up").fontWeight(.semibold)
                            .frame(width: 16, height: 16)
                    }
                    .buttonStyle(.glassProminent)
                    .controlSize(.large)
                    .tint(.accentColor)
                    .disabled(!sendable || draft.wrappedValue.trimmed.isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
                    .help("Send (⌘↩)")
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .onChange(of: dropped) { _, url in
            guard let url else { return }
            dropped = nil
            do { attach(name: url.lastPathComponent, data: try Data(contentsOf: url)) }
            catch { failure = "could not read \(url.lastPathComponent): \(error)" }
        }
    }

    /// ★ macOS already does speech-to-text; he did not want a second one built, he
    /// wanted it on a BUTTON — "i realize it's a key on my mac but that's like a two
    /// button combo". So this fires the system's own dictation rather than bringing in
    /// a recogniser, which also means no microphone entitlement of ours and nothing
    /// that can be invalidated by re-signing the bundle on each deploy.
    ///
    /// `startDictation:` is what the Edit menu's own item sends; NSApplication answers
    /// it, so sending to nil walks the responder chain and lands there (verified:
    /// NSApplication.instancesRespond(to:) == true, NSResponder/NSTextView == false).
    /// ⚠️ Dictation types into the FOCUSED field, so focus must land first — hence the
    /// hop to the next runloop pass before sending.
    private func startDictation() {
        focused = true
        DispatchQueue.main.async {
            NSApp.sendAction(Selector(("startDictation:")), to: nil, from: nil)
        }
    }

    /// Shared by the paperclip and by drag-and-drop.
    func attach(name: String, data: Data) {
        attaching = true
        failure = nil
        Task {
            defer { attaching = false }
            do {
                let res = try await store.api.upload(name: name, data: data)
                attached = res.shared
                focused = true
            } catch {
                failure = "attach failed: \(error)"
            }
        }
    }

    private func pickAttachment() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.message = "Hand this file to Claude"
        panel.prompt = "Attach"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            attach(name: url.lastPathComponent, data: try Data(contentsOf: url))
        } catch {
            failure = "could not read \(url.lastPathComponent): \(error)"
        }
    }

    private func send() {
        let text = draft.wrappedValue.trimmed
        guard sendable, !text.isEmpty else { return }
        store.clearDraft(for: pane)
        failure = nil
        focused = true
        Task {
            do { try await store.send(text, to: pane) }
            catch {
                // The message did not reach the pane; put it back rather than lose it.
                failure = "send failed: \(error)"
                if store.draft(for: pane).isEmpty { store.setDraft(text, for: pane) }
            }
        }
    }
}
