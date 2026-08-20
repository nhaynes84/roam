import SwiftUI

struct ContentView: View {
    @Bindable var store: HubStore
    @Environment(\.controlActiveState) private var activeState

    var body: some View {
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
        .safeAreaInset(edge: .bottom, spacing: 0) { StatusBar(store: store) }
        .onChange(of: activeState, initial: true) { _, state in
            store.appActive = (state != .inactive)
        }
    }
}
