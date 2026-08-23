import AVFoundation
import Foundation

/// Microphone in, speaker out, at [Wire]'s format.
///
/// ★ Half-duplex is what keeps this small. Because a receiver's PTT INTERRUPTS the
/// feed rather than joining it, capture and playback are never live on the same
/// device at the same moment — so there is no echo path and nothing to cancel.
///
/// ⚠️ The engine resamples. The hardware runs at 44.1 or 48 kHz whatever we ask, so
/// the converter below is not optional politeness — feeding raw hardware frames onto
/// the wire would send 48 kHz samples that every other end plays back as 16 kHz, i.e.
/// everyone sounds three times too slow. The Android end has the same contract.
final class StreamAudio: @unchecked Sendable {

    private let engine = AVAudioEngine()
    private var player: AVAudioPlayerNode?
    private var converter: AVAudioConverter?
    private var capturing = false

    private let wireFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: Wire.sampleRate,
        channels: 1,
        interleaved: true
    )!

    // MARK: capture

    func startCapture(onFrame: @escaping (Data) -> Void) {
        guard !capturing else { return }
        capturing = true

        let input = engine.inputNode
        let hw = input.inputFormat(forBus: 0)
        guard hw.sampleRate > 0 else { capturing = false; return }
        converter = AVAudioConverter(from: hw, to: wireFormat)

        input.installTap(onBus: 0, bufferSize: 1024, format: hw) { [weak self] buffer, _ in
            guard let self, let data = self.convert(buffer) else { return }
            onFrame(data)
        }
        startEngine()
    }

    func stopCapture() {
        guard capturing else { return }
        capturing = false
        engine.inputNode.removeTap(onBus: 0)
        converter = nil
        stopEngineIfIdle()
    }

    private func convert(_ buffer: AVAudioPCMBuffer) -> Data? {
        guard let converter else { return nil }
        let ratio = wireFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: wireFormat, frameCapacity: capacity)
        else { return nil }

        var supplied = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if supplied {
                status.pointee = .noDataNow
                return nil
            }
            supplied = true
            status.pointee = .haveData
            return buffer
        }
        guard error == nil, out.frameLength > 0,
              let channel = out.int16ChannelData else { return nil }
        return Data(bytes: channel[0], count: Int(out.frameLength) * 2)
    }

    // MARK: playback

    func startPlayback() {
        guard player == nil else { return }
        let node = AVAudioPlayerNode()
        engine.attach(node)
        engine.connect(node, to: engine.mainMixerNode, format: wireFormat)
        player = node
        startEngine()
        node.play()
    }

    func play(_ pcm: Data) {
        guard let player, pcm.count >= 2 else { return }
        let frames = AVAudioFrameCount(pcm.count / 2)
        guard let buffer = AVAudioPCMBuffer(pcmFormat: wireFormat, frameCapacity: frames),
              let channel = buffer.int16ChannelData else { return }
        buffer.frameLength = frames
        pcm.withUnsafeBytes { raw in
            guard let base = raw.bindMemory(to: Int16.self).baseAddress else { return }
            channel[0].update(from: base, count: Int(frames))
        }
        player.scheduleBuffer(buffer, completionHandler: nil)
    }

    func stopPlayback() {
        guard let player else { return }
        player.stop()
        engine.detach(player)
        self.player = nil
        stopEngineIfIdle()
    }

    // MARK: engine

    private func startEngine() {
        guard !engine.isRunning else { return }
        // ⚠️ Touching mainMixerNode before start() forces the engine to build a
        //    render graph; without an attached node the start throws.
        _ = engine.mainMixerNode
        do { try engine.start() } catch { /* a dead engine is silence, not a crash */ }
    }

    private func stopEngineIfIdle() {
        if !capturing && player == nil && engine.isRunning {
            engine.stop()
        }
    }
}
