import Foundation

/// The liveness label, kept pure so it is a test rather than a running app.
///
/// idle_s is time-since-output-changed sampled live, so on a working pane it
/// reads 0.3, 2.1, 0.2… — floored to seconds it can only ever show 0–2 and
/// looks stuck ("your Working counter just seems to go 0,1,0,1"). So WORKING
/// shows no number (the ellipsis is the signal); a number appears only where
/// it can actually climb: QUIET (working but nothing coming out — the kill
/// decision) and IDLE past 5 s.
enum Liveness: Equatable {
    case working            // producing output; no number
    case quiet(Int)         // working, but output stalled ≥ quietThreshold
    case idle(Int)          // not working, quiet ≥ 5 s
    case dead
    case none               // nothing worth saying (fresh idle, or @host's null idle_s)

    static let quietThresholdS = 10.0
    static let idleThresholdS = 5.0

    static func of(status: String, live: Bool, idleS: Double?) -> Liveness {
        if status == "dead" || !live { return .dead }
        guard let idleS else { return status == "working" ? .working : .none }
        if status == "working" {
            return idleS >= quietThresholdS ? .quiet(Int(idleS)) : .working
        }
        return idleS >= idleThresholdS ? .idle(Int(idleS)) : .none
    }

    var text: String {
        switch self {
        case .working: return "working…"
        case .quiet(let s): return "quiet \(Self.age(s))"
        case .idle(let s): return "idle \(Self.age(s))"
        case .dead: return "dead"
        case .none: return ""
        }
    }

    static func age(_ seconds: Int) -> String {
        switch seconds {
        case ..<60: return "\(seconds)s"
        case ..<3600: return "\(seconds / 60)m"
        default: return "\(seconds / 3600)h \(seconds % 3600 / 60)m"
        }
    }
}
