import SwiftUI

@main
struct NexusApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup("Nexus") {
            RootView(model: model)
                .frame(minWidth: 760, minHeight: 480)
        }
        .windowResizability(.contentMinSize)
        .commands { ViewCommands() }
    }
}

/// ★ Owner: "leave it an option for consistency but default me to expanded mode."
/// The per-row expand/collapse link stays exactly as it was; this only moves which way
/// a row starts, and a row he has clicked keeps his choice for as long as it is on screen.
struct ViewCommands: Commands {
    @AppStorage("defaultExpanded") private var defaultExpanded = true

    var body: some Commands {
        CommandGroup(after: .toolbar) {
            Toggle("Expand responses by default", isOn: $defaultExpanded)
                .keyboardShortcut("e", modifiers: [.command, .shift])
        }
    }
}

@MainActor @Observable
final class AppModel {
    var store: HubStore?
    var configError = false

    init() {
        // Bare `swift run` executables need explicit activation to get a window.
        NSApplication.shared.setActivationPolicy(.regular)
        NSApplication.shared.activate(ignoringOtherApps: true)
        if let config = HubConfig.load() {
            let store = HubStore(api: HubAPI(config: config))
            self.store = store
            store.start()
        } else {
            configError = true
        }
    }
}

struct RootView: View {
    var model: AppModel

    var body: some View {
        if let store = model.store {
            ContentView(store: store)
        } else {
            ContentUnavailableView(
                "No hub configuration",
                systemImage: "key.slash",
                description: Text("Set ROAM_HUB_TOKEN, or write ~/.config/roam-nexus/config.json with {\"base_url\", \"token\"}.")
                    .font(.system(size: 14))
            )
        }
    }
}
