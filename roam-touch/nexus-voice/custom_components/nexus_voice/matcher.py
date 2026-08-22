"""Pick the channel a spoken instruction belongs to.

The voice path says things like *"Nexus, add the OPV test result to the
espresso notes"*. Something has to decide which of the live channels that
belongs in -- or that none of them fit and a new one is needed.

Three facts shape every rule below, all of them learned from live data rather
than assumed:

1. ``cwd`` is a **weak** signal in practice. Panes are spawned in ``$HOME``
   unless someone passes ``cwd``, and on the live hub every single channel
   reported ``/Users/talos``. The field is right in principle and worth
   keeping -- it becomes decisive the moment channels are spawned per project
   -- but nothing may depend on it being set.
2. The **label** is the real signal. It is either the owner's spawn label
   (``@roam_label``, which no agent can overwrite) or Claude's own session
   summary. Live examples: "Gaggia Build", "Home Automation", "Augment
   things".
3. Labels and spoken words do not share vocabulary. "the espresso notes"
   must reach "Gaggia Build". No amount of string comparison does that, which
   is why there is an embedding layer -- and why it is the *last* layer, not
   the first: string equality is free and certain, embeddings cost a network
   round trip and are merely likely.

⚠️ **A wrong match is worse than a question.** Delivering a note into the
wrong agent's conversation corrupts two threads: the note is lost where it was
meant to go and injected where it does not belong. So when the top two
candidates are close, this returns AMBIGUOUS and the voice layer asks. One
extra second of conversation beats a silent misfile.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

#: Words that carry no routing information. "add it to the espresso notes for
#: the roaster project" is about *espresso* and *roaster*; everything else is
#: scaffolding. Kept deliberately small -- an over-eager stop list strips the
#: only distinguishing word out of a short label like "The Cycle".
_FILLER = frozenset(
    """
    a an the to for in on of my our please add note notes noting channel
    project projects thing things stuff about into onto and it that this
    """.split()
)

_PUNCT = re.compile(r"[^\w\s]+")
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, depunctuate, collapse space. No filler removal -- that is
    `keywords`. Two steps because exact matching wants the whole string."""
    return _SPACE.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


def keywords(text: str) -> list[str]:
    """Content words, in order, duplicates kept (repetition is emphasis).

    ⚠️ Falls back to the full word list when filtering would leave nothing. A
    channel labelled "Notes" is a real channel, and a stop list that reduces
    it to the empty set makes it unroutable forever -- found by a test, after
    this module's own docstring warned about exactly that and did it anyway.
    """
    words = normalize(text).split()
    kept = [w for w in words if w not in _FILLER]
    return kept or words


@dataclass(frozen=True)
class Candidate:
    """A channel the utterance could be routed to.

    Mirrors the hub's Channel object but carries only what routing needs, so
    the matcher stays testable without a hub.
    """

    pane_id: str
    label: str
    cwd: str = ""
    live: bool = True
    status: str = "idle"
    #: Cached unit-normalized embedding of `label`, when one has been computed.
    #: Keyed to the label text by the index, so a drifting Claude summary
    #: invalidates itself.
    vector: tuple[float, ...] | None = None


@dataclass(frozen=True)
class Match:
    """What to do with the utterance."""

    kind: str                      # "channel" | "ambiguous" | "spawn"
    pane_id: str | None = None
    label: str = ""
    score: float = 0.0
    method: str = ""               # alias | exact | subset | semantic | none
    alternatives: tuple[str, ...] = field(default=())

    @property
    def routed(self) -> bool:
        return self.kind == "channel"


#: Below this, no candidate is credible and a fresh channel is the answer.
FLOOR = 0.55
#: Two candidates within this of each other are a coin flip -- ask instead.
AMBIGUITY_DELTA = 0.06

# ---------------------------------------------------------------------------
# ★ The embedding layer thresholds a MARGIN, not a score. Measured 2026-08-21
# against live channels and nomic-embed-text, embedding each channel's label
# plus its recent history:
#
#   "the espresso notes"   -> Gaggia Build 0.508, next 0.435   margin 0.073  ✓
#   "wrist display font"   -> Roam Touch   0.431, next 0.367   margin 0.064  ✓
#   "the augment board"    -> Augment      0.425, next 0.375   margin 0.050  ✓
#   "jeep brake booster"   -> (no channel) 0.422, next 0.418   margin 0.004  ✗
#
# Ranking was right every time there was a right answer; the absolute values
# are useless because nomic packs unrelated short text into a narrow 0.3-0.5
# band. An absolute floor at 0.55 rejected all four; one at 0.40 would have
# accepted the jeep. ⚠️ When nothing fits, the scores go FLAT -- that is the
# only reliable "none of these" signal available.
#
# ⚠️ n=5. This threshold fits the measurements; it is not validated by them.
# Log every semantic decision and revisit once there is real traffic.
SEMANTIC_MARGIN = 0.035
#: A sanity floor. Not a discriminator -- just refuses to route on noise.
SEMANTIC_SANITY = 0.33
#: What a confident semantic hit is worth. A flat value, deliberately: the
#: cosine is not calibrated, so it grades a category ("the model is sure"),
#: never a continuum. Sits above FLOOR and below a `subset` string hit -- a
#: guess may rescue a miss, it may never overrule a certainty.
SEMANTIC_CONFIDENT = 0.70


def cosine(a, b) -> float:
    """Cosine similarity. Returns 0.0 for a zero vector rather than raising --
    an unembeddable label is a non-match, not a crash in the voice path."""
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _lexical_score(target: str, cand: Candidate) -> tuple[float, str]:
    """String-only agreement between the spoken target and a candidate.

    Scores are chosen so that certainty outranks likelihood: an exact label
    hit (1.0) can never be beaten by a semantic guess, which is capped below
    it by construction in `match`.
    """
    t_norm, l_norm = normalize(target), normalize(cand.label)
    if not t_norm:
        return 0.0, "none"
    if t_norm == l_norm:
        return 1.0, "exact"

    t_words, l_words = set(keywords(target)), set(keywords(cand.label))
    if not t_words or not l_words:
        return 0.0, "none"

    # Every spoken content word appears in the label ("espresso" -> "espresso
    # water"), or vice versa ("home automation hub" -> "Home Automation").
    if t_words <= l_words or l_words <= t_words:
        return 0.92, "subset"

    overlap = len(t_words & l_words)
    if overlap:
        # Jaccard, deliberately damped: partial word overlap is a hint, not a
        # decision, and must sit below the embedding layer's confident range.
        return 0.5 * overlap / len(t_words | l_words), "overlap"
    return 0.0, "none"


def _cwd_hit(target: str, cand: Candidate) -> bool:
    """Does the pane sit in a directory the utterance names?

    ⚠️ Deliberately NOT a score bonus. It was one, at 0.05, which is smaller
    than `AMBIGUITY_DELTA` -- so the nudge could never separate two tied
    candidates without the pair still reading as ambiguous, and the tiebreak
    was decorative. It is now applied only where a tiebreak is meaningful:
    inside the ambiguous branch. That also keeps the promise in the module
    docstring literally true -- cwd breaks ties and decides nothing else.
    """
    if not cand.cwd:
        return False
    leaf = normalize(cand.cwd.replace("-", " ").replace("_", " ").split("/")[-1])
    if not leaf or leaf == normalize(cand.label):
        return False
    words = set(keywords(target))
    return bool(words and set(leaf.split()) & words)


def _semantic_winner(
    target_vector: tuple[float, ...] | None, live: list[Candidate]
) -> str | None:
    """The pane the embedding model is *confident* about, or None.

    Confidence means it separated a clear leader from the field. See the
    threshold block above for the measurements behind that.
    """
    if not target_vector:
        return None
    sims = sorted(
        ((cosine(target_vector, c.vector), c.pane_id) for c in live if c.vector),
        reverse=True,
    )
    if not sims:
        return None
    top, pane = sims[0]
    if top < SEMANTIC_SANITY:
        return None
    if len(sims) < 2:
        # ⚠️ One candidate means there is no margin to measure, and the
        # measurements say the absolute value cannot stand in for one: an
        # unrelated utterance scored 0.422 while a correct-but-semantic-only
        # match scored 0.431. Overlapping ranges. So with a single channel the
        # embedding abstains entirely and the string layer decides.
        return None
    return pane if top - sims[1][0] >= SEMANTIC_MARGIN else None


def match(
    target: str,
    candidates: list[Candidate],
    target_vector: tuple[float, ...] | None = None,
    floor: float = FLOOR,
) -> Match:
    """Route `target` to a channel, or say it cannot.

    `target_vector` is the utterance's embedding; pass None to run lexically
    only (which is what happens when Ollama is unreachable -- the voice path
    degrades to string matching instead of failing).
    """
    # A dead pane cannot receive: the hub returns 404 on send. Its history is
    # still readable, which is why dead channels exist at all, but they are
    # never a delivery target.
    live = [c for c in candidates if c.live]
    if not live:
        return Match(kind="spawn", method="none")

    semantic_winner = _semantic_winner(target_vector, live)

    scored: list[tuple[float, str, Candidate]] = []
    for cand in live:
        score, method = _lexical_score(target, cand)
        if cand.pane_id == semantic_winner and score < SEMANTIC_CONFIDENT:
            score, method = SEMANTIC_CONFIDENT, "semantic"
        scored.append((min(score, 1.0), method, cand))

    scored.sort(key=lambda s: (-s[0], s[2].pane_id))
    best_score, best_method, best = scored[0]

    if best_score < floor:
        return Match(kind="spawn", score=best_score, method="none")

    runners = [s for s in scored[1:] if best_score - s[0] < AMBIGUITY_DELTA]
    if runners:
        # One last discriminator before bothering him: if exactly one of the
        # tied candidates lives in a directory he just named, that is the one.
        tied = [scored[0], *runners]
        on_cwd = [t for t in tied if _cwd_hit(target, t[2])]
        if len(on_cwd) == 1:
            score, method, cand = on_cwd[0]
            return Match(
                kind="channel",
                pane_id=cand.pane_id,
                label=cand.label,
                score=score,
                method=f"{method}+cwd",
            )
        return Match(
            kind="ambiguous",
            pane_id=best.pane_id,
            label=best.label,
            score=best_score,
            method=best_method,
            alternatives=tuple([best.label] + [r[2].label for r in runners]),
        )

    return Match(
        kind="channel",
        pane_id=best.pane_id,
        label=best.label,
        score=best_score,
        method=best_method,
    )
