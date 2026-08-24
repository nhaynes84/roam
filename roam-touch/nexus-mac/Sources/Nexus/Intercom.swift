import Foundation
import Observation

/// Stream's wire format, shared with the Android client and the hub.
///
/// ★ 16 kHz mono PCM16, 20 ms frames. No codec on purpose: nothing to negotiate,
/// nothing to install, and ~256 kbit/s is free on a tailnet. This is voice, not music.
/// ⚠️ These four numbers are a CONTRACT with `stream/Intercom.kt` and `hub/intercom.py`.
/// Change one here and the other ends do not fail — they play noise.
enum Wire {
    static let sampleRate = 16_000.0
    static let frameMS = 20
    static let samplesPerFrame = 320
    static let bytesPerFrame = 640
}

enum StreamRole: String, CaseIterable, Identifiable {
    case off, sender, receiver
    var id: String { rawValue }

    var label: String {
        switch self {
        case .off: return "Off"
        case .sender: return "Open channel"
        case .receiver: return "Receiver"
        }
    }
}

/// Who the hub says owns the channel. The hub is the authority — see `press()`.
struct Floor: Decodable, Equatable, Sendable {
    var open: Bool
    var sender: String?
    var talker: String?
    var holder: String?
    var receivers: [String]
    /// Devices whose camera is live. NOT floor-governed — video has no echo.
    var video: [String] = []

    func videoLive(_ device: String) -> Bool { video.contains(device) }
    func micLive(_ device: String) -> Bool { holder == device }
    func shouldPlay(_ device: String) -> Bool { holder != nil && holder != device }
}

/// The Stream client.
///
/// ★★ THE HUB DECIDES, NOT THIS APP. His framing: *"same as a multiplayer hosting
/// server for any video game, the server makes core timing decisions, not any
/// individual device."* Pressing the button does not open the microphone; it sends
/// `press` and waits for the [Floor] that comes back. Two devices that each decided
/// locally would eventually both be live, and that is a howl in a real house.
@MainActor @Observable
final class IntercomClient {
    private(set) var role: StreamRole = .off
    private(set) var floor: Floor?
    private(set) var connected = false
    private(set) var notice: String?
    /// Whether THIS Mac's camera is live, per the hub.
    private(set) var videoOut = false
    /// The newest frame from whoever is showing a picture.
    private(set) var frame: Data?
    private(set) var videoNotice: String?

    /// Named after the machine, so the floor snapshot is readable by a human.
    let device: String

    private let config: HubConfig
    private let audio = StreamAudio()
    private let video = StreamVideo()
    private var task: URLSessionWebSocketTask?
    private var videoTask: URLSessionWebSocketTask?
    private var pump: Task<Void, Never>?
    private var videoPump: Task<Void, Never>?

    init(config: HubConfig, device: String = Host.current().localizedName ?? "mac") {
        self.config = config
        self.device = device.replacingOccurrences(of: " ", with: "-")
    }

    var channelOpen: Bool { floor?.open == true }

    // MARK: role

    /// ★ OFF is the launch default and the panic button. A Mac that reboots must not
    /// come back with a live microphone in whatever room it is sitting in.
    func setRole(_ next: StreamRole) {
        guard next != role else { return }
        teardown()
        role = next
        notice = nil
        floor = nil
        guard next != .off else { return }
        connect(as: next)
    }

    private func connect(as role: StreamRole) {
        var comps = URLComponents(url: config.baseURL, resolvingAgainstBaseURL: false)!
        comps.scheme = config.baseURL.scheme == "https" ? "wss" : "ws"
        comps.path = "/intercom"
        comps.queryItems = [
            .init(name: "device", value: device),
            .init(name: "role", value: role == .sender ? "sender" : "receiver"),
            .init(name: "token", value: config.token),
        ]
        let socket = URLSession.shared.webSocketTask(with: comps.url!)
        socket.resume()
        task = socket
        connected = true
        pump = Task { await receiveLoop(socket) }

        // ⚠️ Video gets its OWN socket. A frame is orders of magnitude bigger than a
        //    640-byte audio frame and would head-of-line block the speech behind it.
        var v = comps
        v.path = "/intercom/video"
        v.queryItems = [
            .init(name: "device", value: device),
            .init(name: "token", value: config.token),
        ]
        let vsocket = URLSession.shared.webSocketTask(with: v.url!)
        vsocket.resume()
        videoTask = vsocket
        videoPump = Task { await videoLoop(vsocket) }
    }

    private func receiveLoop(_ socket: URLSessionWebSocketTask) async {
        while !Task.isCancelled {
            do {
                switch try await socket.receive() {
                case .data(let pcm):
                    audio.play(pcm)
                case .string(let text):
                    handle(text)
                @unknown default:
                    break
                }
            } catch {
                connected = false
                if role != .off { notice = "stream link dropped" }
                return
            }
        }
    }

    private func videoLoop(_ socket: URLSessionWebSocketTask) async {
        while !Task.isCancelled {
            do {
                if case .data(let jpeg) = try await socket.receive() { frame = jpeg }
            } catch {
                return
            }
        }
    }

    private func handle(_ text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let kind = obj["type"] as? String else { return }
        switch kind {
        case "floor":
            if let decoded = try? JSONDecoder().decode(Floor.self, from: data) {
                apply(decoded)
            }
        case "denied":
            notice = obj["detail"] as? String
        case "error":
            notice = obj["detail"] as? String
        default:
            break
        }
    }

    /// ⚠️ Capture and playback follow the HUB's answer, never which button is down.
    /// A press the hub refused (someone else got there first) must not open this mic,
    /// and letting the answer decide is the only way to guarantee that.
    private func apply(_ next: Floor) {
        floor = next
        connected = true

        // ⚠️ The camera follows the HUB, never a local toggle — a receiver may switch
        //    this Mac's camera on remotely, so the answer that comes back is the
        //    authority. Same rule the microphone follows.
        let wantVideo = next.videoLive(device)
        if wantVideo != videoOut {
            videoOut = wantVideo
            if wantVideo {
                videoNotice = video.start { [weak self] jpeg in
                    self?.videoTask?.send(.data(jpeg)) { _ in }
                }
            } else {
                video.stop()
                videoNotice = nil
            }
        }

        if next.shouldPlay(device) { audio.startPlayback() } else { audio.stopPlayback() }

        if next.micLive(device) {
            audio.startCapture { [weak self] frame in
                self?.send(frame)
            }
        } else {
            audio.stopCapture()
        }
    }

    // MARK: talking

    func press() {
        send(text: #"{"type":"press"}"#)
    }

    func release() {
        send(text: #"{"type":"release"}"#)
    }

    /// Ask the hub to turn a camera on. Default target is the sender — "receiver can
    /// turn on sender video" is the common case and should not need naming.
    func setVideo(_ on: Bool, target: String? = nil) {
        let t = target.map { #","target":"\#($0)""# } ?? ""
        send(text: #"{"type":"video","on":\#(on)\#(t)}"#)
    }

    private func send(text: String) {
        task?.send(.string(text)) { [weak self] error in
            guard let error else { return }
            Task { @MainActor in self?.notice = "\(error.localizedDescription)" }
        }
    }

    /// Audio out. The hub drops it if this device does not hold the floor — that is
    /// the safety net for a laggy release. Gating locally too is what keeps it quiet;
    /// gating ONLY locally is what would eventually open two mics at once.
    private func send(_ pcm: Data) {
        task?.send(.data(pcm)) { _ in }
    }

    private func teardown() {
        pump?.cancel(); pump = nil
        videoPump?.cancel(); videoPump = nil
        video.stop()
        videoTask?.cancel(with: .goingAway, reason: nil)
        videoTask = nil
        frame = nil
        videoOut = false
        audio.stopCapture()
        audio.stopPlayback()
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        connected = false
    }

    // ⚠️ No deinit teardown: the actor-isolated socket cannot be touched from a
    //    nonisolated deinit. setRole(.off) is the teardown path, and the store holds
    //    this for the app's lifetime anyway — a leaked socket at exit is closed by
    //    the process ending, an isolation violation is a compile error.
}
