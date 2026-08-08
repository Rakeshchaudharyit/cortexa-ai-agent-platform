import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("Phase 12.4 background job operations", () => {
  it("exposes the admin job monitor and navigation", () => {
    const page = readFileSync(join(process.cwd(), "app/admin/jobs/page.tsx"), "utf8");
    const sidebar = readFileSync(join(process.cwd(), "components/admin/AdminSidebar.tsx"), "utf8");
    expect(page).toContain("Run validation job");
    expect(page).toContain("worker_healthy");
    expect(page).toContain("cancelAdminJob");
    expect(page).toContain("requeueAdminJob");
    expect(page).toContain("bulkAdminJobs");
    expect(page).toContain("Dead letter");
    expect(page).toContain("queue_metrics.ready_depth");
    expect(sidebar).toContain('/admin/jobs');
  });
});
