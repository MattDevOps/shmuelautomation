import express, { type Request, type Response, type NextFunction } from "express";
import QRCode from "qrcode";

import { config } from "./config.js";
import type { WhatsAppDaemon } from "./whatsapp.js";

/** Tiny auth middleware. Every endpoint requires the shared token. */
function requireToken(req: Request, res: Response, next: NextFunction): void {
  const got = req.header("x-daemon-token");
  if (got !== config.daemonAuthToken) {
    res.status(401).json({ error: "unauthorized" });
    return;
  }
  next();
}

export function buildServer(daemon: WhatsAppDaemon): express.Application {
  const app = express();
  app.use(express.json({ limit: "2mb" }));

  // Health is unauthenticated so Fly.io's healthcheck can hit it.
  app.get("/health", (_req, res) => {
    res.json({ ok: true });
  });

  app.use(requireToken);

  app.get("/status", (_req, res) => {
    res.json(daemon.getSnapshot());
  });

  /** Returns the current QR. `format=png` returns a PNG data URL for direct <img> rendering. */
  app.get("/qr", async (req, res) => {
    const snap = daemon.getSnapshot();
    if (snap.state === "connected") {
      res.status(409).json({ error: "already_connected", phone: snap.phone });
      return;
    }
    if (!snap.qr) {
      res.status(202).json({ state: snap.state, qr: null });
      return;
    }
    if (req.query.format === "png") {
      const dataUrl = await QRCode.toDataURL(snap.qr, { width: 320, margin: 1 });
      res.json({ state: snap.state, qrPng: dataUrl });
      return;
    }
    res.json({ state: snap.state, qr: snap.qr });
  });

  app.post("/send-dm", async (req, res) => {
    const { toPhone, message } = req.body ?? {};
    if (typeof toPhone !== "string" || typeof message !== "string") {
      res.status(400).json({ error: "toPhone and message are required" });
      return;
    }
    try {
      const messageId = await daemon.sendDirect(toPhone, message);
      if (messageId === null) {
        res.status(503).json({ error: "not_connected" });
        return;
      }
      res.json({ ok: true, messageId });
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  });

  app.post("/send-group", async (req, res) => {
    const { groupId, message } = req.body ?? {};
    if (typeof groupId !== "string" || typeof message !== "string") {
      res.status(400).json({ error: "groupId and message are required" });
      return;
    }
    try {
      const messageId = await daemon.sendGroup(groupId, message);
      if (messageId === null) {
        res.status(503).json({ error: "not_connected" });
        return;
      }
      res.json({ ok: true, messageId });
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  });

  app.get("/groups", async (_req, res) => {
    try {
      const groups = await daemon.listGroups();
      res.json({ groups });
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  });

  app.post("/reset", async (_req, res) => {
    try {
      await daemon.reset();
      res.json({ ok: true });
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  });

  return app;
}
