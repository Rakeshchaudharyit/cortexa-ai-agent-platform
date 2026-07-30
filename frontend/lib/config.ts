/**
 * Frontend runtime configuration.
 * API base URL comes only from NEXT_PUBLIC_API_BASE_URL — do not hardcode hosts in components.
 * Keep the hostname identical to the browser URL (do not mix localhost and 127.0.0.1).
 */
export function getApiBaseUrl(): string {
  const value = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!value) {
    return "http://127.0.0.1:18000";
  }
  return value.replace(/\/$/, "");
}
