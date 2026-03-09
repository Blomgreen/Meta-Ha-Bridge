/**
 * Meta HA Bridge — WhatsApp to Home Assistant voice assistant bridge.
 */

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const yaml = require("js-yaml");
const fs = require("fs");
const path = require("path");

// --- Load config ---

const CONFIG_PATH = path.join(__dirname, "config.yaml");

if (!fs.existsSync(CONFIG_PATH)) {
  console.error(`ERROR: Config file not found: ${CONFIG_PATH}`);
  console.error("Copy config.yaml.example to config.yaml and fill in your values.");
  process.exit(1);
}

const config = yaml.load(fs.readFileSync(CONFIG_PATH, "utf8"));

if (!config?.homeassistant?.url || !config?.homeassistant?.token) {
  console.error("ERROR: homeassistant.url and homeassistant.token are required.");
  process.exit(1);
}

const ha = {
  url: config.homeassistant.url.replace(/\/+$/, ""),
  token: config.homeassistant.token,
  defaultAgentId: config.homeassistant.default_agent_id || "",
  defaultLanguage: config.homeassistant.default_language || "en",
};

const users = {};
for (const [phone, settings] of Object.entries(config.users || {})) {
  users[String(phone)] = {
    phone: String(phone),
    name: settings?.name || "",
    agentId: settings?.agent_id || "",
    language: settings?.language || "",
  };
}

const security = {
  ignoreNonWhitelisted: config.security?.ignore_non_whitelisted ?? true,
};

const messages = {
  commandPrefix: config.messages?.command_prefix || "",
  healthCheckCommand: config.messages?.health_check_command || "!ping",
  noIntentReply: config.messages?.no_intent_reply || "Sorry, I didn't understand that. Try rephrasing your request.",
  errorReply: config.messages?.error_reply || "Home Assistant is currently unavailable. Please try again later.",
};

const logLevel = (config.logging?.level || "INFO").toUpperCase();
const DEBUG = logLevel === "DEBUG";

function log(level, ...args) {
  const levels = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 };
  if ((levels[level] ?? 1) >= (levels[logLevel] ?? 1)) {
    const ts = new Date().toISOString().replace("T", " ").slice(0, 19);
    console.log(`${ts} [${level}] meta-ha-bridge:`, ...args);
  }
}

// --- Home Assistant client ---

async function haConverse(text, agentId, language) {
  const payload = { text, language };
  if (agentId) payload.agent_id = agentId;

  if (DEBUG) log("DEBUG", "HA request:", JSON.stringify(payload));

  try {
    const resp = await fetch(`${ha.url}/api/conversation/process`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ha.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
      log("ERROR", `HA returned HTTP ${resp.status}: ${await resp.text()}`);
      return { speech: "", success: false };
    }

    const data = await resp.json();
    if (DEBUG) log("DEBUG", "HA response:", JSON.stringify(data));

    const response = data.response || {};
    const speech = response.speech?.plain?.speech || "";

    if (response.response_type === "error" || !speech) {
      log("WARNING", "HA returned no_intent_match or empty response");
      return { speech: "", success: false };
    }

    return { speech, success: true };
  } catch (err) {
    if (err.name === "TimeoutError") {
      log("ERROR", "Home Assistant request timed out");
    } else {
      log("ERROR", `Cannot connect to Home Assistant: ${err.message}`);
    }
    return { speech: "", success: false };
  }
}

// --- WhatsApp client with auto-reconnect ---

const BACKOFF_INITIAL = 1000;
const BACKOFF_MAX = 60000;
const BACKOFF_MULTIPLIER = 2;

let client;
let backoff = BACKOFF_INITIAL;
let shuttingDown = false;

function createClient() {
  return new Client({
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
}

function setupClientEvents(client) {
  client.on("qr", (qr) => {
    log("INFO", "QR code received — scan it with your phone.");
    qrcode.generate(qr, { small: true });
  });

  client.on("ready", () => {
    log("INFO", "WhatsApp client is ready!");
    backoff = BACKOFF_INITIAL;
  });

  client.on("message", async (msg) => {
    if (msg.from === "status@broadcast") return;

    const body = msg.body?.trim();
    if (!body) return;

    // Resolve phone number from contact (handles LID format)
    let senderNumber = "";
    try {
      const contact = await msg.getContact();
      senderNumber = contact.number || "";
    } catch {
      // Fall back to extracting from msg.from
    }

    if (!senderNumber) {
      senderNumber = msg.from
        .replace("@c.us", "")
        .replace("@s.whatsapp.net", "")
        .replace("@lid", "");
    }

    log("INFO", `Message from ${msg.from} (phone: ${senderNumber}): ${body}`);

    // Whitelist check
    const user = users[senderNumber];
    if (!user) {
      if (security.ignoreNonWhitelisted) {
        log("INFO", `Ignoring message from non-whitelisted ${senderNumber}`);
        return;
      }
      await msg.reply("You are not authorized to use this bot.");
      return;
    }

    log("INFO", `User matched: ${user.name || senderNumber}`);

    // Command prefix check
    let text = body;
    if (messages.commandPrefix) {
      if (!text.startsWith(messages.commandPrefix)) {
        if (DEBUG) log("DEBUG", `Ignoring message without prefix '${messages.commandPrefix}'`);
        return;
      }
      text = text.slice(messages.commandPrefix.length).trim();
    }

    // Health check
    if (messages.healthCheckCommand && text.toLowerCase() === messages.healthCheckCommand.toLowerCase()) {
      log("INFO", `Health check from ${user.name || senderNumber} — replying pong`);
      await msg.reply("pong");
      return;
    }

    // Forward to Home Assistant
    const agentId = user.agentId || ha.defaultAgentId;
    const language = user.language || ha.defaultLanguage;
    log("INFO", `Forwarding to HA (agent=${agentId}, lang=${language}): ${text}`);

    const result = await haConverse(text, agentId, language);

    if (result.success && result.speech) {
      log("INFO", `HA response: ${result.speech}`);
      await msg.reply(result.speech);
    } else if (!result.success && !result.speech) {
      log("WARNING", "HA unreachable, sending error reply");
      await msg.reply(messages.errorReply);
    } else {
      log("WARNING", "HA returned no match, sending fallback");
      await msg.reply(messages.noIntentReply);
    }
  });

  client.on("disconnected", (reason) => {
    log("ERROR", `Disconnected: ${reason}`);
    scheduleReconnect();
  });

  client.on("auth_failure", (msg) => {
    log("ERROR", `Auth failure: ${msg}`);
    scheduleReconnect();
  });
}

async function startClient() {
  client = createClient();
  setupClientEvents(client);

  try {
    await client.initialize();
  } catch (err) {
    log("ERROR", `Init error: ${err.message}`);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (shuttingDown) return;

  log("WARNING", `Reconnecting in ${(backoff / 1000).toFixed(1)}s...`);
  setTimeout(async () => {
    if (shuttingDown) return;
    try {
      await client.destroy().catch(() => {});
    } catch {}
    backoff = Math.min(backoff * BACKOFF_MULTIPLIER, BACKOFF_MAX);
    startClient();
  }, backoff);
}

// --- Graceful shutdown ---

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  log("INFO", "Shutting down...");
  if (client) {
    client.destroy().then(() => process.exit(0)).catch(() => process.exit(1));
  } else {
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

// --- Start ---

log("INFO", `Meta HA Bridge starting... (${Object.keys(users).length} user(s) whitelisted)`);
startClient();
