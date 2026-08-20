import SwiftUI

/// The "+" popover: spawn a new agent pane on talos.
/// The agents that exist on the box. The dropdown is the whole surface —
/// the shell command is an implementation detail the user never sees.
enum Agent: String, CaseIterable, Identifiable {
    case claude = "Claude"
    case codex = "Codex"
    var id: String { rawValue }

    func command(model: ClaudeModel) -> String {
        switch self {
        case .claude: return model == .default ? "claude" : "claude --model \(model.flag)"
        case .codex: return "codex"
        }
    }
}

/// Model aliases the claude CLI accepts. Default = whatever the box's
/// settings say (currently Fable 5); mid-session, typing /model <alias>
/// into the composer switches the running session.
enum ClaudeModel: String, CaseIterable, Identifiable {
    case `default` = "Default"
    case fable = "Fable"
    case opus = "Opus"
    case sonnet = "Sonnet"
    case haiku = "Haiku"
    var id: String { rawValue }
    var flag: String { rawValue.lowercased() }
}

struct NewSessionSheet: View {
    var store: HubStore
    @Environment(\.dismiss) private var dismiss
    @State private var label = ""
    @State private var agent: Agent = .claude
    @State private var model: ClaudeModel = .default
    @State private var cwd = ""
    @State private var failure: String?
    @State private var creating = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("New session").font(.system(size: 15, weight: .semibold))
            Picker("Agent", selection: $agent) {
                ForEach(Agent.allCases) { a in
                    Text(a.rawValue).font(.system(size: 14)).tag(a)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            if agent == .claude {
                Picker("Model", selection: $model) {
                    ForEach(ClaudeModel.allCases) { m in
                        Text(m.rawValue).font(.system(size: 14)).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }
            TextField("Label — what is this session for?", text: $label)
                .font(.system(size: 14))
            TextField("Working directory (optional, e.g. ~/Projects/roam)", text: $cwd)
                .font(.system(size: 14, design: .monospaced))
            if let failure {
                Text(failure).font(.system(size: 14)).foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button(creating ? "Starting…" : "Start \(agent.rawValue)") { create() }
                    .keyboardShortcut(.defaultAction)
                    .disabled(creating)
            }
        }
        .padding(16)
        .frame(width: 420)
    }

    private func create() {
        creating = true
        failure = nil
        Task {
            do {
                try await store.createSession(command: agent.command(model: model),
                                              label: label.trimmed.isEmpty ? nil : label.trimmed,
                                              cwd: cwd.trimmed.isEmpty ? nil : cwd.trimmed)
                dismiss()
            } catch {
                failure = "\(error)"
                creating = false
            }
        }
    }
}

/// Capture: the raw recent output of the pane — "show me the screen".
struct CaptureSheet: View {
    var store: HubStore
    var pane: String
    @Environment(\.dismiss) private var dismiss
    @State private var text: String?
    @State private var failure: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Screen — \(pane)").font(.system(size: 15, weight: .semibold))
                Spacer()
                Button("Refresh") { Task { await load() } }
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            ScrollView([.vertical, .horizontal]) {
                Text(failure ?? text ?? "loading…")
                    .font(.system(size: 14, design: .monospaced))
                    .foregroundStyle(failure == nil ? Color.primary : Color.red)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(minWidth: 640, minHeight: 400)
        }
        .padding(14)
        .task { await load() }
    }

    private func load() async {
        do {
            text = try await store.api.capture(pane: pane).text
            failure = nil
        } catch {
            failure = "capture failed: \(error)"
        }
    }
}
