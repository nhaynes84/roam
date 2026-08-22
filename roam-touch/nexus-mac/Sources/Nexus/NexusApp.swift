import SwiftUI

@main
struct NexusApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup("Nexus") {
            RootView(model: model)
                .frame(minWidth: 760, minHeight: 480)
                .background(WindowFrameSaver(autosaveName: "nexus.main"))
        }
        .windowResizability(.contentMinSize)
        .commands { NexusCommands() }
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


/// Remember the window's size and position across launches.
///
/// ★ SwiftUI does not persist a WindowGroup's frame on its own, and macOS's own
/// window restoration is gated on a system preference ("Close windows when quitting
/// an application"), so it cannot be relied on. `frameAutosaveName` is AppKit's own
/// mechanism and works regardless — it is what every Mac app has always used.
private struct WindowFrameSaver: NSViewRepresentable {
    let autosaveName: String

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        // The window does not exist yet during makeNSView; next runloop pass it does.
        DispatchQueue.main.async {
            guard let window = view.window else { return }
            window.setFrameAutosaveName(autosaveName)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}
}
