import pino from "pino";

import { config } from "./config.js";
import { BackendClient } from "./backend.js";
import { RemoteAuthStore } from "./authStore.js";
import { WhatsAppDaemon } from "./whatsapp.js";
import { buildServer } from "./server.js";

async function main(): Promise<void> {
  const log = pino({
    level: config.logLevel,
    base: { service: "whatsapp-daemon" },
  });

  const backend = new BackendClient(log);
  const authStore = new RemoteAuthStore(backend);
  const daemon = new WhatsAppDaemon(log, authStore, backend);

  const app = buildServer(daemon);
  app.listen(config.port, "0.0.0.0", () => {
    log.info({ port: config.port }, "HTTP API listening");
  });

  // Kick off the Baileys connect — runs forever, reconnects on drop.
  daemon.start().catch((err) => {
    log.fatal({ err }, "daemon.start failed");
    process.exit(1);
  });

  // Graceful shutdown so the in-flight session writes flush.
  const shutdown = async (signal: string) => {
    log.info({ signal }, "shutting down");
    try {
      await authStore.flush();
    } catch {
      // best-effort
    }
    process.exit(0);
  };
  process.on("SIGINT", () => void shutdown("SIGINT"));
  process.on("SIGTERM", () => void shutdown("SIGTERM"));
}

main().catch((err) => {
  console.error("fatal:", err);
  process.exit(1);
});
