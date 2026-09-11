"""The short list of things Nexus can host, and who may see each one.

★ The owner's framing, and it is the reason this module exists rather than a bookmark
folder: *"these sites don't just run all the time and keeping track of them in chrome
is challenging, having dedicated hosts in the app part of nexus makes more sense."*

So a tile is not a link. A tile is a **host**: it knows what the thing is, whether it
is currently up, and how to bring it up. A link to a dead port is exactly the
experience he is complaining about.

★★ VISIBILITY IS ORGANISATIONAL, NOT SECURITY. Owner, 2026-08-23: *"the shared one she
can see, the non shared ones just me ... encountable doesn't need to be locked down, we
infer 'her data / version' based on 'HER nexus'."* Everything here runs as `talos` on a
tailnet-only hub; a determined client could reach a private app's port directly. What
this module buys is a clean shelf per person, which is the thing that was actually
wrong.

⚠️ Keep this module free of FastAPI and of subprocess. Liveness and starting live in
`hub.py`; what is here is the registry and the filtering, so both are a test rather
than a laptop with a browser open.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The owner. Used when a client does not name itself -- his Nexus is the one that
#: predates the whole idea of a second person, so an unnamed client is his.
DEFAULT_USER = "nick"

#: Everyone the shelf knows about. A name not in here gets the shared apps only,
#: which is the right failure: a typo shows too little, never too much.
KNOWN_USERS = ("nick", "jeanne", "phil")

SHARED = "shared"
PRIVATE = "private"

#: The hub's own port. A tile served ON this port is served BY the hub itself,
#: so it is up whenever the hub is answering and has no separate service to start.
HUB_PORT = 8787


@dataclass(frozen=True)
class App:
    """One tile.

    [id] is the shelf key and the URL segment, so it is lowercase and stable --
    renaming one is renaming a route.

    [icon] is an SF Symbol name. The Mac uses it directly; Android maps it through its
    own table rather than shipping Apple's glyphs, so a name unknown to Android falls
    back to a generic tile instead of failing to build.

    [service] is the launchd label to kickstart when the app is not answering, or None
    for something that is always there. This is the half that makes a tile a host.

    ⚠️ [url] is what the CLIENT should open, which on a tailnet is a tailnet address,
    not `127.0.0.1` -- the phone loading `127.0.0.1:3456` gets the phone, not talos.
    `hub.py` fills the host in at request time; the registry stores the port and path.
    """

    id: str
    label: str
    subtitle: str
    icon: str
    #: Port on the hub's own machine, or None for an app the client draws itself.
    port: int | None = None
    path: str = "/"
    #: [SHARED] -- on everyone's shelf. [PRIVATE] -- only on [owner]'s.
    scope: str = PRIVATE
    owner: str = DEFAULT_USER
    service: str | None = None
    #: Drawn by the client instead of loaded (Stream, Files). No port, no service.
    internal: bool = False
    #: ★★ OURS, so the client may send the hub's bearer token to it.
    #:
    #: ⚠️ Default FALSE and it must stay that way. EnCountAble and Vikunja run their
    #: own auth and are not ours to hand a credential to — sending the hub token to a
    #: third-party service would give it the keys to everything. Only a service in
    #: this repo, on this box, gets `authed = True`.
    authed: bool = False

    @property
    def hosted(self) -> bool:
        """Whether this app is a web thing the hub can check on and start."""
        return not self.internal and self.port is not None

    @property
    def self_hosted(self) -> bool:
        """Served BY the hub (its own port), so it is up whenever the hub is and
        has no separate launchd service to start -- unlike a Next.js tile on its
        own port, which the hub kickstarts when the port is dead."""
        return self.port == HUB_PORT


#: ★ The shelf. Deliberately short and hand-maintained: it is a shelf, not an app
#: drawer, and the same rule the wrist launcher already follows (see AppShelf.kt).
#:
#: ⚠️ Adding an entry here puts it on somebody's home screen. That is the review.
REGISTRY: tuple[App, ...] = (
    App(
        id="stream",
        label="Stream",
        subtitle="Open channel",
        icon="dot.radiowaves.left.and.right",
        scope=SHARED,
        internal=True,
    ),
    App(
        id="files",
        label="Files",
        subtitle="Collab drop",
        icon="folder",
        scope=SHARED,
        internal=True,
    ),
    App(
        id="encountable",
        label="EnCountAble",
        subtitle="Health tracking",
        icon="chart.line.uptrend.xyaxis",
        port=3456,
        # ★ Straight to the picker rather than `/`, which only 307s there anyway.
        #   Once the hub carries an identity this becomes the proxied route that sets
        #   `user_id` from the caller and the picker disappears entirely.
        path="/pick-user",
        # ★★ Shared by owner's ruling: *"encountable is shared ... She has an
        #    encountable user already."* One service, two rows -- `users` has had
        #    `1|Nick` and `2|Jeanne` in it since 2026-05-21.
        scope=SHARED,
        service="com.talos.encountable",
    ),
    App(
        id="notes",
        label="Notes",
        subtitle="Project fragments",
        icon="book.pages",
        port=3459,
        # ★ The React explorer, not the plain pages. The HTML version stays at `/` and
        #   is what a WebView with no JavaScript would want; the tile points at the one
        #   built for reading on a big screen.
        path="/app",
        # ★★ The memory fragments, browsable, with the links resolved both ways.
        #    Owner: *"you're doing everything in fragment files anyway, what about
        #    using HTML and the natural linking that falls out of the projects, I'd
        #    like to have a place to browse the project notes as an app."*
        #    396 fragments and 866 `[[links]]` were already a wiki with no reader.
        # ⚠️ PRIVATE: this is the agent's memory of his work, including health and
        #    business notes. Sharing it is a decision, not a default.
        scope=PRIVATE,
        owner=DEFAULT_USER,
        service="com.talos.notes",
        # ⚠️ Was unauthenticated on the tailnet until a second person joined it.
        authed=True,
    ),
    App(
        id="vikunja",
        label="Kanban",
        subtitle="Vikunja boards",
        icon="checklist",
        port=3457,
        # ⚠️ PRIVATE. This is where the agent process tracks his work -- Augment,
        #    Warble, LiveRoasted, Autotrader, Get Rhythm, EnCountAble, Caboose. It is
        #    his operating picture, not a household app, so it stays off her shelf
        #    until he says otherwise.
        scope=PRIVATE,
        owner=DEFAULT_USER,
        service="com.talos.vikunja",
    ),
    App(
        id="schedules",
        label="Schedules",
        subtitle="Automations",
        icon="calendar.badge.clock",
        # ★ Served BY the hub itself (port 8787, `/schedules`), so there is no
        #   separate service to start -- it is up whenever the hub is. The page
        #   drives the /cron API: list, create, enable, run-now, run history.
        port=8787,
        path="/schedules",
        scope=PRIVATE,
        owner=DEFAULT_USER,
        # ⚠️ The page needs the hub token to call /cron. It IS the hub, in-repo,
        #    on this box -- exactly the case `authed` exists for.
        authed=True,
    ),
)


def visible_for(user: str | None, registry: tuple[App, ...] = REGISTRY) -> list[App]:
    """The shelf `user` should see: everything shared, plus what they own.

    ⚠️ An unknown name gets the shared apps and nothing else. Falling back to the
    OWNER's shelf would put his private apps on a stranger's home screen because
    somebody fat-fingered a header.
    """
    name = (user or DEFAULT_USER).strip().lower()
    if name not in KNOWN_USERS:
        return [a for a in registry if a.scope == SHARED]
    return [a for a in registry if a.scope == SHARED or a.owner == name]


def url_for(app: App, host: str) -> str | None:
    """Where the CLIENT should point, given the host it reached the hub on.

    ★★ `host` is the address the request came in on, not a configured one. The Mac
    reaches the hub over Tailscale, the phone over Tailscale, and a local test over
    loopback; each must be handed back its own working address. Hard-coding
    `127.0.0.1` here is the bug where the tile works on talos and nowhere else, and
    hard-coding the tailnet address is the bug where the test suite needs a network.
    """
    if not app.hosted:
        return None
    return f"http://{host}:{app.port}{app.path}"


def to_json(app: App, host: str, live: bool | None = None) -> dict:
    """One tile as the clients consume it.

    `live` is None for an internal app -- there is no port to ask, and reporting
    `false` would dim a tile that works perfectly.
    """
    return {
        "id": app.id,
        "label": app.label,
        "subtitle": app.subtitle,
        "icon": app.icon,
        "internal": app.internal,
        "shared": app.scope == SHARED,
        "url": url_for(app, host),
        "startable": app.service is not None,
        "authed": app.authed,
        "live": live,
    }


def find(app_id: str, registry: tuple[App, ...] = REGISTRY) -> App | None:
    return next((a for a in registry if a.id == app_id), None)
