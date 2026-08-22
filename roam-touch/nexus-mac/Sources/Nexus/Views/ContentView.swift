import SwiftUI

/// Where the detail pane points: one conversation, or one of the apps.
enum MainDestination: Hashable {
    case channel(String)
    case files
}

struct ContentView: View {
    @Bindable var store: HubStore
    @Environment(\.controlActiveState) private var activeState
    @State private var destination: MainDestination?

    var body: some View {
        // Explicit stacking, not safeAreaInset: on macOS a bottom inset on
        // NavigationSplitView overlays the detail column instead of insetting
        // it, which hid the bottom of the composer under the status bar.
        VStack(spacing: 0) {
            NavigationSplitView {
                Sidebar(store: store, destination: $destination)
                    .navigationSplitViewColumnWidth(min: 250, ideal: 300)
            } detail: {
                switch destination {
                case .channel(let pane):
                    ThreadView(store: store, pane: pane)
                        .id(pane)
                case .files:
                    FilesBrowser(api: store.api)
                case nil:
                    ContentUnavailableView("Pick a channel", systemImage: "rectangle.split.2x1",
                                           description: Text("Each channel is one agent pane on talos.")
                                               .font(.system(size: 14)))
                }
            }
            Divider()
            StatusBar(store: store)
        }
        // ⌘⇧↑ / ⌘⇧↓ quick channel switch. Zero-sized buttons rather than a
        // Commands menu because the shortcut needs the store, and the store
        // lives here — a menu command would have to reach across the scene.
        .background {
            VStack {
                Button("") { store.selectNeighbour(delta: -1) }
                    .keyboardShortcut(.upArrow, modifiers: [.command, .shift])
                Button("") { store.selectNeighbour(delta: 1) }
                    .keyboardShortcut(.downArrow, modifiers: [.command, .shift])
            }
            .opacity(0)
            .accessibilityHidden(true)
        }
        .onChange(of: destination) { _, dest in
            if case .channel(let pane) = dest { store.selectedPane = pane }
            else { store.selectedPane = nil }
        }
        .onChange(of: store.selectedPane) { _, pane in
            // Store-driven selection (a created session lands selected).
            if let pane, destination != .channel(pane) { destination = .channel(pane) }
        }
        .onChange(of: activeState, initial: true) { _, state in
            store.appActive = (state != .inactive)
        }
    }
}

/// Channels scroll in the top of the rail; the apps live at the bottom,
/// pinned — two scopes, one column.
struct Sidebar: View {
    @Bindable var store: HubStore
    @Binding var destination: MainDestination?

    var body: some View {
        VStack(spacing: 0) {
            ChannelList(store: store, destination: $destination)
            Divider()
            AppsSection(destination: $destination)
        }
    }
}

struct AppsSection: View {
    @Binding var destination: MainDestination?

    private struct App: Identifiable {
        let dest: MainDestination
        let name: String
        let icon: String
        var id: String { name }
    }

    private let apps: [App] = [
        App(dest: .files, name: "Files", icon: "folder"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("APPS")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(.tertiary)
                .padding(.horizontal, 14)
                .padding(.top, 10)
            ForEach(apps) { app in
                let selected = destination == app.dest
                Button {
                    destination = selected ? nil : app.dest
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: app.icon)
                            .frame(width: 20)
                        Text(app.name).font(.system(size: 14))
                        Spacer()
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(selected ? Color.accentColor.opacity(0.22) : .clear)
                    )
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 8)
            }
        }
        .padding(.bottom, 10)
    }
}
