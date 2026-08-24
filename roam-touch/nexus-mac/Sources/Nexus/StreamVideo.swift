import AVFoundation
import CoreImage
import Foundation

/// The Mac's camera, at the same modest settings as the phones.
///
/// ★ Same principle as Android: the compression is done by hardware, not by us.
/// `CIContext.jpegRepresentation` goes through Metal on any Mac made this decade, so
/// the CPU cost is the capture callback and nothing else.
///
/// ⚠️ Deliberately NOT a shared session with StreamAudio's AVAudioEngine. Audio and
/// video are independent here — the floor governs audio only, so a camera must be able
/// to keep running while the microphone is muted by someone else talking.
final class StreamVideo: NSObject, @unchecked Sendable {

    struct Profile {
        var width: Int32 = 640
        var height: Int32 = 480
        var fps: Int = 6
        var quality: CGFloat = 0.7
        var frameInterval: TimeInterval { 1.0 / Double(max(fps, 1)) }
    }

    let profile = Profile()

    private let session = AVCaptureSession()
    private let output = AVCaptureVideoDataOutput()
    private let queue = DispatchQueue(label: "stream-video")
    private let ciContext = CIContext()

    private var onFrame: ((Data) -> Void)?
    private var lastSentAt: TimeInterval = 0
    private var running = false

    /// @return nil on success, or why it failed.
    func start(onFrame: @escaping (Data) -> Void) -> String? {
        guard !running else { return nil }
        self.onFrame = onFrame

        // ⚠️ Asking is not the same as being allowed. A denied camera returns no
        //    frames and reports nothing, which looks exactly like a broken camera —
        //    the same trap the microphone had.
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .denied, .restricted:
            return "camera access denied in System Settings"
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { _ in }
            return "asking for camera access — try again once granted"
        default:
            break
        }

        guard let device = AVCaptureDevice.default(for: .video) else {
            return "no camera on this Mac"
        }
        do {
            let input = try AVCaptureDeviceInput(device: device)
            session.beginConfiguration()
            session.sessionPreset = .vga640x480
            if session.canAddInput(input) { session.addInput(input) }
            output.videoSettings = [
                kCVPixelBufferPixelFormatTypeKey as String:
                    kCVPixelFormatType_32BGRA
            ]
            output.alwaysDiscardsLateVideoFrames = true
            output.setSampleBufferDelegate(self, queue: queue)
            if session.canAddOutput(output) { session.addOutput(output) }
            session.commitConfiguration()
        } catch {
            return "could not open the camera: \(error.localizedDescription)"
        }

        running = true
        // ⚠️ startRunning BLOCKS while the camera warms up. On the main thread that is
        //    a visible hang; the whole reason audio has its own threads.
        queue.async { [session] in session.startRunning() }
        return nil
    }

    func stop() {
        guard running else { return }
        running = false
        onFrame = nil
        queue.async { [session, output] in
            session.stopRunning()
            output.setSampleBufferDelegate(nil, queue: nil)
            session.inputs.forEach { session.removeInput($0) }
            session.outputs.forEach { session.removeOutput($0) }
        }
    }
}

extension StreamVideo: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        // ★ Rate-limit here rather than asking the device for a low frame rate: the
        //   camera is happier at its native rate and dropping what we do not need
        //   costs nothing. Same choice as the Android side, for the same reason.
        let now = CFAbsoluteTimeGetCurrent()
        guard now - lastSentAt >= profile.frameInterval else { return }
        guard let pixels = CMSampleBufferGetImageBuffer(sampleBuffer),
              let onFrame else { return }
        lastSentAt = now

        let image = CIImage(cvPixelBuffer: pixels)
        guard let data = ciContext.jpegRepresentation(
            of: image,
            colorSpace: CGColorSpaceCreateDeviceRGB(),
            options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption:
                        profile.quality]
        ) else { return }
        onFrame(data)
    }
}
