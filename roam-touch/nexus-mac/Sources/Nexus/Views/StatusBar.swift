import SwiftUI

/// A worn client must degrade to a visible red bar, never to nothing —
/// the desk client keeps the same rule.
struct StatusBar: View {
    var store: HubStore

    var body: some View {
        HStack(spacing: 8) {
            switch store.connection {
            case .connected:
                Circle().fill(.green).frame(width: 8, height: 8)
                Text("hub \(store.hubVersion ?? "")").font(.system(size: 14)).foregroundStyle(.secondary)
            case .connecting:
                ProgressView().controlSize(.small)
                Text("connecting…").font(.system(size: 14)).foregroundStyle(.secondary)
            case .reconnecting(let detail):
                Circle().fill(.red).frame(width: 8, height: 8)
                Text("reconnecting — \(detail)").font(.system(size: 14)).foregroundStyle(.red).lineLimit(1)
            }
            if store.pendingEvents > 0 {
                // Events written while the hub process was down, not yet adopted.
                Label("\(store.pendingEvents) pending on the hub", systemImage: "tray.full")
                    .font(.system(size: 14)).foregroundStyle(.orange)
            }
            Spacer()
        }
        .padding(.horizontal, 10).padding(.vertical, 5)
        .background(.bar)
    }
}
