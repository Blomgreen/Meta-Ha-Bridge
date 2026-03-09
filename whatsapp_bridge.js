/**
 * whatsapp_bridge.js — WhatsApp Web bridge for Meta HA Bridge.
 *
 * Communicates with the Python orchestrator via JSON lines on stdout/stdin.
 *
 * Outgoing events (stdout):
 *   { "type": "qr",      "data": "<qr_string>" }
 *   { "type": "ready" }
 *   { "type": "message",  "from": "number@c.us", "body": "text", "messageId": "id" }
 *   { "type": "error",    "data": "reason" }
 *
 * Incoming commands (stdin):
 *   { "type": "send", "to": "number@c.us", "body": "text" }
 */

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const fs = require("fs");
const readline = require("readline");

// QR method: "terminal" (default) or "file" — passed via env var
const QR_METHOD = process.env.QR_METHOD || "terminal";

// Send a JSON event to the Python orchestrator
function emit(event) {
  process.stdout.write(JSON.stringify(event) + "\n");
}

// Initialize the WhatsApp client with local session persistence
const client = new Client({
  authStrategy: new LocalAuth({ dataPath: "./.wwebjs_auth" }),
  puppeteer: {
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  },
});

// --- Event handlers ---

client.on("qr", (qr) => {
  emit({ type: "qr", data: qr });

  if (QR_METHOD === "file") {
    // Save QR as a text file (the Python side can also generate an image)
    try {
      const QRCode = require("qrcode");
      QRCode.toFile("qr_code.png", qr, { width: 300 }, (err) => {
        if (err) emit({ type: "error", data: `QR file save failed: ${err.message}` });
      });
    } catch {
      // qrcode npm package not installed — fall back to terminal
      qrcode.generate(qr, { small: true });
    }
  } else {
    qrcode.generate(qr, { small: true });
  }
});

client.on("ready", () => {
  emit({ type: "ready" });
});

client.on("message", async (msg) => {
  // Ignore group messages and status broadcasts
  if (msg.from === "status@broadcast") return;

  // Resolve the actual phone number from the contact,
  // since msg.from may be a LID (Linked ID) instead of a phone number
  let phoneNumber = "";
  try {
    const contact = await msg.getContact();
    phoneNumber = contact.number || "";
  } catch {
    // Fall back to extracting from msg.from if contact lookup fails
  }

  emit({
    type: "message",
    from: msg.from,
    phone: phoneNumber,
    body: msg.body,
    messageId: msg.id._serialized,
  });
});

client.on("disconnected", (reason) => {
  emit({ type: "error", data: `Disconnected: ${reason}` });
  process.exit(1);
});

client.on("auth_failure", (msg) => {
  emit({ type: "error", data: `Auth failure: ${msg}` });
  process.exit(1);
});

// --- Stdin command reader ---

const rl = readline.createInterface({ input: process.stdin });

rl.on("line", async (line) => {
  try {
    const cmd = JSON.parse(line);
    if (cmd.type === "send" && cmd.to && cmd.body) {
      await client.sendMessage(cmd.to, cmd.body);
    }
  } catch (err) {
    emit({ type: "error", data: `Stdin parse error: ${err.message}` });
  }
});

// --- Start ---

client.initialize().catch((err) => {
  emit({ type: "error", data: `Init error: ${err.message}` });
  process.exit(1);
});
