import { request } from "undici";
import type { Logger } from "pino";

import { config } from "./config.js";

/** Persisted Baileys auth state. Opaque to the backend — it just stores the blob. */
export type SessionBlob = {
  // base64-encoded JSON of { creds, keys }
  blob: string;
  updatedAt?: string;
};

function headers(): Record<string, string> {
  const h: Record<string, string> = {
    "X-Daemon-Token": config.daemonAuthToken,
    "Content-Type": "application/json",
  };
  if (config.backendApiKey) {
    h["X-API-Key"] = config.backendApiKey;
  }
  return h;
}

export class BackendClient {
  constructor(private log: Logger) {}

  /** Load the persisted session blob, or null if none exists yet. */
  async loadSession(): Promise<SessionBlob | null> {
    const url = `${config.backendBaseUrl}/whatsapp/session/blob`;
    try {
      const res = await request(url, { method: "GET", headers: headers() });
      if (res.statusCode === 404) return null;
      if (res.statusCode >= 400) {
        this.log.warn({ status: res.statusCode }, "loadSession: backend returned error");
        return null;
      }
      const body = (await res.body.json()) as SessionBlob;
      if (!body || typeof body.blob !== "string") return null;
      return body;
    } catch (err) {
      this.log.warn({ err }, "loadSession failed");
      return null;
    }
  }

  /** Save the session blob. Best-effort; daemon keeps running even if it fails. */
  async saveSession(blob: string): Promise<void> {
    const url = `${config.backendBaseUrl}/whatsapp/session/blob`;
    try {
      const res = await request(url, {
        method: "PUT",
        headers: headers(),
        body: JSON.stringify({ blob }),
      });
      if (res.statusCode >= 400) {
        this.log.warn({ status: res.statusCode }, "saveSession: backend returned error");
      }
    } catch (err) {
      this.log.warn({ err }, "saveSession failed");
    }
  }

  /** Push an inbound message to the backend webhook. */
  async pushInbound(payload: Record<string, unknown>): Promise<void> {
    const url = `${config.backendBaseUrl}/webhooks/whatsapp/inbound`;
    try {
      const res = await request(url, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(payload),
      });
      if (res.statusCode >= 400) {
        const text = await res.body.text();
        this.log.warn({ status: res.statusCode, body: text.slice(0, 300) }, "pushInbound: backend error");
      }
    } catch (err) {
      this.log.warn({ err }, "pushInbound failed");
    }
  }
}
