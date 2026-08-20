import Foundation

/// The live feed. One connection attempt per stream; the store owns the
/// reconnect-with-backoff loop and the `since` cursor.
enum HubSocket {
    static func frames(config: HubConfig, since: Int?) -> AsyncThrowingStream<Frame, Error> {
        AsyncThrowingStream { continuation in
            var req = URLRequest(url: config.wsURL(since: since))
            req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
            req.timeoutInterval = 40  // hub pings every 30 s of silence; a dead peer must surface

            let task = URLSession.shared.webSocketTask(with: req)
            task.resume()

            let pump = Task {
                while !Task.isCancelled {
                    let message = try await task.receive()
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
                task.cancel(with: .goingAway, reason: nil)
            }

            Task {
                do { try await pump.value; continuation.finish() }
                catch { continuation.finish(throwing: error) }
            }
        }
    }
}
