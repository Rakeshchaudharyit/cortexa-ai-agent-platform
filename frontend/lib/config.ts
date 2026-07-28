/**
 * Frontend runtime configuration.
 * API base URL comes only from NEXT_PUBLIC_API_BASE_URL — do not hardcode hosts in components.
 */
export function getApiBaseUrl(): string {
  const value = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!value) {
    return "http://localhost:8000";
  }
  return value.replace(/\/$/, "");
}
