#!/usr/bin/env python3
"""jarvis-bridge — WhatsApp to Home Assistant bridge orchestrator."""

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

from config import load_config, AppConfig
from ha_client import HAClient

logger = logging.getLogger("jarvis-bridge")

# Path to the Node.js bridge script
BRIDGE_SCRIPT = Path(__file__).parent / "whatsapp_bridge.js"

# Subprocess restart backoff settings
BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 60.0
BACKOFF_MULTIPLIER = 2.0


class WhatsAppBridge:
    """Manages the Node.js whatsapp-web.js subprocess and message routing."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.ha = HAClient(config.homeassistant)
        self._process: asyncio.subprocess.Process | None = None
        self._running = True
        self._backoff = BACKOFF_INITIAL

    async def start(self):
        """Start the bridge with automatic restart on failure."""
        while self._running:
            try:
                await self._run_subprocess()
            except Exception:
                logger.exception("Subprocess error")

            if not self._running:
                break

            logger.warning("Node process exited. Restarting in %.1fs...", self._backoff)
            await asyncio.sleep(self._backoff)
            self._backoff = min(self._backoff * BACKOFF_MULTIPLIER, BACKOFF_MAX)

    async def stop(self):
        """Gracefully shut down the bridge."""
        self._running = False
        if self._process and self._process.returncode is None:
            logger.info("Terminating Node process...")
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Node process did not exit, killing...")
                self._process.kill()

    async def _run_subprocess(self):
        """Spawn the Node.js bridge and read its output."""
        env_vars = {
            "QR_METHOD": self.config.whatsapp.qr_method,
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        }

        logger.info("Starting Node.js WhatsApp bridge...")
        self._process = await asyncio.create_subprocess_exec(
            "node", str(BRIDGE_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_vars,
        )

        # Read stderr in background for debugging
        asyncio.create_task(self._read_stderr())

        # Read stdout JSON lines
        assert self._process.stdout is not None
        async for line in self._process.stdout:
            line = line.decode().strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Non-JSON output from Node: %s", line)
                continue

            await self._handle_event(event)

        await self._process.wait()
        logger.info("Node process exited with code %s", self._process.returncode)

    async def _read_stderr(self):
        """Log stderr from the Node process."""
        assert self._process and self._process.stderr
        async for line in self._process.stderr:
            text = line.decode().strip()
            if text:
                logger.debug("[node stderr] %s", text)

    async def _handle_event(self, event: dict):
        """Route an event from the Node bridge."""
        event_type = event.get("type", "")

        if event_type == "ready":
            logger.info("WhatsApp client is ready!")
            # Reset backoff on successful connection
            self._backoff = BACKOFF_INITIAL

        elif event_type == "qr":
            logger.info("QR code received — scan it with your phone.")

        elif event_type == "message":
            await self._handle_message(event)

        elif event_type == "error":
            logger.error("Bridge error: %s", event.get("data", "unknown"))

        else:
            logger.debug("Unknown event type: %s", event_type)

    async def _handle_message(self, event: dict):
        """Process an incoming WhatsApp message."""
        sender = event.get("from", "")
        body = event.get("body", "").strip()
        msg_id = event.get("messageId", "")

        if not body:
            return

        # Use the resolved phone number if available (handles LID format),
        # otherwise fall back to extracting from the chat ID
        phone = event.get("phone", "")
        if phone:
            sender_number = phone
        else:
            sender_number = sender.replace("@c.us", "").replace("@s.whatsapp.net", "").replace("@lid", "")

        logger.info("Message from %s (phone: %s): %s", sender, sender_number, body)

        # --- Security: whitelist check (user lookup) ---
        user = self.config.get_user(sender_number)
        if user is None:
            if self.config.security.ignore_non_whitelisted:
                logger.info("Ignoring message from non-whitelisted %s", sender_number)
                return
            else:
                await self._send(sender, "You are not authorized to use this bot.")
                return

        user_label = user.name or sender_number
        logger.info("User matched: %s", user_label)

        # --- Command prefix check ---
        prefix = self.config.messages.command_prefix
        if prefix:
            if not body.startswith(prefix):
                logger.debug("Ignoring message without prefix '%s'", prefix)
                return
            body = body[len(prefix):].strip()

        # --- Health check ---
        hc = self.config.messages.health_check_command
        if hc and body.lower() == hc.lower():
            logger.info("Health check from %s — replying pong", user_label)
            await self._send(sender, "pong")
            return

        # --- Forward to Home Assistant (with per-user agent + language) ---
        agent_id = self.config.get_agent_id(user)
        language = self.config.get_language(user)
        logger.info("Forwarding to HA (agent=%s, lang=%s): %s", agent_id, language, body)
        result = await self.ha.converse(body, agent_id=agent_id, language=language)

        if result.success and result.speech:
            logger.info("HA response: %s", result.speech)
            await self._send(sender, result.speech)
        elif not result.success and not result.speech:
            logger.warning("HA unreachable, sending error reply")
            await self._send(sender, self.config.messages.error_reply)
        else:
            logger.warning("HA returned no match, sending fallback")
            await self._send(sender, self.config.messages.no_intent_reply)

    async def _send(self, to: str, body: str):
        """Send a message via the Node bridge."""
        if not self._process or not self._process.stdin:
            logger.error("Cannot send — Node process not running")
            return

        cmd = json.dumps({"type": "send", "to": to, "body": body}) + "\n"
        self._process.stdin.write(cmd.encode())
        await self._process.stdin.drain()
        logger.info("Sent reply to %s: %s", to, body)


async def main():
    config = load_config()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("jarvis-bridge starting...")
    bridge = WhatsAppBridge(config)

    # Graceful shutdown on SIGINT/SIGTERM
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(bridge.stop()))

    await bridge.start()
    logger.info("jarvis-bridge stopped.")


if __name__ == "__main__":
    asyncio.run(main())
