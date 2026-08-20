import SwiftUI
// The scene is built fresh inside one task and handed to SwiftUI once —
// nothing else ever holds it, so the non-Sendable hop is safe.
@preconcurrency import SceneKit
import SceneKit.ModelIO
import ModelIO

/// A read-only browser onto the hub's shared folders (CAD / Photos),
/// living in the main window's detail pane. Roots are named, not paths.
struct FilesBrowser: View {
    var api: HubAPI
    @State private var path = ""
    @State private var listing: FilesResponse?
    @State private var selected: FileEntry?
    @State private var failure: String?

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 0) {
                breadcrumb
                Divider()
                if let failure {
                    Text(failure).font(.system(size: 14)).foregroundStyle(.red).padding()
                    Spacer()
                } else {
                    List(listing?.entries ?? [], selection: $selected) { entry in
                        EntryRow(entry: entry)
                            .tag(entry)
                            .onTapGesture(count: 2) { if entry.isDir { descend(entry) } }
                    }
                    .contextMenu(forSelectionType: FileEntry.self) { _ in } primaryAction: { items in
                        if let entry = items.first, entry.isDir { descend(entry) }
                    }
                }
            }
            .frame(minWidth: 300, idealWidth: 340)
            PreviewPane(api: api, entry: selected)
                .frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
        }
        .navigationTitle(path.isEmpty ? "Files" : path)
        .task(id: path) { await load() }
    }

    private var breadcrumb: some View {
        HStack(spacing: 4) {
            Button("Files") { path = "" }.buttonStyle(.link).font(.system(size: 14))
            ForEach(Array(path.split(separator: "/").enumerated()), id: \.offset) { i, part in
                Text("/").foregroundStyle(.tertiary)
                Button(String(part)) {
                    path = path.split(separator: "/")[...i].joined(separator: "/")
                }
                .buttonStyle(.link).font(.system(size: 14))
            }
            Spacer()
        }
        .padding(8)
    }

    private func descend(_ entry: FileEntry) {
        selected = nil
        path = entry.path
    }

    private func load() async {
        do {
            listing = try await api.files(path: path)
            failure = nil
        } catch {
            failure = "cannot list \(path.isEmpty ? "roots" : path): \(error)"
        }
    }
}

struct EntryRow: View {
    var entry: FileEntry

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon).frame(width: 18)
            VStack(alignment: .leading, spacing: 1) {
                Text(entry.name).font(.system(size: 14)).lineLimit(1)
                if !entry.isDir {
                    Text(detail).font(.system(size: 14)).foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 1)
    }

    private var icon: String {
        switch entry.kind {
        case "dir": return "folder"
        case "image": return "photo"
        case "mesh": return "cube.transparent"
        case "cad": return "cube"
        default: return "doc"
        }
    }

    private var detail: String {
        var parts = [ByteCountFormatter.string(fromByteCount: Int64(entry.size), countStyle: .file)]
        if entry.kind == "cad" {
            parts.append(entry.meshPath == nil ? "no mesh built" : "mesh available")
        }
        return parts.joined(separator: " · ")
    }
}

struct PreviewPane: View {
    var api: HubAPI
    var entry: FileEntry?

    var body: some View {
        Group {
            if let entry {
                switch entry.kind {
                case "image":
                    ImagePreview(api: api, path: entry.path)
                case "mesh", "cad":
                    if let renderable = entry.renderablePath {
                        ModelViewer(api: api, path: renderable)
                    } else {
                        // A STEP with no STL beside it: the build pipeline has
                        // not produced a renderable mesh, and a b-rep is not
                        // something to attempt client-side (contract).
                        ContentUnavailableView(
                            "No mesh built for this part",
                            systemImage: "cube",
                            description: Text("Run the CAD build to drop an .stl beside it.")
                                .font(.system(size: 14)))
                    }
                default:
                    ContentUnavailableView(entry.name, systemImage: "doc",
                                           description: Text("No preview for this kind.")
                                               .font(.system(size: 14)))
                }
            } else {
                ContentUnavailableView("Select a file", systemImage: "sidebar.left",
                                       description: Text("Images preview here; STL parts open in the model viewer.")
                                           .font(.system(size: 14)))
            }
        }
    }
}

struct ImagePreview: View {
    var api: HubAPI
    var path: String
    @State private var image: NSImage?
    @State private var failure: String?

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image).resizable().scaledToFit().padding(8)
            } else if let failure {
                Text(failure).font(.system(size: 14)).foregroundStyle(.red)
            } else {
                ProgressView()
            }
        }
        .task(id: path) {
            image = nil
            do { image = NSImage(data: try await api.fileData(path: path)) }
            catch { failure = "\(error)" }
        }
    }
}

/// Native STL viewer: ModelIO imports the mesh, SceneKit renders it with
/// orbit/zoom camera control. No WebView, no three.js.
struct ModelViewer: View {
    var api: HubAPI
    var path: String
    @State private var scene: SCNScene?
    @State private var failure: String?

    var body: some View {
        Group {
            if let scene {
                SceneView(scene: scene,
                          options: [.allowsCameraControl, .autoenablesDefaultLighting])
            } else if let failure {
                Text(failure).font(.system(size: 14)).foregroundStyle(.red)
            } else {
                ProgressView("fetching mesh…")
            }
        }
        .task(id: path) {
            scene = nil
            failure = nil
            do {
                let data = try await api.fileData(path: path)
                scene = try await Task.detached(priority: .userInitiated) {
                    try Self.buildScene(stl: data)
                }.value
            } catch {
                failure = "cannot load mesh: \(error)"
            }
        }
    }

    /// MDLAsset only imports from URLs, so the bytes take one hop through a
    /// temp file. Heavy meshes parse off the main thread.
    nonisolated static func buildScene(stl data: Data) throws -> SCNScene {
        let tmp = FileManager.default.temporaryDirectory
            .appendingPathComponent("nexus-\(UUID().uuidString).stl")
        try data.write(to: tmp)
        defer { try? FileManager.default.removeItem(at: tmp) }
        let asset = MDLAsset(url: tmp)
        let scene = SCNScene(mdlAsset: asset)
        // Neutral matte so geometry reads by shape, not by material accident.
        scene.rootNode.enumerateHierarchy { node, _ in
            for material in node.geometry?.materials ?? [] {
                material.diffuse.contents = NSColor(calibratedWhite: 0.75, alpha: 1)
                material.lightingModel = .physicallyBased
                material.roughness.contents = 0.6
            }
        }
        scene.background.contents = NSColor.windowBackgroundColor
        return scene
    }
}
