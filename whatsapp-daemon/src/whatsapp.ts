import makeWASocket, {
  DisconnectReason,
  fetchLatestBaileysVersion,
  isJidGroup,
  isJidUser,
  jidNormalizedUser,
  type WASocket,
  type proto,
} from "@whiskeysockets/baileys";
import type { Logger } from "pino";

import type { BackendClient } from "./backend.js";
import type { RemoteAuthStore } from "./authStore.js";

export type ConnectionState = "disconnected" | "pairing" | "connecting" | "connected";

export type Snapshot = {
  state: ConnectionState;
  phone: string | null;
  qr: string | null;
  lastConnectedAt: string | null;
  lastDisconnectReason: string | null;
};

export type GroupInfo = {
  id: string;
  subject: string;
  participantCount: number;
  isAnnouncement: boolean;
};

/** A long-lived WhatsApp connection. Reconnects on drop. */
export class WhatsAppDaemon {
  private sock: WASocket | null = null;
  private snapshot: Snapshot = {
    state: "disconnected",
    phone: null,
    qr: null,
    lastConnectedAt: null,
    lastDisconnectReason: null,
  };
  private reconnectAttempt = 0;

  constructor(
    private log: Logger,
    private authStore: RemoteAuthStore,
    private backend: BackendClient,
  ) {}

  getSnapshot(): Snapshot {
    return { ...this.snapshot };
  }

  async start(): Promise<void> {
    await this.authStore.load();
    await this.connect();
  }

  private async connect(): Promise<void> {
    const { version } = await fetchLatestBaileysVersion();
    this.log.info({ version }, "starting Baileys socket");

    const { state, saveCreds } = this.authStore.asState();

    const sock = makeWASocket({
      version,
      auth: state,
      printQRInTerminal: false,
      browser: ["Classic Jerusalem", "Desktop", "1.0"],
      // Tone down noisy logs from Baileys itself.
      logger: this.log.child({ component: "baileys" }) as never,
      // Avoid receipt-storm during initial sync.
      markOnlineOnConnect: false,
      syncFullHistory: false,
    });

    this.sock = sock;
    this.snapshot.state = "connecting";

    sock.ev.on("creds.update", () => {
      void saveCreds();
    });

    sock.ev.on("connection.update", (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        this.snapshot.state = "pairing";
        this.snapshot.qr = qr;
        this.log.info("QR code received — pairing required");
      }

      if (connection === "open") {
        this.reconnectAttempt = 0;
        this.snapshot.state = "connected";
        this.snapshot.qr = null;
        this.snapshot.lastConnectedAt = new Date().toISOString();
        this.snapshot.lastDisconnectReason = null;
        const me = sock.user?.id ? jidNormalizedUser(sock.user.id) : null;
        this.snapshot.phone = me ? me.split("@")[0]!.split(":")[0]! : null;
        this.log.info({ phone: this.snapshot.phone }, "WhatsApp connected");
      }

      if (connection === "close") {
        const code =
          (lastDisconnect?.error as { output?: { statusCode?: number } } | undefined)
            ?.output?.statusCode ?? null;
        const reason = code != null ? DisconnectReason[code] ?? String(code) : "unknown";
        this.snapshot.lastDisconnectReason = reason;
        const shouldReconnect = code !== DisconnectReason.loggedOut;
        this.snapshot.state = shouldReconnect ? "connecting" : "disconnected";
        this.log.warn({ reason, shouldReconnect }, "WhatsApp disconnected");
        if (shouldReconnect) {
          const delay = Math.min(30_000, 1000 * 2 ** this.reconnectAttempt);
          this.reconnectAttempt += 1;
          setTimeout(() => {
            void this.connect();
          }, delay);
        } else {
          // Logged out — wipe creds so the next start triggers a fresh pair.
          void this.authStore.reset();
        }
      }
    });

    sock.ev.on("messages.upsert", (m) => {
      // Only forward `notify` events (live incoming), not `append` (history sync).
      if (m.type !== "notify") return;
      for (const msg of m.messages) {
        if (!msg.message || msg.key.fromMe) continue;
        this.handleInbound(msg).catch((err) => {
          this.log.warn({ err }, "handleInbound failed");
        });
      }
    });
  }

  private async handleInbound(msg: proto.IWebMessageInfo): Promise<void> {
    const key = msg.key;
    const remoteJid = key.remoteJid;
    if (!remoteJid) return;

    const isGroup = isJidGroup(remoteJid);
    const senderJid = isGroup ? key.participant ?? remoteJid : remoteJid;
    const fromPhone = senderJid.split("@")[0]?.split(":")[0] ?? null;

    const text = extractText(msg.message);
    const mediaType = extractMediaType(msg.message);

    let groupName: string | null = null;
    if (isGroup && this.sock) {
      try {
        const meta = await this.sock.groupMetadata(remoteJid);
        groupName = meta.subject ?? null;
      } catch {
        // groupMetadata can fail on groups we just joined; ignore.
      }
    }

    await this.backend.pushInbound({
      messageId: key.id,
      fromJid: senderJid,
      fromPhone,
      fromName: msg.pushName ?? null,
      chatJid: remoteJid,
      isGroup,
      groupId: isGroup ? remoteJid : null,
      groupName,
      text,
      mediaType,
      timestamp: Number(msg.messageTimestamp ?? Math.floor(Date.now() / 1000)),
    });
  }

  async sendDirect(toPhone: string, message: string): Promise<string | null> {
    if (!this.sock || this.snapshot.state !== "connected") return null;
    const jid = `${normalizePhone(toPhone)}@s.whatsapp.net`;
    const sent = await this.sock.sendMessage(jid, { text: message });
    return sent?.key.id ?? null;
  }

  async sendGroup(groupId: string, message: string): Promise<string | null> {
    if (!this.sock || this.snapshot.state !== "connected") return null;
    const jid = groupId.includes("@") ? groupId : `${groupId}@g.us`;
    const sent = await this.sock.sendMessage(jid, { text: message });
    return sent?.key.id ?? null;
  }

  async listGroups(): Promise<GroupInfo[]> {
    if (!this.sock || this.snapshot.state !== "connected") return [];
    const groups = await this.sock.groupFetchAllParticipating();
    return Object.values(groups).map((g) => ({
      id: g.id,
      subject: g.subject ?? "",
      participantCount: g.participants?.length ?? 0,
      isAnnouncement: Boolean(g.announce),
    }));
  }

  async reset(): Promise<void> {
    if (this.sock) {
      try {
        await this.sock.logout();
      } catch {
        // ignore — even if Meta rejects, we still nuke local state
      }
      this.sock = null;
    }
    await this.authStore.reset();
    this.snapshot = {
      state: "disconnected",
      phone: null,
      qr: null,
      lastConnectedAt: null,
      lastDisconnectReason: "reset",
    };
    await this.connect();
  }
}

function normalizePhone(s: string): string {
  // Strip non-digits. Caller passes "+972527485568" or "972527485568" or "0527485568".
  // For Israeli local "05..." numbers, callers should pass full international format —
  // we don't guess country codes.
  return s.replace(/\D+/g, "");
}

function extractText(message: proto.IMessage | null | undefined): string | null {
  if (!message) return null;
  return (
    message.conversation ||
    message.extendedTextMessage?.text ||
    message.imageMessage?.caption ||
    message.videoMessage?.caption ||
    message.documentMessage?.caption ||
    null
  );
}

function extractMediaType(message: proto.IMessage | null | undefined): string | null {
  if (!message) return null;
  if (message.imageMessage) return "image";
  if (message.videoMessage) return "video";
  if (message.audioMessage) return "audio";
  if (message.documentMessage) return "document";
  if (message.stickerMessage) return "sticker";
  return null;
}

// Silence the unused-import warning for jidNormalizedUser / isJidUser when only
// one branch happens to use them across small refactors.
void isJidUser;
