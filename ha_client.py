"""Home Assistant Conversation API client for Meta HA Bridge."""

import logging
from dataclasses import dataclass

import httpx

from config import HomeAssistantConfig

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0


@dataclass
class ConversationResult:
    """Result from the HA Conversation API."""
    speech: str
    success: bool


class HAClient:
    """Async client for the Home Assistant Conversation API."""

    def __init__(self, config: HomeAssistantConfig):
        self._config = config
        self._url = f"{config.url}/api/conversation/process"
        self._headers = {
            "Authorization": f"Bearer {config.token}",
            "Content-Type": "application/json",
        }

    async def converse(self, text: str, agent_id: str, language: str) -> ConversationResult:
        """Send text to HA Conversation API with per-user agent_id and language."""
        payload: dict = {
            "text": text,
            "language": language,
        }
        if agent_id:
            payload["agent_id"] = agent_id

        logger.debug("HA request: %s", payload)

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(
                    self._url, json=payload, headers=self._headers
                )
                resp.raise_for_status()
        except httpx.ConnectError:
            logger.error("Cannot connect to Home Assistant at %s", self._config.url)
            return ConversationResult(speech="", success=False)
        except httpx.TimeoutException:
            logger.error("Home Assistant request timed out")
            return ConversationResult(speech="", success=False)
        except httpx.HTTPStatusError as exc:
            logger.error("HA returned HTTP %s: %s", exc.response.status_code, exc.response.text)
            return ConversationResult(speech="", success=False)

        data = resp.json()
        logger.debug("HA response: %s", data)

        response = data.get("response", {})
        response_type = response.get("response_type", "")
        speech = response.get("speech", {}).get("plain", {}).get("speech", "")

        if response_type == "error" or not speech:
            logger.warning("HA returned no_intent_match or empty response")
            return ConversationResult(speech="", success=False)

        return ConversationResult(speech=speech, success=True)
