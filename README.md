# Meta HA Bridge

A WhatsApp-to-Home Assistant bridge that connects your Home Assistant voice assistants to WhatsApp. Send messages to a WhatsApp bot number and get responses from your configured HA conversation agents.

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
   cp config.yaml.example config.yaml
   ```
   Fill in your `homeassistant.url`, `homeassistant.token`, and `users`. Phone numbers must include the country code without the `+` prefix (e.g. `4512345678` for a Danish number).

3. **Start the container:**
   ```bash
   docker compose up --build
   ```

4. **Scan the QR code:**
   On first run, a QR code will appear in the terminal. Open WhatsApp → Settings → Linked Devices → Link a Device → scan the QR code.

5. **Send a test message:**
   From a whitelisted number, send a message to the bot — either in a DM or a group chat.

### DMs and Groups

The bot reads messages from both direct messages and group chats. Authorization is based on the sender's phone number, not the chat type — if a whitelisted user sends a message in a group, the bot will respond using that user's configured HA agent. Messages from non-whitelisted numbers are ignored regardless of where they're sent.

### Health Check

Send `!ping` to the bot — it will reply `pong` without contacting Home Assistant.

## Configuration

See `config.yaml.example` for all options.

## Running Without Docker

```bash
npm install
pip install -r requirements.txt
python3 main.py
```

## Session Persistence

The WhatsApp session is stored in `.wwebjs_auth/`. This directory is volume-mounted in Docker so you only need to scan the QR code once.
