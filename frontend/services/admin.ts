import { apiGet } from "@/lib/api";
import { getAccessToken } from "@/lib/auth-token";
import type { AdminDashboardResponse } from "@/types/admin";

function auth() {
  return { accessToken: getAccessToken() };
}

export async function fetchAdminDashboard() {
  return apiGet<AdminDashboardResponse>("/api/v1/admin/dashboard", auth());
}
