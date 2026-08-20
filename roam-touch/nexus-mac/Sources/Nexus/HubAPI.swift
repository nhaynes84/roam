import Foundation

/// REST side of the hub contract. One write path: sending is REST only,
/// never a WebSocket frame, so failures report in one place.
struct HubAPI: Sendable {
    var config: HubConfig
    var session: URLSession = .shared

    // Pane ids start with '%', the URL escape character. Contract: strip the
    // leading '%' when building a URL and never think about encoding again.
    private func panePath(_ paneId: String) -> String {
        paneId.hasPrefix("%") ? String(paneId.dropFirst()) : paneId
    }

    private func request(_ method: String, _ path: String,
                         query: [URLQueryItem] = [], body: (any Encodable)? = nil) throws -> URLRequest {
        var parts = URLComponents(url: config.baseURL, resolvingAgainstBaseURL: false)!
        parts.path = path
        if !query.isEmpty { parts.queryItems = query }
        var req = URLRequest(url: parts.url!)
        req.httpMethod = method
        req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONEncoder().encode(body)
        }
        return req
    }

    private func run<T: Decodable>(_ req: URLRequest, as type: T.Type) async throws -> T {
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw HubError.badPayload("no HTTP response") }
        guard (200..<300).contains(http.statusCode) else {
            if http.statusCode == 401 { throw HubError.unauthorised }
            let detail = (try? JSONDecoder.hub.decode(HubErrorBody.self, from: data))?.detail
                ?? String(data: data, encoding: .utf8) ?? ""
            throw HubError.http(status: http.statusCode, detail: detail)
        }
        return try JSONDecoder.hub.decode(T.self, from: data)
    }

    // MARK: - Endpoints

    func health() async throws -> HealthResponse {
        try await run(request("GET", "/health"), as: HealthResponse.self)
    }

    func status() async throws -> StatusResponse {
        try await run(request("GET", "/status"), as: StatusResponse.self)
    }

    func channels(includeArchived: Bool = false) async throws -> ChannelsResponse {
        let q = includeArchived ? [URLQueryItem(name: "include_archived", value: "true")] : []
        return try await run(request("GET", "/channels", query: q), as: ChannelsResponse.self)
    }

    func history(pane: String, limit: Int = 200) async throws -> HistoryResponse {
        try await run(request("GET", "/channels/\(panePath(pane))/history",
                              query: [URLQueryItem(name: "limit", value: String(limit))]),
                      as: HistoryResponse.self)
    }

    struct SendBody: Encodable { var text: String; var enter = true; var origin = "nexus-mac" }
    func send(pane: String, text: String) async throws -> SendResponse {
        try await run(request("POST", "/channels/\(panePath(pane))/send", body: SendBody(text: text)),
                      as: SendResponse.self)
    }

    struct InterruptBody: Encodable { var action: String; var origin = "nexus-mac" }
    /// action: "escape" (stop the agent mid-response) or "interrupt" (C-c).
    /// Never fire control bytes through /send — the hub 400s them now.
    func interrupt(pane: String, action: String = "escape") async throws -> SendResponse {
        try await run(request("POST", "/channels/\(panePath(pane))/interrupt",
                              body: InterruptBody(action: action)),
                      as: SendResponse.self)
    }

    /// The untrimmed event — "expand the details" behind a summary.
    func fullEvent(id: Int) async throws -> Event {
        try await run(request("GET", "/events/\(id)"), as: EventResponse.self).event
    }

    func events(since: Int, limit: Int = 500) async throws -> EventsResponse {
        try await run(request("GET", "/events", query: [
            URLQueryItem(name: "since", value: String(since)),
            URLQueryItem(name: "limit", value: String(limit)),
        ]), as: EventsResponse.self)
    }

    func capture(pane: String, lines: Int = 200) async throws -> CaptureResponse {
        try await run(request("GET", "/channels/\(panePath(pane))/capture",
                              query: [URLQueryItem(name: "lines", value: String(lines))]),
                      as: CaptureResponse.self)
    }

    // MARK: - Presence

    struct PresenceBody: Encodable {
        var source = "nexus-mac"
        var kind = "app"
        var panes: [String]
        var ttlS: Int
        enum CodingKeys: String, CodingKey {
            case source, kind, panes
            case ttlS = "ttl_s"
        }
    }

    /// ⚠️ Only ever the channel actually on screen. `covers_all: true` from a
    /// client with a screen silenced the wearer's arm for a day — a client
    /// showing one channel covers one channel; a list or settings screen covers none.
    func reportPresence(panes: [String], ttlS: Int = 90) async throws {
        struct Ack: Decodable { var source: String? }
        _ = try await run(request("POST", "/presence",
                                  body: PresenceBody(panes: panes, ttlS: ttlS)), as: Ack.self)
    }

    func removePresence() async throws {
        struct Ack: Decodable { var removed: Bool? }
        _ = try await run(request("DELETE", "/presence/nexus-mac"), as: Ack.self)
    }
}
