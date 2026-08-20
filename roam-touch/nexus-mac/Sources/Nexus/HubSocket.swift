import Foundation
import os

/// The live feed. One connection attempt per stream; the store owns the
/// reconnect-with-backoff loop and the `since` cursor.
enum HubSocket {
    /// The hub emits an app-level ping after every 30 s of silence, so a
    /// healthy socket never goes this long without a frame. A laptop that
    /// slept kills the tunnel WITHOUT closing the TCP stream — receive()
    /// then hangs forever with no error, which looked like "the app hub
    /// went down and never came back". The watchdog turns that silence
    /// into a normal reconnect.
    static let silenceLimitS: TimeInterval = 95

    static func frames(config: HubConfig, since: Int?) -> AsyncThrowingStream<Frame, Error> {
        AsyncThrowingStream { continuation in
            var req = URLRequest(url: config.wsURL(since: since))
            req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
            req.timeoutInterval = 30  // connection establishment only

            let task = URLSession.shared.webSocketTask(with: req)
            task.resume()

            let lastFrameAt = OSAllocatedUnfairLock(initialState: Date())

            let watchdog = Task {
                while !Task.isCancelled {
                    try await Task.sleep(for: .seconds(15))
                    let stale = Date().timeIntervalSince(lastFrameAt.withLock { $0 })
                    if stale > silenceLimitS {
                        task.cancel(with: .goingAway, reason: nil)  // unblocks receive()
                        return
                    }
                }
            }

            let pump = Task {
                while !Task.isCancelled {
                    let message = try await task.receive()
                    lastFrameAt.withLock { $0 = Date() }
                    let data: Data
                    switch message {
                    case .string(let s): data = Data(s.utf8)
                    case .data(let d): data = d
                    @unknown default: continue
                    }
                    let frame = try FrameDecoder.decode(data)
                    if case .error(let detail) = frame {
                        // Bad token: hub sends this then closes 4401. Surface it
                        // as a failure so the loop backs off instead of spinning.
                        continuation.finish(throwing: HubError.http(status: 4401, detail: detail))
                        return
                    }
                    continuation.yield(frame)
                    if case .desync = frame {
                        // Hub closes with 1011 right after; reconnect with ?since=.
                        continuation.finish()
                        return
                    }
                }
            }

            continuation.onTermination = { _ in
                pump.cancel()
                watchdog.cancel()
                task.cancel(with: .goingAway, reason: nil)
            }

            Task {
                defer { watchdog.cancel() }
                do { try await pump.value; continuation.finish() }
                catch { continuation.finish(throwing: error) }
            }
        }
    }
}
