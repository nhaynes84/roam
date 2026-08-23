import SwiftUI
import AppKit

/// An image that lives IN the thread.
///
/// ★ "you should be able to dump images into these channel feeds ... don't point me
/// elsewhere." So this draws in the conversation, at the point it was posted — not as
/// a link, not as a filename, and not as a trip to the Files browser.
///
/// ⚠️ Cannot use AsyncImage: the hub needs a Bearer token and AsyncImage has nowhere to
/// put one. The bytes come through HubAPI like everything else.
struct InlineImage: View {
    var store: HubStore
    var payload: ImagePayload
    var caption: String?

    @State private var image: NSImage?
    @State private var failure: String?

    /// ★ Reserve the true aspect ratio BEFORE the bytes land, so a thread does not
    /// jump under the reader while images load. This is why the hub parses dimensions
    /// out of the file header.
    private var ratio: CGFloat? {
        guard let w = payload.width, let h = payload.height, w > 0, h > 0 else { return nil }
        return CGFloat(w) / CGFloat(h)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Group {
                if let image {
                    Image(nsImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                } else if let failure {
                    Label(failure, systemImage: "exclamationmark.triangle")
                        .font(.system(size: 14)).foregroundStyle(.orange)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    ZStack {
                        Rectangle().fill(Theme.agentFill)
                        ProgressView().controlSize(.small)
                    }
                }
            }
            .aspectRatio(ratio, contentMode: .fit)
            .frame(maxWidth: 460, maxHeight: 460, alignment: .leading)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(Theme.agentEdge, lineWidth: 1)
            )

            if let caption, !caption.isEmpty {
                Text(caption).font(.system(size: 14)).foregroundStyle(.secondary)
            }
        }
        .task(id: payload.id) { await load() }
        .contextMenu {
            Button("Copy Image") {
                guard let image else { return }
                NSPasteboard.general.clearContents()
                NSPasteboard.general.writeObjects([image])
            }
            Button("Save As…") { save() }
        }
    }

    private func load() async {
        if image != nil { return }
        do {
            let data = try await store.api.imageData(id: payload.id)
            guard let decoded = NSImage(data: data) else {
                failure = "could not decode this image"
                return
            }
            image = decoded
        } catch {
            failure = "image did not load: \(error.localizedDescription)"
        }
    }

    private func save() {
        guard let image, let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = (caption?.isEmpty == false ? caption! : "image") + ".png"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try? png.write(to: url)
    }
}
