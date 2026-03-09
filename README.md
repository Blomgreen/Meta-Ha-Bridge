# jarvis-bridge

A WhatsApp-to-Home Assistant bridge. Send messages to a WhatsApp bot number and get responses from your Home Assistant conversation agent.

## How It Works

1. A **Node.js** subprocess runs [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js) to connect to WhatsApp Web
2. A **Python** orchestrator receives incoming messages, forwards them to the **Home Assistant Conversation API**, and sends the response back via WhatsApp
3. Communication between Python and Node.js uses JSON lines over stdin/stdout

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A phone with WhatsApp (to scan the QR code on first run)
- A Home Assistant instance with a long-lived access token

### Setup

1. **Clone the repo:**
   ```bash
   git clone <repo-url>
   cd Meta-Ha-Bridge
   ```

2. **Edit the config:**
   ```bash
   cp config.yaml config.yaml  # already provided as a template
   ```
   Open `config.yaml` and fill in:
   - `homeassistant.url` — your HA base URL (e.g. `http://192.168.1.100:8123`)
   - `homeassistant.token` — a long-lived access token (HA → Profile → Security)
   - `security.whitelisted_numbers` — phone numbers allowed to use the bot

3. **Start the container:**
   ```bash
   docker compose up --build
   ```

4. **Scan the QR code:**
   On first run, a QR code will appear in the terminal. Open WhatsApp on your phone → Settings → Linked Devices → Link a Device → scan the QR code.

5. **Send a test message:**
   From a whitelisted number, send a message to the bot's WhatsApp number. You should receive a response from Home Assistant.

### Health Check

Send `!ping` to the bot — it will reply `pong` without contacting Home Assistant. This is useful to verify the bridge is running.

## Configuration Reference

See `config.yaml` for all options with inline documentation. Key settings:

| Setting | Description |
|---------|-------------|
| `homeassistant.url` | HA base URL |
| `homeassistant.token` | Long-lived access token |
| `homeassistant.agent_id` | Conversation agent ID (empty = default) |
| `homeassistant.language` | Response language code |
| `whatsapp.bot_phone` | Bot's phone number |
| `whatsapp.qr_method` | `terminal` or `file` |
| `security.whitelisted_numbers` | Allowed sender numbers |
| `security.ignore_non_whitelisted` | Silently ignore (`true`) or reply with error (`false`) |
| `messages.command_prefix` | Only process messages starting with this prefix |
| `messages.health_check_command` | Command that returns "pong" without hitting HA |
| `logging.level` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

## Running Without Docker

```bash
# Install Node dependencies
npm install

# Install Python dependencies
pip install -r requirements.txt

# Run
python3 main.py
```

## Session Persistence

The WhatsApp session is stored in `.wwebjs_auth/`. This directory is volume-mounted in Docker so you only need to scan the QR code once. If you delete this directory, you'll need to re-scan.
