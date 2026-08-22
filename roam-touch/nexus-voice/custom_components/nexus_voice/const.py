"""Constants for Nexus Voice."""

DOMAIN = "nexus_voice"

CONF_HUB_URL = "hub_url"
CONF_HUB_TOKEN = "hub_token"
CONF_OLLAMA_URL = "ollama_url"
CONF_DEFAULT_SPEAKER = "default_speaker"

DEFAULT_HUB_URL = "http://100.67.237.109:8787"
#: ⚠️ Raw tailnet IP, never a MagicDNS name. argus runs tailscale with
#: `--accept-dns=false` on purpose -- MagicDNS would override the Pi's own
#: resolver and fight dnsmasq -- so `talos.tail39f610.ts.net` does not resolve
#: on this host. Verified 2026-08-21.
DEFAULT_OLLAMA_URL = "http://100.67.237.109:11434"
EMBED_MODEL = "nomic-embed-text"

#: The word that hands an utterance to this agent. Everything before it is
#: HA's own business; everything after it is for the channels.
TRIGGER_WORD = "nexus"

#: How long a spoken answer may take before we stop waiting for it. Nothing
#: cancels the agent -- this only stops us holding a delivery target forever.
DELIVERY_TTL_S = 1800
