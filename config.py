"""Configuration loader and validation for Meta HA Bridge."""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"


@dataclass
class HomeAssistantConfig:
    url: str
    token: str
    default_agent_id: str = ""
    default_language: str = "en"


@dataclass
class UserConfig:
    """Per-user settings — each whitelisted number gets one."""
    phone: str
    name: str = ""
    agent_id: str = ""   # falls back to HA default if empty
    language: str = ""   # falls back to HA default if empty


@dataclass
class WhatsAppConfig:
    bot_phone: str
    qr_method: str = "terminal"


@dataclass
class SecurityConfig:
    ignore_non_whitelisted: bool = True


@dataclass
class MessagesConfig:
    command_prefix: str = ""
    health_check_command: str = "!ping"
    no_intent_reply: str = "Sorry, I didn't understand that. Try rephrasing your request."
    error_reply: str = "Home Assistant is currently unavailable. Please try again later."


@dataclass
class AppConfig:
    homeassistant: HomeAssistantConfig
    whatsapp: WhatsAppConfig
    users: dict[str, UserConfig]  # phone number -> UserConfig
    security: SecurityConfig
    messages: MessagesConfig
    log_level: str = "INFO"

    def get_user(self, phone: str) -> UserConfig | None:
        """Look up a user by phone number. Returns None if not whitelisted."""
        return self.users.get(phone)

    def get_agent_id(self, user: UserConfig) -> str:
        """Get the agent_id for a user, falling back to the global default."""
        return user.agent_id or self.homeassistant.default_agent_id

    def get_language(self, user: UserConfig) -> str:
        """Get the language for a user, falling back to the global default."""
        return user.language or self.homeassistant.default_language


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    """Load and validate configuration from a YAML file."""
    if not path.exists():
        print(f"ERROR: Config file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        print("ERROR: Config file is empty or malformed.", file=sys.stderr)
        sys.exit(1)

    # Home Assistant — required fields
    ha_raw = raw.get("homeassistant", {})
    if not ha_raw.get("url") or not ha_raw.get("token"):
        print("ERROR: homeassistant.url and homeassistant.token are required.", file=sys.stderr)
        sys.exit(1)

    ha = HomeAssistantConfig(
        url=ha_raw["url"].rstrip("/"),
        token=ha_raw["token"],
        default_agent_id=ha_raw.get("default_agent_id", ""),
        default_language=ha_raw.get("default_language", "en"),
    )

    # WhatsApp
    wa_raw = raw.get("whatsapp", {})
    wa = WhatsAppConfig(
        bot_phone=str(wa_raw.get("bot_phone", "")),
        qr_method=wa_raw.get("qr_method", "terminal"),
    )

    # Users
    users_raw = raw.get("users", {})
    users: dict[str, UserConfig] = {}
    for phone, settings in users_raw.items():
        phone = str(phone)
        if isinstance(settings, dict):
            users[phone] = UserConfig(
                phone=phone,
                name=settings.get("name", ""),
                agent_id=settings.get("agent_id", ""),
                language=settings.get("language", ""),
            )
        else:
            # Allow bare entries like "1234567890": null
            users[phone] = UserConfig(phone=phone)

    if not users:
        print("WARNING: No users defined — nobody can use the bot.", file=sys.stderr)

    # Security
    sec_raw = raw.get("security", {})
    sec = SecurityConfig(
        ignore_non_whitelisted=sec_raw.get("ignore_non_whitelisted", True),
    )

    # Messages
    msg_raw = raw.get("messages", {})
    msg = MessagesConfig(
        command_prefix=msg_raw.get("command_prefix", "") or "",
        health_check_command=msg_raw.get("health_check_command", "!ping") or "",
        no_intent_reply=msg_raw.get("no_intent_reply", MessagesConfig.no_intent_reply),
        error_reply=msg_raw.get("error_reply", MessagesConfig.error_reply),
    )

    log_level = raw.get("logging", {}).get("level", "INFO")

    config = AppConfig(
        homeassistant=ha,
        whatsapp=wa,
        users=users,
        security=sec,
        messages=msg,
        log_level=log_level,
    )

    logger.info("Configuration loaded — %d user(s) whitelisted", len(users))
    return config
