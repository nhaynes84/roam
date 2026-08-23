import SwiftUI

/// Stream: the open channel, and talking back to it.
///
/// ★ OPT-IN. Owner: *"opt in, I have to open it on any device."* Role starts at Off
/// on every launch and nothing captures until he picks one here. The status line is
/// deliberately blunt about a live microphone — a mic you cannot see is the failure
/// mode this screen exists to design out.
struct StreamView: View {
    @Bindable var stream: IntercomClient
    @State private var holding = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Stream").font(.system(size: 26, weight: .bold))

            statusCard

            Text("This device — \(stream.device)")
                .font(.system(size: 14)).foregroundStyle(.secondary)
            Picker("", selection: Binding(
                get: { stream.role },
                set: { stream.setRole($0) })
            ) {
                ForEach(StreamRole.allCases) { role in
                    Text(role.label).tag(role)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            if let notice = stream.notice {
                Label(notice, systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 14)).foregroundStyle(.orange)
            }

            if stream.role == .receiver {
                talkButton
            }

            if let floor = stream.floor, floor.open {
                Text("Listening: \(floor.receivers.isEmpty ? "nobody else" : floor.receivers.joined(separator: ", "))")
                    .font(.system(size: 14)).foregroundStyle(.tertiary)
            }
            Spacer()
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var statusCard: some View {
        let (tint, line) = status
        return HStack(spacing: 10) {
            Circle().fill(tint).frame(width: 12, height: 12)
            Text(line).font(.system(size: 16))
            Spacer()
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 14).fill(tint.opacity(0.14)))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(tint.opacity(0.45), lineWidth: 1))
    }

    private var status: (Color, String) {
        guard stream.role != .off else { return (.gray, "Off — nothing sent or received") }
        guard stream.connected else { return (.gray, "Connecting…") }
        let floor = stream.floor
        if stream.role == .sender {
            if let talker = floor?.talker, talker != stream.device {
                return (.green, "\(talker) is talking — your mic is muted")
            }
            return (.red, "LIVE — this Mac is the open mic")
        }
        if let talker = floor?.talker {
            return talker == stream.device
                ? (.red, "You are talking")
                : (.green, "\(talker) is talking")
        }
        if let sender = floor?.sender { return (.green, "Listening to \(sender)") }
        return (.gray, "No open channel yet")
    }

    /// ⚠️ Release is wired to the drag ENDING, not just to a tap, so sliding the
    /// pointer off the button still lets go. Otherwise the floor stays seized until
    /// the hub's 30 s timeout and the monitor is silent with no explanation.
    private var talkButton: some View {
        let live = stream.floor?.talker == stream.device
        return RoundedRectangle(cornerRadius: 20)
            .fill(live ? Color.red.opacity(0.85)
                       : Color.accentColor.opacity(stream.channelOpen ? 0.25 : 0.08))
            .frame(height: 120)
            .overlay(
                Text(!stream.channelOpen ? "No open channel"
                     : live ? "TALKING — release to listen" : "HOLD TO TALK")
                    .font(.system(size: 18, weight: .bold))
            )
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        guard stream.channelOpen, !holding else { return }
                        holding = true
                        stream.press()
                    }
                    .onEnded { _ in
                        guard holding else { return }
                        holding = false
                        stream.release()
                    }
            )
            .disabled(!stream.channelOpen)
    }
}
