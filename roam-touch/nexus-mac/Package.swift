// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "NexusMac",
    platforms: [.macOS("26.0")],
    dependencies: [
        // Block-level markdown (code fences, tables, lists) — the hand-rolled
        // inline-only AttributedString showed raw ``` fences in outcomes.
        .package(url: "https://github.com/gonzalezreal/swift-markdown-ui", from: "2.4.0"),
    ],
    targets: [
        .executableTarget(
            name: "Nexus",
            dependencies: [.product(name: "MarkdownUI", package: "swift-markdown-ui")],
            path: "Sources/Nexus"),
        .testTarget(name: "NexusTests", dependencies: ["Nexus"], path: "Tests/NexusTests"),
    ]
)
