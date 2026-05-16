import {
  initAuthCreds,
  proto,
  BufferJSON,
  type AuthenticationCreds,
  type AuthenticationState,
  type SignalDataTypeMap,
} from "@whiskeysockets/baileys";

import type { BackendClient } from "./backend.js";

type KeyType = keyof SignalDataTypeMap;
// Baileys' SignalDataTypeMap is a discriminated union that TypeScript can't
// narrow when the key is dynamic. Persist as a loose record; cast at the
// API boundary. The Baileys built-in `useMultiFileAuthState` does the same.
type KeyStore = Record<string, Record<string, unknown>>;

type PersistedShape = {
  creds: AuthenticationCreds;
  keys: KeyStore;
};

/** A Baileys auth state that persists to the FastAPI backend over HTTP.
 *
 * Pattern: load() on startup pulls the latest blob; every mutation calls
 * saveLater() which debounces the next save by 250ms. The blob is the
 * JSON-serialized `{ creds, keys }` object using Baileys' BufferJSON
 * replacers (handles the Buffer/Uint8Array round-trip).
 */
export class RemoteAuthStore {
  private creds: AuthenticationCreds = initAuthCreds();
  private keys: KeyStore = {};
  private saveTimer: NodeJS.Timeout | null = null;

  constructor(private backend: BackendClient) {}

  async load(): Promise<void> {
    const remote = await this.backend.loadSession();
    if (!remote) return;
    try {
      const decoded = Buffer.from(remote.blob, "base64").toString("utf-8");
      const parsed = JSON.parse(decoded, BufferJSON.reviver) as PersistedShape;
      if (parsed.creds) this.creds = parsed.creds;
      if (parsed.keys) this.keys = parsed.keys;
    } catch (err) {
      // Bad blob — start fresh. The pair flow will write a clean one.
      console.warn("authStore.load: failed to parse remote blob; starting fresh", err);
    }
  }

  /** Schedule a save in ~250ms, coalescing rapid writes. */
  private saveLater(): void {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => {
      void this.flush();
    }, 250);
  }

  /** Persist immediately. */
  async flush(): Promise<void> {
    const json = JSON.stringify(
      { creds: this.creds, keys: this.keys },
      BufferJSON.replacer,
    );
    const blob = Buffer.from(json, "utf-8").toString("base64");
    await this.backend.saveSession(blob);
  }

  /** Build a Baileys-compatible AuthenticationState wired to this store. */
  asState(): { state: AuthenticationState; saveCreds: () => Promise<void> } {
    const self = this;
    const state: AuthenticationState = {
      creds: this.creds,
      keys: {
        get: async <T extends KeyType>(type: T, ids: string[]) => {
          const bucket = self.keys[type as string] ?? {};
          const out: { [id: string]: SignalDataTypeMap[T] } = {};
          for (const id of ids) {
            let val: unknown = bucket[id];
            if (type === "app-state-sync-key" && val) {
              val = proto.Message.AppStateSyncKeyData.fromObject(
                val as Record<string, unknown>,
              );
            }
            if (val) out[id] = val as SignalDataTypeMap[T];
          }
          return out;
        },
        set: async (data) => {
          for (const category of Object.keys(data)) {
            const bucket = (self.keys[category] ??= {});
            const updates = (data as Record<string, Record<string, unknown>>)[category] ?? {};
            for (const [id, value] of Object.entries(updates)) {
              if (value == null) {
                delete bucket[id];
              } else {
                bucket[id] = value;
              }
            }
          }
          self.saveLater();
        },
      },
    };
    const saveCreds = async () => {
      // The socket mutates `state.creds` in place; just persist current state.
      self.creds = state.creds;
      self.saveLater();
    };
    return { state, saveCreds };
  }

  /** Reset to a brand-new auth (used by /reset endpoint). */
  async reset(): Promise<void> {
    this.creds = initAuthCreds();
    this.keys = {};
    await this.flush();
  }
}
