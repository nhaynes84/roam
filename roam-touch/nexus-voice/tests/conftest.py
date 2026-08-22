"""Make the integration importable without Home Assistant installed.

`nexus_voice/__init__.py` imports `homeassistant.*` at module scope, so a
normal `import nexus_voice.matcher` would drag all of HA into a dev box that
does not have it. Registering the package manually -- with a __path__ but
without executing its __init__ -- lets the pure modules import and keeps their
relative imports working.

The HA-facing modules (`__init__`, `conversation`, `config_flow`) are glue and
are verified on argus, not here. Everything that makes a decision lives in a
module this can reach.
"""

import sys
import types
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1] / "custom_components" / "nexus_voice"

if "nexus_voice" not in sys.modules:
    package = types.ModuleType("nexus_voice")
    package.__path__ = [str(_PKG)]
    sys.modules["nexus_voice"] = package
