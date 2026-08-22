import json, sys, urllib.request, pathlib
sys.path.insert(0, "custom_components")
from nexus_voice.matcher import Candidate, match

TOK = pathlib.Path("/Users/talos/Projects/roam/roam-touch/hub/hub-token.txt").read_text().strip()
HUB = "http://100.67.237.109:8787"

def embed(text):
    body = json.dumps({"model": "nomic-embed-text", "prompt": text[:6000]}).encode()
    r = urllib.request.Request("http://localhost:11434/api/embeddings", body,
                               {"Content-Type": "application/json"})
    return tuple(json.load(urllib.request.urlopen(r, timeout=30))["embedding"])

def history_blob(pane, label, n=12):
    r = urllib.request.Request(f"{HUB}/channels/%25{pane}/history?limit={n}",
                               headers={"Authorization": f"Bearer {TOK}"})
    d = json.load(urllib.request.urlopen(r, timeout=15))
    ev = d.get("events", d if isinstance(d, list) else [])
    seen, parts = set(), [label]
    for e in ev:
        t = (e.get("summary") or e.get("body") or "")[:400]
        if t and t not in seen:
            seen.add(t); parts.append(t)
    return "\n".join(parts)

PANES = {"42": "Gaggia Build", "45": "Home Automation",
         "1": "◑ Augment things", "24": "◐ Roam Touch rebuild discussion"}
UTTER = [
    "add the OPV test result to the espresso notes",
    "note that the blinds token is dead, home automation",
    "add a card to the augment board",
    "the wrist display font is too small",
    "the jeep brake booster is on order",
]

chans = [Candidate(f"%{p}", l, vector=embed(history_blob(p, l))) for p, l in PANES.items()]
print("=== label + recent history as the embedded document ===")
for u in UTTER:
    m = match(u, chans, target_vector=embed(u))
    print(f"  {u[:46]:48} -> {m.kind:9} {m.label[:30]:32} {m.score:.3f} {m.method}")

from nexus_voice.matcher import cosine
print("\n=== full ranking (semantic only, no lexical) ===")
for u in UTTER:
    tv = embed(u)
    ranked = sorted(((cosine(tv, c.vector), c.label) for c in chans), reverse=True)
    print(f"  {u[:44]:46}")
    for s, l in ranked:
        print(f"        {s:.3f}  {l}")
