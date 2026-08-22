import Foundation

// Wire types for hub protocol 1 (hub/API.md). Decoded with .convertFromSnakeCase,
// so property names are the camelCase form of the wire keys.

struct Coverage: Decodable, Sendable, Equatable {
    var known: Bool
    var covered: Bool
    var by: [String]
    var lastInput: String?
}

struct EventMeta: Decodable, Sendable, Equatable {
    var source: String?
    var sessionId: String?
    var echoOf: Int?
    var attempted: String?
    var answerSource: String?
    var transcriptSettled: Bool?
    var origin: String?
    var offline: Bool?
    var key: String?
}

struct Event: Decodable, Sendable, Identifiable, Equatable {
    var id: Int
    var paneId: String
    var kind: String
    var body: String
    var summary: String
    var bodyChars: Int?
    var bodyTruncated: Bool?
    var coverage: Coverage?
    var meta: EventMeta?
    var ts: Double
    var archived: Bool?

    var isTruncated: Bool { bodyTruncated ?? false }
    var echoOf: Int? { kind == "receipt" ? meta?.echoOf : nil }
}

struct Channel: Decodable, Sendable, Identifiable, Equatable {
    var paneId: String
    var label: String
    var session: String?
    var window: Int?
    var index: Int?
    var command: String?
    var live: Bool
    var status: String
    var archived: Bool?
    var firstSeen: Double?
    var lastSeen: Double?
    var lastOutputAt: Double?
    var idleS: Double?
    var lastInputSource: String?
    var lastInputAt: Double?
    var eventCount: Int?
    var lastEvent: Event?

    var id: String { paneId }
}

// MARK: - REST payloads

struct ChannelsResponse: Decodable, Sendable {
    var channels: [Channel]
    var latestEventId: Int
    var serverTime: Double?
}

struct HistoryResponse: Decodable, Sendable {
    var paneId: String
    var events: [Event]
    var latestEventId: Int
}

struct EventsResponse: Decodable, Sendable {
    var events: [Event]
    var latestEventId: Int
}

struct EventResponse: Decodable, Sendable { var event: Event }

struct SendResponse: Decodable, Sendable {
    var event: Event
    var channel: Channel
}

struct CaptureResponse: Decodable, Sendable {
    var paneId: String
    var lines: Int
    var text: String
}

struct HealthResponse: Decodable, Sendable {
    struct Build: Decodable, Sendable {
        var version: String
        var commit: String?
        var schema: Int?
    }
    var ok: Bool
    var version: String
    var protocolVersion: Int
    var build: Build?

    enum CodingKeys: String, CodingKey {
        // .convertFromSnakeCase runs before CodingKeys matching, so these are
        // the post-conversion names; "protocol" has no underscore to convert.
        case ok, version, build
        case protocolVersion = "protocol"
    }
}

struct StatusResponse: Decodable, Sendable {
    var ok: Bool
    var pendingEvents: Int?
    var latestEventId: Int?
    var liveChannels: Int?
}

struct HubErrorBody: Decodable, Sendable { var detail: String }

enum HubError: Error, CustomStringConvertible {
    case http(status: Int, detail: String)
    case badPayload(String)
    case unauthorised

    var description: String {
        switch self {
        case .http(let status, let detail): return "\(detail) (HTTP \(status))"
        case .badPayload(let s): return "unexpected payload: \(s)"
        case .unauthorised: return "hub rejected the token"
        }
    }
}

// MARK: - WebSocket frames

struct Hello: Decodable, Sendable {
    var protocolVersion: Int
    var version: String
    var serverTime: Double
    var latestEventId: Int
    var channels: [Channel]

    enum CodingKeys: String, CodingKey {
        case version, serverTime, latestEventId, channels
        case protocolVersion = "protocol"
    }
}

enum Frame: Sendable {
    case hello(Hello)
    case backlog(since: Int, events: [Event])
    case event(Event)
    case channels([Channel], serverTime: Double?)
    case channel(Channel)
    case activity(panes: [String: Double], serverTime: Double)
    case historyCleared(paneId: String)
    case presence
    case ping
    case pong
    case desync(latestEventId: Int)
    case error(detail: String)
    case unknown(type: String)
}

enum FrameDecoder {
    private struct Envelope: Decodable { var type: String }
    private struct BacklogPayload: Decodable { var since: Int; var events: [Event] }
    private struct EventPayload: Decodable { var event: Event }
    private struct ChannelsPayload: Decodable { var channels: [Channel]; var serverTime: Double? }
    private struct ChannelPayload: Decodable { var channel: Channel }
    private struct ActivityPayload: Decodable { var panes: [String: Double]; var serverTime: Double }
    private struct HistoryClearedPayload: Decodable { var paneId: String }
    private struct DesyncPayload: Decodable { var latestEventId: Int }
    private struct ErrorPayload: Decodable { var detail: String }

    static func decode(_ data: Data) throws -> Frame {
        let decoder = JSONDecoder.hub
        let type = try decoder.decode(Envelope.self, from: data).type
        switch type {
        case "hello": return .hello(try decoder.decode(Hello.self, from: data))
        case "backlog":
            let p = try decoder.decode(BacklogPayload.self, from: data)
            return .backlog(since: p.since, events: p.events)
        case "event": return .event(try decoder.decode(EventPayload.self, from: data).event)
        case "channels":
            let p = try decoder.decode(ChannelsPayload.self, from: data)
            return .channels(p.channels, serverTime: p.serverTime)
        case "channel": return .channel(try decoder.decode(ChannelPayload.self, from: data).channel)
        case "activity":
            let p = try decoder.decode(ActivityPayload.self, from: data)
            return .activity(panes: p.panes, serverTime: p.serverTime)
        case "history_cleared":
            return .historyCleared(paneId: try decoder.decode(HistoryClearedPayload.self, from: data).paneId)
        case "presence": return .presence
        case "ping": return .ping
        case "pong": return .pong
        case "desync": return .desync(latestEventId: try decoder.decode(DesyncPayload.self, from: data).latestEventId)
        case "error": return .error(detail: try decoder.decode(ErrorPayload.self, from: data).detail)
        default: return .unknown(type: type)  // contract: ignore unknown types
        }
    }
}

extension JSONDecoder {
    static var hub: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }
}

// MARK: - Files (~/Collab browse)

struct FileEntry: Decodable, Sendable, Identifiable, Hashable {
    var name: String
    var path: String
    var kind: String    // dir | image | mesh | cad | file
    var size: Int
    var mtime: Double
    var meshPath: String?  // on a cad entry: the renderable STL beside it

    var id: String { path }
    var isDir: Bool { kind == "dir" }
    /// The path a 3D viewer can actually load: STL only — a STEP is a b-rep
    /// needing an OCCT-class kernel (the hub's rule, API.md).
    var renderablePath: String? {
        if kind == "mesh" { return path }
        if kind == "cad" { return meshPath }
        return nil
    }
}

struct FilesResponse: Decodable, Sendable {
    var path: String
    var parent: String?
    var entries: [FileEntry]
}


/// What `/upload` and `/share` say came back.
struct SharedResponse: Decodable, Sendable {
    var shared: String
    var bytes: Int?
}
