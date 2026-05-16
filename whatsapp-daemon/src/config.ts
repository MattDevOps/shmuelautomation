function required(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(`Missing required env var ${name}`);
  }
  return v;
}

export const config = {
  port: Number(process.env.PORT ?? 8787),
  logLevel: process.env.LOG_LEVEL ?? "info",
  daemonAuthToken: required("DAEMON_AUTH_TOKEN"),
  backendBaseUrl: required("BACKEND_BASE_URL").replace(/\/+$/, ""),
  backendApiKey: process.env.BACKEND_API_KEY ?? "",
};

export type Config = typeof config;
