"""Config flow -- one screen, four fields."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_DEFAULT_SPEAKER,
    CONF_HUB_TOKEN,
    CONF_HUB_URL,
    CONF_OLLAMA_URL,
    DEFAULT_HUB_URL,
    DEFAULT_OLLAMA_URL,
    DOMAIN,
)


class NexusVoiceConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Nexus Voice", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HUB_URL, default=DEFAULT_HUB_URL): str,
                vol.Required(CONF_HUB_TOKEN): str,
                vol.Required(CONF_OLLAMA_URL, default=DEFAULT_OLLAMA_URL): str,
                vol.Optional(CONF_DEFAULT_SPEAKER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
