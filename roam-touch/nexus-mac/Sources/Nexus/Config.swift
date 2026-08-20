import Foundation

/// Where the hub is and how to authenticate. Resolution order:
/// env vars → ~/.config/roam-nexus/config.json → the hub's own token file
/// when running on the same box as the hub.
struct HubConfig: Sendable, Equatable {
    var baseURL: URL
    var token: String

    static let defaultBase = URL(string: "http://talos:8787")!

    /// The socket endpoint. URLSession's WebSocket task wants ws/wss even
    /// though the upgrade is negotiated by handshake — derive it, never
    /// hard-code a scheme (API.md §4; hard-coding crashed the Android client).
    func wsURL(since: Int?) -> URL {
        var parts = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        parts.scheme = parts.scheme == "https" ? "wss" : "ws"
        parts.path = "/ws"
        if let since { parts.queryItems = [URLQueryItem(name: "since", value: String(since))] }
        return parts.url!
    }

    static func load(environment: [String: String] = ProcessInfo.processInfo.environment,
                     home: URL = FileManager.default.homeDirectoryForCurrentUser) -> HubConfig? {
        let envURL = environment["ROAM_HUB_URL"].flatMap(URL.init(string:))
        if let token = environment["ROAM_HUB_TOKEN"], !token.isEmpty {
            return HubConfig(baseURL: envURL ?? defaultBase, token: token.trimmed)
        }

        let configFile = home.appending(path: ".config/roam-nexus/config.json")
        if let data = try? Data(contentsOf: configFile),
           let file = try? JSONDecoder.hub.decode(ConfigFile.self, from: data),
           !file.token.isEmpty {
            let base = file.baseUrl.flatMap(URL.init(string:)) ?? envURL ?? defaultBase
            return HubConfig(baseURL: base, token: file.token.trimmed)
        }

        // Same-box fallback: the hub's own token file (0600, gitignored).
        let hubToken = home.appending(path: "Projects/roam/roam-touch/hub/hub-token.txt")
        if let token = try? String(contentsOf: hubToken, encoding: .utf8), !token.trimmed.isEmpty {
            return HubConfig(baseURL: envURL ?? defaultBase, token: token.trimmed)
        }
        return nil
    }

    private struct ConfigFile: Decodable {
        var baseUrl: String?
        var token: String
    }
}

extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}
