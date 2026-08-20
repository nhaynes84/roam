import SwiftUI

struct ContentView: View {
    @Bindable var store: HubStore
    @Environment(\.controlActiveState) private var activeState

    var body: some View {
        // Explicit stacking, not safeAreaInset: on macOS a bottom inset on
        // NavigationSplitView overlays the detail column instead of insetting
        // it, which hid the bottom of the composer under the status bar.
        VStack(spacing: 0) {
            NavigationSplitView {
                ChannelList(store: store)
                    .navigationSplitViewColumnWidth(min: 240, ideal: 290)
            } detail: {
                if let pane = store.selectedPane {
                    ThreadView(store: store, pane: pane)
                        .id(pane)
                } else {
                    ContentUnavailableView("Pick a channel", systemImage: "rectangle.split.2x1",
                                           description: Text("Each channel is one agent pane on talos.")
                                               .font(.system(size: 14)))
                }
            }
            Divider()
            StatusBar(store: store)
        }
        .onChange(of: activeState, initial: true) { _, state in
            store.appActive = (state != .inactive)
        }
    }
}
