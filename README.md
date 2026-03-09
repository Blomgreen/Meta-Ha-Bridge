# Meta HA Bridge

A WhatsApp-to-Home Assistant bridge that connects your Home Assistant voice assistants to WhatsApp. Send messages to a WhatsApp bot number and get responses from your configured HA conversation agents.

## How It Works

1. Connects to WhatsApp Web via [whatsapp-web.js](https://github.com/pedroslopez/whatsapp-web.js)
2. Receives incoming messages, forwards them to the **Home Assistant Conversation API**, and sends the response back via WhatsApp

## Quick Start

1. **Install dependencies:**
   ```bash
   npm install
   ```

2. **Create your config:**
   ```bash
   cp config.yaml.example config.yaml
   ```
   Fill in your `homeassistant.url`, `homeassistant.token`, and `users`. Phone numbers must include the country code without the `+` prefix (e.g. `4512345678` for a Danish number).

3. **Start the bridge:**
   ```bash
   npm start
   ```

4. **Scan the QR code:**
   On first run, a QR code will appear in the terminal. Open WhatsApp → Settings → Linked Devices → Link a Device → scan the QR code.

5. **Send a test message:**
   From a whitelisted number, send a message to the bot — either in a DM or a group chat.

## DMs and Groups

The bot reads messages from both direct messages and group chats. Authorization is based on the sender's phone number, not the chat type — if a whitelisted user sends a message in a group, the bot will respond using that user's configured HA agent. Messages from non-whitelisted numbers are ignored regardless of where they're sent.

## Health Check

Send `!ping` to the bot — it will reply `pong` without contacting Home Assistant.

## Configuration

See `config.yaml.example` for all options.

## Session Persistence

The WhatsApp session is stored in `.wwebjs_auth/`. You only need to scan the QR code once. If you delete this directory, you'll need to re-scan.
