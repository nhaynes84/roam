import SwiftUI

/// Summary first, details on demand — the house rule for every event.
/// Expanding a truncated event fetches GET /events/{id}, never re-derives.
struct EventRow: View {
    var store: HubStore
    var event: Event
    var delivered: Bool
    @State private var expanded = false
    @State private var fullBody: String?

    var body: some View {
        switch event.kind {
        case "sent": sentRow
        case "receipt": receiptRow
        case "control": chipRow(icon: "stop.circle", text: event.body == "interrupt" ? "interrupted (^C)" : "interrupted (esc)", tint: .orange)
        case "error": errorRow
        case "opened": chipRow(icon: "plus.circle", text: "channel opened — \(event.summary)", tint: .secondary)
        case "closed": chipRow(icon: "xmark.circle", text: "pane closed", tint: .secondary)
        case "notice": noticeRow
        default: expandableRow(role: event.kind == "outcome" ? nil : event.kind)
        }
    }

    // MARK: kinds

    private var sentRow: some View {
        HStack {
            Spacer(minLength: 60)
            VStack(alignment: .trailing, spacing: 3) {
                bodyText(event.body)
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 8).fill(.tint.opacity(0.18)))
                metaLine(trailing: delivered ? "delivered" : nil)
            }
        }
    }

    private var receiptRow: some View {
        // No echo mark = typed at the keyboard; this is the message's only record.
        HStack {
            Spacer(minLength: 60)
            VStack(alignment: .trailing, spacing: 3) {
                bodyText(event.body)
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 8).fill(.secondary.opacity(0.15)))
                metaLine(trailing: "typed in tmux")
            }
        }
    }

    private var noticeRow: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "info.circle").foregroundStyle(.secondary).padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                bodyText(event.body).foregroundStyle(.secondary)
                metaLine(trailing: event.meta?.source)
            }
        }
    }

    private var errorRow: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red).padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                bodyText(event.body).foregroundStyle(.red)
                if let attempted = event.meta?.attempted {
                    Text("not typed: \(attempted)")
                        .font(.system(size: 14)).foregroundStyle(.secondary)
                }
                metaLine(trailing: nil)
            }
        }
    }

    private func chipRow(icon: String, text: String, tint: Color) -> some View {
        HStack(spacing: 5) {
            Image(systemName: icon)
            Text(text).font(.system(size: 14))
        }
        .foregroundStyle(tint)
    }

    /// Outcomes and unknown kinds (contract: render unknown as a plain note).
    private func expandableRow(role: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            if let role {
                Text(role).font(.system(size: 14, weight: .semibold)).foregroundStyle(.secondary)
            }
            if expanded {
                bodyText(fullBody ?? event.body)
            } else {
                Text(event.summary).font(.system(size: 14))
            }
            HStack(spacing: 8) {
                if event.meta?.transcriptSettled == false {
                    Label("may be an earlier block of this turn", systemImage: "questionmark.circle")
                        .font(.system(size: 14)).foregroundStyle(.orange)
                }
                Button(expanded ? "collapse" : expandLabel) {
                    expanded.toggle()
                    if expanded, event.isTruncated, fullBody == nil {
                        Task { fullBody = await store.expand(event).body }
                    }
                }
                .buttonStyle(.link).font(.system(size: 14))
                Spacer()
                metaLine(trailing: nil)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(.quaternary.opacity(0.5)))
    }

    private var expandLabel: String {
        if let chars = event.bodyChars, event.isTruncated { return "expand (\(chars) chars)" }
        return "expand"
    }

    // MARK: pieces

    private func bodyText(_ text: String) -> Text {
        // Inline-only markdown keeps whitespace and never eats code fences.
        if let attributed = try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            return Text(attributed).font(.system(size: 14))
        }
        return Text(text).font(.system(size: 14))
    }

    private func metaLine(trailing: String?) -> some View {
        HStack(spacing: 6) {
            Text(Date(timeIntervalSince1970: event.ts), style: .time)
            if let trailing { Text("· \(trailing)") }
        }
        .font(.system(size: 14))
        .foregroundStyle(.tertiary)
    }
}
