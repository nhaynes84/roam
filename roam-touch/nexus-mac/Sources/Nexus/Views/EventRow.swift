import SwiftUI
import MarkdownUI

/// Summary first, details on demand — the house rule for every event.
/// Expanding a truncated event fetches GET /events/{id}, never re-derives.
struct EventRow: View {
    var store: HubStore
    var event: Event
    var delivered: Bool
    /// Owner: "i don't like collapse / expand on macbook, leave it an option for
    /// consistency but default me to expanded mode." So the DEFAULT is expanded and
    /// the toggle stays; `userToggled` is nil until he actually clicks one.
    @AppStorage("defaultExpanded") private var defaultExpanded = true
    @State private var userToggled: Bool?
    @State private var fullBody: String?

    private var expanded: Bool { userToggled ?? defaultExpanded }

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
                    .background(BubbleShape(mine: true).fill(Theme.mineFill))
                    .overlay(BubbleShape(mine: true).strokeBorder(Theme.mineEdge, lineWidth: 1))
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
                    .background(BubbleShape(mine: true).fill(Theme.typedFill))
                    .overlay(BubbleShape(mine: true).strokeBorder(Theme.typedEdge, lineWidth: 1))
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
                Markdown(fullBody ?? event.body)
                    .markdownTheme(.nexus)
                    .textSelection(.enabled)
            } else {
                Text(event.summary).font(.system(size: 14))
            }
            HStack(spacing: 8) {
                if event.meta?.transcriptSettled == false {
                    Label("may be an earlier block of this turn", systemImage: "questionmark.circle")
                        .font(.system(size: 14)).foregroundStyle(.orange)
                }
                Button(expanded ? "collapse" : expandLabel) {
                    userToggled = !expanded
                    Task { await loadFullIfNeeded() }
                }
                .buttonStyle(.link).font(.system(size: 14))
                Spacer()
                metaLine(trailing: nil)
            }
        }
        .padding(.vertical, 10)
        .padding(.leading, 13)
        .padding(.trailing, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(BubbleShape(mine: false).fill(Theme.agentFill))
        .overlay(alignment: .leading) {
            // the rail says "agent" before a single word is read
            Theme.agentRail
                .frame(width: Theme.railWidth)
                .clipShape(.rect(topLeadingRadius: Theme.bubbleRadius,
                                 bottomLeadingRadius: Theme.bubbleRadius / 4))
        }
        .overlay(BubbleShape(mine: false).strokeBorder(Theme.agentEdge, lineWidth: 1))
        .task { await loadFullIfNeeded() }
    }

    private func loadFullIfNeeded() async {
        guard expanded, event.isTruncated, fullBody == nil else { return }
        fullBody = await store.expand(event).body
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


/// House theme: GitHub's block styling at the 14pt floor, monospaced code.
/// Only ever read from SwiftUI body evaluation, hence MainActor.
extension MarkdownUI.Theme {
    @MainActor static let nexus = MarkdownUI.Theme.gitHub
        .text {
            FontSize(14)
        }
        .code {
            FontFamilyVariant(.monospaced)
            FontSize(14)
        }
}
