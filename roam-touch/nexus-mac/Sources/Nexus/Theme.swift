import SwiftUI
import AppKit

/// The palette.
///
/// ★ Owner: "ugly as shit bubbles still though, and the left pane is dark and drab …
///   even this input I'm typing in is fucking ugly, and the buttons suck dick."
///
/// Three rules came out of the reskin, and they are the reason this file exists rather
/// than colours being sprinkled through the views:
///
/// 1. ⚠️⚠️ **Liquid Glass is for the NAVIGATION layer only** — Apple is explicit: never
///    apply it to content (lists, bubbles, media), and never nest glass on glass. So the
///    composer bar and its buttons are glass; message bubbles are NOT. Glassing the
///    bubbles is the obvious move and it is the wrong one.
/// 2. ★ **The status hues are spoken for.** cyan = working, orange = quiet, red = dead,
///    green = live. A bubble may not use any of them or it reads as a state. That is why
///    the agent side is graphite + an indigo rail rather than "some other bright colour".
/// 3. ★ **Both sides must differ in HUE and in LUMINANCE.** The old pair (dark blue on
///    darker grey, dark grey on darker grey) differed in neither by enough, so the only
///    real cue was which edge the bubble hugged.
enum Theme {

    /// A colour that resolves per appearance, so light mode is designed rather than
    /// inherited. Everything below goes through this.
    static func dynamic(light: NSColor, dark: NSColor) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
        })
    }

    // MARK: bubbles (content layer — never glass)

    /// His messages: the accent, carried well clear of the ground.
    static let mineFill = dynamic(
        light: NSColor(srgbRed: 0.16, green: 0.44, blue: 0.90, alpha: 0.16),
        dark:  NSColor(srgbRed: 0.29, green: 0.55, blue: 1.00, alpha: 0.30))
    static let mineEdge = dynamic(
        light: NSColor(srgbRed: 0.16, green: 0.44, blue: 0.90, alpha: 0.38),
        dark:  NSColor(srgbRed: 0.45, green: 0.66, blue: 1.00, alpha: 0.55))

    /// The agent: a raised graphite surface. Warm, so it cannot be mistaken for the
    /// blue side, and neutral, so it cannot be mistaken for a status.
    static let agentFill = dynamic(
        light: NSColor(srgbRed: 0.44, green: 0.41, blue: 0.37, alpha: 0.10),
        dark:  NSColor(srgbRed: 0.62, green: 0.58, blue: 0.52, alpha: 0.16))
    static let agentEdge = dynamic(
        light: NSColor(srgbRed: 0.40, green: 0.37, blue: 0.33, alpha: 0.24),
        dark:  NSColor(srgbRed: 0.70, green: 0.65, blue: 0.57, alpha: 0.30))
    /// The leading rail that says "this side is the agent" at a glance, from across
    /// the room, without reading a word of it.
    static let agentRail = dynamic(
        light: NSColor(srgbRed: 0.40, green: 0.31, blue: 0.72, alpha: 1.0),
        dark:  NSColor(srgbRed: 0.60, green: 0.51, blue: 0.95, alpha: 1.0))

    /// Typed straight into tmux: his words, but not from here — his hue, muted.
    static let typedFill = dynamic(
        light: NSColor(srgbRed: 0.16, green: 0.44, blue: 0.90, alpha: 0.07),
        dark:  NSColor(srgbRed: 0.29, green: 0.55, blue: 1.00, alpha: 0.14))
    static let typedEdge = dynamic(
        light: NSColor(srgbRed: 0.16, green: 0.44, blue: 0.90, alpha: 0.20),
        dark:  NSColor(srgbRed: 0.45, green: 0.66, blue: 1.00, alpha: 0.28))

    // MARK: sidebar

    /// "the left pane is dark and drab" — the rail is a flat wash of window colour
    /// behind system vibrancy. A selected row now carries the accent properly and the
    /// unread capsule is the one saturated thing in the column, so the eye lands on it.
    static let railSelection = dynamic(
        light: NSColor(srgbRed: 0.16, green: 0.44, blue: 0.90, alpha: 0.14),
        dark:  NSColor(srgbRed: 0.36, green: 0.60, blue: 1.00, alpha: 0.22))
    static let railHairline = dynamic(
        light: NSColor(white: 0.0, alpha: 0.07),
        dark:  NSColor(white: 1.0, alpha: 0.07))

    // MARK: geometry

    static let bubbleRadius: CGFloat = 12
    static let railWidth: CGFloat = 3
    static let composerRadius: CGFloat = 16
}

/// A bubble with one squared-off corner on the side it belongs to — the cheapest
/// possible "who said this", readable before any colour is processed.
/// InsettableShape, not just Shape, so `strokeBorder` can draw the edge INSIDE the
/// fill. A plain `stroke` centres on the path and spills half a pixel past the
/// background, which on a 1px border is exactly the fuzzy edge that reads as cheap.
struct BubbleShape: InsettableShape {
    var mine: Bool
    var radius: CGFloat = Theme.bubbleRadius
    var inset: CGFloat = 0

    func inset(by amount: CGFloat) -> BubbleShape {
        var copy = self
        copy.inset += amount
        return copy
    }

    func path(in rect: CGRect) -> Path {
        let rect = rect.insetBy(dx: inset, dy: inset)
        return Path(roundedRect: rect,
             cornerRadii: RectangleCornerRadii(
                topLeading: radius,
                bottomLeading: mine ? radius : radius / 4,
                bottomTrailing: mine ? radius / 4 : radius,
                topTrailing: radius))
    }
}
