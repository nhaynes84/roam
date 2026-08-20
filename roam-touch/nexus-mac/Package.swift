// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "NexusMac",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "Nexus", path: "Sources/Nexus"),
        .testTarget(name: "NexusTests", dependencies: ["Nexus"], path: "Tests/NexusTests"),
    ]
)
