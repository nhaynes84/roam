import SwiftUI

/// Menu commands, and the focused values that let them reach the view that can act.
///
/// ⚠️ These were hidden zero-sized Buttons carrying `.keyboardShortcut`. That looked
/// fine and behaved wrong: ⌘↑ fired the ⌘⇧↑ button, so plain ⌘-arrow moved the active
/// channel — "CMD arrows is top and bottom normally and i need that". Real menu items
/// match modifiers exactly, are discoverable, and show the user what the key is.
///
/// ★ ⌘↑ / ⌘↓  = top / bottom of the thread (the macOS convention)
/// ★ ⌘⇧↑ / ⌘⇧↓ = previous / next channel

struct ThreadScrollAction {
    var toTop: () -> Void
    var toBottom: () -> Void
}

struct ThreadScrollKey: FocusedValueKey {
    typealias Value = ThreadScrollAction
}

struct ChannelNavKey: FocusedValueKey {
    typealias Value = HubStore
}

extension FocusedValues {
    var threadScroll: ThreadScrollAction? {
        get { self[ThreadScrollKey.self] }
        set { self[ThreadScrollKey.self] = newValue }
    }
    var channelNav: HubStore? {
        get { self[ChannelNavKey.self] }
        set { self[ChannelNavKey.self] = newValue }
    }
}

struct NexusCommands: Commands {
    @FocusedValue(\.threadScroll) private var scroll
    @FocusedValue(\.channelNav) private var nav
    @AppStorage("defaultExpanded") private var defaultExpanded = true

    var body: some Commands {
        CommandGroup(after: .toolbar) {
            Button("Scroll to Top") { scroll?.toTop() }
                .keyboardShortcut(.upArrow, modifiers: .command)
                .disabled(scroll == nil)
            Button("Scroll to Bottom") { scroll?.toBottom() }
                .keyboardShortcut(.downArrow, modifiers: .command)
                .disabled(scroll == nil)

            Divider()

            Button("Previous Channel") { nav?.selectNeighbour(delta: -1) }
                .keyboardShortcut(.upArrow, modifiers: [.command, .shift])
                .disabled(nav == nil)
            Button("Next Channel") { nav?.selectNeighbour(delta: 1) }
                .keyboardShortcut(.downArrow, modifiers: [.command, .shift])
                .disabled(nav == nil)

            Divider()

            Toggle("Expand responses by default", isOn: $defaultExpanded)
                .keyboardShortcut("e", modifiers: [.command, .shift])
        }
    }
}
