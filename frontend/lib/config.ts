/**
 * Frontend runtime configuration.
 *
 * The API URL is configured through NEXT_PUBLIC_API_BASE_URL. During local
 * development, browsers treat `localhost` and `127.0.0.1` as different sites.
 * A refresh cookie created for one loopback host is therefore not available to
 * requests sent to the other host when SameSite=Lax is enabled.
 *
 * To keep secure, HttpOnly refresh cookies working after a hard refresh, align
 * only loopback API hosts with the hostname used to open the frontend. Remote
 * and production API hostnames are never rewritten.
 */

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

export function alignLoopbackApiHostname(
  configuredBaseUrl: string,
  browserHostname: string,
): string {
  const normalized = configuredBaseUrl.trim().replace(/\/$/, "");
  if (!normalized || !LOOPBACK_HOSTS.has(browserHostname)) {
    return normalized;
  }

  try {
    const url = new URL(normalized);
    if (!LOOPBACK_HOSTS.has(url.hostname) || url.hostname === browserHostname) {
      return normalized;
    }
    url.hostname = browserHostname;
    return url.toString().replace(/\/$/, "");
  } catch {
    return normalized;
  }
}

export function getApiBaseUrl(): string {
  const configured =
    process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || "http://localhost:18000";

  if (typeof window === "undefined") {
    return configured.replace(/\/$/, "");
  }

  return alignLoopbackApiHostname(configured, window.location.hostname);
}
