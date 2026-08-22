import Foundation

/// What the link to the hub is doing, in terms a human can act on.
///
/// ★ Owner: "fix you disconnect / reconnect status and UI, it is pretty raw right
/// now." It was raw in a specific way: the failure detail was `"\(error)"`, so the
/// status bar rendered things like
///
///     reconnecting — Error Domain=NSURLErrorDomain Code=-1004 "Could not connect
///     to the server." UserInfo={NSErrorFailingURLStringKey=http://100.67…}
///
/// truncated to one line. That tells him nothing he can use, and it looks broken
/// even when the retry logic is working perfectly.
///
/// The three things worth knowing when a link drops are: **why**, **when it will
/// try again**, and **how to make it try now**. Everything here exists to answer
/// one of those.
enum ConnectionState: Equatable {
    case connecting
    case connected
    case reconnecting(reason: String, attempt: Int, retryAt: Date?)

    var isConnected: Bool { self == .connected }

    /// True once it has failed enough times that something is actually wrong,
    /// rather than the single blip a sleeping laptop always produces.
    var isStruggling: Bool {
        if case .reconnecting(_, let attempt, _) = self { return attempt >= 3 }
        return false
    }
}

/// Turn a transport error into something worth showing a person.
///
/// ⚠️ Deliberately does NOT include the URL, the error domain or the code. Those
/// are for the log; on a status bar they push the useful word off the end of the
/// line. Anything unrecognised falls back to a short generic rather than dumping
/// the raw description — an unknown failure is still "can't reach the hub".
enum ConnectionReason {
    static func describe(_ error: any Error) -> String {
        guard let urlError = error as? URLError else {
            if error is DecodingError { return "hub sent something unreadable" }
            return "connection failed"
        }
        switch urlError.code {
        case .notConnectedToInternet: return "no network"
        case .networkConnectionLost: return "network dropped"
        case .cannotConnectToHost, .cannotFindHost: return "hub not answering"
        case .timedOut: return "timed out"
        case .userAuthenticationRequired: return "hub rejected the token"
        case .secureConnectionFailed: return "TLS failed"
        case .dataNotAllowed: return "network not permitted"
        case .internationalRoamingOff: return "roaming off"
        default: return "connection failed"
        }
    }

    /// "in 4s" / "in 1m 5s" — how long until the next attempt.
    static func countdown(to date: Date, now: Date = Date()) -> String? {
        let remaining = Int(date.timeIntervalSince(now).rounded(.up))
        guard remaining > 0 else { return nil }
        if remaining < 60 { return "in \(remaining)s" }
        return "in \(remaining / 60)m \(remaining % 60)s"
    }

    /// "12s" / "4m" / "2h 10m" — how long the link has been down.
    static func age(_ seconds: Int) -> String {
        switch seconds {
        case ..<60: return "\(seconds)s"
        case ..<3600: return "\(seconds / 60)m"
        default: return "\(seconds / 3600)h \(seconds % 3600 / 60)m"
        }
    }
}
