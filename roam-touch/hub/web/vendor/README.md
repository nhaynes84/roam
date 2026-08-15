# Vendored three.js — **r112** (0.112.1, January 2020)

Pinned, not "outdated". The client is **Chrome 74 (2019) on a Pixel 1**, which is
signature-pinned with no Play Store on the device and therefore cannot ever be
updated. Modern three.js ships as ES2020 modules that engine cannot parse at all.

* `three.min.js` — UMD build, `https://unpkg.com/three@0.112.1/build/three.min.js`
* `STLLoader.js` — `examples/js/loaders/STLLoader.js` from the same release
* `OrbitControls.js` — `examples/js/controls/OrbitControls.js`, same release

Vendored rather than loaded from a CDN because the hub is bound to the tailnet
and the phone has no reason to reach the public internet to look at a bracket.

All three are parsed at `ecmaVersion: 2019` by `tests/test_files_api.py`, which
rejects `?.`, `??` and class fields — so a careless upgrade fails the suite
rather than the wrist. If you bump this, run that test, and read the note at the
top of `web/stl.html` first.

License: MIT (three.js authors). `three.min.js` carries its license header.
