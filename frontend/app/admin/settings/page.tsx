"use client";

import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { DangerZone } from "@/components/admin/DangerZone";
import { ActionResultToast } from "@/components/admin/DeletionDialogs";
import { fetchAdminSettings, patchAdminSettings, resetAdminSetting } from "@/services/admin";
import type { AdminSettingItem } from "@/types/admin";

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<AdminSettingItem[]>([]);
  const [draft, setDraft] = useState("");
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [resetKey, setResetKey] = useState<string | null>(null);

  async function reload() {
    const result = await fetchAdminSettings();
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setSettings(result.data.settings);
    const display = result.data.settings.find((s) => s.key === "platform_display_name");
    setDraft(String(display?.value ?? ""));
  }

  useEffect(() => {
    void reload();
  }, []);

  async function save() {
    setToast(null);
    const result = await patchAdminSettings({ platform_display_name: draft });
    if (!result.ok) {
      setToast({ message: result.error, tone: "error" });
      return;
    }
    setToast({ message: `Updated: ${result.data.updated_keys.join(", ")}`, tone: "success" });
    await reload();
  }

  return (
    <div data-testid="admin-settings-page">
      <AdminPageHeader
        title="Platform settings"
        description="Only allowlisted safe settings are editable. Secrets and production security flags are blocked. Use reset to default to remove database overrides."
      />
      <ActionResultToast message={toast?.message ?? null} tone={toast?.tone} />
      <section className="max-w-xl rounded-2xl border border-white/8 bg-slate-900/40 p-4">
        <label className="block text-sm text-slate-300" htmlFor="platform_display_name">
          Platform display name
        </label>
        <input
          id="platform_display_name"
          className="mt-2 w-full rounded-lg border border-white/10 bg-slate-950/70 px-3 py-2 text-sm"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          data-testid="admin-settings-display-name"
        />
        <button
          type="button"
          className="mt-4 rounded-lg bg-cyan-500/20 px-4 py-2 text-sm text-cyan-100 ring-1 ring-cyan-400/30"
          onClick={() => void save()}
          data-testid="admin-settings-save"
        >
          Save
        </button>
      </section>
      <section className="mt-6 rounded-2xl border border-white/8 bg-slate-900/40 p-4">
        <h3 className="mb-3 text-sm font-semibold text-white">All safe settings</h3>
        <ul className="space-y-2 text-sm text-slate-300">
          {settings.map((item) => (
            <li
              key={item.key}
              className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 py-2"
            >
              <span>
                {item.key}
                <span className="ml-2 text-slate-500">
                  {String(item.value)} · {item.source}
                </span>
              </span>
              {item.source === "override" ? (
                <button
                  type="button"
                  className="text-amber-300 hover:underline"
                  data-testid={`admin-settings-reset-${item.key}`}
                  onClick={() => setResetKey(item.key)}
                >
                  Reset to default
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
      <div className="mt-6 max-w-xl">
        <DangerZone description="Reset removes the safe database override and returns to environment/default configuration. This is not a generic delete.">
          <p className="text-xs text-rose-100/60">
            Audit logs cannot be deleted. Unsafe keys remain blocked.
          </p>
        </DangerZone>
      </div>
      <ConfirmDialog
        open={resetKey !== null}
        title="Reset to default"
        message={`Remove the database override for '${resetKey}' and restore the environment/default value.`}
        confirmLabel="Reset to default"
        onCancel={() => setResetKey(null)}
        onConfirm={() => {
          if (!resetKey) return;
          void (async () => {
            const result = await resetAdminSetting(resetKey);
            setResetKey(null);
            setToast(
              result.ok
                ? { message: `Reset ${result.data.updated_keys.join(", ")} to default`, tone: "success" }
                : { message: result.error, tone: "error" },
            );
            await reload();
          })();
        }}
      />
    </div>
  );
}
